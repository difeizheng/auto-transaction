"""
系统配置文件
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# ============ 数据库配置 ============
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/quant_trading.db")

# ============ API 配置 ============
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
TUSHARE_API_URL = "http://api.tushare.pro"

# ============ 日志配置 ============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
LOG_DIR = PROJECT_ROOT / "logs"

# ============ 交易配置 ============
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# 风控参数
MAX_POSITION_RATIO = float(os.getenv("MAX_POSITION_RATIO", 0.8))  # 最大仓位比例
STOP_LOSS_RATIO = float(os.getenv("STOP_LOSS_RATIO", 0.05))  # 止损比例 5%
TAKE_PROFIT_RATIO = float(os.getenv("TAKE_PROFIT_RATIO", 0.15))  # 止盈比例 15%

# 单笔交易最大金额
MAX_ORDER_VALUE = 100000  # 10 万

# 单只股票最大持仓比例
MAX_STOCK_POSITION_RATIO = 0.2  # 20%

# ============ 回测配置 ============
INITIAL_CAPITAL = 1000000  # 初始资金 100 万
COMMISSION_RATE = 0.0003  # 佣金费率 万分之三
STAMP_TAX_RATE = 0.001  # 印花税率 千分之一 (卖出收取)
SLIPPAGE_RATE = 0.001  # 滑点费率 千分之一

# ============ 调度配置 ============
# 盘前准备时间
PRE_MARKET_TIME = "08:30"
# 盘中监控间隔 (秒)
MARKET_MONITOR_INTERVAL = 60
# 盘后分析时间
POST_MARKET_TIME = "16:00"

# ============ 数据目录 ============
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"

# ============ 市场配置 ============
# 交易日历 (A 股交易日由 Tushare 获取)
MARKET_OPEN_TIME = "09:30"
MARKET_CLOSE_TIME = "15:00"
LUNCH_BREAK_START = "11:30"
LUNCH_BREAK_END = "13:00"

# ============ 股票池配置 ============
# 默认股票池 (5 只)
DEFAULT_STOCK_POOL = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']

# 扩展股票池 (沪深 300 成分股示例 - 30 只)
EXTENDED_STOCK_POOL = [
    # 金融
    '600000.SH', '600036.SH', '601166.SH', '601318.SH', '601398.SH',
    '000001.SZ', '000002.SZ', '000063.SZ',
    # 消费
    '600519.SH', '600887.SH', '000858.SZ', '000333.SZ', '002304.SZ',
    # 医药
    '600276.SH', '000538.SZ', '300760.SZ',
    # 科技
    '002415.SZ', '002230.SZ', '000063.SZ', '600036.SH',
    # 制造
    '601318.SH', '600690.SH', '000651.SZ', '600104.SH',
    # 能源
    '601857.SH', '600028.SH', '600938.SH',
    # 其他
    '600030.SH', '601668.SH'
]

# 基本面过滤条件 (增强版 - v5.0)
FUNDAMENTAL_FILTERS = {
    'max_pe': 50,        # 市盈率 < 50
    'min_roe': 0.05,     # ROE > 5%
    'min_revenue_growth': 0.0,  # 营收增长 > 0
    'max_debt_ratio': 0.70,     # 资产负债率 < 70%
    'min_market_cap': 5000000000,  # 最小市值 50 亿
    # v5.0 新增
    'excellent_roe': 0.20,        # 优秀 ROE 20%
    'min_profit_growth': 0.0,     # 最小利润增长 0%
    'max_pb': 10,                 # 最大 PB 10
    'min_current_ratio': 1.0,     # 最小流动比率 1.0
    'roe_stability_window': 4,    # ROE 稳定性计算窗口 (季度数)
}

# 基本面因子权重 (v5.0 新增)
FUNDAMENTAL_FACTOR_WEIGHTS = {
    'roe_weight': 0.30,       # ROE 权重 30%
    'growth_weight': 0.25,    # 增长权重 25%
    'value_weight': 0.20,     # 估值权重 20%
    'health_weight': 0.15,    # 健康权重 15%
    'size_weight': 0.10,      # 市值权重 10%
}

# 调仓周期配置 (增强版 - v5.0)
REBALANCE_CONFIG = {
    'enabled': True,              # 启用定期调仓
    'frequency': 'monthly',       # 调仓频率：weekly/monthly/quarterly
    'max_turnover_ratio': 0.30,   # 单次最大调仓比例 30%
    'holding_period_min': 5,      # 最小持有期 (交易日)
    'holding_period_max': 60,     # 最大持有期 (交易日)
    # v5.0 新增
    'rebalance_on_signal': True,  # 信号触发时调仓
    'fundamental_rebalance_threshold': 0.3,  # 基本面评分下降 30% 时调仓
    'check_fundamental_on_entry': True,  # 入场前检查基本面
}

# ============ 通知配置 ============
ENABLE_EMAIL_NOTIFY = False
ENABLE_WECHAT_NOTIFY = False

# ============ 钉钉通知配置 ============
DINGDING_WEBHOOK = os.getenv("DINGDING_WEBHOOK", "")
DINGDING_SECRET = os.getenv("DINGDING_SECRET", "")
ENABLE_DINGDING_NOTIFY = os.getenv("ENABLE_DINGDING_NOTIFY", "false").lower() == "true"

# 钉钉通知触发条件
DINGDING_NOTIFY_CONFIG = {
    'enabled': ENABLE_DINGDING_NOTIFY,
    'notify_on_trade': True,        # 交易时通知
    'notify_on_signal': False,      # 产生信号时通知（可能频繁）
    'notify_on_stop_loss': True,    # 止损时通知
    'notify_on_take_profit': True,  # 止盈时通知
    'daily_summary': True,          # 每日 summary
    'daily_summary_time': '15:30',  # 每日 summary 发送时间
}

# ============ 实盘交易配置 ============
# 实盘模式开关
REAL_TRADING_MODE = os.getenv("REAL_TRADING_MODE", "false").lower() == "true"

# 券商配置
REAL_BROKER_TYPE = os.getenv("REAL_BROKER_TYPE", "huatai")  # 券商类型
REAL_BROKER_CONFIG_PATH = os.getenv("REAL_BROKER_CONFIG_PATH", "config/broker_config.json")

# 数据源配置
USE_REALTIME_DATA = os.getenv("USE_REALTIME_DATA", "true").lower() == "true"  # 使用实时数据
REALTIME_DATA_SOURCE = os.getenv("REALTIME_DATA_SOURCE", "sina")  # sina/tencent

# 实盘风控参数
REAL_TRADING_RISK_CONFIG = {
    'enabled': REAL_TRADING_MODE,
    # 仓位限制（实盘更严格）
    'max_position_ratio': 0.80,       # 实盘最大仓位 80%
    'max_stock_position_ratio': 0.25, # 单只股票最大 25%
    # 价格异常检测
    'price_anomaly_threshold': 0.03,  # 3% 价格异常波动
    'limit_up_check_enabled': True,   # 启用涨跌停检查
    # 流动性检测
    'min_daily_volume': 100000,       # 最小日成交量 10 万手
    'min_daily_amount': 10000000,     # 最小日成交额 1000 万
    # 交易时段限制
    'avoid_call_auction': True,       # 避免集合竞价
    'morning_start_time': '09:35',    # 上午开始交易时间
    'afternoon_end_time': '14:55',    # 下午结束交易时间
    # 大额订单确认
    'large_order_threshold': 50000,   # 大额订单阈值 5 万
    'large_order_confirmation': True, # 启用大额订单二次确认
}

# 熔断配置
CIRCUIT_BREAKER_CONFIG = {
    'enabled': True,
    'single_stock_loss_threshold': 0.10,  # 单只股票亏损 10% 触发
    'portfolio_loss_threshold': 0.05,     # 组合亏损 5% 触发
    'daily_loss_threshold': 0.03,         # 单日亏损 3% 触发
    'market_drop_threshold': 0.03,        # 市场下跌 3% 触发
    'cooldown_period': 300,               # 冷却期 5 分钟
}

# 实时监控配置
REALTIME_MONITOR_CONFIG = {
    'enabled': REAL_TRADING_MODE,
    'interval': 10,                       # 监控间隔 10 秒
    'price_change_threshold': 0.05,       # 5% 价格变动告警
    'data_delay_threshold': 60,           # 数据延迟 60 秒告警
}

# 紧急处理配置
EMERGENCY_HANDLER_CONFIG = {
    'enabled': REAL_TRADING_MODE,
    'auto_stop_loss': True,               # 自动止损
    'auto_clear_position': True,          # 自动清仓（触发熔断时）
    'dingtalk_emergency_notify': True,    # 紧急通知
}
