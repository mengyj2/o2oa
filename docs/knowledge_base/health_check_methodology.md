# O2OA 运维健康排查方法论

## 1. 黄金法则：MySQL 是权威
- **REST 列表接口常返 404/500，不可全信**
- 所有健康数据探测的第一来源必须是 MySQL 直接查询
- 健康检查命令示例：
  ```bash
  docker exec o2oa-mysql mysql -uroot -po2oa_root_pwd X -N -e "SELECT ..."
  ```

## 2. 健康四维核心指标

### 2.1 流程定义数
- **查询**：`SELECT xapplication, COUNT(*) FROM PP_E_PROCESS GROUP BY xapplication`
- **正常标准**：应有对应的流程定义，0 表示未配置或空壳
- **异常预警**：突发减少可能被误删，突增可能有重复投放

### 2.2 在流转实例
- **查询**：`SELECT xapplication, COUNT(*) FROM PP_C_WORK WHERE (xcompletedTime IS NULL OR xcompletedTime='') GROUP BY xapplication`
- **正常标准**：有活跃流程实例运行，0 表示该模块无人使用
- **异常预警**：大量未完成实例可能卡死流程池

### 2.3 动态表真实数据
- **查询**：`SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN_T%' ORDER BY TABLE_NAME`
- **正常标准**：表有实际行数，0 表示无数据或已被清理
- **异常预警**：行数突增可能意味着脏数据写入

### 2.4 门户页数 + 内容
- **查询**：`SELECT xportal, COUNT(*) FROM PTL_PAGE GROUP BY xportal`
- **内容检查**：`SELECT xid, CHAR_LENGTH(xdata) dlen, CHAR_LENGTH(xname) nlen FROM PTL_PAGE WHERE xportal='{id}'`
- **正常标准**：有页数且实质内容（数据量>0），0 表示空壳或未配置
- **异常预警**：页数多但内容为空可能是占位配置

## 3. 基线 delta 法（零误伤验证）
### 3.1 操作流程
1. **删除前**：捕获所有关键计数（portal/app/process/work/table/query/component/dyn_tables）
2. **执行删除操作**
3. **删除后**：再次查询相同计数
4. **对比差异**：
   - 目标模块：允许有预期变化
   - 其他所有模块：**必须零变化**

### 3.2 验证示例（HR 删除案例）
| 类别 | 删前 | 删后 | 说明 |
|---|---|---|---|
| portal | 35 | 34 | HR门户 o6006001 + 7子页 |
| pp_app | 18 | 17 | a6006000-hr-app |
| pp_process | 50 | 36 | 14流程定义+基础数 |
| pp_work | 45 | 30 | 先清15实例后重试 |
| qry_table | 64 | 52 | 12张表元数据 |
| qry_query | 24 | 23 | 数据应用 |
| component | 35 | 35 | **零变化**，未误伤 |
| dyn_tables | 79 | 67 | 手工DROP 12张物理表 |

### 3.3 快速检查清单
- [ ] `component` 计数是否只有目标模块变化
- [ ] `cms_appinfo` 是否零变化
- [ ] 目标残留全 0（如 `PTL_PORTAL WHERE xid LIKE '%hr%'`）
- [ ] 其他业务模块（财务/预算/档案）无任何异常

## 4. 常用健康探测 SQL 模板

### 4.1 两天安装项目盘点
```sql
-- 09-20起创建的应用
SELECT xid,xname,xcreateTime FROM PP_E_APPLICATION WHERE xcreateTime>='2026-09-20' ORDER BY xcreateTime;

-- 各模块流程定义数
SELECT xapplication, COUNT(*) c FROM PP_E_PROCESS 
  WHERE xapplication IN ('a5005000','a4004000','a3003000','a6006000') 
  GROUP BY xapplication;

-- 在流转实例数
SELECT xapplication, COUNT(*) c FROM PP_C_WORK 
  WHERE xapplication IN ('a5005000','a4004000','a3003000','a6006000') 
  GROUP BY xapplication;
```

### 4.2 动态表与门户探测
```sql
-- HR动态物理表状态
SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES 
  WHERE TABLE_SCHEMA='X' AND TABLE_NAME LIKE 'QRY_DYN_T6006%';

-- 党建门户页详情
SELECT xid,xname,xcreateTime FROM PTL_PAGE WHERE xportal='696177d5-c5e5-4fa7-a382-85ce2e761fa9';

-- HR门户页详情
SELECT xid,xname,xcreateTime FROM PTL_PAGE WHERE xportal='o6006001-hr-portal-00000000000000001';
```

### 4.3 war组件探活
```bash
# 批量检查端点可达性
curl -s --noproxy "*" http://localhost:9090/o2_core/o2/xDesktop/\$Layout/applications.json -o /dev/null && echo "healthy" || echo "unhealthy"
```