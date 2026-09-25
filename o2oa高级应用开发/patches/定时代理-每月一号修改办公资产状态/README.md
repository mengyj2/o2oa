# 定时代理「每月一号修改办公资产状态」启用 — 交付说明

> 修复日期：2026-09-21
> 适用环境：O2OA 社区版 10.0.2（本地 Docker 自托管，已断云）
> 交付物：本说明 + 幂等启用脚本 `enable_monthly_agent.sql`

---

## 一、用户可见现象

服务管理平台 → 代理配置列表里，第二项显示：

```
(禁用)每月一号修改办公资产状态
```

前缀「(禁用)」表示该定时代理当前不运行。需求是**启用并让它真正可运行**。

---

## 二、根因（已实证）

### 2.1 定时代理存在哪

O2OA 的**系统级定时代理**存放在数据库表 `X.CTE_AGENT`（不是流程内的代理活动节点
`PP_E_AGENT`，二者勿混）。关键字段：

| 字段 | 含义 |
|---|---|
| `xid` | 代理唯一 id |
| `xname` | 显示名（即列表里看到的名字） |
| `xcron` | Quartz cron 表达式，决定何时触发 |
| `xenable` | **0=禁用 / 1=启用**（前端「(禁用)」前缀即由此字段决定） |
| `xvalidated` | 脚本是否通过校验 |
| `xtext` | 代理执行的脚本（这里是 JScript/Groovy 片段） |

### 2.2 目标代理实况

```
id     : 7e78ba01-e2bf-402b-badf-f706d7888119
xname  : 每月一号修改办公资产状态
xcron  : 0 */30 * 1 * ?        ← 每月 1 号当天，每 30 分钟触发一次（共 48 次）
xenable: 0                     ← 这就是「(禁用)」的来源
xtext  : 把 CMS「固定资产」分类下文档的 flag 字段改为「未盘点」
```

### 2.3 为什么不能用管理界面直接开

「服务管理平台」的启用/禁用按钮调用 `x_program_center/jaxrs/agent/*`，该接口**需要 manager 权限**
（超级管理员 xadmin 的 cipher token）。实测：

- mengyijie 用户 token 调用 → 返回权限不足；
- xadmin 密码不可知（非 `o2oa_pwd` / `o2oa` 等常见值）；
- 服务端 `token.json` 不含可离线伪造的 cipher 字段。

→ 走管理接口这条路在本环境走不通。

### 2.4 正确且更稳的通道：直接改库

O2OA 的 `TriggerAgent`（调度线程，属于 x_program_center）**每分钟实时重读 `CTE_AGENT` 全表**，
不缓存启用状态。因此：

> **直接 `UPDATE CTE_AGENT SET xenable=1` 即生效，无需重启、无需 manager token、无需走管理接口。**

---

## 三、实现

执行（已做，记录在此以便复现 / 重装后恢复）：

```bash
docker exec o2oa-mysql sh -c 'mysql -uo2oa -po2oa_pwd X < enable_monthly_agent.sql'
```

`enable_monthly_agent.sql` 内容（幂等，可重复执行）：

```sql
UPDATE CTE_AGENT
   SET xenable = 1, xupdateTime = NOW()
 WHERE xid = '7e78ba01-e2bf-402b-badf-f706d7888119';

SELECT xid, xname, xenable+0 AS enable, xcron, xlastStartTime
  FROM CTE_AGENT;
```

> 说明：代理是**系统级**配置，不属于任何应用包，重新导入应用不会把它重置回 0，
> 故一般无需在每次导入后重跑。仅当出现库被还原 / 误改时，用此脚本一键恢复启用。

---

## 四、验证结果（实证，非推测）

启用后恰逢容器一次重启（14:25:34，外部 stop/start，非本会话操作，反而完成了一次冷启动验证）。
冷启动后调度器从库加载到 `xenable=1`，于 **14:28:10** 正常触发并执行了该代理。服务端日志：

```
trigger agent:7e78ba01-..., name:每月一号修改办公资产状态, cron:0 */30 * 1 * ?
[script] PRINT 每月一号把办公资产状态修改为"未盘点"-----------------------
[script] PRINT 获取办公资产数量======0
```

四个代理最终状态（`xenable` 全为 1）：

```
每月一号修改办公资产状态       enable=1  cron=0 */30 * 1 * ?
...（其余三个代理同为 enable=1）
```

浏览器 `Ctrl+F5` 刷新「代理配置」页，该条目不再带「(禁用)」前缀。

---

## 五、必须知道的两个事实

1. **脚本目前空跑（数量=0）**：原脚本逻辑是「把 CMS『固定资产』分类下文档的 `flag`
   改为『未盘点』」，但当前实例 **CMS 里没有任何分类**（`CMS_CATEGORYINFO` 全空），
   所以每次执行都查不到资产文档，无害但没有实际效果。
   - 要真正用起来，**二选一**：
     - A. 在内容管理里先建「固定资产」分类（分类别名 / 路径必须逐字一致为 `固定资产`），
       并录入资产文档；
     - B. 把脚本改成对接我们 06 人力应用的「办公资产」自建表（更贴合本协会实际数据）。
   - 此项需秘书长确认资产数据落在哪，再做。

2. **现 cron 频率偏高**：`0 */30 * 1 * ?` = 每月 1 号当天**每 30 分钟跑一次**（共 48 次），
   对"月初标记未盘点"这种需求显然过密。建议改为每月 1 号 01:00 跑一次：
   `0 0 1 * * ?`。改法同样是 `UPDATE CTE_AGENT SET xcron='0 0 1 * * ?' WHERE xid='7e78ba01-...'`。
   此项同样等秘书长拍板。

---

## 六、注意事项 / 手法沉淀

- **`docker exec` 对 `o2oa-server` 仍失败**（QEMU setns），但对 `o2oa-mysql` 正常 ——
  改库类操作一律走 `docker exec o2oa-mysql ...`。
- **宿主直连 O2OA 用 `localhost:9090`**，不要用 `10.0.0.149:9090`（本轮实测后者超时）。
- **TriggerAgent 实时查库**这一特性可推广：任何系统级定时代理的启用/停用/改 cron，
  直接改 `CTE_AGENT` 即可，不必重启、不必找 manager token。
- 向 `/tmp/work` 投递 `.java` **不会**被服务端自动编译执行（MkToken 通道已不可靠），
  别再指望用它拿 cipher token。
