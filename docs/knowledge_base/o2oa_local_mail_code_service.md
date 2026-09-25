# 在断云 O2OA 上自建「本地验证码服务」（x_sms_assemble_control 平替）

## 1. 目标与约束

- 官方短信/邮件验证码依赖 O2 云平台；本项目已**断云**（见 `o2oa-cloud-cutoff`）。
- 诉求：让「忘记密码」「登录短信验证码」在**纯本地**可用。
- 约束：不写 Java、不打 war、不下载插件。

## 2. 原理：O2OA 如何把验证码请求转出去

O2OA 的 `CodeFactory.create/validate` 只做两件事：先问 `x_program_center`，再按**闸门**转发给自定义服务。
⇒ **通道生效后，O2OA 自己的 `Code` 表根本不参与**（生成与校验全归被转发的那个服务）。
所以"把验证码落到 O2OA 的 Code 表"这个方向**不成立**，投递只能自己实现（本项目走**邮件**）。

### 2.1 通道生效的三个条件（缺一不可）

| # | 条件 | 说明 |
|---|---|---|
| ① | 服务注册表里有 `className` 以 `.x_sms_assemble_control` 结尾的条目 | 靠服务自己上报 |
| ② | `config/custom_sms.json` 存在 | 内容非空即可，仅作开关 |
| ③ | 「忘记密码」额外还需 `collect.enable=true` | 该接口第一行就查 collect，**完全不查通道①** |

### 2.2 为什么「className 以它结尾」就够 —— 不必写 Java

`findApplicationName` 的匹配逻辑等价于：

```java
equalsIgnoreCase(key, name) || endsWithIgnoreCase(key, "." + name)
```

⇒ 只要上报的 `className` **以 `.x_sms_assemble_control` 结尾**即可命中。
本项目用 `com.x.ccia.sms.assemble.control.x_sms_assemble_control`，纯 Python 实现，零 Java。

## 3. 三个必踩的坑（全部实测踩过）

### 3.1 注册用的 `node` 必须是 IP，不能是域名

**背景**：断云手段之一是把容器 `dns` 指向 `127.0.0.1`（`ExtServers` 也是 `127.0.0.1`）
⇒ **容器内一切域名解析失败**。

**症状**：O2OA 日志非常隐晦，只报
`connect connection error, address: http://host.docker.internal:8095/..., because: host.docker.internal.`
（末尾那个孤立的主机名就是 `UnknownHostException`）。

**实测结论**：
- `host.docker.internal` → `bad address` ❌
- `192.168.65.254:8095`（Docker Desktop 宿主网关）→ 200 ✅
- `172.17.0.1` / `172.22.0.1` → Connection refused ❌

### 3.2 注册条目约 30s 不续报就被清掉

`RefreshApplicationsEvent` 按 `reportDate` 超时清理（日志 `cluster dropped application: ...`）。
**条目在、但 reportDate 过期照样被踢**（实测 27s）。

**症状**：O2OA 侧报
`IllegalStateException: randomWithWeight error: com.x.ccia.sms...x_sms_assemble_control`

**做法**：心跳间隔 ≤ 20s，且**无条件重注册**——不要"先判断条目是否存在再决定要不要注册"。

### 3.3 断网脚本的端口白名单

封网用内核 `FORWARD` 链 DROP，放行靠 `--dports` 白名单：

```bash
iptables -I FORWARD 2 -s $O2OA_IP ! -d 172.16.0.0/12 -p tcp \
  -m multiport ! --dports $LLM_PORT,$GW_PORT,$MAIL_PORT -j DROP
```

**新增任何宿主端口都必须加进 `--dports`**，否则被 DROP，症状是 `CodeFactory create error`。

> ★ **容器化后这个坑自然消失**：服务若与 o2oa 同在一个 Docker 网络（如 172.22.0.30），
> 目标地址落在放行的 `172.16/12` 内，无需白名单。这是"把服务放进 compose"的一个额外收益。

## 4. 投递通道的选择

| 方案 | 可行性 |
|---|---|
| 落到 O2OA 的 `Code` 表 | ❌ 通道①下 Code 表不参与 |
| 自己发短信用短信网关 | ❌ 断云环境无网关 |
| **投递到用户注册邮箱**（`person.mail`） | ✅ 推荐 |

手机号 → 人员的查法：`PUT {ORG}/jaxrs/person/list/like {"key": "<mobile>"}`
（`GET person/list/mobile/{m}`、`GET person/mobile/{m}` 都是 404）。
默认 11 人全部已配 `mail`。

## 5. 部署与验证清单

```bash
# 1. 服务在线
curl -s --noproxy "*" http://127.0.0.1:8095/api/health

# 2. 已注册 + 通道三条件
curl -s --noproxy "*" http://127.0.0.1:8095/api/status      # registered / node
#   ① 注册表条目   ② custom_sms.json 存在   ③ collect.enable=true

# 3. 端到端：本地日志应出现「O2OA 请求发码 mobile=... user=... mail=...」
```

### 故障对照表

| 症状 | 根因 | 修法 |
|---|---|---|
| `CodeFactory create error`，服务端完全收不到请求 | 端口被 FORWARD DROP | 加进 `--dports`；或把服务放进同一 Docker 网络 |
| 同上，但端口已放行 | 注册 `node` 用了域名，容器解析不了 | 改 IP / 容器名（容器名需对方 `extra_hosts` 静态声明） |
| 偶发失败、约半分钟后恢复 | 条目被 refresh 踢出 | 心跳 ≤20s 且无条件重注册 |
| `SMTPServerDisconnected` | 授权码为空（163 企业邮箱） | 填入授权码，可用 `smtp.passwordSet` 判空 |

> ★ 一条通用经验：**163 企业邮箱 `smtp.ym.163.com:465` 本身没问题**
> （DNS/TCP/TLS1.3 实测全通，banner `220 ... ESMTP ready`），
> 唯一原因就是授权码没填 —— 别去怀疑网络。
