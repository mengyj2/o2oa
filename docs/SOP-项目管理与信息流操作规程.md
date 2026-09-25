# O2OA 项目管理与信息流操作规程 (SOP)
> 角色：Analyst / Manager
> 期限：基于 2026-09-18 ~ 09-21 全量实战（断云本地化商业平替部署、xadmin 修复、模块安全拆除、健康排查）
> 目的：将对话中沉淀的实战经验、根因诊断、加固措施转化为可执行标准作业程序，并完成 o2oa_api 文档补全

---

## 0、版本与背景
- **SOP 版本**：v1.0 — 2026-09-22
- **基线环境**：O2OA 社区版 10.0.2，Docker 自托管（mysql + o2oa-server），本地 AI 网关 (18790)，4GB UMA iGPU 限制
- **断云状态**：已彻底切断官方云平台联系（netlock + `web_enable=false`），所有应用通过离线安装/自建方式部署
- **核心目标**：在有限硬件（4GB VRAM）下实现稳定运行、安全拆除与健康运维

---

## 1、账号与身份模型 SOP

### 1.1 xadmin 非业务账号铁律
- **现象**：`xadmin` 是虚拟初始管理员，仅存内存（`Config.token().isInitialManager()`），**不在 `ORG_PERSON` 表**，无 identity。
- **根因**：启动流程时后端检测 `指定用户没有找到身份: xadmin.` → 被拒。
- **正解（已验证）**：
  1. another 建真实业务管理员账号，`unique=admin` / `name=系统管理员` / 密码 `o2oaadmin2026`；
  2. 挂顶层组织（中国复合材料工业协会），授权 3 系统角色：`ManagerSystemRole` / `OrganizationManagerSystemRole` / `ProcessPlatformManagerSystemRole`；
  3. 使用脚本 `tools/o2_fix_xadmin_org.py` 支持 `check`/`apply`/`rollback`，幂等。
- **切勿尝试**：在 xadmin 下建人员/身份，将触发「不能使用初始管理员标识」/「人员不存在」双重死锁。

### 1.2 组织 REST 契约速查
| 操作 | REST 端点 | 必填字段 |
|---|---|---|
| 人员列表（模糊） | `PUT /x_organization_assemble_control/jaxrs/person/list/like` | `{ "key": kw }` |
| 身份判定 | `GET /x_organization_assemble_authentication/jaxrs/authentication` (需 `x-token`) | 返回 roleList |
| 密码重置 | `PUT /jaxrs/person/{name}/set/password` | 字段名 **`value`**（非 password/newPassword） |
| 角色成员维护 | `PUT /jaxrs/role/{id}` | 提交完整对象、`personList` 写人员 id |
| 角色列表（空 key 返回空） | `GET /x_organization_assemble_authentication/jaxrs/authentication` (key 为空) | **别用它查角色**，改用已知 role id 直取 |

---

## 2、应用模块安全拆除 SOP（删除契约）

> **铁律**：顺序强制，错序会被系统拦截或留下孤儿数据。

### 2.1 删除顺序（强制）
```
流程实例 → 流程应用 → 自建表定义 → 动态物理表(手工 DROP) → 数据应用 → 门户子页 → 门户 → 开始菜单项
```

### 2.2 各层详细动作
| 层 | 动作 | 关键备注 |
|---|---|---|
| **流程实例** | `DELETE /x_processplatform_assemble_surface/jaxrs/work/{id}` | **必须先清**，否则应用删除会被拦截（“存在 N 个在流转中工作实例”） |
| **流程应用** | `DELETE /x_processplatform_assemble_designer/jaxrs/application/{appId}/false` | 即使 `false` 仍可能拦在在流转实例 |
| **自建表定义** | `DELETE /x_query_assemble_designer/jaxrs/table/{tableFlag}` | `tableFlag` = `QRY_SCH_TABLE.xid` |
| **动态物理表** | `DROP TABLE IF EXISTS QRY_DYN_T{模块号}xxx_...` | **`deleteTable` 只删元数据不 DROP 物理表**，必须手工清 |
| **数据应用** | `DELETE /x_query_assemble_designer/jaxrs/query/{dataappId}` | - |
| **门户子页 → 门户** | `GET .../designer/jaxrs/page/list/portal/{id}` → 逐删 `DELETE .../page/{pageId}` → `DELETE .../portal/{portalId}` | 先删全部子页再删门户 |
| **开始菜单项** | 改 `applications.json` 两处 + `docker cp` + `restart` | 1) 补丁源 `patch/web/applications.json`；2) 容器内 `$Layout/applications.json`；`bash` 中 `\$Layout` |

