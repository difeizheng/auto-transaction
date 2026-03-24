"""
高质量趋势跟踪策略
基于简化信号系统 + 市场状态过滤 + 智能止损止盈

核心逻辑:
1. 简化信号系统 - 只保留最有效的 3-4 个因子
2. 市场状态过滤 - 只在牛市/震荡市交易
3. 智能止损止盈 - 小止损、大止盈、让利润奔跑
4. 选股优化 - 只交易高质量股票
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi
from config.logging_config import strategy_logger


class MarketState(Enum):
    """市场状态"""
    BULL = "bull"      # 牛市 - 正常交易
    SIDEWAYS = "sideways"  # 震荡市 - 轻仓
    BEAR = "bear"      # 熊市 - 空仓


@dataclass
class HQStrategyParams:
    """高质量策略参数"""
    # === 信号系统 ===
    lookback_high: int = 20       # 价格突破周期
    volume_ratio_threshold: float = 1.5  # 成交量放大阈值
    rsi_min: float = 50           # RSI 最小值
    rsi_max: float = 70           # RSI 最大值 (避免超买)

    # === 趋势过滤 ===
    ma_trend: int = 60            # 趋势均线
    ma_short: int = 20            # 短期均线

    # === 市场状态判断 (沪深 300) ===
    market_ma_short: int = 20     # 市场短期均线
    market_ma_long: int = 60      # 市场长期均线

    # === 止损止盈 ===
    initial_stop_loss: float = 0.06    # 初始止损 6%
    initial_take_profit: float = 0.15  # 初始止盈 15%
    trailing_stop_trigger: float = 0.08  # 移动止损触发点 8%
    trailing_stop_ratio: float = 0.03    # 移动止损回撤 3%

    # === 分级止盈 ===
    partial_profit_1: float = 0.10     # 第一级止盈 10%
    partial_ratio_1: float = 0.5       # 卖出 50%
    partial_profit_2: float = 0.20     # 第二级止盈 20%
    partial_ratio_2: float = 0.25      # 卖出 25%

    # === 时间止损 ===
    time_stop_days: int = 5            # 时间止损天数
    time_stop_profit_threshold: float = 0.02  # 时间止损盈利阈值

    # === 仓位管理 ===
    base_position_ratio: float = 0.20  # 基础仓位 20%
    bull_position_ratio: float = 0.25  # 牛市仓位 25%
    sideways_position_ratio: float = 0.10  # 震荡市仓位 10%
    bear_position_ratio: float = 0.0   # 熊市仓位 0%

    # === 信号阈值 ===
    signal_threshold: float = 4.0      # 信号触发阈值 (总分 6.0)


class HQTrendStrategy(BaseStrategy):
    """
    高质量趋势跟踪策略

    信号评分 (总分 6.0 分，≥4.0 分触发):
    - 价格突破 20 日高：2.0 分 (核心动量信号)
    - 成交量放大>50%:1.5 分 (资金确认)
    - RSI(14) 在 50-70:1.0 分 (动量健康)
    - 价格>MA60:1.0 分 (趋势过滤)
    - MACD>0:0.5 分 (辅助确认)
    """

    def __init__(
        self,
        name: str = "hq_trend_strategy",
        params: Optional[HQStrategyParams] = None
    ):
        super().__init__(name)
        self.params = params or HQStrategyParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}
        self.market_state = MarketState.SIDEWAYS
        self.market_data: Optional[pd.DataFrame] = None  # 沪深 300 数据

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"高质量趋势策略初始化")
        strategy_logger.info(f"参数：止损={self.params.initial_stop_loss*100}%, "
                            f"止盈={self.params.initial_take_profit*100}%, "
                            f"阈值={self.params.signal_threshold}/6.0")

    def set_market_data(self, market_df: pd.DataFrame):
        """设置市场数据 (沪深 300)"""
        self.market_data = market_df

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

            # 保留足够数据
            max_history = self.params.ma_trend * 3
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def determine_market_state(self) -> MarketState:
        """
        判断市场状态 (基于沪深 300 指数)

        牛市：MA20>MA60 且 价格>MA60
        震荡市：价格在 MA60 附近±3%
        熊市：MA20<MA60 且 价格<MA60
        """
        if self.market_data is None or len(self.market_data) < self.params.market_ma_long + 5:
            return MarketState.SIDEWAYS

        close = self.market_data['close']
        ma_short = close.rolling(self.params.market_ma_short).mean()
        ma_long = close.rolling(self.params.market_ma_long).mean()

        current_price = close.iloc[-1]
        short_val = ma_short.iloc[-1]
        long_val = ma_long.iloc[-1]

        # 计算价格相对位置
        price_vs_ma = (current_price - long_val) / long_val

        # 判断市场状态
        if short_val > long_val and price_vs_ma > 0.02:
            return MarketState.BULL
        elif short_val < long_val and price_vs_ma < -0.02:
            return MarketState.BEAR
        else:
            return MarketState.SIDEWAYS

    def calculate_signal_score(
        self,
        df: pd.DataFrame,
        current_price: float
    ) -> Tuple[bool, float]:
        """
        计算信号评分 (简化版 - 只保留最有效因子)

        返回：(是否买入，信号强度)
        """
        if len(df) < self.params.lookback_high + 10:
            return False, 0.0

        close = df['close']
        vol = df['vol']

        score = 0.0
        max_score = 6.0

        # 1. 价格突破 20 日高 (2.0 分) - 核心动量信号
        highest_high = close.rolling(self.params.lookback_high).max().iloc[-2]  # 昨日高点
        if current_price > highest_high * 1.01:  # 突破 1% 以上
            score += 2.0

        # 2. 成交量放大 (1.5 分) - 资金确认
        vol_ma = vol.rolling(20).mean()
        current_vol = vol.iloc[-1]
        prev_vol_ma = vol_ma.iloc[-2] if len(vol_ma) >= 2 else current_vol
        if prev_vol_ma > 0 and current_vol > prev_vol_ma * self.params.volume_ratio_threshold:
            score += 1.5

        # 3. RSI 在健康区间 (1.0 分) - 动量确认
        rsi = calculate_rsi(close, 14)
        current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50
        if self.params.rsi_min <= current_rsi <= self.params.rsi_max:
            score += 1.0

        # 4. 价格在 MA60 上方 (1.0 分) - 趋势过滤
        ma_long = close.rolling(self.params.ma_trend).mean().iloc[-1]
        if current_price > ma_long * 1.02:  # 价格在 MA60 上方 2%
            score += 1.0

        # 5. MACD > 0 (0.5 分) - 辅助确认
        macd_data = calculate_macd(close, 12, 26, 9)
        if len(macd_data) > 0:
            macd_val = macd_data['macd'].iloc[-1]
            if macd_val > 0:
                score += 0.5

        # 判断是否买入 (需要达到阈值且在趋势向上时)
        trend_ok = current_price > ma_long
        buy_signal = score >= self.params.signal_threshold and trend_ok
        signal_strength = min(1.0, score / max_score)

        return buy_signal, signal_strength

    def calculate_position_size(
        self,
        signal_strength: float,
        current_price: float
    ) -> int:
        """根据市场状态和信号强度计算仓位"""
        # 根据市场状态确定基础仓位
        if self.market_state == MarketState.BULL:
            position_ratio = self.params.bull_position_ratio
        elif self.market_state == MarketState.SIDEWAYS:
            position_ratio = self.params.sideways_position_ratio
        else:  # BEAR
            position_ratio = self.params.bear_position_ratio

        # 根据信号强度调整
        position_ratio *= (0.5 + signal_strength * 0.5)  # 0.5-1.0 倍

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
        current_date: str
    ) -> Optional[Tuple[str, str]]:
        """
        检查出场条件 (智能止损止盈)

        1. 初始止损：-6%
        2. 初始止盈：+15%
        3. 分级止盈：10% 卖 50%, 20% 再卖 25%
        4. 移动止损：盈利>8% 后，回撤 3% 出场
        5. 时间止损：5 日无盈利出场
        """
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']
        entry_date = pos.get('entry_date', '')
        highest_price = pos.get('highest_price', entry_price)
        original_shares = pos.get('original_shares', 0)
        current_shares = pos.get('shares', original_shares)

        # 更新最高价
        if current_price > highest_price:
            self.positions[ts_code]['highest_price'] = current_price
            highest_price = current_price

        # 当前盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price
        highest_profit = (highest_price - entry_price) / entry_price

        # === 1. 初始止损 ===
        if profit_ratio <= -self.params.initial_stop_loss:
            return ('sell', f'止损 ({profit_ratio:.1%}, SL={-self.params.initial_stop_loss:.1%})')

        # === 2. 初始止盈 ===
        if profit_ratio >= self.params.initial_take_profit:
            return ('sell', f'止盈 ({profit_ratio:.1%}, TP={self.params.initial_take_profit:.1%})')

        # === 3. 分级止盈 ===
        # 第一级：盈利 10% 卖出 50%
        if (profit_ratio >= self.params.partial_profit_1 and
            not pos.get('partial_sold_1', False) and
            current_shares == original_shares):
            # 记录部分止盈，但不完全出场
            self.positions[ts_code]['partial_sold_1'] = True
            # 返回部分卖出信号 (这里简化处理，继续持有观察)

        # 第二级：盈利 20% 再卖 25%
        if (profit_ratio >= self.params.partial_profit_2 and
            not pos.get('partial_sold_2', False) and
            current_shares == original_shares):
            self.positions[ts_code]['partial_sold_2'] = True

        # === 4. 移动止损 (盈利>8% 后激活) ===
        if highest_profit >= self.params.trailing_stop_trigger:
            drawdown = (highest_price - current_price) / highest_price
            if drawdown >= self.params.trailing_stop_ratio:
                return ('sell', f'移动止损 (回撤{drawdown:.1%})')

        # === 5. 时间止损 (5 日无盈利) ===
        if entry_date:
            try:
                entry_dt = datetime.strptime(entry_date, '%Y%m%d')
                current_dt = datetime.strptime(current_date, '%Y%m%d')
                holding_days = (current_dt - entry_dt).days

                if (holding_days >= self.params.time_stop_days and
                    profit_ratio < self.params.time_stop_profit_threshold):
                    return ('sell', f'时间止损 ({holding_days}日，盈利{profit_ratio:.1%})')
            except:
                pass

        return None

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        # 更新价格历史
        self.update_price_history(data, current_date)

        # 判断市场状态
        self.market_state = self.determine_market_state()
        strategy_logger.debug(f"市场状态：{self.market_state.value}")

        signals = []

        for ts_code, bar in data.items():
            # 检查是否有足够数据
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            required_len = self.params.ma_trend + 10
            if len(df) < required_len:
                continue

            current_price = bar.get('close', 0)

            # === 检查出场条件 (如果已持仓) ===
            if ts_code in self.positions:
                exit_result = self.check_exit_conditions(ts_code, current_price, current_date)
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

            # === 熊市过滤 ===
            if self.market_state == MarketState.BEAR:
                continue  # 熊市不买入

            # === 计算信号评分 ===
            buy_signal, signal_strength = self.calculate_signal_score(df, current_price)

            # === 生成买入信号 ===
            if buy_signal and ts_code not in self.positions:
                volume = self.calculate_position_size(signal_strength, current_price)
                if volume >= 100:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=current_price,
                        volume=volume,
                        strength=signal_strength,
                        reason=f"趋势突破 (强度{signal_strength:.1f})"
                    ))
                    # 记录持仓
                    self.positions[ts_code] = {
                        'entry_price': current_price,
                        'highest_price': current_price,
                        'shares': volume,
                        'original_shares': volume,
                        'entry_date': current_date,
                        'partial_sold_1': False,
                        'partial_sold_2': False
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
def create_hq_trend_strategy(
    stop_loss: float = None,
    take_profit: float = None,
    signal_threshold: float = None,
    aggressive: bool = False
) -> HQTrendStrategy:
    """创建高质量趋势策略"""
    default_params = HQStrategyParams()

    if stop_loss is None:
        stop_loss = default_params.initial_stop_loss
    if take_profit is None:
        take_profit = default_params.initial_take_profit
    if signal_threshold is None:
        signal_threshold = default_params.signal_threshold

    if aggressive:
        params = HQStrategyParams(
            initial_stop_loss=stop_loss,
            initial_take_profit=take_profit,
            signal_threshold=signal_threshold,
            bull_position_ratio=0.30,
            sideways_position_ratio=0.15,
        )
        return HQTrendStrategy(name="hq_trend_aggro", params=params)
    else:
        params = HQStrategyParams(
            initial_stop_loss=stop_loss,
            initial_take_profit=take_profit,
            signal_threshold=signal_threshold,
        )
        return HQTrendStrategy(name="hq_trend", params=params)
