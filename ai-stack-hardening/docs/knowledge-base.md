# O2OA AI 栈「看门狗弹窗 / 9090 卡死」根因与看门狗持续化硬化手册

> 来源：2026-09-22 ~ 09-23 多轮排障对话的完整沉淀。
> 适用：本地 Docker 自托管 O2OA 10.0.2 + 本地 AI 网关栈（gateway/ OCR / embed / chat / rerank）。
> 结论先行：9090 服务从未死；弹窗的真凶是 AI 栈看门狗的探活误判死循环；**看门狗本身就是持久化/自愈的锚点**。

---

## 0. 一句话结论

- **9090 卡死 ≠ 服务挂了**：实测 `curl http://localhost:9090/ → HTTP 200 / 4~7ms`，容器首页是官方标准跳转页。
- **powershell / python 不停弹窗**：真凶是 `gateway/watchdog_ai_stack.py` 陷入「误判 DOWN → 杀掉健康服务 → 重启」死循环，每轮拉起一个新 `python.exe` 进程 = 一个窗口。
- **误判根因**：`healthy()` 用 `urllib.request.urlopen` **默认走系统代理**；代理（52068 假 502）劫持了 `127.0.0.1` 探活 → 失败 → 误判 DOWN。
- **持久化方案**：把看门狗设为唯一锚点——启动清代理 env、无窗拉子进程、按 pid 杀旧进程、纯 TCP 探活不误杀；restart bat 与开机 VBS 全部经看门狗。这就是「看门狗持续化」。

---

## 1. 现象时间线（复盘）

| 时间 | 现象 | 当时误判 | 真因 |
|---|---|---|---|
| 运行 `D:\deploy_home_entry_local.ps1` | 9090 卡死、powershell 弹窗 | 以为是部署脚本 / 首页分流死循环 | 脚本只改了本地文件（容器 webServer 未挂卷，无效）；弹窗来自另一处 |
| 看截图发现弹窗是 `.workbuddy\binaries\python\envs\default\Scripts\python.exe` | 以为是 python 包装器 | 误判为 WorkBuddy 自带弹窗 | 实为看门狗拉起的 AI 栈子进程 |
| 10:33~10:53 `watchdog.log` | 每 40s 一轮 DOWN→重启 | 以为是服务真崩 | `healthy()` 代理误判，服务全程 200 |
| 11:10 重启看门狗后仍弹 2 窗 | 以为修复没生效 | 旧看门狗(24100) 未被替换 | 旧进程持单例锁顶掉新看门狗 |
| 后续每几分钟仍 DOWN→重启 | 以为是新 bug | — | 跑着的仍是有缺陷的旧代码 |

---

## 2. 根因分层（必须逐层理解）

### 2.1 部署脚本的两处隐患（已修，非主因）
- `deploy_home_entry_local.ps1` 旧版用 `Get-ChildItem -Recurse` **全盘递归搜索 `index.html`**，在大容量盘上疯狂刷 IO（IO 风暴是把 QEMU 容器拖到短暂无响应的帮凶之一，被误认为"卡死"）。
- 修复后改为「盘根一层受控列举」，并把分流版 `docker cp` 进容器（因为 compose 未挂 webServer 卷，只写本地对运行中的容器**无效**）。
- **隐藏真相**：此前门户首页"分流"从未真正生效——脚本只写本地，容器一直跑镜像内置官方首页。

### 2.2 看门狗「误判 DOWN」死循环（主因）
`watchdog.log` 铁证：gateway(18790) / ocr(8091) 每隔约 40s 被 `taskkill /F` 杀掉再拉起，循环 20+ 轮；而 `gateway.log` 同期 `GET /gateway/health → 200` 全程连续。
**服务没死，是看门狗在误杀健康服务。**

### 2.3 误判根因：探活走代理
`healthy(url, token)` 用 `urllib.request.urlopen(req)`，而 `urllib` **默认读取系统代理环境变量**。
一旦机器开了代理（本机 52068，假 502），探活 `127.0.0.1:18790` 的请求被转发到代理 → 失败 → `healthy()` 返回 False → 看门狗判定 DOWN。

