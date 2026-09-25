#!/usr/bin/env bash
# =============================================================================
# upgrade_o2oa.sh —— O2OA 升级：从新版 zip 自动重放全部补丁并重建镜像
#
# 用法（在 Git Bash 里跑，或双击 upgrade_o2oa.bat）：
#   ./upgrade_o2oa.sh                       # 自动找 D:\O2OA\o2server-*-linux-x64.zip
#   ./upgrade_o2oa.sh o2server-10.0.3-linux-x64.zip
#   SKIP_BUILD=1 ./upgrade_o2oa.sh          # 只打补丁不构建镜像（预演）
#   KEEP_CONTAINER=1 ./upgrade_o2oa.sh      # 构建后不重启容器
#
# 它做这些事：
#   1. 校验 zip、识别版本号
#   2. 从 zip 里提取「原始」console.jar / x_base_core_project.jar
#   3. 起一个临时容器，跑补丁流水线（全程离线、产物带离线 JVM 校验）
#   4. 把补丁产物落回 patch/ 目录
#   5. 更新 Dockerfile 与 compose 里的版本号
#   6. 构建镜像 → 重建容器 → 验证 MySQL 真的接管
#
# 它明确不做（做不到就不装作做到）：
#   - 新版若改了 ResourceFactory.internal() 的方法结构，补丁会失败并给出明确原因，
#     此时【不会】产出镜像，也不会覆盖你现有的可用状态。届时需要人工介入。
# =============================================================================
set -u

cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)

# ---- 配置 ----
IMAGE_TAG_PREFIX="o2oa"
CONTAINER="o2oa-server"
MYSQL_CONTAINER="o2oa-mysql"
MYSQL_ROOT_PWD="o2oa_root_pwd"
DB_NAME="X"
PATCH_IMAGE="o2oa-patch-runner:tmp"

# ---- 颜色 ----
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
die() { err "$1"; [ -n "${2:-}" ] && printf '%s\n' "  → $2"; hr; printf '%s升级中止，未做任何破坏性改动。%s\n' "$R" "$N"; exit 1; }

hr
printf '%s  O2OA 升级助手 —— 自动重放数据源补丁并重建镜像%s\n' "$B" "$N"
hr

