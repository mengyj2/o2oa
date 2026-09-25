#!/bin/bash
# ============================================================================
# restore_o2oa_state.sh —— 从 backup_o2oa_state.sh 产物恢复 O2OA 状态
# ----------------------------------------------------------------------------
# 用法: bash tools/restore_o2oa_state.sh <backup-dir>   （backup-dir 含 MANIFEST.txt）
#
# 恢复内容：
#   1) MySQL 业务库 X  —— 导入 mysql-X.sql.gz（gunzip 流式导入，建库前会先 DROP 再建）
#   2) o2oa 命名卷    —— 清空后解包各 *.tar.gz 回对应卷
#
# ⚠️ 破坏性操作：会覆盖目标 MySQL 库与所有 o2oa 卷的现有内容！
#   建议流程：先 docker compose down（停服务）→ 跑本脚本 → docker compose up -d。
#   本脚本不做自动停服，请自行确保目标容器可写、且无并发写入。
# ============================================================================
set -euo pipefail

# Git Bash 下禁止 MSYS 自动改写路径（否则 -v 挂载的 Windows 绝对路径会被篡改）
export MSYS_NO_PATHCONV=1

SRC="${1:-}"
if [ -z "$SRC" ]; then
  echo "用法: bash tools/restore_o2oa_state.sh <backup-dir>" >&2
  exit 1
fi
if [ ! -f "$SRC/MANIFEST.txt" ]; then
  echo "错误: $SRC/MANIFEST.txt 不存在，确认这是 backup_o2oa_state.sh 的产物" >&2
  exit 1
fi

cd "$(dirname "$0")/.." || exit 1

# 转成 docker(Windows) 认的 Windows 绝对路径（正斜杠），用于 -v 挂载
SRC_ABS="$(cd "$SRC" && pwd)"
SRC_DOCKER="$(cygpath -w "$SRC_ABS" 2>/dev/null | tr '\\' '/')"
: "${SRC_DOCKER:=$SRC_ABS}"

MYSQL_CONTAINER="${O2OA_MYSQL_CONTAINER:-o2oa-mysql}"
MYSQL_DB="${O2OA_DB_NAME:-X}"
MYSQL_PLATFORM="${O2OA_MYSQL_PLATFORM:-linux/arm64}"
VOLUMES=(o2oa_o2oa-config o2oa_o2oa-local o2oa_o2oa-webroot o2oa_o2oa-custom o2oa_o2oa-dynamic)

echo "=================================================================="
echo "  即将从以下备份恢复 O2OA 状态（破坏性，会覆盖现有数据）："
echo "  备份目录 : $SRC"
echo "  MySQL 库 : $MYSQL_DB"
echo "  卷       : ${VOLUMES[*]}"
echo "=================================================================="
echo "  确认继续？5 秒后自动开始（Ctrl-C 取消）..."
sleep 5

# ---- 1) MySQL 导入 ----
SQLGZ="$SRC/mysql-$MYSQL_DB.sql.gz"
if [ ! -f "$SQLGZ" ]; then
  echo "错误: 找不到 $SQLGZ" >&2
  exit 1
fi
echo "[1/2] 恢复 MySQL 库 $MYSQL_DB ..."
docker exec -i "$MYSQL_CONTAINER" sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS '"$MYSQL_DB"'; CREATE DATABASE '"$MYSQL_DB"' CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"' 2>/dev/null
gunzip -c "$SQLGZ" | docker exec -i "$MYSQL_CONTAINER" sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" '"$MYSQL_DB"
echo "      MySQL 恢复完成"

# ---- 2) 卷解包 ----
echo "[2/2] 恢复各命名卷 ..."
for v in "${VOLUMES[@]}"; do
  TAR="$SRC/$v.tar.gz"
  if [ ! -f "$TAR" ]; then
    echo "      ! 跳过 $v （备份中无 $TAR）"
    continue
  fi
  echo "      - $v"
  docker run --rm --platform "$MYSQL_PLATFORM" -v "$v:/dest" -v "$SRC_DOCKER:/src" mysql:8.0 \
    sh -c "cd /dest && rm -rf ./* ./.[!.]* && tar xzf /src/$v.tar.gz"
done

echo "==> 恢复完成。建议: docker compose restart o2oa（或 up -d）让新数据生效。"
