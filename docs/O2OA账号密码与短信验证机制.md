# O2OA 账号密码与短信验证机制（断云本地化实证）

> 取证方式：`describe/sources/**/*.java` 服务端源码 + 活体 REST 实测。
> 环境：社区版 10.0.2 · Docker 自托管 · `http://localhost:9090` · **已断云**（`collect.enable=false`）。
> 结论面向内部运维：**本地短信验证不可用**；**管理员重置/删除可用**。

---

## 一、结论速览

| 问题 | 结论 |
|---|---|
| 系统里有本地短信验证系统吗？ | **没有**。短信下发只有两条通道，本机两条都不通 |
| 登录页有"短信验证码登录"入口吗？ | **有（且是个死按钮）** —— `person.json` 里 `codeLogin: true` |
| 图形验证码能本地用吗？ | **能**。本地 Java 生成图片，零外部依赖 |
| 用户忘密码，admin 能重置吗？ | **能**。`GET person/{flag}/reset/password`，重置为"初始密码" |
| admin 能删除用户吗？ | **能**。`DELETE person/{flag}`，级联清理 + 留一份删除快照 |
| 初始管理员能被重置/删除吗？ | **不能**，服务端硬闸门拦死 |
| 用户能自助找回密码吗？ | **走不通**。`reset` 第一行就检查云采集，必报「系统没有启用节点连接」 |

---

## 二、短信验证：两条通道，都被闸门锁死

### 2.1 闸门源码（三处逻辑完全一致）

| 位置 | 方法 |
|---|---|
| `x_program_center/jaxrs/code/ActionCreate.java` | `GET code/create/mobile/{mobile}` |
| `x_organization_assemble_authentication/…/ActionCode.java` | `GET authentication/code/credential/{credential}` |
| `x_organization_assemble_personal/jaxrs/reset/ActionCode.java` | `GET reset/code/credential/{credential}` |

```java
String customSms = ThisApplication.context().applications()
        .findApplicationName("x_sms_assemble_control");     // ← 自定义短信应用
if (customSms 非空 && Config.customConfig("custom_sms") != null) {
    // 通道①：转发给它
    getQuery(customSms, "sms/send/code/mobile/{mobile}/token/{token}");
} else if (Config.collect().getEnable() != true) {
    // 通道②的开关
    throw new ExceptionDisableCollect();   // 「系统没有启用节点连接.」
} else {
    // 通道②：O2OA 云
    put(Config.collect().url() + "/o2_collect_assemble/jaxrs/code/transfer", …);
}
```

关键常量（`authentication/…/BaseAction.java`）：
```java
CUSTOM_SMS_APPLICATION = "x_sms_assemble_control";
CUSTOM_SMS_CONFIG_NAME = "custom_sms";
```

### 2.2 本机实际状态（实测）

| 检查项 | 实测结果 |
|---|---|
| `config/collect.json` → `enable` | **`false`**（断云） |
| 容器内 `x_sms_assemble_control` 服务 | **不存在**（applicationServer / centerServer 都没有） |
| `config/custom_sms.json` | **不存在** |
| `GET reset/code/credential/孟弋洁` | **500 `ExceptionDisableCollect`「系统没有启用节点连接.」** |
| `GET authentication/code/credential/admin` | **500 同上** |
| `GET x_program_center/jaxrs/code/create/mobile/18516833076` | **500 `ExceptionDisable`「没有启用连接到云服务器功能.」** |
| `GET x_program_center/jaxrs/code/list` | **200 `data: []`** ← 本地 Code 表可读，只是没人能往里写 |
| `GET authentication/captcha/width/100/height/40` | **200 返回 base64 PNG** ← **本地可用** |

### 2.3 两个要点

1. **验证码对象本身是本地存储的**（`x_program_center` 的 `Code` 表，`code/list` 读得到）。
   缺的只是"把验证码发出去"这一段。**只要补上通道①，短信验证就变成纯本地能力。**
2. **通道①的接口契约已经从源码暴露**，这是自建平替的入口：
   ```
   GET {x_sms_assemble_control}/jaxrs/sms/send/code/mobile/{mobile}/token/{token}
   → {"value": true}
   ```
   外加一个 `config/custom_sms.json`（内容非空即可）。自研一个实现该接口的服务端应用即可接管。

### 2.4 ⚠️ 当前配置的矛盾（登录页有死按钮）

`config/person.json`：

```json
{
  "userPwdLogin": true,
  "captchaLogin": false,     // 图形验证码登录：关
  "codeLogin": true,         // ★ 短信验证码登录：开 —— 但通道不通
  "bindLogin": true,
  "twoFactorLogin": false,
  "firstLoginModifyPwd": true,
  "superPermission": true,
  "register": "disable",
  "password": "(return person.getMobile().slice(-6) + \"%o2\";)",
  "passwordRegex": "^(?=.*[a-zA-Z])(?=.*\\d)(?=.*[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>\\/?]).{8,}$"
}
```

