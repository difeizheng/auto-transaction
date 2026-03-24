"""
最终策略优化 - 冲击 15% 年化 + 夏普 1.0 + 胜率 55%

优化方向:
1. 信号系统增强 - 提高胜率
2. 出场策略优化 - 提高盈亏比
3. 市场状态过滤增强 - 提高夏普
4. 股票池精简优化 - 聚焦高质量
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 优化股票池 (基于历史表现精选 5 只)
ENHANCED_STOCKS = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
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


def run_optimization_tests():
    print("=" * 90)
    print("最终策略优化 - 冲击 15% 年化 + 夏普 1.0 + 胜率 55%")
    print("=" * 90)

    data_dict = load_data(ENHANCED_STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票，{START_DATE} - {END_DATE}")
    print()

    # === 测试配置 ===
    # 优化方向:
    # 1. 更高信号阈值 (5.5 -> 6.0/6.5) - 提高胜率
    # 2. 更优止损止盈 (4%/35% -> 3.5%/38%) - 提高盈亏比
    # 3. 更激进移动止损 (15% -> 12% 触发) - 锁定利润
    # 4. 增强市场过滤 (熊市 3% -> 2%) - 提高夏普
    # 5. 增加完美趋势要求 - 只交易高质量信号

    test_configs = [
        # === 基准：当前最优 ===
        {
            'name': '基准 (阈值 5.5)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },

        # === 方向 1: 更高阈值 ===
        {
            'name': '阈值 6.0 (高胜率)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },
        {
            'name': '阈值 6.5 (超高胜率)',
            'threshold': 6.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },

        # === 方向 2: 优化止损止盈 ===
        {
            'name': '止损 3.5% + 止盈 38%',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.38,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },
        {
            'name': '止损 3.5% + 止盈 40%',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.40,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },

        # === 方向 3: 移动止损优化 ===
        {
            'name': '移动 12% 触发 (早锁定)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.12,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },
        {
            'name': '移动 10% 触发 (更早锁定)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.10,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },

        # === 方向 4: 综合优化 ===
        {
            'name': '综合 A (阈值 6.0+ 止盈 38%)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.38,
            'trailing_trigger': 0.15,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },
        {
            'name': '综合 B (阈值 6.0+ 移动 12%)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.12,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },
        {
            'name': '综合 C (阈值 6.0+ 止盈 38%+ 移动 12%)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.38,
            'trailing_trigger': 0.12,
            'bear_position': 0.03,
            'base_position': 0.30,
            'max_position': 0.45,
        },

        # === 方向 5: 激进优化 ===
        {
            'name': '激进 (阈值 6.0+ 止损 3.5%+ 止盈 40%)',
            'threshold': 6.0,
            'stop_loss': 0.035,
            'take_profit': 0.40,
            'trailing_trigger': 0.12,
            'bear_position': 0.02,
            'base_position': 0.28,
            'max_position': 0.42,
        },

        # === 方向 6: 高夏普优化 ===
        {
            'name': '高夏普 (阈值 6.5+ 熊市 2%)',
            'threshold': 6.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'bear_position': 0.02,
            'base_position': 0.25,
            'max_position': 0.40,
        },
    ]

    results = []

    for i, cfg in enumerate(test_configs, 1):
        print(f"[{i}/{len(test_configs)}] 测试 {cfg['name']}")

        params = OptimalStrategyParams(
            base_stop_loss=cfg['stop_loss'],
            base_take_profit=cfg['take_profit'],
            signal_threshold=cfg['threshold'],
            base_position_ratio=cfg['base_position'],
            max_position_ratio=cfg['max_position'],
            min_position_ratio=0.02,
            use_market_filter=True,
            market_bear_max_position=cfg['bear_position'],
            trailing_stop_trigger=cfg['trailing_trigger'],
            trailing_stop_ratio=0.06,
            time_stop_days=10,
            time_stop_profit_threshold=0.05,
        )

        strategy = OptimalStrategy(name=cfg['name'], params=params)
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        results.append({
            'name': cfg['name'],
            'annual': result.annual_return,
            'sharpe': result.sharpe_ratio,
            'drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'total_trades': result.total_trades,
            'sharpe_score': result.sharpe_ratio * 0.4 + result.annual_return * 0.4 + (result.win_rate - 0.45) * 0.2,
        })

        print(f"  年化={result.annual_return*100:.2f}%, 夏普={result.sharpe_ratio:.2f}, "
              f"回撤={result.max_drawdown*100:.2f}%, 胜率={result.win_rate*100:.1f}%, "
              f"盈亏比={result.profit_factor:.2f}, 交易={result.total_trades}笔")

    print()
    print("=" * 90)
    print("优化结果汇总")
    print("=" * 90)

    # 按年化排序
    results_by_annual = sorted(results, key=lambda x: x['annual'], reverse=True)
    print("\n【按年化收益排名 Top 5】")
    for i, r in enumerate(results_by_annual[:5], 1):
        print(f"  {i}. {r['name']}: 年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"胜率={r['win_rate']*100:.1f}%, 回撤={r['drawdown']*100:.1f}%")

    # 按夏普排序
    results_by_sharpe = sorted(results, key=lambda x: x['sharpe'], reverse=True)
    print("\n【按夏普比率排名 Top 5】")
    for i, r in enumerate(results_by_sharpe[:5], 1):
        print(f"  {i}. {r['name']}: 夏普={r['sharpe']:.2f}, 年化={r['annual']*100:.2f}%, "
              f"胜率={r['win_rate']*100:.1f}%, 回撤={r['drawdown']*100:.1f}%")

    # 按胜率排序
    results_by_winrate = sorted(results, key=lambda x: x['win_rate'], reverse=True)
    print("\n【按胜率排名 Top 5】")
    for i, r in enumerate(results_by_winrate[:5], 1):
        print(f"  {i}. {r['name']}: 胜率={r['win_rate']*100:.1f}%, 年化={r['annual']*100:.2f}%, "
              f"夏普={r['sharpe']:.2f}%, 回撤={r['drawdown']*100:.1f}%")

    # 综合评分最高
    results_by_score = sorted(results, key=lambda x: x['sharpe_score'], reverse=True)
    print("\n【综合评分最高 Top 3】")
    for i, r in enumerate(results_by_score[:3], 1):
        print(f"  {i}. {r['name']}: 评分={r['sharpe_score']:.4f}")
        print(f"      年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"胜率={r['win_rate']*100:.1f}%, 回撤={r['drawdown']*100:.1f}%")

    # 目标对比
    print("\n" + "=" * 90)
    print("目标达成情况 (年化≥15%, 夏普≥1.0, 胜率≥55%, 回撤≤15%)")
    print("=" * 90)

    best_annual = max(results, key=lambda x: x['annual'])
    best_sharpe = max(results, key=lambda x: x['sharpe'])
    best_winrate = max(results, key=lambda x: x['win_rate'])

    check_mark = '[OK]'
    cross_mark = '[NG]'

    annual_gap = (0.15 - best_annual['annual']) * 100 if best_annual['annual'] < 0.15 else 0
    sharpe_gap = 1.0 - best_sharpe['sharpe'] if best_sharpe['sharpe'] < 1.0 else 0
    winrate_gap = (0.55 - best_winrate['win_rate']) * 100 if best_winrate['win_rate'] < 0.55 else 0

    print(f"\n最高年化：{best_annual['name']} = {best_annual['annual']*100:.2f}% "
          f"{check_mark if best_annual['annual'] >= 0.15 else cross_mark + ' (差' + str(round(annual_gap, 2)) + '%)'}")
    print(f"最高夏普：{best_sharpe['name']} = {best_sharpe['sharpe']:.2f} "
          f"{check_mark if best_sharpe['sharpe'] >= 1.0 else cross_mark + ' (差' + str(round(sharpe_gap, 2)) + ')'}")
    print(f"最高胜率：{best_winrate['name']} = {best_winrate['win_rate']*100:.1f}% "
          f"{check_mark if best_winrate['win_rate'] >= 0.55 else cross_mark + ' (差' + str(round(winrate_gap, 1)) + '%)'}")

    # 找出最接近目标的配置
    print("\n【最接近目标的配置】")
    # 计算与目标的距离
    for r in results:
        gap = (0.15 - r['annual']) * 10 + (1.0 - r['sharpe']) * 5 + (0.55 - r['win_rate']) * 5
        r['gap'] = gap

    closest = min(results, key=lambda x: x['gap'])
    print(f"  {closest['name']}")
    annual_diff = (0.15 - closest['annual']) * 100
    sharpe_diff = 1.0 - closest['sharpe']
    winrate_diff = (0.55 - closest['win_rate']) * 100
    print(f"  年化={closest['annual']*100:.2f}% (差{round(annual_diff, 2)}%), "
          f"夏普={closest['sharpe']:.2f} (差{round(sharpe_diff, 2)}), "
          f"胜率={closest['win_rate']*100:.1f}% (差{round(winrate_diff, 1)}%), "
          f"回撤={closest['drawdown']*100:.1f}%")

    return results


if __name__ == '__main__':
    run_optimization_tests()
