"""
扩展参数搜索 - 突破年化收益瓶颈
测试更大范围的参数组合
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager
import pandas as pd
import itertools

# 配置
ORIGINAL_STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
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

def optimize_params():
    print("=" * 80)
    print("扩展参数搜索 - 突破年化收益瓶颈")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    # 扩展参数网格 - 测试更高止盈、更高阈值
    stop_loss_list = [0.03, 0.04, 0.05]  # 3%-5% 止损
    take_profit_list = [0.30, 0.35, 0.40, 0.45]  # 30%-45% 止盈 (更宽)
    threshold_list = [4.5, 5.0, 5.5, 6.0]  # 4.5-6.0 信号阈值 (更严格)

    test_cases = list(itertools.product(stop_loss_list, take_profit_list, threshold_list))
    print(f"测试组合数：{len(test_cases)}")
    print(f"测试范围：止损 3%-5%, 止盈 30%-45%, 阈值 4.5-6.0")
    print()

    results = []

    for i, (sl, tp, thr) in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] SL={sl*100:.0f}%, TP={tp*100:.0f}%, Thr={thr}", end=" ... ")

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

    # 综合评分 (夏普*0.4 + 年化*0.3 + 胜率*0.2 + 盈亏比*0.1)
    df['score'] = (
        df['sharpe'] * 0.4 +
        df['annual_return'] * 0.3 +
        (df['win_rate'] - 0.4) * 0.2 +
        (df['profit_factor'] - 1.5) * 0.1
    )

    print("\n" + "=" * 80)
    print("Top 10 - 按综合评分排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'score').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%, "
              f"盈亏比={r['profit_factor']:.2f}, 评分={r['score']:.3f}")

    # 按年化收益排序
    print("\n" + "=" * 80)
    print("Top 10 - 按年化收益排序")
    print("=" * 80)
    for _, r in df.nlargest(10, 'annual_return').iterrows():
        print(f"SL={r['stop_loss']:.0f}%, TP={r['take_profit']:.0f}%, Thr={r['threshold']} -> "
              f"年化={r['annual_return']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    # 最优参数 (综合评分)
    best = df.loc[df['score'].idxmax()]
    print("\n" + "=" * 80)
    print("最优参数组合 (综合评分)")
    print("=" * 80)
    print(f"止损：{best['stop_loss']*100:.0f}%")
    print(f"止盈：{best['take_profit']*100:.0f}%")
    print(f"信号阈值：{best['threshold']}")
    print(f"预期年化：{best['annual_return']*100:.2f}%")
    print(f"预期夏普：{best['sharpe']:.2f}")
    print(f"预期回撤：{best['max_drawdown']*100:.2f}%")
    print(f"预期胜率：{best['win_rate']*100:.1f}%")
    print(f"预期盈亏比：{best['profit_factor']:.2f}")

    # 保存结果
    df.to_csv('data/cache/extended_param_search.csv', index=False)
    print(f"\n结果已保存至：data/cache/extended_param_search.csv")

if __name__ == "__main__":
    optimize_params()
