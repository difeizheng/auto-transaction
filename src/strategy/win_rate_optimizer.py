"""
胜率优化模块
优化方向：
1. 新增动量因子 - 检测价格动能
2. 新增主力资金因子 - 跟踪大单流向
3. 股票池动态筛选强势股
4. 信号质量优化 - 提高买入信号准确性

目标：胜率 51.4% -> 55%+
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class MomentumStrength(Enum):
    """动量强度等级"""
    STRONG_POSITIVE = "strong_positive"  # 强正动量
    WEAK_POSITIVE = "weak_positive"      # 弱正动量
    NEUTRAL = "neutral"                   # 中性
    WEAK_NEGATIVE = "weak_negative"      # 弱负动量
    STRONG_NEGATIVE = "strong_negative"  # 强负动量


@dataclass
class WinRateOptimizationConfig:
    """胜率优化配置"""
    # 动量因子
    use_momentum_factor: bool = True
    momentum_period: int = 10  # 动量计算周期
    min_momentum_score: float = 0.3  # 最小动量得分

    # 资金流向因子
    use_money_flow_factor: bool = True
    money_flow_period: int = 5  # 资金流计算周期
    min_money_flow_score: float = 0.4  # 最小资金流得分

    # 强势股筛选
    use_stock_filter: bool = True
    strength_lookback: int = 20  # 强度计算周期
    min_strength_rank: float = 0.5  # 最小强度排名 (前 50%)

    # 信号质量优化
    use_signal_quality: bool = True
    min_signal_confidence: float = 0.6  # 最小信号置信度


class WinRateOptimizer:
    """胜率优化器"""

    def __init__(self, config: Optional[WinRateOptimizationConfig] = None):
        self.config = config or WinRateOptimizationConfig()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.stock_strength_cache: Dict[str, float] = {}

    def update_price_history(self, ts_code: str, data: pd.DataFrame):
        """更新价格历史"""
        self.price_history[ts_code] = data

    # ==================== 动量因子 ====================

    def calculate_momentum(self, ts_code: str) -> float:
        """
        计算动量得分

        基于：
        1. 价格动量 (ROC 变化率)
        2. 相对强度 (vs 市场)
        3. 动量持续性

        Returns:
            动量得分 (-1 到 1)
        """
        if not self.config.use_momentum_factor:
            return 0

        if ts_code not in self.price_history:
            return 0

        df = self.price_history[ts_code]
        period = self.config.momentum_period

        if len(df) < period * 2:
            return 0

        close = df['close']

        # 1. 价格动量 (ROC)
        roc = (close.iloc[-1] - close.iloc[-period]) / close.iloc[-period]

        # 2. 动量持续性 (连续上涨天数)
        up_days = 0
        for i in range(1, min(period, len(close))):
            if close.iloc[-i] > close.iloc[-i-1]:
                up_days += 1
            else:
                break

        continuity_score = up_days / period

        # 3. 相对强度 (简化版：vs 自身均线)
        ma_period = period
        ma_value = close.rolling(ma_period).mean().iloc[-1]
        relative_strength = (close.iloc[-1] - ma_value) / ma_value if ma_value > 0 else 0

        # 综合动量得分
        momentum_score = roc * 0.5 + continuity_score * 0.3 + relative_strength * 0.2

        return momentum_score

    def get_momentum_strength(self, momentum_score: float) -> MomentumStrength:
        """
        获取动量强度等级

        Args:
            momentum_score: 动量得分

        Returns:
            动量强度等级
        """
        if momentum_score >= 0.1:
            return MomentumStrength.STRONG_POSITIVE
        elif momentum_score >= 0.03:
            return MomentumStrength.WEAK_POSITIVE
        elif momentum_score >= -0.03:
            return MomentumStrength.NEUTRAL
        elif momentum_score >= -0.1:
            return MomentumStrength.WEAK_NEGATIVE
        else:
            return MomentumStrength.STRONG_NEGATIVE

    def get_momentum_factor_score(self, ts_code: str) -> float:
        """
        获取动量因子得分 (用于信号评分)

        Returns:
            因子得分 (0-2 分)
        """
        momentum = self.calculate_momentum(ts_code)
        strength = self.get_momentum_strength(momentum)

        # 根据强度等级给分
        score_map = {
            MomentumStrength.STRONG_POSITIVE: 2.0,
            MomentumStrength.WEAK_POSITIVE: 1.0,
            MomentumStrength.NEUTRAL: 0.5,
            MomentumStrength.WEAK_NEGATIVE: 0,
            MomentumStrength.STRONG_NEGATIVE: -1.0,  # 负分表示应该避免
        }

        return score_map.get(strength, 0)

    def should_skip_trade_due_to_momentum(self, ts_code: str) -> bool:
        """
        是否因动量不足跳过交易

        Returns:
            True 表示应该跳过
        """
        if not self.config.use_momentum_factor:
            return False

        momentum = self.calculate_momentum(ts_code)
        return momentum < self.config.min_momentum_score

    # ==================== 资金流向因子 ====================

    def calculate_money_flow(self, ts_code: str) -> float:
        """
        计算资金流向得分

        基于：
        1. 量价关系 (放量上涨=流入)
        2. 大单流向 (简化版：大成交量方向)
        3. 资金持续性

        Returns:
            资金流得分 (-1 到 1)
        """
        if not self.config.use_money_flow_factor:
            return 0

        if ts_code not in self.price_history:
            return 0

        df = self.price_history[ts_code]
        period = self.config.money_flow_period

        if len(df) < period:
            return 0

        close = df['close']
        vol = df['vol']

        # 1. 计算每日资金流向
        flow_scores = []
        for i in range(period):
            idx = -1 - i
            if idx < -len(df):
                break

            price_change = close.iloc[idx] - close.iloc[idx-1] if idx > -len(df) + 1 else 0
            vol_ratio = vol.iloc[idx] / vol.rolling(period).mean().iloc[idx] if vol.rolling(period).mean().iloc[idx] > 0 else 1

            # 量价配合：放量上涨为正，放量下跌为负
            if price_change > 0:
                flow_score = (1 + price_change / close.iloc[idx-1]) * min(vol_ratio, 3) - 1
            else:
                flow_score = -(1 + abs(price_change) / close.iloc[idx-1]) * min(vol_ratio, 3) + 1

            flow_scores.append(flow_score)

        # 2. 计算平均资金流
        avg_flow = np.mean(flow_scores) if flow_scores else 0

        # 3. 资金持续性 (连续流入天数)
        continuous_inflow = 0
        for score in flow_scores:
            if score > 0:
                continuous_inflow += 1
            else:
                break

        continuity_bonus = continuous_inflow / period * 0.2

        return avg_flow + continuity_bonus

    def get_money_flow_factor_score(self, ts_code: str) -> float:
        """
        获取资金流向因子得分 (用于信号评分)

        Returns:
            因子得分 (0-2 分)
        """
        money_flow = self.calculate_money_flow(ts_code)

        # 根据资金流强度给分
        if money_flow >= 0.3:
            return 2.0  # 强流入
        elif money_flow >= 0.1:
            return 1.5  # 中等流入
        elif money_flow >= 0:
            return 1.0  # 弱流入
        elif money_flow >= -0.1:
            return 0.5  # 弱流出
        else:
            return 0  # 强流出，避免交易

    # ==================== 强势股筛选 ====================

    def calculate_stock_strength(self, ts_code: str) -> float:
        """
        计算股票强度得分

        基于：
        1. 相对强度 (vs 自身历史)
        2. 趋势强度
        3. 波动调整收益

        Returns:
            强度得分 (0-1)
        """
        if ts_code not in self.price_history:
            return 0.5

        df = self.price_history[ts_code]
        lookback = self.config.strength_lookback

        if len(df) < lookback:
            return 0.5

        close = df['close']

        # 1. 价格位置 (当前价格 vs N 日区间)
        high_n = close.rolling(lookback).max().iloc[-1]
        low_n = close.rolling(lookback).min().iloc[-1]
        current_price = close.iloc[-1]

        if high_n == low_n:
            price_position = 0.5
        else:
            price_position = (current_price - low_n) / (high_n - low_n)

        # 2. 趋势强度 (斜率)
        ma20 = close.rolling(20).mean()
        trend_slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] if ma20.iloc[-5] > 0 else 0
        trend_score = min(1, max(0, 0.5 + trend_slope * 10))

        # 3. 波动调整收益
        returns = close.pct_change()
        if len(returns) > 1:
            vol = returns.std()
            mean_return = returns.mean()
            sharpe_like = mean_return / vol if vol > 0 else 0
            volatility_adjusted_score = min(1, max(0, 0.5 + sharpe_like * 0.5))
        else:
            volatility_adjusted_score = 0.5

        # 综合强度得分
        strength = price_position * 0.4 + trend_score * 0.4 + volatility_adjusted_score * 0.2

        # 缓存结果
        self.stock_strength_cache[ts_code] = strength

        return strength

    def get_stock_strength_rank(self, stock_strengths: Dict[str, float]) -> Dict[str, float]:
        """
        获取股票强度排名

        Args:
            stock_strengths: {ts_code: strength}

        Returns:
            {ts_code: rank (0-1, 1 为最强)}
        """
        if not stock_strengths:
            return {}

        # 按强度排序
        sorted_stocks = sorted(stock_strengths.items(), key=lambda x: x[1], reverse=True)

        # 计算排名百分比
        ranks = {}
        n = len(sorted_stocks)
        for i, (ts_code, strength) in enumerate(sorted_stocks):
            ranks[ts_code] = 1 - (i / n)  # 排名百分比 (1 为最强)

        return ranks

    def should_filter_stock(self, ts_code: str) -> bool:
        """
        是否应该过滤该股票 (强度不足)

        Returns:
            True 表示应该过滤
        """
        if not self.config.use_stock_filter:
            return False

        strength = self.stock_strength_cache.get(ts_code, 0.5)
        return strength < self.config.min_strength_rank

    # ==================== 信号质量优化 ====================

    def calculate_signal_confidence(
        self,
        base_score: float,
        momentum_score: float,
        money_flow_score: float,
        stock_strength: float
    ) -> float:
        """
        计算信号置信度

        Args:
            base_score: 基础信号评分
            momentum_score: 动量得分
            money_flow_score: 资金流得分
            stock_strength: 股票强度

        Returns:
            置信度 (0-1)
        """
        if not self.config.use_signal_quality:
            return 1.0

        # 1. 基础信号质量 (基础评分越高，置信度越高)
        base_confidence = min(1.0, base_score / 10.5)

        # 2. 因子确认
        # 动量确认
        momentum_confidence = 1.0 if momentum_score >= 1.0 else momentum_score / 1.0
        # 资金流确认
        flow_confidence = 1.0 if money_flow_score >= 1.5 else money_flow_score / 1.5

        # 3. 股票强度调整
        strength_factor = 0.5 + stock_strength * 0.5  # 0.75-1.0

        # 综合置信度
        confidence = (
            base_confidence * 0.4 +
            momentum_confidence * 0.2 +
            flow_confidence * 0.2 +
            strength_factor * 0.2
        )

        return min(1.0, max(0, confidence))

    def is_high_confidence_signal(
        self,
        base_score: float,
        momentum_score: float,
        money_flow_score: float,
        stock_strength: float
    ) -> bool:
        """
        判断是否为高置信度信号

        Returns:
            True 表示高置信度
        """
        confidence = self.calculate_signal_confidence(
            base_score, momentum_score, money_flow_score, stock_strength
        )
        return confidence >= self.config.min_signal_confidence


def create_win_rate_optimizer() -> WinRateOptimizer:
    """
    创建胜率优化器

    Returns:
        配置好的优化器实例
    """
    config = WinRateOptimizationConfig(
        use_momentum_factor=True,
        momentum_period=10,
        min_momentum_score=0.03,

        use_money_flow_factor=True,
        money_flow_period=5,
        min_money_flow_score=0,

        use_stock_filter=True,
        strength_lookback=20,
        min_strength_rank=0.3,  # 前 30%

        use_signal_quality=True,
        min_signal_confidence=0.6,
    )

    return WinRateOptimizer(config)


def get_win_rate_optimization_params() -> Dict[str, any]:
    """
    获取胜率优化参数配置

    Returns:
        参数字典
    """
    return {
        'momentum': {
            'period': 10,
            'weight': 1.5,  # 动量因子权重
            'threshold': 0.03,  # 最小动量阈值
        },
        'money_flow': {
            'period': 5,
            'weight': 1.5,  # 资金流权重
            'threshold': 0,  # 资金流转正
        },
        'stock_strength': {
            'lookback': 20,
            'min_rank': 0.3,  # 只交易前 30% 强势股
        },
        'signal_quality': {
            'min_confidence': 0.6,  # 60% 置信度阈值
        },
        'optimization_notes': [
            '动量因子 (1.5 分) - 选择强势上涨股票',
            '资金流向 (1.5 分) - 跟踪主力资金动向',
            '强势股筛选 - 只交易强度前 30% 股票',
            '信号置信度 - 过滤低质量信号',
            '预期胜率提升：51.4% -> 55%+',
        ]
    }


if __name__ == "__main__":
    print("胜率优化模块")
    print("=" * 50)

    config = get_win_rate_optimization_params()

    print("\n优化目标：胜率 51.4% -> 55%+")
    print("\n核心优化措施:")
    for note in config['optimization_notes']:
        print(f"  - {note}")
