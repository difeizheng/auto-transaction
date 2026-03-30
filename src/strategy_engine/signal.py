"""
信号数据模型
定义交易信号的数据结构
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class SignalStatus(Enum):
    """信号状态"""
    PENDING = "pending"      # 待执行
    EXECUTED = "executed"    # 已执行
    EXPIRED = "expired"      # 已过期（未执行）
    CANCELLED = "cancelled"  # 已取消


class SignalDirection(Enum):
    """信号方向"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradingSignal:
    """交易信号数据类"""
    ts_code: str                    # 股票代码
    direction: str                  # buy/sell/hold
    signal_date: str                 # 信号生成日期 (YYYYMMDD)
    execute_date: str               # 计划执行日期 (YYYYMMDD)
    target_price: float             # 参考价格
    volume: int = 100               # 交易数量（默认100股）
    confidence: float = 1.0         # 置信度 0~1
    strategy_name: str = ""         # 策略名称
    reason: str = ""                # 信号原因描述
    status: str = "pending"         # 信号状态
    executed_price: float = 0.0     # 实际成交价格
    executed_time: str = ""         # 实际成交时间
    order_id: str = ""              # 订单ID

    def __post_init__(self):
        if not self.signal_date:
            self.signal_date = datetime.now().strftime('%Y%m%d')
        if not self.execute_date:
            # 默认 T+1 执行
            self.execute_date = self.signal_date

    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'direction': self.direction,
            'signal_date': self.signal_date,
            'execute_date': self.execute_date,
            'target_price': self.target_price,
            'volume': self.volume,
            'confidence': self.confidence,
            'strategy_name': self.strategy_name,
            'reason': self.reason,
            'status': self.status,
            'executed_price': self.executed_price,
            'executed_time': self.executed_time,
            'order_id': self.order_id
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(
            ts_code=data.get('ts_code', ''),
            direction=data.get('direction', 'hold'),
            signal_date=data.get('signal_date', ''),
            execute_date=data.get('execute_date', ''),
            target_price=data.get('target_price', 0),
            volume=data.get('volume', 100),
            confidence=data.get('confidence', 1.0),
            strategy_name=data.get('strategy_name', ''),
            reason=data.get('reason', ''),
            status=data.get('status', 'pending'),
            executed_price=data.get('executed_price', 0),
            executed_time=data.get('executed_time', ''),
            order_id=data.get('order_id', '')
        )


# 信号状态常量
SIGNAL_STATUS_PENDING = "pending"
SIGNAL_STATUS_EXECUTED = "executed"
SIGNAL_STATUS_EXPIRED = "expired"
SIGNAL_STATUS_CANCELLED = "cancelled"

# 信号方向常量
SIGNAL_DIRECTION_BUY = "buy"
SIGNAL_DIRECTION_SELL = "sell"
SIGNAL_DIRECTION_HOLD = "hold"