@echo off
REM O2OA 代码级看门狗启动器（双击或计划任务调用）
REM 脚本按自身位置推导仓库根（tools\ 的父目录），不依赖固定盘符。
cd /d "%~dp0\.."
"C:\Users\meng_\.workbuddy\binaries\python\versions\3.13.12\python.exe" tools\watchdog_o2oa_git.py >> tools\watchdog_o2oa_git.log 2>&1
