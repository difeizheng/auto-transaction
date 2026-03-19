"""
Baostock 数据接口客户端
用于获取分钟线数据和高频数据
"""
import baostock as bs
import pandas as pd
from typing import Optional, List
from datetime import datetime, timedelta

import config.settings as settings
from config.logging_config import data_logger
from src.utils.database import db
from src.utils.helpers import normalize_date


class BaostockClient:
    """Baostock API 客户端"""

    def __init__(self):
        """初始化 Baostock 客户端"""
        self._is_login = False

    def login(self):
        """登录 Baostock"""
        if not self._is_login:
            lg = bs.login()
            self._is_login = True
            data_logger.info(f"Baostock 登录成功：{lg}")
        return self._is_login

    def logout(self):
        """登出 Baostock"""
        if self._is_login:
            bs.logout()
            self._is_login = False
            data_logger.info("Baostock 登出成功")

    def _ensure_login(self):
        """确保已登录"""
        if not self._is_login:
            self.login()

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取股票列表

        Returns:
            股票列表 DataFrame
        """
        self._ensure_login()

        try:
            rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            df = pd.DataFrame(data_list, columns=rs.fields)
            data_logger.info(f"获取股票列表成功，共 {len(df)} 只股票")
            return df

        except Exception as e:
            data_logger.error(f"获取股票列表失败：{e}")
            return pd.DataFrame()

    def get_daily_quotes(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        frequency: str = "d"
    ) -> pd.DataFrame:
        """
        获取日线/分钟线数据

        Args:
            code: 股票代码 (sh.600000 或 sz.000001)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            frequency: 频率 (d=日，w=周，m=月，5=5 分钟，15=15 分钟，30=30 分钟，60=60 分钟)

        Returns:
            行情数据 DataFrame
        """
        self._ensure_login()

        # 默认获取最近 30 天
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            rs = bs.query_history_k_data_plus(
                code=code,
                fields="date,time,open,high,low,close,volume,amount,turn",
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag="3"  # 不复权
            )

            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            df = pd.DataFrame(data_list, columns=rs.fields)
            data_logger.info(f"获取行情数据成功，{code}, {len(df)} 条记录")
            return df

        except Exception as e:
            data_logger.error(f"获取行情数据失败：{e}")
            return pd.DataFrame()

    def get_minute_quotes(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        frequency: str = "5"
    ) -> pd.DataFrame:
        """
        获取分钟线数据

        Args:
            code: 股票代码 (sh.600000 或 sz.000001)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            frequency: 频率 (5=5 分钟，15=15 分钟，30=30 分钟，60=60 分钟)

        Returns:
            分钟线 DataFrame
        """
        return self.get_daily_quotes(code, start_date, end_date, frequency)

    def get_financial_data(self, code: str, year: int, report_type: str = "all") -> pd.DataFrame:
        """
        获取财务数据

        Args:
            code: 股票代码
            year: 年份
            report_type: 报告类型 (report=季报，express=快报，forecast=预告)

        Returns:
            财务数据 DataFrame
        """
        self._ensure_login()

        try:
            # 获取盈利能力
            rs_profit = bs.query_profit_data(code=code, year=year, reportType=report_type)
            # 获取成长能力
            rs_growth = bs.query_growth_data(code=code, year=year, reportType=report_type)
            # 获取营运能力
            rs_operation = bs.query_operation_data(code=code, year=year, reportType=report_type)

            data_list = []
            for rs in [rs_profit, rs_growth, rs_operation]:
                while (rs.error_code == '0') and rs.next():
                    data_list.append(rs.get_row_data())

            df = pd.DataFrame(data_list)
            data_logger.info(f"获取财务数据成功，{code}, {len(df)} 条记录")
            return df

        except Exception as e:
            data_logger.error(f"获取财务数据失败：{e}")
            return pd.DataFrame()

    def get_index_daily(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取指数行情数据

        Args:
            code: 指数代码 (sh.000001=上证指数，sz.399001=深证成指)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            指数行情 DataFrame
        """
        self._ensure_login()

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        try:
            rs = bs.query_index_history(code=code, start_date=start_date, end_date=end_date)
            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            df = pd.DataFrame(data_list, columns=rs.fields)
            data_logger.info(f"获取指数行情成功，{code}, {len(df)} 条记录")
            return df

        except Exception as e:
            data_logger.error(f"获取指数行情失败：{e}")
            return pd.DataFrame()

    def convert_to_ts_code(self, code: str) -> str:
        """
        将 Baostock 代码格式转换为 Tushare 格式

        Args:
            code: Baostock 格式 (sh.600000)

        Returns:
            Tushare 格式 (600000.SH)
        """
        if '.' in code:
            exchange, symbol = code.split('.')
            exchange_map = {'sh': 'SH', 'sz': 'SZ', 'bj': 'BJ'}
            return f"{symbol}.{exchange_map.get(exchange.lower(), 'SH')}"
        return code

    @staticmethod
    def to_ts_code(code: str) -> str:
        """
        将 Baostock 代码格式转换为 Tushare 格式 (静态方法)

        Args:
            code: Baostock 格式 (sh.600000)

        Returns:
            Tushare 格式 (600000.SH)
        """
        if '.' in code:
            exchange, symbol = code.split('.')
            exchange_map = {'sh': 'SH', 'sz': 'SZ', 'bj': 'BJ'}
            return f"{symbol}.{exchange_map.get(exchange.lower(), 'SH')}"
        return code

    @staticmethod
    def to_baostock_code(ts_code: str) -> str:
        """
        将 Tushare 格式转换为 Baostock 代码格式

        Args:
            ts_code: Tushare 格式 (600000.SH)

        Returns:
            Baostock 格式 (sh.600000)
        """
        if '.' in ts_code:
            symbol, exchange = ts_code.split('.')
            exchange_map = {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj'}
            return f"{exchange_map.get(exchange.upper(), 'sh')}.{symbol}"
        return f"sh.{ts_code}"


# 创建客户端实例
bs_client = BaostockClient()


if __name__ == "__main__":
    # 测试代码
    print("测试 Baostock 客户端...")

    # 获取日线数据
    daily = bs_client.get_daily_quotes("sh.600000")
    print(f"\n日线数据：{len(daily)} 条")
    print(daily.head())

    # 获取 5 分钟线
    minute = bs_client.get_minute_quotes("sh.600000", frequency="5")
    print(f"\n5 分钟线：{len(minute)} 条")
    print(minute.head())

    # 测试代码转换
    ts_code = bs_client.to_ts_code("sh.600000")
    print(f"\n代码转换：sh.600000 -> {ts_code}")

    bs_client.logout()
