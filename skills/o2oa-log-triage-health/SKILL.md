---
name: o2oa-log-triage-health
description: O2OA 问题日志（CTE 三表）与访问审计（CUSTOM_AUDIT_LOG）的排障/日报工作流。当用户问"今天有什么报错""错误日志怎么查""某异常类为什么这么多""是不是爆发性故障""日报没灌库""CUSTOM_AUDIT_LOG 为什么是空的""定时任务 agent 在哪张表"时调用。含：三表正确列名（xoccurTime/xmessage/xloggerName）、一次性爆发 vs 持续性故障的判定手法、CTE_AGENT 与 PP_E_AGENT 的区分、docker exec 调试禁加 2>/dev/null 的踩坑。
agent_created: true
category: diagnostics

---

# O2OA 日志排障 / 每日健康日报

**一句话**：先摸对三张表的列名，再按「是否随时间推进」区分一次性爆发与现网持续故障。

> **已同步给 O2OA AI 助手**（2026-09-27），两条通道都要维护：
> 1. **知识通道**（RAG）：灌入网关知识库 doc_id=`o2kb::knowledge_base::log_triage_and_daily_health`，
>    源文件 `docs/knowledge_base/log_triage_and_daily_health.md`（8 chunk，召回实测 cos 0.55~0.71）。
> 2. **工具通道**（MCP）：方法论已实现为 stdio MCP server
>    `gateway/o2oa_logtriage_mcp.py`（工具 `o2_error_burst_triage` / `o2_agent_task_list`），
>    已注册进 `gateway/config.json` 的 `mcp_servers`（name=`logtriage`）。
>
> **改动本技能后，两边都要同步更新**，否则会 drift：
> 改知识 → 改那份 md 并 `post_doc` 重新灌库（幂等覆盖）；改判定逻辑 → 改那个 .py。
> 注意：MCP server 进程由网关缓存复用（`mcp_client._clients`），**改 .py 或加注册后须重启网关才生效**。

## 0. 入口：日报先看自动化

每日 06:30 自动化已跑 `tools/ingest_daily_health.py`（工作目录 `D:/O2OA`），
产出 doc_id=`sys-health-daily-YYYYMMDD` 灌入网关知识库，**幂等可重跑**。

```bash
cd /d/O2OA && NO_PROXY="127.0.0.1,localhost" \
C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
tools/ingest_daily_health.py
```

- 网关不可达（exit 2）：**不要尝试拉起网关**（常驻由 watchdog / 用户双击 bat 管），
  直接报告"网关未运行，日报未灌库"，下次运行会补上。
- 判活要绕系统代理：`NO_PROXY=127.0.0.1,localhost`。
- `docker exec` 报 QEMU setns 错：等 30 秒重试一次，仍失败再报。
- 脚本不落盘。取回全文：`sqlite3 gateway/data.db` →
  `select content from docs where id like 'sys-health-daily-%' order by id desc limit 1`。

## 1. ★ 三表列名（写错就白查，已实证踩坑）

| 表 | 时间列 | 异常类列 | 消息列 |
|---|---|---|---|
| `CTE_PROMPTERRORLOG` | **`xoccurTime`** | `xexceptionClass` | **`xmessage`** |
| `CTE_UNEXPECTEDERRORLOG` | `xoccurTime` | `xexceptionClass` | `xmessage` |
| `CTE_WARNLOG` | `xoccurTime` | **`xloggerName`**（无 xexceptionClass） | `xmessage` |

- 时间列是 **`xoccurTime`，不是 `xcreateTime`**（用后者恒 0 行，且因吞 stderr 看不到报错）。
- 访问审计：`CUSTOM_AUDIT_LOG`，规则在 `CUSTOM_AUDIT_CONFIG`（xstatus=1 才算启用）。
  **前置总开关 `general.json requestLogEnable=true`**，关着则审计恒 0 行。

## 2. ★★ 一次性爆发 vs 持续性故障（日报破千时必做）

TOP 异常类单日 >1000 会标"疑似爆发性故障"，但**多数是历史残留的一次性爆发**。判定两步：

```sql
-- ① 看是否集中于单一时间戳
SELECT xexceptionClass, LEFT(xmessage,100) msg, COUNT(*) c, MAX(xoccurTime) last_t
FROM CTE_PROMPTERRORLOG
WHERE xoccurTime > NOW() - INTERVAL 24 HOUR AND xexceptionClass LIKE '%<关键字>%'
GROUP BY xexceptionClass, LEFT(xmessage,100) ORDER BY c DESC LIMIT 8;

-- ② 看近期是否还在涨（把 T 换成爆发时刻之后）
SELECT xexceptionClass, COUNT(*) c, MAX(xoccurTime) last_t FROM CTE_PROMPTERRORLOG
WHERE xoccurTime > NOW() - INTERVAL 24 HOUR AND xexceptionClass IN ('<类1>','<类2>')
  AND xoccurTime > 'T' GROUP BY xexceptionClass;
```

