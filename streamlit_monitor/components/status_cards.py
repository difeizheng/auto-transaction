"""
状态卡片组件
提供各种状态显示卡片
"""
import streamlit as st
from streamlit_monitor.config import COLORS


def render_status_card(title: str, value: str, delta: str = None, color: str = None):
    """渲染状态卡片"""
    if color is None:
        color = COLORS['primary']

    container = st.container()
    with container:
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        ">
            <div style="color: #888; font-size: 12px; margin-bottom: 5px;">{title}</div>
            <div style="color: {color}; font-size: 24px; font-weight: bold;">{value}</div>
            {f'<div style="color: {COLORS["success"] if delta and delta.startswith("+") else COLORS["danger"]}; font-size: 12px; margin-top: 5px;">{delta}</div>' if delta else ''}
        </div>
        """, unsafe_allow_html=True)


def render_metric_row(metrics: list, columns: int = 4):
    """
    渲染一行指标卡片

    Args:
        metrics: 指标列表，每个元素是 (title, value, delta, color) 元组
        columns: 列数
    """
    cols = st.columns(columns)

    for i, (col, metric) in enumerate(zip(cols, metrics)):
        if len(metric) >= 2:
            title = metric[0]
            value = metric[1]
            delta = metric[2] if len(metric) > 2 else None
            color = metric[3] if len(metric) > 3 else None

            with col:
                render_status_card(title, value, delta, color)


def render_running_status(is_running: bool, uptime: str = "N/A"):
    """渲染运行状态"""
    color = COLORS['success'] if is_running else COLORS['danger']
    status_text = "● 运行中" if is_running else "○ 已停止"

    st.markdown(f"""
    <div style="
        background: rgba(0,0,0,0.3);
        border-radius: 8px;
        padding: 10px 15px;
        display: inline-block;
    ">
        <span style="color: {color}; font-size: 16px; font-weight: bold;">{status_text}</span>
        <span style="color: #888; font-size: 14px; margin-left: 15px;">运行时长: {uptime}</span>
    </div>
    """, unsafe_allow_html=True)


def render_market_status(phase: str, phase_name: str, countdown: str):
    """渲染市场状态"""
    phase_colors = {
        'pre_market': COLORS['info'],
        'morning_trading': COLORS['success'],
        'lunch_break': COLORS['warning'],
        'afternoon_trading': COLORS['success'],
        'signal_window': COLORS['danger'],
        'closed': COLORS['secondary'],
        'weekend': COLORS['secondary'],
    }

    color = phase_colors.get(phase, COLORS['primary'])

    st.markdown(f"""
    <div style="
        background: rgba(0,0,0,0.3);
        border-radius: 8px;
        padding: 10px 15px;
        display: inline-block;
    ">
        <span style="color: {color}; font-size: 16px; font-weight: bold;">{phase_name}</span>
        <span style="color: #888; font-size: 14px; margin-left: 15px;">{countdown}</span>
    </div>
    """, unsafe_allow_html=True)


def render_data_source(source: str, last_update: str):
    """渲染数据源状态"""
    source_names = {
        'Sina': ('新浪财经', COLORS['success']),
        'Tencent': ('腾讯财经', COLORS['info']),
        'Database': ('数据库缓存', COLORS['warning']),
        'Unknown': ('未知', COLORS['danger']),
    }

    name, color = source_names.get(source, ('未知', COLORS['danger']))

    st.markdown(f"""
    <div style="
        background: rgba(0,0,0,0.2);
        border-radius: 6px;
        padding: 8px 12px;
    ">
        <span style="color: #888; font-size: 12px;">数据源:</span>
        <span style="color: {color}; font-size: 14px; font-weight: bold; margin-left: 8px;">{name}</span>
        <span style="color: #666; font-size: 11px; margin-left: 15px;">最后更新: {last_update or 'N/A'}</span>
    </div>
    """, unsafe_allow_html=True)


def render_alert(message: str, alert_type: str = "warning"):
    """渲染警告框"""
    colors = {
        'success': COLORS['success'],
        'warning': COLORS['warning'],
        'danger': COLORS['danger'],
        'info': COLORS['info'],
    }

    color = colors.get(alert_type, COLORS['warning'])

    st.markdown(f"""
    <div style="
        background: {color}22;
        border-left: 4px solid {color};
        padding: 10px 15px;
        border-radius: 4px;
        margin: 10px 0;
    ">
        <span style="color: {color};">{message}</span>
    </div>
    """, unsafe_allow_html=True)