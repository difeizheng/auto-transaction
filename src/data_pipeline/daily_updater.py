"""
日线数据自动更新器
盘后 16:10 自动执行，更新所有股票池的日线数据到 SQLite

功能：
- 定时调度（盘后自动运行）
- 批量更新股票池数据
- 数据完整性校验
- 异常告警
"""
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import config.settings as settings
from config.logging_config import data_logger
from src.data_collector.data_manager import data_manager
from src.data_collector.tushare_client import ts_client


class DailyDataUpdater:
    """日线数据自动更新器"""

    def __init__(self, stock_pool: Optional[List[str]] = None):
        """
        初始化更新器

        Args:
            stock_pool: 股票池列表，None 表示使用配置的默认股票池
        """
        self.stock_pool = stock_pool or settings.DEFAULT_STOCK_POOL
        self.last_update_time: Optional[datetime] = None
        self.update_stats: Dict = {
            'success': 0,
            'failed': 0,
            'total': 0
        }

    def update_all(self, days: int = 30) -> Dict:
        """
        批量更新所有股票的日线数据

        Args:
            days: 更新最近 N 天的数据

        Returns:
            更新结果统计
        """
        data_logger.info("=" * 60)
        data_logger.info("开始批量更新日线数据...")
        data_logger.info(f"股票池大小: {len(self.stock_pool)}")
        data_logger.info(f"更新天数: {days}")
        data_logger.info("=" * 60)

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        success_count = 0
        failed_count = 0

        for i, ts_code in enumerate(self.stock_pool):
            try:
                # 获取日线数据
                df = ts_client.get_daily_quotes(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    save_to_db=True
                )
                if not df.empty:
                    success_count += 1
                else:
                    failed_count += 1
                    data_logger.warning(f"{ts_code} 无数据返回")

                # 每 10 只股票打印一次进度
                if (i + 1) % 10 == 0:
                    data_logger.info(f"进度：{i + 1}/{len(self.stock_pool)}, "
                                     f"成功：{success_count}, 失败：{failed_count}")

                # 避免请求过快
                time.sleep(0.2)

            except Exception as e:
                data_logger.error(f"更新 {ts_code} 失败：{e}")
                failed_count += 1

        # 更新统计
        self.update_stats = {
            'success': success_count,
            'failed': failed_count,
            'total': len(self.stock_pool)
        }
        self.last_update_time = datetime.now()

        data_logger.info("=" * 60)
        data_logger.info(f"批量更新日线数据完成")
        data_logger.info(f"总计：{len(self.stock_pool)}, 成功：{success_count}, 失败：{failed_count}")
        data_logger.info("=" * 60)

        return self.update_stats

    def update_single(self, ts_code: str, days: int = 60) -> bool:
        """
        更新单只股票数据

        Args:
            ts_code: 股票代码
            days: 更新天数

        Returns:
            是否成功
        """
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

            df = ts_client.get_daily_quotes(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                save_to_db=True
            )

            if df.empty:
                data_logger.warning(f"{ts_code} 无数据返回")
                return False

            data_logger.info(f"{ts_code} 更新完成: {len(df)} 条")
            return True

        except Exception as e:
            data_logger.error(f"更新 {ts_code} 失败: {e}")
            return False

    def check_data_freshness(self, ts_code: str) -> Dict:
        """
        检查数据新鲜度

        Args:
            ts_code: 股票代码

        Returns:
            新鲜度信息
        """
        return data_manager.check_data_freshness(ts_code)

    def verify_data_completeness(self) -> Dict:
        """
        验证数据完整性

        Returns:
            验证结果
        """
        data_logger.info("验证数据完整性...")

        incomplete_stocks = []
        today = datetime.now().strftime("%Y%m%d")

        for ts_code in self.stock_pool:
            freshness = self.check_data_freshness(ts_code)

            if not freshness.get('fresh', False):
                incomplete_stocks.append({
                    'ts_code': ts_code,
                    'latest_date': freshness.get('latest_date'),
                    'days_ago': freshness.get('days_ago')
                })

        result = {
            'total': len(self.stock_pool),
            'complete': len(self.stock_pool) - len(incomplete_stocks),
            'incomplete': len(incomplete_stocks),
            'incomplete_stocks': incomplete_stocks[:10]  # 只返回前10个
        }

        if incomplete_stocks:
            data_logger.warning(f"数据不完整股票数: {len(incomplete_stocks)}")
        else:
            data_logger.info("所有股票数据都是新鲜的")

        return result

    def get_last_update_info(self) -> Dict:
        """获取最后更新信息"""
        return {
            'last_update_time': self.last_update_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_update_time else None,
            'stats': self.update_stats
        }


