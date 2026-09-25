#!/usr/bin/env bash
# =============================================================================
# o2oa_netlock.sh —— 给 O2OA 容器加"出站封网"（保留宿主访问 + 保留 MySQL 通信）
#
# 背景（2026-09-19 实测结论）：
#   仅靠 docker-compose 的 `dns: [127.0.0.1]` 只能封【域名解析】，
#   **封不住 IP 直连** —— 实测容器内 `curl http://223.5.5.5` 返回 404，
#   说明 O2OA 若硬编码 IP 或缓存过 IP，依然能把数据发出去。
#
#   本脚本在内核 FORWARD 链上，对 O2OA 容器的源 IP 做 DROP：
#     规则：-s <o2oa容器IP> ! -d 172.16.0.0/12 -j DROP
#   即：只允许它访问 Docker 内网段（172.16/12，含 mysql），其余一律丢弃。
#   效果（已实测）：
#     ✓ 容器 → 外网 IP 直连：不通（Network unreachable / 超时）
#     ✓ 容器 → 域名解析：不通
#     ✓ 容器 → mysql:3306：正常（JDBC 实测 314 表可查）
#     ✓ 宿主 → localhost:9090：200 正常（端口映射不受影响）
#
# 用法：
#   sudo bash o2oa_netlock.sh            # 应用封网规则
#   sudo bash o2oa_netlock.sh --check    # 只检查当前状态（不改动）
#   sudo bash o2oa_netlock.sh --remove   # 移除本脚本加的规则
#
# 注意：
#   · Docker Desktop 重启后 iptables 规则会丢失 → 重跑本脚本即可（幂等）
#   · 容器重建后 IP 可能变化 → 重跑本脚本（会先清旧规则再按新 IP 加）
#   · 规则对"新增容器"不自动生效，只针对本脚本执行时的 o2oa 容器 IP
# =============================================================================
set -u

CONTAINER="${O2OA_CONTAINER:-o2oa-server}"
COMMENT_TAG="o2oa-netlock"          # 用 comment 标记本脚本的规则，便于精确增删
# Docker 内网段（允许 o2oa 访问的目标范围）。172.16.0.0/12 覆盖 172.16~172.31，
# 足以覆盖 Docker 默认的各类 bridge 子网，同时排除公网。
ALLOW_DST="172.16.0.0/12"

# ---------------------------------------------------------------------------
# 本地 LLM 白名单（2026-09-19 新增）
#
# 背景：O2OA 的 AI 助手（x_ai_assemble_control）支持"自定义模型"路径 ——
#   ActionChat.execute() 里，当 o2AiEnable=false 时走 aiChat()，
#   直接请求 model.getCompletionUrl()，**完全不碰官方云和 o2AiToken**。
#   所以我们把模型指向本机 LM Studio（局域网 IP:1234），即可离线用 AI。
#
# 问题：LM Studio 跑在【宿主】上，容器访问它要经 FORWARD 链，
#   会被下面的封网 DROP 规则挡掉（实测 SocketTimeoutException）。
#   解法：在 DROP 规则【之前】插一条精确 ACCEPT：
#     只放通 "<容器IP> → <LLM_HOST>:<LLM_PORT>" 这一条 TCP 连接，
#   其余目标（含所有公网）依然全封。
#
# 为什么不用 docker 网关 172.22.0.1？
#   实测 LM Studio 只监听宿主物理网卡与回环，**不响应 Docker 虚拟网卡**
#   （curl http://172.22.0.1:1234 → 000），故只能走宿主局域网 IP。
#
# 改这里：换网卡/换网段时更新 LLM_HOST 即可（可用环境变量覆盖）。
# ---------------------------------------------------------------------------
LLM_HOST="${O2OA_LLM_HOST:-192.168.1.5}"   # LM Studio 所在宿主的局域网 IP
LLM_PORT="${O2OA_LLM_PORT:-1234}"          # LM Studio 端口
GW_PORT="${O2OA_GW_PORT:-18790}"           # o2-agent-gateway（智能体适配网关）端口
# 本地邮件验证码服务（x_sms_assemble_control 平替）端口。
# 必须放行：O2OA 的 x_program_center 会主动 HTTP 回调本服务下发/校验验证码，
# 走 FORWARD 链，不加白名单会被下面的 DROP 干掉（表现为 CodeFactory create error）。
MAIL_PORT="${O2OA_MAIL_PORT:-8095}"        # mailservice/o2oa_mail_service.py 端口
# ★ 容器视角的「宿主」地址（用于 --check 的连通性探测）。
#   切勿用 host.docker.internal / 域名：本脚本会把容器 DNS 掐掉，容器内一切域名解析失败
#   （表现 curl 000 / UnknownHostException）。实测 192.168.65.254 是 Docker Desktop 的
#   宿主网关地址，容器可达宿主 8095。
MAIL_HOST="${O2OA_MAIL_HOST:-192.168.65.254}"
LLM_RULE="${O2OA_LLM_DISABLE:-0}"          # 设为 1 可临时禁用本地 LLM 白名单
ALLOW_TAG="o2oa-netlock-allow"             # 白名单规则的 comment 标记

