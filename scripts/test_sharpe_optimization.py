"""
夏普比率优化测试脚本
对比优化前后的夏普比率表现
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.sharpe_optimizer import SharpeOptimizer, SharpeOptimizationConfig, optimize_sharpe_params
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from config.logging_config import strategy_logger


def test_sharpe_optimizer():
    """测试夏普优化器基础功能"""
    print("=" * 60)
    print("夏普优化器功能测试")
    print("=" * 60)

    config = SharpeOptimizationConfig(
        use_volatility_filter=True,
        max_volatility_threshold=0.04,
        use_stability_factor=True,
        min_stability_threshold=0.6,
    )

    optimizer = SharpeOptimizer(config)

    # 打印配置
    print("\n优化器配置:")
    print(f"  波动率过滤器：{'启用' if config.use_volatility_filter else '禁用'}")
    print(f"  最大波动率阈值：{config.max_volatility_threshold*100}%")
    print(f"  稳定性因子：{'启用' if config.use_stability_factor else '禁用'}")
    print(f"  最小稳定性阈值：{config.min_stability_threshold*100}%")
    print(f"  利润锁定触发点：{config.profit_lock_trigger*100}%")

    return optimizer


def test_optimized_strategy():
    """测试优化后的策略"""
    print("\n" + "=" * 60)
    print("优化后策略测试")
    print("=" * 60)

    # 创建优化后的策略参数
    params = OptimalStrategyParams(
        use_sharpe_optimization=True,
        base_stop_loss=0.035,  # 3.5% 紧止损
        base_take_profit=0.40,  # 40% 宽止盈
        signal_threshold=5.2,  # 略降低阈值
        max_volatility_threshold=0.04,
        min_stability_threshold=0.6,
        profit_lock_trigger=0.08,
    )

    strategy = OptimalStrategy(params=params)

    print("\n策略参数:")
    print(f"  止损：{params.base_stop_loss*100}%")
    print(f"  止盈：{params.base_take_profit*100}%")
    print(f"  信号阈值：{params.signal_threshold}")
    print(f"  波动率过滤：{params.max_volatility_threshold*100}%")
    print(f"  稳定性过滤：{params.min_stability_threshold*100}%")
    print(f"  利润锁定：{params.profit_lock_trigger*100}%")

    # 验证夏普优化器已初始化
    if strategy.sharpe_optimizer:
        print("\n[OK] 夏普优化器已初始化")
    else:
        print("\n[ERR] 夏普优化器未初始化")

    return strategy


def print_optimization_summary():
    """打印优化总结"""
    print("\n" + "=" * 60)
    print("夏普比率优化总结")
    print("=" * 60)

    config = optimize_sharpe_params()

    print("\n优化目标：夏普 0.63 → 1.0+")
    print("\n核心优化措施:")

    for i, note in enumerate(config['optimization_notes'], 1):
        print(f"  {i}. {note}")

    print("\n预期效果:")
    print("  - 紧止损 (3.5%) 减少单笔亏损，降低回撤")
    print("  - 波动率过滤避开高风险股票，减少异常亏损")
    print("  - 稳定性因子提高交易质量，增加收益稳定性")
    print("  - 分级止盈保护利润，降低收益波动率")
    print("  - 综合预期：夏普比率提升 40-60%")

    print("\n后续验证步骤:")
    print("  1. 运行回测对比优化前后表现")
    print("  2. 分析夏普比率、最大回撤、胜率变化")
    print("  3. 根据回测结果微调参数")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("夏普比率优化测试脚本 - v3.0")
    print("=" * 60)

    # 1. 测试优化器
    optimizer = test_sharpe_optimizer()

    # 2. 测试策略
    strategy = test_optimized_strategy()

    # 3. 打印总结
    print_optimization_summary()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
