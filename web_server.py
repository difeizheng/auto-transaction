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
        #equity-chart {
            width: 100%;
            height: 300px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 量化交易系统监控</h1>

        <!-- 导航栏 -->
        <div class="nav">
            <button class="nav-btn active" onclick="showPage('monitor')">📈 实时监控</button>
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

        // 初始化
        refreshData();
        refreshConfig();
        setInterval(refreshData, 5000);  // 每 5 秒刷新监控数据
        setInterval(refreshConfig, 10000);  // 每 10 秒刷新配置
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


@app.post("/api/backtest")
async def run_backtest():
    """运行回测"""
    global current_strategy

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
