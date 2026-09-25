@echo off
chcp 65001 >nul
cd /d "%~dp0"
title O2OA 出站封网

echo ============================================================
echo   O2OA 出站封网（挡住它偷偷连 o2oa.net）
echo ============================================================
echo.
echo   作用：让 O2OA 容器既保留【宿主访问 + MySQL 通信】，
echo         又彻底无法把数据发到外网（含 IP 直连，不只是域名）。
echo.
echo   原理：在内核 FORWARD 链按容器 IP 丢弃出站包，
echo         只放通 Docker 内网段（172.16/12，含 mysql）。
echo.
echo   重要：Docker Desktop 重启后规则会丢，需重新双击本脚本。
echo         容器重建（升级）后 IP 可能变，也要重新跑一次。
echo.
pause

where bash >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 bash。请安装 Git for Windows 后重试。
  pause
  exit /b 1
)

bash ./o2oa_netlock.sh %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [完成] 见上面的逐项验证结果。
) else (
  echo [失败] 请把上面的输出发出来。
)
echo.
pause
exit /b %RC%
