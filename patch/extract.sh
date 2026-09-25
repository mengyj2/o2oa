#!/bin/bash
JP=/opt/o2server/jvm/linux_java11/bin
cd /tmp && rm -rf cj4 && mkdir -p cj4 && cd cj4
unzip -o -q /opt/o2server/console.jar 'com/x/server/console/ResourceFactory.class'
$JP/javap -p -c com/x/server/console/ResourceFactory.class > rf.txt
for m in 'internalDriudC3p0()' 'internalDriudC3p0_original()' 'internal()'; do
  s=$(grep -n "$m" rf.txt | head -1 | cut -d: -f1)
  e=$(awk -v start="$s" 'NR>start && /^[[:space:]]+(private|public|protected)/ && /\(/ {print NR; exit}' rf.txt)
  echo "===== $m : lines $s-$e ====="
  sed -n "${s},${e}p" rf.txt | grep -nE 'invokespecial|invokestatic|invokevirtual|new |Resource|driver_h2|driver_mysql|getUrl|getJdbcUrl|getUsername|getUser|getPassword|getMaxTotal|getMaxActive|getMaxIdle|setJdbcUrl|setDriverClass|setUser|setPassword|setMaxActive|setMaxIdle|dataServers|names|DruidDataSource|externalDataSources|getEnable|enable|jdbc:'
done
