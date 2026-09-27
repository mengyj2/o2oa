---
name: o2oa-local-admin-account
description: 在 O2OA 10.0.2（Docker 自托管）上登录、创建/管理账号、批量改手机号邮箱、批量重置密码、补建组织归属与角色、以及免登录调用管理员 REST 接口。当用户问"O2OA 怎么登录/用户名密码是什么""xadmin 密码怎么改""怎么建用户""改了手机号/邮箱""批量重置密码/初始密码是多少""忘了管理员密码""接口报 401 会话已过期""报没有加入任何组织不能启动流程""xadmin 发不了流程""怎么给人加管理员角色/身份""想让 O2OA 完全离线不联系官方服务器"时调用。覆盖：虚拟初始管理员 xadmin 的真相及其不能当业务人员的硬校验、用真实账号绕过、组织/身份/角色 REST、批量改人（为何必须用 xadmin 以免污染 controllerList）、手机号单值硬校验与"第二个号放 PersonAttribute"、初始密码=手机号后6位+%o2、token.json 密码解密、cipher token 构造（免登录调 CipherManagerJaxrsFilter）、登录/建人/改密 REST、Docker 离线隔离方案与踩坑。
agent_created: true
category: operations
---

# O2OA 本地管理员账号与登录

适用于 O2OA 10.0.2（Docker / 裸部署均可）。目标是**纯本地**拿到可登录的管理员、管理账号、
并能在不登录的情况下调管理员接口。全程不访问 o2oa.net。

## 0. 先明确三件事（避免走大弯路）

1. **`xadmin` 是"虚拟初始管理员"，不在数据库里。**
   `ORG_PERSON` 表 0 行也能用 `xadmin` 登录。登录时 `ActionLogin` 直接判
   `Config.token().isInitialManager(credential)` 然后签发 manager token，**不查库**。
2. **它的密码明文在 `config/token.json` 的 `password` 字段**，存的是 `(ENCRYPT:...)`。
3. **不要试图用 `xadmin` 当普通用户名去建号**——会报"不能使用初始管理员标识"。

`com.x.base.core.project.config.Token` 里的硬编码常量：

| 常量 | 值 |
|---|---|
| `defaultInitialManager` | `xadmin` |
| `defaultInitialManagerDistinguishedName` | `xadmin@o2oa@P` |
| `initPassword` | `o2oa@2022`（token.json 密码为空时的兜底） |
| `surfix` | `o2platform`（DES key，取前 8 字节） |

## 1. 解出管理员密码

`token.json` 里 password 形如 `(ENCRYPT:aGLbUWYtgzekj1h-NZCZbA)`。解密要**用 O2OA 自己的类**
（配置根目录必须是工作目录，否则 `Config` 读不到）：

```java
// DecPwd.java
import com.x.base.core.project.config.Config;
import com.x.base.core.project.config.Token;
public class DecPwd {
  public static void main(String[] a) throws Exception {
    Token t = Config.token();
    System.out.println("plain  = " + t.getPassword());    // 明文
    System.out.println("cipher = " + t.getCipher());      // md5Hex(明文)，后面要它
    System.out.println("key    = " + t.getKey());
  }
}
```

运行（容器内，`-Duser.dir` 指向 O2OA 根）：

```bash
D=/opt/o2server
CLS="."; for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do CLS="$CLS:$j"; done
cd $D && $D/jvm/linux_java11/bin/java -cp "/tmp/work:$CLS" -Duser.dir=$D DecPwd
```

- `getPassword()` 内部就是 `Crypto.plainText(passwordField)`；字段为空时返回 `o2oa@2022`。
- `getCipher()` = `DigestUtils.md5Hex(getPassword())`。
- `getKey()`：字段为空时取 `surfix`（`o2platform`）前 8 位 = `o2platfo`。

## 2. 登录接口

```
POST /x_organization_assemble_authentication/jaxrs/authentication
Content-Type: application/json
{"credential":"xadmin","password":"<明文>"}
```

