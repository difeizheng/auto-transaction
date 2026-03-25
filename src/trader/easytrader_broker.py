"""
easytrader 券商接口封装
用于对接国内券商进行实盘交易
GitHub: https://github.com/shidenggui/easytrader

支持的券商：
- 华泰证券 (htzq)
- 银河证券 (yh_client)
- 国金证券 (gj_client)
- 中金财富 (cicc)
- 其他 easytrader 支持的券商

注意：使用前需要安装 easytrader
pip install easytrader
"""
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

try:
    import easytrader
    EASYTRADER_AVAILABLE = True
except ImportError:
    EASYTRADER_AVAILABLE = False
    print("警告：easytrader 未安装，请运行：pip install easytrader")

import config.settings as settings
from config.logging_config import trader_logger
from src.trader.broker_api import BaseBroker
from src.trader.order_manager import Order, Position
from src.trader.risk_control import RiskController


class EasyTraderBroker(BaseBroker):
    """
    easytrader 封装的实盘交易券商

    支持多种券商客户端接入
    """

    # 券商类型映射
    BROKER_TYPES = {
        'huatai': 'htzq',      # 华泰证券
        'yinhai': 'yh_client', # 银河证券
        'guojin': 'gj_client', # 国金证券
        'cicc': 'cicc',        # 中金财富
        'zhongtaixtp': 'xtp',  # 中泰 XTP
    }

    def __init__(
        self,
        broker_type: str,
        config_path: Optional[str] = None,
        exe_path: Optional[str] = None,
        **kwargs
    ):
        """
        初始化 easytrader 券商

        Args:
            broker_type: 券商类型 (huatai/yinhai/guojin/cicc 等)
            config_path: 配置文件路径 (JSON 格式，包含账号密码等)
            exe_path: 券商客户端 exe 路径（某些券商需要）
            **kwargs: 其他参数
        """
        if not EASYTRADER_AVAILABLE:
            raise ImportError("easytrader 未安装")

        self.broker_type = broker_type
        self.config_path = config_path
        self.exe_path = exe_path
        self.kwargs = kwargs

        self.user = None
        self.connected = False
        self.risk_controller = RiskController()

        # 订单状态缓存
        self._order_cache: Dict[str, Dict] = {}
        self._last_refresh_time = 0
        self._refresh_interval = 5  # 订单刷新间隔（秒）

    def connect(self) -> bool:
        """
        连接券商

        Returns:
            是否连接成功
        """
        try:
            # 获取券商类型
            broker_key = self.BROKER_TYPES.get(
                self.broker_type.lower(),
                self.broker_type.lower()
            )

            trader_logger.info(f"正在连接 {self.broker_type} 券商...")

            # 创建 user 对象
            self.user = easytrader.use(broker_key)

            # 加载配置文件
            if self.config_path:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # 准备登录参数
                login_params = self._prepare_login_params(config)

                # 连接（某些券商需要准备客户端）
                if self.exe_path and hasattr(self.user, 'prepare'):
                    self.user.prepare(self.exe_path, **login_params)
                elif hasattr(self.user, 'connect'):
                    # 某些券商使用 connect 方法
                    self.user.connect(**login_params)
                else:
                    # 通用登录
                    self.user.login(**login_params)

            # 测试连接
            if self.user and self._test_connection():
                self.connected = True
                trader_logger.info(f"{self.broker_type} 连接成功")
                return True
            else:
                trader_logger.warning(f"{self.broker_type} 连接测试失败")
                return False

        except Exception as e:
            trader_logger.error(f"连接券商失败：{e}")
            return False

    def _prepare_login_params(self, config: Dict) -> Dict:
        """
        准备登录参数

        Args:
            config: 配置字典

        Returns:
            登录参数字典
        """
        params = {}

        # 通用参数映射
        param_mapping = {
            'user': config.get('user', config.get('username')),
            'password': config.get('password'),
            'comm_password': config.get('comm_password', config.get('transaction_password')),
            'exchange_password': config.get('exchange_password'),
            'verify_code': config.get('verify_code'),
        }

        # 过滤空值
        for key, value in param_mapping.items():
            if value is not None:
                params[key] = value

        # 添加额外参数
        params.update(self.kwargs)

        return params

    def _test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            # 尝试获取账户信息
            info = self.user.balance
            return info is not None and len(info) > 0
        except Exception:
            return False

    def disconnect(self):
        """断开连接"""
        try:
            if self.user and hasattr(self.user, 'logout'):
                self.user.logout()
        except Exception as e:
            trader_logger.warning(f"断开连接异常：{e}")
        finally:
            self.connected = False
            trader_logger.info("已断开与券商的连接")

    def is_connected(self) -> bool:
        """是否已连接"""
        return self.connected

    def get_account_info(self) -> Dict:
        """
        获取账户信息

        Returns:
            账户信息字典
        """
        if not self.connected:
            return {}

        try:
            balance = self.user.balance
            if not balance or len(balance) == 0:
                return {}

            # easytrader 返回的是列表，取第一个
            acc = balance[0] if isinstance(balance, list) else balance

            return {
                'account_name': self.broker_type,
                'total_asset': float(acc.get('资产', 0)),
                'available_cash': float(acc.get('可用金额', 0)),
                'frozen_cash': float(acc.get('冻结资金', 0)),
                'total_position_value': float(acc.get('持仓市值', 0)),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            trader_logger.error(f"获取账户信息失败：{e}")
            return {}

    def get_positions(self) -> List[Dict]:
        """
        获取持仓

        Returns:
            持仓列表
        """
        if not self.connected:
            return []

        try:
            positions = self.user.position
            if not positions:
                return []

            result = []
            for pos in positions:
                # 转换字段名
                ts_code = self._format_stock_code(pos.get('证券代码', ''))
                result.append({
                    'ts_code': ts_code,
                    'name': pos.get('证券名称', ''),
                    'volume': int(pos.get('股票余额', 0) or pos.get('当前持仓', 0)),
                    'available_volume': int(pos.get('可卖数量', 0)),
                    'avg_cost': float(pos.get('成本价', 0)),
                    'current_price': float(pos.get('最新价', 0)),
                    'market_value': float(pos.get('市值', 0)),
                    'profit_loss': float(pos.get('盈亏', 0)),
                    'profit_ratio': float(pos.get('盈亏比例 (%)', 0) or 0) / 100,
                })

            return result
        except Exception as e:
            trader_logger.error(f"获取持仓失败：{e}")
            return []

    def get_orders(self, status: Optional[str] = None) -> List[Dict]:
        """
        获取订单

        Args:
            status: 订单状态筛选（None 表示全部）

        Returns:
            订单列表
        """
        if not self.connected:
            return []

        try:
            # 刷新订单缓存
            self._refresh_orders()

            orders = []
            for order_id, order in self._order_cache.items():
                if status and order.get('status') != status:
                    continue
                orders.append(order)

            return orders
        except Exception as e:
            trader_logger.error(f"获取订单失败：{e}")
            return []

    def _refresh_orders(self):
        """刷新订单缓存"""
        current_time = time.time()
        if current_time - self._last_refresh_time < self._refresh_interval:
            return

        try:
            raw_orders = self.user.entrust
            if not raw_orders:
                return

            self._order_cache = {}
            for order in raw_orders:
                order_id = str(order.get('委托编号', order.get('订单编号', '')))
                ts_code = self._format_stock_code(order.get('证券代码', ''))

                # 映射状态
                raw_status = str(order.get('委托状态', ''))
                status = self._map_order_status(raw_status)

                self._order_cache[order_id] = {
                    'order_id': order_id,
                    'ts_code': ts_code,
                    'direction': 'buy' if order.get('委托类型', '') == '证券买入' else 'sell',
                    'price': float(order.get('委托价格', 0)),
                    'volume': int(order.get('委托数量', 0)),
                    'filled_volume': int(order.get('成交数量', 0)),
                    'status': status,
                    'created_at': order.get('委托时间', ''),
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

            self._last_refresh_time = current_time
        except Exception as e:
            trader_logger.warning(f"刷新订单失败：{e}")

    def _map_order_status(self, raw_status: str) -> str:
        """
        映射订单状态

        Args:
            raw_status: 原始状态字符串

        Returns:
            标准状态字符串
        """
        raw_status = str(raw_status).lower()

        if '已成' in raw_status or '成交' in raw_status:
            return 'filled'
        elif '已报' in raw_status or '正报' in raw_status:
            return 'submitted'
        elif '撤消' in raw_status or '已撤' in raw_status:
            return 'cancelled'
        elif '拒单' in raw_status or '废单' in raw_status:
            return 'rejected'
        elif '部分' in raw_status:
            return 'partially_filled'
        else:
            return 'pending'

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
            ts_code: 股票代码（Tushare 格式）
            direction: 买卖方向 (buy/sell)
            price: 价格
            volume: 数量
            strategy_name: 策略名称

        Returns:
            订单 ID，失败返回 None
        """
        if not self.connected:
            trader_logger.warning("券商未连接")
            return None

        # 风控检查
        positions = {
            pos['ts_code']: {
                'market_value': pos['market_value'],
                'volume': pos['volume'],
                'avg_cost': pos['avg_cost']
            }
            for pos in self.get_positions()
        }

        account_info = self.get_account_info()
        current_capital = account_info.get('total_asset', 0)

        passed, reason = self.risk_controller.check_order(
            ts_code, direction, price, volume, current_capital, positions
        )

        if not passed:
            trader_logger.warning(f"订单未通过风控检查：{reason}")
            return None

        try:
            # 转换股票代码格式
            stock_code = self._to_trader_code(ts_code)

            # 执行买卖
            if direction == 'buy':
                result = self.user.buy(stock_code, price=price, amount=volume)
            else:
                result = self.user.sell(stock_code, price=price, amount=volume)

            # 检查返回结果
            if not result:
                trader_logger.error("订单提交失败：返回为空")
                return None

            # easytrader 返回格式可能不同
            if isinstance(result, dict):
                if result.get('error'):
                    trader_logger.error(f"订单提交失败：{result.get('error_msg', result)}")
                    return None
                order_id = str(result.get('order_id', result.get('委托编号', '')))
            elif isinstance(result, bool):
                # 返回布尔值，需要查询订单
                order_id = self._get_last_order_id()
            else:
                order_id = str(result)

            if not order_id:
                trader_logger.warning("未能获取订单 ID")
                return None

            trader_logger.info(
                f"[实盘下单] {ts_code} {direction} "
                f"{volume}@{price:.2f}, 订单 ID: {order_id}"
            )

            # 发送钉钉通知
            self._send_order_notification(ts_code, direction, price, volume, order_id, strategy_name)

            return order_id

        except Exception as e:
            trader_logger.error(f"提交订单异常：{e}")
            return None

    def _to_trader_code(self, ts_code: str) -> str:
        """
        转换股票代码为交易代码格式

        Tushare: 000001.SZ -> 深市：sz000001 / 沪市：sh600000
        easytrader 通常需要：sz000001 或 sh600000 格式
        """
        parts = ts_code.upper().split('.')
        if len(parts) != 2:
            return ts_code

        code, exchange = parts
        exchange_map = {
            'SZ': 'sz',
            'SH': 'sh',
            'BJ': 'bj'
        }
        prefix = exchange_map.get(exchange, 'sh')
        return f"{prefix}{code}"

    def _format_stock_code(self, code: str) -> str:
        """
        格式化股票代码为 Tushare 格式

        easytrader 返回：000001 -> Tushare: 000001.SZ
        """
        code = str(code).strip()
        if not code:
            return ""

        # 如果已经包含交易所后缀，直接返回
        if '.' in code:
            return code.upper()

        # 根据代码前缀判断交易所
        if code.startswith(('6', '9')):
            return f"{code}.SH"
        elif code.startswith(('0', '2', '3')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"
        else:
            return code

    def _get_last_order_id(self) -> Optional[str]:
        """获取最后一个订单的 ID"""
        try:
            self._refresh_orders()
            if self._order_cache:
                # 返回最新的订单 ID
                return list(self._order_cache.keys())[-1]
        except Exception:
            pass
        return None

    def _send_order_notification(
        self,
        ts_code: str,
        direction: str,
        price: float,
        volume: int,
        order_id: str,
        strategy_name: str
    ):
        """发送订单通知"""
        try:
            from src.utils.dingtalk_notifier import DingTalkNotifier

            if settings.ENABLE_DINGDING_NOTIFY and settings.DINGDING_WEBHOOK:
                notifier = DingTalkNotifier()
                action = "买入" if direction == 'buy' else "卖出"
                msg = f"[实盘委托] {action} {ts_code}\n价格：{price:.2f}\n数量：{volume}\n订单 ID: {order_id}"
                notifier.send_text(msg)
        except Exception as e:
            trader_logger.warning(f"发送通知失败：{e}")

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单 ID

        Returns:
            是否成功
        """
        if not self.connected:
            return False

        try:
            result = self.user.cancel(order_id)

            if result:
                trader_logger.info(f"已取消订单：{order_id}")
                # 刷新订单缓存
                self._refresh_orders()
                return True
            else:
                trader_logger.warning(f"取消订单失败：{order_id}")
                return False

        except Exception as e:
            trader_logger.error(f"取消订单异常：{e}")
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

        try:
            if start_date:
                trades = self.user.get_entrusts(start_date=start_date)
            else:
                trades = self.user.get_current_entrusts()

            result = []
            for trade in trades:
                ts_code = self._format_stock_code(trade.get('证券代码', ''))
                result.append({
                    'ts_code': ts_code,
                    'name': trade.get('证券名称', ''),
                    'direction': 'buy' if trade.get('委托类型', '') == '证券买入' else 'sell',
                    'price': float(trade.get('成交价格', 0)),
                    'volume': int(trade.get('成交数量', 0)),
                    'amount': float(trade.get('成交金额', 0)),
                    'trade_time': trade.get('成交时间', ''),
                })

            return result
        except Exception as e:
            trader_logger.error(f"获取成交记录失败：{e}")
            return []


# 工厂函数
def create_broker(
    broker_type: str,
    config_path: Optional[str] = None,
    **kwargs
) -> EasyTraderBroker:
    """
    创建券商实例

    Args:
        broker_type: 券商类型
        config_path: 配置文件路径
        **kwargs: 其他参数

    Returns:
        券商实例
    """
    return EasyTraderBroker(
        broker_type=broker_type,
        config_path=config_path,
        **kwargs
    )


if __name__ == "__main__":
    # 测试代码
    print("=" * 50)
    print("easytrader 券商接口测试")
    print("=" * 50)

    # 配置文件示例
    config_example = {
        "user": "你的账号",
        "password": "你的密码",
        "comm_password": "通讯密码/交易密码"
    }

    print("\n配置文件示例:")
    print(json.dumps(config_example, indent=2, ensure_ascii=False))

    print("\n支持的券商:")
    for name, key in EasyTraderBroker.BROKER_TYPES.items():
        print(f"  - {name}: {key}")

    print("\n使用前请:")
    print("1. 安装 easytrader: pip install easytrader")
    print("2. 创建配置文件 (JSON 格式)")
    print("3. 确认券商客户端已安装并能正常登录")
