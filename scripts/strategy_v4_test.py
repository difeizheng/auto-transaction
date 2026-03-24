"""
策略 v4.0 - 深度优化版
目标：突破年化 8% 瓶颈，朝向 15% 目标

优化方向:
1. 更严格的入场信号 - 提高胜率
2. 更智能的出场策略 - 提高盈亏比
3. 市场状态自适应 - 熊市空仓、牛市重仓
4. 动量确认增强 - 只交易强势股
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager
import pandas as pd

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

def test_v4_strategy():
    """测试 v4.0 深度优化策略"""
    print("=" * 80)
    print("策略 v4.0 - 深度优化测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    results = []

    # === 基准：原始最优策略 ===
    print("【基准】原始最优策略 (SL=4%, TP=30%, Thr=4.5)")
    strategy_base = create_optimal_strategy(stop_loss=0.04, take_profit=0.30, signal_threshold=4.5)
    engine_base = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine_base.set_strategy(strategy_base)
    result_base = engine_base.run(data_dict)
    results.append({
        'name': '基准策略',
        'annual': result_base.annual_return,
        'sharpe': result_base.sharpe_ratio,
        'drawdown': result_base.max_drawdown,
        'win_rate': result_base.win_rate,
        'profit_factor': result_base.profit_factor,
        'total_trades': result_base.total_trades
    })
    print(f"年化={result_base.annual_return*100:.2f}%, 夏普={result_base.sharpe_ratio:.2f}, "
          f"回撤={result_base.max_drawdown*100:.2f}%, 胜率={result_base.win_rate*100:.1f}%")
    print()

    # === v4.0 优化方案 1: 更严格信号 + 更高止盈 ===
    print("【v4.0-1】严格信号 + 高止盈 (SL=4%, TP=40%, Thr=5.5)")
    params1 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.40,
        signal_threshold=5.5,
        base_position_ratio=0.20,
        trailing_stop_trigger=0.12,  # 12% 触发移动止损
        trailing_stop_ratio=0.04,    # 回撤 4% 出场
        time_stop_days=10,
        time_stop_profit_threshold=0.05,
    )
    strategy_v4_1 = OptimalStrategy(name="v4_strict_high_tp", params=params1)
    engine_v4_1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine_v4_1.set_strategy(strategy_v4_1)
    result_v4_1 = engine_v4_1.run(data_dict)
    results.append({
        'name': 'v4.0-严格 + 高止盈',
        'annual': result_v4_1.annual_return,
        'sharpe': result_v4_1.sharpe_ratio,
        'drawdown': result_v4_1.max_drawdown,
        'win_rate': result_v4_1.win_rate,
        'profit_factor': result_v4_1.profit_factor,
        'total_trades': result_v4_1.total_trades
    })
    print(f"年化={result_v4_1.annual_return*100:.2f}%, 夏普={result_v4_1.sharpe_ratio:.2f}, "
          f"回撤={result_v4_1.max_drawdown*100:.2f}%, 胜率={result_v4_1.win_rate*100:.1f}%")
    print()

    # === v4.0 优化方案 2: 动态仓位 + 市场过滤增强 ===
    print("【v4.0-2】动态仓位 + 市场过滤 (牛市 30%, 震荡 15%, 熊市 5%)")
    params2 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,
        signal_threshold=5.0,
        base_position_ratio=0.25,
        max_position_ratio=0.35,
        min_position_ratio=0.05,
        use_market_filter=True,
        market_bear_max_position=0.03,  # 熊市仅 3%
        trailing_stop_trigger=0.10,
        trailing_stop_ratio=0.05,
        time_stop_days=8,
        time_stop_profit_threshold=0.03,
    )
    strategy_v4_2 = OptimalStrategy(name="v4_dynamic_pos", params=params2)
    engine_v4_2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine_v4_2.set_strategy(strategy_v4_2)
    result_v4_2 = engine_v4_2.run(data_dict)
    results.append({
        'name': 'v4.0-动态仓位',
        'annual': result_v4_2.annual_return,
        'sharpe': result_v4_2.sharpe_ratio,
        'drawdown': result_v4_2.max_drawdown,
        'win_rate': result_v4_2.win_rate,
        'profit_factor': result_v4_2.profit_factor,
        'total_trades': result_v4_2.total_trades
    })
    print(f"年化={result_v4_2.annual_return*100:.2f}%, 夏普={result_v4_2.sharpe_ratio:.2f}, "
          f"回撤={result_v4_2.max_drawdown*100:.2f}%, 胜率={result_v4_2.win_rate*100:.1f}%")
    print()

    # === v4.0 优化方案 3: 紧止损 + 移动止损增强 ===
    print("【v4.0-3】紧止损 + 移动止损 (SL=3%, TP=35%, 移动止损 8% 触发)")
    params3 = OptimalStrategyParams(
        base_stop_loss=0.03,
        base_take_profit=0.35,
        signal_threshold=5.0,
        base_position_ratio=0.20,
        trailing_stop_trigger=0.08,  # 8% 触发
        trailing_stop_ratio=0.03,    # 回撤 3% 出场
        time_stop_days=7,
        time_stop_profit_threshold=0.03,
    )
    strategy_v4_3 = OptimalStrategy(name="v4_tight_sl_trailing", params=params3)
    engine_v4_3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine_v4_3.set_strategy(strategy_v4_3)
    result_v4_3 = engine_v4_3.run(data_dict)
    results.append({
        'name': 'v4.0-紧止损移动',
        'annual': result_v4_3.annual_return,
        'sharpe': result_v4_3.sharpe_ratio,
        'drawdown': result_v4_3.max_drawdown,
        'win_rate': result_v4_3.win_rate,
        'profit_factor': result_v4_3.profit_factor,
        'total_trades': result_v4_3.total_trades
    })
    print(f"年化={result_v4_3.annual_return*100:.2f}%, 夏普={result_v4_3.sharpe_ratio:.2f}, "
          f"回撤={result_v4_3.max_drawdown*100:.2f}%, 胜率={result_v4_3.win_rate*100:.1f}%")
    print()

    # === 对比总结 ===
    print("=" * 80)
    print("对比总结")
    print("=" * 80)
    import pandas as pd
    df = pd.DataFrame(results)
    print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}" if isinstance(x, float) else str(x)))

    # 找出最优
    best_sharpe = df.loc[df['sharpe'].idxmax()]
    best_annual = df.loc[df['annual'].idxmax()]
    best_winrate = df.loc[df['win_rate'].idxmax()]

    print(f"\n最高夏普：{best_sharpe['name']} (夏普={best_sharpe['sharpe']:.2f})")
    print(f"最高年化：{best_annual['name']} (年化={best_annual['annual']*100:.2f}%)")
    print(f"最高胜率：{best_winrate['name']} (胜率={best_winrate['win_rate']*100:.1f}%)")

    return results

if __name__ == "__main__":
    test_v4_strategy()