成功返回 `{"type":"success","data":{"tokenType":"manager","token":"...","roleList":[...]}}`。
token 同时通过 `Set-Cookie: x-token=...` 下发（`x-token` 名来自 `person.json` 的 `tokenName`）。

登录模式探测（匿名可访问）：
`GET /x_organization_assemble_authentication/jaxrs/authentication/mode`
→ `{userPwdLogin, captchaLogin, codeLogin, bindLogin, twoFactorLogin, faceLogin}`

路径规律：O2OA 每个 war 是 `@ApplicationPath("jaxrs")` + 类级 `@Path("xxx")`，
方法级**只有需要区分时才写 `@Path`**。所以：
- 类级 `@Path("authentication")` + `@POST`（无子路径）→ 就是 `/jaxrs/authentication`
- 类级 `@Path("person")` + `@POST`（无子路径）→ 就是 `/jaxrs/person`
- 带 `@Path("{flag}")` 的是按 path 参数取值的方法（如 GET 单个）

**想确认路径就拆 war 里的源码**（O2OA 把源码打包在 war 里！）：

```bash
unzip -l $D/store/x_organization_assemble_control.war | grep "describe/sources"
# 源码路径：describe/sources/com/x/.../XxxAction.java
```

## 3. cipher token：免登录调用管理员接口（关键）

被 `CipherManagerJaxrsFilter` 保护的接口，可以用 **cipher 类型 token** 直接通过，
无需先登录。这是给自动化脚本用的正路。

### 3.1 token 格式（`HttpToken.who` 里的正则）

```
^(anonymous|user|manager|cipher|systemManager|securityManager|auditManager)
([2][0][1-9]\d[0-1]\d[0-3]\d[0-5]\d[0-5]\d[0-5]\d)     # yyyyMMddHHmmss
(h5|moa|app)?(\S{1,})$
```

### 3.2 生成（务必用 O2OA 自己的 Crypto）

```java
// MkToken.java
import com.x.base.core.project.config.Config;
import com.x.base.core.project.config.Token;
import com.x.base.core.project.tools.Crypto;
public class MkToken {
  public static void main(String[] a) throws Exception {
    Token t = Config.token();
    String type   = Config.person().getEncryptType();   // 默认 "" → DES 分支
    String cipher = t.getCipher();                      // ★ 加密用的 key 就是它
    String token  = "cipher"
        + new java.text.SimpleDateFormat("yyyyMMddHHmmss").format(new java.util.Date())
        + cipher;
    System.out.print(Crypto.encrypt(token, cipher, type));
  }
}
```

### 3.3 ★ 最容易踩的坑：加密 key 是 cipher，不是 getKey()

`CipherManagerJaxrsFilter.doFilter` 调用：
```java
new HttpToken().who(request, response, Config.token().getCipher());
```
而 `HttpToken.who(String token, String key, String encryptType)` 里
`key` 就是 `Crypto.decrypt(token, key, encryptType)` 的 key。

- **正确**：`Crypto.encrypt(plain, Config.token().getCipher(), encryptType)`（32 字符 key，DES 取前 8 字节）
- **错误**：`Crypto.encrypt(plain, Config.token().getKey(), ...)`
  → 服务端报 `can not decrypt token:..., Given final block not properly padded`

### 3.4 发送

```bash
curl -H "x-token: <加密后的值>" http://127.0.0.1:9090/<模块>/jaxrs/<资源>
```

`HttpToken.getToken()` 取值顺序：**query 参数 → Cookie → header(`tokenName`) → `authorization` header**。
`tokenName` 默认 `x-token`（见 `person.json`）。

**cipher token 有效期仅 20 分钟**（`writeFormula` 里 `1200000ms`）。脚本每次调用前重新生成。

## 4. 账号管理 REST（实测通过）

| 用途 | 方法 + 路径 | body |
|---|---|---|
| 建人员 | `POST /x_organization_assemble_control/jaxrs/person` | Person JSON |
| 改密 | `POST .../jaxrs/person/{flag}/set/password/mockputtopost` | `{"value":"新密码"}` |
| 查人员 | `GET .../jaxrs/person/{flag}` | — |
| 导入模板 | `GET .../jaxrs/inputperson/template` | — |
| 导入人员 | `POST .../jaxrs/inputperson/input` | multipart，字段 `file`（xlsx） |
| 清空组织 | `.../jaxrs/inputperson/wipe` | — |

