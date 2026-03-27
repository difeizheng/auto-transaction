"""
技术指标策略模块
实现 MACD、RSI、均线等技术指标策略
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_ma
from config.logging_config import strategy_logger


@dataclass
class TechnicalParams:
    """技术指标策略参数"""
    # 均线策略参数
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20

    # MACD 策略参数
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI 策略参数
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70

    # 布林带策略参数
    bb_window: int = 20
    bb_num_std: float = 2.0


class TechnicalStrategy(BaseStrategy):
    """技术指标策略"""

    def __init__(
        self,
        name: str = "technical_strategy",
        params: Optional[TechnicalParams] = None
    ):
        super().__init__(name)
        self.params = params or TechnicalParams()
        self.price_history: Dict[str, pd.DataFrame] = {}

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': float(bar.get('open', 0)),
                'high': float(bar.get('high', 0)),
                'low': float(bar.get('low', 0)),
                'close': float(bar.get('close', 0)),
                'vol': float(bar.get('vol', 0)),
                'amount': float(bar.get('amount', 0))
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            )

            # 保留最近 N 天的数据
            max_history = max(
                self.params.ma_long * 2,
                self.params.macd_slow * 2,
                self.params.bb_window * 2
            )
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """
        K 线数据回调

        Args:
            data: 当日行情数据字典
            current_date: 当前交易日期

        Returns:
            交易信号列表
        """
        if not self.initialized:
            self.on_init()

        # 更新价格历史
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            # 检查是否有足够的历史数据
            if ts_code not in self.price_history or len(self.price_history[ts_code]) < self.params.ma_long:
                continue

            df = self.price_history[ts_code]

            # 计算技术指标
            # 确保数据类型为 numeric
            close = pd.to_numeric(df['close'], errors='coerce')

            # 均线
            ma_short = close.rolling(window=self.params.ma_short).mean()
            ma_mid = close.rolling(window=self.params.ma_mid).mean()
            ma_long = close.rolling(window=self.params.ma_long).mean()

            # MACD
            macd_data = calculate_macd(
                close,
                self.params.macd_fast,
                self.params.macd_slow,
                self.params.macd_signal
            )

            # RSI
            rsi = calculate_rsi(close, self.params.rsi_period)

            # 布林带
            bb_data = self.calculate_bollinger_bands(
                close,
                self.params.bb_window,
                self.params.bb_num_std
            )

            # 生成信号
            signal = self.generate_signals_from_indicators(
                ts_code=ts_code,
                current_price=bar.get('close', 0),
                ma_short=ma_short.iloc[-1] if len(ma_short) > 0 else 0,
                ma_mid=ma_mid.iloc[-1] if len(ma_mid) > 0 else 0,
                ma_long=ma_long.iloc[-1] if len(ma_long) > 0 else 0,
                dif=macd_data['dif'].iloc[-1] if len(macd_data) > 0 else 0,
                dea=macd_data['dea'].iloc[-1] if len(macd_data) > 0 else 0,
                rsi=rsi.iloc[-1] if len(rsi) > 0 else 0,
                bb_upper=bb_data['upper'].iloc[-1] if len(bb_data) > 0 else 0,
                bb_lower=bb_data['lower'].iloc[-1] if len(bb_data) > 0 else 0,
                bb_middle=bb_data['middle'].iloc[-1] if len(bb_data) > 0 else 0
            )

            if signal:
                signals.append(signal)

        return signals

    def calculate_bollinger_bands(
        self,
        prices: pd.Series,
        window: int,
        num_std: float
    ) -> pd.DataFrame:
        """计算布林带"""
        middle = prices.rolling(window=window).mean()
        std = prices.rolling(window=window).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return pd.DataFrame({'upper': upper, 'middle': middle, 'lower': lower})

    def generate_signals_from_indicators(
        self,
        ts_code: str,
        current_price: float,
        ma_short: float,
        ma_mid: float,
        ma_long: float,
        dif: float,
        dea: float,
        rsi: float,
        bb_upper: float,
        bb_lower: float,
        bb_middle: float
    ) -> Optional[Signal]:
        """
        根据技术指标生成信号

        综合多个指标产生交易信号:
        - 均线：金叉买入，死叉卖出
        - MACD: DIF 上穿 DEA 买入，下穿卖出
        - RSI: 超卖买入，超买卖出
        - 布林带：触及下轨买入，触及上轨卖出
        """
        buy_signals = 0
        sell_signals = 0
        reasons = []

        # 1. 均线策略
        if ma_short > ma_mid and ma_short <= ma_mid * 0.99:  # 短期上穿中期
            buy_signals += 1
            reasons.append("MA 金叉")
        elif ma_short < ma_mid and ma_short >= ma_mid * 1.01:  # 短期下穿中期
            sell_signals += 1
            reasons.append("MA 死叉")

        # 价格相对于均线的位置
        if current_price > ma_long * 1.02:  # 价格在长期均线上方
            buy_signals += 0.5
        elif current_price < ma_long * 0.98:  # 价格在长期均线下方
            sell_signals += 0.5

        # 2. MACD 策略
        macd = dif - dea
        if macd > 0 and dif > dea:  # MACD 在零轴上方且上升
            buy_signals += 0.5
            reasons.append("MACD 多头")
        elif macd < 0 and dif < dea:  # MACD 在零轴下方且下降
            sell_signals += 0.5
            reasons.append("MACD 空头")

        # 3. RSI 策略
        if rsi < self.params.rsi_oversold:  # 超卖
            buy_signals += 1
            reasons.append(f"RSI 超卖 ({rsi:.1f})")
        elif rsi > self.params.rsi_overbought:  # 超买
            sell_signals += 1
            reasons.append(f"RSI 超买 ({rsi:.1f})")

        # 4. 布林带策略
        if current_price <= bb_lower * 1.01:  # 触及下轨
            buy_signals += 0.5
            reasons.append("触及布林下轨")
        elif current_price >= bb_upper * 0.99:  # 触及上轨
            sell_signals += 0.5
            reasons.append("触及布林上轨")

        # 综合判断
        total_buy = buy_signals
        total_sell = sell_signals

        if total_buy >= 2 and total_buy > total_sell:
            # 买入信号
            strength = min(1.0, total_buy / 4.0)
            return self.generate_signal(
                ts_code=ts_code,
                direction='buy',
                price=current_price,
                volume=self.calculate_position_size(
                    ts_code, strength, current_price,
                    self.engine.capital if self.engine else 1000000
                ),
                strength=strength,
                reason="; ".join(reasons)
            )
        elif total_sell >= 2 and total_sell > total_buy:
            # 卖出信号
            strength = min(1.0, total_sell / 4.0)
            return self.generate_signal(
                ts_code=ts_code,
                direction='sell',
                price=current_price,
                volume=1000,  # 全部卖出
                strength=strength,
                reason="; ".join(reasons)
            )

        return None


class MACDStrategy(BaseStrategy):
    """纯 MACD 策略"""

    def __init__(
        self,
        name: str = "macd_strategy",
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ):
        super().__init__(name)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.price_history: Dict[str, List[float]] = {}

    def on_init(self):
        super().on_init()
        self.price_history = {}

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        signals = []

        for ts_code, bar in data.items():
            close = bar.get('close', 0)

            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            self.price_history[ts_code].append(close)

            # 需要足够的数据
            if len(self.price_history[ts_code]) < self.slow_period:
                continue

            prices = pd.Series(self.price_history[ts_code][-self.slow_period * 2:])

            # 计算 MACD
            macd_data = calculate_macd(prices, self.fast_period, self.slow_period, self.signal_period)

            if len(macd_data) < 2:
                continue

            dif = macd_data['dif']
            dea = macd_data['dea']

            # 金叉：DIF 从下向上穿过 DEA
            if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='buy',
                    price=close,
                    volume=1000,
                    reason="MACD 金叉"
                ))
            # 死叉：DIF 从上向下穿过 DEA
            elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='sell',
                    price=close,
                    volume=1000,
                    reason="MACD 死叉"
                ))

        return signals


class RSIStrategy(BaseStrategy):
    """纯 RSI 策略"""

    def __init__(
        self,
        name: str = "rsi_strategy",
        period: int = 14,
        oversold: float = 30,
        overbought: float = 70
    ):
        super().__init__(name)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.price_history: Dict[str, List[float]] = {}

    def on_init(self):
        super().on_init()
        self.price_history = {}

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        signals = []

        for ts_code, bar in data.items():
            close = bar.get('close', 0)

            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            self.price_history[ts_code].append(close)

            # 需要足够的数据
            if len(self.price_history[ts_code]) <= self.period:
                continue

            prices = pd.Series(self.price_history[ts_code][-self.period - 1:])
            rsi = calculate_rsi(prices, self.period).iloc[-1]

            # 超卖买入
            if rsi < self.oversold:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='buy',
                    price=close,
                    volume=1000,
                    reason=f"RSI 超卖 ({rsi:.1f})"
                ))
            # 超买卖出
            elif rsi > self.overbought:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='sell',
                    price=close,
                    volume=1000,
                    reason=f"RSI 超买 ({rsi:.1f})"
                ))

        return signals


class MaCrossoverStrategy(BaseStrategy):
    """均线交叉策略"""

    def __init__(
        self,
        name: str = "ma_crossover_strategy",
        short_period: int = 5,
        long_period: int = 20
    ):
        super().__init__(name)
        self.short_period = short_period
        self.long_period = long_period
        self.price_history: Dict[str, List[float]] = {}

    def on_init(self):
        super().on_init()
        self.price_history = {}

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        signals = []

        for ts_code, bar in data.items():
            close = bar.get('close', 0)

            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            self.price_history[ts_code].append(close)

            # 需要足够的数据
            if len(self.price_history[ts_code]) < self.long_period + 1:
                continue

            prices = pd.Series(self.price_history[ts_code][-self.long_period * 2:])

            # 计算均线
            ma_short = prices.rolling(self.short_period).mean()
            ma_long = prices.rolling(self.long_period).mean()

            # 金叉
            if ma_short.iloc[-2] < ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='buy',
                    price=close,
                    volume=1000,
                    reason=f"MA{self.short_period} 上穿 MA{self.long_period}"
                ))
            # 死叉
            elif ma_short.iloc[-2] > ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='sell',
                    price=close,
                    volume=1000,
                    reason=f"MA{self.short_period} 下穿 MA{self.long_period}"
                ))

        return signals
