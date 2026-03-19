"""
Tushare 数据接口客户端
"""
import tushare as ts
import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import time

import config.settings as settings
from config.logging_config import data_logger
from src.utils.database import db
from src.utils.helpers import normalize_date, format_ts_code


class TushareClient:
    """Tushare API 客户端"""

    def __init__(self, token: Optional[str] = None):
        """
        初始化 Tushare 客户端

        Args:
            token: Tushare API token，默认从配置读取
        """
        self.token = token or settings.TUSHARE_TOKEN
        if not self.token:
            raise ValueError("Tushare token 未配置，请设置环境变量 TUSHARE_TOKEN")

        ts.set_token(self.token)
        self.pro = ts.pro_api()
        self._last_request_time = 0
        self._request_interval = 0.1  # 请求间隔 (秒)，避免频率限制

    def _rate_limit(self):
        """频率限制控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()

    def get_stock_list(
        self,
        exchange: Optional[str] = None,
        list_status: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取股票列表

        Args:
            exchange: 交易所 (SSE/ SZSE)，None 表示全部
            list_status: 上市状态 (L 上市/D 退市/P 暂停)，None 表示全部

        Returns:
            股票列表 DataFrame
        """
        self._rate_limit()
        try:
            df = self.pro.stock_basic(
                exchange=exchange,
                list_status=list_status,
                fields=[
                    'ts_code', 'symbol', 'name', 'area', 'industry',
                    'market', 'list_date', 'status'
                ]
            )
            data_logger.info(f"获取股票列表成功，共 {len(df)} 只股票")
            return df
        except Exception as e:
            data_logger.error(f"获取股票列表失败：{e}")
            return pd.DataFrame()

    def get_daily_quotes(
        self,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        save_to_db: bool = True
    ) -> pd.DataFrame:
        """
        获取日线行情数据

        Args:
            ts_code: 股票代码，None 表示获取全部
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            save_to_db: 是否保存到数据库

        Returns:
            日线行情 DataFrame
        """
        self._rate_limit()

        # 默认获取最近 30 天
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

        start_date = normalize_date(start_date)
        end_date = normalize_date(end_date)

        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=[
                    'ts_code', 'trade_date', 'open', 'high', 'low', 'close',
                    'pre_close', 'change', 'pct_chg', 'vol', 'amount'
                ]
            )

            if save_to_db and not df.empty:
                self._save_daily_quotes(df)

            data_logger.info(f"获取日线数据成功，{ts_code or '全部'}, {len(df)} 条记录")
            return df

        except Exception as e:
            data_logger.error(f"获取日线数据失败：{e}")
            return pd.DataFrame()

    def _save_daily_quotes(self, df: pd.DataFrame):
        """保存日线数据到数据库"""
        for _, row in df.iterrows():
            try:
                db.execute("""
                    INSERT OR REPLACE INTO daily_quotes
                    (ts_code, trade_date, open, high, low, close, pre_close,
                     change, pct_chg, vol, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'),
                    row.get('trade_date'),
                    row.get('open'),
                    row.get('high'),
                    row.get('low'),
                    row.get('close'),
                    row.get('pre_close'),
                    row.get('change'),
                    row.get('pct_chg'),
                    row.get('vol'),
                    row.get('amount')
                ))
            except Exception as e:
                data_logger.warning(f"保存单条行情数据失败：{e}")

    def get_minute_quotes(
        self,
        ts_code: str,
        freq: str = '1m',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取分钟线数据

        Args:
            ts_code: 股票代码
            freq: 频率 (1m/5m/15m/30m/60m)
            start_date: 开始日期时间
            end_date: 结束日期时间

        Returns:
            分钟线 DataFrame
        """
        self._rate_limit()

        # 默认获取最近 5 天
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d %H%M%S")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d %H%M%S")

        try:
            df = self.pro.sina_minute(
                ts_code=ts_code,
                freq=freq,
                start_date=start_date,
                end_date=end_date
            )
            data_logger.info(f"获取分钟线数据成功，{ts_code}, {len(df)} 条记录")
            return df
        except Exception as e:
            data_logger.error(f"获取分钟线数据失败：{e}")
            return pd.DataFrame()

    def get_financial_indicators(
        self,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取财务指标数据

        Args:
            ts_code: 股票代码
            start_date: 公告开始日期
            end_date: 公告结束日期

        Returns:
            财务指标 DataFrame
        """
        self._rate_limit()

        try:
            # 获取主要财务指标
            df = self.pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=[
                    'ts_code', 'ann_date', 'end_date', 'pe', 'pb', 'ps',
                    'roe', 'roa', 'gross_margin', 'net_margin',
                    'asset_liability_ratio', 'total_revenue', 'net_profit',
                    'total_assets', 'total_equity'
                ]
            )

            data_logger.info(f"获取财务指标成功，{ts_code or '全部'}, {len(df)} 条记录")
            return df

        except Exception as e:
            data_logger.error(f"获取财务指标失败：{e}")
            return pd.DataFrame()

    def get_income_statement(
        self,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取利润表数据

        Args:
            ts_code: 股票代码
            start_date: 公告开始日期
            end_date: 公告结束日期

        Returns:
            利润表 DataFrame
        """
        self._rate_limit()

        try:
            df = self.pro.income(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=[
                    'ts_code', 'ann_date', 'end_date', 'total_revenue',
                    'operating_revenue', 'net_profit', 'operating_profit'
                ]
            )
            data_logger.info(f"获取利润表成功，{ts_code or '全部'}, {len(df)} 条记录")
            return df
        except Exception as e:
            data_logger.error(f"获取利润表失败：{e}")
            return pd.DataFrame()

    def get_balance_sheet(
        self,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取资产负债表数据

        Args:
            ts_code: 股票代码
            start_date: 公告开始日期
            end_date: 公告结束日期

        Returns:
            资产负债表 DataFrame
        """
        self._rate_limit()

        try:
            df = self.pro.balancesheet(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=[
                    'ts_code', 'ann_date', 'end_date', 'total_assets',
                    'total_liability', 'total_equity', 'total_hldr_eqy'
                ]
            )
            data_logger.info(f"获取资产负债表成功，{ts_code or '全部'}, {len(df)} 条记录")
            return df
        except Exception as e:
            data_logger.error(f"获取资产负债表失败：{e}")
            return pd.DataFrame()

    def get_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取交易日历

        Args:
            exchange: 交易所 (SSE/ SZSE)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易日历 DataFrame
        """
        self._rate_limit()

        try:
            df = self.pro.trade_cal(
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                fields=['cal_date', 'is_open', 'pre_cal_date', 'next_cal_date']
            )
            df['exchange'] = exchange
            data_logger.info(f"获取交易日历成功，{exchange}, {len(df)} 条记录")
            return df
        except Exception as e:
            data_logger.error(f"获取交易日历失败：{e}")
            return pd.DataFrame()

    def get_index_daily(
        self,
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取指数行情数据

        Args:
            ts_code: 指数代码 (如 000001.SH-上证指数)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            指数行情 DataFrame
        """
        self._rate_limit()

        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        try:
            df = self.pro.index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            data_logger.info(f"获取指数行情成功，{ts_code}, {len(df)} 条记录")
            return df
        except Exception as e:
            data_logger.error(f"获取指数行情失败：{e}")
            return pd.DataFrame()

    def save_stock_list(self, exchanges: List[str] = None):
        """
        保存股票列表到数据库

        Args:
            exchanges: 交易所列表，默认 ['SSE', 'SZSE', 'BSE']
        """
        if exchanges is None:
            exchanges = ['SSE', 'SZSE', 'BSE']

        all_stocks = []
        for exchange in exchanges:
            df = self.get_stock_list(exchange=exchange, list_status='L')
            if not df.empty:
                all_stocks.append(df)

        if all_stocks:
            combined_df = pd.concat(all_stocks, ignore_index=True)
            db.insert_df(combined_df, 'stocks', if_exists='replace')
            data_logger.info(f"保存股票列表到数据库，共 {len(combined_df)} 只股票")

        return combined_df if all_stocks else pd.DataFrame()


# 创建客户端实例
ts_client = TushareClient()


if __name__ == "__main__":
    # 测试代码
    print("测试 Tushare 客户端...")

    # 获取股票列表
    stocks = ts_client.get_stock_list()
    print(f"\n股票列表：{len(stocks)} 只")
    print(stocks.head())

    # 获取日线数据
    if not stocks.empty:
        test_code = stocks.iloc[0]['ts_code']
        daily = ts_client.get_daily_quotes(ts_code=test_code)
        print(f"\n{test_code} 日线数据：{len(daily)} 条")
        print(daily.head())
