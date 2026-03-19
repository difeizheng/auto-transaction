"""
数据库操作工具模块
"""
import sqlite3
from pathlib import Path
import pandas as pd
from typing import List, Optional, Any
from contextlib import contextmanager

import config.settings as settings


class Database:
    """SQLite 数据库操作类"""

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            # 解析 sqlite:/// 格式的 URL
            db_url = settings.DATABASE_URL.replace("sqlite:///", "")
            self.db_path = Path(db_url)

        # 确保 data 目录存在
        self.db_path.parent.mkdir(exist_ok=True)

    @contextmanager
    def get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """
        执行 SQL 语句

        Args:
            sql: SQL 语句
            params: SQL 参数

        Returns:
            受影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.lastrowid

    def query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """
        查询数据并返回 DataFrame

        Args:
            sql: SQL 查询语句
            params: SQL 参数

        Returns:
            查询结果 DataFrame
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def insert_df(self, df: pd.DataFrame, table_name: str, if_exists: str = "append") -> None:
        """
        将 DataFrame 插入数据库

        Args:
            df: 要插入的 DataFrame
            table_name: 表名
            if_exists: 已存在时的处理方式 (append/replace/fail)
        """
        with self.get_connection() as conn:
            df.to_sql(table_name, conn, if_exists=if_exists, index=False)

    def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在

        Args:
            table_name: 表名

        Returns:
            是否存在
        """
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (table_name,))
            return cursor.fetchone() is not None

    def create_tables(self) -> None:
        """创建数据库表结构"""
        tables_sql = {
            # 股票信息表
            "stocks": """
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
            """,

            # 股票行情表 (日 K)
            "daily_quotes": """
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
            """,

            # 股票行情表 (分钟线)
            "minute_quotes": """
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
            """,

            # 财务指标表
            "financial_indicators": """
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
            """,

            # 策略信号表
            "strategy_signals": """
                CREATE TABLE IF NOT EXISTS strategy_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    ts_code TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    signal_price REAL,
                    target_weight REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,

            # 订单表
            "orders": """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE,
                    ts_code TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    strategy_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,

            # 持仓表
            "positions": """
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_code TEXT UNIQUE NOT NULL,
                    volume INTEGER NOT NULL,
                    avg_cost REAL NOT NULL,
                    current_price REAL,
                    market_value REAL,
                    profit_loss REAL,
                    profit_ratio REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,

            # 账户资金表
            "accounts": """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_name TEXT UNIQUE,
                    total_asset REAL,
                    available_cash REAL,
                    frozen_cash REAL,
                    total_position_value REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,

            # 交易日历表
            "trade_cal": """
                CREATE TABLE IF NOT EXISTS trade_cal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    cal_date TEXT NOT NULL,
                    is_open INTEGER,
                    pre_cal_date TEXT,
                    next_cal_date TEXT,
                    UNIQUE(exchange, cal_date)
                )
            """
        }

        # 创建索引
        indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_daily_ts_code ON daily_quotes(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_daily_trade_date ON daily_quotes(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_minute_ts_code ON minute_quotes(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_financial_ts_code ON financial_indicators(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_signals_strategy ON strategy_signals(strategy_name)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
        ]

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建表
            for table_sql in tables_sql.values():
                cursor.execute(table_sql)

            # 创建索引
            for index_sql in indexes_sql:
                cursor.execute(index_sql)


# 创建数据库实例
db = Database()


def init_db():
    """初始化数据库"""
    db.create_tables()
    print("数据库初始化完成!")


if __name__ == "__main__":
    init_db()
