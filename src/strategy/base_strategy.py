"""
策略基类模块
定义策略的标准接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import config.settings as settings
from config.logging_config import strategy_logger


@dataclass
class Signal:
    """交易信号数据类"""
    ts_code: str
    direction: str  # 'buy', 'sell', 'hold'
    price: float
    volume: int
    weight: float = 1.0  # 目标权重
    strength: float = 1.0  # 信号强度 (0-1)
    reason: str = ""  # 信号原因
    strategy_name: str = ""


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str = "base_strategy"):
        """
        初始化策略

        Args:
            name: 策略名称
        """
        self.name = name
        self.engine = None  # 回测引擎引用
        self.positions: Dict[str, Any] = {}
        self.params: Dict[str, Any] = {}
        self.initialized: bool = False

    def on_init(self):
        """策略初始化回调"""
        strategy_logger.info(f"策略 {self.name} 初始化")
        self.initialized = True

    def set_params(self, **kwargs):
        """
        设置策略参数

        Args:
            **kwargs: 策略参数
        """
        self.params.update(kwargs)
        strategy_logger.info(f"策略 {self.name} 参数更新：{kwargs}")

    def get_param(self, key: str, default=None):
        """
        获取策略参数

        Args:
            key: 参数名
            default: 默认值

        Returns:
            参数值
        """
        return self.params.get(key, default)

    @abstractmethod
    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """
        K 线数据回调 (每个交易日调用)

        Args:
            data: 当日行情数据字典 {ts_code: {open, high, low, close, vol, amount, ...}}
            current_date: 当前交易日期

        Returns:
            交易信号列表
        """
        pass

    def generate_signal(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        weight: float = 1.0,
        strength: float = 1.0,
        reason: str = ""
    ) -> Signal:
        """
        生成交易信号

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 价格
            volume: 数量
            weight: 目标权重
            strength: 信号强度
            reason: 信号原因

        Returns:
            交易信号
        """
        return Signal(
            ts_code=ts_code,
            direction=direction,
            price=price,
            volume=volume,
            weight=weight,
            strength=strength,
            reason=reason,
            strategy_name=self.name
        )

    def calculate_position_size(
        self,
        ts_code: str,
        signal_strength: float,
        current_price: float,
        total_capital: float
    ) -> int:
        """
        计算仓位大小

        Args:
            ts_code: 股票代码
            signal_strength: 信号强度
            current_price: 当前价格
            total_capital: 总资金

        Returns:
            买入数量 (100 的整数倍)
        """
        # 单只股票最大仓位
        max_stock_ratio = settings.MAX_STOCK_POSITION_RATIO
        max_order_value = settings.MAX_ORDER_VALUE

        # 根据信号强度调整仓位
        target_value = min(
            total_capital * max_stock_ratio * signal_strength,
            max_order_value
        )

        # 计算股数 (100 股的整数倍)
        volume = int(target_value / current_price / 100) * 100

        return max(0, volume)

    def get_current_position(self, ts_code: str) -> Optional[Any]:
        """
        获取当前持仓

        Args:
            ts_code: 股票代码

        Returns:
            持仓信息
        """
        if self.engine and hasattr(self.engine, 'positions'):
            return self.engine.positions.get(ts_code)
        return self.positions.get(ts_code)

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name})"


class BaseMultiAssetStrategy(BaseStrategy):
    """多资产策略基类"""

    def __init__(self, name: str = "base_multi_asset_strategy"):
        super().__init__(name)
        self.universe: List[str] = []  # 股票池
        self.weights: Dict[str, float] = {}  # 目标权重

    def set_universe(self, universe: List[str]):
        """
        设置股票池

        Args:
            universe: 股票代码列表
        """
        self.universe = universe
        strategy_logger.info(f"策略 {self.name} 股票池设置：{len(universe)} 只股票")

    def rank_stocks(self, scores: Dict[str, float], top_n: int = None) -> List[str]:
        """
        根据评分排序股票

        Args:
            scores: 股票评分字典
            top_n: 选取前 N 只

        Returns:
            排序后的股票列表
        """
        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if top_n:
            sorted_stocks = sorted_stocks[:top_n]

        return [stock for stock, score in sorted_stocks if score > 0]

    def equal_weight(self, stock_list: List[str]) -> Dict[str, float]:
        """
        等权重配置

        Args:
            stock_list: 股票列表

        Returns:
            权重字典
        """
        if not stock_list:
            return {}

        weight = 1.0 / len(stock_list)
        return {stock: weight for stock in stock_list}

    def volatility_weight(
        self,
        stock_list: List[str],
        volatility_data: Dict[str, float]
    ) -> Dict[str, float]:
        """
        波动率倒数加权

        Args:
            stock_list: 股票列表
            volatility_data: 波动率数据

        Returns:
            权重字典
        """
        inv_vol = {stock: 1.0 / vol for stock, vol in volatility_data.items() if vol > 0 and stock in stock_list}
        total = sum(inv_vol.values())

        if total == 0:
            return self.equal_weight(stock_list)

        return {stock: iv / total for stock, iv in inv_vol.items()}