### 建人员的必填与陷阱

`ActionCreate.Wi extends Person`，关键校验：
- `name` 必填且 trim；`unique` 可空但有则校验唯一；`mobile`、`mail` 会做重复校验
- **`unit` 为空时必须自己是 person manager**，否则 `ExceptionAccessDenied`
- **不能用 `xadmin`**（`ExceptionInitialManagerName`）
- 密码为空时会用 `initPassword()` 兜底

最小可用 body：
```json
{"name":"zhangsan","unique":"zhangsan","password":"Zhang@12345",
 "mobile":"13900000000","mail":"zhangsan@local.host","employee":"zhangsan"}
```

创建成功返回 `{"type":"success","data":{"id":"<uuid>"}}`。

## 4.1 ★「xadmin 没有加入任何组织，不能启动流程」——官方硬校验与正解

**现象**：用 `xadmin` 发起任意流程，界面右上角红字
`"xadmin" 没有加入任何组织，不能启动流程。请联系管理员将您添加到对应的组织中。`
API 层对应 `POST /jaxrs/work/process/{processId}` 返回
`500 指定用户没有找到身份: xadmin.`

**根因**：`xadmin` 是虚拟初始管理员（第 0 节），**不在 `ORG_PERSON` 表**，
`distinguishedName = xadmin@o2oa@P` 但它**没有任何 identity 记录**，
流程引擎的组织/身份校验（"发起人必须有身份"）必然失败。

**为什么不能"补一条 xadmin 人员 + 身份"（死锁两条腿）**：

| 尝试 | 结果 |
|---|---|
| `POST /jaxrs/person` 建 `name=xadmin` | `不能使用初始管理员标识`（`ExceptionInitialManagerName`） |
| 同上但换 `unique=xadmin_a`，name 仍含 xadmin | **同样被拒** → 是**包含匹配**，不是精确匹配 |
| 同上但 `name=XAdmin`（大小写） | **同样被拒** → 大小写不敏感 |
| `POST /jaxrs/identity` 用 `person=xadmin@o2oa@P` | `人员:xadmin@o2oa@P, 不存在.`（要求 ORG_PERSON 真实存在） |

**结论：O2OA 设计上 `xadmin` 只能当纯后台管理员，不能当业务流程人员。**
想"就用 xadmin 跑流程"只能改源码打掉校验（不推荐：升级需重放补丁、权限冗余）。

**正解：另建一个真实业务管理员账号**，同时具备「后台管理权限」+「组织身份」：

```python
# 1) 建人员（mobile 必须过格式校验；password 可直接在建的时候给）
POST /x_organization_assemble_control/jaxrs/person
{"name":"系统管理员","unique":"admin","mobile":"13900000000",
 "mail":"admin@o2oa.local","description":"..."}

# 2) 建身份（挂顶层组织，major=True 表示主职）
POST /x_organization_assemble_control/jaxrs/identity
{"person":"系统管理员@admin@P","unit":"<unitId 或 unique>","major":true,"name":"系统管理员"}

# 3) 设密码（★ 路径是 set/password，字段名是 value）
PUT  /x_organization_assemble_control/jaxrs/person/admin/set/password
{"value":"o2oaadmin2026"}

# 4) 授系统角色（★ 成员维护在 role 侧，PUT 必须提交完整对象）
GET  /x_organization_assemble_control/jaxrs/role/794455a8-3b6a-4573-8e46-047ff21cd7e0   # Manager
PUT  /x_organization_assemble_control/jaxrs/role/794455a8-...   # body = 上一步 data + personList:[人员id]
```

**验证（决定性对照）**：
```
POST /x_processplatform_assemble_surface/jaxrs/work/process/{processId}
  admin  → 200 ✅
  xadmin → 500 "指定用户没有找到身份: xadmin." ❌
```

