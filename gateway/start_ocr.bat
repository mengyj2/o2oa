@echo off
REM ============================================================================
REM O2OA OCR service launcher (o2-ocr-service)  --  listen 0.0.0.0:8091
REM
REM What it does:
REM   Standalone CPU OCR process (RapidOCR ONNX). Handles:
REM     1. scanned pages      -> text
REM     2. tables in images   -> markdown grid
REM     3. PDF                -> text layer first, else render + OCR
REM
REM Why standalone:
REM   OCR is CPU-heavy (1-5s per A4 page). Keeping it out of the adapter
REM   gateway means a slow scan never blocks SSE streaming chat.
REM
REM Usage:
REM   start_ocr.bat           start in background
REM   start_ocr.bat /f        start in foreground (see the log live)
REM ============================================================================
setlocal
cd /d "%~dp0"
set "PY=C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
set "PORT=8091"

if not exist "%PY%" (
  echo [ERROR] python not found: %PY%
  if /i "%~1"=="/f" pause
  exit /b 1
)

netstat -ano 2>nul | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo [OCR] port %PORT% already listening, skip
  exit /b 0
)

if /i "%~1"=="/f" (
  echo [OCR] starting o2-ocr-service on 0.0.0.0:%PORT%  ^(foreground^)
  "%PY%" "%~dp0ocr_service.py"
) else (
  echo [OCR] starting o2-ocr-service on 0.0.0.0:%PORT%
  start "o2-ocr" /min "%PY%" "%~dp0ocr_service.py"
)

REM ---- readiness wait (first call builds the ONNX session, ~1-3s) ----
set _n=0
:wait_loop
curl -s --noproxy "*" --max-time 3 "http://127.0.0.1:%PORT%/health" >nul 2>nul
if not errorlevel 1 (
  echo [OCR] ready. check: curl --noproxy "*" http://127.0.0.1:%PORT%/health
  exit /b 0
)
set /a _n+=1
if %_n% geq 20 (
  echo [OCR][ERROR] not ready after 60s. see ocr_service.log
  exit /b 1
)
timeout /t 3 /nobreak >nul
goto :wait_loop
