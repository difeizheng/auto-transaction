"""
数据管理器
统一管理和调度各数据源的数据采集、存储和更新
"""
import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

import config.settings as settings
from config.logging_config import data_logger
from src.utils.database import db
from src.data_collector.tushare_client import TushareClient
from src.data_collector.baostock_client import BaostockClient
from src.utils.helpers import normalize_date


class DataManager:
    """数据管理器"""

    def __init__(self):
        """初始化数据管理器"""
        self.ts_client = TushareClient()
        self.bs_client = BaostockClient()
        self.db = db

    def init_stock_pool(self, exchanges: List[str] = None) -> pd.DataFrame:
        """
        初始化股票池

        Args:
            exchanges: 交易所列表

        Returns:
            股票池 DataFrame
        """
        data_logger.info("开始初始化股票池...")

        # 从 Tushare 获取股票列表
        stocks_df = self.ts_client.save_stock_list(exchanges)

        if stocks_df.empty:
            data_logger.warning("未能获取股票列表")
            return pd.DataFrame()

        # 保存股票列表到数据库
        self.db.insert_df(stocks_df, 'stocks', if_exists='replace')
        data_logger.info(f"股票池初始化完成，共 {len(stocks_df)} 只股票")

        return stocks_df

    def update_all_daily_quotes(
        self,
        ts_codes: Optional[List[str]] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        批量更新日线数据

        Args:
            ts_codes: 股票代码列表，None 表示更新全部
            days: 更新最近 N 天的数据

        Returns:
            更新结果统计
        """
        data_logger.info("开始批量更新日线数据...")

        # 如果未指定股票，从数据库获取全部
        if ts_codes is None:
            if self.db.table_exists('stocks'):
                stocks_df = self.db.query("SELECT ts_code FROM stocks")
                ts_codes = stocks_df['ts_code'].tolist() if not stocks_df.empty else []

        if not ts_codes:
            data_logger.warning("没有需要更新的股票")
            return {"success": 0, "failed": 0}

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        success_count = 0
        failed_count = 0

        for i, ts_code in enumerate(ts_codes):
            try:
                # 获取日线数据
                df = self.ts_client.get_daily_quotes(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    save_to_db=True
                )
                if not df.empty:
                    success_count += 1
                else:
                    failed_count += 1

                # 每 100 只股票打印一次进度
                if (i + 1) % 100 == 0:
                    data_logger.info(f"进度：{i + 1}/{len(ts_codes)}, 成功：{success_count}, 失败：{failed_count}")

            except Exception as e:
                data_logger.error(f"更新 {ts_code} 失败：{e}")
                failed_count += 1

        data_logger.info(
            f"批量更新日线数据完成，总计：{len(ts_codes)}, "
            f"成功：{success_count}, 失败：{failed_count}"
        )

        return {"success": success_count, "failed": failed_count, "total": len(ts_codes)}

    def update_single_stock(self, ts_code: str, days: int = 60) -> Dict[str, Any]:
        """
        更新单只股票的数据

        Args:
            ts_code: 股票代码
            days: 更新最近 N 天的数据

        Returns:
            更新结果
        """
        data_logger.info(f"更新股票 {ts_code} 的数据...")

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        result = {}

        # 更新日线数据
        daily_df = self.ts_client.get_daily_quotes(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            save_to_db=True
        )
        result['daily'] = len(daily_df)

        # 获取财务数据 (最近一年)
        year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        financial_df = self.ts_client.get_financial_indicators(
            ts_code=ts_code,
            start_date=year_ago,
            end_date=end_date
        )
        if not financial_df.empty:
            self.db.insert_df(financial_df, 'financial_indicators', if_exists='replace')
            result['financial'] = len(financial_df)

        data_logger.info(f"股票 {ts_code} 更新完成：日线{result.get('daily', 0)}条，财务{result.get('financial', 0)}条")

        return result

    def get_daily_quotes(
        self,
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        从数据库获取日线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            日线数据 DataFrame
        """
        sql = "SELECT * FROM daily_quotes WHERE ts_code = ?"
        params = [ts_code]

        if start_date:
            sql += " AND trade_date >= ?"
            params.append(normalize_date(start_date))
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(normalize_date(end_date))

        sql += " ORDER BY trade_date ASC"

        df = self.db.query(sql, tuple(params))

        if df.empty:
            data_logger.warning(f"未找到 {ts_code} 的日线数据")
            return pd.DataFrame()

        return df

    def get_financial_indicators(self, ts_code: str) -> pd.DataFrame:
        """
        从数据库获取财务指标

        Args:
            ts_code: 股票代码

        Returns:
            财务指标 DataFrame
        """
        sql = "SELECT * FROM financial_indicators WHERE ts_code = ? ORDER BY ann_date DESC"
        df = self.db.query(sql, (ts_code,))

        if df.empty:
            data_logger.warning(f"未找到 {ts_code} 的财务数据")
            return pd.DataFrame()

        return df

    def get_stock_list(self, status: str = 'L') -> pd.DataFrame:
        """
        从数据库获取股票列表

        Args:
            status: 上市状态 (L 上市/D 退市/P 暂停)

        Returns:
            股票列表 DataFrame
        """
        sql = "SELECT * FROM stocks WHERE status = ?" if status else "SELECT * FROM stocks"
        params = (status,) if status else ()
        return self.db.query(sql, params)

    def get_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取交易日历

        Args:
            exchange: 交易所
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易日历 DataFrame
        """
        # 先从数据库获取
        if self.db.table_exists('trade_cal'):
            sql = "SELECT * FROM trade_cal WHERE exchange = ?"
            params = [exchange]

            if start_date:
                sql += " AND cal_date >= ?"
                params.append(normalize_date(start_date))
            if end_date:
                sql += " AND cal_date <= ?"
                params.append(normalize_date(end_date))

            df = self.db.query(sql, tuple(params))
            if not df.empty:
                return df

        # 数据库没有则从 Tushare 获取并保存
        df = self.ts_client.get_trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date
        )

        if not df.empty:
            self.db.insert_df(df, 'trade_cal', if_exists='replace')

        return df

    def get_latest_trade_date(self, ts_code: str) -> Optional[str]:
        """
        获取某只股票最新的交易日期

        Args:
            ts_code: 股票代码

        Returns:
            最新交易日期
        """
        sql = "SELECT MAX(trade_date) as latest_date FROM daily_quotes WHERE ts_code = ?"
        df = self.db.query(sql, (ts_code,))
        if not df.empty and df.iloc[0]['latest_date']:
            return str(df.iloc[0]['latest_date'])
        return None

    def check_data_freshness(self, ts_code: str) -> Dict[str, Any]:
        """
        检查数据新鲜度

        Args:
            ts_code: 股票代码

        Returns:
            数据新鲜度信息
        """
        latest_date = self.get_latest_trade_date(ts_code)
        today = datetime.now().strftime("%Y%m%d")

        if not latest_date:
            return {"fresh": False, "latest_date": None, "days_ago": None}

        # 计算相差天数 (简单计算，未考虑交易日历)
        latest_dt = datetime.strptime(latest_date, "%Y%m%d")
        today_dt = datetime.strptime(today, "%Y%m%d")
        days_ago = (today_dt - latest_dt).days

        return {
            "fresh": days_ago <= 3,  # 3 天内数据认为新鲜
            "latest_date": latest_date,
            "days_ago": days_ago
        }

    def export_to_parquet(
        self,
        ts_code: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        导出股票数据到 Parquet 文件

        Args:
            ts_code: 股票代码
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        df = self.get_daily_quotes(ts_code)
        if df.empty:
            return None

        if output_path is None:
            output_path = settings.PROCESSED_DATA_DIR / f"{ts_code.replace('.', '_')}_daily.parquet"
        else:
            output_path = Path(output_path)

        # 确保目录存在
        output_path.parent.mkdir(exist_ok=True, parents=True)

        df.to_parquet(output_path, index=False)
        data_logger.info(f"导出数据到 {output_path}")

        return str(output_path)

    def get_merged_data(
        self,
        ts_code: str,
        include_financial: bool = True
    ) -> pd.DataFrame:
        """
        获取合并后的数据 (行情 + 财务)

        Args:
            ts_code: 股票代码
            include_financial: 是否包含财务数据

        Returns:
            合并后的 DataFrame
        """
        # 获取行情数据
        daily_df = self.get_daily_quotes(ts_code)

        if daily_df.empty:
            return pd.DataFrame()

        if not include_financial:
            return daily_df

        # 获取财务数据
        financial_df = self.get_financial_indicators(ts_code)

        if financial_df.empty:
            return daily_df

        # 按日期合并 (财务数据按公告日期合并)
        merged_df = daily_df.merge(
            financial_df,
            left_on='trade_date',
            right_on='ann_date',
            how='left'
        )

        return merged_df

    def filter_stock_pool_by_fundamentals(
        self,
        stock_list: Optional[List[str]] = None,
        max_pe: float = None,
        min_roe: float = None,
        min_revenue_growth: float = None,
        max_debt_ratio: float = None,
        min_market_cap: float = None
    ) -> List[str]:
        """
        基本面过滤股票池 (增强版)

        Args:
            stock_list: 待过滤的股票列表，None 表示使用扩展股票池
            max_pe: 最大市盈率
            min_roe: 最小 ROE
            min_revenue_growth: 最小营收增长率
            max_debt_ratio: 最大资产负债率
            min_market_cap: 最小总市值

        Returns:
            符合基本面条件的股票列表
        """
        if stock_list is None:
            stock_list = settings.EXTENDED_STOCK_POOL

        # 从配置读取默认值
        filters = settings.FUNDAMENTAL_FILTERS
        max_pe = max_pe or filters.get('max_pe', 50)
        min_roe = min_roe or filters.get('min_roe', 0.05)
        min_revenue_growth = min_revenue_growth or filters.get('min_revenue_growth', 0.0)
        max_debt_ratio = max_debt_ratio or filters.get('max_debt_ratio', 0.70)
        min_market_cap = min_market_cap or filters.get('min_market_cap', 5000000000)

        return self.ts_client.filter_stocks_by_fundamentals(
            stock_list=stock_list,
            max_pe=max_pe,
            min_roe=min_roe,
            min_revenue_growth=min_revenue_growth,
            max_debt_ratio=max_debt_ratio,
            min_market_cap=min_market_cap
        )

    def get_hs300_filtered(
        self,
        max_pe: float = 50,
        min_roe: float = 0.05,
        min_revenue_growth: float = 0.0
    ) -> List[str]:
        """
        获取沪深 300 成分股并进行基本面过滤

        Args:
            max_pe: 最大市盈率
            min_roe: 最小 ROE
            min_revenue_growth: 最小营收增长率

        Returns:
            过滤后的沪深 300 成分股列表
        """
        hs300_stocks = self.ts_client.get_hs300_stocks()
        if not hs300_stocks:
            return settings.EXTENDED_STOCK_POOL

        return self.filter_stock_pool_by_fundamentals(
            stock_list=hs300_stocks,
            max_pe=max_pe,
            min_roe=min_roe,
            min_revenue_growth=min_revenue_growth
        )

    def get_stock_industry_mapping(self, stock_list: List[str]) -> Dict[str, str]:
        """
        获取股票行业映射

        Args:
            stock_list: 股票代码列表

        Returns:
            {ts_code: industry} 映射字典
        """
        industry_map = {}
        for ts_code in stock_list:
            industry = self.ts_client.get_stock_industry(ts_code)
            if industry:
                industry_map[ts_code] = industry
        return industry_map

    def check_rebalance_date(self, last_rebalance_date: str) -> bool:
        """
        检查是否需要调仓

        Args:
            last_rebalance_date: 上次调仓日期 (YYYYMMDD)

        Returns:
            是否需要调仓
        """
        config = settings.REBALANCE_CONFIG
        if not config.get('enabled', False):
            return False

        last_dt = datetime.strptime(last_rebalance_date, "%Y%m%d")
        today = datetime.now()

        # 计算调仓周期
        frequency = config.get('frequency', 'monthly')
        if frequency == 'weekly':
            days_threshold = 7
        elif frequency == 'monthly':
            days_threshold = 21  # 约 21 个交易日
        elif frequency == 'quarterly':
            days_threshold = 63  # 约 63 个交易日
        else:
            days_threshold = 21

        days_since_rebalance = (today - last_dt).days
        return days_since_rebalance >= days_threshold

    def generate_rebalance_candidates(
        self,
        current_holdings: List[str],
        stock_pool: List[str],
        max_turnover_ratio: float = 0.30
    ) -> Dict[str, List[str]]:
        """
        生成调仓候选股票

        Args:
            current_holdings: 当前持仓
            stock_pool: 可选股票池
            max_turnover_ratio: 最大调仓比例

        Returns:
            {to_buy: [...], to_sell: [...]} 调仓建议
        """
        # 计算最大调仓数量
        max_turnover_count = max(1, int(len(current_holdings) * max_turnover_ratio))

        # 卖出建议：不在股票池中的持仓
        to_sell = [code for code in current_holdings if code not in stock_pool]
        to_sell = to_sell[:max_turnover_count]  # 限制调仓数量

        # 买入建议：股票池中但不在持仓的股票
        to_buy_candidates = [code for code in stock_pool if code not in current_holdings]
        to_buy = to_buy_candidates[:max_turnover_count]  # 限制调仓数量

        return {
            'to_buy': to_buy,
            'to_sell': to_sell
        }


# 创建数据管理器实例
data_manager = DataManager()


if __name__ == "__main__":
    # 初始化数据库
    db.create_tables()
    print("数据库初始化完成!")

    # 测试数据管理器
    print("\n=== 测试数据管理器 ===")

    # 初始化股票池
    # stocks = data_manager.init_stock_pool()
    # print(f"股票池：{len(stocks)} 只股票")

    # 更新单只股票
    result = data_manager.update_single_stock("600000.SH", days=30)
    print(f"更新结果：{result}")

    # 获取数据
    df = data_manager.get_daily_quotes("600000.SH")
    print(f"\n获取日线数据：{len(df)} 条")
    print(df.head())

    # 检查新鲜度
    freshness = data_manager.check_data_freshness("600000.SH")
    print(f"\n数据新鲜度：{freshness}")
