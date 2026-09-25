# O2OA xadmin 组织归属修复方案

## 1. 问题背景
- `xadmin` 是虚拟初始管理员，DN=`xadmin@o2oa@P`
- **关键事实**：xadmin **不在** `ORG_PERSON` 表，无 identity
- 启动流程时，API 报错：`指定用户没有找到身份: xadmin`

## 2. 根因分析（双重死锁）
### 尝试方案 A：建立 xadmin 人员记录
- 系统硬校验：`name`/`unique` 含 `xadmin`（含大小写不敏感、含前缀匹配）
- **拦截信息**：`不能使用初始管理员标识`
- 结果：失败

### 尝试方案 B：建立 xadmin 身份凭证
- 系统硬校验：新建身份要求 person 必须在 `ORG_PERSON` 真实存在
- **拦截信息**：`人员不存在`
- 结果：失败

### 结论
两条硬校验互为咽喉：建人员被「不能使用初始管理员标识」拦截 → 建身份被「人员不存在」拦截，形成**不可破解的死锁**。

## 3. 正向解法
### 关键决策点
通过 `AskUserQuestion` 让用户明确选择路线，用户确认后：**另建业务管理员账号**

### 操作步骤
1. **创建真实 person**：
   - `unique=admin`、`name=系统管理员`
   - 密码：`o2oaadmin2026`
   - 挂靠顶层组织（中国复合材料工业协会，ID：`9e8b0b36-dff7-4a2c-8964-11b360d7776e`）

2. **授予 3 系统角色**：
   - `ManagerSystemRole`
   - `OrganizationManagerSystemRole`
   - `ProcessPlatformManagerSystemRole`

3. **验证结果**：
   - `admin` 账号登录 -> 可发起流程（HTTP 200）
   - `xadmin` 账号登录 -> 仍被拦截（HTTP 500），确认只能作为纯后台使用

## 4. 铁律沉淀
- **永远不要试图让 xadmin 拥有业务身份**
- xadmin 始终保持为虚拟内存实体，仅用于纯后台操作
- 生产环境始终另建 `admin`（unique=admin / name=系统管理员）作为真正的业务管理账号

## 5. 支持工具
- `tools/o2_fix_xadmin_org.py`：check/apply/rollback 接口，幂等执行上述修复流程