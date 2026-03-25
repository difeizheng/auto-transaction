"""
紧急处理模块
实盘交易时的紧急止损和熔断机制
"""
import threading
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from config.logging_config import trader_logger
import config.settings as settings


class EmergencyLevel(Enum):
    """紧急程度"""
    LOW = "low"           # 低 - 记录
    MEDIUM = "medium"     # 中 - 警告
    HIGH = "high"         # 高 - 部分止损
    CRITICAL = "critical" # 严重 - 全部清仓


class EmergencyType(Enum):
    """紧急事件类型"""
    LARGE_LOSS = "large_loss"              # 大额亏损
    NETWORK_FAILURE = "network_failure"    # 网络故障
    DATA_ANOMALY = "data_anomaly"          # 数据异常
    MARKET_CRASH = "market_crash"          # 市场暴跌
    SYSTEM_ERROR = "system_error"          # 系统错误
    MANUAL_TRIGGER = "manual_trigger"      # 手动触发
    POSITION_EXCEPTION = "position_exception"  # 持仓异常


@dataclass
class EmergencyEvent:
    """紧急事件数据类"""
    event_type: EmergencyType
    level: EmergencyLevel
    message: str
    details: Dict = field(default_factory=dict)
    timestamp: str = ""
    handled: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    # 亏损熔断
    single_stock_loss_threshold: float = 0.10  # 单只股票亏损 10% 触发
    portfolio_loss_threshold: float = 0.05     # 组合亏损 5% 触发
    daily_loss_threshold: float = 0.03         # 单日亏损 3% 触发

    # 市场熔断
    market_drop_threshold: float = 0.03        # 市场下跌 3% 触发

    # 时间相关
    cooldown_period: int = 300                 # 熔断后冷却期（秒）
    recovery_check_interval: int = 60          # 恢复检查间隔（秒）

    # 网络异常
    max_network_errors: int = 5                # 最大网络错误次数
    network_error_window: int = 60             # 网络错误时间窗口（秒）


class CircuitBreaker:
    """熔断器"""

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """
        初始化熔断器

        Args:
            config: 熔断器配置
        """
        self.config = config or CircuitBreakerConfig()
        self.is_triggered = False
        self.trigger_time: Optional[datetime] = None
        self.trigger_reason: str = ""
        self.trigger_level: EmergencyLevel = EmergencyLevel.LOW

        self._lock = threading.Lock()

    def trigger(self, reason: str, level: EmergencyLevel = EmergencyLevel.HIGH):
        """触发熔断"""
        with self._lock:
            self.is_triggered = True
            self.trigger_time = datetime.now()
            self.trigger_reason = reason
            self.trigger_level = level

            trader_logger.critical(
                f"[熔断触发] {level.value}: {reason}"
            )

            # 发送通知
            self._send_notification(reason, level)

    def reset(self):
        """重置熔断"""
        with self._lock:
            self.is_triggered = False
            self.trigger_time = None
            self.trigger_reason = ""
            trader_logger.info("[熔断重置] 交易恢复")

    def can_trade(self) -> bool:
        """是否可以交易"""
        if not self.is_triggered:
            return True

        # 检查冷却期是否结束
        if self.trigger_time:
            elapsed = (datetime.now() - self.trigger_time).total_seconds()
            if elapsed >= self.config.cooldown_period:
                self.reset()
                return True

        return False

    def _send_notification(self, reason: str, level: EmergencyLevel):
        """发送通知"""
        if not settings.ENABLE_DINGDING_NOTIFY or not settings.DINGDING_WEBHOOK:
            return

        try:
            from src.utils.dingtalk_notifier import DingTalkNotifier

            notifier = DingTalkNotifier()
            icon = "🚨" if level in [EmergencyLevel.HIGH, EmergencyLevel.CRITICAL] else "⚠️"
            msg = f"{icon} [熔断触发]\n级别：{level.value}\n原因：{reason}\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            notifier.send_text(msg)

        except Exception as e:
            trader_logger.error(f"发送熔断通知失败：{e}")


