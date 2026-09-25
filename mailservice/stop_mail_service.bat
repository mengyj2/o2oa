@echo off
chcp 65001 >nul
title O2OA 邮件验证码服务 - 停止
cd /d "%~dp0"
setlocal

echo =====================================================
echo   停止 看门狗 + 邮件验证码服务
echo =====================================================
echo.

call :KillOne "watchdog.pid"
call :KillOne "mailservice.pid"

REM 兜底：按端口收尾（应对 PID 文件缺失/失真的情况）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8095" ^| findstr "LISTENING"') do (
  echo   [兜底] 释放 8095 占用者 PID %%p
  taskkill /PID %%p /F /T >nul 2>&1
)

echo.
echo 完成。如需再次启动，双击 start_mail_service.bat。
echo.
pause
exit /b 0

:KillOne
set "F=%~1"
if not exist "%F%" (
  echo   %F% 不存在，跳过
  exit /b 0
)
set "P="
set /p P=<"%F%"
if "%P%"=="" (
  echo   %F% 内容为空，跳过
  del /q "%F%" >nul 2>&1
  exit /b 0
)
echo   结束 %F% -^> PID %P%
taskkill /PID %P% /F /T >nul 2>&1
if errorlevel 1 (
  echo     （进程可能已退出）
) else (
  echo     OK
)
del /q "%F%" >nul 2>&1
exit /b 0
