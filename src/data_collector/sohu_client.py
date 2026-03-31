"""
腾讯财经实时行情客户端（备用方案）
通过 HTTP 轮询获取 A 股实时行情数据
数据延迟：3-5 秒
成本：免费
"""
import requests
import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime
import time
import re

from config.logging_config import data_logger


class TencentClient:
    """腾讯财经 HTTP 实时行情客户端"""

    # 腾讯行情 API 地址
    TENCENT_URL = "https://qt.gtimg.cn/"

    # 请求头
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://stockapp.finance.qq.com/',
    }

    def __init__(self, timeout: int = 10):
        """
        初始化腾讯财经客户端

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._last_request_time = 0
        self._request_interval = 0.3  # 请求间隔

    def _rate_limit(self):
        """频率限制控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()

    def _convert_ts_code(self, ts_code: str) -> str:
        """
        转换股票代码格式为腾讯格式

        Tushare 格式：000001.SZ, 600000.SH
        腾讯格式：sz000001, sh600000

        Args:
            ts_code: Tushare 格式股票代码

        Returns:
            腾讯格式股票代码
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
            ts_codes: 股票代码列表

        Returns:
            DataFrame 包含实时行情数据
        """
        if not ts_codes:
            return pd.DataFrame()

        all_data = []

        # 腾讯支持批量查询，最多 50 只股票
        batch_size = 50
        for i in range(0, len(ts_codes), batch_size):
            batch = ts_codes[i:i + batch_size]

            try:
                self._rate_limit()

                # 构建请求参数（腾讯格式）
                codes_param = ','.join([self._convert_ts_code(c) for c in batch])
                url = f"{self.TENCENT_URL}?q={codes_param}"

                response = self.session.get(url, timeout=self.timeout, headers=self.HEADERS)
                response.raise_for_status()

                # 腾讯返回的是 JavaScript 变量格式：v_sz000001="..."
                content = response.text
                lines = content.strip().split('\n')

                for line in lines:
                    if '=' in line:
                        data = self._parse_line(line)
                        if data:
                            all_data.append(data)

                time.sleep(0.1)  # 批次间延迟

            except requests.exceptions.RequestException as e:
                data_logger.warning(f"腾讯获取 {batch} 失败：{e}")
            except Exception as e:
                data_logger.warning(f"腾讯解析数据失败：{e}")

        if all_data:
            df = pd.DataFrame(all_data)
            return df
        else:
            return pd.DataFrame()

    def _parse_line(self, line: str) -> Optional[Dict]:
        """
        解析腾讯返回的数据行

        格式：v_sz000001="51~平安银行~000001~12.35~12.30~12.35~..."
        字段说明：
        0: 未知
        1: 名称
        2: 代码
        3: 当前价
        4: 昨收
        5: 开盘
        6: 最高
        7: 最低
        ...

        Args:
            line: 腾讯返回的数据行

        Returns:
            标准化后的数据字典
        """
        try:
            # 提取引号内的内容
            match = re.search(r'="([^"]+)"', line)
            if not match:
                return None

            content = match.group(1)
            fields = content.split('~')

            if len(fields) < 30:
                return None

            # 解析字段
            name = fields[1]
            ts_code = fields[2]
            price = float(fields[3]) if fields[3] else 0
            pre_close = float(fields[4]) if fields[4] else 0
            open_price = float(fields[5]) if fields[5] else 0
            high = float(fields[6]) if fields[6] else 0
            low = float(fields[7]) if fields[7] else 0
            volume = float(fields[8]) if fields[8] else 0
            amount = float(fields[9]) if fields[9] else 0

            # 买卖盘
            bid = float(fields[11]) if len(fields) > 11 and fields[11] else 0
            ask = float(fields[13]) if len(fields) > 13 and fields[13] else 0
            bid_volume = int(fields[10]) if len(fields) > 10 and fields[10] else 0
            ask_volume = int(fields[12]) if len(fields) > 12 and fields[12] else 0

            # 计算涨跌幅
            pct_chg = ((price - pre_close) / pre_close * 100) if pre_close > 0 else 0

            # 添加股票后缀
            if ts_code.startswith('6') or ts_code.startswith('9'):
                ts_code = f"{ts_code}.SH"
            else:
                ts_code = f"{ts_code}.SZ"

            return {
                'ts_code': ts_code,
                'name': name,
                'price': price,
                'open': open_price,
                'high': high,
                'low': low,
                'pre_close': pre_close,
                'pct_chg': pct_chg,
                'volume': volume,
                'amount': amount,
                'bid': bid,
                'ask': ask,
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Tencent'
            }

        except Exception as e:
            data_logger.warning(f"解析腾讯数据失败：{e}")
            return None

    def get_single_stock(self, ts_code: str) -> Optional[Dict]:
        """
        获取单只股票实时行情

        Args:
            ts_code: 股票代码

        Returns:
            行情数据字典
        """
        try:
            df = self.get_realtime_quotes([ts_code])
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception as e:
            data_logger.error(f"腾讯获取单只股票失败：{e}")
        return None


# 全局实例
tencent_client = TencentClient()


if __name__ == "__main__":
    # 测试
    print("=== 测试腾讯财经实时行情 ===")

    # 测试股票
    test_codes = ['000001.SZ', '600000.SH', '600519.SH']

    df = tencent_client.get_realtime_quotes(test_codes)

    if not df.empty:
        print(f"成功获取 {len(df)} 只股票数据:")
        print(df[['ts_code', 'name', 'price', 'pct_chg', 'volume']].to_string())
    else:
        print("腾讯获取数据失败")
