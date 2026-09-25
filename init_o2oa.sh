#!/bin/bash
# 通过 O2OA 官方 init REST API 把系统强制初始化到外部 MySQL（不使用内置 H2）
# 用法: bash init_o2oa.sh  [可选环境变量: O2OA_PORT O2OA_ADMIN_PASSWORD O2OA_DB_*]
set -euo pipefail

PORT="${O2OA_PORT:-9090}"
BASE="http://localhost:${PORT}/jaxrs"
ADMIN_PWD="${O2OA_ADMIN_PASSWORD:-o2oaAdmin@2026}"

# 外部库连接信息（须与 docker-compose.yml / initdb/init.sql 一致）
DB_HOST="${O2OA_DB_HOST:-mysql}"
DB_PORT="${O2OA_DB_PORT:-3306}"
DB_NAME="${O2OA_DB_NAME:-X}"
DB_USER="${O2OA_DB_USER:-o2oa}"
DB_PWD="${O2OA_DB_PASSWORD:-o2oa_pwd}"

echo "==> 等待 O2OA init API 就绪 (http://localhost:${PORT}/jaxrs/externaldatasources/check) ..."
for i in $(seq 1 90); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 "${BASE}/externaldatasources/check" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then echo "    init API 已就绪"; break; fi
  if [ "$i" = "90" ]; then echo "!! init API 未能就绪，请确认 O2OA 已启动"; exit 1; fi
  sleep 5
done

# 确保没有残留的 enable=true 配置挡住 set 的护栏
echo "==> 清理容器内可能残留的 externalDataSources.json（避免“已配置”护栏）..."
docker exec o2oa-server rm -f /opt/o2server/config/externalDataSources.json || true

echo "==> [1/3] 设置管理员密码 ..."
curl -sS -X POST "${BASE}/secret/set" \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"${ADMIN_PWD}\"}"
echo

echo "==> [2/3] 选定外部数据源 (MySQL) ..."
SET_BODY=$(cat <<JSON
{
  "externalDataSources": {
    "enable": true,
    "url": "jdbc:mysql://${DB_HOST}:${DB_PORT}/${DB_NAME}?autoReconnect=true&allowPublicKeyRetrieval=true&useSSL=false&useUnicode=true&characterEncoding=UTF-8&useLegacyDatetimeCode=false&serverTimezone=GMT%2B8",
    "username": "${DB_USER}",
    "password": "${DB_PWD}",
    "driverClassName": "",
    "dictionary": "",
    "maxTotal": 100.0,
    "maxIdle": 0.0,
    "statEnable": true,
    "statFilter": "mergeStat",
    "includes": [],
    "excludes": [],
    "logLevel": "ERROR",
    "transactionIsolation": "read-committed",
    "testConnectionOnCheckin": false,
    "testConnectionOnCheckout": false,
    "maxIdleTime": 300.0,
    "autoCommit": false,
    "schema": "",
    "logStatEnable": false,
    "logStatInterval": 180.0,
    "slowSqlEnable": true,
    "slowSqlThreshold": 3000.0
  }
}
JSON
)
curl -sS -X POST "${BASE}/externaldatasources/set" \
  -H "Content-Type: application/json" \
  -d "${SET_BODY}"
echo

echo "==> [3/3] 执行初始化（会在 MySQL 的 ${DB_NAME} 库建表，耗时数分钟）..."
curl -sS -X GET "${BASE}/server/execute"
echo

echo "==> 轮询初始化状态 ..."
for i in $(seq 1 120); do
  resp=$(curl -sS --max-time 10 "${BASE}/server/execute/status" 2>/dev/null || echo '{}')
  st=$(echo "$resp" | grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:"\([^"]*\)".*/\1/')
  echo "    [$(date +%H:%M:%S)] status=${st:-unknown}"
  if [ "$st" = "success" ]; then echo "==> 初始化成功，O2OA 已使用外部 MySQL（库 ${DB_NAME}）"; break; fi
  if [ "$st" = "failure" ]; then echo "!! 初始化失败，请查看 O2OA 日志: docker compose logs o2oa"; echo "$resp"; exit 2; fi
  sleep 10
done

echo "==> 验证 MySQL 中 ${DB_NAME} 库表数量 ..."
docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='${DB_NAME}';" 2>&1 || true
echo "==> 完成。Web 访问: http://localhost:${PORT}   管理员 xadmin 密码: ${ADMIN_PWD}"