现成幂等脚本：`tools/o2_fix_xadmin_org.py`（`check` / `apply` / `rollback`）。
要点：`find_person` 要防 `/person/xadmin` 的**虚拟回退态假阳性**
（返回 200 但 `id="xadmin"`、`unique` 串成 `o2oa`），用 id 是否为 UUID 判断真实性。
清理测试残留：`DELETE /jaxrs/person/{id}`、`DELETE /jaxrs/unit/{id}`、`DELETE /x_processplatform_assemble_surface/jaxrs/work/{id}`。

## 4.2 组织 / 身份 / 角色 REST 契约（实测）

**列接口多走 POST**（GET 常返 405）：
`POST /jaxrs/{person|unit|identity|role}/list/all`、`/role/list/like`（**空 key 返回空数组，别用它查角色**）。

| 用途 | 方法 + 路径 | 必填 / 说明 |
|---|---|---|
| 建人员 | `POST /jaxrs/person` | `name` + `mobile`（过格式校验）；name/unique 含 `xadmin` 被拒 |
| 建组织 | `POST /jaxrs/unit` | `name`；同级唯一（靠 `unique` 判重）；`superior` 指定上级 id |
| 建身份 | `POST /jaxrs/identity` | `person`(dN) + `unit`(id/unique/DN)；同人同组织不可重复 |
| 改密 | `PUT /jaxrs/person/{name}/set/password` | **字段名 `value`** |
| 重置密码 | `PUT /jaxrs/person/{flag}/reset/password` | 无 body |
| 授角色 | `PUT /jaxrs/role/{roleId}` | 提交**完整角色对象**，`personList` 写人员 **id**；缺 name/unique 报「角色名称不能为空」 |
| 查角色 | `GET /jaxrs/role/{roleId}` | 内置 roleId 稳定，见 `ORG_ROLE` 表 |
| 列用户角色 | `GET /jaxrs/role/list/person/{id}` | — |

查真实契约的权威来源（**别靠探针猜**）：
`o2_core/o2/xAction/services/x_organization_assemble_control.json`
→ `{"changePassword": {"uri": "/jaxrs/person/{name}/set/password", "method": "PUT"}, ...}`

**⚠️ REST 探针有副作用**：建人员/组织时**缺字段也可能返 200 并真的落库**。
实测用探针建出 2 个 unit + 1 个 person 需手工清理。宁可先读上面的 json 契约。

**角色/dN 格式速查**：

| 对象 | distinguishedName 示例 |
|---|---|
| 人员 | `李芳@lifang@P` |
| 身份 | `李芳@51100000500009247D_lifang@I`（`{unitUnique}_{personUnique}`） |
| 组织 | `综合管理部@zhb@U` |
| 角色 | `Manager@ManagerSystemRole@R` |

**关键表**：`ORG_PERSON` / `ORG_UNIT` / `ORG_IDENTITY` / `ORG_ROLE` / `ORG_ROLE_personList`（角色↔人员，列 `ROLE_XID` + `xpersonList`）/ `CPT_COMPONENT`。


### 改密的两个陷阱

1. **参数名是 `value`**（Wi 继承 `WrapString`），不是 `newPassword`！
   写错报"密码不能为空"。
2. **不能改 `xadmin`** → `ExceptionDenyChangeInitialManagerPassword`「请通过控制台修改初始管理员密码」。
   改法见下节。

### 4.3 批量改「手机号 / 邮箱」+ 批量重置密码（2026-09-23 实测，9 人实名名单全通过）

**接口**
- 改人：`PUT /jaxrs/person/{id}`，body = **完整 Person 对象**（先 GET，再改字段回写）
- 重置密码：`GET /jaxrs/person/{flag}/reset/password` → `{"value":true}`，无 body

