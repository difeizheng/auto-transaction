"""
最优综合策略系统
整合多因子、多指标、动态仓位管理的最优策略
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.strategy.base_strategy import BaseStrategy, Signal
from src.utils.helpers import calculate_macd, calculate_rsi, calculate_bollinger_bands
from src.strategy.sharpe_optimizer import SharpeOptimizer, SharpeOptimizationConfig
from src.strategy.win_rate_optimizer import WinRateOptimizer, WinRateOptimizationConfig, create_win_rate_optimizer
from src.strategy.fundamental_factors import FundamentalFactorAnalyzer, FundamentalFactorConfig, create_fundamental_analyzer
from config.logging_config import strategy_logger


class MarketState(Enum):
    """市场状态"""
    BULL = "bull"      # 牛市
    BEAR = "bear"      # 熊市
    SIDEWAYS = "sideways"  # 震荡市


@dataclass
class OptimalStrategyParams:
    """最优策略参数 - v2.0 深度优化版 (高胜率 + 高盈亏比 + 市场过滤)"""
    # 均线系统
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20
    ma_trend: int = 60

    # 成交量
    volume_ma_period: int = 20
    volume_ratio_threshold: float = 1.2

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 35
    rsi_overbought: float = 65

    # 布林带
    bb_window: int = 20
    bb_num_std: float = 2.0

    # 动态止损止盈 - v2.0 优化版 (小止损 + 分级止盈 + 移动止损)
    base_stop_loss: float = 0.05      # 基础止损 5% (紧止损)
    base_take_profit: float = 0.25    # 基础止盈 25% (宽止盈)
    atr_multiplier_sl: float = 1.5    # ATR 止损倍数
    atr_multiplier_tp: float = 3.5    # ATR 止盈倍数
    trailing_stop_trigger: float = 0.10  # 移动止损触发点 10%
    trailing_stop_ratio: float = 0.05    # 移动止损回撤 5%

    # 仓位管理
    base_position_ratio: float = 0.20  # 基础仓位 20%
    max_position_ratio: float = 0.30   # 最大仓位 30%
    min_position_ratio: float = 0.10   # 最小仓位 10%

    # 市场状态判断
    trend_threshold: float = 0.05      # 趋势判断阈值 5%

    # 信号阈值（动态可配置）
    signal_threshold: float = 5.0      # 信号触发阈值 5.0/10.5 (更严格)

    # 时间止损
    time_stop_days: int = 8            # 时间止损天数
    time_stop_profit_threshold: float = 0.03  # 时间止损盈利阈值

    # v2.0 新增：市场过滤
    use_market_filter: bool = True     # 启用市场状态过滤
    market_bear_max_position: float = 0.05  # 熊市最大仓位 5%

    # v3.0 新增：夏普优化
    use_sharpe_optimization: bool = True  # 启用夏普优化
    max_volatility_threshold: float = 0.035  # 最大波动率阈值 3.5% (收紧)
    min_stability_threshold: float = 0.65  # 最小稳定性阈值 65% (提高)
    profit_lock_trigger: float = 0.10  # 利润锁定触发点 10% (提高)

    # v5.0 夏普优化增强
    use_enhanced_sharpe: bool = True  # 启用增强夏普优化
    min_stability_r_squared: float = 0.5  # 最小 R 平方值 (趋势稳定性)
    profit_lock_ratio: float = 0.5  # 分级止盈比例 50%

    # v4.0 新增：胜率优化
    use_win_rate_optimization: bool = True  # 启用胜率优化
    min_momentum_score: float = 0.02  # 最小动量得分 (降低阈值)
    min_money_flow_score: float = -0.05  # 最小资金流得分 (允许小幅流出)
    min_stock_strength_rank: float = 0.35  # 最小股票强度排名 (前 35%)
    min_signal_confidence: float = 0.55  # 最小信号置信度 (降低)

    # v5.0 胜率优化增强
    use_enhanced_win_rate: bool = True  # 启用增强胜率优化
    min_momentum_continuous_days: int = 3  # 最小连续上涨天数
    add_momentum_to_signal_score: float = 1.0  # 动量因子额外加分权重
    add_flow_to_signal_score: float = 1.0  # 资金流额外加分权重

    # v5.0 新增：基本面因子
    use_fundamental_factor: bool = True  # 启用基本面因子
    min_fundamental_score: float = 0.5  # 最小基本面综合得分
    fundamental_weight_in_signal: float = 0.15  # 基本面在信号中的权重


class OptimalStrategy(BaseStrategy):
    """
    最优综合策略

    核心逻辑:
    1. 三重均线系统 (短/中/长) 判断趋势
    2. MACD + RSI + 布林带 多重确认
    3. 成交量过滤假突破
    4. 动态止损止盈 (基于 ATR)
    5. 智能仓位管理 (根据市场状态)
    6. 市场状态自适应 (牛/熊/震荡)
    """

    def __init__(
        self,
        name: str = "optimal_strategy",
        params: Optional[OptimalStrategyParams] = None
    ):
        super().__init__(name)
        self.params = params or OptimalStrategyParams()
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Dict] = {}  # {ts_code: {entry_price, highest_price, shares}}
        self.market_state = MarketState.SIDEWAYS

        # v3.0: 初始化夏普优化器
        if self.params.use_sharpe_optimization:
            sharpe_config = SharpeOptimizationConfig(
                use_volatility_filter=True,
                max_volatility_threshold=self.params.max_volatility_threshold,
                min_stability_threshold=self.params.min_stability_threshold,
                profit_lock_trigger=self.params.profit_lock_trigger,
            )
            self.sharpe_optimizer = SharpeOptimizer(sharpe_config)
        else:
            self.sharpe_optimizer = None

        # v4.0: 初始化胜率优化器
        if self.params.use_win_rate_optimization:
            self.win_rate_optimizer = create_win_rate_optimizer()
        else:
            self.win_rate_optimizer = None

        # v5.0: 初始化基本面因子分析器
        if self.params.use_fundamental_factor:
            fundamental_config = FundamentalFactorConfig(
                min_roe=0.05,
                excellent_roe=0.20,
                min_revenue_growth=0.0,
                min_profit_growth=0.0,
                max_pe=50,
                max_pb=10,
                max_debt_ratio=0.70,
                min_market_cap=5e9,
                roe_weight=0.30,
                growth_weight=0.25,
                value_weight=0.20,
                health_weight=0.15,
                size_weight=0.10,
            )
            self.fundamental_analyzer = FundamentalFactorAnalyzer(fundamental_config)
        else:
            self.fundamental_analyzer = None

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.price_history = {}
        self.positions = {}
        strategy_logger.info(f"最优策略初始化 - 市场自适应交易")
        strategy_logger.info(f"参数：止损={self.params.base_stop_loss*100}%, "
                            f"止盈={self.params.base_take_profit*100}%, "
                            f"基础仓位={self.params.base_position_ratio*100}%")

    def update_price_history(self, data: Dict[str, Any], current_date: str):
        """更新价格历史"""
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = pd.DataFrame()

            new_row = pd.DataFrame([{
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0),
                'amount': bar.get('amount', 0)
            }])

            self.price_history[ts_code] = pd.concat(
                [self.price_history[ts_code], new_row],
                ignore_index=True
            )

            # 保留足够数据
            max_history = self.params.ma_trend * 3
            if len(self.price_history[ts_code]) > max_history:
                self.price_history[ts_code] = self.price_history[ts_code].tail(max_history)

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算 ATR (平均真实波幅)"""
        if len(df) < period + 1:
            return 0.02  # 默认 2%

        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return atr / close.iloc[-1] if close.iloc[-1] > 0 else 0.02

    def determine_market_state(self, df: pd.DataFrame) -> MarketState:
        """
        判断市场状态 (增强版 - 更准确的趋势识别)

        基于：
        1. 双均线系统 (短期 vs 长期)
        2. 价格相对位置 (价格 vs 长期均线)
        3. 均线斜率 (趋势方向)
        """
        ma_long_period = self.params.ma_trend

        if len(df) < ma_long_period + 5:
            return MarketState.SIDEWAYS

        close = df['close']

        # 计算双均线
        ma_short_val = close.rolling(self.params.ma_short).mean()
        ma_long_val = close.rolling(ma_long_period).mean()

        current_price = close.iloc[-1]
        short_val = ma_short_val.iloc[-1]
        long_val = ma_long_val.iloc[-1]

        # 检查均线关系
        golden_state = short_val > long_val  # 多头排列
        death_state = short_val < long_val   # 空头排列

        # 价格相对位置 (更严格的阈值)
        price_above_long = current_price > long_val * 1.02  # 价格在长期均线上方 2%
        price_below_long = current_price < long_val * 0.98  # 价格在长期均线下方 2%

        # 检查均线斜率 (5 日变化)
        if len(df) >= 5:
            short_slope = ma_short_val.iloc[-1] - ma_short_val.iloc[-5]
            long_slope = ma_long_val.iloc[-1] - ma_long_val.iloc[-5]
        else:
            short_slope = 0
            long_slope = 0

        # 检查连续趋势（连续 3 日确认，更可靠）
        bull_count = 0
        bear_count = 0
        for i in range(3):
            idx = -1 - i
            if idx >= -len(df):
                s_val = ma_short_val.iloc[idx]
                l_val = ma_long_val.iloc[idx]
                if s_val > l_val:
                    bull_count += 1
                elif s_val < l_val:
                    bear_count += 1

        # 增强判断逻辑
        bull_score = 0
        bear_score = 0

        if bull_count >= 3:
            bull_score += 1
        if bear_count >= 3:
            bear_score += 1

        if golden_state and price_above_long:
            bull_score += 1
        if death_state and price_below_long:
            bear_score += 1

        if short_slope > 0:
            bull_score += 0.5
        if short_slope < 0:
            bear_score += 0.5

        if long_slope > 0:
            bull_score += 0.5
        if long_slope < 0:
            bear_score += 0.5

        # 综合判断
        if bull_score >= 2.5:
            return MarketState.BULL
        elif bear_score >= 2.5:
            return MarketState.BEAR
        else:
            return MarketState.SIDEWAYS

    def calculate_dynamic_stop_loss_take_profit(
        self,
        ts_code: str,
        atr: float
    ) -> Tuple[float, float]:
        """
        计算动态止损止盈

        返回基于参数设置的止损止盈比例
        """
        # 直接使用参数设置的基础止损止盈
        sl = self.params.base_stop_loss
        tp = self.params.base_take_profit

        # 根据市场状态微调
        if self.market_state == MarketState.BULL:
            # 牛市：放宽止损止盈
            sl = max(sl, atr * 1.5)  # 至少 ATR 的 1.5 倍
            tp = max(tp, atr * 3.0)  # 至少 ATR 的 3 倍
        elif self.market_state == MarketState.BEAR:
            # 熊市：收紧止损止盈
            sl = max(sl * 0.8, atr * 1.0)
            tp = max(tp * 0.8, atr * 2.0)
        else:
            # 震荡市：使用基础值
            sl = max(sl, atr * 1.2)
            tp = max(tp, atr * 2.5)

        return sl, tp

    def calculate_position_size(
        self,
        ts_code: str,
        signal_strength: float,
        current_price: float
    ) -> int:
        """
        智能仓位管理 (增强版 - v3.0 夏普优化)

        根据市场状态、信号强度、波动率、稳定性动态调整
        """
        # 基础仓位
        base_ratio = self.params.base_position_ratio

        # 根据市场状态调整
        if self.market_state == MarketState.BULL:
            # 牛市：增加仓位
            position_ratio = min(self.params.max_position_ratio, base_ratio * 1.5)
        elif self.market_state == MarketState.BEAR:
            # 熊市：减少仓位
            position_ratio = max(self.params.min_position_ratio, base_ratio * 0.5)
        else:
            # 震荡市：保持基础仓位
            position_ratio = base_ratio

        # 根据信号强度调整
        position_ratio *= signal_strength

        # 根据波动率调整 (高波动降仓)
        volatility_adjustment = self.get_volatility_adjustment(ts_code)
        position_ratio *= volatility_adjustment

        # v3.0: 根据稳定性调整 (夏普优化)
        if self.sharpe_optimizer and self.params.use_sharpe_optimization:
            stability_adj = self.sharpe_optimizer.get_stability_adjustment(ts_code)
            position_ratio *= stability_adj
            strategy_logger.debug(f"{ts_code}: 稳定性调整因子={stability_adj:.2f}")

        # 计算仓位价值
        total_capital = self.engine.capital if self.engine else 1000000
        target_value = total_capital * position_ratio

        # 计算股数 (100 股的整数倍)
        volume = int(target_value / current_price / 100) * 100

        return max(100, volume)

    def get_volatility_adjustment(self, ts_code: str) -> float:
        """
        根据波动率调整仓位

        高波动率 -> 降仓
        低波动率 -> 增仓

        Args:
            ts_code: 股票代码

        Returns:
            仓位调整因子 (0.5-1.5)
        """
        if ts_code not in self.price_history:
            return 1.0

        df = self.price_history[ts_code]
        if len(df) < 30:
            return 1.0

        # 计算 20 日波动率 (收益率标准差)
        returns = df['close'].pct_change()
        volatility = returns.std()

        # 基准波动率 (假设 2% 为基准)
        base_volatility = 0.02
        scaling = 0.5

        # 波动率调整因子
        if base_volatility > 0:
            vol_ratio = volatility / base_volatility
            adjustment = 1.0 / (1.0 + scaling * (vol_ratio - 1.0))
        else:
            adjustment = 1.0

        # 限制调整范围
        adjustment = max(0.5, min(1.5, adjustment))

        return adjustment

    def check_exit_conditions(
        self,
        ts_code: str,
        current_price: float,
        atr: float
    ) -> Optional[Tuple[str, str]]:
        """
        检查出场条件 (v3.0 夏普优化 - 高盈亏比 + 时间止损 + 分级止盈)

        核心思路:
        1. 紧止损 (3.5%) - 快速止损，保护本金
        2. 移动止盈 - 让利润奔跑
        3. 时间止损 - 避免资金占用 (8 日无盈利退出)
        4. 分级止盈 - 部分锁定利润 (v3.0 新增)

        Returns:
            (方向，原因) 或 None
        """
        if ts_code not in self.positions:
            return None

        pos = self.positions[ts_code]
        entry_price = pos['entry_price']
        entry_date = pos.get('entry_date', '')

        # 更新最高价
        if current_price > pos.get('highest_price', 0):
            self.positions[ts_code]['highest_price'] = current_price
        highest_price = self.positions[ts_code].get('highest_price', entry_price)

        # 计算动态止损止盈
        dynamic_sl, dynamic_tp = self.calculate_dynamic_stop_loss_take_profit(ts_code, atr)

        # 当前盈亏比例
        profit_ratio = (current_price - entry_price) / entry_price
        highest_profit = (highest_price - entry_price) / entry_price

        # === 1. 紧止损检查 ===
        if profit_ratio <= -dynamic_sl:
            return ('sell', f'止损 ({profit_ratio:.1%}, SL={-dynamic_sl:.1%})')

        # === 2. 止盈检查 ===
        if profit_ratio >= dynamic_tp:
            return ('sell', f'止盈 ({profit_ratio:.1%}, TP={dynamic_tp:.1%})')

        # === 3. v3.0: 分级止盈 (盈利 8% 后部分锁定利润) ===
        if self.sharpe_optimizer and self.params.use_sharpe_optimization:
            if highest_profit >= self.params.profit_lock_trigger:
                # 计算回撤
                drawdown = (highest_price - current_price) / highest_price
                if drawdown >= 0.03:  # 3% 回撤触发部分止盈
                    return ('sell', f'部分止盈 (盈利{profit_ratio:.1%}, 回撤{drawdown:.1%})')

        # === 4. 移动止损 (盈利超过 10% 后激活) ===
        if highest_profit >= self.params.trailing_stop_trigger:
            # 计算移动止损回撤阈值
            trailing_threshold = self.params.trailing_stop_ratio
            drawdown = (highest_price - current_price) / highest_price
            if drawdown >= trailing_threshold:
                return ('sell', f'移动止损 (回撤{drawdown:.1%})')

        # === 5. 时间止损 (持仓超过 8 日无盈利退出) ===
        if hasattr(self, 'current_date') and entry_date:
            try:
                from datetime import datetime
                entry_dt = datetime.strptime(entry_date, '%Y%m%d')
                current_dt = datetime.strptime(self.current_date, '%Y%m%d')
                holding_days = (current_dt - entry_dt).days
                if holding_days >= self.params.time_stop_days and profit_ratio < self.params.time_stop_profit_threshold:
                    return ('sell', f'时间止损 ({holding_days}日，盈利{profit_ratio:.1%})')
            except:
                pass

        return None

    def calculate_signal_score(
        self,
        golden_cross: bool,
        macd_bullish: bool,
        rsi_ok: bool,
        rsi_oversold: bool,
        bb_signal: str,
        volume_ok: bool,
        trend_ok: bool,
        perfect_trend: bool = False,  # 新增：完美多头排列
        momentum_score: float = 0.0,  # v4.0: 动量因子得分
        money_flow_score: float = 0.0,  # v4.0: 资金流因子得分
        stock_strength: float = 0.5  # v4.0: 股票强度
    ) -> Tuple[bool, float]:
        """
        综合评分系统 (v4.0 胜率优化 - 新增动量 + 资金流因子)

        权重分配 (总分 13.5 分):
        - 均线金叉：2.0 分 (趋势确认最重要)
        - 完美多头排列：额外 +1.5 分 (最强信号)
        - MACD 多头：1.5 分 (动量确认)
        - RSI 健康：0.5 分
        - RSI 超卖：额外 +0.5 分
        - 布林带下轨：1.0 分 (超卖反弹)
        - 成交量放大：1.5 分 (资金确认)
        - 趋势向上：1.5 分
        - v4.0 新增：动量因子：1.5 分 (价格动能)
        - v4.0 新增：资金流向：1.5 分 (主力动向)
        - v4.0 新增：股票强度：1.0 分 (强势股)

        Returns:
            (是否买入，信号强度)
        """
        score = 0.0
        max_score = 13.5  # 最大可能得分 (v4.0 新增因子)

        # 1. 均线金叉 (权重 2.0 - 最重要)
        if golden_cross:
            score += 2.0

        # 1b. 完美多头排列额外加分 (短>中>长)
        if perfect_trend:
            score += 1.5

        # 2. MACD 多头 (权重 1.5 - 动量确认)
        if macd_bullish:
            score += 1.5

        # 3. RSI 健康 (权重 0.5)
        if rsi_ok:
            score += 0.5

        # 4. RSI 超卖额外加分 (权重 0.5) - 与 RSI 健康互斥，取较高者
        if rsi_oversold:
            score += 0.5

        # 5. 布林带下轨 (权重 1.0 - 超卖反弹信号)
        if bb_signal == 'lower':
            score += 1.0

        # 6. 成交量放大 (权重 1.5 - 资金确认)
        if volume_ok:
            score += 1.5

        # 7. 趋势向上 (权重 1.5)
        if trend_ok:
            score += 1.5

        # v4.0: 8. 动量因子 (权重 1.5)
        # momentum_score 范围：-1 到 1，转换为 0-1.5 分
        momentum_points = max(0, min(1.5, (momentum_score + 0.5) * 1.5))
        score += momentum_points

        # v4.0: 9. 资金流向因子 (权重 1.5)
        # money_flow_score 范围：-1 到 1，转换为 0-1.5 分
        flow_points = max(0, min(1.5, (money_flow_score + 0.5) * 1.5))
        score += flow_points

        # 使用动态阈值 (默认 5.0 分，提高信号质量)
        # 增加趋势过滤：趋势向下时不买入 (即使评分高)
        # 完美趋势排列时可以降低阈值要求 (最低 4.5 分)
        effective_threshold = self.params.signal_threshold
        if perfect_trend:
            effective_threshold = max(4.5, self.params.signal_threshold - 0.5)

        # v4.0: 高置信度信号要求
        if self.params.use_win_rate_optimization:
            # 启用胜率优化时，要求更高阈值
            effective_threshold = max(effective_threshold, 6.0)

        buy_signal = score >= effective_threshold and trend_ok
        signal_strength = min(1.0, score / max_score)

        return buy_signal, signal_strength

    def get_signal_factors(
        self,
        golden_cross: bool,
        perfect_trend: bool,
        macd_bullish: bool,
        rsi_ok: bool,
        rsi_oversold: bool,
        bb_signal: str,
        volume_ok: bool,
        trend_ok: bool,
        current_price: float,
        ma_short: float,
        ma_mid: float,
        ma_long: float
    ) -> Dict[str, Any]:
        """
        获取信号因子详情 (用于可视化)

        Returns:
            包含各因子得分和详细信息的字典
        """
        factors = {
            'ma_cross': 2.0 if golden_cross else 0.0,
            'perfect_trend': 1.5 if perfect_trend else 0.0,
            'macd': 1.5 if macd_bullish else 0.0,
            'rsi': 0.5 if (rsi_ok or rsi_oversold) else 0.0,
            'bb': 1.0 if bb_signal == 'lower' else 0.0,
            'volume': 1.5 if volume_ok else 0.0,
            'trend': 1.5 if trend_ok else 0.0,
        }

        total_score = sum(factors.values())
        max_score = 10.5

        # 确定信号方向
        signal_direction = 'buy' if (total_score >= self.params.signal_threshold and trend_ok) else 'none'

        # 生成触发原因
        reasons = []
        if golden_cross:
            reasons.append('均线金叉')
        if perfect_trend:
            reasons.append('完美多头')
        if macd_bullish:
            reasons.append('MACD 多头')
        if rsi_ok or rsi_oversold:
            reasons.append('RSI 健康')
        if bb_signal == 'lower':
            reasons.append('布林带下轨')
        if volume_ok:
            reasons.append('成交量放大')
        if trend_ok:
            reasons.append('趋势向上')

        return {
            'factors': factors,
            'total_score': total_score,
            'max_score': max_score,
            'signal_direction': signal_direction,
            'trigger_reason': ','.join(reasons) if reasons else '无信号',
            'threshold': self.params.signal_threshold,
            'ma_values': {
                'short': ma_short,
                'mid': ma_mid,
                'long': ma_long,
            },
            'price': current_price,
        }

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调 - 恢复原版逻辑"""
        if not self.initialized:
            self.on_init()

        # 保存当前日期用于时间止损
        self.current_date = current_date

        # 更新价格历史
        self.update_price_history(data, current_date)

        signals = []

        for ts_code, bar in data.items():
            # 检查是否有足够数据
            if ts_code not in self.price_history:
                continue

            df = self.price_history[ts_code]
            required_len = self.params.ma_trend * 2
            if len(df) < required_len:
                continue

            close = df['close']
            vol = df['vol']
            current_price = bar.get('close', 0)

            # === 计算技术指标 ===

            # 均线系统
            ma_short = close.rolling(self.params.ma_short).mean()
            ma_mid = close.rolling(self.params.ma_mid).mean()
            ma_long = close.rolling(self.params.ma_long).mean()
            ma_trend = close.rolling(self.params.ma_trend).mean()

            # MACD
            macd_data = calculate_macd(
                close,
                self.params.macd_fast,
                self.params.macd_slow,
                self.params.macd_signal
            )
            dif = macd_data['dif'].iloc[-1] if len(macd_data) > 0 else 0
            dea = macd_data['dea'].iloc[-1] if len(macd_data) > 0 else 0
            macd = macd_data['macd'].iloc[-1] if len(macd_data) > 0 else 0

            # RSI
            rsi = calculate_rsi(close, self.params.rsi_period)
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 0

            # 布林带
            bb_data = calculate_bollinger_bands(
                close,
                self.params.bb_window,
                self.params.bb_num_std
            )
            bb_upper = bb_data['upper'].iloc[-1] if len(bb_data) > 0 else 0
            bb_lower = bb_data['lower'].iloc[-1] if len(bb_data) > 0 else 0
            bb_middle = bb_data['middle'].iloc[-1] if len(bb_data) > 0 else 0

            # 成交量均线
            vol_ma = vol.rolling(self.params.volume_ma_period).mean()

            # === 计算 ATR ===
            atr = self.calculate_atr(df)

            # === v3.0: 夏普优化 - 波动率过滤 ===
            if self.sharpe_optimizer:
                # 更新价格历史到优化器
                self.sharpe_optimizer.update_price_history(ts_code, df)

                # 检查是否因高波动跳过交易
                if self.sharpe_optimizer.should_skip_trade_due_to_volatility(ts_code):
                    strategy_logger.debug(f"{ts_code}: 波动率过高，跳过交易")
                    continue

                # 检查稳定性因子，低稳定性股票降仓处理
                stability_factor = self.sharpe_optimizer.calculate_stability_factor(ts_code)
                if stability_factor < self.params.min_stability_threshold:
                    strategy_logger.debug(f"{ts_code}: 稳定性不足 ({stability_factor:.2f})，降仓处理")

            # === 判断市场状态 ===
            self.market_state = self.determine_market_state(df)

            # === v3.0: 增强市场状态检查 ===
            if self.sharpe_optimizer and self.params.use_sharpe_optimization:
                enhanced_state = self.sharpe_optimizer.check_enhanced_market_state(
                    df, self.market_state.value
                )
                if enhanced_state != self.market_state.value:
                    strategy_logger.debug(f"{ts_code}: 市场状态调整 {self.market_state.value} -> {enhanced_state}")
                    # 更新市场状态用于仓位计算
                    if enhanced_state == 'bear':
                        self.market_state = MarketState.BEAR
                    elif enhanced_state == 'bull':
                        self.market_state = MarketState.BULL
                    else:
                        self.market_state = MarketState.SIDEWAYS

            # === 检查出场条件 (如果已持仓) ===
            if ts_code in self.positions:
                exit_result = self.check_exit_conditions(ts_code, current_price, atr)
                if exit_result:
                    direction, reason = exit_result
                    shares = self.positions[ts_code].get('shares', 1000)
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction=direction,
                        price=current_price,
                        volume=shares,
                        reason=reason
                    ))
                    del self.positions[ts_code]
                    continue

            # === 计算信号评分 ===

            # 1. 均线金叉 (短周期上穿长周期)
            golden_cross = (ma_short.iloc[-2] <= ma_long.iloc[-2] and
                           ma_short.iloc[-1] > ma_long.iloc[-1])

            # 1b. 完美多头排列 (短>中>长，最强趋势信号)
            perfect_trend = (ma_short.iloc[-1] > ma_mid.iloc[-1] > ma_long.iloc[-1] and
                            ma_short.iloc[-1] > ma_short.iloc[-2] and
                            ma_mid.iloc[-1] > ma_mid.iloc[-2])

            # 2. MACD 多头
            macd_bullish = dif > dea and macd > 0

            # 3. RSI 健康 (不在超买/超卖区)
            rsi_ok = (self.params.rsi_oversold < current_rsi < self.params.rsi_overbought)

            # 4. RSI 超卖 (额外加分项)
            rsi_oversold = current_rsi < self.params.rsi_oversold

            # 5. 布林带信号
            bb_signal = 'lower' if current_price <= bb_lower * 1.01 else \
                       ('upper' if current_price >= bb_upper * 0.99 else 'middle')

            # 6. 成交量放大
            current_vol = bar.get('vol', 0)
            current_vol_ma = vol_ma.iloc[-1] if len(vol_ma) > 0 else 0
            volume_ratio = 1.15 if perfect_trend else 1.25
            volume_ok = current_vol > current_vol_ma * volume_ratio if current_vol_ma > 0 else True

            # 6b. 连续成交量确认
            volume_continuous = False
            if len(vol) >= 2 and current_vol_ma > 0:
                prev_vol = vol.iloc[-2] if len(vol) >= 2 else 0
                prev_vol_ma = vol.rolling(self.params.volume_ma_period).mean().iloc[-2] if len(vol) >= self.params.volume_ma_period else 0
                volume_continuous = prev_vol > prev_vol_ma * 1.05 if prev_vol_ma > 0 else True

            # 合并成交量条件
            volume_confirmed = volume_ok if perfect_trend else (volume_ok and volume_continuous)

            # 7. 趋势判断
            trend_ok = current_price > ma_trend.iloc[-1] * (1 + self.params.trend_threshold)

            # v4.0: 8. 动量因子
            momentum_score = 0.0
            if self.win_rate_optimizer:
                self.win_rate_optimizer.update_price_history(ts_code, df)
                momentum_score = self.win_rate_optimizer.calculate_momentum(ts_code)

            # v4.0: 9. 资金流向因子
            money_flow_score = 0.0
            if self.win_rate_optimizer:
                money_flow_score = self.win_rate_optimizer.calculate_money_flow(ts_code)

            # v4.0: 10. 股票强度
            stock_strength = 0.5
            if self.win_rate_optimizer:
                stock_strength = self.win_rate_optimizer.calculate_stock_strength(ts_code)

                # 检查是否因动量不足跳过
                if self.win_rate_optimizer.should_skip_trade_due_to_momentum(ts_code):
                    strategy_logger.debug(f"{ts_code}: 动量不足，跳过交易")
                    continue

                # 检查是否因强度不足过滤
                if self.win_rate_optimizer.should_filter_stock(ts_code):
                    strategy_logger.debug(f"{ts_code}: 股票强度不足，过滤")
                    continue

            # 综合评分 (v4.0 新增动量、资金流、强度因子)
            buy_signal, signal_strength = self.calculate_signal_score(
                golden_cross, macd_bullish, rsi_ok, rsi_oversold, bb_signal,
                volume_confirmed, trend_ok, perfect_trend,
                momentum_score, money_flow_score, stock_strength
            )

            # 获取信号因子详情 (用于可视化)
            signal_factors = self.get_signal_factors(
                golden_cross, perfect_trend, macd_bullish, rsi_ok, rsi_oversold,
                bb_signal, volume_confirmed, trend_ok,
                current_price,
                ma_short.iloc[-1], ma_mid.iloc[-1], ma_long.iloc[-1]
            )

            # === 生成买入信号 ===
            if buy_signal and ts_code not in self.positions:
                volume = self.calculate_position_size(ts_code, signal_strength, current_price)
                if volume >= 100:
                    signals.append(self.generate_signal(
                        ts_code=ts_code,
                        direction='buy',
                        price=current_price,
                        volume=volume,
                        strength=signal_strength,
                        reason=f"综合信号 (强度{signal_strength:.1f}, RSI={current_rsi:.0f})",
                        factors=signal_factors,
                        market_state=self.market_state.value
                    ))
                    # 记录持仓
                    self.positions[ts_code] = {
                        'entry_price': current_price,
                        'highest_price': current_price,
                        'shares': volume,
                        'entry_date': current_date,
                        'partial_sold': False
                    }

        return signals

    def get_positions_summary(self) -> Dict:
        """获取持仓摘要"""
        if not self.positions:
            return {'count': 0, 'total_value': 0}

        total_value = sum(
            pos['shares'] * pos['entry_price']
            for pos in self.positions.values()
        )

        return {
            'count': len(self.positions),
            'total_value': total_value
        }


# 创建策略实例的工厂函数
def create_optimal_strategy(
    stop_loss: float = None,      # 默认使用参数类中的值
    take_profit: float = None,    # 默认使用参数类中的值
    position_ratio: float = None,
    signal_threshold: float = None,  # 信号触发阈值
    aggressive: bool = False,
    mode: str = 'conservative'  # 'conservative'(稳健版 53%) / 'aggressive'(进取版 55%) / 'default'
) -> OptimalStrategy:
    """
    创建最优策略

    Args:
        stop_loss: 止损比例 (默认 4%)
        take_profit: 止盈比例 (默认 35%)
        position_ratio: 基础仓位比例
        signal_threshold: 信号触发阈值 (默认 5.5)
        aggressive: 是否激进模式 (已废弃，使用 mode 参数)
        mode: 配置模式
            - 'conservative': 稳健版 (牛市 53%, 回撤更优)
            - 'aggressive': 进取版 (牛市 55%, 收益更高)
            - 'default': 默认配置

    Returns:
        OptimalStrategy 实例
    """
    # 使用 OptimalStrategyParams 的默认值
    default_params = OptimalStrategyParams()

    if stop_loss is None:
        stop_loss = 0.04  # 默认 4%
    if take_profit is None:
        take_profit = 0.35  # 默认 35%
    if signal_threshold is None:
        signal_threshold = 5.5  # 默认 5.5

    # 根据 mode 设置仓位参数
    if mode == 'aggressive' or mode == 'aggressive_old':
        # 进取版：牛市 55%
        base_pos = 0.35
        max_pos = 0.55
        bear_pos = 0.02
        name_suffix = "进取版 (牛市 55%)"
    elif mode == 'conservative' or mode == 'conservative_53':
        # 稳健版：牛市 53% (推荐)
        base_pos = 0.33
        max_pos = 0.53
        bear_pos = 0.02
        name_suffix = "稳健版 (牛市 53%)"
    else:
        # 默认配置
        base_pos = position_ratio if position_ratio else default_params.base_position_ratio
        max_pos = default_params.max_position_ratio
        bear_pos = default_params.market_bear_max_position
        name_suffix = "default"

    params = OptimalStrategyParams(
        base_stop_loss=stop_loss,
        base_take_profit=take_profit,
        base_position_ratio=base_pos,
        max_position_ratio=max_pos,
        min_position_ratio=0.01,
        market_bear_max_position=bear_pos,
        trailing_stop_trigger=0.15,    # 移动止损触发 15%
        trailing_stop_ratio=0.06,       # 回撤 6%
        signal_threshold=signal_threshold,
        time_stop_days=10,
        time_stop_profit_threshold=0.03,
        use_market_filter=True,
    )
    return OptimalStrategy(name=f"optimal_{name_suffix}", params=params)
