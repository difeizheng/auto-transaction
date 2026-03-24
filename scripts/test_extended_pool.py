"""
测试最优参数在扩展股票池上的表现
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 配置 - 扩展股票池 (29 只)
EXTENDED_STOCKS = [
    '000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ',
    '000009.SZ', '000012.SZ', '000025.SZ', '000027.SZ', '000028.SZ',
    '000039.SZ', '000060.SZ', '000061.SZ', '000066.SZ', '000069.SZ',
    '000078.SZ', '000089.SZ', '000090.SZ', '000100.SZ', '000157.SZ',
    '000166.SZ', '000176.SZ', '000425.SZ', '000488.SZ', '000538.SZ',
    '000568.SZ', '000596.SZ', '000625.SZ', '000651.SZ'
]

# 原始股票池 (5 只)
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

def test_extended_pool():
    print("=" * 80)
    print("扩展股票池测试 - 最优参数验证")
    print("=" * 80)

    # 最优参数
    best_params = {
        'stop_loss': 0.04,
        'take_profit': 0.30,
        'signal_threshold': 4.5
    }

    print(f"最优参数：SL={best_params['stop_loss']*100}%, TP={best_params['take_profit']*100}%, Thr={best_params['signal_threshold']}")
    print()

    # 测试原始股票池
    print("=" * 80)
    print("测试 1: 原始股票池 (5 只)")
    print("=" * 80)
    data_original = load_data(ORIGINAL_STOCKS, START_DATE, END_DATE)

    strategy1 = create_optimal_strategy(
        stop_loss=best_params['stop_loss'],
        take_profit=best_params['take_profit'],
        signal_threshold=best_params['signal_threshold']
    )
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(data_original)

    print(f"年化收益：{result1.annual_return*100:.2f}%")
    print(f"夏普比率：{result1.sharpe_ratio:.2f}")
    print(f"最大回撤：{result1.max_drawdown*100:.2f}%")
    print(f"胜率：{result1.win_rate*100:.1f}%")
    print(f"盈亏比：{result1.profit_factor:.2f}")
    print(f"总交易：{result1.total_trades}笔")
    print()

    # 测试扩展股票池
    print("=" * 80)
    print("测试 2: 扩展股票池 (29 只)")
    print("=" * 80)
    data_extended = load_data(EXTENDED_STOCKS, START_DATE, END_DATE)

    strategy2 = create_optimal_strategy(
        stop_loss=best_params['stop_loss'],
        take_profit=best_params['take_profit'],
        signal_threshold=best_params['signal_threshold']
    )
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(data_extended)

    print(f"年化收益：{result2.annual_return*100:.2f}%")
    print(f"夏普比率：{result2.sharpe_ratio:.2f}")
    print(f"最大回撤：{result2.max_drawdown*100:.2f}%")
    print(f"胜率：{result2.win_rate*100:.1f}%")
    print(f"盈亏比：{result2.profit_factor:.2f}")
    print(f"总交易：{result2.total_trades}笔")
    print()

    # 对比分析
    print("=" * 80)
    print("对比分析")
    print("=" * 80)
    print(f"股票池扩大：5 只 → 29 只")
    print(f"年化变化：{result1.annual_return*100:.2f}% → {result2.annual_return*100:.2f}% ({'+' if result2.annual_return > result1.annual_return else ''}{(result2.annual_return - result1.annual_return)*100:.2f}%)")
    print(f"夏普变化：{result1.sharpe_ratio:.2f} → {result2.sharpe_ratio:.2f}")
    print(f"回撤变化：{result1.max_drawdown*100:.2f}% → {result2.max_drawdown*100:.2f}%")
    print(f"胜率变化：{result1.win_rate*100:.1f}% → {result2.win_rate*100:.1f}%")
    print(f"交易频率：{result1.total_trades}笔 → {result2.total_trades}笔")

if __name__ == "__main__":
    test_extended_pool()
