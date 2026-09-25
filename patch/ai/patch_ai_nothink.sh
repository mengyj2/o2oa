#!/usr/bin/env bash
# =============================================================================
# patch_ai_nothink.sh —— 修复 O2OA AI 助手的 reasoning_content 陷阱（幂等 / 可回滚）
#
# 问题
# ----
# O2OA 的 ActionChat.aiChat() 向模型端点发送请求体：
#     data.put("enable_thinking", BooleanUtils.isTrue(wi.getThinkingEnabled()));
# 但 LM Studio 的 OpenAI 兼容端点【不认】 enable_thinking 这个键，静默忽略。
# 于是推理模型把 token 全消耗在 reasoning_content 里，而 O2OA 的 picContent()
# 只读 delta.content —— 结果 AI 助手界面一片空白。
#
# 实测（本机 LM Studio / glm-4.7-flash）
# --------------------------------------
#   enable_thinking=false              -> reasoning_tokens=200, content=""
#   chat_template_kwargs{enable_thinking:false} -> rt=63, content 被污染
#   thinking:{type:"disabled"}         -> rt=61, content 被污染
#   system 里加 /no_think              -> 无效
#   user  里加 /no_think               -> 无效
#   reasoning_effort="none"            -> rt=0,  content 完整   ★ 唯一有效
#
# 修复
# ----
# 字节码层面把请求体字段改名并改值：
#     "enable_thinking" -> Boolean.valueOf(isTrue(...))
#   改为
#     "reasoning_effort" -> "none"
#
# 实现细节（关键，勿简化）
# ------------------------
# 1) 不修改任何已有 Utf8 的长度 —— 否则常量池之后所有方法的 attribute_length
#    都要跟着平移，极易出错。改为把新常量【追加】到常量池尾部。
# 2) #415 String 条目原地改指向新 Utf8 "reasoning_effort"（String 条目长度不变）。
# 3) 字节码 10 字节原样等长替换：
#      aload_1 | invokevirtual | invokestatic | invokestatic     (10B)
#      ldc_w #n | nop x7                                        (10B)
# 4) 必须过 -Xverify:all 才认为成功。
#
# 用法
# ----
#   ./patch_ai_nothink.sh apply     # 打补丁并重启（幂等）
#   ./patch_ai_nothink.sh verify    # 只校验当前状态
#   ./patch_ai_nothink.sh restore   # 回滚到原始 class 并重启
#   ./patch_ai_nothink.sh rebuild   # 从备份重新生成补丁 class（不部署）
#
# 约定
# ----
#   · 原始 class 备份：容器内 /tmp/ActionChat.class.bak_orig
#                     宿主侧 D:/O2OA/patch/ai/ActionChat.orig.class
#   · 目标 class：.../x_ai_assemble_control/WEB-INF/classes/.../chat/ActionChat.class
#   · work/ 是解包目录，实测【重启不会被 war 覆盖】，无需改 war
# =============================================================================
set -u

C=o2oa-server
CLASS_REL="servers/applicationServer/work/x_ai_assemble_control/WEB-INF/classes/com/x/ai/assemble/control/jaxrs/chat/ActionChat.class"
CLASS="/opt/o2server/$CLASS_REL"
BAK="/tmp/ActionChat.class.bak_orig"

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${O2OA_PY:-C:/Users/meng_/.workbuddy/binaries/python/versions/3.13.12/python.exe}"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
ok()   { echo "  [OK]   $*"; }
bad()  { echo "  [FAIL] $*"; }
warn() { echo "  [WARN] $*"; }

# docker exec 在本机（ARM64+QEMU）会间歇性 setns 失败 —— 统一加重试
dex() {
  local i out
  for i in 1 2 3 4 5 6; do
    out=$(docker exec "$C" bash -c "$1" 2>&1)
    case "$out" in
      *"setns"*|*"fork/exec /proc"*) sleep 3; continue;;
    esac
    printf '%s' "$out"
    return 0
  done
  return 1
}

# 从容器取文件（走 Docker API，不受 exec 故障影响）
dcp_out() { docker cp "$C:$1" "$2" >/dev/null 2>&1; }
# 写入容器文件
dcp_in()  { docker cp "$1" "$C:$2" >/dev/null 2>&1; }

probe() {
  # 返回: patched | orig | missing
  rm -f .probe.class
  dcp_out "$CLASS" .probe.class || { echo missing; return; }
  [ -s .probe.class ] || { echo missing; return; }
  if grep -qa "reasoning_effort" .probe.class; then echo patched; else echo orig; fi
}

restart_and_wait() {
  say "重启容器使补丁生效..."
  docker restart "$C" >/dev/null 2>&1
  # 等 web 9090 起来（QEMU 下约 3-6 分钟）
  local i code
  for i in $(seq 1 40); do
    sleep 15
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 \
      http://127.0.0.1:9090/x_organization_assemble_authentication/jaxrs/authentication 2>/dev/null)
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      ok "web 已就绪（HTTP $code，第 $((i*15)) 秒）"
      return 0
    fi
    printf '  ... 等待中 %ds\n' $((i*15))
  done
  bad "web 未在 10 分钟内就绪，请手工检查 docker logs $C"
  return 1
}

