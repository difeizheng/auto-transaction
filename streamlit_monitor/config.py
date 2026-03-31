"""
Streamlit 监控系统配置
"""
import os
from pathlib import Path
from datetime import time

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# 数据库路径
DATABASE_PATH = PROJECT_ROOT / "data" / "quant_trading.db"

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"

# 日志文件配置
LOG_FILES = {
    "trader": LOG_DIR / "trader.log",
    "data_collector": LOG_DIR / "data_collector.log",
    "strategy": LOG_DIR / "strategy.log",
    "paper_trading": LOG_DIR / "paper_trading.log",  # 会是动态文件名
}

# 页面配置
PAGE_CONFIG = {
    "page_title": "量化交易监控系统",
    "page_icon": "📈",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# 刷新间隔（毫秒）
REFRESH_INTERVAL = 5000  # 5秒

# 颜色配置
COLORS = {
    "success": "#00C851",
    "warning": "#ffbb33",
    "danger": "#ff4444",
    "info": "#33b5e5",
    "primary": "#4285F4",
    "secondary": "#aa66cc",
    "dark": "#2BBBAD",
}

# 市场时段配置
MARKET_HOURS = {
    "pre_market": (time(0, 0), time(9, 30)),
    "morning_trading": (time(9, 30), time(11, 30)),
    "lunch_break": (time(11, 30), time(13, 0)),
    "afternoon_trading": (time(13, 0), time(14, 50)),
    "signal_window": (time(14, 50), time(15, 0)),
    "closed": (time(15, 0), time(23, 59)),
}

# 初始资金
INITIAL_CAPITAL = 20000

# 股票池大小
STOCK_POOL_SIZE = 44