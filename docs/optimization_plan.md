# 模拟盘系统优化方案

**创建时间**: 2026-03-31 13:25
**问题**: 系统运行 3 分钟后退出，主要受 Tushare API 限流影响

---

## 🔍 问题分析

### 问题1: Tushare API 频繁调用导致限流

**现象**:
- 系统启动后频繁调用 Tushare API
- 每分钟限制 50 次，但系统在 3 分钟内调用了数百次
- 大量 ERROR 日志：`抱歉，您每分钟最多访问该接口50次`

**根本原因**:
```python
# 在 realtime_feed.py 中，每 10 秒刷新一次价格
# 44 只股票 × 6 次/分钟 = 264 次/分钟 >> 50 次限制
```

**影响**:
- 无法获取实时价格
- 系统依赖 Tushare 备用数据
- 增加系统延迟

### 问题2: 非交易时段 Sina 返回空数据

**现象**:
- `WARNING - 新浪财经返回数据为空`
- 当前时间 13:18-13:21（午休时段）

**影响**: 轻微（系统会自动切换到 Tushare）

### 问题3: 系统退出原因不明

**现象**:
- 日志在 13:21:33 突然停止
- 无明确的退出日志或异常信息
- 退出码 0（正常退出）

**可能原因**:
1. 数据获取失败次数过多，触发了某个退出条件
2. 主循环中的某个条件导致 `running = False`
3. 未捕获的异常导致进程退出

---

## 💡 优化方案

### 方案1: 优化实时价格获取策略（高优先级）

**目标**: 减少 Tushare API 调用，避免限流

**实施步骤**:

1. **使用数据库缓存**
   ```python
   # 优先从数据库获取最近的收盘价
   # 仅在必要时调用实时 API

   def get_current_price(ts_code: str) -> float:
       # 1. 尝试从实时缓存获取（Sina）
       price_data = price_cache.get_price(ts_code)
       if price_data and price_data.get('price', 0) > 0:
           return price_data['price']

       # 2. 从数据库获取最近收盘价（无 API 调用）
       df = db.query("""
           SELECT close FROM daily_quotes
           WHERE ts_code = ?
           ORDER BY trade_date DESC
           LIMIT 1
       """, (ts_code,))

       if not df.empty:
           return float(df.iloc[0]['close'])

       # 3. 最后才调用 Tushare（限流风险）
       return get_price_from_tushare(ts_code)
   ```

2. **降低实时价格刷新频率**
   ```python
   # realtime_feed.py
   # 从 10 秒 → 30 秒
   price_cache = RealtimePriceCache(refresh_interval=30.0)
   ```

3. **批量获取价格**
   ```python
   # 一次性获取所有股票价格，而不是逐个获取
   # Sina API 支持批量查询
   def batch_get_prices(ts_codes: List[str]) -> Dict:
       # 一次 API 调用获取多只股票
       pass
   ```

### 方案2: 增加错误处理和重试机制（高优先级）

**目标**: 系统遇到错误时不退出，而是重试或降级

**实施步骤**:

1. **API 调用失败时使用缓存数据**
   ```python
   def get_price_with_fallback(ts_code: str) -> float:
       try:
           return get_realtime_price(ts_code)
       except RateLimitError:
           logger.warning(f"API 限流，使用缓存价格: {ts_code}")
           return get_cached_price(ts_code)
       except Exception as e:
           logger.error(f"获取价格失败: {e}")
           return get_last_close_price(ts_code)
   ```

2. **主循环异常捕获**
   ```python
   while running:
       try:
           # 主逻辑
           pass
       except KeyboardInterrupt:
           logger.info("用户中断")
           break
       except Exception as e:
           logger.error(f"主循环异常: {e}", exc_info=True)
           time.sleep(60)  # 等待 1 分钟后重试
           continue  # 不退出，继续运行
   ```

3. **限流检测和自动降速**
   ```python
   class RateLimiter:
       def __init__(self, max_calls=50, period=60):
           self.max_calls = max_calls
           self.period = period
           self.calls = []

       def can_call(self) -> bool:
           now = time.time()
           # 清理过期记录
           self.calls = [t for t in self.calls if now - t < self.period]
           return len(self.calls) < self.max_calls

       def record_call(self):
           self.calls.append(time.time())
   ```

### 方案3: 非交易时段优化（中优先级）

