#!/bin/bash
# ============================================================================
# backup_o2oa_state.sh —— O2OA 整机「可迁移」状态备份
# ----------------------------------------------------------------------------
# 备份范围（git 不覆盖的运行态业务数据）：
#   1) MySQL 业务库 X  —— 逻辑 dump（mysqldump --single-transaction，一致性快照、不锁表）
#   2) o2oa 命名卷    —— 文件级 tar.gz（config/local/webroot/custom/dynamic）
# 产物落在 backups/<时间戳>/（已 gitignore），迁移时连同 git 仓库一起拷走即可。
#
# 设计要点（踩坑固化）：
#   · 本机 ARM64 + QEMU：mysql:8.0 不显式指定平台会默认拉 amd64，arm64 上 exec format error；
#     故一律 --platform linux/arm64（与 compose 一致，且镜像已存在，免拉新镜像）。
#   · MySQL 端口未映射宿主，只能走 docker exec（已验证可用）；密码用容器内
#     $MYSQL_ROOT_PASSWORD 解析，不在宿主命令行/进程表留明文。
#   · 卷 tar 复用已存在的 mysql:8.0 arm64 镜像，不依赖额外镜像。
#   · 容器内 dns 被断云（127.0.0.1），但容器间/exec 不受影响。
# ============================================================================
set -euo pipefail

# Git Bash 下禁止 MSYS 自动改写路径（否则 -v 挂载的 Windows 绝对路径会被篡改）
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.." || exit 1

MYSQL_CONTAINER="${O2OA_MYSQL_CONTAINER:-o2oa-mysql}"
MYSQL_DB="${O2OA_DB_NAME:-X}"
MYSQL_PLATFORM="${O2OA_MYSQL_PLATFORM:-linux/arm64}"   # 本机 ARM64；换 amd64 机器改此值
# 卷名 = compose 项目名(o2oa) + 服务卷名；若改过 COMPOSE_PROJECT_NAME 请同步调整
VOLUMES=(o2oa_o2oa-config o2oa_o2oa-local o2oa_o2oa-webroot o2oa_o2oa-custom o2oa_o2oa-dynamic)

TS="$(date +%Y%m%d-%H%M%S)"
OUT_BASE="${BACKUP_DIR:-backups}"
OUT="$OUT_BASE/o2oa-state-$TS"
KEEP="${BACKUP_KEEP:-7}"   # 保留最近 N 份，超出自动清理

mkdir -p "$OUT"

# 转成 docker(Windows) 认的 Windows 绝对路径（正斜杠），用于 -v 挂载
OUT_ABS="$(cd "$OUT" && pwd)"
OUT_DOCKER="$(cygpath -w "$OUT_ABS" 2>/dev/null | tr '\\' '/')"
: "${OUT_DOCKER:=$OUT_ABS}"

echo "==> 备份目标: $OUT"

# ---- 1) MySQL 逻辑备份 ----
echo "[1/2] mysqldump $MYSQL_DB (--single-transaction) ..."
docker exec "$MYSQL_CONTAINER" sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --events --triggers --hex-blob '"$MYSQL_DB" \
  | gzip > "$OUT/mysql-$MYSQL_DB.sql.gz"
echo "      mysql-$MYSQL_DB.sql.gz = $(du -h "$OUT/mysql-$MYSQL_DB.sql.gz" | cut -f1)"

# ---- 2) o2oa 命名卷文件级备份 ----
echo "[2/2] volumes -> tar.gz"
for v in "${VOLUMES[@]}"; do
  echo "      - $v"
  docker run --rm --platform "$MYSQL_PLATFORM" -v "$v:/source:ro" -v "$OUT_DOCKER:/dest" mysql:8.0 \
    tar czf "/dest/$v.tar.gz" -C /source .
done

# ---- 3) 清单（关联当前代码状态，便于迁移时对齐版本）----
GIT_HASH="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
{
  echo "O2OA state backup"
  echo "created : $(date)"
  echo "host    : $(hostname)"
  echo "git     : $GIT_HASH ($GIT_BRANCH)"
  echo "mysql   : $MYSQL_DB -> mysql-$MYSQL_DB.sql.gz"
  echo "volumes : ${VOLUMES[*]}"
  echo "--- files ---"
  ls -lh "$OUT" | sed 's/^/  /'
} > "$OUT/MANIFEST.txt"

# ---- 4) 保留策略：仅保留最近 KEEP 份 ----
if [ "$KEEP" -gt 0 ]; then
  # 按目录名时间戳倒序，删除超出部分
  mapfile -t OLD < <(ls -1dt "$OUT_BASE"/o2oa-state-* 2>/dev/null | tail -n +$((KEEP+1)))
  for d in "${OLD[@]:-}"; do
    [ -n "$d" ] && echo "prune   : $d" && rm -rf "$d"
  done
fi

echo "==> DONE. 产物见 $OUT （含 MANIFEST.txt）"
