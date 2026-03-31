"""
日志解析模块
实时读取日志文件，获取系统运行状态
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from collections import deque
import streamlit as st

from streamlit_monitor.config import LOG_DIR, LOG_FILES


class LogParser:
    """日志解析器"""

    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or LOG_DIR

    def get_latest_paper_trading_log(self) -> Optional[Path]:
        """获取最新的 paper_trading 日志文件"""
        pattern = "paper_trading_*.log"
        files = list(self.log_dir.glob(pattern))

        if not files:
            return None

        # 按修改时间排序
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files[0]

    def tail_file(self, filepath: Path, n: int = 50) -> List[str]:
        """读取文件最后 n 行"""
        if not filepath or not filepath.exists():
            return []

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # 使用 deque 高效读取最后 n 行
                lines = deque(f, maxlen=n)
                return list(lines)
        except Exception as e:
            return [f"读取日志失败: {e}"]

    def parse_log_line(self, line: str) -> Dict:
        """解析单行日志"""
        result = {
            'raw': line,
            'timestamp': '',
            'level': 'INFO',
            'module': '',
            'message': line,
        }

        # 尝试解析标准日志格式
        # 格式: 2026-03-31 14:43:17,652 - trader - INFO - 消息
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s*-\s*(\w+)\s*-\s*(\w+)\s*-\s*(.+)'
        match = re.match(pattern, line)

        if match:
            result['timestamp'] = match.group(1)
            result['module'] = match.group(2)
            result['level'] = match.group(3)
            result['message'] = match.group(4)
        else:
            # 尝试简单格式
            simple_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
            simple_match = re.search(simple_pattern, line)
            if simple_match:
                result['timestamp'] = simple_match.group(1)

        return result

    def get_recent_logs(self, log_type: str = 'trader', n: int = 30) -> List[Dict]:
        """获取最近的日志"""
        if log_type == 'paper_trading':
            filepath = self.get_latest_paper_trading_log()
        else:
            filepath = LOG_FILES.get(log_type)

        if not filepath:
            # 尝试直接在 log_dir 中查找
            filepath = self.log_dir / f"{log_type}.log"

        lines = self.tail_file(filepath, n)
        return [self.parse_log_line(line) for line in lines]

    def get_system_phase_from_logs(self) -> str:
        """从日志推断系统阶段"""
        logs = self.get_recent_logs('trader', 20)

        # 查找最近的阶段标记
        for log in reversed(logs):
            msg = log.get('message', '')

            if '信号生成窗口' in msg:
                return 'signal_window'
            elif '信号执行窗口' in msg:
                return 'signal_execution'
            elif '新交易日' in msg:
                return 'new_day'
            elif '模拟盘状态' in msg:
                return 'monitoring'
            elif '周末休市' in msg:
                return 'weekend'

        return 'unknown'

    def get_data_source_from_logs(self) -> Dict[str, str]:
        """从日志获取数据源状态"""
        logs = self.get_recent_logs('data_collector', 30)

        current_source = 'Unknown'
        last_update = ''

        for log in reversed(logs):
            msg = log.get('message', '')
            timestamp = log.get('timestamp', '')

            if 'Sina' in msg and '获取' in msg:
                current_source = 'Sina'
                last_update = timestamp
                break
            elif '腾讯备用数据' in msg:
                current_source = 'Tencent'
                last_update = timestamp
                break
            elif '数据库缓存' in msg:
                current_source = 'Database'
                last_update = timestamp
                break

        return {
            'source': current_source,
            'last_update': last_update,
        }

    def get_error_count(self, log_type: str = 'trader', minutes: int = 30) -> int:
        """获取最近 N 分钟内的错误数量"""
        logs = self.get_recent_logs(log_type, 100)

        cutoff_time = datetime.now()
        error_count = 0

        for log in logs:
            if log.get('level') == 'ERROR':
                # 尝试解析时间
                ts_str = log.get('timestamp', '')
                if ts_str:
                    try:
                        log_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                        diff = (cutoff_time - log_time).total_seconds() / 60
                        if diff <= minutes:
                            error_count += 1
                    except:
                        pass

        return error_count

    def get_api_stats_from_logs(self) -> Dict[str, int]:
        """从日志获取 API 调用统计"""
        logs = self.get_recent_logs('data_collector', 100)

        sina_calls = 0
        tencent_calls = 0
        tushare_calls = 0
        errors = 0

        for log in logs:
            msg = log.get('message', '')
            level = log.get('level', '')

            if 'Sina' in msg:
                sina_calls += 1
            if '腾讯' in msg:
                tencent_calls += 1
            if 'Tushare' in msg:
                tushare_calls += 1
            if level == 'ERROR':
                errors += 1

        return {
            'sina_calls': sina_calls,
            'tencent_calls': tencent_calls,
            'tushare_calls': tushare_calls,
            'errors': errors,
        }


# 全局实例
log_parser = LogParser()


# ========== 缓存函数 ==========

@st.cache_data(ttl=2)
def get_recent_logs_cached(log_type: str = 'trader', n: int = 30):
    """获取最近日志（缓存）"""
    return log_parser.get_recent_logs(log_type, n)


@st.cache_data(ttl=5)
def get_data_source_cached():
    """获取数据源状态（缓存）"""
    return log_parser.get_data_source_from_logs()


@st.cache_data(ttl=10)
def get_api_stats_cached():
    """获取 API 统计（缓存）"""
    return log_parser.get_api_stats_from_logs()