**★★ 批量改人时用 `xadmin`，不要用 `admin`**
`ActionEdit.convertControllerList` 会**无条件把操作者写进目标人的 `controllerList`**：
```java
if (!Config.token().isInitialManager(effectivePerson.getDistinguishedName())) { list.add(...); }
```
⇒ 用 `admin` 每改一个人就给自己添一条「控制者」关系（无谓的数据污染）；
用 `xadmin` 命中 `isInitialManager` 分支 ⇒ **不写**。而 `xadmin` 登录后 `tokenType=manager`，
`Business.editable()` 第一行就是 `effectivePerson.isManager()` ⇒ 权限足够。
**凡"运维式批量改人"，一律用 `xadmin`。**

**★ body 用白名单字段，不要整段回吐 GET 的 `data`**
白名单：`name/unique/description/employee/orderNumber/status/superior/controllerList/mail/mobile/distinguishedName`。
（GET 的 `data` 里混有 `woIdentityList/woRoleList/control/topUnitList/mobileValid` 等非 Person 字段；
Wi copier 本就排除 `id/createTime/updateTime/pinyin*/password*/icon*/lastLogin*/topUnitList`，回吐也不会脏，白名单更稳。）

**★★ 改完必须回读，不要只信 PUT 的 200**
- `ActionEdit` 在 `emc.commit()` **之后**还会调 `business.instrument().collect().person()`（仅手机号变化时）；
  断网封锁 collect 时**可能让响应变 500，但数据其实已提交** ⇒ 以回读为准。
- **紧接 PUT 的 GET 可能读到旧缓存**：实测孟弋洁首次回读 `mail` 仍是旧值，几秒后重读才正确
  ⇒ **回读不一致时再读一次再判定**，别急着报失败。

**★★ 手机号是单值字段（`;` 分隔一定失败）**
- `BaseAction.checkMobile` → `Config.person().isMobile(mobile)` → 用 `person.json.mobileRegex`
  对**整串**做 `Pattern.matches`，**没有 split**（`x_base_core_project.jar` 的 `config/Person.class` 里
  只有 Pattern/Matcher，无 StringUtils.split 痕迹）。
  ⇒ `13371637051;13371677253` 直接 **500 `手机号 ... 错误,不能为空,且必须符合指定格式.`**
- 默认正则（可在 `person.json` 改 `mobileRegex`）：
  `(^(\+)?0{0,2}852\d{8}$)|(^(\+)?0{0,2}853\d{8}$)|(^(\+)?0{0,2}886\d{9}$)|(^1(3|4|5|6|7|8|9)\d{9}$)`
- **要存第二个号 → 用「人员属性 PersonAttribute」**：
  ```
  POST /jaxrs/personattribute  {"person":"<人员id>","name":"备用手机号"}
  PUT  /jaxrs/personattribute/{id}   ← ★ 值字段名是 attributeList（数组），不是 attribute！
  ```
  写成 `attribute` 会**静默建成空属性**（POST 返回 200，但 `attributeList:[]`）。
  读回：person 的 `woPersonAttributeList[].attributeList` 才是值。
- 邮箱走 `StringTools.isMail`；**mobile 与 mail 都做唯一性校验**（重复报 `ExceptionMobileDuplicate` /
  `ExceptionEmployeeDuplicate`，比较时排除自己）。

**★ 重置密码 = 手机号后 6 位 + `%o2`**
`person.json` 的 `password` 脚本：`(return person.getMobile().slice(-6) + "%o2";)`
⇒ **必须先改手机号、后调 reset**，否则新密码按旧手机号算。
接口只返回 `{"value":true}`、**不回显密码** ⇒ 想要铁证就**拿该密码真登录一次**
（`POST /jaxrs/authentication`），实测 8/8 全通。
注意 `captchaLogin:true` 时**首登并不强制图形验证码**（密码对即成功）。
`admin`/`xadmin` 自身被 `ExceptionDenyResetInitialManagerPassword` 硬保护，重置不了。

