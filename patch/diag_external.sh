#!/bin/bash
# Diagnose external datasource resolution chain inside the O2OA container.
JP=/opt/o2server/jvm/linux_java11/bin
CORE=/opt/o2server/store/jars/x_base_core_project.jar
cd /tmp/diagx || exit 1

# build a classpath with everything O2OA uses at runtime
CP="$CORE:/opt/o2server/console.jar"
for d in /opt/o2server/store/jars/*.jar /opt/o2server/commons/ext_java11/*.jar /opt/o2server/commons/*.jar; do
  CP="$CP:$d"
done

echo "===== compile ====="
$JP/javac -cp "$CP" -d /tmp/diagx DiagExternal.java 2>&1 | head -20

echo ""
echo "===== run ====="
cd /opt/o2server
$JP/java -cp "/tmp/diagx:$CP" DiagExternal 2>&1 | head -80
