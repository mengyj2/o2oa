#!/bin/bash
JP=/opt/o2server/jvm/linux_java11/bin
CORE=/opt/o2server/store/jars/x_base_core_project.jar
cd /tmp/diagx || exit 1
CP="/opt/o2server/console.jar:$CORE"
for d in /opt/o2server/store/jars/*.jar /opt/o2server/commons/ext_java11/*.jar /opt/o2server/commons/*.jar; do CP="$CP:$d"; done
$JP/javac -cp "$CP" -d /tmp/diagx DiagProps.java 2>&1 | head -20
cd /opt/o2server
$JP/java -cp "/tmp/diagx:$CP" DiagProps 2>&1 | head -60
