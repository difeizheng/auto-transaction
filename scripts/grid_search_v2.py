"""
参数敏感性测试 - 寻找最优参数组合
测试更广泛的参数范围
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager
import pandas as pd

# 配置
STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

def load_data(stocks, start_date, end_date):
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict

def run_grid_search():
    print("=" * 80)
    print("参数网格搜索 - Optimal Strategy v2.0")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(STOCKS, START_DATE, END_DATE)

    # 参数网格 - 更广泛的测试范围
    stop_loss_list = [0.04, 0.05, 0.06, 0.07]
    take_profit_list = [0.20, 0.25, 0.30, 0.35]
    threshold_list = [4.5, 5.0, 5.5]

    print(f"测试组合数：{len(stop_loss_list) * len(take_profit_list) * len(threshold_list)}")
    print()

    results = []
    total = len(stop_loss_list) * len(take_profit_list) * len(threshold_list)
    count = 0

    for sl in stop_loss_list:
        for tp in take_profit_list:
            for thr in threshold_list:
                count += 1
                print(f"[{count}/{total}] SL={sl*100:.0f}%, TP={tp*100:.0f}%, Thr={thr}", end=" ... ")

                strategy = create_optimal_strategy(
                    stop_loss=sl,
                    take_profit=tp,
                    signal_threshold=thr
                )

                engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
                engine.set_strategy(strategy)

                try:
                    result = engine.run(data_dict)
                    results.append({
                        'stop_loss': sl,
                        'take_profit': tp,
                        'threshold': thr,
                        'total_return': result.total_return,
                        'annual_return': result.annual_return,
                        'sharpe': result.sharpe_ratio,
                        'max_drawdown': result.max_drawdown,
                        'win_rate': result.win_rate,
                        'profit_factor': result.profit_factor,
                        'total_trades': result.total_trades,
                    })
                    print(f"年化={result.annual_return*100:.2f}%, 夏普={result.sharpe_ratio:.2f}, "
                          f"回撤={result.max_drawdown*100:.2f}%, 胜率={result.win_rate*100:.1f}%")
                except Exception as e:
                    print(f"错误：{e}")

    if not results:
        print("\n没有成功结果")
        return

    df = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("Top 10 - 按年化收益排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'annual_return').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%, 盈亏比={r['profit_factor']:.2f}")

    print("\n" + "=" * 80)
    print("Top 10 - 按夏普比率排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'sharpe').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%, 盈亏比={r['profit_factor']:.2f}")

    print("\n" + "=" * 80)
    print("Top 10 - 按胜率排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'win_rate').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%, 盈亏比={r['profit_factor']:.2f}")

    # 保存结果
    df.to_csv('data/cache/grid_search_v2.csv', index=False)
    print(f"\n结果已保存至：data/cache/grid_search_v2.csv")

    # 最优参数
    best = df.loc[df['sharpe'].idxmax()]
    print("\n" + "=" * 80)
    print("最优参数组合 (按夏普比率)")
    print("=" * 80)
    print(f"止损：{best['stop_loss']*100:.0f}%")
    print(f"止盈：{best['take_profit']:.0f}%")
    print(f"信号阈值：{best['threshold']}")
    print(f"年化：{best['annual_return']*100:.2f}%")
    print(f"夏普：{best['sharpe']:.2f}")
    print(f"回撤：{best['max_drawdown']*100:.2f}%")
    print(f"胜率：{best['win_rate']*100:.1f}%")
    print(f"盈亏比：{best['profit_factor']:.2f}")

if __name__ == "__main__":
    run_grid_search()
