#!/bin/sh
# 在 o2oa-server 容器内执行：编译补丁、ASM 注入、离线安全验证。
# 不修改运行中的 jar（产物写入 /tmp/sh/x_base_core_project.work.jar）。
set -u
D=/opt/o2server
SRC=/tmp/sh/script_harden
OUT=/tmp/sh/out
mkdir -p "$OUT"

ASM=$D/commons/ext_java11/asm-9.7.jar
GRAAL=$D/commons/module_java11/graal-sdk-22.3.4.jar
JAVAC=$D/jvm/linux_java11/bin/javac
JAVA=$D/jvm/linux_java11/bin/java
JAR=$D/jvm/linux_java11/bin/jar
JAVAP=$D/jvm/linux_java11/bin/javap

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

echo "=== [2] backup live jar -> work copy ==="
cp "$D/store/jars/x_base_core_project.jar" /tmp/sh/x_base_core_project.work.jar
echo "work jar bytes=$(stat -c%s /tmp/sh/x_base_core_project.work.jar)"

echo "=== [3] run ASM transformer (patch eval + allowClass) ==="
$JAVA -cp "$OUT:$ASM" GraalvmScriptingFactoryHarden /tmp/sh/x_base_core_project.work.jar 2>&1
[ $? -ne 0 ] && { echo "PATCH_FAIL"; exit 1; }

echo "=== [4] inject ScriptHostAccessPolicy.class into jar ==="
( cd "$OUT" && $JAR uf /tmp/sh/x_base_core_project.work.jar com/x/base/core/project/scripting/ScriptHostAccessPolicy.class )
echo "POLICY_INJECTED"

echo "=== [5] read-back: eval must now call ScriptHostAccessPolicy.hardenedHostAccess ==="
$JAVAP -p -c -classpath /tmp/sh/x_base_core_project.work.jar com.x.base.core.project.scripting.GraalvmScriptingFactory 2>/dev/null \
  | grep -nE "ScriptHostAccessPolicy|allowHostAccess" | head
echo "--- allowClass prelude ---"
$JAVAP -p -c -classpath /tmp/sh/x_base_core_project.work.jar com.x.base.core.project.scripting.GraalvmScriptingFactory 2>/dev/null \
  | awk '/private static boolean allowClass/{f=1} f{print} f&&/ireturn/{c++; if(c>1)exit}' | head -40

echo "=== [6] JVM offline verify (-Xverify:all, 复刻 O2OA 的 GraalVM 模块参数) ==="
$JAVA -XX:+UnlockExperimentalVMOptions -XX:+EnableJVMCI \
  --module-path=$D/commons/module_java11 \
  --upgrade-module-path=$D/commons/module_java11/compiler.jar:$D/commons/module_java11/compiler-management.jar \
  -Xverify:all -cp "$OUT:$CP:/tmp/sh/x_base_core_project.work.jar" VerifyScriptHarden 2>&1
rc=$?
echo "VERIFY_RC=$rc"
exit $rc
