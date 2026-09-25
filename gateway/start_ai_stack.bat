@echo off
chcp 65001 >nul
REM ============================================================================
REM O2OA AI stack launcher (thin wrapper over start_ai_stack_detached.py)
REM
REM 设计：所有组件由独立 Python 启动器以「脱离父进程 + 逐个就绪后拉起」方式启动，
REM   - 避免父控制台关闭时子进程被整树回收；
REM   - 错峰加载，规避 4GB 显存下多模型同时加载互相挤崩；
REM   - chat+embed+网关 为必需，rerank/OCR 非必需（缺失自动跳过，不致命）。
REM
REM Usage:
REM   start_ai_stack.bat          chat+embed+网关+OCR（推荐）
REM   start_ai_stack.bat /rerank 额外拉起 rerank（RAG 精排，显存够才加）
REM   start_ai_stack.bat /noocr  不拉 OCR
REM   start_ai_stack.bat /v       仅打印状态后退出
REM ============================================================================
setlocal
cd /d "%~dp0"
set "PY=C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

if not exist "%PY%" (
  echo [ERROR] 找不到 python: %PY%
  if /i "%~1"=="/v" pause
  endlocal & exit /b 1
)

set "ARGS="
if /i "%~1"=="/rerank" set "ARGS=--rerank"
if /i "%~1"=="/noocr"  set "ARGS=--noocr"
if /i "%~1"=="/v"       set "ARGS=--status"

echo [AI] 拉起本地推理后端 + 适配网关（脱离式，bat 退出后进程仍存活）...
"%PY%" "%~dp0start_ai_stack_detached.py" %ARGS%
set _rc=%errorlevel%

if %_rc%==0 (
  echo [AI] 启动序列完成。可用 `start_ai_stack.bat /v` 复检各端口。
) else (
  echo [AI][WARN] 存在必需组件未就绪（见上方日志）。O2OA 仍可正常打开，仅 AI 助手可能受限。
  echo        排查：gateway\llama_chat.log / llama_embed.log / gateway.log
)
if /i "%~1"=="/v" pause
endlocal & exit /b %_rc%
