"""
订单管理模块
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import config.settings as settings
from config.logging_config import trader_logger
from src.utils.database import db


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderDirection(Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """订单数据类"""
    ts_code: str
    direction: str
    price: float
    volume: int
    order_id: str = ""
    status: str = "pending"
    strategy_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    filled_volume: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    stamp_tax: float = 0.0

    def __post_init__(self):
        if not self.order_id:
            self.order_id = self._generate_order_id()
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.updated_at:
            self.updated_at = self.created_at

    @staticmethod
    def _generate_order_id() -> str:
        """生成订单 ID"""
        return f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'order_id': self.order_id,
            'ts_code': self.ts_code,
            'direction': self.direction,
            'price': self.price,
            'volume': self.volume,
            'status': self.status,
            'strategy_name': self.strategy_name,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'filled_volume': self.filled_volume,
            'filled_price': self.filled_price,
            'commission': self.commission,
            'stamp_tax': self.stamp_tax
        }


@dataclass
class Position:
    """持仓数据类"""
    ts_code: str
    volume: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    profit_loss: float = 0.0
    profit_ratio: float = 0.0

    def update_price(self, price: float):
        """更新当前价格"""
        self.current_price = price
        self.market_value = price * self.volume
        self.profit_loss = (price - self.avg_cost) * self.volume
        self.profit_ratio = (price / self.avg_cost - 1) if self.avg_cost > 0 else 0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'volume': self.volume,
            'avg_cost': self.avg_cost,
            'current_price': self.current_price,
            'market_value': self.market_value,
            'profit_loss': self.profit_loss,
            'profit_ratio': self.profit_ratio
        }


@dataclass
class Account:
    """账户数据类"""
    account_name: str
    total_asset: float = 0.0
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    total_position_value: float = 0.0

    def update_position_value(self, position_value: float):
        """更新持仓市值"""
        self.total_position_value = position_value
        self.total_asset = self.available_cash + self.frozen_cash + self.total_position_value

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'account_name': self.account_name,
            'total_asset': self.total_asset,
            'available_cash': self.available_cash,
            'frozen_cash': self.frozen_cash,
            'total_position_value': self.total_position_value
        }


class OrderManager:
    """订单管理器"""

    def __init__(self, account_name: str = "default"):
        """
        初始化订单管理器

        Args:
            account_name: 账户名称
        """
        self.account_name = account_name
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.account = Account(account_name=account_name)

        # 数据库引用
        self.db = db

        # 加载账户和持仓
        self._load_account()
        self._load_positions()

    def _load_account(self):
        """从数据库加载账户信息"""
        if self.db.table_exists('accounts'):
            df = self.db.query("SELECT * FROM accounts WHERE account_name = ?", (self.account_name,))
            if not df.empty:
                row = df.iloc[0]
                self.account = Account(
                    account_name=row['account_name'],
                    total_asset=row['total_asset'],
                    available_cash=row['available_cash'],
                    frozen_cash=row['frozen_cash'],
                    total_position_value=row['total_position_value']
                )
            else:
                # 初始化账户
                self.account.available_cash = settings.INITIAL_CAPITAL
                self.account.total_asset = settings.INITIAL_CAPITAL
                self._save_account()

    def _load_positions(self):
        """从数据库加载持仓"""
        if self.db.table_exists('positions'):
            df = self.db.query("SELECT * FROM positions")
            for _, row in df.iterrows():
                self.positions[row['ts_code']] = Position(
                    ts_code=row['ts_code'],
                    volume=row['volume'],
                    avg_cost=row['avg_cost'],
                    current_price=row.get('current_price', 0),
                    market_value=row.get('market_value', 0),
                    profit_loss=row.get('profit_loss', 0),
                    profit_ratio=row.get('profit_ratio', 0)
                )

    def _save_account(self):
        """保存账户信息到数据库"""
        self.db.execute("""
            INSERT OR REPLACE INTO accounts
            (account_name, total_asset, available_cash, frozen_cash, total_position_value, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            self.account.account_name,
            self.account.total_asset,
            self.account.available_cash,
            self.account.frozen_cash,
            self.account.total_position_value
        ))

    def _save_position(self, position: Position):
        """保存持仓到数据库"""
        self.db.execute("""
            INSERT OR REPLACE INTO positions
            (ts_code, volume, avg_cost, current_price, market_value, profit_loss, profit_ratio, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            position.ts_code,
            position.volume,
            position.avg_cost,
            position.current_price,
            position.market_value,
            position.profit_loss,
            position.profit_ratio
        ))

    def _delete_position(self, ts_code: str):
        """删除持仓"""
        self.db.execute("DELETE FROM positions WHERE ts_code = ?", (ts_code,))

    def create_order(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        strategy_name: str = ""
    ) -> Optional[Order]:
        """
        创建订单

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 价格
            volume: 数量
            strategy_name: 策略名称

        Returns:
            订单对象，失败返回 None
        """
        # 验证订单
        if price <= 0 or volume <= 0:
            trader_logger.warning(f"无效订单：{ts_code} {direction} {volume}@{price}")
            return None

        # 检查资金
        if direction == 'buy':
            required_amount = price * volume * 1.001  # 包含手续费
            if required_amount > self.account.available_cash:
                trader_logger.warning(f"资金不足：需要{required_amount:.2f}, 可用{self.account.available_cash:.2f}")
                return None

        # 检查持仓
        if direction == 'sell':
            if ts_code not in self.positions:
                trader_logger.warning(f"无持仓：{ts_code}")
                return None
            if self.positions[ts_code].volume < volume:
                trader_logger.warning(
                    f"持仓不足：{ts_code} 需要{volume}, 持有{self.positions[ts_code].volume}"
                )
                return None

        # 创建订单
        order = Order(
            ts_code=ts_code,
            direction=direction,
            price=price,
            volume=volume,
            strategy_name=strategy_name
        )

        self.orders[order.order_id] = order

        # 保存订单到数据库
        self._save_order(order)

        trader_logger.info(f"创建订单：{order.order_id} {ts_code} {direction} {volume}@{price}")

        return order

    def _save_order(self, order: Order):
        """保存订单到数据库"""
        self.db.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, ts_code, direction, price, volume, status, strategy_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            order.order_id,
            order.ts_code,
            order.direction,
            order.price,
            order.volume,
            order.status,
            order.strategy_name
        ))

    def submit_order(self, order_id: str) -> bool:
        """
        提交订单

        Args:
            order_id: 订单 ID

        Returns:
            是否成功
        """
        if order_id not in self.orders:
            trader_logger.warning(f"订单不存在：{order_id}")
            return False

        order = self.orders[order_id]

        if order.status != 'pending':
            trader_logger.warning(f"订单状态不正确：{order_id} {order.status}")
            return False

        # 更新订单状态
        order.status = 'submitted'
        order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 冻结资金
        if order.direction == 'buy':
            required_amount = order.price * order.volume * 1.001
            self.account.available_cash -= required_amount
            self.account.frozen_cash += required_amount

        self._save_order(order)
        self._save_account()

        trader_logger.info(f"提交订单：{order_id}")

        return True

    def fill_order(
        self,
        order_id: str,
        filled_price: float,
        filled_volume: int
    ) -> bool:
        """
        成交订单

        Args:
            order_id: 订单 ID
            filled_price: 成交价格
            filled_volume: 成交数量

        Returns:
            是否成功
        """
        if order_id not in self.orders:
            trader_logger.warning(f"订单不存在：{order_id}")
            return False

        order = self.orders[order_id]

        # 计算手续费
        amount = filled_price * filled_volume
        commission = max(5, amount * settings.COMMISSION_RATE)
        stamp_tax = amount * settings.STAMP_TAX_RATE if order.direction == 'sell' else 0

        order.filled_price = filled_price
        order.filled_volume = filled_volume
        order.commission = commission
        order.stamp_tax = stamp_tax
        order.status = 'filled'
        order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新持仓
        ts_code = order.ts_code

        if order.direction == 'buy':
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                old_value = pos.avg_cost * pos.volume
                new_value = filled_price * filled_volume
                pos.volume += filled_volume
                pos.avg_cost = (old_value + new_value) / pos.volume if pos.volume > 0 else filled_price
            else:
                self.positions[ts_code] = Position(
                    ts_code=ts_code,
                    volume=filled_volume,
                    avg_cost=filled_price
                )

            # 扣除资金
            self.account.frozen_cash -= (amount + commission)
            self.account.total_asset -= (amount + commission)

        else:  # sell
            if ts_code in self.positions:
                pos = self.positions[ts_code]
                sell_volume = min(filled_volume, pos.volume)
                pos.volume -= sell_volume

                if pos.volume <= 0:
                    del self.positions[ts_code]
                    self._delete_position(ts_code)
                else:
                    self._save_position(pos)

            # 增加资金
            self.account.frozen_cash += (amount - commission - stamp_tax)
            self.account.total_asset += (amount - commission - stamp_tax)

        # 保存
        self._save_order(order)
        self._save_account()
        if ts_code in self.positions:
            self._save_position(self.positions[ts_code])

        trader_logger.info(
            f"订单成交：{order_id} {ts_code} {order.direction} "
            f"{filled_volume}@{filled_price:.2f}"
        )

        return True

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单 ID

        Returns:
            是否成功
        """
        if order_id not in self.orders:
            trader_logger.warning(f"订单不存在：{order_id}")
            return False

        order = self.orders[order_id]

        if order.status not in ['pending', 'submitted']:
            trader_logger.warning(f"订单不能取消：{order_id} {order.status}")
            return False

        order.status = 'cancelled'
        order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 解冻资金
        if order.direction == 'buy' and order.status == 'submitted':
            required_amount = order.price * order.volume * 1.001
            self.account.frozen_cash -= required_amount
            self.account.available_cash += required_amount

        self._save_order(order)
        self._save_account()

        trader_logger.info(f"取消订单：{order_id}")

        return True

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.orders.get(order_id)

    def get_orders_by_status(self, status: str) -> List[Order]:
        """根据状态获取订单"""
        return [o for o in self.orders.values() if o.status == status]

    def get_position(self, ts_code: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(ts_code)

    def get_all_positions(self) -> Dict[str, Position]:
        """获取所有持仓"""
        return self.positions

    def update_position_price(self, ts_code: str, current_price: float):
        """
        更新持仓价格

        Args:
            ts_code: 股票代码
            current_price: 当前价格
        """
        if ts_code in self.positions:
            self.positions[ts_code].update_price(current_price)

    def refresh_account(self):
        """刷新账户信息"""
        # 计算持仓市值
        position_value = sum(pos.market_value for pos in self.positions.values())
        self.account.update_position_value(position_value)
        self._save_account()

    def get_account_summary(self) -> Dict:
        """
        获取账户摘要

        Returns:
            账户信息字典
        """
        self.refresh_account()

        return {
            'account_name': self.account.account_name,
            'total_asset': self.account.total_asset,
            'available_cash': self.account.available_cash,
            'frozen_cash': self.account.frozen_cash,
            'position_value': self.account.total_position_value,
            'position_count': len(self.positions),
            'pending_orders': len(self.get_orders_by_status('pending')),
            'submitted_orders': len(self.get_orders_by_status('submitted'))
        }


# 创建订单管理器实例
order_manager = OrderManager()
