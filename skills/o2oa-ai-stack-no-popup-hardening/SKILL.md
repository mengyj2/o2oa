---
name: o2oa-ai-stack-no-popup-hardening
description: 诊断并根治 O2OA AI 栈问题。★2026-09-30 起 AI 栈已容器化（ai-gateway/ai-ocr/ai-plan），宿主看门狗作废——本技能优先覆盖「容器化割接 + 四个静默失效根因（硬编码 BASE_DIR、embed_models 漂移、kv 缓存陈旧、token 空串放行）」，并保留看门狗时代的弹窗/9090 卡死排查（历史/回滚用）。当用户说「AI 栈弹窗」「gateway 一直重启」「9090 卡死」「看门狗循环」「割接容器」「capabilities 显示 127.0.0.1」「embedding 失效」时加载。
agent_created: true
category: diagnostics

---

# O2OA AI 栈看门狗弹窗 / 9090 卡死 根治

## ★★★ 2026-09-30 重大变更：AI 栈已容器化，看门狗形态【作废】

**AI 栈已割接到 docker-compose 三容器，宿主看门狗不再使用。**
若问题出现在容器化之后，先看本节；本文档下半部分的看门狗内容仅供**历史排查/回滚**参考。

| 组件 | 容器 | 地址 |
|---|---|---|
| 网关 | `o2oa-ai-gateway` | 172.22.0.60:18790（宿主 `0.0.0.0:18790`） |
| OCR | `o2oa-ai-ocr` | 172.22.0.61:8091 |
| 计划 | `o2oa-ai-plan` | 172.22.0.62:18792 |
| embed | —（已取消 8089） | 改走宿主 LM Studio `host.docker.internal:1234` |

### 割接必须处理的四件事（漏一个就"静默失效"）
1. **先 kill 看门狗本体**（`watchdog.pid` 记录者），再 kill 组件——否则看门狗 30s 内自愈补回。
2. **禁登录自启** `%APPDATA%\...\Startup\O2OA_AI_stack_autostart.vbs`（登录会重拉看门狗抢端口）。
3. **清端口双绑**：`netstat -ano | grep :18790` 若两个 PID（一个 docker 代理、一个旧 python）→ 清后者。
4. **验 `/gateway/capabilities`**：`base` 必须是 `host.docker.internal`/`ai-ocr`，**不是 `127.0.0.1`**。

### ★★ 容器化头号杀手：硬编码宿主路径
`o2_agent_gateway.py` 曾写 `BASE_DIR = Path(r"D:\O2OA\gateway")` → 容器内路径不存在 →
`CFG_PATH.exists()=False` → **静默回退 `DEFAULT_CFG`**（`127.0.0.1:1234` 容器内不通）→ LLM/embed 全断，
且 `/app/gateway/config.json` 从未被加载。已改为 `Path(__file__).resolve().parent`（+ `O2OA_GW_BASE` 覆盖 + 宿主兜底）。
**凡是容器化后"配置改了不起作用"，先查这类硬编码绝对路径。**

### 另两个静默失效点
- `embed_models` 必须与 `embed_base` 成对改：走 LM Studio 时模型名要换成
  `text-embedding-qwen3-embedding-0.6b` / `text-embedding-bge-m3` 等真实名（**没有 `qwen3-embed`**）。
- `emb_model()` 的 kv 缓存须校验是否还在白名单内，否则换后端后仍用旧名 →
  生成器 `tools/gen_gateway_container_config.py` 已加规则 + 网关已加白名单校验。

### ★★★ 容器化后「服务全挂」假警报 + MCP 侧真故障（2026-09-30 实测）

**症状**：Docker Desktop 里容器全绿，但 O2OA 助手回答
「服务健康检测：O2OA 主服务(9090) DOWN / AI 网关(18790) DOWN / 向量(8089) DOWN / OCR(8091) DOWN」，
同一轮里却又能"在组织架构中确认存在某人"——只是"员工档案查询连续 3 次调用失败，报错 Connection refused"。

