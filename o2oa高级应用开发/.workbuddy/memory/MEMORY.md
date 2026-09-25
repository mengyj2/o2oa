# O2OA 应用开发项目 — 长期记忆

> 机制细节（Wrap* 字段清单、控件模板字段名、源码依据、版式规范、门户页格式、离线装包链路）
> 见技能：`o2oa-portal-page-format` / `o2oa-market-offline-install` / `o2oa-local-admin-account` /
> `o2oa-cloud-cutoff` / `o2oa-component-ak-fix`。此处只留结论与坑。

## 项目定位与规模
为**中国复合材料工业协会**开发 **6 个 O2OA 应用**（01 项目 / 02 合同 / 03 预算 / 04 财务 /
05 档案 / 06 人力，横切五大），交付可直接导入应用中心的 `.xapp`。工作区 `D:\O2OA\o2oa高级应用开发`。

**交付规模（2026-09-21）**：7 个包（00 字典 + 6 应用）｜表单 53｜流程 42｜视图 40｜统计 35｜
自建表 31｜查询 31｜字典 41｜**门户 3 个 / 16 页（全部接活数据）**｜Excel 模板 31。
人工节点 **159** 个全部绑定表单（0 遗漏）。ID 规范 `f6006001-form-xxxx`；
**引用一律以 `.xapp` 内实际 ID 为准**（06 有命名与编号错位，勿凭名字推断）。

**数据主线**：`project_no` 全局主干（11 处）；`contract_no / budget_no / expense_no /
archive_no / employee_no`。财务报销/付款三方挂靠（project+budget+contract）；档案主表五方挂靠。

## 组织架构（脚本按「部门名 + 职务名」查人，名字须逐字一致）
- 顶层 **中国复合材料工业协会**：职务 `秘书长` / `副秘书长`
- 四部门：**综合部**、**研究技术部**（秘书长分管）；**会员服务部**、**行业发展部**（副秘书长分管）
- 四部门均设 `部门负责人`，**由分管领导兼任**；综合部仅 1 人，兼设
  `人事专员` / `财务专员` / `档案管理员` / `合同管理员`
- ★ 设部门职务前**必须先把该领导加入该部门成为成员** —— `UnitDuty` 绑的是**身份(Identity)**
  不是人员，身份数 ≠ 人数。处理人查不到时 O2OA 默认**把待办送给拟稿人**。
- 审批链：部门负责人（兼）→ 综合部 → 秘书长 → 综合部员工执行；**终审统一送秘书长**。
  同人免签：`_inject_skip_choice()` 自动插选择节点，命中 19/42 条流程。
- 协会组织与「大企业模板」差异极大（**无财务部/法务部/人力资源部**）→ 写脚本前必须确认组织，勿套模板。

## 构建与校验（`build/`）
类库：`o2oa_builder.py`（含 `escape_json_string()`）｜**`o2oa_org.py` = 组织架构 + 处理人脚本 +
路由条件脚本的唯一来源**（六个 `def_*.py` 统一 `from o2oa_org import *`）｜`o2oa_page.py`（栈式）
｜`o2oa_portal.py`（`portal_page_data()` + `table_holder()` + `_LIVE_JS`）｜`o2oa_hr_portal.py`
｜`pack.py`（打包入口）。

**改任何定义后必跑（七道全绿才交付；第 5~7 道由 `pack.py` 串跑）**：
```
PY="C:/Users/meng_/.workbuddy/binaries/python/versions/3.13.12/python.exe"; cd build
"$PY" pack.py; "$PY" validate_form_tree.py; "$PY" validate_dom_rebuild.py
"$PY" validate_xapp.py; "$PY" validate_flow_topology.py; "$PY" validate_portal.py
"$PY" verify_excel.py --expect
# 导入后：python verify_portal_live.py   ← 线上复刻 JSON.decode，10/10 才算首页可打开
```
- `validate_flow_topology.py`(T1~T9) 是**唯一能发现路由缺陷**的校验器，改流程必跑。
- `validate_portal.py`(P0~P10) = 门户页格式 + 活数据接线。
- ★ 第七道**不要**用 `verify_excel.ps1`：中文路径经宿主 PowerShell 传参被编码破坏 →
  `未能找到路径` 静默失败。`verify_excel.py` 零依赖且不受中文路径影响。

## 门户页覆盖（三门户 16 页，全接活数据）
- **05 合同** 4 页：首页/台账/统计报表/快捷入口 —— 分类＝综合管理
- **06 人力** 7 页：首页/员工档案/员工管理/人才市场/积分管理/考勤管理/员工自助 —— 分类＝综合管理
- **01 项目（承载）→ 业务管理门户** 5 页：业务总览(首页)/项目管理/预算管理/财务管理/档案管理
  —— 分类＝业务管理，`PORTAL_ID=o1001001-biz-portal-000000000000000001`，跨应用聚合 01/03/04/05，
  定义在 `build/def_biz_portal.py`，由 `def_project.py` 以 `PORTALS = _BIZ_PORTALS` 挂载。

