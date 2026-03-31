"""
统一数据库架构初始化脚本
在 quant_trading.db 中创建所有必需的表

创建日期：2026-03-31
目标：统一使用单数据库架构，废弃 paper_trading.db
"""
import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import config.settings as settings

# 数据库路径
DB_PATH = Path("data/quant_trading.db")


def init_all_tables():
    """初始化所有表结构"""

    # 确保目录存在
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"正在初始化数据库: {DB_PATH}")
    print("=" * 60)

    # ========== 历史数据层 ==========

    # 1. 股票基本信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            ts_code TEXT PRIMARY KEY,
            symbol TEXT,
            name TEXT,
            area TEXT,
            industry TEXT,
            market TEXT,
            list_date TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] stocks - 股票基本信息表")

    # 2. 日线行情表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    print("[OK] daily_quotes - 日线行情表")

    # 3. 分钟线行情表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS minute_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_time TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            vol REAL,
            amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_time)
        )
    """)
    print("[OK] minute_quotes - 分钟线行情表")

    # 4. 财务指标表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            pe REAL,
            pb REAL,
            ps REAL,
            roe REAL,
            roa REAL,
            gross_margin REAL,
            net_margin REAL,
            asset_liability_ratio REAL,
            total_revenue REAL,
            net_profit REAL,
            total_assets REAL,
            total_equity REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, ann_date)
        )
    """)
    print("[OK] financial_indicators - 财务指标表")

    # 5. 交易日历表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_cal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL,
            cal_date TEXT NOT NULL,
            is_open INTEGER,
            pre_cal_date TEXT,
            next_cal_date TEXT,
            UNIQUE(exchange, cal_date)
        )
    """)
    print("[OK] trade_cal - 交易日历表")

    # ========== 实时数据层 ==========

    # 6. 实时行情表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS realtime_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            name TEXT,
            open REAL,
            high REAL,
            low REAL,
            price REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            bid REAL,
            ask REAL,
            bid_volume INTEGER,
            ask_volume INTEGER,
            volume INTEGER,
            amount REAL,
            update_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    print("[OK] realtime_quotes - 实时行情表")

    # 7. 监控日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_time TEXT NOT NULL,
            market_state TEXT,
            stock_pool TEXT,
            stocks_count INTEGER DEFAULT 0,
            signals_count INTEGER DEFAULT 0,
            buy_signals_count INTEGER DEFAULT 0,
            sell_signals_count INTEGER DEFAULT 0,
            trades_executed INTEGER DEFAULT 0,
            buy_orders TEXT,
            sell_orders TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] monitoring_logs - 监控日志表")

    # ========== 交易执行层 ==========

    # 8. 交易信号表 ⭐ 关键
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            direction TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            execute_date TEXT NOT NULL,
            target_price REAL,
            confidence REAL,
            strategy_name TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            executed_price REAL,
            executed_volume INTEGER,
            executed_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] signals - 交易信号表 (关键)")

    # 9. 订单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            ts_code TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL NOT NULL,
            volume INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            strategy_name TEXT,
            filled_volume INTEGER DEFAULT 0,
            filled_price REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            stamp_tax REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] orders - 订单表")

    # 10. 成交记录表 ⭐ 关键
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            ts_code TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL,
            volume INTEGER,
            amount REAL,
            commission REAL,
            stamp_tax REAL,
            profit_loss REAL,
            trade_date TEXT,
            trade_time TEXT,
            strategy_name TEXT,
            signal_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] trades - 成交记录表 (关键)")

    # 11. 持仓表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT UNIQUE NOT NULL,
            volume INTEGER NOT NULL,
            avg_cost REAL NOT NULL,
            current_price REAL,
            market_value REAL,
            profit_loss REAL,
            profit_ratio REAL,
            buy_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] positions - 持仓表")

    # 12. 账户状态表 ⭐ 关键
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            total_asset REAL DEFAULT 0,
            available_cash REAL DEFAULT 0,
            frozen_cash REAL DEFAULT 0,
            position_value REAL DEFAULT 0,
            position_count INTEGER DEFAULT 0,
            pending_orders INTEGER DEFAULT 0,
            submitted_orders INTEGER DEFAULT 0,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] account_status - 账户状态表 (关键)")

    # ========== 性能追踪层 ==========

    # 13. 每日净值表 ⭐ 关键
    cursor.execute("""
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
    print("[OK] daily_nav - 每日净值表 (关键)")

    # 14. 性能指标表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            period_days INTEGER,
            total_return REAL,
            annualized_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            win_rate REAL,
            avg_profit REAL,
            avg_loss REAL,
            profit_factor REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] performance_metrics - 性能指标表")

    # 15. 策略对比表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_comparison (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            nav REAL,
            daily_return REAL,
            total_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] strategy_comparison - 策略对比表")

    # ========== 创建索引 ==========

    print("\n创建索引...")

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_daily_ts_code ON daily_quotes(ts_code)",
        "CREATE INDEX IF NOT EXISTS idx_daily_trade_date ON daily_quotes(trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_minute_ts_code ON minute_quotes(ts_code)",
        "CREATE INDEX IF NOT EXISTS idx_financial_ts_code ON financial_indicators(ts_code)",
        "CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(signal_date)",
        "CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
        "CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_time ON monitoring_logs(monitor_time)",
        "CREATE INDEX IF NOT EXISTS idx_daily_nav_date ON daily_nav(date)",
    ]

    for idx_sql in indexes:
        cursor.execute(idx_sql)

    print("[OK] 所有索引创建完成")

    conn.commit()

    # ========== 验证表结构 ==========

    print("\n" + "=" * 60)
    print("验证表结构...")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    expected_tables = [
        'stocks', 'daily_quotes', 'minute_quotes', 'financial_indicators', 'trade_cal',
        'realtime_quotes', 'monitoring_logs',
        'signals', 'orders', 'trades', 'positions', 'account_status',
        'daily_nav', 'performance_metrics', 'strategy_comparison'
    ]

    existing_tables = [t[0] for t in tables]

    print(f"\n预期表数量: {len(expected_tables)}")
    print(f"实际表数量: {len(existing_tables)}")

    missing_tables = set(expected_tables) - set(existing_tables)
    if missing_tables:
        print(f"\n[WARNING] 缺失的表: {missing_tables}")
    else:
        print("\n[SUCCESS] 所有表创建成功!")

    # ========== 统计数据量 ==========

    print("\n" + "=" * 60)
    print("数据量统计...")

    for table in expected_tables:
        if table in existing_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table:25s} : {count:>8,} 条")

    conn.close()

    print("\n" + "=" * 60)
    print(f"[SUCCESS] 数据库初始化完成: {DB_PATH}")
    print(f"文件大小: {DB_PATH.stat().st_size / 1024 / 1024:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    init_all_tables()
