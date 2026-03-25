"""
新浪财经实时行情客户端
通过 HTTP 轮询获取 A 股实时行情数据
数据延迟：3-5 秒
成本：免费
"""
import requests
import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import time
import re

from config.logging_config import data_logger
from src.utils.database import db
from src.utils.helpers import normalize_date, format_ts_code


class SinaClient:
    """新浪财经 HTTP 实时行情客户端"""

    # 新浪行情 API 地址
    SINA_URL = "https://hq.sinajs.cn"

    # 请求头（模拟浏览器）
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://finance.sina.com.cn/',
    }

    def __init__(self, timeout: int = 10):
        """
        初始化新浪财经客户端

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._last_request_time = 0
        self._request_interval = 0.5  # 请求间隔，避免频率限制

    def _rate_limit(self):
        """频率限制控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()

    def _convert_ts_code(self, ts_code: str) -> str:
        """
        转换股票代码格式为新浪格式

        Tushare 格式：000001.SZ, 600000.SH
        新浪格式：sz000001, sh600000

        Args:
            ts_code: Tushare 格式股票代码

        Returns:
            新浪格式股票代码
        """
        parts = ts_code.upper().split('.')
        if len(parts) != 2:
            return ts_code

        code, exchange = parts
        exchange_map = {
            'SZ': 'sz',
            'SH': 'sh',
            'BJ': 'bj'
        }
        prefix = exchange_map.get(exchange, 'sh')
        return f"{prefix}{code}"

    def get_realtime_quotes(self, ts_codes: List[str]) -> pd.DataFrame:
        """
        获取实时行情数据

        Args:
            ts_codes: 股票代码列表（Tushare 格式）

        Returns:
            实时行情 DataFrame，包含字段：
            - ts_code: 股票代码
            - name: 股票名称
            - price: 当前价格
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - pre_close: 昨收价
            - volume: 成交量（手）
            - amount: 成交额（元）
            - bid: 买一价
            - ask: 卖一价
            - bid_volume: 买一量
            - ask_volume: 卖一量
            - pct_chg: 涨跌幅
            - update_time: 更新时间
        """
        if not ts_codes:
            return pd.DataFrame()

        sina_codes = [self._convert_ts_code(code) for code in ts_codes]
        symbols = ','.join(sina_codes)

        try:
            self._rate_limit()
            response = self.session.get(
                self.SINA_URL,
                params={'list': symbols},
                timeout=self.timeout
            )
            response.raise_for_status()

            # 解析返回数据
            data = self._parse_sina_response(response.text, ts_codes)

            if not data:
                data_logger.warning("新浪财经返回数据为空")
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            data_logger.info(f"获取新浪实时行情成功，{len(df)} 只股票")
            return df

        except requests.Timeout:
            data_logger.error("新浪财经请求超时")
            return pd.DataFrame()
        except requests.RequestException as e:
            data_logger.error(f"新浪财经请求失败：{e}")
            return pd.DataFrame()
        except Exception as e:
            data_logger.error(f"解析新浪数据失败：{e}")
            return pd.DataFrame()

    def _parse_sina_response(self, text: str, ts_codes: List[str]) -> List[Dict]:
        """
        解析新浪返回的数据

        新浪返回格式示例：
        var hq_str_sz000001="平安银行，10.50,10.45,10.55,10.60,10.40,10.48,10.49,10000,20000,10.47,30000,..."

        Args:
            text: 新浪返回的原始文本
            ts_codes: 原始股票代码列表（用于映射）

        Returns:
            解析后的数据列表
        """
        data = []
        lines = text.strip().split('\n')

        for i, line in enumerate(lines):
            if i >= len(ts_codes):
                break

            ts_code = ts_codes[i]

            # 提取引号内的数据
            match = re.search(r'="([^"]+)"', line)
            if not match:
                continue

            values = match.group(1).split(',')
            if len(values) < 32:
                continue

            try:
                # 新浪数据字段解析
                # 0: 股票名称，1: 今开，2: 昨收，3: 当前价，4: 最高，5: 最低
                # 6: 买一价，7: 买二价，8: 买三价，9: 买四价，10: 买五价
                # 11: 卖一价，12: 卖二价，13: 卖三价，14: 卖四价，15: 卖五价
                # 16: 买一量，17: 买二量，18: 买三量，19: 买四量，20: 买五量
                # 21: 卖一量，22: 卖二量，23: 卖三量，24: 卖四量，25: 卖五量
                # 26: 成交日期，27: 成交时间
                # 29: 成交量（手），30: 成交额（元）

                name = values[0]
                open_price = float(values[1]) if values[1] else 0
                pre_close = float(values[2]) if values[2] else 0
                current_price = float(values[3]) if values[3] else 0
                high = float(values[4]) if values[4] else 0
                low = float(values[5]) if values[5] else 0

                bid = float(values[6]) if values[6] else 0  # 买一价
                ask = float(values[11]) if values[11] else 0  # 卖一价

                bid_volume = int(float(values[16])) if values[16] else 0  # 买一量
                ask_volume = int(float(values[21])) if values[21] else 0  # 卖一量

                volume = int(float(values[29])) if values[29] else 0  # 成交量（手）
                amount = float(values[30]) if values[30] else 0  # 成交额（元）

                # 计算涨跌幅
                pct_chg = ((current_price - pre_close) / pre_close * 100) if pre_close > 0 else 0

                data.append({
                    'ts_code': ts_code,
                    'name': name,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'price': current_price,
                    'pre_close': pre_close,
                    'change': current_price - pre_close,
                    'pct_chg': pct_chg,
                    'bid': bid,
                    'ask': ask,
                    'bid_volume': bid_volume,
                    'ask_volume': ask_volume,
                    'volume': volume,
                    'amount': amount,
                })

            except (ValueError, IndexError) as e:
                data_logger.warning(f"解析单只股票数据失败 {ts_code}: {e}")
                continue

        return data

    def get_single_stock(self, ts_code: str) -> Optional[Dict]:
        """
        获取单只股票的实时行情

        Args:
            ts_code: 股票代码（Tushare 格式）

        Returns:
            实时行情字典，失败返回 None
        """
        df = self.get_realtime_quotes([ts_code])
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def get_stock_pool_quotes(self, stock_pool: List[str]) -> pd.DataFrame:
        """
        获取股票池实时行情（分批请求，避免频率限制）

        Args:
            stock_pool: 股票池代码列表

        Returns:
            实时行情 DataFrame
        """
        if not stock_pool:
            return pd.DataFrame()

        # 新浪一次最多请求 20 只股票
        batch_size = 20
        all_data = []

        for i in range(0, len(stock_pool), batch_size):
            batch = stock_pool[i:i + batch_size]
            batch_df = self.get_realtime_quotes(batch)
            if not batch_df.empty:
                all_data.append(batch_df)
            # 批次间延迟
            if i + batch_size < len(stock_pool):
                time.sleep(1)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

    def save_realtime_quotes(self, df: pd.DataFrame):
        """
        保存实时行情到数据库

        Args:
            df: 实时行情 DataFrame
        """
        if df.empty:
            return

        for _, row in df.iterrows():
            try:
                db.execute("""
                    INSERT OR REPLACE INTO realtime_quotes
                    (ts_code, trade_date, name, open, high, low, price, pre_close,
                     change, pct_chg, bid, ask, bid_volume, ask_volume, volume, amount, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'),
                    datetime.now().strftime('%Y%m%d'),
                    row.get('name'),
                    row.get('open'),
                    row.get('high'),
                    row.get('low'),
                    row.get('price'),
                    row.get('pre_close'),
                    row.get('change'),
                    row.get('pct_chg'),
                    row.get('bid'),
                    row.get('ask'),
                    row.get('bid_volume'),
                    row.get('ask_volume'),
                    row.get('volume'),
                    row.get('amount'),
                    row.get('update_time')
                ))
            except Exception as e:
                data_logger.warning(f"保存实时行情失败 {row.get('ts_code')}: {e}")

        data_logger.info(f"保存实时行情到数据库，{len(df)} 条记录")

    def compare_with_tushare(self, ts_code: str) -> Dict:
        """
        对比新浪数据与 Tushare 数据一致性

        Args:
            ts_code: 股票代码

        Returns:
            对比结果字典
        """
        from src.data_collector.tushare_client import ts_client

        # 获取新浪实时数据
        sina_data = self.get_single_stock(ts_code)

        # 获取 Tushare 最新日线数据
        tu_df = ts_client.get_daily_quotes(ts_code=ts_code, save_to_db=False)
        tu_data = None
        if not tu_df.empty:
            tu_data = tu_df.iloc[0].to_dict()

        comparison = {
            'ts_code': ts_code,
            'sina': sina_data,
            'tushare': tu_data,
            'price_diff': None,
            'price_diff_pct': None
        }

        if sina_data and tu_data:
            sina_price = sina_data.get('price', 0)
            tu_close = tu_data.get('close', 0)
            comparison['price_diff'] = sina_price - tu_close
            comparison['price_diff_pct'] = (sina_price - tu_close) / tu_close * 100 if tu_close > 0 else 0

        return comparison

    def is_market_open(self) -> bool:
        """
        判断当前是否在交易时间内

        Returns:
            True 表示交易时间，False 表示休市
        """
        now = datetime.now()

        # 周末休市
        if now.weekday() >= 5:
            return False

        # 交易时间：9:30-11:30, 13:00-15:00
        current_time = now.time()
        from datetime import time as dt_time

        morning_start = dt_time(9, 30)
        morning_end = dt_time(11, 30)
        afternoon_start = dt_time(13, 0)
        afternoon_end = dt_time(15, 0)

        return (morning_start <= current_time <= morning_end or
                afternoon_start <= current_time <= afternoon_end)

    def get_market_status(self) -> str:
        """
        获取市场状态

        Returns:
            市场状态字符串
        """
        now = datetime.now()

        if now.weekday() >= 5:
            return "休市（周末）"

        current_time = now.time()
        from datetime import time as dt_time

        if current_time < dt_time(9, 30):
            return "盘前"
        elif current_time < dt_time(11, 30):
            return "交易中（上午）"
        elif current_time < dt_time(13, 0):
            return "午休"
        elif current_time < dt_time(15, 0):
            return "交易中（下午）"
        else:
            return "收盘后"


# 创建客户端实例
sina_client = SinaClient()


if __name__ == "__main__":
    # 测试代码
    print("测试新浪财经客户端...")

    # 测试股票池
    test_stocks = ['000001.SZ', '000002.SZ', '600000.SH', '600036.SH']

    print(f"\n获取实时行情：{test_stocks}")
    df = sina_client.get_realtime_quotes(test_stocks)

    if not df.empty:
        print(f"\n成功获取 {len(df)} 只股票数据:")
        print(df[['ts_code', 'name', 'price', 'pct_chg']].to_string(index=False))

        # 保存到数据库
        sina_client.save_realtime_quotes(df)
        print("\n数据已保存到数据库")

        # 测试单只股票
        print(f"\n测试单只股票 000001.SZ:")
        single = sina_client.get_single_stock('000001.SZ')
        if single:
            print(f"  名称：{single['name']}")
            print(f"  当前价：{single['price']}")
            print(f"  涨跌幅：{single['pct_chg']:.2f}%")

        # 测试市场状态
        print(f"\n当前市场状态：{sina_client.get_market_status()}")
        print(f"是否交易时间：{sina_client.is_market_open()}")
    else:
        print("获取数据失败")
