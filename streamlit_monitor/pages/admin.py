"""
系统管理页面
显示进程状态、日志查看器、系统控制
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from streamlit_monitor.config import PAGE_CONFIG, REFRESH_INTERVAL, LOG_DIR
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
    st.subheader("💻 进程状态")

    system_status = get_system_status_cached()

    col1, col2 = st.columns(2)

    with col1:
        # 纸交易进程状态
        if system_status.get('paper_trading_running'):
            st.success("✅ 纸交易进程运行中")
        else:
            st.error("❌ 纸交易进程未运行")

        # 进程详情
        process_info = system_status.get('process_info', {})
        if process_info:
            st.json(process_info)

    with col2:
        # 系统信息
        st.metric("Python 进程数", system_status.get('python_processes', 0))
        st.metric("运行时长", system_status.get('uptime_str', 'N/A'))

        # 最新日志文件
        latest_log = system_status.get('latest_log')
        if latest_log:
            st.caption(f"日志文件: `{Path(latest_log).name}`")

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
        - 数据源: Sina (主) / Tencent (备)
        """)

    with col2:
        st.markdown("""
        **数据源优先级**
        1. Sina 实时行情 (免费, 3-5秒延迟)
        2. 腾讯财经 (免费, 3-5秒延迟)
        3. 数据库缓存 (收盘价)
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
    st.caption(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    st.set_page_config(**PAGE_CONFIG)
    show()