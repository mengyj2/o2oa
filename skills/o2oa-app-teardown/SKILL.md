---
name: o2oa-app-teardown
description: 在 O2OA（社区版 / Docker 自托管）上**安全、彻底地删除一整套应用模块**（门户 + 门户子页 + 流程应用 + 流程实例 + 数据应用 + 自建表定义 + 动态物理表 + 开始菜单项），且不误伤其它模块。当用户说"把 XX 门户/应用删掉""清理 XX 模块""卸载这个应用""删除合同管理/项目管理/XX 应用不要了"时调用。覆盖：O2OA 各层删除 REST 接口与强制顺序、在流转实例的拦截处理、自建表元数据与物理表的两段式删除、静态文件 applications.json 的容器内同步、清理前后基线核对与误伤防护。
agent_created: true
category: operations
---

# O2OA 应用模块级联安全删除

把一个完整的应用模块从 O2OA 里彻底清除。O2OA 的一个"应用"通常横跨 5~7 层，
只删其中一层会留下孤儿数据，或留下仍在开始菜单里可点击的入口。

## 0. 铁律（务必先做）

1. **先划定边界，再动手。** 删除前用「模块编号」把所有关联对象列全（第 1 节）。
   O2OA 自建应用有稳定命名规律，编号是同模块的公共前缀：
   - 流程应用 `a{模块号}xxx-...-app-...`
   - 数据应用 `a{模块号}xxx-...-dataapp-...`
   - 自建表 `t{模块号}xxx-...-table-...`，物理表 `QRY_DYN_T{模块号}xxx_...`
   - 门户 `o{模块号}xxx-...-portal-...`，门户页 `o{模块号}xxx-...-page-...`
   - 流程定义 `p{模块号}xxx-...`
2. **列出"不动清单"并向用户复述**（如 HR 6006、财务 4004 不在范围内）。
3. **若有业务数据，先向用户确认**是否备份/是否连数据一起删——不要自作主张。
4. **记录删除前基线**（第 5 节），删完比对，确认只少了预期数量。
5. **删除顺序强制**：流程实例 → 流程应用 → 自建表定义 → 动态物理表 → 数据应用 → 门户子页 → 门户 → 菜单项。
   顺序错会被系统拦截或留下孤儿。

## 1. 清点关联对象

```sql
-- 库名通常是 X（不是 o2oa！）
SELECT xid,xname FROM X.PTL_PORTAL       WHERE xid LIKE '%<关键词>%';
SELECT xid,xname FROM X.PP_E_APPLICATION WHERE xid LIKE 'a<模块号>%';
SELECT xid,xname,xapplication FROM X.PP_E_PROCESS WHERE xapplication IN (<应用id列表>);
SELECT xapplication, COUNT(*) FROM X.PP_C_WORK GROUP BY xapplication;   -- 在流转实例（决定能否删应用）
SELECT xid,xname FROM X.QRY_SCH_TABLE    WHERE xid LIKE 't<模块号>%';
SELECT xid,xname FROM X.QRY_QUERY        WHERE xid LIKE 'a<模块号>%';
SELECT TABLE_NAME FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN_T<模块号>%';
```

## 2. 删除动作（按顺序）

### 2.1 流程实例（必做，否则应用删不掉）

应用下有"在流转中"的实例时，删除应用会报：
`应用:XXX, 存在 N 个在流转中工作实例,请确保没有在流转中的工作实例后再尝试删除应用.`

```
SELECT xid FROM X.PP_C_WORK WHERE xapplication='<应用id>';
DELETE /x_processplatform_assemble_surface/jaxrs/work/{workId}
```
> `DELETE /x_processplatform_assemble_designer/jaxrs/application/{id}/{onlyRemoveNotCompleted}`
> 即使传 `false`，**仍会拦在流转的实例**——必须先清实例。

### 2.2 流程应用（连带清掉流程定义与已完成实例）

```
DELETE /x_processplatform_assemble_designer/jaxrs/application/{appId}/false
```

### 2.3 自建表定义

```
DELETE /x_query_assemble_designer/jaxrs/table/{tableFlag}
```
> `tableFlag` 用 `QRY_SCH_TABLE.xid`（如 `t2002001-contract-main-table-0000000001`）。

### 2.4 ★ 动态物理表（必须手工 DROP）

**`deleteTable` 只删元数据，不会 DROP 物理表**（O2OA 有意保留数据）。必须手工清：

```sql
DROP TABLE IF EXISTS QRY_DYN_T<模块号>xxx_<表名>;
```

### 2.5 数据应用

```
DELETE /x_query_assemble_designer/jaxrs/query/{dataappId}
```

### 2.6 门户子页 → 门户

```
GET    /x_portal_assemble_designer/jaxrs/page/list/portal/{portalId}
DELETE /x_portal_assemble_designer/jaxrs/page/{pageId}          # 先删全部子页
DELETE /x_portal_assemble_designer/jaxrs/portal/{portalId}      # 再删门户
```
> `menu`/`source` 子接口返回 404 属正常（该门户无此类子对象）。

### 2.7 开始菜单项（静态文件，两处同步）

流程应用在开始菜单里是 `applications.json` 的 `"@url:"` 条目。需改**两处**：

1. 项目补丁源 `patch/web/applications.json`（Dockerfile 会 COPY 它，保证重建不复活）
2. 运行容器内 `/opt/o2server/servers/webServer/o2_core/o2/xDesktop/$Layout/applications.json`

