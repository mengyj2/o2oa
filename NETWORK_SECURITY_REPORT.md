# O2OA 系统体检报告

**时间**：2026-09-19 01:45
**范围**：运行状态 / 错误日志 / 外网隔离强度 / O2OA 偷连取证

---

## 一、总体结论：系统健康，但外网隔离有一个真实漏洞（已修复）

| 项目 | 状态 |
|---|---|
| 容器状态 | ✅ `o2oa-server` healthy，`o2oa-mysql` healthy |
| HTTP 访问 | ✅ `localhost:9090 → 200` |
| MySQL 接管 | ✅ 314 张表，**H2 零回退**，`jdbc:h2:tcp` 零报错 |
| 补丁有效性 | ✅ 三道门控全部破除且持续生效 |
| 外网隔离 | ⚠️ **原有方案只挡域名，挡不住 IP 直连** → 已加固 |
| O2OA 偷连行为 | ✅ 未发现活跃偷连，但存在 2 个潜在外连点 |

---

## 二、发现的 bug / 错误

### 1. `CMS_CATEGORYINFO_manageableUnitList` 建表冲突（一次性，无需处理）

```
ERROR ... get entityManager for class ApplicationBaseEntity error
Caused by: Table 'CMS_CATEGORYINFO_manageableUnitList' already exists
```

- **性质**：OpenJPA 首次访问 CMS 模块时的建表竞态 —— 它先查"表不存在"就去 CREATE，但表实际已建好。
- **影响**：**仅出现 1 次**（你 00:59 访问 CMS 文档列表时触发），日志里只此一条，不再复现。
- **验证**：该表及 10 张同族关联表在 MySQL 中**结构完整正常**。
- **结论**：**无害**，属 O2OA 自身设计问题（非我们引入）。不用管。

### 2. `DirectoryNotEmptyException: x_component_PdfViewer`（启动期，可忽略）

应用部署时的目录清理告警，O2OA 自行恢复，不影响功能。

### 3. 其余 ERROR 均为"预期内的业务拒绝"

```
ExceptionInitialManagerName      不能用 xadmin 建人员（我们主动测试触发的）
ExceptionPasswordEmpty           改密码时空值（我们测试触发的）
ExceptionPersonNotExistOrInvalidPassword   故意的错误密码测试
ExceptionDenyChangeInitialManagerPassword  REST 拒绝改 xadmin 密码（符合预期）
```
这些都是**我们之前做账号运维时的测试痕迹**，不是系统缺陷。

---

## 三、外网隔离的真实强度（核心问题）

### 你原来的方案：`dns: [127.0.0.1]`

```yaml
dns:
  - 127.0.0.1        # 指向不存在的解析器 → 域名解析全失败
```

**实测结果**：
```
容器内 getent hosts o2oa.net     → 解析失败 ✓
容器内 curl https://www.o2oa.net → 000（不通）✓
```

看起来很好。**但我用 IP 直连测了一下**：

```
容器内 curl http://223.5.5.5     → 404  ← 通了！
```

**这是漏洞**：DNS 隔离只挡"域名 → IP"的翻译，**挡不住任何已知 IP 的直连**。
如果 O2OA 代码硬编码了 IP（实测确实存在 `117.133.7.109`），或曾经缓存过 IP，数据照样能发出去。

另外查了容器路由表：
```
eth0  00000000  010016AC  ...   ← 默认路由 0.0.0.0/0 经网关 172.22.0.1
```
容器**有完整的外网出口能力**，DNS 是唯一屏障。

---

## 四、O2OA 到底会不会"偷偷连接"？—— 取证结果

### 扫描了全部 25 个 jar + console.jar（2404 个 class），外连域名清单：

| 域名 | 所在类 | 用途 | 风险 |
|---|---|---|---|
| `apppack.o2oa.net:40088` | `Collect` | 应用打包服务器 | 中（collect.json 已 `enable:false`） |
| `app.o2oa.net` / `www.o2oa.net` | `Collect` / `Config` | 云平台 / 官网 | 低 |
| `res.o2oa.net` | `Dingding` / `Qiyeweixin` | 钉钉/企微资源（**你都不用**） | 低 |
| `dev.o2oa.net` | `URLTools` | 示例常量 | 无 |
| `117.133.7.109` | `ShaTools` | **硬编码 IP** | 注意 |
| `token.cmpassport.com` | `AndFx` | 中国移动认证（**不用**） | 低 |
| `api.weixin.qq.com` 等 | 微信相关模块 | 微信集成（**不用**） | 低 |
| `java.sun.com` / `www.w3.org` / `apache.org` | 各种 | XML/DTD 命名空间（**不联网**） | 无 |

