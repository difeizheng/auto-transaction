"""
简化版权重方法对比测试
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.data_collector.data_manager import data_manager
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer


def run_weight_comparison():
    """运行权重方法对比"""
    print("=" * 70)
    print("多策略权重方法对比测试")
    print("=" * 70)

    # 股票池 (27 只)
    stock_pool = [
        '000001.SZ', '000002.SZ', '000004.SZ', '000006.SZ', '000007.SZ',
        '000008.SZ', '000009.SZ', '000010.SZ', '000011.SZ', '000012.SZ',
        '000014.SZ', '000016.SZ', '000017.SZ', '000019.SZ', '000020.SZ',
        '000021.SZ', '000025.SZ', '000027.SZ', '000028.SZ', '000031.SZ',
        '000032.SZ', '000035.SZ', '000039.SZ', '000042.SZ', '000050.SZ',
        '000055.SZ', '000059.SZ',
    ]

    # 2 年回测
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

    print(f"\n回测周期：{start_date} - {end_date}")
    print(f"股票池：{len(stock_pool)} 只")

    # 加载数据
    print("\n加载数据...")
    market_data = {}
    for ts_code in stock_pool:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            market_data[ts_code] = df

    print(f"成功加载 {len(market_data)} 只股票\n")

    # 测试不同权重方法
    weight_methods = ['equal', 'dynamic']

    results = []

    for weight_method in weight_methods:
        print(f"测试：{weight_method} 权重...")

        try:
            strategy = create_multi_strategy_portfolio(
                enable_optimal=True,
                enable_trend=True,
                enable_mean_reversion=True,
                weight_method=weight_method
            )

            engine = BacktestEngine(
                initial_capital=100000,
                commission_rate=0.0003,
                stamp_tax_rate=0.001,
                slippage_rate=0.001,
                max_position_ratio=0.8
            )
            engine.set_strategy(strategy)

            data_dict = engine.load_data(
                ts_codes=list(market_data.keys()),
                start_date=start_date,
                end_date=end_date
            )
            result = engine.run(data_dict)

            analyzer = PerformanceAnalyzer()
            metrics = analyzer.analyze(result)

            results.append({
                'name': weight_method,
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
            print(f"  失败：{e}")
            results.append({'name': weight_method, 'error': str(e)})

    # 对比表
    print("\n" + "=" * 70)
    print("权重方法对比")
    print("=" * 70)
    print(f"{'方法':<15} {'总收益':>10} {'年化':>10} {'夏普':>8} {'胜率':>8} {'回撤':>10} {'交易':>8}")
    print("-" * 70)

    best = None
    best_sharpe = -999

    for r in results:
        if 'error' in r:
            print(f"{r['name']:<15} {'失败':>10}")
        else:
            print(f"{r['name']:<15} {r['total_return']:>+9.2f}% {r['annual_return']:>+9.2f}% "
                  f"{r['sharpe']:>8.3f} {r['win_rate']:>7.1f}% {r['max_drawdown']:>9.2f}% "
                  f"{r['total_trades']:>8}")
            if r['sharpe'] > best_sharpe:
                best_sharpe = r['sharpe']
                best = r

    print("=" * 70)

    if best:
        print(f"\n最佳方法：{best['name']}")
        print(f"  夏普比率：{best['sharpe']:.3f}")
        print(f"  年化收益：{best['annual_return']:+.2f}%")
        print(f"  胜率：{best['win_rate']:.1f}%")

    return results


if __name__ == "__main__":
    run_weight_comparison()
