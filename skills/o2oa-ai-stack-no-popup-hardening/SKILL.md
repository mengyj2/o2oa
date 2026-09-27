---
name: o2oa-ai-stack-no-popup-hardening
description: 诊断并根治 O2OA AI 栈（gateway/ocr/embed 看门狗）反复弹出 PowerShell / python 控制台窗口、且 localhost:9090 看似卡死的问题。覆盖：venv 启动器丢失无窗标志、urllib 探活被系统代理劫持误判 DOWN、看门狗单例锁导致旧进程占坑、GBK 输出触发 UnicodeDecodeError。并覆盖「看门狗持续化 / 打包成分支」与「把排障知识写入本地 O2OA 知识库（CMS publish/html）」。当用户说「AI 栈弹窗」「gateway 一直重启」「9090 卡死」「看门狗循环」「保存到 O2OA 知识库」「打包成分支」时加载。
agent_created: true
category: diagnostics

---

# O2OA AI 栈看门狗弹窗 / 9090 卡死 根治

## 现象
- 桌面不停弹出 `python.exe` 或 `powershell.exe` 控制台窗口（每次一个）。
- `localhost:9090` 在浏览器里卡死/超时，但服务其实活着。
- `gateway\watchdog.log` 出现 `gateway:18790 DOWN -> 重新拉起` 每 30~40s 一轮。

## 根因（四条，按出现频率）
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
curl -s --max-time 10 http://localhost:18790/gateway/health -o /dev/null -w "gateway=%{http_code}\n"
curl -s --max-time 10 http://localhost:9090/ -o /dev/null -w "o2oa9090=%{http_code}\n"
tail -20 D:\O2OA\gateway\watchdog.log
```
服务侧通常一直 200；弹窗是看门狗误杀循环，不是服务真死。

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
