"""
策略对比测试 - 基准 vs v4.0 vs v5.0
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.strategy.breakout_strategy_v5 import create_breakout_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

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

def compare_strategies():
    print("=" * 80)
    print("策略对比测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    results = []

    # === 1. 基准策略 ===
    print("[1/3] 基准策略 (SL=4%, TP=30%, Thr=4.5)")
    strategy1 = create_optimal_strategy(stop_loss=0.04, take_profit=0.30, signal_threshold=4.5)
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_dict)
    results.append({
        'name': '基准策略',
        'annual': result1.annual_return,
        'sharpe': result1.sharpe_ratio,
        'drawdown': result1.max_drawdown,
        'win_rate': result1.win_rate,
        'profit_factor': result1.profit_factor,
        'total_trades': result1.total_trades
    })
    print(f"年化={result1.annual_return*100:.2f}%, 夏普={result1.sharpe_ratio:.2f}, "
          f"回撤={result1.max_drawdown*100:.2f}%, 胜率={result1.win_rate*100:.1f}%")
    print()

    # === 2. v4.0 动态仓位 ===
    print("[2/3] v4.0 动态仓位 (SL=4%, TP=35%, Thr=5.0, 动态仓位)")
    from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
    params2 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,
        signal_threshold=5.0,
        base_position_ratio=0.25,
        max_position_ratio=0.35,
        min_position_ratio=0.05,
        use_market_filter=True,
        market_bear_max_position=0.03,
        trailing_stop_trigger=0.10,
        trailing_stop_ratio=0.05,
        time_stop_days=8,
        time_stop_profit_threshold=0.03,
    )
    strategy2 = OptimalStrategy(name="v4_dynamic", params=params2)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_dict)
    results.append({
        'name': 'v4.0 动态仓位',
        'annual': result2.annual_return,
        'sharpe': result2.sharpe_ratio,
        'drawdown': result2.max_drawdown,
        'win_rate': result2.win_rate,
        'profit_factor': result2.profit_factor,
        'total_trades': result2.total_trades
    })
    print(f"年化={result2.annual_return*100:.2f}%, 夏普={result2.sharpe_ratio:.2f}, "
          f"回撤={result2.max_drawdown*100:.2f}%, 胜率={result2.win_rate*100:.1f}%")
    print()

    # === 3. v5.0 突破策略 ===
    print("[3/3] v5.0 突破策略 (SL=3%, TP=50%, 强势股)")
    strategy3 = create_breakout_strategy()
    engine3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine3.set_strategy(strategy3)
    result3 = engine3.run(data_dict)
    results.append({
        'name': 'v5.0 突破',
        'annual': result3.annual_return,
        'sharpe': result3.sharpe_ratio,
        'drawdown': result3.max_drawdown,
        'win_rate': result3.win_rate,
        'profit_factor': result3.profit_factor,
        'total_trades': result3.total_trades
    })
    print(f"年化={result3.annual_return*100:.2f}%, 夏普={result3.sharpe_ratio:.2f}, "
          f"回撤={result3.max_drawdown*100:.2f}%, 胜率={result3.win_rate*100:.1f}%")
    print()

    # === 对比总结 ===
    print("=" * 80)
    print("对比总结")
    print("=" * 80)
    import pandas as pd
    df = pd.DataFrame(results)
    print(df.to_string(index=False))

    # 找出最优
    best_sharpe = df.loc[df['sharpe'].idxmax()]
    best_annual = df.loc[df['annual'].idxmax()]
    best_winrate = df.loc[df['win_rate'].idxmax()]
    best_drawdown = df.loc[df['drawdown'].idxmin()]

    print(f"\n[HIGHEST] 最高夏普：{best_sharpe['name']} (夏普={best_sharpe['sharpe']:.2f})")
    print(f"[HIGHEST] 最高年化：{best_annual['name']} (年化={best_annual['annual']*100:.2f}%)")
    print(f"[HIGHEST] 最高胜率：{best_winrate['name']} (胜率={best_winrate['win_rate']*100:.1f}%)")
    print(f"[LOWEST] 最小回撤：{best_drawdown['name']} (回撤={best_drawdown['drawdown']*100:.1f}%)")

    # 目标对比
    print("\n" + "=" * 80)
    print("目标对比 (目标：年化 15%, 夏普 1.0, 胜率 55%, 回撤<15%)")
    print("=" * 80)
    for _, r in df.iterrows():
        status = []
        if r['annual'] >= 0.15:
            status.append("OK_ANNUAL")
        if r['sharpe'] >= 1.0:
            status.append("OK_SHARPE")
        if r['win_rate'] >= 0.55:
            status.append("OK_WINRATE")
        if r['drawdown'] <= 0.15:
            status.append("OK_DRAWDOWN")
        status_str = ", ".join(status) if status else "NOT_HIT"
        print(f"{r['name']}: {status_str}")

    print("\n" + "=" * 80)
    print("结论：当前策略无法通过参数优化突破 15% 年化目标")
    print("需要更深层次的策略改进或股票池优化")
    print("=" * 80)

    return results

if __name__ == "__main__":
    compare_strategies()
