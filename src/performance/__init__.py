"""
性能追踪模块
每日净值记录和策略绩效计算
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config.logging_config import trader_logger
from src.utils.database import db


class PerformanceTracker:
    """性能追踪器 - 每日净值记录"""

    def __init__(self, initial_capital: float = 20000):
        """
        初始化性能追踪器

        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def record_daily_nav(self, total_asset: float, benchmark_change: float = 0) -> Dict:
        """
        记录每日净值

        Args:
            total_asset: 总资产
            benchmark_change: 基准（如沪深300）涨跌幅

        Returns:
            记录结果
        """
        current_date = datetime.now().strftime('%Y%m%d')

        # 计算净值
        nav = total_asset / self.initial_capital
        daily_return = (total_asset - self.initial_capital) / self.initial_capital

        # 计算超额收益
        excess_return = daily_return - benchmark_change

        try:
            db.execute("""
                INSERT OR REPLACE INTO daily_nav
                (date, total_asset, nav, daily_return, benchmark_change, excess_return)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                current_date,
                total_asset,
                nav,
                daily_return,
                benchmark_change,
                excess_return
            ))

            trader_logger.info(
                f"[净值记录] {current_date} | "
                f"总资产: {total_asset:.2f} | "
                f"净值: {nav:.4f} | "
                f"日收益: {daily_return*100:.2f}% | "
                f"基准: {benchmark_change*100:.2f}% | "
                f"超额: {excess_return*100:.2f}%"
            )

            return {
                'date': current_date,
                'total_asset': total_asset,
                'nav': nav,
                'daily_return': daily_return,
                'benchmark_change': benchmark_change,
                'excess_return': excess_return
            }

        except Exception as e:
            trader_logger.error(f"记录净值失败: {e}")
            return {}

    def get_latest_nav(self) -> Optional[Dict]:
        """获取最新净值"""
        try:
            df = db.query("""
                SELECT * FROM daily_nav
                ORDER BY date DESC
                LIMIT 1
            """)
            if df.empty:
                return None
            return df.iloc[0].to_dict()
        except Exception as e:
            trader_logger.error(f"获取最新净值失败: {e}")
            return None

    def get_nav_series(self, days: int = 30) -> List[Dict]:
        """
        获取净值曲线

        Args:
            days: 天数

        Returns:
            净值历史列表
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        try:
            df = db.query("""
                SELECT * FROM daily_nav
                WHERE date >= ?
                ORDER BY date ASC
            """, (start_date,))

            return df.to_dict('records') if not df.empty else []

        except Exception as e:
            trader_logger.error(f"获取净值曲线失败: {e}")
            return []

    def get_performance_summary(self, days: int = 30) -> Dict:
        """
        获取绩效摘要

        Args:
            days: 统计天数

        Returns:
            绩效指标字典
        """
        nav_series = self.get_nav_series(days)

        if not nav_series:
            return {}

        # 计算累计收益
        first_nav = nav_series[0]['nav']
        last_nav = nav_series[-1]['nav']
        total_return = (last_nav - 1) * 100

        # 年化收益 (假设250交易日)
        if len(nav_series) > 1:
            annualized_return = (last_nav / first_nav - 1) * 250 / len(nav_series) * 100
        else:
            annualized_return = 0

        # 最大回撤
        peak = 1.0
        max_drawdown = 0
        for record in nav_series:
            if record['nav'] > peak:
                peak = record['nav']
            drawdown = (peak - record['nav']) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # 平均超额收益
        avg_excess = sum(r.get('excess_return', 0) for r in nav_series) / len(nav_series) * 100

        # 胜率（跑赢基准的天数）
        wins = sum(1 for r in nav_series if r.get('excess_return', 0) > 0)
        win_rate = wins / len(nav_series) * 100 if nav_series else 0

        return {
            'days': len(nav_series),
            'total_return': total_return,
            'annualized_return': annualized_return,
            'max_drawdown': max_drawdown,
            'avg_excess_return': avg_excess,
            'win_rate': win_rate,
            'current_nav': last_nav,
            'initial_capital': self.initial_capital,
            'current_asset': nav_series[-1]['total_asset']
        }


class DailyBenchmark:
    """沪深300基准数据"""

    # 简化实现：直接使用当日大盘涨跌幅
    # 实际应从数据源获取沪深300实时/收盘数据

    @staticmethod
    def get_today_change() -> float:
        """
        获取今日沪深300涨跌幅

        Returns:
            涨跌幅（小数），如 0.01 表示上涨 1%
        """
        # 方法1：从数据库获取沪深300指数数据
        try:
            # 尝试获取 000300.SH（沪深300）的日线数据
            df = db.query("""
                SELECT pct_chg FROM daily_quotes
                WHERE ts_code = '000300.SH'
                ORDER BY trade_date DESC
                LIMIT 1
            """)
            if not df.empty:
                return df.iloc[0]['pct_chg'] / 100  # 转换为小数
        except Exception:
            pass

        # 方法2：从Tushare获取（需要token）
        # 实际生产环境应实现

        # 默认返回0
        return 0.0


# 全局实例
performance_tracker = PerformanceTracker()
daily_benchmark = DailyBenchmark()


def record_daily_performance(total_asset: float) -> Dict:
    """
    记录每日性能（便捷函数）

    Args:
        total_asset: 总资产

    Returns:
        记录结果
    """
    benchmark_change = daily_benchmark.get_today_change()
    return performance_tracker.record_daily_nav(total_asset, benchmark_change)


def get_performance_summary(days: int = 30) -> Dict:
    """获取绩效摘要（便捷函数）"""
    return performance_tracker.get_performance_summary(days)


def get_nav_curve(days: int = 30) -> List[Dict]:
    """获取净值曲线（便捷函数）"""
    return performance_tracker.get_nav_series(days)


# 初始化数据库表
def init_performance_tables():
    """初始化性能追踪相关表"""
    # 净值记录表
    db.execute("""
        CREATE TABLE IF NOT EXISTS daily_nav (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            total_asset REAL,
            nav REAL,
            daily_return REAL,
            benchmark_change REAL,
            excess_return REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 交易记录表（增强版）
    db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            ts_code TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL,
            volume INTEGER,
            amount REAL,
            commission REAL,
            profit_loss REAL,
            trade_date TEXT,
            trade_time TEXT,
            strategy_name TEXT,
            signal_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    trader_logger.info("性能追踪表初始化完成")


if __name__ == "__main__":
    # 初始化表
    init_performance_tables()

    # 测试
    print("=== 测试性能追踪 ===")

    # 模拟记录净值
    tracker = PerformanceTracker(initial_capital=20000)

    # 模拟几天数据
    import random
    for i in range(10):
        asset = 20000 * (1 + random.uniform(-0.02, 0.03))
        benchmark = random.uniform(-0.015, 0.015)
        tracker.record_daily_nav(asset, benchmark)

    # 获取绩效摘要
    print("\n绩效摘要 (近10天):")
    summary = tracker.get_performance_summary(10)
    for k, v in summary.items():
        print(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")

    # 获取净值曲线
    print("\n净值曲线:")
    curve = tracker.get_nav_series(10)
    for record in curve[:5]:
        print(f"  {record['date']}: nav={record['nav']:.4f}, excess={record.get('excess_return', 0)*100:.2f}%")

    print("\n测试完成")