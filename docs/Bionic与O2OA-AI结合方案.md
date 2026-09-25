# Bionic（LM Studio 0.4）与 O2OA AI 结合方案

> 日期：2026-09-21　｜　实测环境：Windows + AMD Strix Halo（Vulkan 后端）
> 结论先行：**Bionic 与 O2OA 网关其实已经是"同一层"的东西**——两者都在做「OpenAI 兼容端点 + 工具循环 + MCP 消费」。
> 所以正确结合不是"把 Bionic 塞进网关"，而是**分层复用**：把 Bionic 当作 `推理供给层 + 工具/Agent 运行时`，
> 网关只保留 O2OA 专属的**数据接入层**（组织架构 / 待办 / 数据中心 / RAG 权限）。
> 本文给出 4 条可落地路径、实测证据、推荐方案与 PoC 代码。

---

## 项目总览与当前状态（2026-09-18 ~ 09-21 定稿）

> 本文档记录 O2OA AI 网关（`o2_agent_gateway.py` @ `:18790`）从「接 LM Studio 推理」到「借 Bionic agent 能力把 O2OA 智能化」的完整演进。
> 结论先行：**当前网关以 `qwen3.8-27b` 为推理模型、默认不联网（仅约束本网关，Bionic 本体不受影响）、按登录身份返回权限内数据、支持多步任务编排。**

**当前状态（2026-09-21，重启网关后 `/gateway/health` 实测 `chat_model=qwen3.8-27b` / `up=true`）**

| 项 | 值 |
|---|---|
| 推理模型 | `qwen3.8-27b`（vlm 视觉 / Q4_K_M / ctx 上限 262144 / 支持 `tool_use`）；实测加载 ctx 65536、parallel 2、占用 **17.74 GB** |
| 联网策略 | `web_enable=false`（两道闸：工具不注册 + 执行层硬拒）；**仅约束本 O2OA 网关，不影响 Bionic/LM Studio 自身联网** |
| 内置工具 | builtin 共 **31**（含 `web_search`/`web_fetch` 2 个）；`web_enable=false` 时注册 **29**（模型可见） |
| 多步编排 | `task_plan` / `task_run_step` / `task_rollback`（kv 账本，可查 / 可续 / 可回滚） |
| 权限闭环 | 前端 `wi.token`（服务端实填）贯穿为 `x-token`，O2OA 按身份返回权限内待办 / 数据表 / 公文（实测 52 张权限表） |
| 轮次 | `mcp_max_turns=20`（多步编排轮次消耗大，8/14 都会中途截断） |
| 角色人设 | `user` / `analyst` / `manager` 三档白名单；写回、回滚等破坏性操作限 `analyst` 以上 |

**演进时间线（第一 ~ 五批）**

| 阶段 | 日期 | 交付 | 当前状态 |
|---|---|---|---|
| 基础部署 | 09-18 | O2OA 容器化、外部 MySQL、断云六层防护、AI 网关端口 18790 打通 | 持续有效 |
| 第一/二批：接通 + 联网工具 | 09-19 ~ 09-21 | 本地 LM Studio 推理接通（glm-4.7-flash）；补 `web_search`/`web_fetch` 解决「模型拒答」；persona 白名单同步 | web 工具已建但**默认关断**（见第五批） |
| 第三批：角色人设 + 行动能力 | 09-20 | 向导/分析师/参谋三角色白名单；数据回写 + 白名单 + 审计日志；cookie 污染修复 | 持续有效（白名单见 §10.8） |
| 第四批：加固 | 09-21 | 多引擎降级链 + SSRF + 重试退避；`bionic_cli` 会话委派；工具循环熔断/异常隔离；`/gateway/capabilities` 自检 | 持续有效 |
| 第五批：定位纠偏 + 多步编排 | 09-21 | 关断联网（保留开关）；补 16 个 O2OA 内网工具；`task_plan`/`task_run_step`/`task_rollback` 多步编排 | 持续有效 |
| 收尾：换模型 + 权限闭环 | 09-21 | 换 `qwen3.8-27b`（多跳全收敛）；`_o2_call` 让登录 token 优先；`mcp_max_turns`→20 | 持续有效 |

> 文档「节号」与「批号」不完全对应：第 8 节 = 第一/二批落地，第 9 节 = 第四批，第 10 节 = 第五批；第三批未单列专节，其白名单机制贯穿 §10.8。

**关于「联网」的特别说明**：第四批把 `web_search`/`web_fetch` 打磨得可靠，但秘书长定位——「系统不应把公网数据搬入、应借 Bionic 能力在 O2OA 内落地」。故第五批起联网**默认关断**，能力全部保留，恢复仅需 `web_enable=true` 一行（见 §10.2）。工具数随批次增长：初版 13 → 加联网工具 15 → 第四批 16 → 第五批内网工具补厚后 31（含 web 2，web 关时注册 29）。

---

## 0. 先厘清概念：Bionic 到底是什么

用户提到"本地的 bionic 可以提供 cli、runtime、调用工具能力"。实测确认——**Bionic 是 LM Studio 0.4 起启用的新应用/运行时名称**，它不是单纯的"模型加载器"，而是一个完整的 **Agent 运行时**。

### 0.1 实测证据

| 证据 | 命令 | 结果 |
|---|---|---|
| Bionic 应用根目录 | `ls ~/.lmstudio/apps/bionic/` | 含 `projects/ conversations/ working-directories/ workspace/ user-files/ config-presets/` |
| 独立 CLI | `~/.lmstudio/bin/lms.exe --help` | `chat / load / unload / ls / ps / server / runtime / dev / clone / push` |
| 一次性 CLI 推理 | `lms chat -p "只回答两个字：你好"` | ✅ 正常返回（可直接当子进程后端） |
| Runtime 管理 | `lms runtime ls` | 13 个引擎：ROCm / Vulkan / CUDA / CPU（当前选中 Vulkan 2.41.0） |
| 服务器管理 | `lms server status` | `The server is running on port 1234.` |
| 模型能力自述 | `GET :1234/api/v0/models` | `"capabilities": ["tool_use"]`，`max_context_length: 202752` |
| **原生工具调用** | `POST :1234/v1/chat/completions` + `tools` | ✅ 返回 `tool_calls`，`finish_reason: "toolCalls"` |
| **原生 Agent 端点** | `POST :1234/api/v0/chat/completions` + `tools` | ✅ 同上，且附带 `stats`（tokens/s、TTFT）与 `runtime` 版本 |
| **原生 MCP 消费** | server-logs 里 `mcp` 命中 **209 次** | 已挂 `mcp_searxng_web_search`、`mcp_open-websearch_fetchWebContent`、`mcp_pi_research_engine` 等 |
| 内置工具插件 | `ls ~/.lmstudio/extensions/plugins/lmstudio/` | `js-code-sandbox`（JS 代码沙箱）、`rag-v1`（RAG 管道） |

### 0.2 关键认知（决定方案走向）

1. **Bionic 已经具备完整的工具调用循环**——`/api/v0/chat/completions` 原生吃 `tools`，且模型自述 `capabilities: ["tool_use"]`。
   这与网关 `from_mcp_loop()` 做的是同一件事。
2. **Bionic 已经是 MCP 客户端**——GUI 会话里已挂载 searxng / open-websearch / pi-research 等 MCP server。
   也就是说「联网搜索」「网页抓取」「深度研究」这些能力**你已经在 Bionic 侧拥有了**。
3. **Bionic 有内置代码沙箱**——`js-code-sandbox` 插件，这是网关当前**完全没有**的能力。
4. **但 Bionic 不知道 O2OA 的业务数据**——组织架构、待办、自定义数据表、带权限的 RAG，这些只在网关侧。

> **一句话总结：Bionic 强在「通用 Agent 能力（工具/沙箱/MCP 生态）」，网关强在「O2OA 业务数据与权限」。两者互补，不该互相替代。**

---

## 1. 现状：两条并行的工具链（问题所在）

