# O2OA 登录 500：randomWithWeight error（x_organization_assemble_express）根因与修复

> category: o2kb::o2oa_ops  |  id: o2kb::o2oa_ops::login_randomWithWeight
> 适用：O2OA 社区版 10.0.2 断云本地化部署（Docker，MySQL 外部库 X）

## 一、现象
所有账号登录返回 500：
```
{"message":"randomWithWeight error: com.x.base.core.project.x_organization_assemble_express.","count":0}
```
- 口令是对的（"密码错误"分支能正常返回）→ 凭证能找到人。
- 失败发生在**登录流程"计算该人员角色列表"**这一步（栈：`AuthenticationAction` → `RoleFactory.listWithPerson` → `ActionListWithPerson` → `Applications.randomWithWeight(Applications.java:678)`）。
- `count=0` = 该人员的角色/身份列表为空。

## 二、根因（关键澄清，纠过往误判）
- `x_organization_core_express` 把组织（人员/身份/角色）热进**内存**，数据来源是 `x_organization_assemble_control`（直读 MySQL）。
- 容器**重启后**，该内存缓存在启动期同步竞态中失败，且 express 模块**不会自动重试** → 角色列表恒为空 → `randomWithWeight(count=0)` 抛 `IllegalStateException` → 全员 500。
- ⚠️ **不是 H2 损坏**：本部署组织数据全部在 MySQL（X 库），容器内 `find` 无任何 `*.mv.db/*.h2.db` 文件；`control` 模块能正常查到组织（网关 09:05 查表查组织成功），只有 `express` 内存态为空。所以修法是**重启 o2oa-server 让其重建缓存**，不是修 H2。
- 鉴别法：网关/`control` 用 `PUT person/list/like` 等能查到组织 → 数据没丢，是 express 内存态；登录报错含 `randomWithWeight` 且 `count=0` → 确诊。

## 三、快速定位清单
1. 复现：`POST /x_organization_assemble_authentication/jaxrs/authentication` 看是否返回 `randomWithWeight`。
2. 查数据层（MySQL X 库）：`ORG_PERSON / ORG_IDENTITY / ORG_UNIT / ORG_ROLE / ORG_ROLE_personList` 计数应正常（本例 11/22/5/26/5）。
3. 看容器日志：重启前若出现 `use superPermission`（成功登录），重启后全员 500 → 确认是"重启触发 express 缓存空"。
4. 注意 `.5` 往往就是本机：`localhost:9090` 与 `192.168.1.5:9090` 是同一容器（`0.0.0.0:9090`），WorkBuddy 跑在服务器上有 docker 执行通道；从客户端试 SSH/WinRM 才会拒。

## 四、标准修复动作（顺序不能乱）
1. `docker restart o2oa-server` —— 干净重启，express 重建内存组织缓存（O2OA 全起约 5-8 分钟，需等待后再测，勿过早判定失败）。
2. **重启后必重跑** `bash o2oa_netlock.sh` —— docker 重启会清空其写入的 iptables 规则，不断网隔离会丢失。
3. 复测：`POST .../authentication` 返回 `{"type":"success",...}` 即恢复。

## 五、一键修复脚本
桌面 `O2OA登录故障一键修复.ps1`（在 O2OA 服务器本机以管理员运行）：
探测登录 → 重启 organization/o2oa 容器 → 重跑 netlock → 复测。
已更正根因注释（H2→MySQL+express 内存竞态）并补齐 netlock 重跑步骤。

## 六、预防 / 下一步
- 该竞态**偶发**（记忆："docker restart o2oa-server 即愈"）。本次（2026-09-25）是第二次复现，且"重启本身触发病态"。
- 可选看门狗：周期性探测登录，命中 `randomWithWeight` → 自动 `docker restart o2oa-server` + 重跑 `o2oa_netlock.sh`。注意自动重启会短暂中断服务、且每次须重跑 netlock。
- 根治思路（未实施）：让 express 模块在启动期组织同步失败时有重试/告警，避免静默空缓存。
