"""
策略性能指标计算模块
提供专业的金融指标计算
"""
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from config.logging_config import trader_logger
from src.utils.database import db


class PerformanceMetrics:
    """性能指标计算器"""

    # 交易日数量（年）
    TRADING_DAYS_PER_YEAR = 250

    def __init__(self, initial_capital: float = 20000):
        """
        初始化

        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital

    def calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.03) -> float:
        """
        计算年化夏普比率

        Args:
            returns: 日收益率列表
            risk_free_rate: 无风险利率（年化）

        Returns:
            夏普比率
        """
        if not returns or len(returns) < 2:
            return 0.0

        # 计算年化收益率
        mean_return = np.mean(returns)
        annualized_return = mean_return * self.TRADING_DAYS_PER_YEAR

        # 计算年化波动率
        std_return = np.std(returns, ddof=1)
        if std_return == 0:
            return 0.0
        annualized_std = std_return * np.sqrt(self.TRADING_DAYS_PER_YEAR)

        # 夏普比率
        sharpe = (annualized_return - risk_free_rate) / annualized_std

        return round(sharpe, 2)

    def calculate_max_drawdown(self, nav_series: List[float]) -> Dict:
        """
        计算最大回撤

        Args:
            nav_series: 净值列表

        Returns:
            最大回撤信息
        """
        if not nav_series:
            return {'max_drawdown': 0, 'peak_date': '', 'trough_date': '', 'drawdown_duration': 0}

        peak = nav_series[0]
        peak_idx = 0
        max_dd = 0
        trough_idx = 0

        drawdowns = []
        for i, nav in enumerate(nav_series):
            if nav > peak:
                peak = nav
                peak_idx = i

            dd = (peak - nav) / peak if peak > 0 else 0
            drawdowns.append(dd)

            if dd > max_dd:
                max_dd = dd
                trough_idx = i

        # 回撤持续时间
        drawdown_duration = trough_idx - peak_idx

        return {
            'max_drawdown': round(max_dd * 100, 2),  # 百分比
            'peak_idx': peak_idx,
            'trough_idx': trough_idx,
            'drawdown_duration': drawdown_duration
        }

    def calculate_information_ratio(self, strategy_returns: List[float],
                                     benchmark_returns: List[float]) -> float:
        """
        计算信息比率（超额收益/跟踪误差）

        Args:
            strategy_returns: 策略日收益率
            benchmark_returns: 基准日收益率

        Returns:
            信息比率
        """
        if len(strategy_returns) != len(benchmark_returns) or len(strategy_returns) < 2:
            return 0.0

        # 超额收益
        excess_returns = [s - b for s, b in zip(strategy_returns, benchmark_returns)]

        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)

        if std_excess == 0:
            return 0.0

        # 年化信息比率
        ir = (mean_excess * self.TRADING_DAYS_PER_YEAR) / (std_excess * np.sqrt(self.TRADING_DAYS_PER_YEAR))

        return round(ir, 2)

    def calculate_calmar_ratio(self, annualized_return: float, max_drawdown: float) -> float:
        """
        计算卡玛比率（年化收益/最大回撤）

        Args:
            annualized_return: 年化收益率
            max_drawdown: 最大回撤（百分比）

        Returns:
            卡玛比率
        """
        if max_drawdown == 0:
            return 0.0

        return round(annualized_return / max_drawdown, 2)

    def calculate_win_rate(self, returns: List[float]) -> Dict:
        """
        计算胜率

        Args:
            returns: 日收益率列表

        Returns:
            胜率信息
        """
        if not returns:
            return {'win_rate': 0, 'wins': 0, 'losses': 0, 'total': 0}

        wins = sum(1 for r in returns if r > 0)
        losses = sum(1 for r in returns if r < 0)
        total = len(returns)

        return {
            'win_rate': round(wins / total * 100, 2) if total > 0 else 0,
            'wins': wins,
            'losses': losses,
            'total': total
        }

    def calculate_profit_loss_ratio(self, returns: List[float]) -> float:
        """
        计算盈亏比（平均盈利/平均亏损）

        Args:
            returns: 日收益率列表

        Returns:
            盈亏比
        """
        profits = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]

        avg_profit = np.mean(profits) if profits else 0
        avg_loss = abs(np.mean(losses)) if losses else 0

        if avg_loss == 0:
            return 0.0

        return round(avg_profit / avg_loss, 2)

    def calculate_volatility(self, returns: List[float]) -> Dict:
        """
        计算波动率

        Args:
            returns: 日收益率列表

        Returns:
            波动率信息
        """
        if not returns:
            return {'daily_vol': 0, 'annualized_vol': 0}

        daily_vol = np.std(returns, ddof=1)
        annualized_vol = daily_vol * np.sqrt(self.TRADING_DAYS_PER_YEAR)

        return {
            'daily_vol': round(daily_vol * 100, 2),  # 百分比
            'annualized_vol': round(annualized_vol * 100, 2)
        }

    def calculate_all_metrics(self, days: int = 30) -> Dict:
        """
        计算所有指标

        Args:
            days: 统计天数

        Returns:
            完整指标字典
        """
        # 获取净值数据
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        try:
            df = db.query("""
                SELECT date, nav, daily_return, benchmark_change, excess_return
                FROM daily_nav
                WHERE date >= ?
                ORDER BY date ASC
            """, (start_date,))

            if df.empty:
                return {}

            nav_series = df['nav'].tolist()
            returns = df['daily_return'].fillna(0).tolist()
            benchmark_returns = df['benchmark_change'].fillna(0).tolist()

            # 基本指标
            first_nav = nav_series[0]
            last_nav = nav_series[-1]
            total_return = (last_nav - first_nav) / first_nav if first_nav > 0 else 0

            # 年化收益率
            days_count = len(nav_series)
            if days_count > 0:
                annualized_return = (last_nav / first_nav - 1) * self.TRADING_DAYS_PER_YEAR / days_count if first_nav > 0 else 0
            else:
                annualized_return = 0

            # 计算各项指标
            sharpe = self.calculate_sharpe_ratio(returns)
            max_dd_info = self.calculate_max_drawdown(nav_series)
            info_ratio = self.calculate_information_ratio(returns, benchmark_returns)
            calmar = self.calculate_calmar_ratio(annualized_return * 100, max_dd_info['max_drawdown'])
            win_rate_info = self.calculate_win_rate(returns)
            profit_loss = self.calculate_profit_loss_ratio(returns)
            vol_info = self.calculate_volatility(returns)

            # 累计超额收益
            total_excess = sum(df['excess_return'].fillna(0).tolist())

            return {
                'period_days': days_count,
                'total_return': round(total_return * 100, 2),
                'annualized_return': round(annualized_return * 100, 2),
                'sharpe_ratio': sharpe,
                'max_drawdown': max_dd_info['max_drawdown'],
                'max_drawdown_duration': max_dd_info['drawdown_duration'],
                'information_ratio': info_ratio,
                'calmar_ratio': calmar,
                'win_rate': win_rate_info['win_rate'],
                'wins': win_rate_info['wins'],
                'losses': win_rate_info['losses'],
                'profit_loss_ratio': profit_loss,
                'daily_volatility': vol_info['daily_vol'],
                'annualized_volatility': vol_info['annualized_vol'],
                'total_excess_return': round(total_excess * 100, 2),
                'current_nav': round(last_nav, 4),
                'initial_capital': self.initial_capital,
                'current_asset': round(last_nav * self.initial_capital, 2)
            }

        except Exception as e:
            trader_logger.error(f"计算性能指标失败: {e}")
            return {}

    def get_rolling_metrics(self, window: int = 30, step: int = 5) -> List[Dict]:
        """
        获取滚动指标（用于绘制时间序列）

        Args:
            window: 滚动窗口大小
            step: 滚动步长

        Returns:
            滚动指标列表
        """
        try:
            # 获取足够的历史数据
            lookback = window + step * 10
            start_date = (datetime.now() - timedelta(days=lookback)).strftime('%Y%m%d')

            df = db.query("""
                SELECT date, nav, daily_return, benchmark_change
                FROM daily_nav
                WHERE date >= ?
                ORDER BY date ASC
            """, (start_date,))

            if df.empty or len(df) < window:
                return []

            results = []
            returns = df['daily_return'].fillna(0).tolist()
            benchmark_returns = df['benchmark_change'].fillna(0).tolist()

            for i in range(0, len(returns) - window + 1, step):
                window_returns = returns[i:i+window]
                window_benchmark = benchmark_returns[i:i+window]
                window_nav = df['nav'].iloc[i:i+window].tolist()

                first_nav = window_nav[0]
                last_nav = window_nav[-1]
                total_ret = (last_nav - first_nav) / first_nav if first_nav > 0 else 0
                ann_ret = (last_nav / first_nav - 1) * self.TRADING_DAYS_PER_YEAR / window if first_nav > 0 else 0

                metrics = {
                    'date': df['date'].iloc[i + window - 1],
                    'sharpe': self.calculate_sharpe_ratio(window_returns),
                    'max_drawdown': self.calculate_max_drawdown(window_nav)['max_drawdown'],
                    'total_return': round(total_ret * 100, 2),
                    'annualized_return': round(ann_ret * 100, 2),
                    'win_rate': self.calculate_win_rate(window_returns)['win_rate'],
                    'info_ratio': self.calculate_information_ratio(window_returns, window_benchmark)
                }
                results.append(metrics)

            return results

        except Exception as e:
            trader_logger.error(f"计算滚动指标失败: {e}")
            return []


# 全局实例
performance_metrics = PerformanceMetrics()


def get_performance_metrics(days: int = 30) -> Dict:
    """获取性能指标（便捷函数）"""
    return performance_metrics.calculate_all_metrics(days)


def get_rolling_metrics(window: int = 30, step: int = 5) -> List[Dict]:
    """获取滚动指标（便捷函数）"""
    return performance_metrics.get_rolling_metrics(window, step)


if __name__ == "__main__":
    # 测试
    print("=== 测试性能指标计算 ===")

    # 模拟数据
    import random

    # 创建模拟净值
    nav = 1.0
    navs = []
    returns = []
    benchmark = []

    for i in range(60):
        ret = random.uniform(-0.02, 0.03)
        bench = random.uniform(-0.015, 0.02)
        nav = nav * (1 + ret)
        navs.append(nav)
        returns.append(ret)
        benchmark.append(bench)

    # 计算指标
    pm = PerformanceMetrics(initial_capital=20000)

    print(f"\n夏普比率: {pm.calculate_sharpe_ratio(returns)}")
    print(f"最大回撤: {pm.calculate_max_drawdown(navs)}")
    print(f"信息比率: {pm.calculate_information_ratio(returns, benchmark)}")
    print(f"胜率: {pm.calculate_win_rate(returns)}")
    print(f"盈亏比: {pm.calculate_profit_loss_ratio(returns)}")
    print(f"波动率: {pm.calculate_volatility(returns)}")

    print("\n测试完成")