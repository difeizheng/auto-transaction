"""
数据获取模块
直接从数据库读取数据，确保数据真实性
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import streamlit as st

from streamlit_monitor.config import DATABASE_PATH


class DataFetcher:
    """数据获取器"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DATABASE_PATH

    @contextmanager
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """执行查询"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query(sql, conn, params=params)
        except Exception as e:
            print(f"查询失败: {e}")
            return pd.DataFrame()

    # ========== 系统状态 ==========

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        today = datetime.now().strftime('%Y%m%d')

        # 检查是否有今日活动
        today_trades = self.query("""
            SELECT COUNT(*) as count FROM trades WHERE trade_date = ?
        """, (today,))

        today_signals = self.query("""
            SELECT COUNT(*) as count FROM signals WHERE signal_date = ?
        """, (today,))

        # 检查最新净值记录
        latest_nav = self.query("""
            SELECT nav, date FROM nav_history
            ORDER BY date DESC LIMIT 1
        """)

        return {
            'has_today_activity': (today_trades.iloc[0]['count'] > 0 if not today_trades.empty else False) or
                                  (today_signals.iloc[0]['count'] > 0 if not today_signals.empty else False),
            'today_trades': today_trades.iloc[0]['count'] if not today_trades.empty else 0,
            'today_signals': today_signals.iloc[0]['count'] if not today_signals.empty else 0,
            'latest_nav_date': latest_nav.iloc[0]['date'] if not latest_nav.empty else None,
        }

    # ========== 账户信息 ==========

    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息（从持仓和订单计算）"""
        # 获取持仓市值
        positions = self.get_positions()

        # 计算持仓市值
        position_value = sum(p.get('market_value', 0) for p in positions)

        # 获取可用资金（从最新交易记录推算）
        # 这里需要从 order_manager 的数据库获取
        # 暂时使用净值表
        latest_nav = self.query("""
            SELECT nav, date FROM nav_history
            ORDER BY date DESC LIMIT 1
        """)

        if not latest_nav.empty:
            nav = latest_nav.iloc[0]['nav']
            total_asset = nav * 20000  # 假设初始净值=1，初始资金=20000
        else:
            total_asset = 20000

        available_cash = total_asset - position_value
        total_profit = total_asset - 20000

        return {
            'total_asset': total_asset,
            'available_cash': max(0, available_cash),
            'position_value': position_value,
            'total_profit': total_profit,
            'profit_ratio': (total_profit / 20000) * 100 if total_asset > 0 else 0,
        }

    def get_positions(self) -> List[Dict]:
        """获取持仓信息"""
        # 查询当前持仓（从 positions 表或 trades 计算净持仓）
        df = self.query("""
            SELECT
                ts_code,
                SUM(CASE WHEN direction = 'buy' THEN volume ELSE -volume END) as net_volume,
                AVG(CASE WHEN direction = 'buy' THEN price ELSE NULL END) as avg_cost
            FROM trades
            GROUP BY ts_code
            HAVING net_volume > 0
        """)

        if df.empty:
            return []

        positions = []
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            volume = int(row['net_volume'])
            avg_cost = row['avg_cost'] or 0

            # 获取最新价格
            latest_price = self.get_latest_price(ts_code)
            market_value = volume * latest_price
            profit_loss = (latest_price - avg_cost) * volume
            profit_ratio = ((latest_price / avg_cost) - 1) * 100 if avg_cost > 0 else 0

            positions.append({
                'ts_code': ts_code,
                'volume': volume,
                'avg_cost': avg_cost,
                'current_price': latest_price,
                'market_value': market_value,
                'profit_loss': profit_loss,
                'profit_ratio': profit_ratio,
            })

        return positions

    def get_latest_price(self, ts_code: str) -> float:
        """获取股票最新收盘价"""
        df = self.query("""
            SELECT close FROM daily_quotes
            WHERE ts_code = ?
            ORDER BY trade_date DESC LIMIT 1
        """, (ts_code,))

        if not df.empty:
            return float(df.iloc[0]['close'])
        return 0.0

    # ========== 信号数据 ==========

    def get_signals(self, days: int = 7, status: str = None) -> pd.DataFrame:
        """获取信号历史"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        sql = "SELECT * FROM signals WHERE signal_date >= ?"
        params = [start_date]

        if status:
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY signal_date DESC, created_at DESC"

        return self.query(sql, tuple(params))

    def get_today_pending_signals(self) -> List[Dict]:
        """获取今日待执行信号"""
        today = datetime.now().strftime('%Y%m%d')

        df = self.query("""
            SELECT * FROM signals
            WHERE execute_date = ? AND status = 'pending'
            ORDER BY confidence DESC
        """, (today,))

        if df.empty:
            return []

        return df.to_dict('records')

    def get_signal_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取信号统计"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        df = self.query("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) as expired
            FROM signals
            WHERE signal_date >= ?
        """, (start_date,))

        if df.empty:
            return {'total': 0, 'executed': 0, 'pending': 0, 'expired': 0, 'success_rate': 0}

        row = df.iloc[0]
        total = row['total'] or 0
        executed = row['executed'] or 0

        return {
            'total': total,
            'executed': executed,
            'pending': row['pending'] or 0,
            'expired': row['expired'] or 0,
            'success_rate': (executed / total * 100) if total > 0 else 0,
        }

    # ========== 交易数据 ==========

    def get_trades(self, days: int = 7) -> pd.DataFrame:
        """获取交易历史"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        return self.query("""
            SELECT * FROM trades
            WHERE trade_date >= ?
            ORDER BY trade_date DESC, created_at DESC
        """, (start_date,))

    def get_today_trades(self) -> List[Dict]:
        """获取今日交易"""
        today = datetime.now().strftime('%Y%m%d')

        df = self.query("""
            SELECT * FROM trades
            WHERE trade_date = ?
            ORDER BY created_at DESC
        """, (today,))

        if df.empty:
            return []

        return df.to_dict('records')

    def get_trade_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取交易统计"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        df = self.query("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sells,
                SUM(amount) as total_amount
            FROM trades
            WHERE trade_date >= ?
        """, (start_date,))

        if df.empty:
            return {'total': 0, 'buys': 0, 'sells': 0, 'total_amount': 0}

        row = df.iloc[0]
        return {
            'total': row['total'] or 0,
            'buys': row['buys'] or 0,
            'sells': row['sells'] or 0,
            'total_amount': row['total_amount'] or 0,
        }

    # ========== 绩效数据 ==========

    def get_nav_history(self, days: int = 90) -> pd.DataFrame:
        """获取净值历史"""
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        return self.query("""
            SELECT * FROM nav_history
            WHERE date >= ?
            ORDER BY date ASC
        """, (start_date,))

    def get_performance_metrics(self, days: int = 30) -> Dict[str, Any]:
        """获取绩效指标"""
        nav_df = self.get_nav_history(days)

        if nav_df.empty or len(nav_df) < 2:
            return {
                'current_nav': 1.0,
                'total_return': 0,
                'annualized_return': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'win_rate': 0,
            }

        # 计算收益率
        first_nav = nav_df.iloc[0]['nav']
        last_nav = nav_df.iloc[-1]['nav']
        total_return = (last_nav / first_nav - 1) * 100

        # 计算年化收益
        days_held = len(nav_df)
        annualized_return = ((last_nav / first_nav) ** (252 / max(days_held, 1)) - 1) * 100

        # 计算最大回撤
        nav_series = nav_df['nav']
        running_max = nav_series.cummax()
        drawdown = (nav_series - running_max) / running_max
        max_drawdown = abs(drawdown.min()) * 100

        # 计算夏普比率
        returns = nav_series.pct_change().dropna()
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() * 252) / (returns.std() * (252 ** 0.5))
        else:
            sharpe_ratio = 0

        # 计算胜率
        trades = self.get_trades(days)
        if not trades.empty:
            # 简单计算：盈利交易数 / 总交易数
            win_trades = len(trades[trades.get('profit_loss', 0) > 0]) if 'profit_loss' in trades.columns else 0
            win_rate = (win_trades / len(trades) * 100) if len(trades) > 0 else 0
        else:
            win_rate = 0

        return {
            'current_nav': last_nav,
            'total_return': round(total_return, 2),
            'annualized_return': round(annualized_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'win_rate': round(win_rate, 1),
        }

    # ========== 今日统计 ==========

    def get_today_stats(self) -> Dict[str, Any]:
        """获取今日统计"""
        today = datetime.now().strftime('%Y%m%d')

        # 信号统计
        signals_df = self.query("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM signals
            WHERE signal_date = ?
        """, (today,))

        # 成交统计
        trades_df = self.query("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sells
            FROM trades
            WHERE trade_date = ?
        """, (today,))

        return {
            'signals_total': int(signals_df.iloc[0]['total'] or 0) if not signals_df.empty else 0,
            'signals_executed': int(signals_df.iloc[0]['executed'] or 0) if not signals_df.empty else 0,
            'signals_pending': int(signals_df.iloc[0]['pending'] or 0) if not signals_df.empty else 0,
            'trades_total': int(trades_df.iloc[0]['total'] or 0) if not trades_df.empty else 0,
            'trades_buys': int(trades_df.iloc[0]['buys'] or 0) if not trades_df.empty else 0,
            'trades_sells': int(trades_df.iloc[0]['sells'] or 0) if not trades_df.empty else 0,
        }


# 全局实例
data_fetcher = DataFetcher()


# ========== 缓存函数 ==========

@st.cache_data(ttl=5)
def get_account_info_cached():
    """获取账户信息（缓存）"""
    return data_fetcher.get_account_info()


@st.cache_data(ttl=5)
def get_positions_cached():
    """获取持仓（缓存）"""
    return data_fetcher.get_positions()


@st.cache_data(ttl=5)
def get_signals_cached(days: int = 7, status: str = None):
    """获取信号（缓存）"""
    return data_fetcher.get_signals(days, status)


@st.cache_data(ttl=5)
def get_today_stats_cached():
    """获取今日统计（缓存）"""
    return data_fetcher.get_today_stats()


@st.cache_data(ttl=10)
def get_performance_cached(days: int = 30):
    """获取绩效（缓存）"""
    return data_fetcher.get_performance_metrics(days)


@st.cache_data(ttl=10)
def get_nav_history_cached(days: int = 90):
    """获取净值历史（缓存）"""
    return data_fetcher.get_nav_history(days)