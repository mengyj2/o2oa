@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title O2OA 10.0.2 - stop

echo ============================================
echo  O2OA + AI side : stop all
echo ============================================
echo.

echo [1/2] stopping O2OA containers ...
docker compose down
echo.

echo [2/2] stopping AI side (llama-server + gateway + OCR) ...
REM llama-server (chat + embed)
taskkill /F /IM llama-server.exe >nul 2>nul
if errorlevel 1 (echo       - llama-server not running) else (echo       - llama-server stopped)

REM adapter gateway: locate PID by listening port 18790 (more reliable than image name)
set _killed=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":18790 .*LISTENING"') do (
  taskkill /F /PID %%p >nul 2>nul
  set _killed=1
)
if "!_killed!"=="1" (echo       - adapter gateway stopped) else (echo       - adapter gateway not running)

REM OCR service: locate PID by listening port 8091
set _killed=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8091 .*LISTENING"') do (
  taskkill /F /PID %%p >nul 2>nul
  set _killed=1
)
if "!_killed!"=="1" (echo       - OCR service stopped) else (echo       - OCR service not running)

echo.
echo ============================================
echo  [done] containers and AI side stopped (volumes kept).
echo    note: Docker Desktop restart drops iptables rules.
echo          next start use start_o2oa.bat (re-applies netlock).
echo ============================================
pause
