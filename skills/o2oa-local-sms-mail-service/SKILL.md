---
name: o2oa-local-sms-mail-service
description: 在 O2OA（社区版 / Docker 自托管，10.0.2 实证）上**不写 Java、不打 war，纯 Python 平替 `x_sms_assemble_control`**，让短信验证码变成纯本地能力（本机生成 + 经系统邮箱投递），从而让「忘记密码」「登录短信验证码」真正可用。当用户说"本地短信验证""验证码发不出去""忘记密码报 ExceptionDisableCollect""CodeFactory create error""怎么自己发验证码""断云后短信怎么办""邮箱收不到验证码"时调用。覆盖三个必踩的坑：netlock 端口白名单漏放、**容器 DNS 被断云掐断导致用域名注册的地址必然连不上（必须用 IP）**、**注册条目约 30s 不续报会被清出服务表**。
agent_created: true
category: development
---

# O2OA 本地短信验证码服务（自研 `x_sms_assemble_control` 平替）

适用 O2OA 10.x（Docker 自托管 10.0.2 实测，已断云）。

## 0. 结论先行

**不需要写 Java、不需要打 war。** 只要让 O2OA 的服务注册表里存在一个
`className` 以 `.x_sms_assemble_control` 结尾的条目，并提供一个 HTTP 端点，
O2OA 就会把「下发验证码 / 校验验证码」全部转交过来。

## 1. 原理：闸门源码与匹配规则

`x_organization_assemble_authentication` 等处的取码逻辑（三处一致）：

```java
String customSms = applications().findApplicationName("x_sms_assemble_control");
if (isNotBlank(customSms) && Config.customConfig("custom_sms") != null) {
    // 通道①：转给自定义短信服务（我们接管的就是这条）
    getQuery(customSms, "sms/send/code/mobile/{mobile}/token/(0)");   // 期望 {"value":true}
} else if (collect().getEnable() != true) {
    throw new ExceptionDisableCollect();          // 没配时的原状态
} else { /* 通道②：O2OA 云短信 */ }
```

常量：`CUSTOM_SMS_APPLICATION = "x_sms_assemble_control"`、
`CUSTOM_SMS_CONFIG_NAME = "custom_sms"`。

**★ 匹配规则**（反编译 `Applications.findApplicationName` 字节码实测）：

```java
for (String key : keySet())
    if (StringUtils.equalsIgnoreCase(key, name)
        || StringUtils.endsWithIgnoreCase(key, "." + name))   // 常量池拼出来的是 "." + name
        return key;
return null;
```

⇒ 注册的 `className` 只要**以 `.x_sms_assemble_control` 结尾**即命中。
例：`com.x.ccia.sms.assemble.control.x_sms_assemble_control`。
（拼的确实是 `"."`，不是 `"_"` —— 用 `javap -v` 看 BootstrapMethods 的
`makeConcatWithConstants` 实参为 `.\u0001` 可证。）

### 通道①生效的三个条件（缺一不可）

| # | 条件 | 怎么做 |
|---|---|---|
| 1 | 服务注册表里有命中条目 | `PUT /x_program_center/jaxrs/center/regist/applications`（见 §3） |
| 2 | `config/custom_sms.json` 存在 | **内容非空即可**（不必是合法配置对象） |
| 3 | 仅"忘记密码"额外需要 `collect.enable=true` | 该接口第一行就查 collect、**完全不查通道①** |

**关于第 3 条**：`x_organization_assemble_personal/jaxrs/reset/ActionCode.java` 开头就是
`if (isNotTrue(Config.collect().getEnable())) throw new ExceptionDisableCollect();`。
但 O2OA 云的 `/jaxrs/collect/*` 接口若已被（本项目用 javassist 注入的）拦截器物理 403，
则 `collect.enable=true` **无外连风险** —— 可以放心打开。

**通道①下 O2OA 自有的 `Code` 表不参与**：`CodeFactory` 只是把
`create(mobile)` / `validate(mobile,answer)` 转发到 `x_program_center`，
再由它按上面的闸门转发给自定义服务。**生成与校验全归你**。

## 2. ★★ 三个必踩的坑（按实际踩坑顺序）

### 坑 1 · netlock 的出站端口白名单漏放本服务端口

若用了「容器出站封网」脚本（本项目 `o2oa_netlock.sh`：FORWARD 链按源容器 IP 做
端口排除式 DROP），**新增任何宿主端口都必须加进 `--dports` 列表**：

