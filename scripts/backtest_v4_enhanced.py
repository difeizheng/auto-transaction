"""
策略优化回测脚本 - 增强版
支持：大股票池、多权重配置、长周期回测
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_collector.data_manager import data_manager
from src.data_collector.tushare_client import TushareClient
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.strategy.multi_strategy_portfolio import (
    create_multi_strategy_portfolio,
    MultiStrategyConfig,
    StrategyWeightMethod
)
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer


def run_enhanced_backtest(
    stock_pool_size: int = 50,
    backtest_years: int = 2,
    weight_methods: list = None
):
    """
    运行增强版回测

    Args:
        stock_pool_size: 股票池大小
        backtest_years: 回测年数
        weight_methods: 权重方法列表
    """
    print("=" * 70)
    print("策略优化回测 v4.0 - 增强版")
    print("=" * 70)

    # 1. 获取股票池
    print(f"\n[1/4] 准备股票池 (目标：{stock_pool_size} 只)...")

    ts_client = TushareClient()
    try:
        stocks_df = ts_client.get_stock_list(list_status='L')
        if not stocks_df.empty:
            # 选取活跃股票（按上市时间筛选）
            stocks_df['list_date'] = pd.to_numeric(stocks_df['list_date'], errors='coerce')
            stocks_df = stocks_df[stocks_df['list_date'] < 20240101]  # 2024 年前上市
            stock_pool = stocks_df['ts_code'].head(stock_pool_size).tolist()
            print(f"  已选取 {len(stock_pool)} 只活跃股票")
        else:
            stock_pool = []
    except Exception as e:
        print(f"  无法获取股票列表：{e}，使用预设股票池")
        stock_pool = []

    # 预设股票池作为备用
    preset_pool = [
        '000001.SZ', '000002.SZ', '000004.SZ', '000006.SZ', '000007.SZ',
        '000008.SZ', '000009.SZ', '000010.SZ', '000011.SZ', '000012.SZ',
        '000014.SZ', '000016.SZ', '000017.SZ', '000019.SZ', '000020.SZ',
        '000021.SZ', '000022.SZ', '000024.SZ', '000025.SZ', '000027.SZ',
        '000028.SZ', '000031.SZ', '000032.SZ', '000035.SZ', '000039.SZ',
        '000042.SZ', '000046.SZ', '000050.SZ', '000055.SZ', '000059.SZ',
        '000060.SZ', '000061.SZ', '000062.SZ', '000063.SZ', '000065.SZ',
        '000066.SZ', '000069.SZ', '000070.SZ', '000078.SZ', '000088.SZ',
        '000089.SZ', '000090.SZ', '000096.SZ', '000099.SZ', '000100.SZ',
        '000157.SZ', '000158.SZ', '000166.SZ', '000338.SZ', '000415.SZ',
    ]

    if len(stock_pool) < stock_pool_size:
        for code in preset_pool:
            if code not in stock_pool:
                stock_pool.append(code)
            if len(stock_pool) >= stock_pool_size:
                break

    print(f"  最终股票池：{len(stock_pool)} 只")

    # 2. 设置回测周期
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=backtest_years * 365)).strftime("%Y%m%d")
    print(f"\n[2/4] 回测周期：{start_date} 至 {end_date} ({backtest_years} 年)")

    # 3. 加载数据
    print(f"\n[3/4] 加载行情数据...")
    market_data = {}

    # 分批加载数据
    batch_size = 10
    for i in range(0, min(len(stock_pool), 30), batch_size):  # 最多加载 30 只
        batch = stock_pool[i:i+batch_size]
        print(f"  加载进度：{i}-{min(i+batch_size, len(stock_pool))}/{min(len(stock_pool), 30)}")
        for ts_code in batch:
            try:
                df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
                if not df.empty:
                    market_data[ts_code] = df
            except Exception:
                pass

    if not market_data:
        print("  错误：无法获取行情数据")
        return None

    print(f"  成功加载 {len(market_data)} 只股票数据")

    # 4. 运行回测对比
    print(f"\n[4/4] 运行策略回测...")
    print("=" * 70)

    # 权重方法配置
    if weight_methods is None:
        weight_methods = ['equal', 'performance', 'volatility', 'dynamic']

    results = []

    # 测试不同权重方法的多策略组合
    for weight_method in weight_methods:
        print(f"\n>>> 多策略组合 - {weight_method} 权重")

        try:
            strategy = create_multi_strategy_portfolio(
                enable_optimal=True,
                enable_trend=True,
                enable_mean_reversion=True,
                weight_method=weight_method
            )

            engine = BacktestEngine(
                initial_capital=100000,
                commission_rate=0.0003,
                stamp_tax_rate=0.001,
                slippage_rate=0.001,
                max_position_ratio=0.8
            )
            engine.set_strategy(strategy)

            data_dict = engine.load_data(
                ts_codes=list(market_data.keys()),
                start_date=start_date,
                end_date=end_date
            )
            result = engine.run(data_dict)

            analyzer = PerformanceAnalyzer()
            metrics_obj = analyzer.analyze(result)

            result_data = {
                'name': f'多策略 - {weight_method}',
                'total_return': metrics_obj.total_return * 100,
                'annual_return': metrics_obj.annual_return * 100,
                'sharpe': metrics_obj.sharpe_ratio,
                'win_rate': metrics_obj.win_rate * 100,
                'max_drawdown': metrics_obj.max_drawdown * 100,
                'total_trades': metrics_obj.total_trades,
            }
            results.append(result_data)

            print(f"  总收益：{result_data['total_return']:+.2f}%")
            print(f"  年化收益：{result_data['annual_return']:+.2f}%")
            print(f"  夏普比率：{result_data['sharpe']:.3f}")
            print(f"  胜率：{result_data['win_rate']:.1f}%")
            print(f"  最大回撤：{result_data['max_drawdown']:.2f}%")

        except Exception as e:
            print(f"  回测失败：{e}")
            results.append({
                'name': f'多策略 - {weight_method}',
                'error': str(e)
            })

    # 打印对比表
    print("\n" + "=" * 70)
    print("权重方法对比结果")
    print("=" * 70)
    print(f"{'策略名称':<25} {'总收益':>10} {'年化':>10} {'夏普':>8} {'胜率':>8} {'回撤':>10} {'交易次数':>10}")
    print("-" * 70)

    best_result = None
    best_sharpe = -999

    for r in results:
        if 'error' in r:
            print(f"{r['name']:<25} {'失败':>10}")
        else:
            print(f"{r['name']:<25} {r['total_return']:>+9.2f}% {r['annual_return']:>+9.2f}% "
                  f"{r['sharpe']:>8.3f} {r['win_rate']:>7.1f}% {r['max_drawdown']:>9.2f}% "
                  f"{r['total_trades']:>10}")
            if r['sharpe'] > best_sharpe:
                best_sharpe = r['sharpe']
                best_result = r

    print("=" * 70)

    if best_result:
        print(f"\n最佳权重方法：{best_result['name']}")
        print(f"  夏普比率：{best_result['sharpe']:.3f}")
        print(f"  年化收益：{best_result['annual_return']:+.2f}%")
        print(f"  胜率：{best_result['win_rate']:.1f}%")

    return results


if __name__ == "__main__":
    import pandas as pd

    # 运行增强版回测
    # 参数：股票池 50 只，回测 2 年，测试 4 种权重方法
    run_enhanced_backtest(
        stock_pool_size=50,
        backtest_years=2,
        weight_methods=['equal', 'performance', 'volatility', 'dynamic']
    )
