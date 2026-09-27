---
name: o2oa-force-external-mysql
description: 让 O2OA（开源版 / Docker 自托管）真正使用外部 MySQL 而非静默回退内置 H2，并处理 O2OA 升级后的补丁重放。当用户抱怨"配了 externalDataSources.json 还是用 H2""MySQL 里没有表""jdbc:h2:tcp Connection refused""OpenJPA: A JDBC driver or data source class name must be specified""改了 jar 报 VerifyError/ClassFormatError"，或问"O2OA 升级后补丁怎么恢复""怎么升级 O2OA""upgrade_o2oa.sh 怎么用"时调用。覆盖三道硬编码门控的定位、ASM 字节码补丁写法、离线 JVM 校验、JNDI 名映射机制、Dockerfile 固化、以及升级重放流水线（体检/重打/等价性判据）。
agent_created: true
category: diagnostics
---

# O2OA 强制外部 MySQL（破除 H2 静默回退）

O2OA 10.0.2 开源版把"外置数据源"做成商业版卖点，代码里有**三道硬编码门控**把 user 的
`config/externalDataSources.json` 全部无视、静默回退内置 H2。本 SOP 是已验证的完整破除流程
（2026-09 实测：MySQL 库 163 张表建成，H2 零回退）。

## 0. 先做只读取证（别急着改字节码）

```bash
# a) 配置是否被读到
docker exec <c> cat /opt/o2server/config/externalDataSources.json

# b) 关键：MySQL 表数 vs H2 文件
docker exec <mysql> mysql -u<u> -p<p> -N -e \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='X';"
docker exec <c> bash -c 'find /opt/o2server -name "*.mv.db" -o -name "*.h2.db"'

# c) 到底是哪种 H2 回退（文件型 or TCP 型）
docker logs <c> 2>&1 | grep -iE "h2:tcp|jdbc:mysql|persistence provider is attempting" | head
```

判据：
- H2 文件 0 个 + MySQL 0 表 + 日志刷 `jdbc:h2:tcp://127.0.0.1:20050/X ... Connection refused`
  → 是 **TCP 型 H2**（不是文件型！），门控③ 未破。
- 刷 `persistence provider is attempting ... javax.persistence.jdbc.driver`
  → JNDI 名对不上，门控③ 补丁方向有误（见 §3 的 `jdbc/s001`）。

## 1. 定位三道门控（都在 jar 字节码里）

| # | 类/方法 | 原行为 | 修复要点 |
|---|---|---|---|
| ① | `x_base_core_project.jar` → `com.x.base.core.project.config.Config.externalDataSources()` | `return ExternalDataSources.defaultInstance()`（enable=false），不读 JSON | 无条件读 `config/externalDataSources.json`，读不到才 defaultInstance |
| ② | 同 jar → `ExternalDataSources.enable()` | 字节码 `iconst_0; Boolean.valueOf(false); areturn` 硬返回 false | 改为遍历 `this`，任一元素 `getEnable()==TRUE` 即返回 TRUE |
| ③ | `console.jar` → `com.x.server.console.ResourceFactory.internal()` → `internalDriudC3p0()` | 遍历 `Config.nodes().dataServers()`，硬编码 H2，绑 `jdbc/<letter>` 到 H2 **TCP**，**从不读 external 配置** | `internal()` 改调新增 `internalDriudC3p0_external()`，按 external 配置建 MySQL Druid 并绑 `jdbc/sNNN` |

反编译取证（O2OA 自带 JDK，`javap` 不在 PATH）：
```bash
JP=/opt/o2server/jvm/linux_java11/bin
docker exec <c> bash -c "$JP/javap -p -c -classpath /opt/o2server/console.jar \
  com.x.server.console.ResourceFactory" | sed -n '/internalDriudC3p0()/,/^$/p'
```

## 2. ★ 核心机制：外部模式下 OpenJPA 查的 JNDI 名是 `jdbc/s001`，不是 `jdbc/X`

