"""
模拟盘监控运行脚本 (重构版 v1.1)
用于模拟盘 1-2 周的实盘前验证

功能：
- 接入实时价格（Sina）执行策略
- 实时更新持仓市值
- 防重复下单（T+1 信号机制）
- 每日信号生成，次日执行

重写日期：2026-03-30
"""
import os
import sys
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set

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
from src.utils.database import db
from src.data_pipeline.realtime_feed import price_cache, get_price
from src.strategy_engine.signal_scheduler import signal_scheduler, get_pending_signals
from src.performance import record_daily_performance, get_performance_summary, init_performance_tables

# 全局标志
running = True


def signal_handler(signum, frame):
    """信号处理"""
    global running
    trader_logger.info(f"收到信号 {signum}, 准备退出...")
    running = False


def check_market_status() -> str:
    """检查市场状态"""
    now = datetime.now()

    # 周末休市
    if now.weekday() >= 5:
        return "weekend"

    current_time = now.time()
    from datetime import time as dt_time

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


def get_current_price(ts_code: str) -> float:
    """
    获取当前实时价格（优化版 - 减少 API 调用）

    Args:
        ts_code: 股票代码

    Returns:
        当前价格，如果获取失败返回 0
    """
    # 1. 尝试从实时价格缓存获取（Sina，无 API 限制）
    price_data = get_price(ts_code)
    if price_data and price_data.get('price', 0) > 0:
        return price_data['price']

    # 2. 从数据库获取最近收盘价（无 API 调用）
    try:
        df = db.query("""
            SELECT close FROM daily_quotes
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT 1
        """, (ts_code,))

        if not df.empty:
            price = float(df.iloc[0]['close'])
            if price > 0:
                return price
    except Exception as e:
        trader_logger.warning(f"从数据库获取价格失败: {e}")

    # 3. 最后才调用 Tushare（避免限流）
    try:
        current_date = datetime.now().strftime('%Y%m%d')
        df = data_manager.get_daily_quotes(ts_code, current_date, current_date)
        if not df.empty:
            return float(df.iloc[-1].get('close', 0))
    except Exception as e:
        trader_logger.warning(f"Tushare 获取价格失败: {e}")

    trader_logger.warning(f"无法获取 {ts_code} 的价格，使用 0")
    return 0


def update_positions_market_value(broker: PaperBroker):
    """
    更新所有持仓的实时市值

    Args:
        broker: 券商实例
    """
    positions = broker.get_positions()
    for pos in positions:
        ts_code = pos.get('ts_code')
        if ts_code:
            current_price = get_current_price(ts_code)
            if current_price > 0:
                broker.update_market_price(ts_code, current_price)


def has_signal_today(broker: PaperBroker, ts_code: str, direction: str,
                     processed_signals: Dict[str, Set[str]]) -> bool:
    """
    检查今天是否已经处理过该股票的信号（防重复）

    Args:
        broker: 券商实例
        ts_code: 股票代码
        direction: 交易方向
        processed_signals: 已处理信号记录

    Returns:
        True 表示今天已处理过
    """
    today = datetime.now().strftime('%Y%m%d')
    key = f"{today}_{ts_code}_{direction}"
    return key in processed_signals


def record_processed_signal(processed_signals: Dict[str, Set[str]],
                            ts_code: str, direction: str):
    """
    记录已处理的信号

    Args:
        processed_signals: 信号记录字典
        ts_code: 股票代码
        direction: 交易方向
    """
    today = datetime.now().strftime('%Y%m%d')
    key = f"{today}_{ts_code}_{direction}"
    processed_signals[key] = True


