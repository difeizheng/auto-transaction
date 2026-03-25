"""
量化交易系统 - Web 监控界面
使用 FastAPI 提供 REST API 和 HTML 界面
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uvicorn
import json

from src.strategy.optimal_strategy import create_optimal_strategy
from src.strategy.enhanced_ma import EnhancedMaCrossoverStrategy
from src.backtest.engine import BacktestEngine
from src.data_collector.data_manager import data_manager
from src.trader.broker_api import PaperBroker
from src.trader.risk_control import RiskController
from src.utils.database import db

app = FastAPI(title="量化交易系统", version="1.0.0")


# === 数据模型 ===

class SystemStatus(BaseModel):
    status: str
    start_time: str
    uptime_seconds: int
    active_strategy: str
    stock_pool_size: int
    data_bars: int


class PositionInfo(BaseModel):
    ts_code: str
    volume: int
    avg_cost: float
    current_price: float
    market_value: float
    profit_loss: float
    profit_ratio: float


class AccountInfo(BaseModel):
    total_assets: float
    available_cash: float
    position_value: float
    total_profit: float
    total_profit_ratio: float


class TradeRecord(BaseModel):
    ts_code: str
    direction: str
    price: float
    volume: int
    timestamp: str
    profit_loss: Optional[float] = None


# === 全局状态 ===

system_start_time = datetime.now()
paper_broker: Optional[PaperBroker] = None
current_strategy = None
stock_pool = []


# === HTML 界面 ===

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>量化交易系统监控</title>
    <!-- ECharts 图表库 -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            text-align: center;
            padding: 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5em;
            margin-bottom: 30px;
        }
        /* 导航栏 */
        .nav {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 30px;
        }
        .nav-btn {
            background: rgba(0,210,255,0.1);
            color: #00d2ff;
            border: 1px solid rgba(0,210,255,0.3);
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.2s;
        }
        .nav-btn:hover {
            background: rgba(0,210,255,0.2);
            transform: scale(1.05);
        }
        .nav-btn.active {
            background: linear-gradient(90deg, #3a7bd5, #00d2ff);
            color: white;
        }
        .page { display: none; }
        .page.active { display: block; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        .card h2 {
            color: #00d2ff;
            margin-bottom: 20px;
            font-size: 1.3em;
            border-bottom: 1px solid rgba(0,210,255,0.3);
            padding-bottom: 10px;
        }
        .stat-item {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .stat-label { color: #888; }
        .stat-value { font-weight: bold; color: #fff; }
        .stat-value.positive { color: #00ff88; }
        .stat-value.negative { color: #ff4757; }
        .btn {
            background: linear-gradient(90deg, #3a7bd5, #00d2ff);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: transform 0.2s;
            margin: 5px;
        }
        .btn:hover { transform: scale(1.05); }
        .btn-danger {
            background: linear-gradient(90deg, #ff416c, #ff4b2b);
        }
        .btn-success {
            background: linear-gradient(90deg, #11998e, #38ef7d);
        }
        .table {
            width: 100%;
            border-collapse: collapse;
        }
        .table th, .table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .table th {
            background: rgba(0,210,255,0.1);
            color: #00d2ff;
        }
        .table tr:hover {
            background: rgba(255,255,255,0.05);
        }
        .refresh-info {
            text-align: center;
            color: #666;
            margin-top: 20px;
        }
        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.85em;
        }
        .badge-running { background: rgba(0,255,136,0.2); color: #00ff88; }
        .badge-stopped { background: rgba(255,71,87,0.2); color: #ff4757; }
        /* 配置页面样式 */
        .config-section {
            margin-bottom: 25px;
        }
        .config-section h3 {
            color: #00d2ff;
            margin-bottom: 15px;
            font-size: 1.1em;
            border-left: 3px solid #00d2ff;
            padding-left: 10px;
        }
        .config-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 15px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .config-item .label { color: #aaa; }
        .config-item .value { color: #00ff88; font-family: monospace; }
        .config-item .value.warning { color: #ffa500; }
        .config-item .value.error { color: #ff4757; }
        .tag {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            margin-right: 5px;
            margin-bottom: 5px;
        }
        .tag-blue { background: rgba(0,210,255,0.2); color: #00d2ff; }
        .tag-green { background: rgba(0,255,136,0.2); color: #00ff88; }
        .tag-orange { background: rgba(255,165,0,0.2); color: #ffa500; }
        .tag-red { background: rgba(255,71,87,0.2); color: #ff4757; }
        .tag-purple { background: rgba(138,43,226,0.2); color: #8a2be2; }
        #equity-chart {
            width: 100%;
            height: 300px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            margin-top: 15px;
        }
        /* 可视化页面样式 */
        .chart-container {
            width: 100%;
            height: 350px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        .stock-health-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .health-bar {
            flex: 1;
            margin: 0 15px;
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        .health-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }
        .health-fill.bull { background: linear-gradient(90deg, #00ff88, #00d2ff); }
        .health-fill.sideways { background: linear-gradient(90deg, #ffd700, #ffa500); }
        .health-fill.bear { background: linear-gradient(90deg, #ff4757, #ff6b6b); }
        .health-fill.unknown { background: linear-gradient(90deg, #888, #666); }
        .stock-code {
            font-weight: bold;
            color: #fff;
            min-width: 100px;
        }
        .health-score {
            min-width: 60px;
            text-align: right;
            font-weight: bold;
        }
        .health-score.good { color: #00ff88; }
        .health-score.normal { color: #ffd700; }
        .health-score.bad { color: #ff4757; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 量化交易系统监控</h1>

        <!-- 导航栏 -->
        <div class="nav">
            <button class="nav-btn active" onclick="showPage('monitor')">📈 实时监控</button>
            <button class="nav-btn" onclick="showPage('dashboard')">📊 可视化仪表板</button>
            <button class="nav-btn" onclick="showPage('stock-pool')">🔍 股票池监控</button>
            <button class="nav-btn" onclick="showPage('history')">📜 监控历史</button>
            <button class="nav-btn" onclick="showPage('config')">⚙️ 系统配置</button>
        </div>

        <!-- 监控页面 -->
        <div id="page-monitor" class="page active">

        <!-- 系统状态卡片 -->
        <div class="grid">
            <div class="card">
                <h2>🖥️ 系统状态</h2>
                <div class="stat-item">
                    <span class="stat-label">服务状态</span>
                    <span class="stat-value"><span class="badge badge-running">运行中</span></span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">启动时间</span>
                    <span class="stat-value" id="start-time">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">运行时长</span>
                    <span class="stat-value" id="uptime">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">当前策略</span>
                    <span class="stat-value" id="strategy">-</span>
                </div>
            </div>

            <div class="card">
                <h2>💰 账户信息</h2>
                <div class="stat-item">
                    <span class="stat-label">总资产</span>
                    <span class="stat-value" id="total-assets">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">可用资金</span>
                    <span class="stat-value" id="available-cash">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">持仓市值</span>
                    <span class="stat-value" id="position-value">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">总盈亏</span>
                    <span class="stat-value" id="total-profit">-</span>
                </div>
            </div>

            <div class="card">
                <h2>📈 股票池</h2>
                <div class="stat-item">
                    <span class="stat-label">股票数量</span>
                    <span class="stat-value" id="stock-count">-</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">数据 K 线数</span>
                    <span class="stat-value" id="data-bars">-</span>
                </div>
                <div style="margin-top: 15px;">
                    <button class="btn" onclick="refreshData()">🔄 刷新数据</button>
                    <button class="btn btn-success" onclick="runBacktest()">📊 运行回测</button>
                </div>
            </div>
        </div>

        <!-- 持仓信息 -->
        <div class="card" style="margin-bottom: 20px;">
            <h2>📋 持仓信息</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>股票代码</th>
                        <th>持仓数量</th>
                        <th>成本价</th>
                        <th>当前价</th>
                        <th>市值</th>
                        <th>盈亏金额</th>
                        <th>盈亏比例</th>
                    </tr>
                </thead>
                <tbody id="position-table">
                    <tr><td colspan="7" style="text-align:center;color:#666;">暂无持仓</td></tr>
                </tbody>
            </table>
        </div>

        <!-- 交易记录 -->
        <div class="card">
            <h2>📝 交易记录</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>股票代码</th>
                        <th>方向</th>
                        <th>价格</th>
                        <th>数量</th>
                        <th>盈亏</th>
                    </tr>
                </thead>
                <tbody id="trade-table">
                    <tr><td colspan="6" style="text-align:center;color:#666;">暂无交易记录</td></tr>
                </tbody>
            </table>
        </div>

        <div class="refresh-info">
            数据每 5 秒自动刷新 | 最后更新：<span id="last-update">-</span>
        </div>
    </div>
</div>

        <!-- 可视化仪表板页面 -->
        <div id="page-dashboard" class="page">
            <div class="grid">
                <!-- 资金曲线图 -->
                <div class="card" style="grid-column: span 2;">
                    <h2>📈 资金曲线</h2>
                    <div id="equity-chart" class="chart-container"></div>
                </div>

                <!-- 市场状态指示器 -->
                <div class="card">
                    <h2>🌍 市场状态</h2>
                    <div id="market-state-chart" class="chart-container" style="height: 250px;"></div>
                    <div style="margin-top: 15px; display: flex; justify-content: space-around; text-align: center;">
                        <div>
                            <div style="color: #00ff88; font-size: 1.5em;" id="bull-count">-</div>
                            <div style="color: #888; font-size: 0.9em;">牛市次数</div>
                        </div>
                        <div>
                            <div style="color: #ffd700; font-size: 1.5em;" id="sideways-count">-</div>
                            <div style="color: #888; font-size: 0.9em;">震荡市次数</div>
                        </div>
                        <div>
                            <div style="color: #ff4757; font-size: 1.5em;" id="bear-count">-</div>
                            <div style="color: #888; font-size: 0.9em;">熊市次数</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 股票池健康度 -->
            <div class="card" style="margin-bottom: 20px;">
                <h2>💪 股票池健康度</h2>
                <div id="stock-health-container">
                    <!-- 由 JS 动态填充 -->
                </div>
            </div>

            <!-- 信号因子雷达图 -->
            <div class="grid">
                <div class="card">
                    <h2>🎯 最新信号因子分析</h2>
                    <div id="factors-radar-chart" class="chart-container" style="height: 300px;"></div>
                    <div style="text-align: center; margin-top: 15px;">
                        <div style="font-size: 1.2em; color: #00d2ff;">
                            当前得分：<span id="current-score" style="font-weight: bold;">-</span> / 10.5
                        </div>
                        <div style="margin-top: 10px;">
                            <span id="signal-threshold-badge" class="tag tag-blue">阈值 5.5</span>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2>📊 信号统计</h2>
                    <div style="padding: 20px;">
                        <div class="stat-item" style="padding: 15px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span class="stat-label">总监控次数</span>
                            <span class="stat-value" id="total-monitors">-</span>
                        </div>
                        <div class="stat-item" style="padding: 15px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span class="stat-label">买入信号总数</span>
                            <span class="stat-value" style="color: #00ff88;" id="total-buy-signals">-</span>
                        </div>
                        <div class="stat-item" style="padding: 15px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span class="stat-label">卖出信号总数</span>
                            <span class="stat-value" style="color: #ff4757;" id="total-sell-signals">-</span>
                        </div>
                        <div class="stat-item" style="padding: 15px 0;">
                            <span class="stat-label">平均信号强度</span>
                            <span class="stat-value" style="color: #00d2ff;" id="avg-signal-strength">-</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="refresh-info">
                可视化数据每 10 秒自动刷新 | 最后更新：<span id="dashboard-last-update">-</span>
            </div>

            <!-- 信号分布柱状图 -->
            <div class="grid" style="margin-top: 20px;">
                <div class="card" style="grid-column: span 2;">
                    <h2>📊 信号得分分布</h2>
                    <div id="signal-distribution-chart" class="chart-container" style="height: 300px;"></div>
                </div>

                <!-- 告警历史列表 -->
                <div class="card">
                    <h2>🔔 最近告警</h2>
                    <div id="alerts-container" style="max-height: 300px; overflow-y: auto;">
                        <!-- 由 JS 动态填充 -->
                    </div>
                </div>
            </div>

            <!-- 因子趋势图 -->
            <div class="card" style="margin-top: 20px;">
                <h2>📈 因子趋势分析</h2>
                <div id="factor-trend-chart" class="chart-container" style="height: 350px;"></div>
                <div style="margin-top: 15px; display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
                    <button class="btn btn-sm" onclick="loadFactorTrend(3)">3 天</button>
                    <button class="btn btn-sm" onclick="loadFactorTrend(7)">7 天</button>
                    <button class="btn btn-sm" onclick="loadFactorTrend(14)">14 天</button>
                    <button class="btn btn-sm" onclick="loadFactorTrend(30)">30 天</button>
                </div>
            </div>

            <!-- 说明框 -->
            <div class="card" style="margin-top: 20px;">
                <h2>ℹ️ 数据说明</h2>
                <div style="color: #888; line-height: 1.8;">
                    <div>🕒 <strong>盘中监控</strong>：每 5 分钟执行一次（交易时间 9:30-15:00）</div>
                    <div>📊 <strong>股票池健康度</strong>：基于最近 10 次监控的平均信号评分</div>
                    <div>🎯 <strong>信号因子分析</strong>：当策略产生买入信号时记录</div>
                    <div>📈 <strong>资金曲线</strong>：基于实际交易记录计算</div>
                    <div>📊 <strong>信号分布</strong>：展示不同得分区间的信号数量分布</div>
                    <div>🔔 <strong>告警历史</strong>：记录每次监控的重要事件</div>
                    <div style="margin-top: 10px; color: #666;">
                        💡 当前时间已过收盘（15:00），监控数据将在下一个交易日交易时间内产生
                    </div>
                </div>
            </div>
        </div>

        <!-- 配置页面 -->
        <div id="page-config" class="page">
            <div class="card">
                <h2>⚙️ 系统配置信息</h2>

                <!-- 数据库配置 -->
                <div class="config-section">
                    <h3>🗄️ 数据库配置</h3>
                    <div class="config-item">
                        <span class="label">数据库路径</span>
                        <span class="value" id="cfg-database">-</span>
                    </div>
                </div>

                <!-- 交易配置 -->
                <div class="config-section">
                    <h3>💹 交易配置</h3>
                    <div class="config-item">
                        <span class="label">交易模式</span>
                        <span class="value" id="cfg-paper-trading">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">初始资金</span>
                        <span class="value" id="cfg-initial-capital">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">最大仓位比例</span>
                        <span class="value" id="cfg-max-position">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">单只股票最大持仓</span>
                        <span class="value" id="cfg-max-stock-position">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">单笔交易最大金额</span>
                        <span class="value" id="cfg-max-order">-</span>
                    </div>
                </div>

                <!-- 风控配置 -->
                <div class="config-section">
                    <h3>🛡️ 风控配置</h3>
                    <div class="config-item">
                        <span class="label">止损比例</span>
                        <span class="value" id="cfg-stop-loss">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">止盈比例</span>
                        <span class="value" id="cfg-take-profit">-</span>
                    </div>
                </div>

                <!-- 回测配置 -->
                <div class="config-section">
                    <h3>📊 回测配置</h3>
                    <div class="config-item">
                        <span class="label">佣金费率</span>
                        <span class="value" id="cfg-commission">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">印花税率</span>
                        <span class="value" id="cfg-stamp-tax">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">滑点费率</span>
                        <span class="value" id="cfg-slippage">-</span>
                    </div>
                </div>

                <!-- 调度配置 -->
                <div class="config-section">
                    <h3>⏰ 调度配置</h3>
                    <div class="config-item">
                        <span class="label">盘前准备时间</span>
                        <span class="value" id="cfg-pre-market">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">盘中监控间隔</span>
                        <span class="value" id="cfg-monitor-interval">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">盘后分析时间</span>
                        <span class="value" id="cfg-post-market">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">市场开放时间</span>
                        <span class="value" id="cfg-market-time">-</span>
                    </div>
                </div>

                <!-- 策略配置 -->
                <div class="config-section">
                    <h3>📈 策略配置</h3>
                    <div class="config-item">
                        <span class="label">默认股票池</span>
                        <span class="value" id="cfg-stock-pool">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">调仓频率</span>
                        <span class="value" id="cfg-rebalance">-</span>
                    </div>
                </div>

                <!-- 基本面过滤 -->
                <div class="config-section">
                    <h3>🔍 基本面过滤</h3>
                    <div class="config-item">
                        <span class="label">最大市盈率</span>
                        <span class="value" id="cfg-max-pe">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">最小 ROE</span>
                        <span class="value" id="cfg-min-roe">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">最大资产负债率</span>
                        <span class="value" id="cfg-max-debt">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">最小市值</span>
                        <span class="value" id="cfg-min-cap">-</span>
                    </div>
                </div>

                <!-- 日志配置 -->
                <div class="config-section">
                    <h3>📝 日志配置</h3>
                    <div class="config-item">
                        <span class="label">日志级别</span>
                        <span class="value" id="cfg-log-level">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">日志目录</span>
                        <span class="value" id="cfg-log-dir">-</span>
                    </div>
                </div>

                <!-- 钉钉通知配置 -->
                <div class="config-section">
                    <h3>🔔 钉钉通知配置</h3>
                    <div class="config-item">
                        <span class="label">启用状态</span>
                        <span class="value" id="cfg-ding-enabled">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">Webhook</span>
                        <span class="value" id="cfg-ding-webhook">-</span>
                    </div>
                    <div class="config-item">
                        <span class="label">签名密钥</span>
                        <span class="value" id="cfg-ding-secret">-</span>
                    </div>
                    <div style="margin-top: 15px;">
                        <button class="btn btn-success" onclick="testDingTalk()">🔔 测试连接</button>
                    </div>
                    <div id="ding-test-result" style="margin-top: 10px; padding: 10px; border-radius: 8px; display: none;"></div>
                </div>
            </div>

            <div class="refresh-info">
                配置信息每 10 秒自动刷新 | 最后更新：<span id="config-last-update">-</span>
            </div>
        </div>

        <!-- 股票池监控页面 -->
        <div id="page-stock-pool" class="page">
            <div class="card">
                <h2>🔍 股票池实时监控</h2>

                <!-- 刷新提示 -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div style="color: #888;">
                        监控股票池：<span id="pool-stocks" style="color: #00d2ff;">-</span>
                    </div>
                    <button class="btn" onclick="loadStockPoolRealtime()" style="padding: 8px 15px;">🔄 刷新</button>
                </div>

                <!-- 股票行情表格 -->
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>代码</th>
                                <th>名称</th>
                                <th>最新价</th>
                                <th>涨跌幅</th>
                                <th>开盘</th>
                                <th>最高</th>
                                <th>最低</th>
                                <th>成交量</th>
                                <th>成交额</th>
                                <th>MA5</th>
                                <th>MA10</th>
                                <th>MA20</th>
                                <th>RSI</th>
                                <th>趋势</th>
                                <th>K 线图</th>
                            </tr>
                        </thead>
                        <tbody id="stock-pool-table-body">
                            <!-- 由 JS 动态填充 -->
                        </tbody>
                    </table>
                </div>

                <div class="refresh-info">
                    数据每 10 秒自动刷新 | 最后更新：<span id="stock-pool-last-update">-</span>
                </div>
            </div>

            <!-- K 线图模态框 -->
            <div id="kline-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 1000; justify-content: center; align-items: center;">
                <div style="background: linear-gradient(135deg, rgba(58,123,213,0.95), rgba(0,210,255,0.95)); border-radius: 15px; padding: 30px; max-width: 900px; width: 95%; max-height: 90vh; overflow-y: auto;">
                    <h3 style="color: white; margin-bottom: 20px;" id="kline-title">📈 K 线图</h3>
                    <div id="kline-chart" style="width: 100%; height: 500px; background: rgba(0,0,0,0.3); border-radius: 10px;"></div>
                    <div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center;">
                        <div id="kline-info" style="color: white; font-size: 0.9em;"></div>
                        <button class="btn btn-danger" onclick="closeKlineModal()" style="padding: 8px 20px;">关闭</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 监控历史页面 -->
        <div id="page-history" class="page">
            <div class="card">
                <h2>📜 监控历史记录</h2>

                <!-- 筛选条件 -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; margin-bottom: 5px; color: #00d2ff;">开始日期</label>
                        <input type="date" id="filter-start-date" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,210,255,0.3); background: rgba(255,255,255,0.05); color: white;">
                    </div>
                    <div>
                        <label style="display: block; margin-bottom: 5px; color: #00d2ff;">结束日期</label>
                        <input type="date" id="filter-end-date" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,210,255,0.3); background: rgba(255,255,255,0.05); color: white;">
                    </div>
                    <div>
                        <label style="display: block; margin-bottom: 5px; color: #00d2ff;">市场状态</label>
                        <select id="filter-market-state" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,210,255,0.3); background: rgba(255,255,255,0.05); color: white;">
                            <option value="">全部</option>
                            <option value="open">交易中</option>
                            <option value="closed">休市中</option>
                        </select>
                    </div>
                    <div style="display: flex; align-items: flex-end;">
                        <button class="btn btn-primary" onclick="loadMonitoringHistory()" style="flex: 1;">🔍 查询</button>
                    </div>
                </div>

                <!-- 统计摘要 -->
                <div id="history-summary" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px;">
                    <!-- 由 JS 动态填充 -->
                </div>

                <!-- 监控历史记录表格 -->
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="border-bottom: 1px solid rgba(0,210,255,0.3);">
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">时间</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">市场状态</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">股票数</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">信号数</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">买入</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">卖出</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">成交</th>
                                <th style="padding: 12px; text-align: left; color: #00d2ff;">详情</th>
                            </tr>
                        </thead>
                        <tbody id="history-table-body">
                            <!-- 由 JS 动态填充 -->
                        </tbody>
                    </table>
                </div>

                <!-- 详情模态框 -->
                <div id="detail-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; justify-content: center; align-items: center;">
                    <div style="background: linear-gradient(135deg, rgba(58,123,213,0.9), rgba(0,210,255,0.9)); border-radius: 15px; padding: 30px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto;">
                        <h3 style="color: white; margin-bottom: 20px;">📊 监控详情</h3>
                        <div id="modal-content" style="color: white;"></div>
                        <button class="btn btn-secondary" onclick="closeModal()" style="margin-top: 20px;">关闭</button>
                    </div>
                </div>
            </div>

            <div class="refresh-info">
                监控历史记录 | 最后更新：<span id="history-last-update">-</span>
            </div>
        </div>
    </div>

    <script>
        // 页面切换
        function showPage(pageName) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('page-' + pageName).classList.add('active');
            event.target.classList.add('active');
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                document.getElementById('start-time').textContent = data.start_time;
                document.getElementById('uptime').textContent = data.uptime_seconds + ' 秒';
                document.getElementById('strategy').textContent = data.active_strategy;
                document.getElementById('stock-count').textContent = data.stock_pool_size;
                document.getElementById('data-bars').textContent = data.data_bars;
            } catch (e) {
                console.error('获取状态失败:', e);
            }
        }

        async function fetchAccount() {
            try {
                const response = await fetch('/api/account');
                const data = await response.json();

                document.getElementById('total-assets').textContent = '¥' + data.total_assets.toLocaleString();
                document.getElementById('available-cash').textContent = '¥' + data.available_cash.toLocaleString();
                document.getElementById('position-value').textContent = '¥' + data.position_value.toLocaleString();

                const profitEl = document.getElementById('total-profit');
                profitEl.textContent = '¥' + data.total_profit.toLocaleString();
                profitEl.className = 'stat-value ' + (data.total_profit >= 0 ? 'positive' : 'negative');
            } catch (e) {
                console.error('获取账户信息失败:', e);
            }
        }

        async function fetchPositions() {
            try {
                const response = await fetch('/api/positions');
                const data = await response.json();

                const tbody = document.getElementById('position-table');
                if (data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#666;">暂无持仓</td></tr>';
                } else {
                    tbody.innerHTML = data.map(p => `
                        <tr>
                            <td>${p.ts_code}</td>
                            <td>${p.volume}</td>
                            <td>¥${p.avg_cost.toFixed(2)}</td>
                            <td>¥${p.current_price.toFixed(2)}</td>
                            <td>¥${p.market_value.toLocaleString()}</td>
                            <td class="${p.profit_loss >= 0 ? 'positive' : 'negative'}">¥${p.profit_loss.toLocaleString()}</td>
                            <td class="${p.profit_ratio >= 0 ? 'positive' : 'negative'}">${(p.profit_ratio * 100).toFixed(2)}%</td>
                        </tr>
                    `).join('');
                }
            } catch (e) {
                console.error('获取持仓失败:', e);
            }
        }

        async function fetchTrades() {
            try {
                const response = await fetch('/api/trades');
                const data = await response.json();

                const tbody = document.getElementById('trade-table');
                if (data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">暂无交易记录</td></tr>';
                } else {
                    tbody.innerHTML = data.slice(0, 10).map(t => `
                        <tr>
                            <td>${t.timestamp}</td>
                            <td>${t.ts_code}</td>
                            <td style="color: ${t.direction === 'buy' ? '#00ff88' : '#ff4757'}">${t.direction === 'buy' ? '买入' : '卖出'}</td>
                            <td>¥${t.price.toFixed(2)}</td>
                            <td>${t.volume}</td>
                            <td>${t.profit_loss !== null ? '¥' + t.profit_loss.toFixed(2) : '-'}</td>
                        </tr>
                    `).join('');
                }
            } catch (e) {
                console.error('获取交易记录失败:', e);
            }
        }

        // 获取配置信息
        async function fetchConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();

                // 数据库配置
                document.getElementById('cfg-database').textContent = data.database_url;

                // 交易配置
                document.getElementById('cfg-paper-trading').textContent = data.paper_trading ? '模拟交易' : '实盘交易';
                document.getElementById('cfg-initial-capital').textContent = '¥' + data.initial_capital.toLocaleString();
                document.getElementById('cfg-max-position').textContent = (data.max_position_ratio * 100).toFixed(0) + '%';
                document.getElementById('cfg-max-stock-position').textContent = (data.max_stock_position_ratio * 100).toFixed(0) + '%';
                document.getElementById('cfg-max-order').textContent = '¥' + data.max_order_value.toLocaleString();

                // 风控配置
                document.getElementById('cfg-stop-loss').textContent = (data.stop_loss_ratio * 100).toFixed(1) + '%';
                document.getElementById('cfg-take-profit').textContent = (data.take_profit_ratio * 100).toFixed(1) + '%';

                // 回测配置
                document.getElementById('cfg-commission').textContent = (data.commission_rate * 10000).toFixed(0) + '‱ (万分之' + (data.commission_rate * 10000).toFixed(0) + ')';
                document.getElementById('cfg-stamp-tax').textContent = (data.stamp_tax_rate * 1000).toFixed(1) + '‰ (千分之' + (data.stamp_tax_rate * 1000).toFixed(1) + ')';
                document.getElementById('cfg-slippage').textContent = (data.slippage_rate * 1000).toFixed(1) + '‰ (千分之' + (data.slippage_rate * 1000).toFixed(1) + ')';

                // 调度配置
                document.getElementById('cfg-pre-market').textContent = data.pre_market_time;
                document.getElementById('cfg-monitor-interval').textContent = data.monitor_interval + '秒';
                document.getElementById('cfg-post-market').textContent = data.post_market_time;
                document.getElementById('cfg-market-time').textContent = data.market_open + '-' + data.market_close;

                // 策略配置
                document.getElementById('cfg-stock-pool').textContent = data.default_stock_pool.join(', ');
                document.getElementById('cfg-rebalance').textContent = data.rebalance_frequency;

                // 基本面过滤
                document.getElementById('cfg-max-pe').textContent = data.max_pe;
                document.getElementById('cfg-min-roe').textContent = (data.min_roe * 100).toFixed(0) + '%';
                document.getElementById('cfg-max-debt').textContent = (data.max_debt_ratio * 100).toFixed(0) + '%';
                document.getElementById('cfg-min-cap').textContent = (data.min_market_cap / 100000000).toFixed(1) + '亿';

                // 日志配置
                document.getElementById('cfg-log-level').textContent = data.log_level;
                document.getElementById('cfg-log-dir').textContent = data.log_dir;

                // 钉钉通知配置
                document.getElementById('cfg-ding-enabled').textContent = data.dingding_enabled ? '✅ 已启用' : '❌ 未启用';
                document.getElementById('cfg-ding-enabled').className = 'value ' + (data.dingding_enabled ? 'positive' : 'error');
                document.getElementById('cfg-ding-webhook').textContent = data.dingding_webhook ?
                    data.dingding_webhook.substring(0, 30) + '...' : '未配置';
                document.getElementById('cfg-ding-secret').textContent = data.dingding_secret ?
                    '***' + data.dingding_secret.substring(0, 4) : '未配置';

                document.getElementById('config-last-update').textContent = new Date().toLocaleTimeString();
            } catch (e) {
                console.error('获取配置失败:', e);
            }
        }

        // 测试钉钉连接
        async function testDingTalk() {
            const resultEl = document.getElementById('ding-test-result');
            resultEl.style.display = 'block';
            resultEl.innerHTML = '⏳ 发送测试中...';
            resultEl.style.background = 'rgba(0,210,255,0.1)';
            resultEl.style.color = '#00d2ff';

            try {
                const response = await fetch('/api/dingtalk/test', { method: 'POST' });
                const result = await response.json();

                if (result.success) {
                    resultEl.innerHTML = '✅ 测试成功！钉钉消息已发送';
                    resultEl.style.background = 'rgba(0,255,136,0.1)';
                    resultEl.style.color = '#00ff88';
                } else {
                    resultEl.innerHTML = '❌ 测试失败：' + (result.message || '未知错误');
                    resultEl.style.background = 'rgba(255,71,87,0.1)';
                    resultEl.style.color = '#ff4757';
                }
            } catch (e) {
                resultEl.innerHTML = '❌ 测试失败：' + e.message;
                resultEl.style.background = 'rgba(255,71,87,0.1)';
                resultEl.style.color = '#ff4757';
            }

            // 3 秒后隐藏结果
            setTimeout(() => {
                resultEl.style.display = 'none';
            }, 5000);
        }

        function refreshData() {
            fetchStatus();
            fetchAccount();
            fetchPositions();
            fetchTrades();
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
        }

        function refreshConfig() {
            fetchConfig();
        }

        async function runBacktest() {
            alert('开始运行回测...');
            try {
                const response = await fetch('/api/backtest', { method: 'POST' });
                const result = await response.json();
                alert('回测完成！\\n总收益：' + (result.total_return * 100).toFixed(2) + '%\\n夏普比率：' + result.sharpe_ratio.toFixed(2));
            } catch (e) {
                alert('回测失败：' + e.message);
            }
        }

        // 加载监控历史记录
        async function loadMonitoringHistory() {
            try {
                const startDate = document.getElementById('filter-start-date').value;
                const endDate = document.getElementById('filter-end-date').value;
                const marketState = document.getElementById('filter-market-state').value;

                let url = '/api/monitoring-history?';
                if (startDate) url += `start_date=${startDate}&`;
                if (endDate) url += `end_date=${endDate}&`;
                if (marketState) url += `market_state=${marketState}&`;

                const response = await fetch(url);
                const data = await response.json();

                // 更新统计摘要
                const summaryHtml = `
                    <div class="stat-item" style="background: rgba(0,210,255,0.1); padding: 15px; border-radius: 8px;">
                        <span style="color: rgba(255,255,255,0.7);">总监控次数</span>
                        <span style="color: #00d2ff; font-size: 1.5em;">${data.total_count}</span>
                    </div>
                    <div class="stat-item" style="background: rgba(0,255,127,0.1); padding: 15px; border-radius: 8px;">
                        <span style="color: rgba(255,255,255,0.7);">总信号数</span>
                        <span style="color: #00ff7f; font-size: 1.5em;">${data.total_signals}</span>
                    </div>
                    <div class="stat-item" style="background: rgba(255,215,0,0.1); padding: 15px; border-radius: 8px;">
                        <span style="color: rgba(255,255,255,0.7);">买入信号</span>
                        <span style="color: #ffd700; font-size: 1.5em;">${data.total_buy_signals}</span>
                    </div>
                    <div class="stat-item" style="background: rgba(255,71,87,0.1); padding: 15px; border-radius: 8px;">
                        <span style="color: rgba(255,255,255,0.7);">卖出信号</span>
                        <span style="color: #ff4757; font-size: 1.5em;">${data.total_sell_signals}</span>
                    </div>
                    <div class="stat-item" style="background: rgba(138,43,226,0.1); padding: 15px; border-radius: 8px;">
                        <span style="color: rgba(255,255,255,0.7);">成交笔数</span>
                        <span style="color: #8a2be2; font-size: 1.5em;">${data.total_trades}</span>
                    </div>
                `;
                document.getElementById('history-summary').innerHTML = summaryHtml;

                // 填充表格
                const tbody = document.getElementById('history-table-body');
                tbody.innerHTML = '';

                data.logs.forEach(log => {
                    const row = document.createElement('tr');
                    row.style.borderBottom = '1px solid rgba(255,255,255,0.1)';

                    const marketStateText = log.market_state === 'open' ? '🟢 交易中' : '⚫ 休市中';
                    const signalsDetail = log.buy_signals_count > 0 || log.sell_signals_count > 0
                        ? `买:${log.buy_signals_count} 卖:${log.sell_signals_count}`
                        : '-';
                    const buyOrdersDetail = log.buy_orders ? log.buy_orders.substring(0, 30) + (log.buy_orders.length > 30 ? '...' : '') : '-';
                    const sellOrdersDetail = log.sell_orders ? log.sell_orders.substring(0, 30) + (log.sell_orders.length > 30 ? '...' : '') : '-';

                    row.innerHTML = `
                        <td style="padding: 12px; color: white;">${log.monitor_time}</td>
                        <td style="padding: 12px; color: white;">${marketStateText}</td>
                        <td style="padding: 12px; color: white;">${log.stocks_count}</td>
                        <td style="padding: 12px; color: white;">${log.signals_count}</td>
                        <td style="padding: 12px; color: #00ff7f;">${log.buy_signals_count}</td>
                        <td style="padding: 12px; color: #ff4757;">${log.sell_signals_count}</td>
                        <td style="padding: 12px; color: #ffd700;">${log.trades_executed}</td>
                        <td style="padding: 12px;"><button class="btn btn-primary" onclick="showDetail(${log.id})" style="padding: 5px 10px; font-size: 0.9em;">详情</button></td>
                    `;
                    tbody.appendChild(row);
                });

                document.getElementById('history-last-update').textContent = new Date().toLocaleTimeString();
            } catch (e) {
                console.error('加载监控历史失败:', e);
            }
        }

        // 显示详情
        async function showDetail(logId) {
            try {
                const response = await fetch(`/api/monitoring-history/${logId}`);
                const log = await response.json();

                const modalContent = document.getElementById('modal-content');
                modalContent.innerHTML = `
                    <div style="line-height: 1.8;">
                        <p><strong>监控时间：</strong>${log.monitor_time}</p>
                        <p><strong>市场状态：</strong>${log.market_state === 'open' ? '🟢 交易中' : '⚫ 休市中'}</p>
                        <p><strong>股票池：</strong>${log.stock_pool || '-'}</p>
                        <p><strong>股票数量：</strong>${log.stocks_count}</p>
                        <p><strong>信号总数：</strong>${log.signals_count}</p>
                        <p><strong>买入信号：</strong>${log.buy_signals_count}</p>
                        <p><strong>卖出信号：</strong>${log.sell_signals_count}</p>
                        <p><strong>成交笔数：</strong>${log.trades_executed}</p>
                        ${log.buy_orders ? `<p><strong>买入订单：</strong><br><span style="color: #00ff7f;">${log.buy_orders.replace(/,/g, '<br>')}</span></p>` : ''}
                        ${log.sell_orders ? `<p><strong>卖出订单：</strong><br><span style="color: #ff4757;">${log.sell_orders.replace(/,/g, '<br>')}</span></p>` : ''}
                        ${log.error_message ? `<p><strong>错误信息：</strong><br><span style="color: #ff4757;">${log.error_message}</span></p>` : ''}
                    </div>
                `;

                document.getElementById('detail-modal').style.display = 'flex';
            } catch (e) {
                console.error('加载详情失败:', e);
                alert('加载详情失败：' + e.message);
            }
        }

        // 关闭详情模态框
        function closeModal() {
            document.getElementById('detail-modal').style.display = 'none';
        }

        // 点击模态框外部关闭
        document.getElementById('detail-modal')?.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal();
            }
        });

        // === 股票池监控页面相关函数 ===

        let klineChart = null;

        // 加载股票池实时数据
        async function loadStockPoolRealtime() {
            try {
                const response = await fetch('/api/stock-pool/realtime');
                const data = await response.json();

                if (data.error || !data.stocks || data.stocks.length === 0) {
                    document.getElementById('stock-pool-table-body').innerHTML = `
                        <tr><td colspan="15" style="text-align:center;color:#666;padding:30px;">
                            ${data.error || '暂无数据'}
                        </td></tr>
                    `;
                    return;
                }

                // 显示股票池
                document.getElementById('pool-stocks').textContent = data.stocks.map(s => s.ts_code).join(', ');

                // 填充表格
                const tbody = document.getElementById('stock-pool-table-body');
                tbody.innerHTML = data.stocks.map(stock => {
                    // 涨跌幅颜色 (A 股习惯：红涨绿跌)
                    const pctClass = stock.pct_chg >= 0 ? 'positive' : 'negative';
                    const pctColor = stock.pct_chg >= 0 ? '#ff4757' : '#00ff88';

                    // 趋势标识
                    const trendIcon = stock.trend === 'up' ? '📈' : (stock.trend === 'down' ? '📉' : '➡️');

                    // RSI 状态
                    const rsiStatus = stock.rsi > 70 ? '超买' : (stock.rsi < 30 ? '超卖' : '中性');
                    const rsiColor = stock.rsi > 70 ? '#ff4757' : (stock.rsi < 30 ? '#00ff88' : '#ffd700');

                    return `
                        <tr>
                            <td style="font-weight:bold;color:#00d2ff;">${stock.ts_code}</td>
                            <td>${stock.name || '-'}</td>
                            <td style="font-weight:bold;">¥${stock.close.toFixed(2)}</td>
                            <td class="${pctClass}" style="color:${pctColor};">${stock.pct_chg >= 0 ? '+' : ''}${stock.pct_chg.toFixed(2)}%</td>
                            <td>¥${stock.open.toFixed(2)}</td>
                            <td>¥${stock.high.toFixed(2)}</td>
                            <td>¥${stock.low.toFixed(2)}</td>
                            <td>${(stock.volume / 10000).toFixed(1)}万手</td>
                            <td>${(stock.amount / 100000000).toFixed(2)}亿</td>
                            <td style="color:${stock.ma5 ? '#888' : '#666'}">${stock.ma5 || '-'}</td>
                            <td style="color:${stock.ma10 ? '#888' : '#666'}">${stock.ma10 || '-'}</td>
                            <td style="color:${stock.ma20 ? '#888' : '#666'}">${stock.ma20 || '-'}</td>
                            <td style="color:${rsiColor};">${stock.rsi.toFixed(1)} <span style="font-size:0.8em;">(${rsiStatus})</span></td>
                            <td>${trendIcon} ${stock.trend}</td>
                            <td><button class="btn" onclick="showKline('${stock.ts_code}')" style="padding:5px 10px;font-size:0.85em;">📊 查看</button></td>
                        </tr>
                    `;
                }).join('');

                document.getElementById('stock-pool-last-update').textContent = new Date().toLocaleTimeString();
            } catch (e) {
                console.error('加载股票池数据失败:', e);
                document.getElementById('stock-pool-table-body').innerHTML = `
                    <tr><td colspan="15" style="text-align:center;color:#ff4757;padding:30px;">
                        加载失败：${e.message}
                    </td></tr>
                `;
            }
        }

        // 显示 K 线图
        async function showKline(tsCode) {
            try {
                const response = await fetch(`/api/stock-pool/detail/${tsCode}`);
                const data = await response.json();

                if (data.error || !data.kline_data || data.kline_data.length === 0) {
                    alert(data.error || '无 K 线数据');
                    return;
                }

                // 设置标题
                document.getElementById('kline-title').textContent = `📈 ${data.name || tsCode} K 线图`;
                document.getElementById('kline-info').textContent =
                    `行业：${data.industry || '-'} | 地区：${data.area || '-'} | 数据条数：${data.kline_data.length}`;

                // 显示模态框
                document.getElementById('kline-modal').style.display = 'flex';

                // 绘制 K 线图
                if (klineChart) {
                    klineChart.dispose();
                }

                klineChart = echarts.init(document.getElementById('kline-chart'));

                // 准备数据
                const klineData = data.kline_data.map(d => [d.open, d.close, d.low, d.high]);
                const dates = data.kline_data.map(d => d.date);
                const volumes = data.kline_data.map(d => d.volume);

                // 计算 MA 值
                const ma5 = calculateMA(klineData, 5);
                const ma10 = calculateMA(klineData, 10);
                const ma20 = calculateMA(klineData, 20);

                const option = {
                    backgroundColor: 'transparent',
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: { type: 'cross' },
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        borderColor: '#00d2ff',
                        textStyle: { color: '#fff' }
                    },
                    axisPointer: {
                        link: [{ xAxisIndex: 'all' }],
                        label: { backgroundColor: '#00d2ff' }
                    },
                    grid: [
                        { left: '10%', right: '8%', top: '10%', height: '60%' },
                        { left: '10%', right: '8%', top: '75%', height: '15%' }
                    ],
                    xAxis: [
                        {
                            type: 'category',
                            data: dates,
                            scale: true,
                            boundaryGap: false,
                            axisLine: { onZero: false, lineStyle: { color: '#888' } },
                            splitLine: { show: false },
                            splitNumber: 20,
                            axisLabel: { color: '#888' },
                            gridIndex: 0
                        },
                        {
                            type: 'category',
                            gridIndex: 1,
                            data: dates,
                            axisLabel: { show: false, color: '#888' }
                        }
                    ],
                    yAxis: [
                        {
                            scale: true,
                            splitArea: { show: true, areaStyle: { color: ['rgba(255,255,255,0.03)', 'rgba(255,255,255,0.01)'] } },
                            splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
                            axisLabel: { color: '#888' }
                        },
                        {
                            scale: true,
                            gridIndex: 1,
                            splitNumber: 2,
                            axisLabel: { color: '#888' },
                            axisLine: { show: false },
                            splitLine: { show: false }
                        }
                    ],
                    series: [
                        {
                            name: 'K 线',
                            type: 'candlestick',
                            data: klineData,
                            itemStyle: {
                                color: '#ef232a',
                                color0: '#14b143',
                                borderColor: '#ef232a',
                                borderColor0: '#14b143'
                            },
                            xAxisIndex: 0,
                            yAxisIndex: 0
                        },
                        {
                            name: 'MA5',
                            type: 'line',
                            data: ma5,
                            smooth: true,
                            lineStyle: { width: 1, color: '#8a2be2' },
                            xAxisIndex: 0,
                            yAxisIndex: 0
                        },
                        {
                            name: 'MA10',
                            type: 'line',
                            data: ma10,
                            smooth: true,
                            lineStyle: { width: 1, color: '#00d2ff' },
                            xAxisIndex: 0,
                            yAxisIndex: 0
                        },
                        {
                            name: 'MA20',
                            type: 'line',
                            data: ma20,
                            smooth: true,
                            lineStyle: { width: 1, color: '#ffd700' },
                            xAxisIndex: 0,
                            yAxisIndex: 0
                        },
                        {
                            name: '成交量',
                            type: 'bar',
                            data: volumes,
                            xAxisIndex: 1,
                            yAxisIndex: 1,
                            itemStyle: {
                                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                    { offset: 0, color: 'rgba(0,210,255,0.5)' },
                                    { offset: 1, color: 'rgba(0,210,255,0.1)' }
                                ])
                            }
                        }
                    ]
                };

                klineChart.setOption(option);
                window.addEventListener('resize', () => klineChart.resize());

            } catch (e) {
                console.error('加载 K 线图失败:', e);
                alert('加载 K 线图失败：' + e.message);
            }
        }

        // 计算移动平均线
        function calculateMA(klineData, period) {
            const result = [];
            for (let i = 0; i < klineData.length; i++) {
                if (i < period - 1) {
                    result.push('-');
                    continue;
                }
                let sum = 0;
                for (let j = 0; j < period; j++) {
                    sum += klineData[i - j][1]; // 收盘价
                }
                result.push((sum / period).toFixed(2));
            }
            return result;
        }

        // 关闭 K 线图模态框
        function closeKlineModal() {
            document.getElementById('kline-modal').style.display = 'none';
            if (klineChart) {
                klineChart.dispose();
            }
        }

        // 点击模态框外部关闭
        document.getElementById('kline-modal')?.addEventListener('click', function(e) {
            if (e.target === this) {
                closeKlineModal();
            }
        });

        // === 可视化仪表板相关函数 ===

        // ECharts 实例存储
        let equityChart = null;
        let marketStateChart = null;
        let factorsRadarChart = null;

        // 加载股票池健康度
        async function loadStockHealth() {
            try {
                const response = await fetch('/api/monitoring/stock-health');
                const data = await response.json();

                const container = document.getElementById('stock-health-container');
                if (!data.stocks || data.stocks.length === 0) {
                    container.innerHTML = '<div style="text-align:center;color:#666;padding:20px;">暂无数据</div>';
                    return;
                }

                // 检查是否所有股票都是 unknown 状态（无数据）
                const allUnknown = data.stocks.every(s => s.trend_status === 'unknown');
                if (allUnknown && data.stocks[0].monitor_count === 0) {
                    container.innerHTML = `
                        <div style="text-align:center;color:#888;padding:30px;">
                            <div style="font-size:1.2em;margin-bottom:10px;">📊 等待监控数据</div>
                            <div style="font-size:0.9em;">盘中监控每 5 分钟执行一次</div>
                            <div style="font-size:0.8em;margin-top:15px;color:#666;">
                                当前股票池：${data.stocks.map(s => s.ts_code).join(', ')}
                            </div>
                        </div>
                    `;
                    return;
                }

                let html = '';
                data.stocks.forEach(stock => {
                    const scoreClass = stock.health_score >= 70 ? 'good' : (stock.health_score >= 40 ? 'normal' : 'bad');
                    const trendText = stock.trend_status === 'bull' ? '✅ 强势' :
                                     (stock.trend_status === 'bear' ? '❌ 弱势' : '⚠️ 震荡');
                    const trendClass = stock.trend_status;

                    html += `
                        <div class="stock-health-item">
                            <span class="stock-code">${stock.ts_code}</span>
                            <div class="health-bar">
                                <div class="health-fill ${trendClass}" style="width: ${stock.health_score}%"></div>
                            </div>
                            <span class="health-score ${scoreClass}">${stock.health_score}</span>
                            <span class="tag tag-${trendClass === 'bull' ? 'green' : (trendClass === 'bear' ? 'red' : 'orange')}"
                                  style="margin-left:10px;min-width:60px;text-align:center;">${trendText}</span>
                        </div>
                    `;
                });

                container.innerHTML = html;
            } catch (e) {
                console.error('加载股票健康度失败:', e);
            }
        }

        // 加载资金曲线
        async function loadEquityCurve() {
            try {
                const response = await fetch('/api/monitoring/equity-curve');
                const data = await response.json();

                // 如果没有数据，显示当前资金
                if (!data.labels || data.labels.length === 0) {
                    const currentCapital = data.current_capital || 100000;
                    document.getElementById('equity-chart').innerHTML = `
                        <div style="text-align:center;color:#888;padding:50px;">
                            <div style="font-size:0.9em;margin-bottom:10px;">暂无历史数据</div>
                            <div style="font-size:1.5em;color:#00ff88;">当前资金：¥${currentCapital.toLocaleString()}</div>
                            <div style="font-size:0.8em;margin-top:10px;">模拟盘运行后自动显示资金曲线</div>
                        </div>
                    `;
                    return;
                }

                // 初始化 ECharts
                if (equityChart) {
                    equityChart.dispose();
                }

                equityChart = echarts.init(document.getElementById('equity-chart'));

                const option = {
                    tooltip: {
                        trigger: 'axis',
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        borderColor: '#00d2ff',
                        textStyle: { color: '#fff' }
                    },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
                    xAxis: {
                        type: 'category',
                        data: data.labels,
                        axisLabel: { color: '#888' },
                        axisLine: { lineStyle: { color: '#333' } }
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: { color: '#888' },
                        axisLine: { lineStyle: { color: '#333' } },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    series: [{
                        name: '总资产',
                        type: 'line',
                        smooth: true,
                        data: data.data,
                        itemStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: '#00ff88' },
                                { offset: 1, color: '#00d2ff' }
                            ])
                        },
                        areaStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: 'rgba(0,255,136,0.3)' },
                                { offset: 1, color: 'rgba(0,210,255,0.1)' }
                            ])
                        },
                        lineStyle: { width: 3 }
                    }]
                };

                equityChart.setOption(option);

                // 响应式
                window.addEventListener('resize', () => equityChart.resize());
            } catch (e) {
                console.error('加载资金曲线失败:', e);
            }
        }

        // 加载市场状态
        async function loadMarketState() {
            try {
                const response = await fetch('/api/monitoring/market-state');
                const data = await response.json();

                if (data.summary) {
                    document.getElementById('bull-count').textContent = data.summary.bull_count || 0;
                    document.getElementById('sideways-count').textContent = data.summary.sideways_count || 0;
                    document.getElementById('bear-count').textContent = data.summary.bear_count || 0;
                }

                // 检查是否有数据
                const total = (data.summary?.bull_count || 0) + (data.summary?.sideways_count || 0) + (data.summary?.bear_count || 0);

                if (total === 0) {
                    document.getElementById('market-state-chart').innerHTML = `
                        <div style="text-align:center;color:#888;padding:50px;">
                            <div style="font-size:1.2em;margin-bottom:10px;">📊 等待监控数据</div>
                            <div style="font-size:0.9em;">盘中监控每 5 分钟执行一次</div>
                        </div>
                    `;
                    return;
                }

                // 绘制市场状态饼图
                if (marketStateChart) {
                    marketStateChart.dispose();
                }

                marketStateChart = echarts.init(document.getElementById('market-state-chart'));

                const option = {
                    tooltip: {
                        trigger: 'item',
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        textStyle: { color: '#fff' }
                    },
                    series: [{
                        name: '市场状态',
                        type: 'pie',
                        radius: ['40%', '70%'],
                        avoidLabelOverlap: false,
                        label: { color: '#fff' },
                        data: [
                            { value: data.summary?.bull_count || 0, name: '牛市', itemStyle: { color: '#00ff88' } },
                            { value: data.summary?.sideways_count || 0, name: '震荡市', itemStyle: { color: '#ffd700' } },
                            { value: data.summary?.bear_count || 0, name: '熊市', itemStyle: { color: '#ff4757' } }
                        ]
                    }]
                };

                marketStateChart.setOption(option);
                window.addEventListener('resize', () => marketStateChart.resize());
            } catch (e) {
                console.error('加载市场状态失败:', e);
            }
        }

        // 加载信号因子雷达图
        async function loadFactorsRadar() {
            try {
                const response = await fetch('/api/monitoring/factors');
                const data = await response.json();

                if (!data.factors || data.factors.length === 0 || data.count === 0) {
                    document.getElementById('factors-radar-chart').innerHTML = `
                        <div style="text-align:center;color:#888;padding:50px;">
                            <div style="font-size:1.2em;margin-bottom:10px;">📊 等待信号数据</div>
                            <div style="font-size:0.9em;">策略会在监控时自动生成信号</div>
                        </div>
                    `;
                    document.getElementById('current-score').textContent = '-';
                    return;
                }

                // 获取最新一次信号
                const latestFactor = data.factors[0];
                const factors = latestFactor.factors;

                document.getElementById('current-score').textContent = latestFactor.signal_score.toFixed(1);

                if (factorsRadarChart) {
                    factorsRadarChart.dispose();
                }

                factorsRadarChart = echarts.init(document.getElementById('factors-radar-chart'));

                const option = {
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        textStyle: { color: '#fff' }
                    },
                    radar: {
                        indicator: [
                            { name: '均线金叉', max: 2.0 },
                            { name: '完美多头', max: 1.5 },
                            { name: 'MACD', max: 1.5 },
                            { name: 'RSI', max: 0.5 },
                            { name: '布林带', max: 1.0 },
                            { name: '成交量', max: 1.5 },
                            { name: '趋势', max: 1.5 }
                        ],
                        axisName: { color: '#00d2ff' },
                        splitArea: {
                            areaStyle: {
                                color: ['rgba(0,210,255,0.1)', 'rgba(0,210,255,0.05)']
                            }
                        },
                        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.3)' } },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.3)' } }
                    },
                    series: [{
                        name: '信号因子',
                        type: 'radar',
                        data: [{
                            value: [
                                factors.ma_cross,
                                factors.perfect_trend,
                                factors.macd,
                                factors.rsi,
                                factors.bb,
                                factors.volume,
                                factors.trend
                            ],
                            name: '当前信号',
                            areaStyle: { color: 'rgba(0,210,255,0.3)' },
                            lineStyle: { color: '#00d2ff', width: 2 },
                            itemStyle: { color: '#00d2ff' }
                        }]
                    }]
                };

                factorsRadarChart.setOption(option);
                window.addEventListener('resize', () => factorsRadarChart.resize());

                // 更新信号统计
                loadSignalStats(data);
            } catch (e) {
                console.error('加载信号因子失败:', e);
            }
        }

        // 加载信号统计
        async function loadSignalStats(factorsData) {
            try {
                const totalMonitors = factorsData.count || 0;
                const buySignals = factorsData.factors?.filter(f => f.is_buy_signal).length || 0;
                const sellSignals = factorsData.factors?.filter(f => !f.is_buy_signal).length || 0;

                // 计算平均强度
                const avgStrength = factorsData.factors?.length > 0
                    ? factorsData.factors.reduce((sum, f) => sum + (f.signal_score || 0), 0) / factorsData.factors.length
                    : 0;

                document.getElementById('total-monitors').textContent = totalMonitors;
                document.getElementById('total-buy-signals').textContent = buySignals;
                document.getElementById('total-sell-signals').textContent = sellSignals;
                document.getElementById('avg-signal-strength').textContent = avgStrength.toFixed(2);
            } catch (e) {
                console.error('加载信号统计失败:', e);
            }
        }

        // 加载信号分布柱状图
        async function loadSignalDistribution() {
            try {
                const response = await fetch('/api/monitoring/signal-distribution');
                const data = await response.json();

                if (!data.distribution || data.distribution.length === 0) {
                    document.getElementById('signal-distribution-chart').innerHTML = `
                        <div style="text-align:center;color:#888;padding:50px;">
                            <div style="font-size:1.2em;margin-bottom:10px;">📊 等待信号数据</div>
                            <div style="font-size:0.9em;">策略会在监控时自动生成信号</div>
                        </div>
                    `;
                    return;
                }

                const chart = echarts.init(document.getElementById('signal-distribution-chart'));

                const ranges = data.distribution.map(d => d.range);
                const counts = data.distribution.map(d => d.count);
                const buyCounts = data.distribution.map(d => d.buy_count);

                const option = {
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: { type: 'shadow' },
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        textStyle: { color: '#fff' }
                    },
                    legend: {
                        data: ['总信号数', '买入信号'],
                        textStyle: { color: '#888' },
                        top: '0%'
                    },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
                    xAxis: {
                        type: 'category',
                        data: ranges,
                        axisLabel: { color: '#888', rotate: 0 },
                        axisLine: { lineStyle: { color: '#333' } }
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: { color: '#888' },
                        axisLine: { lineStyle: { color: '#333' } },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    series: [
                        {
                            name: '总信号数',
                            type: 'bar',
                            data: counts,
                            itemStyle: {
                                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                    { offset: 0, color: '#00d2ff' },
                                    { offset: 1, color: '#0066cc' }
                                ])
                            },
                            barWidth: '35%'
                        },
                        {
                            name: '买入信号',
                            type: 'bar',
                            data: buyCounts,
                            itemStyle: {
                                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                    { offset: 0, color: '#00ff88' },
                                    { offset: 1, color: '#00aa55' }
                                ])
                            },
                            barWidth: '35%'
                        }
                    ]
                };

                chart.setOption(option);
                window.addEventListener('resize', () => chart.resize());
            } catch (e) {
                console.error('加载信号分布失败:', e);
            }
        }

        // 加载因子趋势图
        let factorTrendChart = null;
        async function loadFactorTrend(days = 7) {
            try {
                const response = await fetch(`/api/monitoring/factor-trend?days=${days}`);
                const data = await response.json();

                if (!data.trend || data.trend.length === 0) {
                    document.getElementById('factor-trend-chart').innerHTML = `
                        <div style="text-align:center;color:#888;padding:50px;">
                            <div style="font-size:1.2em;margin-bottom:10px;">📊 等待趋势数据</div>
                            <div style="font-size:0.9em;">盘中监控每 5 分钟执行一次</div>
                        </div>
                    `;
                    return;
                }

                if (factorTrendChart) {
                    factorTrendChart.dispose();
                }

                factorTrendChart = echarts.init(document.getElementById('factor-trend-chart'));

                const dates = data.trend.map(d => d.date.substring(5)); // 只显示 MM-DD

                const option = {
                    tooltip: {
                        trigger: 'axis',
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        textStyle: { color: '#fff' }
                    },
                    legend: {
                        data: ['综合得分', 'MA 金叉', 'MACD', 'RSI', '布林带', '趋势'],
                        textStyle: { color: '#888' },
                        top: '0%',
                        type: 'scroll'
                    },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
                    xAxis: {
                        type: 'category',
                        data: dates,
                        axisLabel: { color: '#888' },
                        axisLine: { lineStyle: { color: '#333' } }
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: { color: '#888' },
                        axisLine: { lineStyle: { color: '#333' } },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    series: [
                        {
                            name: '综合得分',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.avg_score),
                            itemStyle: { color: '#ffd700' },
                            lineStyle: { width: 3 }
                        },
                        {
                            name: 'MA 金叉',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.ma_cross),
                            itemStyle: { color: '#00d2ff' },
                            lineStyle: { width: 2 }
                        },
                        {
                            name: 'MACD',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.macd),
                            itemStyle: { color: '#ff4757' },
                            lineStyle: { width: 2 }
                        },
                        {
                            name: 'RSI',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.rsi),
                            itemStyle: { color: '#8a2be2' },
                            lineStyle: { width: 2 }
                        },
                        {
                            name: '布林带',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.bb),
                            itemStyle: { color: '#00ff88' },
                            lineStyle: { width: 2 }
                        },
                        {
                            name: '趋势',
                            type: 'line',
                            smooth: true,
                            data: data.trend.map(d => d.trend),
                            itemStyle: { color: '#ff6b6b' },
                            lineStyle: { width: 2 }
                        }
                    ]
                };

                factorTrendChart.setOption(option);
                window.addEventListener('resize', () => factorTrendChart.resize());
            } catch (e) {
                console.error('加载因子趋势失败:', e);
            }
        }

        // 加载告警历史列表
        async function loadAlerts() {
            try {
                const response = await fetch('/api/monitoring/alerts');
                const data = await response.json();

                if (!data.alerts || data.alerts.length === 0) {
                    document.getElementById('alerts-container').innerHTML = `
                        <div style="text-align:center;color:#888;padding:30px;">
                            <div style="font-size:1em;margin-bottom:10px;">暂无告警记录</div>
                            <div style="font-size:0.8em;">监控开始后此处将显示告警信息</div>
                        </div>
                    `;
                    return;
                }

                let html = '';
                data.alerts.forEach((alert, index) => {
                    const scoreClass = alert.total_score >= 7 ? 'good' : (alert.total_score >= 4 ? 'normal' : 'bad');
                    const timeStr = alert.monitor_time.substring(5, 16); // MM-DD HH:MM

                    html += `
                        <div style="padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 3px solid ${alert.total_score >= 7 ? '#00ff88' : (alert.total_score >= 4 ? '#ffd700' : '#ff4757')};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="color: rgba(255,255,255,0.9); font-size: 0.9em;">
                                    <span style="color: #888;">${timeStr}</span>
                                    <span style="margin-left: 10px;">📊 ${alert.market_state || '未知'}</span>
                                </div>
                                <div style="color: ${alert.total_score >= 7 ? '#00ff88' : (alert.total_score >= 4 ? '#ffd700' : '#ff4757')}; font-weight: bold;">
                                    得分：${alert.total_score.toFixed(1)}
                                </div>
                            </div>
                            <div style="margin-top: 8px; display: flex; gap: 15px; font-size: 0.85em; color: #888;">
                                <span>🟢 买入：${alert.buy_signals_count}</span>
                                <span>🔴 卖出：${alert.sell_signals_count}</span>
                                <span>📝 成交：${alert.trades_executed}</span>
                            </div>
                        </div>
                    `;
                });

                document.getElementById('alerts-container').innerHTML = html;
            } catch (e) {
                console.error('加载告警历史失败:', e);
            }
        }

        // 刷新仪表板
        function refreshDashboard() {
            loadStockHealth();
            loadEquityCurve();
            loadMarketState();
            loadFactorsRadar();
            loadSignalDistribution();
            loadFactorTrend(7);
            loadAlerts();
            document.getElementById('dashboard-last-update').textContent = new Date().toLocaleTimeString();
        }

        // 初始化
        refreshData();
        refreshConfig();
        setInterval(refreshData, 5000);  // 每 5 秒刷新监控数据
        setInterval(refreshConfig, 10000);  // 每 10 秒刷新配置

        // 仪表板初始化 (当切换到仪表板页面时加载数据)
        const originalShowPage = showPage;
        showPage = function(pageName) {
            originalShowPage(pageName);
            if (pageName === 'dashboard') {
                refreshDashboard();
                // 每 10 秒刷新仪表板
                if (!window.dashboardInterval) {
                    window.dashboardInterval = setInterval(refreshDashboard, 10000);
                }
            } else if (pageName === 'stock-pool') {
                // 股票池页面 - 每 10 秒刷新
                loadStockPoolRealtime();
                if (!window.stockPoolInterval) {
                    window.stockPoolInterval = setInterval(loadStockPoolRealtime, 10000);
                }
            } else {
                if (window.dashboardInterval) {
                    clearInterval(window.dashboardInterval);
                    window.dashboardInterval = null;
                }
                if (window.stockPoolInterval) {
                    clearInterval(window.stockPoolInterval);
                    window.stockPoolInterval = null;
                }
            }
        };
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """主页 - 返回 HTML 界面"""
    return HTML_TEMPLATE


@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    global system_start_time, current_strategy, stock_pool

    uptime = (datetime.now() - system_start_time).total_seconds()

    # 获取数据量
    df = db.query("SELECT COUNT(*) as count FROM daily_quotes")
    data_bars = int(df.iloc[0]['count']) if len(df) > 0 else 0

    return {
        "status": "running",
        "start_time": system_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_seconds": int(uptime),
        "active_strategy": current_strategy.name if current_strategy else "未设置",
        "stock_pool_size": len(stock_pool),
        "data_bars": data_bars
    }


@app.get("/api/account")
async def get_account():
    """获取账户信息 - 从数据库读取 paper_trading 账户"""
    # 直接从数据库读取 paper_trading 账户信息
    df = db.query("SELECT * FROM accounts WHERE account_name = ?", ("paper_trading",))

    if df.empty:
        return {
            "total_assets": 100000,
            "available_cash": 100000,
            "position_value": 0,
            "total_profit": 0,
            "total_profit_ratio": 0
        }

    row = df.iloc[0]
    total_asset = float(row['total_asset'])
    total_profit = total_asset - 100000  # 初始资金 10 万

    return {
        "total_assets": total_asset,
        "available_cash": float(row['available_cash']),
        "position_value": float(row['total_position_value']),
        "total_profit": total_profit,
        "total_profit_ratio": total_profit / 100000
    }


@app.get("/api/positions")
async def get_positions():
    """获取持仓信息 - 从数据库读取"""
    # 从数据库读取持仓
    df = db.query("SELECT * FROM positions")

    if df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        result.append({
            "ts_code": row['ts_code'],
            "volume": row['volume'],
            "avg_cost": float(row['avg_cost']),
            "current_price": float(row.get('current_price', 0)),
            "market_value": float(row.get('market_value', 0)),
            "profit_loss": float(row.get('profit_loss', 0)),
            "profit_ratio": float(row.get('profit_ratio', 0))
        })

    return result


@app.get("/api/trades")
async def get_trades():
    """获取交易记录 - 从数据库读取"""
    # 从数据库读取已完成的订单
    df = db.query("""
        SELECT * FROM orders
        WHERE status IN ('filled', 'partially_filled')
        ORDER BY created_at DESC
        LIMIT 20
    """)

    if df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        result.append({
            "ts_code": row['ts_code'],
            "direction": row['direction'],
            "price": float(row['price']),
            "volume": row['volume'],
            "timestamp": row['created_at'],
            "profit_loss": None  # 卖出订单的盈亏需要在 fill_order 时记录
        })

    return result


# === 股票池实时监控 API ===

import random
from datetime import time as dt_time

def is_trading_time() -> bool:
    """判断当前是否在交易时间内"""
    now = datetime.now()
    # 周末休市
    if now.weekday() >= 5:
        return False
    # 交易时间：9:30-11:30, 13:00-15:00
    morning_start = dt_time(9, 30)
    morning_end = dt_time(11, 30)
    afternoon_start = dt_time(13, 0)
    afternoon_end = dt_time(15, 0)
    current_time = now.time()
    return (morning_start <= current_time <= morning_end or
            afternoon_start <= current_time <= afternoon_end)

@app.get("/api/stock-pool/realtime")
async def get_stock_pool_realtime():
    """获取股票池实时行情（仅在交易时间模拟波动）"""
    try:
        stock_pool = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
        current_date = datetime.now().strftime('%Y%m%d')

        stocks_data = []

        for ts_code in stock_pool:
            # 获取最近 60 天数据用于计算技术指标
            df = db.query("""
                SELECT trade_date, open, high, low, close, vol, amount, pct_chg
                FROM daily_quotes
                WHERE ts_code = ?
                ORDER BY trade_date DESC
                LIMIT 60
            """, (ts_code,))

            if df.empty:
                continue

            # 获取最新数据
            latest = df.iloc[0]

            # 计算技术指标
            close_series = df['close'].iloc[::-1].reset_index(drop=True)  # 反转成正序

            # MA5, MA10, MA20
            ma5 = close_series.tail(5).mean() if len(close_series) >= 5 else None
            ma10 = close_series.tail(10).mean() if len(close_series) >= 10 else None
            ma20 = close_series.tail(20).mean() if len(close_series) >= 20 else None

            # 涨跌幅
            pct_chg = float(latest['pct_chg']) if latest['pct_chg'] else 0

            # 获取股票名称（如果数据库没有，使用代码映射）
            stock_info = db.query("SELECT name FROM stocks WHERE ts_code = ?", (ts_code,))
            if not stock_info.empty:
                stock_name = stock_info.iloc[0]['name']
            else:
                # 使用默认名称映射
                stock_names = {
                    '000063.SZ': '中兴通讯',
                    '000014.SZ': '沙河股份',
                    '000078.SZ': '海王生物',
                    '000039.SZ': '中集集团',
                    '000001.SZ': '平安银行',
                }
                stock_name = stock_names.get(ts_code, ts_code)

            # 计算 RSI
            if len(close_series) >= 15:
                gains = []
                losses = []
                for i in range(1, len(close_series)):
                    change = close_series.iloc[i] - close_series.iloc[i-1]
                    if change > 0:
                        gains.append(change)
                        losses.append(0)
                    else:
                        gains.append(0)
                        losses.append(abs(change))

                avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
                avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 1
                rs = avg_gain / avg_loss if avg_loss > 0 else 0
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 50

            # 基础价格（最新收盘价）
            base_close = float(latest['close'])

            # 判断是否在交易时间内
            trading = is_trading_time()

            if trading:
                # 交易时间：添加模拟实时波动（0.5% 以内随机波动）
                random.seed(datetime.now().second + datetime.now().microsecond // 10000)
                fluctuation = random.uniform(-0.005, 0.008)  # -0.5% 到 +0.8%

                # 模拟当前价
                current_price = round(base_close * (1 + fluctuation), 2)

                # 模拟今日开盘价（在昨日收盘附近）
                open_fluctuation = random.uniform(-0.003, 0.003)
                simulated_open = round(base_close * (1 + open_fluctuation), 2)

                # 模拟最高价和最低价
                simulated_high = round(max(current_price, simulated_open) * random.uniform(1.001, 1.015), 2)
                simulated_low = round(min(current_price, simulated_open) * random.uniform(0.985, 0.999), 2)

                # 模拟涨跌幅（基于当前价）
                simulated_pct_chg = round((current_price - base_close) / base_close * 100, 2)
            else:
                # 非交易时间：显示固定收盘价
                current_price = base_close
                simulated_open = float(latest['open'])
                simulated_high = float(latest['high'])
                simulated_low = float(latest['low'])
                simulated_pct_chg = pct_chg

            # 判断趋势
            trend = 'up' if ma5 and ma5 > ma10 else ('down' if ma5 and ma5 < ma10 else 'flat')

            stocks_data.append({
                'ts_code': ts_code,
                'name': stock_name,
                'trade_date': str(latest['trade_date']),
                'open': simulated_open,
                'high': simulated_high,
                'low': simulated_low,
                'close': current_price,
                'volume': float(latest['vol']),
                'amount': float(latest['amount']),
                'pct_chg': simulated_pct_chg,
                'ma5': round(ma5, 2) if ma5 else None,
                'ma10': round(ma10, 2) if ma10 else None,
                'ma20': round(ma20, 2) if ma20 else None,
                'rsi': round(rsi, 2),
                'trend': trend,
                'market_status': 'trading' if trading else 'closed',  # 市场状态
            })

        return {'stocks': stocks_data, 'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    except Exception as e:
        return {'error': str(e), 'stocks': [], 'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


@app.get("/api/stock-pool/detail/{ts_code}")
async def get_stock_detail(ts_code: str):
    """获取单只股票详细信息"""
    try:
        # 获取最近 120 天数据用于绘制 K 线图
        df = db.query("""
            SELECT trade_date, open, high, low, close, vol, amount, pct_chg
            FROM daily_quotes
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT 120
        """, (ts_code,))

        if df.empty:
            return {'error': '无数据', 'kline_data': []}

        # 反转成正序
        df = df.iloc[::-1].reset_index(drop=True)

        kline_data = []
        for _, row in df.iterrows():
            kline_data.append({
                'date': str(row['trade_date']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['vol']),
            })

        # 获取股票信息
        stock_info = db.query("SELECT name, industry, area FROM stocks WHERE ts_code = ?", (ts_code,))
        info = stock_info.iloc[0] if not stock_info.empty else {}

        return {
            'ts_code': ts_code,
            'name': info.get('name', ts_code),
            'industry': info.get('industry', ''),
            'area': info.get('area', ''),
            'kline_data': kline_data,
        }

    except Exception as e:
        return {'error': str(e), 'kline_data': []}


@app.post("/api/backtest")
async def run_backtest():
    """运行回测"""
    global current_strategy

    try:
        # 使用最优策略
        if current_strategy is None:
            current_strategy = create_optimal_strategy(aggressive=True)

        # 加载数据
        stock_pool = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']
        data_dict = {}

        for ts_code in stock_pool:
            df = data_manager.get_daily_quotes(ts_code, '20250301', '20260319')
            if not df.empty:
                data_dict[ts_code] = df

        if not data_dict:
            return {"error": "未获取到任何股票数据，请检查数据源"}

        # 运行回测
        engine = BacktestEngine(initial_capital=1000000)
        engine.set_strategy(current_strategy)
        result = engine.run(data_dict)

        return {
            "total_return": result.total_return,
            "annual_return": result.annual_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "final_capital": result.final_capital
        }

    except Exception as e:
        import logging
        logging.error(f"回测失败：{e}", exc_info=True)
        return {"error": f"回测失败：{str(e)}"}


@app.get("/api/strategy/info")
async def get_strategy_info():
    """获取策略信息"""
    global current_strategy

    if current_strategy is None:
        current_strategy = create_optimal_strategy(aggressive=True)

    return {
        "name": current_strategy.name,
        "params": {
            "stop_loss": current_strategy.params.base_stop_loss,
            "take_profit": current_strategy.params.base_take_profit,
            "position_ratio": current_strategy.params.base_position_ratio,
            "ma_short": current_strategy.params.ma_short,
            "ma_long": current_strategy.params.ma_long,
        }
    }


@app.get("/api/config")
async def get_config():
    """获取系统配置信息"""
    import config.settings as settings

    return {
        # 数据库配置
        "database_url": settings.DATABASE_URL.replace("sqlite:///", ""),

        # 交易配置
        "paper_trading": settings.PAPER_TRADING,
        "initial_capital": settings.INITIAL_CAPITAL,
        "max_position_ratio": settings.MAX_POSITION_RATIO,
        "max_stock_position_ratio": settings.MAX_STOCK_POSITION_RATIO,
        "max_order_value": settings.MAX_ORDER_VALUE,

        # 风控配置
        "stop_loss_ratio": settings.STOP_LOSS_RATIO,
        "take_profit_ratio": settings.TAKE_PROFIT_RATIO,

        # 回测配置
        "commission_rate": settings.COMMISSION_RATE,
        "stamp_tax_rate": settings.STAMP_TAX_RATE,
        "slippage_rate": settings.SLIPPAGE_RATE,

        # 调度配置
        "pre_market_time": settings.PRE_MARKET_TIME,
        "monitor_interval": settings.MARKET_MONITOR_INTERVAL,
        "post_market_time": settings.POST_MARKET_TIME,
        "market_open": settings.MARKET_OPEN_TIME,
        "market_close": settings.MARKET_CLOSE_TIME,

        # 策略配置
        "default_stock_pool": settings.DEFAULT_STOCK_POOL,
        "rebalance_frequency": settings.REBALANCE_CONFIG.get('frequency', 'monthly'),

        # 基本面过滤
        "max_pe": settings.FUNDAMENTAL_FILTERS.get('max_pe', 50),
        "min_roe": settings.FUNDAMENTAL_FILTERS.get('min_roe', 0.05),
        "max_debt_ratio": settings.FUNDAMENTAL_FILTERS.get('max_debt_ratio', 0.7),
        "min_market_cap": settings.FUNDAMENTAL_FILTERS.get('min_market_cap', 5000000000),

        # 日志配置
        "log_level": settings.LOG_LEVEL,
        "log_dir": str(settings.LOG_DIR),

        # 钉钉通知配置
        "dingding_enabled": settings.ENABLE_DINGDING_NOTIFY,
        "dingding_webhook": settings.DINGDING_WEBHOOK,
        "dingding_secret": settings.DINGDING_SECRET,
    }


@app.post("/api/dingtalk/test")
async def test_dingtalk():
    """测试钉钉通知"""
    try:
        from src.utils.dingtalk_notifier import DingTalkNotifier

        notifier = DingTalkNotifier()

        if not notifier.webhook:
            return {"success": False, "message": "钉钉 Webhook 未配置"}

        result = notifier.test_connection()

        if result:
            return {"success": True, "message": "测试消息已发送"}
        else:
            return {"success": False, "message": "发送失败，请检查 Webhook 和签名配置"}

    except Exception as e:
        return {"success": False, "message": str(e)}


# === 可视化 API 端点 ===

@app.get("/api/monitoring/factors")
async def get_monitoring_factors(
    start_date: str = None,
    end_date: str = None,
    ts_code: str = None
):
    """获取信号因子详情 (用于雷达图可视化)"""
    try:
        conditions = []
        params = []

        if start_date:
            conditions.append("date(monitor_time) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date(monitor_time) <= ?")
            params.append(end_date)
        if ts_code:
            conditions.append("ts_code = ?")
            params.append(ts_code)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT * FROM monitoring_details {where_clause}
            ORDER BY monitor_time DESC
            LIMIT 100
        """
        df = db.query(sql, tuple(params))

        factors_list = []
        for _, row in df.iterrows():
            factors_list.append({
                "id": int(row['id']),
                "monitor_time": row['monitor_time'],
                "ts_code": row['ts_code'],
                "signal_score": float(row['signal_score']),
                "factors": {
                    "ma_cross": float(row['factor_ma_cross']),
                    "perfect_trend": float(row['factor_perfect_trend']),
                    "macd": float(row['factor_macd']),
                    "rsi": float(row['factor_rsi']),
                    "bb": float(row['factor_bb']),
                    "volume": float(row['factor_volume']),
                    "trend": float(row['factor_trend']),
                },
                "market_state": row['market_state'],
                "signal_direction": row['signal_direction'],
                "trigger_reason": row['trigger_reason'],
                "is_buy_signal": bool(row['is_buy_signal']),
            })

        return {"factors": factors_list, "count": len(factors_list)}

    except Exception as e:
        return {"error": str(e), "factors": [], "count": 0}


