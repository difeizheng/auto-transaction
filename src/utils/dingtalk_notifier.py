"""
钉钉通知模块
通过钉钉机器人 Webhook 发送交易通知
"""
import hmac
import hashlib
import base64
import urllib.parse
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any

import config.settings as settings
from config.logging_config import trader_logger


class DingTalkNotifier:
    """钉钉通知器"""

    def __init__(self, webhook: str = None, secret: str = None):
        """
        初始化钉钉通知器

        Args:
            webhook: 钉钉机器人 Webhook URL
            secret: 加签密钥
        """
        self.webhook = webhook or settings.DINGDING_WEBHOOK
        self.secret = secret or settings.DINGDING_SECRET
        self.enabled = bool(self.webhook)
        self.config = settings.DINGDING_NOTIFY_CONFIG

    def generate_sign(self, timestamp: str) -> str:
        """
        生成钉钉签名

        Args:
            timestamp: 时间戳（毫秒）

        Returns:
            URL 编码的签名
        """
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(
            secret_enc,
            string_to_sign_enc,
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign

    def get_webhook_url(self) -> str:
        """获取带签名的 Webhook URL"""
        if not self.secret:
            return self.webhook

        timestamp = str(round(datetime.now().timestamp() * 1000))
        sign = self.generate_sign(timestamp)
        return f'{self.webhook}&timestamp={timestamp}&sign={sign}'

    def send_text(self, content: str, at_all: bool = True, at_mobiles: list = None):
        """
        发送文本消息

        Args:
            content: 消息内容
            at_all: 是否 @所有人
            at_mobiles: 需要@的手机号列表
        """
        if not self.enabled:
            trader_logger.debug("DingTalk notifier disabled, skipping")
            return False

        if not self.webhook:
            trader_logger.warning("DingTalk Webhook not configured")
            return False

        try:
            url = self.get_webhook_url()
            headers = {'Content-Type': 'application/json; charset=utf-8'}

            data = {
                "msgtype": "text",
                "text": {
                    "content": content
                },
                "at": {
                    "isAtAll": at_all,
                    "atMobiles": at_mobiles or []
                }
            }

            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            result = response.json()

            if result.get('errcode') == 0:
                trader_logger.info(f"DingTalk message sent successfully")
                return True
            else:
                trader_logger.error(f"钉钉消息发送失败：{result}")
                return False

        except Exception as e:
            trader_logger.error(f"DingTalk message send failed: {e}")
            return False

    def send_markdown(self, title: str, text: str, at_all: bool = True):
        """
        发送 Markdown 消息

        Args:
            title: 消息标题
            text: Markdown 格式内容
            at_all: 是否 @所有人
        """
        if not self.enabled:
            trader_logger.debug("DingTalk notifier disabled, skipping")
            return False

        if not self.webhook:
            trader_logger.warning("DingTalk Webhook not configured")
            return False

        try:
            url = self.get_webhook_url()
            headers = {'Content-Type': 'application/json; charset=utf-8'}

            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": text
                },
                "at": {
                    "isAtAll": at_all
                }
            }

            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            result = response.json()

            if result.get('errcode') == 0:
                trader_logger.info(f"DingTalk Markdown message sent successfully: {title}")
                return True
            else:
                trader_logger.error(f"DingTalk message send failed: {result}")
                return False

        except Exception as e:
            trader_logger.error(f"DingTalk message send failed: {e}")
            return False

    def send_trade_notification(self, ts_code: str, direction: str, price: float,
                                 volume: int, strategy_name: str = ""):
        """
        发送交易通知

        Args:
            ts_code: 股票代码
            direction: 买卖方向
            price: 成交价格
            volume: 成交数量
            strategy_name: 策略名称
        """
        if not self.config.get('notify_on_trade', True):
            return

        action = "🟢 买入" if direction == 'buy' else "🔴 卖出"
        action_color = "green" if direction == 'buy' else "red"

        # 获取股票名称（简单映射，实际可以从数据中获取）
        stock_names = {
            '000063.SZ': '中兴通讯',
            '000014.SZ': '沙河股份',
            '000078.SZ': '海王生物',
            '000039.SZ': '中集集团',
            '000001.SZ': '平安银行',
        }
        stock_name = stock_names.get(ts_code, ts_code)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        markdown_text = f"""## {action} 交易通知

| 项目 | 详情 |
|------|------|
| 股票 | {stock_name} ({ts_code}) |
| 方向 | {action} |
| 价格 | ¥{price:.2f} |
| 数量 | {volume} 股 |
| 金额 | ¥{price * volume:,.2f} |
| 策略 | {strategy_name} |
| 时间 | {now} |

---
*量化交易系统自动通知*"""

        title = f"{action} {stock_name}"
        self.send_markdown(title, markdown_text, at_all=False)

    def send_signal_notification(self, ts_code: str, signal_type: str,
                                  score: float, reason: str):
        """
        发送信号通知

        Args:
            ts_code: 股票代码
            signal_type: 信号类型
            score: 信号评分
            reason: 信号原因
        """
        if not self.config.get('notify_on_signal', False):
            return

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        markdown_text = f"""## 📈 交易信号提醒

| 项目 | 详情 |
|------|------|
| 股票 | {ts_code} |
| 信号 | {signal_type} |
| 评分 | {score:.1f} |
| 原因 | {reason} |
| 时间 | {now} |

---
*量化交易系统自动通知*"""

        title = f"📈 信号提醒 - {ts_code}"
        self.send_markdown(title, markdown_text, at_all=False)

    def send_daily_summary(self, total_trades: int, total_profit: float,
                            win_rate: float, position_count: int):
        """
        发送每日总结

        Args:
            total_trades: 当日交易次数
            total_profit: 当日盈亏
            win_rate: 胜率
            position_count: 当前持仓数
        """
        if not self.config.get('daily_summary', True):
            return

        profit_color = "🟢" if total_profit >= 0 else "🔴"
        profit_text = f"{profit_color} ¥{total_profit:,.2f}"

        now = datetime.now().strftime('%Y-%m-%d')

        markdown_text = f"""## 📊 每日交易总结

| 指标 | 数值 |
|------|------|
| 日期 | {now} |
| 交易次数 | {total_trades} |
| 当日盈亏 | {profit_text} |
| 胜率 | {win_rate:.1f}% |
| 当前持仓 | {position_count} 只 |

---
*量化交易系统自动通知*"""

        title = f"📊 每日总结 - {now}"
        self.send_markdown(title, markdown_text, at_all=False)

    def send_system_notification(self, title: str, content: str):
        """
        发送系统通知

        Args:
            title: 通知标题
            content: 通知内容
        """
        markdown_text = f"""## ⚠️ 系统通知

{content}

---
*量化交易系统自动通知*"""

        self.send_markdown(title, markdown_text, at_all=False)

    def test_connection(self) -> bool:
        """
        测试连接

        Returns:
            是否成功
        """
        content = """👋 量化交易系统 - 钉钉通知测试

如果您收到此消息，说明钉钉通知配置正确。

系统将持续监控市场并发送交易通知。"""

        return self.send_text(content, at_all=False)


# 全局实例
dingtalk_notifier = DingTalkNotifier()