### 2.3 误伤防护
- 只按**精确 id / 精确名称**匹配，绝不用宽泛 `LIKE` 做删除。
- `CPT_COMPONENT` 内置项（OnlyOffice/CRM/TeamWork/WpsOffice 等）**不要动**。
- 门户内展示页 ≠ 模块自身（删页不影响那些模块）。
- **必跑基线核对**（见 2.4），确认：目标残留全 0、`component`/`cms_appinfo` 零变化，其他模块计数只减预期值。

### 2.4 基线核对 SQL（每次删除后必跑）
```sql
SELECT 'portal', COUNT(*) FROM X.PTL_PORTAL
UNION ALL SELECT 'pp_app', COUNT(*) FROM X.PP_E_APPLICATION
UNION ALL SELECT 'pp_process', COUNT(*) FROM X.PP_E_PROCESS
UNION ALL SELECT 'pp_work', COUNT(*) FROM X.PP_C_WORK
UNION ALL SELECT 'qry_table', COUNT(*) FROM X.QRY_SCH_TABLE
UNION ALL SELECT 'qry_query', COUNT(*) FROM X.QRY_QUERY
UNION ALL SELECT 'component', COUNT(*) FROM X.CPT_COMPONENT
UNION ALL SELECT 'cms_appinfo', COUNT(*) FROM X.CMS_APPINFO;
SELECT 'dyn_tables', COUNT(*) FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN%';
```
- 判定：`component` 与 `cms_appinfo` **必须零变化**（变了即误伤）；目标四类残留全 0。

### 2.5 空壳应用快速删除（新增模式）
当应用 **0 流程 / 0 表 / 0 实例 / 仅一个空数据应用** 时：
- 无需清 work 实例，直接两步 `DELETE`：流程应用 + 数据应用。
- 若有开始菜单 `@url:` 入口，按 2.3 同步移除。
- 删前/删后仍跑 2.4 基线：`pp_app` / `qry_query` 各减 1，`component`/`cms` 不变。

---

## 3、开始菜单「三源」机制 SOP

### 3.1 三源加载顺序
`Layout.Top.loadMenu()` 只读取：
1. `o2_core/o2/xDesktop/$Layout/applications.json`（默认 `[]`）——流程应用深链入口。
2. `GET /x_component_assemble_control/jaxrs/component/list/all` → MySQL `CPT_COMPONENT`，再经**硬编码 24 个内置名**过滤（`ActionCreate` 强制 `type=custom`）。
3. `GET /x_portal_assemble_surface/jaxrs/portal/list` → **仅 `pcClient=true`** 的门户显示。

> 流程 / CMS / 查询的 `createXxxAppMenu` 在 `Layout.js` 被注释 → **永不单独显示**。

### 3.2 三层补登（幂等脚本 `tools/o2_sync_startmenu.py`）
- **A**：WAR 组件 `POST /jaxrs/component`（存 MySQL 卷，restart 不丢）。
- **B**：流程应用写 `applications.json` 的 `"@url:"` 深链：`/x_desktop/index.html?app=process.Application&option=<urlenc {id,appId}>`。
- **C**：门户置 `pcClient=true`（**必须 designer 端点** `PUT /x_portal_assemble_designer/jaxrs/portal/{id}`，surface PUT 返 405）。

### 3.3 权限模型
- 报错 = `allowList`/`denyList` 交集；**两者都空 = 不校验**。

---

## 4、健康排查方法论 SOP

### 4.1 核心原则：MySQL 为权威，REST 列表接口常因权限/缓存返 404/500，**不可全信**。

