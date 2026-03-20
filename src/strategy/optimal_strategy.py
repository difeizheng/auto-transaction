"""
最优综合策略系统
整合多因子、多指标、动态仓位管理的最优策略
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_bollinger_bands
from config.logging_config import strategy_logger


class MarketState(Enum):
    """市场状态"""
    BULL = "bull"      # 牛市
    BEAR = "bear"      # 熊市
    SIDEWAYS = "sideways"  # 震荡市


@dataclass
class OptimalStrategyParams:
    """最优策略参数"""
    # 均线系统
    ma_short: int = 3
    ma_mid: int = 8
    ma_long: int = 15
    ma_trend: int = 50

    # 成交量
    volume_ma_period: int = 20
    volume_ratio_threshold: float = 1.1

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70

    # 布林带
    bb_window: int = 20
    bb_num_std: float = 2.0

    # 动态止损止盈
    base_stop_loss: float = 0.07      # 基础止损 7%
    base_take_profit: float = 0.20    # 基础止盈 20%
    atr_multiplier_sl: float = 2.0    # ATR 止损倍数
    atr_multiplier_tp: float = 3.0    # ATR 止盈倍数
    trailing_stop_trigger: float = 0.12  # 移动止损触发点 12%

    # 仓位管理
    base_position_ratio: float = 0.25  # 基础仓位 25%
    max_position_ratio: float = 0.35   # 最大仓位 35%
    min_position_ratio: float = 0.10   # 最小仓位 10%

    # 市场状态判断
    trend_threshold: float = 0.03      # 趋势判断阈值 3%

    # 信号阈值（动态可配置）
    signal_threshold: float = 4.0      # 信号触发阈值 4.0/7


class OptimalStrategy(BaseStrategy):
    """
    最优综合策略

    核心逻辑:
    1. 三重均线系统 (短/中/长) 判断趋势
    2. MACD + RSI + 布林带 多重确认
    3. 成交量过滤假突破
    4. 动态止损止盈 (基于 ATR)
    5. 智能仓位管理 (根据市场状态)
    6. 市场状态自适应 (牛/熊/震荡)
    """

    def __init__(
        self,
        name: str = "optimal_strategy",
        params: Optional[OptimalStrategyParams] = None
    ):
        super().__init__(name)
        self.params = params or OptimalStrategyParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}  # {ts_code: {entry_price, highest_price, shares}}
        self.market_state = MarketState.SIDEWAYS

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"最优策略初始化 - 市场自适应交易")
        strategy_logger.info(f"参数：止损={self.params.base_stop_loss*100}%, "
                            f"止盈={self.params.base_take_profit*100}%, "
                            f"基础仓位={self.params.base_position_ratio*100}%")

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

            # 保留足够数据
            max_history = self.params.ma_trend * 3
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算 ATR (平均真实波幅)"""
        if len(df) < period + 1:
            return 0.02  # 默认 2%

        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return atr / close.iloc[-1] if close.iloc[-1] > 0 else 0.02

    def determine_market_state(self, df: pd.DataFrame) -> MarketState:
        """
        判断市场状态 (改进版)

        基于双均线系统 + 时间过滤 + 成交量确认
        - 双均线：短期均线与长期均线的关系
        - 时间过滤：连续 3 日确认
        - 成交量：上涨放量确认
        """
        ma_long_period = self.params.ma_trend

        if len(df) < ma_long_period + 2:
            return MarketState.SIDEWAYS

        close = df['close']
        vol = df['vol']

        # 计算均线
        ma_short = close.rolling(self.params.ma_short).mean()
        ma_long = close.rolling(ma_long_period).mean()

        current_price = close.iloc[-1]
        current_vol = vol.iloc[-1] if len(vol) > 0 else 0
        vol_ma = vol.rolling(self.params.volume_ma_period).mean().iloc[-1] if len(vol) >= self.params.volume_ma_period else 0

        # 检查连续 3 日的均线关系
        consecutive_bull = 0
        consecutive_bear = 0

        for i in range(3):
            idx = -1 - i
            if idx >= -len(df):
                short_val = ma_short.iloc[idx]
                long_val = ma_long.iloc[idx]

                # 短期 > 长期 → 牛市信号
                if short_val > long_val:
                    consecutive_bull += 1
                # 短期 < 长期 → 熊市信号
                elif short_val < long_val:
                    consecutive_bear += 1

        # 成交量确认 (放量上涨才是真牛市)
        volume_confirmed = current_vol > vol_ma * 1.1 if vol_ma > 0 else True

        # 综合判断
        if consecutive_bull >= 3 and volume_confirmed:
            return MarketState.BULL
        elif consecutive_bear >= 3:
            return MarketState.BEAR
        else:
            return MarketState.SIDEWAYS

    def calculate_dynamic_stop_loss_take_profit(
        self,
        ts_code: str,
        atr: float
    ) -> Tuple[float, float]:
        """
        计算动态止损止盈

        基于 ATR 和市场状态
        """
        # 基础止损止盈
        sl = self.params.base_stop_loss
        tp = self.params.base_take_profit

        # 根据 ATR 调整
        atr_sl = atr * self.params.atr_multiplier_sl
        atr_tp = atr * self.params.atr_multiplier_tp

        # 根据市场状态调整
        if self.market_state == MarketState.BULL:
            # 牛市：放宽止损，提高止盈
            sl *= 0.8
            tp *= 1.2
        elif self.market_state == MarketState.BEAR:
            # 熊市：收紧止损，降低止盈
            sl *= 1.2
            tp *= 0.8

        # 使用 ATR 和基础值的较大者
        dynamic_sl = max(sl, atr_sl)
        dynamic_tp = max(tp, atr_tp)

        return dynamic_sl, dynamic_tp

    def calculate_position_size(
        self,
        ts_code: str,
        signal_strength: float,
        current_price: float
    ) -> int:
        """
        智能仓位管理

        根据市场状态和信号强度动态调整
        """
        # 基础仓位
        base_ratio = self.params.base_position_ratio

        # 根据市场状态调整
        if self.market_state == MarketState.BULL:
            # 牛市：增加仓位
            position_ratio = min(self.params.max_position_ratio, base_ratio * 1.5)
        elif self.market_state == MarketState.BEAR:
            # 熊市：减少仓位
            position_ratio = max(self.params.min_position_ratio, base_ratio * 0.5)
        else:
            # 震荡市：保持基础仓位
            position_ratio = base_ratio

        # 根据信号强度调整
        position_ratio *= signal_strength

        # 计算仓位价值
        total_capital = self.engine.capital if self.engine else 1000000
        target_value = total_capital * position_ratio

        # 计算股数 (100 股的整数倍)
        volume = int(target_value / current_price / 100) * 100

        return max(100, volume)

    def check_exit_conditions(
        self,
        ts_code: str,
        current_price: float,
        atr: float
    ) -> Optional[Tuple[str, str]]:
        """
        检查出场条件

        Returns:
            (方向，原因) 或 None
        """
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']

        # 更新最高价
        if current_price > pos.get('highest_price', 0):
            self.positions[ts_code]['highest_price'] = current_price
        highest_price = self.positions[ts_code].get('highest_price', entry_price)

        # 计算动态止损止盈
        dynamic_sl, dynamic_tp = self.calculate_dynamic_stop_loss_take_profit(ts_code, atr)

        # 当前盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price

        # 1. 止损检查
        if profit_ratio <= -dynamic_sl:
            return ('sell', f'止损 ({profit_ratio:.1%}, SL={-dynamic_sl:.1%})')

        # 2. 止盈检查
        if profit_ratio >= dynamic_tp:
            return ('sell', f'止盈 ({profit_ratio:.1%}, TP={dynamic_tp:.1%})')

        # 3. 移动止损检查 (当盈利超过 8% 后激活)
        if highest_price >= entry_price * (1 + self.params.trailing_stop_trigger):
            drawdown = (highest_price - current_price) / highest_price
            trailing_stop = dynamic_sl * 0.5  # 移动止损更紧
            if drawdown >= trailing_stop:
                return ('sell', f'移动止损 (回撤{drawdown:.1%})')

        return None

    def calculate_signal_score(
        self,
        golden_cross: bool,
        macd_bullish: bool,
        rsi_ok: bool,
        rsi_oversold: bool,
        bb_signal: str,
        volume_ok: bool,
        trend_ok: bool
    ) -> Tuple[bool, float]:
        """
        综合评分系统 (加权版)

        权重分配:
        - 均线金叉：1.5 分 (趋势确认最重要)
        - MACD 多头：1.0 分
        - RSI 健康：0.5 分
        - RSI 超卖：额外 +0.5 分
        - 布林带下轨：1.0 分 (超卖反弹)
        - 成交量放大：1.0 分 (资金确认)
        - 趋势向上：1.0 分

        Returns:
            (是否买入，信号强度)
        """
        score = 0.0
        max_score = 7.0  # 最大可能得分

        # 1. 均线金叉 (权重 1.5 - 最重要)
        if golden_cross:
            score += 1.5

        # 2. MACD 多头 (权重 1.0)
        if macd_bullish:
            score += 1.0

        # 3. RSI 健康 (权重 0.5)
        if rsi_ok:
            score += 0.5

        # 4. RSI 超卖额外加分 (权重 0.5) - 与 RSI 健康互斥，取较高者
        if rsi_oversold:
            score += 0.5

        # 5. 布林带下轨 (权重 1.0 - 超卖反弹信号)
        if bb_signal == 'lower':
            score += 1.0

        # 6. 成交量放大 (权重 1.0 - 资金确认)
        if volume_ok:
            score += 1.0

        # 7. 趋势向上 (权重 1.0)
        if trend_ok:
            score += 1.0

        # 7. 趋势向上 (权重 1.0)
        if trend_ok:
            score += 1.0

        # 使用动态阈值 (默认 4.0 分)
        # 注：3.5 分阈值下盈亏比仅 0.83，提高至 4.0 分以提高信号质量
        # 增加趋势过滤：趋势向下时不买入 (即使评分高)
        buy_signal = score >= self.params.signal_threshold and trend_ok
        signal_strength = min(1.0, score / max_score)

        return buy_signal, signal_strength

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        # 更新价格历史
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            # 检查是否有足够数据
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            required_len = self.params.ma_trend * 2
            if len(df) < required_len:
                continue

            close = df['close']
            vol = df['vol']
            current_price = bar.get('close', 0)

            # === 计算技术指标 ===

            # 均线系统
            ma_short = close.rolling(self.params.ma_short).mean()
            ma_mid = close.rolling(self.params.ma_mid).mean()
            ma_long = close.rolling(self.params.ma_long).mean()
            ma_trend = close.rolling(self.params.ma_trend).mean()

            # MACD
            macd_data = calculate_macd(
                close,
                self.params.macd_fast,
                self.params.macd_slow,
                self.params.macd_signal
            )
            dif = macd_data['dif'].iloc[-1] if len(macd_data) > 0 else 0
            dea = macd_data['dea'].iloc[-1] if len(macd_data) > 0 else 0
            macd = macd_data['macd'].iloc[-1] if len(macd_data) > 0 else 0

            # RSI
            rsi = calculate_rsi(close, self.params.rsi_period)
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 0

            # 布林带
            bb_data = calculate_bollinger_bands(
                close,
                self.params.bb_window,
                self.params.bb_num_std
            )
            bb_upper = bb_data['upper'].iloc[-1] if len(bb_data) > 0 else 0
            bb_lower = bb_data['lower'].iloc[-1] if len(bb_data) > 0 else 0
            bb_middle = bb_data['middle'].iloc[-1] if len(bb_data) > 0 else 0

            # 成交量均线
            vol_ma = vol.rolling(self.params.volume_ma_period).mean()

            # 计算 ATR
            atr = self.calculate_atr(df)

            # === 判断市场状态 ===
            self.market_state = self.determine_market_state(df)

            # === 检查出场条件 (如果已持仓) ===
            if ts_code in self.positions:
                exit_result = self.check_exit_conditions(ts_code, current_price, atr)
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

            # === 计算信号评分 ===

            # 1. 均线金叉
            golden_cross = (ma_short.iloc[-2] <= ma_long.iloc[-2] and
                           ma_short.iloc[-1] > ma_long.iloc[-1])

            # 2. MACD 多头
            macd_bullish = dif > dea and macd > 0

            # 3. RSI 健康 (不在超买/超卖区)
            rsi_ok = (self.params.rsi_oversold < current_rsi < self.params.rsi_overbought)

            # 4. RSI 超卖 (额外加分项)
            rsi_oversold = current_rsi < self.params.rsi_oversold

            # 5. 布林带信号
            bb_signal = 'lower' if current_price <= bb_lower * 1.01 else \
                       ('upper' if current_price >= bb_upper * 0.99 else 'middle')

            # 6. 成交量放大
            current_vol = bar.get('vol', 0)
            current_vol_ma = vol_ma.iloc[-1] if len(vol_ma) > 0 else 0
            volume_ok = current_vol > current_vol_ma * self.params.volume_ratio_threshold if current_vol_ma > 0 else True

            # 7. 趋势判断
            trend_ok = current_price > ma_trend.iloc[-1] * (1 + self.params.trend_threshold)

            # 综合评分
            buy_signal, signal_strength = self.calculate_signal_score(
                golden_cross, macd_bullish, rsi_ok, rsi_oversold, bb_signal, volume_ok, trend_ok
            )

            # === 生成买入信号 ===
            if buy_signal and ts_code not in self.positions:
                volume = self.calculate_position_size(ts_code, signal_strength, current_price)
                if volume >= 100:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=current_price,
                        volume=volume,
                        strength=signal_strength,
                        reason=f"综合信号 (强度{signal_strength:.1f}, RSI={current_rsi:.0f})"
                    ))
                    # 记录持仓
                    self.positions[ts_code] = {
                        'entry_price': current_price,
                        'highest_price': current_price,
                        'shares': volume
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


# 创建策略实例的工厂函数
def create_optimal_strategy(
    stop_loss: float = 0.07,      # 更新为新参数 7%
    take_profit: float = 0.20,    # 更新为新参数 20%
    position_ratio: float = 0.25,
    signal_threshold: float = 4.0,  # 信号触发阈值
    aggressive: bool = False
) -> OptimalStrategy:
    """
    创建最优策略

    Args:
        stop_loss: 止损比例
        take_profit: 止盈比例
        position_ratio: 基础仓位比例
        signal_threshold: 信号触发阈值
        aggressive: 是否激进模式

    Returns:
        OptimalStrategy 实例
    """
    if aggressive:
        # 激进模式：更高仓位，使用默认止损止盈
        params = OptimalStrategyParams(
            base_stop_loss=stop_loss,
            base_take_profit=take_profit,
            base_position_ratio=min(position_ratio * 1.2, 0.35),
            max_position_ratio=0.40,
            trailing_stop_trigger=0.12,  # 12% 触发移动止损
            signal_threshold=signal_threshold
        )
        return OptimalStrategy(name="optimal_aggressive", params=params)
    else:
        # 稳健模式
        params = OptimalStrategyParams(
            base_stop_loss=stop_loss,
            base_take_profit=take_profit,
            base_position_ratio=position_ratio,
            max_position_ratio=0.30,
            trailing_stop_trigger=0.12,
            signal_threshold=signal_threshold
        )
        return OptimalStrategy(name="optimal_conservative", params=params)
