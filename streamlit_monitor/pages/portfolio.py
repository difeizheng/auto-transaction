"""
账户与持仓页面
显示账户资金、持仓明细、持仓分布
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from streamlit_monitor.config import PAGE_CONFIG, REFRESH_INTERVAL
from streamlit_monitor.utils import (
    get_account_info_cached,
    get_positions_cached,
)
from streamlit_monitor.components import (
    render_position_pie,
    render_pnl_bar,
)


def show():
    """显示账户与持仓页面"""

    # 自动刷新
    st_autorefresh(interval=REFRESH_INTERVAL, key="portfolio_refresh")

    # 页面标题
    st.title("💼 账户与持仓")

    # ========== 资金概览 ==========
    st.markdown("---")
    st.subheader("💰 资金概览")

    account = get_account_info_cached()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_asset = account.get('total_asset', 0)
        profit_ratio = account.get('profit_ratio', 0)
        st.metric(
            "总资产",
            f"¥{total_asset:,.0f}",
            delta=f"{profit_ratio:.1f}%"
        )

    with col2:
        st.metric(
            "可用资金",
            f"¥{account.get('available_cash', 0):,.0f}",
        )

    with col3:
        st.metric(
            "持仓市值",
            f"¥{account.get('position_value', 0):,.0f}",
        )

    with col4:
        total_profit = account.get('total_profit', 0)
        st.metric(
            "总盈亏",
            f"¥{total_profit:,.0f}",
            delta=f"{profit_ratio:.1f}%"
        )

    # ========== 持仓明细 ==========
    st.markdown("---")
    st.subheader("📊 持仓明细")

    positions = get_positions_cached()

    if not positions:
        st.info("暂无持仓")
    else:
        # 持仓表格
        import pandas as pd

        df = pd.DataFrame(positions)

        # 格式化显示
        df_display = df.copy()
        df_display['avg_cost'] = df_display['avg_cost'].apply(lambda x: f"¥{x:.2f}")
        df_display['current_price'] = df_display['current_price'].apply(lambda x: f"¥{x:.2f}")
        df_display['market_value'] = df_display['market_value'].apply(lambda x: f"¥{x:,.0f}")
        df_display['profit_loss'] = df_display['profit_loss'].apply(lambda x: f"¥{x:+,.0f}")
        df_display['profit_ratio'] = df_display['profit_ratio'].apply(lambda x: f"{x:+.2f}%")

        df_display = df_display.rename(columns={
            'ts_code': '股票代码',
            'volume': '持仓量',
            'avg_cost': '成本价',
            'current_price': '现价',
            'market_value': '市值',
            'profit_loss': '盈亏金额',
            'profit_ratio': '盈亏比例',
        })

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
        )

        # ========== 持仓可视化 ==========
        st.markdown("---")
        st.subheader("📈 持仓分布")

        col1, col2 = st.columns(2)

        with col1:
            render_position_pie(positions)

        with col2:
            render_pnl_bar(positions)

        # 持仓汇总
        st.markdown("---")
        st.subheader("📝 持仓汇总")

        total_market_value = sum(p['market_value'] for p in positions)
        total_profit = sum(p['profit_loss'] for p in positions)
        avg_profit_ratio = sum(p['profit_ratio'] for p in positions) / len(positions) if positions else 0

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("持仓数量", f"{len(positions)} 只")

        with col2:
            st.metric("总市值", f"¥{total_market_value:,.0f}")

        with col3:
            st.metric("平均盈亏", f"{avg_profit_ratio:+.2f}%")

    # ========== 刷新时间 ==========
    st.caption(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()