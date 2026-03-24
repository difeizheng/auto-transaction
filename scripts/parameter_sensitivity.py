"""
参数敏感性分析脚本 - 真实回测版
测试不同止损止盈参数组合的表现

使用方法:
    python scripts/parameter_sensitivity.py

输出:
    - 命令行显示各参数组合的表现
    - data/parameter_sensitivity_result.csv 保存完整结果
"""
import subprocess
import re
import pandas as pd
from itertools import product
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 参数网格 - 扩大测试范围
STOP_LOSS_LIST = [0.04, 0.05, 0.06, 0.07, 0.08, 0.10]
TAKE_PROFIT_LIST = [0.12, 0.15, 0.18, 0.20, 0.25, 0.30]
THRESHOLD_LIST = [3.5, 4.0, 4.5, 5.0, 5.5]

# 回测参数 - 使用 3 年数据验证
STOCKS = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
START_DATE = '20230324'
END_DATE = '20260323'

# 结果缓存目录
CACHE_DIR = Path('data/cache')
CACHE_DIR.mkdir(exist_ok=True)


def parse_backtest_output(output: str) -> dict:
    """解析回测输出，提取绩效指标"""
    result = {
        'total_return': 0.0,
        'annual_return': 0.0,
        'sharpe': 0.0,
        'win_rate': 0.0,
        'profit_loss_ratio': 0.0,
        'max_drawdown': 0.0,
        'total_trades': 0
    }

    try:
        # 提取总收益率
        match = re.search(r'总收益率：\s*([\-0-9.]+)%', output)
        if match:
            result['total_return'] = float(match.group(1)) / 100

        # 提取年化收益率
        match = re.search(r'年化收益率：\s*([\-0-9.]+)%', output)
        if match:
            result['annual_return'] = float(match.group(1)) / 100

        # 提取夏普比率
        match = re.search(r'夏普比率：\s*([\-0-9.]+)', output)
        if match:
            result['sharpe'] = float(match.group(1))

        # 提取胜率
        match = re.search(r'胜率：\s*([\-0-9.]+)%', output)
        if match:
            result['win_rate'] = float(match.group(1)) / 100

        # 提取盈亏比
        match = re.search(r'盈亏比：\s*([\-0-9.]+)', output)
        if match:
            result['profit_loss_ratio'] = float(match.group(1))

        # 提取最大回撤
        match = re.search(r'最大回撤：\s*([\-0-9.]+)%', output)
        if match:
            result['max_drawdown'] = float(match.group(1)) / 100

        # 提取总交易次数
        match = re.search(r'总交易次数：\s*(\d+)', output)
        if match:
            result['total_trades'] = int(match.group(1))

    except Exception as e:
        print(f"  解析输出失败：{e}")

    return result


def run_backtest(stop_loss, take_profit, threshold):
    """运行单次回测并提取结果"""
    cache_file = CACHE_DIR / f"backtest_sl{stop_loss}_tp{take_profit}_thr{threshold}.txt"

    # 检查缓存
    if cache_file.exists():
        print(f"  [缓存] SL={stop_loss*100:.0f}%, TP={take_profit*100:.0f}%, Thr={threshold}")
        with open(cache_file, 'r', encoding='utf-8') as f:
            output = f.read()
        return parse_backtest_output(output)

    print(f"  [测试] SL={stop_loss*100:.0f}%, TP={take_profit*100:.0f}%, Thr={threshold}", end=" ... ")

    # 构建真实回测命令 - 通过修改策略参数运行回测
    # 使用 main.py 的命令行接口传递参数
    cmd = (
        f'python main.py backtest --strategy optimal '
        f'--start-date {START_DATE} --end-date {END_DATE} '
        f'--capital 1000000 2>&1'
    )

    # 由于命令行不直接支持止损止盈参数，我们需要临时修改策略文件或通过 Python API 调用
    # 这里采用直接 Python 调用的方式
    python_code = f'''
import sys
sys.path.insert(0, '.')
from pathlib import Path

# 临时修改策略参数
from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy

# 创建自定义参数
params = OptimalStrategyParams(
    base_stop_loss={stop_loss},
    base_take_profit={take_profit},
    signal_threshold={threshold}
)

# 从 main.py 导入 run_backtest
from main import run_backtest

# 运行回测 - 需要修改 run_backtest 以支持参数传递
result = run_backtest(
    strategy='optimal',
    stocks={STOCKS},
    start_date='{START_DATE}',
    end_date='{END_DATE}',
    initial_capital=1000000,
    stop_loss={stop_loss},
    take_profit={take_profit},
    signal_threshold={threshold}
)

# 输出结果
print(f"总收益率：{{result.get('total_return', 0)*100:.2f}}%")
print(f"年化收益率：{{result.get('annual_return', 0)*100:.2f}}%")
print(f"夏普比率：{{result.get('sharpe_ratio', 0):.2f}}")
print(f"最大回撤：{{result.get('max_drawdown', 0)*100:.2f}}%")
print(f"胜率：{{result.get('win_rate', 0)*100:.2f}}%")
print(f"盈亏比：{{result.get('profit_loss_ratio', 0):.2f}}")
print(f"总交易次数：{{result.get('total_trades', 0)}}")
'''

    try:
        # 运行 Python 代码
        result_output = subprocess.run(
            ['python', '-c', python_code],
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result_output.stdout + result_output.stderr

        # 保存缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(output)

        # 解析结果
        result = parse_backtest_output(output)
        result['stop_loss'] = stop_loss
        result['take_profit'] = take_profit
        result['threshold'] = threshold

        if result['annual_return'] != 0 or result['sharpe'] != 0:
            print(f"年化={result['annual_return']*100:.2f}%, 夏普={result['sharpe']:.2f}, 回撤={result['max_drawdown']*100:.2f}%")
        else:
            print(f"失败")

        return result

    except subprocess.TimeoutExpired:
        print(f"超时")
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'threshold': threshold,
            'total_return': 0.0,
            'annual_return': 0.0,
            'sharpe': 0.0,
            'win_rate': 0.0,
            'profit_loss_ratio': 0.0,
            'max_drawdown': 0.0,
            'total_trades': 0
        }
    except Exception as e:
        print(f"错误：{e}")
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'threshold': threshold,
            'total_return': 0.0,
            'annual_return': 0.0,
            'sharpe': 0.0,
            'win_rate': 0.0,
            'profit_loss_ratio': 0.0,
            'max_drawdown': 0.0,
            'total_trades': 0
        }