class EmergencyHandler:
    """紧急处理器"""

    def __init__(
        self,
        broker=None,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        初始化紧急处理器

        Args:
            broker: 券商实例（用于执行紧急卖出）
            config: 配置
        """
        self.broker = broker
        self.config = config or CircuitBreakerConfig()

        # 熔断器
        self.circuit_breaker = CircuitBreaker(self.config)

        # 事件记录
        self._events: List[EmergencyEvent] = []
        self._event_count: Dict[str, int] = {}  # 各类事件计数
        self._event_times: List[datetime] = []  # 事件时间（用于频率限制）

        # 紧急联系人回调
        self._emergency_callbacks: List[Callable[[EmergencyEvent], None]] = []

        # 持仓成本记录 {ts_code: {cost, peak, timestamp}}
        self._position_costs: Dict[str, Dict] = {}

        # 网络错误记录
        self._network_errors: List[datetime] = []

        # 市场指数缓存
        self._market_index: Dict[str, float] = {}
        self._market_index_time: Optional[datetime] = None

    def add_emergency_callback(self, callback: Callable[[EmergencyEvent], None]):
        """添加紧急事件回调"""
        self._emergency_callbacks.append(callback)

    def _trigger_emergency(
        self,
        event_type: EmergencyType,
        level: EmergencyLevel,
        message: str,
        details: Optional[Dict] = None
    ) -> EmergencyEvent:
        """触发紧急事件"""
        event = EmergencyEvent(
            event_type=event_type,
            level=level,
            message=message,
            details=details or {}
        )

        self._events.append(event)

        # 更新事件计数
        type_key = event_type.value
        self._event_count[type_key] = self._event_count.get(type_key, 0) + 1

        # 记录事件时间
        self._event_times.append(datetime.now())

        trader_logger.critical(
            f"[紧急事件] {level.value} - {event_type.value}: {message}"
        )

        # 触发熔断器
        if level in [EmergencyLevel.HIGH, EmergencyLevel.CRITICAL]:
            self.circuit_breaker.trigger(message, level)

        # 调用回调
        for callback in self._emergency_callbacks:
            try:
                callback(event)
            except Exception as e:
                trader_logger.error(f"紧急事件回调异常：{e}")

        # 发送通知
        self._send_notification(event)

        return event

    def _send_notification(self, event: EmergencyEvent):
        """发送紧急通知"""
        if not settings.ENABLE_DINGDING_NOTIFY or not settings.DINGDING_WEBHOOK:
            return

        try:
            from src.utils.dingtalk_notifier import DingTalkNotifier

            notifier = DingTalkNotifier()
            icon = "🚨" if event.level == EmergencyLevel.CRITICAL else "⚠️"

            msg = f"{icon} [{event.event_type.value}]\n"
            msg += f"级别：{event.level.value}\n"
            msg += f"原因：{event.message}\n"

            if event.details:
                for key, value in event.details.items():
                    msg += f"{key}: {value}\n"

            notifier.send_text(msg)

        except Exception as e:
            trader_logger.error(f"发送紧急通知失败：{e}")

    def check_position_loss(
        self,
        ts_code: str,
        current_price: float,
        position: Optional[Dict] = None
    ) -> bool:
        """
        检查持仓亏损

        Args:
            ts_code: 股票代码
            current_price: 当前价格
            position: 持仓信息

        Returns:
            是否触发紧急处理
        """
        if ts_code not in self._position_costs:
            self._position_costs[ts_code] = {
                'cost': position.get('avg_cost', current_price) if position else current_price,
                'peak': current_price,
                'timestamp': datetime.now()
            }

        cost_info = self._position_costs[ts_code]
        cost_price = cost_info['cost']

        # 更新最高价
        if current_price > cost_info['peak']:
            cost_info['peak'] = current_price

        # 计算亏损
        loss_ratio = (current_price - cost_price) / cost_price if cost_price > 0 else 0

        # 检查止损
        if loss_ratio <= -self.config.single_stock_loss_threshold:
            self._trigger_emergency(
                event_type=EmergencyType.LARGE_LOSS,
                level=EmergencyLevel.HIGH,
                message=f"{ts_code} 亏损 {loss_ratio*100:.2f}% (阈值：{self.config.single_stock_loss_threshold*100}%)",
                details={
                    'ts_code': ts_code,
                    'cost_price': cost_price,
                    'current_price': current_price,
                    'loss_ratio': loss_ratio
                }
            )

            # 执行紧急止损
            self._emergency_sell(ts_code, current_price, "止损")
            return True

        # 检查大幅回撤（从高点回撤）
        peak = cost_info['peak']
        drawdown = (peak - current_price) / peak if peak > 0 else 0

        if drawdown >= 0.08:  # 从高点回撤 8%
            self._trigger_emergency(
                event_type=EmergencyType.POSITION_EXCEPTION,
                level=EmergencyLevel.MEDIUM,
                message=f"{ts_code} 从高点回撤 {drawdown*100:.2f}%",
                details={
                    'ts_code': ts_code,
                    'peak_price': peak,
                    'current_price': current_price
                }
            )
            return True

        return False

    def check_portfolio_loss(
        self,
        current_asset: float,
        initial_asset: float
    ) -> bool:
        """
        检查组合亏损

        Args:
            current_asset: 当前总资产
            initial_asset: 初始总资产

        Returns:
            是否触发紧急处理
        """
        if initial_asset <= 0:
            return False

        loss_ratio = (initial_asset - current_asset) / initial_asset

        if loss_ratio >= self.config.portfolio_loss_threshold:
            self._trigger_emergency(
                event_type=EmergencyType.LARGE_LOSS,
                level=EmergencyLevel.CRITICAL,
                message=f"组合亏损 {loss_ratio*100:.2f}% (阈值：{self.config.portfolio_loss_threshold*100}%)",
                details={
                    'initial_asset': initial_asset,
                    'current_asset': current_asset,
                    'loss_ratio': loss_ratio
                }
            )

            # 执行全部清仓
            self._emergency_sell_all("组合止损")
            return True

        return False

    def check_daily_loss(
        self,
        current_asset: float,
        open_asset: float
    ) -> bool:
        """
        检查单日亏损

        Args:
            current_asset: 当前总资产
            open_asset: 开盘资产

        Returns:
            是否触发紧急处理
        """
        if open_asset <= 0:
            return False

        daily_loss = (open_asset - current_asset) / open_asset

        if daily_loss >= self.config.daily_loss_threshold:
            self._trigger_emergency(
                event_type=EmergencyType.LARGE_LOSS,
                level=EmergencyLevel.CRITICAL,
                message=f"单日亏损 {daily_loss*100:.2f}% (阈值：{self.config.daily_loss_threshold*100}%)",
                details={
                    'open_asset': open_asset,
                    'current_asset': current_asset
                }
            )

            # 执行全部清仓
            self._emergency_sell_all("单日亏损止损")
            return True

        return False

    def record_network_error(self):
        """记录网络错误"""
        now = datetime.now()
        self._network_errors.append(now)

        # 清理超过时间窗口的错误
        window_start = now - timedelta(seconds=self.config.network_error_window)
        self._network_errors = [t for t in self._network_errors if t > window_start]

        # 检查是否超过阈值
        if len(self._network_errors) >= self.config.max_network_errors:
            self._trigger_emergency(
                event_type=EmergencyType.NETWORK_FAILURE,
                level=EmergencyLevel.HIGH,
                message=f"短时间内 {len(self._network_errors)} 次网络错误",
                details={
                    'error_count': len(self._network_errors),
                    'time_window': self.config.network_error_window
                }
            )
            return True

        return False

    def check_market_crash(
        self,
        index_change: float,
        index_name: str = "上证指数"
    ) -> bool:
        """
        检查市场暴跌

        Args:
            index_change: 指数涨跌幅（小数）
            index_name: 指数名称

        Returns:
            是否触发紧急处理
        """
        if index_change <= -self.config.market_drop_threshold:
            self._trigger_emergency(
                event_type=EmergencyType.MARKET_CRASH,
                level=EmergencyLevel.HIGH,
                message=f"{index_name} 暴跌 {index_change*100:.2f}%",
                details={
                    'index_name': index_name,
                    'index_change': index_change
                }
            )
            return True

        return False

    def _emergency_sell(
        self,
        ts_code: str,
        current_price: float,
        reason: str,
        volume: Optional[int] = None
    ):
        """
        紧急卖出

        Args:
            ts_code: 股票代码
            current_price: 当前价格
            reason: 卖出原因
            volume: 卖出数量（None 表示全部）
        """
        if not self.broker:
            trader_logger.warning("券商未连接，无法执行紧急卖出")
            return

        trader_logger.critical(
            f"[紧急卖出] {ts_code}, 原因：{reason}"
        )

        try:
            # 获取持仓
            positions = self.broker.get_positions()
            position = next(
                (p for p in positions if p['ts_code'] == ts_code),
                None
            )

            if not position:
                return

            sell_volume = volume or position['volume']

            # 提交卖出订单
            order_id = self.broker.submit_order(
                ts_code=ts_code,
                direction='sell',
                price=current_price,
                volume=sell_volume,
                strategy_name=f"紧急止损-{reason}"
            )

            if order_id:
                trader_logger.info(f"紧急卖出订单已提交：{order_id}")
            else:
                trader_logger.error("紧急卖出订单提交失败")

        except Exception as e:
            trader_logger.error(f"紧急卖出执行异常：{e}")

    def _emergency_sell_all(self, reason: str):
        """全部清仓"""
        if not self.broker:
            trader_logger.warning("券商未连接，无法执行清仓")
            return

        trader_logger.critical(f"[全部清仓] 原因：{reason}")

        try:
            positions = self.broker.get_positions()

            for position in positions:
                ts_code = position['ts_code']
                volume = position['volume']
                price = position['current_price']

                self._emergency_sell(ts_code, price, reason, volume)

        except Exception as e:
            trader_logger.error(f"全部清仓执行异常：{e}")

    def manual_trigger(self, reason: str, level: EmergencyLevel = EmergencyLevel.CRITICAL):
        """
        手动触发紧急处理

        Args:
            reason: 原因
            level: 紧急程度
        """
        self._trigger_emergency(
            event_type=EmergencyType.MANUAL_TRIGGER,
            level=level,
            message=f"手动触发：{reason}",
            details={'operator': 'manual'}
        )

    def resume_trading(self):
        """恢复交易"""
        self.circuit_breaker.reset()
        trader_logger.info("交易已恢复")

    def can_trade(self) -> bool:
        """是否可以交易"""
        return self.circuit_breaker.can_trade()

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            'circuit_breaker': {
                'is_triggered': self.circuit_breaker.is_triggered,
                'trigger_time': self.circuit_breaker.trigger_time.strftime('%Y-%m-%d %H:%M:%S') if self.circuit_breaker.trigger_time else None,
                'trigger_reason': self.circuit_breaker.trigger_reason
            },
            'event_counts': self._event_count,
            'total_events': len(self._events),
            'network_errors': len(self._network_errors),
            'can_trade': self.can_trade()
        }

    def get_events(self, limit: int = 20) -> List[EmergencyEvent]:
        """获取事件历史"""
        return self._events[-limit:]


# 创建全局实例
global_emergency_handler = EmergencyHandler()


if __name__ == "__main__":
    # 测试代码
    print("测试紧急处理模块...")

    handler = EmergencyHandler()

    # 测试熔断器
    print("\n测试熔断器:")
    print(f"初始状态 - 可以交易：{handler.can_trade()}")

    # 触发熔断
    handler.circuit_breaker.trigger("测试熔断", EmergencyLevel.HIGH)
    print(f"触发后 - 可以交易：{handler.can_trade()}")

    # 重置
    handler.circuit_breaker.reset()
    print(f"重置后 - 可以交易：{handler.can_trade()}")

    # 测试事件记录
    print("\n触发测试事件:")
    handler._trigger_emergency(
        EmergencyType.LARGE_LOSS,
        EmergencyLevel.HIGH,
        "测试亏损事件",
        {'test': True}
    )

    print(f"\n事件历史：{len(handler._events)} 条")
    print(f"事件计数：{handler._event_count}")
    print(f"状态：{handler.get_status()}")
