@echo off
chcp 65001 >nul
title O2OA 邮件验证码服务 - 启动
cd /d "%~dp0"
setlocal

set "PYW=C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=C:\Python314\pythonw.exe"

echo =====================================================
echo   O2OA 邮件验证码服务  (x_sms_assemble_control 平替)
echo   启动：看门狗 + 服务（后台无窗口常驻，掉线自动拉起）
echo   监听 0.0.0.0:8095    配置 mail.json    日志 mailservice.log
echo =====================================================
echo.

curl -s -o nul --noproxy "*" --max-time 4 http://127.0.0.1:8095/api/health >nul 2>&1
if not errorlevel 1 (
  echo [已在运行] 健康检查正常，无需重复启动。
  echo            看门狗会持续守护它（每 30 秒探活，掉线即拉起）。
  goto :end
)

echo 正在后台启动看门狗...
start "" "%PYW%" "%~dp0watchdog_mail_service.py"
echo 已发出启动指令，约 5 秒后就绪。
echo.
echo 提示：本机开机登录时会自动启动（启动文件夹 O2OA_mail_service_autostart.vbs）。

:end
echo.
pause
