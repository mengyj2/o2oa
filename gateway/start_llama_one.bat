@echo off
chcp 65001 >nul
REM ============================================================================
REM llama-server single-process launcher (called by start_ai_stack.bat)
REM   usage: start_llama_one.bat chat   |   start_llama_one.bat embed
REM
REM Two processes are required: llama-server serves only one mode per instance.
REM Vision: the chat process loads the mmproj (multimodal projector).
REM ============================================================================
setlocal
pushd "%~dp0.."
set "LLAMA_DIR=%CD%\llama.cpp\standalone"
popd
set "MODELS=D:/llm_models"

set "CHAT_MODEL=%MODELS%\lmstudio-community\Qwen3.5-4B-GGUF\Qwen3.5-4B-Q8_0.gguf"
set "MMPROJ=%MODELS%\lmstudio-community\Qwen3.5-4B-GGUF\mmproj-Qwen3.5-4B-BF16.gguf"
set "EMBED_MODEL=%MODELS%\Qwen\Qwen3-Embedding-0.6B-GGUF\Qwen3-Embedding-0.6B-Q8_0.gguf"
set "RERANK_MODEL=%MODELS%\gpustack\bge-reranker-v2-m3-GGUF\bge-reranker-v2-m3-Q8_0.gguf"

set "CHAT_PORT=8088"
set "EMBED_PORT=8089"
set "RERANK_PORT=8092"
set "CHAT_CTX=8192"

if /i "%~1"=="chat"  goto :chat
if /i "%~1"=="embed" goto :embed
if /i "%~1"=="rerank" goto :rerank
echo [ERROR] arg must be chat or embed
exit /b 2

:chat
if not exist "%CHAT_MODEL%" (
  echo [ERROR] chat model not found: %CHAT_MODEL%
  exit /b 1
)
pushd "%LLAMA_DIR%"
if exist "%MMPROJ%" (
  echo       [vision] loading mmproj
  start "llama-chat" /min "%LLAMA_DIR%\llama-server.exe" -m "%CHAT_MODEL%" --mmproj "%MMPROJ%" -c %CHAT_CTX% -ngl 999 --host 127.0.0.1 --port %CHAT_PORT% --jinja --alias qwen3.5-4b --no-webui
) else (
  echo       [note] mmproj missing, text-only mode
  start "llama-chat" /min "%LLAMA_DIR%\llama-server.exe" -m "%CHAT_MODEL%" -c %CHAT_CTX% -ngl 999 --host 127.0.0.1 --port %CHAT_PORT% --jinja --alias qwen3.5-4b --no-webui
)
popd
exit /b 0

:rerank
if not exist "%RERANK_MODEL%" (
  echo [ERROR] rerank model not found: %RERANK_MODEL%
  exit /b 1
)
pushd "%LLAMA_DIR%"
start "llama-rerank" /min "%LLAMA_DIR%\llama-server.exe" -m "%RERANK_MODEL%" --alias bge-reranker-v2-m3 -c 8192 -ngl 999 --host 127.0.0.1 --port %RERANK_PORT% --reranking --no-webui
popd
exit /b 0

:embed
if not exist "%EMBED_MODEL%" (
  echo [ERROR] embed model not found: %EMBED_MODEL%
  exit /b 1
)
pushd "%LLAMA_DIR%"
start "llama-embed" /min "%LLAMA_DIR%\llama-server.exe" -m "%EMBED_MODEL%" -c 2048 -ngl 999 --host 127.0.0.1 --port %EMBED_PORT% --embedding --pooling last --alias qwen3-embed --no-webui
popd
exit /b 0
