# 中国股票量化自动交易系统

一个模块化的 A 股量化交易平台，支持策略研发、回测验证、模拟交易和实盘监控。

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 功能特性

### 核心功能

- **数据采集**: 自动获取沪深 A 股日线/分钟线行情和财务数据 (Tushare/Baostock/新浪财经)
- **策略开发**: 支持多因子、技术指标、趋势跟踪、均值回归等多种策略类型
- **回测引擎**: 完整的回测框架，支持绩效分析、归因分析和跨周期验证
- **交易执行**: 订单管理、风险控制、模拟/实盘交易接口 (支持华泰/银河/国金等券商)
- **自动调度**: 定时任务、盘前准备、盘中监控、盘后分析
- **实时监控**: Web 监控界面、钉钉通知、异常告警

### 策略库

| 策略类型 | 文件 | 说明 |
|----------|------|------|
| 最优综合策略 | `optimal_strategy.py` | 多因子综合 + 市场自适应 + 动态仓位 |
| 趋势跟踪策略 | `trend_follow.py` | 均线趋势 + 突破入场 + 移动止损 |
| 均值回归策略 | `mean_reversion.py` | RSI 超买超卖 + 布林带回归 |
| 多策略组合 | `multi_strategy_portfolio.py` | 多策略并行 + 信号聚合 + 动态权重 |

### 优化模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 夏普比率优化 | `sharpe_optimizer.py` | 波动率过滤 + 稳定性因子 + 分级止盈 |
| 胜率优化 | `win_rate_optimizer.py` | 动量因子 + 资金流 + 强势股筛选 |
| 基本面因子 | `fundamental_factors.py` | ROE/增长/估值/健康/市值五因子评分 |
| 市场状态过滤 | `market_filter.py` | 牛熊判断 + 仓位控制 + MACD/RSI 增强 |

## 项目结构

```
auto-transaction/
├── config/                  # 配置文件
│   ├── settings.py          # 系统配置
│   └── logging_config.py    # 日志配置
├── data/                    # 数据存储
│   └── quant_trading.db     # SQLite 数据库
├── src/                     # 源代码
│   ├── data_collector/      # 数据采集模块
│   │   ├── tushare_client.py    # Tushare 接口
│   │   ├── baostock_client.py   # Baostock 接口
│   │   ├── sina_client.py       # 新浪财经实时行情
│   │   └── data_manager.py      # 数据管理
│   ├── strategy/            # 策略模块
│   │   ├── base_strategy.py     # 策略基类
│   │   ├── optimal_strategy.py  # 最优综合策略
│   │   ├── trend_follow.py      # 趋势跟踪
│   │   ├── mean_reversion.py    # 均值回归
│   │   ├── sharpe_optimizer.py  # 夏普优化
│   │   ├── win_rate_optimizer.py # 胜率优化
│   │   ├── fundamental_factors.py # 基本面因子
│   │   ├── market_filter.py     # 市场过滤
│   │   └── multi_strategy_portfolio.py # 多策略组合
│   ├── backtest/            # 回测模块
│   │   ├── engine.py            # 回测引擎
│   │   └── performance.py       # 绩效分析
│   ├── trader/              # 交易执行模块
│   │   ├── risk_control.py      # 风险控制
│   │   ├── scheduler.py         # 调度器
│   │   ├── realtime_monitor.py  # 实时监控
│   │   └── emergency_handler.py # 紧急处理
│   └── utils/               # 工具模块
│       ├── database.py          # 数据库
│       ├── helpers.py           # 辅助函数
│       └── dingtalk_notifier.py # 钉钉通知
├── scripts/                 # 工具脚本
│   ├── strategy_v5_backtest.py  # v5.0 回测对比
│   ├── parameter_sensitivity.py # 参数敏感性测试
│   └── fetch_historical_data.py # 历史数据获取
├── docs/                    # 文档
├── logs/                    # 日志目录
├── web_server.py            # Web 监控服务
├── main.py                  # 主程序入口
└── start_services.py        # 服务启动脚本
```

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
# Tushare Token (https://tushare.pro)
TUSHARE_TOKEN=your_token

# 数据库配置
DATABASE_URL=sqlite:///data/quant_trading.db

# 钉钉通知 (可选)
DINGDING_WEBHOOK=your_webhook
DINGDING_SECRET=your_secret
ENABLE_DINGDING_NOTIFY=true

# 交易配置
PAPER_TRADING=true
REAL_TRADING_MODE=false
```

### 3. 初始化数据库

```bash
python -m src.utils.database
```

### 4. 获取历史数据

```bash
# 获取默认股票池数据
python main.py update-data

# 获取扩展股票池数据 (30 只)
python main.py update-data --extended-pool

# 获取长期历史数据 (使用 Baostock)
python scripts/fetch_historical_data.py
```

## 使用指南

### 回测

```bash
# 基础回测 (最优策略)
python main.py backtest --strategy optimal

# 指定日期范围
python main.py backtest --strategy optimal \
    --start-date 20240324 --end-date 20260323

# 使用扩展股票池
python main.py backtest --strategy optimal --use-extended-pool

# 跨周期回测
python main.py cross-cycle --strategy optimal --years 3
```

### 模拟交易

```bash
# 启动模拟盘 (最优策略)
python main.py paper --strategy optimal --paper-capital 100000

# 启动稳健版模拟盘
python start_paper_conservative.py

# 启动调度器 (自动监控和交易)
python start_services.py scheduler
```

### Web 监控界面

```bash
# 启动 Web 服务
python web_server.py

