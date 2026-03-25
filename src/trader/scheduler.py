"""
自动化调度模块
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, time
from typing import Callable, Optional, Dict, Any
import threading

import config.settings as settings
from config.logging_config import trader_logger


class TradingScheduler:
    """交易调度器"""

    def __init__(self, use_async: bool = False):
        """
        初始化调度器

        Args:
            use_async: 是否使用异步调度器
        """
        if use_async:
            self.scheduler = AsyncIOScheduler()
        else:
            self.scheduler = BlockingScheduler()

        self.jobs: Dict[str, Any] = {}
        self._is_running = False

    def add_job(
        self,
        func: Callable,
        trigger: str = 'cron',
        job_id: Optional[str] = None,
        **trigger_args
    ):
        """
        添加任务

        Args:
            func: 执行函数
            trigger: 触发器类型 (cron/interval/date)
            job_id: 任务 ID
            **trigger_args: 触发器参数
        """
        if trigger == 'cron':
            trig = CronTrigger(**trigger_args)
        elif trigger == 'interval':
            trig = IntervalTrigger(**trigger_args)
        else:
            trig = trigger_args.get('trigger')

        job = self.scheduler.add_job(
            func,
            trigger=trig,
            id=job_id or func.__name__,
            replace_existing=True
        )

        self.jobs[job.id] = job
        trader_logger.info(f"添加任务：{job.id}")

    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self.jobs:
            self.scheduler.remove_job(job_id)
            del self.jobs[job_id]
            trader_logger.info(f"移除任务：{job_id}")

    def start(self):
        """启动调度器"""
        if not self._is_running:
            self._is_running = True
            trader_logger.info("启动调度器...")
            self.scheduler.start()

    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        if self._is_running:
            self._is_running = False
            trader_logger.info("关闭调度器...")
            self.scheduler.shutdown(wait=wait)

    def is_running(self) -> bool:
        """是否运行中"""
        return self._is_running


class TradingBot:
    """交易机器人"""

    def __init__(
        self,
        broker,
        strategy,
        data_manager,
        risk_controller
    ):
        """
        初始化交易机器人

        Args:
            broker: 券商接口
            strategy: 策略实例
            data_manager: 数据管理器
            risk_controller: 风险控制器
        """
        self.broker = broker
        self.strategy = strategy
        self.data_manager = data_manager
        self.risk_controller = risk_controller

        self.scheduler = TradingScheduler()

        # 状态
        self.market_open = False
        self.today_trades = []

    def setup_jobs(self):
        """设置定时任务"""
        from datetime import datetime, timedelta

        # 盘前准备（交易日 08:30）
        self.scheduler.add_job(
            self.pre_market_prepare,
            trigger='cron',
            job_id='pre_market',
            hour=8,
            minute=30,
            day_of_week='mon-fri'
        )

        # 盘中监控 (每 5 分钟，从下一个整 5 分钟开始)
        now = datetime.now()
        next_run = now.replace(second=0, microsecond=0)
        # 计算下一个 5 分钟倍数时间点
        if next_run.minute % 5 != 0:
            next_run += timedelta(minutes=(5 - next_run.minute % 5))

        self.scheduler.add_job(
            self.intra_market_monitor,
            trigger='interval',
            job_id='intra_market',
            minutes=5,
            start_date=next_run,
            end_date=datetime.now().replace(hour=15, minute=5)
        )

        # 盘后分析（交易日 16:00）
        self.scheduler.add_job(
            self.post_market_analysis,
            trigger='cron',
            job_id='post_market',
            hour=16,
            minute=0,
            day_of_week='mon-fri'
        )

        # 风控检查 (每小时)
        self.scheduler.add_job(
            self.risk_check,
            trigger='interval',
            job_id='risk_check',
            hours=1,
            start_date=datetime.now().replace(minute=0, second=0),
            end_date=datetime.now().replace(hour=15, minute=0)
        )

        trader_logger.info(f"定时任务设置完成，盘中监控下次执行：{next_run}")

    def pre_market_prepare(self):
        """盘前准备"""
        trader_logger.info("=== 开始盘前准备 ===")

        # 1. 检查账户状态
        account_info = self.broker.get_account_info()
        trader_logger.info(f"账户状态：{account_info}")

        # 2. 更新持仓价格 (使用昨日收盘价)
        for position in self.broker.get_positions():
            ts_code = position.get('ts_code')
            # 获取最新数据
            df = self.data_manager.get_daily_quotes(ts_code)
            if not df.empty:
                last_close = df.iloc[-1]['close']
                self.broker.update_market_price(ts_code, last_close)

        # 3. 检查止损止盈
        stop_orders = self.broker.check_stop_loss_take_profit()
        for order in stop_orders:
            trader_logger.info(f"止损止盈订单：{order}")

        # 4. 重置每日计数
        self.risk_controller.reset_daily()

        trader_logger.info("=== 盘前准备完成 ===")

    def intra_market_monitor(self):
        """盘中监控 - 每 5 分钟执行一次"""
        from datetime import datetime
        from src.utils.database import db
        import json

        monitor_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_date = datetime.now().strftime("%Y%m%d")

        # 监控日志数据
        log_data = {
            "monitor_time": monitor_time,
            "market_state": "open" if self.market_open else "closed",
            "stock_pool": ",".join(['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']),
            "stocks_count": 0,
            "signals_count": 0,
            "buy_signals_count": 0,
            "sell_signals_count": 0,
            "trades_executed": 0,
            "buy_orders": "",
            "sell_orders": "",
            "error_message": ""
        }

        try:
            if not self.market_open:
                trader_logger.debug("市场未开盘，跳过监控")
                log_data["error_message"] = "市场未开盘"
                self._save_monitoring_log(db, log_data)
                return

            trader_logger.info("=== 盘中监控 ===")

            # 1. 获取当日数据（模拟实时行情）
            stock_pool = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
            data_dict = {}

            for ts_code in stock_pool:
                # 获取最近 60 天数据用于策略计算
                df = self.data_manager.get_daily_quotes(ts_code, '20260101', current_date)
                if not df.empty:
                    data_dict[ts_code] = df
                    trader_logger.debug(f"{ts_code}: 获取到 {len(df)} 条数据")
                else:
                    trader_logger.warning(f"{ts_code}: 无数据")

            log_data["stocks_count"] = len(data_dict)

            if not data_dict:
                trader_logger.warning("未获取到任何股票数据")
                log_data["error_message"] = "未获取到任何股票数据"
                self._save_monitoring_log(db, log_data)
                return

            trader_logger.info(f"获取到 {len(data_dict)} 只股票数据")

            # 2. 调用策略生成信号
            trader_logger.info(f"调用策略 on_bar 方法...")
            signals = self.strategy.on_bar(data_dict, current_date)

            log_data["signals_count"] = len(signals) if signals else 0

            if not signals:
                trader_logger.info("策略未产生信号")
                self._save_monitoring_log(db, log_data)
                return

            trader_logger.info(f"策略产生 {len(signals)} 个信号")

            # 3. 统计买卖信号
            buy_signals = []
            sell_signals = []
            trades_executed = 0

            # 4. 执行信号
            for signal in signals:
                trader_logger.info(f"信号：{signal.ts_code} {signal.direction} {signal.volume}@{signal.price:.2f} - {signal.reason}")

                # 检查风控
                if not self.risk_controller.can_trade(
                    self.broker.get_account_info(),
                    {signal.ts_code: signal.volume}
                ):
                    trader_logger.warning(f"风控阻止交易：{signal.ts_code}")
                    continue

                # 提交订单
                if signal.direction == 'buy':
                    order_id = self.broker.submit_order(
                        ts_code=signal.ts_code,
                        direction='buy',
                        price=signal.price,
                        volume=signal.volume,
                        strategy_name=self.strategy.name
                    )
                    if order_id:
                        trader_logger.info(f"买入订单提交成功：{order_id}")
                        trades_executed += 1
                        buy_signals.append(f"{signal.ts_code}@{signal.price:.2f}x{signal.volume}")
                        # 发送钉钉通知
                        self._send_trade_notification(signal.ts_code, 'buy', signal.price, signal.volume, self.strategy.name)
                elif signal.direction == 'sell':
                    order_id = self.broker.submit_order(
                        ts_code=signal.ts_code,
                        direction='sell',
                        price=signal.price,
                        volume=signal.volume,
                        strategy_name=self.strategy.name
                    )
                    if order_id:
                        trader_logger.info(f"卖出订单提交成功：{order_id}")
                        trades_executed += 1
                        sell_signals.append(f"{signal.ts_code}@{signal.price:.2f}x{signal.volume}")
                        # 发送钉钉通知
                        self._send_trade_notification(signal.ts_code, 'sell', signal.price, signal.volume, self.strategy.name)

            # 更新日志数据
            log_data["buy_signals_count"] = len(buy_signals)
            log_data["sell_signals_count"] = len(sell_signals)
            log_data["trades_executed"] = trades_executed
            log_data["buy_orders"] = ",".join(buy_signals) if buy_signals else ""
            log_data["sell_orders"] = ",".join(sell_signals) if sell_signals else ""

            # 保存监控日志
            self._save_monitoring_log(db, log_data)

        except Exception as e:
            trader_logger.error(f"盘中监控执行失败：{e}", exc_info=True)
            log_data["error_message"] = str(e)
            self._save_monitoring_log(db, log_data)

    def _send_trade_notification(self, ts_code: str, direction: str, price: float, volume: int, strategy_name: str):
        """发送交易通知到钉钉"""
        try:
            from src.utils.dingtalk_notifier import DingTalkNotifier
            notifier = DingTalkNotifier()
            if notifier.enabled and notifier.webhook:
                notifier.send_trade_notification(ts_code, direction, price, volume, strategy_name)
        except Exception as e:
            trader_logger.error(f"发送钉钉通知失败：{e}")

    def _save_monitoring_log(self, db, log_data: dict):
        """保存监控日志到数据库"""
        try:
            sql = """
                INSERT INTO monitoring_logs
                (monitor_time, market_state, stock_pool, stocks_count, signals_count,
                 buy_signals_count, sell_signals_count, trades_executed, buy_orders, sell_orders, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            db.execute(sql, (
                log_data["monitor_time"],
                log_data["market_state"],
                log_data["stock_pool"],
                log_data["stocks_count"],
                log_data["signals_count"],
                log_data["buy_signals_count"],
                log_data["sell_signals_count"],
                log_data["trades_executed"],
                log_data["buy_orders"],
                log_data["sell_orders"],
                log_data["error_message"]
            ))
            trader_logger.debug(f"监控日志已保存：{log_data['monitor_time']}")
        except Exception as e:
            trader_logger.error(f"保存监控日志失败：{e}")

    def post_market_analysis(self):
        """盘后分析"""
        trader_logger.info("=== 开始盘后分析 ===")

        self.market_open = False

        # 1. 获取最终账户状态
        account_info = self.broker.get_account_info()
        trader_logger.info(f"账户状态：{account_info}")

        # 2. 计算今日盈亏
        positions = self.broker.get_positions()
        total_pnl = sum(pos.get('profit_loss', 0) for pos in positions)
        trader_logger.info(f"今日盈亏：{total_pnl:.2f}")

        # 3. 生成风险报告
        report = self.risk_controller.generate_risk_report(
            account_info.get('total_asset', 0),
            {pos['ts_code']: pos for pos in positions}
        )
        trader_logger.info(report)

        # 4. 更新数据
        # 获取并保存最新行情数据

        trader_logger.info("=== 盘后分析完成 ===")

    def risk_check(self):
        """风控检查"""
        account_info = self.broker.get_account_info()
        positions = {
            pos['ts_code']: pos
            for pos in self.broker.get_positions()
        }

        metrics = self.risk_controller.get_risk_metrics(
            account_info.get('total_asset', 0),
            positions
        )

        if metrics.is_trading_halted:
            trader_logger.warning(f"交易暂停：{metrics.halt_reason}")

    def start(self):
        """启动交易机器人"""
        trader_logger.info("启动交易机器人...")

        # 连接券商
        if not self.broker.connect():
            trader_logger.error("券商连接失败")
            return

        # 设置定时任务
        self.setup_jobs()

        # 标记市场状态
        current_time = datetime.now().time()
        market_open_time = time(9, 30)
        market_close_time = time(15, 0)

        if market_open_time <= current_time <= market_close_time:
            self.market_open = True
            trader_logger.info("市场已开盘")

        # 启动调度器
        self.scheduler.start()

    def stop(self):
        """停止交易机器人"""
        trader_logger.info("停止交易机器人...")
        self.scheduler.shutdown()
        self.broker.disconnect()


def create_trading_bot(
    broker_type: str = "paper",
    strategy_name: str = "technical",
    initial_capital: float = None
):
    """
    创建交易机器人

    Args:
        broker_type: 券商类型
        strategy_name: 策略名称
        initial_capital: 初始资金

    Returns:
        TradingBot 实例
    """
    from src.data_collector.data_manager import data_manager
    from src.trader.broker_api import get_broker
    from src.trader.risk_control import RiskController
    from src.strategy.technical import TechnicalStrategy
    from src.strategy.multi_factor import MultiFactorStrategy

    # 创建券商
    broker = get_broker(broker_type, initial_capital=initial_capital)

    # 创建策略
    if strategy_name == "technical":
        strategy = TechnicalStrategy()
    elif strategy_name == "multi_factor":
        strategy = MultiFactorStrategy(top_n=5, rebalance_days=5)
    else:
        strategy = TechnicalStrategy()

    # 创建风控
    risk_controller = RiskController()

    # 创建数据管理器
    dm = data_manager

    # 创建交易机器人
    bot = TradingBot(broker, strategy, dm, risk_controller)

    return bot


if __name__ == "__main__":
    # 测试调度器
    print("创建交易机器人...")

    bot = create_trading_bot(
        broker_type="paper",
        strategy_name="technical",
        initial_capital=20000
    )

    # 注意：实际运行时使用 start() 启动
    # bot.start()