class DailyUpdateScheduler:
    """日线数据更新调度器"""

    def __init__(self, stock_pool: Optional[List[str]] = None):
        """
        初始化调度器

        Args:
            stock_pool: 股票池列表
        """
        self.updater = DailyDataUpdater(stock_pool)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, check_interval: int = 3600):
        """
        启动调度器

        Args:
            check_interval: 检查间隔（秒），默认 1 小时
        """
        if self._running:
            data_logger.warning("调度器已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(check_interval,), daemon=True)
        self._thread.start()
        data_logger.info(f"日线数据更新调度器已启动，检查间隔: {check_interval}秒")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        data_logger.info("日线数据更新调度器已停止")

    def _run_loop(self, check_interval: int):
        """
        运行循环

        Args:
            check_interval: 检查间隔
        """
        while self._running:
            try:
                now = datetime.now()
                current_time = now.time()
                from datetime import time as dt_time

                # 盘后更新时间：16:10 - 17:00
                target_start = dt_time(16, 10)
                target_end = dt_time(17, 0)

                # 检查是否在更新窗口内
                if target_start <= current_time <= target_end:
                    # 检查是否已经更新过（避免重复更新）
                    if self.updater.last_update_time is None or \
                       self.updater.last_update_time.date() < now.date():
                        data_logger.info("进入盘后更新窗口，执行日线数据更新...")
                        result = self.updater.update_all()

                        if result['failed'] > result['success']:
                            data_logger.error(f"日线更新失败较多: {result}")
                        else:
                            data_logger.info(f"日线更新完成: {result}")

                # 检查是否需要验证数据完整性（每周一）
                if now.weekday() == 0 and dt_time(8, 0) <= current_time <= dt_time(8, 30):
                    if self.updater.last_update_time is None or \
                       self.updater.last_update_time.date() < now.date():
                        data_logger.info("周一数据完整性检查...")
                        self.updater.verify_data_completeness()

            except Exception as e:
                data_logger.error(f"调度循环异常: {e}")

            time.sleep(check_interval)

    def manual_update(self) -> Dict:
        """手动触发更新"""
        return self.updater.update_all()


# 全局实例
daily_updater = DailyDataUpdater()
daily_scheduler = DailyUpdateScheduler()


def start_daily_update_scheduler(stock_pool: Optional[List[str]] = None):
    """
    启动日线更新调度器

    Args:
        stock_pool: 股票池列表
    """
    scheduler = DailyUpdateScheduler(stock_pool)
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    # 测试代码
    print("=== 测试日线数据更新器 ===")

    # 创建更新器
    updater = DailyDataUpdater()

    # 更新单只股票
    print("\n测试更新单只股票 600000.SH:")
    result = updater.update_single("600000.SH")
    print(f"结果: {'成功' if result else '失败'}")

    # 批量更新
    print("\n测试批量更新（默认股票池）:")
    result = updater.update_all(days=10)
    print(f"结果: {result}")

    # 验证完整性
    print("\n验证数据完整性:")
    result = updater.verify_data_completeness()
    print(f"结果: {result}")

    # 查看最后更新信息
    print("\n最后更新信息:")
    print(updater.get_last_update_info())