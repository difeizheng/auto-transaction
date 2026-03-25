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
    max_stock_position_ratio: float = 0.15  # 单只股票最大持仓比例 (降至 15%)
    max_industry_ratio: float = 0.30  # 单一行业最大持仓比例

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

    # 动态仓位调整
    volatility_lookback: int = 20  # 波动率观察期 (交易日)
    base_volatility: float = 0.02  # 基准波动率 (2%)
    volatility_scaling: float = 0.5  # 波动率缩放因子

    # ========== 实盘风控增强参数 ==========
    # 价格异常检测
    max_price_change_ratio: float = 0.10  # 单日最大涨跌幅限制 10%
    price_anomaly_threshold: float = 0.03  # 价格异常波动阈值 3%

    # 涨跌停过滤
    limit_up_check_enabled: bool = True  # 启用涨跌停检查
    limit_up_buffer: float = 0.02  # 涨停板缓冲 2%

    # 流动性检测
    min_daily_volume: int = 100000  # 最小日成交量（手）
    min_daily_amount: float = 10000000  # 最小日成交额（元）
    volume_ratio_threshold: float = 0.5  # 量比阈值

    # 交易时段限制
    avoid_call_auction: bool = True  # 避免集合竞价
    morning_start_time: str = "09:35"  # 上午开始交易时间（避开集合竞价）
    afternoon_end_time: str = "14:55"  # 下午结束交易时间（避开尾盘）

    # 订单确认
    large_order_threshold: float = 50000  # 大额订单阈值（元）
    large_order_confirmation: bool = True  # 大额订单需要二次确认

    # 实盘模式标志
    real_trading_mode: bool = False  # 实盘模式开关


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

        # 行业集中度跟踪 {industry: total_value}
        self.industry_exposure: Dict[str, float] = {}

        # 股票行业映射 {ts_code: industry}
        self.stock_industry_map: Dict[str, str] = {}

        # 波动率历史用于动态仓位调整 {ts_code: [volatility_values]}
        self.volatility_history: Dict[str, List[float]] = {}

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

    def set_stock_industry(self, ts_code: str, industry: str):
        """
        设置股票所属行业

        Args:
            ts_code: 股票代码
            industry: 行业名称
        """
        self.stock_industry_map[ts_code] = industry
        trader_logger.debug(f"设置股票行业：{ts_code} -> {industry}")

    def check_industry_concentration(
        self,
        ts_code: str,
        order_value: float,
        positions: Dict
    ) -> Tuple[bool, str]:
        """
        检查行业集中度

        Args:
            ts_code: 股票代码
            order_value: 订单金额
            positions: 当前持仓

        Returns:
            (是否通过，原因) 元组
        """
        industry = self.stock_industry_map.get(ts_code)
        if not industry:
            return True, ""  # 未知行业，跳过检查

        # 计算该行业当前持仓
        current_industry_value = 0.0
        total_position_value = 0.0

        for held_code, pos in positions.items():
            pos_value = pos.get('market_value', 0)
            total_position_value += pos_value

            held_industry = self.stock_industry_map.get(held_code)
            if held_industry == industry:
                current_industry_value += pos_value

        # 加上拟买入金额
        new_industry_value = current_industry_value + order_value
        industry_ratio = new_industry_value / total_position_value if total_position_value > 0 else 0

        if industry_ratio > self.limits.max_industry_ratio:
            return False, f"超过行业集中度限制：{industry} 行业 {industry_ratio:.1%} > {self.limits.max_industry_ratio:.1%}"

        return True, ""

    def update_volatility_history(self, ts_code: str, volatility: float):
        """
        更新股票波动率历史

        Args:
            ts_code: 股票代码
            volatility: 波动率值
        """
        if ts_code not in self.volatility_history:
            self.volatility_history[ts_code] = []

        self.volatility_history[ts_code].append(volatility)

        # 保留观察期数据
        lookback = self.limits.volatility_lookback
        if len(self.volatility_history[ts_code]) > lookback:
            self.volatility_history[ts_code] = self.volatility_history[ts_code][-lookback:]

    def calculate_dynamic_position_adjustment(self, ts_code: str) -> float:
        """
        计算动态仓位调整因子

        基于历史波动率：高波动降仓，低波动增仓

        Args:
            ts_code: 股票代码

        Returns:
            仓位调整因子 (0.5-1.5)
        """
        if ts_code not in self.volatility_history or not self.volatility_history[ts_code]:
            return 1.0  # 无数据，不调整

        vol_history = self.volatility_history[ts_code]
        if len(vol_history) < 5:
            return 1.0  # 数据不足，不调整

        # 计算平均波动率
        avg_volatility = np.mean(vol_history[-self.limits.volatility_lookback:])
        base_vol = self.limits.base_volatility

        # 波动率调整因子
        # 波动率 > 基准 -> 降仓 (最低 0.5)
        # 波动率 < 基准 -> 增仓 (最高 1.5)
        if base_vol > 0:
            vol_ratio = avg_volatility / base_vol
            adjustment = 1.0 / (1.0 + self.limits.volatility_scaling * (vol_ratio - 1.0))
        else:
            adjustment = 1.0

        # 限制调整范围
        adjustment = max(0.5, min(1.5, adjustment))

        return adjustment

    # ========== 实盘风控增强方法 ==========

    def enable_real_trading_mode(self, enabled: bool = True):
        """
        启用/禁用实盘模式

        Args:
            enabled: 是否启用实盘模式
        """
        self.limits.real_trading_mode = enabled
        if enabled:
            trader_logger.info("实盘风控模式已启用")
        else:
            trader_logger.info("已切换至模拟风控模式")

    def check_trading_time(self) -> Tuple[bool, str]:
        """
        检查当前是否在允许交易的时间段内

        Returns:
            (是否允许交易，原因) 元组
        """
        if not self.limits.avoid_call_auction:
            return True, ""

        from datetime import time as dt_time
        from datetime import datetime

        now = datetime.now()
        current_time = now.time()

        # 解析时间配置
        morning_parts = self.limits.morning_start_time.split(':')
        morning_start = dt_time(int(morning_parts[0]), int(morning_parts[1]))

        afternoon_parts = self.limits.afternoon_end_time.split(':')
        afternoon_end = dt_time(int(afternoon_parts[0]), int(afternoon_parts[1]))

        # 检查是否在允许的交易时间段
        if current_time < morning_start:
            return False, f"集合竞价时段禁止交易（早于 {self.limits.morning_start_time}）"

        if current_time > afternoon_end:
            return False, f"尾盘时段禁止交易（晚于 {self.limits.afternoon_end_time}）"

        return True, "交易时段正常"

    def check_price_anomaly(
        self,
        ts_code: str,
        current_price: float,
        prev_close: float,
        realtime_volatility: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        检查价格异常

        Args:
            ts_code: 股票代码
            current_price: 当前价格
            prev_close: 昨收价
            realtime_volatility: 实时波动率

        Returns:
            (是否通过，原因) 元组
        """
        if prev_close <= 0:
            return True, ""

        # 计算涨跌幅
        price_change = (current_price - prev_close) / prev_close

        # 检查是否接近涨跌停
        if self.limits.limit_up_check_enabled:
            limit_up_threshold = 1.0 - self.limits.limit_up_buffer
            limit_down_threshold = -1.0 + self.limits.limit_up_buffer

            if price_change > limit_up_threshold:
                return False, f"接近涨停，禁止买入：{price_change*100:.2f}%"
            if price_change < limit_down_threshold and realtime_volatility:
                # 跌停时如果有异常波动，禁止交易
                return False, f"接近跌停且波动异常：{price_change*100:.2f}%"

        # 检查异常波动
        if abs(price_change) > self.limits.price_anomaly_threshold:
            trader_logger.warning(f"{ts_code} 价格异常波动：{price_change*100:.2f}%")

        return True, "价格正常"

    def check_liquidity(
        self,
        ts_code: str,
        daily_volume: int,
        daily_amount: float,
        order_volume: int,
        order_value: float
    ) -> Tuple[bool, str]:
        """
        检查流动性

        Args:
            ts_code: 股票代码
            daily_volume: 日成交量（手）
            daily_amount: 日成交额（元）
            order_volume: 订单数量
            order_value: 订单金额

        Returns:
            (是否通过，原因) 元组
        """
        # 检查最小成交量
        if daily_volume < self.limits.min_daily_volume:
            return False, f"成交量过低：{daily_volume} < {self.limits.min_daily_volume}手"

        # 检查最小成交额
        if daily_amount < self.limits.min_daily_amount:
            return False, f"成交额过低：{daily_amount:.2f} < {self.limits.min_daily_amount:.2f}元"

        # 检查订单占成交量比例（避免过大冲击）
        if daily_volume > 0:
            order_ratio = order_volume / daily_volume
            if order_ratio > 0.05:  # 订单超过日成交量 5%
                return False, f"订单过大，可能产生较大冲击：{order_ratio*100:.2f}%"

        return True, "流动性正常"

    def check_large_order(
        self,
        order_value: float
    ) -> Tuple[bool, str]:
        """
        检查大额订单

        Args:
            order_value: 订单金额

        Returns:
            (是否通过，原因) 元组
        """
        if not self.limits.large_order_confirmation:
            return True, ""

        if order_value >= self.limits.large_order_threshold:
            return False, f"大额订单需要二次确认：{order_value:.2f} >= {self.limits.large_order_threshold:.2f}"

        return True, "订单金额正常"

    def check_order_real_trading(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        market_data: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """
        实盘模式下的订单检查（整合所有实盘风控检查）

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 当前价格
            volume: 数量
            market_data: 市场数据（包含 prev_close, daily_volume, daily_amount 等）

        Returns:
            (是否通过，原因) 元组
        """
        if not self.limits.real_trading_mode:
            return True, "模拟模式，跳过实盘检查"

        # 1. 检查交易时间
        time_ok, time_reason = self.check_trading_time()
        if not time_ok:
            return False, time_reason

        # 2. 检查价格异常
        if market_data:
            prev_close = market_data.get('prev_close', price)
            price_ok, price_reason = self.check_price_anomaly(
                ts_code, price, prev_close
            )
            if not price_ok:
                return False, price_reason

            # 3. 检查流动性
            daily_volume = market_data.get('daily_volume', 0)
            daily_amount = market_data.get('daily_amount', 0)
            liquidity_ok, liquidity_reason = self.check_liquidity(
                ts_code, daily_volume, daily_amount, volume, price * volume
            )
            if not liquidity_ok:
                return False, liquidity_reason

        # 4. 检查大额订单
        order_value = price * volume
        large_order_ok, large_order_reason = self.check_large_order(order_value)
        if not large_order_ok:
            return False, large_order_reason

        return True, "通过实盘风控检查"

    # ========== 原有方法 ==========

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

            # 检查行业集中度
            industry_ok, industry_reason = self.check_industry_concentration(ts_code, order_value, positions)
            if not industry_ok:
                return False, industry_reason

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

    def get_industry_exposure(self, positions: Dict) -> Dict[str, Dict]:
        """
        获取行业暴露度

        Args:
            positions: 持仓

        Returns:
            {industry: {value, ratio, stocks}}
        """
        exposure = {}
        total_value = sum(pos.get('market_value', 0) for pos in positions.values())

        for ts_code, pos in positions.items():
            industry = self.stock_industry_map.get(ts_code, '未知')
            pos_value = pos.get('market_value', 0)

            if industry not in exposure:
                exposure[industry] = {'value': 0, 'ratio': 0, 'stocks': []}

            exposure[industry]['value'] += pos_value
            exposure[industry]['stocks'].append(ts_code)

        # 计算比例
        for industry in exposure:
            if total_value > 0:
                exposure[industry]['ratio'] = exposure[industry]['value'] / total_value

        return exposure

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
        industry_exposure = self.get_industry_exposure(positions)

        report = []
        report.append("=" * 50)
        report.append("风险控制报告")
        report.append("=" * 50)
        report.append("")
        report.append("【仓位状况】")
        report.append(f"  总仓位：{metrics.position_ratio * 100:.1f}%")
        report.append(f"  最大个股仓位：{metrics.largest_position_ratio * 100:.1f}%")
        report.append("")
        report.append("【行业集中度】")
        for industry, data in sorted(industry_exposure.items(), key=lambda x: x[1]['ratio'], reverse=True):
            stocks = ', '.join(data['stocks'][:3])  # 只显示前 3 只
            report.append(f"  {industry}: {data['ratio']*100:.1f}% ({stocks})")
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