@app.get("/api/monitoring/stock-health")
async def get_stock_health():
    """获取股票池健康度 (用于健康度卡片展示)"""
    try:
        stock_pool = ['000063.SZ', '000014.SZ', '000078.SZ', '000039.SZ', '000001.SZ']
        health_data = []

        for ts_code in stock_pool:
            # 获取最近 10 次监控的平均评分
            sql = """
                SELECT
                    ts_code,
                    COUNT(*) as monitor_count,
                    AVG(signal_score) as avg_score,
                    AVG(factor_ma_cross + factor_perfect_trend + factor_macd + factor_rsi + factor_bb + factor_volume + factor_trend) as avg_total_score,
                    SUM(is_buy_signal) as buy_signal_count
                FROM monitoring_details
                WHERE ts_code = ?
                GROUP BY ts_code
            """
            df = db.query(sql, (ts_code,))

            if not df.empty:
                row = df.iloc[0]
                avg_score = float(row['avg_score']) if row['avg_score'] else 0
                # 计算健康度分数 (满分 10.5 分)
                health_score = min(100, int((avg_score / 10.5) * 100))

                # 判断趋势状态
                trend_status = 'unknown'
                if health_score >= 70:
                    trend_status = 'bull'  # 强势
                elif health_score >= 40:
                    trend_status = 'sideways'  # 震荡
                else:
                    trend_status = 'bear'  # 弱势

                health_data.append({
                    "ts_code": ts_code,
                    "health_score": health_score,
                    "avg_score": round(avg_score, 2),
                    "monitor_count": int(row['monitor_count']),
                    "buy_signal_count": int(row['buy_signal_count'] or 0),
                    "trend_status": trend_status,
                })
            else:
                # 无数据时返回默认值
                health_data.append({
                    "ts_code": ts_code,
                    "health_score": 50,
                    "avg_score": 0,
                    "monitor_count": 0,
                    "buy_signal_count": 0,
                    "trend_status": 'unknown',
                })

        # 按健康度排序
        health_data.sort(key=lambda x: x['health_score'], reverse=True)

        return {"stocks": health_data}

    except Exception as e:
        return {"error": str(e), "stocks": []}