R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[36m'; N=$'\033[0m'
log() { printf '%s[netlock]%s %s\n' "$B" "$N" "$*"; }
ok()  { printf '%s  ✓ %s%s\n' "$G" "$*" "$N"; }
warn(){ printf '%s  ! %s%s\n' "$Y" "$*" "$N"; }
err() { printf '%s  ✗ %s%s\n' "$R" "$*" "$N"; }

# ---- 所有 iptables 操作都借一个 privileged + host 网络的临时容器执行 ----
# （Docker Desktop on Windows 下，宿主的 iptables 在 VM 里，只能这样访问）
ipt() {
  docker run --rm --privileged --net=host alpine:latest sh -c \
    "apk add --no-cache iptables >/dev/null 2>&1 && $*" 2>/dev/null
}

# ---- 解析容器 IP ----
get_ip() {
  docker inspect "$CONTAINER" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' 2>/dev/null \
    | tr ' ' '\n' | grep -E '^[0-9]' | head -1
}

# ---- 清掉本脚本以前加的规则（按 comment 精确匹配）----
clear_mine() {
  # 反复删除，直到没有匹配（因为 line number 会变）
  # 同时清理封网规则(o2oa-netlock)与本地LLM白名单(o2oa-netlock-allow)
  for TAG in "$ALLOW_TAG" "$COMMENT_TAG"; do
    for _ in $(seq 1 20); do
      HIT=$(ipt "iptables -L FORWARD -n --line-numbers 2>/dev/null | grep '$TAG' | head -1" | awk '{print $1}')
      [ -n "$HIT" ] || break
      ipt "iptables -D FORWARD $HIT" >/dev/null 2>&1
    done
  done
}

# ---------------------------------------------------------------------------
# 容器内探测助手
#   ★ 本机 o2oa-server 的 `docker exec` 经常失败：
#     OCI runtime exec failed: ... fork/exec /proc/self/fd/6: no such file or directory
#     （Docker Desktop + QEMU 下 setns 不稳）。失败时回落为「临时 alpine 容器 + 目标容器
#     的网络命名空间」，DNS / 路由 / 源 IP 与容器内完全一致，探测结果等价。
# ---------------------------------------------------------------------------
in_container() {   # $1 = 在容器内执行的 sh 片段
  local out
  out=$(docker exec "$CONTAINER" sh -c "$1" 2>/dev/null)
  case "$out" in
    *"OCI runtime exec failed"*) ;;                    # exec 挂了 -> 回落
    "") ;;                                             # 无输出 -> 回落
    *) printf '%s\n' "$out"; return ;;
  esac
  docker run --rm --platform linux/arm64 --network "container:$CONTAINER" \
    alpine:latest sh -c "$1" 2>/dev/null
}

http_code() {   # $1 = url，输出 3 位状态码或 000
  local url="$1" out
  out=$(in_container "curl -s -o /dev/null -w '%{http_code}' --max-time 6 '$url'")
  if printf '%s' "$out" | grep -qE '^[0-9]{3}$'; then printf '%s' "$out"; return; fi
  # 无 curl（alpine 回落场景）-> 用 busybox wget 折算为 200 / 000
  in_container "wget -q -O /dev/null -T 6 '$url' >/dev/null 2>&1 && echo 200 || echo 000"
}

