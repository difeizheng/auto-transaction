"""
简化版策略测试 v3.0
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
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

def test():
    print("=" * 80)
    print("策略重构 v3.0 - 简化测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    results = []

    # 测试 1: 原始最优策略 (基准)
    print("测试 1: 原始最优策略 (SL=4%, TP=30%, Thr=4.5)")
    strategy1 = create_optimal_strategy(stop_loss=0.04, take_profit=0.30, signal_threshold=4.5)
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_dict)
    results.append({'name': '原始最优', 'annual': result1.annual_return, 'sharpe': result1.sharpe_ratio,
                    'drawdown': result1.max_drawdown, 'win_rate': result1.win_rate, 'profit_factor': result1.profit_factor})
    print(f"年化={result1.annual_return*100:.2f}%, 夏普={result1.sharpe_ratio:.2f}, 回撤={result1.max_drawdown*100:.2f}%, 胜率={result1.win_rate*100:.1f}%")
    print()

    # 测试 2: 优化参数 (SL=5%, TP=35%, Thr=4.0)
    print("测试 2: 优化参数 (SL=5%, TP=35%, Thr=4.0)")
    strategy2 = create_optimal_strategy(stop_loss=0.05, take_profit=0.35, signal_threshold=4.0)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_dict)
    results.append({'name': '优化参数', 'annual': result2.annual_return, 'sharpe': result2.sharpe_ratio,
                    'drawdown': result2.max_drawdown, 'win_rate': result2.win_rate, 'profit_factor': result2.profit_factor})
    print(f"年化={result2.annual_return*100:.2f}%, 夏普={result2.sharpe_ratio:.2f}, 回撤={result2.max_drawdown*100:.2f}%, 胜率={result2.win_rate*100:.1f}%")
    print()

    # 测试 3: 优化参数 (SL=5%, TP=30%, Thr=4.0)
    print("测试 3: 优化参数 (SL=5%, TP=30%, Thr=4.0)")
    strategy3 = create_optimal_strategy(stop_loss=0.05, take_profit=0.30, signal_threshold=4.0)
    engine3 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine3.set_strategy(strategy3)
    result3 = engine3.run(data_dict)
    results.append({'name': '优化参数 2', 'annual': result3.annual_return, 'sharpe': result3.sharpe_ratio,
                    'drawdown': result3.max_drawdown, 'win_rate': result3.win_rate, 'profit_factor': result3.profit_factor})
    print(f"年化={result3.annual_return*100:.2f}%, 夏普={result3.sharpe_ratio:.2f}, 回撤={result3.max_drawdown*100:.2f}%, 胜率={result3.win_rate*100:.1f}%")
    print()

    # 对比
    print("=" * 80)
    print("对比总结")
    print("=" * 80)
    import pandas as pd
    df = pd.DataFrame(results)
    print(df.to_string(index=False))

    best = df.loc[df['sharpe'].idxmax()]
    print(f"\n最优策略：{best['name']} (夏普={best['sharpe']:.2f}, 年化={best['annual']*100:.2f}%)")

if __name__ == "__main__":
    test()