这是最容易走弯路的地方（本 SOP 的作者在此卡了整整一轮）。

`com.x.base.core.container.factory.PersistenceXmlHelper` 有三组对称方法：
`properties{Base,External,Internal}{Slice,Single}`，派发在 `properties(String, boolean isSlice)`：
`isSlice ? (external?ExternalSlice:InternalSlice) : (external?ExternalSingle:InternalSingle)`。

外部分支写的是 **per-slice 动态键**（BootstrapMethods 常量）：
```
openjpa.slice.Names                      = s001
openjpa.slice.s001.ConnectionFactoryName = jdbc/s001      # slice 模式
openjpa.ConnectionFactoryName            = jdbc/s001      # single 模式
```
- 名字来自 `ExternalDataSources.names()`，规则 `"s" + (1000+序号)` 取后 3 位 → 首条 = `s001`。
- `propertiesBaseSlice` 里**没有任何** `javax.persistence.jdbc.driver` → JNDI 查不到就直接报
  "A JDBC driver or data source class name must be specified"。

**所以原版 `internalDriudC3p0()` 绑的 `jdbc/X` 外部模式根本不用** → 必须绑 `jdbc/s001`。

实测命令（确认名字，别猜）：
```java
Config.externalDataSources().names();                 // [s001]
Config.externalDataSources().findNamesOfContainerEntity("x_general");  // [s001]
PersistenceXmlHelper.properties("x_general", true);    // 打印全部 key/value
```

## 3. Druid 类层级陷阱（直接导致 VerifyError）

`com.alibaba.druid.pool.DruidDataSourceC3P0Adapter` **只 `implements javax.sql.DataSource`**，
**不继承** `DruidDataSource`（内部是 `private DruidDataSource dataSource`）。

- 直接在 Adapter 上调：`setDriverClass / setJdbcUrl / setUser / setPassword /
  setMaxPoolSize / setMinPoolSize / setAcquireIncrement`
- **必须先取出内部对象再调**：
  `DruidDataSource inner = (DruidDataSource) FieldUtils.readField(adapter,"dataSource",true);`
  然后 `inner.setTestWhileIdle/setTestOnBorrow/setTestOnReturn/setValidationQuery/
  setTimeBetweenEvictionRunsMillis/setMinEvictableIdleTimeMillis/setMaxWait`

否则 JVM 校验报 `VerifyError: Bad type on operand stack`（方法 owner 解析成 `DruidDataSource`，
而 Adapter 不是其子类）。

## 4. 改 console.jar 必须用 ASM，不能用 Javassist

- **Javassist 3.21 复制方法会破坏 Java 11 `NestMembers` 属性** →
  `ClassFormatError: Nest member class_info_index 546 has bad constant type`（容器崩溃循环）。
- **ASM `COMPUTE_FRAMES` 在多处控制流会崩**（`Frame.merge` 的 `ArrayIndexOutOfBounds`、
  `getCommonSuperClass` 类加载失败抛 `TypeNotPresentException`）。
  → 用 `COMPUTE_MAXS` + **手工 StackMapTable 帧**；static 方法 slot0/1 填 `TOP`。
- 工具：容器内 `commons/ext_java11/asm-9.7.jar`；JDK `/opt/o2server/jvm/linux_java11/bin`。
- **补丁必须从原始 jar 读取**：否则重复注入 → `ClassFormatError: Duplicate method name`。

## 5. 离线 JVM 校验（必须！否则容器崩溃循环）

注入前先用真实 classpath 强制校验生成的 class：

```java
// VerifyCls.java：自定义 ClassLoader defineClass + 反射列方法
class Probe extends ClassLoader {
  Class<?> define(byte[] b){ return defineClass("com.x.server.console.ResourceFactory", b,0,b.length,null); }
}
```
```bash
CP="/opt/o2server/console.jar:$(ls /opt/o2server/store/jars/*.jar /opt/o2server/commons/ext_java11/*.jar /opt/o2server/commons/*.jar | tr '\n' ':')"
$JP/java -Xverify:all -cp "/tmp/rfasm:$CP" VerifyCls   # 期望输出 VERIFY_OK
```
**只有 `VERIFY_OK` 才允许 `jar uf` 注入 + 重启。**