`authentication/mode` 实测返回 `codeLogin: true` → **登录页会渲染"短信验证码登录"入口**，
用户点"获取验证码"必然看到「系统没有启用节点连接」。**建议置为 `false`。**

---

## 三、忘记密码的三条路，只有一条走得通

| 路径 | 接口 | 本机可用性 |
|---|---|---|
| ① 自助找回（短信验证码） | `GET reset/code/credential/{c}` → `PUT reset` | ❌ **走不通**（`ExceptionDisableCollect`） |
| ② 已知旧密码自助改密 | `POST reset/password/anonymous`（需旧密码，无需短信） | ✅ 可用 |
| ③ **管理员重置** | `GET person/{flag}/reset/password` | ✅ **推荐主通道** |

> 路径②实测证据：`reset/check/credential` 对业务用户（孟弋洁/杜阳/卢宏萍）均返回 `{value: true}`，
> 说明入口是开放的；但紧接着取验证码即 500 —— **能走到门口，进不去**。

---

## 四、管理员重置密码

```
GET {org}/x_organization_assemble_control/jaxrs/person/{flag}/reset/password
```

源码（`jaxrs/person/ActionResetPassword.java`）：

```java
if (Config.token().isInitialManager(flag))
    throw new ExceptionDenyResetInitialManagerPassword();          // 初始管理员不可重置
Person o = business.person().pick(flag);
if (!effectivePerson.isSecurityManager() && !business.editable(effectivePerson, o))
    throw new ExceptionDenyEditPerson(effectivePerson, flag);
business.person().setPassword(o, this.initPassword(business, o), true);
```

### 4.1 重置成什么密码？= "初始密码"脚本

`BaseAction.initPassword()` → 取 `Config.person().getPassword()`，用 GraalVM 按正则匹配脚本求值：

```java
// config/person.json
"password": "(return person.getMobile().slice(-6) + \"%o2\";)"
```

**即：手机号后 6 位 + `%o2`**

| 手机号 | 重置后密码 |
|---|---|
| 13700000005 | `000005%o2` |
| 13911168091 | `111091%o2` |
| 18516833076 | `168330%o2` |

> 该口令同时满足 `passwordRegex`（9 位，含数字 / 字母 o / 特殊字符 %）。
> 配合 `firstLoginModifyPwd: true` → 用户首次登录会被强制改密码。
> ⚠️ **若人员没绑手机号**，该脚本取值会异常 → 必须先补手机号，或改用下面的直接设密接口。

### 4.2 想指定任意密码（不走"初始密码"）？

```
PUT {org}/x_organization_assemble_control/jaxrs/person/{flag}/password
```

或强制下次登录改密：`person/{flag}/set/password/expired/time`

---

## 五、管理员删除用户

```
DELETE {org}/x_organization_assemble_control/jaxrs/person/{flag}
```

源码（`jaxrs/person/ActionDelete.java`）：

```java
if (Config.token().isInitialManager(flag))
    throw new ExceptionDenyDeleteInitialManager();      // 初始管理员不可删除
```

级联清理顺序：`UnitDuty`（组织职务成员）→ `Identity`（身份）→ `PersonAttribute` → `PersonExtend`
→ `Custom`（自定义信息）→ `Group`（群组成员）→ `Role`（角色成员）→ `Unit`（组织管理者）
→ `PersonSuperior`（汇报关系）→ 最后删 `Person`。

**全程留痕**：删除前写一条 `Custom`（name = `person#delete`），内容为
`{operator: 操作人dN, operateTime: 时间, person: 被删人快照}` → **有软备份，可追溯、可重建**。

⚠️ **边界**：只清理组织域，**不清理业务数据**。流程实例 / 文件 / 内容 / 消息里对该人的引用会保留，
表现为"历史记录里的人名点不开 / 找不到人"。删除前建议先**禁用（ban）或锁定（lock）**观察一段时间：
```
PUT person/{flag}/lock      PUT person/{flag}/unlock
PUT person/{flag}/ban       PUT person/{flag}/unban
```
更温和的替代：`person/{flag}/reserve/delete`（保留删除）。

---

## 六、权限模型（"与角色对齐"的官方答案）

`jaxrs/person/BaseAction.java`：

```java
protected boolean editable(Business business, EffectivePerson effectivePerson, String personFlag) throws Exception {
    if (business.hasAnyRole(effectivePerson, OrganizationDefinition.Manager,
            OrganizationDefinition.OrganizationManager)) {
        return true;                                    // 系统管理员 / 组织管理员 → 全权
    }
    if (business.hasAnyRole(effectivePerson, OrganizationDefinition.PersonManager)) {
        if (business.sameTopUnit(effectivePerson, personFlag)) {
            return true;                                // 人员管理员 → 仅同顶层单位内
        }
    }
    return false;
}
```