```bash
iptables -I FORWARD 2 -s $IP ! -d 172.16.0.0/12 -p tcp \
  -m multiport ! --dports $LLM_PORT,$GW_PORT,$MAIL_PORT -j DROP
```

漏放的症状就是 `CodeFactory create error:{mobile}`，且服务端收不到任何请求。

> 注意该脚本里那条 `-d $LLM_HOST` 的 ACCEPT 规则其实是**死规则** ——
> Docker Desktop 会把「容器→宿主 LAN IP」做 NAT，到达 FORWARD 链时目标 IP 已变，
> 所以真正起作用的是 DROP 规则的**端口排除**部分。

### 坑 2 · ★★ 容器内域名解析被断云策略掐断 ⇒ 注册地址必须用 IP

O2OA 容器为断云通常设了 `dns: [127.0.0.1]`，容器内实际是：

```
nameserver 127.0.0.11        # Docker 内嵌 DNS
ExtServers: [127.0.0.1]      # 上游指向一个没有 DNS 服务的地址
```

后果：**所有域名都解析失败**，包括 `host.docker.internal`。
O2OA 日志表现得非常隐晦：

```
java.lang.Exception: GET connect connection error,
  address: http://host.docker.internal:8095/x_sms_assemble_control/jaxrs/...,
  because: host.docker.internal.          ← 就是 UnknownHostException，主机名后面是空的
```

**排查手法**（`docker exec` 常因 QEMU setns 不可用时，用共享网络命名空间的临时容器精确复现）：

```bash
# 源 IP = 该容器的 IP，DNS/路由与它完全一致
docker run --rm --platform linux/arm64 --network container:o2oa-server alpine \
  sh -c 'wget -qO- -T 6 http://host.docker.internal:8095/api/health; echo rc=$?'
```

实测对比（Docker Desktop on Windows）：

| 地址 | 结果 |
|---|---|
| `host.docker.internal:8095` | `bad address`（DNS 失败） |
| **`192.168.65.254:8095`** | **200 ✅**（Docker Desktop 的宿主网关，稳定） |
| `172.17.0.1:8095` / `172.22.0.1:8095` | Connection refused |

⇒ **注册时 `node` 字段填 IP，不要填域名**。
（Linux 原生 Docker 上用 `172.17.0.1`；本项目默认 `192.168.65.254`，可配置覆盖。）

### 坑 3 · ★★ 注册条目约 30s 不续报就被清出服务表

`x_program_center` 的 `RefreshApplicationsEvent` 约每 30s 扫一次，按 `reportDate`
判超时清理。日志证据：

```
WARN com.x.server.console.node.RefreshApplicationsEvent - cluster dropped application:
  com.x.ccia.sms.assemble.control.x_sms_assemble_control, node: 192.168.65.254,
  report date: 2026-09-23 13:47:53.
```

被清掉后，O2OA 侧表现为：

```
IllegalStateException: randomWithWeight error: com.x.ccia.sms...x_sms_assemble_control
```

⇒ **keepalive 必须 ≤20s，且必须"无条件重注册"**。
只判断"条目是否存在"是不够的 —— **条目还在但 `reportDate` 过期，照样被 drop**。

```python
KEEPALIVE_INTERVAL = 20   # 留足余量（清理阈值约 30s）

def _keepalive_loop():
    time.sleep(3)
    while True:
        try:
            if load_config().get("enabled", True):
                if not app_registered():
                    log("注册条目不在服务表中，重新注册…")
                register_application()        # ★ 无条件重注册，刷新 reportDate
        except Exception as exc:
            log("心跳注册异常：", exc)
        time.sleep(KEEPALIVE_INTERVAL)
```

## 3. 服务注册（核心调用）

```python
def register_application():
    now = o2oa_now()            # ★ 必须是"服务器当前时间"，误差 <30s（见下）
    app = {
        "className": "com.<你的前缀>.x_sms_assemble_control",   # 结尾必须是 .x_sms_assemble_control
        "name": "邮件验证码服务",
        "node": "192.168.65.254",     # ★★ IP，不能是域名（坑 2）
        "contextPath": "/x_sms_assemble_control",
        "port": 8095,
        "sslEnable": False,
        "proxyHost": "", "proxyPort": 8095,
        "reportDate": now,            # ★★ 超时会被 drop（坑 3）
        "scheduleRequestList": [], "scheduleLocalRequestList": [],
    }
    body = {"value": json.dumps([app], ensure_ascii=False),
            "node": "127.0.0.1", "serverTime": now}
    # PUT /x_program_center/jaxrs/center/regist/applications  →  {"value":true}
```

