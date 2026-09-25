# O2OA AI 栈 · 看门狗持续化运行手册

> 本手册定义 AI 栈「持续化」的唯一机制：**看门狗（watchdog）常驻 + 开机自启 VBS**，全部以代码形式纳管于 git，可随分支打包复现。
> 目标：不依赖任何交互式会话（AI 助手会话结束即回收），AI 栈由看门狗自愈保持长期运行。

## 1. 角色定位

| 组件 | 文件 | 端口 | 职责 |
|---|---|---|---|
| 看门狗 | `gateway/watchdog_ai_stack.py` | — | 每 30s 探活，组件崩则脱离式拉起；持 `watchdog.pid` 单例锁 |
| 网关 | `gateway/o2_agent_gateway.py` | 18790 | AI 助手入口，内置 RAG、设计态工具、成长感知 |
| 向量嵌入 | `llama.cpp` standalone `llama-server` | 8089 | `qwen3-embed` 向量化 |
| OCR | `gateway/ocr_service.py` | 8091 | 扫描件/表格 OCR |
| 聊天后端 | LM Studio | 1234 | `qwen3.8-27b`（经 `config.json` 的 `bionic_base` 路由） |
| O2OA | docker 容器 | 9090 | 业务平台 |
| 自启 | `gateway/autostart/O2OA_AI_stack_autostart.vbs` | — | 登录时隐藏拉起看门狗 |

## 2. 持续化链路（开机 → 常驻）

```
Windows 登录
  └─ Startup\O2OA_AI_stack_autostart.vbs  (ASCII+CRLF，纯英文注释)
       ├─ 先按 *.pid 文件 taskkill 旧进程（防单例锁误留旧看门狗）
       ├─ Sleep 20s（等 GPU/系统就绪）
       └─ pythonw 隐藏拉起 watchdog_ai_stack.py
            └─ 看门狗循环：探活 embed/gateway/ocr → 任意 DOWN 则脱离式重启
```

要点：
- **看门狗是持续化的唯一锚点**。所有组件都由它拉起与看护，不在别处散养。
- **单例锁**：看门狗启动即写 `watchdog.pid`，第二实例检测到存活立即自退，杜绝「双击互杀」。
- **安全探活**：`pid_alive()` 用 `ctypes.OpenProcess + GetExitCodeProcess`，**绝不**用 `os.kill(pid,0)`（Windows 上等价于 `TerminateProcess`，会把加载中的组件误杀，导致反复 DOWN→重启抖动）。

## 3. 常用操作

```bash
# 启（开机自启会自动做；手动也行，重复双击安全）
双击 D:\O2OA\gateway\start_ai_watchdog.bat

# 停（看门狗 + 全部组件）
# 方式A：删 watchdog.pid 后 taskkill；或
powershell -c "Get-Process python | Stop-Process -Force"

# 状态
cat D:\O2OA\gateway\watchdog.pid
for p in 18790 8089 8091 9090 1234; do curl --noproxy "*" -s -o /dev/null -w "%{http_code} " http://127.0.0.1:$p/ ; echo ":$p"; done

# 看门狗日志
tail -f D:\O2OA\gateway\watchdog.log
```

## 4. 重启 O2OA 服务后必须做

O2OA 容器重启会重排网络，AI 栈虽不依赖 O2OA 但**断云封网规则需重跑**：

```bash
bash D:\O2OA\o2oa_netlock.sh    # 恢复外网隔离、保留 9090 宿主可达
```

## 5. 分支打包（代码级持久化）

AI 栈全部代码已纳管于 git。要「把目前运行的打包成分支」：

```bash
git -C D:\O2OA checkout -b feature/o2oa-ai-stack   # 从当前运行态切分支
git -C D:\O2OA add gateway/ docs/ tools/            # 含自启 VBS、运行手册、KB 合成文档
git -C D:\O2OA commit -m "ai-stack: 看门狗持续化 + 知识库沉淀"
```

克隆/恢复时：拉取分支 → 放置 `autostart/*.vbs` 到 `Startup\` → 双击 `start_ai_watchdog.bat` 即复现。

## 6. 已知坑（详见知识库 o2kb::troubleshooting::*）

- VBS 必须纯 ASCII + CRLF，中文注释会被 GBK 吞换行 → `800A01A8 缺少对象 'sh'`。
- `os.kill(pid,0)` 在 Windows 误杀进程，必须用 ctypes 安全探活。
- 沙箱内无法创建持久进程（schtasks/WMI 被拦），常驻只能由用户侧（双击/自启）完成。
- 本地探测一律 `curl --noproxy "*"`，否则 shell 代理（52068）伪装 502。
- 模型后端走 `bionic_base=http://127.0.0.1:1234`（LM Studio），非本地 8088。
