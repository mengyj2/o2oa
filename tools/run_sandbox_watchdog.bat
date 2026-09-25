@echo off
set PYTHONIOENCODING=utf-8
REM ============================================================================
REM O2OA 脚本沙箱硬化看门狗 · 启动器（后台持续运行）
REM ----------------------------------------------------------------------------
REM 双击本文件即可在后台拉起看门狗（最小化窗口，标题 O2OA-SandboxWatchdog）。
REM 看门狗每 300 秒巡检一次运行容器内 x_base_core_project.jar 的硬化签名，
REM 发现漂移自动从黄金副本重放 + 重启 + 重跑断网隔离。
REM 真正跨重启的持续化请用 install_watchdog_task.bat 注册为 Windows 计划任务。
REM ============================================================================
cd /d D:\O2OA
start "O2OA-SandboxWatchdog" /min "C:\Users\meng_\.workbuddy\binaries\python\versions\3.13.12\python.exe" tools\o2_sandbox_harden_watchdog.py --interval=300
echo 看门狗已在后台启动。日志：tools\o2_sandbox_harden_watchdog.log
timeout /t 2 >nul
