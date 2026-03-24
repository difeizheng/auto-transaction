"""
参数网格搜索脚本 - 真实回测版
测试不同参数组合的表现并找到最优配置

使用方法:
    python scripts/run_parameter_search.py

输出:
    - 命令行显示各参数组合的表现
    - data/cache/parameter_search_result.csv 保存完整结果
    - 自动保存最优参数到文件
"""
import sys
import pandas as pd
import numpy as np
from itertools import product
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer
from src.data_collector.data_manager import data_manager

# 参数网格 - 聚焦于更有希望的区域
PARAM_GRID = {
    'stop_loss': [0.04, 0.05, 0.06, 0.07],
    'take_profit': [0.15, 0.18, 0.22, 0.28],
    'signal_threshold': [4.0, 4.5, 5.0, 5.5],
    'ma_short': [3, 5],
    'ma_long': [15, 20],
}

# 回测配置
STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000

# 结果缓存目录
CACHE_DIR = Path('data/cache')
CACHE_DIR.mkdir(exist_ok=True)


def load_data(stocks, start_date, end_date):
    """加载股票数据"""
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict


def create_strategy_with_params(stop_loss, take_profit, signal_threshold, ma_short=5, ma_long=20):
    """创建指定参数的策略"""
    params = OptimalStrategyParams(
        base_stop_loss=stop_loss,
        base_take_profit=take_profit,
        signal_threshold=signal_threshold,
        ma_short=ma_short,
        ma_long=ma_long,
    )
    return OptimalStrategy(name=f"optimal_{stop_loss}_{take_profit}", params=params)


def run_single_backtest(params):
    """运行单次参数组合的回测"""
    stop_loss, take_profit, threshold, ma_short, ma_long = params

    # 检查缓存
    cache_key = f"sl{stop_loss}_tp{take_profit}_thr{threshold}_mas{ma_short}_mal{ma_long}"
    cache_file = CACHE_DIR / f"backtest_{cache_key}.csv"

    if cache_file.exists():
        print(f"  [缓存] {cache_key}")
        cached_result = pd.read_csv(cache_file)
        return cached_result.iloc[0].to_dict()

    print(f"  [测试] SL={stop_loss*100:.0f}%, TP={take_profit*100:.0f}%, Thr={threshold}, MA={ma_short}/{ma_long}", end=" ... ")

    try:
        # 创建策略
        strategy = create_strategy_with_params(stop_loss, take_profit, threshold, ma_short, ma_long)

        # 加载数据
        data_dict = load_data(STOCKS, START_DATE, END_DATE)

        if not data_dict:
            print("无数据")
            return None

        # 运行回测
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        # 绩效分析
        analyzer = PerformanceAnalyzer()
        report_dict = analyzer.analyze(result)

        # 保存结果
        result_row = {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'signal_threshold': threshold,
            'ma_short': ma_short,
            'ma_long': ma_long,
            'total_return': result.get('total_return', 0),
            'annual_return': report_dict.get('annual_return', 0),
            'sharpe': report_dict.get('sharpe_ratio', 0),
            'max_drawdown': report_dict.get('max_drawdown', 0),
            'win_rate': report_dict.get('win_rate', 0),
            'profit_loss_ratio': report_dict.get('profit_loss_ratio', 0),
            'total_trades': result.get('total_trades', 0),
        }

        # 缓存结果
        pd.DataFrame([result_row]).to_csv(cache_file, index=False)

        print(f"年化={result_row['annual_return']*100:.2f}%, 夏普={result_row['sharpe']:.2f}, "
              f"回撤={result_row['max_drawdown']*100:.2f}%, 胜率={result_row['win_rate']*100:.1f}%")

        return result_row

    except Exception as e:
        print(f"错误：{e}")
        return None