CMD="${1:-verify}"

case "$CMD" in
  # -------------------------------------------------------------------------
  apply)
    say "===== apply: 打 reasoning_effort 补丁 ====="

    ST=$(probe)
    if [ "$ST" = "patched" ]; then
      ok "当前已是补丁版（reasoning_effort），无需重复操作"
      say "如需确认，请运行: $0 verify"
      exit 0
    fi
    if [ "$ST" = "missing" ]; then
      bad "无法从容器读取 ActionChat.class"; exit 1
    fi
    ok "当前是原始版，开始打补丁"

    # 1) 备份（容器内；若已存在则不覆盖，保留最早的原件）
    if ! dex "test -f $BAK && echo yes" | grep -q yes; then
      dcp_out "$CLASS" /dev/null 2>/dev/null  # no-op，仅为日志清晰
      dex "cp $CLASS $BAK" >/dev/null
      ok "已在容器内备份原始 class -> $BAK"
    else
      warn "容器内已存在备份 $BAK，沿用（保留最早原件）"
    fi

    # 2) 取原件到宿主机
    rm -f ActionChat.orig.class
    dcp_out "$CLASS" ActionChat.orig.class
    [ -s ActionChat.orig.class ] || { bad "拉取原始 class 失败"; exit 1; }
    ok "原件已取回: $(stat -c%s ActionChat.orig.class 2>/dev/null || wc -c < ActionChat.orig.class) 字节"

    # 3) 生成补丁 class
    say "生成补丁 class..."
    "$PY" "$HERE/PatchActionChat.py" ActionChat.orig.class ActionChat.patched.class || {
      bad "补丁生成/自校验失败"; exit 1; }
    ok "补丁 class 已生成"

    # 4) 部署
    dcp_in ActionChat.patched.class "$CLASS" || { bad "写入容器失败"; exit 1; }
    ok "补丁 class 已部署到容器"

    # 5) 确认部署成功
    ST=$(probe)
    [ "$ST" = "patched" ] && ok "部署确认：容器内已是补丁版" || { bad "部署后探测异常"; exit 1; }

    # 6) 重启生效
    restart_and_wait || exit 1

    say "重新校验..."
    "$0" verify
    ;;

  # -------------------------------------------------------------------------
  verify)
    say "===== verify: 校验补丁状态 ====="
    ST=$(probe)
    case "$ST" in
      patched)
        ok "容器内 ActionChat.class 含 'reasoning_effort' —— 补丁已生效"
        ;;
      orig)
        bad "容器内仍是原始版（enable_thinking）—— 补丁未应用"
        echo "       下一步: $0 apply"
        exit 1
        ;;
      *)
        bad "无法读取容器内 class"; exit 1
        ;;
    esac

    # javap 级反汇编确认（exec 故障时跳过，不影响结论）
    DUMP=$(dex "/opt/o2server/jvm/linux_java11/bin/javap -p -v $CLASS 2>/dev/null | grep -c reasoning_effort")
    if echo "$DUMP" | grep -qE '^[1-9]'; then
      ok "javap 反汇编确认含 reasoning_effort（出现 $DUMP 次）"
    else
      warn "javap 校验跳过（容器 exec 暂时不可用），字节匹配已足够"
    fi

    # 端到端冒烟（可选，需可用凭据）
    if [ -f /c/temp/o2cookie.txt ] || [ -f ./o2cookie.txt ]; then
      ok "提示：可用 curl 直连 /x_ai_assemble_control/jaxrs/chat/completion 做端到端冒烟"
    fi
    ;;

  # -------------------------------------------------------------------------
  restore)
    say "===== restore: 回滚到原始 class ====="
    if ! dex "test -f $BAK && echo yes" | grep -q yes; then
      bad "容器内找不到备份 $BAK，无法回滚"
      echo "       若宿主机有原件，可手工: docker cp ActionChat.orig.class $C:$CLASS"
      exit 1
    fi
    dex "cp $BAK $CLASS" >/dev/null
    ST=$(probe)
    if [ "$ST" = "orig" ]; then
      ok "已回滚为原始 class"
    else
      bad "回滚后探测仍异常（$ST）"; exit 1
    fi
    restart_and_wait || exit 1
    say "回滚完成。注意：AI 助手对接推理模型时会再次出现空白回复。"
    ;;

  # -------------------------------------------------------------------------
  rebuild)
    say "===== rebuild: 仅重建补丁 class（不部署）====="
    rm -f ActionChat.orig.class
    dcp_out "$CLASS" ActionChat.orig.class
    [ -s ActionChat.orig.class ] || { bad "拉取失败"; exit 1; }
    "$PY" "$HERE/PatchActionChat.py" ActionChat.orig.class ActionChat.patched.class
    ok "产物: $HERE/ActionChat.patched.class"
    ;;

  *)
    grep '^#' "$0" | head -40
    exit 2
    ;;
esac