```
                    ┌─────────────────────────────────────────┐
   浏览器 ──9090──> │ O2OA 容器 (x_ai 模块)                    │
                    └───────────────┬─────────────────────────┘
                                    │ POST /ai-gateway-completion/generate
                                    │ {generateType:auto|searchKnowledgeBase, input, ...}
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │ o2_agent_gateway.py  (:18790)           │
                    │  ├ from_mcp_loop()   ← 工具循环          │
                    │  ├ BUILTIN_TOOLS ×13 ← O2OA 业务工具     │
                    │  └ load_external_mcp() ← stdio/HTTP MCP │
                    └───────────────┬─────────────────────────┘
                                    │ POST /v1/chat/completions + tools
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │ Bionic :1234  (qwen3.8-27b)            │
                    │  ├ tool_use ✓                           │
                    │  ├ MCP 客户端 ✓  ← 但网关没用上！        │
                    │  └ js-code-sandbox ✓ ← 但网关没用上！    │
                    └─────────────────────────────────────────┘
```

**当前的问题**：

| 问题 | 现象（来自 `gateway.log` 实测） |
|---|---|
| **① 工具链重复** | 网关做了工具循环，Bionic 也能做工具循环；两边各一套，能力不共享 |
| **② Bionic 的 MCP/沙箱被浪费** | 你在 Bionic GUI 里配的 searxng / open-websearch / pi-research **在 O2OA 对话里完全不可达** |
| **③ 模型会"拒绝调用工具"** | 截图场景：问天气 → 模型答"我无法访问外部数据"。根因是**没给它 `get_weather` 这类工具**，它只能硬答 |
| **④ 工具 XML 泄漏** | 日志 `final answer leaked tool-call XML, retry once` —— glm 偶发把 tool_call 语法当文本吐出 |
| **⑤ 上下文被压到 64K** | 模型 `max_context_length=202752`，但 `loaded_context_length=65536`（欠配置） |
| **⑥ 网关无代码执行能力** | 复杂计算/数据处理只能靠 `calc` 单表达式，无法多步 |

---

## 2. 四条结合路径（按侵入性排序）

### 路径 A：Bionic 仅作推理供给层（当前形态的加固）　★ 成本最低

保持现状架构，只把 Bionic 的能力"用满"：

1. **换用 Bionic native 端点** `/api/v0/chat/completions`（而非 `/v1/`）——拿到 `stats`/`runtime` 元信息，便于排障。
2. **调大上下文**：`lms load qwen3.8-27b --context-length 65536`（够用且省显存；上限 262144），缓解长对话截断。
3. **补工具集**：把截图暴露的缺口补上（天气、联网搜索等），让模型"有话可答"。

- 改动面：`config.json` + 若干 `BUILTIN_TOOLS`
- 收益：中（解决截图里的"拒答"和截断）
- 风险：低

### 路径 B：网关反向消费 Bionic 的 MCP（把 Bionic 当 MCP 中枢）　★ 性价比最高

思路：**Bionic 侧已经配好的 MCP server，让网关直接连过去**。

```jsonc
// config.json — mcp_servers 增加 Bionic 同款 MCP
"mcp_servers": [
  { "name": "demo", "transport": "stdio", "command": "...", "args": [".../demo_mcp_server.py"] },
  // 新增：联网搜索（与 Bionic GUI 里同一套 searxng）
  { "name": "websearch", "transport": "stdio",
    "command": "npx", "args": ["-y", "open-websearch@latest"] },
  { "name": "searxng", "transport": "http", "url": "http://127.0.0.1:8888/mcp" }
]
```

- 工具名自动带前缀：`websearch__search`、`searxng__web_search`，模型可直接调用
- 改动面：仅 `config.json`（`load_external_mcp()` **已实现**，无需改代码）
- 收益：高（O2OA 对话瞬间获得联网搜索/网页抓取）
- 风险：低（MCP 子进程隔离，挂了不影响网关）

### 路径 C：Bionic CLI 作为「重型子进程工具」　★ 能力补强

把 `lms chat -p` 包成一个工具，让模型在需要「长推理 / 独立上下文」时委派出去：

```python
# 新增工具：bionic_cli —— 让模型把子任务丢给一个干净的 Bionic 会话
{
  "name": "bionic_cli",
  "description": "把独立的子任务交给本地 Bionic 模型单独处理（干净上下文、不污染当前会话）。"
                 "适合：长文分析、代码审阅、需要专注推理的子问题。",
  "parameters": {"type": "object", "properties": {
      "prompt": {"type": "string"},
      "system": {"type": "string", "description": "可选系统提示"}
  }, "required": ["prompt"]}
}
```

实现：`subprocess.run([lms.exe, "chat", "-p", prompt, "--ttl", "300"], timeout=180)`

- 收益：中高（相当于给 O2OA 助手加了一个"第二个大脑"）
- 风险：中（子进程启动慢、需管控并发；建议加超时与并发上限）

### 路径 D：Bionic 当主 Agent，网关降级为「数据 MCP」　★ 架构级重构

彻底反转：**让 Bionic 做 Agent 大脑，把 O2OA 业务能力做成 MCP server 暴露给它**。

```
用户在 Bionic GUI / CLI 对话
        │
        ├─ MCP: o2oa-data  → 组织架构 / 待办 / 数据中心 / 知识库(带权限)
        ├─ MCP: searxng    → 已有
        └─ 内置: js-code-sandbox → 已有
```

需要新写一个 `o2oa_mcp_server.py`（把网关现有 `BUILTIN_TOOLS` 用 MCP 协议重新暴露）。

- 收益：高（获得 Bionic 完整 Agent 能力 + 沙箱 + 全部 MCP 生态）
- 成本：中高（新写 MCP server；O2OA 对话入口要改成走 Bionic）
- 风险：中（脱离 O2OA 前端，用户体验变化大）
- **注意**：这条路**放弃了 O2OA 前端的会话/权限闭环**，适合"内部高级用户/开发者"场景，不适合替代现有助手。

---

## 3. 推荐方案：**B 为主 + A/C 为辅**（不动架构，收益最大）

```
O2OA 前端 ──> 网关 :18790 ──┬── /api/v0/chat/completions ──> Bionic :1234 (qwen3.8-27b, tool_use)
                            │                                    └─ 上下文实测加载 65536
                            ├── 内置工具 ×31（web 关时注册 29）
                            ├── 外部 MCP ×N  ← 复用 Bionic 同款 searxng/open-websearch   【路径B】
                            └── bionic_cli 工具 → lms.exe chat -p  (重型子任务委派)        【路径C】
```

**理由**：
- 网关已经是 O2OA 的**唯一接入点**，动它一处即可，O2OA 容器零改动（符合既有"能力开关单点"架构）。
- `<tool_call>` 泄漏、persona 白名单、写回二次确认、审计日志等**既有治理逻辑全部保留**——这些是路径 D 拿不到的。
- MCP 机制**已经实现**（`mcp_client.py` + `load_external_mcp()`），路径 B 几乎是纯配置。
- 风险可控：每个能力都能单独开关、单独回滚。

---

## 4. 分阶段落地计划

> 注：本计划落地时推理模型为 `glm-4.7-flash`；2026-09-21 已切换为 `qwen3.8-27b`（见 §10.7），下文 P0-1 / P1-1 中的模型名仅为当时记录。