> 同一根因的另一面：`o2oa_netlock.sh` 记忆铁律——**本地探测一律 `curl --noproxy "*"`**，因为 shell 代理会假 502。看门狗探活也必须绕过代理。

### 2.4 弹窗帮凶：子进程可见窗口 + GBK 解码崩溃
- 看门狗用 `subprocess.run(["powershell", ...])` / `["netstat", ...]` / `["taskkill", ...]` 时**没加 `CREATE_NO_WINDOW`** → 每个子进程都新分配一个可见控制台窗口 = 每轮探活弹 2~3 个 PowerShell 窗口。
- `watchdog_stdout.log` 里 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xbb`：看门狗把 `netstat` 的 **GBK 输出按 UTF-8 解码**，直接抛异常，该异常又被当成「服务 DOWN」参与误判。

### 2.5 子进程弹窗：venv 启动器丢失无窗标志（最后一弹）
看门狗用 `DETACHED_PROCESS(0x8)` 拉子进程（意为"无控制台"），但 venv 的 `Scripts\python.exe` 是**启动器**，会再 `spawn` 基础解释器；父进程没有控制台可继承 → 孙进程被 Windows 新分配一个**可见**控制台。
**修复**：把创建标志换成 `CREATE_NO_WINDOW`（隐藏控制台可被孙进程继承，整条进程树都不弹窗）。

### 2.6 9090 浏览器"卡死"真相
- 服务端实测 `curl 9090 → 200 / 6ms`，容器首页是标准 O2OA 跳转页（`x_desktop/index.html`，2295 字节，无分流无死循环）。
- 你在浏览器里卡死 = **系统代理把 `localhost:9090` 也劫持了**（与看门狗被代理误杀同源）。
- 解决：把 `localhost;127.0.0.1` 加入代理「绕过」列表，或临时关代理刷新即可秒开。

### 2.7 容器 `unhealthy` 是误报
容器 `o2oa-server` 状态 `unhealthy`，但 `curl 9090 → 200`。健康检查命令用了 `docker exec`，而 ARM+QEMU 环境下 `exec` 的 setns 会失败（`OCI runtime exec failed ... setns process`），导致健康检查永远失败 → 误报 unhealthy。**服务实际正常**。

---

## 3. 代码级修复清单（已全部落盘）

| 文件 | 修改 | 作用 |
|---|---|---|
| `gateway/start_ai_stack_detached.py` | `healthy()` 改**纯 TCP 连通性** + `ProxyHandler({})` 强制直连；`DETACHED` 常量改 `CREATE_NO_WINDOW` | 代理不再误判；孙进程不再弹窗 |
| `gateway/watchdog_ai_stack.py` | 所有 `subprocess.run` 加 `CREATE_NO_WINDOW` + `errors="replace"`；启动时清空全部代理 env；`from start_ai_stack_detached import healthy, DETACHED` | 不再弹窗；不再 GBK 崩溃；探活走 TCP |
| `gateway/restart_ai_gateway.bat` | 按 pid 文件**精准杀旧** + 隐藏窗口拉起 | 不再被旧进程单例锁顶掉 |
| `O2OA_AI_stack_autostart.vbs`（启动项） | 开机先按 6 个 pid 文件清杀全部组件再启动；纯 ASCII + CRLF | 根治「旧看门狗占锁→新看门狗被顶掉」 |
| `deploy_home_entry_local.ps1` | 加 `docker cp` 进容器；去掉末尾 `Read-Host` 挂窗；补 UTF-8 BOM | 门户化真正生效；不再挂等待窗口；PowerShell 按 GBK 误报语法错的根治 |

### 3.1 关键代码片段
`healthy()` 纯 TCP 版（彻底免疫代理/HTTP/鉴权）：
```python
def healthy(host, port, timeout=3):
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
```
看门狗启动清代理 + 无窗：
```python
CREATE_NO_WINDOW = 0x08000000
_RUN_KW = dict(encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
for _k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(_k, None)
```

---

## 4. 看门狗持续化设计（本次核心要求）

「看门狗持续化」= **看门狗是唯一持久化/自愈入口**，而非散落各处的脚本：

1. **单一来源**：所有 AI 栈子进程**只**由看门狗拉起；`restart_ai_gateway.bat` 与开机 VBS 都只负责「按 pid 杀干净 → 隐藏拉起看门狗」。
2. **启动自检即持久化**：看门狗每次启动都
   - 清掉全部代理 env（子进程一并免疫）；
   - 用 `CREATE_NO_WINDOW` 无窗拉子进程（进程树无窗）；
   - 按 pid 文件 + 端口兜底杀掉上一轮所有残留（双开机/双击也不叠加）；
   - 用纯 TCP 探活，端口 listening 即存活，**绝不因代理开关误杀健康服务**。
3. **可打包为分支**：本目录 `ai-stack-hardening/` 即「运行态」的代码快照——`gateway/` + `deploy/` + `startup/` + `install.ps1`，`git` 提交到分支 `ai-stack-hardening`，未来可 `git bundle` / `git archive` 直接分发复现。

---

## 5. 可复用的经验 / 技巧（跨会话）

1. **本地探活必绕代理**：`curl --noproxy "*"`；Python `urllib` 装 `ProxyHandler({})`；`httpx` 设 `trust_env=False`。
2. **venv 启动器无窗**：子进程创建标志用 `CREATE_NO_WINDOW`，不要用 `DETACHED_PROCESS`（孙进程会丢标志弹窗）。
3. **代理会假 502 劫持 localhost**：O2OA 探测 / 本机服务探活一律绕代理；浏览器卡 localhost 先查代理 bypass。
4. **别用 `-Recurse` 全盘递归搜索**：大容量盘会 IO 风暴，改受控列举。
5. **控制台子进程加 `CREATE_NO_WINDOW`**；GBK 输出用 `errors="replace"`，否则 `UnicodeDecodeError 0xbb` 参与逻辑误判。
6. **容器 unhealthy 但 9090=200** → 多半是 `docker exec` 健康探针在 QEMU/ARM 下 setns 失败误报，服务正常。
7. **PowerShell `.ps1` 中文要用 UTF-8 BOM**，否则中文 Windows 按 GBK 误报语法错（ParseFile 报一堆中文乱码假错误）。
8. **按 pid 文件精准杀**比按命令行匹配更可靠（VBS 隐藏启动的 32 位 python 常查不到 CommandLine）。

---

## 6. 操作命令（止血 + 让修复生效）

> 沙箱隔离了主机进程，以下需在**真实主机 PowerShell** 执行。

```powershell
# ① 按 pid 文件精准杀旧看门狗 + 各组件（含子进程 /T）
$ids = @(); 'watchdog','gateway','ocr','embed','chat','rerank' | ForEach-Object {
  $pf = "D:\O2OA\gateway\$_.pid"
  if (Test-Path $pf) { $id=[int](Get-Content $pf -Raw); if($id){$ids+=$id}; Remove-Item $pf -Force }
}
$ids | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
# ② 兜底按命令行再杀残留
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -like '*watchdog_ai_stack.py*' -or $_.CommandLine -like '*o2_agent_gateway.py*' -or $_.CommandLine -like '*ocr_service.py*'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 3
# ③ 清空代理环境变量，隐藏窗口拉起修复版看门狗
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:http_proxy='';$env:https_proxy='';$env:ALL_PROXY='';$env:all_proxy=''
Start-Process -FilePath "C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe" `
  -ArgumentList "D:\O2OA\gateway\watchdog_ai_stack.py" -WindowStyle Hidden -WorkingDirectory "D:\O2OA\gateway"
Write-Host "已重启修复版看门狗（无窗口 + TCP 探活）。约 30 秒后弹窗消失、不再循环重启。"
```

9090 浏览器卡死：在代理里把 `localhost;127.0.0.1` 加入「绕过」，或临时关代理刷新。

---

## 7. 验证清单

- [ ] `watchdog.log` 不再出现 `DOWN -> 重新拉起` 循环。
- [ ] 桌面不再弹出任何 python/powershell 窗口。
- [ ] `curl http://localhost:18790/gateway/health` 持续 200（无论代理开关）。
- [ ] `curl http://localhost:9090/` 返回 200（浏览器侧需把 localhost 加入代理 bypass）。
- [ ] 重启网关双击 `restart_ai_gateway.bat` 无窗口；开机由 VBS 自动无窗自愈。
