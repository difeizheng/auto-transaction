"""
实时监控模块
用于实盘交易时的实时监控和异常检测
"""
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from config.logging_config import trader_logger
import config.settings as settings


class MarketState(Enum):
    """市场状态"""
    PRE_MARKET = "盘前"
    MORNING_TRADING = "交易中（上午）"
    LUNCH_BREAK = "午休"
    AFTERNOON_TRADING = "交易中（下午）"
    CLOSED = "收盘后"
    WEEKEND = "休市（周末）"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MarketAlert:
    """市场告警数据类"""
    alert_type: str
    level: AlertLevel
    message: str
    ts_code: Optional[str] = None
    current_price: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


@dataclass
class MonitoringConfig:
    """监控配置"""
    # 价格波动阈值
    price_change_threshold: float = 0.05  # 5% 价格变动告警
    rapid_change_threshold: float = 0.02  # 2% 快速变动告警（1 分钟内）

    # 数据延迟阈值
    data_delay_threshold: int = 60  # 数据延迟超过 60 秒告警

    # 网络异常
    network_error_threshold: int = 3  # 连续 3 次网络错误告警

    # 账户异常
    account_loss_threshold: float = 0.05  # 账户单日亏损 5% 告警

    # 监控间隔
    monitor_interval: int = 10  # 监控间隔（秒）