| 阶段 | 内容 | 改动 | 验收 |
|---|---|---|---|
| **P0-1** | 上下文 64K → 128K | `lms load --context-length 131072` + 重启栈 | `/api/v0/models` → `loaded_context_length: 131072` |
| **P0-2** | 补"联网搜索"MCP（路径 B） | `config.json` 加 `mcp_servers` 条目 | `GET /gateway/capabilities` 出现 `tools__*`；问"今天北京天气"能真调工具 |
| **P0-3** | 补基础工具：`get_weather` / `http_fetch` | `BUILTIN_TOOLS` + `exec_builtin` | 截图场景复测：模型不再说"我无法访问外部数据" |
| **P1-1** | 切 Bionic native 端点 | `bionic_base` 走 `/api/v0` | 日志能看到 `stats.tokens_per_second` |
| **P1-2** | `bionic_cli` 子进程工具（路径 C） | 新增工具 + 并发/超时护栏 | 长文分析类任务可用 |
| **P2-1** | 工具 XML 泄漏加固（现有 retry 升级为 2 次 + 强制剥离） | `_final_answer_mcp()` | 日志不再出现泄漏后仍输出语法 |
| **P2-2** | （可选）路径 D PoC：`o2oa_mcp_server.py` | 新文件 | Bionic GUI 里能调 O2OA 待办 |

---

## 5. PoC 代码（可直接落地）

### 5.1 路径 B：配置即接入（零代码）

`config.json` 增加（示例，按你 Bionic 里实际的 MCP 命令替换）：

```json
"mcp_servers": [
  {
    "name": "demo",
    "transport": "stdio",
    "command": "C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
    "args": ["D:/O2OA/gateway/demo_mcp_server.py"]
  },
  {
    "name": "searxng",
    "transport": "http",
    "url": "http://127.0.0.1:8888/mcp",
    "timeout": 30
  }
]
```

验证：`curl :18790/gateway/capabilities` → `external_mcp` 里出现 `searxng`；日志出现
`mcp server 'searxng' loaded N tools: [...]`。

### 5.2 路径 C：`bionic_cli` 工具

在 `BUILTIN_TOOLS` 末尾加定义，并在 `exec_builtin()` 加分支：

```python
# ---- BUILTIN_TOOLS 追加 ----
{
    "name": "bionic_cli",
    "description": "把独立的子任务交给本地 Bionic 模型单独处理（干净上下文，不受当前会话干扰）。"
                   "适合：长文分析、代码审阅、需要专注推理的子问题。",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "交给 Bionic 的完整任务描述"},
            "system": {"type": "string", "description": "可选：角色/约束设定"},
        },
        "required": ["prompt"],
    },
},
```

```python
# ---- exec_builtin() 内追加分支 ----
if name == "bionic_cli":
    import subprocess
    lms = os.path.expanduser("~/.lmstudio/bin/lms.exe")
    if not os.path.exists(lms):
        return "bionic_cli 不可用：未找到 lms.exe"
    cmd = [lms, "chat", "-p", args.get("prompt", ""), "--ttl", "300", "-y"]
    if args.get("system"):
        cmd += ["-s", args["system"]]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        out = (p.stdout or "").strip()
        return out[:6000] if out else ("bionic_cli 返回为空: " + (p.stderr or "")[:300])
    except subprocess.TimeoutExpired:
        return "bionic_cli 超时（>180s）"
    except Exception as e:
        return f"bionic_cli 调用失败: {e}"
```

> ⚠️ 护栏：必须设 `timeout`；建议加"同一会话内至多调用 2 次"的计数上限，防止递归委派。

### 5.3 上下文调大（P0-1）

```bash
export HOME=/c/Users/meng_
LMS="$HOME/.lmstudio/bin/lms.exe"
"$LMS" unload --all
"$LMS" load glm-4.7-flash --context-length 131072 --gpu max
```

---

## 6. 风险与注意事项

| 风险 | 说明 | 缓解 |
|---|---|---|
| **显存/内存** | Strix Halo UMA 下 128K 上下文 KV cache 会显著增大 | 先试 96K；观察 `lms ps` 的 SIZE |
| **`lms chat` 子进程开销** | 每次调用要重新进入 CLI，冷启动慢 | 加 `--ttl`；或改用 HTTP 委派（向同端口发独立 `/api/v0` 请求） |
| **MCP 工具名冲突** | 外部 MCP 工具带 `{server}__` 前缀，天然避冲突；但**内置优先** | 已知行为，无需处理 |
| **persona 白名单会过滤新工具** | `persona_tools.user` 是显式列表，**新工具默认对 user 不可见** | 新增工具后同步更新 `persona_tools` |
| **`<tool_call>` 泄漏** | glm 系列偶发 | 已有 retry；建议加固到 2 次 + 强制剥离 |
| **Bionic 未常驻** | 当前 `qwen3.8-27b` 已 LOADED（TTL 24h，`--ttl 86400`），过期需重载 | 设 `jitModelTTL` 或按需重载 |

---

## 7. 结论

1. **Bionic 不是"另一个模型后端"，而是一个已经具备 Agent 运行时能力的平台**——工具循环、MCP 客户端、代码沙箱它都有。
2. **它与网关的重复点是"工具循环"**，互补点是"Bionic 有通用能力/生态，网关有 O2OA 业务数据与权限"。
3. **最优结合不是二选一，而是分工**：网关守住 O2OA 接入层与治理（权限/审计/写回），把**通用能力（联网搜索、代码沙箱、长推理）通过 MCP 与子进程委派复用过来**。
4. **落地成本极低**：路径 B 是纯配置（机制已实现），路径 C 约 30 行代码，路径 A 一条命令。
5. **截图里的"模型拒绝调用工具"**，本质不是模型不行（实测 `tool_use` ✓），而是**没给它对应的工具**——补上 `get_weather`/联网搜索即可根治。

---

## 8. 落地实施记录（2026-09-21 已完成并实测通过）

### 8.1 已完成的三项改动

| 项 | 改动 | 文件 |
|---|---|---|
| **P0-1 上下文扩容** | `lms load glm-4.7-flash -c 131072 --gpu max --ttl 86400`，64K → **128K**，常驻 24h | 运行时（`lms ps` 已确认） |
| **P0-3 补齐检索工具** | 新增 `web_fetch`（抓网页正文）+ `web_search`（Bing 搜索）两个内置工具 | `o2_agent_gateway.py` `BUILTIN_TOOLS` + `exec_builtin()` |
| **P0-4 persona 白名单同步** | 把两个新工具加进 `user`/`analyst` 白名单（否则新工具对普通用户不可见） | `o2_agent_gateway.py` `persona_tools` |

### 8.2 实测结果（截图场景复现）

**改造前**（截图）：
> 用户："你能调用工具查找北京今天的天气吗？"
> 模型："抱歉作为智能助手暂时无法直接为您访问外部实时天气预报数据……"

**改造后**（同问题实测）：
```
event: extend.status  clueId: chat-d7dde2c7-...
日志: tool get_current_time -> 2026-09-21 12:04:54 星期一
日志: tool web_fetch  url=https://www.weather.com.cn/weather/101010100.shtml -> HTTP 200
回答: 今天北京 晴 29/18℃；22日多云 28~19℃；建议防晒、注意降雨过程…
```

```
日志: tool web_search args={'query':'今日 科技 新闻…'} -> 搜索"…"结果（bing）：
```

**结论：模型已从"拒绝调用工具"变为"主动调用工具并给出真实数据"。**

### 8.3 关键技术发现（踩坑记录）

1. **搜索引擎选型必须适配国内网络**：实测 `cn.bing.com` = HTTP 200 可用；`html.duckduckgo.com` / `lite.duckduckgo.com` = **000 不可达**（国内网络屏蔽）。默认引擎已改为 Bing。
2. **`_client` 不能用于外网**：网关主客户端是 `httpx.Client(trust_env=False)`（专为本地端点），外网抓取必须另建
   `httpx.Client(trust_env=True, timeout=20, follow_redirects=True)` 才能走系统代理。
3. **Bing HTML 解析**：`<li class="b_algo">…<h2><a href="…">标题</a>` + `<p>摘要</p>`，严格正则命中 10 条；失败时用宽松
   `<h2><a href="http…">` 回落。
4. **`get_current_time` 是必要前置**：模型处理"今天"类问题会先取时间，再据此构造搜索/抓取 URL——这个工具不可省。
5. **升级路径要带上 persona 白名单**：新增工具若不同步 `persona_tools`，`user` 角色（普通员工）会看不到——
   这是设计上的显式白名单，不是 bug，但极易遗漏。