def main():
    """主函数"""
    print("=" * 90)
    print("参数网格搜索 - 真实回测版")
    print("=" * 90)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print(f"参数组合数：{len(PARAM_GRID['stop_loss']) * len(PARAM_GRID['take_profit']) * "
          f"{len(PARAM_GRID['signal_threshold']) * len(PARAM_GRID['ma_short']) * len(PARAM_GRID['ma_long'])}")
    print()

    results = []

    # 生成所有参数组合
    param_combinations = list(product(
        PARAM_GRID['stop_loss'],
        PARAM_GRID['take_profit'],
        PARAM_GRID['signal_threshold'],
        PARAM_GRID['ma_short'],
        PARAM_GRID['ma_long']
    ))

    print(f"总测试组合数：{len(param_combinations)}")
    print()

    # 运行回测
    for i, params in enumerate(param_combinations, 1):
        print(f"[{i}/{len(param_combinations)}]", end=" ")
        result = run_single_backtest(params)
        if result:
            results.append(result)

    if not results:
        print("\n没有成功的回测结果")
        return

    # 转换为 DataFrame
    df = pd.DataFrame(results)

    # 保存所有结果
    output_file = CACHE_DIR / "parameter_search_result.csv"
    df.to_csv(output_file, index=False)
    print(f"\n结果已保存至：{output_file}")

    # 显示结果
    print("\n" + "=" * 90)
    print("回测结果汇总")
    print("=" * 90)

    # 按夏普比率排序
    print("\n【Top 10 - 按夏普比率】")
    top_sharpe = df.nlargest(10, 'sharpe')
    display_cols = ['stop_loss', 'take_profit', 'signal_threshold', 'ma_short', 'ma_long',
                    'annual_return', 'sharpe', 'max_drawdown', 'win_rate', 'profit_loss_ratio']
    for _, row in top_sharpe.iterrows():
        print(f"SL={row['stop_loss']:.0f}%, TP={row['take_profit']:.0f}%, Thr={row['signal_threshold']}, "
              f"MA={row['ma_short']}/{row['ma_long']} -> "
              f"年化={row['annual_return']*100:.2f}%, 夏普={row['sharpe']:.2f}, "
              f"回撤={row['max_drawdown']*100:.2f}%, 胜率={row['win_rate']*100:.1f}%")

    # 按年化收益排序
    print("\n【Top 10 - 按年化收益】")
    top_return = df.nlargest(10, 'annual_return')
    for _, row in top_return.iterrows():
        print(f"SL={row['stop_loss']:.0f}%, TP={row['take_profit']:.0f}%, Thr={row['signal_threshold']}, "
              f"MA={row['ma_short']}/{row['ma_long']} -> "
              f"年化={row['annual_return']*100:.2f}%, 夏普={row['sharpe']:.2f}, "
              f"回撤={row['max_drawdown']*100:.2f}%, 胜率={row['win_rate']*100:.1f}%")

    # 按最大回撤排序
    print("\n【Top 10 - 按最大回撤（从小到大）】")
    top_dd = df.nsmallest(10, 'max_drawdown')
    for _, row in top_dd.iterrows():
        print(f"SL={row['stop_loss']:.0f}%, TP={row['take_profit']:.0f}%, Thr={row['signal_threshold']}, "
              f"MA={row['ma_short']}/{row['ma_long']} -> "
              f"年化={row['annual_return']*100:.2f}%, 夏普={row['sharpe']:.2f}, "
              f"回撤={row['max_drawdown']*100:.2f}%, 胜率={row['win_rate']*100:.1f}%")

    # 有效前沿分析
    print("\n" + "=" * 90)
    print("有效前沿分析（夏普>0.5, 回撤<15%, 年化>8%）")
    print("=" * 90)
    efficient = df[
        (df['sharpe'] > 0.5) &
        (df['max_drawdown'] < 0.15) &
        (df['annual_return'] > 0.08)
    ]
    if len(efficient) > 0:
        print(f"找到 {len(efficient)} 个有效参数组合:")
        for _, row in efficient.nlargest(5, 'sharpe').iterrows():
            print(f"  SL={row['stop_loss']:.0f}%, TP={row['take_profit']:.0f}%, Thr={row['signal_threshold']} -> "
                  f"年化={row['annual_return']*100:.2f}%, 夏普={row['sharpe']:.2f}, 回撤={row['max_drawdown']*100:.2f}%")
    else:
        print("未找到符合有效前沿条件的参数组合")
        print("放宽条件：夏普>0.3, 回撤<20%, 年化>3%")
        efficient = df[
            (df['sharpe'] > 0.3) &
            (df['max_drawdown'] < 0.20) &
            (df['annual_return'] > 0.03)
        ]
        if len(efficient) > 0:
            print(f"找到 {len(efficient)} 个放宽条件的参数组合:")
            for _, row in efficient.nlargest(5, 'sharpe').iterrows():
                print(f"  SL={row['stop_loss']:.0f}%, TP={row['take_profit']:.0f}%, Thr={row['signal_threshold']} -> "
                      f"年化={row['annual_return']*100:.2f}%, 夏普={row['sharpe']:.2f}, 回撤={row['max_drawdown']*100:.2f}%")

    # 生成最优参数推荐
    print("\n" + "=" * 90)
    print("最优参数推荐")
    print("=" * 90)

    # 综合评分 = 夏普 * 0.4 + 年化 * 0.3 + (1-回撤) * 0.3
    df['composite_score'] = (
        df['sharpe'] * 0.4 +
        df['annual_return'] * 10 * 0.3 +  # 年化处理
        (1 - df['max_drawdown']) * 0.3
    )

    best = df.loc[df['composite_score'].idxmax()]
    print(f"\n综合最优参数组合:")
    print(f"  止损：{best['stop_loss']*100:.0f}%")
    print(f"  止盈：{best['take_profit']*100:.0f}%")
    print(f"  信号阈值：{best['signal_threshold']}")
    print(f"  均线周期：{best['ma_short']}/{best['ma_long']}")
    print(f"\n预期表现:")
    print(f"  年化收益：{best['annual_return']*100:.2f}%")
    print(f"  夏普比率：{best['sharpe']:.2f}")
    print(f"  最大回撤：{best['max_drawdown']*100:.2f}%")
    print(f"  胜率：{best['win_rate']*100:.1f}%")
    print(f"  盈亏比：{best['profit_loss_ratio']:.2f}")


if __name__ == "__main__":
    main()
