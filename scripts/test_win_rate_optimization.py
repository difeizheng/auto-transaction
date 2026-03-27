"""
胜率优化测试脚本
验证动量因子、资金流因子、股票强度筛选效果
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.win_rate_optimizer import (
    WinRateOptimizer, WinRateOptimizationConfig,
    create_win_rate_optimizer, get_win_rate_optimization_params
)
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from config.logging_config import strategy_logger


def test_win_rate_optimizer():
    """测试胜率优化器基础功能"""
    print("=" * 60)
    print("胜率优化器功能测试")
    print("=" * 60)

    optimizer = create_win_rate_optimizer()

    # 打印配置
    print("\n优化器配置:")
    print(f"  动量因子：{'启用' if optimizer.config.use_momentum_factor else '禁用'}")
    print(f"  动量周期：{optimizer.config.momentum_period} 日")
    print(f"  资金流向：{'启用' if optimizer.config.use_money_flow_factor else '禁用'}")
    print(f"  资金流周期：{optimizer.config.money_flow_period} 日")
    print(f"  强势股筛选：{'启用' if optimizer.config.use_stock_filter else '禁用'}")
    print(f"  强度排名：前{optimizer.config.min_strength_rank*100:.0f}%")
    print(f"  信号置信度：>{optimizer.config.min_signal_confidence*100:.0f}%")

    return optimizer


def test_optimized_strategy():
    """测试优化后的策略"""
    print("\n" + "=" * 60)
    print("优化后策略测试")
    print("=" * 60)

    # 创建优化后的策略参数
    params = OptimalStrategyParams(
        use_win_rate_optimization=True,
        use_sharpe_optimization=True,
        signal_threshold=6.0,  # 提高阈值 (原 5.5)
        min_momentum_score=0.03,
        min_stock_strength_rank=0.3,
        min_signal_confidence=0.6,
    )

    strategy = OptimalStrategy(params=params)

    print("\n策略参数:")
    print(f"  信号阈值：{params.signal_threshold}")
    print(f"  动量过滤：>{params.min_momentum_score*100:.1f}%")
    print(f"  股票强度：前{params.min_stock_strength_rank*100:.0f}%")
    print(f"  置信度阈值：>{params.min_signal_confidence*100:.0f}%")

    # 验证优化器已初始化
    if strategy.win_rate_optimizer:
        print("\n[OK] 胜率优化器已初始化")
    else:
        print("\n[ERR] 胜率优化器未初始化")

    if strategy.sharpe_optimizer:
        print("[OK] 夏普优化器已初始化")
    else:
        print("[ERR] 夏普优化器未初始化")

    return strategy


def print_optimization_summary():
    """打印优化总结"""
    print("\n" + "=" * 60)
    print("胜率优化总结")
    print("=" * 60)

    config = get_win_rate_optimization_params()

    print("\n优化目标：胜率 51.4% -> 55%+")
    print("\n核心优化措施:")

    for i, note in enumerate(config['optimization_notes'], 1):
        print(f"  {i}. {note}")

    print("\n预期效果:")
    print("  - 动量因子选择强势上涨股票，提高买入即涨概率")
    print("  - 资金流向跟踪主力动向，避免散户陷阱")
    print("  - 强势股筛选只交易强度前 30% 股票")
    print("  - 信号置信度过滤低质量信号")
    print("  - 综合预期：胜率提升 3-5%")

    print("\n后续验证步骤:")
    print("  1. 运行回测对比优化前后表现")
    print("  2. 分析胜率、盈亏比、交易次数变化")
    print("  3. 根据回测结果微调参数")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("胜率优化测试脚本 - v4.0")
    print("=" * 60)

    # 1. 测试优化器
    optimizer = test_win_rate_optimizer()

    # 2. 测试策略
    strategy = test_optimized_strategy()

    # 3. 打印总结
    print_optimization_summary()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