**取"服务器当前时间"**：容器与宿主有时差，不能直接用本机 `datetime.now()`。
从 `GET /x_program_center/jaxrs/config/list` 返回体里的 `time` 字段取。

`getUrlJaxrsRoot()` 的拼法 = `(ssl?"https":"http") + "://" + node + (port==80/443?"":":"+port)`，
所以 `node` 只承载"主机"部分。

**为什么用 `PUT regist/applications` 而不是部署 war**：本项目已在
`/opt/o2server/custom/` 下有多个官方扩展 war（会自动进服务表）—— 若愿意写 Java，
那是更"正统"的做法；但纯 Python 注册完全够用，且**改一行代码即生效、无需编译**。

## 4. 要实现的 HTTP 契约

```
GET {ctx}/jaxrs/sms/send/code/mobile/{mobile}/token/{token}
    → {"value": true}                    # false → O2OA 侧抛 CodeFactory create error
GET {ctx}/jaxrs/sms/validate/mobile/{mobile}/answer/{answer}/token/{token}
    → {"value": <bool>}
```

注意 O2OA 会把 `token` 占位符编码成 `%280%29`（即字面量 `(0)`），路径匹配要容忍。

**行为差异（实测）**：
- 登录页「短信验证码」接口**不检查返回值** —— 你返回 false 它照样 200
  「验证码已下发，如未收到，请确认是否已绑定该号码。」（会误导用户！）
- 「忘记密码」接口返回 false 会**直接抛 `CodeFactory create error`**。

## 5. 投递通道选择

- **落到本地 `Code` 表**：**不适用** —— 通道①下 O2OA 的 Code 表不参与，
  生成与校验都在你这边，自己存即可（文件/SQLite/内存）。
- **发到注册邮箱**（推荐，本项目采用）：
  `PUT {ORG}/jaxrs/person/list/like {"key": "<手机号>"}` 反查人员 → 取 `mail` 字段。
  （`GET person/list/mobile/{m}` 与 `GET person/mobile/{m}` 都是 404，别走弯路。）

## 6. 部署与验证清单

```bash
# 1) 起本地服务（监听 0.0.0.0:<port>）
python o2oa_mail_service.py

# 2) 放行端口（若用了出站封网脚本）
bash o2oa_netlock.sh

# 3) 容器内连通性自证（必须 200，否则一定是 IP/DNS 或 netlock 问题）
docker run --rm --platform linux/arm64 --network container:o2oa-server alpine \
  sh -c 'wget -qO- -T 6 http://192.168.65.254:8095/api/health'

# 4) 触发一次真实下发，看两侧日志
curl -s --noproxy "*" -H "x-token:$TK" \
  "http://localhost:9090/x_organization_assemble_personal/jaxrs/reset/code/credential/<姓名>"
tail -20 <服务日志>      # 应出现 "O2OA 请求发码 mobile=… user=… mail=…"
```

**故障对照表**：

| 现象 | 根因 | 处置 |
|---|---|---|
| 日志 `because: host.docker.internal.` | 容器内域名解析失败 | 注册 `node` 改 **IP**（坑 2） |
| 日志 `randomWithWeight error: …` | 注册条目被 30s 超时清掉 | keepalive ≤20s 且**无条件**重注册（坑 3） |
| 服务端**完全收不到请求** + `CodeFactory create error` | netlock 未放行端口 | 加进 `--dports`（坑 1） |
| `ExceptionDisableCollect`（仅"忘记密码"） | `collect.enable=false` | 置 true（collect 接口已被 403 时无外连风险） |
| 连接错误但服务可达、TCP 通 | 服务返回 `{"value":false}` | 查投递环节（SMTP 密码为空最常见，报 `SMTPServerDisconnected`） |

## 7. 本项目落地物（可直接参考/复用）

- 服务：`mailservice/o2oa_mail_service.py`（纯标准库，0.0.0.0:8095）+ `start_mail_service.bat`
- 配置：`mailservice/mail.json`（SMTP / 模板 / 开关）；验证码：`codes.json`；日志：`mailservice.log`
- 管理 API（全带 CORS + `do_OPTIONS`→204，方便浏览器直调）：
  `GET /api/health|status|config|codes|log`、`PUT /api/config`（**patch 语义**，
  密码传 `******` 或留空表示不修改）、`POST /api/test/mail {to}`、
  `POST /api/test/code {mobile}`、`POST /api/register|revoke`
