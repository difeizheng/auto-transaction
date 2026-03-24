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

    <script>
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

        function refreshData() {
            fetchStatus();
            fetchAccount();
            fetchPositions();
            fetchTrades();
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
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

        // 初始化
        refreshData();
        setInterval(refreshData, 5000);  // 每 5 秒刷新
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
    """获取账户信息"""
    global paper_broker

    if paper_broker is None:
        # 创建模拟账户
        paper_broker = PaperBroker(initial_capital=100000)
        paper_broker.connect()

    if not paper_broker.is_connected():
        return {
            "total_assets": 100000,
            "available_cash": 100000,
            "position_value": 0,
            "total_profit": 0,
            "total_profit_ratio": 0
        }

    summary = paper_broker.get_account_info()

    return {
        "total_assets": float(summary.get('total_asset', 100000)),
        "available_cash": float(summary.get('available_cash', 100000)),
        "position_value": float(summary.get('position_value', 0)),
        "total_profit": float(summary.get('total_profit', 0)),
        "total_profit_ratio": float(summary.get('total_profit_ratio', 0))
    }


@app.get("/api/positions")
async def get_positions():
    """获取持仓信息"""
    global paper_broker

    if paper_broker is None:
        paper_broker = PaperBroker(initial_capital=100000)
        paper_broker.connect()

    if not paper_broker.is_connected():
        return []

    positions = paper_broker.get_positions()
    result = []

    for pos in positions:
        result.append({
            "ts_code": pos.get('ts_code', ''),
            "volume": pos.get('volume', 0),
            "avg_cost": float(pos.get('avg_cost', 0)),
            "current_price": float(pos.get('current_price', 0)),
            "market_value": float(pos.get('market_value', 0)),
            "profit_loss": float(pos.get('profit_loss', 0)),
            "profit_ratio": float(pos.get('profit_ratio', 0))
        })

    return result


@app.get("/api/trades")
async def get_trades():
    """获取交易记录"""
    global paper_broker

    if paper_broker is None:
        paper_broker = PaperBroker(initial_capital=100000)
        paper_broker.connect()

    if not paper_broker.is_connected():
        return []

    # 获取订单记录
    orders = paper_broker.get_orders()
    result = []

    for order in orders[-20:]:  # 最近 20 条
        result.append({
            "ts_code": order.get('ts_code', ''),
            "direction": order.get('direction', ''),
            "price": float(order.get('price', 0)),
            "volume": order.get('volume', 0),
            "timestamp": order.get('create_time', ''),
            "profit_loss": None
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
