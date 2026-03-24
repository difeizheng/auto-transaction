"""
策略 v5.0 - 强势股突破策略
目标：年化 15%+, 胜率 55%+, 夏普 1.0+

核心思路:
1. 只交易强势股 (价格在 60 日新高附近)
2. 等待回调后突破 (避免追高)
3. 快速止损 + 让利润奔跑
4. 高胜率信号 (8 分制需 6 分)

与 v4.0 的区别:
- 更强调价格强度 (只买强势股)
- 更严格的入场 (回调 + 突破)
- 更快的止损 (3% 紧止损)
- 更高的止盈 (50%+ 让利润奔跑)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_bollinger_bands
from config.logging_config import strategy_logger
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class MarketState(Enum):
    """市场状态"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


@dataclass
class BreakoutStrategyParams:
    """突破策略参数"""
    # 均线系统
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20
    ma_trend: int = 60  # 长期趋势均线

    # 强度判断
    high_period: int = 60  # 60 日新高
    near_high_ratio: float = 0.95  # 距离新高 5% 以内

    # 回调判断
    pullback_ratio: float = 0.05  # 回调 5% 后突破
    pullback_days: int = 5  # 至少回调 5 天

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI
    rsi_period: int = 14
    rsi_strength: float = 55  # RSI>55 表示强势

    # 成交量
    volume_ma_period: int = 20
    volume_ratio_breakout: float = 1.5  # 突破时成交量 1.5 倍

    # 止损止盈
    stop_loss: float = 0.03  # 3% 紧止损
    take_profit: float = 0.50  # 50% 宽止盈
    trailing_stop_trigger: float = 0.15  # 盈利 15% 触发移动止损
    trailing_stop_ratio: float = 0.08  # 回撤 8% 出场

    # 仓位管理
    base_position_ratio: float = 0.20
    max_position_ratio: float = 0.30

    # 信号阈值
    signal_threshold: float = 6.0  # 8 分制需 6 分


