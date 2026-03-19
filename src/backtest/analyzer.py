"""
归因分析模块
分析收益来源和风险贡献
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import config.settings as settings
from config.logging_config import backtest_logger


@dataclass
class AttributionResult:
    """归因分析结果"""
    # _brinson 归因
    allocation_effect: float = 0.0  # 配置效应
    selection_effect: float = 0.0  # 选股效应
    interaction_effect: float = 0.0  # 交互效应

    # 因子归因
    factor_contribution: Dict[str, float] = None

    # 行业归因
    industry_contribution: Dict[str, float] = None

    # 个股贡献
    stock_contribution: Dict[str, float] = None

    def __post_init__(self):
        if self.factor_contribution is None:
            self.factor_contribution = {}
        if self.industry_contribution is None:
            self.industry_contribution = {}
        if self.stock_contribution is None:
            self.stock_contribution = {}


class AttributionAnalyzer:
    """归因分析器"""

    def __init__(self):
        """初始化归因分析器"""
        pass

    def brinson_attribution(
        self,
        portfolio_weights: pd.Series,
        benchmark_weights: pd.Series,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> Tuple[float, float, float]:
        """
        Brinson 归因分析

        将超额收益分解为:
        - 配置效应 (Allocation): 行业配置带来的收益
        - 选股效应 (Selection): 个股选择带来的收益
        - 交互效应 (Interaction): 配置和选股的交互作用

        Args:
            portfolio_weights: 组合各行业/资产权重
            benchmark_weights: 基准各行业/资产权重
            portfolio_returns: 组合各行业/资产收益率
            benchmark_returns: 基准各行业/资产收益率

        Returns:
            (allocation_effect, selection_effect, interaction_effect) 元组
        """
        # 对齐数据
        all_assets = portfolio_weights.index.union(benchmark_weights.index)

        w_p = portfolio_weights.reindex(all_assets, fill_value=0)
        w_b = benchmark_weights.reindex(all_assets, fill_value=0)
        r_p = portfolio_returns.reindex(all_assets, fill_value=0)
        r_b = benchmark_returns.reindex(all_assets, fill_value=0)

        # 总收益率
        total_r_p = (w_p * r_p).sum()
        total_r_b = (w_b * r_b).sum()

        # 配置效应：(w_p - w_b) * r_b
        allocation_effect = ((w_p - w_b) * r_b).sum()

        # 选股效应：w_b * (r_p - r_b)
        selection_effect = (w_b * (r_p - r_b)).sum()

        # 交互效应：(w_p - w_b) * (r_p - r_b)
        interaction_effect = ((w_p - w_b) * (r_p - r_b)).sum()

        return allocation_effect, selection_effect, interaction_effect

    def sector_attribution(
        self,
        portfolio_holdings: pd.DataFrame,
        benchmark_holdings: pd.DataFrame,
        sector_mapping: Dict[str, str]
    ) -> Dict[str, float]:
        """
        行业归因分析

        Args:
            portfolio_holdings: 组合持仓 DataFrame (ts_code, weight, return)
            benchmark_holdings: 基准持仓 DataFrame
            sector_mapping: 股票代码到行业的映射

        Returns:
            各行业贡献度字典
        """
        # 映射行业
        portfolio_holdings = portfolio_holdings.copy()
        benchmark_holdings = benchmark_holdings.copy()

        portfolio_holdings['sector'] = portfolio_holdings['ts_code'].map(sector_mapping)
        benchmark_holdings['sector'] = benchmark_holdings['ts_code'].map(sector_mapping)

        # 按行业聚合
        portfolio_sector = portfolio_holdings.groupby('sector').agg({
            'weight': 'sum',
            'return': lambda x: (x * portfolio_holdings.loc[x.index, 'weight']).sum() / portfolio_holdings.loc[x.index, 'weight'].sum() if portfolio_holdings.loc[x.index, 'weight'].sum() > 0 else 0
        }).rename(columns={'weight': 'w_p', 'return': 'r_p'})

        benchmark_sector = benchmark_holdings.groupby('sector').agg({
            'weight': 'sum',
            'return': lambda x: (x * benchmark_holdings.loc[x.index, 'weight']).sum() / benchmark_holdings.loc[x.index, 'weight'].sum() if benchmark_holdings.loc[x.index, 'weight'].sum() > 0 else 0
        }).rename(columns={'weight': 'w_b', 'return': 'r_b'})

        # 合并
        sector_data = portfolio_sector.join(benchmark_sector, how='outer').fillna(0)

        # 计算各行业贡献
        sector_data['allocation'] = (sector_data['w_p'] - sector_data['w_b']) * sector_data['r_b']
        sector_data['selection'] = sector_data['w_b'] * (sector_data['r_p'] - sector_data['r_b'])
        sector_data['interaction'] = (sector_data['w_p'] - sector_data['w_b']) * (sector_data['r_p'] - sector_data['r_b'])
        sector_data['total_contribution'] = sector_data['allocation'] + sector_data['selection'] + sector_data['interaction']

        return sector_data.to_dict('index')

    def stock_contribution(
        self,
        trades: List,
        positions: Dict
    ) -> Dict[str, float]:
        """
        个股贡献分析

        Args:
            trades: 交易记录列表
            positions: 持仓字典

        Returns:
            个股贡献度字典
        """
        stock_pnl = {}

        for trade in trades:
            ts_code = trade.ts_code
            if ts_code not in stock_pnl:
                stock_pnl[ts_code] = 0.0

            if trade.direction == 'buy':
                stock_pnl[ts_code] -= trade.price * trade.volume + trade.commission
            else:
                stock_pnl[ts_code] += trade.price * trade.volume - trade.commission - trade.stamp_tax

        # 计算当前持仓的浮盈浮亏
        for ts_code, pos in positions.items():
            unrealized_pnl = pos.market_value - pos.avg_cost * pos.volume
            if ts_code not in stock_pnl:
                stock_pnl[ts_code] = unrealized_pnl
            else:
                stock_pnl[ts_code] += unrealized_pnl

        return stock_pnl

    def factor_attribution(
        self,
        portfolio_returns: pd.Series,
        factor_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        因子归因分析 (基于回归)

        Args:
            portfolio_returns: 组合收益率序列
            factor_returns: 因子收益率 DataFrame (多列)

        Returns:
            各因子贡献度字典
        """
        # 对齐数据
        aligned = pd.concat([portfolio_returns, factor_returns], axis=1).dropna()

        if len(aligned) < len(factor_returns.columns) + 2:
            backtest_logger.warning("数据不足以进行因子归因")
            return {}

        # 多因子回归
        from sklearn.linear_model import LinearRegression

        y = aligned.iloc[:, 0].values
        X = aligned.iloc[:, 1:].values

        model = LinearRegression()
        model.fit(X, y)

        # 因子贡献 = 因子收益率 * 因子暴露 (beta)
        factor_names = factor_returns.columns
        factor_contribution = {}

        for i, name in enumerate(factor_names):
            beta = model.coef_[i]
            factor_mean_return = aligned.iloc[:, i + 1].mean() * 252  # 年化
            contribution = beta * factor_mean_return
            factor_contribution[name] = contribution

        # Alpha (残差)
        alpha = model.intercept_ * 252
        factor_contribution['alpha'] = alpha

        return factor_contribution

    def calculate_risk_contribution(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray,
        asset_names: List[str]
    ) -> Dict[str, float]:
        """
        计算风险贡献度

        Args:
            weights: 资产权重向量
            covariance_matrix: 协方差矩阵
            asset_names: 资产名称列表

        Returns:
            各资产风险贡献度字典
        """
        # 组合方差
        portfolio_variance = weights @ covariance_matrix @ weights.T
        portfolio_vol = np.sqrt(portfolio_variance)

        # 边际风险贡献
        marginal_risk = covariance_matrix @ weights / portfolio_vol

        # 风险贡献度
        risk_contribution = weights * marginal_risk

        # 百分比形式
        total_risk = risk_contribution.sum()
        if total_risk > 0:
            risk_contribution_pct = risk_contribution / total_risk
        else:
            risk_contribution_pct = risk_contribution

        return {name: contrib for name, contrib in zip(asset_names, risk_contribution_pct)}

    def generateAttributionReport(
        self,
        attribution_result: AttributionResult
    ) -> str:
        """
        生成归因分析报告

        Args:
            attribution_result: 归因分析结果

        Returns:
            报告文本
        """
        report = []
        report.append("=" * 60)
        report.append("收益归因分析报告")
        report.append("=" * 60)
        report.append("")

        # Brinson 归因
        report.append("【Brinson 归因】")
        report.append(f"  配置效应：    {attribution_result.allocation_effect * 100:.2f}%")
        report.append(f"  选股效应：    {attribution_result.selection_effect * 100:.2f}%")
        report.append(f"  交互效应：    {attribution_result.interaction_effect * 100:.2f}%")
        total = attribution_result.allocation_effect + attribution_result.selection_effect + attribution_result.interaction_effect
        report.append(f"  合计：        {total * 100:.2f}%")
        report.append("")

        # 因子贡献
        if attribution_result.factor_contribution:
            report.append("【因子贡献】")
            for factor, contrib in sorted(attribution_result.factor_contribution.items(), key=lambda x: abs(x[1]), reverse=True):
                report.append(f"  {factor:15s}: {contrib * 100:8.2f}%")
            report.append("")

        # 个股贡献
        if attribution_result.stock_contribution:
            report.append("【个股贡献 Top 10】")
            sorted_stocks = sorted(attribution_result.stock_contribution.items(), key=lambda x: x[1], reverse=True)[:10]
            for ts_code, contrib in sorted_stocks:
                report.append(f"  {ts_code:15s}: {contrib:12.2f}")
            report.append("")

        report.append("=" * 60)
        return "\n".join(report)


# 创建分析器实例
attribution_analyzer = AttributionAnalyzer()
