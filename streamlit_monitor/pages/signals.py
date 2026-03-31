"""
信号与交易页面
显示今日信号、信号历史、成交记录
"""
import streamlit as st
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

from streamlit_monitor.config import PAGE_CONFIG, REFRESH_INTERVAL
from streamlit_monitor.utils import (
    get_signals_cached,
    get_today_stats_cached,
    data_fetcher,
)
from streamlit_monitor.components import (
    render_signal_timeline,
    render_trade_distribution,
)


def show():
    """显示信号与交易页面"""

    # 自动刷新
    st_autorefresh(interval=REFRESH_INTERVAL, key="signals_refresh")

    # 页面标题
    st.title("📈 信号与交易")

    # ========== 今日信号看板 ==========
    st.markdown("---")
    st.subheader("⚡ 今日信号")

    today_stats = get_today_stats_cached()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("信号总数", today_stats.get('signals_total', 0))

    with col2:
        st.metric("已执行", today_stats.get('signals_executed', 0))

    with col3:
        st.metric("待执行", today_stats.get('signals_pending', 0))

    with col4:
        total = today_stats.get('signals_total', 0)
        executed = today_stats.get('signals_executed', 0)
        success_rate = (executed / total * 100) if total > 0 else 0
        st.metric("执行率", f"{success_rate:.1f}%")

    # ========== 今日待执行信号 ==========
    st.markdown("---")
    st.subheader("📋 待执行信号")

    pending_signals = data_fetcher.get_today_pending_signals()

    if not pending_signals:
        st.info("暂无待执行信号")
    else:
        import pandas as pd

        df = pd.DataFrame(pending_signals)

        df_display = df[['ts_code', 'direction', 'signal_date', 'execute_date', 'target_price', 'volume', 'strategy_name', 'status']].copy()
        df_display['target_price'] = df_display['target_price'].apply(lambda x: f"¥{x:.2f}")

        df_display = df_display.rename(columns={
            'ts_code': '股票代码',
            'direction': '方向',
            'signal_date': '信号日期',
            'execute_date': '执行日期',
            'target_price': '目标价',
            'volume': '数量',
            'strategy_name': '策略',
            'status': '状态',
        })

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
        )

    # ========== 信号历史 ==========
    st.markdown("---")
    st.subheader("📜 信号历史")

    # 筛选选项
    col1, col2, col3 = st.columns(3)

    with col1:
        days = st.selectbox(
            "时间范围",
            options=[7, 14, 30, 60],
            index=0,
            key="signal_days"
        )

    with col2:
        status_filter = st.selectbox(
            "信号状态",
            options=['全部', 'pending', 'executed', 'expired'],
            index=0,
            key="signal_status"
        )

    with col3:
        search_code = st.text_input(
            "股票代码",
            placeholder="输入代码搜索...",
            key="signal_search"
        )

    # 获取信号数据
    status = None if status_filter == '全部' else status_filter
    signals_df = get_signals_cached(days, status)

    # 搜索过滤
    if search_code and not signals_df.empty:
        signals_df = signals_df[signals_df['ts_code'].str.contains(search_code.upper())]

    if signals_df.empty:
        st.info("暂无信号数据")
    else:
        # 显示信号表格
        display_df = signals_df[['ts_code', 'direction', 'signal_date', 'execute_date', 'target_price', 'volume', 'status', 'strategy_name']].copy()
        display_df['target_price'] = display_df['target_price'].apply(lambda x: f"¥{x:.2f}")

        display_df = display_df.rename(columns={
            'ts_code': '股票代码',
            'direction': '方向',
            'signal_date': '信号日期',
            'execute_date': '执行日期',
            'target_price': '目标价',
            'volume': '数量',
            'status': '状态',
            'strategy_name': '策略',
        })

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

        # 信号统计图表
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            render_signal_timeline(signals_df)

        with col2:
            # 状态分布
            status_counts = signals_df['status'].value_counts()
            import plotly.graph_objects as go

            fig = go.Figure(data=[go.Pie(
                labels=status_counts.index,
                values=status_counts.values,
                hole=.4,
            )])

            fig.update_layout(
                title='信号状态分布',
                template='plotly_dark',
                height=250,
                margin=dict(l=0, r=0, t=40, b=0),
            )

            st.plotly_chart(fig, use_container_width=True)

    # ========== 成交记录 ==========
    st.markdown("---")
    st.subheader("💹 成交记录")

    trades_days = st.selectbox(
        "成交记录时间范围",
        options=[7, 14, 30],
        index=0,
        key="trades_days"
    )

    trades_df = data_fetcher.get_trades(trades_days)

    if trades_df.empty:
        st.info("暂无成交记录")
    else:
        # 成交表格
        trade_display = trades_df[['ts_code', 'direction', 'price', 'volume', 'amount', 'trade_date']].copy()
        trade_display['price'] = trade_display['price'].apply(lambda x: f"¥{x:.2f}")
        trade_display['amount'] = trade_display['amount'].apply(lambda x: f"¥{x:,.0f}")

        trade_display = trade_display.rename(columns={
            'ts_code': '股票代码',
            'direction': '方向',
            'price': '成交价',
            'volume': '数量',
            'amount': '金额',
            'trade_date': '日期',
        })

        st.dataframe(
            trade_display,
            use_container_width=True,
            hide_index=True,
        )

        # 成交统计
        col1, col2 = st.columns(2)

        with col1:
            render_trade_distribution(trades_df)

        with col2:
            # 每日成交金额
            daily_amount = trades_df.groupby('trade_date')['amount'].sum().reset_index()

            import plotly.graph_objects as go
            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=daily_amount['trade_date'],
                y=daily_amount['amount'],
                marker_color='#33b5e5',
            ))

            fig.update_layout(
                title='每日成交金额',
                template='plotly_dark',
                height=250,
                margin=dict(l=0, r=0, t=40, b=0),
            )

            st.plotly_chart(fig, use_container_width=True)

    # ========== 刷新时间 ==========
    st.caption(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()