## 6. 注入、验证、固化

```bash
# 注入（jar update 单文件）
$JP/jar uf /opt/o2server/console.jar com/x/server/console/ResourceFactory.class
docker restart <c>          # 保留容器层，补丁不丢
```

**验证闭环（全绿才算成功）**：
| 项 | 期望 |
|---|---|
| `information_schema.tables WHERE table_schema='X'` | **> 0**（实测 163） |
| `find / -name "*.mv.db" -o -name "*.h2.db"` | **0 个** |
| 日志 `persistence provider is attempting` | **0** |
| 日志 `VerifyError`/`ClassFormatError` | **0** |
| 日志 `h2:tcp` | **0**（破除前可达数百条） |
| `curl -o /dev/null -w '%{http_code}' localhost:<port>/` | **200** |

**固化到镜像**（否则 `force-recreate` 丢补丁）：
```bash
docker exec <c> cat /opt/o2server/console.jar > patch/console.jar.patched   # 导出
# Dockerfile 增加：
#   COPY patch/x_base_core_project.patched.jar ${O2OA_HOME}/store/jars/x_base_core_project.jar
#   COPY patch/console.jar.patched             ${O2OA_HOME}/console.jar
docker compose build && docker compose up -d --force-recreate   # 实测后补丁仍在
```

## 7. 环境硬坑（本机 ARM64 + QEMU on Windows）

- `docker cp /d/...` 在 Git Bash 下会被错转成 `d:\d\...` → 用 `D:/...` 形式，或
  `docker exec <c> cat <in-container> > <hostfile>` 重定向。
  **★ 更稳的修法：`export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'` + `cygpath -w` 转 Windows 路径。**
  实测报错原文：`invalid output path: directory "D:\d\O2OA\patch" does not exist`。
- `docker exec`（不带 shell）**不会展开通配符** `console.jar*` → 用 `bash -c 'ls ...'`。
- 改 jar 后**必须重启** JVM 才加载新类；`docker restart` 保留容器层，
  `force-recreate` 需先 `docker compose build`。
- init 服务激活门控：`token.json 密码为空 AND X.mv.db 不存在`，否则 `/jaxrs/*` 全 404。

---

## 8. ★★ O2OA 升级后的补丁重放（2026-09-19 交付并实测）

O2OA 每次升级（10.0.2 → 10.0.X）**都必须重打三道补丁**，否则新版又退回 H2。
已交付自动化：`D:\O2OA\upgrade_o2oa.sh`（宿主侧 8 步编排）+ `patch/o2oa_rebuild_patches.sh`
（容器内 6 阶段流水线）+ `UPGRADE.md`（用户文档）。

**用户操作只有两步**：把新版 `o2server-10.0.X-linux-x64.zip` 放到 `D:\O2OA`，跑脚本。

### 8.1 流水线的设计原则（改脚本时别破坏）

1. **体检先行**：用 `javap -c` 判三道门控是否还在，已修复则**跳过**该补丁（不盲目重打）。
   - 门控① 判据：`externalDataSources()` 的 javap 输出含 `ExternalDataSources.defaultInstance`
   - 门控② 判据：`enable()` 输出含 `iconst_0` 且**不含** `hasNext|iterator`
   - 门控③ 判据：`ResourceFactory` 方法清单含 `internalDriudC3p0`
2. **补丁③ 先离线校验再产出**：`VerifyCls.java` + `-Xverify:all` → `VERIFY_OK` 才 `jar uf`。
3. **补丁必须从 `/in/*.orig.jar`（原始 jar）读**，不能从已打的 jar 读（`Duplicate method name`）。

### 8.2 ★ ASM 补丁的输出路径陷阱

