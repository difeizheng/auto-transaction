"""
策略优化回测脚本 v4.0
验证夏普比率优化和胜率优化效果
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_collector.data_manager import data_manager
from src.data_collector.tushare_client import TushareClient
from src.strategy.optimal_strategy import OptimalStrategy, OptimalStrategyParams
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio
from src.backtest.engine import BacktestEngine
from src.backtest.performance import PerformanceAnalyzer
from src.utils.database import init_db


def run_optimization_backtest():
    """运行优化策略回测"""
    print("=" * 60)
    print("策略优化回测 v4.0 - 夏普比率 + 胜率优化验证")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n[1/6] 初始化数据库...")
    init_db()

    # 2. 准备数据
    print("\n[2/6] 准备回测数据...")

    # 更新股票列表
    ts_client = TushareClient()
    try:
        stocks_df = ts_client.get_stock_list(list_status='L')
    except Exception as e:
        print(f"警告：无法获取股票列表 ({e})，使用预设股票池")
        stocks_df = None

    # 预设股票池 (活跃股票)
    stock_pool = [
        '000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ',
        '000002.SZ', '000069.SZ', '000089.SZ', '000027.SZ', '000012.SZ',
        '000021.SZ', '000025.SZ', '000028.SZ', '000032.SZ', '000035.SZ',
        '000042.SZ', '000046.SZ', '000050.SZ', '000055.SZ', '000059.SZ',
    ]

    if stocks_df is not None and not stocks_df.empty:
        stock_pool = stocks_df['ts_code'].head(30).tolist()

    print(f"股票池：{len(stock_pool)} 只股票")

    # 回测日期 (最近 1 年)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    print(f"回测区间：{start_date} 至 {end_date}")

    # 更新数据
    print("更新行情数据...")
    for i, ts_code in enumerate(stock_pool[:15]):
        try:
            data_manager.update_single_stock(ts_code, days=365)
            if (i + 1) % 5 == 0:
                print(f"  进度：{i + 1}/{len(stock_pool[:15])}")
        except Exception as e:
            print(f"  跳过 {ts_code}: {e}")

    # 3. 加载数据
    print("\n[3/6] 加载回测数据...")

    market_data = {}
    for ts_code in stock_pool[:10]:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            market_data[ts_code] = df
            print(f"  {ts_code}: {len(df)} 条数据")

    if not market_data:
        print("错误：无法获取行情数据")
        return None

    # 4. 设置策略配置
    print("\n[4/6] 设置策略配置...")

    # 策略对比配置
    strategies_config = [
        {
            'name': '基础策略 (v1.0)',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=False,
                use_win_rate_optimization=False,
                signal_threshold=5.0,
            ),
            'description': '无优化，基础版本'
        },
        {
            'name': '夏普优化 (v3.0)',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=True,
                use_win_rate_optimization=False,
                signal_threshold=5.5,
                max_volatility_threshold=0.04,
                min_stability_threshold=0.6,
                profit_lock_trigger=0.08,
            ),
            'description': '波动率过滤 + 稳定性因子 + 分级止盈'
        },
        {
            'name': '胜率优化 (v4.0)',
            'params': OptimalStrategyParams(
                use_sharpe_optimization=True,
                use_win_rate_optimization=True,
                signal_threshold=6.0,
                min_momentum_score=0.03,
                min_money_flow_score=0,
                min_stock_strength_rank=0.3,
                min_signal_confidence=0.6,
            ),
            'description': '夏普优化 + 动量因子 + 资金流 + 强势股筛选'
        },
        {
            'name': '多策略组合 (v4.0)',
            'type': 'multi_strategy',
            'description': '最优 + 趋势跟踪 + 均值回归'
        }
    ]

    results = {}

    # 5. 运行回测
    print("\n[5/6] 运行回测...")
    print("=" * 60)

    for config in strategies_config:
        print(f"\n>>> 回测：{config['name']}")
        print(f"    描述：{config['description']}")
        print("-" * 40)

        try:
            # 创建策略
            if config.get('type') == 'multi_strategy':
                strategy = create_multi_strategy_portfolio(
                    enable_optimal=True,
                    enable_trend=True,
                    enable_mean_reversion=True,
                    weight_method='equal'
                )
                strategy_name = 'multi_strategy'
            else:
                strategy = OptimalStrategy(
                    name=config['name'],
                    params=config['params']
                )
                strategy_name = config['name']

            # 创建回测引擎
            engine = BacktestEngine(
                initial_capital=100000,  # 10 万初始资金
                commission_rate=0.0003,
                stamp_tax_rate=0.001,
                slippage_rate=0.001,
                max_position_ratio=0.8
            )

            # 设置策略
            engine.set_strategy(strategy)

            # 加载数据
            data_dict = engine.load_data(
                ts_codes=list(market_data.keys()),
                start_date=start_date,
                end_date=end_date
            )

            # 运行回测
            result = engine.run(data_dict)
            results[config['name']] = result

            # 绩效分析
            analyzer = PerformanceAnalyzer()
            report = analyzer.generate_report(result)
            print(report)

        except Exception as e:
            print(f"回测失败：{e}")
            results[config['name']] = None

    # 6. 对比总结
    print("\n[6/6] 策略对比总结")
    print("=" * 60)
    print(f"{'策略名称':<25} {'年化收益':>10} {'夏普比率':>10} {'胜率':>10} {'最大回撤':>10}")
    print("-" * 65)

    for name, result in results.items():
        if result is not None:
            try:
                analyzer = PerformanceAnalyzer()
                metrics = analyzer.calculate_metrics(result)
                annual_return = metrics.get('annual_return', 0) * 100
                sharpe = metrics.get('sharpe', 0)
                win_rate = metrics.get('win_rate', 0) * 100
                max_dd = metrics.get('max_drawdown', 0) * 100
                print(f"{name:<25} {annual_return:>9.2f}% {sharpe:>10.3f} {win_rate:>9.2f}% {max_dd:>9.2f}%")
            except Exception:
                print(f"{name:<25} {'计算失败':>10}")
        else:
            print(f"{name:<25} {'回测失败':>10}")

    print("=" * 60)
    print("回测完成!")

    return results


if __name__ == "__main__":
    run_optimization_backtest()
