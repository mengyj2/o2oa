---
name: o2oa-cloud-cutoff
description: 切断 O2OA（Docker 自托管）与官方云平台（collect.o2oa.net / apppack.o2oa.net / app.o2oa.net）的一切联系，并准确回答"断云影响什么功能""是不是 SaaS""要不要 License""应用市场/打包怎么办"。当用户问"怎么让 O2OA 不连官方服务器""注册云账号/云平台怎么禁掉""断网后哪些功能不能用""没有应用市场/应用打包有什么影响""O2OA 需要 License 吗""本机装的是不是 SaaS 版"，或抱怨"关了 enable 还是怕它偷连"时调用。涵盖：外连终点全清单、collect 接口门控审计方法、CollectJaxrsFilter 字节码封锁补丁、License 存在性取证、应用市场临时开闸流程。
agent_created: true
category: security

---

# O2OA 云平台联系切断

## 核心结论（可直接答复用户）

| 用户疑问 | 正确结论 |
|---|---|
| 所有外连都在 Collect？ | **不准确**。云平台类外连（市场/打包/账号）走 `x_program_center` 的 collect 家族；但**钉钉/企微/WeLink/政务钉钉/安Fx 是各自独立的外连模块**，各走各的 `enable` 开关 |
| 断云影响什么？ | **只影响 4 项**：应用市场、APK 云打包、云账号注册/登录/找回密码、移动端 APP 下载页。核心功能（组织/流程/表单/门户/CMS/会议/考勤/日程/附件/AI/搜索/IM）**全部正常** |
| 没应用市场怎么办？ | 市场只是"下载器"。从别处拿 `.o2app` 包，管理后台「本地安装」导入即可，功能一致 |
| 没应用打包怎么办？ | 打包是**纯云端服务**（`ActionAndroidPack` 把 APK POST 到 `apppack.o2oa.net:40088`，本地无 Android SDK/Gradle）。替代：官方公版 APK / 自建 WebView 壳 / PWA |
| 能只临时连市场吗？ | **可以**。`netlock --remove` 开闸 → 进市场下载 → 立刻重新封上。注意市场接口需要 `COLLECT_TOKEN`，得先填云账号密码 |
| 本机是 SaaS 吗？ | **不是**。SaaS 是 O2OA 官方托管；本机是本地自托管社区版，数据/账号/流程全在本地 MySQL。**"预留连云能力" ≠ "是 SaaS"** |
| 需要 License 吗？ | **不需要，且系统根本不校验**。详见下文取证 |

## 关键事实：注册接口没有 enable 门控（这是真正的漏洞）

`x_program_center` 的 `/jaxrs/collect/*` 共 21 个接口，审计结果：

- **有 `Config.collect().getEnable()` 门控**：仅 `login`、`validate`
- **没有门控**：`regist`（POST `/jaxrs/collect`）、`resetpassword`、`code`、
  `exist`、`controllermobile`、`disconnect` 等 **19 个**

**判定方法**：逐文件 grep 是否有 `throw new ExceptionDisable` 或 `isFalse(Config.collect().getEnable())`。

**危害链**（`ActionRegist.java`）：
```java
if (BooleanUtils.isTrue(wo.getValue())) {
    Config.collect().setEnable(true);   // 自动打开云连接
    Config.collect().setName(name);
    Config.collect().setPassword(password);
    Config.collect().save();
    this.configFlush(effectivePerson);
    ThisApplication.context().scheduleLocal(CollectPerson.class);  // 立即上报人员手机号
}
```
→ 只要容器能联网 + 有人调注册接口，就会真的注册云账号、自动启用云、**上报本机人员手机号**。

**因此：只写 `collect.json` 的 `enable:false` 是不够的，必须在接口层物理切断。**

## 取证方法（可复用命令）

### 1. 外连终点全清单 —— 从字节码提取硬编码地址
```bash
# 解压全部 jar（jar 命令比 unzip 可靠，容器内 unzip 可能不存在）
docker exec <容器> sh -c 'mkdir -p /tmp/alljar && cd /tmp/alljar && \
  for j in /opt/o2server/store/jars/*.jar; do /opt/o2server/jvm/linux_java11/bin/jar xf "$j"; done'
# 提取 URL 字面量（容器内可能没有 strings，用 tr 替代）
docker exec <容器> sh -c 'tr -c "[:print:]" "\n" < /tmp/alljar/com/x/base/core/project/config/Collect.class \
  | grep -iE "http|o2oa|jaxrs|apppack|o2_collect" | sort -u'
```
实测结果：`apppack.o2oa.net:40088`、`collect.o2oa.net`、`collect.o2oa.io`、`app.o2oa.net`、
`www.o2oa.net`、`res.o2oa.net`、`117.133.7.109`（ShaTools 硬编码 IP）、`token.cmpassport.com`。

