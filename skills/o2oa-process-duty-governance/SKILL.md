---
name: o2oa-process-duty-governance
description: 治理 O2OA 流程审批人——把硬编码人名改成「按组织职务指派」或「按表单数据路径取人」，并做全量审计与验收。当用户说"审批人写死了人名""换人要改流程""一提交全部门都收到待办""某节点静默派给发起人""按所选项目自动派负责人""领导节点该派谁""流程结构被改坏要复原""谁该审这个节点""点选流程后没反应""选完身份就返回了""发起后表单没打开"时调用。含三范式选择边界、组织 API 契约（秘书长兜底不卡单）、数据路径值必须身份DN、六个会静默出错的坑、草稿发起(defaultStartMode)根治"选身份后返回"、审计与 E2E 验收法、以及企业化运维（推仓库/镜像/备份/知识库化）。
agent_created: true
category: operations
---

# O2OA 流程审批节点治理（按组织职务 / 数据路径指派）

> 适用：O2OA 社区版 / Docker 自托管（10.0.2 实证）。核心命题：**审批人不该写死在流程里** ——
> 流程只写职务/规则，「谁是人」由**组织管理**决定；**换人只改组织数据、流程不动**。
> 唯一真源脚本在 `D:\O2OA\o2oa优化\o2oa_audit\`；知识库稿 `docs/knowledge_base/process_duty_assignment_governance.md`。
> 相关技能：`o2oa-ops`（写入类运维总入口）、`o2oa-app-io`（只读导出）、`o2oa-runtime-drift-hardening`（构建期固化）。

## 0. ★ 最高铁律

1. **先干跑、再写库、必回读。** 所有修正脚本默认 dry-run，`--apply` 才写；写前自动备份到 `_archive/`，写后回读校验。
2. **改前整份 GET、整份改、整份 PUT。** 流程保存是「按 id 全量对账」——列表外的节点/路由会被删除。
3. **验收门禁全绿才算完成**：硬编码 **0** · 无指派 **0** · 路由问题 **0** · `passSameTarget` 与批前一致。
4. **零硬编码人名**（用户硬要求）：流程节点里绝不出现 `人名@unit@P`；只有职务脚本 / 数据路径 / 显式发起人。

## 1. 三范式（先选对，再动手）

| 范式 | 机制 | 何时用 | 硬约束 |
|---|---|---|---|
| **A 组织职务脚本** | 节点 `taskScriptText` 用 `java_resources.getOrganization()` 取人 | 固定审批岗 | 脚本读不到表单数据 |
| **B 数据路径取人** | 节点 `taskDataPathList=['字段名']` | 审批人随表单选择变化 | 字段值必须是**身份 DN** |
| **C 显式发起人** | 节点 `taskParticipant={type:'creator'}` | 办理人=发起人 | 不能留空（空且无脚本→静默派发起人） |

## 2. A 范式：组织职务脚本契约

```js
var org = java_resources.getOrganization();      // ★ 不是 .organization()（写错被 catch 吞→静默回退）
var ids = org.unitDuty().listIdentityWithUnitWithName(unitDn, dutyName);  // 某单位上持某职务的身份 DN 列表
var chain = org.unit().listWithUnitSupNested(deptDn);   // 本部门 + 全部上级单位
var ci = JSON.parse("" + java_workContext.getWork()).creatorUnit;         // 发起人部门 DN
```

**作用域**：`chain`（部门+全部上级，最常用）/ `global`（全组织）/ `own:<职务名>`（先定位持该职务的单位，再在其上取目标职务）。

★★ **不卡单铁律**：每条职务链**最后一跳必须 `秘书长(chain)`**（秘书长只在顶层，chain 可上溯到顶）⇒ 任何部门发起人都能解析到人。组织缺某职务时沿链回退，流程照走；**补建职务并配人后，流程无需再改**。

## 3. B 范式：数据路径取人（表单驱动）

- `taskDataPathList` 指向表单字段名，用该字段的**值**当审批人。
- ★ **值唯一合法形态 = 身份 DN `姓名@unique@I`**（`@P`/姓名/unique 均无效→节点被跳过）。取主身份：`ORG_IDENTITY.xmajor=1`。
- ★ 平台约束（实测）：**`taskScriptText` 读不到表单数据** ⇒ 「按表单取人」只能走 B 范式。
- ★ 指向组织/单位 DN 会展开成**全部门成员**（=「全员派」失控）——必须指向**具体人**的身份 DN。

## 4. 六个会静默出错的坑

1. 保存按 id 全量对账 → 列表外的节点/路由被删。
2. 以官方为准覆盖会丢现状 `passSameTarget`（同人自动合并）→ 覆盖时必须显式保留。
3. 空身份节点被静默派给**发起人** → 自服务节点显式 `{type:'creator'}`。
4. 节点 `properties` 里有 `taskParticipant` **镜像**，服务端以 properties 为准；克隆节点会残留模板 `creator` → 新节点被当发起人而**合并跳过**。改指派必须**同时改顶层与 properties**。
5. `passSameTarget` 标在**被跳过节点自身的出向路由**上。
6. 表单 `data` 是**双层 JSON 编码**（库中为 `{"html":...}`）→ 改表单必须写回双层 + 改前后**前缀逐字符比对**，否则表单白屏。

## 5. 审计与验收

```bash
python o2oa优化/o2oa_audit/audit_system.py          # 全系统复审（硬编码/无指派/路由/passSameTarget）
python o2oa优化/o2oa_audit/proc_fix_batch1.py       # 干跑；--apply 写库（1~4 批同构）
python o2oa优化/o2oa_audit/b5_project_chain.py --apply   # 施工任务单：表单下拉注入 + 数据路径（幂等）
```

- **在用判定**：扫 surface `work`+`workcompleted`（`POST …/{work|workcompleted}/list/filter/{p}/size/{s}/manage`，含 `count`）。
- **E2E 走真单**：`switchuser`→`POST …/surface/jaxrs/work/process/{pid}`→逐节点 `GET …/task/list/work/{wid}`→
  `POST …/task/{tid}/processing`（★ 须用**任务持有人 token**）。测完 `DELETE …/work/{wid}`，DB 复核 0 残留。
- **验收**：干跑全部通过 → `--apply` PUT 200 + 回读 → 复审门禁全绿 → E2E 每节点落到具体人。

## 6. 结构复原 vs 有意简化（判定法）

- **改坏的复原**：现状是官方结构的**严格子集（纯删除）**→ 按官方补回缺节点/路由（保留现状 `passSameTarget`）。
- **有意的保留**：现状含官方没有的节点/条件分支（自定义逻辑，且在办件）→ **只修指派、不动结构**。
- 判定证据：节点 id 级对照（官方导出 vs 现状）+ 是否有在办实例。
- ★ **改名不换节点**：要把某节点改名（如「分管领导审核」→「秘书长审核」）时，**只改 `name`、保留官方 id**——
  在办待办按路由 id 流转，改名**零副作用、不破引用**。
- ★ **照抄官方会「无人可派」**：官方若用 `taskDataPathList` 取人、而**现表单已无这些字段**（表单被改过），
  复原时照抄会让节点无人可派 ⇒ 必须改 **A 范式组织职务脚本**，并保留现网 `passSameTarget`。
  （实证：请购申请 `724266a0` 复原官方链路 + 官方节点 `b5b8ce2c` 改名「秘书长审核」；详见知识库稿 §12）

## 7. 企业化运维（成果交付六件套）

治理成果（脚本/报告/知识库稿/技能）**不止写进库**，还必须走完「持久化六件套」：

1. **知识库化** —— 写 `docs/knowledge_base/*.md` → `python tools/ingest_knowledge_base_docs.py` 灌入 O2OA 知识库（供 AI 检索）。
2. **技能化** —— 方法沉淀成本 skill；`bash tools/sync_skills_to_repos.sh` 镜像进两仓。
3. **更新档案** —— 登记 `tools/o2_docs_audit.py` 的 REGISTRY → `--all` 刷新 `docs/DOC-STATUS.md`；更新 `docs/README.md`、`docs/CHANGELOG.md`。
4. **推仓库** —— git 提交推送（驱动仓 `o2oa-driver` + 真源仓）。
5. **备份** —— `tools/backup_o2oa_chain.bat`（状态+文件+DB）。
6. **镜像** —— 若改到了构建期资源（★ 网关 KB 在 `gateway/data.db`，烘进镜像），必须回写 + 重建 + force-recreate 才能真正持久。

## 8. 启动体验：草稿发起 `defaultStartMode`（★ 治「点选后没反应 / 选完身份就返回」）

**症状**：用户点某流程 → 弹出身份卡 → **选完身份后流程窗口没打开、界面"退回"**（"点选后没有反应"）。

**根因（不是坏了）**：前端 `x_component_process_Application/Main.js · startProcessInstance()`
**只在「发起人本人就是首个任务处理人」时（`currentTaskIndex !== -1`）才自动打开表单窗口**；
否则只弹一条桌面"已启动"提示、**不开窗**。若该流程首节点指派给的是别人（如"行政专员→李芳"），
非该岗的发起人就会"选完身份就返回"。**服务端发起完全正常**（任务正确落岗），问题纯在前端是否开窗。

**根治 = 把该流程设为「草稿发起」**：`defaultStartMode: "instance" → "draft"`（整份 GET/改/PUT）。
`x_desktop/js/base_work.js · startWork()`：`draft` 分支走 `draw()` →
`POST /x_processplatform_assemble_surface/jaxrs/draft/process/{processFlag}`
→ 服务端回**绑定好表单的草稿模板** → 前端**无论首任务处理人是谁都直接开表单**，绕开上述判定。

- 该接口回的是**草稿模板**（`data.work` 是 `Work` 对象、`id` 空、`form` 已绑定），不是已落库草稿；
  判"能不能开窗"看 `data.work.form`；真正落库在表单保存时。
- 草稿提交后任务仍按首节点指派落到对应岗（业务预期）——**不要**为了"让发起人有待办"而乱改指派。
- 脚本：`o2oa优化/o2oa_audit/proc_fix_bgyp_restore.py`（干跑/`--apply`/回读）；E2E：`e2e_bgyp.py`。

### 顺带：节点「改名 + 收紧」一步到位（同 §6）
- **改名**：只改 `name`、**保留 id**（在办零副作用）。
- **收紧**：A 范式的 **`own:<职务名>`** 作用域 —— 先定位持该职务的单位、再在其上取职务，
  把原来的 `global`（全组织泛查）钉到**具体部门**。
  ⚠️ 别用 `chain` 代替收紧：chain 只含发起人本部门及上级，**非该部门的人发起时会跳过该岗、错落兜底岗**。
