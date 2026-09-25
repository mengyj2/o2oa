# MCP 生态接入 + 自主技能（skills）实施报告

日期：2026-09-19 ｜ 状态：**已完成，端到端实测 5/5 通过**（本地引擎栈）

---

## 0. 结论速览

| P0 项 | 状态 | 说明 |
|---|---|---|
| 标准 MCP client | ✅ | `mcp_client.py`：stdio（Content-Length 帧）+ HTTP（JSON-RPC POST）双传输，`tools/list` 动态注入 `from_mcp_loop()` |
| skills 自主能力 | ✅ | `skills_list / skills_get / skills_create / skills_run` 四工具 + `gateway/skills/` 仓库，模型可自主发现/创建/执行技能 |
| （此前已完成） | ✅ | 启动链三件套 / 内置工具集 / 多模态 / OCR / 查询改写+rerank 均已在线 |

**最终架构（用户决策：放弃 8090 Bionic/LM Studio 路由，回归本地引擎直连）**

```
O2OA 前端 ──> 网关 :18790（唯一入口，鉴权+协议翻译+工具循环）
                 ├─ chat    :8088  llama-server Qwen3.5-4B（--mmproj 视觉，tool_calls 原生）
                 ├─ embed   :8089  Qwen3-Embedding-0.6B
                 ├─ rerank  :8092  bge-reranker-v2-m3（RAG 精排）
                 ├─ OCR     :8091  RapidOCR（扫描/表格/PDF，纯 CPU 零显存）
                 ├─ 内置工具 ×10（含 skills_* ×4）
                 ├─ O2OA HTTP 型 MCP（前端 McpConfig 配置）
                 └─ 标准 MCP 生态（config.mcp_servers，stdio/HTTP）
                      └─ demo server：echo / add（示例，可换成任意 MCP server）
```

---

## 1. 标准 MCP client（`gateway/mcp_client.py`）

### 实现要点
- **stdio 传输**：子进程 + LSP 帧（`Content-Length: N\r\n\r\n` + UTF-8 JSON），独立读线程解析响应，`queue` 按 id 配对；支持通知（`notifications/initialized`）。
- **HTTP 传输**：POST `application/json` JSON-RPC（最简形态，覆盖大多数桥接实现）。
- **握手**：`initialize`（protocolVersion `2024-11-05`）→ `notifications/initialized` → `tools/list`。
- **连接复用**：模块级 `_clients` 缓存，进程死了自动重连；`shutdown_all()` 兜底。
- **防冲突**：外部工具名加前缀 `{server}__{tool}`（如 `demo__add`），天然与内置/O2OA 工具隔离。
- **调用**：`tools/call` → 解析 `content[].text` 拼接；`isError` 时加 `TOOL_ERROR:` 前缀。

### 注入路径（`from_mcp_loop()` 三源合并）
```
内置工具（10 个，含 skills_*）  ── 优先
O2OA HTTP 型 MCP（kv 表 mcp:*）── 次之（同名跳过）
标准 MCP 生态（config.mcp_servers）── 前缀名，直接合并
        ↓
分发顺序：builtin → ext_dispatch（标准 MCP）→ O2OA HTTP MCP
```

### 配置（`config.json`）
```json
"mcp_servers": [
  { "name": "demo", "transport": "stdio",
    "command": "C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
    "args": ["D:/O2OA/gateway/demo_mcp_server.py"] },
  { "name": "xxx", "transport": "http", "url": "http://127.0.0.1:xxxx/mcp",
    "headers": { "Authorization": "Bearer ..." } }
]
```
接入任意真实 MCP server（文件系统、fetch、sqlite 等）只需加一条配置，无需改代码。

---

## 2. skills 自主技能

### 仓库格式
`gateway/skills/<name>.md`，frontmatter 头 + markdown 正文：
```
---
name: meeting_minutes
description: 将会议记录/口述要点整理为结构化纪要
---
# 指引正文（模型执行时遵循的步骤）
```

### 四个工具（已入 BUILTIN_TOOLS，mcp 模式自动可用）
| 工具 | 作用 |
|---|---|
| `skills_list` | 列出全部技能（名称+一句话说明） |
| `skills_get` | 读取某技能完整内容 |
| `skills_create` | 创建新技能（模型可自主固化流程） |
| `skills_run` | 应用技能：返回指引正文，模型据此执行（可继续调用其他工具） |

预置示例：`meeting_minutes`（会议纪要）、`weekly_report`（周报，e2e 测试中由模型自主创建）。