**根因 A（假警报，4/4 全错）**：`gateway/o2oa_tools_mcp.py::o2_service_health` 硬编码
探测 `127.0.0.1:{9090,18790,8089,8091}` 的**根路径 `/`**。本 MCP 子进程由 `ai-gateway`
容器拉起 ⇒ 容器内 `127.0.0.1` 就是网关自己：
- `9090`、`8091` 容器内无监听（O2OA 在 `o2oa-server`、OCR 在 `ai-ocr`）→ Connection refused
- `8089` 早已下线（embed 改走宿主 LM Studio 1234）→ 恒 DOWN（探针过时）
- `18790` 虽在监听，但根路径无路由返回 **404**；生成回答期间单 worker 忙还会**超时**
⇒ 与"容器有没有在跑"完全无关。

**根因 B（真故障，且被 A 掩盖）**：`gateway/config.container.json` 里
`mcp_servers[o2oa].env.O2OA_BASE = http://127.0.0.1:9090`，
而 `mcp_client.py:96` 是 `full_env = dict(os.environ); full_env.update(env)` —— **配置里的 env 覆盖容器级 env**，
于是 compose 里正确的 `O2OA_BASE=http://o2oa-server:9090` 被顶掉。
⇒ `o2oa_tools_mcp.py` 的**全部** REST 工具（人员/HR 档案/组织/待办/数据字典/错误日志）Connection refused；
而网关**内置**工具走 `CFG.o2oa_base`（正确）⇒ 出现「组织架构查得到、员工档案查不到」的割裂现象，
极易被误判成"权限问题 / HR 服务挂机"。

**修法（已落地）**：
1. `o2_service_health` 重写：地址**一律取 config.json**（`o2oa_base` / `ocr_base` / `bionic_base` / `listen_port`），
   探活改为**纯 TCP 连通性**（内核 backlog 应答，不受单 worker 阻塞影响），删掉已下线的 8089/8092，输出注明"TCP OK ≠ 接口可用"。
2. `_cfg_local()` 按 `O2OA_GW_CONFIG` → 本目录 → `../gateway/` → `/app/gateway` 顺序找 config（只认 `__file__` 同目录会把拷出去的副本读成"未配置"）。
3. `tools/gen_gateway_container_config.py` 增加 **mcp env 端口映射**
   （`127.0.0.1:9090→o2oa-server` / `:8091→ai-ocr` / `:1234,8089,8092→host.docker.internal`），防止下次重生成又回退。
4. `config.container.json` 的 `O2OA_BASE` 改为 `http://o2oa-server:9090`。
   **生效需 `docker compose build ai-gateway && up -d`（或 `docker cp` 后重启该容器）**。

**一行定案（容器内对比地址）**：
```bash
export MSYS_NO_PATHCONV=1
docker exec o2oa-ai-gateway python -c "
import socket
for h,p in [('127.0.0.1',9090),('o2oa-server',9090),('ai-ocr',8091),('host.docker.internal',1234)]:
    s=socket.socket(); s.settimeout(3)
    try: s.connect((h,p)); print(h,p,'OK')
    except Exception as e: print(h,p,'FAIL',type(e).__name__)
    finally: s.close()"
```
预期：`127.0.0.1 9090 FAIL ConnectionRefusedError`、其余全 OK。这就是「容器在跑但工具说挂了」的铁证。

**教训**：**"容器在运行" ≠ "容器内能按你写的地址访问到别的服务"。**
容器化后所有 `127.0.0.1` 都要重审一遍——不只 config 顶层 base，
还包括 `mcp_servers[].env`、工具源码里的硬编码（生成器最容易漏这两处）。

### ★★ 同现场第二层 bug：地址修通后，工具解析立刻崩（2026-09-30）

把 `O2OA_BASE` 改对后，`o2_login_status` 立即 `login_ok=True`，但 `o2_person_query` 仍报
`TOOL_ERROR: 'list' object has no attribute 'get'` —— **只修网络层等于没修**。

