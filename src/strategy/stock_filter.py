"""
股票筛选模块
基于基本面、技术面、历史表现筛选高质量股票

筛选条件:
1. 基本面：ROE>8%, 营收增长>5%, 资产负债率<60%
2. 技术面：价格>MA60, 相对强度前 30%
3. 历史表现：年化>5%, 夏普>0.3, 回撤<20%
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from config.logging_config import strategy_logger


@dataclass
class StockFilterParams:
    """股票筛选参数"""
    # 基本面过滤
    min_roe: float = 8.0           # 最小 ROE(%)
    min_revenue_growth: float = 5.0  # 最小营收增长 (%)
    max_debt_ratio: float = 60.0    # 最大资产负债率 (%)
    min_market_cap: float = 100     # 最小市值 (亿)

    # 技术面过滤
    ma_period: int = 60             # 趋势均线
    price_ma_threshold: float = 0.0  # 价格>MA 阈值

    # 历史表现过滤
    min_annual_return: float = 0.05   # 最小年化收益
    min_sharpe: float = 0.3           # 最小夏普比率
    max_drawdown: float = 0.20        # 最大回撤

    # 相对强度
    momentum_window: int = 20         # 动量窗口
    min_momentum_percentile: float = 0.3  # 最小动量分位数


class StockFilter:
    """股票筛选器"""

    def __init__(self, params: Optional[StockFilterParams] = None):
        self.params = params or StockFilterParams()
        self.stock_data: Dict[str, pd.DataFrame] = {}
        self.fundamental_data: Dict[str, Dict] = {}

    def set_stock_data(self, stock_data: Dict[str, pd.DataFrame]):
        """设置股票历史数据"""
        self.stock_data = stock_data

    def set_fundamental_data(self, fundamental_data: Dict[str, Dict]):
        """设置基本面数据"""
        self.fundamental_data = fundamental_data

    def filter_by_price_trend(self, stocks: List[str]) -> List[str]:
        """
        基于价格趋势过滤

        条件：价格 > MA60
        """
        filtered = []
        for ts_code in stocks:
            if ts_code not in self.stock_data:
                continue

            df = self.stock_data[ts_code]
            if len(df) < self.params.ma_period + 5:
                continue

            close = df['close']
            ma_val = close.rolling(self.params.ma_period).mean().iloc[-1]
            current_price = close.iloc[-1]

            if current_price > ma_val * (1 + self.params.price_ma_threshold):
                filtered.append(ts_code)

        strategy_logger.info(f"价格趋势过滤：{len(stocks)} -> {len(filtered)}")
        return filtered

    def filter_by_momentum(self, stocks: List[str]) -> List[str]:
        """
        基于动量排名过滤

        条件：动量排名前 70%
        """
        momentum_scores = {}

        for ts_code in stocks:
            if ts_code not in self.stock_data:
                continue

            df = self.stock_data[ts_code]
            if len(df) < self.params.momentum_window + 5:
                continue

            close = df['close']
            mom = (close.iloc[-1] - close.iloc[-self.params.momentum_window]) / close.iloc[-self.params.momentum_window]
            momentum_scores[ts_code] = mom

        if not momentum_scores:
            return stocks

        # 计算分位数
        mom_values = list(momentum_scores.values())
        threshold = np.percentile(mom_values, self.params.min_momentum_percentile * 100)

        filtered = [ts for ts, mom in momentum_scores.items() if mom >= threshold]
        strategy_logger.info(f"动量过滤：{len(stocks)} -> {len(filtered)}")
        return filtered

    def filter_by_fundamentals(self, stocks: List[str]) -> List[str]:
        """
        基于基本面过滤

        条件：ROE>8%, 营收增长>5%, 资产负债率<60%
        """
        if not self.fundamental_data:
            strategy_logger.warning("无基本面数据，跳过基本面过滤")
            return stocks

        filtered = []
        for ts_code in stocks:
            if ts_code not in self.fundamental_data:
                continue

            funda = self.fundamental_data[ts_code]
            roe = funda.get('roe', 0)
            revenue_growth = funda.get('revenue_growth', 0)
            debt_ratio = funda.get('debt_ratio', 100)
            market_cap = funda.get('market_cap', 0)

            if (roe >= self.params.min_roe and
                revenue_growth >= self.params.min_revenue_growth and
                debt_ratio <= self.params.max_debt_ratio and
                market_cap >= self.params.min_market_cap):
                filtered.append(ts_code)

        strategy_logger.info(f"基本面过滤：{len(stocks)} -> {len(filtered)}")
        return filtered

    def filter_by_history_performance(
        self,
        stocks: List[str],
        strategy,
        start_date: str,
        end_date: str
    ) -> List[str]:
        """
        基于历史表现过滤

        条件：年化>5%, 夏普>0.3, 回撤<20%
        """
        from src.backtest.engine import BacktestEngine

        filtered = []
        performance_data = {}

        for ts_code in stocks:
            if ts_code not in self.stock_data:
                continue

            try:
                # 单只股票回测
                engine = BacktestEngine(initial_capital=100000)
                engine.set_strategy(strategy)
                result = engine.run({ts_code: self.stock_data[ts_code]})

                performance_data[ts_code] = {
                    'annual_return': result.annual_return,
                    'sharpe': result.sharpe_ratio,
                    'max_drawdown': result.max_drawdown
                }

                if (result.annual_return >= self.params.min_annual_return and
                    result.sharpe_ratio >= self.params.min_sharpe and
                    result.max_drawdown <= self.params.max_drawdown):
                    filtered.append(ts_code)
            except Exception as e:
                strategy_logger.warning(f"{ts_code} 回测失败：{e}")

        strategy_logger.info(f"历史表现过滤：{len(stocks)} -> {len(filtered)}")
        return filtered

    def rank_stocks(self, stocks: List[str]) -> List[Tuple[str, float]]:
        """
        对股票综合评分

        返回：
            排序后的股票列表 [(ts_code, score), ...]
        """
        scores = {}

        for ts_code in stocks:
            score = 0

            # 动量评分 (40%)
            if ts_code in self.stock_data:
                df = self.stock_data[ts_code]
                if len(df) >= self.params.momentum_window:
                    mom = (df['close'].iloc[-1] - df['close'].iloc[-self.params.momentum_window]) / df['close'].iloc[-self.params.momentum_window]
                    score += mom * 40

            # 基本面评分 (40%)
            if ts_code in self.fundamental_data:
                funda = self.fundamental_data[ts_code]
                roe_score = min(funda.get('roe', 0) / 20, 1) * 20  # ROE 最高 20 分
                growth_score = min(funda.get('revenue_growth', 0) / 30, 1) * 20  # 增长最高 20 分
                score += roe_score + growth_score

            scores[ts_code] = score

        # 排序
        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_stocks

    def select_top_stocks(
        self,
        stocks: List[str],
        top_n: int = 15
    ) -> List[str]:
        """
        选择 Top N 只股票

        Args:
            stocks: 候选股票列表
            top_n: 选择数量

        Returns:
            选中的股票列表
        """
        # 1. 价格趋势过滤
        filtered = self.filter_by_price_trend(stocks)

        # 2. 动量过滤
        filtered = self.filter_by_momentum(filtered)

        # 3. 基本面过滤 (如果有数据)
        if self.fundamental_data:
            filtered = self.filter_by_fundamentals(filtered)

        # 4. 综合排名选 Top N
        ranked = self.rank_stocks(filtered)
        selected = [s[0] for s in ranked[:top_n]]

        strategy_logger.info(f"最终选中：{len(selected)} 只股票")
        return selected


# 工厂函数
def create_stock_filter(
    min_roe: float = 8.0,
    min_revenue_growth: float = 5.0,
    max_debt_ratio: float = 60.0,
    min_annual_return: float = 0.05,
    min_sharpe: float = 0.3,
    max_drawdown: float = 0.20
) -> StockFilter:
    """创建股票筛选器"""
    params = StockFilterParams(
        min_roe=min_roe,
        min_revenue_growth=min_revenue_growth,
        max_debt_ratio=max_debt_ratio,
        min_annual_return=min_annual_return,
        min_sharpe=min_sharpe,
        max_drawdown=max_drawdown
    )
    return StockFilter(params)
