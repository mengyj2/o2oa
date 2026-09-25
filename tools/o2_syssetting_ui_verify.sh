#!/bin/bash
# o2_syssetting_ui_verify.sh —— 「系统设置」真机 UI 回归（包装 node 版）
#
# 说明：原先照 o2_drive_ui_verify.sh 用 agent-browser，但本机 agent-browser 的
#       daemon 会卡死（open 无输出、数分钟不返回；清 default.* 状态文件与重装
#       Chrome 都无效）。已改为 playwright-core 直驱 Chrome，见同名 .js。
#       如需回到 agent-browser 版，请先确认 `agent-browser open about:blank` 能返回。
#
# 用法： bash tools/o2_syssetting_ui_verify.sh [截图路径]
set -u
cd "$(dirname "$0")/.." || exit 1

NODE="${O2OA_NODE:-}"
if [ -z "$NODE" ]; then
  if command -v node >/dev/null 2>&1; then
    NODE="node"
  else
    for c in "/c/Program Files/nodejs/node.exe" \
             "/c/Users/meng_/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"; do
      [ -x "$c" ] && NODE="$c" && break
    done
  fi
fi
[ -n "$NODE" ] || { echo "FAIL —— 找不到 node，可设 O2OA_NODE 指定"; exit 2; }

echo "node: $NODE"
"$NODE" tools/o2_syssetting_ui_verify.js "${1:-.syssetting-ui-verify.png}"