### 4.2 健康四维判定（逐模块）
| 维度 | 查询方式 | 正常标准 |
|---|---|---|
| 流程定义数 | `SELECT COUNT(*) FROM PP_E_PROCESS WHERE xapplication IN (...) GROUP BY xapplication` | >0 说明有流程支撑 |
| 在流转实例 | `SELECT xapplication,COUNT(*) FROM PP_C_WORK ... GROUP BY xapplication` | >0 说明活跃运行 |
| 动态表真实数据 | `information_schema.TABLES` 行数 `TABLE_ROWS` + `QRY_DYN_T*` 表存在 | 有实际行数据 |
| 门户页数 + 内容 | `PTL_PAGE` 计数 + `CHAR_LENGTH(xdata)` | 页数>0 且内容有实质长度 |

### 4.3 基线 delta 法
- 删/改前后各取一次全量计数（沿用 2.4 SQL），用差值证明"只动了目标、没伤其他"。

### 4.4 常用探活命令
```bash
# 1) 直连 MySQL 权威查询
docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd X -e "SQL"

# 2) 健康检查 HTTP 200
curl -s -o /dev/null -w "%{http_code}" --noproxy "*" http://localhost:9090/

# 3) restart 后恢复断网隔离
bash /d/O2OA/o2oa_netlock.sh

# 4) 同步开始菜单并刷新
docker cp "D:/O2OA/patch/web/applications.json" \
  'o2oa-server:/opt/o2server/servers/webServer/o2_core/o2/xDesktop/$Layout/applications.json'
docker restart o2oa-server
```

---

## 5、AI 网关栈 SOP

### 5.1 端口与入口
- 统一入口 `18790`（gateway）；内部 chat `8088` / embed `8089` / rerank `8092` / OCR `8091`。
- 模型：已切 `qwen3.8-27b`（17.74GB ctx 65536），4GB 核显先卸后载，`mcp_max_turns` 8→14→**20**（第五批多步编排需更多轮次）。

### 5.2 两道闸默认关
- `web_enable=false` 一行恢复，代码零删除。
- 联网两道闸默认关，不搬公网数据进系统。

### 5.3 故障判定
- AI 助手报 `connect timed out` = **网关没在跑**（栈活着时容器→`192.168.1.5:18790` 实测 200）。
- 服务号不存在则回落 `o2oa_user`(xadmin)。

### 5.4 关键加固
- bat：CRLF + UTF-8 无 BOM + `chcp 65001`；
- `.sh` 必须 LF；容器 UTC+8h；
- OCR：`POST {ocr_base}/ocr` 吃 **base64 JSON**（`file_b64`+`filename`），非 multipart。

---

## 6、高频坑与加固 SOP

| 坑 | 现象 | 对策 |
---|---|---
| 库名不对 | `Unknown database 'o2oa'` | 库名是 **`X`**，先 `SHOW DATABASES` 确认 |
| xadmin 登录锁定 | 报「用户不存在或密码错误」≠密码错 | 查 `config/ternaryManagement.json`：`enable=true` 且三员密码空 → 置 `enable=false` 后重启 |
| 容器 QEMU 长跑病态 | Jersey SSE 读空、exec setns 失败 | `docker restart` 即愈；规避 exec，用 docker cp/HTTP |
| 静态文件改了不生效 | 菜单仍显旧 | 必须 `docker cp` 进容器 + `docker restart` |
| 应用删不掉 | `存在 N 个在流转中工作实例` | 先删实例（2.1） |
| cookie 污染 | 服务号请求被当成上一用户(500) | O2OA REST 走专用 client + 每请求 `cookies.clear()` |
| bat 乱码/不执行 | 中文乱码、命令不跑 | CRLF + UTF-8 无 BOM + `chcp 65001` |
| 后台进程被回收 | `cmd &` 调用结束即回收 | `run_in_background=true` 或交看门狗 |
| `.sh` 不执行 | 行尾 CRLF | `.sh` 必须 LF；容器 UTC+8h |

---

## 7、已拆除与当前保留清单 SOP

