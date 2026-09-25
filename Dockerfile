# O2OA 10.0.2 自建镜像（基于本地 linux-x64 安装包，离线可控）
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    O2OA_HOME=/opt/o2server

# 安装运行所需的系统库（字体/AWT/X11/Hadoop native/TLS 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    unzip \
    ca-certificates \
    curl \
    procps \
    gettext-base \
    tzdata \
    fontconfig fonts-dejavu-core \
    libxext6 libxrender1 libxtst6 libxi6 libgconf-2-4 \
    libnss3 libasound2 libsnappy1v5 libssl3 \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# 把本地安装包解压到 /opt/o2server（zip 顶层目录即为 o2server/）
COPY o2server-10.0.2-linux-x64.zip /tmp/o2server.zip
RUN cd /opt \
    && unzip -q /tmp/o2server.zip \
    && rm -f /tmp/o2server.zip \
    && chmod +x /opt/o2server/*.sh 2>/dev/null || true

# 启动入口与数据源模板
COPY entrypoint.sh ${O2OA_HOME}/entrypoint.sh
COPY externalDataSources.json.tmpl ${O2OA_HOME}/externalDataSources.json.tmpl
RUN chmod +x ${O2OA_HOME}/entrypoint.sh

# 【关键补丁】x_base_core_project.jar 由 patch/o2oa_rebuild_patches.sh 流水线生成（patch/ 挂载进容器 /src），
# ★ 2026-09-25 路线B起：输入 jar 为【官方 10.0.2-ce 源码 mvn 全量编译产物】（不再取自官方 zip），
#   全流程复现见 tools/build_o2server_from_source.sh。携带两层加固：
#   ① 数据源补丁：Config.externalDataSources() / ExternalDataSources.enable() 真正读 JSON（10.0.2 体检判定为 no-op，
#      原样透传；新版若又硬编码则自动重打）。Javassist 实现见 patch/ConfigPatch2.java / ExternalDataSourcesPatch.java。
#   ② 脚本沙箱 HostAccess 收敛：GraalvmScriptingFactory.eval 的 allowHostAccess(HostAccess.ALL)
#      → ScriptHostAccessPolicy.hardenedHostAccess()（逐项 denyAccess 危险类，掐断 Class.forName().getMethod().invoke()
#      反射越权链）；allowClass 前置 isDangerousClass 类名层纵深防御。ASM 改写 + 离线安全验证见 patch/script_harden/。
# 两步均带离线 JVM 校验（-Xverify:all + GraalVM 模块参数），未通过绝不产出。升级可重放（upgrade_o2oa.sh）。
COPY patch/x_base_core_project.patched.jar ${O2OA_HOME}/store/jars/x_base_core_project.jar

# 【关键补丁 3】console.jar 的 com.x.server.console.ResourceFactory.internal() 会把 JNDI 名
# "jdbc/<letter>" 死绑到内置 H2 TCP（永远连不上，导致实体层全部报错）。外部数据源模式下 O2OA 实际
# 查找的 JNDI 名是 "jdbc/s001"（由 ExternalDataSources.names() 生成），原方法从不绑它，
# 于是 OpenJPA 回退到 persistence.xml 并报 "A JDBC driver or data source class name must be specified"。
# 此处用 ASM 重写的 console.jar 覆盖：internal() 改调新增的 internalDriudC3p0_external()，
# 它按 config/externalDataSources.json 构建 MySQL DruidDataSource 并绑定 jdbc/sNNN + jdbc/B..Z。
# 重打包/校验方法见 patch/ResourceFactoryAsmPatch.java + patch/patch3_verify.sh（离线 JVM 校验后再注入）。
COPY patch/console.jar.patched ${O2OA_HOME}/console.jar

# 【本地管理员工具】纯离线的账号运维脚本（不改动 O2OA 任何 jar，仅用其自带类生成 token / 调 REST）。
#   token            生成 20 分钟有效的 cipher token（管理员 API 用）
#   login  <user> <pwd>        测试登录
#   mkperson <name> <pwd>      创建普通人员（管理员 API）
#   setpwd <flag> <newpwd>     修改某人密码
# 说明：xadmin 是 token.json 里的"虚拟初始管理员"（不落库），密码明文在
#   config/token.json 的 password 字段（(ENCRYPT:...) 形式，用 Crypto.plainText 解出）。
#   改 xadmin 密码只能改 token.json，接口层明确拒绝。详见 patch/admin/README.md
COPY patch/admin/o2admin.sh ${O2OA_HOME}/admin-tools/o2admin.sh
COPY patch/admin/MkToken.java ${O2OA_HOME}/admin-tools/MkToken.java
RUN chmod +x ${O2OA_HOME}/admin-tools/o2admin.sh

# 【AI 推理补丁工具】供下方「构建期内联烤入」与 reassert 脚本复用
COPY patch/ai/ ${O2OA_HOME}/patch/ai/

# 【离线加固 · 云平台接口封锁】patch_collect_lock.sh 在每次启动时（由 entrypoint 调用）
# 用 javassist 给 x_program_center 的 CollectJaxrsFilter 注入 doFilter()，
# 使 /jaxrs/collect/* 全部返回 403 —— 物理切断「注册/登录云账号、找回密码、发短信验证码」。
# 原因：这 21 个接口里只有 login/validate 有 enable 门控，regist/resetpassword/code
# 没有门控，联网即可真的注册云账号，且注册成功会自动 setEnable(true) 并上报人员手机号。
# 影响面：仅 collect 模块；market/apppack 走各自 filter，不受影响。
# 幂等，且 O2OA 升级重部署 war 后会自动重新打上。
COPY patch_collect_lock.sh ${O2OA_HOME}/patch_collect_lock.sh
RUN chmod +x ${O2OA_HOME}/patch_collect_lock.sh \
    && bash ${O2OA_HOME}/patch_collect_lock.sh --war \
    && bash ${O2OA_HOME}/patch_collect_lock.sh --verify

# 【AI 推理补丁 · 构建期内联烤入】把 reasoning_effort 修复写进 x_ai_assemble_control.war，
# 使「本地模型直连兜底路径」连容器重建（force-recreate）都扛得住，无需运行期补丁。
# 说明：O2OA 升级走云端网关（o2Chat → 本地适配网关）时本补丁并非必需；它是为
# 禁用网关、回退到 model.getCompletionUrl() 直连路径时的兜底。整段用 RUN <<'AISCRIPT'
# 原生 heredoc 包裹，set +e 确保任一环节失败（python3 缺失 / 新版 class 结构已变）
# 仅告警并 exit 0，绝不阻断镜像构建；真要兜底还有 reassert_ai_after_upgrade.sh。
RUN <<'AISCRIPT'
set +e
if ! command -v python3 >/dev/null 2>&1; then echo "[AI] 无 python3，跳过 war 补丁"; exit 0; fi
if [ ! -f /opt/o2server/store/x_ai_assemble_control.war ]; then echo "[AI] 无 AI war，跳过"; exit 0; fi
if [ ! -f /opt/o2server/patch/ai/PatchActionChat.py ]; then echo "[AI] 无 patcher，跳过"; exit 0; fi
rm -rf /tmp/aiwar && mkdir -p /tmp/aiwar && cd /tmp/aiwar
unzip -o -q /opt/o2server/store/x_ai_assemble_control.war
python3 /opt/o2server/patch/ai/PatchActionChat.py \
  WEB-INF/classes/com/x/ai/assemble/control/jaxrs/chat/ActionChat.class \
  /tmp/ActionChat.patched.class
if [ $? -ne 0 ]; then echo "[AI] 补丁生成失败（新版 class 结构可能已变），跳过烤入"; exit 0; fi
cp /tmp/ActionChat.patched.class WEB-INF/classes/com/x/ai/assemble/control/jaxrs/chat/ActionChat.class
python3 - <<'PY'
import zipfile, os
war='/opt/o2server/store/x_ai_assemble_control.war'
cls='WEB-INF/classes/com/x/ai/assemble/control/jaxrs/chat/ActionChat.class'
tmp=war+'.tmp'
with zipfile.ZipFile(war,'r') as zin, zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as zout:
    for it in zin.infolist():
        zout.writestr(it, open(cls,'rb').read() if it.filename==cls else zin.read(it.filename))
os.replace(tmp,war)
print('[AI] x_ai_assemble_control.war 已注入 reasoning 补丁')
PY
if [ $? -eq 0 ]; then echo "[AI] war reasoning 补丁已烤入镜像"; else echo "[AI] war 重打包失败，跳过"; fi
AISCRIPT

# 【前端 AI 悬浮窗补丁 · 场景上下文注入】x_component_AI/Main.js / Main.min.js 修改版：
# 发送对话时把当前页面 URL 压缩为 [场景:page?query] 前缀放进 input
# （ActionChat 协议无场景字段，input 前缀是唯一可注入点），
# 由本地网关(18790)剥离该前缀并转入 system prompt。
# 修改点搜索 "[o2-gw-patch 2026-09-19]"。
COPY patch/web/Main.js ${O2OA_HOME}/servers/webServer/x_component_AI/Main.js
COPY patch/web/Main.min.js ${O2OA_HOME}/servers/webServer/x_component_AI/Main.min.js

# 【开始菜单补丁 · 流程应用直达】桌面「开始」菜单原本只显示
#   applications.json(空) + CPT_COMPONENT(24个内置) + 门户(pcClient=true)，
#   流程应用/查询/CMS 的菜单生成代码在 Layout.js 里是注释掉的，
#   所以导入的 19 个流程应用在开始菜单里看不到。
# 修复方式：往 applications.json 写 "@url:" 条目。createApplicationMenu 对
#   path 以 "@url" 开头的条目用 openApplication -> 新窗口直跳；
#   深链 /x_desktop/index.html?app=process.Application&option={id,appId}
#   由 Layout.initData 解析成 status.apps[app]，窗口 isMax:true 直接可见。
# 文件由 tools/o2_register_process_apps.py gen 生成（应用 id 变了要重新生成）。
# ★ 2026-09-22 修复：`$Layout` 目录名是字面量（不是构建变量），必须转义为 \$Layout。
#   之前未转义 → Docker 把 $Layout 展开为空 → 文件被 COPY 到 xDesktop/applications.json（错位路径），
#   正确路径仍是 zip 里的 `[]` ⇒ 容器重建后 16 条流程应用直达「静默消失」（2026-09-22 20:30 重建事故）。
#   重建后务必验证：docker exec o2oa-server cat ".../xDesktop/\$Layout/applications.json" 应有 16 条。
COPY patch/web/applications.json "${O2OA_HOME}/servers/webServer/o2_core/o2/xDesktop/\$Layout/applications.json"

# ★ 2026-09-22 自研「企业网盘」组件 x_component_Drive（UI 层复刻，数据层复用 x_file_assemble_control）
#   目录内 $Main 为字面量子目录；源与目标路径本身均不含 $，故无需转义。
#   已迁移至代码级仓库 deploy/runtime/webroot/x_component_Drive（与运行态容器卷字节一致）。
#   配套：门户应用菜单字典中「企业网盘」的 app 由 File 切到 Drive
#        （tools/o2_dict_set_menu_app.py，改 GEN_DICT_ITEM 中 appNavis/5/children/4/app）。
COPY deploy/runtime/webroot/x_component_Drive ${O2OA_HOME}/servers/webServer/x_component_Drive

# ★ 首页入口定制（git 真源 = deploy/host/x_desktop/）构建期烤入镜像，重建不丢。
#   机制同上方 x_component_AI/Main.js：O2OA webServer 定制文件必须用 COPY 烤进镜像，
#   bind mount 单文件覆盖层对 O2OA 无效（实测线上仍返回官方版 index.html）。
#   index.html      —— 三分流版（admin/xadmin→admin.html；mengyijie→index_home.html；其余→门户）
#   index_home.html —— 管理员登录后仍进「用户门户首页入口」页面（不分流到 admin.html 后台）
#   res/config/config.json —— O2OA 桌面全局配置（系统标题/页脚/密码正则/语言等定制项）
COPY deploy/host/x_desktop/index.html ${O2OA_HOME}/servers/webServer/x_desktop/index.html
COPY deploy/host/x_desktop/index_home.html ${O2OA_HOME}/servers/webServer/x_desktop/index_home.html
COPY deploy/host/x_desktop/res/config/config.json ${O2OA_HOME}/servers/webServer/x_desktop/res/config/config.json

# 容器内统一对外端口（entrypoint 会把默认 80 改为 O2OA_WEB_PORT）
EXPOSE 9090 20010 20020 20030 20040 20050

WORKDIR ${O2OA_HOME}
ENTRYPOINT ["/opt/o2server/entrypoint.sh"]
