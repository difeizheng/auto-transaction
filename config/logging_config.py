"""
日志配置模块
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import config.settings as settings


def setup_logger(name: str) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 如果已经有处理器，不重复添加
    if logger.handlers:
        return logger

    # 创建 formatter
    formatter = logging.Formatter(settings.LOG_FORMAT)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    # Windows 控制台使用 errors='ignore' 避免编码问题
    if sys.platform == 'win32':
        console_handler.stream = open(sys.stdout.fileno(), 'w', encoding='utf-8', errors='ignore', closefd=False)
    logger.addHandler(console_handler)

    # 文件处理器 (按大小轮转，最大 10MB)
    log_dir = settings.LOG_DIR
    log_dir.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# 创建各模块 logger
data_logger = setup_logger("data_collector")
strategy_logger = setup_logger("strategy")
backtest_logger = setup_logger("backtest")
trader_logger = setup_logger("trader")