**★★ 初始密码有时效，且失败尝试有配额（2026-09-23 15:39 实测踩到，很坑）**
- `person.json` 的 `firstLoginModifyPwd=true` ⇒ 用户首次用初始密码登录后**被强制改密**，初始密码随即失效。
- `reset/password` **不写** `xchangePasswordTime`（被重置但从没登录过的账号该列 = `NULL`）
  ⇒ **该列非空 == 用户本人改过密码**。这是区分"重置失败"与"已被正常启用"的唯一可靠旁证（走 DB 查）。
  实测：9 人名单发布后 20 分钟内 7 人已自行登录改密；此时用初始密码回测 7 个全 500
  `用户不存在或者密码错误.` —— **但这不是故障**。
- **登录失败会累计 `failureCount`**（`ActionLogin.personLogin` → `failure()`）：
  距上次失败未超 `failureInterval`（本机 10 分钟）则 +1；满 `failureCount`（本机 5）即
  `status=LOCK` + `lockExpireTime=now+interval`，登录改报 `ExceptionFailureLocked`（"锁定至 …"）。
  **★ 成功登录不会清零 `failureCount`** —— 只有"距上次失败超过 interval 分钟"的下一次失败
  才会把它重置为 1。⇒ **任何"拿初始密码试登录"的验证都要先查 DB 再决定试不试，别盲试。**

**现成工具（本项目，2026-09-23 沉淀）**：`tools/o2_batch_person_contact.py`
（`backup` 只读快照 / `apply --dry-run` 空跑 / `apply` 执行 / `verify` 回读+登录取证 / `rollback` 还原），
名册与快照在 `docs/artifacts/person-contact-20260923/`。`verify` 已内置
"先查 `xchangePasswordTime`，已知被本人改密就跳过登录尝试、不消耗失败配额"。

**★ 证明「组织关系不变」的做法**：改人前后各取一次
`GET /jaxrs/identity/list/person/{personId}` + `GET /jaxrs/role/list/person/{personId}` 做 diff。
`Identity` 是独立实体，`PUT person` 不会碰它；只在 `isNameUpdate` 时才顺带同步 identity 的 `name`。

## 5. 修改 xadmin 密码

只能改 `config/token.json`（接口层拒绝）。流程：

```bash
# 1) 生成新的 (ENCRYPT:...) 值
#    Crypto.formattedDefaultEncrypt(明文)
docker exec -it o2oa-server sh -c '
D=/opt/o2server; cd /opt/o2server/admin-tools
cat > Enc.java <<EOF
import com.x.base.core.project.tools.Crypto;
public class Enc { public static void main(String[] a) throws Exception {
  System.out.print(Crypto.formattedDefaultEncrypt(a[0])); } }
EOF
CLS="."; for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do CLS="$CLS:$j"; done
$D/jvm/linux_java11/bin/javac -cp "$CLS" -d classes Enc.java
cd $D && $D/jvm/linux_java11/bin/java -cp "/opt/o2server/admin-tools/classes:$CLS" -Duser.dir=$D Enc "新密码"
'

# 2) 写回 config/token.json 的 "password" 字段
# 3) docker restart o2oa-server
```

## 6. Docker 离线隔离（不触发与官方服务器的联系）

目标：**容器不能出外网，但宿主仍能访问 web 端口**。

`docker-compose.yml`：

```yaml
services:
  o2oa:
    dns:
      - 127.0.0.1                    # 不存在的解析器 → 外网域名全部解析失败
    extra_hosts:
      - "mysql:${O2OA_MYSQL_IP:-172.22.0.2}"   # 容器间通信走静态解析
networks:
  o2oa-net:
    driver: bridge                   # ★ 普通 bridge
```

**为什么不能用 `internal: true`**：internal 网络没有默认网关，会**同时切断宿主机的端口映射**，
`localhost:9090` 直接变 502。这是本方案最关键的一条经验。

原理：O2OA 对 o2oa.net 的访问（更新检查/许可校验/统计上报）**全部依赖域名解析**，
DNS 被指到 127.0.0.1 就等于把对外通道掐断；而容器间 `mysql` 用 `extra_hosts` 静态解析不受影响。

验证：
```bash
docker exec o2oa-server curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://www.o2oa.net  # 000
docker exec o2oa-server getent hosts mysql                                                          # 172.22.0.2
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9090/                                     # 200
```