# 无论成功、失败还是被 Ctrl-C，都清掉临时打补丁容器，避免残留。
# （工作目录 .upgrade-work 故意保留，失败时它是唯一证据。）
cleanup() {
  docker rm -f o2oa-patch-runner >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# =============================================================================
# 1. 定位并校验 zip
# =============================================================================
log "步骤 1/8：定位新版安装包"

ZIP="${1:-}"
if [ -z "$ZIP" ]; then
  # 自动挑选：优先 10.0.X 版本号最大的
  ZIP=$(ls -1 o2server-*-linux-x64.zip 2>/dev/null | sort -V | tail -1)
fi
[ -n "$ZIP" ] || die "没有找到 o2server-*-linux-x64.zip" "请把新版 zip 放到 $ROOT 下，或作为第一个参数传入"
[ -f "$ZIP" ] || die "文件不存在: $ZIP" "检查路径与文件名"

# 版本号：从文件名解析
VER=$(printf '%s' "$ZIP" | sed -n 's/^o2server-\(.*\)-linux-x64\.zip$/\1/p')
[ -n "$VER" ] || die "无法从文件名解析版本号: $ZIP" "期望形如 o2server-10.0.3-linux-x64.zip"

ZIP_MD5=$(md5sum "$ZIP" 2>/dev/null | cut -d' ' -f1)
ZIP_SIZE=$(stat -c%s "$ZIP" 2>/dev/null || echo 0)
ok "安装包: $ZIP"
log "       版本 = $VER   大小 = $((ZIP_SIZE/1024/1024)) MB   md5 = ${ZIP_MD5:-N/A}"

# 校验 zip 结构（顶层必须是 o2server/）
if ! unzip -l "$ZIP" 2>/dev/null | grep -qE '^\s+[0-9]+.*o2server/(store|commons|jvm)/'; then
  warn "zip 顶层结构不像标准 O2OA 包，继续但请留意"
fi

# 记录这次升级的目标版本（后面要用）
printf '%s\n' "$VER" > .o2oa_target_version

# 记录升级前的状态，便于回滚（旧 zip 名 + 旧镜像标签）
OLD_ZIP=$(grep -oE 'o2server-[0-9.]+-linux-x64\.zip' Dockerfile 2>/dev/null | head -1)
OLD_IMG=$(grep -oE 'o2oa:[0-9.]+' docker-compose.yml 2>/dev/null | head -1)
{
  echo "upgraded_at=$(date -Iseconds)"
  echo "target_version=$VER"
  echo "old_zip=$OLD_ZIP"
  echo "old_image=$OLD_IMG"
} > .o2oa_upgrade_history
[ -n "$OLD_ZIP" ] && log "       升级前安装包: $OLD_ZIP   镜像: ${OLD_IMG:-未知}"

# =============================================================================
# 2. 提取原始 jar
# =============================================================================
log "步骤 2/8：从 zip 提取原始 jar"

WORK=".upgrade-work"
rm -rf "$WORK"; mkdir -p "$WORK/in" "$WORK/out"

CJ_IN_ZIP="o2server/console.jar"
XC_IN_ZIP="o2server/store/jars/x_base_core_project.jar"

unzip -o -q "$ZIP" "$CJ_IN_ZIP" -d "$WORK/raw" || die "无法从 zip 解出 console.jar" "确认 zip 内含 o2server/console.jar"
unzip -o -q "$ZIP" "$XC_IN_ZIP" -d "$WORK/raw" || die "无法从 zip 解出 x_base_core_project.jar" "确认 zip 内含 o2server/store/jars/x_base_core_project.jar"

cp "$WORK/raw/$CJ_IN_ZIP" "$WORK/in/console.orig.jar"
cp "$WORK/raw/$XC_IN_ZIP" "$WORK/in/x_base_core_project.orig.jar"
ok "console.orig.jar            md5=$(md5sum "$WORK/in/console.orig.jar" | cut -d' ' -f1)"
ok "x_base_core_project.orig.jar md5=$(md5sum "$WORK/in/x_base_core_project.orig.jar" | cut -d' ' -f1)"

# 幂等短路：若与当前 Dockerfile 用的产物同源，提示
if [ -f patch/.patched_source_md5 ]; then
  PREV_CJ=$(sed -n '1p' patch/.patched_source_md5 2>/dev/null)
  PREV_XC=$(sed -n '2p' patch/.patched_source_md5 2>/dev/null)
  if [ "$PREV_CJ" = "$(md5sum "$WORK/in/console.orig.jar" | cut -d' ' -f1)" ] \
     && [ "$PREV_XC" = "$(md5sum "$WORK/in/x_base_core_project.orig.jar" | cut -d' ' -f1)" ]; then
    warn "检测到该版本已打过补丁（源 jar 哈希一致）"
    printf '%s' "        仍要继续重打吗？产物会覆盖现有同名文件 [y/N] "
    read -r _a </dev/tty 2>/dev/null || _a=n
    case "$_a" in y|Y) ok "继续重打" ;; *) log "已取消"; exit 0 ;; esac
  fi
fi

# =============================================================================
# 3. 准备临时打补丁容器
# =============================================================================
log "步骤 3/8：准备打补丁环境（复用现有镜像，纯离线）"

