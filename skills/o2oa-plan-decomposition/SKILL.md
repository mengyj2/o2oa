---
name: o2oa-plan-decomposition
description: 在 O2OA（社区版/Docker 自托管，10.0.2 实证）上把「个人工作台·工作计划」按【组织→部门→个人】双层分解，含部门职责映射、无负责人/无执行人兜底上收、「待分配预警」、个人→部门→组织完成率加权回写。当用户问"组织计划能自动分解到部门吗""工作计划怎么落实到个人""部门计划自动拆到岗位""完成率怎么汇总回写""工作计划数据存在哪张表"时调用。覆盖 TEW2_TASK 真实数据模型、ORG 组织树取数、只读分解器用法、本机 LLM 三个硬坑。
category: development
agent_created: true
---

# O2OA 工作计划「组织→部门→个人」双层分解

## 0. 结论先行（回答用户的第一句）
- **O2OA 内置不会自动分解**：组织级计划不会自动落到部门，部门计划也不会自动落到个人。
- 你看到的「公司计划 / 部门计划 / 个人计划」只是**查询视图里的分类标签**，
  三层之间**没有任何外键**，是互不相干的孤岛。
- 但底层表**预留了层级能力**（`xparent` 父子任务），所以**技术上完全可以做**，
  适合交给后台 AI 完成。

## 1. 真实数据模型（实证，别猜）
| 项 | 事实 |
|---|---|
| 工作计划底表 | **`TEW2_TASK`**（"工作管理"模块）。**不是** CMS、**不是** QRY_DYN 数据应用 |
| 关键列 | `xid` `xname` `xparent`（父子外键，**根级='0'**）`xproject` `xexecutor`（责任人，存身份DN）`xprogress`（完成率）`xcreatorPerson` `xstartTime` `xendTime` |
| 参与人 | `TEW2_TASK_participantList` |
| 分类标签 | `o2oa优化/queries/工作计划.json` 的 `categoryInfoList`：公司计划 `f5303f95` / 部门计划 `f44c341e` / 个人计划 `7f473b6d` |
| 组织 | `ORG_UNIT`（`xid/xname/xunique/xlevel/xsuperior/xdistinguishedName`） |
| 岗位(身份) | `ORG_IDENTITY`（`xperson`→人、`xunit`→部门、`xdistinguishedName`） |
| 人员 | `ORG_PERSON` |
| 角色成员表列名 | `ORG_ROLE_personList` 是 **`ROLE_XID` + `xpersonList`**（不是 `xperson`） |

**DN 格式**：岗位身份 `姓名@<部门unique>_<personunique>@I`（例 `李芳@zhb_lifang@I`）；
人员 `姓名@<unique>@P`；组织 `部门名@<unique>@U`。

### ★ 部门负责人在 O2OA 里怎么取（三个候选源，实测可能全空）
1. `ORG_UNITDUTY`（部门职务）+ `ORG_UNITDUTY_identityList`
2. `ORG_ROLE` 里 `UnitManager`（xunique=`UnitManagerSystemRole`）的 `personList`
3. `ORG_UNIT_controllerList`（部门控制者）

**本协会实例三者全空** → 部门负责人根本没配置 → 兜底上收规则每次都触发。
取数前先探这三者，别假设有值。

## 2. 三套业务规则（用户确认版，写进 `o2_plan_rules.json`）
```jsonc
{
  "department_duties": { "<部门名>": { "duties": ["主责主业…"], "members": [{"name","identity_dn"}] } },
  "fallback": {
    "no_dept_leader_to": "TOP_MANAGER",   // 无部门负责人→上收秘书长并公开任务清单
    "no_executor_to": "DEPT_LEADER",      // 无执行人→挂部门负责人，2 工作日补配
    "top_manager": "孟弋洁@mengyijie@P",
    "reassign_days": 2,
    "unassigned_warn_days": 3,            // 超 3 天推最高管理者工作台
    "warn_flag": "待分配预警"
  },
  "progress": {
    "personal_by": "delivered_items",     // 个人按实际交付事项
    "dept_agg": "weighted_avg",           // 部门=成员完成率加权平均
    "org_agg": "weighted_avg",            // 组织=部门完成率加权平均
    "weight_by": "task_count"
  }
}
```

