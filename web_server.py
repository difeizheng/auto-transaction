"""
量化交易系统 - Web 监控界面 (重构版 v2.0)
使用 FastAPI + WebSocket 提供实时监控

功能：
- WebSocket 实时推送持仓和行情
- 性能指标 API
- 信号历史 API
- 净值曲线 API
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uvicorn
import json
import asyncio
import threading

from src.trader.broker_api import PaperBroker
from src.utils.database import db
from src.performance import get_performance_summary, get_nav_curve
from src.performance.metrics import get_performance_metrics, get_rolling_metrics

app = FastAPI(title="量化交易系统", version="2.0.0")

# 全局状态
system_start_time = datetime.now()
broker: Optional[PaperBroker] = None


# === WebSocket 连接管理 ===

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        """接收新的 WebSocket 连接"""
        await websocket.accept()
        with self._lock:
            self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """断开 WebSocket 连接"""
        with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict):
        """广播消息到所有连接"""
        with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass  # 忽略发送失败的连接


# 全局实例
manager = ConnectionManager()


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
    buy_date: str = ""


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


# === WebSocket 端点 ===

@app.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """
    持仓实时推送
    每 10 秒推送一次持仓状态
    """
    await manager.connect(websocket)

    try:
        while True:
            # 获取持仓数据
            positions = []
            if broker and broker.is_connected():
                try:
                    positions = broker.get_positions()
                    account = broker.get_account_info()

                    # 格式化持仓数据
                    position_details = []
                    for pos in positions:
                        ts = pos.get('ts_code', '')
                        # 尝试获取实时价格
                        current_price = pos.get('current_price', pos.get('avg_cost', 0))
                        volume = pos.get('volume', 0)
                        avg_cost = pos.get('avg_cost', 0)

                        market_value = current_price * volume
                        profit_loss = (current_price - avg_cost) * volume
                        profit_ratio = (current_price / avg_cost - 1) * 100 if avg_cost > 0 else 0

                        position_details.append({
                            'ts_code': ts,
                            'volume': volume,
                            'avg_cost': avg_cost,
                            'current_price': current_price,
                            'market_value': market_value,
                            'profit_loss': profit_loss,
                            'profit_ratio': round(profit_ratio, 2),
                            'buy_date': pos.get('buy_date', '')
                        })

                    # 发送数据
                    await websocket.send_json({
                        'type': 'portfolio',
                        'account': account,
                        'positions': position_details,
                        'timestamp': datetime.now().isoformat()
                    })

                except Exception as e:
                    await websocket.send_json({
                        'type': 'error',
                        'message': str(e)
                    })

            # 等待下一次推送
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


# === REST API ===

@app.get("/")
async def root():
    """返回监控界面"""
    return HTMLResponse(HTML_TEMPLATE)


@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    global broker

    # 初始化 broker（如未初始化）
    if broker is None:
        broker = PaperBroker(initial_capital=20000)
        broker.connect()

    uptime = (datetime.now() - system_start_time).total_seconds()

    return {
        "status": "running" if broker.is_connected() else "stopped",
        "start_time": system_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_seconds": int(uptime),
        "active_strategy": "TechnicalStrategy",
        "stock_pool_size": 46,
        "data_bars": 0
    }


@app.get("/api/account")
async def get_account():
    """获取账户信息"""
    global broker

    if broker is None:
        broker = PaperBroker(initial_capital=20000)
        broker.connect()

    account = broker.get_account_info()

    return {
        "total_assets": account.get("total_asset", 0),
        "available_cash": account.get("available_cash", 0),
        "position_value": account.get("total_position_value", 0),
        "total_profit": account.get("total_asset", 0) - 20000,
        "total_profit_ratio": (account.get("total_asset", 20000) / 20000 - 1) * 100
    }


@app.get("/api/positions")
async def get_positions():
    """获取持仓列表"""
    global broker

    if broker is None:
        broker = PaperBroker(initial_capital=20000)
        broker.connect()

    positions = broker.get_positions()

    # 格式化
    result = []
    for pos in positions:
        result.append({
            "ts_code": pos.get("ts_code"),
            "volume": pos.get("volume"),
            "avg_cost": pos.get("avg_cost"),
            "current_price": pos.get("current_price", 0),
            "market_value": pos.get("market_value", 0),
            "profit_loss": pos.get("profit_loss", 0),
            "profit_ratio": pos.get("profit_ratio", 0),
            "buy_date": pos.get("buy_date", "")
        })

    return result


@app.get("/api/performance/summary")
async def get_perf_summary(days: int = 30):
    """获取绩效摘要"""
    summary = get_performance_metrics(days)
    return summary


@app.get("/api/performance/nav")
async def get_nav(days: int = 90):
    """获取净值曲线"""
    curve = get_nav_curve(days)

    # 格式化
    result = []
    for record in curve:
        result.append({
            "date": record.get("date"),
            "nav": record.get("nav", 1),
            "daily_return": record.get("daily_return", 0) * 100,
            "benchmark_change": record.get("benchmark_change", 0) * 100,
            "excess_return": record.get("excess_return", 0) * 100
        })

    return result


@app.get("/api/performance/rolling")
async def get_rolling(window: int = 30):
    """获取滚动指标"""
    metrics = get_rolling_metrics(window, 5)
    return metrics


@app.get("/api/signals")
async def get_signals(days: int = 30, status: str = None):
    """获取信号历史"""
    start_date = (datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')

    sql = "SELECT * FROM signals WHERE signal_date >= ?"
    params = [start_date]

    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY signal_date DESC, execute_date DESC"

    try:
        df = db.query(sql, tuple(params))
        if df.empty:
            return []

        return df.to_dict('records')
    except Exception as e:
        return []


@app.get("/api/trades")
async def get_trades(days: int = 30):
    """获取交易历史"""
    start_date = (datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')

    try:
        df = db.query("""
            SELECT * FROM trades
            WHERE trade_date >= ?
            ORDER BY trade_date DESC, created_at DESC
        """, (start_date,))

        if df.empty:
            return []

        return df.to_dict('records')
    except Exception:
        # 表可能不存在
        return []


# === HTML 模板 ===

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>量化交易系统监控 v2.0</title>
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
            padding: 12px 24px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            color: #fff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .nav-btn:hover, .nav-btn.active {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border-color: transparent;
        }

        /* 页面内容 */
        .page { display: none; }
        .page.active { display: block; }

        /* 指标卡片 */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .metric-label { color: #888; margin-top: 5px; }

        /* 表格 */
        table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { background: rgba(255,255,255,0.1); }
        .profit-positive { color: #4caf50; }
        .profit-negative { color: #f44336; }

        /* 图表容器 */
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .chart { width: 100%; height: 400px; }

        /* 状态指示 */
        .status-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4caf50;
            margin-right: 5px;
        }
        .status-dot.stopped { background: #f44336; }
    </style>
</head>
<body>
    <div class="container">
        <h1>量化交易系统监控 v2.0</h1>

        <div class="nav">
            <button class="nav-btn active" onclick="showPage('portfolio')">实盘面板</button>
            <button class="nav-btn" onclick="showPage('signals')">信号面板</button>
            <button class="nav-btn" onclick="showPage('performance')">绩效面板</button>
            <button class="nav-btn" onclick="showPage('trades')">交易记录</button>
        </div>

        <!-- 实盘面板 -->
        <div id="portfolio" class="page active">
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value" id="total-assets">--</div>
                    <div class="metric-label">总资产 (元)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="available-cash">--</div>
                    <div class="metric-label">可用资金 (元)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="position-value">--</div>
                    <div class="metric-label">持仓市值 (元)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="total-profit">--</div>
                    <div class="metric-label">总盈亏 (元)</div>
                </div>
            </div>

            <h3>持仓明细</h3>
            <table>
                <thead>
                    <tr>
                        <th>股票代码</th>
                        <th>持仓量</th>
                        <th>成本价</th>
                        <th>当前价</th>
                        <th>市值</th>
                        <th>盈亏</th>
                        <th>盈亏比</th>
                        <th>买入日期</th>
                    </tr>
                </thead>
                <tbody id="positions-table">
                    <tr><td colspan="8">加载中...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- 信号面板 -->
        <div id="signals" class="page">
            <h3>最近交易信号</h3>
            <table>
                <thead>
                    <tr>
                        <th>股票代码</th>
                        <th>方向</th>
                        <th>信号日期</th>
                        <th>执行日期</th>
                        <th>目标价</th>
                        <th>成交量</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody id="signals-table">
                    <tr><td colspan="7">加载中...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- 绩效面板 -->
        <div id="performance" class="page">
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value" id="current-nav">--</div>
                    <div class="metric-label">当前净值</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="total-return">--</div>
                    <div class="metric-label">累计收益 (%)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="annualized-return">--</div>
                    <div class="metric-label">年化收益 (%)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="sharpe-ratio">--</div>
                    <div class="metric-label">夏普比率</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="max-drawdown">--</div>
                    <div class="metric-label">最大回撤 (%)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="win-rate">--</div>
                    <div class="metric-label">胜率 (%)</div>
                </div>
            </div>

            <div class="chart-container">
                <div id="nav-chart" class="chart"></div>
            </div>

            <div class="chart-container">
                <div id="rolling-chart" class="chart"></div>
            </div>
        </div>

        <!-- 交易记录 -->
        <div id="trades" class="page">
            <h3>最近交易记录</h3>
            <table>
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>股票代码</th>
                        <th>方向</th>
                        <th>价格</th>
                        <th>数量</th>
                        <th>金额</th>
                    </tr>
                </thead>
                <tbody id="trades-table">
                    <tr><td colspan="6">加载中...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // 页面切换
        function showPage(pageId) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(pageId).classList.add('active');
            event.target.classList.add('active');
        }

        // 获取账户数据
        async function fetchAccount() {
            try {
                const res = await fetch('/api/account');
                const data = await res.json();
                document.getElementById('total-assets').textContent = data.total_assets.toFixed(2);
                document.getElementById('available-cash').textContent = data.available_cash.toFixed(2);
                document.getElementById('position-value').textContent = data.position_value.toFixed(2);

                const profitEl = document.getElementById('total-profit');
                profitEl.textContent = data.total_profit.toFixed(2);
                profitEl.style.color = data.total_profit >= 0 ? '#4caf50' : '#f44336';
            } catch(e) { console.error(e); }
        }

        // 获取持仓数据
        async function fetchPositions() {
            try {
                const res = await fetch('/api/positions');
                const positions = await res.json();
                const tbody = document.getElementById('positions-table');

                if (positions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8">暂无持仓</td></tr>';
                    return;
                }

                tbody.innerHTML = positions.map(p => `
                    <tr>
                        <td>${p.ts_code}</td>
                        <td>${p.volume}</td>
                        <td>${p.avg_cost.toFixed(2)}</td>
                        <td>${p.current_price.toFixed(2)}</td>
                        <td>${p.market_value.toFixed(2)}</td>
                        <td class="${p.profit_loss >= 0 ? 'profit-positive' : 'profit-negative'}">${p.profit_loss.toFixed(2)}</td>
                        <td class="${p.profit_ratio >= 0 ? 'profit-positive' : 'profit-negative'}">${p.profit_ratio.toFixed(2)}%</td>
                        <td>${p.buy_date || '-'}</td>
                    </tr>
                `).join('');
            } catch(e) { console.error(e); }
        }

        // 获取信号数据
        async function fetchSignals() {
            try {
                const res = await fetch('/api/signals?days=30');
                const signals = await res.json();
                const tbody = document.getElementById('signals-table');

                if (signals.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7">暂无信号</td></tr>';
                    return;
                }

                tbody.innerHTML = signals.slice(0, 20).map(s => `
                    <tr>
                        <td>${s.ts_code}</td>
                        <td class="${s.direction === 'buy' ? 'profit-positive' : 'profit-negative'}">${s.direction}</td>
                        <td>${s.signal_date}</td>
                        <td>${s.execute_date}</td>
                        <td>${s.target_price.toFixed(2)}</td>
                        <td>${s.volume}</td>
                        <td>${s.status}</td>
                    </tr>
                `).join('');
            } catch(e) { console.error(e); }
        }

        // 获取绩效数据
        async function fetchPerformance() {
            try {
                const res = await fetch('/api/performance/summary?days=90');
                const data = await res.json();

                document.getElementById('current-nav').textContent = (data.current_nav || 1).toFixed(4);
                document.getElementById('total-return').textContent = (data.total_return || 0).toFixed(2);
                document.getElementById('annualized-return').textContent = (data.annualized_return || 0).toFixed(2);
                document.getElementById('sharpe-ratio').textContent = data.sharpe_ratio || 0;
                document.getElementById('max-drawdown').textContent = data.max_drawdown || 0;
                document.getElementById('win-rate').textContent = data.win_rate || 0;

                // 绘制净值曲线
                fetchNavChart();
            } catch(e) { console.error(e); }
        }

        // 绘制净值曲线
        let navChart, rollingChart;
        async function fetchNavChart() {
            try {
                const res = await fetch('/api/performance/nav?days=90');
                const data = await res.json();

                if (!navChart) {
                    navChart = echarts.init(document.getElementById('nav-chart'));
                }

                const dates = data.map(d => d.date);
                const navs = data.map(d => d.nav);
                const excess = data.map(d => d.excess_return);

                navChart.setOption({
                    title: { text: '净值曲线', textStyle: { color: '#fff' } },
                    tooltip: { trigger: 'axis' },
                    legend: { data: ['净值', '超额收益'], textStyle: { color: '#fff' } },
                    xAxis: { type: 'category', data: dates, axisLabel: { color: '#fff' } },
                    yAxis: [
                        { type: 'value', name: '净值', axisLabel: { color: '#fff' } },
                        { type: 'value', name: '超额%', axisLabel: { color: '#fff' } }
                    ],
                    series: [
                        { name: '净值', type: 'line', data: navs, smooth: true },
                        { name: '超额收益', type: 'line', yAxisIndex: 1, data: excess }
                    ]
                });
            } catch(e) { console.error(e); }
        }

        // 获取交易记录
        async function fetchTrades() {
            try {
                const res = await fetch('/api/trades?days=30');
                const trades = await res.json();
                const tbody = document.getElementById('trades-table');

                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6">暂无交易记录</td></tr>';
                    return;
                }

                tbody.innerHTML = trades.slice(0, 20).map(t => `
                    <tr>
                        <td>${t.trade_date || t.created_at}</td>
                        <td>${t.ts_code}</td>
                        <td class="${t.direction === 'buy' ? 'profit-positive' : 'profit-negative'}">${t.direction}</td>
                        <td>${t.price.toFixed(2)}</td>
                        <td>${t.volume}</td>
                        <td>${t.amount.toFixed(2)}</td>
                    </tr>
                `).join('');
            } catch(e) { console.error(e); }
        }

        // 初始化
        async function init() {
            await fetchAccount();
            await fetchPositions();
            await fetchSignals();
            await fetchPerformance();
            await fetchTrades();

            // 每30秒刷新
            setInterval(async () => {
                await fetchAccount();
                await fetchPositions();
            }, 30000);
        }

        init();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)