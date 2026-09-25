# O2OA 升级与补丁重放指南

> 适用：本目录的 O2OA 自建镜像（Docker）。目标版本 10.0.X 系列。

---

## 一句话流程

```powershell
# 1. 把新版安装包放到 D:\O2OA\（保持原始文件名）
#    例：o2server-10.0.3-linux-x64.zip

# 2. 双击 upgrade_o2oa.bat    （或 PowerShell 里： .\upgrade_o2oa.bat）
```

跑完看到绿色的 `✓ 升级完成：O2OA 10.0.3 已运行在外部 MySQL 上` 就算成功。

---

## 为什么需要这个脚本

O2OA 社区版（开源版）把「用外部数据库」这个能力**硬编码关掉了**。用官方 zip 直接起容器，
无论你怎么写 `config/externalDataSources.json`，它都会**静默回退到内置 H2**。

具体是三道门控（都在字节码里）：

| # | 位置 | 原始行为 | 补丁做法 |
|---|---|---|---|
| ① | `x_base_core_project.jar`<br>`Config.externalDataSources()` | `return ExternalDataSources.defaultInstance()`<br>即永远 enable=false，无视 JSON | 改为无条件读 `config/externalDataSources.json` |
| ② | `x_base_core_project.jar`<br>`ExternalDataSources.enable()` | 字节码 `iconst_0 → return false`<br>（疑为商业版开关） | 改为遍历列表，任一 `getEnable()` 为真即返回 true |
| ③ | `console.jar`<br>`ResourceFactory.internal()` | 把 JNDI 名 `jdbc/<字母>` 死绑到内置 H2 TCP | 新增 `internalDriudC3p0_external()`，按 JSON 建 MySQL DruidDataSource 并绑 `jdbc/sNNN` |

所以**每次升级都必须重新打这三个补丁**，否则新版本又会退回 H2。
`upgrade_o2oa.sh` 就是把这个重打过程自动化。

---

## 脚本做了什么（8 步）

1. **定位 zip** —— 自动挑版本号最大的 `o2server-*-linux-x64.zip`，也可用参数指定
2. **提取原始 jar** —— 从 zip 里取出 `console.jar` 和 `store/jars/x_base_core_project.jar`
3. **起临时容器** —— 复用现有镜像，`--network none`（完全离线）
4. **跑补丁流水线** —— 体检 → 重打 → 离线字节码校验
5. **同步版本号** —— 改 Dockerfile / docker-compose.yml 里的版本引用
6. **构建镜像** —— `docker compose build`
7. **重建容器** —— `docker compose up -d --force-recreate`
8. **验证** —— 查 MySQL 表数 / H2 文件残留 / h2:tcp 报错

---

## 环境变量开关

| 变量 | 作用 |
|---|---|
| `SKIP_BUILD=1` | 只打补丁，不构建不重启（预演用） |
| `KEEP_CONTAINER=1` | 构建镜像但不重启容器 |

```bash
SKIP_BUILD=1 bash upgrade_o2oa.sh      # 只想看看新版补丁能不能打上
```

> ⚠️ 用 `SKIP_BUILD=1` 时，Dockerfile/compose 的版本号**已经被改了**。
> 若之后想直接 `docker compose up -d`，会因为找不到新标签的镜像而失败，
> 要么补跑 `docker compose build`，要么从 `.upgrade-backup/` 还原这两个文件。

---

## 补丁流水线在体检什么

脚本**不会盲目重打**。它会先用 `javap` 反编译新版字节码，判断三个门控是否还存在：

- 如果检出某道门控**已消失** → 说明 O2OA 官方在这个版本修好了 → **跳过该补丁**（打印 WARN）
- 如果三道都还在 → 照常重打

这样如果哪天 O2OA 官方真修了，你不会有"补丁把已经修好的代码搞坏"的风险。

体检输出示例：

```
[OK]   门控① 仍存在（externalDataSources() 返回 defaultInstance）→ 需要补丁
[OK]   门控② 仍存在（enable() 硬返回 false）→ 需要补丁
[OK]   门控③ 仍存在（internal() 走 internalDriudC3p0，绑 H2）→ 需要补丁
体检结果: 补丁①=yes  补丁②=yes  补丁③=yes
```

---

## 失败时会怎样

**明确承诺：失败不会破坏你现有的可用状态。**

- ✗ **补丁①② 失败** → 说明 `Config` / `ExternalDataSources` 的方法结构变了。
  脚本中止，**不产出镜像，不覆盖现有产物**。
- ✗ **补丁③ 失败**（常见 `VerifyError`）→ 说明 `ResourceFactory.internal()` 结构变了，
  ASM 写入的 StackMapTable 帧对不上。脚本中止，同样不动现有产物。
- ✗ **镜像构建失败** → 自动把 Dockerfile / docker-compose.yml 还原回升级前内容。
- ✗ **容器重建失败** → 同上，自动还原。

任何失败时，请把这两个文件发出来（这是唯一证据）：