| 角色（本部署实际 dN） | 能力 |
|---|---|
| `Manager@ManagerSystemRole@R` | 全权（admin 实测持有） |
| `OrganizationManager@OrganizationManagerSystemRole@R` | 全权（admin 实测持有） |
| `PersonManager@…@R` | 仅同顶层单位内的人 |

> 实测 `GET authentication` → admin 角色 = `[ProcessPlatformManager…, OrganizationManager…, Manager…]`
> ⇒ **admin 命中第一条，对全部业务人员拥有重置 + 删除权限**。

### 6.1 受保护账号（服务端硬闸门，无法绕过）

| 账号 | 重置 | 删除 |
|---|---|---|
| `admin`（真实初始管理员，人员 dN `系统管理员@admin@P`） | ❌ `DenyResetInitialManagerPassword` | ❌ `DenyDeleteInitialManager` |
| `xadmin`（虚拟超级管理员） | ❌ 同上 | ❌ 同上 |

> 注：`GET person/admin` 返回的 `control.allowEdit/allowDelete` 都是 `true` ——
> 那是**通用字段**，不代表真能删；真正的拦截在 Action 内部的 `isInitialManager` 判断。
> **别被这个字段误导**（实测已确认）。

---

## 七、其他相关接口

| 用途 | 接口 |
|---|---|
| 图形验证码（本地可用） | `GET authentication/captcha/width/{w}/height/{h}` |
| 图形验证码登录 | `POST authentication/captcha`（当前 `captchaLogin: false`） |
| 双因子登录 | `POST authentication/two/factory/login`（当前 `twoFactorLogin: false`） |
| 登录方式开关总览 | `GET authentication/mode` |
| 登录后改自己密码 | `PUT personal/jaxrs/password` |
| 强制下次登录改密 | `person/{flag}/set/password/expired/time` |
| 自助注册开关 | `GET personal/jaxrs/regist/mode` → 实测 **`disable`** |
| 重置前置校验 | `GET personal/jaxrs/reset/check/credential/{c}`、`reset/check/password/{p}` |

---

## 八、建议（分层）

### P0 · 配置层（立刻，零成本）
1. **关掉 `codeLogin`**（`config/person.json` → `false`）→ 消除登录页的短信死按钮。
2. 明确"忘记密码"唯一通道 = **找管理员重置**；把 §4.1 的初始密码规则告知使用者。
3. （可选）开启 `captchaLogin: true`，用**本地图形验证码**提升登录防爆破能力。
4. 给全体人员补手机号（当前 11 人均已绑定，含 `1370000000x` 段的占位号）。

### P1 · 若要"真本地短信"
- **方案 A｜自研短信通道**：注册服务名 `x_sms_assemble_control`，实现
  `GET jaxrs/sms/send/code/mobile/{mobile}/token/{token}` → `{value:true}`，
  并放置 `config/custom_sms.json`。验证码会写进本地 `Code` 表，落地方式自选
  （写文件 / 推到本机 AI 网关 / 显示在管理端）。
  **契约已从源码挖出，技术可行**；但属服务端 Java 应用，工作量大于桌面组件。
- **方案 B｜"忘记密码"申请流（推荐）**：不动核心，做自研组件/流程 ——
  用户提交申请 → 部门负责人审批 → 管理员一键调 `person/{flag}/reset/password` → 告知初始密码。
  全本地、可审计、契合 OA 惯例，复用已有自研组件机制。
- 两者可叠加：B 解决流程，A 解决"总想发条短信"的体验。

### P2 · 真要手机到达
只能接第三方短信商（阿里云 / 腾讯云 / 华为云）。**与"断云"不冲突**（走短信商 API，不是 O2OA 云），
但需要外网出口 + 密钥 + 计费，需评估合规与成本。

---

## 附：本文结论的复现命令

```bash
# 1) 登录方式开关
curl -s --noproxy "*" -H "x-token:$TK" \
  http://localhost:9090/x_organization_assemble_authentication/jaxrs/authentication/mode

# 2) 短信闸门（预期 500 ExceptionDisableCollect）
curl -s --noproxy "*" -H "x-token:$TK" \
  http://localhost:9090/x_organization_assemble_personal/jaxrs/reset/code/credential/孟弋洁

# 3) 图形验证码（预期 200 + base64 PNG）
curl -s --noproxy "*" -H "x-token:$TK" \
  http://localhost:9090/x_organization_assemble_authentication/jaxrs/authentication/captcha/width/100/height/40

# 4) 本地验证码表（预期 200 data:[]）
curl -s --noproxy "*" -H "x-token:$TK" \
  http://localhost:9090/x_program_center/jaxrs/code/list

# 5) 管理员重置（谨慎：会改数据）
curl -s --noproxy "*" -H "x-token:$TK" -X GET \
  "http://localhost:9090/x_organization_assemble_control/jaxrs/person/<人员名>/reset/password"
```
