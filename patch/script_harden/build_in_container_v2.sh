#!/bin/sh
# 干净重建：以主机提供的原始 jar 为基线（不读 live jar，避免污染），
# 编译补丁 -> ASM 注入 eval/allowClass -> 注入策略类 -> javap 回读 + 离线安全验证。
# 前置：docker cp 已将 script_harden 源目录、x_base_core_project.before_harden.jar
#       分别落到容器 /tmp/sh/script_harden 与 /tmp/sh/x_base_core_project.work.jar
set -u
D=/opt/o2server
SRC=/tmp/sh/script_harden
OUT=/tmp/sh/out
BASE=/tmp/sh/x_base_core_project.work.jar   # 已知原始 jar（来自主机 before_harden.jar）
FINAL=/tmp/sh/x_base_core_project.hardened.jar

mkdir -p "$OUT"

ASM=$D/commons/ext_java11/asm-9.7.jar
GRAAL=$D/commons/module_java11/graal-sdk-22.3.4.jar
JAVAC=$D/jvm/linux_java11/bin/javac
JAVA=$D/jvm/linux_java11/bin/java
JAR=$D/jvm/linux_java11/bin/jar
JAVAP=$D/jvm/linux_java11/bin/javap

echo "=== base jar bytes=$(stat -c%s $BASE 2>/dev/null) ==="

# 运行时完整 classpath（含 graal js 引擎 / 平台类）
CP=""
for j in $(find $D/store $D/commons -name '*.jar' 2>/dev/null); do
  CP="$CP:$j"
done

echo "=== [1] compile patch sources ==="
$JAVAC -cp "$GRAAL:$ASM" -d "$OUT" \
  "$SRC/ScriptHostAccessPolicy.java" \
  "$SRC/GraalvmScriptingFactoryHarden.java" \
  "$SRC/VerifyScriptHarden.java" 2>&1
[ $? -ne 0 ] && { echo "COMPILE_FAIL"; exit 1; }
echo "COMPILE_OK"

echo "=== [3] run ASM transformer (patch eval + allowClass) ==="
$JAVA -cp "$OUT:$ASM" GraalvmScriptingFactoryHarden "$BASE" 2>&1
[ $? -ne 0 ] && { echo "PATCH_FAIL"; exit 1; }
# 此时 BASE 已被原地更新
echo "PATCHED_BASE"

echo "=== [4] inject ScriptHostAccessPolicy.class into jar ==="
( cd "$OUT" && $JAR uf "$BASE" com/x/base/core/project/scripting/ScriptHostAccessPolicy.class )
echo "POLICY_INJECTED"

echo "=== [5] read-back: eval 应调用 ScriptHostAccessPolicy.hardenedHostAccess，且无 getstatic HostAccess.ALL ==="
$JAVAP -p -c -classpath "$BASE" com.x.base.core.project.scripting.GraalvmScriptingFactory 2>/dev/null \
  > /tmp/sh/eval_disasm.txt
echo "--- eval 内的 hardening 证据 ---"
grep -nE "ScriptHostAccessPolicy.hardenedHostAccess|allowHostAccess" /tmp/sh/eval_disasm.txt | head
echo "--- eval 内是否仍残留 getstatic HostAccess.ALL（应为 0 行）---"
awk '/eval\(/{f=1} f{print} f&&/^$/{exit}' /tmp/sh/eval_disasm.txt | grep -c "HostAccess.ALL"
echo "--- allowClass 前置 isDangerousClass 证据 ---"
grep -nE "ScriptHostAccessPolicy.isDangerousClass" /tmp/sh/eval_disasm.txt | head

echo "=== [6] JVM offline verify (-Xverify:all, 复刻 O2OA 的 GraalVM 模块参数) ==="
$JAVA -XX:+UnlockExperimentalVMOptions -XX:+EnableJVMCI \
  --module-path=$D/commons/module_java11 \
  --upgrade-module-path=$D/commons/module_java11/compiler.jar:$D/commons/module_java11/compiler-management.jar \
  -Xverify:all -cp "$OUT:$CP:$BASE" VerifyScriptHarden 2>&1
rc=$?
echo "VERIFY_RC=$rc"

if [ $rc -eq 0 ]; then
  cp "$BASE" "$FINAL"
  echo "FINAL_JAR=$FINAL bytes=$(stat -c%s $FINAL)"
else
  echo "VERIFY_NOT_OK refusing to publish"
  exit $rc
fi
exit $rc