- 原因：`person/list/like` 返回 `{"data":[...]}`（数组），旧代码写
  `people = (d.get("data") or {}).get("data") or (d.get("data") or [])` → 对 list 调 `.get` 直接抛异常。
  同款写法还出现在 `o2_task_my`。
- 修法：`o2oa_tools_mcp.py` 新增 `_rows(d)`，统一兼容
  `{"data":[...]}` / `{"data":{"data":[...],"count":n}}` / 裸列表，供 `o2_org_unit_top`/`o2_task_my`/`o2_person_query` 使用；
  `o2_person_query` 顺带输出 手机/邮箱/工号（模型问"某人手机号"时才有内容可答）。
- 复测（容器内**按网关真实方式**调 `StdioMCPClient`，别只调脚本）：
  ```bash
  export MSYS_NO_PATHCONV=1
  docker exec o2oa-ai-gateway python -c "
  import sys,json; sys.path.insert(0,'/app/gateway')
  from mcp_client import StdioMCPClient
  cfg=json.load(open('/app/gateway/config.json',encoding='utf-8'))
  spec=[s for s in cfg['mcp_servers'] if s['name']=='o2oa'][0]
  c=StdioMCPClient('o2oa',spec['command'],spec.get('args'),spec.get('env'),spec.get('timeout',30)); c.initialize()
  print(c.call_tool('o2_person_query',{'key':'罗'})); c.close()"
  ```
- ★ **改完必须端到端重跑工具链**：网络故障会掩盖解析类 bug，"改了、能连了"≠"能答了"。

### ★ 重启后网关 15~30 秒才对外响应（2026-09-30 实测）
`docker restart o2oa-ai-gateway` 后，TCP 已能连上 18790，但 `GET /gateway/health` 会
**无响应超时**（事件循环被启动期任务占住），约 15~30 秒后才恢复 200。
期间若用探针判活会误报"网关挂了"。容器日志可见 4 行 `[mcp] ... loaded N tools` 即已加载完成。

### 割接验证命令
```bash
export MSYS_NO_PATHCONV=1   # 否则 taskkill /PID 被 MSYS 路径转换毁掉
curl -s --max-time 20 http://127.0.0.1:18790/gateway/health                 # 宿主
docker exec o2oa-ai-gateway python -c \
  "import httpx;print(httpx.get('http://127.0.0.1:18790/gateway/capabilities',headers={'Authorization':'Bearer local-o2-agent-2026'},trust_env=False).text)"
```
判据：chat/embed `up:true` 且 base=`host.docker.internal:1234`；ocr `ok:true` 且 base=`ai-ocr:8091`。
复盘全文见仓库 `docs/knowledge_base/ai_stack_container_cutover_20260930.md`（提交 `5db6cb2`）。

---

## 现象（看门狗时代，历史）
- 桌面不停弹出 `python.exe` 或 `powershell.exe` 控制台窗口（每次一个）。
- `localhost:9090` 在浏览器里卡死/超时，但服务其实活着。
- `gateway\watchdog.log` 出现 `gateway:18790 DOWN -> 重新拉起` 每 30~40s 一轮。

## 根因（六条，按出现频率）
1. **venv 启动器丢失无窗标志（弹窗主因）**
   `Scripts\python.exe` 是启动器，会再 spawn 基础解释器；父进程用 `DETACHED_PROCESS(0x8)` 时无控制台可继承 → 孙进程被 Windows 新分配【可见】控制台。
   修复：`start_ai_stack_detached.py` 的 `DETACHED` 改为
   `0x00000200 | 0x01000000 | 0x08000000`（NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW）。隐藏控制台可被子进程继承，整树无窗。
2. **urllib 探活被系统代理劫持（误杀健康服务）**
   `healthy()` 默认读 Windows 系统代理，宿主开 Clash 等时 `127.0.0.1` 探活被转发到代理 → 失败 → 误判 DOWN → 杀掉健康服务重启，形成死循环。
   修复：改成**纯 TCP 连通性**判定（`socket.create_connection`），完全绕过代理/HTTP/鉴权；另在 watchdog 启动前清空 `HTTP(S)_PROXY` 等环境变量，子进程（httpx trust_env=True）一并免疫。