### 关键判定

1. **`LICENSE_TIP` / `DEFAULT_PUBLIC_KEY` 是离线 RSA 验签**，不需要联网校验授权。
   我用反编译确认：`Config.class` 里 `www.o2oa.net` 只出现在一句**提示文案**里：
   > "抱歉！当前产品未授权或授权已过期，请通过官网(www.o2oa.net)或客服电话..."

2. **`collect.json` 的 `enable` 默认就是 `false`** —— 云平台连接是关闭的。
   而且 `Collect` 类的引用者只有 `config/*` 和 `tools/DocumentTools`（读配置、生成文档），
   **没有任何定时任务或 service 主动调用它发起外连**。

3. **运行日志里零外连痕迹**：
   ```
   日志中出现的全部 URL：  17 次 http://127.0.0.1，3 次 http://localhost
   外网域名：0 次
   未知主机/连接超时错误：0 条
   ```

**结论**：**没有发现 O2OA 在偷偷外连。** 但"没有发现"不等于"不可能发生" ——
上面那些域名常量都还在字节码里，只要触发对应功能（如点"应用市场"、配置钉钉/企微）
就会尝试外连。**所以内核级封网是必要的兜底。**

---

## 五、已实施的加固（`o2oa_netlock.sh`）

### 原理

在东 O2OA 容器的**出站路径**上，按源 IP 丢弃非内网流量：

```
iptables -I FORWARD 1 -s <o2oa容器IP> ! -d 172.16.0.0/12 -j DROP
```

- 只放通 **Docker 内网段**（`172.16/12`，含 mysql）
- 其余一律 DROP —— **这是内核级封堵，IP 直连也挡得住**

### 为什么不用 `internal: true` 网络

实测复现了你之前踩过的坑：
```
internal 网络 + -p 18082:80   →  宿主访问 502
```
Docker Desktop 对 internal 网络**不做 DNAT**，端口映射失效。所以不能用。

### 实测效果（全部已验证）

| 测试项 | 结果 |
|---|---|
| 容器 → `223.5.5.5` IP 直连 | ✅ `000` **不通** |
| 容器 → 域名解析 | ✅ 不通 |
| 容器 → `mysql:3306` | ✅ **通**（JDBC 实测 314 表可查） |
| 宿主 → `localhost:9090` | ✅ **200** |
| 规则命中计数 | ✅ `pkts=6`（真实拦到过数据包） |
| `--remove` 可逆性 | ✅ 移除后 `223.5.5.5 → 404`（证明之前的 000 确实是封堵导致） |

### 怎么用

```powershell
.\netlock_o2oa.bat              # 双击应用封网
bash o2oa_netlock.sh --check    # 只看状态
bash o2oa_netlock.sh --remove   # 撤销封网
```

### ⚠️ 两个必须记住的注意事项

1. **Docker Desktop 重启后 iptables 规则会丢失** → 需重新跑一次。
2. **容器重建（升级）后 IP 可能变化** → 也要重新跑一次。
   （建议把 `netlock_o2oa.bat` 加进开机流程，或每次升级后跑一次）

---

## 六、"能上外网但不与 O2OA 服务器通信" —— 回答你的问题

**你的真实需求可以拆成两个独立的事**：

### ① 宿主（你自己）能上外网 → ✅ **一直都能**
宿主机和容器是隔离的。容器被封网**完全不影响**你在 Windows 上用浏览器、
以及用 `localhost:9090` 访问 O2OA。

### ② O2OA 容器不与 o2oa.net 通信 → ✅ **已实现**
现在它是：
- 域名解析：不通
- IP 直连：不通
- MySQL 通信：正常
- 宿主访问：正常

### ③ 那"O2OA 需要联网的功能"怎么办？
O2OA 里唯一需要外网的是**应用市场 / 云平台 / 应用打包**（`Collect` 模块），
这些功能对你**本来就没用**（都需要 O2OA 官方账号）。封了不影响任何你用得上的功能。

**如果你以后确实需要**（比如想在应用市场下载某插件）：
```bash
bash o2oa_netlock.sh --remove    # 临时开网
# ……用完……
bash o2oa_netlock.sh             # 再封上
```

---

## 七、建议的下一步

1. **保持当前封网状态**（已生效）—— 这是最稳妥的。
2. **把 `netlock_o2oa.bat` 加进你的启动流程** —— 避免 Docker Desktop 重启后忘记。
   （已顺手改好了 `start_o2oa.bat`：启动等到就绪后会自动调用封网脚本）
