---
name: o2oa-bionic-agent-bridge
agent_created: true
description: 把本地 Bionic（LM Studio 0.4+ 的 Agent 运行时）的 CLI / runtime / 工具调用能力接进 O2OA AI 网关；并根治"模型拒绝调用工具只能硬答""工具调了但没数据""外网抓取超时"等工具链问题。当用户问"bionic 能提供 cli/runtime/工具调用，怎么和 O2OA 结合""怎么让 AI 助手能联网查资料""助手说无法访问外部数据""模型不调用工具""web_search 超时/无结果""llm 上下文太小""lms 怎么加载模型/管后端"时调用。
category: integration

---

# O2OA × Bionic Agent 能力桥接

## 核心认知（先读这段，避免误判）

**Bionic = LM Studio 0.4+ 的 Agent 运行时**（不只是模型加载器）。实测它已具备：
- 独立 CLI：`~/.lmstudio/bin/lms.exe`（`chat / load / unload / ls / ps / server / runtime`）
- Runtime 管理：ROCm / Vulkan / CUDA / CPU 多引擎切换
- **原生 tool_use**：`GET :1234/api/v0/models` → `"capabilities": ["tool_use"]`
- **原生 MCP 客户端**：GUI 会话可挂 searxng / open-websearch / pi-research 等
- **内置代码沙箱**：`~/.lmstudio/extensions/plugins/lmstudio/js-code-sandbox`

**所以 Bionic 与 O2OA 网关的"工具循环"是重复能力，不是互补。**
正确分工：**网关守住 O2OA 接入层与治理（权限/审计/写回/RAG），通用能力（联网/沙箱/长推理）通过工具与 MCP 复用。**

## 关键事实（2026-09-21 实测）

| 项 | 值 |
|---|---|
| Bionic 应用根 | `~/.lmstudio/apps/bionic/`（含 `projects/ conversations/ workspace/`） |
| CLI 路径 | `~/.lmstudio/bin/lms.exe`（**不在 PATH**，用绝对路径） |
| 端点 | `:1234`；`/v1/chat/completions`（OpenAI 兼容）、`/api/v0/chat/completions`（native，带 stats） |
| 上下文 | 模型 `max_context_length` 可达 202752；默认只加载 65536 —— **必须显式调大** |
| `lms load` TTL | `--ttl` 最小 1，**不接受 -1**；要常驻用 `--ttl 86400` |
| 搜索端点 | `cn.bing.com`=200 可用；`html.duckduckgo.com`=**000 不可达**（国内网络） |
| 网关外网客户端 | `_client` 是 `trust_env=False`（只给本地端点）；外网必须另建 `trust_env=True` |

## 症状 → 处置速查

| 症状 | 根因 | 处置 |
|---|---|---|
| 助手说"我无法访问外部数据/无法查询实时信息" | **没给它检索类工具**（不是模型不行） | 加 `web_fetch` / `web_search` 内置工具，并同步 `persona_tools` 白名单 |
| 工具调了但返回超时/空 | 搜索端点在国内不可达（DuckDuckGo 类） | 换 `cn.bing.com`；**更优：改用本地 searxng**（字符串化 JSON，见下） |
| **搜索结果只有标题没摘要** | 用的 HTML 引擎（Bing），解析不到 `<p>` | 改用 `type=searxng` 引擎，`content` 字段自带摘要 |
| 长对话后报错/截断 | 上下文只加载了 65536 | `lms load <model> -c 131072 --gpu max --ttl 86400 -y` |
| 普通员工看不到新工具 | `persona_tools.user` 是显式白名单 | 把新工具名加入 `user`/`analyst` 列表 |
| 模型把 `<tool_call>` 当文本吐出 | 最终流式请求没带 tools | 网关已有 retry；必要时加固到 2 次 + 强制剥离 |
| **模型反复用同样参数调同一工具** | 模型陷入原地打转 | 网关已内置熔断（同签名 ≥3 次拦截）；确认阈值与"不同参数不误伤" |
| **模型假装能联网、编造实时数据** | 工具被 persona 裁剪后 system 仍暗示有联网能力 | 无 `web_search` 时注入"你当前没有联网能力…严禁编造" |
| `lms load -c` 报 "argument '-1' is invalid" | `--ttl` 不接受 -1 | 用 `--ttl 86400` |
| `/gateway/*` 报 `bad token` | 鉴权只认 `Authorization` 头（`auth.endswith(token)`） | 用 `-H "Authorization: Bearer <token>"`，别用 `token:`/`x-token` |

## 可靠性设计范式（把"能用"做成"可靠"）

三条铁律，加工具时逐条自检：

1. **不许静默失败** —— 工具挂了要明说"是网断了"，不是"没这回事"。
   失败文案应包含：① 明确归因（网络/引擎侧）② 已尝试的动作 ③ 可替代路径。
   > 反例：`return "未找到相关结果"` → 模型会当成"事实不存在"直接下结论。