def run_simulation_day():
    """运行一个交易日的模拟（重构版）"""
    trader_logger.info("=" * 60)
    trader_logger.info("模拟盘监控启动 (v1.1 - 实时价格版)")
    trader_logger.info("=" * 60)

    # 初始化性能追踪表
    init_performance_tables()

    # 初始化组件
    broker = get_broker(broker_type='paper', initial_capital=20000)
    if not broker.connect():
        trader_logger.error("券商连接失败")
        return False

    risk_controller = RiskController()
    strategy = TechnicalStrategy()
    scheduler = TradingScheduler()

    # 获取股票池
    stock_pool = settings.DEFAULT_STOCK_POOL

    # 订阅实时价格
    price_cache.subscribe(stock_pool)
    price_cache.start_background_refresh()

    # 启动信号调度器（后台线程）
    signal_scheduler.start_scheduler(check_interval=60)
    trader_logger.info("信号调度器已启动")

    # 启动每日数据更新调度器（后台线程）
    from src.data_pipeline.daily_updater import daily_scheduler
    daily_scheduler.start()
    trader_logger.info("每日数据更新调度器已启动")

    # 已处理信号记录（防止同一天重复下单）
    processed_signals: Dict[str, Set[str]] = {}

    # 今日信号生成标志（14:50 后生成，次日执行）
    today_signals_generated = False
    last_signal_date = ""

    # 今日净值记录标志（防止 15:05-15:10 窗口内重复记录）
    nav_recorded_today = False

    # 发送启动通知
    if settings.ENABLE_DINGDING_NOTIFY:
        try:
            notifier = DingTalkNotifier()
            notifier.send_text(
                f"【模拟盘启动 v1.1】\n"
                f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"初始资金：20000 元\n"
                f"策略：{strategy.name}\n"
                f"股票池：{len(stock_pool)} 只\n"
                f"价格来源：实时 (Sina)"
            )
        except Exception as e:
            trader_logger.warning(f"发送通知失败：{e}")

    # 统计信息
    stats = {
        'total_signals': 0,
        'buy_signals': 0,
        'sell_signals': 0,
        'trades_executed': 0,
        'rejected_by_t1': 0,
        'rejected_by_risk': 0,
        'start_time': datetime.now()
    }

    # 监控循环
    last_log_time = datetime.now()
    last_market_update = datetime.now()
    log_interval = timedelta(minutes=30)  # 每 30 分钟记录一次
    market_update_interval = timedelta(seconds=30)  # 每 30 秒更新市值

    trader_logger.info(f"股票池: {stock_pool}")

    while running:
        try:
            market_status = check_market_status()

            # ===== 交易时间 =====
            if market_status in ['morning_trading', 'afternoon_trading']:
                now = datetime.now()
                current_date = now.strftime('%Y%m%d')
                current_time = now.strftime('%H:%M:%S')

                # === 14:50 信号生成窗口 ===
                # 每日 14:50-15:00 生成次日信号（使用当日数据）
                if not today_signals_generated and now.hour >= 14 and now.minute >= 50:
                    trader_logger.info("=== 进入信号生成窗口 (14:50) ===")
                    # 使用信号调度器生成信号
                    signal_scheduler.generate_signals(current_date)
                    today_signals_generated = True
                    last_signal_date = current_date

                # === 9:31-9:35 信号执行窗口 ===
                # 读取昨日生成的信号并执行
                if now.hour == 9 and 31 <= now.minute <= 35:
                    # 使用信号调度器获取待执行信号
                    pending_signals = get_pending_signals(current_date)

                    if pending_signals and not today_signals_generated:
                        trader_logger.info(f"=== 进入信号执行窗口 (9:31-9:35), 待执行: {len(pending_signals)} 个 ===")

                        for sig in pending_signals:
                            # 防重复检查
                            if has_signal_today(broker, sig.ts_code, sig.direction, processed_signals):
                                trader_logger.debug(
                                    f"跳过重复信号: {sig.ts_code} {sig.direction} (今日已处理)"
                                )
                                continue

                            # 获取实时价格（开盘价或实时价）
                            current_price = get_current_price(sig.ts_code)
                            if current_price <= 0:
                                trader_logger.warning(
                                    f"无法获取价格，跳过信号: {sig.ts_code}"
                                )
                                continue

                            # 使用实时价格执行
                            sig_price = current_price
                            sig_volume = sig.volume

                            # 更新统计
                            if sig.direction == 'buy':
                                stats['buy_signals'] += 1
                            else:
                                stats['sell_signals'] += 1

                            # 风控检查
                            account = broker.get_account_info()
                            positions = {
                                p['ts_code']: {
                                    'market_value': p.get('market_value', 0),
                                    'volume': p.get('volume', 0),
                                    'avg_cost': p.get('avg_cost', 0)
                                }
                                for p in broker.get_positions()
                            }

                            passed, reason = risk_controller.check_order(
                                sig.ts_code, sig.direction, sig_price, sig_volume,
                                account.get('total_asset', 0), positions
                            )

                            if passed:
                                # 执行交易
                                order_id = broker.submit_order(
                                    ts_code=sig.ts_code,
                                    direction=sig.direction,
                                    price=sig_price,
                                    volume=sig_volume,
                                    strategy_name=sig.strategy_name
                                )

                                if order_id:
                                    stats['trades_executed'] += 1
                                    stats['total_signals'] += 1
                                    record_processed_signal(
                                        processed_signals, sig.ts_code, sig.direction
                                    )

                                    # 标记信号已执行
                                    signal_scheduler.mark_signal_executed(
                                        sig.ts_code, current_date, sig_price, order_id
                                    )

                                    trader_logger.info(
                                        f"[信号执行] {sig.ts_code} {sig.direction} "
                                        f"{sig_volume}@{sig_price:.2f} - {order_id}"
                                    )
                            else:
                                stats['rejected_by_risk'] += 1
                                trader_logger.warning(f"风控阻止：{sig.ts_code} - {reason}")

                        # 标记本次执行已完成
                        today_signals_generated = True

                # === 盘中实时市值更新 ===
                if now - last_market_update >= market_update_interval:
                    update_positions_market_value(broker)
                    last_market_update = now

                # === 定期日志输出 ===
                if now - last_log_time >= log_interval:
                    account = broker.get_account_info()
                    positions = broker.get_positions()

                    # 获取持仓实时价格
                    position_details = []
                    for pos in positions:
                        ts = pos.get('ts_code')
                        realtime_price = get_current_price(ts) if ts else 0
                        if realtime_price > 0:
                            pos_market_value = pos.get('volume', 0) * realtime_price
                            pos_cost = pos.get('volume', 0) * pos.get('avg_cost', 0)
                            pnl = pos_market_value - pos_cost
                            position_details.append(
                                f"{ts}@{realtime_price:.2f}({pnl:+.0f})"
                            )

                    trader_logger.info(
                        f"[模拟盘状态] "
                        f"总资产：{account.get('total_asset', 0):.2f}, "
                        f"可用资金：{account.get('available_cash', 0):.2f}, "
                        f"持仓数：{len(positions)}, "
                        f"持仓：{', '.join(position_details) if position_details else '无'}, "
                        f"今日信号：{stats['total_signals']}, "
                        f"成交笔数：{stats['trades_executed']}, "
                        f"数据源：{price_cache.get_stats().get('current_source', 'N/A')}"
                    )
                    last_log_time = now

            elif market_status == 'weekend':
                trader_logger.info("周末休市，暂停监控")
                time.sleep(300)  # 周末每 5 分钟检查一次
                continue

            elif market_status == "pre_market":
                # 每天 8:30 重置信号生成标志（新交易日开始）
                now = datetime.now()
                if now.hour == 8 and now.minute == 30:
                    today_signals_generated = False
                    nav_recorded_today = False  # 重置净值记录标志
                    trader_logger.info("新交易日开始，重置信号状态")

            # === 15:05 每日净值记录 + 钉钉日报 ===
            now = datetime.now()
            if market_status == "closed" and now.hour == 15 and 5 <= now.minute <= 10 and not nav_recorded_today:
                nav_recorded_today = True  # 标记今日已记录，防止重复
                # 记录每日净值
                account = broker.get_account_info()
                record_daily_performance(account.get('total_asset', 0))

                # 获取绩效摘要
                summary = get_performance_summary(30)
                if summary:
                    trader_logger.info(
                        f"[绩效摘要] 净值: {summary.get('current_nav', 1):.4f}, "
                        f"累计: {summary.get('total_return', 0):.2f}%, "
                        f"年化: {summary.get('annualized_return', 0):.2f}%, "
                        f"回撤: {summary.get('max_drawdown', 0):.2f}%"
                    )

                    # 发送每日日报
                    if settings.ENABLE_DINGDING_NOTIFY:
                        try:
                            notifier = DingTalkNotifier()

                            # 获取持仓信息
                            positions = broker.get_positions()
                            position_count = len(positions)

                            # 计算当日交易次数（从统计中获取）
                            today_trades = stats.get('trades_executed', 0)
                            total_profit = account.get('total_asset', 0) - 20000
                            win_rate = summary.get('win_rate', 0)

                            # 发送每日总结
                            profit_color = "🟢" if total_profit >= 0 else "🔴"
                            notifier.send_markdown(
                                title=f"📊 每日总结 - {now.strftime('%Y-%m-%d')}",
                                text=f"""## 📊 每日交易总结

| 指标 | 数值 |
|------|------|
| 日期 | {now.strftime('%Y-%m-%d')} |
| 总资产 | ¥{account.get('total_asset', 0):,.2f} |
| 净值 | {summary.get('current_nav', 1):.4f} |
| 累计收益 | {summary.get('total_return', 0):.2f}% |
| 年化收益 | {summary.get('annualized_return', 0):.2f}% |
| 夏普比率 | {summary.get('sharpe_ratio', 0)} |
| 最大回撤 | {summary.get('max_drawdown', 0):.2f}% |
| 胜率 | {win_rate:.1f}% |
| 今日交易 | {today_trades} 笔 |
| 当前持仓 | {position_count} 只 |

---
*量化交易系统自动通知*""",
                                at_all=False
                            )

                            # 检查回撤告警（超过 5% 触发）
                            max_dd = summary.get('max_drawdown', 0)
                            if max_dd > 5:
                                notifier.send_markdown(
                                    title=f"⚠️ 回撤告警 - {max_dd:.1f}%",
                                    text=f"""## ⚠️ 最大回撤告警

| 指标 | 数值 |
|------|------|
| 当前回撤 | {max_dd:.1f}% |
| 触发阈值 | 5% |
| 当前净值 | {summary.get('current_nav', 1):.4f} |
| 建议 | 请检查策略是否正常运行 |

---
*量化交易系统自动通知*""",
                                    at_all=True
                                )

                        except Exception as e:
                            trader_logger.warning(f"发送钉钉日报失败: {e}")

            # 等待下一次检查
            time.sleep(30)  # 30 秒检查一次（盘中）

        except KeyboardInterrupt:
            trader_logger.info("用户中断")
            break
        except Exception as e:
            trader_logger.error(f"监控循环异常：{e}", exc_info=True)
            time.sleep(60)  # 异常后等待 1 分钟

    # 清理
    price_cache.stop_background_refresh()
    signal_scheduler.stop_scheduler()
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
                f"成交笔数：{stats['trades_executed']}\n"
                f"风控阻止：{stats['rejected_by_risk']}"
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
    trader_logger.info("模拟盘监控系统 (v1.1 - 实时价格版)")
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