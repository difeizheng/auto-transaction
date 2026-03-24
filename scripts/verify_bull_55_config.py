"""
牛市 55% 配置回测验证脚本

配置参数:
- 信号阈值：5.0
- 止损：4%
- 止盈：35%
- 基础仓位：35%
- 牛市最大：55%
- 熊市仓位：2%
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 配置参数
STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
START_DATE = '20240324'
END_DATE = '20260323'
INITIAL_CAPITAL = 1000000


def load_data(stocks, start_date, end_date):
    data_dict = {}
    for ts_code in stocks:
        df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
        if not df.empty:
            data_dict[ts_code] = df
    return data_dict


def run_backtest():
    print("=" * 90)
    print("牛市 55% 配置回测验证")
    print("=" * 90)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print(f"初始资金：{INITIAL_CAPITAL:,.0f}元")
    print()

    # 加载数据
    print("加载数据...")
    data_dict = load_data(STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票")
    print()

    # 配置策略参数
    params = OptimalStrategyParams(
        # 信号阈值
        signal_threshold=5.0,

        # 止损止盈
        base_stop_loss=0.04,      # 4%
        base_take_profit=0.35,    # 35%

        # 仓位管理
        base_position_ratio=0.35,  # 35%
        max_position_ratio=0.55,   # 55%
        min_position_ratio=0.01,   # 1%

        # 市场过滤
        use_market_filter=True,
        market_bear_max_position=0.02,  # 2%

        # 移动止损
        trailing_stop_trigger=0.15,  # 15%
        trailing_stop_ratio=0.06,    # 6%

        # 时间止损
        time_stop_days=10,
        time_stop_profit_threshold=0.03,
    )

    print("策略参数配置:")
    print(f"  信号阈值：{params.signal_threshold}")
    print(f"  止损/止盈：{params.base_stop_loss*100}% / {params.base_take_profit*100}%")
    print(f"  仓位管理：基础{params.base_position_ratio*100}% / 牛市{params.max_position_ratio*100}% / 熊市{params.market_bear_max_position*100}%")
    print(f"  移动止损：触发{params.trailing_stop_trigger*100}% / 回撤{params.trailing_stop_ratio*100}%")
    print(f"  时间止损：{params.time_stop_days}日")
    print()

    # 创建策略和回测引擎
    strategy = OptimalStrategy(name="牛市 55% 配置", params=params)
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_strategy(strategy)

    # 运行回测
    print("运行回测...")
    result = engine.run(data_dict)

    # 输出结果
    print()
    print("=" * 90)
    print("回测结果")
    print("=" * 90)
    print()
    print("=" * 50)
    print("资金曲线")
    print("=" * 50)
    print(f"初始资金：{INITIAL_CAPITAL:,.2f}元")
    print(f"最终权益：{result.final_capital:,.2f}元")
    print(f"总收益：{result.total_return*100:.2f}%")
    print()
    print("=" * 50)
    print("收益指标")
    print("=" * 50)
    print(f"年化收益率：{result.annual_return*100:.2f}%")
    print(f"夏普比率：{result.sharpe_ratio:.2f}")
    print()
    print("=" * 50)
    print("风险指标")
    print("=" * 50)
    print(f"最大回撤：{result.max_drawdown*100:.2f}%")
    print(f"波动率：{result.volatility*100:.2f}%" if hasattr(result, 'volatility') else "波动率：N/A")
    print()
    print("=" * 50)
    print("交易统计")
    print("=" * 50)
    print(f"总交易次数：{result.total_trades}")
    print(f"盈利交易：{result.winning_trades}")
    print(f"亏损交易：{result.losing_trades}")
    print(f"胜率：{result.win_rate*100:.1f}%")
    print(f"盈亏比：{result.profit_factor:.2f}")
    print()
    print("=" * 50)
    print("目标达成情况")
    print("=" * 50)

    targets = {
        '年化收益>=15%': result.annual_return >= 0.15,
        '夏普>=1.0': result.sharpe_ratio >= 1.0,
        '胜率>=55%': result.win_rate >= 0.55,
        '盈亏比>=2.0': result.profit_factor >= 2.0,
        '回撤<=15%': result.max_drawdown <= 0.15,
    }

    check_mark = "[OK]"
    cross_mark = "[NG]"

    for target, achieved in targets.items():
        status = check_mark if achieved else cross_mark
        print(f"  {target}: {status}")

    return result


if __name__ == '__main__':
    run_backtest()
