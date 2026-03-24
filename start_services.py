"""
中国股票量化自动交易系统 - 服务启动脚本
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime
import sys
import argparse

from src.trader.scheduler import create_trading_bot
from src.trader.broker_api import PaperBroker
from src.trader.risk_control import RiskController
from src.strategy.optimal_strategy import create_optimal_strategy
from src.data_collector.data_manager import data_manager


def start_scheduler():
    """启动定时任务调度器"""
    print('='*60)
    print('中国股票量化自动交易系统 - 定时任务服务')
    print('='*60)
    print()

    scheduler = BlockingScheduler()

    # 盘前准备任务 (交易日 09:15)
    @scheduler.scheduled_job('cron', hour=9, minute=15, day_of_week='mon-fri', id='pre_market')
    def pre_market_job():
        print(f'[{datetime.now()}] 执行盘前准备任务...')
        # 1. 获取外围市场表现
        # 2. 分析财经新闻
        # 3. 生成关注股票列表

    # 集合竞价监控 (交易日 09:25)
    @scheduler.scheduled_job('cron', hour=9, minute=25, day_of_week='mon-fri', id='call_auction')
    def call_auction_job():
        print(f'[{datetime.now()}] 执行集合竞价监控...')
        # 1. 获取集合竞价数据
        # 2. 识别强势股
        # 3. 生成开盘策略

    # 收盘后处理 (交易日 15:05)
    @scheduler.scheduled_job('cron', hour=15, minute=5, day_of_week='mon-fri', id='post_market')
    def post_market_job():
        print(f'[{datetime.now()}] 执行盘后处理任务...')
        # 1. 计算当日盈亏
        # 2. 更新持仓成本
        # 3. 生成交易日志

    # 盘后分析 (交易日 20:00)
    @scheduler.scheduled_job('cron', hour=20, minute=0, day_of_week='mon-fri', id='daily_analysis')
    def daily_analysis_job():
        print(f'[{datetime.now()}] 执行盘后分析任务...')
        # 1. 分析当日交易
        # 2. 筛选潜力股票
        # 3. 更新策略参数

    print('已注册的定时任务:')
    for job in scheduler.get_jobs():
        print(f'  - {job.name}: {job.trigger}')

    print()
    print('服务启动成功 (按 Ctrl+C 停止)...')
    print()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print()
        print('服务已停止')
        sys.exit(0)


def start_paper_trading(strategy: str = 'optimal', capital: float = 100000, mode: str = 'conservative'):
    """启动模拟交易
    Args:
        strategy: 策略类型
        capital: 初始资金
        mode: 配置模式 ('conservative' 稳健版 53% / 'aggressive' 进取版 55%)
    """
    print('='*60)
    print('中国股票量化自动交易系统 - 模拟交易')
    print('='*60)
    print()

    # 创建策略
    if strategy == 'optimal':
        strat = create_optimal_strategy(aggressive=(mode=='aggressive'), mode=mode)
        print(f'策略：最优策略 ({mode} 模式)')
        if mode == 'conservative':
            print(f'  配置：牛市 53% / 阈值 5.5 / 止损 4% / 止盈 35%')
            print(f'  预期：年化 15.22%, 回撤 14.46%, 胜率 51.4%')
        elif mode == 'aggressive':
            print(f'  配置：牛市 55% / 阈值 5.5 / 止损 4% / 止盈 35%')
            print(f'  预期：年化 16.15%, 回撤 15.26%, 胜率 51.4%')
    elif strategy == 'enhanced':
        from src.strategy.enhanced_ma import EnhancedMaCrossoverStrategy
        strat = EnhancedMaCrossoverStrategy()
        print(f'策略：增强均线策略')
    else:
        from src.strategy.technical import TechnicalStrategy
        strat = TechnicalStrategy()
        print(f'策略：技术指标策略')

    # 创建模拟券商
    broker = PaperBroker(initial_capital=capital)
    print(f'初始资金：{capital:,.0f} 元')

    # 创建风控
    risk = RiskController()
    print('风控规则：已加载')

    # 股票池
    stock_pool = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
    print(f'股票池：{len(stock_pool)} 只股票：{", ".join(stock_pool)}')
    print()

    # 创建交易机器人
    bot = create_trading_bot(
        broker_type='paper',
        strategy_name=strategy,
        initial_capital=capital
    )

    print('模拟交易服务运行中...')
    print('(按 Ctrl+C 停止)')
    print()

    try:
        bot.start()
    except KeyboardInterrupt:
        print()
        print('模拟交易已停止')
        broker.get_account_summary()


def main():
    parser = argparse.ArgumentParser(description='量化交易系统服务启动器')
    parser.add_argument('service', choices=['scheduler', 'paper', 'all'],
                        help='服务类型：scheduler(定时任务), paper(模拟交易), all(全部)')
    parser.add_argument('--strategy', type=str, default='optimal',
                        help='策略类型：optimal, enhanced, technical')
    parser.add_argument('--capital', type=float, default=100000,
                        help='模拟交易初始资金')
    parser.add_argument('--mode', type=str, default='conservative',
                        choices=['conservative', 'aggressive'],
                        help='配置模式：conservative(稳健版 53%), aggressive(进取版 55%)')

    args = parser.parse_args()

    if args.service == 'scheduler':
        start_scheduler()
    elif args.service == 'paper':
        start_paper_trading(strategy=args.strategy, capital=args.capital, mode=args.mode)
    elif args.service == 'all':
        print('启动全部服务...')
        print()
        # 先启动模拟交易
        start_paper_trading(strategy=args.strategy, capital=args.capital, mode=args.mode)


if __name__ == '__main__':
    main()
