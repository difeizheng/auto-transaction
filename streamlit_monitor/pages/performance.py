"""
绩效分析页面
显示净值曲线、收益指标、风险指标
"""
import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from streamlit_monitor.config import PAGE_CONFIG, REFRESH_INTERVAL
from streamlit_monitor.utils import (
    get_performance_cached,
    get_nav_history_cached,
)
from streamlit_monitor.components import (
    render_nav_chart,
    render_drawdown_chart,
    render_monthly_returns,
)


def show():
    """显示绩效分析页面"""

    # 自动刷新（绩效数据刷新频率可以低一些）
    st_autorefresh(interval=REFRESH_INTERVAL * 2, key="performance_refresh")

    # 页面标题
    st.title("📉 绩效分析")

    # ========== 绩效指标卡片 ==========
    st.markdown("---")
    st.subheader("📊 核心指标")

    # 时间范围选择
    days = st.selectbox(
        "统计周期",
        options=[30, 60, 90, 180],
        index=2,
        key="perf_days"
    )

    metrics = get_performance_cached(days)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "当前净值",
            f"{metrics.get('current_nav', 1):.4f}",
        )
        st.metric(
            "累计收益",
            f"{metrics.get('total_return', 0):.2f}%",
        )

    with col2:
        st.metric(
            "年化收益",
            f"{metrics.get('annualized_return', 0):.2f}%",
        )
        st.metric(
            "夏普比率",
            f"{metrics.get('sharpe_ratio', 0):.2f}",
        )

    with col3:
        st.metric(
            "最大回撤",
            f"{metrics.get('max_drawdown', 0):.2f}%",
            delta=-metrics.get('max_drawdown', 0) if metrics.get('max_drawdown', 0) > 0 else None,
        )
        st.metric(
            "胜率",
            f"{metrics.get('win_rate', 0):.1f}%",
        )

    # ========== 净值曲线 ==========
    st.markdown("---")
    st.subheader("📈 净值曲线")

    nav_days = st.selectbox(
        "净值曲线周期",
        options=[30, 60, 90, 180],
        index=2,
        key="nav_days"
    )

    nav_df = get_nav_history_cached(nav_days)

    if nav_df.empty:
        st.warning("暂无净值数据，请确保系统已运行并记录净值")
    else:
        render_nav_chart(nav_df)

        # ========== 回撤分析 ==========
        st.markdown("---")
        st.subheader("📉 回撤分析")

        render_drawdown_chart(nav_df)

        # ========== 月度收益 ==========
        st.markdown("---")
        st.subheader("📅 月度收益")

        render_monthly_returns(nav_df)

    # ========== 风险指标详解 ==========
    st.markdown("---")
    st.subheader("⚠️ 风险指标详解")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **收益指标**
        - **累计收益**: 从开始到现在的总收益率
        - **年化收益**: 按年化计算的收益率，便于与其他投资比较
        - **夏普比率**: 风险调整后收益，>1 为良好，>2 为优秀
        """)

    with col2:
        st.markdown("""
        **风险指标**
        - **最大回撤**: 从峰值到谷值的最大跌幅，越小越好
        - **胜率**: 盈利交易占总交易的比例
        - **波动率**: 收益的波动程度
        """)

    # ========== 收益分布 ==========
    if not nav_df.empty and len(nav_df) > 10:
        st.markdown("---")
        st.subheader("📊 日收益分布")

        import pandas as pd
        import plotly.graph_objects as go

        # 计算日收益率
        nav_df['daily_return'] = nav_df['nav'].pct_change() * 100
        returns = nav_df['daily_return'].dropna()

        fig = go.Figure()

        fig.add_trace(go.Histogram(
            x=returns,
            nbinsx=30,
            marker_color='#33b5e5',
            opacity=0.75,
        ))

        fig.update_layout(
            title='日收益率分布',
            template='plotly_dark',
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            xaxis=dict(title='日收益率 (%)'),
            yaxis=dict(title='频数'),
        )

        st.plotly_chart(fig, use_container_width=True)

        # 统计信息
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("平均日收益", f"{returns.mean():.3f}%")

        with col2:
            st.metric("收益标准差", f"{returns.std():.3f}%")

        with col3:
            positive_days = len(returns[returns > 0])
            st.metric("正收益天数", positive_days)

        with col4:
            negative_days = len(returns[returns < 0])
            st.metric("负收益天数", negative_days)

    # ========== 刷新时间 ==========
    st.caption(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()