> **OA 惯例**：门户是**按业务域聚合的门面**，不是"一个流程应用配一个门户"。按
> `PTL_PORTAL.xportalCategory` 分组展示；我方自定义两类「综合管理」「业务管理」。
> 补门户时：**一个门户 + N 个分类栏目页（横向 Tab）**，别再开 N 个孤立门户。
> 门户数据一律走 `table_holder`（表直读）；`view_holder` 只用于 process/cms 视图（见坑 12）。
> 栏目页生成器：`o2oa_hr_portal.biz_header()` / `biz_view_page_html()`。

## 导入顺序
`00_公共数据字典` → 01→06 依次 → 自建表需在数据中心执行「创建数据库表」。
**组织架构必须先建**，清单见 `docs/05_组织架构搭建清单.md`。

## 环境事实
Python `C:/Users/meng_/.workbuddy/binaries/python/versions/3.13.12/python.exe`；
Node `C:/Users/meng_/.workbuddy/binaries/node/versions/22.22.2-3/node.exe`。
- **无外网 PyPI**，`pip install` 全失败 → 需库时手写（见 `zero-dep-xlsx` 技能）。
- 本机有 Office16(x86) + WPS，`Excel.Application` COM 可用。
- **PowerShell 工具输出会被宿主吞掉** → 让脚本 `Set-Content` 写文件再用 Read 读。
- 容器 `o2oa-server`；MySQL `o2oa/o2oa_pwd`（库 `X`）。
- 宿主 Git Bash 路径 `/c/temp/...` **Python 读不通** → 一律写 `C:/temp/...`。
- 前端源码取法：`docker cp o2oa-server:/opt/o2server/webroot/x_component_XXX ./`（目录级）。

## ★ 阻断级坑（必记）

**A. 流程拓扑分两处存，缺一不可**：`Route.activity` = 目标活动 id；`Manual`/`Choice`.routeList
= 本活动**出口**路由 id；`Begin.route` = 开始活动出口（单值）。早期误写
`arriveActivity`（O2OA 中无此字段）且活动无 `routeList` → 源、目标双丢，42 条流程全部无法流转。
该错误源自 `validate_xapp.py` 的 `REQ_ROUTE`，校验器须同步修正。另：`begin_id` 构建时生成、
`def_*.py` 引用不到 → 起点边必须在 `to_wrap()` 里自动补。

**B. 不存在两个处理人 API**：`listIdentityWithUnitWithName(unit, duty)` → `getDuty(duty, unit)`；
`listLeaderByIdentity(dn, bool)` → `listSupPerson(dn, true)`。

**C. 门户页首页白屏 = 数据格式错（两层，缺一不可）**：门户页**不是网页**，是被当**表单(Form)**
渲染的数据对象。① 解码后必须是表单定义 JSON
`{"json":{…},"html":"<div mwftype=\"form\">…","id":"","isNewPage":false}`；
② `.xapp`/库内 `xdata` 存的是该 JSON **再被 JSON 转义一次**的字符串（= `o2.encodeJsonString` 产物）。
前端固定链 `JSON.decode(MWF.decodeJsonString(data.data))`，decodeJsonString 把 str 原样拼进
`["…"]` → 裸 JSON 抛 `Unexpected identifier 'json'` → 白屏、服务端零报错。
**只有经过 decodeJsonString 的字段（Form/Page 的 data、mobileData）要转义；
QRY_VIEW/QRY_STAT/自建表 data 原生未转义 → 别一刀切。** 验证器必须**完整复刻双层解码链**。
- 正文由 **Html 模块**承载，`insertAdjacentHTML` 注入**桌面同一 document**（非 iframe）→
  **CSS 必须限域 `#op-root`**，否则 `body{}`/`*{}` 污染整个 O2OA 桌面。
- Html 模块里的 `<script>` **不执行** → 运行时 JS 必须放 `json.events.postLoad.code`。
- 顶层 `html` 字段**必须含 `mwftype` 骨架节点**，否则 `Form._getModuleNodes()` 拿不到 node。

**D. 视图 data 必须是【字符串】**：`o2oa_builder.view()` 的 `data` 要 `json.dumps(...)`（落库
`QRY_VIEW.xdata`）。传嵌套对象 → 导入 query 应用报
`Expected STRING but was BEGIN_OBJECT at path $.viewList[0].data` → **整个数据中心应用 HTTP 500**。

**E. 本版本（10.0.2）无 TablePlan —— 自建表视图(table 类型)根本跑不了**：
`dealPlan()` switch 只认 cms，其余全给 `ProcessPlatformPlan` → 抛 `adjustWhere` NPE。
→ **门户要显示自建表数据，别嵌视图，走「表行接口直读 + 前端渲染」**：
`POST /x_query_assemble_surface/jaxrs/table/list/table/{tableFlag}/row/paging/{page}/size/{size}`
（body `{}`；返回**裸字段名，不带 x 前缀**）。流程/内容类视图（process/cms）仍可用 view_holder。

