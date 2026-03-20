"""
中国股票量化自动交易系统
主程序入口
"""
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.database import init_db
from src.data_collector.data_manager import data_manager
from src.data_collector.tushare_client import TushareClient
from src.trader.broker_api import PaperBroker
from src.trader.risk_control import RiskController
from src.trader.scheduler import TradingBot, create_trading_bot
from src.strategy.technical import TechnicalStrategy, MACDStrategy, MaCrossoverStrategy
from src.strategy.optimal_strategy import create_optimal_strategy
from src.strategy.enhanced_ma import EnhancedMaCrossoverStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer


def init():
    """初始化系统"""
    print("初始化量化交易系统...")
    init_db()
    print("数据库初始化完成")


def update_data(days: int = 30, stocks: list = None):
    """更新数据"""
    print(f"更新最近 {days} 天的行情数据...")

    if stocks is None:
        # 使用扩展股票池
        from config.settings import EXTENDED_STOCK_POOL
        stocks = EXTENDED_STOCK_POOL

    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    for ts_code in stocks:
        try:
            data_manager.get_daily_quotes(
                ts_code,
                start_date.strftime('%Y%m%d'),
                end_date.strftime('%Y%m%d')
            )
            print(f"  [OK] {ts_code}")
        except Exception as e:
            print(f"  [FAIL] {ts_code}: {e}")

    print("数据更新完成")


def run_backtest(strategy: str = "optimal", stocks: list = None,
                 start_date: str = '20250301', end_date: str = '20260319',
                 initial_capital: float = 1000000,
                 use_extended_pool: bool = True,
                 filter_fundamentals: bool = True,
                 stop_loss: float = None,
                 take_profit: float = None,
                 signal_threshold: float = None):
    """运行回测

    Args:
        strategy: 策略类型
        stocks: 自定义股票池
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        use_extended_pool: 是否使用扩展股票池
        filter_fundamentals: 是否进行基本面过滤
        stop_loss: 止损比例（可选，覆盖默认值）
        take_profit: 止盈比例（可选，覆盖默认值）
        signal_threshold: 信号阈值（可选，覆盖默认值）
    """
    print(f"开始回测 - 策略：{strategy}")

    # 确定股票池
    if stocks is None:
        if use_extended_pool:
            from config.settings import EXTENDED_STOCK_POOL, FUNDAMENTAL_FILTERS
            if filter_fundamentals:
                print('正在基本面过滤股票池...')
                stocks = data_manager.filter_stock_pool_by_fundamentals(
                    stock_list=EXTENDED_STOCK_POOL,
                    max_pe=FUNDAMENTAL_FILTERS['max_pe'],
                    min_roe=FUNDAMENTAL_FILTERS['min_roe'],
                    min_revenue_growth=FUNDAMENTAL_FILTERS['min_revenue_growth']
                )
                print(f'基本面过滤后股票数量：{len(stocks)}')
            else:
                stocks = EXTENDED_STOCK_POOL
        else:
            # 默认股票池
            stocks = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']

    # 加载数据
    print('加载数据...')
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df

    print(f'已加载 {len(data_dict)} 只股票')

    # 创建策略
    print('创建策略...')
    if strategy.lower() == 'optimal':
        # 支持动态传递止损止盈参数
        strat = create_optimal_strategy(
            stop_loss=stop_loss,
            take_profit=take_profit,
            aggressive=True
        )
        # 如果指定了信号阈值，需要修改策略参数
        if signal_threshold is not None:
            strat.params.signal_threshold = signal_threshold
    elif strategy.lower() == 'enhanced':
        strat = EnhancedMaCrossoverStrategy()
    elif strategy.lower() == 'ma':
        strat = MaCrossoverStrategy()
    elif strategy.lower() == 'macd':
        strat = MACDStrategy()
    else:
        strat = TechnicalStrategy()

    # 运行回测
    print('运行回测...')
    engine = BacktestEngine(initial_capital=initial_capital)
    engine.set_strategy(strat)
    result = engine.run(data_dict)

    # 绩效分析
    analyzer = PerformanceAnalyzer()
    report = analyzer.generate_report(result)
    print(report)

    return result


