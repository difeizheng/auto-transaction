"""
信号分析脚本 - 分析策略信号触发情况
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.data_collector.data_manager import data_manager
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_bollinger_bands

def analyze_signals():
    """分析信号触发情况"""

    # 获取数据
    stocks = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y%m%d')

    # 创建策略
    params = OptimalStrategyParams()
    strategy = OptimalStrategy(params=params)

    print("=" * 80)
    print("信号触发分析")
    print("=" * 80)
    print(f"参数配置：止损={params.base_stop_loss*100}%, 止盈={params.base_take_profit*100}%")
    print(f"触发阈值：3.5/7 (加权)")
    print()

    total_signals = 0
    score_distribution = []
    factor_triggered = {
        'golden_cross': 0,
        'macd_bullish': 0,
        'rsi_ok': 0,
        'rsi_oversold': 0,
        'bb_lower': 0,
        'volume_ok': 0,
        'trend_ok': 0
    }

    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if df.empty or len(df) < 60:
            print(f"{ts_code}: 数据不足，跳过")
            continue

        print(f"\n分析 {ts_code} ({len(df)} 天数据)...")

        # 计算指标
        close = df['close']
        vol = df['vol']

        ma_short = close.rolling(params.ma_short).mean()
        ma_long = close.rolling(params.ma_long).mean()
        ma_trend = close.rolling(params.ma_trend).mean()

        macd_data = calculate_macd(close, params.macd_fast, params.macd_slow, params.macd_signal)
        rsi = calculate_rsi(close, params.rsi_period)
        bb_data = calculate_bollinger_bands(close, params.bb_window, params.bb_num_std)
        vol_ma = vol.rolling(params.volume_ma_period).mean()

        # 逐日分析
        for i in range(60, len(df)):
            current_price = close.iloc[i]

            # 1. 均线金叉
            golden_cross = (ma_short.iloc[i-1] <= ma_long.iloc[i-1] and
                           ma_short.iloc[i] > ma_long.iloc[i])

            # 2. MACD 多头
            dif = macd_data['dif'].iloc[i] if len(macd_data) > i else 0
            dea = macd_data['dea'].iloc[i] if len(macd_data) > i else 0
            macd = macd_data['macd'].iloc[i] if len(macd_data) > i else 0
            macd_bullish = dif > dea and macd > 0

            # 3. RSI 健康
            current_rsi = rsi.iloc[i] if len(rsi) > i else 50
            rsi_ok = params.rsi_oversold < current_rsi < params.rsi_overbought

            # 4. RSI 超卖
            rsi_oversold = current_rsi < params.rsi_oversold

            # 5. 布林带信号
            bb_lower = bb_data['lower'].iloc[i] if len(bb_data) > i else 0
            bb_upper = bb_data['upper'].iloc[i] if len(bb_data) > i else 0
            bb_signal = 'lower' if current_price <= bb_lower * 1.01 else ('upper' if current_price >= bb_upper * 0.99 else 'middle')

            # 6. 成交量放大
            current_vol = vol.iloc[i]
            current_vol_ma = vol_ma.iloc[i] if len(vol_ma) > i else 0
            volume_ok = current_vol > current_vol_ma * params.volume_ratio_threshold if current_vol_ma > 0 else True

            # 7. 趋势判断
            trend_ok = current_price > ma_trend.iloc[i] * (1 + params.trend_threshold)

            # 统计因子触发
            if golden_cross: factor_triggered['golden_cross'] += 1
            if macd_bullish: factor_triggered['macd_bullish'] += 1
            if rsi_ok: factor_triggered['rsi_ok'] += 1
            if rsi_oversold: factor_triggered['rsi_oversold'] += 1
            if bb_signal == 'lower': factor_triggered['bb_lower'] += 1
            if volume_ok: factor_triggered['volume_ok'] += 1
            if trend_ok: factor_triggered['trend_ok'] += 1

            # 计算评分
            score = 0.0
            if golden_cross: score += 1.5
            if macd_bullish: score += 1.0
            if rsi_ok: score += 0.5
            if rsi_oversold: score += 0.5
            if bb_signal == 'lower': score += 1.0
            if volume_ok: score += 1.0
            if trend_ok: score += 1.0

            score_distribution.append(score)

            if score >= 3.5:  # 修改阈值为 3.5
                total_signals += 1
                if total_signals <= 10:  # 只显示前 10 个信号
                    print(f"  [信号] {df['trade_date'].iloc[i]}: 得分={score:.1f}, "
                          f"金叉={golden_cross}, MACD={macd_bullish}, RSI_OK={rsi_ok}, "
                          f"RSI_OS={rsi_oversold}, BB={bb_signal}, Vol={volume_ok}, Trend={trend_ok}")

    # 汇总统计
    print("\n" + "=" * 80)
    print("因子触发频率统计")
    print("=" * 80)
    total_days = len(score_distribution)
    for factor, count in factor_triggered.items():
        rate = count / total_days * 100 if total_days > 0 else 0
        print(f"  {factor}: {count} 次 ({rate:.1f}%)")

    print("\n" + "=" * 80)
    print("得分分布统计")
    print("=" * 80)
    score_arr = np.array(score_distribution)
    print(f"  总天数：{total_days}")
    print(f"  平均分：{score_arr.mean():.2f}")
    print(f"  中位数：{np.median(score_arr):.2f}")
    print(f"  最高分：{score_arr.max():.2f}")
    print(f"  最低分：{score_arr.min():.2f}")
    print(f"  得分 >= 4.5 的天数：{np.sum(score_arr >= 4.5)} ({np.sum(score_arr >= 4.5)/total_days*100:.1f}%)")
    print(f"  得分 >= 5.0 的天数：{np.sum(score_arr >= 5.0)} ({np.sum(score_arr >= 5.0)/total_days*100:.1f}%)")
    print(f"  得分 >= 5.5 的天数：{np.sum(score_arr >= 5.5)} ({np.sum(score_arr >= 5.5)/total_days*100:.1f}%)")
    print(f"  得分 >= 3.5 的天数：{np.sum(score_arr >= 3.5)} ({np.sum(score_arr >= 3.5)/total_days*100:.1f}%)")

    print("\n" + "=" * 80)
    print(f"总信号数：{total_signals}")
    print("=" * 80)

    return total_signals, score_distribution

if __name__ == "__main__":
    analyze_signals()