3. **看门狗内部子进程弹窗 + GBK 解码崩溃**
   `subprocess.run(["powershell"/"netstat"/"taskkill"], ...)` 未加 `CREATE_NO_WINDOW` → 每个调用弹一个可见窗口；且输出是 GBK，按 UTF-8 解码触发 `UnicodeDecodeError` 被当成探活异常参与 DOWN 误判。
   修复：统一用 `_RUN_KW = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)`。
4. **单例锁让旧看门狗占坑（改了代码不生效）**
   看门狗有单例锁：旧进程（旧代码）活着时，新看门狗按命令行匹配杀不到（VBS 隐藏启动的 32 位 python 常查不到 CommandLine）→ 新进程直接退出，旧 bug 进程一直跑。
   修复：`restart_ai_gateway.bat` 与开机自启 `O2OA_AI_stack_autostart.vbs` 改为**先按各组件 pid 文件（`watchdog/gateway/ocr/embed/chat/rerank.pid`）精确 taskkill /T，再删 pid 文件**，最后 `-WindowStyle Hidden` 拉起新看门狗。
5. **看门狗重启逻辑不做"端口归属对账"，会误杀健康孤儿网关（2026-09-25 实证）**
   看门狗按 `pid 文件` 判活：`old=load_pid(); if not pid_alive(old): 记 "DOWN->重新拉起" 并 free_port+重启`。但若旧 pid 已死、而**另一个进程（手动双击 bat / 上次实例遗留）正占用该端口且健康**（如 18790 被 pid 23216 正常服务 `/gateway/health`→200，而 pid 文件记的是已死的 26632），看门狗会 `free_port` 把**健康的 23216 杀掉**再重启 → 端口短暂横跳 → 用户侧 18790 间歇性超时。表现为：gateway.log 一路 200、`netstat` 显示端口有人听，但 watchdog.log 反复 "gateway DOWN->重新拉起 / 60s 未就绪"。
   修复（硬化版已落地，2026-09-25 实测根治）：
   - **单例锁改用内核级 socket 互斥端口(18800)**：bind 成功=独占，失败=已有实例退出。比 pid 文件锁可靠（无 TOCTOU 竞态），进程退出内核自动释放。
   - **端口归属感知 `port_state(port)`**：每轮先判定 `down / ours / foreign`。`ours`=TCP 通+健康端点 200（网关带 token 复核）→ 刷新陈旧 pid 为真实占用者、**绝不误杀**；`foreign`=TCP 通但复核失败 → 仅此场景 `free_port` 释放后重建；`down` → 直接拉起。
   - **启动期防抖 `START_GUARD`**：对某组件执行过 free/restart 后 N 秒内不重复触发，给新进程加载时间，避免一次空窗被反复重启。
   - **`launch()` 第 3 步 bind 前先查端口占用者并 `free_port`**：修复"孤儿进程占端口导致新网关 bind 失败、反复 WARN 永不就绪"的死循环。
   - **彻底移除首轮无条件 `free_port`**：旧版每轮首轮对 18790 无差别 free_port 是误杀健康孤儿的直接代码证据，已删除。
   - **rerank 开关解耦**：看门狗读 `config.json` 的 `rerank_enable`（不再仅依赖 `--rerank`），改 config 即开/关 8092 rerank 服务。
   - 务必**只保留一条启动链路**（VBS 或 bat 二选一）；socket 锁已让双开无害（第二个实例自动退出）。
