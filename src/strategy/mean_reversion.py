"""
均值回归策略
基于超买超卖和价格反转逻辑，捕捉回调买入机会

核心逻辑:
1. 识别超买超卖状态 (RSI + 布林带)
2. 等待价格 extreme 偏离均值
3. 在反转信号出现时入场
4. 均值回归后出场
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_rsi, calculate_bollinger_bands
from config.logging_config import strategy_logger


@dataclass
class MeanReversionParams:
    """均值回归策略参数"""
    # RSI 参数
    rsi_period: int = 14
    rsi_oversold: float = 25     # 超卖阈值 25
    rsi_overbought: float = 75   # 超买阈值 75

    # 布林带参数
    bb_window: int = 20
    bb_num_std: float = 2.5      # 标准差倍数 (更宽)

    # 均值回归
    mean_window: int = 30        # 均值计算窗口
    deviation_threshold: float = 0.15  # 偏离阈值 15%

    # 出场参数
    target_profit: float = 0.08  # 目标收益 8%
    stop_loss: float = 0.06      # 止损 6%
    time_exit_days: int = 5      # 时间出场天数


class MeanReversionStrategy(BaseStrategy):
    """
    均值回归策略

    核心思路:
    1. 超卖时买入，超买时卖出
    2. 价格偏离均值过大时反向交易
    3. 快速获利了结，严格止损
    """

    def __init__(
        self,
        name: str = "mean_reversion",
        params: Optional[MeanReversionParams] = None
    ):
        super().__init__(name)
        self.params = params or MeanReversionParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"均值回归策略初始化")
        strategy_logger.info(f"参数：RSI 超卖={self.params.rsi_oversold}, "
                            f"布林带={self.params.bb_num_std}std")

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
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            )

            max_history = self.params.mean_window * 2
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def is_oversold(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查是否超卖

        Returns:
            (是否超卖，原因)
        """
        close = df['close']

        # 1. RSI 超卖
        rsi = calculate_rsi(close, self.params.rsi_period)
        current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50

        # 2. 布林带下轨
        bb_data = calculate_bollinger_bands(close, self.params.bb_window, self.params.bb_num_std)
        bb_lower = bb_data['lower'].iloc[-1] if len(bb_data) > 0 else 0
        current_price = close.iloc[-1]

        # 3. 均值偏离
        mean_price = close.rolling(self.params.mean_window).mean().iloc[-1]
        deviation = (current_price - mean_price) / mean_price if mean_price > 0 else 0

        # 综合判断
        reasons = []
        oversold_score = 0

        if current_rsi < self.params.rsi_oversold:
            oversold_score += 1
            reasons.append(f'RSI 超卖 ({current_rsi:.0f})')

        if current_price <= bb_lower * 1.01:  # 触及或跌破下轨
            oversold_score += 1
            reasons.append(f'布林带下轨 ({current_price:.2f} <= {bb_lower:.2f})')

        if deviation < -self.params.deviation_threshold:
            oversold_score += 1
            reasons.append(f'均值偏离 ({deviation:.1%})')

        return oversold_score >= 2, ', '.join(reasons) if reasons else ''

    def check_exit_conditions(
        self,
        ts_code: str,
        current_price: float,
        df: pd.DataFrame
    ) -> Optional[Tuple[str, str]]:
        """检查出场条件"""
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']
        entry_date = pos.get('entry_date', '')

        # 当前盈亏
        profit_ratio = (current_price - entry_price) / entry_price

        # === 1. 目标止盈 ===
        if profit_ratio >= self.params.target_profit:
            return ('sell', f'止盈 ({profit_ratio:.1%} >= {self.params.target_profit:.1%})')

        # === 2. 止损出场 ===
        if profit_ratio <= -self.params.stop_loss:
            return ('sell', f'止损 ({profit_ratio:.1%} <= {-self.params.stop_loss:.1%})')

        # === 3. RSI 超买出场 ===
        close = df['close']
        rsi = calculate_rsi(close, self.params.rsi_period)
        current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50

        if current_rsi > self.params.rsi_overbought and profit_ratio > 0:
            return ('sell', f'RSI 超买 ({current_rsi:.0f})')

        # === 4. 布林带上轨出场 ===
        bb_data = calculate_bollinger_bands(close, self.params.bb_window, self.params.bb_num_std)
        bb_upper = bb_data['upper'].iloc[-1] if len(bb_data) > 0 else 0

        if current_price >= bb_upper * 0.98 and profit_ratio > 0:
            return ('sell', '触及布林带上轨')

        # === 5. 时间出场 ===
        if entry_date:
            try:
                from datetime import datetime
                entry_dt = datetime.strptime(entry_date, '%Y%m%d')
                current_dt = datetime.strptime(self.current_date, '%Y%m%d')
                holding_days = (current_dt - entry_dt).days

                if holding_days >= self.params.time_exit_days:
                    if profit_ratio < self.params.target_profit * 0.5:  # 盈利未达一半
                        return ('sell', f'时间出场 ({holding_days}日)')
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
            required_len = self.params.mean_window + self.params.bb_window
            if len(df) < required_len:
                continue

            current_price = bar.get('close', 0)

            # === 检查出场 (如果已持仓) ===
            if ts_code in self.positions:
                exit_result = self.check_exit_conditions(ts_code, current_price, df)
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

            # === 检查入场条件 ===

            # 1. 超卖判断
            is_oversold, reason = self.is_oversold(df)
            if not is_oversold:
                continue

            # 2. 等待反转信号 (当日收阳)
            if len(df) >= 2:
                today_close = df['close'].iloc[-1]
                yesterday_close = df['close'].iloc[-2]
                if today_close <= yesterday_close:  # 未反转
                    continue

            # 3. 计算信号强度
            # RSI 越低、偏离越大，信号越强
            rsi = calculate_rsi(df['close'], self.params.rsi_period)
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50

            close = df['close']
            mean_price = close.rolling(self.params.mean_window).mean().iloc[-1]
            deviation = (current_price - mean_price) / mean_price if mean_price > 0 else 0

            # 信号强度 (0-1)
            rsi_score = max(0, (self.params.rsi_oversold - current_rsi) / self.params.rsi_oversold)
            dev_score = max(0, -deviation / self.params.deviation_threshold)
            signal_strength = min(1.0, (rsi_score * 0.6 + dev_score * 0.4))

            # 4. 生成买入信号
            volume = self.calculate_position_size(ts_code, signal_strength, current_price)
            if volume >= 100:
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='buy',
                    price=current_price,
                    volume=volume,
                    strength=signal_strength,
                    reason=f'均值回归 ({reason})',
                ))

                # 记录持仓
                self.positions[ts_code] = {
                    'entry_price': current_price,
                    'shares': volume,
                    'entry_date': current_date,
                }

        return signals

    def calculate_position_size(
        self,
        ts_code: str,
        signal_strength: float,
        current_price: float
    ) -> int:
        """计算仓位"""
        # 基础仓位 15% (均值回归风险较高，仓位较低)
        base_ratio = 0.15

        # 根据信号强度调整
        position_ratio = base_ratio * signal_strength

        # 计算仓位价值
        total_capital = self.engine.capital if self.engine else 1000000
        target_value = total_capital * position_ratio

        # 计算股数 (100 股的整数倍)
        volume = int(target_value / current_price / 100) * 100

        return max(100, volume)


if __name__ == "__main__":
    strategy = MeanReversionStrategy()
    strategy.on_init()
    print("均值回归策略初始化完成")
