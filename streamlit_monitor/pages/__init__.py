"""
Streamlit 监控页面模块
"""
from streamlit_monitor.pages.monitor import show as show_monitor
from streamlit_monitor.pages.portfolio import show as show_portfolio
from streamlit_monitor.pages.signals import show as show_signals
from streamlit_monitor.pages.performance import show as show_performance
from streamlit_monitor.pages.admin import show as show_admin

__all__ = [
    'show_monitor',
    'show_portfolio',
    'show_signals',
    'show_performance',
    'show_admin',
]