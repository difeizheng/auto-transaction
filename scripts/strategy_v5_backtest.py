"""
策略 v5.0 回测对比测试脚本
测试不同优化策略的表现

测试组:
1. v4.0 基准 (牛市 55%)
2. v5.0 夏普增强
3. v5.0 胜率增强
4. v5.0 基本面增强
5. v5.0 综合优化
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.engine import BacktestEngine
from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio
from config.logging_config import strategy_logger


def format_metrics(name: str, metrics: dict) -> str:
    """格式化指标输出"""
    return (
        f"{name:<18} "
        f"{metrics.get('annual_return', 0)*100:>8.2f}% "
        f"{metrics.get('sharpe_ratio', 0):>8.2f} "
        f"{metrics.get('max_drawdown', 0)*100:>8.2f}% "
        f"{metrics.get('win_rate', 0)*100:>7.2f}% "
        f"{metrics.get('profit_factor', 0):>8.2f} "
        f"{metrics.get('total_trades', 0):>6}"
    )


def run_single_backtest(strategy_name: str, strategy, stock_pool: list,
                        start_date: str, end_date: str, initial_capital: float) -> dict:
    """运行单次回测"""
    print(f"\n运行回测：{strategy_name}")
    print("-" * 70)

    try:
        from src.backtest.engine import BacktestEngine
        from src.backtest.performance import PerformanceAnalyzer
        from src.data_collector.data_manager import data_manager

        # 加载数据
        data_dict = {}
        for ts_code in stock_pool:
            df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
            if not df.empty:
                data_dict[ts_code] = df

        if not data_dict:
            print(f"  错误：无法加载数据")
            return {
                'name': strategy_name,
                'annual_return': 0,
                'sharpe': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_trades': 0,
                'total_return': 0,
                'error': '无法加载数据',
            }

        # 运行回测
        engine = BacktestEngine(initial_capital=initial_capital)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        # 绩效分析
        analyzer = PerformanceAnalyzer()
        report = analyzer.generate_report(result)

        metrics = {
            'annual_return': result.annual_return,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'total_trades': result.total_trades,
            'total_return': result.total_return,
        }

        print(f"  年化收益：{metrics['annual_return']*100:.2f}%")
        print(f"  夏普比率：{metrics['sharpe_ratio']:.2f}")
        print(f"  最大回撤：{metrics['max_drawdown']*100:.2f}%")
        print(f"  胜率：{metrics['win_rate']*100:.2f}%")
        print(f"  盈亏比：{metrics['profit_factor']:.2f}")
        print(f"  交易次数：{metrics['total_trades']}")

        return {
            'name': strategy_name,
            'annual_return': metrics['annual_return'],
            'sharpe': metrics['sharpe_ratio'],
            'max_drawdown': metrics['max_drawdown'],
            'win_rate': metrics['win_rate'],
            'profit_factor': metrics['profit_factor'],
            'total_trades': metrics['total_trades'],
            'total_return': metrics['total_return'],
        }

    except Exception as e:
        print(f"  回测失败：{e}")
        import traceback
        traceback.print_exc()
        return {
            'name': strategy_name,
            'annual_return': 0,
            'sharpe': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_trades': 0,
            'total_return': 0,
            'error': str(e),
        }


def run_v5_comparison_test():
    """
    运行 v5.0 策略对比测试
    """
    print("=" * 80)
    print("策略 v5.0 回测对比测试")
    print("=" * 80)

    # 回测配置
    start_date = "20240324"
    end_date = "20260323"
    initial_capital = 1000000
    stock_pool = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']

    results = []

    # ========== 测试 1: v4.0 基准 ==========
    params_v4 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,
        signal_threshold=5.5,
        base_position_ratio=0.35,
        max_position_ratio=0.55,
        market_bear_max_position=0.02,
        use_sharpe_optimization=True,
        use_win_rate_optimization=True,
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.06,
    )
    strategy_v4 = create_optimal_strategy(
        stop_loss=params_v4.base_stop_loss,
        take_profit=params_v4.base_take_profit,
        signal_threshold=params_v4.signal_threshold,
        mode='aggressive'
    )
    strategy_v4.params = params_v4

    result_v4 = run_single_backtest(
        "v4.0 基准 (牛市 55%)", strategy_v4, stock_pool,
        start_date, end_date, initial_capital
    )
    results.append(result_v4)

    # ========== 测试 2: v5.0 夏普增强 ==========
    params_v5_sharpe = OptimalStrategyParams(
        base_stop_loss=0.035,  # 收紧止损
        base_take_profit=0.40,  # 放宽止盈
        signal_threshold=5.2,  # 降低阈值
        base_position_ratio=0.35,
        max_position_ratio=0.55,
        market_bear_max_position=0.02,
        use_sharpe_optimization=True,
        use_win_rate_optimization=True,
        use_enhanced_sharpe=True,
        max_volatility_threshold=0.035,  # 收紧波动率阈值
        min_stability_threshold=0.65,    # 提高稳定性要求
        profit_lock_trigger=0.10,        # 提高分级止盈触发点
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.05,
    )
    strategy_v5_sharpe = create_optimal_strategy(
        stop_loss=params_v5_sharpe.base_stop_loss,
        take_profit=params_v5_sharpe.base_take_profit,
        signal_threshold=params_v5_sharpe.signal_threshold,
        mode='aggressive'
    )
    strategy_v5_sharpe.params = params_v5_sharpe

    result_sharpe = run_single_backtest(
        "v5.0 夏普增强", strategy_v5_sharpe, stock_pool,
        start_date, end_date, initial_capital
    )
    results.append(result_sharpe)

    # ========== 测试 3: v5.0 胜率增强 ==========
    params_v5_winrate = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,
        signal_threshold=5.0,  # 进一步降低阈值
        base_position_ratio=0.35,
        max_position_ratio=0.55,
        market_bear_max_position=0.02,
        use_sharpe_optimization=True,
        use_win_rate_optimization=True,
        use_enhanced_win_rate=True,
        min_momentum_score=0.02,       # 降低动量阈值
        min_stock_strength_rank=0.35,  # 放宽强度要求
        min_signal_confidence=0.55,    # 降低置信度要求
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.06,
    )
    strategy_v5_winrate = create_optimal_strategy(
        stop_loss=params_v5_winrate.base_stop_loss,
        take_profit=params_v5_winrate.base_take_profit,
        signal_threshold=params_v5_winrate.signal_threshold,
        mode='aggressive'
    )
    strategy_v5_winrate.params = params_v5_winrate

    result_winrate = run_single_backtest(
        "v5.0 胜率增强", strategy_v5_winrate, stock_pool,
        start_date, end_date, initial_capital
    )
    results.append(result_winrate)

    # ========== 测试 4: v5.0 综合优化 ==========
    params_v5_full = OptimalStrategyParams(
        base_stop_loss=0.035,
        base_take_profit=0.40,
        signal_threshold=5.2,
        base_position_ratio=0.35,
        max_position_ratio=0.55,
        market_bear_max_position=0.02,
        use_sharpe_optimization=True,
        use_win_rate_optimization=True,
        use_enhanced_sharpe=True,
        use_enhanced_win_rate=True,
        use_fundamental_factor=True,  # 启用基本面因子
        max_volatility_threshold=0.035,
        min_stability_threshold=0.65,
        profit_lock_trigger=0.10,
        min_momentum_score=0.02,
        min_stock_strength_rank=0.35,
        min_fundamental_score=0.5,
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.05,
    )
    strategy_v5_full = create_optimal_strategy(
        stop_loss=params_v5_full.base_stop_loss,
        take_profit=params_v5_full.base_take_profit,
        signal_threshold=params_v5_full.signal_threshold,
        mode='aggressive'
    )
    strategy_v5_full.params = params_v5_full

    result_full = run_single_backtest(
        "v5.0 综合优化", strategy_v5_full, stock_pool,
        start_date, end_date, initial_capital
    )
    results.append(result_full)

    # ========== 打印对比结果 ==========
    print("\n")
    print("=" * 80)
    print("回测结果对比")
    print("=" * 80)

    header = f"{'策略':<18} {'年化':>9} {'夏普':>8} {'回撤':>9} {'胜率':>7} {'盈亏比':>8} {'交易数':>6}"
    print(header)
    print("-" * 80)

    for r in results:
        print(f"{r['name']:<18} {r['annual_return']*100:>8.2f}% {r['sharpe']:>8.2f} "
              f"{r['max_drawdown']*100:>8.2f}% {r['win_rate']*100:>6.2f}% "
              f"{r['profit_factor']:>8.2f} {r['total_trades']:>6}")

    # 找出最优
    if results:
        best_annual = max(results, key=lambda x: x['annual_return'])
        best_sharpe = max(results, key=lambda x: x['sharpe'])
        best_winrate = max(results, key=lambda x: x['win_rate'])
        best_drawdown = min(results, key=lambda x: x['max_drawdown'])

        print("\n")
        print("最优策略:")
        print(f"  最高年化：{best_annual['name']} ({best_annual['annual_return']*100:.2f}%)")
        print(f"  最高夏普：{best_sharpe['name']} ({best_sharpe['sharpe']:.2f})")
        print(f"  最高胜率：{best_winrate['name']} ({best_winrate['win_rate']*100:.2f}%)")
        print(f"  最小回撤：{best_drawdown['name']} ({best_drawdown['max_drawdown']*100:.2f}%)")

        # 目标达成检查
        print("\n")
        print("目标达成检查 (目标：年化 15%, 夏普 1.0, 胜率 55%, 回撤<15%):")
        for r in results:
            annual_ok = r['annual_return'] >= 0.15
            sharpe_ok = r['sharpe'] >= 1.0
            winrate_ok = r['win_rate'] >= 0.55
            drawdown_ok = r['max_drawdown'] <= 0.15

            checks = [
                f"年化{'OK' if annual_ok else 'NG'}",
                f"夏普{'OK' if sharpe_ok else 'NG'}",
                f"胜率{'OK' if winrate_ok else 'NG'}",
                f"回撤{'OK' if drawdown_ok else 'NG'}",
            ]
            print(f"  {r['name']}: {', '.join(checks)}")

    return results


def run_multi_strategy_test():
    """
    测试多策略组合
    """
    print("\n")
    print("=" * 80)
    print("多策略组合测试")
    print("=" * 80)

    # 测试不同权重方法
    weight_methods = [
        ('equal', '等权重'),
        ('dynamic', '动态权重'),
    ]

    for method, method_name in weight_methods:
        print(f"\n权重方法：{method_name} ({method})")
        print("-" * 50)

        try:
            portfolio = create_multi_strategy_portfolio(
                enable_optimal=True,
                enable_trend=True,
                enable_mean_reversion=True,
                weight_method=method
            )

            weights = portfolio.get_strategy_weights()
            print(f"  策略权重:")
            for name, weight in weights.items():
                print(f"    {name}: {weight:.1%}")

        except Exception as e:
            print(f"  测试失败：{e}")

    print("\n多策略组合框架验证完成")


def print_v5_optimization_summary():
    """
    打印 v5.0 优化总结
    """
    print("\n")
    print("=" * 80)
    print("策略 v5.0 优化总结")
    print("=" * 80)

    summary = """