# 访问监控面板
# http://localhost:8801
```

#### Web 界面功能

| 页面 | 路径 | 功能 |
|------|------|------|
| 总览面板 | `/` | 账户概览、持仓明细、当日交易 |
| 回测分析 | `/backtest` | 策略回测、绩效分析、参数优化 |
| 信号监控 | `/monitoring` | 实时信号、因子得分、市场状态 |
| 监控历史 | `/monitoring-history` | 历史监控记录、信号统计 |
| 告警历史 | `/alerts` | 系统告警、异常检测 |

### 钉钉通知

系统支持交易执行、止损止盈、每日总结等钉钉通知：

```bash
# 在 .env 中启用
ENABLE_DINGDING_NOTIFY=true
DINGDING_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGDING_SECRET=xxx
```

## 策略配置

### 最优策略参数 (v5.0)

```python
# 止损止盈
stop_loss = 0.035          # 3.5% 紧止损
take_profit = 0.40         # 40% 宽止盈
trailing_stop_trigger = 0.15  # 移动止损触发 15%

# 信号阈值
signal_threshold = 5.2     # 综合评分阈值 (总分 13.5)

# 仓位管理
base_position_ratio = 0.35   # 基础仓位 35%
max_position_ratio = 0.55    # 牛市最大 55%
bear_position_ratio = 0.02   # 熊市仓位 2%
```

### 多策略组合配置

```python
from src.strategy.multi_strategy_portfolio import create_multi_strategy_portfolio

# 创建多策略组合
portfolio = create_multi_strategy_portfolio(
    enable_optimal=True,      # 最优综合策略
    enable_trend=True,        # 趋势跟踪策略
    enable_mean_reversion=True, # 均值回归策略
    weight_method="equal"     # 等权重/动态权重
)
```

## 风控参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| MAX_POSITION_RATIO | 0.8 | 最大仓位比例 |
| STOP_LOSS_RATIO | 0.05 | 止损比例 |
| TAKE_PROFIT_RATIO | 0.15 | 止盈比例 |
| MAX_ORDER_VALUE | 100000 | 单笔最大金额 |
| MAX_STOCK_POSITION_RATIO | 0.2 | 单只股票最大持仓 |
| MAX_DAILY_LOSS | 0.03 | 单日最大亏损 |

## 实盘部署

### 前置条件

1. 开通证券账户，获取 easytrader 支持
2. 配置券商账户信息 (`config/broker_config.json`)
3. 准备足够资金，完成模拟盘验证

### 部署步骤

```bash
# 1. 配置券商账户
cp config/broker_config.json.example config/broker_config.json
# 编辑配置：券商类型、账号、密码等

# 2. 启用实盘模式
# 在 .env 中设置
REAL_TRADING_MODE=true
USE_REALTIME_DATA=true

# 3. 启动实盘监控
python run_paper_trading.py  # 模拟盘
# 或
python start_services.py real-trading  # 实盘

# 4. 启动 Web 监控
python web_server.py
```

### 服务进程管理

使用 systemd (Linux) 或 Task Scheduler (Windows) 管理进程：

```ini
# /etc/systemd/system/quant-trading.service
[Unit]
Description=Quantitative Trading System
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/path/to/auto-transaction
ExecStart=/path/to/venv/bin/python start_services.py scheduler
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# 启动服务
sudo systemctl start quant-trading
sudo systemctl enable quant-trading
```

## 性能基准

### 策略 v5.0 回测结果 (20240324-20260323)

| 策略版本 | 年化收益 | 夏普比率 | 最大回撤 | 胜率 | 盈亏比 |
|----------|----------|----------|----------|------|--------|
| v4.0 基准 | 1.97% | 0.24 | 6.96% | 37.04% | 1.48 |
| v5.0 夏普增强 | 3.20% | 0.35 | 6.03% | 42.31% | 1.82 |
| v5.0 综合优化 | 3.20% | 0.35 | 6.03% | 42.31% | 1.82 |

**优化方向**:
- 夏普比率目标：1.0+
- 胜率目标：55%+
- 年化收益目标：15%+

## 常见问题

### Q: 如何获取 Tushare Token?
A: 注册 https://tushare.pro 并在个人中心获取 Token

### Q: 数据更新频率？
A: 日线数据 T+1 盘后更新，实时行情盘中 10 秒轮询

### Q: 如何添加新策略？
A: 继承 `src/strategy/base_strategy.py` 的 `BaseStrategy` 类，实现 `on_bar()` 方法

### Q: 回测和实盘差异大？
A: 检查滑点、手续费设置，验证数据完整性，确认交易成本计算

## 开发计划

- [x] 基础框架搭建
- [x] 数据采集模块
- [x] 策略框架开发
- [x] 回测引擎
- [x] 交易执行模块
- [x] 自动化调度
- [x] Web 监控界面
- [x] 策略优化 v5.0
- [ ] 更多策略类型
- [ ] AI 增强功能
- [ ] 组合优化器

## 注意事项

⚠️ **合规提醒**: 请遵守中国交易所规定，避免高频交易和异常交易行为

⚠️ **投资风险**: 量化策略可能失效，历史回测不代表未来收益。实盘前请充分测试

⚠️ **数据安全**: 请妥善保管 API Token 和券商账户信息，不要提交到版本控制

## 相关资源

- [Tushare 文档](https://tushare.pro/document/2)
- [Baostock 文档](http://baostock.com/baostock/index.php/Python_API 文档)
- [easytrader 文档](https://github.com/shidenggui/easytrader)

## License

MIT
