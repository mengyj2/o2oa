# O2OA 脚本沙箱 HostAccess 收敛 + 看门狗持续化（安全加固知识库）

> 类别：`o2oa_security`（O2OA 本地化实例安全加固专题）
> 来源：2026-09-22 ~ 09-23 对话沉淀 + `docs/` 相关方案提炼
> 适用：本地 Docker 自托管 O2OA 10.0.2 社区版（已断云）

---

## 0. 一句话结论

O2OA 服务端脚本（GraalVM polyglot）存在反射越权沙箱逃逸链；本版本（10.0.2）**没有**
`scriptingBlockedClasses` 取值器，单靠"黑名单"无法堵住反射绕过。正确修法是以
`HostAccess.ALL` 为基线、逐项 `denyAccess` 危险类（保留 `allowPublicAccess` 兼容业务脚本），
并把 `allowClass` 类名层拦截作为纵深；再用 ASM 把 `eval` 实际调用的 `HostAccess.ALL`
替换为 `ScriptHostAccessPolicy.hardenedHostAccess()`。硬化通过 Dockerfile 烤入 + 升级脚本重放
**声明式固化**，再用**看门狗**补齐运行态持续守护，构成三层闭环。

---

## 1. 根因分析（为什么"黑名单不够"）

### 1.1 攻击面
- `GraalvmScriptingFactory.eval` 用 `Context.allowHostAccess(HostAccess.ALL)` +
  `allowHostClassLookup(name -> true)`（全放行）。
- 于是脚本只要持有一个宿主对象（如平台注入的 `com.x.*` 实例），即可：
  `Class.forName("java.lang.Runtime").getMethod("getRuntime").invoke(null)
   .exec("...")` —— 反射链直达 `Runtime.exec`，完成 RCE。
- `allowClass` 只做**类名层**拦截（`denyClassList.contains` 才拒），反射链通过
  任意宿主对象绕开，黑名单必然被绕过。

### 1.2 本版本实测前提（与用户初始假设不同）
- 用户以为 `general.json` 的 `scriptingBlockedClasses` 默认含 Runtime/ProcessBuilder/Class。
  **实测 10.0.2 只有 `scriptingAllowedClasses` 白名单 + `HostAccess.ALL`，并无 `scriptingBlockedClasses` 取值器。**
- 所以修法不是"补黑名单"，而是"收敛 HostAccess"。**不能直接用裸 `EXPLICIT`**——
  业务脚本大量依赖绑定宿主对象（平台 API），裸 EXPLICIT 会把这些合法调用全杀掉，搞瘫业务。

### 1.3 关键坑（排查中踩过、已固化为经验）
| 坑 | 现象 | 正确做法 |
|---|---|---|
| **ASM `owner` 斜杠 vs 点名** | `visitFieldInsn` 里 `owner` 是 JVM 内部名 `org/graalvm/polyglot/HostAccess`，代码却用点名 `org.graalvm.polyglot.HostAccess` 比较 → 条件永不成立，`HostAccess.ALL` 始终未被替换（半生效） | 比较串必须用斜杠内部名 `org/graalvm/polyglot/HostAccess` |
| **`super.visitXxx()` 吞指令** | ASM visitor 误调基类空实现 → 改写静默无效果 | 必须 `mv.visitXxx()` 显式委托 |
| **`docker exec` setns 失败** | 本机 ARM64/QEMU 跑 amd64 镜像，重启后偶发 `fork/exec /proc/self/fd/6: no such file or directory` | 核验 live jar 用 `docker cp` 拉文件 + zipfile 类哈希比对，绝不依赖 exec |
| **`docker run` 被 ENTRYPOINT 劫持** | `docker run o2oa:10.0.2 sh -c '...'` 会去起 O2OA，自定义脚本不执行 | 必须 `--entrypoint sh` 覆盖 |
| **javac 缺 `graal-sdk`** | 编译 ASM 改写器报找不到 `org.graalvm.polyglot` | cp 补 `commons/module_java11/graal-sdk-22.3.4.jar` |
| **JVM 缺 JVMCI 参数** | 离线 `VerifyScriptHarden` 抛 `NoClassDefFoundError: jdk.vm.ci.services.Services` | 加 `-XX:+UnlockExperimentalVMOptions -XX:+EnableJVMCI --module-path=.../module_java11 --upgrade-module-path=.../compiler.jar:.../compiler-management.jar` |

---

## 2. 修法（代码级）

