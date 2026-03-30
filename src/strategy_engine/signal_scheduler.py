"""
信号调度器
控制信号生成时机：14:50 生成次日信号，次日 9:31 执行

功能：
- 盘后 14:50-15:00 生成次日交易信号
- 信号持久化到数据库
- 次日 9:31-9:35 执行待执行信号
- 信号过期自动处理
"""
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import asdict

from config.logging_config import trader_logger
from src.utils.database import db
from src.data_collector.data_manager import data_manager
from src.strategy.technical import TechnicalStrategy
from src.strategy_engine.signal import TradingSignal, SIGNAL_STATUS_PENDING, SIGNAL_STATUS_EXECUTED, SIGNAL_STATUS_EXPIRED


class SignalScheduler:
    """信号调度器"""

    def __init__(self, stock_pool: List[str] = None):
        """
        初始化信号调度器

        Args:
            stock_pool: 股票池列表
        """
        import config.settings as settings
        self.stock_pool = stock_pool or settings.DEFAULT_STOCK_POOL
        self.strategy = TechnicalStrategy()

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 今日信号生成状态
        self._signals_generated_today = False
        self._last_signal_date = ""

        trader_logger.info(f"SignalScheduler 初始化完成，股票池: {len(self.stock_pool)} 只")

    def generate_signals(self, signal_date: str = None) -> List[TradingSignal]:
        """
        生成交易信号（在 14:50 调用）

        Args:
            signal_date: 信号生成日期，默认今天

        Returns:
            信号列表
        """
        signal_date = signal_date or datetime.now().strftime('%Y%m%d')
        self._signals_generated_today = True
        self._last_signal_date = signal_date

        trader_logger.info("=" * 60)
        trader_logger.info(f"开始生成信号，日期: {signal_date}")
        trader_logger.info("=" * 60)

        # 获取所有股票的最近 N 天数据
        # 使用 60 天数据确保有足够历史计算指标
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
        end_date = signal_date

        data_dict = {}
        for ts_code in self.stock_pool:
            df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
            if df is not None and not df.empty and len(df) >= 20:
                data_dict[ts_code] = df
            else:
                trader_logger.debug(f"{ts_code} 数据不足，跳过")

        if not data_dict:
            trader_logger.warning("没有足够数据生成信号")
            return []

        # 运行策略生成信号
        signals = self.strategy.on_bar(data_dict, signal_date)

        # 转换为 TradingSignal 对象
        trading_signals = []
        for sig in signals:
            # 计算执行日期（次日）
            execute_date = (datetime.strptime(signal_date, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')

            trading_sig = TradingSignal(
                ts_code=sig.ts_code,
                direction=sig.direction,
                signal_date=signal_date,
                execute_date=execute_date,
                target_price=sig.price,
                volume=sig.volume if hasattr(sig, 'volume') else 100,
                confidence=1.0,
                strategy_name=self.strategy.name,
                reason=f"策略信号: {sig.direction}",
                status=SIGNAL_STATUS_PENDING
            )
            trading_signals.append(trading_sig)

        # 保存信号到数据库
        self._save_signals(trading_signals)

        trader_logger.info(f"信号生成完成，共 {len(trading_signals)} 个信号")
        for sig in trading_signals:
            trader_logger.info(f"  {sig.ts_code} {sig.direction} @ {sig.target_price:.2f} (执行日期: {sig.execute_date})")

        return trading_signals

    def _save_signals(self, signals: List[TradingSignal]):
        """保存信号到数据库"""
        for sig in signals:
            try:
                db.execute("""
                    INSERT OR REPLACE INTO signals
                    (ts_code, direction, signal_date, execute_date, target_price, volume,
                     confidence, strategy_name, reason, status, executed_price, executed_time, order_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sig.ts_code,
                    sig.direction,
                    sig.signal_date,
                    sig.execute_date,
                    sig.target_price,
                    sig.volume,
                    sig.confidence,
                    sig.strategy_name,
                    sig.reason,
                    sig.status,
                    sig.executed_price,
                    sig.executed_time,
                    sig.order_id
                ))
            except Exception as e:
                trader_logger.error(f"保存信号失败: {e}")

    def get_pending_signals(self, execute_date: str = None) -> List[TradingSignal]:
        """
        获取待执行的信号

        Args:
            execute_date: 执行日期，默认今天

        Returns:
            待执行信号列表
        """
        execute_date = execute_date or datetime.now().strftime('%Y%m%d')

        try:
            df = db.query("""
                SELECT * FROM signals
                WHERE execute_date = ? AND status = ?
                ORDER BY confidence DESC
            """, (execute_date, SIGNAL_STATUS_PENDING))

            if df.empty:
                return []

            signals = []
            for _, row in df.iterrows():
                sig = TradingSignal(
                    ts_code=row['ts_code'],
                    direction=row['direction'],
                    signal_date=row['signal_date'],
                    execute_date=row['execute_date'],
                    target_price=row['target_price'],
                    volume=row['volume'],
                    confidence=row['confidence'],
                    strategy_name=row['strategy_name'],
                    reason=row['reason'],
                    status=row['status'],
                    executed_price=row.get('executed_price', 0),
                    executed_time=row.get('executed_time', ''),
                    order_id=row.get('order_id', '')
                )
                signals.append(sig)

            return signals

        except Exception as e:
            trader_logger.error(f"获取待执行信号失败: {e}")
            return []

    def mark_signal_executed(self, ts_code: str, execute_date: str,
                             executed_price: float, order_id: str):
        """
        标记信号已执行

        Args:
            ts_code: 股票代码
            execute_date: 执行日期
            executed_price: 成交价格
            order_id: 订单ID
        """
        try:
            db.execute("""
                UPDATE signals
                SET status = ?, executed_price = ?, executed_time = ?, order_id = ?
                WHERE ts_code = ? AND execute_date = ? AND status = ?
            """, (
                SIGNAL_STATUS_EXECUTED,
                executed_price,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                order_id,
                ts_code,
                execute_date,
                SIGNAL_STATUS_PENDING
            ))
            trader_logger.info(f"信号已执行: {ts_code} @ {executed_price}")
        except Exception as e:
            trader_logger.error(f"标记信号执行失败: {e}")

    def mark_signals_expired(self, execute_date: str = None):
        """
        标记过期信号（未执行的）

        Args:
            execute_date: 执行日期
        """
        execute_date = execute_date or datetime.now().strftime('%Y%m%d')

        try:
            result = db.execute("""
                UPDATE signals
                SET status = ?
                WHERE execute_date = ? AND status = ?
            """, (SIGNAL_STATUS_EXPIRED, execute_date, SIGNAL_STATUS_PENDING))

            trader_logger.info(f"标记 {result} 个信号为过期")
        except Exception as e:
            trader_logger.error(f"标记过期信号失败: {e}")

    def get_signal_history(self, days: int = 30) -> List[Dict]:
        """
        获取信号历史

        Args:
            days: 最近天数

        Returns:
            信号历史列表
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        try:
            df = db.query("""
                SELECT * FROM signals
                WHERE signal_date >= ?
                ORDER BY signal_date DESC, execute_date DESC
            """, (start_date,))

            return df.to_dict('records') if not df.empty else []

        except Exception as e:
            trader_logger.error(f"获取信号历史失败: {e}")
            return []

    def start_scheduler(self, check_interval: int = 60):
        """
        启动信号调度器（后台线程）

        Args:
            check_interval: 检查间隔（秒）
        """
        if self._running:
            trader_logger.warning("信号调度器已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(check_interval,), daemon=True)
        self._thread.start()
        trader_logger.info(f"信号调度器已启动，检查间隔: {check_interval}秒")

    def stop_scheduler(self):
        """停止信号调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        trader_logger.info("信号调度器已停止")

    def _run_loop(self, check_interval: int):
        """运行循环"""
        while self._running:
            try:
                now = datetime.now()
                current_time = now.time()
                current_date = now.strftime('%Y%m%d')
                from datetime import time as dt_time

                # === 14:50 信号生成窗口 ===
                if now.hour == 14 and 50 <= now.minute <= 59:
                    if not self._signals_generated_today or self._last_signal_date != current_date:
                        trader_logger.info("进入信号生成窗口 (14:50)")
                        self.generate_signals(current_date)

                # === 9:31-9:35 信号执行窗口 ===
                # 注意：这个逻辑通常由主交易循环调用，这里只是检查状态
                if now.hour == 9 and 31 <= now.minute <= 35:
                    pending = self.get_pending_signals(current_date)
                    if pending:
                        trader_logger.info(f"今日待执行信号: {len(pending)} 个")

                # === 新交易日重置 ===
                if now.hour == 8 and now.minute == 30:
                    if self._last_signal_date != current_date:
                        self._signals_generated_today = False
                        trader_logger.info("新交易日，重置信号状态")

                # === 15:10 标记过期信号 ===
                if now.hour == 15 and now.minute >= 10:
                    yesterday = (now - timedelta(days=1)).strftime('%Y%m%d')
                    self.mark_signals_expired(yesterday)

            except Exception as e:
                trader_logger.error(f"信号调度循环异常: {e}")

            time.sleep(check_interval)


# 全局实例
signal_scheduler = SignalScheduler()


def get_pending_signals(execute_date: str = None) -> List[TradingSignal]:
    """获取待执行信号（便捷函数）"""
    return signal_scheduler.get_pending_signals(execute_date)


def generate_signals(signal_date: str = None) -> List[TradingSignal]:
    """生成信号（便捷函数）"""
    return signal_scheduler.generate_signals(signal_date)


if __name__ == "__main__":
    # 测试
    print("=== 测试信号调度器 ===")

    # 初始化数据库表
    db.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            direction TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            execute_date TEXT NOT NULL,
            target_price REAL,
            volume INTEGER,
            confidence REAL,
            strategy_name TEXT,
            reason TEXT,
            status TEXT,
            executed_price REAL,
            executed_time TEXT,
            order_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, signal_date, direction)
        )
    """)

    scheduler = SignalScheduler()

    # 测试生成信号
    print("\n生成信号测试:")
    signals = scheduler.generate_signals()
    print(f"生成了 {len(signals)} 个信号")

    # 测试获取待执行信号
    print("\n获取待执行信号:")
    pending = scheduler.get_pending_signals()
    print(f"待执行信号: {len(pending)} 个")

    # 测试获取信号历史
    print("\n信号历史:")
    history = scheduler.get_signal_history(days=7)
    print(f"历史信号: {len(history)} 条")

    print("\n测试完成")