### 7.1 已安全拆除（零误伤）
| 模块 | 时间 | 规模 | 关键验证 |
|---|---|---|---|
| 经营管理平台（5 应用） | 09-19 | 全链路清净，源码留 `tools/biz_*` | 基线六类计数全 0，其他模块零变化 |
| 合同·业务双门户 | 09-21 | 应用/表/19 在流转实例全清 | portal 35→17 / pp_app 18→17 / dyn 79→68 |
| 人力资源全模块 | 09-21 | 14 流程 / 15 实例 / 12 表 / 数据应用 / 7 页 | portal 35→34 / pp_app 18→17 / dyn 79→67 |
| 公共数据空壳 | 09-21 | 0 流程 / 0 表 / 空数据应用 | 仅剩 1 个空 dataapp，pp_app 17→16 |

### 7.2 当前保留（运行正常）
- 业务模块：档案(5005) / 财务(4004) / 预算(3003)（均含流程定义 + 动态表真实数据 + 在流转实例活跃）
- 党建门户（09-21，1 实页 361KB）
- 11 个 war 组件（TeamWork / CRM / StandingBook / TableTool 等，已验证 up）
- 18 个离线导入应用（标准应用/组件）

---

## 8、o2oa_api 文档补全 SOP

### 8.1 现状概述
本地已有 RAG 与记忆能力，`gateway/data.db` 中 `docs` 表已索引 **41 条 O2OA API 文档**，覆盖 44/45 个模块映射（仅 `x_okr_assemble_control` - OKRAction 为空）。

### 8.2 已完成模块
Attendance、BBS、Calendar、CMS、Collaboration(websocket)、Component、FaceSet、File、General、HotPic、Meeting、MessageCommunicate、Mind、Organization、OrganizationExpress、Personal、PortalDesigner、PortalSurface、BAM、Designer、ProcessPlatform*、ProgramCenter*、Query*、SmartOffice、StrategyDeploy、Teamwork——均已通过 `ingest_o2oa_api_direct.py` 入库并重index。

### 8.3 待补全模块
- **`x_okr_assemble_control` (OKRAction)**：对应 `/o2_core/o2/xAction/services/x_okr_assemble_control.json`，包含 OKR 相关的增删改查接口。建议运行：
  ```bash
  python3 /d/O2OA/tools/ingest_o2oa_api_direct.py
  ```
  以补全剩余文档并加入向量检索能力。

### 8.4 API 文档结构参考
每条 doc 遵循格式：
```
# O2OA API 模块: <ModuleDisplayName>

## 接口列表
  - <op_name>: <method> <uri>
*以上接口已通过 O2OA 运行态 :9090 /o2_core/o2/xAction/services/*.json 入库，支持 RAG 检索。*
```

### 8.5 验证入库
运行后可查询：
```sql
SELECT id, title FROM docs WHERE category='o2oa_api' AND id LIKE '%OKR%';
```
确认 `o2kb::o2oa_api::OKRAction` 出现且内容非空。

---

## 9、SOP 执行检查表

| # | 操作 | 责任人 | 状态 |
|---|---|---|---|
| 1 | 启动流程前确认使用 `admin` 业务管理员（非 xadmin） | Analyst | ⬜ |
| 2 | 删除模块前后跑基线 SQL 对比 | Manager | ⬜ |
| 3 | docker restart 后重跑 `o2oa_netlock.sh` | Operator | ⬜ |
| 4 | 每次静态文件改动后 `docker cp` + `restart` | Operator | ⬜ |
| 5 | 健康检查优先 MySQL 为权威，不盲信 REST 列表 | Analyst | ⬜ |
| 6 | AI网关异常时先检查 `web_enable=false` + 端口 18790 连通性 | Analyst | ⬜ |
| 7 | 每月核对一次 API 文档索引是否完整（尤其是新增模块） | Manager | ⬜ |

> **SOP 生效要点**：(1) 结论先行；(2) 数据为王（MySQL 权威）；(3) 顺序不可逆（删除契约严格）；(4) 断网隔离不间断；(5) 文档与技能同步更新。

---
*文档维护：如有新发现的坑或流程，建议追加至对应章节，并考虑是否值得通过 Skill 形式固化以便复用。*