6. **★★ 看门狗把「正在服务请求」的网关误判为孤儿并杀掉（2026-09-27 实证，危害最大）**
   用户侧症状：前端调用 AI 技能时弹 `POST connect connection error, address:
   http://192.168.1.5:18790/ai-gateway-clue/list/... because: connect timed out`，
   看起来像"服务没起来/地址写错/鉴权失败"，**全都不是**。
   取证关键（先做这三步，别急着改配置）：
   - `gateway.log` 显示**该请求其实 200 成功**（如 `23:38:56 POST /ai-gateway-completion/generate -> 200`），
     会话也已落库 → 说明网关当时是好的。
   - `watchdog.log` 在同一秒附近有 `gateway:18790 被外部/孤儿进程 [0, <pid>] 占用，释放后重建`
     + `DOWN -> 重新拉起` → **是看门狗在用户提问那一刻把网关杀了**。
   - owners 里出现 **pid 0** 是同症状（端口上的非 LISTENING 连接痕迹）。
   机理：健康端点 `/gateway/health` 与 LLM 生成**共用同一事件循环**，
   长任务（流式生成）期间健康探测排队超时 → `port_state()` 判 `foreign` → `free_port()` 误杀。
   修复（2026-09-27 已落地，`0b4dcb0`）：
   - 新增 `port_busy(port)`：检测端口上 **ESTABLISHED / SYN_RECEIVED**。
     ★★ **绝不能用 `netstat -p TCP` 过滤** —— 那会漏掉 ESTABLISHED 行、恒返回 False，
     这是最容易写错的实现细节。
   - `port_state()` 新增 **busy 态**：有活动连接即视为健康、**绝不 free_port**；
     且下 `foreign` 结论前追加一次 1s 延迟的二次健康确认。
   - 主循环 `busy` 与 `ours` 同等待遇（跳过重建 + 校正 pid）。
   - `is_up()` 超时 1s → 3s（容忍高峰期排队）。
   - 判据口诀：**"端口有人在连" 优先于 "健康端点答不答"** —— 有连接就说明进程在干活。

## 涉及文件（全部位于 D:\O2OA\gateway\，除 VBS 在启动文件夹）
- `start_ai_stack_detached.py` — `DETACHED` 常量 + `healthy()` TCP 版。
- `watchdog_ai_stack.py` — `_RUN_KW` 无窗+容错；`free_port`/`launch` 用 `DETACHED`/`_RUN_KW`；启动清代理 env。
- `restart_ai_gateway.bat` — 按 pid 文件杀 + 隐藏拉起（手动重启入口）。
- `O2OA_AI_stack_autostart.vbs` — 开机先按 pid 文件清杀再启动（纯 ASCII + CRLF）。
- `D:\deploy_home_entry_local.ps1` — 首页门户化脚本：写本地后**必须 `docker cp` 进 `o2oa-server` 容器**才对运行中的 O2OA 生效（webServer 在镜像内、未挂卷，仅写本地无效）；末尾勿用 `Read-Host` 挂窗。文件须 UTF-8 **带 BOM**，否则中文 Windows PowerShell 按 GBK 误读中文报假语法错误。

## 持续化：看门狗即唯一持久化/自愈锚点（核心原则）
「看门狗持续化」≠ 散落各处的脚本，而是：**看门狗是唯一入口**。
- 所有 AI 栈子进程**只**由看门狗拉起；`restart_ai_gateway.bat` 与开机 VBS 只做「按 pid 杀干净 → 隐藏拉起看门狗」。
- 看门狗每次启动即自检：清代理 env → `CREATE_NO_WINDOW` 无窗拉子进程 → 按 pid+端口兜底杀残留 → 纯 TCP 探活不误杀。
- 改了代码必须**杀掉旧看门狗并重新拉起**才生效（否则单例锁让旧进程一直跑旧代码）。

