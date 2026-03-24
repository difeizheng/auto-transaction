"""
策略深度优化 v3.0 - 冲击夏普 1.0 + 胜率 55%

当前瓶颈分析:
- 年化 16.15% ✅ 已达标
- 夏普 0.63 ❌ 差 0.37 (需提高收益稳定性)
- 胜率 51.4% ❌ 差 3.6% (需提高信号质量)
- 回撤 15.26% ⚠️ 略超 0.26%

优化方向:
1. 信号质量增强 - 增加动量因子、主力资金因子
2. 出场策略优化 - 分级止盈 + 趋势跟踪
3. 市场时机改进 - 更精确的牛熊判断
4. 仓位优化 - 测试 52-53% 牛市仓位平衡收益回撤
5. 止损优化 - ATR 动态止损
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


def run_v3_optimization():
    print("=" * 90)
    print("策略深度优化 v3.0 - 冲击夏普 1.0 + 胜率 55%")
    print("=" * 90)
    print(f"回测区间：{START_DATE} - {END_DATE}")
    print(f"股票池：{len(STOCKS)} 只")
    print()

    # 加载数据
    print("加载数据...")
    data_dict = load_data(STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成")
    print()

    # === v3.0 测试配置 ===
    # 优化思路:
    # 1. 测试更低牛市仓位 (52-53%) 平衡收益与回撤
    # 2. 测试更高信号阈值 (6.0) 提高胜率
    # 3. 测试更紧止损 (3.5%) 降低回撤
    # 4. 测试更早移动止损 (12%) 锁定利润
    # 5. 测试时间止损优化 (7 日) 减少资金占用

    test_configs = [
        # === 基准 ===
        {
            'name': '基准 (牛市 55%/阈值 5.5)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 10,
        },

        # === 方向 1: 仓位微调 (52-53%) ===
        {
            'name': '牛市 53% (平衡收益回撤)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 10,
        },
        {
            'name': '牛市 52% (更保守)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.32,
            'bull_pos': 0.52,
            'bear_pos': 0.02,
            'time_stop': 10,
        },

        # === 方向 2: 提高信号阈值 (6.0) ===
        {
            'name': '阈值 6.0 (高胜率)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 10,
        },
        {
            'name': '阈值 6.0 + 牛市 53%',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 10,
        },

        # === 方向 3: 更紧止损 (3.5%) ===
        {
            'name': '止损 3.5% (降低回撤)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 10,
        },
        {
            'name': '止损 3.5% + 阈值 6.0',
            'threshold': 6.0,
            'stop_loss': 0.035,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 10,
        },

        # === 方向 4: 更早移动止损 (12%) ===
        {
            'name': '移动 12% (早锁定利润)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.12,
            'trailing_ratio': 0.05,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 10,
        },
        {
            'name': '移动 12% + 牛市 53%',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.12,
            'trailing_ratio': 0.05,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 10,
        },

        # === 方向 5: 时间止损优化 (7 日) ===
        {
            'name': '时间止损 7 日 (减少占用)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.35,
            'bull_pos': 0.55,
            'bear_pos': 0.02,
            'time_stop': 7,
        },

        # === 方向 6: 综合优化 ===
        {
            'name': '综合 A (53%+3.5%+12%)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.35,
            'trailing': 0.12,
            'trailing_ratio': 0.05,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 7,
        },
        {
            'name': '综合 B (6.0+53%+3.5%)',
            'threshold': 6.0,
            'stop_loss': 0.035,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 7,
        },
        {
            'name': '综合 C (6.0+53%+3.5%+12%)',
            'threshold': 6.0,
            'stop_loss': 0.035,
            'take_profit': 0.35,
            'trailing': 0.12,
            'trailing_ratio': 0.05,
            'base_pos': 0.33,
            'bull_pos': 0.53,
            'bear_pos': 0.02,
            'time_stop': 7,
        },

        # === 方向 7: 高夏普配置 ===
        {
            'name': '高夏普 (阈值 6.0+ 熊市 1%)',
            'threshold': 6.0,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing': 0.15,
            'trailing_ratio': 0.06,
            'base_pos': 0.30,
            'bull_pos': 0.50,
            'bear_pos': 0.01,
            'time_stop': 8,
        },
    ]

    results = []

    for i, cfg in enumerate(test_configs, 1):
        print(f"[{i}/{len(test_configs)}] 测试 {cfg['name']}")

        params = OptimalStrategyParams(
            signal_threshold=cfg['threshold'],
            base_stop_loss=cfg['stop_loss'],
            base_take_profit=cfg['take_profit'],
            base_position_ratio=cfg['base_pos'],
            max_position_ratio=cfg['bull_pos'],
            min_position_ratio=0.01,
            use_market_filter=True,
            market_bear_max_position=cfg['bear_pos'],
            trailing_stop_trigger=cfg['trailing'],
            trailing_stop_ratio=cfg['trailing_ratio'],
            time_stop_days=cfg['time_stop'],
            time_stop_profit_threshold=0.03,
        )

        strategy = OptimalStrategy(name=cfg['name'], params=params)
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        # 综合评分：年化 30% + 夏普 30% + 胜率 20% + 回撤 20%
        score = (result.annual_return * 2 +
                 result.sharpe_ratio * 0.5 +
                 result.win_rate * 0.3 +
                 (1 - result.max_drawdown) * 0.2)

        results.append({
            'name': cfg['name'],
            'annual': result.annual_return,
            'sharpe': result.sharpe_ratio,
            'drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'total_trades': result.total_trades,
            'score': score,
        })

        # 标记改进
        improvement = ""
        if result.annual_return > 0.1615:
            improvement = "[NEW BEST 年化]"
        if result.sharpe_ratio > 0.63:
            improvement = "[NEW BEST 夏普]"
        if result.win_rate > 0.514:
            improvement = "[NEW BEST 胜率]"
        if result.max_drawdown < 0.1526 and result.max_drawdown <= 0.15:
            improvement = "[回撤达标]"

        print(f"  年化={result.annual_return*100:.2f}%, 夏普={result.sharpe_ratio:.2f}, "
              f"回撤={result.max_drawdown*100:.2f}%, 胜率={result.win_rate*100:.1f}% {improvement}")

    print()
    print("=" * 90)
    print("v3.0 优化结果汇总")
    print("=" * 90)

    # 按年化排序
    results_by_annual = sorted(results, key=lambda x: x['annual'], reverse=True)
    print("\n【按年化收益排名 Top 5】")
    for i, r in enumerate(results_by_annual[:5], 1):
        print(f"  {i}. {r['name']}: 年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"回撤={r['drawdown']*100:.1f}%, 胜率={r['win_rate']*100:.1f}%")

    # 按夏普排序
    results_by_sharpe = sorted(results, key=lambda x: x['sharpe'], reverse=True)
    print("\n【按夏普比率排名 Top 5】")
    for i, r in enumerate(results_by_sharpe[:5], 1):
        print(f"  {i}. {r['name']}: 夏普={r['sharpe']:.2f}, 年化={r['annual']*100:.2f}%, "
              f"回撤={r['drawdown']*100:.1f}%, 胜率={r['win_rate']*100:.1f}%")

    # 按胜率排序
    results_by_winrate = sorted(results, key=lambda x: x['win_rate'], reverse=True)
    print("\n【按胜率排名 Top 5】")
    for i, r in enumerate(results_by_winrate[:5], 1):
        print(f"  {i}. {r['name']}: 胜率={r['win_rate']*100:.1f}%, 年化={r['annual']*100:.2f}%, "
              f"夏普={r['sharpe']:.2f}%, 回撤={r['drawdown']*100:.1f}%")

    # 按综合评分排序
    results_by_score = sorted(results, key=lambda x: x['score'], reverse=True)
    print("\n【综合评分 Top 5】")
    for i, r in enumerate(results_by_score[:5], 1):
        print(f"  {i}. {r['name']}: 评分={r['score']:.4f}")

    # 找出最佳配置
    best_annual = max(results, key=lambda x: x['annual'])
    best_sharpe = max(results, key=lambda x: x['sharpe'])
    best_winrate = max(results, key=lambda x: x['win_rate'])
    best_score = max(results, key=lambda x: x['score'])

    print("\n" + "=" * 90)
    print("最优配置推荐")
    print("=" * 90)
    print(f"最高年化：{best_annual['name']} = {best_annual['annual']*100:.2f}%")
    print(f"最高夏普：{best_sharpe['name']} = {best_sharpe['sharpe']:.2f}")
    print(f"最高胜率：{best_winrate['name']} = {best_winrate['win_rate']*100:.1f}%")
    print(f"最高评分：{best_score['name']} = {best_score['score']:.4f}")

    # 目标达成检查
    print("\n" + "=" * 90)
    print("目标达成检查 (年化≥15%, 夏普≥1.0, 胜率≥55%, 回撤≤15%)")
    print("=" * 90)

    check_mark = "[OK]"
    cross_mark = "[NG]"

    for r in [best_annual, best_sharpe, best_winrate, best_score]:
        annual_ok = r['annual'] >= 0.15
        sharpe_ok = r['sharpe'] >= 1.0
        winrate_ok = r['win_rate'] >= 0.55
        drawdown_ok = r['drawdown'] <= 0.15

        print(f"\n{r['name']}:")
        print(f"  年化：{r['annual']*100:.2f}% {check_mark if annual_ok else cross_mark}")
        print(f"  夏普：{r['sharpe']:.2f} {check_mark if sharpe_ok else cross_mark}")
        print(f"  胜率：{r['win_rate']*100:.1f}% {check_mark if winrate_ok else cross_mark}")
        print(f"  回撤：{r['drawdown']*100:.1f}% {check_mark if drawdown_ok else cross_mark}")

    return results


if __name__ == '__main__':
    run_v3_optimization()