---

## 3. 本轮踩坑与修复（重要）

### ★ 坑1：e2e 测试字段名 —— `input` 不是 `prompt`
网关 `generate()` 读 `wi.get("input")`。测试脚本发 `prompt:` 字段 → 网关拿到空字符串 → 模型收到空 user 消息只会输出寒暄能力清单，**且完全看不出报错**。现象极具迷惑性（响应正常 200、模型正常回答）。

### ★ 坑2：最终回答泄漏 `<tool_call>` XML 文本
工具循环全部正确执行后，最终流式回答阶段模型（尤其 27B 级）可能把工具调用意图**以 XML 文本**吐给用户。三层防护（全部已实装）：
1. system 后缀追加"工具调用已结束"指令（原有）；
2. 循环结束**追加最后一条 user 强指令**（模型对最近 user 指令服从度最高）；
3. **mcp 模式最终回答先缓冲不下发** → 检出 `<tool_call`/`<function=` 泄漏 → 追加强指令重试一次 → 仍泄漏则正则剥离 → 剥完为空回退为"工具结果摘要"。下发给 O2OA 前端后无法撤回，必须先净场。

### ★ 坑3：后端瞬时 400 —— "Model is unloaded"
LM Studio JIT 换载/引擎崩溃窗口（`Engine protocol startup was aborted`）会让请求 400。原逻辑一次失败即放弃 → 最终回答退化为空。修复：
- 工具循环内模型调用**指数退避重试**（等待 0/2/10/20s，给 27B 重载时间），400 响应体记入日志；
- 流式 `collect()` 同样退避重试（0/3/15s）+ `raise_for_status()` 使非 200 不再静默产出空回答。
> 注：该问题仅在 8090 LM Studio 路由出现；回归本地 llama-server 直连后未再复现。但重试机制保留，对任何后端的瞬时抖动都有韧性。

### ★ 用户决策：8090 弃用
qwen3.8-27b 经 LM Studio 路由 JIT 加载不稳（连续 `Failed to load model`），**已回归本地引擎直连**：`config.json` 改回 `bionic_base=8088 / chat_model=qwen3.5-4b`。收益：工具循环延迟从 60-80s/轮 降到 **4-18s/轮**，且无 JIT 崩溃。

---

## 4. 端到端实测（2026-09-19 18:00，本地引擎栈，5/5 通过）

| # | 提问 | 工具执行 | 回答要点 |
|---|---|---|---|
| 1 | 现在几点？列出可用技能 | `get_current_time` + `skills_list` | 时间正确；两个技能带说明列出 |
| 2 | 用 demo__add 算 3+39 | `demo__add`（**外部 stdio MCP**） | **42**（4.4s） |
| 3 | 按 meeting_minutes 整理会议记录 | `skills_run` | 严格按技能结构输出：概况表/决议/待办表/待确认事项 |
| 4 | 创建 weekly_report 技能 | `skills_create` | "已成功创建"，无 XML 泄漏 |
| 5 | 再列一次技能 | `skills_list` | 两个技能齐全 |

能力自检：`chat up tool_calls=true vision=true` / `embed up` / `ocr up` / skills 2 个 / ext_mcp demo(stdio)。

## 5. 文件清单

- NEW `gateway/mcp_client.py` —— 标准 MCP client（stdio+HTTP）
- NEW `gateway/demo_mcp_server.py` —— 最小 MCP stdio server（协议测试/示例）
- NEW `gateway/skills/meeting_minutes.md`、`weekly_report.md`
- NEW `gateway/e2e_mcp_skills.js` —— 端到端五项测试
- MOD `gateway/o2_agent_gateway.py`：
  - import mcp_client；`from_mcp_loop` 三源合并 + 分发路由
  - `BUILTIN_TOOLS` 增至 10 个（含 skills_* ×4）；`exec_builtin` 增 skills 分支
  - `_final_answer_mcp()` 防泄漏管线；`stream_openai` 加 `raise_for_status`
  - 工具循环模型调用指数退避重试；`/gateway/capabilities` 增加 `skills`/`external_mcp`
- MOD `gateway/config.json`：`mcp_servers` 数组；`bionic_base=8088`、`chat_model=qwen3.5-4b`（回归本地引擎）

## 6. 后续（P1/P2）
- 混合检索（向量+关键词）：P2，待做。
- 接入真实业务 MCP server（如文件系统/网页抓取）：改 `config.json` 即可。
- Agent Harness：按用户指示继续后置。
