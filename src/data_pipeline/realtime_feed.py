"""
实时价格数据管道
提供线程安全的内存价格缓存，支持多数据源自动切换
"""
import threading
import time
from typing import Dict, Optional, List
from datetime import datetime
from collections import defaultdict

from config.logging_config import data_logger
from src.data_collector.sina_client import sina_client
from src.data_collector.sohu_client import tencent_client
from src.data_collector.tushare_client import ts_client


class RealtimePriceCache:
    """实时价格缓存（线程安全）"""

    def __init__(self, refresh_interval: float = 30.0):
        """
        初始化实时价格缓存

        Args:
            refresh_interval: 刷新间隔（秒），默认 30 秒（优化后，避免 API 限流）
        """
        self.refresh_interval = refresh_interval
        self._prices: Dict[str, Dict] = {}  # {ts_code: {price, pre_close, pct_chg, update_time}}
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._subscribed_codes: set = set()
        self._last_fetch_time: Dict[str, float] = {}

        # 数据源
        self._current_source = "Sina"
        self._fallback_source = "Tencent"  # 腾讯财经作为备用

        data_logger.info(f"RealtimePriceCache 初始化完成，刷新间隔: {refresh_interval}秒")

    def subscribe(self, ts_codes: List[str]):
        """
        订阅股票实时价格

        Args:
            ts_codes: 股票代码列表
        """
        with self._lock:
            self._subscribed_codes.update(ts_codes)
            data_logger.info(f"订阅实时价格: {len(ts_codes)} 只股票")

            # 立即获取一次数据
            self._fetch_prices(ts_codes)

    def unsubscribe(self, ts_codes: List[str]):
        """取消订阅"""
        with self._lock:
            self._subscribed_codes.difference_update(ts_codes)
            # 从缓存中移除
            for code in ts_codes:
                self._prices.pop(code, None)

    def get_price(self, ts_code: str) -> Optional[Dict]:
        """
        获取股票实时价格（从缓存）

        Args:
            ts_code: 股票代码

        Returns:
            价格字典，包含 price, pre_close, pct_chg, update_time
            如果缓存中不存在，返回 None
        """
        with self._lock:
            data = self._prices.get(ts_code)
            if data:
                # 检查数据是否过期（超过 60 秒）
                age = time.time() - data.get('_fetch_time', 0)
                if age > 60:
                    data_logger.debug(f"价格数据已过期 ({age:.0f}秒): {ts_code}")
                    return None
            return data

    def get_all_prices(self) -> Dict[str, Dict]:
        """获取所有订阅股票的价格"""
        with self._lock:
            return dict(self._prices)

    def update_price(self, ts_code: str, price_data: Dict):
        """
        更新单只股票价格（内部使用）

        Args:
            ts_code: 股票代码
            price_data: 价格数据字典
        """
        with self._lock:
            price_data['_fetch_time'] = time.time()
            self._prices[ts_code] = price_data

    def _fetch_prices(self, ts_codes: List[str]):
        """
        从数据源获取价格（内部使用）

        Args:
            ts_codes: 股票代码列表
        """
        if not ts_codes:
            return

        # 优先使用 Sina
        try:
            df = sina_client.get_realtime_quotes(ts_codes)
            if not df.empty:
                self._current_source = "Sina"
                for _, row in df.iterrows():
                    self.update_price(row['ts_code'], {
                        'price': row.get('price', 0),
                        'pre_close': row.get('pre_close', 0),
                        'pct_chg': row.get('pct_chg', 0),
                        'open': row.get('open', 0),
                        'high': row.get('high', 0),
                        'low': row.get('low', 0),
                        'volume': row.get('volume', 0),
                        'amount': row.get('amount', 0),
                        'bid': row.get('bid', 0),
                        'ask': row.get('ask', 0),
                        'bid_volume': row.get('bid_volume', 0),
                        'ask_volume': row.get('ask_volume', 0),
                        'name': row.get('name', ''),
                        'source': 'Sina',
                        'update_time': row.get('update_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    })
                data_logger.debug(f"[DataFeed] Sina 获取 {len(df)} 只股票实时价格")
                return
        except Exception as e:
            data_logger.warning(f"Sina 数据获取失败: {e}")

        # Fallback 1: 使用腾讯财经备用数据源
        try:
            df = tencent_client.get_realtime_quotes(ts_codes)
            if not df.empty:
                self._current_source = "Tencent"
                for _, row in df.iterrows():
                    self.update_price(row['ts_code'], {
                        'price': row.get('price', 0),
                        'pre_close': row.get('pre_close', 0),
                        'pct_chg': row.get('pct_chg', 0),
                        'open': row.get('open', 0),
                        'high': row.get('high', 0),
                        'low': row.get('low', 0),
                        'volume': row.get('volume', 0),
                        'amount': row.get('amount', 0),
                        'bid': row.get('bid', 0),
                        'ask': row.get('ask', 0),
                        'bid_volume': row.get('bid_volume', 0),
                        'ask_volume': row.get('ask_volume', 0),
                        'name': row.get('name', ''),
                        'source': 'Tencent',
                        'update_time': row.get('update_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    })
                data_logger.info(f"[DataFeed] 使用腾讯备用数据 {len(df)} 只股票")
                return
        except Exception as e:
            data_logger.warning(f"腾讯数据获取失败：{e}")

        # Fallback 2: 使用数据库缓存
        data_logger.warning(f"Sina 和腾讯都获取失败，将使用数据库缓存价格")

    def start_background_refresh(self):
        """启动后台刷新线程"""
        if self._running:
            data_logger.warning("后台刷新已在运行中")
            return

        self._running = True
        self._thread = threading.Thread(target=self._background_loop, daemon=True)
        self._thread.start()
        data_logger.info("实时价格后台刷新已启动")

    def stop_background_refresh(self):
        """停止后台刷新"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        data_logger.info("实时价格后台刷新已停止")

    def _background_loop(self):
        """后台刷新循环"""
        while self._running:
            try:
                with self._lock:
                    codes_to_fetch = list(self._subscribed_codes)

                if codes_to_fetch:
                    # 分批获取，避免请求过多
                    batch_size = 20
                    for i in range(0, len(codes_to_fetch), batch_size):
                        batch = codes_to_fetch[i:i + batch_size]
                        self._fetch_prices(batch)
                        time.sleep(1)  # 批次间延迟

            except Exception as e:
                data_logger.error(f"后台刷新异常: {e}")

            # 等待下一次刷新
            time.sleep(self.refresh_interval)

    def get_market_status(self) -> str:
        """获取当前市场状态"""
        return sina_client.get_market_status()

    def is_market_open(self) -> bool:
        """判断是否在交易时间"""
        return sina_client.is_market_open()

    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            return {
                'subscribed_count': len(self._subscribed_codes),
                'cached_count': len(self._prices),
                'current_source': self._current_source,
                'refresh_interval': self.refresh_interval,
                'running': self._running
            }


# 全局实例
price_cache = RealtimePriceCache(refresh_interval=30.0)


def get_price(ts_code: str) -> Optional[Dict]:
    """
    获取股票实时价格（便捷函数）

    Args:
        ts_code: 股票代码

    Returns:
        价格字典或 None
    """
    return price_cache.get_price(ts_code)


def get_realtime_prices(ts_codes: List[str]) -> Dict[str, Dict]:
    """
    批量获取实时价格（便捷函数）

    Args:
        ts_codes: 股票代码列表

    Returns:
        {ts_code: price_dict}
    """
    # 确保订阅
    price_cache.subscribe(ts_codes)
    return price_cache.get_all_prices()


def start_price_feed():
    """启动价格订阅（全局初始化）"""
    price_cache.start_background_refresh()


def stop_price_feed():
    """停止价格订阅"""
    price_cache.stop_background_refresh()


if __name__ == "__main__":
    # 测试代码
    print("=== 测试实时价格缓存 ===")

    # 订阅测试股票
    test_stocks = ['000001.SZ', '600000.SH', '600036.SH']
    price_cache.subscribe(test_stocks)

    # 启动后台刷新
    price_cache.start_background_refresh()

    # 测试获取价格
    time.sleep(3)  # 等待首次获取

    for ts_code in test_stocks:
        price = price_cache.get_price(ts_code)
        if price:
            print(f"{ts_code}: {price.get('name')} ¥{price.get('price'):.2f} "
                  f"(来源: {price.get('source')}) "
                  f"涨跌: {price.get('pct_chg', 0):+.2f}%")
        else:
            print(f"{ts_code}: 无数据")

    # 查看统计
    print(f"\n缓存统计: {price_cache.get_stats()}")

    # 停止
    time.sleep(2)
    price_cache.stop_background_refresh()
    print("\n测试完成")