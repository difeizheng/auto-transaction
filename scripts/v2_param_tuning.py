"""
市场时机 v2 参数微调优化
在 v2 基础上测试关键参数的敏感性

测试维度:
1. 信号阈值：4.8, 5.0, 5.2, 5.5
2. 止盈：35%, 40%, 45%
3. 牛市仓位：35%, 40%, 45%
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

ENHANCED_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
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

def test_v2_optimization():
    print("=" * 80)
    print("市场时机 v2 参数微调优化")
    print("=" * 80)

    data_dict = load_data(ENHANCED_STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票")
    print()

    # 测试配置
    test_configs = [
        # 基准 v2
        {'name': 'v2 基准', 'threshold': 5.0, 'take_profit': 0.40, 'max_pos': 0.45},
        # 测试信号阈值
        {'name': 'v2 阈值 4.8', 'threshold': 4.8, 'take_profit': 0.40, 'max_pos': 0.45},
        {'name': 'v2 阈值 5.2', 'threshold': 5.2, 'take_profit': 0.40, 'max_pos': 0.45},
        {'name': 'v2 阈值 5.5', 'threshold': 5.5, 'take_profit': 0.40, 'max_pos': 0.45},
        # 测试止盈
        {'name': 'v2 止盈 35%', 'threshold': 5.0, 'take_profit': 0.35, 'max_pos': 0.45},
        {'name': 'v2 止盈 45%', 'threshold': 5.0, 'take_profit': 0.45, 'max_pos': 0.45},
        # 测试牛市仓位
        {'name': 'v2 牛市 35%', 'threshold': 5.0, 'take_profit': 0.40, 'max_pos': 0.35},
        {'name': 'v2 牛市 40%', 'threshold': 5.0, 'take_profit': 0.40, 'max_pos': 0.40},
        # 组合优化
        {'name': 'v2 组合 A', 'threshold': 5.2, 'take_profit': 0.35, 'max_pos': 0.40},
        {'name': 'v2 组合 B', 'threshold': 4.8, 'take_profit': 0.45, 'max_pos': 0.40},
        {'name': 'v2 组合 C', 'threshold': 5.0, 'take_profit': 0.42, 'max_pos': 0.42},
    ]

    results = []

    for i, cfg in enumerate(test_configs, 1):
        print(f"[{i}/{len(test_configs)}] 测试 {cfg['name']}")

        params = OptimalStrategyParams(
            base_stop_loss=0.04,
            base_take_profit=cfg['take_profit'],
            signal_threshold=cfg['threshold'],
            base_position_ratio=0.30,
            max_position_ratio=cfg['max_pos'],
            min_position_ratio=0.03,
            use_market_filter=True,
            market_bear_max_position=0.03,
            trailing_stop_trigger=0.12,
            trailing_stop_ratio=0.06,
            time_stop_days=10,
            time_stop_profit_threshold=0.05,
        )

        strategy = OptimalStrategy(name=cfg['name'], params=params)
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        results.append({
            'name': cfg['name'],
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

    for _, r in df_sorted.iterrows():
        marker = " <-- BEST" if r['name'] == best_annual['name'] else ""
        print(f"  {r['name']}: {r['score']:.3f}{marker}")

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
    print("测试完成")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_v2_optimization()