class RealtimeMonitor:
    """实时监控器"""

    def __init__(self, config: Optional[MonitoringConfig] = None):
        """
        初始化实时监控器

        Args:
            config: 监控配置
        """
        self.config = config or MonitoringConfig()
        self.running = False
        self._monitor_thread: Optional[threading.Thread] = None

        # 告警回调函数列表
        self._alert_callbacks: List[Callable[[MarketAlert], None]] = []

        # 状态记录
        self._last_data_time: Dict[str, datetime] = {}  # 每只股票最后数据时间
        self._last_prices: Dict[str, float] = {}  # 上次价格
        self._price_change_time: Dict[str, datetime] = {}  # 价格变动时间
        self._network_errors = 0
        self._last_network_error_time: Optional[datetime] = None

        # 告警历史
        self._alert_history: List[MarketAlert] = []
        self._alert_cooldown: Dict[str, datetime] = {}  # 告警冷却时间

        # 市场状态
        self._current_market_state: MarketState = MarketState.CLOSED

    def add_alert_callback(self, callback: Callable[[MarketAlert], None]):
        """
        添加告警回调函数

        Args:
            callback: 回调函数，接收 MarketAlert 参数
        """
        self._alert_callbacks.append(callback)

    def remove_alert_callback(self, callback: Callable[[MarketAlert], None]):
        """移除告警回调函数"""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)

    def _trigger_alert(self, alert: MarketAlert):
        """触发告警"""
        # 检查冷却时间
        cooldown_key = f"{alert.alert_type}_{alert.ts_code}"
        now = datetime.now()

        if cooldown_key in self._alert_cooldown:
            last_alert_time = self._alert_cooldown[cooldown_key]
            if (now - last_alert_time).total_seconds() < 60:  # 1 分钟冷却
                return

        self._alert_cooldown[cooldown_key] = now

        # 记录告警
        self._alert_history.append(alert)
        trader_logger.warning(
            f"[告警] {alert.level.value}: {alert.message}"
        )

        # 调用回调
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                trader_logger.error(f"告警回调异常：{e}")

        # 发送钉钉通知
        self._send_dingtalk_alert(alert)

    def _send_dingtalk_alert(self, alert: MarketAlert):
        """发送钉钉告警通知"""
        if not settings.ENABLE_DINGDING_NOTIFY or not settings.DINGDING_WEBHOOK:
            return

        try:
            from src.utils.dingtalk_notifier import DingTalkNotifier

            notifier = DingTalkNotifier()

            level_icon = {
                AlertLevel.INFO: "📢",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.ERROR: "❌",
                AlertLevel.CRITICAL: "🚨"
            }

            icon = level_icon.get(alert.level, "📢")
            msg = f"{icon} [{alert.alert_type}]\n{alert.message}"

            if alert.ts_code:
                msg += f"\n股票代码：{alert.ts_code}"
            if alert.current_price:
                msg += f"\n当前价格：{alert.current_price:.2f}"

            notifier.send_text(msg)

        except Exception as e:
            trader_logger.error(f"发送钉钉告警失败：{e}")

    def check_price_change(
        self,
        ts_code: str,
        current_price: float,
        prev_price: Optional[float] = None
    ) -> bool:
        """
        检查价格变动

        Args:
            ts_code: 股票代码
            current_price: 当前价格
            prev_price: 上次价格（None 则使用记录的上次价格）

        Returns:
            是否触发告警
        """
        if prev_price is None:
            prev_price = self._last_prices.get(ts_code)

        if prev_price is None or prev_price <= 0:
            self._last_prices[ts_code] = current_price
            return False

        # 计算价格变动
        price_change = (current_price - prev_price) / prev_price

        # 检查是否超过阈值
        if abs(price_change) >= self.config.price_change_threshold:
            alert = MarketAlert(
                alert_type="价格大幅波动",
                level=AlertLevel.WARNING,
                message=f"{ts_code} 价格变动 {price_change*100:.2f}% (阈值：{self.config.price_change_threshold*100}%)",
                ts_code=ts_code,
                current_price=current_price,
                threshold=self.config.price_change_threshold
            )
            self._trigger_alert(alert)
            self._price_change_time[ts_code] = datetime.now()
            self._last_prices[ts_code] = current_price
            return True

        # 检查快速变动（1 分钟内）
        if ts_code in self._price_change_time:
            time_since_change = (
                datetime.now() - self._price_change_time[ts_code]
            ).total_seconds()

            if time_since_change < 60 and abs(price_change) >= self.config.rapid_change_threshold:
                alert = MarketAlert(
                    alert_type="价格快速变动",
                    level=AlertLevel.WARNING,
                    message=f"{ts_code} 1 分钟内快速变动 {price_change*100:.2f}%",
                    ts_code=ts_code,
                    current_price=current_price,
                    threshold=self.config.rapid_change_threshold
                )
                self._trigger_alert(alert)

        self._last_prices[ts_code] = current_price
        return False

    def check_data_freshness(
        self,
        ts_code: str,
        update_time: Optional[datetime] = None
    ) -> bool:
        """
        检查数据新鲜度

        Args:
            ts_code: 股票代码
            update_time: 数据更新时间（None 则使用记录的时间）

        Returns:
            是否触发告警
        """
        if update_time is None:
            update_time = self._last_data_time.get(ts_code)

        if update_time is None:
            return False

        delay_seconds = (datetime.now() - update_time).total_seconds()

        if delay_seconds > self.config.data_delay_threshold:
            alert = MarketAlert(
                alert_type="数据延迟",
                level=AlertLevel.WARNING,
                message=f"{ts_code} 数据延迟 {delay_seconds:.0f} 秒",
                ts_code=ts_code,
                threshold=self.config.data_delay_threshold
            )
            self._trigger_alert(alert)
            return True

        return False

    def record_network_error(self):
        """记录网络错误"""
        now = datetime.now()

        # 检查是否是连续错误
        if self._last_network_error_time:
            time_diff = (now - self._last_network_error_time).total_seconds()
            if time_diff < 30:  # 30 秒内
                self._network_errors += 1
            else:
                self._network_errors = 1
        else:
            self._network_errors = 1

        self._last_network_error_time = now

        # 检查是否超过阈值
        if self._network_errors >= self.config.network_error_threshold:
            alert = MarketAlert(
                alert_type="网络异常",
                level=AlertLevel.ERROR,
                message=f"连续 {self._network_errors} 次网络错误",
                threshold=self.config.network_error_threshold
            )
            self._trigger_alert(alert)
            self._network_errors = 0  # 重置

    def reset_network_errors(self):
        """重置网络错误计数"""
        self._network_errors = 0

    def check_account_loss(
        self,
        current_asset: float,
        initial_asset: float,
        peak_asset: float
    ) -> bool:
        """
        检查账户亏损

        Args:
            current_asset: 当前总资产
            initial_asset: 初始总资产
            peak_asset: 峰值总资产

        Returns:
            是否触发告警
        """
        if initial_asset <= 0:
            return False

        # 计算单日亏损（相对于初始）
        daily_loss = (initial_asset - current_asset) / initial_asset

        # 计算回撤（相对于峰值）
        drawdown = (peak_asset - current_asset) / peak_asset if peak_asset > 0 else 0

        triggered = False

        if daily_loss >= self.config.account_loss_threshold:
            alert = MarketAlert(
                alert_type="账户亏损告警",
                level=AlertLevel.WARNING,
                message=f"单日亏损 {daily_loss*100:.2f}% (阈值：{self.config.account_loss_threshold*100}%)",
                current_price=current_asset,
                threshold=self.config.account_loss_threshold
            )
            self._trigger_alert(alert)
            triggered = True

        if drawdown >= 0.10:  # 10% 回撤告警
            alert = MarketAlert(
                alert_type="回撤告警",
                level=AlertLevel.WARNING,
                message=f"当前回撤 {drawdown*100:.2f}%",
                current_price=current_asset,
                threshold=0.10
            )
            self._trigger_alert(alert)
            triggered = True

        return triggered

    def get_market_state(self) -> MarketState:
        """
        获取当前市场状态

        Returns:
            市场状态
        """
        now = datetime.now()

        # 周末休市
        if now.weekday() >= 5:
            return MarketState.WEEKEND

        current_time = now.time()
        from datetime import time as dt_time

        if current_time < dt_time(9, 30):
            return MarketState.PRE_MARKET
        elif current_time < dt_time(11, 30):
            return MarketState.MORNING_TRADING
        elif current_time < dt_time(13, 0):
            return MarketState.LUNCH_BREAK
        elif current_time < dt_time(15, 0):
            return MarketState.AFTERNOON_TRADING
        else:
            return MarketState.CLOSED

    def is_trading_time(self) -> bool:
        """是否在交易时间"""
        state = self.get_market_state()
        return state in [MarketState.MORNING_TRADING, MarketState.AFTERNOON_TRADING]

    def update_stock_data(self, ts_code: str, price: float):
        """
        更新股票数据（外部调用）

        Args:
            ts_code: 股票代码
            price: 当前价格
        """
        now = datetime.now()
        self._last_data_time[ts_code] = now
        self.check_price_change(ts_code, price)

    def get_alert_history(
        self,
        limit: int = 50,
        alert_type: Optional[str] = None
    ) -> List[MarketAlert]:
        """
        获取告警历史

        Args:
            limit: 返回数量限制
            alert_type: 告警类型筛选

        Returns:
            告警列表
        """
        alerts = self._alert_history

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        # 按时间倒序
        alerts = sorted(alerts, key=lambda x: x.timestamp, reverse=True)

        return alerts[:limit]

    def start_monitoring(self, interval: Optional[int] = None):
        """
        启动监控（后台线程）

        Args:
            interval: 监控间隔（秒），None 使用配置值
        """
        if self.running:
            return

        self.running = True
        interval = interval or self.config.monitor_interval

        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()

        trader_logger.info(f"实时监控已启动，间隔：{interval}秒")

    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        trader_logger.info("实时监控已停止")

    def _monitoring_loop(self, interval: int):
        """监控循环"""
        while self.running:
            try:
                # 检查数据新鲜度
                now = datetime.now()
                for ts_code, last_time in list(self._last_data_time.items()):
                    self.check_data_freshness(ts_code, last_time)

                    # 清理过时记录（超过 1 小时）
                    if (now - last_time).total_seconds() > 3600:
                        del self._last_data_time[ts_code]

                # 更新市场状态
                self._current_market_state = self.get_market_state()

                time.sleep(interval)

            except Exception as e:
                trader_logger.error(f"监控循环异常：{e}")
                time.sleep(interval)

    def get_status(self) -> Dict:
        """获取监控状态"""
        return {
            'running': self.running,
            'market_state': self._current_market_state.value,
            'is_trading_time': self.is_trading_time(),
            'tracked_stocks': len(self._last_data_time),
            'network_errors': self._network_errors,
            'alert_count': len(self._alert_history),
            'last_alert': self._alert_history[-1].to_dict() if self._alert_history else None
        }


# 创建全局监控实例
global_monitor = RealtimeMonitor()


if __name__ == "__main__":
    # 测试代码
    print("测试实时监控模块...")

    monitor = RealtimeMonitor()

    # 测试市场状态
    print(f"\n当前市场状态：{monitor.get_market_state().value}")
    print(f"是否交易时间：{monitor.is_trading_time()}")

    # 测试价格变动检测
    def on_alert(alert: MarketAlert):
        print(f"\n[告警回调] {alert.level.value}: {alert.message}")

    monitor.add_alert_callback(on_alert)

    # 模拟价格大幅变动
    print("\n模拟价格大幅变动测试:")
    monitor.check_price_change("000001.SZ", 10.0)
    monitor.check_price_change("000001.SZ", 10.6)  # 上涨 6%，触发告警

    # 获取告警历史
    print(f"\n告警历史：{len(monitor._alert_history)} 条")
    for alert in monitor._alert_history:
        print(f"  - {alert.timestamp}: {alert.message}")

    # 获取状态
    print(f"\n监控状态：{monitor.get_status()}")
