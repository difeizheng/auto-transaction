"""
系统管理页面
显示进程状态、日志查看器、系统控制
"""
import os
import sys
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from streamlit_autorefresh import st_autorefresh

from streamlit_monitor.config import PAGE_CONFIG, REFRESH_INTERVAL, LOG_DIR, PROJECT_ROOT
from streamlit_monitor.utils import (
    get_system_status_cached,
    get_recent_logs_cached,
    get_api_stats_cached,
)
from streamlit_monitor.components import (
    render_log_filter,
    render_alert,
)


def show():
    """显示系统管理页面"""

    # 自动刷新
    st_autorefresh(interval=REFRESH_INTERVAL, key="admin_refresh")

    # 页面标题
    st.title("⚙️ 系统管理")

    # ========== 进程监控 ==========
    st.markdown("---")
    st.subheader("💻 系统架构")

    system_status = get_system_status_cached()

    col1, col2 = st.columns(2)

    with col1:
        # 主进程状态
        if system_status.get('paper_trading_running'):
            st.success("✅ 主进程运行中 (run_paper_trading.py)")
        else:
            st.error("❌ 主进程未运行")

        # 进程详情
        process_info = system_status.get('process_info', {})
        if process_info:
            with st.expander("📊 进程详情"):
                st.json(process_info)

    with col2:
        # 系统信息
        st.metric("Python 进程数", system_status.get('python_processes', 0))
        st.metric("运行时长", system_status.get('uptime_str', 'N/A'))

        # 最新日志文件
        latest_log = system_status.get('latest_log')
        if latest_log:
            st.caption(f"日志文件: `{Path(latest_log).name}`")

    # 后台线程状态表格
    st.markdown("#### 🧵 后台线程状态")

    now = datetime.now()
    current_time = now.time()

    def get_thread_status(thread_name):
        """根据当前时间判断线程状态"""
        if thread_name == 'RealtimePriceCache':
            return '✅ 运行中' if now.weekday() < 5 else '⏸️ 周末休市'
        elif thread_name == 'SignalScheduler':
            if now.weekday() >= 5:
                return '⏸️ 周末休市'
            elif 14 <= current_time.hour < 15 and current_time.minute >= 50:
                return '✅ 信号生成中'
            else:
                return '⏸️ 等待窗口 (14:50-15:00)'
        elif thread_name == 'DailyDataUpdater':
            if now.weekday() >= 5:
                return '⏸️ 周末休市'
            elif 16 <= current_time.hour < 17 and current_time.minute >= 10:
                return '✅ 数据更新中'
            elif current_time.hour >= 17:
                return '✔️ 今日已完成'
            else:
                return '⏸️ 等待窗口 (16:10-17:00)'
        return '❓ 未知'

    threads_data = [
        {
            '线程名称': 'RealtimePriceCache',
            '日志文件': 'data_collector.log',
            '运行时段': '全天 (30秒刷新)',
            '状态': get_thread_status('RealtimePriceCache')
        },
        {
            '线程名称': 'SignalScheduler',
            '日志文件': 'trader.log',
            '运行时段': '14:50-15:00',
            '状态': get_thread_status('SignalScheduler')
        },
        {
            '线程名称': 'DailyDataUpdater',
            '日志文件': 'data_collector.log',
            '运行时段': '16:10-17:00',
            '状态': get_thread_status('DailyDataUpdater')
        }
    ]

    df_threads = pd.DataFrame(threads_data)
    st.dataframe(df_threads, use_container_width=True, hide_index=True)

    st.caption("💡 提示：部分线程仅在特定时间窗口运行，非运行时段无日志输出属于正常现象")

    # ========== 日志查看器 ==========
    st.markdown("---")
    st.subheader("📋 日志查看器")

    # 日志类型选择
    log_types = ['trader', 'data_collector', 'strategy', 'paper_trading']
    log_type = st.selectbox(
        "选择日志类型",
        options=log_types,
        index=0,
        key="admin_log_type"
    )

    # 日志说明
    log_descriptions = {
        'trader': '📝 主进程日志 + 信号调度器（全天 + 14:50-15:00）',
        'data_collector': '📝 实时价格缓存（全天 30秒刷新） + 盘后数据更新（16:10-17:00）',
        'strategy': '📝 策略执行日志（仅在 14:50-15:00 信号生成窗口写入）',
        'paper_trading': '📝 历史会话日志（按时间戳命名的归档文件）'
    }
    st.caption(log_descriptions.get(log_type, ''))

    # 获取日志
    logs = get_recent_logs_cached(log_type, 100)

    # 带筛选的日志查看器
    render_log_filter(logs, key="admin_log_viewer")

    # ========== 系统配置 ==========
    st.markdown("---")
    st.subheader("🔧 系统配置")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **当前配置**
        - 刷新间隔: 30 秒
        - 初始资金: ¥20,000
        - 股票池大小: 44 只
        - **数据源: Tencent (主) / Sina (备)**
        """)

    with col2:
        st.markdown("""
        **数据源优先级**
        1. **腾讯财经 (主)** - 免费, 3-5秒延迟
        2. **Sina 实时行情 (备)** - 免费, 3-5秒延迟
        3. **数据库缓存 (最后)** - 收盘价
        """)

    # ========== 数据库信息 ==========
    st.markdown("---")
    st.subheader("💾 数据库信息")

    db_path = PROJECT_ROOT / "data" / "quant_trading.db"

    if db_path.exists():
        db_size = db_path.stat().st_size / (1024 * 1024)  # MB

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("数据库大小", f"{db_size:.2f} MB")

        with col2:
            st.metric("数据库路径", str(db_path.relative_to(PROJECT_ROOT)))

        with col3:
            # 检查表数量
            import sqlite3
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                conn.close()
                st.metric("数据表数量", table_count)
            except:
                st.metric("数据表数量", "N/A")

    else:
        st.warning("数据库文件不存在")

    # ========== 系统控制 ==========
    st.markdown("---")
    st.subheader("🎮 系统控制")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.success("缓存已清除，数据已刷新")
            st.rerun()

    with col2:
        if st.button("📊 查看原始数据", use_container_width=True):
            st.switch_page("pages/portfolio.py")

    with col3:
        if st.button("📈 查看信号", use_container_width=True):
            st.switch_page("pages/signals.py")

    # ========== 启动命令 ==========
    st.markdown("---")
    st.subheader("📝 启动命令参考")

    st.code("""
# 启动纸交易系统
python run_paper_trading.py

# 启动 Streamlit 监控
streamlit run streamlit_monitor/app.py

# 启动 Web API (旧版)
python web_server.py
""", language="bash")

    # ========== 系统环境 ==========
    st.markdown("---")
    st.subheader("🖥️ 系统环境")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        - **操作系统**: {sys.platform}
        - **Python 版本**: {sys.version.split()[0]}
        - **工作目录**: {os.getcwd()}
        """)

    with col2:
        st.markdown(f"""
        - **项目根目录**: {PROJECT_ROOT}
        - **日志目录**: {LOG_DIR}
        - **配置文件**: config/settings.py
        """)

    # ========== 刷新时间 ==========
    st.markdown(f"""
    <div style="
        text-align: center;
        padding: 10px;
        background: rgba(0, 200, 81, 0.1);
        border-radius: 8px;
        border: 1px solid rgba(0, 200, 81, 0.3);
        margin-top: 20px;
    ">
        <span style="color: #00C851;">🔄 自动刷新中</span> |
        最后更新: {datetime.now().strftime('%H:%M:%S')} |
        刷新间隔: 5 秒
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()