2. **不许硬答编造** —— 能力缺失时在 system 显式声明，禁止编造具体数值。
3. **不许原地打转** —— 同签名调用计数 + 熔断；工具异常 try/except 隔离，不打断整个循环。

### 多引擎降级链（搜索类工具的标配）

```
searxng（本地自托管、结构化 JSON、带摘要）  ← 首选
   ↓ 失败才降级
bing / html 型（宽松正则兜底，防页面改版）
   ↓ 全失败
返回可读失败摘要（含每个引擎的原因）
```
实测同查询对比：searxng **17 条带摘要** vs bing 3 条无摘要 → **优先 searxng**。

### 外网工具的必备防护

- **SSRF**：默认拒绝 `127.`/`10.`/`192.168.`/`172.16-31.`/`localhost`/裸 IP。放开需显式开关。
- **重试退避**：连接错误/超时/5xx/429 才重试；4xx 立即失败（别浪费超时预算）。
- **HTML 清洗**：先剔 `script/style/noscript/svg/iframe/注释` 再剥标签，
  否则 JS/CSS 会污染正文（`re.sub('<[^>]+>')` 单独用是不够的）。
- **JSON 自动识别** —— 别把 API JSON 当 HTML 洗。

### 子任务委派（`bionic_cli` 型工具）的取舍

**收益在"干净上下文"，不在"换个模型"**：主对话已很长时，把长文分析丢进独立会话，
既不挤主上下文、又不污染主链路。**实现走 HTTP 复用已加载模型**（尤其 4GB 显存机器——
反复 spawn `lms.exe chat` 代价过高），`lms` 仅作兜底。
必须三层限流：单轮次数（防递归委派）+ 全局并发（护后端）+ 硬超时。

## 标准工作流

### 1. 能力侦察（先取证，别猜）
```bash
export HOME=/c/Users/meng_          # Git Bash 下必须，否则 lms 找不到配置
LMS="$HOME/.lmstudio/bin/lms.exe"
"$LMS" ps                            # 已加载模型 + CONTEXT 值
"$LMS" server status                 # 端口
"$LMS" ls                            # 磁盘模型清单
curl --noproxy "*" -s -m5 http://127.0.0.1:1234/api/v0/models | \
  python -c "import sys,json;[print(m['id'],m.get('capabilities'),m.get('loaded_context_length')) for m in json.load(sys.stdin)['data'] if m.get('state')=='loaded']"
```

### 2. 调大上下文（最容易被忽略、收益最大）
```bash
"$LMS" load glm-4.7-flash -c 131072 --gpu max --ttl 86400 -y
# 先用 --estimate-only 估算资源，避免爆显存
"$LMS" load glm-4.7-flash -c 131072 --estimate-only
```

### 3. 补检索工具（根治"拒绝调用工具"）
在 `D:\O2OA\gateway\o2_agent_gateway.py`：
1. `BUILTIN_TOOLS` 加 `web_fetch`（抓网页正文）与 `web_search`（多引擎检索）定义
2. `exec_builtin()` 加对应分支（薄壳，实现在 `web_*_impl()`）
3. **同步 `persona_tools` 的 `user`/`analyst` 白名单**（漏了则普通用户不可见）
4. 外网请求必须新建 `httpx.Client(trust_env=True, ...)`，
   **不要用网关的 `_client`**（它是 `trust_env=False`，只服务本地端点）

### 4. 验证（必须端到端，不能只编译）
```bash
TOK=$(python -c "import json;print(json.load(open('D:/O2OA/gateway/config.json'))['token'])")
curl --noproxy "*" -s -m 60 -H "Authorization: Bearer $TOK" \
  http://127.0.0.1:18790/gateway/capabilities   # 看 builtin_tools + 引擎逐个探活
# 工具链轨迹（一眼看出"没调工具/工具失败/原地打转"）
curl --noproxy "*" -s -H "Authorization: Bearer $TOK" \
  "http://127.0.0.1:18790/gateway/trace?limit=5"
# 复现真实场景，再看日志确认工具真的被调用
grep "tool " D:/O2OA/gateway/gateway.log | tail
```

### 5. 重启网关（关键：先释放端口）
旧进程占着 18790 时看门狗会跳过加载 → 新代码永不生效。
```bash
# 按端口精准结束（比双击 bat 更适合脚本化）
# PowerShell: Stop-Process -Id <18790的PID> -Force
# 再后台拉起；注意 Bash 工具的后台进程在调用结束会被回收，用 run_in_background
```

## 可选进阶

**A. 复用 Bionic 的 MCP（纯配置，零代码）**
`config.json` 的 `mcp_servers` 加条目即可（`load_external_mcp()` 已实现）：
```json
{"name":"searxng","transport":"http","url":"http://127.0.0.1:8888/mcp","timeout":30}
```
工具名自动带 `{server}__{tool}` 前缀避免冲突。

