# O2OA 本地化实践 SOP：数据层联通与 o2oa API 接入指南

**版本**：v1.0 — 2026-09-22  
**作者**： analyst / manager（小复）  
**适用范围**：O2OA 社区版 10.0.2（本地 Docker 自托管 · 已断云）  
**相关记忆**：`.workbuddy/memory/MEMORY.md` + `2026-09-21.md`

---
## 1. 背景与目的

- **背景**：秘书长（用户）指令「把 O2OA 真正用起来」，从组件上传卡死、19 个应用包部署、数据层打通，到两个具体故障修复（CRM 百度地图弹窗、每月一号定时代理启用），全部闭环。
- **目的**：把第八轮起对话中关于「实现数据层联通功能」的经验教训，以 SOP 形式固化为可复用标准作业程序；同步梳理 o2oa_api 接入/补全要点，避免后续项目重蹈覆辙。

---
## 2. 基本概念（术语对照）

| 概念 | 对应字段 / 表 | 备注 |
|---|---|---|
| 自建表定义 | `X.自建表定义` | 在数据中心执行「创建数据库表」后方可使用 |
| 物理表 | `CMS_* / xtable_*` | 底层存储表，已就位 |
| 视图（QRY_VIEW） | `Qry_view.xdata` | 必须是 **字符串**（`json.dumps(...)`），否则 HTTP 500 |
| 无 TablePlan | `dealPlan()` switch 只认 cms | `table` 类型视图执行链无实现 → NPE，不使用 table 类型视图 |
| 表行接口直读 | `POST /x_query_assemble_surface/jaxrs/table/list/table/{flag}/row/paging/{p}/size/{s}` | body `{}`，返回裸字段名（不带 x 前缀），用于门户显示自建表数据 |
| 门户 | 3 门户 / 16 页 | 按「综合管理/业务管理」分类；`PTL_PORTAL.xportalCategory` 分组 |
| toPortal vs openApplication | `Main.toPortal(portalId, pageId)` | `openApplication` 因 `multitask=true` 会另开新页签 → 用户看到「点了没反应」 |
| 门户 ≠ 办理入口 | — | 没有门户 ≠ 应用不可用；真正办业务走流程应用工作台（iframe） |

---
## 3. 数据层联通——核心实施路径

### 3.1 前置检查
- 31 张自建表**定义+物理表+种子数据**已就位（`CMS_*` / 自建表）。
- 确认 `project_no` 全局主干（11 处）；各业务编号 `contract_no / budget_no / expense_no / archive_no / employee_no` 已按规范 `f6006001-form-xxxx` 注册。

### 3.2 关键修复 1：视图 data 必须是字符串
- **问题**：106 个视图里 40 个 `xdata=NULL`（恰为 6 应用的视图）→ 嵌视图渲染空白。
- **根因**：`o2oa_builder.view()` 写库时未 `json.dumps(...)`，导致数据中心存入对象而非字符串；前端固定链 `JSON.decode(MWF.decodeJsonString(data.data))`，decodeJsonString 把 str 原样拼进 `["…"]` → 裸 JSON 抛 `Unexpected identifier 'json'` → 白屏。
- **修复**：
  - `o2oa_builder.view()` 的 `data` 要 `json.dumps(...)`（落库 `QRY_VIEW.xdata`）。
  - 验证器必须**完整复刻双层解码链**：只有经过 `decodeJsonString` 的字段（Form/Page 的 data、mobileData）要转义；`QRY_VIEW/QRY_STAT/自建表 data` 原生未转义 → 别一刀切。
- **验证**：七道构建校验全绿；导入后门户首页 10/10 可打开。

### 3.3 关键修复 2：无 TablePlan——改用表行接口直读
- **问题**：`dealPlan()` switch 只认 cms，其余全给 `ProcessPlatformPlan` → 抛 `adjustWhere` NPE。
- **根因**：本版本（10.0.2）无 TablePlan 支持，`table` 类型视图执行链未实现。
- **修复**：
  - 不要试图用 table 类型视图渲染自建表数据。
  - 改用**原生 106 视图从不使用 table 类型**，反证不受支持。
  - 新增 `table_holder()` + `_LIVE_JS.loadTables()`：`POST /x_query_assemble_surface/jaxrs/table/list/table/{flag}/row/paging/{p}/size/{s}`（body `{}`），返回裸字段名。
  - 门户要显示自建表数据，别嵌视图，走「表行接口直读 + 前端渲染」。
- **验证**：HR「员工档案」9 行真实员工、合同台账千分位正确、`startWork` 真实创建流程实例；七道校验全绿。

### 3.4 关键修复 3：门户——1 个聚合门户 + N 个分类栏目页
- **OA 惯例**：门户是**按业务域聚合的门面**，不是「一个流程应用配一个门户」。
- **设计**：一个门户 + N 个分类栏目页（横向 Tab）。
  - `PTL_PORTAL.xportalCategory` 分组展示；我方自定义两类「综合管理」「业务管理」。
  - 补门户时：**一个门户 + N 个分类栏目页**（横向 Tab），别再开 N 个孤立门户。
