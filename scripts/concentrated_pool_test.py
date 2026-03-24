"""
精简股票池测试 - 聚焦龙头股
只用表现最强的股票，提高资金效率

基于单只股票回测数据:
- 000063.SZ: 年化 3.8%, 夏普 0.52, 盈亏比 4.48 (最强)
- 000014.SZ: 年化 2.4%, 夏普 0.25, 盈亏比 2.07
- 000078.SZ: 年化 2.0%, 夏普 0.22, 盈亏比 1.64
- 000039.SZ: 年化 1.9%, 夏普 0.23, 盈亏比 1.83
- 000001.SZ: 年化 0.7%, 夏普 0.22, 盈亏比 inf (交易少)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 不同精简程度的股票池
TOP3_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ']
TOP2_STOCKS = ['000063.SZ', '000014.SZ']
TOP4_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ']
CURRENT_BEST = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']

START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

# 最优策略参数 (移动 15% 触发)
BEST_PARAMS = OptimalStrategyParams(
    base_stop_loss=0.04,
    base_take_profit=0.35,
    signal_threshold=5.0,
    base_position_ratio=0.30,
    max_position_ratio=0.45,
    min_position_ratio=0.03,
    use_market_filter=True,
    market_bear_max_position=0.03,
    trailing_stop_trigger=0.15,
    trailing_stop_ratio=0.06,
    time_stop_days=10,
    time_stop_profit_threshold=0.05,
)

def load_data(stocks, start_date, end_date):
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict

def test_concentrated_pool():
    print("=" * 80)
    print("精简股票池测试 - 聚焦龙头股")
    print("=" * 80)

    test_configs = [
        {'name': 'Top 2 (000063+000014)', 'stocks': TOP2_STOCKS},
        {'name': 'Top 3 (000063+000014+000078)', 'stocks': TOP3_STOCKS},
        {'name': 'Top 4 ( +000039)', 'stocks': TOP4_STOCKS},
        {'name': '当前最优 (5 只)', 'stocks': CURRENT_BEST},
    ]

    results = []

    for i, cfg in enumerate(test_configs, 1):
        print(f"\n[{i}/{len(test_configs)}] 测试 {cfg['name']}")
        print(f"  股票：{cfg['stocks']}")

        data_dict = load_data(cfg['stocks'], START_DATE, END_DATE)
        if len(data_dict) == 0:
            print(f"  跳过：无数据")
            continue

        strategy = OptimalStrategy(name=cfg['name'], params=BEST_PARAMS)
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        results.append({
            'name': cfg['name'],
            'stocks': len(cfg['stocks']),
            'annual': result.annual_return,
            'sharpe': result.sharpe_ratio,
            'drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'total_trades': result.total_trades
        })

        print(f"  年化={result.annual_return*100:.2f}%, 夏普={result.sharpe_ratio:.2f}, "
              f"回撤={result.max_drawdown*100:.2f}%, 胜率={result.win_rate*100:.1f}%, "
              f"交易={result.total_trades}笔")

    # 对比总结
    print("\n" + "=" * 80)
    print("对比总结")
    print("=" * 80)
    import pandas as pd
    df = pd.DataFrame(results)
    print(df.to_string(index=False))

    # 找出最优
    best_annual = df.loc[df['annual'].idxmax()]
    best_sharpe = df.loc[df['sharpe'].idxmax()]
    best_drawdown = df.loc[df['drawdown'].idxmin()]
    best_winrate = df.loc[df['win_rate'].idxmax()]

    print(f"\n[HIGHEST] 最高年化：{best_annual['name']} ({best_annual['annual']*100:.2f}%)")
    print(f"[HIGHEST] 最高夏普：{best_sharpe['name']} ({best_sharpe['sharpe']:.2f})")
    print(f"[LOWEST] 最小回撤：{best_drawdown['name']} ({best_drawdown['drawdown']*100:.1f}%)")
    print(f"[HIGHEST] 最高胜率：{best_winrate['name']} ({best_winrate['win_rate']*100:.1f}%)")

    # 综合评分
    print("\n" + "=" * 80)
    print("综合评分 (Sharpe*0.4 + Annual*0.3 + (WinRate-0.45)*0.2 + (ProfitFactor-1.5)*0.1)")
    print("=" * 80)
    df['score'] = (df['sharpe'] * 0.4 +
                   df['annual'] * 0.3 +
                   (df['win_rate'] - 0.45) * 0.2 +
                   (df['profit_factor'] - 1.5) * 0.1)
    df_sorted = df.sort_values('score', ascending=False)

    for idx, (_, r) in enumerate(df_sorted.iterrows(), 1):
        marker = " <-- BEST" if idx == 1 else ""
        print(f"  #{idx} {r['name']}: {r['score']:.3f}{marker}")

    # 集中度分析
    print("\n" + "=" * 80)
    print("集中度分析")
    print("=" * 80)
    for _, r in df.iterrows():
        print(f"{r['name']} ({r['stocks']}只股票):")
        print(f"  年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, 胜率={r['win_rate']*100:.1f}%")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_concentrated_pool()
