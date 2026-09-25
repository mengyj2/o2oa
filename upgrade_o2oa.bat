@echo off
chcp 65001 >nul
cd /d "%~dp0"
title O2OA 升级助手

echo ============================================================
echo   O2OA 升级助手（自动重放数据源补丁 + 重建镜像 + 验证）
echo ============================================================
echo.
echo   将新版 o2server-10.0.X-linux-x64.zip 放在本目录下，
echo   运行本脚本即可。会自动：
echo     1) 提取新版原始 jar
echo     2) 体检新版是否还需要三道补丁（官方若已修复则跳过）
echo     3) 离线重打补丁（带 JVM 字节码校验）
echo     4) 更新 Dockerfile / compose 版本号
echo     5) 构建镜像、重建容器
echo     6) 验证 MySQL 是否真的接管
echo.
echo   注意：若新版改了 ResourceFactory 结构，补丁会失败并中止，
echo         此时【不会】动你的现有镜像，服务照常可用。
echo.
echo   只想预演（不构建不重启）：改用预演模式
echo.
pause

where bash >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 bash。请安装 Git for Windows 后重试。
  pause
  exit /b 1
)

echo.
echo   正在执行...（构建阶段可能需要几分钟，请勿关闭窗口）
echo.

bash ./upgrade_o2oa.sh %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [成功] 升级完成。详见 UPGRADE.md
) else if "%RC%"=="2" (
  echo [警告] 升级已执行，但验证有未通过项，请查看上面的逐项输出。
  echo        常见原因与对策见 UPGRADE.md「失败时会怎样」。
) else (
  echo [失败] 升级已中止，你的现有服务未受影响。
  echo        请把下面这个文件发出来：
  echo            .upgrade-work\out\report.txt
  echo        以及执行日志：
  echo            .upgrade-work\pipeline.log
)
echo.
pause
exit /b %RC%
