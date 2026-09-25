# ai-stack-hardening — O2OA AI 栈「看门狗持续化」硬化分支

> 本目录是 **当前运行态** 的代码快照，可整体打包成分支（`git bundle` / `git archive`）分发复现。
> 核心思想：**看门狗是唯一持久化/自愈锚点**，所有 AI 栈子进程只由看门狗拉起，restart 与开机启动都只负责「按 pid 杀干净 → 隐藏拉起看门狗」。

## 目录结构
```
ai-stack-hardening/
├── gateway/
│   ├── watchdog_ai_stack.py          # 看门狗（持久化锚点）：TCP 探活 + 无窗拉子进程 + 按 pid 杀旧
│   ├── start_ai_stack_detached.py    # healthy() 纯 TCP + ProxyHandler({})；DETACHED=CREATE_NO_WINDOW
│   └── restart_ai_gateway.bat        # 按 pid 文件精准杀旧 + 隐藏拉起看门狗
├── deploy/
│   └── deploy_home_entry_local.ps1   # O2OA 首页门户化：docker cp 进容器 + 去挂窗 + UTF-8 BOM
├── startup/
│   └── O2OA_AI_stack_autostart.vbs  # 开机自启：按 6 个 pid 文件清杀全部组件再启动（无窗）
├── docs/
│   ├── knowledge-base.md             # 整轮排障对话的根因/方法/技巧（Markdown）
│   └── knowledge-base.html           # 同上（已推送到本地 O2OA 知识库 CMS 应用「AI运维知识库」）
├── README.md
└── install.ps1                      # 一键部署到真实路径并重启看门狗
```

## 已固化的根因与修复
| 现象 | 根因 | 修复 |
|---|---|---|
| powershell/python 不停弹窗 | 看门狗 `healthy()` 走系统代理误判 DOWN → 杀健康服务 → 重启循环 | `healthy()` 改纯 TCP + `ProxyHandler({})` 强制直连 |
| 每轮弹可见窗口 | 子进程 `subprocess` 未加 `CREATE_NO_WINDOW`；GBK 输出按 UTF-8 解码崩溃 | 全部 `CREATE_NO_WINDOW` + `errors="replace"`；启动清代理 env |
| 孙进程仍弹窗 | venv `python.exe` 是启动器，`DETACHED(0x8)` 无控制台可继承 | `DETACHED` 改 `CREATE_NO_WINDOW`（隐藏控制台被子进程继承） |
| 旧看门狗顶掉新看门狗 | 按命令行匹配杀不到隐藏 VBS 启动的进程 | 按 pid 文件精准杀；VBS/restart 都先按 pid 清杀 |
| 9090 浏览器卡死 | 服务实测 200，浏览器侧代理劫持 localhost | 代理 bypass `localhost;127.0.0.1` |
| 容器 unhealthy | `docker exec` 健康探针在 QEMU/ARM 下 setns 失败误报 | 服务实际正常，无需处理 |
| 首页分流无效 | compose 未挂 webServer 卷，只写本地对容器无效 | `docker cp` 进容器；持久化请固化进 Dockerfile 或挂卷 |

## 安装 / 部署
以**管理员 PowerShell** 运行：
```powershell
cd D:\O2OA\ai-stack-hardening
.\install.ps1
```
`install.ps1` 会把 `gateway/*` 覆盖到 `D:\O2OA\gateway\`、`deploy/*` 到 `D:\deploy_home_entry_local.ps1`、`startup/*` 到启动文件夹，并按 pid 重启看门狗（无窗）。

## 打包成分支
```bash
cd D:\O2OA\ai-stack-hardening
git init -b ai-stack-hardening
git add -A && git commit -m "ai-stack: watchdog-based persistence & no-popup hardening"
# 分发：
git bundle create ai-stack-hardening.bundle ai-stack-hardening
```

## 验证
- [ ] `watchdog.log` 不再出现 `DOWN -> 重新拉起` 循环
- [ ] 桌面不再弹出任何 python/powershell 窗口
- [ ] `curl http://localhost:18790/gateway/health` 持续 200（无论代理开关）
- [ ] O2OA 知识库 `AI运维知识库 / 排障与硬化` 可见本文档
