"""
模拟交易演示脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import random

from src.data_collector.data_manager import data_manager
from src.trader.broker_api import PaperBroker
from src.trader.risk_control import RiskController
from src.strategy.technical import TechnicalStrategy
from src.utils.database import init_db


def run_paper_trading_demo():
    """运行模拟交易演示"""
    print("=" * 60)
    print("模拟交易演示")
    print("=" * 60)

    # 1. 初始化
    print("\n[1/4] 初始化系统...")
    init_db()

    # 2. 创建组件
    print("\n[2/4] 创建交易组件...")

    # 创建模拟券商 (初始资金 2 万)
    broker = PaperBroker(initial_capital=20000)

    # 创建策略
    strategy = TechnicalStrategy(name="demo_strategy")

    # 创建风控
    risk_controller = RiskController()

    # 连接券商
    if not broker.connect():
        print("错误：券商连接失败")
        return

    print(f"模拟券商连接成功，初始资金：20,000")

    # 3. 准备数据
    print("\n[3/4] 准备股票数据...")

    # 选取几只股票作为演示
    demo_stocks = ['600000.SH', '000001.SZ', '600036.SH', '000651.SZ', '600519.SH']

    # 更新数据
    for ts_code in demo_stocks:
        try:
            data_manager.update_single_stock(ts_code, days=60)
            print(f"  更新 {ts_code} 完成")
        except Exception as e:
            print(f"  更新 {ts_code} 失败：{e}")

    # 4. 模拟交易循环
    print("\n[4/4] 开始模拟交易...")
    print("-" * 60)

    # 获取历史数据用于模拟
    stock_data = {}
    for ts_code in demo_stocks:
        df = data_manager.get_daily_quotes(ts_code)
        if not df.empty:
            stock_data[ts_code] = df.to_dict('records')

    if not stock_data:
        print("错误：无法获取股票数据")
        return

    # 模拟交易日
    trading_days = set()
    for df in stock_data.values():
        for row in df:
            trading_days.add(row.get('trade_date'))

    sorted_days = sorted(list(trading_days))

    # 初始化策略
    strategy.on_init()

    print(f"开始模拟 {len(sorted_days)} 个交易日的交易...")
    print("-" * 60)

    for i, trade_date in enumerate(sorted_days):
        # 获取当日数据
        day_data = {}
        for ts_code, data in stock_data.items():
            for row in data:
                if row.get('trade_date') == trade_date:
                    day_data[ts_code] = row
                    break

        if not day_data:
            continue

        # 策略生成信号
        signals = strategy.on_bar(day_data, trade_date)

        # 执行信号
        for signal in signals:
            order_id = broker.submit_order(
                ts_code=signal.ts_code,
                direction=signal.direction,
                price=signal.price,
                volume=signal.volume,
                strategy_name=signal.strategy_name
            )

            if order_id:
                print(f"[{trade_date}] {signal.direction.upper()} {signal.ts_code} "
                      f"{signal.volume}@{signal.price:.2f} - {signal.reason}")

        # 更新持仓价格
        for ts_code, row in day_data.items():
            broker.update_market_price(ts_code, row.get('close', 0))

        # 定期输出账户状态
        if (i + 1) % 10 == 0 or i == len(sorted_days) - 1:
            account = broker.get_account_info()
            print(f"\n--- 交易日 {i + 1}/{len(sorted_days)} ---")
            print(f"日期：{trade_date}")
            print(f"总资产：{account.get('total_asset', 0):,.2f}")
            print(f"可用资金：{account.get('available_cash', 0):,.2f}")
            print(f"持仓市值：{account.get('position_value', 0):,.2f}")
            print(f"持仓数量：{account.get('position_count', 0)}")

            # 打印持仓
            positions = broker.get_positions()
            if positions:
                print("\n持仓明细:")
                for pos in positions:
                    print(f"  {pos['ts_code']}: {pos['volume']} 股，"
                          f"盈亏：{pos['profit_loss']:.2f} ({pos['profit_ratio']:.2%})")

    # 最终报告
    print("\n" + "=" * 60)
    print("模拟交易完成!")
    print("=" * 60)

    account = broker.get_account_info()
    positions = broker.get_positions()

    print(f"\n最终账户状态:")
    print(f"  总资产：{account.get('total_asset', 0):,.2f}")
    print(f"  初始资金：20,000.00")
    print(f"  总盈亏：{account.get('total_asset', 0) - 20000:.2f}")
    print(f"  收益率：{(account.get('total_asset', 0) / 20000 - 1) * 100:.2f}%")

    # 风险报告
    print("\n" + broker.get_risk_report())


if __name__ == "__main__":
    run_paper_trading_demo()
