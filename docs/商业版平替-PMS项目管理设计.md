# 商业版平替 — PMS 项目管理（10 模块全生命周期）

> 2026-09-19 落地。基于公文管理系统（3aed5fe9）应用级克隆改造，覆盖商业版 PMS 十大模块。
> 应用 id：`9139f4c7-d337-4483-977c-0a0b16c7eecb`（alias PMS），查询应用 id：`d5d36c17-d252-4ff7-a0fa-d8049b761d4b`。

## 1. 成果结构（已安装并验证）

| 层 | 内容 |
|---|---|
| 门户 | 项目管理系统（7ec08640），10 页面 = 10 模块页签 |
| 页面 | 项目管理门户 / 项目启动 / 项目全景 / 进度管控 / 成本管理 / 质量管理 / 风险管理 / 相关方管理 / 合同管理 / 项目收尾 |
| 流程(7) | 立项管理、执行管理、项目任务流程、进度汇报流程、风险上报流程、质量检查流程、项目验收流程 |
| 视图(33) | 19 改名沿用 + 14 新增（门户-待办项目、全景-全部项目、启动-立项在办、进度-在办/已完成、成本-台账、质量-在办/已完成、风险-在办/已完成、相关方-台账、合同-台账、收尾-在办/已完成） |
| 表单(10) | 项目立项申请表 / 任务登记表 / 执行审核表 / 部门任务办理表 / 项目立项表_只读 / 立项单-打印 / 执行单-打印 / 附件子表单×2 / 操作条-子表单 |

新流程活动示例：进度汇报（进度填报→进度汇总→PMO审核→部门填报→进度归档）、风险上报（风险登记→风险分派→PMO评估→风险处置→风险关闭）、质量检查、项目验收同理。

## 2. 技术路线：应用级克隆改造（非重写）

1. **选源**：公文管理（版式即用户截图样式，脚本为通用框架）。
2. **id 重映射**：收集键名为 id/引用键的 uuid（209 个），剔除外部引用黑名单（45 个：已装应用 id、门户 id、原作者服务器 URL）→ 全部换成新 uuid，保证不污染公文管理原件。
3. **改名映射**：89 条文案映射（`pms_rename_map.json`，长串优先）。文案在 `page.data` 里出现两份（moduleList.text + html 镜像），整串替换一次改净两处。
4. **双层转义边界**（踩坑实录）：
   - `page.data` 是「字符串化的 JSON」→ 只能文本域替换，不可 json 往返（111854 ≠ 125771）。
   - 结构引号 = `\"`；字符串值内引号（html 属性/JS）= `\\\"`。
   - 页签模块定位锚点：`\"label_4\":{\"id\"`（含 `{`）到 `\"recoveryStyles\":null}`；改文案用 id 锚定 `retext_module`，防子串误伤（如"项目档案"⊂"项目档案管理"）。
5. **10 模块扩展**：3 源页注入 10 页签模块（`this.page.toPage("页面名")` 跳转，active 蓝底 #4381cb）；7 个克隆页从母版页深拷贝，queryView 用精确串重绑（tpl_view_id+qid 构造完整 old_block）。
6. **打包安装**：`o2_pkg.py build-install`（multipart 字段名必须 `file`；成功返回 `{"type":"success","data":{"value":true}}`）。

## 3. 工具链（留档于 D:\O2OA\tools\）

| 文件 | 用途 |
|---|---|
| `o2_clone_app.py` | zip→重映射自有 id→批量改名→写 xapp |
| `pms_rename_map.json` | 89 条改名映射 |
| `extend_pms.py` | 10 模块扩展器（页签注入/克隆页/视图/流程） |
| `o2_pkg.py` | 离线包构造 + `/market/install/offline` 安装 |
| `pms_final.xapp.json` | 最终安装包源（本目录留档） |

## 4. REST 验证接口速查（与直觉不同的路由）

- 流程列表：`GET /x_processplatform_assemble_designer/jaxrs/process/application/{appId}`（**没有 /list**；form 才是 `/form/list/application/{id}`）
- 查询应用列表：`GET /x_query_assemble_designer/jaxrs/query/list/all`
- 视图列表：`GET /x_query_assemble_designer/jaxrs/view/list/query/{queryId}`
- 视图执行：`PUT /x_query_assemble_surface/jaxrs/view/{viewId}/execute` body `{"filterList":[]}`
- 门户入口：`/x_desktop/portal.html?id={portalId}`（实测 200）
- war 内 `describe/sources/**.java` 含完整源码，查路由先读它，别猜。

## 5. 后续扩展

- Phase 4：PMS 业务数据接入 18790 网关自然语言查询（视图 execute 已程序化可用，可作为 NL2Query 的执行层）。
- 字段级增强：立项申请表可补预算/里程碑字段，成本-台账视图相应加列。
- 移动端适配未做（公文源页无移动版式）。

## 6. 页签修复记录（2026-09-19 第二轮，实况截图驱动）

首装后实况发现页签栏破碎，REST 拉取 10 页 moduleList 逐一定位出 5 个根因，全部修复：

| # | 根因 | 修复 |
|---|---|---|
| A | 门户页/启动页原有模块占用 `label_4_1` id → 注入 JSON 键冲突，「进度管控」页签被覆盖丢失 | 把 `label_4_1`（DOM 位置恰在页签行内 label_4 之后）改造为「进度管控」页签 |
| B | 7 个克隆页 `label_3` 文本被误改成本页名（出现重复页签且 click 指向项目全景） | 文本恢复「项目全景」 |
| C | 注入页签 click code 含字面反斜杠 `toPage(\"X\")` → 非法 JS，点击必报错 | 统一规范为 `this.page.toPage("页面名")`（code+html 两字段） |
| D | active 高亮全部错位（每页都没落在本页页签上） | 按 text==本页名 重设 bg=#4381cb，其余清除 |
| E | 页签 fs=18px/pad=20px → 10 页签溢出换行且 float:right 换行视觉破碎 | 统一 fs=14px/pad=0 7px；空占位 label_1 清 padding；logo 标题 28→22px，一行放下 |

**经验教训（克隆改造必读）**：
- 注入模块 id 必须先查目标页是否已占用（dict 键覆盖是静默的）。
- O2OA 门户页运行时**只读 moduleList**（text/styles/events），html 镜像仅设计器用 → 结构性修改可放心走「json.loads → 改 dict → json.dumps → 双层转义 PUT」路线，无需维持字节等长。
- `PUT /x_portal_assemble_designer/jaxrs/page/{id}` body `{"data": "<双层转义 inner>"}`；data_field = `json.dumps(inner_str)[1:-1]`。
- 保存后校验闭环：页签完整性 / 无重复 / active 归位 / click 无反斜杠（脚本 `tools/pms_fix_tabs.py`）。
- 页面 uuid 引用对照：视图+流程+表单+统计+门户+文件资源全命中；原作者外链图片（60.190.x.x / 192.168.10.206）为原版遗留，无功能影响。
