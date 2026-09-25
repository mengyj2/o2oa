#!/usr/bin/env bash
# =============================================================================
# tools/build_o2server_from_source.sh —— 路线B「真源码编译 + 硬化织入」全流程
#
# 在官方 10.0.2-ce 源码 fork（本仓）上，从源码全量编译 55 个 Maven 模块，
# 再对【源码构建】的 x_base_core_project.jar / console.jar 重放三层补丁
# （数据源①② + 脚本沙箱收敛 + console JNDI③），经 -Xverify:all 离线校验后，
# 产出 patch/x_base_core_project.patched.jar 与 patch/console.patched.jar
# 供 Dockerfile COPY 烤入镜像。
#
# 用法:  bash tools/build_o2server_from_source.sh
#
# 前提（2026-09-25 实测环境）:
#   - JDK:  C:\tools\jdk11\jdk-11.0.32.1+1（Temurin 11 x64，清华镜像下载；
#           ARM64 Windows 无原生 JDK11，x64 模拟可跑）
#   - Maven: C:\tools\maven\apache-maven-3.9.9（华为云镜像下载）
#   - ~/.m2/settings.xml: mirrorOf=* → https://maven.aliyun.com/repository/public
#           （GitHub/Apache 国际链路慢，依赖必须走国内镜像）
#   - docker 镜像 o2oa:10.0.2（硬化流水线执行环境：内含 JDK/javassist/ASM/GraalVM）
#   - Git Bash 注意：docker run 挂载须 MSYS_NO_PATHCONV=1，否则 /src 被转义成宿主路径
#
# 产物落位: patch/x_base_core_project.patched.jar、patch/console.patched.jar
#           （Dockerfile COPY 的就是这两个；console.patched.jar 需手动更名
#            为 console.jar.patched 与既有 Dockerfile 对齐）
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
O2SERVER="$REPO/o2server"
PATCH="$REPO/patch"
STAGE_IN="${TMPDIR:-/c/temp}/o2oa_srcbuild/in"
STAGE_OUT="${TMPDIR:-/c/temp}/o2oa_srcbuild/out"

export JAVA_HOME="/c/tools/jdk11/jdk-11.0.32.1+1"
export PATH="$JAVA_HOME/bin:/c/tools/maven/apache-maven-3.9.9/bin:$PATH"
export MAVEN_OPTS="-Xmx6g -Dfile.encoding=UTF-8"

echo "[1/4] Maven 全量编译（55 模块，依赖走阿里云，跳过测试）..."
cd "$O2SERVER"
mvn -B -ntp -T 1C package -DskipTests -Dmaven.test.skip=true \
    -Dmaven.repo.local=C:/m2repo
# 注: 若遇 "Could not acquire lock(s)"（Windows 并行写本地仓锁竞争），
#     直接重跑即可——依赖已入本地仓后锁竞争自然消失（2026-09-25 实测）。

echo "[2/4] 暂存源码构建 jar ..."
rm -rf "$STAGE_IN" "$STAGE_OUT"; mkdir -p "$STAGE_IN" "$STAGE_OUT"
cp "$O2SERVER/x_base_core_project/target/x_base_core_project.jar" \
   "$STAGE_IN/x_base_core_project.orig.jar"
cp "$O2SERVER/x_console/target/x_console.jar" "$STAGE_IN/console.orig.jar"

echo "[3/4] 容器内硬化织入 + 离线校验（-Xverify:all）..."
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint bash \
  -v "D:/o2oaccia/patch:/src" \
  -v "$(cygpath -w "$STAGE_IN" | sed 's|\\|/|g'):/in" \
  -v "$(cygpath -w "$STAGE_OUT" | sed 's|\\|/|g'):/out" \
  o2oa:10.0.2 /src/o2oa_rebuild_patches.sh

echo "[4/4] 产物落位 ..."
cp "$STAGE_OUT/x_base_core_project.patched.jar" "$PATCH/"
cp "$STAGE_OUT/console.patched.jar" "$PATCH/console.jar.patched"
echo "完成: patch/x_base_core_project.patched.jar + patch/console.jar.patched"
echo "下一步: docker compose build o2oa && docker compose up -d o2oa && bash o2oa_netlock.sh"
