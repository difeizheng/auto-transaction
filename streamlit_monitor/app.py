"""
量化交易系统 - Streamlit 监控面板
主入口文件

使用方法:
    streamlit run streamlit_monitor/app.py

功能:
    - 系统监控总览
    - 账户与持仓
    - 信号与交易
    - 绩效分析
    - 系统管理
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from streamlit_monitor.config import PAGE_CONFIG

# 设置页面配置
st.set_page_config(**PAGE_CONFIG)

# 自定义 CSS
st.markdown("""
<style>
    /* 主题色 */
    :root {
        --primary-color: #00d2ff;
        --secondary-color: #3a7bd5;
        --success-color: #00C851;
        --warning-color: #ffbb33;
        --danger-color: #ff4444;
    }

    /* 隐藏默认页脚 */
    footer {
        visibility: hidden;
    }

    /* 隐藏汉堡菜单 */
    #MainMenu {
        visibility: hidden;
    }

    /* 隐藏 Streamlit 默认的页面标题和导航 */
    header[data-testid="stHeader"] {
        display: none !important;
    }

    /* 隐藏顶部的 app 标题区域 */
    .stAppHeader {
        display: none !important;
    }

    /* 隐藏默认的 sidebar header */
    section[data-testid="stSidebar"] header {
        display: none !important;
    }

    /* ========== 侧边栏样式 ========== */
    /* 侧边栏背景 - 使用较浅的深色 */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e2a3a 0%, #2d3e50 100%);
    }

    /* 侧边栏内容区域 */
    section[data-testid="stSidebar"] > div > div {
        background: transparent;
    }

    /* 侧边栏标题 */
    section[data-testid="stSidebar"] h1 {
        color: #ffffff !important;
        font-size: 1.5rem !important;
        font-weight: bold !important;
        text-shadow: 0 0 10px rgba(0, 210, 255, 0.5);
    }

    /* 侧边栏分隔线 */
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255, 255, 255, 0.2) !important;
    }

    /* Radio 按钮容器 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 10px;
    }

    /* Radio 按钮选项 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        color: #ffffff !important;
        font-size: 1rem !important;
    }

    /* Radio 按钮选中状态 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] [data-checked="true"] {
        background: linear-gradient(90deg, #00d2ff, #3a7bd5) !important;
        border-radius: 8px;
    }

    /* Radio 按钮未选中状态 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] [data-checked="false"] {
        background: rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px;
    }

    /* Radio 按钮悬停效果 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] > div > label:hover {
        background: rgba(0, 210, 255, 0.2) !important;
        border-radius: 8px;
    }

    /* 侧边栏文字 */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] .stCaption {
        color: #e0e0e0 !important;
    }

    /* ========== 主内容区域 ========== */

    /* 按钮样式 */
    .stButton>button {
        background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: bold;
    }

    .stButton>button:hover {
        opacity: 0.9;
    }

    /* 指标卡片样式 */
    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 15px;
        border: 1px solid rgba(255,255,255,0.1);
    }

    /* 数据表格样式 */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }

    /* 选择框样式 */
    .stSelectbox>div>div {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """主函数"""

    # 设置页面标题（覆盖 Streamlit 默认标题）
    st.markdown("""
    <script>
        document.title = "量化交易监控系统";
    </script>
    """, unsafe_allow_html=True)

    # 侧边栏导航
    with st.sidebar:
        st.title("📈 量化交易监控")
        st.markdown("---")

        page = st.radio(
            "导航菜单",
            options=[
                "📊 系统监控总览",
                "💼 账户与持仓",
                "📈 信号与交易",
                "📉 绩效分析",
                "⚙️ 系统管理"
            ],
            index=0,
            label_visibility="collapsed"
        )

        st.markdown("---")

        # 显示版本信息
        st.caption("版本: v2.0 (Streamlit)")
        st.caption("刷新间隔: 5秒")

    # 根据选择显示页面
    if page == "📊 系统监控总览":
        from streamlit_monitor.pages.monitor import show
        show()
    elif page == "💼 账户与持仓":
        from streamlit_monitor.pages.portfolio import show
        show()
    elif page == "📈 信号与交易":
        from streamlit_monitor.pages.signals import show
        show()
    elif page == "📉 绩效分析":
        from streamlit_monitor.pages.performance import show
        show()
    elif page == "⚙️ 系统管理":
        from streamlit_monitor.pages.admin import show
        show()


if __name__ == "__main__":
    main()