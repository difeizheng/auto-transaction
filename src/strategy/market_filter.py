"""
市场状态过滤模块
基于沪深 300 指数判断市场状态，指导仓位控制

核心逻辑:
1. 双均线系统判断趋势
2. 市场宽度确认
3. 波动率过滤
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from config.logging_config import strategy_logger


class MarketState(Enum):
    """市场状态"""
    BULL = "bull"          # 牛市 - 正常交易
    BULL_WEAK = "bull_weak"  # 弱牛市 - 轻仓
    SIDEWAYS_WEAK = "sideways_weak"   # 震荡偏强 - 轻仓
    SIDEWAYS_STRONG = "sideways_strong"  # 震荡偏弱 - 轻仓
    BEAR = "bear"          # 熊市 - 空仓
    BEAR_WEAK = "bear_weak"  # 弱熊市 - 轻仓


@dataclass
class MarketFilterParams:
    """市场过滤参数"""
    # 均线判断
    ma_short: int = 20          # 短期均线
    ma_long: int = 60           # 长期均线
    ma_trend: int = 120         # 趋势均线 (半年线)

    # 趋势确认
    trend_confirm_days: int = 3  # 连续确认天数

    # 阈值设置
    bull_threshold: float = 0.05    # 牛市阈值：价格>MA60*1.05
    bear_threshold: float = -0.05   # 熊市阈值：价格<MA60*0.95

    # MACD 参数
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_weight: float = 0.25  # MACD 评分权重

    # RSI 参数
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30
    rsi_weight: float = 0.15  # RSI 评分权重

    # 波动率过滤
    vol_window: int = 20        # 波动率计算窗口
    vol_threshold: float = 2.0  # 波动率阈值 (超过 2 倍平均波动率时减仓)

    # 仓位控制
    bull_position: float = 1.0      # 牛市仓位系数 100%
    bull_weak_position: float = 0.7  # 弱牛市仓位系数 70%
    sideways_position: float = 0.4  # 震荡市仓位系数 40% (提升从 30%)
    bear_weak_position: float = 0.2  # 弱熊市仓位系数 20%
    bear_position: float = 0.0      # 熊市仓位系数 0%


class MarketFilter:
    """
    市场状态过滤器

    判断逻辑:
    1. 价格 vs MA60 位置
    2. MA20 vs MA60 关系
    3. 连续趋势确认
    4. 波动率异常检测
    """

    def __init__(self, params: Optional[MarketFilterParams] = None):
        self.params = params or MarketFilterParams()
        self.market_state = MarketState.SIDEWAYS_WEAK
        self.market_data: Optional[pd.DataFrame] = None
        self.state_history: list = []  # 状态历史

    def set_market_data(self, market_df: pd.DataFrame):
        """设置市场数据 (沪深 300)"""
        self.market_data = market_df

    def calculate_ma(self, close: pd.Series, period: int) -> pd.Series:
        """计算移动平均"""
        return close.rolling(window=period).mean()

    def calculate_volatility(self, close: pd.Series) -> pd.Series:
        """计算波动率 (收益率标准差)"""
        returns = close.pct_change()
        return returns.rolling(window=self.params.vol_window).std()

    def calculate_macd(self, close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算 MACD 指标"""
        ema_fast = close.ewm(span=self.params.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.params.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.params.macd_signal, adjust=False).mean()
        hist_line = macd_line - signal_line
        return macd_line, signal_line, hist_line

    def calculate_rsi(self, close: pd.Series) -> pd.Series:
        """计算 RSI 指标"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def determine_market_state(self) -> MarketState:
        """
        判断市场状态

        返回:
            MarketState: 当前市场状态
        """
        if self.market_data is None or len(self.market_data) < self.params.ma_long + 5:
            return MarketState.SIDEWAYS_WEAK

        close = self.market_data['close']

        # 计算均线
        ma_short = self.calculate_ma(close, self.params.ma_short)
        ma_long = self.calculate_ma(close, self.params.ma_long)

        current_price = close.iloc[-1]
        short_val = ma_short.iloc[-1]
        long_val = ma_long.iloc[-1]
        short_prev = ma_short.iloc[-2]
        long_prev = ma_long.iloc[-2]

        # 价格相对位置
        price_position = (current_price - long_val) / long_val

        # 均线关系
        ma_golden = short_val > long_val  # 金叉状态
        ma_death = short_val < long_val   # 死叉状态

        # 均线斜率
        short_slope = short_val - short_prev
        long_slope = long_val - long_prev

        # 连续趋势确认 (最近 N 天)
        bull_days = 0
        bear_days = 0
        for i in range(self.params.trend_confirm_days):
            idx = -1 - i
            if idx >= -len(self.market_data):
                s_val = ma_short.iloc[idx]
                l_val = ma_long.iloc[idx]
                if s_val > l_val:
                    bull_days += 1
                elif s_val < l_val:
                    bear_days += 1

        # 综合评分
        bull_score = 0
        bear_score = 0

        # 价格位置评分
        if price_position > self.params.bull_threshold:
            bull_score += 2
        elif price_position > 0:
            bull_score += 1

        if price_position < self.params.bear_threshold:
            bear_score += 2
        elif price_position < 0:
            bear_score += 1

        # 均线关系评分
        if ma_golden and bull_days >= self.params.trend_confirm_days:
            bull_score += 2
        elif ma_golden:
            bull_score += 1

        if ma_death and bear_days >= self.params.trend_confirm_days:
            bear_score += 2
        elif ma_death:
            bear_score += 1

        # 均线斜率评分
        if short_slope > 0 and long_slope > 0:
            bull_score += 1
        if short_slope < 0 and long_slope < 0:
            bear_score += 1

        # MACD 评分 (新增加)
        macd_line, signal_line, hist_line = self.calculate_macd(close)
        macd_current = macd_line.iloc[-1]
        macd_prev = macd_line.iloc[-2]
        hist_current = hist_line.iloc[-1]

        if macd_current > 0 and hist_current > 0:
            bull_score += int(2 * self.params.macd_weight)
        if macd_current > macd_prev:
            bull_score += int(1 * self.params.macd_weight)
        if macd_current < 0 and hist_current < 0:
            bear_score += int(2 * self.params.macd_weight)
        if macd_current < macd_prev:
            bear_score += int(1 * self.params.macd_weight)

        # RSI 评分 (新增加)
        rsi = self.calculate_rsi(close)
        rsi_current = rsi.iloc[-1]

        if rsi_current > 50 and rsi_current < self.params.rsi_overbought:
            bull_score += int(1 * self.params.rsi_weight)
        if rsi_current > self.params.rsi_overbought:
            # 超买，可能回调
            bear_score += int(1 * self.params.rsi_weight)
        if rsi_current < self.params.rsi_oversold:
            # 超卖，可能反弹
            bull_score += int(2 * self.params.rsi_weight)
        elif rsi_current < 40:
            bull_score += int(1 * self.params.rsi_weight)

        # 波动率检查
        volatility = self.calculate_volatility(close).iloc[-1]
        avg_volatility = self.calculate_volatility(close).iloc[-self.params.vol_window:].mean()
        high_volatility = volatility > avg_volatility * self.params.vol_threshold if avg_volatility > 0 else False

        # 高波动率减仓信号
        if high_volatility:
            strategy_logger.debug(f"波动率异常：当前={volatility:.4f}, 平均={avg_volatility:.4f}")

        # 确定市场状态 (细化判断)
        total_bull = bull_score
        total_bear = bear_score

        if total_bull >= 6:
            self.market_state = MarketState.BULL
        elif total_bull >= 4:
            self.market_state = MarketState.BULL_WEAK
        elif total_bull >= 2:
            self.market_state = MarketState.SIDEWAYS_WEAK
        elif total_bear >= 6:
            self.market_state = MarketState.BEAR
        elif total_bear >= 4:
            self.market_state = MarketState.BEAR_WEAK
        elif total_bear >= 2:
            self.market_state = MarketState.SIDEWAYS_STRONG
        else:
            self.market_state = MarketState.SIDEWAYS_WEAK

        # 记录状态历史
        self.state_history.append(self.market_state)
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]

        strategy_logger.debug(
            f"市场状态：{self.market_state.value}, "
            f"价格位置：{price_position:.2%}, "
            f"RSI: {rsi_current:.1f}, "
            f"bull_score={total_bull}, bear_score={total_bear}"
        )

        return self.market_state

    def get_position_multiplier(self) -> float:
        """
        获取仓位系数

        返回:
            float: 仓位乘数 (0.0-1.0)
        """
        state = self.determine_market_state()

        if state == MarketState.BULL:
            return self.params.bull_position
        elif state == MarketState.BULL_WEAK:
            return self.params.bull_weak_position
        elif state in [MarketState.SIDEWAYS_WEAK, MarketState.SIDEWAYS_STRONG]:
            return self.params.sideways_position
        elif state == MarketState.BEAR_WEAK:
            return self.params.bear_weak_position
        else:  # BEAR
            return self.params.bear_position

    def is_tradeable(self) -> bool:
        """
        判断是否可交易

        返回:
            bool: 是否可交易
        """
        state = self.determine_market_state()
        return state != MarketState.BEAR

    def get_state_summary(self) -> Dict:
        """获取市场状态摘要"""
        if not self.state_history:
            return {'current': 'unknown', 'bull_ratio': 0, 'bear_ratio': 0}

        bull_count = sum(1 for s in self.state_history if s == MarketState.BULL)
        bear_count = sum(1 for s in self.state_history if s == MarketState.BEAR)
        total = len(self.state_history)

        return {
            'current': self.market_state.value,
            'bull_ratio': bull_count / total if total > 0 else 0,
            'bear_ratio': bear_count / total if total > 0 else 0,
            'sideways_ratio': 1 - (bull_count + bear_count) / total if total > 0 else 0
        }


# 工厂函数
def create_market_filter(
    ma_short: int = 20,
    ma_long: int = 60,
    bull_threshold: float = 0.05,
    bear_threshold: float = -0.05,
    sideways_position: float = 0.3
) -> MarketFilter:
    """创建市场过滤器"""
    params = MarketFilterParams(
        ma_short=ma_short,
        ma_long=ma_long,
        bull_threshold=bull_threshold,
        bear_threshold=bear_threshold,
        sideways_position=sideways_position
    )
    return MarketFilter(params)
