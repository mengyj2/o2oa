# O2OA 应用模块级联删除契约

## 1. 核心原则
- **删前必拍基线**，删后验证 delta，证明「只动目标、零误伤」
- MySQL 是权威数据源，REST 列表常返 404/500，**不可全信**
- 六类计数需对比：`portal/pp_app/pp_process/pp_work/qry_table/qry_query/component/dyn_tables`

## 2. 强制删除顺序
> **流程实例 → 流程应用 → 自建表定义 → DROP 物理表 → 数据应用 → 门户子页 → 门户 → 菜单项**

### 详细步骤

#### 第一步：清理在流转工作实例
- **关键点**：`DELETE /jaxrs/application/{id}/false` 会拦截「存在 N 个在流转中工作实例」
- **正确做法**：先逐个 `DELETE /x_processplatform_assemble_surface/jaxrs/work/{id}` 清理所有 work 实例
- **验证**：导出所有 xid，检查 completedTime 是否为空（有的已完成有的未完成）

#### 第二步：删除流程应用
- 接口：`DELETE /x_processplatform_assemble_designer/jaxrs/application/{id}/false`
- 顺序必须在第一步之后

#### 第三步：自建表定义
- 接口：`deleteTable` 只删元数据，**不 DROP 物理表**（有意保数据）
- 物理表命名规律：`t{模块号}-table-*`（对应物理 `QRY_DYN_T{模块号}*`）

#### 第四步：手工 DROP 物理动态表
- 对每张自建表对应的动态物理表执行 `DROP TABLE IF EXISTS QRY_DYN_T{num}*`
- 示例：`DROP TABLE QRY_DYN_T6006001, QRY_DYN_T6006002, ...`

#### 第五步：删除数据应用
- 数据应用入口对应的后端服务

#### 第六步：删除门户子页
- 先 `GET .../designer/jaxrs/page/list/portal/{id}` 获取所有子页 ID
- 再逐个删除子页

#### 第七步：删除门户
- 接口：`DELETE /x_portal_assemble_designer/jaxrs/portal/{id}`

#### 第八步：移除开始菜单项
- 同步容器内 `applications.json`，移除对应的 `@url:` 条目
- 如需，执行 `docker cp` + `docker restart` 刷新静态缓存

## 3. 空壳应用快速删除规则
> **当 0 流程 / 0 表 / 0 实例 时**，直接删流程应用 + 数据应用即可。

### 情形示例：公共数据（全局）空壳
- 特征：0 流程 / 0 表 / 0 实例 / 仅一个空数据应用占位
- 操作：直接两步 REST 删除流程应用 + 数据应用
- 验证：pp_app 计数减少、qry_query 计数减少，component/其他模块零变化

## 4. 命名规律（便于定位与批量操作）
- 流程应用：`a{模块号}-app-*`
- 数据应用：`a{模块号}-dataapp-*`
- 自建表：`t{模块号}-table-*`（物理 `QRY_DYN_T{模块号}*`）
- 门户：`o{模块号}-portal-*`
- 流程定义：`p{模块号}*`

## 5. 基线核对 SQL（每次删除后必跑）
```sql
-- 六类计数 delta 验证
SELECT 'portal',COUNT(*) FROM PTL_PORTAL
UNION ALL SELECT 'pp_app',COUNT(*) FROM PP_E_APPLICATION
UNION ALL SELECT 'pp_process',COUNT(*) FROM PP_E_PROCESS
UNION ALL SELECT 'pp_work',COUNT(*) FROM PP_C_WORK
UNION ALL SELECT 'qry_table',COUNT(*) FROM QRY_SCH_TABLE
UNION ALL SELECT 'qry_query',COUNT(*) FROM QRY_QUERY
UNION ALL SELECT 'component',COUNT(*) FROM CPT_COMPONENT;
SELECT 'dyn_tables', COUNT(*) FROM information_schema.TABLES 
  WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN%';
```

## 6. 已验证的零误伤案例
- **经营管理平台 5 应用**：全拆净，源码留 `tools/biz_*`
- **合同/业务两门户**（09-21）：19实例+11表+7页完整链路删净，其他模块零变化
- **人力资源门户全模块**（09-21）：14流程/15实例/12表/数据应用/7页全部删除，残留全 0
- **公共数据空壳**：0流程/0表，直接两步 REST 删净

## 7. 关键提醒
- `docker restart` 后必重跑 `o2oa_netlock.sh` 恢复断网隔离
- WAR 组件的 `applications.json` 深链需要同步容器内文件并重启生效
- 菜单 JSON 的 `$Layout` 路径在 Git Bash 中需特殊处理（转义或使用完整 Windows 路径）