# 中国股票量化自动交易系统

一个模块化的 A 股量化交易平台，支持策略研发、回测验证和实盘交易。

## 功能特性

- **数据采集**: 自动获取沪深 A 股行情和财务数据 (Tushare/Baostock)
- **策略开发**: 支持多因子、技术指标、机器学习等多种策略
- **回测引擎**: 完整的回测框架，支持绩效分析和归因分析
- **交易执行**: 订单管理、风险控制、模拟/实盘交易接口
- **自动调度**: 定时任务、盘前准备、盘后分析、通知告警

## 项目结构

```
auto-transaction/
├── config/                  # 配置文件
├── data/                    # 数据存储
├── src/                     # 源代码
│   ├── data_collector/      # 数据采集模块
│   ├── strategy/            # 策略模块
│   ├── backtest/            # 回测模块
│   ├── trader/              # 交易执行模块
│   └── utils/               # 工具模块
├── notebooks/               # Jupyter 研究笔记
├── tests/                   # 测试目录
├── logs/                    # 日志目录
└── ...
```

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
TUSHARE_TOKEN=your_token
DATABASE_URL=sqlite:///data/quant_trading.db
```

### 3. 初始化数据库

```bash
python -m src.utils.database
```

### 4. 运行回测

```bash
python -m src.backtest.engine
```

## 策略示例

### 多因子策略

```python
from src.strategy.multi_factor import MultiFactorStrategy

strategy = MultiFactorStrategy(
    factors=['pe', 'pb', 'roe', 'momentum'],
    top_n=10
)
```

### 技术指标策略

```python
from src.strategy.technical import MACDStrategy

strategy = MACDStrategy(
    fast_period=12,
    slow_period=26,
    signal_period=9
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

## 注意事项

⚠️ **合规提醒**: 请遵守中国交易所规定，避免高频交易和异常交易行为

⚠️ **投资风险**: 量化策略可能失效，历史回测不代表未来收益

## 开发计划

- [x] 基础框架搭建
- [x] 数据采集模块
- [x] 策略框架开发
- [x] 回测引擎
- [x] 交易执行模块
- [x] 自动化调度
- [ ] Web 监控界面
- [ ] 更多策略类型
- [ ] AI 增强功能

## License

MIT
