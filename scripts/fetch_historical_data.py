"""
历史数据获取脚本
用于获取 2-3 年历史日线数据，支持断点续传和进度显示
使用 Baostock 免费接口
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import time

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_collector.data_manager import data_manager
from src.data_collector.baostock_client import BaostockClient
from config.settings import EXTENDED_STOCK_POOL, FUNDAMENTAL_FILTERS
from config.logging_config import data_logger
from src.utils.database import db

import baostock as bs
import pandas as pd


class HistoricalDataFetcher:
    """历史数据获取器"""

    def __init__(self, years: int = 3):
        """
        初始化历史数据获取器

        Args:
            years: 获取年数
        """
        self.years = years
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=years * 365)
        self.progress_file = Path(__file__).parent / ".fetch_progress.txt"
        self.bs_client = BaostockClient()
        import baostock as bs
        self.bs = bs  # 保存 baostock 模块引用

    def to_baostock_code(self, ts_code: str) -> str:
        """将 Tushare 格式转换为 Baostock 格式"""
        return BaostockClient.to_baostock_code(ts_code)

    def get_progress(self) -> dict:
        """获取下载进度"""
        if not self.progress_file.exists():
            return {'completed': [], 'failed': [], 'current': None}

        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            completed = []
            failed = []
            current = None

            for line in lines:
                line = line.strip()
                if line.startswith('completed:'):
                    completed = line.replace('completed:', '').split(',')
                elif line.startswith('failed:'):
                    failed = line.replace('failed:', '').split(',')
                elif line.startswith('current:'):
                    current = line.replace('current:', '')

            return {
                'completed': [c.strip() for c in completed if c.strip()],
                'failed': [f.strip() for f in failed if f.strip()],
                'current': current
            }
        except Exception as e:
            data_logger.warning(f"读取进度文件失败：{e}")
            return {'completed': [], 'failed': [], 'current': None}

    def save_progress(self, completed: list, failed: list, current: str = None):
        """保存下载进度"""
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                f.write(f"completed:{','.join(completed)}\n")
                f.write(f"failed:{','.join(failed)}\n")
                if current:
                    f.write(f"current:{current}\n")
        except Exception as e:
            data_logger.warning(f"保存进度文件失败：{e}")

    def clear_progress(self):
        """清除进度文件"""
        if self.progress_file.exists():
            self.progress_file.unlink()
            print("进度文件已清除")

    def fetch_from_baostock(self, ts_code: str) -> tuple:
        """
        从 Baostock 获取历史数据

        Args:
            ts_code: Tushare 格式股票代码

        Returns:
            (success, count) 元组
        """
        try:
            # 转换为 Baostock 格式
            bs_code = self.to_baostock_code(ts_code)

            # 获取日线数据
            rs = bs.query_history_k_data_plus(
                code=bs_code,
                fields='date,open,high,low,close,volume,amount',
                start_date=self.start_date.strftime("%Y-%m-%d"),
                end_date=self.end_date.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3"
            )

            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            if data_list:
                # 构建 DataFrame
                df = pd.DataFrame(data_list, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount'])
                df['ts_code'] = ts_code

                # 保存到数据库
                for _, row in df.iterrows():
                    try:
                        db.execute("""
                            INSERT OR REPLACE INTO daily_quotes
                            (ts_code, trade_date, open, high, low, close, vol, amount)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row.get('ts_code'),
                            str(row.get('trade_date')).replace('-', ''),
                            row.get('open'),
                            row.get('high'),
                            row.get('low'),
                            row.get('close'),
                            row.get('vol'),
                            row.get('amount')
                        ))
                    except Exception as e:
                        data_logger.debug(f"保存单条数据失败 {ts_code}: {e}")

                return True, len(df)
            else:
                return False, 0

        except Exception as e:
            data_logger.warning(f"{ts_code} 获取失败：{e}")
            return False, 0

    def fetch_data(self, stock_list: list = None, resume: bool = True):
        """
        获取历史数据

        Args:
            stock_list: 股票代码列表，None 表示使用扩展股票池
            resume: 是否从断点续传
        """
        # 登录 Baostock
        self.bs_client.login()

        if stock_list is None:
            # 使用扩展股票池
            stock_list = EXTENDED_STOCK_POOL
            print(f"使用扩展股票池：{len(stock_list)} 只股票")

        if not stock_list:
            print("没有可获取的股票")
            return

        # 获取进度
        progress = self.get_progress() if resume else {'completed': [], 'failed': [], 'current': None}
        completed = set(progress['completed'])
        failed_stocks = set(progress['failed'])

        # 过滤已完成的股票
        remaining_stocks = [s for s in stock_list if s not in completed]

        print(f"\n{'='*60}")
        print(f"历史数据获取 (Baostock)")
        print(f"{'='*60}")
        print(f"获取区间：{self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}")
        print(f"获取年数：{self.years} 年")
        print(f"股票数量：{len(remaining_stocks)} 只 (已完成：{len(completed)})")
        print(f"{'='*60}\n")

        # 开始获取
        success_count = 0
        fail_count = 0
        total_records = 0

        for i, ts_code in enumerate(remaining_stocks):
            current_idx = len(completed) + i + 1
            total = len(remaining_stocks) + len(completed)

            print(f"[{current_idx}/{total}] 获取 {ts_code} ...", end=" ")

            success, count = self.fetch_from_baostock(ts_code)

            if success:
                completed.add(ts_code)
                failed_stocks.discard(ts_code)
                self.save_progress(list(completed), list(failed_stocks), ts_code)
                success_count += 1
                total_records += count
                print(f"成功 ({count} 条)")
            else:
                failed_stocks.add(ts_code)
                self.save_progress(list(completed), list(failed_stocks), ts_code)
                fail_count += 1
                print("失败")

            # 频率限制控制
            time.sleep(0.1)

            # 每 10 只股票显示一次统计
            if current_idx % 10 == 0:
                print(f"\n  --- 进度：{current_idx}/{total}, 成功：{success_count}, 失败：{fail_count}, 总记录：{total_records} ---\n")

        # 完成统计
        print(f"\n{'='*60}")
        print("数据获取完成")
        print(f"{'='*60}")
        print(f"总计：{len(remaining_stocks)} 只股票")
        print(f"成功：{success_count} 只")
        print(f"失败：{fail_count} 只")
        print(f"总记录数：{total_records} 条")
        print(f"成功率：{success_count/len(remaining_stocks)*100:.1f}%")
        print(f"{'='*60}\n")

        # 登出 Baostock
        self.bs_client.logout()

        # 清理进度文件
        if fail_count == 0:
            self.clear_progress()
            print("所有股票数据获取成功，进度文件已清除")

        return {
            'success': success_count,
            'failed': fail_count,
            'total': len(remaining_stocks),
            'records': total_records
        }

    def check_data_completeness(self, stock_list: list = None):
        """
        检查数据完整性

        Args:
            stock_list: 股票代码列表
        """
        if stock_list is None:
            stock_list = EXTENDED_STOCK_POOL[:10]  # 默认检查前 10 只

        print(f"\n{'='*60}")
        print("数据完整性检查")
        print(f"{'='*60}\n")

        results = []
        for ts_code in stock_list:
            df = data_manager.get_daily_quotes(
                ts_code=ts_code,
                start_date=self.start_date.strftime('%Y%m%d'),
                end_date=self.end_date.strftime('%Y%m%d')
            )

            if df is not None and len(df) > 0:
                # 计算数据覆盖率
                expected_days = self.years * 252  # 约 252 个交易日/年
                coverage = len(df) / expected_days * 100

                # 获取最早和最晚日期
                min_date = df['trade_date'].min()
                max_date = df['trade_date'].max()

                results.append({
                    'ts_code': ts_code,
                    'count': len(df),
                    'coverage': coverage,
                    'min_date': min_date,
                    'max_date': max_date
                })

                status = "OK" if coverage > 80 else "WARN"
                print(f"[{status}] {ts_code}: {len(df)}条，覆盖率 {coverage:.1f}%, {min_date} - {max_date}")
            else:
                print(f"[FAIL] {ts_code}: 无数据")
                results.append({
                    'ts_code': ts_code,
                    'count': 0,
                    'coverage': 0,
                    'min_date': None,
                    'max_date': None
                })

        print(f"\n{'='*60}")
        return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='历史数据获取脚本 (Baostock)')
    parser.add_argument('--years', type=int, default=3, help='获取年数 (默认 3 年)')
    parser.add_argument('--stocks', type=str, nargs='+', default=None, help='指定股票代码列表')
    parser.add_argument('--resume', action='store_true', default=False, help='断点续传')
    parser.add_argument('--clear-progress', action='store_true', help='清除进度文件')
    parser.add_argument('--check', action='store_true', help='检查数据完整性')

    args = parser.parse_args()

    fetcher = HistoricalDataFetcher(years=args.years)

    if args.clear_progress:
        fetcher.clear_progress()
        return

    if args.check:
        # 检查数据完整性
        stock_list = args.stocks if args.stocks else EXTENDED_STOCK_POOL[:20]
        fetcher.check_data_completeness(stock_list)
    else:
        # 获取历史数据
        fetcher.fetch_data(stock_list=args.stocks, resume=args.resume)


if __name__ == "__main__":
    main()
