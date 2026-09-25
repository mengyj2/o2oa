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
# 注意：① agent-browser 每次 bash 调用都是**全新浏览器会话**，整条流程必须写在一次调用里；
#      ② 被 SIGTERM 杀掉的上一次运行可能留下**脏守护进程** ⇒ 开头先 close 再 open；
#      ③ `screenshot` 的第 1 个位置参数是「选择器」而不是路径，故用 `screenshot body <path>`；
#      ④ 登录用 `input[name=credential]` / `input[name=password]` + 文本为「登录」的 button；
#         开始菜单按钮 = `.layout_menu_start_button`，菜单项 = `.layout_start_item_text`；
#      ⑤ 登录结果要**轮询** `layout.session.user`，不要用固定 sleep。
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
ev(){ agent-browser eval "$1" 2>/dev/null; }
clean(){ printf '%s' "$1" | tr -d '\\'; }

echo "[1/5] 打开桌面并登录 ..."
# ★ 每次 Bash 调用都是全新浏览器会话；且被 SIGTERM 杀掉的上一次运行可能留下脏守护进程，
#   故先 close 复位再 open（曾经因为跳过这步导致后续所有 eval 返回 {} 而全线失败）。
run close
sleep 2
run open "$URL"
sleep 8
# 用 CSS 选择器而非 snapshot 的 @eN —— 序号会随页面结构变化而失效
run fill "input[name=credential]" "$USER"
run fill "input[name=password]" "$PASS"
sleep 2
ev "(function(){var b=document.querySelectorAll('button,a,div,span');for(var i=0;i<b.length;i++){if((b[i].textContent||'').trim()==='登录'){b[i].click();return 'clicked';}}return 'no';})" >/dev/null
# ★ 轮询登录结果，不要用固定 sleep（登录耗时随机器负载波动）
USER_NAME=""
for i in 1 2 3 4 5 6 7 8; do
  sleep 4
  USER_NAME="$(clean "$(ev "(function(){return (typeof layout!=='undefined'&&layout.session&&layout.session.user)?layout.session.user.name:'';})()")" | sed 's/^"//;s/"$//')"
  [ -n "$USER_NAME" ] && break
  if [ "$i" = "4" ]; then
    ev "(function(){var b=document.querySelectorAll('button,a,div,span');for(var j=0;j<b.length;j++){if((b[j].textContent||'').trim()==='登录'){b[j].click();return 'reclicked';}}return 'no';})()" >/dev/null
  fi
done
echo "      登录用户：$USER_NAME"
[ -n "$USER_NAME" ] || { echo "FAIL —— 登录未成功（明细 $LOG）"; exit 1; }

echo "[2/5] 安装前端错误收集器 ..."
run eval "(function(){window.__errs=[];window.addEventListener('error',function(e){window.__errs.push('ERR: '+e.message);},true);return 'ok';})()"

echo "[3/5] 走真实路径：开始菜单「企业网盘」 ..."
# ★ 开始菜单按钮的稳定选择器是 .layout_menu_start_button（不再依赖 @e3 的序号）
# ★ 菜单面板异步渲染，固定 sleep 后只查一次会抖动 ⇒ 轮询 + 按需补点；
#   且只在「当前 0 项」时才点开始按钮（否则会把它 toggle 关掉，永远点不到）。
CLICKED="NOT-FOUND(n=0)"
for att in 1 2 3 4 5 6; do
  N="$(clean "$(ev "(function(){return document.querySelectorAll('.layout_start_item_text').length;})()")")"
  if [ "$N" = "0" ] || [ "$N" = '""' ]; then
    ev "(function(){var b=document.querySelector('.layout_menu_start_button');if(b){b.click();return 'start';}return 'no-start';})()" >/dev/null
  fi
  sleep 5
  CLICKED="$(clean "$(ev "(function(){var a=document.querySelectorAll('.layout_start_item_text');for(var i=0;i<a.length;i++){if((a[i].textContent||'').trim().indexOf('企业网盘')>=0){var t=a[i].closest('.layout_start_item')||a[i].parentNode;t.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));return 'clicked';}}return 'NOT-FOUND(n='+a.length+')';})()")")"
  case "$CLICKED" in *clicked*) break ;; esac
  sleep 2
done
echo "      $CLICKED"
# 窗口里还要等 drive.js 注入 + 首屏数据回来
for w in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  R="$(clean "$(ev "(function(){return document.querySelector('.drive-root')?'ready':'wait';})()")")"
  [ "$R" = '"ready"' ] && break
done

echo "[4/5] 断言渲染 ..."
STATE="$(agent-browser eval "(function(){return JSON.stringify({driveRoot:!!document.querySelector('.drive-root'),viewer:typeof (MWF.xApplication.Drive&&MWF.xApplication.Drive.Viewer),errs:(window.__errs||[]).slice(0,4)});})()" 2>/dev/null)"
echo "      $STATE"

echo "[5/5] 截图 -> $SHOT"
agent-browser screenshot body "$SHOT" >> "$LOG" 2>&1
agent-browser close >> "$LOG" 2>&1

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
