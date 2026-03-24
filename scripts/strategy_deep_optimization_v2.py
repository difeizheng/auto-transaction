"""
策略深度优化 v2.0 - 突破 15% 年化瓶颈

核心洞察:
- 当前策略胜率 50%、盈亏比 2.48，年化 13.58%
- 参数优化已达瓶颈，需要策略层面改进

优化方向:
1. 增强信号质量 - 增加动量因子、资金流因子
2. 优化出场策略 - 分级止盈 + 趋势跟踪止损
3. 市场时机选择 - 更精确的牛熊判断
4. 股票池动态选择 - 聚焦强势股
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.optimal_strategy import OptimalStrategyParams, OptimalStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager

# 测试股票池 (5 只最优组合)
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


def run_deep_optimization():
    print("=" * 90)
    print("策略深度优化 v2.0 - 突破 15% 年化瓶颈")
    print("=" * 90)

    data_dict = load_data(ENHANCED_STOCKS, START_DATE, END_DATE)
    print(f"数据加载完成：{len(data_dict)} 只股票")
    print()

    # === 深度优化配置 ===
    # 优化思路:
    # 1. 更低止损 (3.5%) + 更高止盈 (45%) = 提高盈亏比
    # 2. 更早移动止损 (10% 触发) = 锁定利润
    # 3. 更低基础仓位 (25%) + 更高牛市仓位 (50%) = 市场时机选择
    # 4. 更严格熊市仓位 (1%) = 避免亏损

    test_configs = [
        # === 基准 ===
        {
            'name': '基准 (阈值 5.5)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.45,
            'bear_position': 0.03,
            'time_stop': 10,
        },

        # === 方向 1: 极致盈亏比 ===
        {
            'name': '极致盈亏比 (3.5%/45%)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.45,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.45,
            'bear_position': 0.03,
            'time_stop': 10,
        },
        {
            'name': '极致盈亏比 + 早锁定 (10%)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.45,
            'trailing_trigger': 0.10,
            'trailing_ratio': 0.05,
            'base_position': 0.30,
            'max_position': 0.45,
            'bear_position': 0.03,
            'time_stop': 10,
        },

        # === 方向 2: 市场时机增强 ===
        {
            'name': '市场时机 (熊市 1%)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.50,
            'bear_position': 0.01,
            'time_stop': 10,
        },
        {
            'name': '市场时机 (牛市 55%)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.35,
            'max_position': 0.55,
            'bear_position': 0.02,
            'time_stop': 10,
        },

        # === 方向 3: 综合优化 ===
        {
            'name': '综合 A (3.5%/40%+ 熊市 1%)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.40,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.50,
            'bear_position': 0.01,
            'time_stop': 10,
        },
        {
            'name': '综合 B (3.5%/45%+ 早锁定)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.45,
            'trailing_trigger': 0.10,
            'trailing_ratio': 0.05,
            'base_position': 0.28,
            'max_position': 0.48,
            'bear_position': 0.02,
            'time_stop': 10,
        },
        {
            'name': '综合 C (4%/40%+ 市场时机)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.40,
            'trailing_trigger': 0.12,
            'trailing_ratio': 0.05,
            'base_position': 0.32,
            'max_position': 0.52,
            'bear_position': 0.01,
            'time_stop': 10,
        },

        # === 方向 4: 时间止损优化 ===
        {
            'name': '时间止损 7 日 (更紧)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.45,
            'bear_position': 0.03,
            'time_stop': 7,
        },
        {
            'name': '时间止损 5 日 (超紧)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.35,
            'trailing_trigger': 0.15,
            'trailing_ratio': 0.06,
            'base_position': 0.30,
            'max_position': 0.45,
            'bear_position': 0.03,
            'time_stop': 5,
        },

        # === 方向 5: 激进组合 ===
        {
            'name': '激进 A (3.5%/45%+ 熊市 1%+7 日)',
            'threshold': 5.5,
            'stop_loss': 0.035,
            'take_profit': 0.45,
            'trailing_trigger': 0.12,
            'trailing_ratio': 0.05,
            'base_position': 0.28,
            'max_position': 0.50,
            'bear_position': 0.01,
            'time_stop': 7,
        },
        {
            'name': '激进 B (4%/42%+ 市场时机)',
            'threshold': 5.5,
            'stop_loss': 0.04,
            'take_profit': 0.42,
            'trailing_trigger': 0.12,
            'trailing_ratio': 0.05,
            'base_position': 0.30,
            'max_position': 0.52,
            'bear_position': 0.01,
            'time_stop': 8,
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
            min_position_ratio=0.01,
            use_market_filter=True,
            market_bear_max_position=cfg['bear_position'],
            trailing_stop_trigger=cfg['trailing_trigger'],
            trailing_stop_ratio=cfg['trailing_ratio'],
            time_stop_days=cfg['time_stop'],
            time_stop_profit_threshold=0.03,
        )

        strategy = OptimalStrategy(name=cfg['name'], params=params)
        engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
        engine.set_strategy(strategy)
        result = engine.run(data_dict)

        # 综合评分：年化 40% + 夏普 30% + 胜率 20% + 回撤 10%
        score = (result.annual_return * 3 +
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

        status = "[NEW BEST]" if result.annual_return > 0.1358 else ""
        print(f"  年化={result.annual_return*100:.2f}%, 夏普={result.sharpe_ratio:.2f}, "
              f"回撤={result.max_drawdown*100:.2f}%, 胜率={result.win_rate*100:.1f}%, "
              f"交易={result.total_trades}笔 {status}")

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

    # 按综合评分排序
    results_by_score = sorted(results, key=lambda x: x['score'], reverse=True)
    print("\n【综合评分最高 Top 5】")
    for i, r in enumerate(results_by_score[:5], 1):
        print(f"  {i}. {r['name']}: 评分={r['score']:.4f}")
        print(f"      年化={r['annual']*100:.2f}%, 夏普={r['sharpe']:.2f}, "
              f"胜率={r['win_rate']*100:.1f}%, 回撤={r['drawdown']*100:.1f}%")

    # 找出最佳配置
    best = max(results, key=lambda x: x['annual'])
    best_score = max(results, key=lambda x: x['score'])

    print("\n" + "=" * 90)
    print("最佳配置推荐")
    print("=" * 90)
    print(f"最高年化：{best['name']} = {best['annual']*100:.2f}%")
    print(f"最高评分：{best_score['name']} = {best_score['score']:.4f}")

    return results


if __name__ == '__main__':
    run_deep_optimization()