- 配套 UI：`x_component_SysSetting` 的「系统邮箱 / 登录与安全 / 验证码服务」三个分组

### 7.1 ★★ 验证码时效与明文泄露防护（2026-09-26 加固，照抄即可）

`codes.json` 存的是**真实手机号 + 未消费验证码明文**，服务又监听 `0.0.0.0`，
是这个服务唯一的高危面。四条必须同时做到：

1. **TTL 有代码级硬上限**（`CODE_TTL_MAX_MINUTES = 10`）。
   `code_ttl_seconds()` 把 `mail.json` 的 `codeTtlMinutes` 强制 clamp 到 `[1,10]` ——
   配置里填 99999 也只按 10 分钟生效。再叠一层 `effective_expire()`：
   `min(expire, sentAt + 硬上限)`，即使 json 里 expire 被人为改大也不算数。
2. **过期 = 从磁盘消失**。旧实现只在「下次发码时」顺带 `_gc_codes()`，
   导致最后一个验证码的**明文永久滞留**在 `codes.json`（内存已判无效、磁盘仍可读），
   这就是用户看到的"终身"。修法两处：
   - `_load_codes()` **载入即清理**（过期条目当场抹除并回写）；
   - 后台清扫线程 `_sweep_loop()`，`CODE_SWEEP_INTERVAL = 30`s，有变化才落盘。
3. **落盘原子写**（`tmp` + `os.replace` + `fsync`）并 `chmod 600`，
   避免进程被杀留半截 JSON。
4. **管理接口脱敏**：`/api/codes`、`/api/status.pendingCodes` 只出 `mask_mobile()`
   后的 `137****0005`（服务监听 0.0.0.0，局域网可达）。

`.gitignore` 用**通配**而非单文件名，防"改个名/换个目录就漏网"：

```gitignore
mailservice/codes*.json
mailservice/**/codes*.json
mailservice/*.tmp
mailservice/mail.json      # 宿主直跑时默认就落源码根目录，含 SMTP 授权码
```

**历史教训**：`mailservice/data/codes.json` 曾在基线提交 `df25210` 入库过一次
真实手机号 + 6 位验证码，直到 `4f6621a` 才停止跟踪 —— **blob 仍在 git 历史里**。
新项目一开始就要把运行期目录整体 ignore，别等事后 `git filter-repo` + force push。

### 7.2 ★ 双实例抢注册（本项目实地踩到）

宿主直跑一份（`node=192.168.65.254:8095`）+ 容器跑一份（`node=o2oa-mailservice:8095`），
**两者用同一个 className 向 O2OA 续报**，谁最后续报谁生效 → 验证码投递**间歇性失败**。
更要命的是：宿主那份**没有 `mail.json`**（`DATA_DIR` 缺省 = 源码目录，而真实配置在
`mailservice/data/`），于是走 `DEFAULT_CONFIG`、`smtpPassword` 为空 →
`SMTPServerDisconnected` **必然发不出去**。

判定方法（一眼区分）：

```bash
tail -3 mailservice/mailservice.log        # 宿主实例：node=192.168.65.254:8095
tail -3 mailservice/data/mailservice.log   # 容器实例：node=o2oa-mailservice:8095
```

两条都在 20s 内刷新 = 双实例并存。修法二选一：**只留容器实例**（停掉宿主看门狗 +
`O2OA_mail_service_autostart.vbs`），或给宿主实例设 `O2OA_MAIL_DATA_DIR` 指向
`mailservice/data`（注意 `watchdog_mail_service.py` 的路径要同步改，否则判活错位）。

## 8. ★ 配套 UI 挂到菜单（最易漏，且极易假 PASS）

做完服务别以为就完了：**自研的配置界面要真的能被用户点开**。这里的坑是
**O2OA 桌面有两个「开始菜单」，来源完全不同**：

| 菜单 | 驱动 | 形态 |
|---|---|---|
| ☰ 开始菜单 | MySQL `CPT_COMPONENT`（+ 种子 `config/components.json`） | 白色图标网格，页签 `应用/流程/信息/数据` |
| **门户首页「应用菜单」** | **只由门户数据字典 `appmenus` 驱动** | 左侧竖排分组 / 窄屏深蓝分栏大菜单 |