3. **`entrypoint.sh` 的配置消毒已改好但需要重建镜像才生效** ——
   当前运行容器里的 `collect.json` 我已手动消毒（等效）。下次 `docker compose build`
   时会自动带上，之后每次启动都会自动清空外连地址。
4. ~~修复 `CMS_CATEGORYINFO` 建表冲突~~ —— 无需处理，一次性。
5. **★ 云平台接口封锁**：已通过 `patch_collect_lock.sh --war` 在**镜像构建期**完成，
   `docker compose build` 即自动打上。详见第九~十二章。

---

## 八、当前生效状态一览（验收）

```
三层防护
  ① DNS 隔离        ✓ 域名解析不通
  ② iptables 封堵   ✓ 223.5.5.5 (IP直连) → 000，规则命中 pkts=6
  ③ 配置层消毒      ✓ collect.json appPackServerUrl 已清空

业务可用性（全部正常）
  o2oa-server       ✓ healthy
  o2oa-mysql        ✓ healthy
  宿主 → 9090       ✓ 200
  MySQL 表数        ✓ 314
  H2 文件数         ✓ 0（无回退）
  o2oa → mysql:3306 ✓ 通（JDBC 实测）
```

### ⚠️ 必须记住的一件事

**Docker Desktop 重启后，第 ② 层会失效**（iptables 规则存在 VM 内存里）。
这是 Docker Desktop 的固有限制，无法持久化。

**应对**：
- 用 `start_o2oa.bat` 启动（已内置自动封网），或
- Docker 重启后手动双击 `netlock_o2oa.bat`
- 随时用 `bash o2oa_netlock.sh --check` 确认状态

---

# 附加加固：云平台接口封锁（2026-09-19 02:30）

## 九、发现的真实漏洞：注册云账号接口【没有 enable 门控】

前面第 ④ 层防护（配置层 `collect.json.enable=false`）**是不够的**。
我逐行审计了 `x_program_center` 的 21 个 `/jaxrs/collect/*` 接口源码，结果：

| 接口 | 路径 | 有 `enable` 门控？ |
|---|---|---|
| 登录 | `POST /jaxrs/collect/login` | ✅ 有（`ExceptionDisable`） |
| 校验 | `POST /jaxrs/collect/validate` | ✅ 有 |
| **注册** | `POST /jaxrs/collect` | ❌ **没有** |
| **找回密码** | `PUT /jaxrs/collect/resetpassword` | ❌ **没有** |
| **发短信验证码** | `GET /jaxrs/collect/code/mobile/{mobile}` | ❌ **没有** |
| 用户名是否存在 | `GET /jaxrs/collect/name/{name}/exist` | ❌ 没有 |
| 手机号是否为管理手机 | `GET /jaxrs/collect/controllermobile/...` | ❌ 没有 |
| 其余 14 个 | …… | ❌ 没有 |

**实测证据**（补丁前，管理员身份调用注册接口）：
```json
{"type":"error",
 "message":"无法连接到外网注册服务器,请检查服务器是否可以正常连接到Internet网络,DNS解析是否正常.",
 "prompt":"com.x.program.center.jaxrs.collect.ExceptionUnableConnect"}
```
注意报的是 **`ExceptionUnableConnect`（连不上）**，而不是 `ExceptionDisable`（未启用）
—— 证明它**根本没走 enable 门控**，仅因为 iptables 封网才失败。

### 更危险的地方

`ActionRegist.java` 注册成功后：
```java
if (BooleanUtils.isTrue(wo.getValue())) {
    Config.collect().setEnable(true);     // ← 自动打开云平台连接！
    Config.collect().setName(name);
    Config.collect().setPassword(password);
    Config.collect().save();
    this.configFlush(effectivePerson);
    ThisApplication.context().scheduleLocal(CollectPerson.class);  // ← 立即上报人员手机号
}
```
**只要封网失效一次 + 有人点一下注册**（或直接调接口），系统就会：
1. 真的把账号注册到 O2OA 云平台
2. 自动把 `enable` 改成 `true`
3. 立即触发 `CollectPerson` → **把本机所有人员的手机号上报到云平台**

## 十、License 授权校验：核实结果 —— 【不存在】

你担心"License 授权校验"，我做了全平台取证：

- 解压 **全部 jar，共 2308 个 class**，全量搜索 `license`
- 命中仅 **1 个文件**：`com/x/base/core/project/config/Config.class`
- 其中 `LICENSE_TIP` 是**静态常量**，真值为：
  > "抱歉！当前产品未授权或授权已过期，请通过官网(www.o2oa.net)或客服电话(400-888-0545)联系."
