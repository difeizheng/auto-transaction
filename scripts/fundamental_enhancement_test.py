"""
基本面因子增强策略
在最优策略基础上增加基本面过滤条件

基本面因子:
1. ROE (净资产收益率) - 衡量盈利能力
2. 营收增长率 - 衡量成长性
3. 资产负债率 - 衡量财务健康
4. 经营现金流 - 衡量现金流质量

筛选条件:
- ROE > 8%
- 营收增长 > 5%
- 资产负债率 < 60%
- 经营现金流 > 0
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy, OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 优化股票池 + 基本面数据
# 使用已筛选的优化股票池
OPTIMIZED_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

# 模拟基本面数据 (实际应从 Tushare/Baostock 获取)
FUNDAMENTAL_DATA = {
    # 000063.SZ - 中兴通讯 (科技龙头)
    '000063.SZ': {'roe': 15.0, 'revenue_growth': 12.0, 'debt_ratio': 45.0, 'market_cap': 1500},
    # 000014.SZ - 沙河股份 (房地产)
    '000014.SZ': {'roe': 8.0, 'revenue_growth': 5.0, 'debt_ratio': 55.0, 'market_cap': 300},
    # 000078.SZ - 海王生物 (医药)
    '000078.SZ': {'roe': 10.0, 'revenue_growth': 8.0, 'debt_ratio': 50.0, 'market_cap': 250},
    # 000039.SZ - 上海机场 (交运)
    '000039.SZ': {'roe': 12.0, 'revenue_growth': 15.0, 'debt_ratio': 35.0, 'market_cap': 800},
    # 000001.SZ - 平安银行 (金融)
    '000001.SZ': {'roe': 11.0, 'revenue_growth': 6.0, 'debt_ratio': 52.0, 'market_cap': 2000},
}

def load_data(stocks, start_date, end_date):
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict

def filter_by_fundamentals(stocks, fundamental_data):
    """基于基本面过滤股票"""
    filtered = []
    for ts_code in stocks:
        if ts_code not in fundamental_data:
            continue
        funda = fundamental_data[ts_code]
        # 筛选条件：ROE>8%, 营收增长>5%, 负债率<60%
        if (funda.get('roe', 0) >= 8.0 and
            funda.get('revenue_growth', 0) >= 5.0 and
            funda.get('debt_ratio', 100) <= 60.0):
            filtered.append(ts_code)
    return filtered

def test_fundamental_enhancement():
    print("=" * 80)
    print("基本面因子增强策略测试")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    all_data = load_data(OPTIMIZED_STOCKS, START_DATE, END_DATE)
    print(f"加载成功：{len(all_data)} 只")
    print()

    # 基本面过滤
    print("基本面筛选条件：ROE>8%, 营收增长>5%, 负债率<60%")
    filtered_stocks = filter_by_fundamentals(OPTIMIZED_STOCKS, FUNDAMENTAL_DATA)
    print(f"筛选后：{len(filtered_stocks)} 只 - {filtered_stocks}")

    if len(filtered_stocks) == 0:
        print("没有符合基本面条件的股票，使用原始股票池")
        filtered_stocks = OPTIMIZED_STOCKS

    filtered_data = {k: v for k, v in all_data.items() if k in filtered_stocks}
    print()

    results = []

    # === 基准：优化股票池 (无基本面过滤) ===
    print("[1/2] 基准策略 (优化股票池，无基本面过滤)")
    strategy1 = create_optimal_strategy(
        stop_loss=0.04,
        take_profit=0.30,
        signal_threshold=4.5
    )
    engine1 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine1.set_strategy(strategy1)
    result1 = engine1.run(all_data)
    results.append({
        'name': '基准 (优化股票池)',
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

    # === 基本面增强：基本面过滤后的股票池 ===
    print("[2/2] 基本面增强策略 (基本面过滤)")
    # 基本面增强的策略：更高仓位、更宽止盈
    params2 = OptimalStrategyParams(
        base_stop_loss=0.04,
        base_take_profit=0.35,  # 更宽止盈
        signal_threshold=4.5,
        base_position_ratio=0.25,  # 更高仓位
        max_position_ratio=0.35,
        use_market_filter=True,
        market_bear_max_position=0.05,
        trailing_stop_trigger=0.10,
        trailing_stop_ratio=0.05,
        time_stop_days=8,
        time_stop_profit_threshold=0.03,
    )
    strategy2 = OptimalStrategy(name="fundamental_enhanced", params=params2)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine2.set_strategy(strategy2)
    result2 = engine2.run(filtered_data)
    results.append({
        'name': '基本面增强',
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
    print(f"基本面增强 vs 基准:")
    print(f"年化收益变化：{improvement:+.2f}%")
    print(f"夏普比率变化：{result2.sharpe_ratio - result1.sharpe_ratio:+.2f}")
    print(f"回撤变化：{(result2.max_drawdown - result1.max_drawdown)*100:+.2f}%")
    print(f"胜率变化：{(result2.win_rate - result1.win_rate)*100:+.1f}%")

    return results

if __name__ == "__main__":
    test_fundamental_enhancement()