**B. `bionic_cli` 子进程委派** —— ✅ **已实现**（2026-09-21 第四批）
要点（若要在别的项目复刻）：**别真的 spawn `lms.exe chat`**，用 HTTP
`POST {bionic_base}/v1/chat/completions` 复用已加载模型——4GB 显存机器反复冷启进程不划算。
```python
{
  "name": "bionic_cli",
  "description": "把独立的、需要专注推理的重型子任务交给后台干净会话执行并取回结果。"
                 "适合长文摘要/代码审阅/多步推理；不适合简单问题，别把整个用户问题原样丢进去。",
  "parameters": {"type":"object","properties":{
      "prompt":{"type":"string","description":"自包含的任务指令（背景+要求+输出格式）"},
      "system":{"type":"string","description":"可选角色设定"}},
   "required":["prompt"]},
}
# exec_builtin 分支： return bionic_cli_impl(args.get("prompt"), args.get("system") or "", clue_id or "")
```
实现里必须有三层限流（漏一层就会被模型递归调用拖垮）：
1. **单轮次数**（`clue_id` 维度计数，默认 2）—— 防递归委派；
2. **全局并发信号量**（默认 2）—— 护后端；
3. **硬超时**（默认 240s）+ 复用主链路 400/断流退避。
另需 `tool_repeat_guard`：同签名调用 ≥3 次熔断（不同参数不误伤）。

**C. MCP 生态工具**（`load_external_mcp()` 已实现，纯配置）
```json
{"name":"searxng","transport":"http","url":"http://127.0.0.1:8888/mcp","timeout":30}
```
工具名自动带 `{server}__{tool}` 前缀避免冲突。

**D. O2OA 网关注册协议**（已逆向，供扩展参考）
- 网关侧已实现：`/ai-gateway-mcp/{create,update,get/{flag},delete/{flag},list/paging/{p}/size/{s}}`
- O2OA 侧：`ConfigAction` 的 `create/mcp`、`list/mcp/paging/...`、`get/mcp/ext/{flag}`
- **注意**：O2OA 的 `McpConfig` **不落 O2OA 库**，纯转发给网关 → MCP 配置实际存于网关 kv。
- 前端 `extend.output` 卡片渲染依赖 `McpConfig.extra`（`template`/`css`/`script`），
  网关 `get/{flag}` 需返回 `Wo{id,name,extra}` 才能让卡片生效。

## 坑（务必避开）

1. **`lms` 不在 PATH** —— 永远用绝对路径；Git Bash 下先 `export HOME=/c/Users/meng_`。
2. **`--ttl -1` 非法** —— 最小 1；常驻用大值（如 86400）。
3. **搜索引擎必须适配国内网络** —— DuckDuckGo 系列返回 000，用 `cn.bing.com`。
4. **抓外网别用网关的 `_client`** —— 它是 `trust_env=False`，会绕过系统代理。
5. **新增工具必须同步 `persona_tools`** —— 否则 `user` 角色看不到（显式白名单，不是 bug）。
6. **改完必须重启网关进程** —— 沙箱改的是宿主文件，且旧进程占端口会导致看门狗跳过加载。
7. **验证要看日志里的 `tool xxx` 行** —— 只测"回答正确"不够，模型可能没调工具而靠自身知识蒙对。
8. **`netstat` 输出在 Windows 是 GBK** —— 用 Python 解析时传 `errors="replace"`，否则 `UnicodeDecodeError`。
9. **`/gateway/*` 鉴权只认 `Authorization` 头** —— `check_token()` 是 `auth.endswith(CFG["token"])`，
   所以 curl 必须 `-H "Authorization: Bearer <token>"`。用 `-H "token: xxx"` 或 `x-token` 一律返回
   `{"type":"error","message":"bad token"}`（401），**容易误判成"网关没起来/工具没注册"**。
   注意 token 值本身形如 `local-o2-agent-2026`，带 `Bearer ` 前缀即可（`endswith` 不校验前缀）。
10. **`/gateway/capabilities` 里的 `chat_backend.tool_calls` 可能为 `null`** —— 后端 `/props` 未暴露
    `chat_template_caps` 时的正常表现，**不代表模型不支持 tool_use**。判据以 `builtin_tools` 列表 + 日志
    的 `tool xxx` 行为准。
11. **本机已有 searxng，别浪费** —— `127.0.0.1:8080/search?q=..&format=json` 返回结构化结果
    （含 `content` 摘要字段），质量与稳定性都优于抓 Bing HTML。加搜索工具时**先探本地 searxng**。
12. **别用 `re.sub(r"<[^>]+>", " ")` 单独做 HTML 清洗** —— 它会把 `<script>` 内的 JS 全部保留，
    正文被污染。必须先剔 `script/style/noscript/svg/iframe/注释`。
