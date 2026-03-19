"""
策略模块测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import pandas as pd
import numpy as np

from src.strategy.technical import TechnicalStrategy, MACDStrategy, MaCrossoverStrategy, RSIStrategy
from src.strategy.multi_factor import MultiFactorStrategy
from src.strategy.base_strategy import Signal


class TestTechnicalIndicators(unittest.TestCase):
    """测试技术指标计算"""

    def setUp(self):
        # 创建测试数据
        np.random.seed(42)
        self.prices = pd.Series(np.random.randn(100).cumsum() + 100)

    def test_ma_calculation(self):
        """测试均线计算"""
        from src.utils.helpers import calculate_ma

        ma_df = calculate_ma(self.prices, [5, 10, 20])
        self.assertIn('ma5', ma_df.columns)
        self.assertIn('ma10', ma_df.columns)
        self.assertIn('ma20', ma_df.columns)
        self.assertEqual(len(ma_df), len(self.prices))

    def test_rsi_calculation(self):
        """测试 RSI 计算"""
        from src.utils.helpers import calculate_rsi

        rsi = calculate_rsi(self.prices, 14)
        self.assertEqual(len(rsi), len(self.prices))
        # RSI 应该在 0-100 之间
        self.assertTrue((rsi.dropna() >= 0).all())
        self.assertTrue((rsi.dropna() <= 100).all())

    def test_macd_calculation(self):
        """测试 MACD 计算"""
        from src.utils.helpers import calculate_macd

        macd = calculate_macd(self.prices, 12, 26, 9)
        self.assertIn('dif', macd.columns)
        self.assertIn('dea', macd.columns)
        self.assertIn('macd', macd.columns)
        self.assertEqual(len(macd), len(self.prices))


class TestTechnicalStrategy(unittest.TestCase):
    """测试技术指标策略"""

    def setUp(self):
        self.strategy = TechnicalStrategy()
        self.strategy.on_init()

        # 创建模拟数据
        self.test_data = {
            '000001.SZ': {
                'open': 10.0,
                'high': 10.5,
                'low': 9.8,
                'close': 10.2,
                'vol': 1000000,
                'amount': 10200000
            }
        }
        self.current_date = '20240101'

    def test_on_bar(self):
        """测试 K 线回调"""
        # 多次调用以积累历史数据
        for i in range(30):
            date = f'20240{1 + i // 30:02d}{i % 30 + 1:02d}'
            signals = self.strategy.on_bar(self.test_data, date)
            self.assertIsInstance(signals, list)

    def test_signal_generation(self):
        """测试信号生成"""
        # 积累足够的数据
        for i in range(50):
            date = f'202401{i % 30 + 1:02d}'
            self.strategy.on_bar(self.test_data, date)

        # 检查价格历史
        self.assertIn('000001.SZ', self.strategy.price_history)
        self.assertGreater(len(self.strategy.price_history['000001.SZ']), 20)


class TestMACDStrategy(unittest.TestCase):
    """测试 MACD 策略"""

    def setUp(self):
        self.strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        self.strategy.on_init()

    def test_golden_cross(self):
        """测试金叉信号"""
        # 创建上升趋势数据
        data = []
        for i in range(50):
            data.append({
                'open': 10 + i * 0.1,
                'high': 10.5 + i * 0.1,
                'low': 9.5 + i * 0.1,
                'close': 10.2 + i * 0.15,
                'vol': 1000000
            })

        signals = []
        for i, bar in enumerate(data):
            date = f'202401{i + 1:02d}'
            signals = self.strategy.on_bar({'000001.SZ': bar}, date)

        # 应该有买入信号
        buy_signals = [s for s in signals if s.direction == 'buy']
        # MACD 策略在趋势市场应该产生信号

    def test_death_cross(self):
        """测试死叉信号"""
        # 创建下降趋势数据
        data = []
        for i in range(50):
            data.append({
                'open': 15 - i * 0.1,
                'high': 15.5 - i * 0.1,
                'low': 14.5 - i * 0.1,
                'close': 15.2 - i * 0.15,
                'vol': 1000000
            })

        for i, bar in enumerate(data):
            date = f'202401{i + 1:02d}'
            signals = self.strategy.on_bar({'000001.SZ': bar}, date)


class TestMaCrossoverStrategy(unittest.TestCase):
    """测试均线交叉策略"""

    def setUp(self):
        self.strategy = MaCrossoverStrategy(short_period=5, long_period=20)
        self.strategy.on_init()

    def test_signal_generation(self):
        """测试信号生成"""
        # 创建模拟数据
        np.random.seed(42)
        prices = np.random.randn(50).cumsum() + 100

        signals_count = {'buy': 0, 'sell': 0}

        for i, price in enumerate(prices):
            bar = {
                'open': price,
                'high': price + 1,
                'low': price - 1,
                'close': price,
                'vol': 1000000
            }
            date = f'202401{i + 1:02d}'
            signals = self.strategy.on_bar({'000001.SZ': bar}, date)

            for signal in signals:
                signals_count[signal.direction] += 1

        # 应该产生一些信号
        total_signals = signals_count['buy'] + signals_count['sell']
        self.assertGreater(total_signals, 0)


class TestMultiFactorStrategy(unittest.TestCase):
    """测试多因子策略"""

    def setUp(self):
        self.strategy = MultiFactorStrategy(top_n=5, rebalance_days=5)
        self.strategy.on_init()

    def test_factor_calculation(self):
        """测试因子计算"""
        # 测试单个股票的因子计算
        factors = self.strategy._calculate_factor_values('600000.SH', '20240101')
        self.assertIsInstance(factors, dict)

    def test_stock_ranking(self):
        """测试股票排序"""
        # 创建测试评分
        scores = {
            '000001.SZ': 0.8,
            '000002.SZ': 0.6,
            '000003.SZ': 0.9,
            '000004.SZ': 0.5
        }

        # 测试排序
        top_stocks = self.strategy.rank_stocks(scores, top_n=2)
        self.assertEqual(len(top_stocks), 2)
        self.assertEqual(top_stocks[0], '000003.SZ')  # 最高分

    def test_equal_weight(self):
        """测试等权重配置"""
        stocks = ['A', 'B', 'C']
        weights = self.strategy.equal_weight(stocks)

        self.assertEqual(len(weights), 3)
        expected_weight = 1.0 / 3
        for weight in weights.values():
            self.assertAlmostEqual(weight, expected_weight)


if __name__ == "__main__":
    unittest.main(verbosity=2)
