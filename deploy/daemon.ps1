#Requires -Version 5.1
<#
.SYNOPSIS
    量化交易系统进程守护脚本

.DESCRIPTION
    提供进程监控、自动重启、钉钉告警等功能

.EXAMPLE
    .\daemon.ps1 -Action start
    .\daemon.ps1 -Action stop
    .\daemon.ps1 -Action restart
    .\daemon.ps1 -Action status
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Action,

    [string]$ConfigFile = ".\daemon_config.json"
)

# 配置
$script:Config = @{
    ProjectRoot = Split-Path -Parent $PSScriptRoot
    ProcessName = "python.exe"
    ScriptName = "run_paper_trading.py"
    PidFile = "logs\paper_trading.pid"
    LogFile = "logs\paper_trading.log"
    MonitorLog = "logs\daemon_monitor.log"
    MaxRestarts = 5
    RestartInterval = 60  # 秒
    CheckInterval = 30    # 秒
    DingtalkWebhook = $null  # 在配置文件中设置
}

# 加载配置文件
function Load-Config {
    if (Test-Path $ConfigFile) {
        try {
            $savedConfig = Get-Content $ConfigFile | ConvertFrom-Json
            $savedConfig.PSObject.Properties | ForEach-Object {
                $script:Config[$_.Name] = $_.Value
            }
            Write-Log "已加载配置文件: $ConfigFile"
        } catch {
            Write-Log "配置文件加载失败: $_" -Level WARN
        }
    }
}

# 写入日志
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "FATAL")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"

    Write-Host $logMessage

    # 写入监控日志
    $logDir = Join-Path $script:Config.ProjectRoot "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $monitorLogPath = Join-Path $script:Config.ProjectRoot $script:Config.MonitorLog
    $logMessage | Out-File -Append -FilePath $monitorLogPath
}

# 发送钉钉告警
function Send-DingtalkAlert {
    param([string]$Message)

    if (-not $script:Config.DingtalkWebhook) {
        Write-Log "钉钉 Webhook 未配置，跳过告警" -Level WARN
        return
    }

    try {
        $body = @{
            msgtype = "text"
            text = @{ content = "【量化交易告警】$Message" }
        } | ConvertTo-Json

        $response = Invoke-RestMethod -Uri $script:Config.DingtalkWebhook -Method Post -ContentType "application/json" -Body $body
        Write-Log "钉钉告警发送成功" -Level INFO
    } catch {
        Write-Log "钉钉告警发送失败: $_" -Level ERROR
    }
}

# 获取进程状态
function Get-ProcessStatus {
    $pidFile = Join-Path $script:Config.ProjectRoot $script:Config.PidFile

    if (-not (Test-Path $pidFile)) {
        return @{ Running = $false; PID = $null }
    }

    $pid = Get-Content $pidFile -ErrorAction SilentlyContinue
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue

    if ($process) {
        return @{
            Running = $true
            PID = $pid
            StartTime = $process.StartTime
            CPU = $process.CPU
            Memory = [math]::Round($process.WorkingSet64 / 1MB, 2)
        }
    }

    return @{ Running = $false; PID = $null }
}

# 启动进程
function Start-TradingProcess {
    Write-Log "正在启动纸交易进程..."

    $status = Get-ProcessStatus
    if ($status.Running) {
        Write-Log "进程已在运行 (PID: $($status.PID))" -Level WARN
        return $false
    }

    try {
        $scriptPath = Join-Path $script:Config.ProjectRoot $script:Config.ScriptName
        $logPath = Join-Path $script:Config.ProjectRoot $script:Config.LogFile
        $pidFile = Join-Path $script:Config.ProjectRoot $script:Config.PidFile

        # 创建日志目录
        $logDir = Split-Path -Parent $logPath
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }

        # 启动进程
        $process = Start-Process -FilePath "python" -ArgumentList $scriptPath -WorkingDirectory $script:Config.ProjectRoot -RedirectStandardOutput $logPath -RedirectStandardError "$logPath.err" -WindowStyle Hidden -PassThru

        # 保存 PID
        $process.Id | Out-File -FilePath $pidFile -Force

        Write-Log "进程已启动 (PID: $($process.Id))"
        Send-DingtalkAlert "纸交易进程已启动 (PID: $($process.Id))"

        return $true
    } catch {
        Write-Log "进程启动失败: $_" -Level ERROR
        return $false
    }
}