### 8.4 部署方式

```bash
# 1) 模型侧（如需重载大上下文）
export HOME=/c/Users/meng_
~/.lmstudio/bin/lms.exe load glm-4.7-flash -c 131072 --gpu max --ttl 86400 -y

# 2) 网关侧（重载新代码，先释放端口）
双击 D:\O2OA\gateway\restart_ai_gateway.bat
```

### 8.5 后续可选（尚未实施）

| 项 | 说明 |
|---|---|
| **P0-2 复用 Bionic 的 MCP** | `config.json` 的 `mcp_servers` 加入 searxng / open-websearch 等，即可获得更强的搜索与网页抓取 |
| **P1-2 `bionic_cli` 工具** | 子进程委派重型子任务（§5.2 已给出完整代码） |
| **P1-1 切 Bionic native 端点** | `bionic_base` 走 `/api/v0`，日志可带 `stats.tokens_per_second` |
| **P2-1 工具 XML 泄漏加固** | 现有 retry 1 次 → 2 次 + 强制剥离 |
| **P2-2 路径 D PoC** | `o2oa_mcp_server.py`，让 Bionic GUI 能调 O2OA 待办 |

---

## 附：本次实测证据清单

| 证据 | 命令 / 位置 | 结果 |
|---|---|---|
| Bionic 是 Agent 运行时 | `ls ~/.lmstudio/apps/bionic/` | `projects/ conversations/ workspace/ user-files/` |
| CLI 存在且可一次性推理 | `lms chat -p "..."` | ✅ 正常返回 |
| Runtime 可管理 | `lms runtime ls` | 13 引擎，选中 `llama.cpp-win-x86_64-vulkan-avx2@2.41.0` |
| 模型自述支持工具 | `GET :1234/api/v0/models` | `capabilities: ["tool_use"]` |
| 上/下文上限 | 同上 | `max_context_length: 202752`，改造后 `loaded: 131072` |
| GLM 原生 tool_calls | `POST :1234/v1/chat/completions` + tools | ✅ `tool_calls` + `finish_reason: toolCalls` |
| Agent 端点带统计 | `POST :1234/api/v0/chat/completions` | ✅ `stats.tokens_per_second=71.8` |
| Bionic 已消费 MCP | `grep -i mcp server-logs/2026-09-21.1.log` | 209 次命中，含 `mcp_searxng_web_search` 等 |
| Bionic 有代码沙箱 | `ls ~/.lmstudio/extensions/plugins/lmstudio/` | `js-code-sandbox`, `rag-v1` |
| 网关已有工具循环 | `o2_agent_gateway.py:1682 from_mcp_loop()` | 已有内置 + MCP 三类工具合并 |
| 网关已有 MCP 客户端 | `o2_agent_gateway.py:251 load_external_mcp()` | 支持 stdio / HTTP 双传输 |
| 网关工具实际执行成功 | `gateway.log` | `tool calc … -> 12373936.7` |
| KB 检索闭环成功 | `gateway.log` | 检索命中《财务报销新规》《会议室预约规则》 |
| 泄漏重试机制存在 | `gateway.log` | `final answer leaked tool-call XML, retry once` |
| **新工具已注册** | `GET :18790/gateway/capabilities` | `builtin_tools` 含 `web_fetch`、`web_search` |
| **新工具端到端可用** | `gateway.log` | `tool web_fetch … -> HTTP 200`；`tool web_search … -> 结果（bing）` |
| **国内搜索引擎选型** | `curl -o /dev/null -w %{http_code}` | `cn.bing.com`=200；`html.duckduckgo.com`=**000** |

---

# 第九节 第四批加固：从"能用"到"最强、最可靠"（2026-09-21 · 已实测）

承接第 8 节（`web_fetch`/`web_search` 首次落地）。第 8 节解决的是**有无**问题，
本节解决的是**稳不稳、强不强**问题——目标是把工具链从"晴天能用"做成"网络抖动、引擎宕机、
页面改版、模型打转时都还能给出**可信答案或可信失败**"。

## 9.1 设计原则：三个"不许"

| 原则 | 具体约束 | 落地手段 |
|---|---|---|
| **不许静默失败** | 工具挂了必须让模型知道"是网断了"，而不是"没有这回事" | 失败文案显式标注"网络/引擎侧故障，不是没有相关资料"+ 附可替代方案 |
| **不许硬答编造** | 没有联网能力时必须承认，不得凭记忆编造实时数据 | system 注入"你当前**没有**联网能力…严禁编造具体数值" |
| **不许原地打转** | 同参数重复调用、工具链失控必须被系统拦住 | 同签名调用 ≥3 次熔断 + 累计重复 ≥3 次中止循环 |

## 9.2 落地清单（4 项，全部实测通过）

### P1 联网检索可靠性 ── 多引擎降级链 + 重试退避 + SSRF 防护

**核心改进：引擎从"单个 Bing HTML 抓取"改为"可配置降级链"。**

```
searxng（本地自托管，返回结构化 JSON，最稳）
   ↓ 失败才降级
bing（HTML 兜底，含宽松正则防页面改版）
   ↓ 全失败
返回可读失败摘要（含每个引擎的失败原因）
```

实测收益（同一查询"北京天气"）：

| 引擎 | 返回条数 | 摘要质量 | 耗时 |
|---|---|---|---|
| **searxng**（本机 8080） | **17 条** | ✅ 有完整摘要 | 快 |
| bing（`cn.bing.com`） | 3 条 | ⚠️ 无摘要（仅标题+链接） | 中 |

**结论：SearXNG 结构化结果质量显著优于 HTML 抓取，现为首选引擎**（此前只用 Bing 是次优解）。

配套加固：

- **重试退避**：连接错误/超时/5xx/429 自动重试（默认 2 次，退避 1s/2s）；4xx 立即失败不浪费预算。
- **SSRF 防护**：默认拒绝内网/回环/保留地址与裸 IP，实测拦截 `127.0.0.1`、`localhost`、
  `192.168.1.5`、`10.0.0.1`、`8.8.8.8`，放行公网域名。可用 `web_allow_private=true` 放开。
- **域名黑名单**：`web_domain_deny` 后缀匹配。
- **HTML 清洗升级**：旧实现 `re.sub('<[^>]+>')` 会把 `<script>` 里的 JS 全留下；
  新 `html_to_text()` 先剔 script/style/noscript/svg/iframe/注释，块级标签转行保留段落感，
  再做实体归一化。实测输出干净无残留。
- **`mode` 参数**：`text` 抽正文（网页）/ `raw` 保留原文（API JSON），JSON 可自动识别。

### P2 `bionic_cli` 会话委派 ── 重型子任务丢进干净上下文

**这是本节最有设计价值的一项。** 把"需要专注推理的重型子任务"（长文摘要、代码审阅、
多步推理、大段资料归纳）交给一次**全新干净的模型会话**执行，取回结果继续作答。

**为什么这样做（关键取舍）**：

1. **收益在"干净上下文"，不在"换个模型"**。主对话可能已经很长（含大量工具返回的原文），
   把长文分析丢进独立会话，既不挤占主上下文窗口，也不会让主对话被中间过程污染。
2. **实现走 HTTP 而非真的 spawn `lms.exe chat`**。本机是 4GB 显存核显，
   反复冷启子进程代价过高；HTTP 复用**已加载**的模型，零额外显存、无进程开销。
   `lms` 路径已探测到（`~/.lmstudio/bin/lms.exe`）仅作兜底。
3. **三层限流防自伤**：
   - 单轮次数上限（默认 2）—— 防模型递归委派；
   - 全局并发闸（默认 2）—— 保护推理后端不被打爆；
   - 硬超时（默认 240s）+ 复用主链路 400/断流退避策略。

实测：委派"三点归纳成一句话"→ 61.6s 返回干净结果；第 3 次调用被正确拦截。

