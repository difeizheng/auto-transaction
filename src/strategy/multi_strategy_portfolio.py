"""
多策略组合框架
整合多个子策略，实现策略多样化、信号聚合、动态权重分配

核心功能:
1. 多策略并行运行
2. 信号加权聚合
3. 策略动态权重
4. 组合风险管理
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.strategy.base_strategy import BaseStrategy, Signal
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.strategy.trend_follow import TrendFollowStrategy, TrendFollowParams
from src.strategy.mean_reversion import MeanReversionStrategy, MeanReversionParams
from config.logging_config import strategy_logger


class StrategyWeightMethod(Enum):
    """权重分配方法"""
    EQUAL = "equal"                    # 等权重
    PERFORMANCE = "performance"        # 按历史表现
    VOLATILITY = "volatility"          # 按波动率倒数
    DYNAMIC = "dynamic"                # 动态调整


@dataclass
class MultiStrategyConfig:
    """多策略组合配置"""
    # 策略启用开关
    enable_optimal: bool = True        # 最优综合策略
    enable_trend_follow: bool = True   # 趋势跟踪策略
    enable_mean_reversion: bool = True # 均值回归策略

    # 权重配置
    weight_method: StrategyWeightMethod = StrategyWeightMethod.EQUAL
    custom_weights: Dict[str, float] = field(default_factory=dict)

    # 信号聚合
    aggregation_method: str = "weighted_vote"  # weighted_vote / score_avg
    min_agreement: float = 0.5  # 最小一致性要求

    # 风险控制
    max_total_position: float = 0.8  # 最大总仓位
    max_single_stock: float = 0.2    # 单只股票最大仓位
    max_strategy_correlation: float = 0.7  # 最大策略相关性


class MultiStrategyPortfolio:
    """
    多策略组合管理器

    核心思路:
    1. 多个策略独立生成信号
    2. 按权重聚合信号
    3. 统一风险管理
    4. 动态策略权重调整
    """

    def __init__(self, config: Optional[MultiStrategyConfig] = None):
        self.config = config or MultiStrategyConfig()
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_performance: Dict[str, Dict] = {}  # 策略表现记录
        self.signal_history: Dict[str, List] = {}  # 信号历史用于计算相关性

        self._init_strategies()

    def _init_strategies(self):
        """初始化子策略"""
        # 1. 最优综合策略
        if self.config.enable_optimal:
            optimal_params = OptimalStrategyParams(
                use_sharpe_optimization=True,
                use_win_rate_optimization=True,
                signal_threshold=5.5,
            )
            self.strategies['optimal'] = OptimalStrategy(params=optimal_params)
            strategy_logger.info("已初始化：最优综合策略")

        # 2. 趋势跟踪策略
        if self.config.enable_trend_follow:
            trend_params = TrendFollowParams(
                ma_trend=40,
                breakout_period=10,
                trailing_start=0.08,
            )
            self.strategies['trend_follow'] = TrendFollowStrategy(params=trend_params)
            strategy_logger.info("已初始化：趋势跟踪策略")

        # 3. 均值回归策略
        if self.config.enable_mean_reversion:
            mr_params = MeanReversionParams(
                rsi_oversold=25,
                rsi_overbought=75,
                bb_num_std=2.5,
                target_profit=0.08,
            )
            self.strategies['mean_reversion'] = MeanReversionStrategy(params=mr_params)
            strategy_logger.info("已初始化：均值回归策略")

        strategy_logger.info(f"多策略组合初始化完成，共 {len(self.strategies)} 个策略")

    def get_strategy_weights(self) -> Dict[str, float]:
        """
        获取各策略权重

        Returns:
            {strategy_name: weight}
        """
        if self.config.weight_method == StrategyWeightMethod.EQUAL:
            # 等权重
            n = len(self.strategies)
            return {name: 1.0/n for name in self.strategies}

        elif self.config.weight_method == StrategyWeightMethod.PERFORMANCE:
            # 按历史表现加权 (需要累积数据)
            if not self.strategy_performance:
                # 无历史数据时使用等权重
                return {name: 1.0/len(self.strategies) for name in self.strategies}

            # 计算夏普比率加权
            sharpe_sum = sum(
                max(0, perf.get('sharpe', 0))
                for perf in self.strategy_performance.values()
            )
            if sharpe_sum == 0:
                return {name: 1.0/len(self.strategies) for name in self.strategies}

            return {
                name: max(0, perf.get('sharpe', 0)) / sharpe_sum
                for name, perf in self.strategy_performance.items()
            }

        elif self.config.weight_method == StrategyWeightMethod.VOLATILITY:
            # 按波动率倒数加权 (低波动高权重)
            if not self.strategy_performance:
                return {name: 1.0/len(self.strategies) for name in self.strategies}

            vol_sum = sum(
                1.0 / max(0.01, perf.get('volatility', 0.1))
                for perf in self.strategy_performance.values()
            )
            return {
                name: (1.0 / max(0.01, perf.get('volatility', 0.1))) / vol_sum
                for name, perf in self.strategy_performance.items()
            }

        elif self.config.weight_method == StrategyWeightMethod.DYNAMIC:
            # 动态调整 (基于市场状态)
            # 牛市：趋势跟踪权重高
            # 震荡市：均值回归权重高
            # 熊市：最优策略权重高
            return self._calculate_dynamic_weights()

        # 默认等权重
        return {name: 1.0/len(self.strategies) for name in self.strategies}

    def _calculate_dynamic_weights(self) -> Dict[str, float]:
        """计算动态权重 (基于市场状态)"""
        # 简化版：固定配置
        # 实际应根据市场指标动态调整
        base_weights = {
            'optimal': 0.4,
            'trend_follow': 0.35,
            'mean_reversion': 0.25,
        }

        # 只返回已启用策略的权重
        enabled_weights = {
            name: weight for name, weight in base_weights.items()
            if name in self.strategies
        }

        # 归一化
        total = sum(enabled_weights.values())
        return {name: weight/total for name, weight in enabled_weights.items()}

    def aggregate_signals(
        self,
        signals_list: List[List[Signal]],
        weights: Dict[str, float]
    ) -> List[Signal]:
        """
        聚合多个策略的信号

        Args:
            signals_list: 各策略的信号列表
            weights: 策略权重

        Returns:
            聚合后的信号
        """
        # 按股票代码分组信号
        stock_signals: Dict[str, List[Tuple[str, Signal, float]]] = {}

        for strategy_name, signals in zip(self.strategies.keys(), signals_list):
            weight = weights.get(strategy_name, 0)
            for signal in signals:
                if signal.ts_code not in stock_signals:
                    stock_signals[signal.ts_code] = []
                stock_signals[signal.ts_code].append((strategy_name, signal, weight))

        # 聚合每个股票的信号
        aggregated = []
        for ts_code, sig_list in stock_signals.items():
            # 1. 检查信号方向一致性
            buy_count = sum(1 for _, s, _ in sig_list if s.direction == 'buy')
            sell_count = sum(1 for _, s, _ in sig_list if s.direction == 'sell')

            total_weight = sum(w for _, _, w in sig_list)
            if total_weight == 0:
                continue

            # 2. 计算加权信号强度
            if self.config.aggregation_method == "weighted_vote":
                # 多数投票 + 权重
                if buy_count > sell_count:
                    direction = 'buy'
                    agreement = buy_count / len(sig_list)
                elif sell_count > buy_count:
                    direction = 'sell'
                    agreement = sell_count / len(sig_list)
                else:
                    continue  # 平票，跳过

                # 检查一致性阈值
                if agreement < self.config.min_agreement:
                    strategy_logger.debug(f"{ts_code}: 一致性不足 ({agreement:.1%})，跳过")
                    continue

                # 加权平均强度
                avg_strength = sum(s.strength * w for _, s, w in sig_list if s.direction == direction) / total_weight

            else:  # score_avg
                # 分数平均
                avg_strength = sum(s.strength * w for _, s, w in sig_list) / total_weight
                direction = 'buy' if avg_strength > 0.5 else 'sell' if avg_strength < -0.5 else None
                if not direction:
                    continue

            # 3. 创建聚合信号
            reasons = [f"{name}: {sig.reason}" for name, sig, _ in sig_list]
            aggregated_signal = Signal(
                ts_code=ts_code,
                direction=direction,
                price=sig_list[0][1].price,
                volume=sig_list[0][1].volume,
                strength=avg_strength,
                reason=' | '.join(reasons[:3]),  # 最多显示 3 个原因
            )
            aggregated.append(aggregated_signal)

        return aggregated

    def on_init(self):
        """策略初始化"""
        strategy_logger.info(f"多策略组合初始化完成，共 {len(self.strategies)} 个策略")
        for name, strategy in self.strategies.items():
            try:
                strategy.on_init()
                strategy_logger.info(f"  - {name}: 已初始化")
            except Exception as e:
                strategy_logger.error(f"  - {name}: 初始化失败 {e}")

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """
        K 线数据回调 - 所有策略并行运行

        Args:
            data: K 线数据
            current_date: 当前日期

        Returns:
            聚合后的信号
        """
        strategy_logger.info(f"[多策略] 开始生成信号 ({current_date})")

        # 1. 各策略独立生成信号
        all_signals = []
        strategy_names = []

        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_bar(data, current_date)
                all_signals.append(signals)
                strategy_names.append(name)
                strategy_logger.info(f"[多策略] {name}: 生成 {len(signals)} 个信号")
            except Exception as e:
                strategy_logger.error(f"[多策略] {name} 策略执行失败：{e}")
                all_signals.append([])
                strategy_names.append(name)

        # 2. 获取策略权重
        weights = self.get_strategy_weights()
        strategy_logger.debug(f"[多策略] 策略权重：{weights}")

        # 3. 聚合信号
        aggregated_signals = self.aggregate_signals(all_signals, weights)
        strategy_logger.info(f"[多策略] 聚合后信号：{len(aggregated_signals)} 个")

        # 4. 应用组合风险控制
        final_signals = self._apply_portfolio_risk_control(aggregated_signals, data, current_date)

        return final_signals

    def _apply_portfolio_risk_control(
        self,
        signals: List[Signal],
        data: Dict[str, Any],
        current_date: str
    ) -> List[Signal]:
        """
        应用组合风险控制

        - 检查总仓位限制
        - 检查单只股票集中度
        """
        if not signals:
            return signals

        # 简化版风控
        # 实际应结合账户状态、持仓等

        filtered_signals = []
        for signal in signals:
            # 检查单只股票集中度
            if signal.volume * signal.price > 1000000 * self.config.max_single_stock:
                strategy_logger.warning(f"{signal.ts_code}: 超出单只股票限制，过滤")
                continue

            filtered_signals.append(signal)

        return filtered_signals

    def update_performance(self, strategy_name: str, metrics: Dict):
        """更新策略表现记录"""
        self.strategy_performance[strategy_name] = metrics

    def get_strategy_summary(self) -> Dict:
        """获取策略摘要"""
        return {
            'strategies': list(self.strategies.keys()),
            'weights': self.get_strategy_weights(),
            'performance': self.strategy_performance,
        }


# 工厂函数
def create_multi_strategy_portfolio(
    enable_optimal: bool = True,
    enable_trend: bool = True,
    enable_mean_reversion: bool = False,
    weight_method: str = "equal"
) -> MultiStrategyPortfolio:
    """
    创建多策略组合

    Args:
        enable_optimal: 启用最优综合策略
        enable_trend: 启用趋势跟踪策略
        enable_mean_reversion: 启用均值回归策略
        weight_method: 权重方法 (equal/performance/volatility/dynamic)

    Returns:
        多策略组合实例
    """
    weight_map = {
        'equal': StrategyWeightMethod.EQUAL,
        'performance': StrategyWeightMethod.PERFORMANCE,
        'volatility': StrategyWeightMethod.VOLATILITY,
        'dynamic': StrategyWeightMethod.DYNAMIC,
    }

    config = MultiStrategyConfig(
        enable_optimal=enable_optimal,
        enable_trend_follow=enable_trend,
        enable_mean_reversion=enable_mean_reversion,
        weight_method=weight_map.get(weight_method, StrategyWeightMethod.EQUAL),
    )

    return MultiStrategyPortfolio(config)


if __name__ == "__main__":
    # 测试多策略组合
    portfolio = create_multi_strategy_portfolio(
        enable_optimal=True,
        enable_trend=True,
        enable_mean_reversion=True,
        weight_method="equal"
    )

    print("多策略组合初始化完成")
    print(f"策略列表：{list(portfolio.strategies.keys())}")
    print(f"策略权重：{portfolio.get_strategy_weights()}")