# 找一个「已解压好 O2OA + 自带 JDK/javassist/ASM」的镜像来跑补丁。
# 优先新标签（若已 build 过），其次老标签（当前在用的），最后才联网构建。
BASE_IMG=""
for cand in "o2oa:$VER" "o2oa:10.0.2"; do
  if docker image inspect "$cand" >/dev/null 2>&1; then
    if docker run --rm --entrypoint sh "$cand" -c \
         'test -x /opt/o2server/jvm/linux_java11/bin/java && test -f /opt/o2server/commons/ext_java11/javassist-3.21.0-GA.jar && test -f /opt/o2server/commons/ext_java11/asm-9.7.jar' \
         >/dev/null 2>&1; then
      BASE_IMG="$cand"; break
    fi
  fi
done

if [ -z "$BASE_IMG" ]; then
  warn "本地没有「已解压 O2OA 且带 JDK/javassist/ASM」的镜像"
  log "        需要临时构建一个（只解压 zip，不联网 apt）…"
  # 注意：不能写 `COPY o2server-*-linux-x64.zip` —— 目录里可能存在多个版本的
  # zip，glob 命中多个会让 COPY 直接失败。这里用 tar 管道把「指定这一个 zip」
  # 作为构建上下文传进去，彻底避开宿主机 glob 与 .dockerignore 的坑。
  if ! tar -cf - "$ZIP" | docker build -t "$PATCH_IMAGE" -f - . > "$WORK/baseimg.log" 2>&1 <<'DOCKERFILE'
FROM ubuntu:22.04
COPY o2server-10.0.2-linux-x64.zip /tmp/o2server.zip
RUN cd /opt && unzip -q /tmp/o2server.zip && rm -f /tmp/o2server.zip
DOCKERFILE
  then
    tail -20 "$WORK/baseimg.log" | sed 's/^/    /'
    die "无法准备打补丁基础镜像" "完整日志: $WORK/baseimg.log"
  fi
  BASE_IMG="$PATCH_IMAGE"
  ok "临时基础镜像已构建: $BASE_IMG"
fi
ok "使用基础镜像: $BASE_IMG"

# 打补丁容器：只挂载工作目录，无网络（--network none 保证纯离线）
docker rm -f o2oa-patch-runner >/dev/null 2>&1
docker run -d --name o2oa-patch-runner \
  --network none \
  -v "$ROOT/$WORK/in:/in:ro" \
  -v "$ROOT/$WORK/out:/out" \
  -v "$ROOT/patch:/src:ro" \
  "$BASE_IMG" sleep 3600 >/dev/null 2>&1 \
  || die "无法启动打补丁容器" "检查 Docker Desktop 是否运行"

ok "打补丁容器已就绪（--network none，完全离线）"

# =============================================================================
# 4. 跑补丁流水线
# =============================================================================
log "步骤 4/8：执行补丁流水线（体检 → 重写 → 离线校验）"
hr

# 脚本需为 LF 换行
if grep -qU $'\r' patch/o2oa_rebuild_patches.sh 2>/dev/null; then
  warn "补丁脚本含 CRLF，自动转为 LF（否则容器内无法执行）"
  sed -i 's/\r$//' patch/o2oa_rebuild_patches.sh
fi

docker exec o2oa-patch-runner sh -c 'mkdir -p /work && sh /src/o2oa_rebuild_patches.sh' 2>&1 \
  | tee "$WORK/pipeline.log"

RC=${PIPESTATUS[0]}
hr

if ! grep -q "PIPELINE_OK" "$WORK/pipeline.log" 2>/dev/null; then
  err "补丁流水线未成功完成（退出码 $RC）"
  printf '\n'
  printf '%s诊断摘要（详见 .upgrade-work/out/report.txt）%s\n' "$Y" "$N"
  grep -E "\[FAIL\]|\[WARN\]|ABORT|VERIFY|Error|error:" "$WORK/pipeline.log" 2>/dev/null | head -30 | sed 's/^/    /'
  printf '\n'
  printf '%s可能的原因与对策：%s\n' "$Y" "$N"
  printf '    · ResourceFactory.internal() 方法结构变化 → 需人工重新分析 ASM 帧\n'
  printf '    · javassist API 变化 → 需调整 ConfigPatch2 / ExternalDataSourcesPatch\n'
  printf '    · O2OA 已官方支持 externalDataSources.json → 可删除对应补丁，直接跑原版\n'
  printf '\n%s你现有的补丁产物与镜像都没被动，服务仍可用。%s\n' "$G" "$N"
  printf '%s把 .upgrade-work/out/report.txt 发出来即可人工接力。%s\n' "$B" "$N"
  exit 1
