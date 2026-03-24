"""
筛选高质量股票池
基于历史表现和基本面对股票池进行筛选
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager
import pandas as pd

# 扩展股票池 (29 只)
EXTENDED_STOCKS = [
    '000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ',
    '000009.SZ', '000012.SZ', '000025.SZ', '000027.SZ', '000028.SZ',
    '000039.SZ', '000060.SZ', '000061.SZ', '000066.SZ', '000069.SZ',
    '000078.SZ', '000089.SZ', '000090.SZ', '000100.SZ', '000157.SZ',
    '000166.SZ', '000176.SZ', '000425.SZ', '000488.SZ', '000538.SZ',
    '000568.SZ', '000596.SZ', '000625.SZ', '000651.SZ'
]

START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

# 最优参数
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

def test_single_stock(ts_code, data_dict):
    """测试单只股票的表现"""
    strategy = create_optimal_strategy(
        stop_loss=BEST_PARAMS['stop_loss'],
        take_profit=BEST_PARAMS['take_profit'],
        signal_threshold=BEST_PARAMS['signal_threshold']
    )
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)
    result = engine.run({ts_code: data_dict[ts_code]})
    return {
        'ts_code': ts_code,
        'annual_return': result.annual_return,
        'sharpe': result.sharpe_ratio,
        'max_drawdown': result.max_drawdown,
        'win_rate': result.win_rate,
        'profit_factor': result.profit_factor,
        'total_trades': result.total_trades,
    }

def screen_stocks():
    print("=" * 80)
    print("股票池筛选分析")
    print("=" * 80)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"候选股票：{len(EXTENDED_STOCKS)} 只")
    print()

    # 加载数据
    print("加载数据...")
    data_dict = load_data(EXTENDED_STOCKS, START_DATE, END_DATE)
    print(f"成功加载：{len(data_dict)} 只")
    print()

    # 逐只测试
    print("逐只股票回测...")
    results = []
    for i, ts_code in enumerate(data_dict.keys(), 1):
        print(f"[{i}/{len(data_dict)}] {ts_code}", end=" ... ")
        try:
            r = test_single_stock(ts_code, data_dict)
            results.append(r)
            print(f"年化={r['annual_return']*100:.1f}%, 夏普={r['sharpe']:.2f}, 胜率={r['win_rate']*100:.1f}%")
        except Exception as e:
            print(f"错误：{e}")

    if not results:
        print("没有成功结果")
        return

    df = pd.DataFrame(results)

    # 按年化收益排序
    print("\n" + "=" * 80)
    print("按年化收益排序 (从高到低)")
    print("=" * 80)
    for _, r in df.nlargest(20, 'annual_return').iterrows():
        print(f"{r['ts_code']}: 年化={r['annual_return']*100:.1f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['max_drawdown']*100:.1f}%, 胜率={r['win_rate']*100:.1f}%")

    # 筛选高质量股票 (年化>5%, 夏普>0.3, 回撤<20%)
    print("\n" + "=" * 80)
    print("筛选条件：年化>5%, 夏普>0.3, 回撤<20%")
    print("=" * 80)
    qualified = df[
        (df['annual_return'] > 0.05) &
        (df['sharpe'] > 0.3) &
        (df['max_drawdown'] < 0.20)
    ]

    if len(qualified) > 0:
        print(f"符合条件：{len(qualified)} 只")
        for _, r in qualified.nlargest(20, 'annual_return').iterrows():
            print(f"  {r['ts_code']}: 年化={r['annual_return']*100:.1f}%, 夏普={r['sharpe']:.2f}, "
                  f"回撤={r['max_drawdown']*100:.1f}%")

        # 测试高质量股票池组合
        selected_stocks = qualified.nlargest(15, 'annual_return')['ts_code'].tolist()
        print(f"\n选取前 15 只构建股票池：{selected_stocks}")

        # 测试组合表现
        print("\n" + "=" * 80)
        print("测试高质量股票池 (前 15 只)")
        print("=" * 80)

        strategy = create_optimal_strategy(
            stop_loss=BEST_PARAMS['stop_loss'],
            take_profit=BEST_PARAMS['take_profit'],
            signal_threshold=BEST_PARAMS['signal_threshold']
        )
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)

        selected_data = {k: v for k, v in data_dict.items() if k in selected_stocks}
        result = engine.run(selected_data)

        print(f"年化收益：{result.annual_return*100:.2f}%")
        print(f"夏普比率：{result.sharpe_ratio:.2f}")
        print(f"最大回撤：{result.max_drawdown*100:.2f}%")
        print(f"胜率：{result.win_rate*100:.1f}%")
        print(f"盈亏比：{result.profit_factor:.2f}")
        print(f"总交易：{result.total_trades}笔")
    else:
        print("没有符合条件的股票")

    # 保存结果
    df.to_csv('data/cache/stock_screen_results.csv', index=False)
    print(f"\n结果已保存至：data/cache/stock_screen_results.csv")

if __name__ == "__main__":
    screen_stocks()
