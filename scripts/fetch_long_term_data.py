"""
获取更长历史数据 (5-10 年)
用于更准确的股票筛选和回测验证

数据来源：Baostock (免费)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import baostock as bs
import pandas as pd
from datetime import datetime
import os
from config.logging_config import strategy_logger

# 配置
OUTPUT_DIR = "data/cache/long_term"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 候选股票池 (沪深 300 成分股子集)
CANDIDATE_STOCKS = [
    # 金融
    '600000.SH', '600016.SH', '600030.SH', '600036.SH', '600048.SH',
    '601166.SH', '601318.SH', '601328.SH', '601398.SH', '601939.SH',
    # 消费
    '000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ',
    '000333.SZ', '000538.SZ', '000568.SZ', '000651.SZ', '000858.SZ',
    # 科技
    '000066.SZ', '000100.SZ', '000725.SZ', '000977.SZ', '002001.SZ',
    '002230.SZ', '002415.SZ', '002475.SZ', '300014.SZ', '300059.SZ',
    # 医药
    '000538.SZ', '000963.SZ', '600196.SH', '600276.SH', '600436.SH',
    '600519.SH', '600535.SH', '600867.SH', '603259.SH', '603882.SH',
    # 周期
    '000009.SZ', '000012.SZ', '000025.SZ', '000027.SZ', '000028.SZ',
    '000039.SZ', '000060.SZ', '000061.SZ', '000069.SZ', '000078.SZ',
]

# 扩展股票池 (更多沪深 300 成分股)
EXTENDED_STOCKS = [
    '000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ',
    '000009.SZ', '000012.SZ', '000025.SZ', '000027.SZ', '000028.SZ',
    '000039.SZ', '000060.SZ', '000061.SZ', '000066.SZ', '000069.SZ',
    '000078.SZ', '000089.SZ', '000100.SZ', '000157.SZ', '000166.SZ',
    '000176.SZ', '000425.SZ', '000488.SZ', '000538.SZ', '000568.SZ',
    '000596.SZ', '000625.SZ', '000651.SZ', '000725.SZ', '000761.SZ',
    '000776.SZ', '000783.SZ', '000858.SZ', '000876.SZ', '000895.SZ',
    '000938.SZ', '000963.SZ', '001979.SZ', '002001.SZ', '002007.SZ',
    '002027.SZ', '002032.SZ', '002044.SZ', '002049.SZ', '002050.SZ',
    '002120.SZ', '002129.SZ', '002142.SZ', '002146.SZ', '002153.SZ',
    '002157.SZ', '002179.SZ', '002185.SZ', '002202.SZ', '002230.SZ',
    '002236.SZ', '002241.SZ', '002252.SZ', '002271.SZ', '002299.SZ',
    '002304.SZ', '002310.SZ', '002311.SZ', '002352.SZ', '002371.SZ',
    '002385.SZ', '002410.SZ', '002415.SZ', '002422.SZ', '002456.SZ',
    '002466.SZ', '002475.SZ', '002508.SZ', '002555.SZ', '002594.SZ',
    '002601.SZ', '002607.SZ', '002624.SZ', '002714.SZ', '002736.SZ',
    '002739.SZ', '002773.SZ', '002821.SZ', '002841.SZ', '300003.SZ',
    '300014.SZ', '300015.SZ', '300033.SZ', '300059.SZ', '300122.SZ',
    '300124.SZ', '300136.SZ', '300142.SZ', '300144.SZ', '300251.SZ',
    '300347.SZ', '300408.SZ', '300413.SZ', '300433.SZ', '300498.SZ',
]

# 时间范围
START_DATE = '20180101'  # 5 年数据
END_DATE = '20260324'

def fetch_stock_data(ts_code: str) -> pd.DataFrame:
    """获取单只股票历史数据"""
    try:
        rs = bs.query_history_k_data_plus(
            ts_code,
            "date,code,open,high,low,close,volume,amount,turn",
            start_date=START_DATE,
            end_date=END_DATE,
            frequency="d",
            adjustflag="3"  # 不复权
        )

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return pd.DataFrame()

        df = pd.DataFrame(data_list, columns=rs.fields)
        df['trade_date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d')
        df = df.astype({
            'open': float, 'high': float, 'low': float, 'close': float,
            'volume': float, 'amount': float
        })
        df = df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low',
                               'close': 'close', 'volume': 'vol', 'amount': 'amount'})
        df = df[['trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']]
        return df

    except Exception as e:
        strategy_logger.error(f"{ts_code} 数据获取失败：{e}")
        return pd.DataFrame()

def fetch_industry_data():
    """获取行业指数数据"""
    industries = [
        ('金融', 'sh.000037'),
        ('消费', 'sh.000036'),
        ('科技', 'sh.000038'),
        ('医药', 'sh.000039'),
        ('周期', 'sh.000040'),
    ]

    result = {}
    for name, code in industries:
        try:
            rs = bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,volume",
                start_date=START_DATE,
                end_date=END_DATE,
                frequency="d",
                adjustflag="3"
            )
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if data_list:
                df = pd.DataFrame(data_list, columns=rs.fields)
                df['trade_date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d')
                result[name] = df
        except Exception as e:
            strategy_logger.error(f"行业 {name} 数据获取失败：{e}")

    return result

def main():
    print("=" * 80)
    print("获取长周期历史数据 (5-10 年)")
    print("=" * 80)
    print(f"时间范围：{START_DATE} - {END_DATE}")
    print(f"候选股票：{len(EXTENDED_STOCKS)} 只")
    print()

    # 登录 Baostock
    print("登录 Baostock...")
    lg = bs.login()
    print(f"登录状态：{'成功' if lg.error_code == '0' else '失败'}")
    print()

    # 获取股票数据
    print("开始获取股票数据...")
    stock_data = {}
    success_count = 0

    for i, ts_code in enumerate(EXTENDED_STOCKS, 1):
        print(f"[{i}/{len(EXTENDED_STOCKS)}] {ts_code}", end=" ... ")
        df = fetch_stock_data(ts_code)
        if len(df) > 100:
            stock_data[ts_code] = df
            success_count += 1
            print(f"成功 ({len(df)}条)")
        else:
            print("数据不足")

    print(f"\n成功获取：{success_count}/{len(EXTENDED_STOCKS)} 只")

    # 保存数据
    print(f"\n保存数据到 {OUTPUT_DIR}...")
    for ts_code, df in stock_data.items():
        file_name = ts_code.replace('.', '_') + '.csv'
        file_path = os.path.join(OUTPUT_DIR, file_name)
        df.to_csv(file_path, index=False)

    print(f"已保存 {len(stock_data)} 只股票数据")

    # 统计信息
    print("\n" + "=" * 80)
    print("数据统计")
    print("=" * 80)
    for ts_code, df in stock_data.items():
        if len(df) > 0:
            start = df['trade_date'].iloc[0]
            end = df['trade_date'].iloc[-1]
            print(f"{ts_code}: {start} - {end} ({len(df)}条)")

    print(f"\n数据已保存至：{OUTPUT_DIR}")

if __name__ == "__main__":
    main()
