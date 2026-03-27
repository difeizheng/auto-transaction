"""
策略优化回测 - 综合版
整合所有优化项：
1. 大股票池 (50 只)
2. 优化权重配置
3. 增强市场状态判断
4. 2-3 年回测周期
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.data_collector.data_manager import data_manager
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer


def run_comprehensive_backtest():
    """运行综合版回测"""
    print("=" * 70)
    print("策略优化回测 v4.0 - 综合版")
    print("整合优化：大股票池 + 优权重 + 强市场判断 + 长周期")
    print("=" * 70)

    # 1. 准备股票池 (50 只)
    print("\n[1/4] 准备股票池...")
    stock_pool = [
        '000001.SZ', '000002.SZ', '000004.SZ', '000006.SZ', '000007.SZ',
        '000008.SZ', '000009.SZ', '000010.SZ', '000011.SZ', '000012.SZ',
        '000014.SZ', '000016.SZ', '000017.SZ', '000019.SZ', '000020.SZ',
        '000021.SZ', '000022.SZ', '000024.SZ', '000025.SZ', '000027.SZ',
        '000028.SZ', '000031.SZ', '000032.SZ', '000035.SZ', '000039.SZ',
        '000042.SZ', '000046.SZ', '000050.SZ', '000055.SZ', '000059.SZ',
        '000060.SZ', '000061.SZ', '000062.SZ', '000063.SZ', '000065.SZ',
        '000066.SZ', '000069.SZ', '000070.SZ', '000078.SZ', '000088.SZ',
        '000089.SZ', '000090.SZ', '000096.SZ', '000099.SZ', '000100.SZ',
        '000157.SZ', '000158.SZ', '000166.SZ', '000338.SZ', '000415.SZ',
    ]
    print(f"  股票池：{len(stock_pool)} 只股票")

    # 2. 设置回测周期 (3 年)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=1095)).strftime("%Y%m%d")  # 3 年
    print(f"\n[2/4] 回测周期：{start_date} 至 {end_date} (3 年)")

    # 3. 加载数据
    print(f"\n[3/4] 加载行情数据...")
    market_data = {}

    batch_size = 10
    for i in range(0, min(len(stock_pool), 30), batch_size):
        batch = stock_pool[i:i+batch_size]
        print(f"  加载进度：{i}-{min(i+batch_size, len(stock_pool))}/{min(len(stock_pool), 30)}")
        for ts_code in batch:
            try:
                df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
                if not df.empty:
                    market_data[ts_code] = df
            except Exception:
                pass

    if not market_data:
        print("  错误：无法获取行情数据")
        return None

    print(f"  成功加载 {len(market_data)} 只股票数据")

    # 4. 运行回测
    print(f"\n[4/4] 运行策略回测...")
    print("=" * 70)

    # 策略配置
    strategies = [
        {
            'name': '最优策略 (v4.0)',
            'strategy': OptimalStrategy(
                name='optimal_v4',
                params=OptimalStrategyParams(
                    use_sharpe_optimization=True,
                    use_win_rate_optimization=True,
                    signal_threshold=6.0,
                )
            )
        },
        {
            'name': '多策略组合 (equal)',
            'strategy': create_multi_strategy_portfolio(
                enable_optimal=True,
                enable_trend=True,
                enable_mean_reversion=True,
                weight_method='equal'
            )
        },
        {
            'name': '多策略组合 (dynamic)',
            'strategy': create_multi_strategy_portfolio(
                enable_optimal=True,
                enable_trend=True,
                enable_mean_reversion=True,
                weight_method='dynamic'
            )
        }
    ]

    results = []

    for config in strategies:
        print(f"\n回测：{config['name']}")
        print("-" * 50)

        try:
            engine = BacktestEngine(
                initial_capital=100000,
                commission_rate=0.0003,
                stamp_tax_rate=0.001,
                slippage_rate=0.001,
                max_position_ratio=0.8
            )
            engine.set_strategy(config['strategy'])

            data_dict = engine.load_data(
                ts_codes=list(market_data.keys()),
                start_date=start_date,
                end_date=end_date
            )
            result = engine.run(data_dict)

            analyzer = PerformanceAnalyzer()
            metrics = analyzer.analyze(result)

            results.append({
                'name': config['name'],
                'total_return': metrics.total_return * 100,
                'annual_return': metrics.annual_return * 100,
                'sharpe': metrics.sharpe_ratio,
                'win_rate': metrics.win_rate * 100,
                'max_drawdown': metrics.max_drawdown * 100,
                'total_trades': metrics.total_trades,
            })

            print(f"  总收益：{metrics.total_return*100:+.2f}%")
            print(f"  年化：{metrics.annual_return*100:+.2f}%")
            print(f"  夏普：{metrics.sharpe_ratio:.3f}")
            print(f"  胜率：{metrics.win_rate*100:.1f}%")
            print(f"  回撤：{metrics.max_drawdown*100:.2f}%")

        except Exception as e:
            print(f"  回测失败：{e}")
            results.append({'name': config['name'], 'error': str(e)})

    # 对比表
    print("\n" + "=" * 70)
    print("策略对比结果")
    print("=" * 70)
    print(f"{'策略名称':<25} {'总收益':>10} {'年化':>10} {'夏普':>8} {'胜率':>8} {'回撤':>10} {'交易':>8}")
    print("-" * 70)

    best = None
    best_sharpe = -999

    for r in results:
        if 'error' in r:
            print(f"{r['name']:<25} {'失败':>10}")
        else:
            print(f"{r['name']:<25} {r['total_return']:>+9.2f}% {r['annual_return']:>+9.2f}% "
                  f"{r['sharpe']:>8.3f} {r['win_rate']:>7.1f}% {r['max_drawdown']:>9.2f}% "
                  f"{r['total_trades']:>8}")
            if r['sharpe'] > best_sharpe:
                best_sharpe = r['sharpe']
                best = r

    print("=" * 70)

    if best:
        print(f"\n最佳策略：{best['name']}")
        print(f"  夏普比率：{best['sharpe']:.3f}")
        print(f"  年化收益：{best['annual_return']:+.2f}%")
        print(f"  胜率：{best['win_rate']:.1f}%")
        print(f"  最大回撤：{best['max_drawdown']:.2f}%")

    # 目标对比
    print("\n" + "=" * 70)
    print("优化目标完成度")
    print("=" * 70)
    print("夏普比率目标：0.63 -> 1.0 (提升 59%)")
    print("胜率目标：51.4% -> 55% (提升 7%)")

    if best:
        base_sharpe = 0.63  # 基准
        base_win = 51.4  # 基准

        sharpe_improve = ((best['sharpe'] - base_sharpe) / base_sharpe) * 100 if base_sharpe > 0 else 0
        win_improve = best['win_rate'] - base_win

        print(f"\n实际达成:")
        print(f"  夏普比率：{best['sharpe']:.3f} ({sharpe_improve:+.1f}%)")
        print(f"  胜率：{best['win_rate']:.1f}% ({win_improve:+.1f}%)")

        # 目标判断
        sharpe_target = 1.0
        win_target = 55.0

        print(f"\n目标评估:")
        if best['sharpe'] >= sharpe_target:
            print(f"  [OK] 夏普比率目标达成 ({best['sharpe']:.3f} >= {sharpe_target})")
        else:
            print(f"  [ ] 夏普比率未达标 ({best['sharpe']:.3f} < {sharpe_target})")

        if best['win_rate'] >= win_target:
            print(f"  [OK] 胜率目标达成 ({best['win_rate']:.1f}% >= {win_target}%)")
        else:
            print(f"  [ ] 胜率未达标 ({best['win_rate']:.1f}% < {win_target}%)")

    print("\n回测完成!")
    return results


if __name__ == "__main__":
    run_comprehensive_backtest()