**F. 门户页内跳转必须用 `toPortal()`，不能用 `openApplication`**：后者因
`Portal.options.multitask = true` 会**另开新页签** → 用户看到"点了没反应"。
正解：遍历 `layout.desktop.apps`（key 形如 `Portal-<32位HEX>`），找带 `toPortal` 且
`options.portalId` 等于目标的**当前实例**，调 `Main.toPortal(portalId, pageId)`。
实现见 `o2oa_portal.py::_LIVE_JS.gotoPortal()`。

**G. 桌面组件（自建应用）**：装在 `/opt/o2server/webroot/x_component_XXX/`。
注册表 `GET /x_component_assemble_control/jaxrs/component/list/all`。
打开方式 `/x_desktop/app.html?app=XXX&status={}`（**不是**桌面内嵌 `layout.openApplication`，
后者报 `this.loadWindowFlat is not a function`）。
★ 浏览器实际加载的是 **min 版**（`Main.min.js`）→ 改非 min 版无效。
★ 组件 JS 带 `?v=10.0.2-<hash>` → 改完必须 Ctrl+F5。
★ 自建应用常见故障：**硬编码第三方服务 AK/SK 过期** → 前端 alert 阻塞。排查/修复范式见技能
`o2oa-component-ak-fix`（含 `fix_crm_bmap.py` 幂等补丁器 + `bake_into_zip.py` zip 固化器）。

**G2. 定时代理**：表 `CTE_AGENT`（`xcron`/`xenable`/`xtext`；`PP_E_AGENT` 是流程内代理节点，勿混）。
启用/停用 = `xenable`，前端「(禁用)」前缀即此。管理 API `x_program_center/jaxrs/agent/*` 需
manager token；★ `TriggerAgent` 每分钟实时查库 → **直接 UPDATE CTE_AGENT SET xenable=1 即生效**。

**H. 市场应用包入口是「应用市场离线安装」，不是组件资源**：包结构
`setup.json`(id/name/version)+`xapp/*.xapp`+data/web/custom →
`POST /x_program_center/jaxrs/market/install/offline`（multipart 字段 `file`，断云安全）。
重复装只更新同一模块实例，但 **InstallLog 每次新增一条**（勿据此判重复）。
`market/{flag}/uninstall` 要求 `Application` 实体，离线安装不创建 → 必 500，
**卸载离线装的应用别走这个接口**。
★ 10.0.2「系统设置→组件资源」上传 zip 点确定**必静默失败**（原生 bug：接口已从 api.json 删除）。
替代链：`POST /x_program_center/jaxrs/deploy/web/resource/as/new/{asNew}` +
`POST /x_component_assemble_control/jaxrs/component`。

**I. 环境/工具类**
- **别信 healthcheck**：ARM64/QEMU 下 `docker exec` 报 `error starting setns process`（**持续**失败）
  但 HTTP 正常 → 用 `curl` 判活、`docker cp` 取文件；跑不了命令改宿主侧 Python urllib。
  验证脚本的 ID **必须从模块自动取**（曾因手写 portal id 少一位误判 500）。
- **cipher token 20 分钟有效**（MkToken.java 常驻容器 `/tmp/work`）；
  宿主 Git Bash curl 读不了中文路径 `@file`（curl 26）→ 先 `docker cp` 进容器再容器内 curl。
- `docker exec sh -c` 内层命令用单引号防 `$` 被外层吃掉。
- `cat >> file <<'PYEOF'` heredoc 追加长代码会**截断损坏文件** → 一律用 Write/Edit。
- 压缩 JS **严禁插 `/* */` 块注释**（与相邻注释嵌套冲突）→ 标记只放文件头单行。
- **playwright 注入 token cookie 必须用 `url: BASE`**（不是 `domain`），且在**第二次 `goto` 之前**
  注入；`NODE_PATH` 指 `C:/Users/meng_/.workbuddy/binaries/node/workspace/node_modules`；
  登录用 `mengyijie`（**密码不是 `o2oa_pwd`**）。
- **门户只是"仪表盘/门面"，不是业务办理入口**：真正办业务走**流程应用工作台**
  （桌面页签 `流程应用-<应用名>应用`，内容在 iframe 内需遍历 `page.frames()`）。
  **没有门户 ≠ 应用不可用**（01/03/04/05 的 42 条流程全部 `xstartableTerminal=all`）。
- ★ **别只 grep 顶层 `*.js`**：打包器会产出 `X.min.js` / `X.min.min.js` 双份，
  漏一个就漏一个入口（见 CRM 案例）。

## 交付偏好（秘书长）
带导航 HTML + 同款 DOCX；报告 ≥1 万字、数据驱动、有据可查，反对科普式泛而浅；论据必须可查证；
官方发文忌口语化；多方案用 A/B/C + 风险表。称呼「秘书长」，自称「小复」。
