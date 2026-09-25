#!/usr/bin/env bash
# 驱动 O2OA init 恢复流程，验证外部 MySQL 是否真正接管存储。
set +e
JAR_OK=50606550cd0c21383a7f6dfc3e64da9f
REST=http://localhost:9090/jaxrs
MYSQL_TBL() { docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='X';" 2>/dev/null | tail -1; }
H2_EXISTS() { docker exec o2oa-server test -f /opt/o2server/local/repository/data/X.mv.db && echo YES || echo NO; }
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== 0) 重启容器(加载双补丁 jar, 进入 init 模式) ==="
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

log "=== 5) 轮询 MySQL 表数 & H2 是否回退 ==="
for i in $(seq 1 60); do
  TBL=$(MYSQL_TBL); H2=$(H2_EXISTS)
  log "MySQL_X_tables=$TBL  H2_recreated=$H2"
  if [ -n "$TBL" ] && [ "$TBL" -gt 0 ] && [ "$H2" = "NO" ]; then
    log "SUCCESS: 外部 MySQL 已接管存储, 且未回退 H2"; break
  fi
  sleep 15
done
log "=== 最终结果: MySQL_X_tables=$(MYSQL_TBL)  H2_recreated=$(H2_EXISTS) ==="
