"""
模拟盘监控任务脚本
定期检查模拟盘状态并发送钉钉通知
"""
import sys
from pathlib import Path
from datetime import datetime
import sqlite3

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.database import Database
from src.utils.dingtalk_notifier import DingTalkNotifier
from config.logging_config import trader_logger


def get_paper_trading_stats(days: int = 1):
    """
    获取模拟盘统计数据

    Args:
        days: 统计天数

    Returns:
        统计数据字典
    """
    db = Database()

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # 获取最新账户状态 (从 accounts 表)
            cursor.execute("""
                SELECT total_asset, available_cash, frozen_cash, total_position_value
                FROM accounts
                ORDER BY created_at DESC
                LIMIT 1
            """)
            account = cursor.fetchone()

            # 获取今日成交笔数 (从 orders 表)
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*) as trade_count, SUM(price * volume) as total_amount
                FROM orders
                WHERE DATE(created_at) = ? AND status = 'filled'
            """, (today,))
            today_trades = cursor.fetchone()

            # 获取持仓数量
            cursor.execute("""
                SELECT COUNT(*) FROM positions WHERE volume > 0
            """)
            position_count = cursor.fetchone()[0]

            # 获取最近 N 天的监控历史统计
            cursor.execute("""
                SELECT
                    COUNT(*) as monitor_count,
                    SUM(signals_count) as total_signals,
                    SUM(buy_signals_count) as buy_signals,
                    SUM(sell_signals_count) as sell_signals,
                    SUM(trades_executed) as total_trades
                FROM monitoring_logs
                WHERE DATE(monitor_time) >= DATE('now', ?)
            """, (f'-{days} days',))
            monitor_stats = cursor.fetchone()

            # 获取持仓盈亏
            cursor.execute("""
                SELECT SUM(profit_loss) as total_profit
                FROM positions
                WHERE volume > 0
            """)
            profit_result = cursor.fetchone()

            return {
                'total_asset': account[0] if account else 100000,
                'available_cash': account[1] if account else 100000,
                'frozen_cash': account[2] if account else 0,
                'position_value': account[3] if account else 0,
                'position_count': position_count,
                'today_trades': today_trades[0] if today_trades else 0,
                'today_amount': today_trades[1] if today_trades else 0,
                'monitor_count': monitor_stats[0] if monitor_stats else 0,
                'total_signals': monitor_stats[1] if monitor_stats else 0,
                'buy_signals': monitor_stats[2] if monitor_stats else 0,
                'sell_signals': monitor_stats[3] if monitor_stats else 0,
                'total_trades': monitor_stats[4] if monitor_stats else 0,
                'today_profit': profit_result[0] if profit_result else 0,
            }
    except Exception as e:
        trader_logger.error(f"获取统计数据失败：{e}")
        # 返回默认值
        return {
            'total_asset': 100000,
            'available_cash': 100000,
            'position_value': 0,
            'position_count': 0,
            'today_trades': 0,
            'today_amount': 0,
            'monitor_count': 0,
            'total_signals': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'total_trades': 0,
            'today_profit': 0,
        }


def send_daily_summary():
    """发送每日总结通知"""
    stats = get_paper_trading_stats(days=1)
    if not stats:
        return False

    notifier = DingTalkNotifier()

    # 计算收益率
    initial_capital = 100000  # 初始资金
    total_return = ((stats['total_asset'] - initial_capital) / initial_capital) * 100

    # 判断盈亏颜色
    if total_return >= 0:
        profit_emoji = "🟢"
    else:
        profit_emoji = "🔴"

    # 计算胜率
    if stats['buy_signals'] > 0:
        win_rate = (stats['total_trades'] / stats['buy_signals']) * 100 if stats['buy_signals'] > 0 else 0
    else:
        win_rate = 0

    markdown_text = f"""## 📊 模拟盘每日总结

| 指标 | 数值 |
|------|------|
| 日期 | {datetime.now().strftime('%Y-%m-%d')} |
| 总资产 | ¥{stats['total_asset']:,.2f} |
| 可用资金 | ¥{stats['available_cash']:,.2f} |
| 持仓市值 | ¥{stats['position_value']:,.2f} |
| 持仓数量 | {stats['position_count']} 只 |
| 今日成交 | {stats['today_trades']} 笔 |
| 总收益 | {profit_emoji} {total_return:+.2f}% |

---
*量化交易系统自动通知*"""

    title = f"📊 模拟盘总结 - {datetime.now().strftime('%Y-%m-%d')}"
    return notifier.send_markdown(title, markdown_text, at_all=False)


def send_status_check():
    """发送状态检查通知（每 4 小时）"""
    stats = get_paper_trading_stats(days=1)
    if not stats:
        return False

    notifier = DingTalkNotifier()

    # 计算收益率
    initial_capital = 100000
    total_return = ((stats['total_asset'] - initial_capital) / initial_capital) * 100

    # 根据收益决定颜色
    if total_return >= 0:
        status_emoji = "✅"
    elif total_return >= -3:
        status_emoji = "⚠️"
    else:
        status_emoji = "🔴"

    content = f"""【模拟盘状态检查】
时间：{datetime.now().strftime('%m-%d %H:%M')}
总资产：¥{stats['total_asset']:,.2f}
收益率：{total_return:+.2f}%
持仓：{stats['position_count']} 只
今日成交：{stats['today_trades']} 笔
状态：{status_emoji}"""

    return notifier.send_text(content, at_all=False)


def check_abnormal_conditions():
    """
    检查异常情况
    - 单日亏损超过阈值
    - 连续亏损
    - 仓位异常
    """
    stats = get_paper_trading_stats(days=1)
    if not stats:
        return

    notifier = DingTalkNotifier()
    alerts = []

    # 检查单日亏损
    initial_capital = 100000
    daily_return = ((stats['total_asset'] - initial_capital) / initial_capital) * 100

    if daily_return < -5:
        alerts.append(f"⚠️ 单日亏损超过 5%: {daily_return:.2f}%")

    # 检查仓位
    if stats['position_count'] == 0 and stats['available_cash'] > initial_capital * 0.95:
        alerts.append("⚠️ 空仓状态，资金利用率过低")

    if stats['position_value'] / stats['total_asset'] > 0.9:
        alerts.append("⚠️ 仓位过重，超过 90%")

    # 发送告警
    if alerts:
        content = f"""【模拟盘异常告警】
时间：{datetime.now().strftime('%m-%d %H:%M')}

""" + "\n".join(alerts) + """

请及时检查系统状态和策略表现。"""
        notifier.send_text(content, at_all=True)


def run_monitor():
    """运行监控任务"""
    trader_logger.info("=== 开始执行模拟盘监控任务 ===")

    # 1. 检查异常情况
    check_abnormal_conditions()

    # 2. 如果是收盘后，发送每日总结
    now = datetime.now()
    if now.hour >= 15:  # 收盘后
        send_daily_summary()
    else:
        send_status_check()

    trader_logger.info("=== 模拟盘监控任务完成 ===")


if __name__ == "__main__":
    run_monitor()
