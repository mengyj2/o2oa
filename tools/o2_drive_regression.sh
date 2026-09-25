#!/bin/bash
# o2_drive_regression.sh —— 「企业网盘」第五批功能回归（真机 · agent-browser）
#
# 与 o2_drive_ui_verify.sh 的分工：
#   o2_drive_ui_verify.sh      = 冒烟自检（能否打开、有没有 JS 报错）
#   o2_drive_regression.sh     = 功能回归（建夹/删除/上传/预览/共享/设置/超限拦截），跑完整业务流
#
# 用法：
#   bash tools/o2_drive_regression.sh                 # 跑主回归
#   bash tools/o2_drive_regression.sh uploadlimit     # 只跑「共享区上传大小上限」专项
#   bash tools/o2_drive_regression.sh admin           # 只跑「后台管理（成员容量/用户总览）」专项
#   bash tools/o2_drive_regression.sh main out.png    # 指定截图路径
#
# ★ 前置约定（踩过的坑）：
#   ① 每次 Bash 调用都是全新浏览器会话 ⇒ 整条流程必须写在一个脚本里；
#   ② 被 SIGTERM 杀掉的上一次运行会留下**脏守护进程** ⇒ 开头先 close 再 open；
#   ③ 登录要**轮询** `layout.session.user`，不要固定 sleep；
#   ④ 开始菜单是异步渲染 + toggle 面板 ⇒ 先查项数，为 0 才点按钮，再轮询；
#   ⑤ 回归脚本会在盘里留下测试文件/共享/文件夹，跑完请按提示清理（见末尾）。
set -u
cd "$(dirname "$0")/.." || exit 1

BASE="${O2OA_BASE:-http://localhost:9090}"
USER="${O2OA_USER:-admin}"
PASS="${O2OA_PASS:-o2oaadmin2026}"

case "${1:-main}" in
  uploadlimit|size) RUNNER="tools/drive_regression_uploadlimit.js"; VAR="__rt5b" ;;
  admin)            RUNNER="tools/drive_regression_admin.js";       VAR="__rt6" ;;
  uploaddiag)       RUNNER="tools/drive_upload_diag.js";           VAR="__rt7" ;;
  main|*)           RUNNER="tools/drive_regression_runner.js";      VAR="__rt5" ;;
esac
SHOT="${2:-.drive-regression.png}"
[ -f "$RUNNER" ] || { echo "找不到回归脚本 $RUNNER"; exit 1; }

run(){ agent-browser "$@" >/dev/null 2>&1; }
ev(){ agent-browser eval "$1" 2>/dev/null; }
clean(){ printf '%s' "$1" | tr -d '\\'; }

echo "[1/4] 打开桌面并登录 ..."
run close
sleep 2
run open "$BASE/x_desktop/index.html"
sleep 9
run fill "input[name=credential]" "$USER"
run fill "input[name=password]" "$PASS"
sleep 1
ev "(function(){var b=document.querySelectorAll('button,a,div,span');for(var i=0;i<b.length;i++){if((b[i].textContent||'').trim()==='登录'){b[i].click();return 'clicked';}}return 'no';})" >/dev/null
U=""
for i in 1 2 3 4 5 6 7 8; do
  sleep 4
  U="$(clean "$(ev "(function(){return (typeof layout!=='undefined'&&layout.session&&layout.session.user)?layout.session.user.name:'';})()")" | sed 's/^"//;s/"$//')"
  [ -n "$U" ] && break
  [ "$i" = "4" ] && ev "(function(){var b=document.querySelectorAll('button,a,div,span');for(var j=0;j<b.length;j++){if((b[j].textContent||'').trim()==='登录'){b[j].click();return 'reclicked';}}return 'no';})()" >/dev/null
done
echo "      登录用户：$U"
[ -n "$U" ] || { echo "FAIL —— 登录未成功"; exit 1; }

echo "[2/4] 启动页面内回归脚本（$RUNNER）..."
ev "$(cat "$RUNNER")" >/dev/null

echo "[3/4] 轮询结果（最长 ~3 分钟）..."
OUT=""
for i in $(seq 1 45); do
  sleep 4
  R="$(ev "(function(){return window.$VAR&&window.$VAR.done?window.$VAR.out:'PENDING';})()")"
  case "$R" in
    *PENDING*|"") printf "." ;;
    *) printf '\n'; OUT="$(printf '%b' "$R" | sed 's/^"//;s/"$//')"; printf '%s\n' "$OUT"; break ;;
  esac
done
[ -n "$OUT" ] || { printf '\n'; echo "!! 超时未拿到结果"; }

echo
echo "[4/4] 截图 -> $SHOT"
ev "(function(){var w=document.querySelector('.drive-root');return 'ok';})()" >/dev/null
agent-browser screenshot body "$SHOT" >/dev/null 2>&1
run close

case "$OUT" in
  *"EXCEPTION"*) echo "FAIL —— 回归脚本抛异常，见上方 EXCEPTION 行"; exit 1 ;;
esac
echo "DONE —— 回归执行完毕（逐项断言见上方输出）"
echo "提示：回归会在网盘里留残留（测试文件夹/文件/共享），需要时用 tools/o2_drive_selftest.py 或手工在界面里清理。"