# 停止进程
function Stop-TradingProcess {
    Write-Log "正在停止纸交易进程..."

    $status = Get-ProcessStatus

    if (-not $status.Running) {
        Write-Log "进程未运行" -Level WARN
        return
    }

    try {
        Stop-Process -Id $status.PID -Force
        Write-Log "进程已停止 (PID: $($status.PID))"
        Send-DingtalkAlert "纸交易进程已手动停止"

        # 删除 PID 文件
        $pidFile = Join-Path $script:Config.ProjectRoot $script:Config.PidFile
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    } catch {
        Write-Log "停止进程失败: $_" -Level ERROR
    }
}

# 监控循环
function Start-MonitorLoop {
    Write-Log "监控进程已启动"
    Write-Log "最大重启次数: $($script:Config.MaxRestarts)"
    Write-Log "检查间隔: $($script:Config.CheckInterval)秒"

    $restartCount = 0

    while ($true) {
        Start-Sleep -Seconds $script:Config.CheckInterval

        $status = Get-ProcessStatus

        if (-not $status.Running) {
            Write-Log "检测到进程未运行，准备重启..." -Level WARN
            $restartCount++

            if ($restartCount -gt $script:Config.MaxRestarts) {
                Write-Log "超过最大重启次数，停止监控" -Level FATAL
                Send-DingtalkAlert "纸交易进程多次重启失败，请立即检查！"
                break
            }

            Write-Log "第 $restartCount 次重启..."
            Send-DingtalkAlert "纸交易进程已自动重启 (第 $restartCount 次)"

            Start-TradingProcess

            Start-Sleep -Seconds $script:Config.RestartInterval
        } else {
            # 检查进程资源使用情况
            if ($status.Memory -gt 500) {  # 内存超过 500MB
                Write-Log "进程内存使用过高: $($status.Memory)MB" -Level WARN
                Send-DingtalkAlert "纸交易进程内存使用过高: $($status.Memory)MB"
            }

            # 重置重启计数
            if ($restartCount -gt 0 -and $status.Running) {
                $restartCount = 0
                Write-Log "进程运行正常，重置重启计数"
            }
        }
    }
}

# 显示状态
function Show-Status {
    $status = Get-ProcessStatus

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "      纸交易进程状态" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan

    if ($status.Running) {
        Write-Host "状态: " -NoNewline
        Write-Host "运行中" -ForegroundColor Green
        Write-Host "PID: $($status.PID)"
        Write-Host "启动时间: $($status.StartTime)"
        Write-Host "CPU时间: $([math]::Round($status.CPU, 2))秒"
        Write-Host "内存使用: $($status.Memory)MB"
    } else {
        Write-Host "状态: " -NoNewline
        Write-Host "未运行" -ForegroundColor Red
    }

    Write-Host "`n========================================`n" -ForegroundColor Cyan
}

# 显示日志
function Show-Logs {
    $logPath = Join-Path $script:Config.ProjectRoot $script:Config.LogFile

    if (Test-Path $logPath) {
        Write-Host "`n========================================" -ForegroundColor Cyan
        Write-Host "      最近 50 行日志" -ForegroundColor Cyan
        Write-Host "========================================`n" -ForegroundColor Cyan

        Get-Content $logPath -Tail 50 | ForEach-Object {
            if ($_ -match "ERROR|FATAL") {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match "WARN") {
                Write-Host $_ -ForegroundColor Yellow
            } else {
                Write-Host $_
            }
        }

        Write-Host "`n========================================`n" -ForegroundColor Cyan
    } else {
        Write-Host "日志文件不存在: $logPath" -ForegroundColor Yellow
    }
}

# 主函数
function Main {
    Load-Config

    switch ($Action) {
        "start" {
            if (Start-TradingProcess) {
                # 启动后台监控
                Start-Job -ScriptBlock ${function:Start-MonitorLoop} | Out-Null
                Write-Log "后台监控已启动"
            }
        }
        "stop" {
            Stop-TradingProcess
        }
        "restart" {
            Stop-TradingProcess
            Start-Sleep -Seconds 2
            Start-TradingProcess
        }
        "status" {
            Show-Status
        }
        "logs" {
            Show-Logs
        }
    }
}

# 执行主函数
Main
