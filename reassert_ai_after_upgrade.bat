@echo off
chcp 65001 >nul
cd /d "%~dp0"
title O2OA AI 智能体升级后自愈

echo ============================================================
echo   O2OA AI 智能体 · 升级/重启后自愈
echo ============================================================
echo.
echo   自动做四件事（全部幂等）：
echo     1) 拉起本地 AI 适配网关（若未运行）
echo     2) 恢复容器→网关 18790 防火墙白名单
echo     3) 把 O2OA AI 配置重新指向本地网关
echo     4) 端到端冒烟，失败则自动补推理补丁
echo.
echo   适用于：O2OA 升级后 / Docker 重启后 / 容器重建后。
echo   正常升级时由 upgrade_o2oa.bat 自动调用，本文件供手动补跑。
echo.

where bash >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 bash（Git for Windows）。请先安装 Git for Windows。
  pause
  exit /b 1
)

echo 正在执行...（约 1 分钟，请勿关闭窗口）
echo.

bash ./reassert_ai_after_upgrade.sh
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [完成] 脚本已执行完毕，请查看上方 PASS/FAIL 小结。
) else (
  echo [注意] 脚本退出码 %RC%，但本程序不阻断——请按上方提示排查。
)
echo.
pause
exit /b %RC%