**目标**: 非交易时段减少不必要的操作

**实施步骤**:

1. **检测市场状态**
   ```python
   market_status = check_market_status()

   if market_status in ["weekend", "closed", "lunch_break"]:
       # 非交易时段，降低刷新频率
       time.sleep(300)  # 5 分钟检查一次
       continue
   ```

2. **午休时段暂停实时价格更新**
   ```python
   if market_status == "lunch_break":
       logger.info("午休时段，暂停实时价格更新")
       price_cache.pause()
   else:
       price_cache.resume()
   ```

### 方案4: 增加监控和告警（中优先级）

**目标**: 系统异常时及时发现

**实施步骤**:

1. **心跳监控**
   ```python
   def send_heartbeat():
       """每 5 分钟发送一次心跳"""
       notifier.send_message(f"[心跳] 系统运行正常 - {datetime.now()}")

   # 在主循环中
   if now - last_heartbeat > timedelta(minutes=5):
       send_heartbeat()
       last_heartbeat = now
   ```

2. **异常告警**
   ```python
   def send_alert(message: str):
       """发送告警消息"""
       notifier.send_message(f"[告警] {message}")

   # 在异常处理中
   except Exception as e:
       send_alert(f"系统异常: {e}")
   ```

3. **退出时发送通知**
   ```python
   def cleanup():
       """清理资源并发送通知"""
       logger.info("系统正在退出...")
       notifier.send_message(f"[通知] 模拟盘系统已退出 - {datetime.now()}")

   # 注册退出处理
   import atexit
   atexit.register(cleanup)
   ```

### 方案5: 配置进程守护（低优先级）

**目标**: 系统崩溃后自动重启

**实施步骤**:

1. **使用 systemd（Linux）**
   ```ini
   # /etc/systemd/system/paper-trading.service
   [Unit]
   Description=Paper Trading System
   After=network.target

   [Service]
   Type=simple
   User=your_user
   WorkingDirectory=/path/to/project
   ExecStart=/usr/bin/python3 run_paper_trading.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. **使用 supervisor（跨平台）**
   ```ini
   # /etc/supervisor/conf.d/paper-trading.conf
   [program:paper-trading]
   command=python run_paper_trading.py
   directory=/path/to/project
   autostart=true
   autorestart=true
   stderr_logfile=/var/log/paper-trading.err.log
   stdout_logfile=/var/log/paper-trading.out.log
   ```

3. **简单的 shell 守护脚本**
   ```bash
   #!/bin/bash
   # run_with_restart.sh

   while true; do
       echo "[$(date)] 启动模拟盘系统..."
       python run_paper_trading.py

       exit_code=$?
       echo "[$(date)] 系统退出，退出码: $exit_code"

       if [ $exit_code -eq 0 ]; then
           echo "正常退出，不重启"
           break
       fi

       echo "等待 30 秒后重启..."
       sleep 30
   done
   ```

---

## 📋 实施计划

### 立即实施（今天）

1. ✅ **优化实时价格获取**
   - 修改 `get_current_price()` 优先使用数据库
   - 降低刷新频率 10秒 → 30秒
   - 预计耗时：15 分钟

2. ✅ **增加错误处理**
   - 主循环异常捕获
   - API 失败时使用缓存
   - 预计耗时：10 分钟

3. ✅ **非交易时段优化**
   - 午休时段暂停更新
   - 预计耗时：5 分钟

### 明天实施

4. **增加监控告警**
   - 心跳监控
   - 异常告警
   - 预计耗时：20 分钟

5. **配置进程守护**
   - 编写守护脚本
   - 测试自动重启
   - 预计耗时：15 分钟

---

## 🎯 预期效果

**优化前**:
- 运行时长：3 分钟
- API 调用：264 次/分钟
- 限流错误：频繁
- 稳定性：差

**优化后**:
- 运行时长：≥ 24 小时
- API 调用：< 50 次/分钟
- 限流错误：罕见
- 稳定性：良好

---

## 📊 验证标准

1. **系统连续运行 ≥ 24 小时**
2. **无 Tushare 限流错误**
3. **实时价格获取成功率 > 95%**
4. **每小时发送心跳消息**
5. **异常时自动恢复，无需人工干预**

---

**文档版本**: v1.0
**创建时间**: 2026-03-31 13:25
**下次更新**: 优化完成后