fi

ok "补丁流水线成功"

# 从容器拷回产物。
# ★ Git Bash（MSYS2）会把「以 / 开头的参数」当路径自动转换：
#   `docker cp c:/out/x.jar /d/O2OA/patch/...` 会被改写为 `D:\d\O2OA\patch\...`
#   于是 docker 报 `invalid output path: directory "D:\d\O2OA\patch" does not exist`。
#   对策：MSYS_NO_PATHCONV=1 关掉转换，并显式给出容器侧绝对路径 + 宿主侧原生路径。
if command -v cygpath >/dev/null 2>&1; then
  HOST_PATCH_DIR=$(cygpath -w "$ROOT/patch")   # 例: D:\O2OA\patch
else
  HOST_PATCH_DIR="$ROOT/patch"
fi
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

dcp() {  # dcp <容器内路径> <宿主目标文件>
  docker cp "o2oa-patch-runner:$1" "$2" 2>&1
}

dcp /out/console.patched.jar "$HOST_PATCH_DIR\\console.jar.patched" >/dev/null \
  || die "拷回 console.patched.jar 失败" "检查容器是否仍在运行: docker ps -a | grep o2oa-patch-runner"
dcp /out/x_base_core_project.patched.jar "$HOST_PATCH_DIR\\x_base_core_project.patched.jar" >/dev/null \
  || die "拷回 x_base_core_project.patched.jar 失败" "检查容器是否仍在运行"
if command -v cygpath >/dev/null 2>&1; then
  dcp /out/report.txt "$(cygpath -w "$ROOT/$WORK")\\report.txt" >/dev/null 2>&1 || true
else
  dcp /out/report.txt "$ROOT/$WORK/report.txt" >/dev/null 2>&1 || true
fi

unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

# 拷回后立刻清理临时容器，避免残留占用
docker rm -f o2oa-patch-runner >/dev/null 2>&1

ok "产物已落回 patch/"
log "       console.jar.patched            md5=$(md5sum patch/console.jar.patched | cut -d' ' -f1)"
log "       x_base_core_project.patched.jar md5=$(md5sum patch/x_base_core_project.patched.jar | cut -d' ' -f1)"

# 记录源 jar 哈希（用于幂等判断）
md5sum "$WORK/in/console.orig.jar"          | cut -d' ' -f1 > patch/.patched_source_md5
md5sum "$WORK/in/x_base_core_project.orig.jar" | cut -d' ' -f1 >> patch/.patched_source_md5

# 顺便刷新原始 jar 备份（方便日后对比/回滚）
cp "$WORK/in/console.orig.jar"            patch/console.jar.orig
cp "$WORK/in/x_base_core_project.orig.jar" patch/x_base_core_project.orig.jar

docker rm -f o2oa-patch-runner >/dev/null 2>&1

# =============================================================================
# 5. 更新 Dockerfile / compose 版本号
# =============================================================================
log "步骤 5/8：同步版本号"

changed=0
# ★ 本项目不是 git 仓库，所以 auto-rollback 必须靠文件备份，不能靠 git checkout。
#   在改之前先留一份持久备份（.upgrade-backup/ 不会被下次运行清掉）。
BACKUP_DIR=".upgrade-backup"
mkdir -p "$BACKUP_DIR"
for f in Dockerfile docker-compose.yml; do
  if [ -f "$f" ] && [ ! -f "$BACKUP_DIR/$f.upgraded_to_${VER}.bak" ]; then
    cp "$f" "$BACKUP_DIR/$f.upgraded_to_${VER}.bak"
  fi