- **关键**：该常量在全平台**只被自己的声明处引用，零调用点**
- `DEFAULT_PUBLIC_KEY` / `DEFAULT_PRIVATE_KEY` 是 RSA 密钥对，用于**离线加解密**（如配置文件加密），**不是授权校验**

**结论**：这套代码里**根本没有 License 校验流程**。`LICENSE_TIP` 只是一段
"预留的提示文案"，等未来某个商业版模块来调用，当前版本没有任何调用者。
**断网不会触发任何授权问题，你也不需要 License。**

## 十一、实施的加固：`CollectJaxrsFilter` 字节码补丁

### 原理

`x_program_center` 有个统一入口过滤器：
```java
@WebFilter(urlPatterns = "/jaxrs/collect/*", asyncSupported = true)
public class CollectJaxrsFilter extends CipherManagerJaxrsFilter { }
```
它原本只有一个默认构造器。补丁注入一个 `doFilter()` 覆写：

```java
public void doFilter(ServletRequest req, ServletResponse resp, FilterChain chain) {
    HttpServletResponse _resp = (HttpServletResponse) resp;
    _resp.setStatus(403);
    _resp.setContentType("application/json;charset=UTF-8");
    _resp.getWriter().write("{\"type\":\"error\",\"message\":\"O2OA collect(o2cloud) interface is disabled by local netlock policy.\"}");
    _resp.getWriter().flush();
    return;   // ← chain.doFilter 永不执行
}
```

**效果**：所有 `/jaxrs/collect/*` 请求（任何方法、任何路径）**一律 403**，
物理切断，永不进入业务逻辑。

### 影响面（经过实测）

| 模块 | 过滤器 | 是否受影响 |
|---|---|---|
| **collect**（云账号注册/登录/找回密码/验证码） | `CollectJaxrsFilter` | ✅ **全部拒绝（这是目的）** |
| **market**（应用市场） | `MarketJaxrsFilter` | ❌ 不受影响，**保持可用** |
| **apppack**（应用打包） | `AppPackJaxrsFilter` | ❌ 不受影响，**保持可用** |

即：**你仍然可以临时开闸使用应用市场和应用打包，但任何人都无法再注册/登录云账号。**

### 实测对比（补丁前 → 补丁后）

| 接口 | 补丁前 | 补丁后 |
|---|---|---|
| `POST /jaxrs/collect`（注册） | `500` `ExceptionUnableConnect` | ✅ **`403`** |
| `POST /jaxrs/collect/login`（登录） | `500` `ExceptionDisable` | ✅ **`403`** |
| `GET /jaxrs/collect/connect`（探活） | `200` `{"value":false}` | ✅ **`403`** |

### 回归测试（核心功能全部正常）

```
首页                    → 200
管理员登录 /authentication → 200
系统配置 /config/list     → 200
应用市场 /jaxrs/market/*  → 200   ← 故意保留
9090 web 服务            → 200
```

### 持久化设计（关键）

- 补丁脚本：`patch_collect_lock.sh`（内联 javassist 程序，自包含）
- 由 **`entrypoint.sh` 在每次启动时调用** → **O2OA 升级重部署 war 后自动重新打上**
- 已写入 **Dockerfile**（COPY 进镜像），重建容器不丢失
- **幂等**：每次先移除已有 `doFilter` 再重新注入，重跑安全
- 手动操作：
  ```bash
  bash patch_collect_lock.sh            # 应用
  bash patch_collect_lock.sh --verify   # 查看状态
  bash patch_collect_lock.sh --restore  # 恢复原始
  ```

## 十二、最终防护体系（四层 → 六层）

```
① DNS 隔离          dns: [127.0.0.1]                → 挡域名
② iptables 内核封堵  FORWARD DROP 非内网目标          → 挡 IP 直连
③ 配置层消毒        collect.json 地址清空 + enable=false
④ 接口层封锁 ★新增  CollectJaxrsFilter → /jaxrs/collect/* 全 403
⑤ 定时任务门控      CollectMarket/CollectPerson/Area 受 enable=false 约束
⑥ 第三方集成开关    钉钉/企微/WeLink/政务钉钉/安Fx 默认 enable=false
```

**已封死的路径**：云账号注册、登录、找回密码、发短信验证码、人员手机号上报。
**保留可用的路径**：应用市场、应用打包（需配合 `netlock --remove` 临时开闸）。
**License**：不存在校验，无需担心。
