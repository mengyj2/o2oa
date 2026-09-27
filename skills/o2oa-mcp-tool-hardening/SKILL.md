---
name: o2oa-mcp-tool-hardening
description: 诊断并修复 O2OA（社区版 10.0.2 / Docker 自托管）AI 助手所调用的 **MCP 工具**——createMeeting / createCalendar / queryHr / querySalary / queryMail / queryCalendar / queryTask / startProcess_overtime / startProcess_apply——报 HTTP 500、静默失败（说成功但没落库）、卡片白屏或回吐 ${xxx} 表达式、查询返回**越权全量数据**（如"我的待办"列出所有人）。当用户说"AI 助手调用工具报错""工具调了但没数据""查我的待办查出来是所有人的""日程查询恒返回空""新建日程提示成功但日历里没有""卡片上出现 ${person} 这种东西""MCP 工具不可用/新建会议室通了但别的没通"时调用。
agent_created: true
category: diagnostics
---

# O2OA MCP 工具族诊断与硬化（9 个 HTTP 型工具）

**一句话根因**：O2OA invoke 的 `bodyMap` 用 `${param}` 模板拼请求体；**模型没提供的参数，bodyMap 会把字面量 `${person}` 原样发出去**（不是空串、不是省略）→ 服务端 `getPerson("${person}")` 返回 null → 500 或静默失败。
所有 8 个 invoke 脚本的修复核心都是**同一件事：把未替换的占位符归一为空串**。

## 0. 链路（先搞清谁在调谁）

```
AI 助手卡片
  └ getMcpExtra(name)            x_component_AI/Main.js:279
     └ O2OA 库 extra（不是网关 kv）
再渲染：脚本先 eval → 再 renderTemplate + marked.parse 注入
  └ renderTemplate             x_component_AI/Main.js:286
     new Function(...dataKeys, "return (expr)")  ← 变量缺失抛 ReferenceError
     → catch 后**原样回吐 ${expr}**（这就是卡片上看到 ${genderType=="m"?"男":"女"} 的来历）

网关侧：
  kv `mcp:<id>` 的 httpOption.bodyMap（${param} 模板）
    └ gateway/o2_agent_gateway.py exec_tool(≈3878) → _fill_body_map(≈3855) 填参
       └ POST http://127.0.0.1:9090/x_program_center/jaxrs/invoke/MCP_<name>/execute
          带用户 x-token
```

★ **`MCP_startProcess` 一个 invoke 服务两个工具**（`startProcess_overtime` / `startProcess_apply`）→ 打补丁/自检都要按 invoke 去重，否则重复改同一个实体。

## 1. ★★ 核心防御：统一取值 `txt()`

每个 invoke 脚本头部都要有（会议脚本同样）：

```javascript
function txt(v) {
    if (v === undefined || v === null) return "";
    var s = ("" + v).replace(/^\s+|\s+$/g, "");
    if (/^\$\{[^}]*\}$/.test(s)) return "";   // ← bodyMap 未替换的占位符
    return s;
}
```

**凡是取 `requestJson.*` 的地方一律走 `txt()`**，包括"是否为空"的判断（`requestJson.person || fallback` 会被 `${person}` 短路，永远拿不到 fallback）。

## 2. 逐工具修复要点（实测结论，勿"简化"）