done
# 同时存一份"最近一次"的快照，供 rollback_cfg 使用
cp Dockerfile         "$WORK/Dockerfile.bak"         2>/dev/null || true
cp docker-compose.yml "$WORK/docker-compose.yml.bak" 2>/dev/null || true
ok "已备份 Dockerfile / docker-compose.yml → $BACKUP_DIR/"

if grep -qE "o2server-10\.0\.[0-9]+-linux-x64\.zip" Dockerfile 2>/dev/null; then
  if ! grep -q "o2server-${VER}-linux-x64.zip" Dockerfile; then
    sed -i "s/o2server-10\.0\.[0-9]*-linux-x64\.zip/o2server-${VER}-linux-x64.zip/g" Dockerfile
    ok "Dockerfile 安装包引用 → $VER"
    changed=1
  else
    log "       Dockerfile 已是 $VER"
  fi
else
  log "       Dockerfile 版本引用无需更改"
fi

if grep -qE "o2oa:10\.0\.[0-9]+" docker-compose.yml 2>/dev/null; then
  if ! grep -q "o2oa:${VER}\b" docker-compose.yml; then
    sed -i "s/o2oa:10\.0\.[0-9]*/o2oa:${VER}/g" docker-compose.yml
    ok "docker-compose.yml 镜像标签 → o2oa:$VER"
    changed=1
  else
    log "       docker-compose.yml 已是 o2oa:$VER"
  fi
else
  log "       docker-compose.yml 版本引用无需更改"
fi

# 残留检查：只报「仍然指向旧版本安装包/镜像」的硬引用，排除注释里的历史说明文字
RESIDUAL=$(grep -nE "(COPY|image:).*10\.0\.[0-9]+" Dockerfile docker-compose.yml 2>/dev/null \
  | grep -v "o2server-${VER}-linux-x64\.zip" | grep -v "o2oa:${VER}\b")
if [ -n "$RESIDUAL" ]; then
  warn "以下位置仍硬引用旧版本，请自查："
  printf '%s\n' "$RESIDUAL" | sed 's/^/        /'
else
  ok "无残留的旧版本硬引用"
fi

# =============================================================================
# 6. 构建镜像
# =============================================================================
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  warn "SKIP_BUILD=1 —— 跳过构建与重启"
  log "        已完成的检查：① 新版是否仍需补丁 ② 补丁能否成功重放 ③ 产物是否通过离线校验 ④ 版本号是否已同步"
  log "        未完成的检查：镜像构建、容器重建、MySQL 接管验证"
  if [ "$changed" = "1" ]; then
    warn "注意：Dockerfile/compose 的版本号已被改为 $VER，但镜像尚未重建。"
    warn "      现在若直接 docker compose up -d，会因找不到 o2oa:$VER 镜像而失败。"
    warn "      要么执行 docker compose build && docker compose up -d，"
    warn "      要么从 $BACKUP_DIR/ 还原这两个文件。"
  fi
  log "        补丁已就绪，稍后可手动执行: docker compose build && docker compose up -d"
  hr; printf '%s完成（仅打补丁，未构建、未重启）%s\n' "$G" "$N"; exit 0
fi

log "步骤 6/8：构建镜像（几分钟，请耐心）"
hr
# 注意：不能用 `if ! docker compose build | tail` —— 管道退出码来自 tail（恒为 0），
# 会吞掉构建失败。这里把输出落盘再判 docker 自己的退出码。
if ! docker compose build > "$WORK/build.log" 2>&1; then
  tail -25 "$WORK/build.log" | sed 's/^/    /'
  err "镜像构建失败"
  if [ -f "$WORK/Dockerfile.bak" ]; then
    cp "$WORK/Dockerfile.bak" Dockerfile && cp "$WORK/docker-compose.yml.bak" docker-compose.yml
    warn "已把 Dockerfile / docker-compose.yml 还原为升级前内容"
  fi
  hr; printf '%s升级中止，现有服务未受影响。完整日志: %s%s\n' "$R" "$WORK/build.log" "$N"; exit 1