@app.get("/api/monitoring/equity-curve")
async def get_equity_curve():
    """获取资金曲线数据 (用于绘制收益趋势图)"""
    try:
        # 首先尝试从 monitoring_logs 获取历史数据
        sql = """
            SELECT
                monitor_time,
                buy_signals_count,
                sell_signals_count,
                trades_executed
            FROM monitoring_logs
            ORDER BY monitor_time ASC
            LIMIT 100
        """
        df = db.query(sql)

        base_capital = 100000

        # 如果没有监控日志，尝试从 orders 表获取交易历史
        if df.empty:
            # 从 orders 表获取交易记录，按日期分组
            sql = """
                SELECT
                    DATE(created_at) as trade_date,
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sell_count
                FROM orders
                GROUP BY DATE(created_at)
                ORDER BY trade_date ASC
                LIMIT 30
            """
            df = db.query(sql)

            if df.empty:
                # 没有任何交易记录，返回初始资金
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                return {
                    "labels": [now],
                    "data": [base_capital],
                    "buy_count": [0],
                    "sell_count": [0],
                    "current_capital": base_capital,
                }

            # 从交易记录计算资金曲线
            labels = []
            capital_data = []
            buy_counts = []
            sell_counts = []
            cumulative_profit = 0

            # 获取当前账户资金
            account_df = db.query("SELECT total_asset FROM accounts WHERE account_name = ?", ("paper_trading",))
            current_capital = float(account_df.iloc[0]['total_asset']) if not account_df.empty else base_capital

            for _, row in df.iterrows():
                labels.append(str(row['trade_date']))
                buy_counts.append(int(row['buy_count'] or 0))
                sell_counts.append(int(row['sell_count'] or 0))
                # 简化：假设每笔卖出交易平均盈利 1%
                cumulative_profit += int(row['sell_count']) * 1000
                capital_data.append(base_capital + cumulative_profit)

            # 更新为当前实际资金
            if capital_data:
                capital_data[-1] = current_capital

            return {
                "labels": labels,
                "data": capital_data,
                "buy_count": buy_counts,
                "sell_count": sell_counts,
                "current_capital": current_capital,
            }

        # 原有逻辑：从 monitoring_logs 计算
        base_capital = 100000
        cumulative_profit = 0
        capital_data = []
        labels = []
        buy_counts = []
        sell_counts = []

        for _, row in df.iterrows():
            labels.append(row['monitor_time'])
            buy_counts.append(int(row['buy_signals_count'] or 0))
            sell_counts.append(int(row['sell_signals_count'] or 0))

            # 简化：假设每个买入信号带来 0.5% 收益，每个卖出信号实现 1% 收益
            if row['buy_signals_count']:
                cumulative_profit += int(row['buy_signals_count']) * 500
            if row['sell_signals_count']:
                cumulative_profit += int(row['sell_signals_count']) * 1000

            capital_data.append(base_capital + cumulative_profit)

        return {
            "labels": labels,
            "data": capital_data,
            "buy_count": buy_counts,
            "sell_count": sell_counts,
            "current_capital": capital_data[-1] if capital_data else base_capital,
        }

    except Exception as e:
        return {"error": str(e), "labels": [], "data": [], "buy_count": [], "sell_count": []}