13. **Bash 工具的后台进程会被回收** —— `cmd &` 启的网关在本次工具调用结束时就死了。
    要长期驻留必须用 `run_in_background=true`，或交给看门狗拉（本机 `watchdog_ai_stack.py` 有
    自愈能力，杀进程后约 30s 会自动拉起**最新代码**）。
14. **看门狗探活端口时不会重载已占用的服务** —— 旧进程还活着就一直用旧代码。改完网关必须
    **先杀 18790 的占用进程**，或等看门狗下一轮探活失败再拉。
15. **网关必须在它自己的 venv 里跑** —— `/gateway/*` 模块依赖 `httpx`，只有
    `C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（或 everos）装了。
    用 binaries 的裸 3.13.12 解释器 import 网关会 `ModuleNotFoundError: No module named 'httpx'`。
    写验证脚本一律用 venv 的 python。
16. **写验证脚本别猜返回值形状** —— `web_search_impl(query, limit)` 返回**字符串**（面向模型的
    可读文本），不是 `(items, err)` 元组；`BUILTIN_TOOLS` 元素是 OpenAI 裸格式，取名字用
    `t['name']` 而非 `t['function']['name']`。动脚本前先 `inspect.signature` / `inspect.getsource`。
17. **★ 弱模型（glm-4.7-flash 一类）无法生成嵌套对象参数** —— 工具 schema 里放
    `params: {type: object, properties: {...}}`，它会把整个对象**拼进外层字符串字段**：
    实测得到 `kind = "read;params:{}{}{}}(待补充) - 修正参数格式并调用 query_table_list…"`。
    **对策：工具参数一律平铺**（`source`/`flag`/`query` 平铺而不是 `params.source`），
    并对枚举字段做**宽容净化**（`kind` 只取开头第一个合法单词，而不是报错断链）。
    这条适用于所有面向弱模型的工具设计，不限本系统。
18. **★ 弱模型会凭印象编标识，必须加"真实性护栏"** —— 它会发明 `__all_tables`、
    `o2oa_system_tables`、`demo orders` 之类的表名，每次 HTTP 500，既浪费轮次又让用户
    误以为"系统里没这表"。对策：`_o2_table_flag_valid()`（60s 缓存全表清单，校验
    name/alias/id），不匹配就返回「**不要猜表名**，先用 `query_table_list`」——
    把一次注定失败的调用转化成一次有效的自我纠正。
19. **★ 长清单必须支持定向过滤，且输出要以"可直接用的标识"开头** —— 75 行表清单弱模型
    **会看漏**目标表（实测两次）。① `query_table_list` 加 `keyword` 模糊过滤
    （`keyword='order'` 只返 1 行）；② 输出改为 `[1] 【aiDemoOrders】　alias：…` ——
    模型心里想的是 alias，就让它一眼看到 alias，而不是埋在 `t5005003_...` 表名后面。
20. **★ jpql 字面量必须类型感知（否则静默错答）** —— 数字字段裸写 `o.amount=7`，
    加引号写 `o.amount='7'` 类型不匹配 → **恒 0 行**。字符串才加单引号（内部 `'` → `''`）。
    "查不到数据"和"条件写错"在返回上长得一样，极难发现，务必按类型生成字面量。
21. **★ 回滚抓手必须"写完就记"，且要能从写入响应拿不到 id 时兜住** —— O2OA 写接口只返回
    `{"value":1}`（影响行数），**拿不到新行 id**。若等回滚时才反查，期间数据被改/增就不唯一了。
    正确做法：写入成功后**立刻**按字段值反查 id 存进账本（要求恰好命中 1 行，0/多行都保守跳过）。
22. **★ 弱模型多跳决策会编造结果 —— 护栏只能降级失败模式，不能补齐能力** —— 实测：
    模型拿到**正确的** `query_table_list(keyword='order')` 结果后，转而调用错误的工具
    （`query_data('demo orders')` → 500），轮次耗尽后**编造统计**（"系统显示该应用中包含多条数据"）。
    简单问题、跨源汇总、直接调 API 层全部正确 → **根因是模型能力天花板，不是代码缺陷**。
    多步事务须切更强 `chat_model`；护栏的价值是把"静默错答"降级为"明确报错+指路"。
23. **★ 换模型：LM Studio 的模型标识用短横线，不是冒号** —— 用户口头说的 `qwen3.8:27b`，
    在 REST/CLI 里的真实 id 是 **`qwen3.8-27b`**（`:` 是 LM Studio 内部的 tag 分隔符）。
    查真实标识：`curl :1234/api/v0/models`（或 `lms ls`），看 `id` 字段，别照抄用户的口头叫法。
    `qwen3.8-27b` 属性：`type=vlm`（带视觉）、`Q4_K_M`、`max_context_length=262144`、
    `capabilities=["tool_use"]` ✅。备选 `bonsai-27b`（llm/Q1_0/同样 tool_use）。