fi
tail -6 "$WORK/build.log" | sed 's/^/    /'
hr
ok "镜像构建完成（日志: $WORK/build.log）"

# =============================================================================
# 7. 重建容器
# =============================================================================
# 从这里开始，失败会自动把 Dockerfile / compose 还原（镜像已建好不影响旧镜像）。
rollback_cfg() {
  if [ -f "$WORK/Dockerfile.bak" ]; then
    cp "$WORK/Dockerfile.bak" Dockerfile && cp "$WORK/docker-compose.yml.bak" docker-compose.yml
    warn "已把 Dockerfile / docker-compose.yml 还原为升级前内容"
    warn "本次构建成功的镜像仍保留在本地（$IMAGE_TAG_PREFIX:$VER），可手动使用"
  fi
}

log "步骤 7/8：重建容器"

# 备份关键配置（token.json 在具名卷里，不重建卷就不会丢）
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  if [ -f o2server/config/token.json ]; then
    cp o2server/config/token.json "o2server/config/token.json.preupgrade.bak" 2>/dev/null \
      && ok "已备份 token.json → token.json.preupgrade.bak"
  fi
fi

if ! docker compose up -d --force-recreate > "$WORK/up.log" 2>&1; then
  tail -15 "$WORK/up.log" | sed 's/^/    /'
  err "容器重建失败"
  rollback_cfg
  hr; printf '%s升级中止，现有服务未受影响。日志: %s%s\n' "$R" "$WORK/up.log" "$N"; exit 1
fi
tail -8 "$WORK/up.log" | sed 's/^/    /'
ok "容器已重建"

if [ "${KEEP_CONTAINER:-0}" = "1" ]; then
  warn "KEEP_CONTAINER=1 —— 跳过启动验证"
  hr; printf '%s完成%s\n' "$G" "$N"; exit 0
fi

# =============================================================================
# 8. 验证：MySQL 真的接管了吗
# =============================================================================
log "步骤 8/8：验证外部 MySQL 是否真的接管"
hr
log "等待 O2OA 启动（ARM64+QEMU 下约 5-8 分钟，请勿中断）…"

WAIT_MAX=900   # 15 分钟
t=0
until curl -s -o /dev/null --max-time 3 "http://localhost:9090/" 2>/dev/null; do
  sleep 15; t=$((t+15))
  if [ "$t" -ge "$WAIT_MAX" ]; then
    err "等待超时（${WAIT_MAX}s）"
    printf '    查看日志: docker logs --tail 80 %s\n' "$CONTAINER"
    exit 1
  fi
  [ $((t % 60)) -eq 0 ] && log "  已等待 ${t}s …"
done
ok "http://localhost:9090 已响应"

# 给建表留出时间。
# 密码走 MYSQL_PWD 环境变量（不走命令行，避免 "Using a password on the command
# line is insecure" 警告污染 stderr，也符合最小暴露原则）。
TBL=0
for i in $(seq 1 20); do
  TBL=$(docker exec -e MYSQL_PWD="$MYSQL_ROOT_PWD" "$MYSQL_CONTAINER" \
    mysql -uroot -N -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null | tail -1)
  TBL=${TBL:-0}
  [ "$TBL" -gt 50 ] && break
  sleep 10
done

