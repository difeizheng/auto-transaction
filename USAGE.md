# 量化交易系统使用指南

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（可选）
python -m venv venv

# Windows 激活虚拟环境
venv\Scripts\activate

# Mac/Linux 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

`.env` 文件已配置好 Tushare API Token，如需修改请编辑该文件。

### 3. 初始化系统

```bash
# 初始化数据库
python main.py init
```

### 4. 更新数据

```bash
# 更新最近 30 天的数据
python main.py update --days 30

# 更新最近一年的数据
python main.py update --days 365
```

### 5. 运行回测

```bash
# 使用默认策略回测
python main.py backtest

# 指定策略类型
python main.py backtest --strategy macd
python main.py backtest --strategy ma
python main.py backtest --strategy factor
```

### 6. 模拟交易

```bash
# 运行模拟交易演示
python main.py paper
```

---

## 命令行参数

```
usage: main.py [-h] [--days DAYS] [--start-date START_DATE]
               [--end-date END_DATE] [--strategy STRATEGY]
               [--capital CAPITAL]
               {init,update,backtest,paper,trade}

命令说明:
  init                初始化数据库
  update              更新行情数据
  backtest            运行回测
  paper               模拟交易
  trade               实盘交易 (需配置券商)

可选参数:
  --days DAYS         更新数据的天数 (默认：30)
  --start-date        回测开始日期 YYYYMMDD
  --end-date          回测结束日期 YYYYMMDD
  --strategy          策略类型：technical/macd/ma/factor
  --capital           初始资金 (默认：20000)
```

---

## 项目结构

```
auto-transaction/
├── config/                  # 配置文件
│   ├── settings.py          # 系统配置
│   └── logging_config.py    # 日志配置
├── data/                    # 数据存储
│   ├── raw/                 # 原始数据
│   ├── processed/           # 处理后数据
│   └── cache/               # 缓存数据
├── src/                     # 源代码
│   ├── data_collector/      # 数据采集模块
│   │   ├── tushare_client.py
│   │   ├── baostock_client.py
│   │   └── data_manager.py
│   ├── strategy/            # 策略模块
│   │   ├── base_strategy.py
│   │   ├── technical.py     # 技术指标策略
│   │   ├── multi_factor.py  # 多因子策略
│   │   └── ml_strategy.py   # 机器学习策略
│   ├── backtest/            # 回测模块
│   │   ├── engine.py        # 回测引擎
│   │   ├── performance.py   # 绩效分析
│   │   └── analyzer.py      # 归因分析
│   ├── trader/              # 交易执行模块
│   │   ├── order_manager.py
│   │   ├── risk_control.py  # 风控模块
│   │   ├── broker_api.py    # 券商接口
│   │   └── scheduler.py     # 调度器
│   └── utils/               # 工具模块
│       ├── database.py      # 数据库操作
│       └── helpers.py       # 辅助函数
├── notebooks/               # Jupyter 研究笔记
├── scripts/                 # 脚本
│   ├── run_backtest.py      # 回测脚本
│   └── paper_trading.py     # 模拟交易脚本
├── tests/                   # 测试
├── logs/                    # 日志目录
├── main.py                  # 主程序入口
└── requirements.txt         # 依赖
```

---

## 策略说明

### 技术指标策略 (TechnicalStrategy)

综合多个技术指标生成交易信号：
- 均线 (MA5/10/20)
- MACD
- RSI
- 布林带

```python
from src.strategy.technical import TechnicalStrategy

strategy = TechnicalStrategy(
    name="technical_strategy",
    params=None  # 使用默认参数
)
```

### MACD 策略 (MACDStrategy)

基于 MACD 金叉/死叉信号：

```python
from src.strategy.technical import MACDStrategy

strategy = MACDStrategy(
    name="macd_strategy",
    fast_period=12,
    slow_period=26,
    signal_period=9
)
```

### 均线交叉策略 (MaCrossoverStrategy)

基于短期均线上穿/下穿长期均线：

```python
from src.strategy.technical import MaCrossoverStrategy

strategy = MaCrossoverStrategy(
    name="ma_crossover",
    short_period=5,
    long_period=20
)
```

### 多因子策略 (MultiFactorStrategy)

基于多个因子评分选股：

```python
from src.strategy.multi_factor import MultiFactorStrategy

strategy = MultiFactorStrategy(
    name="multi_factor",
    factors=['pe', 'pb', 'roe', 'momentum'],
    top_n=10,          # 选取前 10 只
    rebalance_days=5   # 5 天调仓一次
)
```

---

## 风控参数配置

在 `config/settings.py` 中配置：

```python
# 仓位限制
MAX_POSITION_RATIO = 0.95         # 最大仓位 95% (激进)
MAX_STOCK_POSITION_RATIO = 0.30   # 单只股票最大 30%

# 止损止盈
STOP_LOSS_RATIO = 0.08            # 止损 8%
TAKE_PROFIT_RATIO = 0.20          # 止盈 20%

# 交易限制
MAX_ORDER_VALUE = 20000           # 单笔最大 2 万
MAX_CONCENTRATION = 5             # 最多持有 5 只股票

# 回撤控制
MAX_DRAWDOWN = 0.15               # 最大回撤 15%
```

---

## 使用 Jupyter Notebook

### 数据探索

```bash
# 打开数据探索笔记
jupyter notebook notebooks/data_exploration.ipynb
```

### 策略研究

```bash
# 打开策略研究笔记
jupyter notebook notebooks/strategy_research.ipynb
```

---

## 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/test_data.py -v
pytest tests/test_strategy.py -v
pytest tests/test_backtest.py -v
```

---

## 常见问题

### Q: Tushare API 报错？
A: 检查 `.env` 文件中的 `TUSHARE_TOKEN` 是否正确配置。

### Q: 数据库初始化失败？
A: 确保有写入权限，`data/` 目录存在。

### Q: 回测结果为空？
A: 检查数据是否已更新，股票池是否有数据。

### Q: 模拟交易不产生信号？
A: 策略需要积累足够的历史数据才能生成信号，耐心等待或增加数据天数。

---

## 风险提示

⚠️ **投资有风险，入市需谨慎**

- 本系统仅供学习研究使用
- 历史回测不代表未来收益
- 实盘交易前请充分测试
- 建议先用模拟账户运行
