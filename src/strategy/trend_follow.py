"""
趋势跟踪策略 - 基于价格行为和动量
核心逻辑：
1. 只在明确上升趋势中交易
2. 使用价格突破作为入场信号
3. 使用 ATR 动态止损和追踪止盈
4. 严格的市场过滤
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_bollinger_bands
from config.logging_config import strategy_logger


class MarketTrend(Enum):
    """市场趋势"""
    STRONG_BULL = "strong_bull"    # 强势牛市
    WEAK_BULL = "weak_bull"        # 弱势牛市
    SIDEWAYS = "sideways"          # 震荡市
    WEAK_BEAR = "weak_bear"        # 弱势熊市
    STRONG_BEAR = "strong_bear"    # 强势熊市


@dataclass
class TrendFollowParams:
    """趋势跟踪参数 - 优化版"""
    # 趋势判断
    ma_trend: int = 40              # 长期趋势均线 (降低至 40)
    ma_short: int = 5               # 短期均线
    ma_mid: int = 20                # 中期均线

    # 价格突破
    breakout_period: int = 10       # 突破周期 (降低至 10)
    breakout_threshold: float = 0.01  # 突破阈值 1%

    # 动量指标
    momentum_period: int = 10       # 动量周期
    rsi_period: int = 14            # RSI 周期

    # 止损止盈 - 基于 ATR
    atr_period: int = 14            # ATR 周期
    stop_loss_atr: float = 2.0      # ATR 止损倍数
    take_profit_atr: float = 4.0    # ATR 止盈倍数

    # 追踪止损
    trailing_start: float = 0.08    # 追踪启动点 8%
    trailing_ratio: float = 0.04    # 追踪回撤 4%

    # 仓位管理
    base_position: float = 0.15     # 基础仓位 15%
    max_position: float = 0.25      # 最大仓位 25%

    # RSI 范围
    rsi_min: float = 35             # RSI 下限
    rsi_max: float = 75             # RSI 上限


class TrendFollowStrategy(BaseStrategy):
    """趋势跟踪策略"""

    def __init__(self, name: str = "trend_follow", params: Optional[TrendFollowParams] = None):
        super().__init__(name)
        self.params = params or TrendFollowParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}
        self.market_trend = MarketTrend.SIDEWAYS

    def on_init(self):
        """初始化"""
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"趋势跟踪策略初始化")
        strategy_logger.info(f"参数：止损={self.params.stop_loss_atr}xATR, "
                           f"止盈={self.params.take_profit_atr}xATR, "
                           f"仓位={self.params.base_position*100}%")

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

            max_history = self.params.ma_trend * 3
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def calculate_atr(self, df: pd.DataFrame) -> float:
        """计算 ATR"""
        period = self.params.atr_period
        if len(df) < period + 1:
            return 0.02

        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return atr / close.iloc[-1] if close.iloc[-1] > 0 else 0.02

    def determine_trend(self, df: pd.DataFrame) -> MarketTrend:
        """
        判断市场趋势
        基于均线和价格位置
        """
        if len(df) < self.params.ma_trend + 5:
            return MarketTrend.SIDEWAYS

        close = df['close']
        ma_short = close.rolling(self.params.ma_short).mean()
        ma_mid = close.rolling(self.params.ma_mid).mean()
        ma_long = close.rolling(self.params.ma_trend).mean()

        current_price = close.iloc[-1]
        s = ma_short.iloc[-1]
        m = ma_mid.iloc[-1]
        l = ma_long.iloc[-1]

        # 计算均线排列
        bull_alignment = (s > m > l)  # 多头排列
        bear_alignment = (s < m < l)  # 空头排列

        # 价格相对位置
        price_ratio_long = current_price / l - 1

        # 综合判断
        if bull_alignment and price_ratio_long > 0.05:
            return MarketTrend.STRONG_BULL
        elif bull_alignment:
            return MarketTrend.WEAK_BULL
        elif bear_alignment and price_ratio_long < -0.05:
            return MarketTrend.STRONG_BEAR
        elif bear_alignment:
            return MarketTrend.WEAK_BEAR
        else:
            return MarketTrend.SIDEWAYS

    def check_breakout(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查价格突破
        Returns: (是否突破，突破方向)
        """
        period = self.params.breakout_period
        if len(df) < period + 5:
            return False, ''

        close = df['close']
        high = df['high']
        low = df['low']
        current_price = close.iloc[-1]

        # 计算 N 日高低点
        high_20 = high.rolling(period).max().iloc[-2]  # 前一日的高点
        low_20 = low.rolling(period).min().iloc[-2]

        # 检查突破
        upside_break = current_price > high_20 * (1 + self.params.breakout_threshold)
        downside_break = current_price < low_20 * (1 - self.params.breakout_threshold)

        if upside_break:
            return True, 'up'
        elif downside_break:
            return True, 'down'
        else:
            return False, ''

    def check_exit(self, ts_code: str, current_price: float, atr: float) -> Optional[Tuple[str, str]]:
        """检查出场条件 - 简化版 (固定百分比止损止盈)"""
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']
        highest_price = pos.get('highest_price', entry_price)
        entry_date = pos.get('entry_date', '')

        # 更新最高价
        if current_price > highest_price:
            self.positions[ts_code]['highest_price'] = current_price
            highest_price = current_price

        # 当前盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price

        # 固定百分比止损止盈 (更简单直接)
        # 止损 8%, 止盈 20% - 目标盈亏比 2.5
        stop_loss_ratio = 0.08
        take_profit_ratio = 0.20

        # 1. 基础止损
        if profit_ratio <= -stop_loss_ratio:
            return ('sell', f'止损 ({profit_ratio:.1%})')

        # 2. 基础止盈
        if profit_ratio >= take_profit_ratio:
            return ('sell', f'止盈 ({profit_ratio:.1%})')

        # 3. 追踪止损 (盈利超过 10% 后启动)
        if highest_price >= entry_price * 1.10:
            trailing_stop = highest_price * 0.95  # 回撤 5% 出场
            if current_price <= trailing_stop:
                drawdown = (highest_price - current_price) / highest_price
                return ('sell', f'追踪止损 (回撤{drawdown:.1%})')

        # 4. 时间止损 (持仓超过 15 日无盈利退出)
        if hasattr(self, 'current_date') and entry_date:
            try:
                from datetime import datetime
                entry_dt = datetime.strptime(entry_date, '%Y%m%d')
                current_dt = datetime.strptime(self.current_date, '%Y%m%d')
                holding_days = (current_dt - entry_dt).days
                if holding_days >= 15 and profit_ratio < 0.05:
                    return ('sell', f'时间止损 ({holding_days}日)')
            except:
                pass

        return None

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线回调"""
        if not self.initialized:
            self.on_init()

        self.current_date = current_date
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            required_len = self.params.ma_trend + 10
            if len(df) < required_len:
                continue

            close = df['close']
            current_price = bar.get('close', 0)

            # 计算指标
            ma_short = close.rolling(self.params.ma_short).mean()
            ma_mid = close.rolling(self.params.ma_mid).mean()
            ma_long = close.rolling(self.params.ma_trend).mean()

            # ATR
            atr = self.calculate_atr(df)

            # RSI
            rsi = calculate_rsi(close, self.params.rsi_period)
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50

            # 动量
            momentum = close.pct_change(self.params.momentum_period).iloc[-1]

            # 判断趋势
            self.market_trend = self.determine_trend(df)

            # === 出场检查 ===
            if ts_code in self.positions:
                exit_result = self.check_exit(ts_code, current_price, atr)
                if exit_result:
                    direction, reason = exit_result
                    shares = self.positions[ts_code].get('shares', 1000)
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction=direction,
                        price=current_price,
                        volume=shares,
                        reason=reason
                    ))
                    del self.positions[ts_code]
                    continue

            # === 入场检查 ===
            # 只在强/弱牛市交易
            if self.market_trend not in [MarketTrend.STRONG_BULL, MarketTrend.WEAK_BULL]:
                continue

            # 价格突破信号
            breakout, breakout_dir = self.check_breakout(df)

            # 动量确认
            momentum_ok = momentum > 0.03  # 14 日动量 > 3%

            # RSI 健康
            rsi_ok = 40 <= current_rsi <= 70

            # 均线多头排列
            trend_ok = ma_short.iloc[-1] > ma_mid.iloc[-1] > ma_long.iloc[-1]

            # 成交量确认
            vol_ma = close.rolling(20).mean()
            volume_ok = bar.get('vol', 0) > vol_ma.iloc[-1] * 1.2 if len(vol_ma) > 0 else True

            # 综合判断 - 优化版（更宽松的入场条件）
            # 只在强/弱牛市交易
            if self.market_trend not in [MarketTrend.STRONG_BULL, MarketTrend.WEAK_BULL]:
                continue

            # 价格突破信号
            breakout, breakout_dir = self.check_breakout(df)

            # 动量确认（降低要求）
            momentum_ok = momentum > 0.02  # 10 日动量 > 2%

            # RSI 健康（更宽松的范围）
            rsi_ok = self.params.rsi_min <= current_rsi <= self.params.rsi_max

            # 均线多头排列（或者至少在趋势均线上方）
            trend_ok = current_price > ma_long.iloc[-1]

            # 成交量确认（降低要求）
            vol_ma = close.rolling(20).mean()
            volume_ok = bar.get('vol', 0) > vol_ma.iloc[-1] * 1.1 if len(vol_ma) > 0 else True

            # 综合判断 - 不需要所有条件都满足
            signal_count = sum([breakout and breakout_dir == 'up', momentum_ok, rsi_ok, trend_ok, volume_ok])

            # 至少 3 个条件满足时入场
            if signal_count >= 3:
                # 计算仓位
                position_ratio = self.params.base_position
                if self.market_trend == MarketTrend.STRONG_BULL:
                    position_ratio = self.params.max_position

                total_capital = self.engine.capital if self.engine else 1000000
                target_value = total_capital * position_ratio
                volume = int(target_value / current_price / 100) * 100

                if volume >= 100:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=current_price,
                        volume=volume,
                        strength=signal_count / 5.0,
                        reason=f"突破信号 (RSI={current_rsi:.0f}, 动量={momentum*100:.1f}%, 趋势={self.market_trend.value})"
                    ))
                    self.positions[ts_code] = {
                        'entry_price': current_price,
                        'highest_price': current_price,
                        'shares': volume,
                        'entry_date': current_date
                    }

        return signals

    def get_positions_summary(self) -> Dict:
        """获取持仓摘要"""
        if not self.positions:
            return {'count': 0, 'total_value': 0}

        total_value = sum(
            pos['shares'] * pos['entry_price']
            for pos in self.positions.values()
        )

        return {
            'count': len(self.positions),
            'total_value': total_value
        }


# 工厂函数
def create_trend_follow_strategy(
    stop_loss_atr: float = None,
    take_profit_atr: float = None,
    position_ratio: float = None
) -> TrendFollowStrategy:
    """创建趋势跟踪策略"""
    params = TrendFollowParams()

    if stop_loss_atr is not None:
        params.stop_loss_atr = stop_loss_atr
    if take_profit_atr is not None:
        params.take_profit_atr = take_profit_atr
    if position_ratio is not None:
        params.base_position = position_ratio

    strategy = TrendFollowStrategy(name="trend_follow", params=params)
    strategy_logger.info(f"趋势跟踪策略初始化")
    strategy_logger.info(f"参数：止损={params.stop_loss_atr}xATR, 止盈={params.take_profit_atr}xATR, "
                        f"仓位={params.base_position*100}%")
    return strategy