- **核心 bug 与修复**：
  - 页内 Tab 点击无效：原用 `openApplication` 因 `multitask=true` 会另开新页签 → 看起来没反应。
    - **正解**：遍历 `layout.desktop.apps`（key 形如 `Portal-<32位HEX>`），找带 `toPortal` 且 `options.portalId` 等于目标的**当前实例**，调 `Main.toPortal(portalId, pageId)`。
- **验证**：业务总览 4 表 11 行、跨门户 4 行均真实；门户实例数恒为 1。

### 3.5 关键修复 4：无门户 ≠ 不能用
- **结论**：01 项目/03 预算/04 财务/05 档案四个「无门户」应用功能完全可用，入口是 O2OA 原生「流程应用工作台」，不是门户。
- **实证**：42 条流程全部落库、全部 `xstartableTerminal=all`（任何人可发起）；桌面有现成页签「流程应用-××应用」等，点击即开；工作台含待办/已办/草稿+发起流程按钮。
- **定位**：门户=仪表盘/门面；流程应用工作台=真正业务办理入口。没有门户 ≠ 不能用。

---
## 4. 门户建设最佳实践（三门户 16 页）

| 门户 | 页数 | 分类 | 备注 |
|---|---|---|---|
| 05 合同 | 4 页 | 综合管理 | 首页/台账/统计报表/快捷入口 |
| 06 人力 | 7 页 | 综合管理 | 首页/员工档案/员工管理/人才市场/积分管理/考勤管理/员工自助 |
| 01 项目（承载） | 5 页 | 业务管理 | 跨应用聚合 01/03/04/05，定义在 `build/def_biz_portal.py` |

- **门户数据一律走 `table_holder`**（表直读）；`view_holder` 只用于 process/cms 视图。
- **栏目页生成器**：`o2oa_hr_portal.biz_header()` / `biz_view_page_html()`。

---
## 5. o2oa API 接入/补全要点

### 5.1 已覆盖的核心接口
根据对话实测与 `api.json` 逆向，以下高频接口已在本地直连验证通过：

| 功能 | 接口路径 | 备注 |
|---|---|---|
| 用户登录 | `/x_organization_assemble_authentication/jaxrs/authentication` | credential/password 流程 |
| 组件列表 | `/x_component_assemble_control/jaxrs/component/list/all` | 带 `x-token` 头 |
| 代理列表 | `/x_program_center/jaxrs/agent/list/all` | `TriggerAgent` 每分钟实时查库；改库即生效 (`UPDATE CTE_AGENT SET xenable=1`) |
| CMS 分类 | `/x_cms_assemble/jaxrs/category/list` | 需确认 alias 逐字一致 |
| 内容管理文档 | `/x_cms_assemble_surface/jaxrs/doc/list` | 离线/在线均可 |

### 5.2 常用但易忽略的接口
- **定时代理启停**：直接 `UPDATE CTE_AGENT SET xenable=1/0`（无需 manager token，TriggerAgent 每分钟实时查库生效）。
- **门户跳转**：`Main.toPortal(portalId, pageId)` —— 必须在当前实例的 `layout.desktop.apps` 里命中，否则另开新页签。
- **组件资源部署**（非 zip 直接上传）：
  - 正确链路：`POST /x_program_center/jaxrs/deploy/web/resource/as/new/{asNew}` + `POST /x_component_assemble_control/jaxrs/component`（注册表条目）。
  - 错误入口：组件资源 UI 是错入口，`t.dispatchResource` 在 10.0.2 线上 `api.json` 中根本不存在 → 静默失败。

### 5.3 想要补全的接口（建议优先级）
| 接口 | 当前状态 | 建议 |
|---|---|---|
| CMS「固定资产」分类查询 | CMS_CATEGORYINFO 表为空 → 脚本空跑 | 若需生效，需先建立「固定资产」分类（alias 必须逐字一致）并录入资产文档；或改脚本对接 06 人力自建表 |
| 离线应用市场批量安装日志查询 | `InstallLog` 每次新增一条，无法据此判重复 | 已确认：离线安装不创建 Application 实体，InstallLog 每次新增一条；卸载离线装的应用别走 `market/{flag}/uninstall`（必 500） |
| 门户子页数据接口兼容性 | `QRY_VIEW.xdata` 必须是转义双层字符串 | 已固化：验证器必须完整复刻双层解码链，避免白屏 |

---
## 6. 常见问题与排查范式（沉淀为技能）