`ResourceFactoryAsmPatch` **内部硬编码把补丁类写到 `/tmp/rfasm/`**，不是 cwd！
流水线必须显式：
```bash
ASMOUT=/tmp/rfasm
rm -rf "$ASMOUT"                                   # 先清，否则拿到上次的残留
$JP/java -cp "$ASM:." ResourceFactoryAsmPatch ./console.orig.jar
PATCHED_CLS="$ASMOUT/com/x/server/console/ResourceFactory.class"
( cd "$ASMOUT" && $JP/jar uf "$WORK/asm/console.orig.jar" com/x/server/console/ResourceFactory.class )
```
离线校验的 classpath 也必须双份：
`CP="$ASMOUT:$WORK/asm:$CJ:$XC:$alljars"` —— `$WORK/asm` 是 VerifyCls 自身所在，
漏了会报 `Could not find or load main class VerifyCls`。

### 8.3 ★★★ 产物等价性判据（最容易误判的认知坑）

**`jar uf` 会向 jar 写入内嵌时间戳 → 同一份源码重打两次，jar 整体 md5 也会不同。**

所以判断两次补丁产物是否一致，**必须比类文件字节，不能比 jar 的 md5**：
```bash
# 分别 unzip 出 .class，再 md5sum 比对
cd a && unzip -o -q X.jar 'com/x/server/console/*' && md5sum $(find . -name '*.class'|sort) > A.txt
cd b && unzip -o -q Y.jar 'com/x/server/console/*' && md5sum $(find . -name '*.class'|sort) > B.txt
diff A.txt B.txt        # 一致即内容等价
```
实测基准值（10.0.2，重放产物 = 线上产物，jar md5 不同但类字节一致）：
```
com/x/server/console/ResourceFactory.class                8867206df33f00aa4ba02ec137d2d84b
com/x/server/console/ResourceFactory$1.class                29b2f605c61ab5b86202e19bb97d67b5
com/x/base/core/project/config/Config.class                efea32ef5759db47dd586ccf7a5a1d09
com/x/base/core/project/config/ExternalDataSources.class   1abfa76263e12d69d7d2e6070b17d784
```

### 8.4 宿主侧编排的 5 个坑（端到端实跑才暴露）

1. **`if ! cmd | tail` 吞掉失败** —— 管道退出码来自 `tail`（恒 0）。输出落盘再判 `cmd` 的 rc。
2. **`COPY o2server-*-linux-x64.zip` 多版本 glob 陷阱** —— 目录里有多个版本 zip 时 glob 命中多个，
   COPY 直接失败。用 `tar -cf - "$ZIP" | docker build -t X -f - .` 只传指定那一个作上下文。
3. **`grep -c` 无匹配时 rc=1 且打印 "0"**，再配 `|| echo 0` 得到两行 → 改 `wc -l`。
4. **`[ "$X" -lt N ]` 遇非数字报 `integer expression expected`** → 先 `case "$X" in ''|*[!0-9]*) X=0;; esac`。
5. **失败了要能回滚**：本项目**不是 git 仓库**，不能靠 `git checkout`。
   用文件备份（`.upgrade-backup/`）+ `rollback_cfg()` 在 build/up 失败时自动还原。

### 8.5 失败时的承诺边界（对用户要讲清楚）

**不能承诺"处理所有可能的问题"**。补丁③ 是 ASM 改字节码 + 手工 StackMapTable 帧，
新版若改 `ResourceFactory.internal()` 方法结构、换 JDK（11→17+）、或重构类，
补丁会失败。此时脚本必须：
- 给出**明确的失败原因**（不是静默产出坏镜像）
- **不覆盖现有产物、不产出镜像**（现有服务照常可用）
- 让用户能拿到 `.upgrade-work/out/report.txt` 做人工接力

### 8.6 幂等

`patch/.patched_source_md5` 记录产物对应的源 jar 哈希。若源哈希一致（同一版本重跑），
脚本会提示并询问是否继续重打（避免无意义覆盖）。