### 2. License 存在性取证（结论：不存在）
```bash
# 全平台搜 license，只应命中 Config.class 一个文件
docker exec <容器> sh -c 'grep -ril "license" /tmp/alljar'
# 读常量真值（-constants 才能看到被内联的字符串常量）
docker exec <容器> sh -c '/opt/o2server/jvm/linux_java11/bin/javap -p -c -constants \
  -cp /tmp/alljar com.x.base.core.project.config.Config 2>/dev/null | grep -A2 LICENSE_TIP'
# 找引用者（关键：零调用点 = 代码里没有校验流程）
docker exec <容器> sh -c 'cd /tmp/alljar && grep -rl "LICENSE_TIP" .'
```
- `LICENSE_TIP` 真值：「抱歉！当前产品未授权或授权已过期，请通过官网(www.o2oa.net)或客服电话(400-888-0545)联系.」
- **全平台 2308 个 class 中，它只被自己声明处引用，零调用点**
- `DEFAULT_PUBLIC_KEY` 是 RSA 密钥对，用于**离线加解密**，不是授权校验
- → **这套代码里没有 License 校验流程**；断网不会触发授权问题

### 3. 接口可达性实测（管理员身份）
```bash
# 取管理员 token
T=$(curl -s -X POST "http://localhost:9090/x_organization_assemble_authentication/jaxrs/authentication" \
  -H "Content-Type: application/json" -d '{"credential":"xadmin","password":"<密码>"}' \
  | grep -oE '"token": *"[^"]+"' | head -1 | sed 's/"token": *"//; s/"$//')

# 关键：观察报错类型
curl -s -X POST "http://localhost:9090/x_program_center/jaxrs/collect" -H "x-token: $T" \
  -H "Content-Type: application/json" -d '{"name":"t","password":"Test1234!","mobile":"13800138000","codeAnswer":"x","mail":"a@b.com"}'
# ExceptionUnableConnect  → 没有 enable 门控（仅因封网失败）★ 说明有漏洞
# ExceptionDisable       → 有 enable 门控（安全）
```
**判读要点**：报 `ExceptionUnableConnect` 说明它**没走 enable 门控**。

## 加固方案：CollectJaxrsFilter 字节码封锁

### 为什么选这个类
`x_program_center` 每个模块一个过滤器，`CollectJaxrsFilter` 是 collect 的统一入口：
```java
@WebFilter(urlPatterns = "/jaxrs/collect/*", asyncSupported = true)
public class CollectJaxrsFilter extends CipherManagerJaxrsFilter { }
```
原本**只有一个默认构造器** → 注入一个 `doFilter()` 极干净，且**一次覆盖全部 21 个接口**。

### 补丁内容
注入的 `doFilter()` 直接 403 返回，**不调用 `chain.doFilter()`**（物理切断，永不进业务逻辑）：
```java
resp.setStatus(403);
resp.setContentType("application/json;charset=UTF-8");
resp.getWriter().write("{\"type\":\"error\",\"message\":\"O2OA collect(o2cloud) interface is disabled by local netlock policy.\"}");
return;
```

### 影响面（已实测）
| 模块 | 过滤器 | 结果 |
|---|---|---|
| collect | `CollectJaxrsFilter` | **全部 403（目的）** |
| market（应用市场） | `MarketJaxrsFilter` | 不受影响，**保持可用** |
| apppack（应用打包） | `AppPackJaxrsFilter` | 不受影响，**保持可用** |

即：**仍可临时开闸用市场和打包，但任何人都无法注册/登录云账号。**

### 落地位置（关键工程决策）
**必须打 war，不能打运行时解包目录。** 踩过的坑：

1. **entrypoint 在 JVM 启动前跑补丁 → 找不到 class**：`servers/centerServer/work/` 是
   JVM **启动后**才从 war 解包出来的，启动前该目录为空。
