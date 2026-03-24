"""
精简参数搜索 - 只测试最有希望的组合
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer
from src.data_collector.data_manager import data_manager

# 精简参数网格 - 基于之前测试的有希望区域
STOP_LOSS_LIST = [0.05, 0.06, 0.07]
TAKE_PROFIT_LIST = [0.15, 0.20, 0.25]
THRESHOLD_LIST = [4.0, 4.5, 5.0]

# 回测配置 - 使用 5 只股票
STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000


def load_data(stocks, start_date, end_date):
    """加载股票数据"""
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict


def run_backtest(sl, tp, thr):
    """运行单次回测"""
    params = OptimalStrategyParams(
        base_stop_loss=sl,
        base_take_profit=tp,
        signal_threshold=thr,
    )
    strategy = OptimalStrategy(name=f"opt_{sl}_{tp}", params=params)

    data_dict = load_data(STOCKS, START_DATE, END_DATE)

    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)
    result = engine.run(data_dict)

    return {
        'stop_loss': sl,
        'take_profit': tp,
        'threshold': thr,
        'total_return': result.total_return,
        'annual_return': result.annual_return,
        'sharpe': result.sharpe_ratio,
        'max_drawdown': result.max_drawdown,
        'win_rate': result.win_rate,
        'profit_loss_ratio': result.profit_factor,
        'total_trades': result.total_trades,
    }


def main():
    print("=" * 80)
    print("精简参数搜索 - Optimal Strategy")
    print("=" * 80)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print(f"测试组合数：{len(STOP_LOSS_LIST) * len(TAKE_PROFIT_LIST) * len(THRESHOLD_LIST)}")
    print()

    results = []

    for i, (sl, tp, thr) in enumerate(
        [(sl, tp, thr) for sl in STOP_LOSS_LIST for tp in TAKE_PROFIT_LIST for thr in THRESHOLD_LIST],
        1
    ):
        print(f"[{i}/{len(STOP_LOSS_LIST) * len(TAKE_PROFIT_LIST) * len(THRESHOLD_LIST)}] "
              f"SL={sl*100:.0f}%, TP={tp*100:.0f}%, Thr={thr}", end=" ... ")

        try:
            r = run_backtest(sl, tp, thr)
            results.append(r)
            print(f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
                  f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")
        except Exception as e:
            print(f"错误：{e}")

    if not results:
        print("\n没有成功结果")
        return

    import pandas as pd
    df = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("Top 5 - 按年化收益排序")
    print("=" * 80)
    for _, r in df.nlargest(5, 'annual_return').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    print("\n" + "=" * 80)
    print("Top 5 - 按夏普比率排序")
    print("=" * 80)
    for _, r in df.nlargest(5, 'sharpe').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    print("\n" + "=" * 80)
    print("Top 5 - 按最大回撤排序")
    print("=" * 80)
    for _, r in df.nsmallest(5, 'max_drawdown').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    # 保存结果
    df.to_csv('data/cache/quick_param_search.csv', index=False)
    print(f"\n结果已保存至：data/cache/quick_param_search.csv")

    # 最优参数
    best_sharpe = df.loc[df['sharpe'].idxmax()]
    print("\n" + "=" * 80)
    print("最优参数组合 (按夏普比率)")
    print("=" * 80)
    print(f"止损：{best_sharpe['stop_loss']*100:.0f}%")
    print(f"止盈：{best_sharpe['take_profit']*100:.0f}%")
    print(f"信号阈值：{best_sharpe['threshold']}")
    print(f"预期年化：{best_sharpe['annual_return']*100:.2f}%")
    print(f"预期夏普：{best_sharpe['sharpe']:.2f}")
    print(f"预期回撤：{best_sharpe['max_drawdown']*100:.2f}%")
    print(f"预期胜率：{best_sharpe['win_rate']*100:.1f}%")


if __name__ == "__main__":
    main()
