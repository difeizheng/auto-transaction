"""
改进的均线交叉策略
增加成交量过滤、RSI 过滤、趋势过滤和止损止盈机制
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_rsi
from config.logging_config import strategy_logger


@dataclass
class EnhancedMaParams:
    """增强均线策略参数"""
    # 均线参数
    short_period: int = 5
    long_period: int = 20

    # 成交量过滤
    volume_ma_period: int = 20
    volume_ratio_threshold: float = 1.5  # 成交量需大于均量的 1.5 倍

    # RSI 过滤
    rsi_period: int = 14
    rsi_buy_threshold: float = 50  # RSI 大于 50 才买入
    rsi_sell_threshold: float = 70  # RSI 大于 70 考虑卖出

    # 趋势过滤
    trend_ma_period: int = 60  # 长期均线判断趋势
    trend_threshold: float = 0.02  # 价格在长期均线上方 2% 才认为是上升趋势

    # 止损止盈
    stop_loss: float = 0.05  # 5% 止损
    take_profit: float = 0.15  # 15% 止盈
    trailing_stop: float = 0.08  # 8% 移动止损


class EnhancedMaCrossoverStrategy(BaseStrategy):
    """
    增强的均线交叉策略

    改进点:
    1. 成交量过滤：金叉时成交量需放大
    2. RSI 过滤：避免在超买区买入
    3. 趋势过滤：只在上升趋势中交易
    4. 止损止盈：保护利润，限制亏损
    5. 移动止损：锁定部分利润
    """

    def __init__(
        self,
        name: str = "enhanced_ma_crossover",
        params: Optional[EnhancedMaParams] = None
    ):
        super().__init__(name)
        self.params = params or EnhancedMaParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.entry_prices: Dict[str, float] = {}  # 记录入场价
        self.highest_prices: Dict[str, float] = {}  # 记录最高价 (用于移动止损)

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}
        self.entry_prices = {}
        self.highest_prices = {}
        strategy_logger.info(f"策略参数：成交量倍数={self.params.volume_ratio_threshold}, "
                            f"RSI 买入阈值={self.params.rsi_buy_threshold}, "
                            f"止损={self.params.stop_loss*100}%, 止盈={self.params.take_profit*100}%")

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0),
                'amount': bar.get('amount', 0)
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            )

            # 保留足够的数据
            max_history = max(self.params.long_period, self.params.trend_ma_period) * 2
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def check_stop_loss_take_profit(
        self,
        ts_code: str,
        current_price: float
    ) -> Optional[str]:
        """
        检查止损止盈条件

        Returns:
            'stop_loss' / 'take_profit' / 'trailing_stop' / None
        """
        if ts_code not in self.entry_prices:
            return None

        entry_price = self.entry_prices[ts_code]

        # 更新最高价
        if ts_code not in self.highest_prices:
            self.highest_prices[ts_code] = current_price
        else:
            self.highest_prices[ts_code] = max(self.highest_prices[ts_code], current_price)

        highest_price = self.highest_prices[ts_code]

        # 计算盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price

        # 1. 止损检查
        if profit_ratio <= -self.params.stop_loss:
            return 'stop_loss'

        # 2. 止盈检查
        if profit_ratio >= self.params.take_profit:
            return 'take_profit'

        # 3. 移动止损检查 (当盈利超过一定比例后激活)
        if highest_price >= entry_price * (1 + self.params.trailing_stop / 2):
            # 从最高点回撤超过阈值
            drawdown = (highest_price - current_price) / highest_price
            if drawdown >= self.params.trailing_stop:
                return 'trailing_stop'

        return None

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        # 更新价格历史
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            # 检查是否有足够数据
            if ts_code not in self.price_history or len(self.price_history[ts_code]) < self.params.trend_ma_period:
                continue

            df = self.price_history[ts_code]
            close = df['close']
            vol = df['vol']

            # 计算技术指标
            ma_short = close.rolling(window=self.params.short_period).mean()
            ma_long = close.rolling(window=self.params.long_period).mean()
            ma_trend = close.rolling(window=self.params.trend_ma_period).mean()

            # 成交量均线
            vol_ma = vol.rolling(window=self.params.volume_ma_period).mean()

            # RSI
            rsi = calculate_rsi(close, self.params.rsi_period)

            # 当前值
            current_price = bar.get('close', 0)
            current_vol = bar.get('vol', 0)
            current_vol_ma = vol_ma.iloc[-1] if len(vol_ma) > 0 else 0
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 0

            # 检查止损止盈 (如果已持仓)
            if ts_code in self.entry_prices:
                sl_tp_type = self.check_stop_loss_take_profit(ts_code, current_price)
                if sl_tp_type:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=1000,  # 全部卖出
                        reason=f"触发{sl_tp_type}"
                    ))
                    # 清除记录
                    del self.entry_prices[ts_code]
                    if ts_code in self.highest_prices:
                        del self.highest_prices[ts_code]
                    continue

            # 均线交叉信号
            ma_short_prev = ma_short.iloc[-2] if len(ma_short) > 1 else 0
            ma_long_prev = ma_long.iloc[-2] if len(ma_long) > 1 else 0
            ma_short_curr = ma_short.iloc[-1]
            ma_long_curr = ma_long.iloc[-1]

            # 金叉：短期均线上穿长期均线
            golden_cross = ma_short_prev <= ma_long_prev and ma_short_curr > ma_long_curr

            # 死叉：短期均线下穿长期均线
            death_cross = ma_short_prev >= ma_long_prev and ma_short_curr < ma_long_curr

            # 趋势判断：价格在长期均线上方
            is_uptrend = current_price > ma_trend.iloc[-1] * (1 + self.params.trend_threshold)

            # 成交量放大
            volume_ok = current_vol > current_vol_ma * self.params.volume_ratio_threshold if current_vol_ma > 0 else True

            # RSI 判断
            rsi_ok_for_buy = current_rsi > self.params.rsi_buy_threshold and current_rsi < 70
            rsi_overbought = current_rsi > self.params.rsi_sell_threshold

            # 生成买入信号 (需要满足多个条件)
            if golden_cross and is_uptrend and volume_ok and rsi_ok_for_buy:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='buy',
                    price=current_price,
                    volume=self.calculate_position_size(
                        ts_code,
                        signal_strength=0.8,
                        current_price=current_price,
                        total_capital=self.engine.capital if self.engine else 1000000
                    ),
                    strength=0.8,
                    reason=f"金叉 + 趋势 + 放量 +RSI  ({current_rsi:.1f})"
                ))
                # 记录入场价
                self.entry_prices[ts_code] = current_price
                self.highest_prices[ts_code] = current_price

            # 生成卖出信号
            elif death_cross or rsi_overbought:
                if ts_code in self.entry_prices:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=1000,
                        reason=f"死叉或 RSI 超买 ({current_rsi:.1f})"
                    ))
                    del self.entry_prices[ts_code]
                    if ts_code in self.highest_prices:
                        del self.highest_prices[ts_code]

        return signals

    def calculate_position_size(
        self,
        ts_code: str,
        signal_strength: float,
        current_price: float,
        total_capital: float
    ) -> int:
        """
        计算仓位大小

        根据信号强度和风险调整仓位
        """
        # 单只股票最大仓位 (激进风格 30%)
        max_stock_ratio = 0.30
        max_order_value = 20000  # 单笔最大 2 万

        # 根据信号强度调整仓位
        target_value = min(
            total_capital * max_stock_ratio * signal_strength,
            max_order_value
        )

        # 计算股数 (100 股的整数倍)
        volume = int(target_value / current_price / 100) * 100

        return max(100, volume)


# 创建一个更简单的测试策略
class SimpleEnhancedStrategy(BaseStrategy):
    """
    简化版增强策略
    用于快速回测验证
    """

    def __init__(
        self,
        name: str = "simple_enhanced",
        short_period: int = 5,
        long_period: int = 20,
        stop_loss: float = 0.05,
        take_profit: float = 0.15
    ):
        super().__init__(name)
        self.short_period = short_period
        self.long_period = long_period
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.price_history: Dict[str, List[float]] = {}
        self.entry_prices: Dict[str, float] = {}

    def on_init(self):
        super().on_init()
        self.price_history = {}
        self.entry_prices = {}

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        signals = []

        for ts_code, bar in data.items():
            close = bar.get('close', 0)

            # 更新价格历史
            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            self.price_history[ts_code].append(close)

            # 检查止损止盈
            if ts_code in self.entry_prices:
                entry_price = self.entry_prices[ts_code]
                profit_ratio = (close - entry_price) / entry_price

                # 止损
                if profit_ratio <= -self.stop_loss:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=close,
                        volume=1000,
                        reason=f"止损 ({profit_ratio:.1%})"
                    ))
                    del self.entry_prices[ts_code]
                    continue

                # 止盈
                if profit_ratio >= self.take_profit:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=close,
                        volume=1000,
                        reason=f"止盈 ({profit_ratio:.1%})"
                    ))
                    del self.entry_prices[ts_code]
                    continue

            # 需要足够数据计算均线
            if len(self.price_history.get(ts_code, [])) < self.long_period + 1:
                continue

            prices = pd.Series(self.price_history[ts_code])
            ma_short = prices.rolling(self.short_period).mean()
            ma_long = prices.rolling(self.long_period).mean()

            # 金叉买入
            if ma_short.iloc[-2] <= ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]:
                if ts_code not in self.entry_prices:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=close,
                        volume=1000,
                        reason="金叉买入"
                    ))
                    self.entry_prices[ts_code] = close

            # 死叉卖出
            elif ma_short.iloc[-2] >= ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]:
                if ts_code in self.entry_prices:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=close,
                        volume=1000,
                        reason="死叉卖出"
                    ))
                    del self.entry_prices[ts_code]

        return signals