def main():
    """主函数"""
    print("=" * 80)
    print("参数敏感性分析")
    print("=" * 80)
    print(f"止损测试范围：{[int(x*100) for x in STOP_LOSS_LIST]}%")
    print(f"止盈测试范围：{[int(x*100) for x in TAKE_PROFIT_LIST]}%")
    print(f"阈值测试范围：{THRESHOLD_LIST}")
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print(f"测试组合数：{len(STOP_LOSS_LIST) * len(TAKE_PROFIT_LIST) * len(THRESHOLD_LIST)}")
    print()
    print("**注意**: 当前为估算模型，需要实现真实回测以获得准确结果")
    print()

    results = []

    # 全因子测试
    for sl, tp, thr in product(STOP_LOSS_LIST, TAKE_PROFIT_LIST, THRESHOLD_LIST):
        result = run_backtest(sl, tp, thr)
        results.append(result)

    # 转换为 DataFrame
    df = pd.DataFrame(results)

    # 排序并显示最优组合
    print("\n" + "=" * 80)
    print("按夏普比率排序 - Top 10")
    print("=" * 80)
    top10_sharpe = df.nlargest(10, 'sharpe')
    print(top10_sharpe[['stop_loss', 'take_profit', 'threshold', 'annual_return', 'sharpe', 'max_drawdown', 'win_rate', 'profit_loss_ratio']].to_string(index=False))

    print("\n" + "=" * 80)
    print("按年化收益排序 - Top 10")
    print("=" * 80)
    top10_return = df.nlargest(10, 'annual_return')
    print(top10_return[['stop_loss', 'take_profit', 'threshold', 'annual_return', 'sharpe', 'max_drawdown', 'win_rate', 'profit_loss_ratio']].to_string(index=False))

    print("\n" + "=" * 80)
    print("按最大回撤排序 - Top 10 (从小到大)")
    print("=" * 80)
    top10_dd = df.nsmallest(10, 'max_drawdown')
    print(top10_dd[['stop_loss', 'take_profit', 'threshold', 'annual_return', 'sharpe', 'max_drawdown', 'win_rate', 'profit_loss_ratio']].to_string(index=False))

    # 保存结果
    output_file = 'data/parameter_sensitivity_result.csv'
    df.to_csv(output_file, index=False)
    print(f"\n结果已保存至：{output_file}")

    # 有效前沿分析
    print("\n" + "=" * 80)
    print("有效前沿分析（高夏普/低回撤/高收益区域）")
    print("=" * 80)
    # 筛选条件：夏普>0.4, 回撤<10%, 年化>5%
    efficient = df[
        (df['sharpe'] > 0.4) &
        (df['max_drawdown'] < 0.10) &
        (df['annual_return'] > 0.05)
    ]
    if len(efficient) > 0:
        print(f"找到 {len(efficient)} 个有效前沿参数组合:")
        print(efficient[['stop_loss', 'take_profit', 'threshold', 'annual_return', 'sharpe', 'max_drawdown', 'win_rate', 'profit_loss_ratio']].to_string(index=False))
    else:
        print("未找到符合有效前沿条件的参数组合")
        print("建议：调整筛选条件或检查策略逻辑")

    # 热力图数据
    print("\n" + "=" * 80)
    print("热力图数据（按止损/止盈分组的平均年化收益）")
    print("=" * 80)
    pivot_return = df.groupby(['stop_loss', 'take_profit'])['annual_return'].mean().unstack()
    print(pivot_return.to_string())

    # 保存热力图数据
    pivot_file = 'data/parameter_sensitivity_heatmap.csv'
    pivot_return.to_csv(pivot_file)
    print(f"\n热力图数据已保存至：{pivot_file}")

    # 生成报告
    print("\n" + "=" * 80)
    print("参数敏感性分析报告")
    print("=" * 80)

    best_sl = df.loc[df['sharpe'].idxmax(), 'stop_loss']
    best_tp = df.loc[df['sharpe'].idxmax(), 'take_profit']
    best_thr = df.loc[df['sharpe'].idxmax(), 'threshold']

    print(f"最优夏普比率参数组合:")
    print(f"  止损：{best_sl*100:.0f}%")
    print(f"  止盈：{best_tp*100:.0f}%")
    print(f"  阈值：{best_thr}")
    print(f"  夏普比率：{df['sharpe'].max():.3f}")
    print(f"  年化收益：{df.loc[df['sharpe'].idxmax(), 'annual_return']*100:.2f}%")
    print(f"  最大回撤：{df.loc[df['sharpe'].idxmax(), 'max_drawdown']*100:.2f}%")


if __name__ == "__main__":
    main()
