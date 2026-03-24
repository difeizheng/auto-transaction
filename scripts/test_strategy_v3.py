"""
测试重构后的策略 v3.0

测试内容:
1. 市场状态过滤效果
2. 多策略组合表现
3. 最优参数验证
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.multi_strategy import create_multi_strategy, MultiStrategyParams
from src.strategy.optimal_strategy import create_optimal_strategy
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

def test_strategies():
    print("=" * 80)
    print("策略重构 v3.0 - 对比测试")
    print("=" * 80)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(ORIGINAL_STOCKS)} 只")
    print()

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    results = []

    # === 测试 1: 原始最优策略 (基准) ===
    print("=" * 80)
    print("测试 1: 原始最优策略 (SL=4%, TP=30%, Thr=4.5)")
    print("=" * 80)

    strategy1 = create_optimal_strategy(
        stop_loss=0.04,
        take_profit=0.30,
        signal_threshold=4.5
    )
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_dict)

    results.append({
        'name': '原始最优策略',
        'annual_return': result1.annual_return,
        'sharpe': result1.sharpe_ratio,
        'max_drawdown': result1.max_drawdown,
        'win_rate': result1.win_rate,
        'profit_factor': result1.profit_factor,
        'total_trades': result1.total_trades
    })

    print(f"年化收益：{result1.annual_return*100:.2f}%")
    print(f"夏普比率：{result1.sharpe_ratio:.2f}")
    print(f"最大回撤：{result1.max_drawdown*100:.2f}%")
    print(f"胜率：{result1.win_rate*100:.1f}%")
    print(f"盈亏比：{result1.profit_factor:.2f}")
    print(f"总交易：{result1.total_trades}笔")
    print()

    # === 测试 2: 多策略组合 (50% 趋势 +30% 均值回归 +20% 动量) ===
    print("=" * 80)
    print("测试 2: 多策略组合 (趋势 + 均值回归 + 动量)")
    print("=" * 80)

    params = MultiStrategyParams(
        trend_weight=0.5,
        mr_weight=0.3,
        mom_weight=0.2,
        trend_stop_loss=0.05,
        trend_take_profit=0.30,
        mr_stop_loss=0.08,
        mr_take_profit=0.15,
        mom_top_n=3,
        mom_rebalance_days=5
    )

    from src.strategy.multi_strategy import MultiStrategyPortfolio
    strategy2 = MultiStrategyPortfolio(params=params)

    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_dict)

    results.append({
        'name': '多策略组合',
        'annual_return': result2.annual_return,
        'sharpe': result2.sharpe_ratio,
        'max_drawdown': result2.max_drawdown,
        'win_rate': result2.win_rate,
        'profit_factor': result2.profit_factor,
        'total_trades': result2.total_trades
    })

    print(f"年化收益：{result2.annual_return*100:.2f}%")
    print(f"夏普比率：{result2.sharpe_ratio:.2f}")
    print(f"最大回撤：{result2.max_drawdown*100:.2f}%")
    print(f"胜率：{result2.win_rate*100:.1f}%")
    print(f"盈亏比：{result2.profit_factor:.2f}")
    print(f"总交易：{result2.total_trades}笔")
    print()

    # === 测试 3: 优化参数策略 (SL=5%, TP=35%, Thr=4.0) ===
    print("=" * 80)
    print("测试 3: 优化参数策略 (SL=5%, TP=35%, Thr=4.0)")
    print("=" * 80)

    strategy3 = create_optimal_strategy(
        stop_loss=0.05,
        take_profit=0.35,
        signal_threshold=4.0
    )
    engine3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine3.set_strategy(strategy3)
    result3 = engine3.run(data_dict)

    results.append({
        'name': '优化参数策略',
        'annual_return': result3.annual_return,
        'sharpe': result3.sharpe_ratio,
        'max_drawdown': result3.max_drawdown,
        'win_rate': result3.win_rate,
        'profit_factor': result3.profit_factor,
        'total_trades': result3.total_trades
    })

    print(f"年化收益：{result3.annual_return*100:.2f}%")
    print(f"夏普比率：{result3.sharpe_ratio:.2f}")
    print(f"最大回撤：{result3.max_drawdown*100:.2f}%")
    print(f"胜率：{result3.win_rate*100:.1f}%")
    print(f"盈亏比：{result3.profit_factor:.2f}")
    print(f"总交易：{result3.total_trades}笔")
    print()

    # === 对比分析 ===
    print("=" * 80)
    print("对比分析")
    print("=" * 80)

    df = pd.DataFrame(results)
    print("\n策略对比:")
    print(df.to_string(index=False))

    # 找出最优
    best_sharpe = df.loc[df['sharpe'].idxmax()]
    best_return = df.loc[df['annual_return'].idxmax()]

    print(f"\n最高夏普：{best_sharpe['name']} ({best_sharpe['sharpe']:.2f})")
    print(f"最高年化：{best_return['name']} ({best_return['annual_return']*100:.2f}%)")

if __name__ == "__main__":
    test_strategies()
