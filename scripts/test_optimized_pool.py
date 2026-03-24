"""
测试优化股票池组合
基于单只股票回测表现重新构建股票池
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 基于回测结果构建的股票池
# Top 5: 000063.SZ, 000014.SZ, 000078.SZ, 000039.SZ, 000016.SZ
OPTIMIZED_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
ORIGINAL_STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']

START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

BEST_PARAMS = {
    'stop_loss': 0.04,
    'take_profit': 0.30,
    'signal_threshold': 4.5
}

def load_data(stocks, start_date, end_date):
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict

def compare_stock_pools():
    print("=" * 80)
    print("股票池对比测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    original_data = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)
    optimized_data = load_data(OPTIMIZED_STOCKS, START_DATE, END_DATE)
    print(f"原始股票池：{len(original_data)} 只")
    print(f"优化股票池：{len(optimized_data)} 只")
    print()

    results = []

    # === 测试原始股票池 ===
    print("[1/2] 原始股票池 (000001, 000002, 000063, 000014, 000016)")
    strategy1 = create_optimal_strategy(
        stop_loss=BEST_PARAMS['stop_loss'],
        take_profit=BEST_PARAMS['take_profit'],
        signal_threshold=BEST_PARAMS['signal_threshold']
    )
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(original_data)
    results.append({
        'name': '原始股票池',
        'stocks': ','.join(ORIGINAL_STOCKS),
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

    # === 测试优化股票池 ===
    print("[2/2] 优化股票池 (000063, 000014, 000078, 000039, 000001)")
    strategy2 = create_optimal_strategy(
        stop_loss=BEST_PARAMS['stop_loss'],
        take_profit=BEST_PARAMS['take_profit'],
        signal_threshold=BEST_PARAMS['signal_threshold']
    )
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(optimized_data)
    results.append({
        'name': '优化股票池',
        'stocks': ','.join(OPTIMIZED_STOCKS),
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

    # === 对比总结 ===
    print("=" * 80)
    print("对比总结")
    print("=" * 80)
    import pandas as pd
    df = pd.DataFrame(results)
    print(df.to_string(index=False))

    # 比较
    print("\n" + "=" * 80)
    improvement = (result2.annual_return - result1.annual_return) * 100
    print(f"优化股票池 vs 原始股票池:")
    print(f"年化收益变化：{improvement:+.2f}%")
    print(f"夏普比率变化：{result2.sharpe_ratio - result1.sharpe_ratio:+.2f}")
    print(f"回撤变化：{(result2.max_drawdown - result1.max_drawdown)*100:+.2f}%")
    print(f"胜率变化：{(result2.win_rate - result1.win_rate)*100:+.1f}%")

    # 最佳组合
    if result2.annual_return > result1.annual_return:
        print(f"\n[建议] 使用优化股票池：{OPTIMIZED_STOCKS}")
    else:
        print(f"\n[建议] 保持原始股票池：{ORIGINAL_STOCKS}")

    return results

if __name__ == "__main__":
    compare_stock_pools()