def run_paper_trading(strategy: str = 'optimal', stocks: list = None, initial_capital: float = 100000):
    """运行模拟交易"""
    print(f"启动模拟交易 - 策略：{strategy}, 初始资金：{initial_capital:,.0f}")

    if stocks is None:
        # 使用扩展股票池
        from config.settings import EXTENDED_STOCK_POOL
        stocks = EXTENDED_STOCK_POOL

    # 创建策略
    if strategy.lower() == 'optimal':
        strat = create_optimal_strategy(aggressive=True)
    elif strategy.lower() == 'enhanced':
        strat = EnhancedMaCrossoverStrategy()
    else:
        strat = TechnicalStrategy()

    # 创建模拟券商
    broker = PaperBroker(initial_capital=initial_capital)

    # 创建风控控制器
    risk_controller = RiskController()

    # 创建交易机器人
    bot = create_trading_bot(
        strategy=strat,
        broker=broker,
        risk_controller=risk_controller,
        stock_pool=stocks
    )

    print(f"模拟交易已启动 (按 Ctrl+C 停止)")
    print(f"股票池：{len(stocks)} 只股票")
    print(f"初始资金：{initial_capital:,.2f}")
    print()

    try:
        bot.start()
    except KeyboardInterrupt:
        print("\n停止模拟交易...")
        bot.stop()
        broker.get_account_summary()


def show_menu():
    """显示菜单"""
    print()
    print('='*60)
    print('中国股票量化自动交易系统')
    print('='*60)
    print('1. 更新数据 (最近 30 天)')
    print('2. 更新数据 (最近 365 天)')
    print('3. 运行回测 - 最优策略')
    print('4. 运行回测 - 增强均线策略')
    print('5. 启动模拟交易')
    print('0. 退出')
    print('='*60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='中国股票量化自动交易系统')
    parser.add_argument('command', choices=['init', 'update', 'backtest', 'paper', 'trade', 'menu'],
                        help='命令：init(初始化), update(更新数据), backtest(回测), paper(模拟交易), trade(实盘交易), menu(交互菜单)')
    parser.add_argument('--days', type=int, default=30, help='更新数据的天数')
    parser.add_argument('--start-date', type=str, help='回测开始日期 (YYYYMMDD)')
    parser.add_argument('--end-date', type=str, help='回测结束日期 (YYYYMMDD)')
    parser.add_argument('--strategy', type=str, default='optimal',
                        help='策略类型：optimal, enhanced, technical, macd, ma')
    parser.add_argument('--capital', type=float, default=1000000, help='回测初始资金')
    parser.add_argument('--paper-capital', type=float, default=100000, help='模拟交易初始资金')
    parser.add_argument('--stocks', type=str, nargs='+', default=None, help='股票池')
    parser.add_argument('--use-extended-pool', action='store_true', default=True, help='使用扩展股票池')
    parser.add_argument('--no-fundamental-filter', action='store_true', help='不进行基本面过滤')
    parser.add_argument('--pool-size', type=int, default=30, help='股票池目标数量')
    # 参数敏感性测试支持
    parser.add_argument('--stop-loss', type=float, default=None, help='止损比例 (可选，覆盖默认值)')
    parser.add_argument('--take-profit', type=float, default=None, help='止盈比例 (可选，覆盖默认值)')
    parser.add_argument('--signal-threshold', type=float, default=None, help='信号阈值 (可选，覆盖默认值)')

    args = parser.parse_args()

    if args.command == 'init':
        init()
    elif args.command == 'update':
        update_data(args.days, args.stocks)
    elif args.command == 'backtest':
        run_backtest(
            strategy=args.strategy,
            stocks=args.stocks,
            start_date=args.start_date or '20250301',
            end_date=args.end_date or '20260319',
            initial_capital=args.capital,
            use_extended_pool=args.use_extended_pool,
            filter_fundamentals=not args.no_fundamental_filter,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
            signal_threshold=args.signal_threshold
        )
    elif args.command == 'paper':
        run_paper_trading(strategy=args.strategy, stocks=args.stocks, initial_capital=args.paper_capital)
    elif args.command == 'trade':
        print("实盘交易功能需要配置券商接口")
    elif args.command == 'menu':
        interactive_menu()


def interactive_menu():
    """交互式菜单"""
    from datetime import datetime
    print('='*60)
    print('中国股票量化自动交易系统')
    print('='*60)
    print(f'启动时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    print('[快速回测演示]')
    run_backtest(strategy='optimal', start_date='20251201', end_date='20260319')

    # 交互式菜单
    while True:
        show_menu()
        choice = input('请选择功能 (0-5): ').strip()

        if choice == '1':
            update_data(days=30)
        elif choice == '2':
            update_data(days=365)
        elif choice == '3':
            run_backtest(strategy='optimal')
        elif choice == '4':
            run_backtest(strategy='enhanced')
        elif choice == '5':
            run_paper_trading()
        elif choice == '0':
            print('再见!')
            break
        else:
            print('无效选择，请重试')


if __name__ == "__main__":
    main()
