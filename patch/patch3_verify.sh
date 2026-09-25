#!/bin/bash
# Stage 1: build + OFFLINE JVM verification of the patched class (no injection, no restart).
JP=/opt/o2server/jvm/linux_java11/bin
ASM=/opt/o2server/commons/ext_java11/asm-9.7.jar
CORE=/opt/o2server/store/jars/x_base_core_project.jar
cd /tmp/rfasm || exit 1

echo "== clean =="
rm -rf com *.class 2>/dev/null
mkdir -p com/x/server/console

echo "== compile patch + probe =="
$JP/javac -cp "$ASM" -d . ResourceFactoryAsmPatch.java VerifyCls.java || { echo COMPILE_FAIL; exit 1; }
echo "COMPILE_OK"

echo "== run ASM patch against PRISTINE jar =="
$JP/java -cp "$ASM:." ResourceFactoryAsmPatch /tmp/rfasm/console.orig.jar || { echo PATCH_FAIL; exit 1; }

echo "== build full O2OA classpath for verification =="
CP="/opt/o2server/console.jar:$CORE"
for d in /opt/o2server/store/jars/*.jar /opt/o2server/commons/ext_java11/*.jar /opt/o2server/commons/*.jar; do
  CP="$CP:$d"
done

echo "== offline JVM verification =="
$JP/java -Xverify:all -cp "/tmp/rfasm:$CP" VerifyCls 2>&1 | head -60
echo "VERIFY_EXIT=$?"
