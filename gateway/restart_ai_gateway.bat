@echo off
chcp 65001 >nul 2>nul
REM ============================================================================
REM 重启 O2OA AI 网关 / 看门狗（强化版）
REM
REM 死结根因：旧版 pid 文件单例锁存在 TOCTOU 竞态，双击多次会起多个看门狗，
REM 互相 free_port 杀对方网关 -> 18790 反复 DOWN->重启抖动。
REM
REM 本脚本：复用 start_ai_watchdog.bat 的「精确清理旧进程 + 单例拉起加固看门狗」逻辑，
REM 看门狗改用内核级 socket 互斥端口(18800)，从根上杜绝双开互杀。
REM 仅结束本栈网关/看门狗/OCR，不影响 LM Studio 的 llama-server.exe。
REM ============================================================================
call "%~dp0start_ai_watchdog.bat" %*
exit /b 0