```bash
docker cp patch/web/applications.json \
  "o2oa-server:/opt/o2server/servers/webServer/o2_core/o2/xDesktop/\$Layout/applications.json"
docker restart o2oa-server      # 静态文件有内存缓存，必须重启
```
> bash 双引号内 `$Layout` 要写成 `\$Layout` 才不会被展开。
> 门户类也可能经 `CPT_COMPONENT` 出现在菜单，删完核对
> `GET /x_component_assemble_control/jaxrs/component/list/all` 无残留。

### 2.8 空壳应用快速删除（无流程/无表/无实例）

当应用 **0 流程 / 0 表 / 0 实例 / 仅一个空数据应用** 时（例：`公共数据 a0000000-common-dict-app`，09-21 实战）：

- **无需清 work 实例**（根本没有），直接两步 `DELETE`：
  ```python
  _delete(f"/x_processplatform_assemble_designer/jaxrs/application/{appId}/false", tok)   # 流程应用
  _delete(f"/x_query_assemble_designer/jaxrs/query/{dataAppId}", tok)                      # 空数据应用
  ```
- 若有开始菜单 `@url:` 入口，按 2.7 同步移除；若仅经 WAR 组件注册，核对 `GET /jaxrs/component/list/all` 无残留。
- 删前/删后仍跑第 5 节基线：`pp_app` / `qry_query` 各减 1，`component` / `cms_appinfo` 零变化。

> 已实战验证 3 轮完整拆除（经营管理平台 / 合同·业务双门户 / 人力资源全模块）+ 1 轮空壳清理，删除契约零误伤。

## 3. 误伤防护

- 只按**精确 id / 精确名称**匹配，绝不用宽泛 `LIKE` 做删除。
- `CPT_COMPONENT` 里的自定义组件多为系统内置（OnlyOffice/CRM/TeamWork/WpsOffice 等），**不要动**。
- 门户里的展示页（如"业务门户"含"档案管理""财务管理"页）**只是页面**，删页不影响那些模块自身。
- 删除前后都用第 5 节核对，确认其他模块计数不变。

## 4. 删除脚本骨架

```python
from o2 import login, get, post, BASE          # o2.py: 登录 + get/post/put
import urllib.request, urllib.error

def _delete(path, tok, timeout=300):
    req = urllib.request.Request(BASE + path, headers={"x-token": tok}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

tok = login()
for w in WORK_IDS:                              # 1 流程实例
    _delete(f"/x_processplatform_assemble_surface/jaxrs/work/{w}", tok)
for a in APP_IDS:                               # 2 流程应用
    _delete(f"/x_processplatform_assemble_designer/jaxrs/application/{a}/false", tok, 600)
for t in TABLE_FLAGS:                           # 3 自建表定义
    _delete(f"/x_query_assemble_designer/jaxrs/table/{t}", tok)
# 4 动态物理表 -> mysql DROP（见 2.4）
for q in DATAAPP_IDS:                           # 5 数据应用
    _delete(f"/x_query_assemble_designer/jaxrs/query/{q}", tok)
for pid in PORTAL_IDS:                          # 6 门户子页 + 门户
    _, j = get(f"/x_portal_assemble_designer/jaxrs/page/list/portal/{pid}", tok)
    for pg in (j.get("data") or []):
        _delete(f"/x_portal_assemble_designer/jaxrs/page/{pg['id']}", tok)
    _delete(f"/x_portal_assemble_designer/jaxrs/portal/{pid}", tok)
```

## 5. 基线核对（清理前后各跑一次）

```sql
SELECT 'portal',        COUNT(*) FROM X.PTL_PORTAL
UNION ALL SELECT 'pp_app',      COUNT(*) FROM X.PP_E_APPLICATION
UNION ALL SELECT 'pp_process',  COUNT(*) FROM X.PP_E_PROCESS
UNION ALL SELECT 'pp_work',     COUNT(*) FROM X.PP_C_WORK
UNION ALL SELECT 'pp_task',     COUNT(*) FROM X.PP_C_TASK
UNION ALL SELECT 'qry_table',   COUNT(*) FROM X.QRY_SCH_TABLE
UNION ALL SELECT 'qry_query',   COUNT(*) FROM X.QRY_QUERY
UNION ALL SELECT 'component',   COUNT(*) FROM X.CPT_COMPONENT
UNION ALL SELECT 'cms_appinfo', COUNT(*) FROM X.CMS_APPINFO;
SELECT 'dyn_tables', COUNT(*) FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN%';
```

判定标准：
- 目标残留全部为 **0**；
- 其他模块（HR / 财务 / 预算 / 档案 / 公文）的应用、门户、表计数**不变**；
- `component` 与 `cms_appinfo` **零变化**（变了就是误伤）。

## 6. 环境坑

| 坑 | 现象 | 对策 |
|---|---|---|
| 库名不对 | `Unknown database 'o2oa'` | 库名是 **`X`**，先 `SHOW DATABASES` 确认 |
| MySQL 密码 | `Access denied` | 读 compose 的 `${MYSQL_ROOT_PASSWORD:-o2oa_root_pwd}` |
| 中文乱码 | `mysql -N` 输出 `?????` | 终端编码所致，属正常；改用 REST 读名称 |
| `docker exec` setns 失败 | `no such file or directory` | 直连 mysql 容器查询；或先 `docker restart` |
| 静态文件改了不生效 | 菜单仍显示 | 必须 `docker cp` 到容器内 + `docker restart` |
| 应用删不掉 | `存在 N 个在流转中工作实例` | 先删实例（2.1） |

## 7. 交付话术要点

删完向用户报告：**删了什么（分类计数）→ 基线对比（前后数字）→ 明确没动什么（其他模块计数）→ 服务可用性验证（HTTP 200 / 登录正常）**。
数字对不上要查明原因，不要含糊带过。
