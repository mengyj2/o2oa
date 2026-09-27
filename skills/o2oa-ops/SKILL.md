---
name: o2oa-ops
description: O2OA（社区版 / Docker 自托管，10.0.2 实证）**写入 / 删除 / 注册类**运维操作集中入口。当用户要求「克隆应用」「批量装插件」「删 HR 模块」「拆公共数据应用」「注册到开始菜单」「切换登录开关」「改门户菜单项」「改网盘指向」等**会改变 O2OA 状态**的操作时调用。★ 铁律：这些工具**一律由 WorkBuddy(本机助手)在用户明确确认后执行**，绝不暴露给自治的 O2OA 网关助手（网关助手只通过 o2oa_ops_mcp 拿到只读/导出类工具）。所有脚本唯一真源在 `D:\O2OA\tools\`。
agent_created: true
category: operations
---

# O2OA 写入 / 删除 / 注册类运维操作

本 skill 与 `o2oa-app-io`（只读/导出）互补：**这里只收会改变 O2OA 状态的操作**。

## 0. ★★ 最高铁律

1. **先确认，再动手。** 凡本 skill 下任一工具，执行前必须向用户明确展示「将做什么、影响哪些应用/表/菜单项、可否回滚」，取得明确同意。
2. **绝不进自治 MCP。** 这些工具**不**写入 `gateway/config.json` 的 `mcp_servers`，也不做任何 MCP 暴露——自治网关助手（18790）只能看到 `o2oa_ops_mcp` 的只读/导出工具。
3. **单一真源。** 全部脚本位于 `D:\O2OA\tools\`（与 git 仓库、`o2oa_ops_mcp` 同源）。本 skill 不另存副本。
4. **破坏性操作先备份。** 删应用/拆模块前，先跑 `tools/backup_o2oa_state.sh`（或确认最近备份可用）。

## 1. 工具清单（按风险分组）

### 1.1 安装 / 克隆（写入，需确认）
- **`o2_batch_install.py`** — 断云环境批量安装离线插件包。
  - `scan` 仅扫描；`install` 去重安装；`install --keep-all` 全装；`--only-name A,B`/`--skip-name A,B` 过滤；`--fix-only` 只修 setup.json。
  - 环境变量 `O2OA_BASE/USER/PWD`、插件目录 `O2OA_PLUGIN_DIR`(默认 `D:\O2OA\插件`)。
- **`o2_clone_app.py`** — 把 `.xapp`/zip 克隆改名重映射 id 后重装（避免覆盖原件）。
  - `--src <包> --out <新包> --new-name <名> --new-alias <别名> --rename-map <json> [--dry-run]`。
  - 关键坑：xapp 内 id 必须重映射；`data` 字段只能文本级替换，不可 json 往返。

### 1.2 删除 / 拆解（破坏性，先备份）
- **`o2_delete_hr.py`** — 级联删 HR 模块(6006)：流程应用→12 张表定义→数据应用→7 门户页→门户→菜单。物理 DROP `QRY_DYN_T6006*` 需另在 bash 跑（deleteTable 只删元数据）。
- **`o2_delete_common_dict.py`** — 删空壳「公共数据（全局）」应用 + 其空数据应用。
- **`o2_verify_hr_delete.py` / `o2_delete_hr_works.py`** — HR 删除前后的核对/工作流辅助（见文件头）。

### 1.3 开始菜单注册（写入 DB / 容器文件 / patch）
- **`o2_register_startmenu.py`** — 把导入但未进开始菜单的 WAR 组件注册成 CPT_COMPONENT。`list`(看现状)/`plan`(预览)/`apply`(幂等注册)/`fixportal`(修 pcClient 空)。
- **`o2_sync_startmenu.py`** — 一键三层补登记（WAR 组件→CPT_COMPONENT；流程/门户→applications.json；门户 pcClient→true）。`check`(体检)/`apply`(执行)。
- **`o2_register_process_apps.py`** — 流程/门户型应用走 `applications.json` 深链。`gen`(只生成 patch 文件)/`push`(生成+写容器立即生效)/`show`/`reset`。

> ⚠ 落地点：servers/webServer 在镜像层不在卷，故 `applications.json` 必须**同时**写容器运行时路径和 `patch/web/applications.json`（供 Dockerfile COPY 固化），否则 docker 重建即丢。

### 1.4 配置 / 菜单项改写（写入）
- **`o2_toggle_login.py`** — 切换 `captchaLogin`/`codeLogin`。`off`/`on`/`show`。用于自动化 UI 验证时临时关闭验证码。
- **`o2_dict_set_menu_app.py`** — 按 xpath 改门户「应用菜单」字典项字段（直写 MySQL，可 `rollback`）。`check`/`apply`/`rollback`。
- **`o2_drive_switch_menu.py`** — 把门户菜单「企业网盘」app 从 `File` 切到 `Drive`（自研组件）。

### 1.5 品牌词 / 公文数据治理（写入，幂等）
- **`fix_wenzhong_orgname.py`** — 公文 demo **公司名**残留（纵横翱途→中国复合材料工业协会）：红头 HTML、成文/版记单位、前缀置空、悬空 DN。**只覆盖 `QRY_ITEM`**。
- **`rename_gongwen_brand.py`** — 公文**发文字号（冠字）/红头名称**品牌词替换（2026-09-26 新增）。
  - 覆盖**两处存储**：① `QRY_ITEM.xstringShortValue`（`xpath0`=`crowns`/`redHeaders`/`datatable`）；② `PP_C_SNAP.xproperties`（JSON `crowns.data[].crownName`）——①的兄弟脚本漏了②，**同类残留必查多存储层**。
  - 顺带清 `filetypeEditionUnitPrefix`/`filetypeIssuanceUnitPrefix`（**前缀一律置空**，渲染=前缀+顶层单位名）。
  - 映射表在文件头（`CROWN_MAP`）；REPLACE 链**长串在前**（「兰德翱途联合发文」含「翱途」）。

> ★ 品牌词治理通用法（详见 KB ch16/ch17）：
> 1. **全库扫描**：`information_schema.COLUMNS` 取 X 库全部 char/varchar/text 列 → 逐列 `SELECT 'T.C', COUNT(*) FROM T WHERE C LIKE '%关键词%' HAVING n>0` 汇总执行。O2OA 的 `xdata` 均为 longtext，**blob/binary 列数=0**，故文本列扫描即完整。
> 2. **只走 SQL REPLACE，不走设计器 API**（设计器保存会重算清空 `PTL_PAGE.xproperties.relatedScriptMap` → 门户点击全失效，KB ch15）。
> 3. **MySQL + API 双验 + `docker restart o2oa-server`**（CMS/流程配置有 flag 级缓存）。
> 4. **品牌词分两类**：自己的组织品牌残留（清）vs 软件产品自身品牌（O2OA/翱途，属官方发行包，保留）。
> 5. `deploy/db/seed-*.sql` 需同步检查，否则重建实例会带回旧品牌。

### 1.6 其它（非本 skill 主责，按需调用）
打包/分支/看门狗类见各自 skill：`o2_pkg.py`(打包)、`o2_package_branch.py`(分支打包)、`o2_sandbox_harden_watchdog.py`(沙箱硬化看护)、`o2_state_guard.py`(状态守卫)、`o2_fix_xadmin_org.py`(xadmin 组织修复)、`o2_drive_selftest.py`/`o2_drive_entry.py`/`o2_drive_cleanup_testdata.py`(网盘自检/入口/清测试)、`o2_batch_person_contact.py`(批量人员联系人)。

### 1.7 会议模块（楼宇 / 会议室 / 会议预定，2026-09-27 实证）

**存储**：`X.MT_BUILDING` / `X.MT_ROOM` / `X.MT_MEETING`（含 `MT_MEETING_invitePersonList` 等子表）。
**授权**：建/改楼宇与房间、管理员视图需 `manager` 或 **MeetingManager 角色**（xadmin 已满足，无需额外配）。

**播种 / 改名（API，即时生效，无需重启）**
- 建楼宇：`POST /x_meeting_assemble_control/jaxrs/building` `{"name":"7c12"}` → 返回 id。
- 建房间：`POST /jaxrs/room` `{"name":"大会议室","building":"<楼宇id>","capacity":20,"available":true,"floor":1}`。
- 改名/改属性：`PUT /jaxrs/building/{id}`、`PUT /jaxrs/room/{id}`（**整对象覆盖**，先 GET 再改再 PUT）。
- 列表：`GET /jaxrs/building/list`（含 `roomList`）、`GET /jaxrs/room/list`。
- 落地现状：楼宇 `7c12`(74714328…) + `大会议室`(811e4b03…,20人) + `小会议室`(02da4bc3…,8人)；★ 这三件套是 **MySQL 业务数据**，不入 git/驱动仓，随 `tools/backup_o2oa_state.sh` 带走；从零恢复须重新播种。

**★★ AI 卡片「申请会议」曾有致命缺陷，2026-09-27 已改为一步落库**
- **历史缺陷（官方样例，务必别再按它做）**：`POST /x_program_center/jaxrs/invoke/MCP_createMeeting/execute`
  **只查空闲会议室并回 `type:output` + `roomObj`，不落库**；真正创建在卡片「确认预定」按钮里。
  → 用户不点按钮就没有会议（`MT_MEETING` 长期 0 行即为此故），卡片还**无 error 回调，失败静默**。
  → 症状：**AI 说「已安排」，界面里什么都没有**。
- **现行做法（硬化版）**：invoke 脚本校验通过后**自己** `self.applications.postQuery("x_meeting_assemble_control", "meeting", body)`
  直接创建，**一次调用即落库，无需任何二次点击**；卡片只留「查看会议」按钮。
  - ★★ 内部调用 `effectivePerson.isCipher() === true` → body **必须显式传 `applicant`**（=当前调用者 DN），
    否则报 `person: not exist`。
  - ★★ `postQuery` 第二参是**相对路径、不带 `jaxrs/`**（写 `"meeting"`；写 `"jaxrs/meeting"` → 404）。
  - 手工等价形态：`POST /x_meeting_assemble_control/jaxrs/meeting`（`room` 传**房间 id** 不是名字）。

**日期坑**：`GET /jaxrs/building/list/start/{s}/completed/{c}/allmeeting` 的日期必须 `yyyy-MM-dd HH:mm`；
★ **空格必须 URL 编码**（`%20`），否则 Tomcat 返回 500 或客户端 `_validate_path` 直接抛错。

**视图路由速查**
- 我的会议：`jaxrs/meeting/list/coming/month/{count}`、`.../coming/day/{count}`、`list/year/{y}/month/{m}/day/{d}`。
- 管理员/会议可见人：`listOnMonthAll`、`listOnDayAll`（前端 `Main.js isMeetingViewer()` 由系统配置 `meetingViewer` 名单 + `isManager` 决定；普通用户只走 `listOnMonth` = 本人申请人/受邀人/审核人）。
- 图形化入口：会议管理应用 →「会议室」页签（楼宇/房间维护，按钮仅管理员/MeetingManager 可见）；新建会议走日历视图 → 选房间。

> 副作用提醒：用 `GET person/{flag}/reset/password` 重置密码（新密码=`手机号后6位+%o2`）后，
> 该账号登录会带 `passwordExpired:true`（网页端提示改密）；实测 `GET person/{flag}/set/password/expired/time/{date}` 改期后该标记**仍为 true**，需用户首次登录自行改密。

**★★ 硬化版（2026-09-27 起，标记 `[o2-meeting-harden]`，源码 `patch/meeting/`）**
- **时间必须 `yyyy-MM-dd HH:mm:ss`**：`ActionCreate` 传无秒/ISO-T 直接 500 `Unable to parse the date`；
  硬化版 invoke 已把 AI 给的各种写法（无秒/斜杠/ISO-T/带Z）统一归一化后再创建。
- **可直接落库**：invoke 内 `self.applications.postQuery(服务, "meeting", body)`（★ 必须传 `applicant`、路径不带 `jaxrs/`）。
- **失败一律 `type=error` 且 `data` 恒为对象**（含 `statusText/message`），卡片模板 `${statusText}` 才不会回退成字面量。
- **六道守卫**（删任一即复发）：时间归一化 / 空楼宇·空会议室守卫（官方硬访问 `json.data[0].roomList` 会崩）/
  邀请人归一化（数组·逗号串·JSON 串）/ 房间名容错匹配（精确→去括号→唯一包含）/ **占用与不存在分开报错** /
  失败可读中文。
- **定义四分身（改一处不生效）**：
  ① 服务端脚本 = O2OA invoke 实体（库，**不在 git/镜像**）；
  ② 卡片脚本+模板 = MCP 定义 `extra.script`/`extra.template`（库 + 网关 kv `mcp:<id>`；O2OA 会代理转发 `/ai-gateway-mcp/update`）；
  ③ 容器 `servers/*/work/x_ai_assemble_control/WEB-INF/classes/InitMcp.json`（**war 启动会重展，只改这里重启即丢**）；
  ④ war 内 `WEB-INF/classes/InitMcp.json`（构建期 `PatchInitMcp.py` 烤入）。
**重放 / 自检（写入，需确认；自检只读+自动清理）**
- **`o2_patch_meeting.py`** — 会议链路硬化重放。`check`(体检) / `apply`(应用，幂等带备份)。
  改完卡片脚本要**先跑** `patch/meeting/gen_InitMcp.py` 再 apply。
- **`o2_meeting_selftest.py`** — 7 用例回归（正常落库/占用/不存在/未指定/时间非法/邀请人不存在/时间倒挂），
  自带清理。**改完 `patch/meeting/*` 或 apply 后必跑**。`[用例号...]` 可只跑指定用例。
- 看门狗启动后台自动 apply → 换库/重建后无需手动补；构建期由 Dockerfile 调 `patch/meeting/PatchInitMcp.py` 烤进 war。
- **★ 幂等判据一律用「与仓库源逐字符（JSON 等值）比对」，不要用「含硬化标记」**
  （只认标记会让"脚本升级了但线上还是旧硬化版"被静默跳过——`o2_patch_meeting.py` 与 `PatchInitMcp.py` 都踩过）。
- **三个已修的真 bug（勿回退）**：
  ① 网关 `o2_agent_gateway.py` 的 `/ai-gateway-mcp/update|delete`：路由无 `{flag}` 却把 flag 声明必填
     → FastAPI 当必填 query → **任何从 O2OA 界面改 MCP 定义都 422/500**；现支持 路径/query/body.id。
  ② 更新 MCP 的 flag **必须用记录 id**：用 name 当 flag 会**新建一条重复定义**（实测踩过）。
  ③ 卡片模板变量必须与 invoke 返回的 `data` 键**一一齐全**，否则 `renderTemplate` 原样回退成 `${x}`。

**★ 权限矩阵（2026-09-27 实测，常被误解）**
- 建**会议**：`Meeting ActionCreate` **无权限校验** → 任何登录用户都能建，无需额外配置。
- 建**楼宇/会议室**：需 `MeetingManager` 角色 **或** Manager（`isAdministrator()`）；
  判据 = `Business.buildingEditAvailable()/roomEditAvailable()`，前端 = `MWF.AC.isMeetingAdministrator()`。
- 角色成员查 `ORG_ROLE_personList.xpersonList`；★★ 角色 `xunique` 是 **`MeetingManagerSystemRole`**
  （不是 `MeetingManager`），DN `MeetingManager@MeetingManagerSystemRole@R`——按 'MeetingManager' 查会**查不到**，
  曾差点误判成"没配"。
- 加人：`PUT /x_organization_assemble_control/jaxrs/role/{flag}` 传 `personList`，
  元素**必须用 DN**（如 `李芳@lifang@P`；传 personId 不生效，因内部 `person().pick()` 需可解析标识）。
- 常态：孟弋洁(Manager)=可建会+可建房间；李芳(MeetingManager)=同；普通用户=仅可建会。
- ★★ **GUI 维护路径（首选，不用改代码）**：桌面 → 开始菜单(☰) → **组织管理** → 左侧竖栏第 3 个图标
  **「角色管理」** → 左列选 `MeetingManager` → 右侧 **「个人成员」** 页签 → 右上角 **「添加」**（勾选后「删除」）。
  - 深链 `/x_desktop/app.html?app=Org`；组件 `servers/webServer/x_component_Org`（`RoleExplorer.js`）；
    左侧竖栏按钮靠 `div[title="角色管理"]` 之类定位；页签 DOM `.tabNodeContainerArea > div`
    （索引 0=角色信息 / 1=个人成员 / 2=群组成员）。
  - **同界面「群组成员」页签可批量授权**，人多时比逐人加省事。
  - 真机回归：`tools/o2_org_role_ui_verify.js`（Playwright 直驱，断言角色可见 + 成员增删入口）。
  - 下方 API 只是自动化时的**等价手段**，不是唯一途径。

**表结构坑**：`MT_MEETING` **无** `xinvitePersonList` 列，受邀人在子表
`MT_MEETING_invitePersonList`（`MEETING_XID` + `xinvitePersonList`）；`xroom` = 房间 id。

## 2. 标准执行流程

1. 用户提出变更诉求 → 先 `o2_app_io.py list` / `o2_inventory.py` 盘点现状（只读，可放心跑）。
2. 选对应工具，**先 `--dry-run` / `plan` / `check` / `show`** 预览，把预览结果贴给用户。
3. 等用户明确确认（"执行"/"apply"/"确定"等）→ 再跑真正写入的命令。
4. 写入后立即复检（再跑一次 list/inventory 或对应 check），确认达到预期、无副作用。
5. 若涉及镜像层文件（applications.json 等），提醒用户需 `docker compose build o2oa && up -d` 才能固化（bind mount 对 O2OA 无效）。

## 3. 凭据

`tools/o2.py` 统一用 `xadmin / o2oaadmin2026` 登录 `http://127.0.0.1:9090`；部分脚本用 `admin / o2oaadmin2026`（见各文件头）。无需本 skill 管理凭据。
