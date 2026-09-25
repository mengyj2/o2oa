#!/usr/bin/env bash
# 驱动 O2OA init 恢复流程(第三轮: 双补丁 console.jar + x_base_core 均已就位)。
# 关键: 先清 token 密码 + 删 H2, 重启后触发 init 模式, 再驱动 server/execute 把表建进 MySQL。
set +e
REST=http://localhost:9090/jaxrs
MYSQL_TBL() { docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='X';" 2>/dev/null | tail -1; }
H2_FILE() { docker exec o2oa-server test -f /opt/o2server/local/repository/data/X.mv.db && echo YES || echo NO; }
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== 0) 清 token 密码 + 删 H2, 然后重启容器(加载补丁 console.jar) ==="
docker exec o2oa-server sed -i 's/"password": "(ENCRYPT:[^"]*)",/"password": "",/' /opt/o2server/config/token.json
docker exec o2oa-server rm -f /opt/o2server/local/repository/data/X.mv.db /opt/o2server/local/repository/data/h2.version
docker restart o2oa-server

log "=== 1) 等待 init 服务可用 (GET /jaxrs/externaldatasources/list == 200) ==="
READY=0
for i in $(seq 1 80); do
  CODE=$(docker exec o2oa-server curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:9090/jaxrs/externaldatasources/list 2>/dev/null)
  if [ "$CODE" = "200" ]; then READY=1; log "init 服务就绪 (attempt $i, code=$CODE)"; break; fi
  sleep 10
done
[ "$READY" = "0" ] && { log "ERROR: init 服务 13+ 分钟仍未就绪"; exit 2; }

log "=== 2) 注入 externalDataSources 配置 (POST /externaldatasources/set) ==="
docker exec -i o2oa-server bash -c 'cat > /tmp/setbody.json' <<'JSON'
{"externalDataSources":[{"enable":true,"url":"jdbc:mysql://mysql:3306/X?autoReconnect=true&allowPublicKeyRetrieval=true&useSSL=false&useUnicode=true&characterEncoding=UTF-8&useLegacyDatetimeCode=false&serverTimezone=GMT%2B8","username":"o2oa","password":"o2oa_pwd","driverClassName":"com.mysql.cj.jdbc.Driver","dictionary":"","maxTotal":100.0,"maxIdle":0.0,"statEnable":true,"statFilter":"mergeStat","includes":[],"excludes":[],"logLevel":"ERROR","transactionIsolation":"read-committed","testConnectionOnCheckin":false,"testConnectionOnCheckout":false,"maxIdleTime":300.0,"autoCommit":false,"schema":"","logStatEnable":false,"logStatInterval":180.0,"slowSqlEnable":true,"slowSqlThreshold":3000.0}]}
JSON
docker exec o2oa-server curl -s -X POST -H "Content-Type: application/json" --data @/tmp/setbody.json $REST/externaldatasources/set; echo

log "=== 3) 设置管理员密钥 (POST /secret/set) ==="
docker exec -i o2oa-server bash -c 'cat > /tmp/secretbody.json' <<'JSON'
{"secret":"o2oaadmin2026"}
JSON
docker exec o2oa-server curl -s -X POST -H "Content-Type: application/json" --data @/tmp/secretbody.json $REST/secret/set; echo

log "=== 4) 触发恢复 (GET /server/execute) ==="
docker exec o2oa-server curl -s -X GET --max-time 30 $REST/server/execute; echo

log "=== 5) 轮询 MySQL 表数 (目标 >0 且 H2 文件不生成) ==="
for i in $(seq 1 80); do
  TBL=$(MYSQL_TBL); H2=$(H2_FILE)
  log "MySQL_X_tables=$TBL  H2_file=$H2"
  if [ -n "$TBL" ] && [ "$TBL" -gt 0 ] && [ "$H2" = "NO" ]; then
    log ">>> SUCCESS: 外部 MySQL 已接管存储, 建表 $TBL 张, 且无 H2 回退"; break
  fi
  sleep 15
done
log "=== 最终结果: MySQL_X_tables=$(MYSQL_TBL)  H2_file=$(H2_FILE) ==="