注意：Docker Desktop 会**忽略 compose 的 `dns:` 覆盖**（容器内 `/etc/resolv.conf` 仍写
`nameserver 127.0.0.11`），但外网实际已经不通，效果达成。

## 7. 现成工具脚本 o2admin.sh

装到容器 `$O2OA_HOME/admin-tools/`：

```bash
S=/opt/o2server/admin-tools/o2admin.sh
$S token                            # 生成 cipher token（20 分钟）
$S login xadmin o2oaadmin2026       # 测试登录
$S mkperson zhangsan Zhang@12345    # 建普通人员
$S setpwd   zhangsan NewPwd@2026    # 改密
```

要点：脚本内 classpath 必须分开变量拼（`"$CLS$JARS"`），
否则 `sed` 批量替换路径时会把 `classes` 拼到 jar 列表尾部导致
`java -cp ...zip4j-2.11.5.jar/classes` 这种坏路径。

## 8. 环境硬坑清单

| 坑 | 现象 | 对策 |
|---|---|---|
| Windows 写的 `.sh` 是 **CRLF** | 容器内执行报 `sh: ...: not found` | 先转 LF 再 `docker cp` |
| `docker exec sh -c 'cat > f' < localfile` | 目标文件 **0 字节** | 改用 `docker cp` |
| `docker cp` 目标目录不存在 | `Could not find the file` | 先 `docker exec mkdir -p` |
| `docker cp` 抓大目录超时 | 无输出 / SIGTERM | 只抓需要的子路径；或走 HTTP 直拉 |
| `/tmp` 非持久 | 文件莫名消失 | 工具装 `$O2OA_HOME/` 下 |
| 加密 key 用错 | `Given final block not properly padded` | key 用 `getCipher()` 不是 `getKey()` |
| 改密参数名 | "密码不能为空" | body 用 `{"value":"..."}` |
| `internal: true` 网络 | 宿主 9090 → 502 | 用普通 bridge + `dns` + `extra_hosts` |
| **REST 探针误伤** | 探针请求返 200 却真写库 | 先读 `xAction/services/*.json` 契约；建完核对计数 |
| **`/person/xadmin` 假阳性** | 返 200 但 `id="xadmin"`、`unique` 串成 `o2oa` | 用 **id 是否为 UUID** 判断人员是否真实存在 |
| **MySQL 库名不是 `o2oa`** | `Unknown database 'o2oa'` | 本项目库名是 **`X`**（`SHOW DATABASES` 确认）；密码见 compose 的 `MYSQL_ROOT_PASSWORD` |
| `docker exec` OCI setns 失败 | `no such file or directory` | `docker restart` 后短暂可用；或用 `docker cp` / 临时容器绕 |

## 9. 快速排查路径

```
登录失败「用户不存在或者密码错误」
  ├─ credential 是 xadmin？ → 密码必须是 token.json 的明文（第 1 节解密）
  └─ 普通用户？ → 查 ORG_PERSON 是否有该 name；密码是否被改过
报「没有加入任何组织，不能启动流程」/「指定用户没有找到身份」
  ├─ 是 xadmin？ → 官方硬校验，正解见第 4.1 节（另建 admin，别硬绕）
  └─ 普通用户？ → 查 ORG_IDENTITY 是否有该人身份；身份 unit 是否有效
接口 401「会话已过期或未登录」
  ├─ 用的什么 token？ → cipher 用第 3 节生成；普通 token 需先登录
  ├─ token 超过 20 分钟？ → 重新生成
  └─ 仍 401 → 查容器日志 grep "can not decrypt token" / "token format error"
接口 404
  └─ 路径不对（鉴权已过）。查 o2_core/o2/xAction/services/<模块>.json 的 uri/method
接口 405「Method Not Allowed」
  └─ 方法不对但路径存在：组织模块的 list 多为 POST；PUT/GET 混用很常见
接口 500 带业务 message
  └─ 鉴权已过，是业务校验失败（看 message/prompt 字段）
```