## 3. 工具用法（`tools/o2_plan_decomposer.py`）
```bash
python tools/o2_plan_decomposer.py init-rules   # 从库生成规则配置骨架（含真实部门/人员DN）
python tools/o2_plan_decomposer.py org          # 打印组织树（部门/岗位/人员）
python tools/o2_plan_decomposer.py plans        # 列出工作计划
python tools/o2_plan_decomposer.py run --plan-text "组织级计划文本"
python tools/o2_plan_decomposer.py run --plan <TEW2_TASK.xid>
python tools/o2_plan_decomposer.py run --plan-text "..." --no-llm   # 规则模式，不调模型
```
产物：`tools/o2_plan_rules.json`（可编辑规则）+ `tools/plan_out/decompose-*.{json,md}`（建议，**不落库**）。

### 取数方式
MySQL 未暴露宿主端口 → 用 `docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd
--default-character-set=utf8mb4 -N -B X -e "<SQL>"`（中文必须带 utf8mb4）。

## 4. ★★ 本机 LLM 三个硬坑（本次摸清，务必遵守）
1. **唯一可用模型是思考型 `qwen3.5-4b`**：一次调用光 `Thinking Process` 就吃掉上万字符，
   `max_tokens` 给小了 JSON 根本生成不出来。
   → 对策：**两层合并为单次调用**（`build_prompt_both`）+ `max_tokens=6000` + `timeout=240`。
2. **`reasoning_effort:"none"` 在本机 LM Studio 无效**（仍输出思考）。
3. **9B 及以上模型加载失败**：`lms load agentscope-ai_copaw-flash-9b` →
   `failed to allocate buffer for kv cache`（上下文 262144 太大）。
   请求未加载模型会触发即时加载并返回 **400 `Engine protocol predict request failed: fetch failed`**。
   → **运行前先 `lms ps` 确认哪个模型已加载**，只用它。
4. 引擎**间歇性** 400/超时（刚成功一次、下一次就失败）→ `llm_chat` 已内置 3 次重试+退避；
   输出常被截断 → `extract_json` 用**括号平衡匹配 + 抢救式子对象提取**（但注意抢救出来的
   可能是 prompt 里的示例对象，需校验 executor 是否真属该部门）。
5. 网关 18790 常有 CLOSE_WAIT 堆积、health 超时 → 仅首轮试一次（20s），随后回落 LM Studio 1234。

## 4.5 ★★★ 数据溯源红线（2026-09-28 踩坑，务必遵守）
**任何"跑通了"的分解结果，汇报前必须先核对库里真有这条数据。**
- `run --plan-text "..."` 传入的文本可以是示例；不要把示例输出当成用户真实计划的分解结论汇报。
- 汇报前必跑：`docker exec o2oa-mysql mysql ... X -e "SELECT xid,xname,xcreatorPerson,xproject FROM TEW2_TASK;"`
- 本实例实测：`TEW2_TASK` 只有 2 条 xadmin 测试任务（`xname`='而'）、`TEW2_PROJECT` 只有 2 个
  （`xtitle`='微软'/'的'）、`CMS_DOCUMENT` 里 `xtitle LIKE '%计划%'` **0 命中** → 真实计划不在这里。
- 找不到就**直说查不到**，并让用户指认入口/贴原文，不要自行编造一份"看起来像"的计划。

## 5. 第二步（落库）——接口已确认，待用户放行
**服务名 = `x_teamwork_assemble_control`**（已证实；`x_tew2_*` / `x_work_*` / `x_task_*` 都是错的）。
describe 源：`o2oa优化/_tmp/desc/x_teamwork_assemble_control.json`（宿主可直接解析，不必进容器）。

| 动作 | 接口 |
|---|---|
| 新建/更新任务 | `POST /x_teamwork_assemble_control/jaxrs/task`（TaskAction.save，json） |
| 查任务 | `GET .../jaxrs/task/{id}` |
| 查子任务 | `GET .../jaxrs/task/list/sub/{taskId}` |
| **回写完成率** | `POST .../jaxrs/task/{id}/property`（updateSingleProperty） |
| 改参与人 | `POST .../jaxrs/task/updateParticipant` |

**字段口径（与直觉不同，落库前必看）**：
- `TEW2_TASK.xexecutor` 存的是 **person unique 名**（现有值 `xadmin`），**不是**身份 DN。
- `TEW2_PROJECT` 标题列是 **`xtitle`**，没有 `xname`（查 xname 会报 Unknown column）。
- 根级任务 `xparent='0'`；`xprogress` 为 int(0–100)；`xworkStatus` 现有值 `processing`。

其余待办：按配置口径向上加权汇总；「待分配预警」+ 3 天升级推送（定时任务 + 最高管理者工作台入口）；
建议先在组织里补配部门负责人，否则每次分解都会上收秘书长。

## 6. 相关
- 组织/账号事实：`o2oa-local-admin-account`
- 知识库：本技能的实证结论已写入 `D:/O2OA/.workbuddy/memory/2026-09-28.md`
