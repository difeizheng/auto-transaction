"""
多因子选股策略模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.strategy.base_strategy import BaseStrategy, Signal, BaseMultiAssetStrategy
from src.utils.database import db
from src.data_collector.data_manager import data_manager
from config.logging_config import strategy_logger


@dataclass
class FactorParams:
    """因子参数"""
    name: str
    direction: int  # 1: 越大越好，-1: 越小越好
    weight: float = 1.0
    normalize: bool = True


class MultiFactorStrategy(BaseMultiAssetStrategy):
    """
    多因子选股策略

    支持的因子:
    - 估值因子：PE, PB, PS
    - 盈利因子：ROE, ROA
    - 成长因子：营收增长率，利润增长率
    - 动量因子：过去 N 日收益率
    - 波动因子：过去 N 日波动率
    """

    def __init__(
        self,
        name: str = "multi_factor_strategy",
        factors: Optional[List[str]] = None,
        top_n: int = 10,
        rebalance_days: int = 5
    ):
        """
        初始化多因子策略

        Args:
            name: 策略名称
            factors: 因子列表
            top_n: 选取评分最高的 N 只股票
            rebalance_days: 调仓周期 (交易日)
        """
        super().__init__(name)

        self.factors = factors or ['pe', 'pb', 'roe', 'momentum']
        self.top_n = top_n
        self.rebalance_days = rebalance_days

        # 因子权重 (可调整)
        self.factor_weights = {
            'pe': 0.25,      # 估值
            'pb': 0.15,      # 市净率
            'ps': 0.10,      # 市销率
            'roe': 0.25,     # 盈利能力
            'roa': 0.10,     # 资产回报
            'momentum': 0.15 # 动量
        }

        # 因子方向 (1: 越大越好，-1: 越小越好)
        self.factor_directions = {
            'pe': -1,    # PE 越低越好
            'pb': -1,    # PB 越低越好
            'ps': -1,    # PS 越低越好
            'roe': 1,    # ROE 越高越好
            'roa': 1,    # ROA 越高越好
            'momentum': 1 # 动量越高越好
        }

        # 状态变量
        self.current_holdings: List[str] = []
        self.last_rebalance_date: str = ""
        self.stock_scores: Dict[str, pd.DataFrame] = {}
        self.price_history: Dict[str, List[float]] = {}

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.current_holdings = []
        self.last_rebalance_date = ""
        self.stock_scores = {}
        self.price_history = {}

        # 加载股票池
        self._load_stock_pool()

    def _load_stock_pool(self):
        """从数据库加载股票池"""
        stocks_df = data_manager.get_stock_list(status='L')
        if not stocks_df.empty:
            self.universe = stocks_df['ts_code'].tolist()
            strategy_logger.info(f"加载股票池：{len(self.universe)} 只股票")

    def _calculate_factor_values(
        self,
        ts_code: str,
        current_date: str
    ) -> Dict[str, float]:
        """
        计算单只股票的各项因子值

        Args:
            ts_code: 股票代码
            current_date: 当前日期

        Returns:
            因子值字典
        """
        factors = {}

        # 1. 获取财务数据
        financial_df = data_manager.get_financial_indicators(ts_code)

        if not financial_df.empty:
            latest_financial = financial_df.iloc[0]

            # 估值因子
            factors['pe'] = latest_financial.get('pe', None)
            factors['pb'] = latest_financial.get('pb', None)
            factors['ps'] = latest_financial.get('ps', None)

            # 盈利因子
            factors['roe'] = latest_financial.get('roe', None)
            factors['roa'] = latest_financial.get('roa', None)

        # 2. 获取行情数据计算动量和波动率
        daily_df = data_manager.get_daily_quotes(ts_code)

        if not daily_df.empty:
            # 计算动量 (过去 20 日收益率)
            if len(daily_df) >= 20:
                close_20 = daily_df.iloc[-20]['close']
                close_latest = daily_df.iloc[-1]['close']
                factors['momentum'] = (close_latest / close_20 - 1) * 100

            # 计算波动率 (过去 20 日)
            if len(daily_df) >= 20:
                returns = daily_df['close'].pct_change().dropna()
                factors['volatility'] = returns.std() * np.sqrt(252) * 100

        return factors

    def _calculate_stock_scores(
        self,
        current_date: str
    ) -> pd.DataFrame:
        """
        计算所有股票的因子评分

        Args:
            current_date: 当前日期

        Returns:
            评分 DataFrame
        """
        all_factors = []

        # 选取活跃的股票 (有成交量)
        active_stocks = self._get_active_stocks(current_date)

        for ts_code in active_stocks[:200]:  # 限制数量以提高性能
            factors = self._calculate_factor_values(ts_code, current_date)
            factors['ts_code'] = ts_code
            all_factors.append(factors)

        if not all_factors:
            return pd.DataFrame()

        df = pd.DataFrame(all_factors)

        if df.empty:
            return df

        # 标准化因子值 (Z-Score)
        for factor in self.factors:
            if factor in df.columns:
                valid_data = df[factor].dropna()
                if len(valid_data) > 10:
                    mean_val = valid_data.mean()
                    std_val = valid_data.std()
                    if std_val > 0:
                        df[factor + '_z'] = (df[factor] - mean_val) / std_val

        # 计算综合评分
        df['composite_score'] = 0.0

        for factor in self.factors:
            if factor + '_z' in df.columns:
                direction = self.factor_directions.get(factor, 1)
                weight = self.factor_weights.get(factor, 1.0)
                df['composite_score'] += direction * weight * df[factor + '_z'].fillna(0)

        return df

    def _get_active_stocks(self, current_date: str) -> List[str]:
        """
        获取活跃股票 (有成交量)

        Args:
            current_date: 当前日期

        Returns:
            活跃股票列表
        """
        # 简单实现：返回部分股票
        # 实际使用应该从数据库查询当日有成交量的股票
        return self.universe[:500] if len(self.universe) > 0 else []

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """
        K 线数据回调

        Args:
            data: 当日行情数据字典
            current_date: 当前交易日期

        Returns:
            交易信号列表
        """
        if not self.initialized:
            self.on_init()

        signals = []

        # 检查是否需要调仓
        should_rebalance = self._should_rebalance(current_date)

        if should_rebalance:
            strategy_logger.info(f"{current_date} 开始调仓...")

            # 计算股票评分
            scores_df = self._calculate_stock_scores(current_date)

            if not scores_df.empty:
                # 选取评分最高的股票
                top_stocks = scores_df.nlargest(self.top_n, 'composite_score')

                target_holdings = top_stocks['ts_code'].tolist()
                target_weights = {
                    row['ts_code']: 1.0 / len(target_stocks)
                    for _, row in top_stocks.iterrows()
                }

                # 生成调仓信号
                signals = self._generate_rebalance_signals(
                    target_holdings=target_holdings,
                    target_weights=target_weights,
                    current_holdings=self.current_holdings,
                    data=data
                )

                # 更新持仓
                self.current_holdings = target_holdings
                self.last_rebalance_date = current_date

                strategy_logger.info(f"调仓完成，持有 {len(self.current_holdings)} 只股票")

        return signals

    def _should_rebalance(self, current_date: str) -> bool:
        """
        判断是否需要调仓

        Args:
            current_date: 当前交易日期

        Returns:
            是否需要调仓
        """
        # 首次运行
        if not self.last_rebalance_date:
            return True

        # 计算间隔天数
        try:
            last_date = datetime.strptime(self.last_rebalance_date, "%Y%m%d")
            curr_date = datetime.strptime(current_date, "%Y%m%d")
            days_diff = (curr_date - last_date).days

            # 简单按自然日计算，实际应该用交易日历
            rebalance_interval = self.rebalance_days

            return days_diff >= rebalance_interval
        except ValueError:
            return False

    def _generate_rebalance_signals(
        self,
        target_holdings: List[str],
        target_weights: Dict[str, float],
        current_holdings: List[str],
        data: Dict[str, Any]
    ) -> List[Signal]:
        """
        生成调仓信号

        Args:
            target_holdings: 目标持仓
            target_weights: 目标权重
            current_holdings: 当前持仓
            data: 行情数据

        Returns:
            交易信号列表
        """
        signals = []

        # 计算需要买入和卖出的股票
        to_buy = set(target_holdings) - set(current_holdings)
        to_sell = set(current_holdings) - set(target_holdings)
        to_hold = set(target_holdings) & set(current_holdings)

        # 获取当前资本
        capital = self.engine.capital if self.engine else 1000000

        # 生成买入信号
        for ts_code in to_buy:
            if ts_code in data:
                price = data[ts_code].get('close', 0)
                if price > 0:
                    weight = target_weights.get(ts_code, 1.0 / len(target_holdings))
                    target_value = capital * weight
                    volume = int(target_value / price / 100) * 100

                    if volume > 0:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='buy',
                            price=price,
                            volume=volume,
                            weight=weight,
                            reason=f"多因子选股买入"
                        ))

        # 生成卖出信号
        for ts_code in to_sell:
            if ts_code in data:
                price = data[ts_code].get('close', 0)
                # 全部卖出
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='sell',
                    price=price,
                    volume=100000,  # 大数量表示全部卖出
                    reason=f"多因子选股卖出"
                ))

        # 调整持仓权重
        for ts_code in to_hold:
            if ts_code in data:
                price = data[ts_code].get('close', 0)
                target_weight = target_weights.get(ts_code, 0)
                current_weight = 1.0 / len(current_holdings) if current_holdings else 0

                # 如果权重变化超过阈值，进行调整
                if abs(target_weight - current_weight) > 0.05:
                    if target_weight > current_weight:
                        # 加仓
                        weight_diff = target_weight - current_weight
                        target_value = capital * weight_diff
                        volume = int(target_value / price / 100) * 100
                        if volume > 0:
                            signals.append(self.generate_signal(
                                ts_code=ts_code,
                                direction='buy',
                                price=price,
                                volume=volume,
                                weight=target_weight,
                                reason=f"多因子加仓"
                            ))
                    else:
                        # 减仓
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='sell',
                            price=price,
                            volume=1000,
                            weight=target_weight,
                            reason=f"多因子减仓"
                        ))

        return signals

    def get_factor_exposure(self) -> Dict[str, float]:
        """
        获取当前组合的因子暴露

        Returns:
            因子暴露字典
        """
        if not self.current_holdings:
            return {}

        exposures = {}

        for factor in self.factors:
            factor_values = []
            for ts_code in self.current_holdings:
                factors = self._calculate_factor_values(ts_code, "")
                if factor in factors and factors[factor] is not None:
                    factor_values.append(factors[factor])

            if factor_values:
                exposures[factor] = np.mean(factor_values)

        return exposures


# 简化的多因子策略 (适用于回测)
class SimpleMultiFactorStrategy(MultiFactorStrategy):
    """
    简化多因子策略
    直接使用预计算的因子数据进行选股
    """

    def __init__(
        self,
        name: str = "simple_multi_factor",
        factors: Optional[List[str]] = None,
        top_n: int = 10,
        rebalance_days: int = 5
    ):
        super().__init__(name, factors, top_n, rebalance_days)

        # 预加载的因子数据
        self.factor_data: pd.DataFrame = None

    def set_factor_data(self, factor_data: pd.DataFrame):
        """
        设置因子数据

        Args:
            factor_data: 因子数据 DataFrame
                        包含 ts_code 和各因子列
        """
        self.factor_data = factor_data
        strategy_logger.info(f"设置因子数据：{len(factor_data)} 只股票")

    def _calculate_stock_scores(self, current_date: str) -> pd.DataFrame:
        """使用预加载的因子数据计算评分"""
        if self.factor_data is None or self.factor_data.empty:
            return pd.DataFrame()

        df = self.factor_data.copy()

        # 选取需要的因子
        available_factors = [f for f in self.factors if f in df.columns]

        if not available_factors:
            return pd.DataFrame()

        # 标准化
        for factor in available_factors:
            valid_data = df[factor].dropna()
            if len(valid_data) > 10:
                mean_val = valid_data.mean()
                std_val = valid_data.std()
                if std_val > 0:
                    df[factor + '_z'] = (df[factor] - mean_val) / std_val

        # 计算综合评分
        df['composite_score'] = 0.0

        for factor in available_factors:
            if factor + '_z' in df.columns:
                direction = self.factor_directions.get(factor, 1)
                weight = self.factor_weights.get(factor, 1.0)
                df['composite_score'] += direction * weight * df[factor + '_z'].fillna(0)

        return df
