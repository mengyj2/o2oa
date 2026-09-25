#!/bin/bash
# deploy_drive.sh —— 把自研「企业网盘」组件 x_component_Drive 部署进运行中的 O2OA 容器
#
# ★ 关键事实（踩过的坑）：
#   O2OA 启动时会执行「move the unofficial directory to webroot directory」——
#   把 servers/webServer/x_component_Drive 整目录【移动】到 webroot 下。
#   所以运行中容器里**真正被 HTTP 服务的路径是**：
#         /opt/o2server/webroot/x_component_Drive
#   （compose 中 webroot 是命名卷 o2oa-webroot，持久化，容器重建不丢）
#   ⇒ 更新组件内容必须 docker cp 到 webroot 路径；拷到 servers/webServer 会在下次启动被再次移动。
#
# 用法：bash tools/deploy_drive.sh
set -u
cd "$(dirname "$0")/.." || exit 1

CT="${O2OA_CONTAINER:-o2oa-server}"
BASE="${O2OA_BASE:-http://localhost:9090}"
SRC="deploy/runtime/webroot/x_component_Drive"
WD_LIVE="/opt/o2server/webroot/x_component_Drive"          # 实际生效
WD_IMG="/opt/o2server/servers/webServer/x_component_Drive" # 镜像内 COPY 位（新装用）

# 自研组件必须成对提供 *.min.js（bundle.js 会把 .js 改写成 .min.js）
cp -f "$SRC/Main.js"      "$SRC/Main.min.js"
cp -f "$SRC/lp/zh-cn.js"  "$SRC/lp/zh-cn.min.js"
cp -f "$SRC/drive/drive.js" "$SRC/drive/drive.min.js"

# 语法自检
NODE="${NODE_BIN:-C:/Users/meng_/.workbuddy/binaries/node/versions/22.22.2-3/node.exe}"
if [ -x "$NODE" ]; then
  for f in "$SRC/Main.js" "$SRC/drive/drive.js" "$SRC/lp/zh-cn.js"; do
    "$NODE" --check "$f" || { echo "语法检查失败：$f"; exit 1; }
  done
  echo "[1/3] 语法检查通过"
fi

echo "[2/3] 同步到容器 $WD_LIVE ..."
for f in Main.js Main.min.js drive/drive.js drive/drive.min.js drive/drive.css lp/zh-cn.js lp/zh-cn.min.js; do
  docker cp "$SRC/$f" "$CT:$WD_LIVE/$f" || { echo "  !! 失败 $f"; exit 1; }
done
# 顺带同步镜像 COPY 位（存在才拷；下次新装/重建时生效）
for f in Main.js Main.min.js drive/drive.js drive/drive.min.js drive/drive.css lp/zh-cn.js lp/zh-cn.min.js; do
  docker cp "$SRC/$f" "$CT:$WD_IMG/$f" >/dev/null 2>&1 || true
done

echo "[3/3] HTTP 校验 ..."
ok=1
for f in Main.js Main.min.js drive/drive.js drive/drive.min.js drive/drive.css lp/zh-cn.js lp/zh-cn.min.js; do
  code=$(curl -s --noproxy "*" -o /dev/null -w "%{http_code}" "$BASE/x_component_Drive/$f")
  printf "      %s  %s\n" "$code" "$f"
  [ "$code" = "200" ] || ok=0
done
[ "$ok" = "1" ] && echo "PASS —— 组件已部署（版本 $(curl -s --noproxy '*' "$BASE/x_component_Drive/Main.js" | grep -o 'VERSION = "[^"]*"'))" || { echo "FAIL"; exit 1; }