只写 `CPT_COMPONENT` ⇒ 用户在**门户首页**里**看不到**你的配置入口（本项目实测踩到，
用户当场报"系统管理下没有系统设置"）。往字典加条目的完整做法（读/写端点、字段、
图标白名单、`app` = `x_component_` 后的目录名、`allow:[]` = 不限角色）见技能
**`o2oa-custom-desktop-component` 的「铁律 4」**；改完**刷页面即生效，无需重启**。

**验证必须走门户真实路径**：`portal.html?id=<portalId>` → 展开目标分组 →
断言条目在列 → 点击 → 断言配置界面真的渲染出来。只查 `.layout_start_item_text`
（☰ 网格）会给出**假 PASS**。


---

## 9. ★★ 持久化与自愈（本地 Python 服务怎么活过重启）

本地服务是**宿主机上的裸 Python 进程**（不在容器里）⇒ 与 O2OA 容器生命周期完全解耦，
但也**没有任何东西帮你拉起它**。默认状态 = 双击 bat 才活，重启即失联，
而 O2OA 侧只会报 `CodeFactory create error`（看不出是"服务根本没起"）。

### 9.1 三层持久化（本项目已落地，可直接抄）

| 层 | 文件 | 作用 |
|---|---|---|
| ① 自愈 | `mailservice/watchdog_mail_service.py` | 每 30s HTTP 探活 `/api/health`；DOWN 即脱离式重启；PID 锁防双看门狗 |
| ② 开机自启 | 启动文件夹 `O2OA_mail_service_autostart.vbs` | 登录后 sleep 15s → 隐藏窗口拉起 watchdog |
| ③ 运维入口 | `start` / `stop` / `status_mail_service.bat` | 双击可用的启停与体检（含端口兜底清理） |

**看门狗必须幂等**：先探活，健康就什么都不做 ⇒ 重复双击 / 重复自启都安全。
「端口被占但探活不通」判定为**僵死进程**，先按端口杀再拉。

### 9.2 ★★ 三个必踩硬坑

**坑 A · venv 的 `python.exe` 是重定向器 ⇒ `Popen.pid` ≠ 真实 PID**
实测 `Popen(...).pid = 29692`，而真正监听 8095 的是 `2468`。
⇒ **PID 文件必须由进程自己用 `os.getpid()` 写**（唯一写入者），看门狗不要代写，
否则写出的是重定向器 pid，`stop.bat` / VBS 清理时会杀错或杀不到。（`pythonw.exe` 同理。）
判别：`mailservice.pid` 与 `netstat` 里的监听 PID 不一致即中招。

**坑 B · bat 里 `if exist X ( cmd ) else cmd` 单行 + 内嵌 PowerShell 引号会解析错**
症状：`'exist' is not recognized as an internal or external command`。
改成**两条独立的 `if`**，别用括号 else：
```bat
if not exist "watchdog.log" echo     (无 watchdog.log)
if exist "watchdog.log" powershell -NoProfile -Command "Get-Content -Path '%~dp0watchdog.log' -Tail 5"
```

**坑 C · 从 AI 的 Bash 会话里启动的进程，命令一结束就被回收**
`DETACHED_PROCESS` 也救不了（Windows Job Object 按 job 关）。
且安全策略把 `schtasks` / WMI `Win32_Process.Create` / `Start-Process` / 从 Bash 调 `cmd.exe`
**全部拦死** ⇒ **AI 无法单方面把常驻服务"钉"在系统里**，收尾必须交给用户侧：
**双击 `start_mail_service.bat`**，或靠登录自启 VBS。
（`run_in_background` 起的任务能跨命令存活，但会话结束仍终止 —— 只适合验证。）

### 9.3 与 O2OA 启动顺序无关（重要）
注册靠**无条件 20s 心跳重注册**（见坑 3）⇒ 无论「容器先起」还是「服务先起」，
最多 20s 后自动对齐。开机时即使 O2OA 还没就绪，watchdog 也能安全先拉起服务。

### 9.4 验证自愈的正确姿势
```bash
# 1) 让看门狗跑起来（会话内即可，验证用）
python watchdog_mail_service.py &
# 2) 确认服务在跑并记下 PID，同时核对 mailservice.pid 是否一致（坑 A）
netstat -ano | grep ":8095 " | grep LISTENING
# 3) 杀掉它，等一个探活周期 + 就绪时间（约 35–50s）
taskkill /PID <pid> /F
# 4) 断言：新 PID 出现 + registered=True + watchdog.log 有「DOWN -> 拉起」
```

