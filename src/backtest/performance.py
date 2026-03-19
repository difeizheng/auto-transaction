"""
绩效分析模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import matplotlib.pyplot as plt

import config.settings as settings
from src.backtest.engine import BacktestResult


@dataclass
class PerformanceMetrics:
    """绩效指标数据类"""
    # 收益指标
    total_return: float = 0.0
    annual_return: float = 0.0
    excess_return: float = 0.0  # 超额收益
    alpha: float = 0.0
    beta: float = 0.0

    # 风险指标
    volatility: float = 0.0  # 年化波动率
    downside_volatility: float = 0.0  # 下行波动率
    var_95: float = 0.0  # 95% VaR
    cvar_95: float = 0.0  # 95% CVaR

    # 风险调整收益
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0

    # 回撤指标
    max_drawdown: float = 0.0
    avg_drawdown: float = 0.0
    max_drawdown_duration: int = 0  # 最大回撤持续期

    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    avg_holding_period: float = 0.0  # 平均持仓期


class PerformanceAnalyzer:
    """绩效分析器"""

    def __init__(self, risk_free_rate: float = 0.02, benchmark_returns: Optional[pd.Series] = None):
        """
        初始化绩效分析器

        Args:
            risk_free_rate: 无风险利率 (年化)
            benchmark_returns: 基准收益率序列 (如沪深 300)
        """
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns

    def analyze(self, result: BacktestResult) -> PerformanceMetrics:
        """
        分析回测结果

        Args:
            result: 回测结果

        Returns:
            绩效指标
        """
        if result.daily_returns.empty:
            return PerformanceMetrics()

        daily_returns = result.daily_returns.dropna()

        metrics = PerformanceMetrics()

        # 基本收益指标
        metrics.total_return = result.total_return
        metrics.annual_return = result.annual_return

        # 波动率
        metrics.volatility = daily_returns.std() * np.sqrt(252)

        # 下行波动率
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0:
            metrics.downside_volatility = negative_returns.std() * np.sqrt(252)

        # VaR 和 CVaR
        metrics.var_95 = daily_returns.quantile(0.05)
        metrics.cvar_95 = daily_returns[daily_returns <= metrics.var_95].mean()

        # 夏普比率
        metrics.sharpe_ratio = result.sharpe_ratio

        # 索提诺比率
        if metrics.downside_volatility > 0:
            excess_return = daily_returns.mean() * 252 - self.risk_free_rate
            metrics.sortino_ratio = excess_return / metrics.downside_volatility

        # 卡玛比率
        if metrics.max_drawdown > 0:
            metrics.calmar_ratio = metrics.annual_return / metrics.max_drawdown

        # 信息比率 (如果有基准)
        if self.benchmark_returns is not None:
            tracking_error = (daily_returns - self.benchmark_returns).std() * np.sqrt(252)
            if tracking_error > 0:
                excess_alpha = (daily_returns.mean() - self.benchmark_returns.mean()) * 252
                metrics.information_ratio = excess_alpha / tracking_error

        # 最大回撤
        metrics.max_drawdown = result.max_drawdown

        # 平均回撤
        if result.equity_curve is not None and not result.equity_curve.empty:
            equity = result.equity_curve['total_equity']
            peak = equity.expanding(min_periods=1).max()
            drawdown = (equity - peak) / peak
            metrics.avg_drawdown = abs(drawdown[drawdown != 0].mean()) if len(drawdown[drawdown != 0]) > 0 else 0

        # 交易统计
        metrics.total_trades = result.total_trades
        metrics.winning_trades = result.winning_trades
        metrics.losing_trades = result.losing_trades
        metrics.win_rate = result.win_rate
        metrics.profit_factor = result.profit_factor
        metrics.avg_profit = result.avg_profit
        metrics.avg_loss = result.avg_loss

        return metrics

    def calculate_alpha_beta(
        self,
        portfolio_returns: pd.Series,
        market_returns: pd.Series
    ) -> Tuple[float, float]:
        """
        计算 Alpha 和 Beta

        Args:
            portfolio_returns: 组合收益率序列
            market_returns: 市场收益率序列

        Returns:
            (alpha, beta) 元组
        """
        # 对齐数据
        aligned = pd.concat([portfolio_returns, market_returns], axis=1).dropna()
        if len(aligned) < 2:
            return 0.0, 0.0

        # 计算超额收益
        daily_rf = self.risk_free_rate / 252
        excess_portfolio = aligned.iloc[:, 0] - daily_rf
        excess_market = aligned.iloc[:, 1] - daily_rf

        # 线性回归
        covariance = excess_portfolio.cov(excess_market)
        market_variance = excess_market.var()

        if market_variance == 0:
            return 0.0, 0.0

        beta = covariance / market_variance
        alpha = excess_portfolio.mean() - beta * excess_market.mean()

        # 年化 Alpha
        alpha = alpha * 252

        return alpha, beta

    def calculate_rolling_metrics(
        self,
        equity_curve: pd.DataFrame,
        window: int = 20
    ) -> pd.DataFrame:
        """
        计算滚动指标

        Args:
            equity_curve: 权益曲线 DataFrame
            window: 滚动窗口

        Returns:
            滚动指标 DataFrame
        """
        if equity_curve.empty:
            return pd.DataFrame()

        # 计算收益率
        returns = equity_curve['total_equity'].pct_change()

        # 滚动夏普比率
        rolling_sharpe = returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(252)

        # 滚动最大回撤
        def rolling_max_dd(series):
            peak = series.expanding().max()
            drawdown = (series - peak) / peak
            return drawdown.min()

        rolling_dd = equity_curve['total_equity'].rolling(window).apply(rolling_max_dd, raw=False)

        result = pd.DataFrame({
            'rolling_sharpe': rolling_sharpe,
            'rolling_max_drawdown': rolling_dd,
            'rolling_return': returns.rolling(window).sum()
        }, index=equity_curve.index)

        return result

    def plot_equity_curve(
        self,
        result: BacktestResult,
        benchmark_equity: Optional[pd.Series] = None,
        save_path: Optional[str] = None
    ):
        """
        绘制权益曲线

        Args:
            result: 回测结果
            benchmark_equity: 基准权益曲线
            save_path: 保存路径
        """
        if result.equity_curve is None or result.equity_curve.empty:
            return

        fig, axes = plt.subplots(3, 1, figsize=(12, 10))

        # 权益曲线
        ax1 = axes[0]
        ax1.plot(
            result.equity_curve.index,
            result.equity_curve['total_equity'],
            label='Portfolio',
            linewidth=1.5
        )
        if benchmark_equity is not None:
            ax1.plot(benchmark_equity.index, benchmark_equity.values, label='Benchmark', linewidth=1.5, alpha=0.7)
        ax1.set_title('Equity Curve')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Equity')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 回撤曲线
        ax2 = axes[1]
        equity = result.equity_curve['total_equity']
        peak = equity.expanding(min_periods=1).max()
        drawdown = (equity - peak) / peak * 100
        ax2.fill_between(range(len(drawdown)), drawdown, 0, color='red', alpha=0.3)
        ax2.set_title('Drawdown (%)')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Drawdown %')
        ax2.grid(True, alpha=0.3)

        # 收益率分布
        ax3 = axes[2]
        if not result.daily_returns.empty:
            ax3.hist(result.daily_returns * 100, bins=50, edgecolor='black', alpha=0.7)
            ax3.axvline(x=result.daily_returns.mean() * 100, color='red', linestyle='--', label='Mean')
            ax3.set_title('Daily Returns Distribution')
            ax3.set_xlabel('Return (%)')
            ax3.set_ylabel('Frequency')
            ax3.legend()
            ax3.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        else:
            plt.show()

    def generate_report(self, result: BacktestResult) -> str:
        """
        生成绩效报告

        Args:
            result: 回测结果

        Returns:
            报告文本
        """
        metrics = self.analyze(result)

        report = []
        report.append("=" * 60)
        report.append("量化交易策略绩效分析报告")
        report.append("=" * 60)
        report.append("")

        # 收益指标
        report.append("【收益指标】")
        report.append(f"  总收益率：        {metrics.total_return * 100:.2f}%")
        report.append(f"  年化收益率：      {metrics.annual_return * 100:.2f}%")
        report.append(f"  波动率：          {metrics.volatility * 100:.2f}%")
        report.append("")

        # 风险调整收益
        report.append("【风险调整收益】")
        report.append(f"  夏普比率：        {metrics.sharpe_ratio:.2f}")
        report.append(f"  索提诺比率：      {metrics.sortino_ratio:.2f}")
        report.append(f"  卡玛比率：        {metrics.calmar_ratio:.2f}")
        report.append(f"  信息比率：        {metrics.information_ratio:.2f}")
        report.append("")

        # 风险指标
        report.append("【风险指标】")
        report.append(f"  最大回撤：        {metrics.max_drawdown * 100:.2f}%")
        report.append(f"  平均回撤：        {metrics.avg_drawdown * 100:.2f}%")
        report.append(f"  95% VaR:         {metrics.var_95 * 100:.2f}%")
        report.append(f"  95% CVaR:        {metrics.cvar_95 * 100:.2f}%")
        report.append("")

        # 交易统计
        report.append("【交易统计】")
        report.append(f"  总交易次数：      {metrics.total_trades}")
        report.append(f"  盈利次数：        {metrics.winning_trades}")
        report.append(f"  亏损次数：        {metrics.losing_trades}")
        report.append(f"  胜率：            {metrics.win_rate * 100:.2f}%")
        report.append(f"  盈亏比：          {metrics.profit_factor:.2f}")
        report.append(f"  平均盈利：        {metrics.avg_profit:.2f}")
        report.append(f"  平均亏损：        {metrics.avg_loss:.2f}")
        report.append("")
        report.append("=" * 60)

        return "\n".join(report)


# 创建分析器实例
performance_analyzer = PerformanceAnalyzer()
