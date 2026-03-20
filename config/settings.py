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

# 基本面过滤条件
FUNDAMENTAL_FILTERS = {
    'max_pe': 50,        # 市盈率 < 50
    'min_roe': 0.05,     # ROE > 5%
    'min_revenue_growth': 0.0,  # 营收增长 > 0
}

# ============ 通知配置 ============
ENABLE_EMAIL_NOTIFY = False
ENABLE_WECHAT_NOTIFY = False
