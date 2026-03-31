# 部署与进程守护

本目录包含量化交易系统的部署配置和进程守护脚本。

## 文件说明

| 文件 | 说明 |
|------|------|
| `paper_trading_daemon.bat` | Windows 批处理版本的进程管理脚本 |
| `daemon.ps1` | PowerShell 版本的进程管理脚本（推荐） |
| `daemon_config.json.example` | 配置文件模板 |

## 快速开始

### 1. 配置钉钉告警（可选）

```bash
# 复制配置文件模板
copy daemon_config.json.example daemon_config.json

# 编辑配置文件，填入你的钉钉 Webhook
daemon_config.json
```

### 2. 使用 PowerShell 脚本（推荐）

```powershell
# 查看状态
.\daemon.ps1 -Action status

# 启动纸交易系统
.\daemon.ps1 -Action start

# 停止系统
.\daemon.ps1 -Action stop

# 重启系统
.\daemon.ps1 -Action restart

# 查看日志
.\daemon.ps1 -Action logs
```

### 3. 使用批处理脚本

```cmd
# 启动（带自动监控）
paper_trading_daemon.bat start

# 停止
paper_trading_daemon.bat stop

# 重启
paper_trading_daemon.bat restart

# 查看状态
paper_trading_daemon.bat status
```

## 功能特性

- ✅ **进程守护**: 自动检测进程崩溃并重启
- ✅ **重启限制**: 最多连续重启 5 次，防止无限重启
- ✅ **钉钉告警**: 进程异常时自动发送告警通知
- ✅ **资源监控**: 监控内存使用，过高时告警
- ✅ **日志管理**: 自动记录监控日志和进程日志

## 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DingtalkWebhook` | null | 钉钉机器人 Webhook URL |
| `MaxRestarts` | 5 | 最大连续重启次数 |
| `RestartInterval` | 60 | 重启间隔（秒） |
| `CheckInterval` | 30 | 进程检查间隔（秒） |
| `MemoryThreshold` | 500 | 内存告警阈值（MB） |

## 开机自启配置

### Windows 任务计划程序

1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：当特定用户登录时 / 系统启动时
4. 操作：启动程序
5. 程序：`powershell.exe`
6. 参数：`-File "D:\project_room\workspace2024\mytest\auto-transaction\deploy\daemon.ps1" -Action start`

### 使用 Windows 服务（高级）

如果需要更专业的进程管理，可以使用 NSSM（Non-Sucking Service Manager）将纸交易系统注册为 Windows 服务。

```cmd
# 下载 NSSM 后执行
nssm install PaperTrading "python" "run_paper_trading.py"
nssm set PaperTrading AppDirectory "D:\project_room\workspace2024\mytest\auto-transaction"
nssm start PaperTrading
```

## 故障排查

### 进程无法启动

1. 检查 Python 环境: `python --version`
2. 检查依赖安装: `pip install -r requirements.txt`
3. 检查日志文件: `logs/paper_trading.log`

### 钉钉告警未收到

1. 检查 Webhook URL 是否正确
2. 检查钉钉机器人是否开启
3. 检查网络连接

### 进程频繁重启

1. 查看监控日志: `logs/daemon_monitor.log`
2. 检查应用日志: `logs/paper_trading.log`
3. 检查系统资源: 内存、磁盘空间

## 注意事项

- 生产环境建议使用 PowerShell 版本，功能更完善
- 确保日志目录 `logs/` 存在且有写入权限
- 定期检查日志文件大小，避免磁盘占满