### P3 工具循环健壮性 ── 熔断 + 异常隔离 + 可观测

| 加固点 | 旧行为 | 新行为 |
|---|---|---|
| **同参数重复调用** | 一遍遍真执行，耗满 180s 超时 | ≥3 次拦截并回灌提示，逼模型换策略 |
| **累计重复过多** | 无 | ≥3 次即中止循环，强制收口 |
| **工具抛异常** | 打断整个循环 | try/except 隔离，降级为 `ERROR:` 文本回灌，循环继续 |
| **工具链观察** | 只有逐行日志 | 结构化 trace 落库 + `/gateway/trace` 接口 |
| **能力缺失表述** | 模型可能假装能联网 | 无 `web_search` 时 system 明确禁止编造 |

实测：熔断在第 3 次同参数调用起生效，且**不同参数不误伤**（计数恒为 1）。

### P4 能力自检 ── 一眼看出"哪个环节挂了"

`GET /gateway/capabilities` 新增：

- `web_search.engines[]`：**逐个引擎探活**（up / http / error），不再只报"整体可用"；
- `bionic_cli`：启用状态、模型、限额、并发占用、`lms` 是否找到；
- `config`：新增 `web_retry` / `tool_repeat_guard` / `trace_enable`。

## 9.3 实测证据（本次加固）

| 证据 | 命令 / 位置 | 结果 |
|---|---|---|
| 内置工具增至 16 个 | `GET /gateway/capabilities` | 含新增 `bionic_cli` |
| **双引擎均探活通过** | 同上 `web_search.engines` | `searxng` up=**200**、`bing` up=**200** |
| SSRF 防护生效 | `_url_guard()` 实测 6 例 | 5 拦截 / 1 放行（公网） |
| HTML 清洗彻底 | `html_to_text()` | 无 `var x=1`、无 `color:red`，正文完整 |
| searxng 结构化检索 | `_engine_search()` | **17 条**，含完整摘要 |
| bing 兜底可用 | 同上 | 3 条，标题+URL |
| 降级链生效 | `web_search_impl("北京天气")` | 走 searxng 返回 5 条 |
| `bionic_cli` 委派成功 | `bionic_cli_impl()` | 61.6s 返回归纳结果 |
| `bionic_cli` 限流生效 | 连续 3 次调用 | 第 3 次被拦截 |
| 熔断生效且不误伤 | 单元验证 | 第 3 次起拦截；不同参数恒为 1 |
| **端到端：天气场景** | `POST /ai-gateway-completion/generate` | 工具链 `get_current_time → web_fetch → feedback` |
| **端到端：新闻场景** | 同上 | 工具链 `web_search(searxng) → web_fetch(toutiao)` |
| **前后对比（同一查询）** | `gateway.log` | 12:03 `web_search … timed out` → 12:23 `搜索结果（引擎 searxng）` 0.8s |
| trace 可查 | `GET /gateway/trace` | 返回会话工具链，标注成功/失败 |

## 9.4 配置项（全部有默认值，可按需覆盖）

```jsonc
{
  "web_search_engines": [            // 有序降级链，前面的失败才用后面的
    {"name":"searxng","type":"searxng","url":"http://127.0.0.1:8080/search",
     "timeout":12,"enable":true},
    {"name":"bing","type":"html","url":"https://cn.bing.com/search",
     "timeout":15,"enable":true}
  ],
  "web_retry": 2,                    // 单引擎重试次数（共 retry+1 次）
  "web_retry_backoff": 1.0,          // 退避基数（秒），第 n 次等 backoff*n
  "web_allow_private": false,        // SSRF 防护开关（放开需显式确认）
  "web_domain_deny": [],             // 域名黑名单（后缀匹配）
  "web_fetch_max_chars": 6000,

  "bionic_cli_enable": true,
  "bionic_cli_timeout": 240,
  "bionic_cli_max_per_turn": 2,      // 单轮委派上限（防递归）
  "bionic_cli_max_concurrent": 2,    // 全局并发上限（护 4GB 显存后端）
  "bionic_cli_model": ""             // 空=复用 chat_model
}
```

## 9.5 仍未实施（建议优先级）

| 项 | 说明 | 建议 |
|---|---|---|
| **P3 原列的 MCP 注册协议闭环** | 网关 `/ai-gateway-mcp/*` 已可用（实测 list/get 通），O2OA 侧 `create/mcp` 会转发到网关。但 O2OA 的 `McpConfig` **不落 O2OA 库**（纯转发），MCP 配置存于网关 kv。若要让**前端 `extend.output` 卡片渲染**生效，还需补 `extra.template/script` 约定 | 中 |
| searxng 引擎健康巡检 | 目前每次 capabilities 才探活；可加看门狗周期探活，宕机自动摘除 | 低 |
| `bionic_cli` 结果缓存 | 同 prompt 短时重复委派可命中缓存，省一次推理 | 低 |
| native 端点 `/api/v0` 取 stats | 便于观测委派任务的 tokens/s | 低 |

## 9.6 韧性路径实测（"最强、最可靠"的验收标准）

"可靠"不等于"正常情况下能用"，而是**异常情况下仍给出可信答案或可信失败**。以下四条是验收底线，
全部实测通过（2026-09-21 晚复验）：

| 场景 | 构造方式 | 实测结果 | 结论 |
|---|---|---|---|
| **主引擎宕机自动降级** | searxng url 指向死端口 `127.0.0.1:59999` | 9.38s 后自动落到 bing，正常返回 3 条带摘要结果 | ✅ |
| **全引擎宕机** | 两个引擎 url 均改死 | 18.31s 后返回可读失败摘要，点名 `searxng: HTTP 502；bing: HTTP 502`，并明确告知"**这是网络/引擎侧故障，不是"没有相关资料"**"，同时建议改用 `web_fetch` 抓已知站点 | ✅ |
| **SSRF 防护** | `127.0.0.1` / `localhost` / `192.168.1.5` / `10.0.0.1` / `172.20.0.1` / `example.com` | 内网 5 例全部拦截（附 `web_allow_private=true` 放行提示），公网正常放行 | ✅ 5 拦 1 放 |
| **HTML 清洗质量** | 含 `<script>` `<style>` `<noscript>` `<iframe>` `<svg>` `<head>` + HTML 实体的页面 | 输出 `'标题\n正文&内容\n尾部'`，JS/CSS/标签零残留 | ✅ |

### 为什么"全引擎宕机的可读摘要"是关键

模型在工具返回 `ERROR: search failed` 时，**倾向于改用自身记忆编造数据**（幻觉），这比直接报错危险得多。
因此 `web_search_impl` 全挂时返回的不是错误码，而是一段**指令性文本**：

```
联网搜索暂时不可用（<query>）。已尝试的引擎：searxng: HTTP 502；bing: HTTP 502。
这是**网络/引擎侧故障，不是"没有相关资料"**。请如实告知用户检索通道暂时不可用，
或改用 web_fetch 直接抓取已知站点（如 https://www.weather.com.cn/... 查北京天气）。
不要凭记忆编造实时数据。
```

配合 `from_mcp_loop()` 在无 `web_search` 工具时注入的 system 声明（"你当前**没有**联网能力…
严禁凭记忆编造具体数值"），形成**双保险**：有工具但坏了 → 可读摘要劝退幻觉；没工具 → system 直接禁止。

### 端到端证据

| 时间 | 场景 | 工具链 | 结果 |
|---|---|---|---|
| 12:23 | 天气查询 | `get_current_time → web_fetch → feedback` | ✅ 给出具体数值 |
| 12:23 | 新闻查询 | `web_search(searxng) → web_fetch(toutiao)` | ✅ 带真实 URL |
| 12:26 | 新闻查询（复验） | `get_current_time → web_search → web_search` | ✅ |
| 对比 | 改造前 12:03 | `web_search timed out`（Bing HTML 抓取） | ❌ |
| 对比 | 改造后 12:23 | `结果（引擎 searxng）` | ✅ **0.8s** |

