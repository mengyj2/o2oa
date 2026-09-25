@echo off
chcp 65001 >nul
title O2OA 邮件验证码服务 - 状态
cd /d "%~dp0"

echo =====================================================
echo   邮件验证码服务状态
echo =====================================================
echo.

echo [1] 进程
netstat -ano | findstr ":8095" | findstr "LISTENING"
if errorlevel 1 echo     8095 未监听（服务未运行）
echo.

echo [2] PID 文件
if exist "watchdog.pid" ( <nul set /p "=    看门狗 PID = " & type watchdog.pid & echo. ) else echo     看门狗 PID = (无)
if exist "mailservice.pid" ( <nul set /p "=    服务   PID = " & type mailservice.pid & echo. ) else echo     服务   PID = (无)
echo.

echo [3] 健康与注册状态
curl -s --noproxy "*" --max-time 6 http://127.0.0.1:8095/api/status
echo.
echo.

echo [4] 看门狗最近 5 行日志
if not exist "watchdog.log" echo     (无 watchdog.log)
if exist "watchdog.log" powershell -NoProfile -Command "Get-Content -Path '%~dp0watchdog.log' -Tail 5"
echo.

echo [5] 开机自启
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\O2OA_mail_service_autostart.vbs" (
  echo     已启用（启动文件夹 O2OA_mail_service_autostart.vbs）
) else (
  echo     未启用
)
echo.
pause
