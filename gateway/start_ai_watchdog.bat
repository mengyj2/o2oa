@echo off
chcp 65001 >nul
REM ============================================================================
REM O2OA AI 栈看门狗启动器（硬化版）
REM
REM 功能：① 精确结束旧的看门狗/网关/OCR 进程（按命令行匹配，不影响 LM Studio）
REM       ② 清理陈旧 pid 文件
REM       ③ 单例拉起加固版看门狗（socket 互斥锁 + 端口归属感知 + 启动期防抖，自愈合）
REM
REM 双击本文件即可完成「彻底清理 + 干净重启」，无需手动结束进程。
REM   - 看门狗常驻后台（无黑窗口），每 30s 探活，掉线自动补位重启
REM   - 看门狗拉起的网关/embed/OCR 均为脱离式进程，独立于本窗口
REM
REM Usage:
REM   start_ai_watchdog.bat          按 config.json 决定组件（默认 embed+网关+OCR）
REM   start_ai_watchdog.bat /rerank  额外拉起 rerank(8092)
REM   start_ai_watchdog.bat /noocr   不拉 OCR
REM ============================================================================
setlocal
cd /d "%~dp0"
set "PY=C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

REM ── 关键：清除可能污染 localhost 调用的系统/环境代理 ──
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="

if not exist "%PY%" (
  echo [ERROR] 找不到 python: %PY%
  pause
  endlocal & exit /b 1
)

set "ARGS="
if /i "%~1"=="/rerank" set "ARGS=--rerank"
if /i "%~1"=="/noocr"  set "ARGS=--noocr"

echo [1/3] 结束旧的看门狗/网关/OCR 进程（按命令行精准匹配，不影响 LM Studio）...
powershell -NoProfile -WindowStyle Hidden -Command "$ps=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*watchdog_ai_stack.py*' -or $_.CommandLine -like '*o2_agent_gateway.py*' -or $_.CommandLine -like '*ocr_service.py*' }; foreach($p in $ps){ try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }"

echo [2/3] 清理陈旧 pid 文件...
for %%f in (watchdog gateway ocr embed chat rerank) do if exist "%%f.pid" del /f "%%f.pid" >nul 2>&1
timeout /t 3 >nul

echo [3/3] 单例拉起加固版看门狗（隐藏常驻，互斥锁+端口归属感知，自愈合）...
cd /d "%~dp0"
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%PY%' -ArgumentList '%~dp0watchdog_ai_stack.py','%ARGS%' -WindowStyle Hidden -WorkingDirectory '%~dp0'"

echo.
echo [完成] 看门狗已隐藏启动（无黑窗口）。约 30~60 秒后全栈就绪。
echo [验证] 运行：python gateway\health_check.py   应全部 healthy（非 404 误报）。
echo [停止] 任务管理器结束 python.exe(watchdog_ai_stack.py) 即可。
timeout /t 4 >nul
endlocal & exit /b 0
