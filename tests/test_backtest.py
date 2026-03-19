"""
回测模块测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import pandas as pd
import numpy as np

from src.backtest.engine import BacktestEngine, BacktestResult, Order, Position
from src.backtest.performance import PerformanceAnalyzer, PerformanceMetrics
from src.backtest.analyzer import AttributionAnalyzer, AttributionResult
from src.strategy.technical import MaCrossoverStrategy


class TestBacktestEngine(unittest.TestCase):
    """测试回测引擎"""

    def setUp(self):
        self.engine = BacktestEngine(
            initial_capital=1000000,
            commission_rate=0.0003,
            stamp_tax_rate=0.001,
            slippage_rate=0.001
        )
        self.strategy = MaCrossoverStrategy(short_period=5, long_period=20)

    def _create_test_data(self, days=100):
        """创建测试数据"""
        np.random.seed(42)

        # 生成价格序列
        prices = 100 + np.random.randn(days).cumsum()

        data = []
        for i, price in enumerate(prices):
            data.append({
                'ts_code': '000001.SZ',
                'trade_date': pd.Timestamp(2024, 1, 1) + pd.Timedelta(days=i),
                'open': price,
                'high': price + np.random.rand(),
                'low': price - np.random.rand(),
                'close': price,
                'vol': 1000000,
                'amount': price * 1000000,
                'pre_close': price,
                'change': 0,
                'pct_chg': 0
            })

        df = pd.DataFrame(data)
        return {'000001.SZ': df}

    def test_initialization(self):
        """测试引擎初始化"""
        self.assertEqual(self.engine.initial_capital, 1000000)
        self.assertEqual(self.engine.capital, 1000000)
        self.assertEqual(len(self.engine.positions), 0)

    def test_reset(self):
        """测试重置功能"""
        self.engine.capital = 500000
        self.engine.reset()
        self.assertEqual(self.engine.capital, 1000000)

    def test_calculate_transaction_cost(self):
        """测试交易成本计算"""
        # 买入
        commission, stamp_tax, slippage = self.engine.calculate_transaction_cost(
            'buy', 10.0, 1000
        )
        self.assertGreater(commission, 0)
        self.assertEqual(stamp_tax, 0)  # 买入不收印花税
        self.assertGreater(slippage, 0)

        # 卖出
        commission, stamp_tax, slippage = self.engine.calculate_transaction_cost(
            'sell', 10.0, 1000
        )
        self.assertGreater(commission, 0)
        self.assertGreater(stamp_tax, 0)  # 卖出收印花税
        self.assertGreater(slippage, 0)

    def test_load_data(self):
        """测试数据加载"""
        data = self._create_test_data()
        loaded = self.engine.load_data(
            ts_codes=['000001.SZ'],
            start_date='20240101',
            end_date='20240430'
        )
        self.assertIn('000001.SZ', loaded)
        self.assertGreater(len(self.engine.trade_dates), 0)

    def test_run_backtest(self):
        """测试运行回测"""
        data = self._create_test_data(100)

        self.engine.set_strategy(self.strategy)
        self.engine.load_data(
            ts_codes=['000001.SZ'],
            start_date='20240101',
            end_date='20240430'
        )

        result = self.engine.run(data)

        self.assertIsInstance(result, BacktestResult)
        self.assertGreater(len(result.equity_curve), 0)

    def test_generate_result(self):
        """测试结果生成"""
        # 手动添加一些测试数据
        self.engine.equity_curve = [
            {'date': '20240101', 'capital': 1000000, 'position_value': 0, 'total_equity': 1000000},
            {'date': '20240102', 'capital': 900000, 'position_value': 150000, 'total_equity': 1050000},
            {'date': '20240103', 'capital': 800000, 'position_value': 280000, 'total_equity': 1080000},
        ]
        self.engine.daily_returns = [0.0, 0.05, 0.028]

        result = self.engine.generate_result()

        self.assertGreater(result.total_return, 0)
        self.assertGreater(result.final_capital, self.engine.initial_capital)


class TestPerformanceAnalyzer(unittest.TestCase):
    """测试绩效分析器"""

    def setUp(self):
        self.analyzer = PerformanceAnalyzer(risk_free_rate=0.02)

    def _create_test_result(self):
        """创建测试回测结果"""
        result = BacktestResult()
        result.total_return = 0.15
        result.annual_return = 0.18
        result.sharpe_ratio = 1.5
        result.max_drawdown = 0.08
        result.win_rate = 0.55
        result.profit_factor = 1.8
        result.total_trades = 50
        result.winning_trades = 28
        result.losing_trades = 22
        result.avg_profit = 2000
        result.avg_loss = -1200
        result.final_capital = 1150000

        # 创建权益曲线
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        equity = 1000000 + np.random.randn(100).cumsum() * 1000
        result.equity_curve = pd.DataFrame({
            'date': dates,
            'total_equity': equity
        })

        # 创建收益率序列
        result.daily_returns = pd.Series(np.random.randn(100) * 0.01)

        return result

    def test_analyze(self):
        """测试绩效分析"""
        result = self._create_test_result()
        metrics = self.analyzer.analyze(result)

        self.assertIsInstance(metrics, PerformanceMetrics)
        self.assertAlmostEqual(metrics.total_return, result.total_return, places=2)
        self.assertAlmostEqual(metrics.sharpe_ratio, result.sharpe_ratio, places=1)
        self.assertAlmostEqual(metrics.max_drawdown, result.max_drawdown, places=2)

    def test_generate_report(self):
        """测试报告生成"""
        result = self._create_test_result()
        report = self.analyzer.generate_report(result)

        self.assertIsInstance(report, str)
        self.assertIn("绩效分析报告", report)
        self.assertIn("夏普比率", report)
        self.assertIn("最大回撤", report)

    def test_calculate_alpha_beta(self):
        """测试 Alpha 和 Beta 计算"""
        np.random.seed(42)
        portfolio_returns = pd.Series(np.random.randn(100) * 0.01)
        market_returns = pd.Series(np.random.randn(100) * 0.01)

        alpha, beta = self.analyzer.calculate_alpha_beta(portfolio_returns, market_returns)

        self.assertIsInstance(alpha, float)
        self.assertIsInstance(beta, float)


class TestAttributionAnalyzer(unittest.TestCase):
    """测试归因分析器"""

    def setUp(self):
        self.analyzer = AttributionAnalyzer()

    def test_brinson_attribution(self):
        """测试 Brinson 归因"""
        # 创建测试数据
        portfolio_weights = pd.Series({'消费': 0.4, '科技': 0.3, '金融': 0.3})
        benchmark_weights = pd.Series({'消费': 0.3, '科技': 0.4, '金融': 0.3})
        portfolio_returns = pd.Series({'消费': 0.15, '科技': 0.20, '金融': 0.10})
        benchmark_returns = pd.Series({'消费': 0.12, '科技': 0.18, '金融': 0.10})

        allocation, selection, interaction = self.analyzer.brinson_attribution(
            portfolio_weights, benchmark_weights,
            portfolio_returns, benchmark_returns
        )

        self.assertIsInstance(allocation, float)
        self.assertIsInstance(selection, float)
        self.assertIsInstance(interaction, float)

    def test_stock_contribution(self):
        """测试个股贡献"""
        # 创建测试交易
        from src.backtest.engine import Trade

        trades = [
            Trade(
                order_id='1', ts_code='000001.SZ', direction='buy',
                price=10.0, volume=1000, timestamp='20240101',
                commission=5, stamp_tax=0, slippage=10
            ),
            Trade(
                order_id='2', ts_code='000001.SZ', direction='sell',
                price=11.0, volume=1000, timestamp='20240102',
                commission=5, stamp_tax=11, slippage=11
            )
        ]

        positions = {}

        contribution = self.analyzer.stock_contribution(trades, positions)

        self.assertIn('000001.SZ', contribution)
        self.assertGreater(contribution['000001.SZ'], 0)  # 应该盈利


if __name__ == "__main__":
    unittest.main(verbosity=2)