24. **★ 4GB 核显换模型必须"先卸后载"，且 ctx 不要顶满** —— 两个 27B 不能同时常驻。
    顺序：① `lms unload <old>` → ② `lms load <new> --context-length 65536 --gpu max --ttl 86400`
    → ③ 改 `config.json` 的 `chat_model` 并**重启网关**。`qwen3.8-27b` 实测占用 **17.74 GB**。
    ctx 取 65536 而非 max（262144）：够用且省显存。
25. **★ 换强模型时 `mcp_max_turns` 必须同步调大** —— 多步编排的轮次消耗远高于单步问答，
    默认 8 会在第 3~4 步就被截断。实测调至 **14** 后多步盘点一次收敛。
26. **★ 联网闸只加在 O2OA 网关，与 Bionic 本体无关** —— 用户会问"删掉联网会不会影响
    Bionic 自己用"。答案：**不影响**。所有闸门只在 `o2_agent_gateway.py` 内
    （`builtin_tool_defs()` 不注册 + `exec_builtin()` 硬拒绝），`~/.lmstudio/` 无我方写入，
    只做过 `lms load/unload` 运行时操作（非修改）。Bionic 作为通用 Agent 运行时联网能力完好。
27. **★ 权限闭环靠"网关全程用 `wi.token` 当 `x-token`"，不是 switchuser** —— 前端 AI 入口经
    x_ai 模块把 `wi.person`(DN)+`wi.token`(会话 token) 转发到 `/ai-gateway-completion/generate`；
    网关对所有 O2OA REST 一律 `x-token: wi.token`，服务端按该 token 权限**强制过滤** →
    用户只看到自己有权看的数据（待办/数据表/公文）。**`_o2_call` 必须让真实 token 优先、
    跳过 `switchuser`**（旧逻辑在"同时收到 person(DN)+token"时拿 DN 当 switchuser 凭据，错位）；
    switchuser 仅保留给"无 token、仅凭 person 名模拟"的管理视角。
28. **★ 本地直连 O2OA 必须绕开 shell 代理** —— 环境 `http_proxy=127.0.0.1:60195`，
    Python `urllib` 默认走代理会 `RemoteDisconnected`（或假 502）。验证用
    `urllib.request.build_opener(ProxyHandler({}))`，或 `curl --noproxy "*"`。
29. **★ `roles=[]` 可能是真实状态，别误判为解析 bug** —— `o2_user_info` 读 `data.roleList`
    是对的；普通用户没被授角色时就是 `[]`，persona 正确回退 `user`。数据表 list 路径用
    `surface` 模块（`/x_query_assemble_surface/jaxrs/table/list/paging`），**不是** `designer`。

30. **★ 设计态（创建/改删 门户页·动态表·数据应用·门户）必须有"四层安全闸"，光有审核不够** ——
    O2OA 的 designer REST 全开放，AI 若直接以管理员落库，一次越权或幻觉就能改写生产结构。
    落地 `design_op`/`design_rollback` 工具，四层闸：① 角色闸门（`design_personas=[manager,analyst]`，
    普通 user 看不到工具）② 草稿不落地（confirm=false 只出 `CONFIRM_REQUIRED` 提案，不碰系统）
    ③ 过程授权（无静态 deny-all 白名单，人类在对话确认即授权，按需而动）④ 落地前快照+审计+可回滚
    （`design_rollback` 账本，create 回滚=删新建、update 回滚=恢复前定义、delete 留快照供手动重建）。
    系统级硬底线 `design_denylist`（如 `a0000000-common-dict-app`）命中即拒，任何角色都碰不了。
    接口走 designer REST（逆向 war 源码）；动态表 create 须续跑
    `status/build → table/query/{appId}/build → reload/dynamic`。工具参数一律**平铺**；改完须**重启网关**生效。

## 多步任务编排（task_plan / task_run_step / task_rollback）

**设计取舍**：不在 4GB 显存上另起 planner 推理进程，而是把**编排状态外置成 kv 账本**
（`task_plan:{clueId}`，ttl 7200s，max 12 步），由主模型按工具协议驱动。收益：
零额外显存 / 可观测 / 可续跑 / 可回滚。

与 `bionic_cli` **互补而非替代**：`bionic_cli` 治「上下文污染」（长文推理丢干净会话），
`task_plan` 治「多步可靠性」（跨步状态、失败定位、逆序回滚）。

**编排指引只在"真需要多步"时下发**（system 里写明"≥3 步才建计划，简单问题直接答"），
否则会过度规划。实测判别正确：问"现在几点"→ 仅 `get_current_time` 不建计划；
问"盘点表数据并汇总"→ `task_plan → task_run_step → …`。

