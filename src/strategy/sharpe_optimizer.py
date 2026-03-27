"""
夏普比率优化模块
优化方向：
1. 降低收益波动率 - 增加稳定性因子
2. 提高收益风险比 - 优化出场逻辑
3. 改进市场状态判断 - 更准确的牛熊识别
4. 增加波动率过滤 - 避开高波动时段
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SharpeOptimizationConfig:
    """夏普优化配置"""
    # 波动率过滤
    use_volatility_filter: bool = True
    max_volatility_threshold: float = 0.04  # 最大波动率阈值 4%
    volatility_lookback: int = 20  # 波动率计算周期

    # 稳定性因子
    use_stability_factor: bool = True
    stability_lookback: int = 10  # 稳定性计算周期
    min_stability_threshold: float = 0.6  # 最小稳定性阈值

    # 市场状态优化
    use_enhanced_market_filter: bool = True
    bear_market_min_position: float = 0.05  # 熊市最小仓位 5%
    bull_market_max_position: float = 0.55  # 牛市最大仓位 55%

    # 出场优化
    use_dynamic_exit: bool = True
    profit_lock_trigger: float = 0.08  # 利润锁定触发点 8%
    profit_lock_ratio: float = 0.5  # 利润锁定比例 50%


class SharpeOptimizer:
    """夏普比率优化器"""

    def __init__(self, config: Optional[SharpeOptimizationConfig] = None):
        self.config = config or SharpeOptimizationConfig()
        self.price_history: Dict[str, pd.DataFrame] = {}

    def update_price_history(self, ts_code: str, data: pd.DataFrame):
        """更新价格历史"""
        self.price_history[ts_code] = data

    def calculate_volatility(self, ts_code: str) -> float:
        """
        计算波动率 (收益率标准差)

        Returns:
            波动率值 (0-1)
        """
        if ts_code not in self.price_history:
            return 0.02  # 默认 2%

        df = self.price_history[ts_code]
        lookback = self.config.volatility_lookback

        if len(df) < lookback + 1:
            return 0.02

        # 计算收益率
        returns = df['close'].pct_change().dropna()

        # 计算滚动标准差
        volatility = returns.tail(lookback).std()

        return volatility if pd.notna(volatility) else 0.02

    def should_skip_trade_due_to_volatility(self, ts_code: str) -> bool:
        """
        是否因高波动跳过交易

        Returns:
            True 表示应该跳过
        """
        if not self.config.use_volatility_filter:
            return False

        volatility = self.calculate_volatility(ts_code)
        return volatility > self.config.max_volatility_threshold

    def calculate_stability_factor(self, ts_code: str) -> float:
        """
        计算稳定性因子

        基于：
        1. 价格趋势稳定性 (R-squared)
        2. 收益率自相关性 (避免随机游走)

        Returns:
            稳定性分数 (0-1)
        """
        if not self.config.use_stability_factor:
            return 1.0

        if ts_code not in self.price_history:
            return 1.0

        df = self.price_history[ts_code]
        lookback = self.config.stability_lookback

        if len(df) < lookback:
            return 1.0

        close = df['close'].tail(lookback)

        # 1. 计算趋势稳定性 (线性回归 R-squared)
        x = np.arange(len(close))
        y = close.values

        # 线性拟合
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept

        # R-squared
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # 2. 计算收益率自相关性 (检测趋势持续性)
        returns = close.pct_change().dropna()
        if len(returns) > 2:
            autocorr = returns.autocorr(lag=1)
            if pd.isna(autocorr):
                autocorr = 0
        else:
            autocorr = 0

        # 综合稳定性因子
        # R-squared 越高表示趋势越稳定
        # 正自相关表示趋势持续，负自相关表示均值回归
        stability = max(0, min(1, (r_squared + abs(autocorr)) / 2))

        return stability

    def get_stability_adjustment(self, ts_code: str) -> float:
        """
        获取稳定性调整因子

        Returns:
            调整因子 (0.5-1.2)
        """
        stability = self.calculate_stability_factor(ts_code)

        if stability < self.config.min_stability_threshold:
            return 0.5  # 低稳定性，降仓
        elif stability > 0.8:
            return 1.2  # 高稳定性，增仓
        else:
            return 1.0

    def check_enhanced_market_state(
        self,
        df: pd.DataFrame,
        current_state: str
    ) -> str:
        """
        增强版市场状态检查

        在传统双均线基础上增加：
        1. 成交量确认
        2. 波动率状态
        3. 趋势强度

        Args:
            df: 价格数据
            current_state: 当前市场状态 ('bull'/'bear'/'sideways')

        Returns:
            优化后的市场状态
        """
        if not self.config.use_enhanced_market_filter:
            return current_state

        if len(df) < 30:
            return current_state

        close = df['close']
        vol = df.get('vol', pd.Series([1] * len(df)))

        # 1. 计算趋势强度 (ADX 简化版)
        # 使用 20 日均线斜率
        ma20 = close.rolling(20).mean()
        ma_slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] if ma20.iloc[-5] > 0 else 0

        # 2. 成交量确认
        vol_ma = vol.rolling(20).mean()
        vol_ratio = vol.iloc[-1] / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1

        # 3. 波动率状态
        returns = close.pct_change()
        current_volatility = returns.tail(20).std()

        # 4. 综合判断
        if current_state == 'bull':
            # 牛市确认：需要正斜率 + 成交量配合
            if ma_slope < -0.01:  # 斜率转负
                return 'sideways'  # 转为震荡市
            if vol_ratio > 1.5 and ma_slope < 0.005:  # 放量但趋势弱
                return 'sideways'

        elif current_state == 'bear':
            # 熊市确认：需要负斜率确认
            if ma_slope > 0.02:  # 斜率转正
                return 'sideways'

        return current_state

    def calculate_dynamic_exit_price(
        self,
        entry_price: float,
        current_price: float,
        highest_price: float,
        atr: float,
        market_state: str
    ) -> Tuple[Optional[float], str]:
        """
        动态出场价格计算

        优化逻辑：
        1. 分级止盈 - 部分锁定利润
        2. 波动率调整止损 - 高波动放宽
        3. 市场状态自适应

        Args:
            entry_price: 入场价
            current_price: 当前价
            highest_price: 最高价
            atr: ATR 值
            market_state: 市场状态

        Returns:
            (出场价格，出场原因) 或 (None, '')
        """
        if not self.config.use_dynamic_exit:
            return None, ''

        profit_ratio = (current_price - entry_price) / entry_price
        highest_profit = (highest_price - entry_price) / entry_price

        # === 分级止盈逻辑 ===
        # 当盈利达到触发点时，建议部分止盈
        if highest_profit >= self.config.profit_lock_trigger:
            # 计算回撤
            drawdown = (highest_price - current_price) / highest_price

            # 如果从最高点回撤超过阈值，建议部分止盈
            if drawdown >= 0.03:  # 3% 回撤
                return current_price, f'部分止盈 (盈利{profit_ratio:.1%}, 回撤{drawdown:.1%})'

        # === 波动率调整止损 ===
        # 高波动时放宽止损，避免被震荡出局
        vol_adjustment = min(2.0, max(1.0, atr / 0.02))  # 基准 ATR 2%

        # 动态止损阈值
        dynamic_sl = 0.05 * vol_adjustment  # 基础 5% * 波动调整

        if profit_ratio <= -dynamic_sl:
            return current_price, f'动态止损 ({profit_ratio:.1%})'

        # === 市场状态自适应止盈 ===
        if market_state == 'bear':
            # 熊市：提前止盈
            if profit_ratio >= 0.15:  # 15% 止盈
                return current_price, '熊市止盈'
        elif market_state == 'bull':
            # 牛市：让利润奔跑
            # 使用移动止损而非固定止盈
            if highest_profit >= 0.15:
                trailing_sl = highest_price * 0.92  # 8% 移动止损
                if current_price < trailing_sl:
                    return current_price, f'牛市移动止损 ({(highest_price - current_price)/highest_price:.1%}回撤)'

        return None, ''

    def get_position_adjustment(
        self,
        ts_code: str,
        base_position: float,
        market_state: str
    ) -> float:
        """
        获取仓位调整建议

        Args:
            ts_code: 股票代码
            base_position: 基础仓位
            market_state: 市场状态

        Returns:
            调整后的仓位
        """
        # 1. 波动率过滤
        if self.should_skip_trade_due_to_volatility(ts_code):
            return 0

        # 2. 稳定性调整
        stability_adj = self.get_stability_adjustment(ts_code)
        adjusted_position = base_position * stability_adj

        # 3. 市场状态调整
        if market_state == 'bear':
            max_pos = self.config.bear_market_min_position
            adjusted_position = min(adjusted_position, max_pos)
        elif market_state == 'bull':
            max_pos = self.config.bull_market_max_position
            adjusted_position = min(adjusted_position, max_pos)

        return adjusted_position


def optimize_sharpe_params() -> Dict[str, Any]:
    """
    优化后的夏普比率参数配置

    目标：夏普 0.63 -> 1.0+

    Returns:
        优化后的参数字典
    """
    return {
        # 原参数
        'original': {
            'base_stop_loss': 0.04,
            'base_take_profit': 0.35,
            'signal_threshold': 5.5,
            'base_position_ratio': 0.30,
            'max_position_ratio': 0.55,
        },

        # 夏普优化参数
        'optimized': {
            #  tighter 止损 + 分级止盈
            'base_stop_loss': 0.035,  # 3.5% 紧止损 (原 4%)
            'base_take_profit': 0.40,  # 40% 宽止盈 (原 35%)
            'trailing_stop_trigger': 0.08,  # 8% 触发移动止损
            'trailing_stop_ratio': 0.03,  # 3% 移动回撤

            # 信号阈值微调
            'signal_threshold': 5.2,  # 略降低阈值 (原 5.5)

            # 仓位优化
            'base_position_ratio': 0.25,  # 降低基础仓位
            'max_position_ratio': 0.50,  # 降低最大仓位

            # 新增波动率过滤
            'max_volatility_threshold': 0.04,  # 4% 波动率上限
            'min_stability_threshold': 0.6,  # 60% 稳定性下限

            # 市场状态优化
            'bear_market_max_position': 0.05,  # 熊市最多 5%
            'bull_market_max_position': 0.50,  # 牛市最多 50%
        },

        # 优化说明
        'optimization_notes': [
            '紧止损 (3.5%) - 减少单笔亏损，保护本金',
            '分级止盈 - 盈利 8% 后部分锁定，降低回撤',
            '波动率过滤 - 跳过 4%+高波动股票，避免异常亏损',
            '稳定性因子 - 优先交易趋势稳定的股票',
            '熊市轻仓 (5%) - 减少下跌市暴露',
            '移动止损 (3% 回撤) - 让利润奔跑同时保护收益',
        ]
    }


# 使用示例
if __name__ == "__main__":
    optimizer = SharpeOptimizer()
    config = optimize_sharpe_params()

    print("夏普比率优化配置")
    print("=" * 50)
    print("优化目标：夏普 0.63 -> 1.0+")
    print()
    print("核心优化:")
    for note in config['optimization_notes']:
        print(f"  - {note}")