## 打包成分支（代码级持久化、可复现分发）
把运行态代码快照整理成自包含目录 `D:\O2OA\ai-stack-hardening\`，结构：
```
ai-stack-hardening/
├── gateway/      (watchdog_ai_stack.py, start_ai_stack_detached.py, restart_ai_gateway.bat)
├── deploy/       (deploy_home_entry_local.ps1)
├── startup/      (O2OA_AI_stack_autostart.vbs)
├── docs/         (knowledge-base.md / knowledge-base.html)
├── README.md
└── install.ps1   (一键覆盖真实路径 + 按 pid 重启看门狗)
```
初始化即「分支」：
```bash
cd D:\O2OA\ai-stack-hardening
git init -b ai-stack-hardening
git add -A && git commit -m "ai-stack: watchdog-based persistence & no-popup hardening"
git bundle create ai-stack-hardening.bundle ai-stack-hardening   # 分发用
```
`install.ps1` 用管理员 PowerShell 运行，复制文件到真实路径并 `Start-Process -WindowStyle Hidden` 重启看门狗。

## 把排障知识写入本地 O2OA 知识库（CMS publish/html）
O2OA 本地「知识管理」模块未装（断云），用 **CMS（内容管理）** 承载知识库。实测可用端点（admin/o2oaadmin2026 登录取 token）：
1. 登录取 token：`POST /x_organization_assemble_authentication/jaxrs/authentication {"credential":"admin","password":"o2oaadmin2026"}` → `data.token`。
2. 建应用：`POST /x_cms_assemble_control/jaxrs/appinfo {"appName":"AI运维知识库","appAlias":"AIOPS-KB","appType":"知识库","documentType":"信息","appInfoSeq":"1000"}` → `data.id`（应用 id）。
3. 建分类：⚠️ 分类**必须绑定编辑表单(formId)**，否则建文档报 `ExceptionCategoryFormIdEmpty`。`POST /x_cms_assemble_control/jaxrs/categoryinfo {"appId":<应用id>,"categoryName":"排障与硬化","categoryAlias":"AIOPS-TS","categoryType":"信息","documentType":"信息","formId":<已有表单id>,"readFormId":<同>}` → 分类 id。无自建表单时可**复用现有表单 id**（跨应用绑定 publish 仍成功；本环境复用了公文配置/公章配置的 formId `965291d5-bf7b-403a-91ea-117f639f07e1`）。
4. 建文档(草稿)：`POST /x_cms_assemble_control/jaxrs/document {"title":...,"categoryId":<分类id>,"docStatus":"draft"}` → 文档 id。
5. 注入 HTML 正文：`POST /x_cms_assemble_control/jaxrs/document/{文档id}/publish/html {"htmlContent":"<html>...</html>"}` → 写成 `webServer/cms_publish/{文档id}.html`，浏览器可访问 `http://localhost:9090/cms_publish/{文档id}.html`。
6. 标记已发布（进 CMS 文章列表）：`PUT /x_cms_assemble_control/jaxrs/document/publish/{文档id}`。
> 注意：调用时 token 放 header `x-token`；若用 venv 的 Windows 版 python，文件路径用 `D:/...` 而非 `/d/...`（Git-Bash 挂载路径 python 不认）。

## 验证命令（沙箱内可执行，用于取证）
```
# ★ 必须绕过系统代理，否则本机代理会返回 502，让你误判服务已死
curl -s --max-time 10 --noproxy '*' http://127.0.0.1:18790/gateway/health -o /dev/null -w "gateway=%{http_code}\n"
tail -20 D:\O2OA\gateway\watchdog.log
tail -20 D:\O2OA\gateway\gateway.log
```
服务侧通常一直 200；弹窗是看门狗误杀循环，不是服务真死。
★ `watchdog.log` 是**纯 UTF-8**，在 GBK 控制台下直接 `grep` 会显示成 `琚�澶栭儴`
这类乱码——**文件没问题，是终端解码问题**；用 Python 以 utf-8 读或先 `chcp 65001`。

## ★★ bat 启动器三个隐蔽 bug（2026-09-27 实测，会导致"双击没反应"）
1. **LF-only 行尾**：`cmd` 只认 CRLF。LF-only 会把多行**粘成一条命令**，报
   `'xxx' 不是内部或外部命令`。实测 `restart_ai_gateway.bat` / `start_ai_watchdog.bat` /
   `start_gateway.bat` / `start_llama.bat` 四个都是 LF-only（57 个 LF、0 个 CRLF）。
   自检：`open(p,'rb').read()` 里 `count(b'\r\n')` 与总 LF 数是否相等。
   修复：统一转 CRLF（UTF-8 **无** BOM，与 `.ps1` 的"有 BOM"约定**相反**）。