case "${1:-}" in
  --check) DO=check ;;
  --remove) DO=remove ;;
  *) DO=apply ;;
esac

printf '%s' "$B"; echo "═══════════════════════════════════════════════════════════"
echo "  O2OA 出站封网（保留宿主访问 + MySQL 通信）"
echo "═══════════════════════════════════════════════════════════"; printf '%s' "$N"

# ---- 前置检查 ----
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  err "容器 $CONTAINER 未运行"
  exit 1
fi
IP=$(get_ip)
if [ -z "$IP" ]; then
  err "无法解析 $CONTAINER 的 IP"
  exit 1
fi
log "容器 $CONTAINER 的 IP = $IP"

if [ "$DO" = "check" ]; then
  log "当前规则状态："
  ipt "iptables -L FORWARD -n --line-numbers 2>/dev/null | head -8" | sed 's/^/    /'
  echo
  log "容器外网连通性："
  _C=$(http_code "http://223.5.5.5")
  if [ "$_C" = "000" ] || [ -z "$_C" ]; then
    echo "    223.5.5.5 → 不通（已封）"
  else
    echo "    223.5.5.5 → 通（HTTP $_C）未封"
  fi
  _D=$(in_container "nslookup www.baidu.com >/dev/null 2>&1 && echo OK || echo FAIL" | tr -d ' \r\n')
  if [ "$_D" = "OK" ]; then
    echo "    DNS 解析 → 通（未隔离）"
  else
    echo "    DNS 解析 → 不通（已隔离）"
  fi
  echo
  log "宿主访问："
  printf '    localhost:9090 → %s\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:9090/ 2>/dev/null)"
  echo
  log "本地 LLM + 智能体网关（AI 助手依赖）："
  printf '    规则: %s\n' \
    "$(ipt "iptables -L FORWARD -n 2>/dev/null | grep -c '$ALLOW_TAG'" | tr -d ' ')"
  printf '    %s:%s → %s\n' "$LLM_HOST" "$LLM_PORT" "$(http_code "http://$LLM_HOST:$LLM_PORT/v1/models")"
  printf '    %s:%s → %s\n' "$LLM_HOST" "$GW_PORT" "$(http_code "http://$LLM_HOST:$GW_PORT/gateway/health")"
  printf '    邮件验证码 %s:%s → %s\n' "$MAIL_HOST" "$MAIL_PORT" "$(http_code "http://$MAIL_HOST:$MAIL_PORT/api/health")"
  exit 0
fi

if [ "$DO" = "remove" ]; then
  clear_mine
  ok "已移除本脚本添加的封网规则"
  warn "注意：容器现在恢复为「能上外网」的状态（仍受 DNS 限制）"
  exit 0
fi

# ---- 应用 ----
clear_mine     # 先清旧的（容器重建后 IP 会变）

# ① 先插本地 LLM 白名单（必须在 DROP 之前，否则被 DROP 抢先）
if [ "$LLM_RULE" = "1" ]; then
  warn "本地 LLM 白名单已按 O2OA_LLM_DISABLE=1 禁用（AI 助手将不可用）"
else
  # 先确保能到宿主的这条包被放通；插在链首（multiport 一条规则放通 LLM + 网关两个端口）
  ipt "iptables -I FORWARD 1 -s $IP -d $LLM_HOST -p tcp -m multiport --dports $LLM_PORT,$GW_PORT,$MAIL_PORT -m comment --comment '$ALLOW_TAG' -j ACCEPT"
  if ipt "iptables -L FORWARD -n 2>/dev/null | grep -q '$ALLOW_TAG'"; then
    ok "本地白名单已生效：$IP → $LLM_HOST:$LLM_PORT(LM Studio) + $GW_PORT(智能体网关) + $MAIL_PORT(邮件验证码) 放通"
  else
    err "本地 LLM 白名单添加失败"
  fi
fi