### 2.1 安全策略类 `ScriptHostAccessPolicy`（patch/script_harden/）
- `hardenedHostAccess()`：以 `HostAccess.ALL` 为基线 `newBuilder()`，`allowPublicAccess()` 保留业务兼容，
  再逐项 `denyAccess`：Runtime / ProcessBuilder / Process / System / ClassLoader / Thread / ThreadGroup /
  RuntimePermission / SecurityManager / Method / Field / Constructor / AccessibleObject / Modifier / Proxy /
  InvocationHandler / File 系 / Files / Paths / Path / URL / URLClassLoader / Socket 系 / InetAddress /
  NetworkInterface / DriverManager / Connection / Statement / PreparedStatement。
- `isDangerousClass(String)`：fail-closed（空名返回 true），拒绝前缀
  `java.lang.reflect.` / `java.lang.invoke.` / `java.io.` / `java.nio.file.` / `java.net.` / `java.sql.` /
  `javax.script.` / `javax.xml.` / `org.w3c.dom.` + 上述精确类名。

### 2.2 ASM 改写器 `GraalvmScriptingFactoryHarden`（patch/script_harden/）
- `EvalVisitor`：把 `eval` 方法里 `getstatic HostAccess.ALL` 替换为
  `invokestatic ScriptHostAccessPolicy.hardenedHostAccess()`（注意坑 1.3 的斜杠比较）。
- `AllowClassVisitor`：在 `allowClass(String)` 方法开头前置
  `if (ScriptHostAccessPolicy.isDangerousClass(name)) return false;`，作为类名层纵深。
- 改写后 `jar uf` 注入 `ScriptHostAccessPolicy.class`，`javap` 回读校验：
  eval 调 `hardenedHostAccess`、allowClass 前置 `isDangerousClass`、`getstatic HostAccess.ALL` 残留 = 0。

### 2.3 离线验证器 `VerifyScriptHarden`（patch/script_harden/）
- 直接用 `hardenedHostAccess()` 构造 `Context`，断言：良性 `ArrayList`/`String`/平台类零回归；
  `Runtime.exec` / 反射链 / `new java.io.File().exists()` / `new java.net.Socket()` / JDBC 全被
  `PolyglotException` 拦截。**23 项全过输出 `VERIFY_OK`，否则 `VERIFY_FAIL` 退 1**。

---

## 3. 固化（声明式基线）—— 三层

| 层 | 机制 | 防什么 |
|---|---|---|
| 镜像层 | `Dockerfile` `COPY patch/x_base_core_project.patched.jar` → `store/jars/`（合并版 = 原始 + 脚本硬化，与 MySQL `ResourceFactory` 补丁③同 jar 无冲突） | 容器重建丢硬化 |
| 升级层 | `patch/o2oa_rebuild_patches.sh`【步骤 2b】（恒需不跳过）：编译 ASM+GraalVM SDK → 改写 eval/allowClass → 注入策略 → 回读校验 → `-Xverify:all`+GraalVM 模块跑 `VERIFY_OK`；**任一不过则 `die` 不产带病 jar** | 升级冲掉硬化 |
| 运行层 | **看门狗** `tools/o2_sandbox_harden_watchdog.py` | 运行态手工/异常漂移 |

> 重要事实：`docker-compose.yml` 里 `store/jars` **不是卷**（仅 config/local/logs/webroot/custom/dynamic 是卷），
> 所以重建容器走镜像，硬化不丢。

---

## 4. 看门狗持续化（本次新增，解决"等同持久化"不够）

### 4.1 为什么需要
"等同持久化"（只在磁盘放等价 jar + Dockerfile）补不到运行态盲区：有人手工 `docker cp` 回滚、
异常升级重置 jar、误拉旧镜像——这些不触发升级脚本，O2OA 侧零报错，硬化静默丢失。

### 4.2 机制（tools/o2_sandbox_harden_watchdog.py）
- 每 `POLL_INTERVAL`（默认 300s）：`docker cp` 拉出 live jar → zipfile 算
  `GraalvmScriptingFactory.class` 的 SHA-256 + 检查 `ScriptHostAccessPolicy.class` 是否存在 →
  与黄金副本 `patch/x_base_core_project.patched.jar` 比对。
- 漂移 → 自动重放：`docker cp` 黄金 jar → 容器 → `docker restart` → 重跑 `o2oa_netlock.sh`
  （Docker 重启丢 iptables，必须重锁）。
- **全程零 `docker exec`**（规避 1.3 的 setns 坑），零 JVM 依赖。
- 退出码：`--once` 模式 `0`=健康/`1`=漂移（可接 CI/监控）。

### 4.3 部署
```bash
python tools/o2_sandbox_harden_watchdog.py              # 前台循环
python tools/o2_sandbox_harden_watchdog.py --once       # 单次校验（CI）
python tools/o2_sandbox_harden_watchdog.py --install    # 注册系统服务（开机自启）
```
- 配套：`run_sandbox_watchdog.bat`（后台拉起）、`install_watchdog_task.bat`（管理员注册 Windows 计划任务）、
  `o2_sandbox_harden_watchdog.service`（Linux systemd 模板）。
