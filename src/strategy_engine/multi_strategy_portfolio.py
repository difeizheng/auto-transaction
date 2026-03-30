"""
多策略并行框架
同时运行多个策略并对比表现
"""
from typing import List, Dict, Optional
from datetime import datetime
import json

from config.logging_config import trader_logger
from src.strategy.technical import TechnicalStrategy
from src.strategy.trend_follow import TrendFollowStrategy
from src.strategy.mean_reversion import MeanReversionStrategy
from src.strategy.optimal_strategy import create_optimal_strategy
from src.data_collector.data_manager import data_manager


class MultiStrategyPortfolio:
    """多策略投资组合"""

    def __init__(self, initial_capital: float = 20000):
        """
        初始化多策略组合

        Args:
            initial_capital: 初始资金（每个策略分配）
        """
        self.initial_capital = initial_capital

        # 策略实例
        self.strategies = {
            'optimal': create_optimal_strategy(),
            'trend': TrendFollowStrategy(),
            'mean_reversion': MeanReversionStrategy(),
            'technical': TechnicalStrategy()
        }

        # 策略状态
        self.strategy_state = {}

        # 初始化每个策略的状态
        for name, strategy in self.strategies.items():
            self.strategy_state[name] = {
                'cash': initial_capital,
                'positions': {},  # {ts_code: {'volume': x, 'avg_cost': y}}
                'trades': [],
                'nav': 1.0,
                'nav_history': []
            }

        trader_logger.info(f"多策略组合初始化完成，策略: {list(self.strategies.keys())}")

    def generate_signals_all(self, stock_pool: List[str], current_date: str) -> Dict[str, List]:
        """
        为所有策略生成信号

        Args:
            stock_pool: 股票池
            current_date: 当前日期

        Returns:
            {策略名: 信号列表}
        """
        # 获取数据
        data_dict = {}
        for ts_code in stock_pool:
            df = data_manager.get_daily_quotes(ts_code, '20210101', current_date)
            if df is not None and not df.empty and len(df) >= 30:
                data_dict[ts_code] = df

        results = {}
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_bar(data_dict, current_date)
                results[name] = signals
            except Exception as e:
                trader_logger.error(f"策略 {name} 生成信号失败: {e}")
                results[name] = []

        return results

    def update_nav(self, strategy_name: str, current_prices: Dict[str, float]):
        """
        更新策略净值

        Args:
            strategy_name: 策略名称
            strategy_name: 策略名称
            current_prices: {ts_code: price}
        """
        state = self.strategy_state[strategy_name]

        # 计算持仓市值
        position_value = 0
        for ts_code, pos in state['positions'].items():
            price = current_prices.get(ts_code, pos.get('avg_cost', 0))
            position_value += pos['volume'] * price

        # 计算净值
        total_value = state['cash'] + position_value
        nav = total_value / self.initial_capital

        state['nav'] = nav
        state['nav_history'].append({
            'date': datetime.now().strftime('%Y%m%d'),
            'nav': nav,
            'cash': state['cash'],
            'position_value': position_value
        })

    def get_strategy_performance(self, strategy_name: str) -> Dict:
        """
        获取策略表现

        Args:
            strategy_name: 策略名称

        Returns:
            绩效字典
        """
        state = self.strategy_state[strategy_name]
        nav_history = state['nav_history']

        if not nav_history:
            return {}

        navs = [h['nav'] for h in nav_history]

        # 基本指标
        first_nav = navs[0]
        last_nav = navs[-1]
        total_return = (last_nav - first_nav) / first_nav * 100

        # 年化收益（假设250交易日）
        days = len(navs)
        if days > 0:
            annualized = (last_nav / first_nav - 1) * 250 / days * 100
        else:
            annualized = 0

        # 最大回撤
        peak = navs[0]
        max_dd = 0
        for nav in navs:
            if nav > peak:
                peak = nav
            dd = (peak - nav) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # 交易次数
        total_trades = len(state['trades'])

        return {
            'strategy_name': strategy_name,
            'total_return': round(total_return, 2),
            'annualized_return': round(annualized, 2),
            'max_drawdown': round(max_dd, 2),
            'total_trades': total_trades,
            'current_nav': round(last_nav, 4),
            'days': days
        }

    def get_all_performance(self) -> List[Dict]:
        """
        获取所有策略的表现

        Returns:
            策略表现列表
        """
        results = []
        for name in self.strategies.keys():
            perf = self.get_strategy_performance(name)
            if perf:
                results.append(perf)

        # 按收益排序
        results.sort(key=lambda x: x['total_return'], reverse=True)

        return results

    def rank_strategies(self) -> List[Dict]:
        """
        策略排名

        Returns:
            排序后的策略列表
        """
        return self.get_all_performance()

    def get_winner(self) -> Optional[Dict]:
        """
        获取当前最优策略

        Returns:
            最优策略信息
        """
        ranking = self.rank_strategies()
        return ranking[0] if ranking else None


def run_multi_strategy_backtest(stock_pool: List[str], start_date: str, end_date: str) -> Dict:
    """
    运行多策略回测

    Args:
        stock_pool: 股票池
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        回测结果
    """
    portfolio = MultiStrategyPortfolio(initial_capital=20000)

    # 获取所有交易日
    from src.utils.database import db
    try:
        df = db.query(f"""
            SELECT DISTINCT trade_date FROM daily_quotes
            WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
            ORDER BY trade_date
        """)
        trade_dates = df['trade_date'].tolist() if not df.empty else []
    except Exception as e:
        trader_logger.error(f"获取交易日失败: {e}")
        return {}

    trader_logger.info(f"开始多策略回测, 日期: {start_date} ~ {end_date}, 交易日: {len(trade_dates)}")

    # 每月运行一次（简化）
    for i, date in enumerate(trade_dates):
        if i % 20 == 0:  # 每20个交易日
            # 生成信号
            signals_dict = portfolio.generate_signals_all(stock_pool, date)

            # 更新净值（简化：假设价格不变）
            current_prices = {}
            for ts_code in stock_pool:
                df = data_manager.get_daily_quotes(ts_code, date, date)
                if not df.empty:
                    current_prices[ts_code] = float(df.iloc[-1]['close'])

            for name in portfolio.strategies.keys():
                portfolio.update_nav(name, current_prices)

    # 获取结果
    results = portfolio.get_all_performance()

    trader_logger.info("多策略回测完成:")
    for perf in results:
        trader_logger.info(f"  {perf['strategy_name']}: "
                          f"收益 {perf['total_return']:.2f}%, "
                          f"年化 {perf['annualized_return']:.2f}%, "
                          f"回撤 {perf['max_drawdown']:.2f}%, "
                          f"交易 {perf['total_trades']} 次")

    return {
        'start_date': start_date,
        'end_date': end_date,
        'results': results,
        'winner': portfolio.get_winner()
    }


if __name__ == "__main__":
    # 测试
    print("=== 测试多策略框架 ===")

    # 使用默认股票池
    import config.settings as settings
    stock_pool = settings.DEFAULT_STOCK_POOL[:10]  # 用10只测试

    # 运行回测
    results = run_multi_strategy_backtest(
        stock_pool=stock_pool,
        start_date='20240101',
        end_date='20240331'
    )

    print("\n回测结果:")
    for r in results.get('results', []):
        print(f"  {r['strategy_name']}: 收益 {r['total_return']:.2f}%")

    if results.get('winner'):
        print(f"\n最优策略: {results['winner']['strategy_name']}")

    print("\n测试完成")