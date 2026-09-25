#!/bin/bash
# O2OA 容器启动入口：初始化配置 -> 端口修正 -> 前台启动
# 注意：外部数据源(MySQL)不再在此处写死 enable=true，
# 而是由 init_o2oa 脚本通过官方 init REST API 选定外部库并执行初始化，
# 否则会触发 init 接口“外部数据源已配置”的护栏，反而卡死正常初始化流程。
set -e

export MALLOC_ARENA_MAX=1
O2OA_HOME=/opt/o2server
WEB_PORT=${O2OA_WEB_PORT:-9090}

# 给外部数据源占位符提供默认值（envsubst 只认 ${VAR}，不支持 ${VAR:-default}）
export O2OA_DB_HOST=${O2OA_DB_HOST:-mysql}
export O2OA_DB_PORT=${O2OA_DB_PORT:-3306}
export O2OA_DB_NAME=${O2OA_DB_NAME:-X}
export O2OA_DB_USER=${O2OA_DB_USER:-o2oa}
export O2OA_DB_PASSWORD=${O2OA_DB_PASSWORD:-o2oa_pwd}

# 1) 首次启动：从 configSample 复制默认配置到 config（仅缺文件时补齐，不覆盖已有配置）
if [ ! -f "${O2OA_HOME}/config/node_127.0.0.1.json" ]; then
  echo "[entrypoint] 初始化 config（从 configSample）..."
  mkdir -p "${O2OA_HOME}/config"
  cp -rn "${O2OA_HOME}"/configSample/* "${O2OA_HOME}/config/" 2>/dev/null || true
fi

# 2) 把默认 80 端口改为容器统一端口（center/application/web 均为 80.0）
if [ -f "${O2OA_HOME}/config/node_127.0.0.1.json" ]; then
  # 同时覆盖「默认值 80.0」与「历史上被改成 8080.0 的旧卷」，确保无论是否复用旧配置卷都能切到 WEB_PORT
  sed -i -E "s/(\"(port|proxyPort)\": ?)80\.0/\1${WEB_PORT}.0/g; s/(\"(port|proxyPort)\": ?)8080\.0/\1${WEB_PORT}.0/g" \
    "${O2OA_HOME}/config/node_127.0.0.1.json"
fi

# 3) 外部数据源配置（关键坑位）：
#    O2OA 的初始化恢复(MissionRestore)读取的是“init 状态”，而非本配置文件；
#    server/execute 会忽略预置的 enable=true，回退到内置 H2。真正切换到 MySQL 必须由
#    初始化脚本通过官方 init REST API 的 externaldatasources/set 完成（它把选择写入 init 状态）。
#    该接口有护栏：config 已 enable=true 时会拒绝。因此这里只生成 enable=false 占位，
#    把 MySQL 切换留给 init 流程。仅当文件不存在或仍为 enable=false 时（重新）生成。
EXT="${O2OA_HOME}/config/externalDataSources.json"
if [ ! -f "${EXT}" ] || grep -q '"enable"[[:space:]]*:[[:space:]]*false' "${EXT}"; then
  echo "[entrypoint] 生成 config/externalDataSources.json（enable=false 占位，MySQL 切换交由 init REST API 完成）..."
  envsubst < "${O2OA_HOME}/externalDataSources.json.tmpl" > "${EXT}"
fi

# 4) 【离线加固】中和 config/collect.json 的外连地址
#    O2OA 的云平台/应用市场/应用打包模块（com.x.base.core.project.config.Collect）
#    里有硬编码的官方服务器域名，触发对应功能时会尝试外连：
#      appPackServerUrl = https://apppack.o2oa.net:40088
#      server           = (云平台地址)
#      appUrl           = app.o2oa.net
#    这些功能全部需要 O2OA 官方账号，本机离线自托管用不到。
#    这里在每次启动时把它们清空，从【配置层】再堵一道（不改字节码，官方支持）。
#    注意：只清空"地址"，保留 enable=false 等其余字段，避免影响 O2OA 解析。
#    该操作是幂等的：已清空则原样保留。
COLLECT="${O2OA_HOME}/config/collect.json"
if [ -f "${COLLECT}" ]; then
  if grep -qE '"appPackServerUrl"[[:space:]]*:[[:space:]]*"https?://' "${COLLECT}" \
     || grep -qE '"server"[[:space:]]*:[[:space:]]*"[^"]+"' "${COLLECT}" \
     || grep -qE '"appUrl"[[:space:]]*:[[:space:]]*"https?://' "${COLLECT}"; then
    echo "[entrypoint] 离线加固：清空 collect.json 中的云平台/应用打包外连地址..."
    cp -f "${COLLECT}" "${COLLECT}.prelock.bak" 2>/dev/null || true
    sed -i -E \
      -e 's|("appPackServerUrl"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' \
      -e 's|("appUrl"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' \
      -e 's|("server"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' \
      "${COLLECT}"
    echo "[entrypoint]   原文件已备份为 collect.json.prelock.bak"
  else
    echo "[entrypoint] collect.json 外连地址已为空，跳过"
  fi
fi

# 5) 【离线加固 · 内核级】云平台接口封锁 —— 已在【镜像构建期】完成
#    为什么不能只靠 collect.json 的 enable=false：
#      x_program_center 的 21 个 collect 接口中，只有 login/validate 有
#      `Config.collect().getEnable()` 门控；regist（注册）/ resetpassword（找回密码）/
#      code（发短信验证码）等【完全没有门控】—— 只要容器能联网，就能真的把账号
#      注册到 O2OA 云平台；且注册成功后会执行 Config.collect().setEnable(true)
#      自动打开云连接，并立即触发 CollectPerson 上报本机人员手机号。
#    加固方式：Dockerfile 构建期调用 patch_collect_lock.sh --war，
#      用 javassist 给 store/x_program_center.war 里的 CollectJaxrsFilter
#      注入 doFilter()，对 /jaxrs/collect/* 全部返回 403（物理切断）。
#      影响面：仅 collect 模块；market（应用市场）/ apppack（打包）走各自 filter，保持可用。
#    此处仅做一次状态自检（不修改），便于发现异常。war 被升级替换后，
#      重新 build 镜像即可自动补上。
COLLECTLOCK="${O2OA_HOME}/patch_collect_lock.sh"
if [ -f "${COLLECTLOCK}" ]; then
  if bash "${COLLECTLOCK}" --verify >/dev/null 2>&1; then
    echo "[entrypoint] 离线加固：云平台 collect 接口封锁 ✓ 已生效"
  else
    echo "[entrypoint]   ! 云平台 collect 接口封锁【未生效】—— 请重新 build 镜像"
  fi
fi

# 5.5) 【启动时序根治】等待 MySQL 真正就绪后再启动 O2OA
#    根因（2026-09-25 三次 randomWithWeight 复发的真相）：整机/守护进程重启时，
#    Docker 按重启策略各自拉起容器，不会重新评估 compose 的 depends_on；
#    o2oa 首次建 EntityManager 时 mysql 尚未就绪 → 组织相关模块
#    （x_organization_assemble_express 等）带着失败加载出【空内存组织缓存】，
#    且之后不重试 → 所有交互式登录 500（randomWithWeight ... count=0）。
#    修法：在启动 JVM 前用 TCP 探测 O2OA_DB_HOST:O2OA_DB_PORT，阻塞至就绪。
#    注意：探测的是【配置的数据库端口】，而非假设 mysql 容器名，幂等且无副作用。
DB_HOST="${O2OA_DB_HOST}"
DB_PORT="${O2OA_DB_PORT}"
echo "[entrypoint] 等待数据库就绪 ${DB_HOST}:${DB_PORT} ..."
DB_WAIT_OK=""
for i in $(seq 1 60); do
  if (exec 3<>"/dev/tcp/${DB_HOST}/${DB_PORT}") 2>/dev/null; then
    exec 3>&- 3<&- || true
    DB_WAIT_OK=1
    echo "[entrypoint] 数据库端口已就绪（第 ${i} 次探测）"
    break
  fi
  sleep 2
done
if [ -z "$DB_WAIT_OK" ]; then
  echo "[entrypoint] ! 等待数据库超时（120s），仍尝试启动 O2OA（历史上这会导致登录 500，请检查 mysql 容器）"
else
  # 端口通了再给 InnoDB 收尾/XA recovery 一点余量，避免"端口已监听但连接握手失败"的窗口
  sleep 3
fi

echo "[entrypoint] 启动 O2OA (web port=${WEB_PORT}) ..."
exec "${O2OA_HOME}/jvm/linux_java11/bin/java" \
  -javaagent:"${O2OA_HOME}/console.jar" \
  -server -Djava.awt.headless=true \
  -Xms${O2OA_JVM_XMS:-4g} -Xmx${O2OA_JVM_XMX:-4g} \
  -Duser.timezone=GMT+08 \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:+UnlockExperimentalVMOptions -XX:+EnableJVMCI \
  --module-path="${O2OA_HOME}/commons/module_java11" \
  --upgrade-module-path="${O2OA_HOME}/commons/module_java11/compiler.jar:${O2OA_HOME}/commons/module_java11/compiler-management.jar" \
  -jar "${O2OA_HOME}/console.jar"
