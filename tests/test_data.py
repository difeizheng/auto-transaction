"""
数据采集模块测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import pandas as pd

from src.data_collector.tushare_client import TushareClient
from src.data_collector.baostock_client import BaostockClient
from src.data_collector.data_manager import DataManager
from src.utils.database import Database, init_db


class TestTushareClient(unittest.TestCase):
    """测试 Tushare 客户端"""

    def setUp(self):
        self.client = TushareClient()

    def test_get_stock_list(self):
        """测试获取股票列表"""
        df = self.client.get_stock_list(list_status='L')
        self.assertFalse(df.empty)
        self.assertIn('ts_code', df.columns)
        print(f"获取股票列表：{len(df)} 只")

    def test_get_daily_quotes(self):
        """测试获取日线数据"""
        df = self.client.get_daily_quotes(ts_code='600000.SH', start_date='20240101', end_date='20241231')
        self.assertFalse(df.empty)
        self.assertIn('ts_code', df.columns)
        self.assertIn('close', df.columns)
        print(f"获取日线数据：{len(df)} 条")

    def test_get_financial_indicators(self):
        """测试获取财务指标"""
        df = self.client.get_financial_indicators(ts_code='600000.SH')
        self.assertFalse(df.empty)
        self.assertIn('pe', df.columns)
        print(f"获取财务指标：{len(df)} 条")


class TestDatabase(unittest.TestCase):
    """测试数据库"""

    def setUp(self):
        self.db = Database()
        init_db()

    def test_create_tables(self):
        """测试创建表"""
        # 检查表是否存在
        tables = ['stocks', 'daily_quotes', 'financial_indicators', 'orders', 'positions']
        for table in tables:
            self.assertTrue(self.db.table_exists(table), f"表 {table} 不存在")
        print("所有表创建成功")

    def test_insert_and_query(self):
        """测试插入和查询数据"""
        # 插入测试数据
        test_data = pd.DataFrame({
            'ts_code': ['000001.SZ'],
            'symbol': ['000001'],
            'name': ['测试股票'],
            'area': ['深圳'],
            'industry': ['银行'],
            'market': ['主板'],
            'list_date': ['19910403'],
            'status': ['L']
        })
        self.db.insert_df(test_data, 'stocks', if_exists='replace')

        # 查询数据
        df = self.db.query("SELECT * FROM stocks WHERE ts_code = ?", ('000001.SZ',))
        self.assertFalse(df.empty)
        print(f"查询数据：{len(df)} 条")


class TestDataManager(unittest.TestCase):
    """测试数据管理器"""

    def setUp(self):
        self.dm = DataManager()
        init_db()

    def test_update_single_stock(self):
        """测试更新单只股票数据"""
        result = self.dm.update_single_stock('600000.SH', days=30)
        self.assertIn('daily', result)
        print(f"更新结果：{result}")

    def test_get_daily_quotes(self):
        """测试获取日线数据"""
        df = self.dm.get_daily_quotes('600000.SH')
        self.assertFalse(df.empty)
        self.assertIn('close', df.columns)
        print(f"获取数据：{len(df)} 条")

    def test_check_data_freshness(self):
        """测试检查数据新鲜度"""
        freshness = self.dm.check_data_freshness('600000.SH')
        self.assertIn('fresh', freshness)
        print(f"数据新鲜度：{freshness}")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
