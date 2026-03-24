"""
阈值 5.5 深度优化
基于阈值 5.5 (年化 13.58%) 继续优化

测试维度:
1. 止盈：38%, 40%, 45%
2. 止损：3.5%, 4.0%
3. 移动止损触发：12%, 15%, 18%
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

def test_threshold_55_optimization():
    print("=" * 80)
    print("阈值 5.5 深度优化 - 冲击 15% 年化")
    print("=" * 80)

    data_dict = load_data(ENHANCED_STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票")
    print()

    # 测试配置 - 基于阈值 5.5 优化
    test_configs = [
        # 基准：阈值 5.5
        {'name': '基准 (阈值 5.5)', 'threshold': 5.5, 'take_profit': 0.35, 'stop_loss': 0.04, 'trailing': 0.15},
        # 测试止盈
        {'name': '止盈 38%', 'threshold': 5.5, 'take_profit': 0.38, 'stop_loss': 0.04, 'trailing': 0.15},
        {'name': '止盈 40%', 'threshold': 5.5, 'take_profit': 0.40, 'stop_loss': 0.04, 'trailing': 0.15},
        {'name': '止盈 45%', 'threshold': 5.5, 'take_profit': 0.45, 'stop_loss': 0.04, 'trailing': 0.15},
        # 测试止损
        {'name': '止损 3.5%', 'threshold': 5.5, 'take_profit': 0.35, 'stop_loss': 0.035, 'trailing': 0.15},
        # 测试移动止损
        {'name': '移动 12% 触发', 'threshold': 5.5, 'take_profit': 0.35, 'stop_loss': 0.04, 'trailing': 0.12},
        {'name': '移动 18% 触发', 'threshold': 5.5, 'take_profit': 0.35, 'stop_loss': 0.04, 'trailing': 0.18},
        # 组合优化
        {'name': '组合 A (止盈 40%+ 移动 12%)', 'threshold': 5.5, 'take_profit': 0.40, 'stop_loss': 0.04, 'trailing': 0.12},
        {'name': '组合 B (止盈 45%+ 移动 18%)', 'threshold': 5.5, 'take_profit': 0.45, 'stop_loss': 0.04, 'trailing': 0.18},
        {'name': '组合 C (止盈 40%+ 止损 3.5%)', 'threshold': 5.5, 'take_profit': 0.40, 'stop_loss': 0.035, 'trailing': 0.15},
        # 激进组合
        {'name': '激进 A (止盈 45%+ 止损 3.5%+ 移动 18%)', 'threshold': 5.5, 'take_profit': 0.45, 'stop_loss': 0.035, 'trailing': 0.18},
        {'name': '激进 B (止盈 40%+ 止损 3.5%+ 移动 15%)', 'threshold': 5.5, 'take_profit': 0.40, 'stop_loss': 0.035, 'trailing': 0.15},
    ]

    results = []

    for i, cfg in enumerate(test_configs, 1):
        print(f"[{i}/{len(test_configs)}] 测试 {cfg['name']}")

        params = OptimalStrategyParams(
            base_stop_loss=cfg['stop_loss'],
            base_take_profit=cfg['take_profit'],
            signal_threshold=cfg['threshold'],
            base_position_ratio=0.30,
            max_position_ratio=0.45,
            min_position_ratio=0.03,
            use_market_filter=True,
            market_bear_max_position=0.03,
            trailing_stop_trigger=cfg['trailing'],
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

    for idx, (_, r) in enumerate(df_sorted.iterrows(), 1):
        marker = " <-- BEST" if idx == 1 else ""
        print(f"  #{idx} {r['name']}: {r['score']:.3f}{marker}")

    # Top 3 推荐
    print("\n" + "=" * 80)
    print("Top 3 策略推荐")
    print("=" * 80)
    for idx, (_, r) in enumerate(df_sorted.head(3).iterrows(), 1):
        print(f"  #{idx} {r['name']}")
        print(f"      年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['drawdown']*100:.2f}%, 胜率={r['win_rate']*100:.1f}%")

    # 最终推荐
    best = df_sorted.iloc[0]
    print("\n" + "=" * 80)
    print("最终推荐策略")
    print("=" * 80)
    print(f"策略：{best['name']}")
    print(f"  年化：{best['annual']*100:.2f}%")
    print(f"  夏普：{best['sharpe']:.2f}")
    print(f"  回撤：{best['drawdown']*100:.2f}%")
    print(f"  胜率：{best['win_rate']*100:.1f}%")

    # 目标对比
    print("\n" + "=" * 80)
    print("目标对比 (目标：年化 15%, 夏普 1.0, 胜率 55%, 回撤<15%)")
    print("=" * 80)
    status = []
    if best['annual'] >= 0.15:
        status.append("OK_ANNUAL")
    if best['sharpe'] >= 1.0:
        status.append("OK_SHARPE")
    if best['win_rate'] >= 0.55:
        status.append("OK_WINRATE")
    if best['drawdown'] <= 0.15:
        status.append("OK_DRAWDOWN")
    status_str = ", ".join(status) if status else "NOT_HIT"
    print(f"达成目标：{status_str}")

    gap_annual = 0.15 - best['annual']
    gap_sharpe = 1.0 - best['sharpe']
    gap_winrate = 0.55 - best['win_rate']
    print(f"\n差距分析:")
    print(f"  年化收益差距：{gap_annual*100:.2f}% (需提升 {gap_annual/best['annual']*100:.1f}%)")
    print(f"  夏普比率差距：{gap_sharpe:.2f} (需提升 {gap_sharpe/best['sharpe']*100:.1f}%)")
    print(f"  胜率差距：{gap_winrate*100:.1f}% (需提升 {gap_winrate/best['win_rate']*100:.1f}%)")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_threshold_55_optimization()
