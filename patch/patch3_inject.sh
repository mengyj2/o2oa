#!/bin/bash
# Stage 2: inject the (already offline-verified) patched class into console.jar.
set -e
JP=/opt/o2server/jvm/linux_java11/bin
cd /tmp/rfasm

if [ ! -f com/x/server/console/ResourceFactory.class ]; then
  echo "MISSING patched class - run patch3_verify.sh first"; exit 1
fi

echo "== backup current console.jar (if not already) =="
[ -f /opt/o2server/console.jar.bak_patch3_full ] || cp /opt/o2server/console.jar /opt/o2server/console.jar.bak_patch3_full
ls -la /opt/o2server/console.jar*

echo "== inject =="
$JP/jar uf /opt/o2server/console.jar com/x/server/console/ResourceFactory.class
echo "JAR_UPDATED"
ls -la /opt/o2server/console.jar

echo "== javap sanity =="
$JP/javap -p -classpath /opt/o2server/console.jar com.x.server.console.ResourceFactory 2>&1 | grep -iE 'internal'

echo "== extract back and re-verify the IN-JAR bytes =="
rm -rf /tmp/rfasm_verify && mkdir -p /tmp/rfasm_verify
cd /tmp/rfasm_verify
$JP/jar xf /opt/o2server/console.jar com/x/server/console/ResourceFactory.class
ls -la com/x/server/console/ResourceFactory.class
