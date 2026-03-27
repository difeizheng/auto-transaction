"""
多策略组合测试脚本
验证多策略框架运行和信号聚合
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.multi_strategy_portfolio import (
    create_multi_strategy_portfolio,
    MultiStrategyConfig,
    StrategyWeightMethod
)


def test_multi_strategy_portfolio():
    """测试多策略组合"""
    print("=" * 60)
    print("多策略组合测试")
    print("=" * 60)

    # 1. 创建多策略组合 (全部策略启用)
    portfolio = create_multi_strategy_portfolio(
        enable_optimal=True,
        enable_trend=True,
        enable_mean_reversion=True,
        weight_method="equal"
    )

    print("\n策略配置:")
    summary = portfolio.get_strategy_summary()
    print(f"  策略列表：{summary['strategies']}")
    print(f"  策略权重：{summary['weights']}")

    # 2. 测试不同权重方法
    print("\n" + "-" * 40)
    print("不同权重方法对比:")

    weight_methods = ["equal", "dynamic"]
    for method in weight_methods:
        portfolio_test = create_multi_strategy_portfolio(
            enable_optimal=True,
            enable_trend=True,
            enable_mean_reversion=True,
            weight_method=method
        )
        weights = portfolio_test.get_strategy_weights()
        print(f"\n  {method} 权重:")
        for name, weight in weights.items():
            print(f"    {name}: {weight:.2%}")

    return portfolio


def test_selective_strategies():
    """测试选择性启用策略"""
    print("\n" + "=" * 60)
    print("选择性启用策略测试")
    print("=" * 60)

    # 只启用最优策略 + 趋势跟踪
    portfolio = create_multi_strategy_portfolio(
        enable_optimal=True,
        enable_trend=True,
        enable_mean_reversion=False,
        weight_method="dynamic"
    )

    print("\n配置：最优 + 趋势跟踪")
    summary = portfolio.get_strategy_summary()
    print(f"  策略列表：{summary['strategies']}")
    print(f"  策略权重：{summary['weights']}")

    return portfolio


def print_summary():
    """打印总结"""
    print("\n" + "=" * 60)
    print("多策略组合总结")
    print("=" * 60)

    print("\n策略组成:")
    print("  1. 最优综合策略 - 核心策略，多因子综合")
    print("  2. 趋势跟踪策略 - 捕捉强势股持续上涨")
    print("  3. 均值回归策略 - 超买超卖反转交易")

    print("\n权重方法:")
    print("  - equal: 等权重分配")
    print("  - performance: 按历史夏普比率加权")
    print("  - volatility: 按波动率倒数加权")
    print("  - dynamic: 基于市场状态动态调整")

    print("\n预期效果:")
    print("  - 策略多样化降低相关性")
    print("  - 不同市场环境下均有策略适用")
    print("  - 平滑收益曲线，提升夏普比率")

    print("\n后续步骤:")
    print("  1. 运行回测验证多策略表现")
    print("  2. 分析策略相关性")
    print("  3. 优化权重配置")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("多策略组合测试脚本")
    print("=" * 60)

    # 1. 测试多策略组合
    portfolio = test_multi_strategy_portfolio()

    # 2. 测试选择性启用
    portfolio2 = test_selective_strategies()

    # 3. 打印总结
    print_summary()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
