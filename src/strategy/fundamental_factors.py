"""
基本面因子增强模块
提供 ROE、营收增长、估值等基本面因子的计算和筛选功能

优化方向:
1. ROE 质量因子 - 筛选高 ROE 且稳定的股票
2. 营收增长因子 - 筛选持续增长的股票
3. 估值因子 - PE/PB 综合评分
4. 财务健康因子 - 负债率、现金流
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from config.logging_config import data_logger


class ROELevel(Enum):
    """ROE 等级"""
    EXCELLENT = "excellent"    # ROE > 20%
    GOOD = "good"             # ROE > 15%
    NORMAL = "normal"         # ROE > 10%
    LOW = "low"               # ROE > 5%
    POOR = "poor"             # ROE <= 5%


class GrowthLevel(Enum):
    """增长等级"""
    HIGH = "high"          # 增长 > 30%
    MEDIUM = "medium"      # 增长 > 15%
    LOW = "low"            # 增长 > 5%
    NEGATIVE = "negative"  # 增长 <= 5%


@dataclass
class FundamentalFactorConfig:
    """基本面因子配置"""
    # ROE 因子
    min_roe: float = 0.05         # 最小 ROE 5%
    excellent_roe: float = 0.20   # 优秀 ROE 20%
    roe_stability_window: int = 4  # ROE 稳定性计算窗口 (季度数)

    # 增长因子
    min_revenue_growth: float = 0.0     # 最小营收增长
    min_profit_growth: float = 0.0      # 最小利润增长
    high_growth_threshold: float = 0.30  # 高增长阈值 30%

    # 估值因子
    max_pe: float = 50           # 最大 PE
    max_pb: float = 10           # 最大 PB
    min_pe: float = 0            # 最小 PE (排除负值)

    # 财务健康
    max_debt_ratio: float = 0.70  # 最大资产负债率 70%
    min_current_ratio: float = 1.0  # 最小流动比率

    # 市值因子
    min_market_cap: float = 5e9   # 最小市值 50 亿
    max_market_cap: float = 1e12  # 最大市值 1 万亿

    # 综合评分权重
    roe_weight: float = 0.30      # ROE 权重 30%
    growth_weight: float = 0.25   # 增长权重 25%
    value_weight: float = 0.20    # 估值权重 20%
    health_weight: float = 0.15   # 健康权重 15%
    size_weight: float = 0.10     # 市值权重 10%


class FundamentalFactorAnalyzer:
    """基本面因子分析器"""

    def __init__(self, config: Optional[FundamentalFactorConfig] = None):
        self.config = config or FundamentalFactorConfig()
        self.financial_data: Dict[str, pd.DataFrame] = {}

    def update_financial_data(self, ts_code: str, data: pd.DataFrame):
        """更新财务数据"""
        self.financial_data[ts_code] = data

    # ==================== ROE 因子 ====================

    def calculate_roe_score(self, ts_code: str) -> float:
        """
        计算 ROE 得分

        基于:
        1. ROE 绝对值
        2. ROE 稳定性 (波动率)
        3. ROE 趋势 (改善/恶化)

        Returns:
            ROE 得分 (0-1)
        """
        if ts_code not in self.financial_data:
            return 0.5

        df = self.financial_data[ts_code]
        if 'roe' not in df.columns or len(df) < 2:
            return 0.5

        roe = df['roe'].dropna()
        if len(roe) < 2:
            return 0.5

        # 1. ROE 绝对值得分
        latest_roe = roe.iloc[-1]
        if latest_roe >= self.config.excellent_roe:
            roe_level_score = 1.0
        elif latest_roe >= self.config.min_roe:
            # 线性插值
            roe_level_score = (latest_roe - self.config.min_roe) / (self.config.excellent_roe - self.config.min_roe)
        else:
            roe_level_score = 0

        # 2. ROE 稳定性得分 (波动率越小越稳定)
        if len(roe) >= self.config.roe_stability_window:
            roe_volatility = roe.tail(self.config.roe_stability_window).std()
            # 波动率越小，得分越高 (假设 5% 为基准)
            stability_score = max(0, 1 - roe_volatility / 0.05)
        else:
            stability_score = 0.5

        # 3. ROE 趋势得分
        if len(roe) >= 2:
            roe_trend = roe.iloc[-1] - roe.iloc[-2]
            trend_score = 0.5 + roe_trend / 0.1  # 10% 变化为满分
            trend_score = max(0, min(1, trend_score))
        else:
            trend_score = 0.5

        # 综合 ROE 得分
        roe_score = roe_level_score * 0.5 + stability_score * 0.3 + trend_score * 0.2

        return roe_score

    def get_roe_level(self, roe: float) -> ROELevel:
        """获取 ROE 等级"""
        if roe >= self.config.excellent_roe:
            return ROELevel.EXCELLENT
        elif roe >= 0.15:
            return ROELevel.GOOD
        elif roe >= 0.10:
            return ROELevel.NORMAL
        elif roe >= self.config.min_roe:
            return ROELevel.LOW
        else:
            return ROELevel.POOR

    # ==================== 增长因子 ====================

    def calculate_growth_score(self, ts_code: str) -> float:
        """
        计算增长得分

        基于:
        1. 营收增长率
        2. 利润增长率
        3. 增长稳定性

        Returns:
            增长得分 (0-1)
        """
        if ts_code not in self.financial_data:
            return 0.5

        df = self.financial_data[ts_code]
        if len(df) < 2:
            return 0.5

        # 营收增长
        if 'revenue_growth' in df.columns:
            revenue_growth = df['revenue_growth'].iloc[-1] if len(df['revenue_growth']) > 0 else 0
        elif 'total_revenue' in df.columns:
            rev = df['total_revenue']
            revenue_growth = (rev.iloc[-1] - rev.iloc[-1] if len(rev) >= 2 else 0) / rev.iloc[-2] if len(rev) >= 2 and rev.iloc[-2] > 0 else 0
        else:
            revenue_growth = 0

        # 利润增长
        if 'profit_growth' in df.columns:
            profit_growth = df['profit_growth'].iloc[-1] if len(df['profit_growth']) > 0 else 0
        elif 'net_profit' in df.columns:
            profit = df['net_profit']
            profit_growth = (profit.iloc[-1] - profit.iloc[-2]) / profit.iloc[-2] if len(profit) >= 2 and profit.iloc[-2] > 0 else 0
        else:
            profit_growth = 0

        # 1. 营收增长得分
        if revenue_growth >= self.config.high_growth_threshold:
            revenue_score = 1.0
        elif revenue_growth >= self.config.min_revenue_growth:
            revenue_score = (revenue_growth - self.config.min_revenue_growth) / (self.config.high_growth_threshold - self.config.min_revenue_growth)
        else:
            revenue_score = 0

        # 2. 利润增长得分
        if profit_growth >= self.config.high_growth_threshold:
            profit_score = 1.0
        elif profit_growth >= self.config.min_profit_growth:
            profit_score = (profit_growth - self.config.min_profit_growth) / (self.config.high_growth_threshold - self.config.min_profit_growth)
        else:
            profit_score = 0

        # 3. 增长稳定性 (两者都正增长为稳定)
        stability_bonus = 0.2 if (revenue_growth > 0 and profit_growth > 0) else 0

        # 综合增长得分
        growth_score = (revenue_score + profit_score) / 2 * 0.8 + stability_bonus

        return max(0, min(1, growth_score))

    def get_growth_level(self, growth: float) -> GrowthLevel:
        """获取增长等级"""
        if growth >= self.config.high_growth_threshold:
            return GrowthLevel.HIGH
        elif growth >= 0.15:
            return GrowthLevel.MEDIUM
        elif growth >= self.config.min_revenue_growth:
            return GrowthLevel.LOW
        else:
            return GrowthLevel.NEGATIVE

    # ==================== 估值因子 ====================

    def calculate_value_score(self, ts_code: str, current_pe: float = None, current_pb: float = None) -> float:
        """
        计算估值得分

        基于:
        1. PE 分位数
        2. PB 分位数
        3. PEG 比率

        Returns:
            估值得分 (0-1, 越低估值越便宜)
        """
        if ts_code not in self.financial_data:
            return 0.5

        df = self.financial_data[ts_code]

        # 获取当前 PE/PB
        if current_pe is None:
            current_pe = df['pe'].iloc[-1] if 'pe' in df.columns and len(df) > 0 else 20

        if current_pb is None:
            current_pb = df['pb'].iloc[-1] if 'pb' in df.columns and len(df) > 0 else 2

        # PE 得分 (越低越好，但要排除负值和异常值)
        if current_pe < 0:
            pe_score = 0
        elif current_pe < self.config.min_pe:
            pe_score = 0
        elif current_pe < 10:
            pe_score = 1.0
        elif current_pe < self.config.max_pe:
            pe_score = 1 - (current_pe - 10) / (self.config.max_pe - 10)
        else:
            pe_score = 0

        # PB 得分 (越低越好)
        if current_pb < 1:
            pb_score = 1.0
        elif current_pb < self.config.max_pb:
            pb_score = 1 - (current_pb - 1) / (self.config.max_pb - 1)
        else:
            pb_score = 0

        # PEG 得分 (PE / 增长率，<1 为低估)
        if 'profit_growth' in df.columns and len(df) > 0:
            growth = df['profit_growth'].iloc[-1] if len(df['profit_growth']) > 0 else 0.1
            if growth > 0:
                peg = current_pe / (growth * 100)
                if peg < 0.5:
                    peg_score = 1.0
                elif peg < 1:
                    peg_score = 0.7
                elif peg < 2:
                    peg_score = 0.5
                else:
                    peg_score = 0.2
            else:
                peg_score = 0
        else:
            peg_score = 0.5

        # 综合估值得分
        value_score = pe_score * 0.4 + pb_score * 0.3 + peg_score * 0.3

        return max(0, min(1, value_score))

    # ==================== 财务健康因子 ====================

    def calculate_health_score(self, ts_code: str) -> float:
        """
        计算财务健康得分

        基于:
        1. 资产负债率
        2. 流动比率
        3. 利息保障倍数

        Returns:
            健康得分 (0-1)
        """
        if ts_code not in self.financial_data:
            return 0.5

        df = self.financial_data[ts_code]

        # 资产负债率 (越低越健康)
        if 'debt_ratio' in df.columns and len(df) > 0:
            debt_ratio = df['debt_ratio'].iloc[-1]
        elif 'asset_liability_ratio' in df.columns and len(df) > 0:
            debt_ratio = df['asset_liability_ratio'].iloc[-1]
        else:
            debt_ratio = 0.5  # 默认 50%

        if debt_ratio < 0.3:
            debt_score = 1.0
        elif debt_ratio < self.config.max_debt_ratio:
            debt_score = 1 - (debt_ratio - 0.3) / (self.config.max_debt_ratio - 0.3)
        else:
            debt_score = 0

        # 流动比率 (1.5-2 为理想)
        if 'current_ratio' in df.columns and len(df) > 0:
            current_ratio = df['current_ratio'].iloc[-1]
        else:
            current_ratio = 1.5  # 默认理想值

        if 1.5 <= current_ratio <= 2.5:
            current_score = 1.0
        elif current_ratio < 1.5:
            current_score = current_ratio / 1.5
        else:
            current_score = 0.8  # 过高也不好

        # 综合健康得分
        health_score = debt_score * 0.6 + current_score * 0.4

        return max(0, min(1, health_score))

    # ==================== 市值因子 ====================

    def calculate_size_score(self, market_cap: float) -> float:
        """
        计算市值得分

        基于:
        1. 市值绝对值
        2. 市值排名

        Returns:
            市值得分 (0-1)
        """
        if market_cap < self.config.min_market_cap:
            return 0
        elif market_cap < 1e10:  # 100 亿
            return 0.5
        elif market_cap < 5e10:  # 500 亿
            return 0.7
        elif market_cap < 1e11:  # 1000 亿
            return 0.9
        else:
            return 1.0

    # ==================== 综合评分 ====================

    def calculate_composite_score(
        self,
        ts_code: str,
        market_cap: float = None,
        pe: float = None,
        pb: float = None
    ) -> float:
        """
        计算综合基本面得分

        Returns:
            综合得分 (0-1)
        """
        # 各因子得分
        roe_score = self.calculate_roe_score(ts_code)
        growth_score = self.calculate_growth_score(ts_code)
        value_score = self.calculate_value_score(ts_code, pe, pb)
        health_score = self.calculate_health_score(ts_code)
        size_score = self.calculate_size_score(market_cap) if market_cap else 0.5

        # 加权综合
        composite = (
            roe_score * self.config.roe_weight +
            growth_score * self.config.growth_weight +
            value_score * self.config.value_weight +
            health_score * self.config.health_weight +
            size_score * self.config.size_weight
        )

        return composite

    def should_filter_stock(self, ts_code: str) -> Tuple[bool, str]:
        """
        判断是否应该过滤该股票

        Returns:
            (是否过滤，过滤原因)
        """
        if ts_code not in self.financial_data:
            return True, "无财务数据"

        df = self.financial_data[ts_code]

        # ROE 过滤
        if 'roe' in df.columns and len(df) > 0:
            roe = df['roe'].iloc[-1]
            if roe < self.config.min_roe:
                return True, f"ROE 过低 ({roe:.1%} < {self.config.min_roe:.1%})"

        # 增长过滤
        if 'revenue_growth' in df.columns and len(df) > 0:
            growth = df['revenue_growth'].iloc[-1]
            if growth < self.config.min_revenue_growth:
                return True, f"营收负增长 ({growth:.1%})"

        # 负债率过滤
        if 'debt_ratio' in df.columns and len(df) > 0:
            debt = df['debt_ratio'].iloc[-1]
            if debt > self.config.max_debt_ratio:
                return True, f"负债率过高 ({debt:.1%} > {self.config.max_debt_ratio:.1%})"

        # PE 过滤
        if 'pe' in df.columns and len(df) > 0:
            pe = df['pe'].iloc[-1]
            if pe > self.config.max_pe:
                return True, f"PE 过高 ({pe:.1f} > {self.config.max_pe})"
            if pe < 0:
                return True, f"PE 为负 ({pe:.1f})"

        return False, ""


def create_fundamental_analyzer() -> FundamentalFactorAnalyzer:
    """
    创建基本面分析器

    Returns:
        配置好的分析器实例
    """
    config = FundamentalFactorConfig(
        min_roe=0.05,
        excellent_roe=0.20,
        min_revenue_growth=0.0,
        min_profit_growth=0.0,
        max_pe=50,
        max_pb=10,
        max_debt_ratio=0.70,
        min_market_cap=5e9,
        roe_weight=0.30,
        growth_weight=0.25,
        value_weight=0.20,
        health_weight=0.15,
        size_weight=0.10,
    )

    return FundamentalFactorAnalyzer(config)


if __name__ == "__main__":
    print("基本面因子增强模块")
    print("=" * 50)

    analyzer = create_fundamental_analyzer()

    print("\n因子配置:")
    print(f"  ROE 权重：{analyzer.config.roe_weight:.0%}")
    print(f"  增长权重：{analyzer.config.growth_weight:.0%}")
    print(f"  估值权重：{analyzer.config.value_weight:.0%}")
    print(f"  健康权重：{analyzer.config.health_weight:.0%}")
    print(f"  市值权重：{analyzer.config.size_weight:.0%}")

    print("\n过滤条件:")
    print(f"  最小 ROE: {analyzer.config.min_roe:.0%}")
    print(f"  最小营收增长：{analyzer.config.min_revenue_growth:.0%}")
    print(f"  最大 PE: {analyzer.config.max_pe}")
    print(f"  最大负债率：{analyzer.config.max_debt_ratio:.0%}")
    print(f"  最小市值：{analyzer.config.min_market_cap/1e8:.0f}亿")