# ② 再插封网 DROP —— 必须排在白名单【之后】
#    注意：不能再用 -I FORWARD 1（那会把 DROP 插到白名单前面，白名单永远命中不到）。
#    此时链首是白名单规则，所以 DROP 插到位置 2。
#
#    ★ 关键修正（2026-09-20）：Docker Desktop 把"容器→宿主 LAN IP(192.168.1.5)"做了
#      NAT，到达 FORWARD 链时目标 IP 已不再是 192.168.1.5，导致上面第①条
#      `-d 192.168.1.5` 的白名单【永远匹配不上】，容器访问宿主网关(18790)/
#      LM Studio(1234)全部被本 DROP 规则干掉（实测 curl 返回 000）。
#      因此这里改用「端口排除」而非「目标 IP 白名单」：对发往本地 AI 服务端口
#      (1234/18790) 的 TCP 一律放行，其余发往非 172.16/12 的流量照旧 DROP。
#      这样既保留断云隔离，又保证容器→宿主的 AI 链路可达（不受 NAT 影响）。
ipt "iptables -I FORWARD 2 -s $IP ! -d $ALLOW_DST -p tcp -m multiport ! --dports $LLM_PORT,$GW_PORT,$MAIL_PORT -m comment --comment '$COMMENT_TAG' -j DROP"

if ipt "iptables -L FORWARD -n 2>/dev/null | grep -q '$COMMENT_TAG'"; then
  ok "封网规则已生效：源 $IP → 目标非 $ALLOW_DST 且非端口 $LLM_PORT/$GW_PORT/$MAIL_PORT 全部 DROP（本地服务端口放行）"
else
  err "规则添加失败（可能需要 Docker Desktop 管理员权限）"
  exit 1
fi

# ---- 立即验证 ----
echo
log "验证中…"
sleep 2
# 注意：curl 失败时自己会打印 000，若再加 `|| echo 000` 会得到 "000000"。
# 这里统一取最后一次输出，非 000 才算"通"。
EXT=$(docker exec "$CONTAINER" sh -c \
  'curl -s -o /dev/null -w "%{http_code}" --max-time 6 http://223.5.5.5 2>/dev/null; echo' | tr -d ' \r\n')
case "$EXT" in
  ''|*[!0-9]*) EXT=000 ;;
esac
if [ "$EXT" = "000" ]; then
  ok "外网 IP 直连已封死（223.5.5.5 不可达）"
else
  err "外网仍可达（$EXT）—— 请检查规则是否被其他链放通"
fi

HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:9090/ 2>/dev/null)
[ "$HTTP" = "200" ] && ok "宿主访问 9090 正常" || warn "宿主访问 9090 返回 $HTTP"

# ---- 本地 LLM 连通性验证（仅当白名单启用）----
if [ "$LLM_RULE" != "1" ]; then
  LLMCODE=$(docker exec "$CONTAINER" sh -c \
    "curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://$LLM_HOST:$LLM_PORT/v1/models 2>/dev/null; echo" 2>/dev/null | tr -d ' \r\n')
  case "$LLMCODE" in
    ''|*[!0-9]*) LLMCODE=000 ;;
  esac
  if [ "$LLMCODE" = "200" ]; then
    ok "本地 LLM 可达（$LLM_HOST:$LLM_PORT → HTTP 200，AI 助手可用）"
  else
    warn "本地 LLM 不可达（$LLM_HOST:$LLM_PORT → $LLMCODE）"
    warn "  · 请确认宿主已启动 LM Studio 并加载模型、端口为 $LLM_PORT"
    warn "  · 若宿主 IP 已变，请设置 O2OA_LLM_HOST=<新IP> 后重跑本脚本"
  fi
fi

echo
printf '%s完成。%s\n' "$G" "$N"
echo "  · Docker Desktop 重启后需重跑本脚本（规则会丢）"
echo "  · 容器重建后需重跑本脚本（IP 会变）"
echo "  · 查看状态: bash o2oa_netlock.sh --check"
echo "  · 撤销封网: bash o2oa_netlock.sh --remove"
echo "  · 本地 LLM: $LLM_HOST:$LLM_PORT （禁用: O2OA_LLM_DISABLE=1）"
