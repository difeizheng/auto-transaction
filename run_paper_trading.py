"""
模拟盘监控运行脚本
用于模拟盘 1-2 周的实盘前验证

功能：
- 自动运行策略
- 实时监控市场
- 生成交易信号
- 记录运行日志
- 异常自动重启
"""
import os
import sys
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import config.settings as settings
from config.logging_config import trader_logger
from src.trader.broker_api import PaperBroker, get_broker
from src.trader.risk_control import RiskController
from src.strategy.technical import TechnicalStrategy
from src.data_collector.data_manager import data_manager
from src.trader.scheduler import TradingScheduler
from src.utils.dingtalk_notifier import DingTalkNotifier

# 全局标志
running = True


def signal_handler(signum, frame):
    """信号处理"""
    global running
    trader_logger.info(f"收到信号 {signum}, 准备退出...")
    running = False


def check_market_status():
    """检查市场状态"""
    from datetime import datetime, time as dt_time

    now = datetime.now()

    # 周末休市
    if now.weekday() >= 5:
        return "weekend"

    current_time = now.time()

    if current_time < dt_time(9, 30):
        return "pre_market"
    elif current_time < dt_time(11, 30):
        return "morning_trading"
    elif current_time < dt_time(13, 0):
        return "lunch_break"
    elif current_time < dt_time(15, 0):
        return "afternoon_trading"
    else:
        return "closed"


def run_simulation_day():
    """运行一个交易日的模拟"""
    trader_logger.info("=" * 60)
    trader_logger.info("模拟盘监控启动")
    trader_logger.info("=" * 60)

    # 初始化组件
    broker = get_broker(broker_type='paper', initial_capital=20000)
    if not broker.connect():
        trader_logger.error("券商连接失败")
        return False

    risk_controller = RiskController()
    strategy = TechnicalStrategy()
    scheduler = TradingScheduler()

    # 发送启动通知
    if settings.ENABLE_DINGDING_NOTIFY:
        try:
            notifier = DingTalkNotifier()
            notifier.send_text(
                f"【模拟盘启动】\n"
                f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"初始资金：20000 元\n"
                f"策略：{strategy.name}"
            )
        except Exception as e:
            trader_logger.warning(f"发送通知失败：{e}")

    # 统计信息
    stats = {
        'total_signals': 0,
        'buy_signals': 0,
        'sell_signals': 0,
        'trades_executed': 0,
        'start_time': datetime.now()
    }

    # 监控循环
    last_log_time = datetime.now()
    log_interval = timedelta(minutes=30)  # 每 30 分钟记录一次

    while running:
        try:
            market_status = check_market_status()

            if market_status in ['morning_trading', 'afternoon_trading']:
                # 交易时间：执行监控
                current_date = datetime.now().strftime('%Y%m%d')
                current_time = datetime.now().strftime('%H:%M:%S')

                # 获取股票池数据
                stock_pool = settings.DEFAULT_STOCK_POOL
                data_dict = {}

                for ts_code in stock_pool:
                    df = data_manager.get_daily_quotes(ts_code, '20260101', current_date)
                    if not df.empty:
                        data_dict[ts_code] = df

                if data_dict:
                    # 运行策略
                    signals = strategy.on_bar(data_dict, current_date)

                    if signals:
                        stats['total_signals'] += len(signals)
                        for sig in signals:
                            if sig.direction == 'buy':
                                stats['buy_signals'] += 1
                            else:
                                stats['sell_signals'] += 1

                            # 风控检查
                            account = broker.get_account_info()
                            positions = {
                                p['ts_code']: {'market_value': p.get('market_value', 0),
                                               'volume': p.get('volume', 0),
                                               'avg_cost': p.get('avg_cost', 0)}
                                for p in broker.get_positions()
                            }

                            passed, reason = risk_controller.check_order(
                                sig.ts_code, sig.direction, sig.price, sig.volume,
                                account.get('total_asset', 0), positions
                            )

                            if passed:
                                # 执行交易
                                order_id = broker.submit_order(
                                    ts_code=sig.ts_code,
                                    direction=sig.direction,
                                    price=sig.price,
                                    volume=sig.volume,
                                    strategy_name=strategy.name
                                )

                                if order_id:
                                    stats['trades_executed'] += 1
                                    trader_logger.info(
                                        f"[交易执行] {sig.ts_code} {sig.direction} "
                                        f"{sig.volume}@{sig.price:.2f} - {order_id}"
                                    )
                            else:
                                trader_logger.warning(f"风控阻止：{sig.ts_code} - {reason}")

                # 定期日志
                if datetime.now() - last_log_time >= log_interval:
                    account = broker.get_account_info()
                    positions = broker.get_positions()

                    trader_logger.info(
                        f"[模拟盘状态] "
                        f"总资产：{account.get('total_asset', 0):.2f}, "
                        f"可用资金：{account.get('available_cash', 0):.2f}, "
                        f"持仓数：{len(positions)}, "
                        f"今日信号：{stats['total_signals']}, "
                        f"成交笔数：{stats['trades_executed']}"
                    )
                    last_log_time = datetime.now()

            elif market_status == 'weekend':
                trader_logger.info("周末休市，暂停监控")
                time.sleep(300)  # 周末每 5 分钟检查一次
                continue

            else:
                # 非交易时间
                trader_logger.debug(f"非交易时间：{market_status}")

            # 等待下一次检查
            time.sleep(60)  # 每分钟检查一次

        except KeyboardInterrupt:
            trader_logger.info("用户中断")
            break
        except Exception as e:
            trader_logger.error(f"监控循环异常：{e}", exc_info=True)
            time.sleep(60)  # 异常后等待 1 分钟

    # 清理
    broker.disconnect()

    # 发送结束通知
    if settings.ENABLE_DINGDING_NOTIFY:
        try:
            notifier = DingTalkNotifier()
            runtime = datetime.now() - stats['start_time']
            notifier.send_text(
                f"【模拟盘停止】\n"
                f"运行时长：{runtime}\n"
                f"总信号数：{stats['total_signals']}\n"
                f"买入信号：{stats['buy_signals']}\n"
                f"卖出信号：{stats['sell_signals']}\n"
                f"成交笔数：{stats['trades_executed']}"
            )
        except Exception as e:
            trader_logger.warning(f"发送通知失败：{e}")

    return True


def main():
    """主函数"""
    global running

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    trader_logger.info("=" * 60)
    trader_logger.info("模拟盘监控系统")
    trader_logger.info("=" * 60)
    trader_logger.info(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    trader_logger.info(f"运行模式：{'实盘' if settings.REAL_TRADING_MODE else '模拟'}")
    trader_logger.info(f"初始资金：20000 元")
    trader_logger.info(f"钉钉通知：{'开启' if settings.ENABLE_DINGDING_NOTIFY else '关闭'}")
    trader_logger.info("=" * 60)

    try:
        run_simulation_day()
    except Exception as e:
        trader_logger.error(f"主函数异常：{e}", exc_info=True)
        sys.exit(1)

    trader_logger.info("模拟盘监控已停止")


if __name__ == "__main__":
    main()