2. **`$_.CommandLine` 在 `powershell -Command` 内联里会失败**：
   它是只读属性，内联场景报
   `ParameterBindingValidationException`，导致 `Where-Object` 匹配数为 0 →
   **清理旧进程的逻辑静默失效**、旧进程残留。改 `-match 'a\.py|b\.py'` 管道式写法。
3. **`-ArgumentList 'x',''` 会校验失败**：`ARGS` 为空时传 `''` 报
   `The argument is null or empty` → **看门狗根本没被拉起**。
   改 `if defined ARGS (... ) else ( ... )` 分支。
   另：`timeout /t N` 在本机不可用（报 `invalid time interval`）→ 用 `ping -n N+1 127.0.0.1 >nul`。

## ★★ 沙箱内无法启动常驻进程（交付前必须先说清，别急着说"已修好"）
本会话（及任何沙箱化会话）在**每条命令结束时回收该命令派生的所有子进程**：
`subprocess.Popen(DETACHED_PROCESS)`、`Start-Process -WindowStyle Hidden`、
`cmd /c start /MIN`、VBS 桥（`cscript`/`wscript` 本身被安全策略拦）**全部会被回收**。
典型症状：看门狗日志写了 `看门狗启动：...`、端口短暂 LISTEN，**45s 后再查进程数为 0**，
`*.pid` 文件却还在（所以 pid 文件"alive"判断也可能因 PID 复用而误导）。
→ **常驻服务（看门狗/网关/OCR）只能由用户在真实桌面双击 bat 启动。**
→ 排查此类问题时，切勿把"沙箱回收"误判成"代码 bug"而反复重启；先把当前代码改对、
   语法校验通过、单测跑通，**再明确告知用户"需要你双击一次 start_ai_watchdog.bat"**。
→ 单测技巧：`port_busy`/`port_state` 这类纯函数可在沙箱内直接 import 单测
   （用 `socket.create_connection` 自己造一条长连接来模拟"正在服务请求"），
   **不需要真的起服务**。

## 让修复生效（沙箱隔离主机进程，需用户在真实主机执行一次）
```powershell
# 按 pid 文件精准杀旧看门狗 + 所有组件，再隐藏拉起修复版
$ids=@(); 'watchdog','gateway','ocr','embed','chat','rerank' | %{ $pf="D:\O2OA\gateway\$_.pid"; if(Test-Path $pf){ $id=[int](Get-Content $pf -Raw); if($id){$ids+=$id}; Remove-Item $pf -Force } }
$ids|Sort -Unique|%{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process|?{$_.CommandLine -like '*watchdog_ai_stack.py*' -or $_.CommandLine -like '*o2_agent_gateway.py*' -or $_.CommandLine -like '*ocr_service.py*'}|%{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 3
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:http_proxy='';$env:https_proxy='';$env:ALL_PROXY='';$env:all_proxy=''
Start-Process -FilePath "C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -ArgumentList "D:\O2OA\gateway\watchdog_ai_stack.py" -WindowStyle Hidden -WorkingDirectory "D:\O2OA\gateway"
```
之后约 30s 弹窗消失、循环停止。以后重启直接双击 `restart_ai_gateway.bat`，开机由 VBS 自动无窗自愈。

## 9090「浏览器卡死」的特殊说明
若 `curl 9090` 返回 200 而浏览器卡死，是**客户端系统代理劫持了 localhost**（与看门狗被代理误杀同源）。解决：代理设置里把 `localhost;127.0.0.1` 加入「绕过代理」，或临时关代理刷新 `http://localhost:9090/`。服务本身正常，无需重启 O2OA。

## 容器 `unhealthy` 多半是误报
`o2oa-server` 状态 `unhealthy` 但 `curl 9090 → 200`：健康检查用了 `docker exec`，而 ARM+QEMU 环境下 `exec` 的 setns 会失败（`OCI runtime exec failed ... setns process`），导致健康检查永远失败 → 误报 unhealthy。**服务实际正常**，勿据此重启容器。