@app.get("/api/monitoring/market-state")
async def get_market_state_history():
    """获取市场状态历史 (用于绘制市场状态变化图)"""
    try:
        sql = """
            SELECT
                monitor_time,
                market_state,
                COUNT(*) as signal_count
            FROM monitoring_details
            GROUP BY date(monitor_time), market_state
            ORDER BY monitor_time ASC
            LIMIT 50
        """
        df = db.query(sql)

        if df.empty:
            return {"states": [], "labels": []}

        states = []
        labels = []
        bull_count = 0
        bear_count = 0
        sideways_count = 0

        for _, row in df.iterrows():
            labels.append(row['monitor_time'])
            state = row['market_state']
            if state == 'bull':
                bull_count += 1
            elif state == 'bear':
                bear_count += 1
            else:
                sideways_count += 1

            states.append({
                "time": row['monitor_time'],
                "state": state,
                "signal_count": int(row['signal_count']),
            })

        return {
            "states": states,
            "labels": labels,
            "summary": {
                "bull_count": bull_count,
                "bear_count": bear_count,
                "sideways_count": sideways_count,
            }
        }

    except Exception as e:
        return {"error": str(e), "states": [], "labels": [], "summary": {}}


@app.get("/api/monitoring-history")
async def get_monitoring_history(
    start_date: str = None,
    end_date: str = None,
    market_state: str = None
):
    """获取监控历史记录列表"""
    try:
        # 构建查询条件
        conditions = []
        params = []

        if start_date:
            conditions.append("date(monitor_time) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("date(monitor_time) <= ?")
            params.append(end_date)

        if market_state:
            conditions.append("market_state = ?")
            params.append(market_state)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 查询统计摘要
        stats_sql = f"""
            SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(signals_count), 0) as total_signals,
                COALESCE(SUM(buy_signals_count), 0) as total_buy_signals,
                COALESCE(SUM(sell_signals_count), 0) as total_sell_signals,
                COALESCE(SUM(trades_executed), 0) as total_trades
            FROM monitoring_logs {where_clause}
        """
        stats_df = db.query(stats_sql, tuple(params))

        # 查询历史记录（最近 100 条）
        history_sql = f"""
            SELECT * FROM monitoring_logs {where_clause}
            ORDER BY monitor_time DESC
            LIMIT 100
        """
        history_df = db.query(history_sql, tuple(params))

        # 转换为字典列表
        logs = []
        for _, row in history_df.iterrows():
            logs.append({
                "id": int(row['id']),
                "monitor_time": row['monitor_time'],
                "market_state": row['market_state'],
                "stock_pool": row['stock_pool'],
                "stocks_count": int(row['stocks_count']),
                "signals_count": int(row['signals_count']),
                "buy_signals_count": int(row['buy_signals_count']),
                "sell_signals_count": int(row['sell_signals_count']),
                "trades_executed": int(row['trades_executed']),
                "buy_orders": row['buy_orders'],
                "sell_orders": row['sell_orders'],
                "error_message": row['error_message']
            })

        return {
            "total_count": int(stats_df.iloc[0]['total_count']),
            "total_signals": int(stats_df.iloc[0]['total_signals']),
            "total_buy_signals": int(stats_df.iloc[0]['total_buy_signals']),
            "total_sell_signals": int(stats_df.iloc[0]['total_sell_signals']),
            "total_trades": int(stats_df.iloc[0]['total_trades']),
            "logs": logs
        }

    except Exception as e:
        return {
            "total_count": 0,
            "total_signals": 0,
            "total_buy_signals": 0,
            "total_sell_signals": 0,
            "total_trades": 0,
            "logs": [],
            "error": str(e)
        }


@app.get("/api/monitoring-history/{log_id}")
async def get_monitoring_history_detail(log_id: int):
    """获取单条监控历史详情"""
    try:
        df = db.query("SELECT * FROM monitoring_logs WHERE id = ?", (log_id,))

        if df.empty:
            return {"error": "记录不存在"}

        row = df.iloc[0]
        return {
            "id": int(row['id']),
            "monitor_time": row['monitor_time'],
            "market_state": row['market_state'],
            "stock_pool": row['stock_pool'],
            "stocks_count": int(row['stocks_count']),
            "signals_count": int(row['signals_count']),
            "buy_signals_count": int(row['buy_signals_count']),
            "sell_signals_count": int(row['sell_signals_count']),
            "trades_executed": int(row['trades_executed']),
            "buy_orders": row['buy_orders'],
            "sell_orders": row['sell_orders'],
            "error_message": row['error_message']
        }

    except Exception as e:
        return {"error": str(e)}


# === 监控可视化增强 API ===

@app.get("/api/monitoring/signal-distribution")
async def get_signal_distribution():
    """获取信号分布统计 (用于柱状图)"""
    try:
        sql = """
            SELECT
                CASE
                    WHEN signal_score >= 8 THEN '8-10.5 (强买入)'
                    WHEN signal_score >= 6 THEN '6-8 (买入)'
                    WHEN signal_score >= 4 THEN '4-6 (观望)'
                    WHEN signal_score >= 2 THEN '2-4 (弱势)'
                    ELSE '0-2 (极弱)'
                END as score_range,
                COUNT(*) as count,
                SUM(is_buy_signal) as buy_count
            FROM monitoring_details
            GROUP BY score_range
            ORDER BY
                CASE score_range
                    WHEN '8-10.5 (强买入)' THEN 1
                    WHEN '6-8 (买入)' THEN 2
                    WHEN '4-6 (观望)' THEN 3
                    WHEN '2-4 (弱势)' THEN 4
                    ELSE 5
                END
        """
        df = db.query(sql)

        distribution = []
        for _, row in df.iterrows():
            distribution.append({
                'range': row['score_range'],
                'count': int(row['count']),
                'buy_count': int(row['buy_count'] or 0)
            })

        return {"distribution": distribution}

    except Exception as e:
        return {"error": str(e), "distribution": []}


@app.get("/api/monitoring/factor-trend")
async def get_factor_trend(ts_code: str = None, days: int = 7):
    """获取因子趋势 (用于折线图)"""
    try:
        conditions = []
        params = []

        if ts_code:
            conditions.append("ts_code = ?")
            params.append(ts_code)

        date_condition = f"date(monitor_time) >= date('now', '-{days} days')"
        conditions.append(date_condition)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT
                date(monitor_time) as monitor_date,
                AVG(signal_score) as avg_score,
                AVG(factor_ma_cross) as avg_ma_cross,
                AVG(factor_macd) as avg_macd,
                AVG(factor_rsi) as avg_rsi,
                AVG(factor_bb) as avg_bb,
                AVG(factor_trend) as avg_trend,
                COUNT(*) as monitor_count,
                SUM(is_buy_signal) as buy_signals
            FROM monitoring_details
            {where_clause}
            GROUP BY date(monitor_time)
            ORDER BY monitor_date ASC
        """
        df = db.query(sql, tuple(params))

        trend_data = []
        for _, row in df.iterrows():
            trend_data.append({
                'date': row['monitor_date'],
                'avg_score': float(row['avg_score']) if row['avg_score'] else 0,
                'ma_cross': float(row['avg_ma_cross']) if row['avg_ma_cross'] else 0,
                'macd': float(row['avg_macd']) if row['avg_macd'] else 0,
                'rsi': float(row['avg_rsi']) if row['avg_rsi'] else 0,
                'bb': float(row['avg_bb']) if row['avg_bb'] else 0,
                'trend': float(row['avg_trend']) if row['avg_trend'] else 0,
                'buy_signals': int(row['buy_signals'] or 0),
                'monitor_count': int(row['monitor_count'])
            })

        return {"trend": trend_data, "days": days}

    except Exception as e:
        return {"error": str(e), "trend": []}


@app.get("/api/monitoring/stock-correlation")
async def get_stock_correlation():
    """获取股票相关性矩阵 (用于热力图)"""
    try:
        sql = """
            SELECT ts_code, signal_score, factor_ma_cross, factor_macd, factor_rsi, factor_bb, factor_trend
            FROM monitoring_details
            WHERE ts_code IN ('000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ')
            ORDER BY monitor_time DESC
            LIMIT 100
        """
        df = db.query(sql)

        if df.empty:
            return {"matrix": [], "stocks": []}

        # 计算股票间的信号相关性
        stocks = df['ts_code'].unique().tolist()
        matrix = []

        for i, stock1 in enumerate(stocks):
            row = {'stock': stock1}
            stock1_data = df[df['ts_code'] == stock1]['signal_score'].values
            for stock2 in stocks:
                stock2_data = df[df['ts_code'] == stock2]['signal_score'].values
                if len(stock1_data) > 0 and len(stock2_data) > 0:
                    # 简单相关系数计算
                    min_len = min(len(stock1_data), len(stock2_data))
                    data1 = stock1_data[:min_len]
                    data2 = stock2_data[:min_len]
                    mean1 = data1.mean()
                    mean2 = data2.mean()
                    std1 = data1.std()
                    std2 = data2.std()
                    if std1 > 0 and std2 > 0:
                        corr = ((data1 - mean1) * (data2 - mean2)).mean() / (std1 * std2)
                    else:
                        corr = 0
                    row[stock2] = round(corr, 3)
                else:
                    row[stock2] = 0
            matrix.append(row)

        return {"matrix": matrix, "stocks": stocks}

    except Exception as e:
        return {"error": str(e), "matrix": [], "stocks": []}


@app.get("/api/monitoring/alerts")
async def get_monitoring_alerts(limit: int = 50):
    """获取监控告警历史 (用于告警列表)"""
    try:
        sql = """
            SELECT * FROM monitoring_logs
            ORDER BY monitor_time DESC
            LIMIT ?
        """
        df = db.query(sql, (limit,))

        alerts = []
        for _, row in df.iterrows():
            # 计算总信号得分
            total_signals = (row['buy_signals_count'] or 0) + (row['sell_signals_count'] or 0)
            alerts.append({
                'id': int(row['id']),
                'monitor_time': row['monitor_time'],
                'market_state': row['market_state'],
                'buy_signals_count': int(row['buy_signals_count'] or 0),
                'sell_signals_count': int(row['sell_signals_count'] or 0),
                'trades_executed': int(row['trades_executed'] or 0),
                'total_score': float(total_signals)
            })

        return {"alerts": alerts, "count": len(alerts)}

    except Exception as e:
        return {"error": str(e), "alerts": []}


def init_system():
    """初始化系统"""
    global current_strategy, stock_pool, system_start_time

    # 创建策略
    current_strategy = create_optimal_strategy(aggressive=True)

    # 设置股票池
    stock_pool = ['000001.SZ', '000002.SZ', '000063.SZ', '000014.SZ', '000016.SZ']

    # 重置启动时间
    system_start_time = datetime.now()

    print("系统初始化完成")


if __name__ == "__main__":
    init_system()
    uvicorn.run(app, host="0.0.0.0", port=8801)