---

# 第十节 第五批：定位纠偏 —— 从"联网检索器"回到"Bionic 能力在 O2OA 内落地"（2026-09-21 · 已实测）

## 10.1 纠偏的由来

秘书长一句话定了方向：

> **"系统应该不能将网络的数据放入系统，只是将 bionic 的能力在系统中实现 agent 的各项功能"**

第四批把 `web_search`/`web_fetch` 打磨得很可靠，但那是**把公网数据搬进系统**——
与 O2OA 作为内网协同平台的定位是拧的：数据出了系统边界，权限闭环就断了，
知识库/待办/组织/动态表这些**真正属于本系统**的数据反而没被用起来。

本批做的三件事：
1. **联网默认关断**（保留开关与全部实现，一行配置即可恢复）；
2. **把系统内数据能力补厚**——待办流程、组织架构、数据表、公文、知识库全部打通；
3. **多步任务编排**——让 agent 能编排跨多步、跨数据源的系统内事务，可查、可续、可回滚。

## 10.2 联网的两道闸（默认关断）

| 闸门 | 位置 | 作用 |
|---|---|---|
| 第一道：不注册 | `builtin_tool_defs()` | `web_enable=False` 时把 `web_search`/`web_fetch` 从工具列表剔除 —— **模型根本看不见**，比"注册后拒绝"更干净 |
| 第二道：执行层拒绝 | `exec_builtin()` 开头 | 即便被手工塞入调用，也硬拒绝并指路内网工具 |

```json
// config.json —— 恢复联网只改这一行
"web_enable": false
```

**代码零删除**，`web_search_impl`/`web_fetch_impl`/多引擎降级链/SSRF 防护全部保留。

`/gateway/capabilities` 同时暴露两个口径，便于自检不谎报：

```json
"builtin_tools":     [...29 个, 不含 web_*],   // 实际注册（模型可见）
"builtin_tools_all": [...31 个, 含 web_*],     // 实现总量
"web_enable": false,
"positioning": "系统内数据闭环：Bionic agent 能力 + O2OA 业务数据（待办/组织/数据表/公文/流程），默认不联网"
```

## 10.3 内网数据地图（system 注入）

模型不知道"系统里有什么"就会乱猜。故在 `from_mcp_loop()` 注入一张数据地图，
并明确"没有联网能力、不得编造实时数据"：

```
【系统内数据地图（信息不足时按此顺序用足）】
  · 制度/文档/资料        → kb_search（本地知识库）
  · 业务台账/清单类数据   → query_rows。★ 严禁凭印象编造表名：
                            第一次查某张表前，必须先调 query_table_list
  · 我的任务              → list_my_todo → todo_detail；list_my_done 看已办
  · 人/部门               → search_org / org_unit_tree / org_person_identity
  · 流程与应用            → process_app_list
  · 公文/通知/制度文件    → cms_list → cms_detail 读正文
  · 附件/扫描件/图片      → ocr_file
```

## 10.4 新增内网工具（16 个）

| 分组 | 工具 | 实测结果 |
|---|---|---|
| 待办流程 | `list_my_todo` / `todo_detail` / `list_my_done` | 孟弋洁 5 条待办（合同草拟/任务分派/资产借用/信息发布/报销申请），详情含"可走路由：提交审核"+流转记录 |
| 组织架构 | `search_org` / `org_unit_tree` / `org_person_identity` | 顶层「中国复合材料工业协会」+ 4 下级部门；某人 3 个身份 |
| 数据表 | `query_table_list` / `query_rows` | **75 张自建表**；`where` 精确过滤 `o.archive_no='DA2026-001'` 得 3 行 |
| 公文信息 | `cms_list` / `cms_detail` / `cms_channels` | 1 篇文档 + **18 个信息栏目** |
| 流程应用 | `process_app_list` | **19 个流程应用** |
| 知识库 | `kb_read` / `ocr_file` | 5 篇文档列表 + 全文；OCR base64 通路 |

### 关键接口契约（逆向 war 内 Java 源码得出）

★ **必须以 war 内 `describe/sources/.../Action.java`（接口文件，非实现类）的
JAX-RS 注解为准** —— 猜路径必 404。本批纠正的坑：

| 用途 | 正确路径 | 我原先猜的（都错） |
|---|---|---|
| 自建表列表 | `POST {QRY}/table/list/paging/{page}/size/{size}` | GET `table/list/paging` |
| 表行分页 | `POST {QRY}/table/list/table/{flag}/row/paging/1/size/{n}` | GET |
| 公文列表 | `PUT {CMS}/document/filter/list/{page}/size/{size}` | `filter/list/0/next/{n}`（恒空） |
| 组织顶层 | `GET {ORG}/unit/list/top` | `unit/list/paging` |
| 人员模糊 | `PUT {ORG}/person/list/like` | `person/list/paging` |

### 两个必须记住的响应结构

```python
# 待办详情：数据是嵌套的
task/{id}/reference → data.task      # 标题在 activityName（title 常为 null！）
                    + data.work      # 表单数据
                    + data.attachmentList / data.workLogList
# 可走路由在 task.routeNameList（不是 manualRouteList）

# 公文详情：同样嵌套
cms/document/{id} → data.document    # 元数据
                  + data.data        # 表单数据（含 $attachmentList，正文藏在长字段里）
```

### 服务号不存在的静默失效（重要）

`网关服务号` 在本环境**并不存在**（`用户不存在或者密码错误`），
导致 `o2oa_token()` 返空 → **全部内网工具 HTTP 0，静默失效**（不报错，只是啥都查不到）。
修复：候选级联「服务号 → xadmin」回落，并把生效账号记入 `kv("o2oa_token_user")`，
在 `/gateway/capabilities.internal_capability.o2oa_login_user` 暴露（当前 = `xadmin`）。

### OCR 协议坑

`POST {ocr_base}/ocr` 吃 **base64 JSON**（`{"file_b64":..., "filename":...}`），
**不是 multipart** —— 用 multipart 会 400「缺少 file_b64 / image_b64 / pdf_b64」。

## 10.5 多步任务编排（target #35）

### 设计取舍：为什么不做独立 planner

4GB 显存不允许再起一份推理进程做 planner。故把**编排状态外置成任务账本**
（存 kv 表），由主模型按工具协议驱动。四个收益：

1. **零额外显存** —— 只花主模型 token，不占第二份 KV cache；
2. **可观测** —— 每步入参/结果/成败都落账本，可查；
3. **可续跑** —— 会话中断后凭 `plan_id` 恢复，长流程不必从头再来；
4. **可回滚** —— write 类步骤记录下发 id，失败时按逆序补偿。

与 `bionic_cli` 是**互补**关系：
`bionic_cli` 治「上下文污染」（把长文推理丢进干净会话），
`task_plan` 治「多步可靠性」（跨步状态、失败定位、回滚）。

### 三个工具

| 工具 | 作用 |
|---|---|
| `task_plan` | 计划账本：create（登记步骤）/ update（回填某步状态+结果）/ show / close / cancel |
| `task_run_step` | 逐步落地：read（表/知识库/公文/待办）/ write（受写回白名单+二次确认）/ notify_note |
| `task_rollback` | 回滚：对已成功的 write 步骤按**逆序**删除，破坏性操作需 `confirm=true` |

### 关键设计决策（都是踩坑后改的）

**① 参数必须全部平铺 —— 弱模型无法生成嵌套对象**

初版 `task_run_step` 用了嵌套 `params` 对象，实测 `glm-4.7-flash` **完全无法生成**：

```
kind = "read;params:{}{}{}}(待补充) - 修正参数格式并调用 query_table_list…"
```

它把整个对象拼进了 `kind` 字符串。改为**全平铺字段**后立刻正常：

```json
{"step_index":1, "kind":"read", "source":"table", "flag":"aiDemoOrders"}
```

同时加**宽容净化**：`kind` 只取开头第一个合法单词，而不是直接报错打断链。

