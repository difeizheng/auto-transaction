"""
回测引擎核心模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

import config.settings as settings
from config.logging_config import backtest_logger
from src.utils.database import db
from src.data_collector.data_manager import data_manager


@dataclass
class Order:
    """订单数据类"""
    ts_code: str
    direction: str  # 'buy' or 'sell'
    price: float
    volume: int
    timestamp: str
    order_id: str = ""
    status: str = "pending"  # pending/filled/cancelled
    strategy_name: str = ""


@dataclass
class Position:
    """持仓数据类"""
    ts_code: str
    volume: int
    avg_cost: float
    market_value: float = 0.0
    profit_loss: float = 0.0
    profit_ratio: float = 0.0


@dataclass
class Trade:
    """成交数据类"""
    order_id: str
    ts_code: str
    direction: str
    price: float
    volume: int
    timestamp: str
    commission: float
    stamp_tax: float
    slippage: float


@dataclass
class BacktestResult:
    """回测结果数据类"""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    final_capital: float = 0.0
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    trades: List[Trade] = field(default_factory=list)
    daily_returns: pd.Series = field(default_factory=pd.Series)


class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        initial_capital: float = None,
        commission_rate: float = None,
        stamp_tax_rate: float = None,
        slippage_rate: float = None,
        max_position_ratio: float = None
    ):
        """
        初始化回测引擎

        Args:
            initial_capital: 初始资金
            commission_rate: 佣金费率
            stamp_tax_rate: 印花税率
            slippage_rate: 滑点费率
            max_position_ratio: 最大仓位比例
        """
        self.initial_capital = initial_capital or settings.INITIAL_CAPITAL
        self.commission_rate = commission_rate or settings.COMMISSION_RATE
        self.stamp_tax_rate = stamp_tax_rate or settings.STAMP_TAX_RATE
        self.slippage_rate = slippage_rate or settings.SLIPPAGE_RATE
        self.max_position_ratio = max_position_ratio or settings.MAX_POSITION_RATIO

        # 状态变量
        self.capital = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        self.daily_returns: List[float] = []

        # 交易日期
        self.trade_dates: List[str] = []
        self.current_date: str = ""

        # 策略引用
        self.strategy = None

    def reset(self):
        """重置引擎状态"""
        self.capital = self.initial_capital
        self.positions.clear()
        self.orders.clear()
        self.trades.clear()
        self.equity_curve.clear()
        self.daily_returns.clear()
        self.current_date = ""

    def load_data(
        self,
        ts_codes: List[str],
        start_date: str,
        end_date: str
    ) -> Dict[str, pd.DataFrame]:
        """
        加载回测数据

        Args:
            ts_codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            股票代码 -> 行情数据的字典
        """
        backtest_logger.info(f"加载回测数据：{ts_codes}, {start_date} - {end_date}")

        data_dict = {}
        for ts_code in ts_codes:
            df = data_manager.get_daily_quotes(ts_code, start_date, end_date)
            if not df.empty:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df = df.sort_values('trade_date')
                data_dict[ts_code] = df

        # 获取交易日期
        all_dates = set()
        for df in data_dict.values():
            all_dates.update(df['trade_date'].astype(str).str.replace('-', ''))

        self.trade_dates = sorted(list(all_dates))
        backtest_logger.info(f"加载完成，共 {len(self.trade_dates)} 个交易日")

        return data_dict

    def set_strategy(self, strategy):
        """
        设置策略

        Args:
            strategy: 策略实例
        """
        self.strategy = strategy
        strategy.engine = self

    def calculate_transaction_cost(
        self,
        direction: str,
        price: float,
        volume: int
    ) -> Tuple[float, float, float]:
        """
        计算交易成本

        Args:
            direction: 买卖方向
            price: 成交价格
            volume: 成交数量

        Returns:
            (佣金，印花税，滑点) 元组
        """
        amount = price * volume
        commission = max(5, amount * self.commission_rate)  # 最低 5 元
        stamp_tax = amount * self.stamp_tax_rate if direction == 'sell' else 0
        slippage = amount * self.slippage_rate

        return commission, stamp_tax, slippage

    def execute_order(self, order: Order, current_price: float) -> Optional[Trade]:
        """
        执行订单

        Args:
            order: 订单
            current_price: 当前价格

        Returns:
            成交记录
        """
        # 应用滑点
        if order.direction == 'buy':
            exec_price = current_price * (1 + self.slippage_rate)
        else:
            exec_price = current_price * (1 - self.slippage_rate)

        # 计算成本
        commission, stamp_tax, slippage = self.calculate_transaction_cost(
            order.direction, exec_price, order.volume
        )

        total_cost = commission + stamp_tax + slippage

        # 检查资金是否充足
        if order.direction == 'buy':
            required_amount = exec_price * order.volume + total_cost
            if required_amount > self.capital:
                # 资金不足，调整数量
                available_volume = int((self.capital - total_cost) / exec_price / 100) * 100
                if available_volume <= 0:
                    order.status = 'cancelled'
                    return None
                order.volume = available_volume

        # 更新持仓
        ts_code = order.ts_code

        if order.direction == 'buy':
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                old_value = pos.avg_cost * pos.volume
                new_value = exec_price * order.volume
                pos.volume += order.volume
                pos.avg_cost = (old_value + new_value) / pos.volume if pos.volume > 0 else exec_price
            else:
                self.positions[ts_code] = Position(
                    ts_code=ts_code,
                    volume=order.volume,
                    avg_cost=exec_price
                )
            # 扣除资金
            self.capital -= (exec_price * order.volume + total_cost)

        else:  # sell
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                sell_volume = min(order.volume, pos.volume)
                if sell_volume <= 0:
                    order.status = 'cancelled'
                    return None

                # 实现盈亏
                profit = (exec_price - pos.avg_cost) * sell_volume
                pos.volume -= sell_volume

                if pos.volume <= 0:
                    del self.positions[ts_code]

                # 增加资金
                self.capital += (exec_price * sell_volume - total_cost)

        # 创建成交记录
        trade = Trade(
            order_id=order.order_id or f"{order.timestamp}_{ts_code}_{order.direction}",
            ts_code=ts_code,
            direction=order.direction,
            price=exec_price,
            volume=order.volume,
            timestamp=order.timestamp,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage=slippage
        )

        order.status = 'filled'
        self.trades.append(trade)
        self.orders.append(order)

        backtest_logger.debug(f"成交：{ts_code} {order.direction} {order.volume}@{exec_price:.2f}")

        return trade

    def update_equity_curve(self, market_data: Dict[str, pd.DataFrame]):
        """
        更新权益曲线

        Args:
            market_data: 行情数据字典
        """
        # 计算当前持仓市值
        position_value = 0.0
        for ts_code, pos in self.positions.items():
            if ts_code in market_data and not market_data[ts_code].empty:
                # 获取最新价格
                latest_price = market_data[ts_code].iloc[-1]['close']
                pos.market_value = latest_price * pos.volume
                pos.profit_loss = (latest_price - pos.avg_cost) * pos.volume
                pos.profit_ratio = (latest_price / pos.avg_cost - 1) if pos.avg_cost > 0 else 0
                position_value += pos.market_value

        # 总权益
        total_equity = self.capital + position_value

        # 记录权益曲线
        self.equity_curve.append({
            'date': self.current_date,
            'capital': self.capital,
            'position_value': position_value,
            'total_equity': total_equity
        })

        # 计算日收益率
        if len(self.equity_curve) > 1:
            prev_equity = self.equity_curve[-2]['total_equity']
            curr_equity = self.equity_curve[-1]['total_equity']
            daily_return = (curr_equity - prev_equity) / prev_equity if prev_equity > 0 else 0
            self.daily_returns.append(daily_return)

    def run(self, market_data: Dict[str, pd.DataFrame]) -> BacktestResult:
        """
        运行回测

        Args:
            market_data: 行情数据字典

        Returns:
            回测结果
        """
        backtest_logger.info("开始运行回测...")
        self.reset()

        if self.strategy is None:
            raise ValueError("未设置策略")

        # 获取所有交易日期
        all_dates = set()
        for df in market_data.values():
            # 确保 trade_date 是字符串格式
            try:
                all_dates.update(df['trade_date'].dt.strftime('%Y%m%d'))
            except AttributeError:
                # 如果 trade_date 已经是字符串，直接使用
                all_dates.update(df['trade_date'].astype(str).tolist())

        sorted_dates = sorted(list(all_dates))

        # 初始化策略
        self.strategy.on_init()

        # 按日期迭代
        for i, date_str in enumerate(sorted_dates):
            self.current_date = date_str

            # 获取当日数据
            day_data = {}
            for ts_code, df in market_data.items():
                try:
                    row = df[df['trade_date'].dt.strftime('%Y%m%d') == date_str]
                except AttributeError:
                    row = df[df['trade_date'].astype(str) == date_str]
                if not row.empty:
                    day_data[ts_code] = row.iloc[0]

            # 策略生成信号
            if self.strategy:
                signals = self.strategy.on_bar(day_data, date_str)

                # 执行信号
                if signals:
                    for signal in signals:
                        order = Order(
                            ts_code=signal.ts_code,
                            direction=signal.direction,
                            price=day_data.get(signal.ts_code, {}).get('close', 0) if signal.ts_code in day_data else signal.price,
                            volume=signal.volume,
                            timestamp=date_str,
                            strategy_name=signal.strategy_name
                        )
                        if order.price > 0 and order.volume > 0:
                            self.execute_order(order, order.price)

            # 更新权益曲线
            self.update_equity_curve(market_data)

        backtest_logger.info("回测完成")
        return self.generate_result()

    def generate_result(self) -> BacktestResult:
        """生成回测结果"""
        if not self.equity_curve:
            return BacktestResult()

        # 转换为 DataFrame
        equity_df = pd.DataFrame(self.equity_curve)

        # 计算收益率序列
        daily_returns = pd.Series(self.daily_returns)

        # 总收益率
        total_return = (equity_df['total_equity'].iloc[-1] - self.initial_capital) / self.initial_capital

        # 年化收益率
        trading_days = len(self.equity_curve)
        annual_return = (1 + total_return) ** (252 / trading_days) - 1 if trading_days > 0 else 0

        # 夏普比率
        if daily_returns.std() > 0:
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
        else:
            sharpe_ratio = 0

        # 最大回撤
        equity_curve = equity_df['total_equity']
        peak = equity_curve.expanding(min_periods=1).max()
        drawdown = (equity_curve - peak) / peak
        max_drawdown = abs(drawdown.min())

        # 交易统计
        total_trades = len(self.trades)
        buy_trades = [t for t in self.trades if t.direction == 'buy']
        sell_trades = [t for t in self.trades if t.direction == 'sell']

        # 计算盈亏
        trade_profits = []
        position_books = defaultdict(list)  # 持仓成本记录

        for trade in self.trades:
            if trade.direction == 'buy':
                position_books[trade.ts_code].append(trade.price)
            elif trade.direction == 'sell' and trade.ts_code in position_books:
                if position_books[trade.ts_code]:
                    cost_basis = position_books[trade.ts_code].pop(0)
                    profit = (trade.price - cost_basis) * trade.volume
                    trade_profits.append(profit)

        winning_trades = sum(1 for p in trade_profits if p > 0)
        losing_trades = sum(1 for p in trade_profits if p < 0)
        win_rate = winning_trades / len(trade_profits) if trade_profits else 0

        gross_profit = sum(p for p in trade_profits if p > 0)
        gross_loss = abs(sum(p for p in trade_profits if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        avg_profit = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0

        result = BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            final_capital=equity_df['total_equity'].iloc[-1],
            equity_curve=equity_df,
            trades=self.trades,
            daily_returns=daily_returns
        )

        self._print_result(result)
        return result

    def _print_result(self, result: BacktestResult):
        """打印回测结果"""
        print("\n" + "=" * 50)
        print("回测结果")
        print("=" * 50)
        print(f"初始资金：{self.initial_capital:,.2f}")
        print(f"最终权益：{result.final_capital:,.2f}")
        print(f"总收益率：{result.total_return * 100:.2f}%")
        print(f"年化收益率：{result.annual_return * 100:.2f}%")
        print(f"夏普比率：{result.sharpe_ratio:.2f}")
        print(f"最大回撤：{result.max_drawdown * 100:.2f}%")
        print(f"胜率：{result.win_rate * 100:.2f}%")
        print(f"盈亏比：{result.profit_factor:.2f}")
        print(f"总交易次数：{result.total_trades}")
        print(f"盈利次数：{result.winning_trades}")
        print(f"亏损次数：{result.losing_trades}")
        print("=" * 50)


# 回测引擎实例
backtest_engine = BacktestEngine()