H2=$(docker exec "$CONTAINER" sh -c "find /opt/o2server -name '*.mv.db' -o -name '*.h2.db' 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
# 注意：grep -c 无匹配时退出码为 1 且会打印 "0"，若再 `|| echo 0` 会得到两行。
# 这里统一用 wc -l 计数，规避退出码与重复输出问题。
H2TCP=$(docker exec "$CONTAINER" sh -c \
  "grep 'jdbc:h2:tcp' /opt/o2server/logs/out.log 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
H2=${H2:-0}; TBL=${TBL:-0}; H2TCP=${H2TCP:-0}

hr
printf '%s验证结果%s\n' "$B" "$N"
printf '    MySQL %s 库表数        : %s\n' "$DB_NAME" "$TBL"
printf '    容器内 H2 文件数       : %s\n' "$H2"
printf '    jdbc:h2:tcp 报错次数   : %s\n' "$H2TCP"
printf '    HTTP 9090              : %s\n' "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:9090/ 2>/dev/null)"
hr

PASS=1
# 数值安全：非纯数字一律归 0，避免 [ x -lt 100 ] 报 "integer expression expected"
case "$TBL" in ''|*[!0-9]*) TBL=0 ;; esac
case "$H2" in ''|*[!0-9]*) H2=0 ;; esac
case "$H2TCP" in ''|*[!0-9]*) H2TCP=0 ;; esac
if [ "$TBL" -lt 100 ]; then err "MySQL 表数偏低（$TBL < 100），外部数据源可能没生效"; PASS=0; else ok "MySQL 已接管（$TBL 张表）"; fi
if [ "$H2" != "0" ]; then err "检测到 H2 文件 $H2 个，存在回退"; PASS=0; else ok "无 H2 文件，未回退内置库"; fi
if [ "$H2TCP" != "0" ]; then warn "有 $H2TCP 次 h2:tcp 报错（升级后首启可能偶发，观察即可）"; else ok "无 h2:tcp 报错"; fi

# =============================================================================
# 9. AI 智能体升级后自愈（独立于 MySQL 验证；不阻断主流程）
#    O2OA 升级重建容器后：① 容器→网关 18790 防火墙规则会丢（Docker 重启）
#    ② O2OA AI 配置可能被重置。reassert 脚本会重放 netlock、把配置重新指向
#    本地网关、并端到端冒烟，确保「刚刚配好的 AI 智能体」仍然可用。
# =============================================================================
log "步骤 9/8（附加）：AI 智能体升级后自愈"
hr
if [ -f "$ROOT/reassert_ai_after_upgrade.sh" ]; then
  bash "$ROOT/reassert_ai_after_upgrade.sh" 2>&1 | tee "$WORK/ai_reassert.log" || \
    warn "AI 自愈脚本返回非零（详见 $WORK/ai_reassert.log），但主升级已完成"
else
  warn "未找到 reassert_ai_after_upgrade.sh，跳过 AI 自愈"
  warn "请手动运行: bash reassert_ai_after_upgrade.sh"
fi
hr

if [ "$PASS" = "1" ]; then
  printf '%s  ✓ 升级完成：O2OA %s 已运行在外部 MySQL 上%s\n' "$G" "$VER" "$N"
  printf '\n  · 登录: http://localhost:9090  (xadmin / 原密码保持不变)\n'
  printf '  · 管理员工具: docker exec %s /opt/o2server/admin-tools/o2admin.sh token\n' "$CONTAINER"
  printf '  · 本次升级已记录: .o2oa_upgrade_history\n'
else
  printf '%s  ! 升级完成但验证未全过，请按上面的 ✗ 项排查%s\n' "$Y" "$N"
  printf '    常见处理：\n'
  printf '      - 表数偏低 → 稍等 2 分钟再看，或 docker logs %s | grep -i openjpa\n' "$CONTAINER"
  printf '      - 有 H2 文件 → 补丁未生效，检查 report.txt 与 Dockerfile 的 COPY 行\n'
  printf '      - 想退回旧版本 → 见 UPGRADE.md「回滚」一节（本项目无 git，用文件备份还原）\n'
fi
hr
printf '  完整报告: %s/report.txt\n' "$WORK"
printf '  源 jar 备份: patch/*.orig*\n'
printf '  配置备份:  %s/\n' "$BACKUP_DIR"
printf '  升级指南:  UPGRADE.md\n'
hr
hr

[ "$PASS" = "1" ] || exit 2
