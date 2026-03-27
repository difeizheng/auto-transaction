"""
市场状态判断逻辑测试
验证增强版市场过滤器的判断效果
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.data_collector.data_manager import data_manager
from src.strategy.market_filter import MarketFilter, MarketFilterParams, create_market_filter


def test_market_filter():
    """测试市场状态判断"""
    print("=" * 70)
    print("市场状态判断逻辑测试")
    print("=" * 70)

    # 获取沪深 300 数据 (用 000300.SZ 或替代数据)
    print("\n获取市场数据...")

    # 使用 000001.SZ (平安银行) 作为市场代表 (简化测试)
    ts_code = '000001.SZ'
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

    df = data_manager.get_daily_quotes(ts_code, start_date, end_date)

    if df.empty:
        print(f"无法获取 {ts_code} 的数据")
        return

    print(f"数据区间：{df['trade_date'].iloc[0]} 至 {df['trade_date'].iloc[-1]}")
    print(f"数据条数：{len(df)}")

    # 创建市场过滤器 (增强版)
    params = MarketFilterParams(
        ma_short=20,
        ma_long=60,
        ma_trend=120,
        macd_weight=0.25,
        rsi_weight=0.15,
        sideways_position=0.4,
        bull_weak_position=0.7,
        bear_weak_position=0.2,
    )

    market_filter = MarketFilter(params)
    market_filter.set_market_data(df)

    # 判断市场状态
    print("\n市场状态判断结果:")
    print("-" * 50)

    state = market_filter.determine_market_state()
    position_mult = market_filter.get_position_multiplier()

    print(f"当前市场状态：{state.value}")
    print(f"建议仓位系数：{position_mult:.0%}")

    # 获取状态摘要
    summary = market_filter.get_state_summary()
    print(f"\n历史状态分布:")
    print(f"  牛市占比：{summary.get('bull_ratio', 0):.1%}")
    print(f"  熊市占比：{summary.get('bear_ratio', 0):.1%}")
    print(f"  震荡市占比：{summary.get('sideways_ratio', 0):.1%}")

    # 测试不同参数的效果
    print("\n" + "=" * 70)
    print("参数敏感性测试")
    print("=" * 70)

    param_sets = [
        {'name': '默认参数', 'params': MarketFilterParams()},
        {'name': '激进参数 (高仓位)', 'params': MarketFilterParams(sideways_position=0.6, bull_weak_position=0.9)},
        {'name': '保守参数 (低仓位)', 'params': MarketFilterParams(sideways_position=0.2, bull_weak_position=0.5)},
        {'name': '高 MACD 权重', 'params': MarketFilterParams(macd_weight=0.4)},
        {'name': '高 RSI 权重', 'params': MarketFilterParams(rsi_weight=0.3)},
    ]

    print(f"\n{'参数配置':<20} {'市场状态':<15} {'仓位系数':>10}")
    print("-" * 50)

    for config in param_sets:
        mf_test = MarketFilter(config['params'])
        mf_test.set_market_data(df)
        state_test = mf_test.determine_market_state()
        mult_test = mf_test.get_position_multiplier()

        print(f"{config['name']:<20} {state_test.value:<15} {mult_test:>10.0%}")

    print("\n测试完成!")


if __name__ == "__main__":
    test_market_filter()