**回滚设计**：只对**已成功的 write 步骤**回滚（读类天然无需回滚），按**逆序**补偿删除，
破坏性操作需 `confirm=true`；`task_rollback` **不进 `user` persona 白名单**（限分析师以上）。

## 模型选型（编排能不能跑通的决定因素）

**同一套编排代码，模型换一代，结论从"未收敛"变"完美收敛"。** 实测对照（`e2e_orch_live.py` 多步盘点）：

| 模型 | 表现 |
|---|---|
| `glm-4.7-flash` | 编排机制全程正确，但**未能收敛**：塞长描述进 `flag` → 转调错工具 → 轮次耗尽**编造统计** |
| `qwen3.8-27b` | `task_plan(4步) → run_step → update → run_step → update → calc → update×2 → close`，**4 行明细 + 正确求和 590.5 + 占比分析** |

**坑 17-22 在 `qwen3.8-27b` 上全部消失**（嵌套参数/编造表标识/长清单看漏/多跳编造）。
结论：**护栏保证"不骗人"，模型决定"能不能成事"** —— 两者都要，别指望护栏替代模型。

**多跳实测（`gateway/tests/e2e_multihop.py`，三场景）**：
- 找表→查数：`query_table_list(keyword=合同) → query_rows` → 4 张表全对（含物理表名），主表 2 条 + 明细 ✅
- 组织→人员：`org_unit_tree → org_person_identity` → 4 部门人数正确，并**主动指出"直属身份 2 但只匹配到 1 人"的数据不一致**（未编造）✅
- 待办→详情：测试通道无登录态时**如实说明需从前端入口**，未编造待办 ✅

## 验证基线（判定"真的通了"）

- `GET :18790/gateway/capabilities` → `builtin_tools` 含新工具（当前 **29**，`web_enable=False` 时）
- `capabilities.web_enable` / `positioning` → 确认定位（关断时 = "系统内数据闭环…默认不联网"）
- `capabilities.orchestrator` → `enable=true`、`max_steps=12`、`active_plans`
- `capabilities.internal_capability.o2oa_login_user` → **必须非空**（空 = 服务号回落也失败，
  全部内网工具会 HTTP 0 静默失效）
- `capabilities.web_search.engines[]` → **每个引擎 up=true**（不能只看整体）
- `GET :18790/gateway/trace` → 能看到会话的工具链与成败
- `gateway.log` 出现 `tool web_fetch ... -> HTTP 200` 或 `tool web_search ... -> 结果（引擎 searxng）`
- 回答中引用了工具返回的真实数据（如具体气温、URL）
- 改造前问"今天天气"模型答"我无法访问外部数据" → 改造后能给出具体数值
- 反例监测：`web_search` 不应只返回标题没有摘要（说明退到了 HTML 引擎）

### 韧性路径（"最强最可靠"必须验这四条）

| 场景 | 构造方式 | 期望 | 实测 |
|---|---|---|---|
| 主引擎宕机降级 | 把 searxng url 改成 `127.0.0.1:59999` | 自动走 bing，结果非空 | ✅ 9.38s 出 bing 结果 |
| 全引擎宕机 | 两个引擎 url 都改死 | **可读失败摘要**，点名每引擎 HTTP 状态 + "是引擎侧故障不是没资料" + 建议改用 `web_fetch` | ✅ 18.31s |
| SSRF | `127.` / `localhost` / `192.168.` / `10.` / `172.20.` / 裸域名 | 内网 5 例拦截、公网放行 | ✅ 5 拦 1 放 |
| HTML 清洗 | 含 `<script>/<style>/<noscript>/<iframe>/<svg>` + 实体的页面 | 输出只剩正文与换行，无 JS/CSS/标签残留 | ✅ `'标题\n正文&内容\n尾部'` |

> 关键：**引擎全挂时的输出必须让模型知道"通道坏了"而不是"没这回事"**，否则模型会用自身
> 记忆编造数据 —— 这比直接报错更危险。

### 坑 31：RAG / 多层记忆 / 成长感知——先复用网关内置底座，别重建向量库

