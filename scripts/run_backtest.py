"""
回测示例脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

from src.data_collector.data_manager import data_manager
from src.data_collector.tushare_client import TushareClient
from src.strategy.technical import TechnicalStrategy, MACDStrategy, MaCrossoverStrategy
from src.strategy.multi_factor import SimpleMultiFactorStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer
from src.utils.database import init_db


def run_backtest_example():
    """运行回测示例"""
    print("=" * 60)
    print("量化交易策略回测系统")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n[1/5] 初始化数据库...")
    init_db()

    # 2. 准备数据
    print("\n[2/5] 准备回测数据...")

    # 更新股票列表
    ts_client = TushareClient()
    stocks_df = ts_client.get_stock_list(list_status='L')

    if stocks_df.empty:
        print("警告：无法获取股票列表，请检查 Tushare Token 配置")
        return

    # 选取部分股票作为股票池
    stock_pool = stocks_df['ts_code'].head(50).tolist()
    print(f"股票池：{len(stock_pool)} 只股票")

    # 更新日线数据 (最近 1 年)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    print(f"更新 {start_date} 至 {end_date} 的行情数据...")

    # 更新部分股票的数据
    for i, ts_code in enumerate(stock_pool[:20]):  # 仅更新前 20 只用于测试
        data_manager.update_single_stock(ts_code, days=365)
        if (i + 1) % 5 == 0:
            print(f"  进度：{i + 1}/{len(stock_pool[:20])}")

    # 3. 加载数据
    print("\n[3/5] 加载回测数据...")

    # 选取部分活跃股票
    active_stocks = stock_pool[:10]

    market_data = {}
    for ts_code in active_stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            market_data[ts_code] = df
            print(f"  {ts_code}: {len(df)} 条数据")

    if not market_data:
        print("错误：无法获取行情数据")
        return

    # 4. 设置策略
    print("\n[4/5] 设置交易策略...")

    # 示例 1: 技术指标策略
    strategy = TechnicalStrategy(
        name="technical_strategy",
        params=None  # 使用默认参数
    )

    # 示例 2: MACD 策略
    # strategy = MACDStrategy(name="macd_strategy")

    # 示例 3: 均线交叉策略
    # strategy = MaCrossoverStrategy(name="ma_crossover", short_period=5, long_period=20)

    print(f"策略：{strategy.name}")

    # 5. 运行回测
    print("\n[5/5] 运行回测...")
    print("=" * 60)

    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=1000000,  # 100 万初始资金
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        slippage_rate=0.001,
        max_position_ratio=0.8
    )

    # 设置策略
    engine.set_strategy(strategy)

    # 加载数据
    data_dict = engine.load_data(
        ts_codes=list(market_data.keys()),
        start_date=start_date,
        end_date=end_date
    )

    # 运行回测
    result = engine.run(data_dict)

    # 6. 绩效分析
    print("\n")
    analyzer = PerformanceAnalyzer()
    report = analyzer.generate_report(result)
    print(report)

    # 7. 保存结果
    print("\n回测完成!")

    # 可选：绘制权益曲线
    try:
        analyzer.plot_equity_curve(result, save_path="logs/equity_curve.png")
        print("权益曲线已保存到 logs/equity_curve.png")
    except Exception as e:
        print(f"无法绘制图表：{e}")

    return result


if __name__ == "__main__":
    run_backtest_example()
