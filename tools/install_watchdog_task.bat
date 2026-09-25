@echo off
set PYTHONIOENCODING=utf-8
REM ============================================================================
REM 注册看门狗为 Windows 计划任务（开机自启 · 真·持续化，跨重启生效）
REM ----------------------------------------------------------------------------
REM 需以管理员身份运行本文件，/RU SYSTEM 才能注册成功；
REM 若失败，可把管理员 PowerShell 里执行，或改用当前用户：
REM   schtasks /Create /TN O2OA_SandboxHardenWatchdog /TR "..." /SC ONSTART /RU %USERNAME% /F
REM 卸载：schtasks /Delete /TN O2OA_SandboxHardenWatchdog /F
REM ============================================================================
cd /d D:\O2OA
"C:\Users\meng_\.workbuddy\binaries\python\versions\3.13.12\python.exe" tools\o2_sandbox_harden_watchdog.py --install
echo 注册完成。查看：schtasks /Query /TN O2OA_SandboxHardenWatchdog
timeout /t 3 >nul