- **别从零造向量库**：网关 `data.db` 已有完整 RAG 内核——`docs(id,title,category,content,permission,meta)` + `chunks(doc_id,seq,text,embedding BLOB)`，`embed()` 调本地 `qwen3-embed`@8089，`rag_retrieve()` 做向量+rerank 融合，`kb_search/kb_save` 工具链齐全。**`docs.category` 字段就是多层记忆的命名空间**，新分层只需约定一个 category 值（o2oa_manual/o2oa_api/o2oa_ops/o2oa_version/ops_experience/business_process/ai_synthesis）。
- **入库要走 HTTP 接口**：`POST /idx-gateway-doc/update`（需 `Authorization: Bearer <token>`，`check_token` 是 `auth.endswith(CFG["token"])`）；它在服务进程内 `reindex_doc`，自动分块+向量化，**避免外部脚本直连 SQLite 与运行网关抢锁**（WAL 下短连可读但写易冲突）。
- **经验→知识合成（成长感知）**：`kb_reflect` 收集 `ops_experience` + `feedbacks`，用 chat 模型提炼 SOP（confirm=false 先出草案，confirm=true 落盘为 `ai_synthesis` 并记 `growth_ledger`）。`growth_report` 只读汇报分层规模+反馈+事件。
- **验证技巧**：在隔离 venv(`python/envs/default`) 装 `httpx fastapi` 后 `importlib` 导入网关模块，可直接调 `growth_report_impl()`/`kb_reflect_impl(confirm=False)` 做实跑校验（绕过"旧进程占 18790 不加载新代码"陷阱）；注意直接 `binaries/3.13.12` 裸解释器 import 会因缺 httpx 失败。
- 架构与分层详见 `D:\O2OA\docs\本地知识库与多层记忆成长体系.md`。

### 坑 32：AI 栈「起不来/反复抖动」三板斧——VBS 编码、os.kill 误杀、双开互杀（2026-09-22 实战）

- **自启 VBS 必须「纯 ASCII 注释 + CRLF」**：WSH 按 ANSI/GBK 解析 .vbs，UTF-8 中文注释的高位字节会吞掉换行符，把 `Set sh = CreateObject(...)` 并进上一行注释 → 后面 `sh.Run` 报 `800A01A8 缺少对象 'sh'`（行号还会错位）。开机自启链路一旦如此，AI 栈永远没人拉。修法：重写为 ASCII-only + CRLF，用 `file` 验证应输出 `ASCII text, with CRLF line terminators`。
- **★ Windows 上 `os.kill(pid, 0)` 不是探活，是 TerminateProcess**：Python 在 Windows 对非 CTRL 信号直接 `TerminateProcess(pid,0)`——「检测存活」实际把目标进程杀掉。看门狗在「端口未就绪但旧 pid 活着（模型加载中）」时调 `pid_alive` 恰好误杀加载中的组件 → 等 60s 报未就绪 → 下轮重启 = 反复 DOWN→重启抖动的真凶。**探活正解**：ctypes `OpenProcess(0x1000, pid)` + `GetExitCodeProcess()==STILL_ACTIVE(259)` + `CloseHandle`，并单测验证「检测不杀、死/空/假 pid 均 False」。
- **看门狗必须单例锁**：开机自启 + 手动双击可能同时各起一个看门狗，两实例首 cycle 都 `free_port(18790)` 杀对方网关再拉起 = 互杀战争（实测：第二实例经 os.kill 误杀第一实例后抢锁）。修法：`watchdog.pid` + 存活检测，已有存活实例则打印后 `sys.exit(0)`。
- **WorkBuddy 沙箱内无法创建持久进程**：沙箱 Bash `run_in_background` 拉起的看门狗及其 DETACHED/BREAKAWAY 子进程，**会话回合结束即整树回收**（实测 10:06 全绿 → 10:11 全灭、无 traceback、python 进程归零）；逃逸 Job 的三条路 cscript / WMI `Invoke-CimMethod Win32_Process Create` / `schtasks` 全被安全黑名单拦截。**结论：常驻服务必须由用户双击 `start_ai_watchdog.bat`（或 `start_o2oa.bat`）拉起**，agent 只能做临时验证用拉起。
- **验证对话别误判**：`/ai-gateway-completion/generate` 的 SSE 帧是 `event: extend.status` 行 + `data:` 行（JSON **无顶层 type 键**，正文在 `data.choices[0].delta.content`，结束帧是 `data: [DONE]`）——按顶层 `type` 解析会误判「无正文」。chat 走 LM Studio 1234（`bionic_base=127.0.0.1:1234`），**LM Studio 不在则 AI 无回答**，排障先查 1234 `/v1/models`。

## 版本记录