### 6.1 第三方 AK 失效排查范式
- **技能**：`o2oa-component-ak-fix`
- **流程**：
  1. 全局 grep `api.map.baidu.com` / 硬编码 AK 字面量 → 命中文件列表。
  2. verify 接口实测：`curl "http://api.map.baidu.com/?qt=verify&v=2.1&ak=<AK>"` → `{"error":201,...}` → SDK 内置表 `ta[201]` → alert()。
  3. 只把 URL 置空不够：`window.BDMapApiLoaded || loadDom("")` 仍执行 → 空 URL 拿回 HTML `SyntaxError`，再 load BDMarkerTool 报 `ReferenceError: BMap is not defined`。
  4. **必须让整个分支恒假**：`0&&!window.BDMapApiLoaded&&...` 或 `if(false && …)`。
  5. min 文件严禁插 `/* */` 块注释（与相邻注释嵌套冲突）→ MARK 只放文件头单行。
  6. `Main.js` 的 `if( !window.BDMapApiLoaded ){` 用**窄锚点**替换，不要整块模板匹配。
  7. 覆盖 `Main.js / Main.min.js / Main.min.min.js / BaiduMap*.js / AddressExplorer*.js` 共 8 文件。
- **验证**：Playwright E2E → DIALOGS 0 / PAGEERRORS 0 / BDMarkerTool 请求 0 / 百度外网请求 0。

### 6.2 定时代理启用范式
- **位置**：表 `X.CTE_AGENT`（非流程内 `PP_E_AGENT`）。
- **机制**：`xenable=0` 即「(禁用)」来源；cron `0 */30 * 1 * ?`（每月 1 号每 30 分钟）。
- **启用手法**：直接 `UPDATE CTE_AGENT SET xenable=1`——O2OA 的 `TriggerAgent` 每分钟实时查库，改库即生效，**无需重启、无需 manager token**。
- **两点事实**：
  1. 脚本目前空跑：CMS 无「固定资产」分类 → 查不到文档。要生效需建该分类或改脚本对接资产表。
  2. cron 频率偏高（1 号 48 次），建议改 `0 0 1 * * ?`（每月 1 号 01:00 一次）。

### 6.3 组件编辑卡死排查范式
- **根因**：前端 chunk `ComponentDeploy` 的 OK handler 整体 async 无 try/catch；其调用的 `t.dispatchResource` 在 10.0.2 线上 `api.json` 中根本不存在 → `TypeError: undefined` 未捕获 → 静默失败。
- **正解**：组件资源 UI 是错入口。正确链路：`POST /x_program_center/jaxrs/deploy/web/resource/as/new/{asNew}` + `POST /x_component_assemble_control/jaxrs/component`。

---
## 7. 验证与校验清单

| 校验项 | 通过标准 |
|---|---|
| 构建校验 | 七道全绿（`pack.py → validate_form_tree.py → validate_dom_rebuild.py → validate_xapp.py → validate_flow_topology.py → validate_portal.py → verify_excel.py --expect`） |
| 导入后复刻 | 门户首页 10/10 可打开（`python verify_portal_live.py`） |
| 数据一致性 | `project_no` 全局主干 11 处无断层；各业务编号对应关系正确 |
| E2E 真实流程 | Playwright+Edge：桌面标题正常、0 页面错误；办公中心待办 16 条真实流转 |

---
## 8. 相关记忆与技能入口

- **项目长期记忆**：`.workbuddy/memory/MEMORY.md` + `.workbuddy/memory/2026-09-21.md`
- **沉淀技能**：
  - `o2oa-component-ak-fix`（第三方 AK 失效排查范式）
  - `o2oa-portal-page-format`（门户/数据层格式与 toPortal 坑）
- **交付文档**：
  - `patches/客户管理-百度地图AK修复/`（8 文件全闭环 SOP）
  - `patches/定时代理-每月一号修改办公资产状态/`（README + 启用脚本）

---
## 9. 后续建议（待秘书长拍板）

| 选项 | 内容 |
|---|---|
| A. CRM 地图恢复 | 提供新百度地图 AK，改 3 处 `apiPath` + 去 `false` 即可。内网/断云环境建议离线瓦片或天地图。 |
| B. 每月一号代理优化 | 确认办公资产数据落点（CMS「固定资产」分类 或 06 人力自建表）→ 建分类或改脚本；并把 cron 改为 `0 0 1 * * ?`。 |
| C. 可选增强 | 若希望 01/03/04/05 四应用也有「门面」，可各补 1 个门户页（已验证的 table_holder 模式，工作量小；不做也不影响业务办理）。 |
| D. SOP 固化 | 已完成（当前文件），下次遇类似任务直接调用技能 `o2oa-component-ak-fix` / `o2oa-portal-page-format` 即可。 |

---
**结束语**：本 SOP 记录了第八轮起对话中关于数据层联通、门户建设、故障修复及 API 接入的全部实战经验。希望能为后续 O2OA 本地化落地提供可复用的方法论，避免在相同问题上重复排查。如有遗漏或需调整，请秘书长指正。

---
*文档生成于 2026-09-22 · analyst/manager 模式 · 小复*