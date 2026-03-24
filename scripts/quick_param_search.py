"""
简单参数搜索脚本
测试 optimal_strategy 在不同止损止盈组合下的表现

使用方法:
    python scripts/quick_param_search.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer
from src.data_collector.data_manager import data_manager
from config.settings import EXTENDED_STOCK_POOL

# 参数网格
STOP_LOSS_LIST = [0.05, 0.06, 0.07, 0.08]
TAKE_PROFIT_LIST = [0.15, 0.20, 0.25, 0.30]
THRESHOLD_LIST = [4.0, 4.5, 5.0]

# 回测配置
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
    # 创建策略
    params = OptimalStrategyParams(
        base_stop_loss=sl,
        base_take_profit=tp,
        signal_threshold=thr,
    )
    strategy = OptimalStrategy(name=f"opt_{sl}_{tp}", params=params)

    # 加载数据
    data_dict = load_data(STOCKS, START_DATE, END_DATE)

    # 运行回测
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)
    result = engine.run(data_dict)

    # 绩效分析
    analyzer = PerformanceAnalyzer()
    report = analyzer.analyze(result)

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
    print("参数搜索 - Optimal Strategy")
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

    # 显示 Top 10
    import pandas as pd
    df = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("Top 10 - 按年化收益排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'annual_return').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    print("\n" + "=" * 80)
    print("Top 10 - 按夏普比率排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'sharpe').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    print("\n" + "=" * 80)
    print("Top 10 - 按最大回撤排序")
    print("=" * 80)
    for _, r in df.nsmallest(10, 'max_drawdown').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    # 保存结果
    df.to_csv('data/cache/param_search_result.csv', index=False)
    print(f"\n结果已保存至：data/cache/param_search_result.csv")


if __name__ == "__main__":
    main()