判据：`MAX(xoccurTime)` 停在爆发点 + 分组行时间戳高度一致 ⇒ **一次性，已自愈，无需介入**；
`MAX` 随时间持续推进 ⇒ 真持续故障，需排查。

## 3. ★★ agent 表定位（易混）

- `CTE_AGENT` = **定时任务 / 定时 Agent**（`xname` / `xcron` / `xenable` / `xlastStartTime` / `xlastEndTime`）。
  `com.x.program.center.jaxrs.agent.ExceptionAgentExecute` 的源头在这。
- `PP_E_AGENT` = **流程环节 Agent**（`xprocess` / `xform` / `xbeforeExecuteScript`…），**没有** `xcron`/`xenable`。
- `xenable` 在 mysql CLI 里 0/1 显示成**空白**，读 `xenable+0` 才可靠。
- `xlastStartTime` 更新而 `xlastEndTime` 停在旧值 ⇒ 该轮执行抛错未正常收尾。

## 4. 已知残留根因（本实例）

### 4.1 已停用的一次性爆发（2026-09-26，未再复发）

CTE_AGENT 的 `6c948659` 通用内容管理数据迁移 / `b7e2d13e` 通用流程数据迁移
（cron `11 * * * * ?`，**xenable=0 已停用**）：demo 迁移后 `transferFlow` /
`transferDocument` 自建表不存在，一轮跑出各 602 条
`ExceptionEntityNotExist` + `ExceptionAgentExecute`，可占当日日志 98%。
**2026-09-29 复查：`xenable` 仍 0、`xlastStartTime` 仍停在 2026-09-26 16:52:33 →
确认未再触发。若再出现同类爆发，不要默认归因于它，先查 `xlastStartTime` 是否推进。**

### 4.2 ★★ 现网持续复发（2026-09-29 定位）

`ExceptionEntityNotExist` 单日 789 条，**持续性**而非一次性：

- 两条 Work ID `3bb242e8` / `f218fb1c` 自 09-28 16:15 起**每 5~10 分钟**复现至今晨 06:25。
- 来源：`AttachmentAction /attachment/list`（116+64）与
  `DataAction /data/work/{id}`（81+77+28…），person = 孟弋洁@mengyijie / admin。
- **根因是客户端残留，不是服务端故障**：Work 已被删除（疑与 09-21 拆应用有关），
  而浏览器/门户页面**未刷新，仍在轮询已失效的 Work ID**。
- 处置：**刷新或关闭该页面即止**，不要去改服务端或查 agent。

### 4.3 误报类（看到别慌）

- `…authentication.jaxrs.authentication.BaseAction` 数百条 = **WARN**
  `user: XXX use superPermission.`，管理员正常提权，**非错误**。
  注意它在 `CTE_WARNLOG` 按 **`xloggerName`** 分组（`CTE_WARNLOG` **无 `xperson` 列**，
  `CTE_PROMPTERRORLOG` 才有）。
- 文件类 `ExceptionFileNotExisted` / `ExceptionAttachmentNotExist` 成对出现且
  `MAX(xoccurTime)` 停在单一时刻 ⇒ 一次性，已自愈。

## 4.4 ★ 时区
本实例 MySQL `SELECT NOW()` **已与主机（GMT+8）一致**，无需 +8 换算；
但**每轮仍应先跑一次 `SELECT NOW()` 对齐**，别沿用旧结论。

## 5. ★ docker exec 调试三条纪律

1. **别加 `2>/dev/null`**：列名写错会被吞成"结果为空"，极易误判为"表里没数据"（已白绕三轮）。
2. 中文 `LIKE` 必须 `--default-character-set=utf8mb4`，否则 latin1 恒 0 命中。
3. 不确定列名先查：
   `SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='X' AND TABLE_NAME='<T>' ORDER BY ORDINAL_POSITION;`

## 6. AI 侧深挖

网关已挂 4 个工具：`o2_error_logs` / `o2_error_log_stats` / `o2_audit_logs` / `o2_server_log_tail`，
可在 AI 助手里直接问"最近 24 小时哪类错最多"。