- **注意**：`--install` 的 `schtasks /Create /RU SYSTEM` 需管理员权限；普通会话会"拒绝访问"，
  此时以管理员运行 `install_watchdog_task.bat` 即可。

---

## 5. 验证铁证（均已实跑）
- 字节级：新容器 live jar 与 `patch/x_base_core_project.patched.jar` **类内容逐字节等价**（691 类、零差异、含 `ScriptHostAccessPolicy`）。
- 反编译：eval 调 `hardenedHostAccess()`，eval 内 `getstatic HostAccess.ALL` 残留 = 0；allowClass 前置 `isDangerousClass`。
- 离线 `VERIFY_OK`（23 项全过）：良性脚本零回归；Runtime/ProcessBuilder/System/反射链/File/Socket/Connection 全拦截。
- 运行态：9090=200；MySQL 接管确认（X 库 622 表，未回退 H2）；断网隔离恢复（外网封死、宿主 9090 正常、AI 端口放行）。
- 看门狗 `--once` 实测 `[HEALTHY] OK`。

---

## 6. 回滚预案
- 原始基线 `patch/x_base_core_project.before_harden.jar`（1244308）/ 部署前 live 备份 `x_base_core_project.live_before_deploy.jar`。
- 回滚：`docker cp` 任一带回 `store/jars/` + `docker restart` + 重跑 `o2oa_netlock.sh`。
- **回滚前先停用看门狗**，否则看门狗会再次把它"修回"硬化。
- 副作用：硬化会拒绝脚本内 `java.io`/`java.net`/`java.sql`/`java.lang.reflect` 等危险类访问（有意的攻击面收缩）；
  `java.util.*`/`com.x.*` 正常能力不受影响。

---

## 7. 从 `docs/` 提炼的同源方法/技巧/思路（复用清单）

| 主题 | 文档 | 可复用要点 |
|---|---|---|
| 本地知识库 + 多层记忆 | `docs/本地知识库与多层记忆成长体系.md` | 网关 RAG 向量库（`data.db`）+ `docs.category` 命名空间 + `kb_ingest`/`kb_reflect`/`growth_report` 成长闭环；本条目即经 `ingest_o2oa_kb.py` 灌入 `o2oa_security` |
| 商业版平替总体方案 | `docs/商业版平替方案.md` / `商业版平替-实施验证报告.md` | HR/合同/公文/财务/PMS/资产等用低代码自建，断云后不依赖应用市场 |
| 断云六层网络防护 | 同上 + `NETWORK_SECURITY_REPORT.md` | compose `dns:[127.0.0.1]` + `extra_hosts` + 普通 bridge（**绝不能 internal:true**，否则宿主端口 502）；Docker 重启丢 iptables，须重跑 `o2oa_netlock.sh` |
| 外部 MySQL 三道门控 | `UPGRADE.md` + `patch/*.java` | 配了 externalDataSources.json 仍静默回退 H2 → 三道门补丁 + Dockerfile COPY + upgrade 可重放；DB 前缀 PP_C_*/PTL_*/QRY_*；容器时间 UTC，比主机 +8h |
| 容器 QEMU 病态 | `o2oa高级应用开发/docs` 经验 | ARM64 跑 amd64 镜像长跑易病态，`docker restart` 即愈；尽量不 exec，用 docker cp / HTTP / 临时容器 |
| cookie 污染 | `本地知识库与多层记忆成长体系.md` L1 | O2OA REST 走专用 `_o2_http` 客户端，每请求 `cookies.clear()`，严格以 Header `x-token` 鉴权 |
| 设计态四层安全闸 | 同上 | AI 经 design_op 改门户/动态表需：角色闸门 + 草稿不落地 + 过程授权 + 快照回滚；系统级应用命中 deny 直接拒 |
| 动态表走 designer | 同上 | 建表必须走 designer 模块，surface 滞后报 ClassNotFoundException |
| AI 网关栈拓扑 | `docs/网关能力扩展分析.md` / `OCR服务实施报告.md` | chat 8088 / embed 8089 / rerank 8092 / OCR 8091 统一由 18790 网关调度；4GB VRAM 下大模型按需加载 |

> 思路提炼：**任何"声明式固化"（Dockerfile/镜像/升级脚本）都有运行态盲区，必须有"看门狗"持续守护**——
> 这一范式已从邮件服务容器（`docker-compose.yml` 的 `restart: unless-stopped`）和本沙箱看门狗两次印证：
> 声明式（写在代码、随分支走、可复现、可审计）才是真·持久化，外挂进程/手工守护都不如写进代码。
