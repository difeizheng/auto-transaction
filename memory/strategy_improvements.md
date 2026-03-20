# 策略改进记录

## 改进时间
2026-03-20

## 改进内容

### 1. 止损止盈优化 (已完成)
**文件**: `src/strategy/optimal_strategy.py`

**改动**:
- `base_stop_loss`: 0.08 → 0.05 (8% → 5%)
- `base_take_profit`: 0.20 → 0.15 (20% → 15%)
- 新增 `trailing_stop_trigger`: 0.08 (移动止损触发点 8%)
- 趋势阈值：0.05 → 0.03 (5% → 3%)

**目的**: 提高盈亏比，止盈更容易达成，止损更紧

---

### 2. 信号评分权重优化 (已完成)
**文件**: `src/strategy/optimal_strategy.py`

**改动**:
- `calculate_signal_score` 方法重构，引入加权评分：
  - 均线金叉：1.5 分 (最重要)
  - MACD 多头：1.0 分
  - RSI 健康：0.5 分
  - RSI 超卖：额外 +0.5 分
  - 布林带下轨：1.0 分
  - 成交量放大：1.0 分
  - 趋势向上：1.0 分
- 触发阈值：4/6 → 5/7 (提高标准)
- 新增 RSI 超卖判断参数

**目的**: 提高胜率，区分因子重要性

---

### 3. 市场状态判断优化 (已完成)
**文件**: `src/strategy/optimal_strategy.py`

**改动**:
- `determine_market_state` 方法重构
- 引入双均线系统 (短/中/长) 判断趋势
- 时间过滤：连续 3 日确认
- 成交量确认：上涨放量才是真牛市
- 阈值从 5% 改为 3%

**目的**: 减少误判，仓位管理更有效

---

### 4. 扩大股票池 + 基本面过滤 (已完成)
**文件**: `config/settings.py`, `src/data_collector/tushare_client.py`, `src/data_collector/data_manager.py`, `main.py`

**改动**:
1. `config/settings.py`:
   - 新增 `EXTENDED_STOCK_POOL` (约 30 只沪深 300 成分股)
   - 新增 `FUNDAMENTAL_FILTERS` 配置 (PE<50, ROE>5%, 营收增长>0)

2. `src/data_collector/tushare_client.py`:
   - 新增 `filter_stocks_by_fundamentals` 方法
   - 新增 `get_hs300_stocks` 方法

3. `src/data_collector/data_manager.py`:
   - 新增 `filter_stock_pool_by_fundamentals` 方法
   - 新增 `get_hs300_filtered` 方法

4. `main.py`:
   - `run_backtest` 函数新增 `use_extended_pool` 和 `filter_fundamentals` 参数
   - 新增命令行参数 `--use-extended-pool` 和 `--no-fundamental-filter`

**目的**: 分散风险，避免垃圾股

---

## 预期效果

| 指标 | 改进前 | 目标 |
|------|--------|------|
| 胜率 | 50% | 60%+ |
| 盈亏比 | 1.33 | 2.0+ |
| 夏普比率 | 0.23 | 0.5+ |
| 年化收益 | 2.62% | 10%+ |
| 最大回撤 | 13.79% | <10% |

---

## 回测验证命令

```bash
# 改进后回测
python main.py backtest --strategy optimal --start-date 20250101 --end-date 20260319 --use-extended-pool

# 关闭基本面过滤回测
python main.py backtest --strategy optimal --start-date 20250101 --end-date 20260319 --no-fundamental-filter
```
