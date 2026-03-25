"""
券商接口模块
提供模拟交易和实盘交易接口
"""
import abc
from typing import Dict, List, Optional, Any
from datetime import datetime
import random

import config.settings as settings
from config.logging_config import trader_logger
from src.trader.order_manager import OrderManager, Order, Position
from src.trader.risk_control import RiskController


class BaseBroker(abc.ABC):
    """券商接口基类"""

    @abc.abstractmethod
    def connect(self) -> bool:
        """连接券商"""
        pass

    @abc.abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        pass

    @abc.abstractmethod
    def get_account_info(self) -> Dict:
        """获取账户信息"""
        pass

    @abc.abstractmethod
    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        pass

    @abc.abstractmethod
    def get_orders(self) -> List[Dict]:
        """获取订单"""
        pass

    @abc.abstractmethod
    def submit_order(self, order: Dict) -> Optional[str]:
        """提交订单"""
        pass

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        pass


class PaperBroker(BaseBroker):
    """
    模拟交易券商

    用于模拟真实交易环境，不支持真实资金
    """

    def __init__(self, initial_capital: float = None):
        """
        初始化模拟券商

        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital or settings.INITIAL_CAPITAL
        self.connected = False
        self.order_manager = None
        self.risk_controller = None

    def connect(self) -> bool:
        """连接模拟券商"""
        try:
            self.order_manager = OrderManager(account_name="paper_trading")
            self.risk_controller = RiskController()

            # 如果账户没有资金，初始化
            if self.order_manager.account.available_cash <= 0:
                self.order_manager.account.available_cash = self.initial_capital
                self.order_manager.account.total_asset = self.initial_capital

            self.connected = True
            trader_logger.info(f"模拟券商连接成功，初始资金：{self.initial_capital}")
            return True
        except Exception as e:
            trader_logger.error(f"模拟券商连接失败：{e}")
            return False

    def disconnect(self):
        """断开连接"""
        self.connected = False
        trader_logger.info("模拟券商断开连接")

    def is_connected(self) -> bool:
        """是否已连接"""
        return self.connected

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        if not self.connected:
            return {}

        return self.order_manager.get_account_summary()

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if not self.connected:
            return []

        positions = self.order_manager.get_all_positions()
        return [pos.to_dict() for pos in positions.values()]

    def get_orders(self, status: Optional[str] = None) -> List[Dict]:
        """获取订单"""
        if not self.connected:
            return []

        if status:
            orders = self.order_manager.get_orders_by_status(status)
        else:
            orders = list(self.order_manager.orders.values())

        return [o.to_dict() for o in orders]

    def submit_order(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        strategy_name: str = ""
    ) -> Optional[str]:
        """
        提交订单

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 价格
            volume: 数量
            strategy_name: 策略名称

        Returns:
            订单 ID，失败返回 None
        """
        if not self.connected:
            trader_logger.warning("模拟券商未连接")
            return None

        # 风控检查
        current_capital = self.order_manager.account.total_asset
        positions = {
            ts: {'market_value': pos.market_value, 'volume': pos.volume, 'avg_cost': pos.avg_cost}
            for ts, pos in self.order_manager.positions.items()
        }

        passed, reason = self.risk_controller.check_order(
            ts_code, direction, price, volume, current_capital, positions
        )

        if not passed:
            trader_logger.warning(f"订单未通过风控检查：{reason}")
            return None

        # 创建订单
        order = self.order_manager.create_order(
            ts_code=ts_code,
            direction=direction,
            price=price,
            volume=volume,
            strategy_name=strategy_name
        )

        if not order:
            return None

        # 模拟提交订单
        self.order_manager.submit_order(order.order_id)

        # 模拟成交 (模拟即时成交)
        self._simulate_fill(order)

        return order.order_id

    def _simulate_fill(self, order: Order):
        """
        模拟订单成交

        Args:
            order: 订单
        """
        # 添加随机滑点
        slippage = random.uniform(-0.005, 0.005)  # ±0.5% 滑点

        if order.direction == 'buy':
            fill_price = order.price * (1 + slippage)
        else:
            fill_price = order.price * (1 - slippage)

        # 成交
        self.order_manager.fill_order(order.order_id, fill_price, order.volume)

        # 记录到风控
        self.risk_controller.record_trade({
            'ts_code': order.ts_code,
            'direction': order.direction,
            'price': fill_price,
            'volume': order.volume,
            'value': fill_price * order.volume
        })

        trader_logger.info(
            f"[模拟成交] {order.ts_code} {order.direction} "
            f"{order.volume}@{fill_price:.2f}"
        )

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if not self.connected:
            return False

        return self.order_manager.cancel_order(order_id)

    def update_market_price(self, ts_code: str, price: float):
        """
        更新市场价格 (用于计算持仓市值)

        Args:
            ts_code: 股票代码
            price: 市场价格
        """
        if self.connected:
            self.order_manager.update_position_price(ts_code, price)

    def check_stop_loss_take_profit(self) -> List[Dict]:
        """
        检查止损止盈

        Returns:
            需要执行的止损止盈订单列表
        """
        if not self.connected:
            return []

        sell_orders = []

        for ts_code, position in self.order_manager.positions.items():
            triggered, reason = self.risk_controller.check_stop_loss_take_profit(
                ts_code, position.current_price, position.to_dict()
            )

            if triggered:
                trader_logger.info(f"{ts_code}: {reason}")
                sell_orders.append({
                    'ts_code': ts_code,
                    'direction': 'sell',
                    'price': position.current_price,
                    'volume': position.volume,
                    'reason': reason
                })

        return sell_orders

    def get_risk_report(self) -> str:
        """获取风险报告"""
        if not self.connected:
            return "模拟券商未连接"

        return self.risk_controller.generate_risk_report(
            self.order_manager.account.total_asset,
            {
                ts: pos.to_dict()
                for ts, pos in self.order_manager.positions.items()
            }
        )


class RealBroker(BaseBroker):
    """
    实盘交易券商接口

    整合 easytrader 实现，支持多种券商接入
    """

    def __init__(
        self,
        broker_type: str = "huatai",
        config_path: Optional[str] = None,
        use_easytrader: bool = True
    ):
        """
        初始化实盘券商

        Args:
            broker_type: 券商类型 (huatai/yinhai/guojin/cicc 等)
            config_path: 配置文件路径 (JSON 格式)
            use_easytrader: 是否使用 easytrader(默认 True)
        """
        self.broker_type = broker_type
        self.config_path = config_path
        self.use_easytrader = use_easytrader

        self.connected = False
        self.client = None
        self.risk_controller = None

        # 订单管理器（用于本地记录）
        self.order_manager = None

    def connect(self) -> bool:
        """连接实盘券商"""
        try:
            if self.use_easytrader:
                # 使用 easytrader 连接
                from src.trader.easytrader_broker import EasyTraderBroker

                self.client = EasyTraderBroker(
                    broker_type=self.broker_type,
                    config_path=self.config_path
                )

                if self.client.connect():
                    self.connected = True
                    self.risk_controller = RiskController()
                    trader_logger.info(f"实盘券商连接成功：{self.broker_type}")
                    return True
                else:
                    trader_logger.error("实盘券商连接失败")
                    return False
            else:
                # 自定义券商接口（用户可自行扩展）
                trader_logger.warning("自定义券商接口需要自行实现")
                return False

        except ImportError as e:
            trader_logger.error(f"easytrader 未安装：{e}")
            trader_logger.info("请运行：pip install easytrader")
            return False
        except Exception as e:
            trader_logger.error(f"连接实盘券商异常：{e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client and hasattr(self.client, 'disconnect'):
            self.client.disconnect()
        self.connected = False
        trader_logger.info("实盘券商已断开连接")

    def is_connected(self) -> bool:
        """是否已连接"""
        return self.connected

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        if not self.connected:
            return {}

        if self.client:
            return self.client.get_account_info()
        return {}

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if not self.connected:
            return []

        if self.client:
            return self.client.get_positions()
        return []

    def get_orders(self, status: Optional[str] = None) -> List[Dict]:
        """获取订单"""
        if not self.connected:
            return []

        if self.client and hasattr(self.client, 'get_orders'):
            return self.client.get_orders(status)
        return []

    def submit_order(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        strategy_name: str = ""
    ) -> Optional[str]:
        """
        提交订单

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 价格
            volume: 数量
            strategy_name: 策略名称

        Returns:
            订单 ID
        """
        if not self.connected:
            trader_logger.warning("实盘券商未连接")
            return None

        if self.client and hasattr(self.client, 'submit_order'):
            return self.client.submit_order(
                ts_code=ts_code,
                direction=direction,
                price=price,
                volume=volume,
                strategy_name=strategy_name
            )
        return None

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if not self.connected:
            return False

        if self.client and hasattr(self.client, 'cancel_order'):
            return self.client.cancel_order(order_id)
        return False

    def get_trades(self, start_date: Optional[str] = None) -> List[Dict]:
        """
        获取成交记录

        Args:
            start_date: 开始日期 (YYYYMMDD)

        Returns:
            成交记录列表
        """
        if not self.connected:
            return []

        if self.client and hasattr(self.client, 'get_trades'):
            return self.client.get_trades(start_date)
        return []

    def check_stop_loss_take_profit(self) -> List[Dict]:
        """
        检查止损止盈

        Returns:
            需要执行的订单列表
        """
        if not self.connected or not self.risk_controller:
            return []

        sell_orders = []
        positions = self.get_positions()

        for pos in positions:
            ts_code = pos['ts_code']
            triggered, reason = self.risk_controller.check_stop_loss_take_profit(
                ts_code, pos['current_price'], pos
            )

            if triggered:
                trader_logger.info(f"{ts_code}: {reason}")
                sell_orders.append({
                    'ts_code': ts_code,
                    'direction': 'sell',
                    'price': pos['current_price'],
                    'volume': pos['volume'],
                    'reason': reason
                })

        return sell_orders


# 创建模拟券商实例
paper_broker = PaperBroker()


def get_broker(
    broker_type: str = "paper",
    real_broker_type: str = "huatai",
    config_path: Optional[str] = None,
    **kwargs
) -> BaseBroker:
    """
    获取券商实例

    Args:
        broker_type: 券商类型 (paper/real)
        real_broker_type: 实盘券商类型 (huatai/yinhai/guojin 等)
        config_path: 配置文件路径
        **kwargs: 额外参数

    Returns:
        券商实例
    """
    if broker_type == "paper":
        return PaperBroker(kwargs.get('initial_capital'))
    elif broker_type == "real":
        return RealBroker(
            broker_type=real_broker_type,
            config_path=config_path
        )
    else:
        raise ValueError(f"不支持的券商类型：{broker_type}")
