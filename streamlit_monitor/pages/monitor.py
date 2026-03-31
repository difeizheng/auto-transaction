"""
系统监控总览页面
显示系统运行状态、市场状态、数据源状态、今日统计、实时日志
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
    get_system_status_cached,
    get_market_phase_cached,
    get_next_phase_countdown_cached,
    get_data_source_cached,
    get_today_stats_cached,
    get_recent_logs_cached,
    get_account_info_cached,
    get_api_stats_cached,
)
from streamlit_monitor.components import (
    render_running_status,
    render_market_status,
    render_data_source,
    render_alert,
    render_simple_log_viewer,
)


def show():
    """显示系统监控总览页面"""

    # 自动刷新
    st_autorefresh(interval=REFRESH_INTERVAL, key="monitor_refresh")

    # 页面标题
    st.title("📊 系统监控总览")

    # ========== 顶部状态栏 ==========
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        # 系统运行状态
        system_status = get_system_status_cached()
        render_running_status(
            system_status.get('paper_trading_running', False),
            system_status.get('uptime_str', 'N/A')
        )

        # 进程信息
        if system_status.get('paper_trading_running'):
            st.caption(f"日志文件: {system_status.get('latest_log', 'N/A')}")

    with col2:
        # 市场状态
        phase, phase_name = get_market_phase_cached()
        countdown = get_next_phase_countdown_cached()
        render_market_status(phase, phase_name, countdown)

    # ========== 数据源状态 ==========
    st.markdown("---")
    st.subheader("📡 数据源状态")

    data_source = get_data_source_cached()
    render_data_source(
        data_source.get('source', 'Unknown'),
        data_source.get('last_update', '')
    )

    # API 调用统计
    api_stats = get_api_stats_cached()
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Sina 调用", api_stats.get('sina_calls', 0))
    with col2:
        st.metric("腾讯调用", api_stats.get('tencent_calls', 0))
    with col3:
        st.metric("Tushare 调用", api_stats.get('tushare_calls', 0))
    with col4:
        error_count = api_stats.get('errors', 0)
        st.metric("错误数", error_count, delta=-error_count if error_count > 0 else None)

    # ========== 今日统计 ==========
    st.markdown("---")
    st.subheader("📈 今日统计")

    today_stats = get_today_stats_cached()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "今日信号",
            today_stats.get('signals_total', 0),
            delta=f"待执行: {today_stats.get('signals_pending', 0)}"
        )

    with col2:
        st.metric(
            "已执行信号",
            today_stats.get('signals_executed', 0),
        )

    with col3:
        st.metric(
            "今日成交",
            today_stats.get('trades_total', 0),
            delta=f"买: {today_stats.get('trades_buys', 0)} / 卖: {today_stats.get('trades_sells', 0)}"
        )

    with col4:
        # 账户概览
        account = get_account_info_cached()
        st.metric(
            "总资产",
            f"¥{account.get('total_asset', 0):,.0f}",
            delta=f"{account.get('profit_ratio', 0):.1f}%"
        )

    # ========== 系统阶段指示器 ==========
    st.markdown("---")
    st.subheader("⏰ 当前阶段")

    phase_descriptions = {
        'pre_market': "系统处于盘前等待状态，将在 9:30 开盘后开始监控",
        'morning_trading': "早盘交易时段，系统正在监控价格和执行信号",
        'lunch_break': "午休时段，系统暂停实时监控",
        'afternoon_trading': "下午交易时段，系统正在监控价格和执行信号",
        'signal_window': "信号生成窗口（14:50-15:00），系统正在生成次日交易信号",
        'closed': "已收盘，系统进入盘后状态",
        'weekend': "周末休市，系统暂停监控",
    }

    phase, phase_name = get_market_phase_cached()
    description = phase_descriptions.get(phase, "")

    # 显示阶段卡片
    phase_icons = {
        'pre_market': '🌅',
        'morning_trading': '📈',
        'lunch_break': '🍽️',
        'afternoon_trading': '📊',
        'signal_window': '⚡',
        'closed': '🌙',
        'weekend': '📅',
    }

    icon = phase_icons.get(phase, '⏰')

    st.info(f"{icon} **{phase_name}** - {description}")

    # ========== 实时日志 ==========
    st.markdown("---")
    st.subheader("📋 实时日志")

    # 日志类型选择
    log_type = st.selectbox(
        "选择日志类型",
        options=['trader', 'data_collector', 'paper_trading'],
        index=0,
        key="monitor_log_type"
    )

    # 获取并显示日志
    logs = get_recent_logs_cached(log_type, 30)
    render_simple_log_viewer(logs, title=f"{log_type} 日志", lines=25)

    # ========== 刷新时间 ==========
    st.caption(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()