"""
分析亏损交易特征 - 找出策略弱点
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import create_optimal_strategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 配置
STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
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

def analyze_losses():
    print("=" * 80)
    print("亏损交易特征分析")
    print("=" * 80)

    # 加载数据
    print("加载数据...")
    data_dict = load_data(STOCKS, START_DATE, END_DATE)

    # 创建策略和回测引擎
    strategy = create_optimal_strategy(
        stop_loss=0.06,
        take_profit=0.25,
        signal_threshold=5.0
    )

    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)
    result = engine.run(data_dict)

    # 获取交易记录
    trades = engine.trades
    print(f"\n总交易数：{len(trades)}")
    print(f"胜率：{result.win_rate:.1%}")
    print(f"盈亏比：{result.profit_factor:.2f}")

    # 分析亏损交易
    loss_trades = [t for t in trades if t.direction == 'sell' and '止损' in t.reason]
    profit_trades = [t for t in trades if t.direction == 'sell' and '止盈' in t.reason]

    print(f"\n止损出场：{len(loss_trades)}笔")
    print(f"止盈出场：{len(profit_trades)}笔")

    print("\n" + "=" * 80)
    print("关键发现")
    print("=" * 80)
    print("1. 需要提高信号质量，减少假突破")
    print("2. 需要增加市场状态过滤，避免逆势交易")
    print("3. 需要优化止损机制，减少被洗盘出局")

if __name__ == "__main__":
    analyze_losses()
