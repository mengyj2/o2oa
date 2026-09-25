#!/usr/bin/env bash
# =============================================================================
# reassert_ai_after_upgrade.sh —— O2OA 升级 / 容器重建 / Docker 重启后，
# 自动保证「AI 智能体（本地适配网关）」仍然可用。
#
# 它做四件事（全部幂等）：
#   1. 本地 AI 适配网关（o2_agent_gateway.py）存活 → 不在就拉起
#   2. 重放 o2oa_netlock.sh，恢复「容器 → 网关 18790」防火墙白名单
#      （Docker Desktop 重启 / 容器重建会让 iptables 规则丢失）
#   3. 用 gateway/o2_gw_cfg.js 把 O2OA AI 配置重新指向本地网关
#      （o2AiEnable=true / o2AiBaseUrl / o2AiToken，覆盖升级重置）
#   4. 端到端冒烟（经 9090 → 网关 → 本地推理后端），断言 content 分片 > 0
#      若失败且网关健康，自动补打 ActionChat 推理补丁（本地模型兜底路径）并复测
#
# 用法（在 Git Bash 或双击 reassert_ai_after_upgrade.bat）：
#   ./reassert_ai_after_upgrade.sh
#
# 设计原则：
#   - 不修改任何 O2OA jar；只调 REST + 宿主进程 + 防火墙
#   - 任一步失败都不致命，最后给出明确 PASS/FAIL 与人工兜底提示
#   - 已被 upgrade_o2oa.sh 第 9 步自动调用
# =============================================================================
set -u

cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)

# 把 Unix 路径转成 Windows 原生路径，避免 Git Bash 把 /d/O2OA/... 错转成 D:\d\O2OA\...
# （node / python 是原生 Windows 程序，认 Windows 路径；bash 之间调用才用 Unix 路径）
winpath() { cygpath -w "$1" 2>/dev/null || echo "$1"; }