```
.upgrade-work/out/report.txt     ← 体检结论 + 每步结果
.upgrade-work/pipeline.log       ← 完整执行日志
```

---

## 边界：脚本做不到什么

**不能承诺"处理所有可能的问题"。**

补丁③ 是直接改写字节码的（ASM 方法入口重写 + 手工 StackMapTable 帧）。
如果新版 O2OA：

- 把 `ResourceFactory.internal()` 的方法签名改了
- 换了 JDK 版本（Java 11 → 17+，栈映射规则不同）
- 重构了 `ResourceFactory` 类结构

那么补丁③ 会失败。这种情况**必须人工重新分析该方法**，没有自动化捷径。
脚本的作用是让你**一眼看出是哪一步失败了、为什么失败**，而不是默默产出一个坏镜像。

---

## 验证产物等价性（进阶）

如果怀疑重打的产物和原来不一样，**不要比 jar 的 md5** ——
`jar uf` 会写入时间戳，同一份源码重打两次 md5 都会不同。

正确的比法是比类文件字节：

```bash
mkdir -p /tmp/cmp/a /tmp/cmp/b
cd /tmp/cmp/a && unzip -o -q /d/O2OA/patch/console.jar.patched com/x/server/console/ResourceFactory*.class
cd /tmp/cmp/b && unzip -o -q <旧产物.jar> com/x/server/console/ResourceFactory*.class
diff <(cd /tmp/cmp/a && md5sum $(find . -name '*.class'|sort)) \
     <(cd /tmp/cmp/b && md5sum $(find . -name '*.class'|sort))
```

已实测：2026-09-19 用 10.0.2 zip 重放，`ResourceFactory.class` 与线上产物字节**完全一致**：

```
com/x/server/console/ResourceFactory.class    8867206df33f00aa4ba02ec137d2d84b
com/x/server/console/ResourceFactory$1.class   29b2f605c61ab5b86202e19bb97d67b5
com/x/base/core/project/config/Config.class                efea32ef5759db47dd586ccf7a5a1d09
com/x/base/core/project/config/ExternalDataSources.class   1abfa76263e12d69d7d2e6070b17d784
```

---

## 目录说明

```
upgrade_o2oa.sh              ← 升级总编排（宿主侧，8 步）
upgrade_o2oa.bat             ← Windows 双击入口
UPGRADE.md                   ← 本文件
patch/
  o2oa_rebuild_patches.sh    ← 补丁流水线（容器内执行，6 阶段）
  ConfigPatch2.java          ← 补丁① javassist 源码
  ExternalDataSourcesPatch.java ← 补丁② javassist 源码
  ResourceFactoryAsmPatch.java  ← 补丁③ ASM 源码
  VerifyCls.java             ← 离线字节码校验器
  console.jar.patched        ← 补丁③ 产物（被 Dockerfile COPY）
  x_base_core_project.patched.jar ← 补丁①② 产物（被 Dockerfile COPY）
  *.orig*                    ← 原始 jar 备份（仅供对比/回滚）
  .patched_source_md5        ← 记录产物对应的源 jar 哈希（幂等判断用）
.upgrade-backup/             ← Dockerfile/compose 的升级前备份（可回滚）
.o2oa_upgrade_history        ← 每次升级的时间/版本/来源记录
.upgrade-work/               ← 临时工作目录（失败时保留作证据，成功后可删）
```

---

## 回滚

> **本项目不是 git 仓库**，所以没有 `git checkout` 可用。回滚靠脚本自动留的文件备份。

**脚本自动留的备份：**

```
.upgrade-backup/
  Dockerfile.upgraded_to_10.0.3.bak          ← 升级前的 Dockerfile
  docker-compose.yml.upgraded_to_10.0.3.bak  ← 升级前的 docker-compose.yml
patch/
  console.jar.orig                            ← 原始 console.jar（每次升级刷新）
  x_base_core_project.orig.jar                ← 原始 x_base_core_project.jar
```

**退回旧版本（两种方式）：**

```bash
# 方式一：把旧 zip 放回来，用参数指定，整体重跑一遍
bash upgrade_o2oa.sh o2server-10.0.2-linux-x64.zip
```

```bash
# 方式二：只还原配置（若只是想撤销版本号改动）
cp .upgrade-backup/Dockerfile.upgraded_to_10.0.3.bak Dockerfile
cp .upgrade-backup/docker-compose.yml.upgraded_to_10.0.3.bak docker-compose.yml
docker compose build && docker compose up -d
```

**只还原补丁产物：** 若 `.orig` 备份还在且版本对应，可以直接用它们重新构建；
或者直接重跑 `upgrade_o2oa.sh <对应版本的 zip>` 重新生成。

---

## 相关文档

- `patch/admin/README.md` —— 本地管理员账号 / token / 登录运维
- `docker-compose.yml` 注释 —— 离线隔离（挡外网）、端口、平台说明
- `Dockerfile` 注释 —— 三道补丁的原理详解