| 工具 | 症状 | 根因 | 修法 |
|---|---|---|---|
| `queryTask` | 返回**全库待办**（越权级正确性缺陷） | 传了无效 credential → `credentialList` 被丢弃 → 不过滤 | `person` 缺省回落 `self.effectivePerson`；显式传 DN |
| `queryMail` / `querySalary` | HTTP 500 `Cannot read property 'distinguishedName' of null` | `getPerson` 收到 `${person}` 返回 null | `txt()` + 回落 + null 守卫；`readList/mailFrom/publishTime` 空值守卫 |
| `querySalary` | 卡片白屏 | 失败时 data 结构不对，卡片 `.reduce` 崩 | 失败时 `data` 仍返回 `{earnings:[],deductions:[]}` |
| `queryCalendar` | **恒返回空** | Gson 只认 `yyyy-MM-dd HH:mm:ss`，**无秒**的 `2026-11-01 00:00` 被当 null → 回落"本月" → 静默空结果（实测：无秒 0 条 / 带秒 10 条） | `normDate` 强归一化；查本人走 `listWithFilterSample`（非管理员走 manager 版会 AccessDenied） |
| `queryHr` | 卡片回吐 `${genderType=="m"?"男":"女"}` | 简版人员对象缺模板需要的字段 | `shape()` 补齐 `genderType/officePhone/weixin/qq`，再用 `PersonAction.get` 取全量 |
| `createCalendar` | 提示成功但日历里没有 | `managerListWithPerson(undefined)` → `calendarId` 恒 undefined → `manageCreate` 无失败回调 → data 为空 | 日历账号三级兜底：`listMyCalendar` → `managerListWithPerson` → `save()`；加失败回调；真正落库后返回 `id/calendarId` |
| `startProcess_overtime/apply` | 恒回"未找到申请人信息"（100% 不可用） | bodyMap 里根本没有 person | `person` 缺省回落；`TITLES` 区分"的加班申请"与"的请假申请单"（官方 bodyMap 把请假也写成"的加班申请单"）；守卫 `json.data[0].taskList[0].id` |
| `createMeeting` | 传 `${subject}` 占位符 | bodyMap 未替换 | 入参改用 `txt()` |

## 3. 卡片修订（脚本 + 模板）

- 位置：`patch/mcp/cards/<name>.card.js` 与 `<name>.card.tpl`
- 原则：**真的落库/真的返回才注入按钮或链接**。
  `if (data && data.id) { ... }`；模板用 `${id ? "点击查看：" : ""}${statusText}`。
- ★★ 更新卡片定义必须用**记录 id 作 flag**——用 name 会**新建一条重复定义**。
- `patch/meeting/gen_InitMcp.py` 是 `InitMcp.json` 的**唯一产出者**，已折叠 `patch/mcp/cards/` 的修订；改卡片后要重跑它并 `docker cp` 到容器 `WORK_MCP`。

## 4. 补丁管线（幂等，可回归）

```bash
# 判据 = 与仓库源【逐字符一致】；PUT 字段走白名单 INVOKE_FIELDS
python tools/o2_patch_mcp.py check      # 只检查，报差异
python tools/o2_patch_mcp.py apply      # 应用（7 个 invoke + 3 个卡片）
```

- 清单：`patch/mcp/manifest.json`（`marker: "[o2-mcp-harden]"` + 8 条 工具→invoke→file 映射）
- 脚本都带 `[o2-mcp-harden]` 标记，便于确认"已硬化"而非"官方原版"
- 改动容器/DB 后复检：`check` 应全 True

## 5. 端到端自检（必须断言"实质结果"，不是只断 HTTP 200）

```bash
python tools/o2_mcp_selftest.py     # 10 用例（queryCalendar 两条）
```

断言口径：**真落库 / 真返回 / 错误可读**。
自动清理：会议（用返回的 `meetingId` 直删）→ 日程（`event/single/{id}` DELETE）→ 流程（`x_processplatform_service_processing/jaxrs/work/{id}` DELETE）。

★ 会议列表用 **`POST list/1/size/50` + 普通用户 token**：
- `list/paging/...` 是 **404**；GET 是 405；admin token **看不到普通用户的会议** → 清理会静默失效、`MT_MEETING` 里留垃圾。

## 6. 易踩的坑

- **`PP_E_PROCESS` 才是流程定义表**（没有 `PP_C_PROCESS`）；`PP_E_WORKCOMPLETED` 表不存在。
- `MeetingAction` 路径：`list/{page}/size/{size}`（POST，普通用户）、`{id}` GET/DELETE。
- `Calendar_EventAction`：`list/filter/sample`(PUT，用户版) 与 `list/filter/sample/manager`(POST，管理员版)；
  `CalendarAction.list/my` 返回 `{myCalendars:[{id,manageable,...}]}`。
- 失败信息里出现 `${person}` 字面量，说明脚本里还有没走 `txt()` 的取值点。
- 中文查询/比对在 MySQL 侧必须 `--default-character-set=utf8mb4`，否则 LIKE 恒 0 命中。

## 7. 与其它 skill 的边界

- 会改变 O2OA 状态的**写操作入口** → `o2oa-ops`
- 网关 / 本地模型 / RAG 侧 → `o2oa-local-ai-assistant`
- 本 skill 只管 **MCP 工具（invoke + 卡片）这条链的正确性**