2. **改运行时解包目录的 class 不会热生效**：JVM 已加载旧 class，必须重启。
3. **正确做法**：在 **Dockerfile 构建期**直接改写 `store/x_program_center.war` 内的 class。
   启动即生效，无需运行时补丁。

参考实现见 `scripts/patch_collect_lock.sh`，接入方式：
```dockerfile
COPY patch_collect_lock.sh ${O2OA_HOME}/patch_collect_lock.sh
RUN chmod +x ${O2OA_HOME}/patch_collect_lock.sh \
    && bash ${O2OA_HOME}/patch_collect_lock.sh --war \
    && bash ${O2OA_HOME}/patch_collect_lock.sh --verify
```
entrypoint 里只做 `--verify` 自检（不修改），便于发现异常。

### 升级兼容
`upgrade_o2oa.sh` 只对 Dockerfile 做**版本号 sed 原地替换**，不删新增行
→ 升级时 `docker compose build` 会自动重打补丁，链路自动兼容。

## 应用市场的临时使用流程

```bash
bash o2oa_netlock.sh --remove      # 1. 解除内核封网
# 2. 改 config/collect.json：enable=true，name/password 填云平台账号
docker restart <容器>               # 3. 重启生效
# 4. 进管理后台 → 应用市场 → 下载应用
bash o2oa_netlock.sh               # 5. 用完立刻重新封上
# 6. 把 enable 改回 false
```
注意：collect 接口已被补丁封死（403），**但市场/打包走独立 filter 仍可用**。
若走接口直连市场的路径需要 `CollectToken`，则需云账号登录——此时被补丁挡住，
→ 这种情况下改用**本地安装 `.o2app` 包**的方式替代。

## 完整防护体系（六层）
1. **DNS 隔离** `dns: [127.0.0.1]` —— 挡域名（**挡不住 IP 直连**）
2. **iptables 内核封堵** `FORWARD DROP 非内网目标` —— 挡 IP 直连（见 `docker-container-egress-lockdown` skill）
3. **配置层消毒** `collect.json` 三地址清空 + `enable:false`
4. **接口层封锁** `CollectJaxrsFilter` → `/jaxrs/collect/*` 全 403
5. **定时任务门控** `CollectMarket`/`CollectPerson`/`Area` 受 `enable=false` 约束
6. **第三方集成开关** 钉钉/企微/WeLink/政务钉钉/安Fx 默认 `enable=false`

## 验收清单
```
【云平台接口】应全部 403
  POST /x_program_center/jaxrs/collect              （注册）
  POST /x_program_center/jaxrs/collect/login        （登录）
  GET  /x_program_center/jaxrs/collect/connect      （探活）
  PUT  /x_program_center/jaxrs/collect/resetpassword（找回密码）
  GET  /x_program_center/jaxrs/collect/code/mobile/{mobile}
【业务接口】应全部 200
  GET  /                                   （首页）
  POST /x_organization_assemble_authentication/jaxrs/authentication
  GET  /x_program_center/jaxrs/config/list
  POST /x_program_center/jaxrs/market/list/paging/1/size/10   ← 故意保留
【entrypoint 日志】
  [entrypoint] 离线加固：云平台 collect 接口封锁 ✓ 已生效
```

## 注意事项
- 容器重建后 IP 变化 → 需重跑 `netlock` 脚本；Docker Desktop 重启后 iptables 规则丢失 → 同样
- 修补后 `x_program_center.war.orig` 是**权威原始副本，请勿删除**（`--restore` 依赖它）
- 补丁脚本幂等：会先检测 war 是否已含 `doFilter`，是则从 `.orig` 取干净副本重新注入，
  避免在补丁态上叠加
- `--verify` 优先检查 war（权威），其次运行时 class（用于 JVM 已启动的场景）
- 解压 jar/war 时 `unzip` 在 O2OA 容器内可能不存在，改用 `$O2OA_HOME/jvm/linux_java11/bin/jar`
- `javap` 不在 PATH，用 `$O2OA_HOME/jvm/linux_java11/bin/javap`
- QEMU（ARM64 跑 amd64）环境下容器 `exec` 偶发
  `error starting setns process: fork/exec /proc/self/fd/6` →
  `docker compose up -d --force-recreate <服务>` 重建后恢复
