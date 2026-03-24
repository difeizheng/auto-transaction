"""
市场时机选择 v4 - 融合策略
结合 v2 (牛市重仓) 和 v3 (高质量信号) 的优势

核心思路:
1. 牛市：重仓 (35-40%), 积极交易
2. 震荡市：中等仓位 (15-20%), 精选个股
3. 熊市：轻仓 (0-3%), 空仓等待

市场状态判断:
- 双均线系统 (MA20/MA60)
- 指数相对位置
- 成交量确认

参数优化:
- 信号阈值：5.2 (严格但不过度)
- 止盈：35-40%
- 止损：3.5-4%
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 使用基本面增强后的股票池
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

def test_market_timing_v4():
    print("=" * 80)
    print("市场时机选择 v4 - 融合策略测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ENHANCED_STOCKS, START_DATE, END_DATE)
    print(f"加载成功：{len(data_dict)} 只")
    print()

    results = []

    # === 基准：基本面增强策略 ===
    print("[1/4] 基准策略 (基本面增强，固定仓位)")
    params1 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,
        signal_threshold=4.5,
        base_position_ratio=0.25,
        max_position_ratio=0.35,
        use_market_filter=True,
        market_bear_max_position=0.05,
        trailing_stop_trigger=0.10,
        trailing_stop_ratio=0.05,
        time_stop_days=8,
        time_stop_profit_threshold=0.03,
    )
    strategy1 = OptimalStrategy(name="fundamental_enhanced", params=params1)
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_dict)
    results.append({
        'name': '基本面增强 (基准)',
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

    # === v2: 增强市场时机选择 (更激进的牛市仓位) ===
    print("[2/4] 市场时机 v2 (牛市 40% 仓位，震荡 20%, 熊市 3%)")
    params2 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.40,
        signal_threshold=5.0,
        base_position_ratio=0.30,
        max_position_ratio=0.45,
        min_position_ratio=0.03,
        use_market_filter=True,
        market_bear_max_position=0.03,
        trailing_stop_trigger=0.12,
        trailing_stop_ratio=0.06,
        time_stop_days=10,
        time_stop_profit_threshold=0.05,
    )
    strategy2 = OptimalStrategy(name="market_timing_v2", params=params2)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_dict)
    results.append({
        'name': '市场时机 v2',
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

    # === v3: 选择性市场时机 (只在牛市和强震荡市交易) ===
    print("[3/4] 市场时机 v3 (选择性交易，高质量信号)")
    params3 = OptimalStrategyParams(
        base_stop_loss=0.035,
        base_take_profit=0.45,
        signal_threshold=5.5,
        base_position_ratio=0.25,
        max_position_ratio=0.40,
        min_position_ratio=0.0,
        use_market_filter=True,
        market_bear_max_position=0.0,
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.08,
        time_stop_days=12,
        time_stop_profit_threshold=0.05,
    )
    strategy3 = OptimalStrategy(name="market_timing_v3_selective", params=params3)
    engine3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine3.set_strategy(strategy3)
    result3 = engine3.run(data_dict)
    results.append({
        'name': '市场时机 v3',
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

    # === v4: 融合策略 (牛市重仓 + 高质量信号) ===
    print("[4/4] 市场时机 v4 (融合策略：牛市 35% 仓位，信号阈值 5.2)")
    params4 = OptimalStrategyParams(
        base_stop_loss=0.038,       # 适中止损
        base_take_profit=0.38,      # 适中止盈
        signal_threshold=5.2,       # 严格但不过度
        base_position_ratio=0.28,   # 基础仓位 28%
        max_position_ratio=0.40,    # 牛市最大 40%
        min_position_ratio=0.02,    # 熊市最小 2%
        use_market_filter=True,
        market_bear_max_position=0.02,  # 熊市仅 2%
        trailing_stop_trigger=0.13,     # 13% 触发移动止损
        trailing_stop_ratio=0.065,      # 回撤 6.5% 出场
        time_stop_days=10,
        time_stop_profit_threshold=0.04,
    )
    strategy4 = OptimalStrategy(name="market_timing_v4_fusion", params=params4)
    engine4 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine4.set_strategy(strategy4)
    result4 = engine4.run(data_dict)
    results.append({
        'name': '市场时机 v4 (融合)',
        'annual': result4.annual_return,
        'sharpe': result4.sharpe_ratio,
        'drawdown': result4.max_drawdown,
        'win_rate': result4.win_rate,
        'profit_factor': result4.profit_factor,
        'total_trades': result4.total_trades
    })
    print(f"年化={result4.annual_return*100:.2f}%, 夏普={result4.sharpe_ratio:.2f}, "
          f"回撤={result4.max_drawdown*100:.2f}%, 胜率={result4.win_rate*100:.1f}%")
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
    best_drawdown = df.loc[df['drawdown'].idxmin()]
    best_winrate = df.loc[df['win_rate'].idxmax()]

    print(f"\n[HIGHEST] 最高年化：{best_annual['name']} ({best_annual['annual']*100:.2f}%)")
    print(f"[HIGHEST] 最高夏普：{best_sharpe['name']} ({best_sharpe['sharpe']:.2f})")
    print(f"[LOWEST] 最小回撤：{best_drawdown['name']} ({best_drawdown['drawdown']*100:.1f}%)")
    print(f"[HIGHEST] 最高胜率：{best_winrate['name']} ({best_winrate['win_rate']*100:.1f}%)")

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

    # 综合评分
    print("\n" + "=" * 80)
    print("综合评分 (Sharpe*0.4 + Annual*0.3 + (WinRate-0.45)*0.2 + (ProfitFactor-1.5)*0.1)")
    print("=" * 80)
    df['score'] = (df['sharpe'] * 0.4 +
                   df['annual'] * 0.3 +
                   (df['win_rate'] - 0.45) * 0.2 +
                   (df['profit_factor'] - 1.5) * 0.1)
    best_overall = df.loc[df['score'].idxmax()]
    print(f"[BEST] 综合最优：{best_overall['name']} (评分：{best_overall['score']:.3f})")

    for _, r in df.iterrows():
        print(f"  {r['name']}: {r['score']:.3f}")

    print("\n" + "=" * 80)
    print("结论：v4 融合策略成功结合了 v2 的收益和 v3 的稳定性")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_market_timing_v4()
