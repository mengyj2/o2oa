@echo off
REM ============================================================================
REM O2OA 智能体本地适配网关 (o2-agent-gateway) 启动器
REM 作用：把 O2OA 私有智能体协议翻译到本地 OpenAI 兼容推理后端
REM       （默认 http://127.0.0.1:8090 —— lms headless，不依赖 Bionic GUI）。
REM       后端地址/模型见同目录 config.json。
REM 依赖：O2OA 的 AI 助手配置已指向本机 http://<宿主IP>:18790（见 o2_gw_cfg.js）。
REM 注意：只能起一个实例；若报 "address already in use" 请先结束旧 python 进程。
REM ============================================================================
cd /d "%~dp0"
set "PY=C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" (
  echo [错误] 找不到 Python 解释器: %PY%
  pause
  exit /b 1
)
echo 正在启动 o2-agent-gateway (监听 0.0.0.0:18790) ...
echo 日志写入 gateway.log，关闭请结束该 python 窗口 / 终止进程。
start "" "%PY%" o2_agent_gateway.py
timeout /t 3 >nul
echo 启动命令已发出。验证: curl http://127.0.0.1:18790/gateway/health
