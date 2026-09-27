#!/bin/bash
# o2_drive_ui_verify.sh —— 「企业网盘」前端 UI 真机回归自检
#
# 为什么需要它：
#   `tools/o2_drive_selftest.py` 只验证后端数据层（HTTP 接口全通），
#   无法发现"组件被浏览器加载/渲染失败"这类问题——本次正是踩了这个坑：
#   后端 20/20 通过，但前端因缺 Main.min.js 而打开一片空白。
#
# 它做什么：
#   用真实浏览器登录 O2OA 桌面 -> 走真实用户路径（办公中心 -> 开始菜单「企业网盘」）
#   -> 断言 .drive-root 渲染成功且无 JS 报错 -> 存档截图。
#
# 前置：agent-browser 可用；账号 admin / o2oaadmin2026；服务在 localhost:9090。
# 注意：agent-browser 的浏览器会话不跨命令存活，因此整条流程必须写在一次调用里。
#       （screenshot 的第 1 个位置参数是「选择器」而不是路径，故用 `screenshot body <path>`）
#
# 用法： bash tools/o2_drive_ui_verify.sh
set -u
cd "$(dirname "$0")/.." || exit 1

BASE="${O2OA_BASE:-http://localhost:9090}"
URL="$BASE/x_desktop/index.html"
USER="${O2OA_USER:-admin}"
PASS="${O2OA_PASS:-o2oaadmin2026}"
SHOT="${1:-.drive-ui-verify.png}"
LOG="$(mktemp -t driveui.XXXXXX.log)"
: > "$LOG"

run(){ agent-browser "$@" >> "$LOG" 2>&1; }
say(){ echo "###### $*" >> "$LOG"; }

echo "[1/5] 打开桌面并登录 ..."
run open "$URL"
sleep 5
run snapshot -i -c
run fill @e6 "$USER"
run fill @e7 "$PASS"
run click @e4
sleep 15
run eval "typeof (window.layout&&layout.session&&layout.session.user)!=='undefined'&&layout.session.user?layout.session.user.name:''" >> "$LOG" 2>&1

echo "[2/5] 安装前端错误收集器 ..."
run eval "(function(){window.__errs=[];window.addEventListener('error',function(e){window.__errs.push('ERR: '+e.message);},true);return 'ok';})()"

echo "[3/5] 走真实路径：办公中心 -> 开始菜单「企业网盘」 ..."
run click @e3          # 办公中心（触发开始菜单渲染）
sleep 8
CLICKED="$(agent-browser eval "(function(){var a=document.querySelectorAll('.layout_start_item_text');for(var i=0;i<a.length;i++){if((a[i].textContent||'').trim().indexOf('企业网盘')>=0){var t=a[i].closest('.layout_start_item')||a[i].parentNode;t.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));return 'clicked';}}return 'NOT-FOUND';})()" 2>/dev/null)"
echo "      $CLICKED"
sleep 15

echo "[4/5] 断言渲染 ..."
STATE="$(agent-browser eval "(function(){return JSON.stringify({driveRoot:!!document.querySelector('.drive-root'),viewer:typeof (MWF.xApplication.Drive&&MWF.xApplication.Drive.Viewer),errs:(window.__errs||[]).slice(0,4)});})()" 2>/dev/null)"
echo "      $STATE"

echo "[5/5] 截图 -> $SHOT"
agent-browser screenshot body "$SHOT" >> "$LOG" 2>&1

# eval 返回的是 JSON 外层已转义的字符串（含 \" ），先去掉反斜杠再断言
STATE_CLEAN="$(printf '%s' "$STATE" | tr -d '\\')"
OK=1
case "$CLICKED" in *clicked*) ;; *) OK=0; echo "  !! 未找到「企业网盘」入口" ;; esac
case "$STATE_CLEAN" in *'"driveRoot":true'*) ;; *) OK=0; echo "  !! .drive-root 未渲染" ;; esac
case "$STATE_CLEAN" in *'"viewer":"function"'*) ;; *) OK=0; echo "  !! Drive.Viewer 未加载（检查 *.min.js 是否齐全）" ;; esac
case "$STATE_CLEAN" in *'ERR:'*) OK=0; echo "  !! 前端有 JS 报错" ;; esac

echo
if [ "$OK" = "1" ]; then
  echo "PASS —— 企业网盘 UI 真机渲染正常（截图 $SHOT，明细 $LOG）"
  exit 0
else
  echo "FAIL —— 明细见 $LOG"
  exit 1
fi
