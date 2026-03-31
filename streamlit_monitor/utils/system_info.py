"""
系统信息模块
获取进程状态、系统资源等信息
"""
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess
import streamlit as st

from streamlit_monitor.config import LOG_DIR


class SystemInfo:
    """系统信息获取器"""

    def __init__(self):
        self.is_windows = platform.system() == 'Windows'

    def get_python_processes(self) -> List[Dict]:
        """获取所有 Python 进程"""
        processes = []

        try:
            if self.is_windows:
                # Windows: 使用 tasklist
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, encoding='gbk', errors='ignore'
                )

                for line in result.stdout.strip().split('\n'):
                    if line and 'python.exe' in line.lower():
                        parts = line.split('","')
                        if len(parts) >= 5:
                            pid = parts[1].replace('"', '')
                            mem = parts[4].replace('"', '').replace(',', '').replace(' K', '')
                            try:
                                processes.append({
                                    'pid': int(pid),
                                    'name': 'python.exe',
                                    'memory_kb': int(mem) if mem.isdigit() else 0,
                                })
                            except ValueError:
                                pass
            else:
                # Linux/Mac: 使用 ps
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True, text=True
                )

                for line in result.stdout.strip().split('\n'):
                    if 'python' in line and 'grep' not in line:
                        parts = line.split()
                        if len(parts) >= 6:
                            try:
                                processes.append({
                                    'pid': int(parts[1]),
                                    'name': parts[10] if len(parts) > 10 else 'python',
                                    'cpu': float(parts[2]),
                                    'memory_kb': int(parts[5]),
                                })
                            except (ValueError, IndexError):
                                pass
        except Exception as e:
            print(f"获取进程列表失败: {e}")

        return processes

    def find_paper_trading_process(self) -> Optional[Dict]:
        """查找纸交易进程"""
        processes = self.get_python_processes()

        # 尝试通过日志文件找到进程
        latest_log = self.get_latest_paper_trading_log()
        if latest_log:
            # 检查日志文件是否正在被写入
            stat = latest_log.stat()
            now = datetime.now().timestamp()
            # 如果日志在最近 60 秒内有更新，说明进程正在运行
            if now - stat.st_mtime < 60:
                return {
                    'status': 'running',
                    'log_file': str(latest_log),
                    'last_update': datetime.fromtimestamp(stat.st_mtime).strftime('%H:%M:%S'),
                }

        # 通过进程命令行查找
        for proc in processes:
            # 这里可以添加更多检测逻辑
            pass

        return None

    def get_latest_paper_trading_log(self) -> Optional[Path]:
        """获取最新的纸交易日志"""
        pattern = "paper_trading_*.log"
        files = list(LOG_DIR.glob(pattern))

        if not files:
            return None

        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files[0]

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        # 检查进程
        pt_process = self.find_paper_trading_process()

        # 获取最新日志
        latest_log = self.get_latest_paper_trading_log()

        # 计算运行时长
        uptime = None
        if latest_log:
            try:
                # 从日志文件名解析启动时间
                # paper_trading_20260331_144316.log
                filename = latest_log.stem
                parts = filename.split('_')
                if len(parts) >= 4:
                    date_str = parts[2]
                    time_str = parts[3]
                    start_time = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H%M%S")
                    uptime = datetime.now() - start_time
            except:
                pass

        return {
            'paper_trading_running': pt_process is not None,
            'process_info': pt_process,
            'latest_log': str(latest_log) if latest_log else None,
            'uptime': uptime,
            'uptime_str': self.format_uptime(uptime) if uptime else 'N/A',
            'python_processes': len(self.get_python_processes()),
        }

    def format_uptime(self, delta) -> str:
        """格式化运行时长"""
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_market_phase(self) -> Tuple[str, str]:
        """获取当前市场阶段"""
        from datetime import time

        now = datetime.now()
        current_time = now.time()

        # 周末
        if now.weekday() >= 5:
            return "weekend", "周末休市"

        # 盘前
        if current_time < time(9, 30):
            return "pre_market", "盘前等待"

        # 早盘
        if time(9, 30) <= current_time < time(11, 30):
            return "morning_trading", "早盘交易"

        # 午休
        if time(11, 30) <= current_time < time(13, 0):
            return "lunch_break", "午休"

        # 下午交易
        if time(13, 0) <= current_time < time(14, 50):
            return "afternoon_trading", "下午交易"

        # 信号生成窗口
        if time(14, 50) <= current_time < time(15, 0):
            return "signal_window", "信号生成窗口"

        # 收盘后
        return "closed", "已收盘"

    def get_next_phase_countdown(self) -> str:
        """获取下一阶段倒计时"""
        from datetime import time

        now = datetime.now()
        current_time = now.time()

        if now.weekday() >= 5:
            # 周末，计算到周一开盘
            days_until_monday = 7 - now.weekday()
            return f"距离周一开盘: {days_until_monday} 天"

        if current_time < time(9, 30):
            # 盘前，计算到开盘
            target = datetime(now.year, now.month, now.day, 9, 30)
            delta = target - now
            return f"距离开盘: {self.format_countdown(delta)}"

        if time(9, 30) <= current_time < time(11, 30):
            # 早盘，计算到午休
            target = datetime(now.year, now.month, now.day, 11, 30)
            delta = target - now
            return f"距离午休: {self.format_countdown(delta)}"

        if time(11, 30) <= current_time < time(13, 0):
            # 午休，计算到下午开盘
            target = datetime(now.year, now.month, now.day, 13, 0)
            delta = target - now
            return f"距离下午盘: {self.format_countdown(delta)}"

        if time(13, 0) <= current_time < time(14, 50):
            # 下午交易，计算到信号生成窗口
            target = datetime(now.year, now.month, now.day, 14, 50)
            delta = target - now
            return f"距离信号生成: {self.format_countdown(delta)}"

        if time(14, 50) <= current_time < time(15, 0):
            # 信号生成窗口，计算到收盘
            target = datetime(now.year, now.month, now.day, 15, 0)
            delta = target - now
            return f"距离收盘: {self.format_countdown(delta)}"

        # 收盘后
        return "今日已收盘"

    def format_countdown(self, delta) -> str:
        """格式化倒计时"""
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "已开始"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}小时{minutes}分"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"


# 全局实例
system_info = SystemInfo()


# ========== 缓存函数 ==========

@st.cache_data(ttl=3)
def get_system_status_cached():
    """获取系统状态（缓存）"""
    return system_info.get_system_status()


@st.cache_data(ttl=3)
def get_market_phase_cached():
    """获取市场阶段（缓存）"""
    return system_info.get_market_phase()


@st.cache_data(ttl=3)
def get_next_phase_countdown_cached():
    """获取下一阶段倒计时（缓存）"""
    return system_info.get_next_phase_countdown()