class BreakoutStrategy(BaseStrategy):
    """
    强势股突破策略

    入场条件 (8 分制):
    1. 价格在 60 日新高附近 (2 分)
    2. 回调后突破 (2 分)
    3. 均线多头排列 (1.5 分)
    4. MACD 金叉 (1.5 分)
    5. RSI>55 强势 (1 分)
    6. 成交量放大 (1 分)

    出场条件:
    1. 紧止损 3%
    2. 宽止盈 50%
    3. 移动止损 (盈利 15% 后回撤 8% 出场)
    4. 时间止损 (5 日无盈利)
    """

    def __init__(self, name: str = "breakout_v5", params: Optional[BreakoutStrategyParams] = None):
        super().__init__(name)
        self.params = params or BreakoutStrategyParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}
        self.market_state = MarketState.SIDEWAYS

    def on_init(self):
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"突破策略 v5.0 初始化 - 强势股 + 高胜率")
        strategy_logger.info(f"参数：止损={self.params.stop_loss*100}%, "
                            f"止盈={self.params.take_profit*100}%, "
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

            max_history = self.params.ma_trend * 3
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def determine_market_state(self, df: pd.DataFrame) -> MarketState:
        """判断市场状态"""
        if len(df) < self.params.ma_trend:
            return MarketState.SIDEWAYS

        close = df['close']
        ma_long = close.rolling(self.params.ma_trend).mean()

        current_price = close.iloc[-1]
        long_val = ma_long.iloc[-1]

        if current_price > long_val * 1.05:
            return MarketState.BULL
        elif current_price < long_val * 0.95:
            return MarketState.BEAR
        else:
            return MarketState.SIDEWAYS

    def check_price_strength(self, df: pd.DataFrame) -> Tuple[bool, float]:
        """
        检查价格强度
        返回：(是否强势，强度分数)
        """
        close = df['close']
        current_price = close.iloc[-1]

        # 计算 60 日最高价
        high_60 = close.rolling(self.params.high_period).max()
        if len(high_60) < self.params.high_period:
            return False, 0.0

        high_60_val = high_60.iloc[-1]

        # 检查是否在 60 日新高附近 (5% 以内)
        near_high = current_price >= high_60_val * self.params.near_high_ratio

        # 计算强度分数 (距离新高越近分数越高)
        strength = current_price / high_60_val if high_60_val > 0 else 0

        return near_high, strength

    def check_pullback_breakout(self, df: pd.DataFrame) -> Tuple[bool, float]:
        """
        检查回调后突破
        返回：(是否回调突破，回调分数)
        """
        close = df['close']
        current_price = close.iloc[-1]

        if len(close) < self.params.pullback_days + 10:
            return False, 0.0

        # 检查过去 N 天是否有回调
        recent_lows = close.rolling(self.params.pullback_days).min()
        recent_low = recent_lows.iloc[-2] if len(recent_lows) >= 2 else close.iloc[-1]

        # 突破前低
        breakout = current_price > recent_low * 1.02

        # 计算回调深度
        pullback_depth = (close.iloc[-self.params.pullback_days] - recent_low) / close.iloc[-self.params.pullback_days] if close.iloc[-self.params.pullback_days] > 0 else 0

        # 有回调且突破
        has_pullback = pullback_depth >= self.params.pullback_ratio * 0.5  # 至少回调 2.5%

        score = 0.0
        if has_pullback and breakout:
            score = min(1.0, pullback_depth / self.params.pullback_ratio)
        elif breakout:
            score = 0.5

        return breakout, score

    def calculate_signal_score(
        self,
        price_strength: Tuple[bool, float],
        pullback_breakout: Tuple[bool, float],
        golden_cross: bool,
        macd_bullish: bool,
        rsi_strong: bool,
        volume_ok: bool,
        trend_ok: bool,
        perfect_trend: bool
    ) -> Tuple[bool, float]:
        """
        综合评分系统 (8 分制)

        权重分配:
        - 价格强度 (60 日新高附近): 2.0 分
        - 回调后突破：2.0 分
        - 均线多头排列：1.5 分
        - MACD 金叉：1.5 分
        - RSI 强势：0.5 分
        - 成交量放大：0.5 分

        需 6 分才触发买入
        """
        score = 0.0
        max_score = 8.0

        # 1. 价格强度 (2.0 分)
        if price_strength[0]:
            score += 1.5 + price_strength[1] * 0.5  # 1.5-2.0 分

        # 2. 回调突破 (2.0 分)
        if pullback_breakout[0]:
            score += 1.0 + pullback_breakout[1] * 1.0  # 1.0-2.0 分

        # 3. 均线多头排列 (1.5 分)
        if perfect_trend:
            score += 1.5
        elif golden_cross:
            score += 0.8

        # 4. MACD 金叉 (1.5 分)
        if macd_bullish:
            score += 1.5

        # 5. RSI 强势 (0.5 分)
        if rsi_strong:
            score += 0.5

        # 6. 成交量放大 (0.5 分)
        if volume_ok:
            score += 0.5

        # 趋势过滤
        if not trend_ok:
            score *= 0.5  # 趋势不好减半

        buy_signal = score >= self.params.signal_threshold
        signal_strength = min(1.0, score / max_score)

        return buy_signal, signal_strength

    def check_exit_conditions(
        self,
        ts_code: str,
        current_price: float,
        atr: float
    ) -> Optional[Tuple[str, str]]:
        """检查出场条件"""
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']
        entry_date = pos.get('entry_date', '')

        # 更新最高价
        if current_price > pos.get('highest_price', 0):
            self.positions[ts_code]['highest_price'] = current_price
        highest_price = self.positions[ts_code].get('highest_price', entry_price)

        # 当前盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price
        highest_profit = (highest_price - entry_price) / entry_price

        # === 1. 紧止损 (3%) ===
        if profit_ratio <= -self.params.stop_loss:
            return ('sell', f'止损 ({profit_ratio:.1%}, SL={-self.params.stop_loss:.1%})')

        # === 2. 宽止盈 (50%) ===
        if profit_ratio >= self.params.take_profit:
            return ('sell', f'止盈 ({profit_ratio:.1%}, TP={self.params.take_profit:.1%})')

        # === 3. 移动止损 (盈利 15% 后回撤 8% 出场) ===
        if highest_profit >= self.params.trailing_stop_trigger:
            drawdown = (highest_price - current_price) / highest_price
            if drawdown >= self.params.trailing_stop_ratio:
                return ('sell', f'移动止损 (回撤{drawdown:.1%})')

        # === 4. 时间止损 (5 日无盈利) ===
        if hasattr(self, 'current_date') and entry_date:
            try:
                from datetime import datetime
                entry_dt = datetime.strptime(entry_date, '%Y%m%d')
                current_dt = datetime.strptime(self.current_date, '%Y%m%d')
                holding_days = (current_dt - entry_dt).days
                if holding_days >= 5 and profit_ratio < 0.03:
                    return ('sell', f'时间止损 ({holding_days}日)')
            except:
                pass

        return None

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        self.current_date = current_date
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            required_len = self.params.ma_trend + self.params.high_period
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

            # 成交量均线
            vol_ma = vol.rolling(self.params.volume_ma_period).mean()

            # 计算 ATR
            high = df['high']
            low = df['low']
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1] / close.iloc[-1] if close.iloc[-1] > 0 else 0.02

            # 判断市场状态
            self.market_state = self.determine_market_state(df)

            # === 检查出场条件 ===
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

            # === 检查入场信号 ===

            # 1. 价格强度
            price_strength = self.check_price_strength(df)

            # 2. 回调突破
            pullback_breakout = self.check_pullback_breakout(df)

            # 3. 均线金叉
            golden_cross = (ma_short.iloc[-2] <= ma_long.iloc[-2] and
                           ma_short.iloc[-1] > ma_long.iloc[-1])

            # 4. 完美多头排列
            perfect_trend = (ma_short.iloc[-1] > ma_mid.iloc[-1] > ma_long.iloc[-1] and
                            ma_short.iloc[-1] > ma_short.iloc[-2] and
                            ma_mid.iloc[-1] > ma_mid.iloc[-2])

            # 5. MACD 金叉
            macd_bullish = dif > dea and macd > 0

            # 6. RSI 强势
            rsi_strong = current_rsi >= self.params.rsi_strength

            # 7. 成交量放大
            current_vol = bar.get('vol', 0)
            current_vol_ma = vol_ma.iloc[-1] if len(vol_ma) > 0 else 0
            volume_ok = current_vol > current_vol_ma * self.params.volume_ratio_breakout if current_vol_ma > 0 else True

            # 8. 趋势向上
            trend_ok = current_price > ma_trend.iloc[-1] * 1.02

            # 综合评分
            buy_signal, signal_strength = self.calculate_signal_score(
                price_strength, pullback_breakout, golden_cross, macd_bullish,
                rsi_strong, volume_ok, trend_ok, perfect_trend
            )

            # === 生成买入信号 ===
            if buy_signal and ts_code not in self.positions:
                # 根据市场状态调整仓位
                if self.market_state == MarketState.BEAR:
                    position_ratio = self.params.base_position_ratio * 0.3
                elif self.market_state == MarketState.SIDEWAYS:
                    position_ratio = self.params.base_position_ratio * 0.7
                else:
                    position_ratio = self.params.base_position_ratio

                volume = int(self.engine.capital * position_ratio / current_price / 100) * 100

                if volume >= 100:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=current_price,
                        volume=volume,
                        strength=signal_strength,
                        reason=f"突破信号 (强度{signal_strength:.1f}, RSI={current_rsi:.0f})"
                    ))
                    self.positions[ts_code] = {
                        'entry_price': current_price,
                        'highest_price': current_price,
                        'shares': volume,
                        'entry_date': current_date,
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


def create_breakout_strategy(
    stop_loss: float = None,
    take_profit: float = None,
    signal_threshold: float = None,
) -> BreakoutStrategy:
    """创建突破策略"""
    params = BreakoutStrategyParams()

    if stop_loss is not None:
        params.stop_loss = stop_loss
    if take_profit is not None:
        params.take_profit = take_profit
    if signal_threshold is not None:
        params.signal_threshold = signal_threshold

    return BreakoutStrategy(name="breakout_v5", params=params)


if __name__ == "__main__":
    # 简单测试
    from src.backtest.engine import BacktestEngine
    from src.data_collector.data_manager import data_manager

    ORIGINAL_STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
    START_DATE = '20240324'
    END_DATE = '20260323'
    INITIAL_CAPITAL = 1000000

    data_dict = {}
    for ts_code in ORIGINAL_STOCKS:
        df = data_manager.get_daily_quotes(ts_code, START_DATE, END_DATE)
        if not df.empty:
            data_dict[ts_code] = df

    print(f"加载 {len(data_dict)} 只股票")

    strategy = create_breakout_strategy()
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)
    result = engine.run(data_dict)

    print(f"\n回测结果:")
    print(f"总收益：{(result.final_capital/INITIAL_CAPITAL-1)*100:.2f}%")
    print(f"年化收益：{result.annual_return*100:.2f}%")
    print(f"夏普比率：{result.sharpe_ratio:.2f}")
    print(f"最大回撤：{result.max_drawdown*100:.2f}%")
    print(f"胜率：{result.win_rate*100:.1f}%")
    print(f"盈亏比：{result.profit_factor:.2f}")