**② 表标识必须硬护栏 —— 否则模型反复编表名**

模型会凭印象编 `__all_tables` / `o2oa_system_tables` / `demo orders`，每次都 HTTP 500，
既费轮次又给用户"系统里没这表"的**错误印象**。加真实性校验（60s 缓存全表清单）：

```
ERROR: 系统中不存在标识为 '__all_tables' 的自建表（未通过真实性校验）。
★ 不要猜测表名。请立即改用 query_table_list …
```

把一次注定失败的调用，转化成一次有效的自我纠正。

**③ 表清单必须支持 keyword 定向查找**

`query_table_list` 返回 75 行时，弱模型**看漏**了 `aiDemoOrders`（实测两次）。
加 `keyword` 过滤后 `keyword='order'` 只返回 1 行，一眼可见：

```
匹配「order」的自建表（1 张）。★ 查数据时 table_flag 用每行【】里的值：
[1] 【aiDemoOrders】　alias：aiDemoOrders　表名：AI演示订单表　应用：AI演示数据应用
```

并把输出形态从「按表名开头」改为「**按可用的 table_flag 开头**」——
模型心里想的是 alias，就该让它一眼看到 alias。

**④ 回滚抓手必须"写完就记"**

写接口只返回 `{"value":1}`（影响行数），**拿不到新行 id**。若等到回滚时才反查，
期间数据可能被改/增，反查就不唯一了。故写入成功后**立刻反查并落账本**
（`_row_locate` 要求恰好命中 1 行，0 行或多行都保守跳过，避免误删）。

**⑤ 类型感知的 jpql 字面量**

数字字段必须裸写，加引号会类型不匹配 → 恒 0 行：

```python
def _jpql_literal(v):
    if isinstance(v, (int, float)): return repr(v)   # o.amount=7   ✅
    return f"'{str(v).replace(chr(39), chr(39)*2)}'" # o.name='x'   ✅
# 反例：o.amount='7'  → 类型不匹配，恒 0 行（实测踩过）
```

### 编排指引只在"真需要多步"时下发

```
【多步任务编排】当一件事需要 3 步以上系统内操作才能完成时……先用 task_plan(action=create) 登记计划。
★ 简单问题（单次查询/计算/直接问答）不要建计划，直接答即可。
```

**实测判别正确**：问"现在几点了" → 工具链仅 `get_current_time`，**未建计划**；
问"盘点表数据并汇总" → 工具链 `task_plan → task_run_step → …`，按计划走。

## 10.6 实测证据

### 单元测试（15 组，0 失败）

覆盖：空计划友好报错 / create 参数与超上限校验 / 重复 create 阻止 /
update 状态与越界校验 / 三步状态流转 / 非法 kind 净化 / read 各 source 路由 /
write 生成预案 / rollback 二次确认 / cancel 后可重建 / 账本清理。

### 端到端写入→回滚闭环（真数据）

| 步骤 | 结果 |
|---|---|
| 建计划 → `task_run_step(write)` 不带 confirm | `CONFIRM_REQUIRED`（预案生成，未落库） |
| 同 payload 带 confirm=true | ✅ 写入成功，**已记录回滚抓手 row_id=fbbfa1bb…** |
| 反查确认 | 查到 1 行（`编排回滚验证品`, amount=7） |
| `task_rollback(confirm=false)` | `CONFIRM_REQUIRED`，列出将逆序删除的步骤 |
| `task_rollback(confirm=true)` | ✅ 已删除行 fbbfa1bb…，账本置 `rolled_back` |
| 复查 | **剩余 0 行** —— 补偿链路真实生效 |

测试后已把表恢复到原有 4 行，无测试污染残留。

### 端到端问答（走完整 LLM + 工具循环）

| 场景 | 工具链 | 结果 |
|---|---|---|
| 简单问题（几点） | `get_current_time` | ✅ 正确时间；**未过度规划** |
| 跨源汇总（待办+表清单） | `list_my_todo(fail) → query_table_list` | ✅ 75 表按应用分类；待办如实说明"需从前端会话发起"（未编造） |
| 多步盘点（表数据+汇总） | `task_plan → task_run_step → query_table_list → query_rows …` | ✅ 换上 `qwen3.8-27b` 后**完美收敛**（见 10.7） |

## 10.7 换模型：`glm-4.7-flash` → `qwen3.8-27b`（已验证收敛）

### 10.7.1 问题现象（换模型前）

多步盘点场景下 `glm-4.7-flash` **未能收敛**，表现为三连：

1. 把长描述塞进 `flag`（`"aiDemoOrderssmall2, or just use the alias…"`）；
2. 拿到正确的 `query_table_list(keyword='order')` 结果后，**转而调用错误的工具**
   （`query_data` 传 `'demo orders'` → HTTP 500）；
3. 轮次耗尽后**编造统计结果**（"系统显示该应用中包含多条数据"）。

**根因是模型能力天花板，不是编排代码缺陷** —— 同一套代码下：简单问题、跨源汇总、
`read/todo`（带身份）均**正确作答**；所有护栏、路由、账本、回滚**按设计工作**；
直接调用 API 层（`task_run_step_impl`）时多步链路**全部正确**。

### 10.7.2 模型库核对

LM Studio `:1234/api/v0/models` 共 17 个模型。**`qwen3.8:27b` 的真实标识是
`qwen3.8-27b`（短横线，不是冒号）**，LM Studio 里 `:` 是标签分隔符，REST 走短横线：

| 字段 | 值 |
|---|---|
| id | `qwen3.8-27b` |
| type | `vlm`（带视觉） |
| quantization | `Q4_K_M` |
| max_context_length | 262144 |
| capabilities | `["tool_use"]` ✅ |

另有 `bonsai-27b`（llm / Q1_0 / 同样支持 tool_use）可作备选。

### 10.7.3 切换步骤（三步，可复用）

```bash
# ① 卸载旧模型，释放显存（4GB 核显必须，两个 27B 不能同时常驻）
lms unload glm-4.7-flash

# ② 加载新模型（ctx 取 65536 而非 262144：够用且省显存）
lms load qwen3.8-27b --context-length 65536 --gpu max --ttl 86400

# ③ 改 config.json 并重启网关
#    "chat_model": "qwen3.8-27b"
#    "mcp_max_turns": 20        （多步编排需要更多轮次，用户要求调到 20）
```

实测占用 **17.74 GB**，ctx 65536，parallel 2。重启后
`GET /gateway/health` → `chat_model=qwen3.8-27b`，
`/gateway/capabilities` → `chat_backend.up=true`。

### 10.7.4 切换后实测（全绿）

| 场景 | 工具链路 | 结果 |
|---|---|---|
| **多跳2** 找表→查数 | `query_table_list(keyword=合同) → query_rows(合同主表)` | ✅ 4 张合同表全对（含物理表名），主表 **2 条**记录 + 明细（HT2026-001/002、金额、履行率） |
| **多跳3** 组织→人员 | `org_unit_tree → org_person_identity` | ✅ 协会 4 个部门及人数；综合管理部李芳；**主动说明"直属身份 2 但只匹配到 1 人"的数据不一致**（未编造） |
| **多步盘点** | `task_plan(create 4步) → task_run_step(source=tables) → update → task_run_step(source=table,limit=100) → update → calc → update×2 → close` | ✅ 4 行明细 + 正确求和 **590.5** + 占比分析 |
| 简单问题（几点） | `get_current_time` | ✅ **未过度规划** |
| 跨源汇总 | `list_my_todo(fail) → query_table_list` | ✅ 75 表按应用分类；待办如实说明需前端身份（未编造） |

**结论：弱模型上的 4 条坑（无法生成嵌套对象 / 凭印象编表标识 / 长清单看漏 /
多跳轮次耗尽即编造）在 `qwen3.8-27b` 上全部消失。**

### 10.7.5 安全边界（重要）

