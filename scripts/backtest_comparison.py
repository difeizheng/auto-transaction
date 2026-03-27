"""
回测结果对比脚本
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from src.data_collector.data_manager import data_manager
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer


def run_comparison_backtest():
    """运行简化版对比回测"""
    print("=" * 70)
    print("策略优化回测对比 v4.0")
    print("=" * 70)

    # 使用预设股票池
    stock_pool = [
        '000001.SZ', '000002.SZ', '000004.SZ', '000006.SZ', '000007.SZ',
        '000008.SZ', '000009.SZ', '000010.SZ', '000011.SZ', '000012.SZ'
    ]

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    print(f"\n回测区间：{start_date} - {end_date}")
    print(f"股票池：{len(stock_pool)} 只股票")
    print(f"初始资金：100,000 元\n")

    # 加载数据
    print("加载数据...")
    market_data = {}
    for ts_code in stock_pool:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            market_data[ts_code] = df

    if not market_data:
        print("错误：无法获取行情数据")
        return

    # 策略配置对比
    configs = [
        {
            'name': '基础策略 (v1.0)',
            'type': 'optimal',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=False,
                use_win_rate_optimization=False,
                signal_threshold=5.0,
            )
        },
        {
            'name': '夏普优化 (v3.0)',
            'type': 'optimal',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=True,
                use_win_rate_optimization=False,
                signal_threshold=5.5,
                max_volatility_threshold=0.04,
                min_stability_threshold=0.6,
            )
        },
        {
            'name': '胜率优化 (v4.0)',
            'type': 'optimal',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=True,
                use_win_rate_optimization=True,
                signal_threshold=6.0,
            )
        },
        {
            'name': '多策略组合 (v4.0)',
            'type': 'multi'
        }
    ]

    results = []

    for config in configs:
        print(f"\n回测：{config['name']} ...")

        try:
            # 创建策略
            if config['type'] == 'multi':
                strategy = create_multi_strategy_portfolio(
                    enable_optimal=True,
                    enable_trend=True,
                    enable_mean_reversion=True,
                    weight_method='equal'
                )
            else:
                strategy = OptimalStrategy(
                    name=config['name'],
                    params=config['params']
                )

            # 回测引擎
            engine = BacktestEngine(
                initial_capital=100000,
                commission_rate=0.0003,
                stamp_tax_rate=0.001,
                slippage_rate=0.001,
                max_position_ratio=0.8
            )
            engine.set_strategy(strategy)

            # 运行回测
            data_dict = engine.load_data(
                ts_codes=list(market_data.keys()),
                start_date=start_date,
                end_date=end_date
            )
            result = engine.run(data_dict)

            # 计算指标
            analyzer = PerformanceAnalyzer()
            metrics_obj = analyzer.analyze(result)

            # 提取指标
            metrics = {
                'total_return': metrics_obj.total_return,
                'annual_return': metrics_obj.annual_return,
                'sharpe': metrics_obj.sharpe_ratio,
                'win_rate': metrics_obj.win_rate,
                'max_drawdown': metrics_obj.max_drawdown,
                'total_trades': metrics_obj.total_trades,
            }

            results.append({
                'name': config['name'],
                'total_return': metrics['total_return'] * 100,
                'annual_return': metrics['annual_return'] * 100,
                'sharpe': metrics['sharpe'],
                'win_rate': metrics['win_rate'] * 100,
                'max_drawdown': metrics['max_drawdown'] * 100,
                'total_trades': metrics['total_trades']
            })

            print(f"  总收益：{metrics.get('total_return', 0)*100:+.2f}%")
            print(f"  年化收益：{metrics.get('annual_return', 0)*100:+.2f}%")
            print(f"  夏普比率：{metrics.get('sharpe', 0):.3f}")
            print(f"  胜率：{metrics.get('win_rate', 0)*100:.1f}%")
            print(f"  最大回撤：{metrics.get('max_drawdown', 0)*100:.2f}%")

        except Exception as e:
            print(f"  回测失败：{e}")
            results.append({
                'name': config['name'],
                'error': str(e)
            })

    # 打印对比表
    print("\n" + "=" * 70)
    print("策略对比结果")
    print("=" * 70)
    print(f"{'策略名称':<20} {'总收益':>10} {'年化':>10} {'夏普':>8} {'胜率':>8} {'回撤':>10} {'交易次数':>10}")
    print("-" * 70)

    for r in results:
        if 'error' in r:
            print(f"{r['name']:<20} {'失败':>10}")
        else:
            print(f"{r['name']:<20} {r['total_return']:>+9.2f}% {r['annual_return']:>+9.2f}% "
                  f"{r['sharpe']:>8.3f} {r['win_rate']:>7.1f}% {r['max_drawdown']:>9.2f}% "
                  f"{r['total_trades']:>10}")

    print("=" * 70)

    # 目标对比
    print("\n目标完成度")
    print("-" * 70)
    print("夏普比率目标：0.63 -> 1.0 (提升 59%)")
    print("胜率目标：51.4% -> 55% (提升 7%)")

    if results:
        base_sharpe = next((r['sharpe'] for r in results if 'v1.0' in r['name'] and 'error' not in r), None)
        best_sharpe = max((r['sharpe'] for r in results if 'error' not in r), default=0)
        base_win = next((r['win_rate'] for r in results if 'v1.0' in r['name'] and 'error' not in r), None)
        best_win = max((r['win_rate'] for r in results if 'error' not in r), default=0)

        if base_sharpe:
            print(f"\n夏普比率：基准 {base_sharpe:.3f} -> 最佳 {best_sharpe:.3f} "
                  f"({((best_sharpe-base_sharpe)/abs(base_sharpe)*100 if base_sharpe else 0):+.1f}%)")
        if base_win:
            print(f"胜率：基准 {base_win:.1f}% -> 最佳 {best_win:.1f}% "
                  f"({best_win-base_win:+.1f}%)")

    print("\n回测完成!")


if __name__ == "__main__":
    run_comparison_backtest()
