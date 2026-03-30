"""
批量获取历史日线数据
用于补全 5 年历史数据（2021-2026）

使用方法：
    python scripts/fetch_5year_data.py
"""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config.settings as settings
from src.data_collector.tushare_client import ts_client
from src.data_collector.data_manager import data_manager
from config.logging_config import data_logger


def fetch_5year_data(stock_pool=None, days_per_batch=100):
    """
    批量获取 5 年历史数据

    Args:
        stock_pool: 股票池，默认使用配置
        days_per_batch: 每次请求的天数（避免接口超时）
    """
    stock_pool = stock_pool or settings.DEFAULT_STOCK_POOL

    # 计算时间范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=365*5 + 30)).strftime('%Y%m%d')

    data_logger.info("=" * 60)
    data_logger.info("开始获取 5 年历史数据")
    data_logger.info(f"股票池: {len(stock_pool)} 只")
    data_logger.info(f"时间范围: {start_date} ~ {end_date}")
    data_logger.info("=" * 60)

    # 分批获取（避免请求超时）
    total_success = 0
    total_failed = 0

    for i, ts_code in enumerate(stock_pool):
        try:
            # 分段获取数据
            current_start = start_date
            batch_count = 0

            while current_start < end_date:
                # 计算本次获取的结束日期
                current_end = (datetime.strptime(current_start, '%Y%m%d') +
                              timedelta(days=days_per_batch)).strftime('%Y%m%d')
                if current_end > end_date:
                    current_end = end_date

                # 获取数据
                df = ts_client.get_daily_quotes(
                    ts_code=ts_code,
                    start_date=current_start,
                    end_date=current_end,
                    save_to_db=True
                )

                batch_count += 1

                # 移动到下一个时间段
                current_start = (datetime.strptime(current_end, '%Y%m%d') +
                                timedelta(days=1)).strftime('%Y%m%d')

                # 避免请求过快
                time.sleep(0.3)

            # 检查数据完整性
            df_check = data_manager.get_daily_quotes(ts_code)
            if not df_check.empty:
                total_success += 1
                data_logger.info(f"[{i+1}/{len(stock_pool)}] {ts_code}: {len(df_check)} 条")
            else:
                total_failed += 1
                data_logger.warning(f"[{i+1}/{len(stock_pool)}] {ts_code}: 无数据")

        except Exception as e:
            total_failed += 1
            data_logger.error(f"[{i+1}/{len(stock_pool)}] {ts_code} 失败: {e}")

        # 每 10 只打印进度
        if (i + 1) % 10 == 0:
            data_logger.info(f"进度: {i+1}/{len(stock_pool)}, 成功: {total_success}, 失败: {total_failed}")

    data_logger.info("=" * 60)
    data_logger.info(f"5 年历史数据获取完成")
    data_logger.info(f"总计: {len(stock_pool)}, 成功: {total_success}, 失败: {total_failed}")
    data_logger.info("=" * 60)

    return {
        'total': len(stock_pool),
        'success': total_success,
        'failed': total_failed
    }


def verify_data_completeness(stock_pool=None):
    """
    验证数据完整性

    Args:
        stock_pool: 股票池
    """
    stock_pool = stock_pool or settings.DEFAULT_STOCK_POOL

    data_logger.info("=" * 60)
    data_logger.info("验证数据完整性")
    data_logger.info("=" * 60)

    # 期望的天数（约 5 年 × 250 交易日 = 1250 天）
    # 考虑节假日，1250 ~ 1300 天是合理的
    min_days = 1200

    complete_stocks = []
    incomplete_stocks = []

    for ts_code in stock_pool:
        df = data_manager.get_daily_quotes(ts_code)
        days = len(df) if not df.empty else 0

        if days >= min_days:
            complete_stocks.append(ts_code)
        else:
            incomplete_stocks.append({
                'ts_code': ts_code,
                'days': days,
                'first_date': df['trade_date'].min() if not df.empty else None,
                'last_date': df['trade_date'].max() if not df.empty else None
            })

    data_logger.info(f"完整数据 (>= {min_days} 天): {len(complete_stocks)} 只")
    data_logger.info(f"不完整数据: {len(incomplete_stocks)} 只")

    if incomplete_stocks:
        data_logger.warning("不完整股票:")
        for item in incomplete_stocks[:10]:
            data_logger.warning(f"  {item['ts_code']}: {item['days']} 天 "
                               f"({item.get('first_date')} ~ {item.get('last_date')})")

    return {
        'complete': complete_stocks,
        'incomplete': incomplete_stocks,
        'min_days': min_days
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='获取5年历史数据')
    parser.add_argument('--verify', action='store_true', help='只验证数据完整性')
    parser.add_argument('--days', type=int, default=100, help='每次请求的天数')

    args = parser.parse_args()

    if args.verify:
        verify_data_completeness()
    else:
        fetch_5year_data(days_per_batch=args.days)