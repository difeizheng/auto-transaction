"""
辅助函数模块
"""
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Union
import pandas as pd
import numpy as np


def format_ts_code(symbol: str, exchange: str = "SH") -> str:
    """
    将股票代码转换为 Tushare 格式 (代码.交易所)

    Args:
        symbol: 股票代码 (6 位数字)
        exchange: 交易所 (SH/SZ)

    Returns:
        Tushare 格式的代码，如 000001.SZ

    Examples:
        >>> format_ts_code("000001", "SZ")
        '000001.SZ'
        >>> format_ts_code("600000", "SH")
        '600000.SH'
    """
    symbol = str(symbol).zfill(6)
    exchange = exchange.upper()
    return f"{symbol}.{exchange}"


def parse_ts_code(ts_code: str) -> Tuple[str, str]:
    """
    解析 Tushare 格式的代码

    Args:
        ts_code: Tushare 格式的代码

    Returns:
        (symbol, exchange) 元组
    """
    match = re.match(r"(\d{6})\.(SH|SZ)", ts_code.upper())
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"无效的 Tushare 代码格式：{ts_code}")


def get_trade_time_range(date: str) -> Tuple[str, str]:
    """
    获取交易日的分钟线时间范围

    Args:
        date: 交易日期 (YYYYMMDD 或 YYYY-MM-DD)

    Returns:
        (开始时间，结束时间) 元组
    """
    date = date.replace("-", "")
    start = f"{date} 09:30:00"
    end = f"{date} 15:00:00"
    return start, end


def calculate_ma(prices: pd.Series, windows: List[int]) -> pd.DataFrame:
    """
    计算多条均线

    Args:
        prices: 价格序列
        windows: 均线周期列表

    Returns:
        包含多条均线的 DataFrame
    """
    result = pd.DataFrame()
    for window in windows:
        result[f"ma{window}"] = prices.rolling(window=window).mean()
    return result


def calculate_ema(prices: pd.Series, span: int) -> pd.Series:
    """
    计算指数移动平均线 (EMA)

    Args:
        prices: 价格序列
        span: EMA 周期

    Returns:
        EMA 序列
    """
    return prices.ewm(span=span, adjust=False).mean()


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算相对强弱指标 (RSI)

    Args:
        prices: 价格序列
        period: RSI 周期

    Returns:
        RSI 序列
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    prices: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> pd.DataFrame:
    """
    计算 MACD 指标

    Args:
        prices: 价格序列
        fast_period: 快线周期
        slow_period: 慢线周期
        signal_period: 信号线周期

    Returns:
        包含 DIF, DEA, MACD 的 DataFrame
    """
    ema_fast = calculate_ema(prices, fast_period)
    ema_slow = calculate_ema(prices, slow_period)

    dif = ema_fast - ema_slow
    dea = calculate_ema(dif, signal_period)
    macd = 2 * (dif - dea)

    return pd.DataFrame({
        "dif": dif,
        "dea": dea,
        "macd": macd
    })


def calculate_bollinger_bands(
    prices: pd.Series,
    window: int = 20,
    num_std: float = 2.0
) -> pd.DataFrame:
    """
    计算布林带

    Args:
        prices: 价格序列
        window: 均线周期
        num_std: 标准差倍数

    Returns:
        包含 upper, middle, lower 的 DataFrame
    """
    middle = prices.rolling(window=window).mean()
    std = prices.rolling(window=window).std()

    upper = middle + num_std * std
    lower = middle - num_std * std

    return pd.DataFrame({
        "upper": upper,
        "middle": middle,
        "lower": lower
    })


def calculate_momentum(prices: pd.Series, period: int = 10) -> pd.Series:
    """
    计算动量指标

    Args:
        prices: 价格序列
        period: 动量周期

    Returns:
        动量序列
    """
    return prices.pct_change(periods=period)


def calculate_volatility(prices: pd.Series, window: int = 20) -> pd.Series:
    """
    计算波动率 (滚动标准差)

    Args:
        prices: 价格序列
        window: 滚动窗口

    Returns:
        波动率序列
    """
    returns = prices.pct_change()
    return returns.rolling(window=window).std()


def normalize_date(date: Union[str, datetime]) -> str:
    """
    规范化日期格式为 YYYYMMDD

    Args:
        date: 日期 (字符串或 datetime)

    Returns:
        YYYYMMDD 格式的字符串
    """
    if isinstance(date, datetime):
        return date.strftime("%Y%m%d")

    date = str(date).replace("-", "")
    if len(date) == 8:
        return date
    raise ValueError(f"无效的日期格式：{date}")


def get_previous_trade_date(date: str, days: int = 1) -> str:
    """
    获取前 N 个交易日 (简单实现，未考虑节假日)

    Args:
        date: 当前日期
        days: 向前推的天数

    Returns:
        前 N 个交易日的日期
    """
    dt = datetime.strptime(date.replace("-", ""), "%Y%m%d")
    # 简单减去天数 (未考虑周末和节假日，实际使用应从交易日历查询)
    prev_dt = dt - timedelta(days=days)
    return prev_dt.strftime("%Y%m%d")


def format_amount(amount: float) -> str:
    """
    格式化金额为万元/亿元显示

    Args:
        amount: 金额

    Returns:
        格式化后的字符串
    """
    if amount >= 1e8:
        return f"{amount / 1e8:.2f}亿"
    elif amount >= 1e4:
        return f"{amount / 1e4:.2f}万"
    else:
        return f"{amount:.2f}"


def round_lot_size(volume: int, ts_code: str) -> int:
    """
    根据股票类型调整手数 (100 股的整数倍)

    Args:
        volume: 原始股数
        ts_code: 股票代码

    Returns:
        调整后的股数
    """
    # A 股最小交易单位是 100 股
    return (volume // 100) * 100


def is_market_open(time_str: str) -> bool:
    """
    判断是否在交易时间内

    Args:
        time_str: 时间字符串 (HH:MM:SS)

    Returns:
        是否在交易时间内
    """
    try:
        t = datetime.strptime(time_str, "%H:%M:%S").time()

        # 早盘 9:30-11:30
        morning_start = datetime.strptime("09:30:00", "%H:%M:%S").time()
        morning_end = datetime.strptime("11:30:00", "%H:%M:%S").time()

        # 午盘 13:00-15:00
        afternoon_start = datetime.strptime("13:00:00", "%H:%M:%S").time()
        afternoon_end = datetime.strptime("15:00:00", "%H:%M:%S").time()

        return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)
    except ValueError:
        return False


def calculate_portfolio_return(
    weights: np.ndarray,
    returns: pd.DataFrame
) -> pd.Series:
    """
    计算投资组合收益率

    Args:
        weights: 权重数组
        returns: 各资产收益率 DataFrame

    Returns:
        组合收益率序列
    """
    return (weights * returns).sum(axis=1)


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> float:
    """
    计算夏普比率

    Args:
        returns: 收益率序列
        risk_free_rate: 无风险利率
        periods_per_year: 每年交易天数

    Returns:
        夏普比率
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    if excess_returns.std() == 0:
        return 0.0
    return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()


def calculate_max_drawdown(cumulative_returns: pd.Series) -> float:
    """
    计算最大回撤

    Args:
        cumulative_returns: 累计收益率曲线

    Returns:
        最大回撤比例
    """
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    return abs(drawdown.min())
