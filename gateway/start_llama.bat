@echo off
REM ============================================================================
REM 本地推理后端启动器 —— 官方 llama.cpp standalone（完全独立，不依赖 Bionic/LM Studio）
REM
REM 用官方 llama.cpp release 的 llama-server.exe 直接加载 GGUF：
REM   聊天  :8088  (Qwen3.5-4B)   嵌入 :8089  (Qwen3-Embedding-0.6B)
REM 两者共用同一份 exe，但必须分成两个进程（llama-server 一次只能服务一种模式）。
REM O2OA 的本地适配网关 (o2_agent_gateway.py) 分别连这两个端口。
REM
REM 目录布局：
REM   D:\O2OA\llama.cpp\standalone\   <- llama-server.exe + 依赖 DLL
REM   D:\llm_models\...               <- GGUF 模型
REM ============================================================================
setlocal

set "LLAMA_DIR=D:\O2OA\llama.cpp\standalone"
set "MODELS=D:\llm_models"

set "CHAT_MODEL=%MODELS%\lmstudio-community\Qwen3.5-4B-GGUF\Qwen3.5-4B-Q8_0.gguf"
set "MMPROJ=%MODELS%\lmstudio-community\Qwen3.5-4B-GGUF\mmproj-Qwen3.5-4B-BF16.gguf"
set "EMBED_MODEL=%MODELS%\Qwen\Qwen3-Embedding-0.6B-GGUF\Qwen3-Embedding-0.6B-Q8_0.gguf"

set "CHAT_PORT=8088"
set "EMBED_PORT=8089"
set "CHAT_CTX=8192"

if not exist "%LLAMA_DIR%\llama-server.exe" (
  echo [错误] 找不到 %LLAMA_DIR%\llama-server.exe
  echo 请先解压官方 llama.cpp release 并补齐依赖 DLL。
  pause & exit /b 1
)
if not exist "%CHAT_MODEL%" (
  echo [错误] 找不到聊天模型: %CHAT_MODEL%
  pause & exit /b 1
)
if not exist "%EMBED_MODEL%" (
  echo [错误] 找不到向量模型: %EMBED_MODEL%
  pause & exit /b 1
)

pushd "%LLAMA_DIR%"

echo [1/2] 启动聊天服务 (llama-server :%CHAT_PORT%, ROCm offload) ...
if exist "%MMPROJ%" (
  start "llama-chat" /min "%LLAMA_DIR%\llama-server.exe" -m "%CHAT_MODEL%" --mmproj "%MMPROJ%" -c %CHAT_CTX% -ngl 999 --host 127.0.0.1 --port %CHAT_PORT% --jinja --alias qwen3.5-4b --no-webui
) else (
  start "llama-chat" /min "%LLAMA_DIR%\llama-server.exe" -m "%CHAT_MODEL%" -c %CHAT_CTX% -ngl 999 --host 127.0.0.1 --port %CHAT_PORT% --jinja --alias qwen3.5-4b --no-webui
)

echo [2/2] 启动向量服务 (llama-server :%EMBED_PORT%) ...
start "llama-embed" /min "%LLAMA_DIR%\llama-server.exe" -m "%EMBED_MODEL%" -c 2048 -ngl 999 --host 127.0.0.1 --port %EMBED_PORT% --embedding --pooling last --alias qwen3-embed --no-webui

popd
echo.
echo 已启动。等待模型加载（约 5-15 秒）后验证：
echo   curl http://127.0.0.1:%CHAT_PORT%/health
echo   curl http://127.0.0.1:%EMBED_PORT%/health
echo 完成后请确保网关 (gateway\start_gateway.bat) 已在运行。
timeout /t 5 >nul
endlocal
