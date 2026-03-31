@echo off
chcp 65001 >nul
echo ==========================================
echo 量化交易系统 - 进程守护管理脚本
echo ==========================================
echo.

set PROJECT_ROOT=%~dp0..
set PID_FILE=%PROJECT_ROOT%\logs\paper_trading.pid
set LOG_FILE=%PROJECT_ROOT%\logs\paper_trading_daemon.log

cd /d %PROJECT_ROOT%

if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="monitor" goto monitor
goto usage

:start
echo [INFO] 启动纸交易进程...

:: 检查是否已在运行
if exist %PID_FILE% (
    set /p PID=<%PID_FILE%
    tasklist /FI "PID eq %PID%" 2>nul | findstr %PID% >nul
    if %errorlevel%==0 (
        echo [WARN] 纸交易进程已在运行 (PID: %PID%)
        exit /b 1
    ) else (
        del %PID_FILE%
    )
)

:: 启动进程
start /b python run_paper_trading.py > %LOG_FILE% 2>&1
set PID=%ERRORLEVEL%

:: 保存 PID
echo %PID% > %PID_FILE%
echo [INFO] 纸交易进程已启动 (PID: %PID%)
echo [INFO] 日志文件: %LOG_FILE%

:: 启动监控循环
start /b "" cmd /c "%~f0 monitor"
goto :eof

:stop
echo [INFO] 停止纸交易进程...

if not exist %PID_FILE% (
    echo [WARN] 未找到 PID 文件，尝试查找进程...
    taskkill /F /FI "WINDOWTITLE eq python run_paper_trading.py" 2>nul
    echo [INFO] 进程已停止
    goto :eof
)

set /p PID=<%PID_FILE%
taskkill /PID %PID% /F 2>nul
if %errorlevel%==0 (
    echo [INFO] 进程已停止 (PID: %PID%)
) else (
    echo [WARN] 进程可能已停止或未找到
)

del %PID_FILE% 2>nul
goto :eof

:restart
echo [INFO] 重启纸交易进程...
call :stop
timeout /t 2 /nobreak >nul
call :start
goto :eof

:status
echo [INFO] 检查进程状态...

if exist %PID_FILE% (
    set /p PID=<%PID_FILE%
    tasklist /FI "PID eq %PID%" 2>nul | findstr %PID% >nul
    if %errorlevel%==0 (
        echo [INFO] 纸交易进程运行中 (PID: %PID%)
        echo [INFO] 启动时间:
        for /f "tokens=2" %%a in ('tasklist /FI "PID eq %PID%" /FO LIST ^| findstr "启动时间"') do echo %%a
    ) else (
        echo [WARN] PID 文件存在但进程未运行，建议重启
    )
) else (
    echo [WARN] 纸交易进程未运行
)
goto :eof

:monitor
:: 后台监控进程，自动重启
setlocal enabledelayedexpansion

set RESTART_COUNT=0
set MAX_RESTARTS=5
set RESTART_INTERVAL=10

echo [INFO] 监控进程已启动，最大重启次数: %MAX_RESTARTS%

:monitor_loop
timeout /t %RESTART_INTERVAL% /nobreak >nul

if not exist %PID_FILE% (
    goto monitor_loop
)

set /p PID=<%PID_FILE%
tasklist /FI "PID eq %PID%" 2>nul | findstr %PID% >nul
if %errorlevel%==0 (
    goto monitor_loop
)

:: 进程崩溃，需要重启
set /a RESTART_COUNT+=1
echo [ERROR] 检测到进程崩溃 (PID: %PID%) >> %LOG_FILE%
echo [INFO] 尝试第 %RESTART_COUNT% 次重启...

if %RESTART_COUNT% GTR %MAX_RESTARTS% (
    echo [FATAL] 超过最大重启次数，停止自动重启
    echo [FATAL] 超过最大重启次数，停止自动重启 >> %LOG_FILE%

    :: 发送钉钉告警
    call :send_alert "纸交易进程多次重启失败，请立即检查！"

    goto :eof
)

:: 重启进程
del %PID_FILE% 2>nul
start /b python run_paper_trading.py > %LOG_FILE% 2>&1
set NEW_PID=%ERRORLEVEL%
echo %NEW_PID% > %PID_FILE%
echo [INFO] 进程已重启 (PID: %NEW_PID%)

:: 发送钉钉告警
call :send_alert "纸交易进程已自动重启 (第 %RESTART_COUNT% 次)"

goto monitor_loop

:send_alert
:: 发送钉钉告警（需要配置 webhook）
set MSG=%~1
set WEBHOOK_URL=your_dingtalk_webhook_url_here

if "%WEBHOOK_URL%"=="your_dingtalk_webhook_url_here" (
    echo [WARN] 钉钉 Webhook 未配置，跳过告警
    goto :eof
)

curl -s -X POST %WEBHOOK_URL% \
    -H "Content-Type: application/json" \
    -d "{\"msgtype\": \"text\", \"text\": {\"content\": \"【量化交易告警】%MSG%\"}}" >nul 2>&1

goto :eof

:usage
echo 用法: %~nx0 {start^|stop^|restart^|status}
echo.
echo 命令:
echo   start   - 启动纸交易进程并启用自动监控
echo   stop    - 停止纸交易进程
echo   restart - 重启纸交易进程
echo   status  - 查看进程状态
echo.
