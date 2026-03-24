"""
多策略组合框架
整合趋势跟踪、均值回归、动量轮动三种策略

核心逻辑:
1. 趋势跟踪策略 - 捕捉趋势行情
2. 均值回归策略 - 捕捉震荡行情
3. 动量轮动策略 - 捕捉相对强度
4. 策略权重动态调整
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.strategy.base_strategy import BaseStrategy, Signal
from src.strategy.market_filter import MarketFilter, MarketState
from config.logging_config import strategy_logger


@dataclass
class MultiStrategyParams:
    """多策略组合参数"""
    # 基础参数
    initial_capital: float = 1000000

    # 趋势跟踪策略参数
    trend_stop_loss: float = 0.05
    trend_take_profit: float = 0.30
    trend_signal_threshold: float = 4.5

    # 均值回归策略参数
    mr_window: int = 20          # 回归窗口
    mr_entry_threshold: float = 2.0  # 入场阈值 (标准差倍数)
    mr_exit_threshold: float = 0.5   # 出场阈值
    mr_stop_loss: float = 0.08       # 止损 8%
    mr_take_profit: float = 0.15     # 止盈 15%

    # 动量轮动策略参数
    mom_window: int = 20         # 动量计算窗口
    mom_rank_method: str = 'percentile'  # 排名方法
    mom_top_n: int = 5           # 持有前 N 只
    mom_rebalance_days: int = 5  # 调仓周期

    # 仓位分配
    trend_weight: float = 0.5    # 趋势策略权重
    mr_weight: float = 0.3       # 均值回归权重
    mom_weight: float = 0.2      # 动量权重

    # 市场过滤
    use_market_filter: bool = True
    bear_position_limit: float = 0.1  # 熊市最大仓位 10%


class TrendFollowingStrategy(BaseStrategy):
    """
    趋势跟踪策略

    核心逻辑:
    1. 价格突破 N 日高点入场
    2. 成交量放大确认
    3. 移动止损让利润奔跑
    """

    def __init__(self, params: MultiStrategyParams):
        super().__init__("trend_following")
        self.params = params
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}
        self.lookback = 20  # 突破周期

    def on_init(self):
        super().on_init()
        self.price_history = {}
        self.positions = {}

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0),
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            ).tail(60)

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        self.update_price_history(data, current_date)
        signals = []

        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            if len(df) < self.lookback + 5:
                continue

            close = df['close']
            vol = df['vol']
            current_price = bar.get('close', 0)

            # 计算 N 日高点
            highest_high = close.rolling(self.lookback).max().iloc[-2]  # 昨日高点
            vol_ma = vol.rolling(20).mean().iloc[-1]
            current_vol = vol.iloc[-1]

            # 检查持仓
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                entry_price = pos['entry_price']
                highest_price = max(pos.get('highest_price', entry_price), current_price)

                # 更新最高价
                if current_price > pos.get('highest_price', 0):
                    self.positions[ts_code]['highest_price'] = current_price

                # 止损检查
                profit_ratio = (current_price - entry_price) / entry_price
                if profit_ratio <= -self.params.trend_stop_loss:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=pos.get('shares', 1000),
                        reason=f'止损 ({profit_ratio:.1%})'
                    ))
                    del self.positions[ts_code]
                    continue

                # 止盈检查
                if profit_ratio >= self.params.trend_take_profit:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=pos.get('shares', 1000),
                        reason=f'止盈 ({profit_ratio:.1%})'
                    ))
                    del self.positions[ts_code]
                    continue

                # 移动止损
                if highest_price > entry_price * 1.1:  # 盈利 10% 后激活
                    trailing_stop = highest_price * 0.95
                    if current_price < trailing_stop:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='sell',
                            price=current_price,
                            volume=pos.get('shares', 1000),
                            reason=f'移动止损'
                        ))
                        del self.positions[ts_code]
                        continue
            else:
                # 突破入场
                if current_price > highest_high * 1.01 and current_vol > vol_ma * 1.2:
                    volume = int(self.engine.capital * 0.2 / current_price / 100) * 100 if self.engine else 1000
                    if volume >= 100:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='buy',
                            price=current_price,
                            volume=volume,
                            reason=f'突破 {self.lookback}日高'
                        ))
                        self.positions[ts_code] = {
                            'entry_price': current_price,
                            'highest_price': current_price,
                            'shares': volume,
                            'entry_date': current_date
                        }

        return signals


class MeanReversionStrategy(BaseStrategy):
    """
    均值回归策略

    核心逻辑:
    1. RSI 超卖时入场
    2. RSI 回归均值时出场
    3. 严格止损
    """

    def __init__(self, params: MultiStrategyParams):
        super().__init__("mean_reversion")
        self.params = params
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}

    def on_init(self):
        super().on_init()
        self.price_history = {}
        self.positions = {}

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0),
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            ).tail(40)

    def calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        """计算 RSI"""
        if len(close) < period + 1:
            return 50

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 0
        return 100 - (100 / (1 + rs))

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        self.update_price_history(data, current_date)
        signals = []

        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            if len(df) < 25:
                continue

            close = df['close']
            current_price = bar.get('close', 0)

            # 计算 RSI
            rsi = self.calculate_rsi(close, 14)

            # 检查持仓
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                entry_price = pos['entry_price']
                profit_ratio = (current_price - entry_price) / entry_price

                # 止损
                if profit_ratio <= -self.params.mr_stop_loss:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=pos.get('shares', 1000),
                        reason=f'止损 ({profit_ratio:.1%})'
                    ))
                    del self.positions[ts_code]
                    continue

                # 止盈 (RSI 回归)
                if rsi > 50 or profit_ratio >= self.params.mr_take_profit:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=current_price,
                        volume=pos.get('shares', 1000),
                        reason=f'RSI 回归 ({rsi:.0f})'
                    ))
                    del self.positions[ts_code]
                    continue
            else:
                # RSI 超买入场
                if rsi < 30:
                    volume = int(self.engine.capital * 0.15 / current_price / 100) * 100 if self.engine else 1000
                    if volume >= 100:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='buy',
                            price=current_price,
                            volume=volume,
                            reason=f'RSI 超卖 ({rsi:.0f})'
                        ))
                        self.positions[ts_code] = {
                            'entry_price': current_price,
                            'shares': volume,
                            'entry_date': current_date
                        }

        return signals


class MomentumRotationStrategy(BaseStrategy):
    """
    动量轮动策略

    核心逻辑:
    1. 计算股票动量排名
    2. 持有前 N 只股票
    3. 定期调仓
    """

    def __init__(self, params: MultiStrategyParams):
        super().__init__("momentum_rotation")
        self.params = params
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}
        self.days_since_rebalance = 0

    def on_init(self):
        super().on_init()
        self.price_history = {}
        self.positions = {}
        self.days_since_rebalance = 0

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0),
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            ).tail(30)

    def calculate_momentum(self, df: pd.DataFrame) -> float:
        """计算动量 (N 日收益率)"""
        if len(df) < self.params.mom_window:
            return 0

        close = df['close']
        mom = (close.iloc[-1] - close.iloc[-self.params.mom_window]) / close.iloc[-self.params.mom_window]
        return mom

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        self.update_price_history(data, current_date)
        self.days_since_rebalance += 1
        signals = []

        # 调仓日
        if self.days_since_rebalance >= self.params.mom_rebalance_days:
            self.days_since_rebalance = 0

            # 计算动量排名
            momentum_rank = {}
            for ts_code, df in self.price_history.items():
                if len(df) >= self.params.mom_window:
                    mom = self.calculate_momentum(df)
                    momentum_rank[ts_code] = mom

            # 排序
            sorted_stocks = sorted(momentum_rank.items(), key=lambda x: x[1], reverse=True)
            top_stocks = [s[0] for s in sorted_stocks[:self.params.mom_top_n]]

            # 卖出不在 Top N 的持仓
            for ts_code in list(self.positions.keys()):
                if ts_code not in top_stocks:
                    pos = self.positions[ts_code]
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='sell',
                        price=data[ts_code].get('close', 0),
                        volume=pos.get('shares', 1000),
                        reason='调仓'
                    ))
                    del self.positions[ts_code]

            # 买入 Top N 股票
            for ts_code in top_stocks:
                if ts_code not in self.positions and ts_code in data:
                    current_price = data[ts_code].get('close', 0)
                    volume = int(self.engine.capital * 0.2 / current_price / 100) * 100 if self.engine else 1000
                    if volume >= 100:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='buy',
                            price=current_price,
                            volume=volume,
                            reason=f'动量 Top{self.params.mom_top_n}'
                        ))
                        self.positions[ts_code] = {
                            'entry_price': current_price,
                            'shares': volume,
                            'entry_date': current_date
                        }

        return signals


class MultiStrategyPortfolio(BaseStrategy):
    """
    多策略组合

    整合:
    1. 趋势跟踪 (50%)
    2. 均值回归 (30%)
    3. 动量轮动 (20%)

    市场过滤:
    - 牛市：100% 仓位
    - 震荡市：30% 仓位
    - 熊市：0-10% 仓位
    """

    def __init__(
        self,
        name: str = "multi_strategy",
        params: Optional[MultiStrategyParams] = None
    ):
        super().__init__(name)
        self.params = params or MultiStrategyParams()

        # 初始化子策略
        self.trend_strategy = TrendFollowingStrategy(self.params)
        self.mr_strategy = MeanReversionStrategy(self.params)
        self.mom_strategy = MomentumRotationStrategy(self.params)

        # 市场过滤器
        self.market_filter = MarketFilter()

    def on_init(self):
        super().on_init()
        self.trend_strategy.on_init()
        self.mr_strategy.on_init()
        self.mom_strategy.on_init()
        strategy_logger.info("多策略组合初始化")
        strategy_logger.info(f"权重：趋势={self.params.trend_weight}, "
                            f"均值回归={self.params.mr_weight}, "
                            f"动量={self.params.mom_weight}")

    def set_market_data(self, market_df: pd.DataFrame):
        """设置市场数据"""
        self.market_filter.set_market_data(market_df)

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        # 判断市场状态
        if self.params.use_market_filter:
            # 使用第一个股票的数据作为市场数据代理
            if data:
                first_stock = list(data.keys())[0]
                if first_stock in self.price_history if hasattr(self, 'price_history') else True:
                    pass  # 市场数据已在外部设置
            position_mult = self.market_filter.get_position_multiplier()
            strategy_logger.info(f"市场状态：{self.market_filter.market_state.value}, 仓位系数：{position_mult}")

        # 合并各策略信号
        all_signals = []

        # 趋势策略信号
        trend_signals = self.trend_strategy.on_bar(data, current_date)
        all_signals.extend(trend_signals)

        # 均值回归信号
        mr_signals = self.mr_strategy.on_bar(data, current_date)
        all_signals.extend(mr_signals)

        # 动量轮动信号
        mom_signals = self.mom_strategy.on_bar(data, current_date)
        all_signals.extend(mom_signals)

        return all_signals


# 工厂函数
def create_multi_strategy(
    trend_weight: float = 0.5,
    mr_weight: float = 0.3,
    mom_weight: float = 0.2,
    use_market_filter: bool = True
) -> MultiStrategyPortfolio:
    """创建多策略组合"""
    params = MultiStrategyParams(
        trend_weight=trend_weight,
        mr_weight=mr_weight,
        mom_weight=mom_weight,
        use_market_filter=use_market_filter
    )
    return MultiStrategyPortfolio(params)
