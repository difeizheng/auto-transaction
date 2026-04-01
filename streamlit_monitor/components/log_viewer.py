"""
日志查看器组件
提供实时日志显示和筛选功能
"""
import streamlit as st
import streamlit.components.v1 as components
from typing import List, Dict


def get_level_style(level: str) -> tuple:
    """获取日志级别的样式"""
    styles = {
        'ERROR': ('🔴', '#ff4444', 'rgba(255, 68, 68, 0.15)'),
        'WARNING': ('🟠', '#ff8800', 'rgba(255, 136, 0, 0.15)'),
        'INFO': ('🟢', '#00C851', 'rgba(0, 200, 81, 0.1)'),
        'DEBUG': ('🔵', '#33b5e5', 'rgba(51, 181, 229, 0.1)'),
    }
    return styles.get(level, ('⚪', '#888888', 'rgba(136, 136, 136, 0.1)'))


def render_log_viewer(logs: List[Dict], max_height: int = 400, auto_scroll: bool = True):
    """
    渲染日志查看器（使用 HTML 组件）

    Args:
        logs: 日志列表
        max_height: 最大高度（像素）
        auto_scroll: 是否自动滚动到底部
    """
    if not logs:
        st.info("暂无日志")
        return

    # 构建日志 HTML 内容
    log_html_lines = []

    for log in logs:
        level = log.get('level', 'INFO')
        timestamp = log.get('timestamp', '')
        module = log.get('module', '')
        message = log.get('message', log.get('raw', ''))

        emoji, level_color, bg_color = get_level_style(level)

        # 构建单行日志 HTML
        log_line = f"""
        <div style="
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            padding: 6px 10px;
            margin: 2px 0;
            border-radius: 4px;
            background: {bg_color};
            border-left: 3px solid {level_color};
            display: flex;
            align-items: flex-start;
            gap: 8px;
        ">
            <span style="color: #666; flex-shrink: 0; min-width: 60px;">{timestamp.split()[-1] if timestamp else '--:--:--'}</span>
            <span style="color: {level_color}; font-weight: bold; flex-shrink: 0;">{emoji} {level:8}</span>
            <span style="color: #888; flex-shrink: 0; min-width: 80px;">[{module:12}]</span>
            <span style="color: #e0e0e0; flex: 1; word-break: break-word;">{message}</span>
        </div>
        """
        log_html_lines.append(log_line)

    # 完整的日志容器
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: #1a1a2e;
            }}
        </style>
    </head>
    <body>
        <div id="logContainer" style="
            background: #1a1a2e;
            border-radius: 8px;
            padding: 10px;
            max-height: {max_height}px;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.1);
            font-family: monospace;
        ">
            {''.join(log_html_lines)}
        </div>
        <script>
        window.onload = function() {{
            var container = document.getElementById('logContainer');
            if (container && {str(auto_scroll).lower()}) {{
                container.scrollTop = container.scrollHeight;
            }}
        }};
        </script>
    </body>
    </html>
    """

    # 使用 st.components.v1.html 确保 HTML 正确渲染
    components.html(full_html, height=max_height + 50, scrolling=True)


def render_log_stats(logs: List[Dict]):
    """渲染日志统计"""
    if not logs:
        return

    # 统计各级别数量
    counts = {'ERROR': 0, 'WARNING': 0, 'INFO': 0, 'DEBUG': 0}
    for log in logs:
        level = log.get('level', 'INFO')
        if level in counts:
            counts[level] += 1

    cols = st.columns(4)

    styles = {
        'ERROR': ('🔴 错误', '#ff4444'),
        'WARNING': ('🟠 警告', '#ff8800'),
        'INFO': ('🟢 信息', '#00C851'),
        'DEBUG': ('🔵 调试', '#33b5e5'),
    }

    for i, (level, (label, color)) in enumerate(styles.items()):
        with cols[i]:
            count = counts[level]
            st.markdown(f"""
            <div style="
                text-align: center;
                padding: 10px;
                background: rgba(255,255,255,0.05);
                border-radius: 8px;
                border: 1px solid {color}40;
            ">
                <div style="color: {color}; font-size: 12px;">{label}</div>
                <div style="color: {color}; font-size: 24px; font-weight: bold;">{count}</div>
            </div>
            """, unsafe_allow_html=True)


def render_log_filter(logs: List[Dict], key: str = "log_filter"):
    """
    带筛选功能的日志查看器

    Args:
        logs: 日志列表
        key: 组件唯一键
    """
    if not logs:
        st.info("暂无日志")
        return

    # 筛选选项
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        level_filter = st.selectbox(
            "日志级别",
            options=['全部', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
            key=f"{key}_level"
        )

    with col2:
        search_keyword = st.text_input(
            "搜索关键词",
            placeholder="输入关键词过滤...",
            key=f"{key}_search"
        )

    with col3:
        auto_scroll = st.checkbox(
            "自动滚动",
            value=True,
            key=f"{key}_auto_scroll",
            help="开启后，每次刷新自动显示最新日志"
        )

    # 应用筛选
    filtered_logs = logs

    if level_filter != '全部':
        filtered_logs = [log for log in logs if log.get('level') == level_filter]

    if search_keyword:
        filtered_logs = [
            log for log in filtered_logs
            if search_keyword.lower() in log.get('message', '').lower()
            or search_keyword.lower() in log.get('raw', '').lower()
        ]

    # 显示统计
    render_log_stats(filtered_logs)

    # 显示日志数量
    st.caption(f"显示 {len(filtered_logs)} 条日志")

    # 显示日志
    render_log_viewer(
        filtered_logs[-50:] if len(filtered_logs) > 50 else filtered_logs,
        auto_scroll=auto_scroll
    )


def render_simple_log_viewer(logs: List[Dict], title: str = "实时日志", lines: int = 20):
    """
    简洁的日志查看器

    Args:
        logs: 日志列表
        title: 标题
        lines: 显示行数
    """
    st.subheader(title)

    if not logs:
        st.info("暂无日志")
        return

    # 只显示最近的日志
    recent_logs = logs[-lines:] if len(logs) > lines else logs

    render_log_viewer(recent_logs, max_height=300)