"""
风险控制模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import config.settings as settings
from config.logging_config import trader_logger


@dataclass
class RiskLimits:
    """风险限制参数"""
    # 仓位限制
    max_position_ratio: float = 0.8  # 最大仓位比例
    max_stock_position_ratio: float = 0.2  # 单只股票最大持仓比例
    max_industry_ratio: float = 0.3  # 单一行业最大持仓比例

    # 交易限制
    max_order_value: float = 100000  # 单笔交易最大金额
    max_daily_turnover: float = 500000  # 单日最大成交额
    max_order_count: int = 50  # 单日最大交易次数

    # 止损止盈
    stop_loss_ratio: float = 0.05  # 止损比例 5%
    take_profit_ratio: float = 0.15  # 止盈比例 15%
    trailing_stop_ratio: float = 0.03  # 移动止损比例 3%

    # 回撤控制
    max_drawdown: float = 0.10  # 最大回撤 10%
    daily_max_loss: float = 0.03  # 单日最大亏损 3%

    # 集中度限制
    max_concentration: int = 10  # 最大持仓股票数量


@dataclass
class RiskMetrics:
    """风险指标"""
    # 仓位指标
    position_ratio: float = 0.0
    largest_position_ratio: float = 0.0

    # 盈亏指标
    total_profit_loss: float = 0.0
    total_profit_ratio: float = 0.0
    unrealized_profit_loss: float = 0.0

    # 回撤指标
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0

    # 交易指标
    today_turnover: float = 0.0
    today_order_count: int = 0

    # 风险状态
    is_trading_halted: bool = False  # 是否暂停交易
    halt_reason: str = ""


class RiskController:
    """风险控制器"""

    def __init__(self, limits: Optional[RiskLimits] = None):
        """
        初始化风险控制器

        Args:
            limits: 风险限制参数
        """
        self.limits = limits or RiskLimits()

        # 根据用户配置调整参数 (激进风格，2 万资金)
        self._adjust_for_aggressive_style()

        # 状态变量
        self.metrics = RiskMetrics()

        # 交易记录
        self.today_trades: List[Dict] = []
        self.today_orders: List[Dict] = []

        # 权益曲线用于计算回撤
        self.equity_history: List[float] = []
        self.peak_equity: float = 0.0

        # 持仓成本记录 (用于止损止盈)
        self.position_costs: Dict[str, Dict] = {}  # {ts_code: {cost, highest_price}}

    def _adjust_for_aggressive_style(self):
        """调整为激进风格参数 (2 万资金)"""
        # 激进风格：更高仓位，更宽止损
        self.limits.max_position_ratio = 0.95  # 最高 95% 仓位
        self.limits.max_stock_position_ratio = 0.30  # 单只股票最高 30%
        self.limits.stop_loss_ratio = 0.08  # 止损 8%
        self.limits.take_profit_ratio = 0.20  # 止盈 20%
        self.limits.max_drawdown = 0.15  # 最大回撤 15%
        self.limits.max_concentration = 5  # 最多持有 5 只股票
        self.limits.max_order_value = 20000  # 单笔最大 2 万

        trader_logger.info("风险控制参数已调整为激进风格 (2 万资金)")

    def check_order(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        current_capital: float,
        positions: Dict
    ) -> Tuple[bool, str]:
        """
        检查订单是否符合风控要求

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 价格
            volume: 数量
            current_capital: 当前资金
            positions: 当前持仓

        Returns:
            (是否通过，原因) 元组
        """
        order_value = price * volume

        # 1. 检查单笔交易金额
        if order_value > self.limits.max_order_value:
            return False, f"超过单笔交易限额：{order_value:.2f} > {self.limits.max_order_value:.2f}"

        # 2. 检查单日交易次数
        if len(self.today_orders) >= self.limits.max_order_count:
            return False, f"超过单日交易次数限制：{len(self.today_orders)} >= {self.limits.max_order_count}"

        # 3. 检查单日成交额
        today_turnover = sum(t.get('value', 0) for t in self.today_trades)
        if today_turnover + order_value > self.limits.max_daily_turnover:
            return False, f"超过单日成交额限制"

        # 4. 买入检查
        if direction == 'buy':
            # 检查仓位
            current_position_value = sum(
                pos.get('market_value', 0) for pos in positions.values()
            ) if positions else 0
            current_position_ratio = current_position_value / current_capital if current_capital > 0 else 0

            if current_position_ratio >= self.limits.max_position_ratio:
                return False, f"超过最大仓位限制：{current_position_ratio:.2%}"

            # 检查单只股票持仓
            if ts_code in positions:
                current_stock_value = positions[ts_code].get('market_value', 0)
            else:
                current_stock_value = 0

            new_stock_value = current_stock_value + order_value
            new_stock_ratio = new_stock_value / current_capital if current_capital > 0 else 0

            if new_stock_ratio > self.limits.max_stock_position_ratio:
                return False, f"超过单只股票持仓限制：{new_stock_ratio:.2%}"

            # 检查持仓集中度
            if len(positions) >= self.limits.max_concentration and ts_code not in positions:
                return False, f"超过最大持仓股票数量限制：{len(positions)}"

        # 5. 卖出检查
        elif direction == 'sell':
            if ts_code not in positions:
                return False, f"不持有该股票：{ts_code}"

            pos = positions[ts_code]
            if pos.get('volume', 0) < volume:
                return False, f"持仓不足：{pos.get('volume', 0)} < {volume}"

        # 6. 检查是否暂停交易
        if self.metrics.is_trading_halted:
            return False, f"交易已暂停：{self.metrics.halt_reason}"

        # 通过检查
        return True, "订单符合风控要求"

    def check_stop_loss_take_profit(
        self,
        ts_code: str,
        current_price: float,
        position: Dict
    ) -> Tuple[bool, str]:
        """
        检查止损止盈

        Args:
            ts_code: 股票代码
            current_price: 当前价格
            position: 持仓信息

        Returns:
            (是否触发，原因) 元组
        """
        if ts_code not in self.position_costs:
            self.position_costs[ts_code] = {
                'cost': position.get('avg_cost', current_price),
                'highest_price': current_price
            }

        cost_info = self.position_costs[ts_code]
        cost_price = cost_info['cost']

        # 更新最高价
        if current_price > cost_info['highest_price']:
            cost_info['highest_price'] = current_price

        # 计算盈亏比例
        profit_ratio = (current_price - cost_price) / cost_price if cost_price > 0 else 0

        # 1. 止损检查
        if profit_ratio <= -self.limits.stop_loss_ratio:
            return True, f"触发止损：{profit_ratio:.2%} <= {-self.limits.stop_loss_ratio:.2%}"

        # 2. 止盈检查
        if profit_ratio >= self.limits.take_profit_ratio:
            return True, f"触发止盈：{profit_ratio:.2%} >= {self.limits.take_profit_ratio:.2%}"

        # 3. 移动止损检查
        highest_price = cost_info['highest_price']
        if highest_price > cost_price * (1 + self.limits.trailing_stop_ratio):
            # 从最高点回撤超过阈值
            drawdown_from_peak = (highest_price - current_price) / highest_price
            if drawdown_from_peak >= self.limits.trailing_stop_ratio:
                return True, f"触发移动止损：回撤{drawdown_from_peak:.2%}"

        return False, ""

    def check_drawdown(self, current_equity: float) -> Tuple[bool, str]:
        """
        检查回撤

        Args:
            current_equity: 当前权益

        Returns:
            (是否触发，原因) 元组
        """
        self.equity_history.append(current_equity)

        # 更新峰值
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # 计算当前回撤
        if self.peak_equity > 0:
            current_drawdown = (self.peak_equity - current_equity) / self.peak_equity
        else:
            current_drawdown = 0

        self.metrics.current_drawdown = current_drawdown
        self.metrics.max_drawdown = max(self.metrics.max_drawdown, current_drawdown)

        # 检查最大回撤
        if current_drawdown >= self.limits.max_drawdown:
            self.metrics.is_trading_halted = True
            self.metrics.halt_reason = f"触发最大回撤限制：{current_drawdown:.2%}"
            return True, self.metrics.halt_reason

        return False, ""

    def check_daily_loss(self, today_pnl: float, initial_equity: float) -> Tuple[bool, str]:
        """
        检查单日亏损

        Args:
            today_pnl: 今日盈亏
            initial_equity: 初始权益

        Returns:
            (是否触发，原因) 元组
        """
        if initial_equity <= 0:
            return False, ""

        daily_loss_ratio = abs(today_pnl) / initial_equity if today_pnl < 0 else 0

        if daily_loss_ratio >= self.limits.daily_max_loss:
            self.metrics.is_trading_halted = True
            self.metrics.halt_reason = f"触发单日亏损限制：{daily_loss_ratio:.2%}"
            return True, self.metrics.halt_reason

        return False, ""

    def record_order(self, order: Dict):
        """
        记录订单

        Args:
            order: 订单信息
        """
        self.today_orders.append(order)

    def record_trade(self, trade: Dict):
        """
        记录成交

        Args:
            trade: 成交信息
        """
        self.today_trades.append(trade)

        # 更新持仓成本记录
        ts_code = trade.get('ts_code')
        if ts_code:
            if trade.get('direction') == 'buy':
                # 买入更新成本
                self.position_costs[ts_code] = {
                    'cost': trade.get('price', 0),
                    'highest_price': trade.get('price', 0)
                }

    def reset_daily(self):
        """重置每日计数"""
        self.today_orders = []
        self.today_trades = []
        self.metrics.is_trading_halted = False
        self.metrics.halt_reason = ""
        trader_logger.info("重置每日交易计数")

    def resume_trading(self):
        """恢复交易"""
        self.metrics.is_trading_halted = False
        self.metrics.halt_reason = ""
        trader_logger.info("恢复交易")

    def get_risk_metrics(self, current_capital: float, positions: Dict) -> RiskMetrics:
        """
        计算风险指标

        Args:
            current_capital: 当前资金
            positions: 持仓

        Returns:
            风险指标
        """
        # 仓位指标
        position_value = sum(
            pos.get('market_value', 0) for pos in positions.values()
        ) if positions else 0

        self.metrics.position_ratio = position_value / current_capital if current_capital > 0 else 0

        # 最大持仓比例
        if positions and current_capital > 0:
            largest_pos = max(
                pos.get('market_value', 0) for pos in positions.values()
            )
            self.metrics.largest_position_ratio = largest_pos / current_capital
        else:
            self.metrics.largest_position_ratio = 0

        # 盈亏指标
        total_cost = sum(
            pos.get('avg_cost', 0) * pos.get('volume', 0) for pos in positions.values()
        ) if positions else 0

        self.metrics.unrealized_profit_loss = position_value - total_cost
        self.metrics.total_profit_loss = self.metrics.unrealized_profit_loss
        self.metrics.total_profit_ratio = (
            self.metrics.unrealized_profit_loss / total_cost if total_cost > 0 else 0
        )

        # 交易指标
        self.metrics.today_turnover = sum(t.get('value', 0) for t in self.today_trades)
        self.metrics.today_order_count = len(self.today_orders)

        return self.metrics

    def generate_risk_report(self, current_capital: float, positions: Dict) -> str:
        """
        生成风险报告

        Args:
            current_capital: 当前资金
            positions: 持仓

        Returns:
            风险报告文本
        """
        metrics = self.get_risk_metrics(current_capital, positions)

        report = []
        report.append("=" * 50)
        report.append("风险控制报告")
        report.append("=" * 50)
        report.append("")
        report.append("【仓位状况】")
        report.append(f"  总仓位：{metrics.position_ratio * 100:.1f}%")
        report.append(f"  最大个股仓位：{metrics.largest_position_ratio * 100:.1f}%")
        report.append("")
        report.append("【盈亏状况】")
        report.append(f"  浮动盈亏：{metrics.unrealized_profit_loss:.2f}")
        report.append(f"  盈亏比例：{metrics.total_profit_ratio * 100:.1f}%")
        report.append("")
        report.append("【回撤状况】")
        report.append(f"  当前回撤：{metrics.current_drawdown * 100:.1f}%")
        report.append(f"  最大回撤：{metrics.max_drawdown * 100:.1f}%")
        report.append("")
        report.append("【交易状况】")
        report.append(f"  今日成交：{len(self.today_trades)} 笔")
        report.append(f"  今日成交额：{metrics.today_turnover:.2f}")
        report.append("")
        report.append("【风险状态】")
        if metrics.is_trading_halted:
            report.append(f"  ⚠️ 交易暂停：{metrics.halt_reason}")
        else:
            report.append("  ✓ 交易正常")
        report.append("=" * 50)

        return "\n".join(report)


# 创建风险控制器实例
risk_controller = RiskController()