> **以上所有改动仅在 `D:\O2OA\gateway\o2_agent_gateway.py` 一个文件内（O2OA 侧）。**
> **Bionic / LM Studio 自身的联网能力从未被触碰** —— `~/.lmstudio/` 目录无任何我方写入，
> 只执行过 `lms load/unload` 运行时操作（非修改）。切断联网是本系统的**内部策略**，
> 不影响 Bionic 作为通用 Agent 运行时对外使用。

## 10.8 配置项

```json
"web_enable": false,              // 联网总开关（一行恢复）；仅约束本网关
"o2oa_user": "xadmin",            // 服务号不可用时的回落账号
"o2oa_pwd": "o2oaadmin2026",
"orchestrator_enable": true,
"orchestrator_max_steps": 12,
"orchestrator_ttl": 7200,
"orchestrator_rollback": true,
"chat_model": "qwen3.8-27b",      // ★ 换模型（原 glm-4.7-flash）
"mcp_max_turns": 20               // ★ 多步编排需更多轮次（原 8；用户要求调到 20）
```

persona 白名单同步（★ 新增工具必须同步，否则对应角色看不见）：
`user` 23 项（含 `task_plan`/`task_run_step`，不含 `task_rollback`——破坏性操作限分析师以上）
`analyst` 27 项（含 `task_rollback`）；`manager` = None（不限）。

## 10.9 登录态与权限闭环（用户要求：根据身份访问对应权限项目和资料）

**结论：本网关已经「按登录身份访问权限数据」的完整闭环，无需新写接口——关键是让 `wi.token`
（O2OA 服务端实填的用户会话 token）贯穿到每一次 O2OA REST 调用。**

### 身份链路（已实测打通）

```
O2OA 前端（用户已登录）
  └─ AI 助手 → x_ai 模块 ActionChat 代理转发，POST /ai-gateway-completion/generate
       wi.person = 服务端 effectivePerson（DN，前端不可伪造）
       wi.token = 服务端实填的用户会话 token   ★ 权限闭环的关键
  └─ 网关 generate() 取出 usertoken，一次 o2_user_info(usertoken) 取角色/DN/姓名
  └─ from_mcp_loop / exec_builtin → 各 impl → _o2_rest / _o2_call
       ★ 全部以 x-token: usertoken 调 O2OA REST
  └─ O2OA 服务端按该 token 的权限强制过滤 → 用户只看到「自己有权看」的待办/数据表/公文
```

### 实测证据（2026-09-21，绕开 shell 代理直连 localhost）

- `POST /jaxrs/authentication`（xadmin 凭据）→ 200，DN `xadmin@o2oa@P`，拿到 token
- `GET  /jaxrs/authentication`（带该 token）→ 200，返回 `roleList`（xadmin 4 个系统角色）
  → 印证 `o2_user_info` 解析 `data.roleList` 正确；此前 `孟弋洁` 的 `roles=[]` 是该用户**真实无角色**，
    故 persona 默认回退 `user`（设计正确，非 bug）
- `GET  /x_processplatform.../task/list/my/paging`（带 token）→ 200，返回该用户本人待办（xadmin=0 条）
- `POST /x_query_assemble_surface/jaxrs/table/list/paging`（带 token）→ 200，返回 **52 张**权限内数据表
  ★ 注意路径是 `surface` 模块（非 `designer`）；新建表的动态实体类加载滞后会 ClassNotFoundException，
    故写回/读新表优先走 designer（见 10.4）

### 本轮代码修复（让权限闭环更干净）

- `o2_agent_gateway.py` 的 `_o2_call` 原先在「同时收到 person(DN)+token」时会多余地执行
  `switchuser(credential=<DN>)`（DN 不是 switchuser 凭据，逻辑错位）。
  **改为：token 非空时直接以本人身份调用（x-token: token），跳过 switchuser；**
  switchuser 仅保留给「无用户 token、仅凭 person 名模拟指定人」的管理视角（参谋查他人待办）。
- `config.json`：`mcp_max_turns` 14 → **20**（用户要求；多步编排轮次消耗大，8/14 都会在中途被截断）。

### 前端怎么用

用户从 O2OA 前端智能助手入口正常提问（如「我有哪些待办」「盘点一下订单表数据」），
网关即以其登录身份执行：只返回该用户权限范围内的待办、数据、公文，**不会越权看到他人或管理员数据**。
（测试脚本走协议层、无登录态时会如实提示「请从前端入口发起」，属预期行为，非缺陷。）

---

## 第十一节 Phase A：设计态能力（创建/修改 门户页·动态表·数据应用·门户）

> 用户原问「AI 能创建/修改流程、表单、应用吗？只要有审核机制就可以了吗？」
> 结论：**审核是必要不充分条件**。O2OA 的 designer REST 全开放（门户/页面/数据应用/动态表/流程应用均可建改删），
> 若 AI 直接以管理员身份落库，一次越权或幻觉就能改写生产结构。故采用**四层安全闸**，而非单一"事后审核"。

### 11.1 四层安全闸（核心设计）

1. **角色闸门**：`design_personas=["manager","analyst"]`，普通向导用户根本看不到工具（persona 白名单过滤）。
2. **草稿不落地**：`design_op(confirm=false)` 只生成 `CONFIRM_REQUIRED` 提案文本，**不改动任何系统**。
3. **过程授权**：无静态 deny-all 白名单；人类在对话里明确同意提案（`confirm=true`）本身即授权——按需而动，零预置清单。
4. **落地前快照 + 审计 + 可回滚**：update/delete 前先 GET 当前定义存账本；执行后落 `audit_log`；并写 `design_rollback` 账本，可两步回滚。
   - 系统级硬底线：`design_denylist`（如 `a0000000-common-dict-app`）命中即拒绝，任何角色都碰不了系统应用。

### 11.2 代码落点（`D:\O2OA\gateway\o2_agent_gateway.py`）

- 工具定义：`BUILTIN_TOOLS` 新增 `design_op` / `design_rollback`（参数全平铺，防弱模型把嵌套对象拼进字符串）。
- 配置：`DEFAULT_CFG` 新增 `design_enable` / `design_personas` / `design_denylist` / `design_confirm_ttl(=600)`。
- 分发：`exec_builtin` 新增 `if name=="design_op"` / `if name=="design_rollback"` 两分支。
- 实现：`design_op_impl` / `design_rollback_impl` + 辅助 `_design_rest_map` / `_design_snapshot_path` / `_design_double_escape` / `_design_proposal_text`。
- 白名单：`persona_tools["analyst"]` 追加 `design_op`/`design_rollback`（`manager=None` 全量可见）。
- 可视：`/gateway/capabilities` 的 `internal_capability` 新增"设计态"分组，`config` 段暴露 `design_*` 开关。
- 语法校验：`python -m py_compile o2_agent_gateway.py` 已通过。

### 11.3 四类操作映射（designer REST，逆向 war 内 Java 源码得出）

| kind | create | update | delete |
|---|---|---|---|
| portal（门户） | `POST /x_portal_assemble_designer/jaxrs/portal` | `PUT .../portal/{id}` | `DELETE .../portal/{id}` |
| page（门户页） | `POST .../page?portalId={parent_id}` | `PUT .../page/{id}`（data 双层转义） | `DELETE .../page/{id}` |
| data_app（数据应用） | `POST .../query` | `PUT .../query/{id}` | `DELETE .../query/{id}` |
| dynamic_table（动态表） | `POST .../table`（draftData 必须字符串 `{"fieldList":[...]}`）→ 续跑 `table/{id}/status/build` → `table/query/{appId}/build` → `table/reload/dynamic` | `PUT .../table/{id}` | `DELETE .../table/{id}` |

### 11.4 生效方式

改动仅限 `o2_agent_gateway.py`，**需重启 AI 栈网关进程**（双击 `start_o2oa.bat` 或对应 VBS 启动器）才能加载新代码。
重启后可用 `GET /gateway/capabilities` 的 `internal_capability.groups["设计态"]` 与 `config.design_*` 核验已加载。

