"""
图表组件
提供各种可视化图表
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import List, Dict, Optional


def render_nav_chart(nav_df: pd.DataFrame, benchmark_df: pd.DataFrame = None):
    """渲染净值曲线图"""
    if nav_df.empty:
        st.info("暂无净值数据")
        return

    fig = go.Figure()

    # 策略净值
    fig.add_trace(go.Scatter(
        x=nav_df['date'],
        y=nav_df['nav'],
        mode='lines',
        name='策略净值',
        line=dict(color='#00d2ff', width=2),
        hovertemplate='<b>净值</b>: %{y:.4f}<br><b>日期</b>: %{x}<extra></extra>'
    ))

    # 基准（如果有）
    if benchmark_df is not None and not benchmark_df.empty:
        fig.add_trace(go.Scatter(
            x=benchmark_df['date'],
            y=benchmark_df['nav'],
            mode='lines',
            name='基准',
            line=dict(color='#888', width=1, dash='dash'),
        ))

    fig.update_layout(
        title='净值曲线',
        template='plotly_dark',
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title='日期'),
        yaxis=dict(title='净值'),
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)


def render_drawdown_chart(nav_df: pd.DataFrame):
    """渲染回撤图"""
    if nav_df.empty:
        return

    # 计算回撤
    nav_series = nav_df['nav']
    running_max = nav_series.cummax()
    drawdown = (nav_series - running_max) / running_max * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=nav_df['date'],
        y=drawdown,
        fill='tozeroy',
        mode='lines',
        name='回撤',
        line=dict(color='#ff4444', width=1),
        fillcolor='rgba(255, 68, 68, 0.3)',
    ))

    fig.update_layout(
        title='最大回撤',
        template='plotly_dark',
        height=200,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title='日期'),
        yaxis=dict(title='回撤 (%)'),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_position_pie(positions: List[Dict]):
    """渲染持仓占比饼图"""
    if not positions:
        st.info("暂无持仓")
        return

    labels = [p['ts_code'] for p in positions]
    values = [p['market_value'] for p in positions]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=.4,
        textinfo='label+percent',
        marker=dict(colors=px.colors.sequential.Blues_r),
    )])

    fig.update_layout(
        title='持仓分布',
        template='plotly_dark',
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_pnl_bar(positions: List[Dict]):
    """渲染盈亏柱状图"""
    if not positions:
        return

    fig = go.Figure()

    colors = ['#00C851' if p['profit_loss'] >= 0 else '#ff4444' for p in positions]

    fig.add_trace(go.Bar(
        x=[p['ts_code'] for p in positions],
        y=[p['profit_loss'] for p in positions],
        marker_color=colors,
        text=[f"{'+' if p['profit_loss'] >= 0 else ''}{p['profit_loss']:.0f}" for p in positions],
        textposition='outside',
    ))

    fig.update_layout(
        title='持仓盈亏',
        template='plotly_dark',
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title='股票代码'),
        yaxis=dict(title='盈亏 (元)'),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_signal_timeline(signals_df: pd.DataFrame):
    """渲染信号时间线"""
    if signals_df.empty:
        st.info("暂无信号数据")
        return

    # 按日期聚合
    daily_signals = signals_df.groupby('signal_date').size().reset_index(name='count')

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=daily_signals['signal_date'],
        y=daily_signals['count'],
        marker_color='#33b5e5',
    ))

    fig.update_layout(
        title='每日信号数量',
        template='plotly_dark',
        height=200,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title='日期'),
        yaxis=dict(title='信号数'),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_trade_distribution(trades_df: pd.DataFrame):
    """渲染交易分布"""
    if trades_df.empty:
        return

    # 按方向分组
    direction_counts = trades_df['direction'].value_counts()

    fig = go.Figure(data=[go.Pie(
        labels=['买入', '卖出'] if 'buy' in direction_counts.index else ['卖出', '买入'],
        values=[direction_counts.get('buy', 0), direction_counts.get('sell', 0)],
        hole=.4,
        marker=dict(colors=['#00C851', '#ff4444']),
    )])

    fig.update_layout(
        title='交易方向分布',
        template='plotly_dark',
        height=250,
        margin=dict(l=0, r=0, t=40, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_monthly_returns(nav_df: pd.DataFrame):
    """渲染月度收益"""
    if nav_df.empty:
        return

    # 按月分组计算收益
    nav_df['date'] = pd.to_datetime(nav_df['date'])
    nav_df['month'] = nav_df['date'].dt.to_period('M')

    monthly_returns = nav_df.groupby('month').apply(
        lambda x: (x['nav'].iloc[-1] / x['nav'].iloc[0] - 1) * 100
    ).reset_index(name='return')

    monthly_returns['month'] = monthly_returns['month'].astype(str)

    fig = go.Figure()

    colors = ['#00C851' if r >= 0 else '#ff4444' for r in monthly_returns['return']]

    fig.add_trace(go.Bar(
        x=monthly_returns['month'],
        y=monthly_returns['return'],
        marker_color=colors,
    ))

    fig.update_layout(
        title='月度收益 (%)',
        template='plotly_dark',
        height=250,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title='月份'),
        yaxis=dict(title='收益 (%)'),
    )

    st.plotly_chart(fig, use_container_width=True)