v5.0 核心优化措施:

1. 夏普比率优化 (目标：0.63 -> 1.0+)
   - 波动率阈值：4% -> 3.5% (更严格过滤)
   - 稳定性要求：60% -> 65% (提高趋势稳定性)
   - 分级止盈触发：8% -> 10% (延后部分止盈)
   - 新增 R 平方稳定性指标

2. 胜率优化 (目标：51.4% -> 55%+)
   - 动量阈值：0.03 -> 0.02 (降低门槛)
   - 股票强度：前 30% -> 前 35% (放宽筛选)
   - 信号置信度：0.6 -> 0.55 (降低要求)
   - 新增连续上涨天数要求

3. 基本面因子增强 (新增)
   - ROE 因子 (权重 30%)：筛选高 ROE 且稳定的股票
   - 增长因子 (权重 25%)：筛选营收和利润持续增长
   - 估值因子 (权重 20%)：PE/PB 综合评分
   - 健康因子 (权重 15%)：负债率、流动比率
   - 市值因子 (权重 10%)：大市值偏好

4. 多策略组合验证
   - 最优综合策略 + 趋势跟踪 + 均值回归
   - 等权重/动态权重两种配置
   - 策略相关性检测

参数配置更新:
- 止损：4% -> 3.5% (更紧止损)
- 止盈：35% -> 40% (更宽止盈)
- 信号阈值：5.5 -> 5.2 (适度放宽)
- 牛市仓位：55% (维持)
- 熊市仓位：2% (维持)

预期效果:
- 年化收益：15-18% (v4.0: 16.15%)
- 夏普比率：0.8-1.0+ (v4.0: 0.63)
- 胜率：53-56% (v4.0: 51.4%)
- 最大回撤：<15% (v4.0: 15.26%)
"""
    print(summary)


if __name__ == "__main__":
    print(f"回测开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 运行 v5.0 对比测试
    results = run_v5_comparison_test()

    # 测试多策略组合
    run_multi_strategy_test()

    # 打印优化总结
    print_v5_optimization_summary()

    print(f"\n回测结束时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n优化脚本执行完成")