GW="http://127.0.0.1:18790"
O2OA_PORT=9090
# 托管 venv python（已确认具备 fastapi/uvicorn/httpx）
GW_PY="C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# ---- 颜色（非 tty 时关闭）----
if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[36m'; N=$'\033[0m'
else
  R=; G=; Y=; B=; N=
fi
hr()  { printf '%s\n' "────────────────────────────────────────────────────────────"; }
log() { printf '%s[%s]%s %s\n' "$B" "$(date +%H:%M:%S)" "$N" "$*"; }
ok()  { printf '%s  ✓ %s%s\n' "$G" "$*" "$N"; }
warn(){ printf '%s  ! %s%s\n' "$Y" "$*" "$N"; }
err() { printf '%s  ✗ %s%s\n' "$R" "$*" "$N"; }

hr
printf '%s  O2OA AI 智能体 · 升级后自愈%s\n' "$B" "$N"
hr

# ---------------------------------------------------------------------------
# 0. 本地推理后端（官方 llama.cpp standalone，端口 8088 聊天 / 8089 嵌入）
#    完全独立，不依赖 Bionic / LM Studio 的 GUI 或引擎。
#    后端是网关的上游：网关 18790 要能工作，必须这两个端口有模型在跑。
# ---------------------------------------------------------------------------
LLAMA_DIR="D:/O2OA/llama.cpp/standalone"
LLAMA_EXE="$LLAMA_DIR/llama-server.exe"
CHAT_BASE="http://127.0.0.1:8088"
EMBED_BASE="http://127.0.0.1:8089"
CHAT_MODEL="D:/llm_models/lmstudio-community/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q8_0.gguf"
EMBED_MODEL="D:/llm_models/Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"

log "0/5 检查本地推理后端 (官方 llama.cpp :8088 聊天 / :8089 嵌入)"
LLM_UP=0
chat_up=0; embed_up=0
curl -s -m 5 "$CHAT_BASE/health"  2>/dev/null | grep -q '"ok"' && chat_up=1
curl -s -m 5 "$EMBED_BASE/health" 2>/dev/null | grep -q '"ok"' && embed_up=1

if [ "$chat_up" = "0" ] && [ -f "$LLAMA_EXE" ]; then
  log "    聊天服务未响应，用官方 llama-server 拉起（ROCm offload）..."
  ( cd "$LLAMA_DIR" && "$LLAMA_EXE" -m "$CHAT_MODEL" -c 8192 -ngl 999 \
      --host 127.0.0.1 --port 8088 --jinja --alias qwen3.5-4b --no-webui \
      >/dev/null 2>&1 & )
fi
if [ "$embed_up" = "0" ] && [ -f "$LLAMA_EXE" ]; then
  log "    嵌入服务未响应，用官方 llama-server 拉起..."
  ( cd "$LLAMA_DIR" && "$LLAMA_EXE" -m "$EMBED_MODEL" -c 2048 -ngl 999 \
      --host 127.0.0.1 --port 8089 --embedding --pooling last --alias qwen3-embed --no-webui \
      >/dev/null 2>&1 & )
fi
for i in $(seq 1 12); do
  [ "$chat_up" = "0" ]  && curl -s -m 5 "$CHAT_BASE/health"  2>/dev/null | grep -q '"ok"' && chat_up=1
  [ "$embed_up" = "0" ] && curl -s -m 5 "$EMBED_BASE/health" 2>/dev/null | grep -q '"ok"' && embed_up=1
  [ "$chat_up" = "1" ] && [ "$embed_up" = "1" ] && break
  sleep 3
done
[ "$chat_up" = "1" ] && [ "$embed_up" = "1" ] && LLM_UP=1
if [ "$LLM_UP" = "1" ]; then
  ok "推理后端存活 (官方 llama.cpp :8088/:8089, ROCm)"
else
  warn "推理后端未就绪 (聊天=$chat_up 嵌入=$embed_up) —— 请手动运行 gateway/start_llama.bat"
fi

# ---------------------------------------------------------------------------
# 1. 本地适配网关存活
# ---------------------------------------------------------------------------
log "1/5 检查本地 AI 适配网关 ($GW)"
GW_UP=0
for i in $(seq 1 8); do
  if curl -s -m 5 "$GW/gateway/health" 2>/dev/null | grep -q '"status"'; then
    GW_UP=1; break
  fi
  # 首次尝试：拉起网关（宿主常驻进程，与 O2OA 版本无关）
  if [ "$i" = "1" ]; then
    log "    网关未响应，尝试启动..."
    if [ -f "$GW_PY" ] && [ -f "$ROOT/gateway/o2_agent_gateway.py" ]; then
      nohup "$GW_PY" "$(winpath "$ROOT/gateway/o2_agent_gateway.py")" \
        > "$(winpath "$ROOT/gateway/gateway.log")" 2>&1 &
      disown 2>/dev/null || true
    elif [ -f "$ROOT/gateway/start_gateway.bat" ]; then
      cmd //c "start \"\" \"$(winpath "$ROOT/gateway/start_gateway.bat")\"" >/dev/null 2>&1 &
    fi
  fi
  sleep 4
done
if [ "$GW_UP" = "1" ]; then ok "网关存活"; else err "网关无法启动 —— AI 不可用"; warn "请手动双击 gateway/start_gateway.bat 后重试"; fi

# ---------------------------------------------------------------------------
# 2. 容器 → 网关 防火墙白名单
# ---------------------------------------------------------------------------
log "2/5 重放 o2oa_netlock.sh（恢复 18790 白名单）"
if [ -f "$ROOT/o2oa_netlock.sh" ]; then
  if bash "$ROOT/o2oa_netlock.sh" >/dev/null 2>&1; then
    ok "netlock 已重放（含容器→网关 18790 ACCEPT）"
  else
    warn "netlock 执行异常，请手动: bash o2oa_netlock.sh"
  fi
else
  warn "未找到 o2oa_netlock.sh，跳过（容器可能无法访问网关）"
fi

# ---------------------------------------------------------------------------
# 3. 重新断言 O2OA AI 配置指向网关
# ---------------------------------------------------------------------------
log "3/5 重新断言 O2OA AI 配置（o2AiEnable=true / baseUrl=网关 / token）"
  if command -v node >/dev/null 2>&1; then
  if node "$(winpath "$ROOT/gateway/o2_gw_cfg.js")" >/dev/null 2>&1; then
    ok "O2OA AI 配置已重新指向本地网关"
  else
    warn "配置断言失败，请检查 gateway/o2_gw_cfg.js 与 9090 可达性"
  fi
else
  warn "未找到 node，跳过配置断言（手动: node gateway/o2_gw_cfg.js）"
fi

# ---------------------------------------------------------------------------
# 4. 端到端冒烟
# ---------------------------------------------------------------------------
log "4/5 端到端冒烟（经 9090 → 网关 → 本地推理后端）"
SMOKE=1
if [ -f "$ROOT/gateway/ai_smoke.js" ] && command -v node >/dev/null 2>&1; then
  OUT=$(node "$(winpath "$ROOT/gateway/ai_smoke.js")" 2>&1)
  echo "    $OUT" | head -c 500
  echo
  if echo "$OUT" | grep -q '"ok":true'; then ok "冒烟通过：chat 返回 content 分片（界面不会空白）"; SMOKE=0; fi
else
  warn "缺少 ai_smoke.js 或 node，跳过冒烟"
fi

# ---------------------------------------------------------------------------
# 5. 冒烟失败且网关健康 → 自动补 ActionChat 推理补丁（本地模型兜底路径）
#    注：网关路径本身不依赖此补丁；仅当 O2OA 走本地模型直连兜底时它才生效。
# ---------------------------------------------------------------------------
if [ "$SMOKE" = "1" ] && [ "$GW_UP" = "1" ]; then
  warn "冒烟未通过，尝试自动补打 ActionChat 推理补丁（兜底用）..."
  if [ -f "$ROOT/patch/ai/patch_ai_nothink.sh" ]; then
    bash "$ROOT/patch/ai/patch_ai_nothink.sh" apply >/dev/null 2>&1 || true
    OUT2=$(node "$(winpath "$ROOT/gateway/ai_smoke.js")" 2>&1)
    echo "    $OUT2" | head -c 500; echo
    if echo "$OUT2" | grep -q '"ok":true'; then ok "补丁后冒烟通过"; SMOKE=0; else err "补丁后仍失败，需人工排查（模型/网关/网络）"; fi
  else
    warn "未找到 patch/ai/patch_ai_nothink.sh，跳过自动补丁"
  fi
fi

hr
if [ "$GW_UP" = "1" ] && [ "$SMOKE" = "0" ]; then
  printf '%s  ✓ AI 智能体已确认可用（升级/重启后自愈成功）%s\n' "$G" "$N"
elif [ "$GW_UP" = "1" ]; then
  printf '%s  ! AI 网关在线，但冒烟未通过 —— 见上方 ✗ 项，可能需人工排查% s\n' "$Y" "$N"
else
  printf '%s  ✗ 网关未启动，AI 不可用 —— 请先启动 gateway/start_gateway.bat% s\n' "$R" "$N"
fi
hr
exit 0
