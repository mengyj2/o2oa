@echo off
chcp 65001 >nul
cd /d "%~dp0"
title O2OA 升级预演（不构建不重启）

echo ============================================================
echo   O2OA 升级【预演模式】
echo ============================================================
echo.
echo   这个模式只做前面 5 步，做完就停：
echo     1) 定位新版 zip
echo     2) 提取原始 jar
echo     3) 起临时容器跑补丁流水线
echo     4) 体检新版是否还需要三道补丁（官方若已修复则自动跳过）
echo     5) 离线字节码校验补丁产物
echo.
echo   不做：构建镜像、重建容器。所以你的 O2OA 服务全程不受影响。
echo   适合：先确认新版能不能顺利打上补丁，再决定要不要真升级。
echo.
echo   注意：预演仍会把补丁产物写回 patch/ 目录，
echo         但【不会】改动 Dockerfile / docker-compose.yml。
echo.
pause

where bash >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 bash。请安装 Git for Windows 后重试。
  pause
  exit /b 1
)

echo.
echo   正在预演...
echo.

set SKIP_BUILD=1
bash ./upgrade_o2oa.sh %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [预演成功] 新版补丁可以顺利重放。
  echo            体检结论与产物校验详见 .upgrade-work\out\report.txt
  echo            确认无误后，双击 upgrade_o2oa.bat 执行真正的升级。
) else (
  echo [预演失败] 新版补丁无法自动重放（或流程中断）。
  echo            你的现有服务未受任何影响。
  echo            请把这两个文件发出来：
  echo              .upgrade-work\out\report.txt
  echo              .upgrade-work\pipeline.log
)
echo.
pause
exit /b %RC%
