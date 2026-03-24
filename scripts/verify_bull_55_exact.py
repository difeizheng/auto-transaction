"""
牛市 55% 配置验证 - 精确匹配深度优化测试参数

根据 strategy_deep_optimization_v2.py 的配置：
- 基础仓位：35%
- 牛市最大：55%
- 熊市仓位：2%
- 信号阈值：5.5 (不是 5.0!)
- 止损：4%
- 止盈：35%
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 配置参数
STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
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


def run_backtest():
    print("=" * 90)
    print("牛市 55% 配置验证 - 精确参数测试")
    print("=" * 90)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print()

    # 加载数据
    print("加载数据...")
    data_dict = load_data(STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票")
    print()

    # 配置 1: 牛市 55% (信号阈值 5.5)
    print("=" * 60)
    print("配置 1: 牛市 55% (阈值 5.5)")
    print("=" * 60)

    params1 = OptimalStrategyParams(
        signal_threshold=5.5,          # 5.5
        base_stop_loss=0.04,           # 4%
        base_take_profit=0.35,         # 35%
        base_position_ratio=0.35,      # 35%
        max_position_ratio=0.55,       # 55%
        min_position_ratio=0.01,
        use_market_filter=True,
        market_bear_max_position=0.02,  # 2%
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.06,
        time_stop_days=10,
        time_stop_profit_threshold=0.03,
    )

    strategy1 = OptimalStrategy(name="牛市 55% (阈值 5.5)", params=params1)
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_dict)

    print(f"年化：{result1.annual_return*100:.2f}%, 夏普：{result1.sharpe_ratio:.2f}, "
          f"回撤：{result1.max_drawdown*100:.2f}%, 胜率：{result1.win_rate*100:.1f}%")

    # 配置 2: 牛市 55% (信号阈值 5.0)
    print()
    print("=" * 60)
    print("配置 2: 牛市 55% (阈值 5.0)")
    print("=" * 60)

    params2 = OptimalStrategyParams(
        signal_threshold=5.0,          # 5.0
        base_stop_loss=0.04,           # 4%
        base_take_profit=0.35,         # 35%
        base_position_ratio=0.35,      # 35%
        max_position_ratio=0.55,       # 55%
        min_position_ratio=0.01,
        use_market_filter=True,
        market_bear_max_position=0.02,  # 2%
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.06,
        time_stop_days=10,
        time_stop_profit_threshold=0.03,
    )

    strategy2 = OptimalStrategy(name="牛市 55% (阈值 5.0)", params=params2)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_dict)

    print(f"年化：{result2.annual_return*100:.2f}%, 夏普：{result2.sharpe_ratio:.2f}, "
          f"回撤：{result2.max_drawdown*100:.2f}%, 胜率：{result2.win_rate*100:.1f}%")

    # 配置 3: 基准 (阈值 5.5, 仓位 45%)
    print()
    print("=" * 60)
    print("配置 3: 基准 (阈值 5.5, 牛市 45%)")
    print("=" * 60)

    params3 = OptimalStrategyParams(
        signal_threshold=5.5,
        base_stop_loss=0.04,
        base_take_profit=0.35,
        base_position_ratio=0.30,
        max_position_ratio=0.45,
        min_position_ratio=0.01,
        use_market_filter=True,
        market_bear_max_position=0.03,
        trailing_stop_trigger=0.15,
        trailing_stop_ratio=0.06,
        time_stop_days=10,
        time_stop_profit_threshold=0.03,
    )

    strategy3 = OptimalStrategy(name="基准 (牛市 45%)", params=params3)
    engine3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine3.set_strategy(strategy3)
    result3 = engine3.run(data_dict)

    print(f"年化：{result3.annual_return*100:.2f}%, 夏普：{result3.sharpe_ratio:.2f}, "
          f"回撤：{result3.max_drawdown*100:.2f}%, 胜率：{result3.win_rate*100:.1f}%")

    # 总结
    print()
    print("=" * 90)
    print("结果对比")
    print("=" * 90)
    print(f"| 配置 | 年化 | 夏普 | 回撤 | 胜率 |")
    print(f"|------|------|------|------|------|")
    print(f"| 牛市 55% (5.5) | {result1.annual_return*100:.2f}% | {result1.sharpe_ratio:.2f} | {result1.max_drawdown*100:.1f}% | {result1.win_rate*100:.1f}% |")
    print(f"| 牛市 55% (5.0) | {result2.annual_return*100:.2f}% | {result2.sharpe_ratio:.2f} | {result2.max_drawdown*100:.1f}% | {result2.win_rate*100:.1f}% |")
    print(f"| 基准 (5.5/45%) | {result3.annual_return*100:.2f}% | {result3.sharpe_ratio:.2f} | {result3.max_drawdown*100:.1f}% | {result3.win_rate*100:.1f}% |")

    # 找出最优
    results = [
        ('牛市 55% (阈值 5.5)', result1),
        ('牛市 55% (阈值 5.0)', result2),
        ('基准 (牛市 45%)', result3),
    ]

    best_annual = max(results, key=lambda x: x[1].annual_return)
    print()
    print(f"最优年化：{best_annual[0]} = {best_annual[1].annual_return*100:.2f}%")

    return results


if __name__ == '__main__':
    run_backtest()