| 时间 | 内容 |
|---|---|
| 2026-09-21 上午 | 首次落地：`web_fetch`+`web_search`（Bing 单引擎）、上下文 64K→128K、persona 白名单同步 |
| 2026-09-21 中午 | **第四批加固**：searxng 优先的多引擎降级链、重试退避、SSRF 防护、HTML 清洗升级、`bionic_cli` 委派（三层限流）、工具熔断、`/gateway/trace`、capabilities 引擎逐个探活。工具数 15→16 |
| 2026-09-21 晚 | 韧性路径复验全绿（降级/全挂摘要/SSRF/清洗四表）；补坑 15-16（venv 依赖、别猜返回值形状） |
| 2026-09-21 深夜 | **第五批：定位纠偏 + 内网能力 + 多步编排**。①联网**两道闸**默认关断（`builtin_tool_defs()` 不注册 + `exec_builtin()` 硬拒绝，`web_enable=false` 一行恢复，代码零删除）；②补厚 16 个内网工具（待办3/组织3/数据表2/公文3/流程1/知识库2），逆向 war 内接口文件拿到权威路径；③`task_plan`+`task_run_step`+`task_rollback` 多步编排（kv 账本）。工具数 16→**31**（`web_enable=False` 时注册 29）。**补坑 17-22**（弱模型嵌套参数/jpql 类型/编造标识/长清单/回滚抓手/多跳编造） |
| 2026-09-21 深夜 | **换模型 `glm-4.7-flash` → `qwen3.8-27b`（用户指定）**。①查证真实标识是 `qwen3.8-27b`（短横线，非冒号）；②`lms unload` → `lms load --context-length 65536`（17.74GB）→ config 改 `chat_model` + `mcp_max_turns` 8→14 → 重启；③**多跳链路全绿**：多步盘点从"未收敛"变"完美收敛"（求和 590.5），找表→查数、组织→人员 均正确。**新增「模型选型」章节 + 补坑 23-26**（短横线标识/先卸后载/同步调 max_turns/联网闸不影响 Bionic 本体） |
| 2026-09-21 下午 | **登录态权限闭环 + mcp_max_turns→20（用户要求）**。①确认权限闭环已具备：前端 `wi.token` 转发到网关，全程 `x-token: token` 调 O2OA REST，服务端按 token 权限强制过滤；②修复 `_o2_call`：token 非空直接以本人身份调用、跳过 `switchuser`（DN 非 switchuser 凭据）；③`config.json` mcp_max_turns 14→**20**、代码默认 `or 8`→`or 20`；④实测 token 级权限闭环成立（52 张权限内数据表、本人待办）。**补坑 27-29**（token优先非switchuser/绕shell代理/roles=[]真实状态）。文档新增 10.9 登录态与权限闭环 |
| 2026-09-21 晚 | **Phase A 设计态能力落地（四层安全闸）**。`design_op`/`design_rollback` 工具（仅 analyst/manager 可见），四层闸=角色闸门+草稿不落地(confirm=false 只出提案)+过程授权(人类确认即授权，无静态白名单)+落地前快照+审计+可回滚(`design_rollback` 账本)；`design_denylist` 系统应用永禁。接口走 designer REST（逆向 war 源码：portal/page/data_app/dynamic_table 的 create/update/delete，动态表 create 续跑 build 链）。代码落点：`BUILTIN_TOOLS`+`exec_builtin`+`DEFAULT_CFG`+`persona_tools.analyst`+`/gateway/capabilities`。`py_compile` 通过。文档新增第十一节；**补坑 30**。 |
| 2026-09-21 深夜 | **本地知识库·多层记忆·成长感知体系**。关键发现：网关内已自带 RAG 内核（data.db 的 `docs` 表 `category`/`permission` 字段 + `chunks` 表存 embedding BLOB + `qwen3-embed`@8089 + `rag_retrieve` 向量(0.6)+rerank(0.4) 融合 + `kb_search/kb_save`），**`docs.category` 天然就是多层记忆命名空间，无需另造向量库**。复用做法：`tools/ingest_o2oa_kb.py` 走 HTTP `/idx-gateway-doc/update`（进程内 `reindex_doc`，避免直接锁库）灌库，实跑 **52 文档 / 451 向量块**跨 9 分层（o2oa_manual/o2oa_api/o2oa_ops/o2oa_version/ops_experience/…）；新增 `kb_ingest`(持续入库)/`kb_reflect`(经验→SOP 合成，确认真调 chat 出 5 条高质量 SOP)/`growth_report`(账本)+`growth_ledger` 表，接入 `/gateway/capabilities.memory_layers`。**补坑 31**（RAG 底座复用 / category 即分层 / 入库走 HTTP 接口）。架构见 `docs/本地知识库与多层记忆成长体系.md`。 |
| 2026-09-22 上午 | **AI 栈「起不来」根治**。用户截图自启 VBS 报 800A01A8 → 三根因连修：①自启 VBS UTF-8 中文注释被 WSH 按 GBK 误读吞换行（重写为纯 ASCII+CRLF）；②`watchdog_ai_stack.py` 的 `pid_alive` 用 `os.kill(pid,0)` 实为 TerminateProcess 误杀加载中组件（改 ctypes OpenProcess+GetExitCodeProcess，单测通过）——即 9/21 反复抖动真凶；③补 `watchdog.pid` 单例锁防双开互杀（实测第二实例正确自退）。端到端复验全绿：对话（SSE event:/data: 帧）+ RAG（92 篇库引用准确）+ capabilities 新工具全注册。**补坑 32**。遗留：`网关服务号` person 不存在待建（先 docker restart 愈 randomWithWeight/express + 重跑 netlock）。 |
