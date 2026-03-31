"""
补全历史数据脚本
获取 2023-2026 年 3 年历史日线数据

创建日期：2026-03-31
目标：补全至少 35,000 条日线记录
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import config.settings as settings
from src.data_collector.tushare_client import ts_client
from src.utils.database import db


def fetch_3year_data():
    """获取 3 年历史数据"""

    stock_pool = settings.DEFAULT_STOCK_POOL
    start_date = '20230101'
    end_date = datetime.now().strftime('%Y%m%d')

    print(f"开始获取历史数据")
    print(f"股票池: {len(stock_pool)} 只")
    print(f"时间范围: {start_date} ~ {end_date}")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    total_records = 0

    for ts_code in tqdm(stock_pool, desc="获取日线数据"):
        try:
            # 获取日线数据（前复权）
            df = ts_client.get_daily_quotes(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is not None and not df.empty:
                # 写入数据库（追加模式）
                db.insert_df(df, 'daily_quotes', if_exists='append')

                records = len(df)
                total_records += records
                success_count += 1

                tqdm.write(f"[OK] {ts_code}: {records} 条记录")
            else:
                fail_count += 1
                tqdm.write(f"[WARN] {ts_code}: 无数据")

            # 限速（Tushare 限制）
            time.sleep(0.3)

        except Exception as e:
            fail_count += 1
            tqdm.write(f"[ERROR] {ts_code}: {e}")
            time.sleep(1)

    print("\n" + "=" * 60)
    print("数据获取完成")
    print(f"成功: {success_count} 只")
    print(f"失败: {fail_count} 只")
    print(f"总记录数: {total_records:,} 条")
    print("=" * 60)

    # 验证数据
    verify_data()


def verify_data():
    """验证数据完整性"""

    print("\n验证数据完整性...")

    # 统计总记录数
    result = db.query("SELECT COUNT(*) as count FROM daily_quotes")
    total_count = result.iloc[0]['count']

    print(f"数据库总记录数: {total_count:,} 条")

    # 统计每只股票的记录数
    result = db.query("""
        SELECT ts_code, COUNT(*) as count
        FROM daily_quotes
        GROUP BY ts_code
        ORDER BY count DESC
    """)

    print(f"\n股票数量: {len(result)}")
    print(f"平均每只股票: {total_count / len(result):.0f} 条")

    # 检查数据缺失
    min_count = result['count'].min()
    max_count = result['count'].max()

    print(f"最少记录: {min_count} 条")
    print(f"最多记录: {max_count} 条")

    # 显示记录数最少的股票
    print("\n记录数最少的 5 只股票:")
    print(result.tail(5).to_string(index=False))

    # 检查日期范围
    result = db.query("""
        SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
        FROM daily_quotes
    """)

    print(f"\n日期范围: {result.iloc[0]['min_date']} ~ {result.iloc[0]['max_date']}")

    # 判断是否达标
    if total_count >= 30000:
        print("\n[SUCCESS] 数据量达标 (≥30,000 条)")
    else:
        print(f"\n[WARNING] 数据量不足，还需 {30000 - total_count:,} 条")


def fetch_financial_data():
    """获取财务数据（可选）"""

    stock_pool = settings.DEFAULT_STOCK_POOL

    print("\n开始获取财务数据...")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for ts_code in tqdm(stock_pool, desc="获取财务指标"):
        try:
            # 获取最近 4 个季度的财务数据
            df = ts_client.get_financial_indicators(ts_code)

            if df is not None and not df.empty:
                db.insert_df(df, 'financial_indicators', if_exists='append')
                success_count += 1
                tqdm.write(f"[OK] {ts_code}: {len(df)} 条")
            else:
                fail_count += 1

            time.sleep(0.3)

        except Exception as e:
            fail_count += 1
            tqdm.write(f"[ERROR] {ts_code}: {e}")
            time.sleep(1)

    print(f"\n财务数据获取完成: 成功 {success_count}, 失败 {fail_count}")


def fetch_trade_calendar():
    """获取交易日历"""

    print("\n开始获取交易日历...")

    try:
        # 获取 2023-2026 年交易日历
        df = ts_client.get_trade_calendar(
            start_date='20230101',
            end_date='20261231'
        )

        if df is not None and not df.empty:
            db.insert_df(df, 'trade_cal', if_exists='replace')
            print(f"[OK] 交易日历: {len(df)} 条记录")
        else:
            print("[WARN] 交易日历获取失败")

    except Exception as e:
        print(f"[ERROR] 交易日历获取失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='补全历史数据')
    parser.add_argument('--financial', action='store_true', help='同时获取财务数据')
    parser.add_argument('--calendar', action='store_true', help='同时获取交易日历')
    parser.add_argument('--verify-only', action='store_true', help='仅验证数据')

    args = parser.parse_args()

    if args.verify_only:
        verify_data()
    else:
        # 获取日线数据
        fetch_3year_data()

        # 可选：获取财务数据
        if args.financial:
            fetch_financial_data()

        # 可选：获取交易日历
        if args.calendar:
            fetch_trade_calendar()

        print("\n[SUCCESS] 所有数据获取完成!")
