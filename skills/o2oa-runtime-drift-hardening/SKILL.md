---
name: o2oa-runtime-drift-hardening
description: 诊断并消除 O2OA（Docker 自托管）「改动只进了容器命名卷、仓库与镜像里没有」的临时补漏——审计 o2oa-webroot / o2oa-custom / o2oa-config 三卷与镜像层、git 仓库的差异，把运行时人工安装的 war 与 web 组件固化为**构建期 seed**（清单驱动）。当用户说"改进必须落到仓库代码""不能只进容器""需要持久化""杜绝临时补漏""重建镜像后功能丢了""改了文件/build 了却没生效""线上还是旧版""页面改了不生效""docker volume rm 之后服务全没了""换机器部署缺组件/war"，或要求核查「镜像层 vs 卷 vs 容器 vs 仓库」时调用。含：绕开 docker exec 失效的挂卷盘点法、**容器可写层遮蔽镜像层（docker diff 诊断 + --force-recreate 治本）**、zip↔卷 md5 来源闭合、seed 机制（custom.seed/webroot.seed）、.dockerignore 导致的 GB 级 build context 陷阱。
agent_created: true
category: troubleshooting
---

# O2OA 运行态漂移审计与构建期固化

> 实证环境：O2OA 10.0.2 社区版 / Docker（`o2oa-server`，QEMU amd64）+ MySQL 8 + DocumentServer。
> 首个案例：用户发现 OnlyOffice 修复「只进了容器」，追查后暴露**11 个 war + 19 个组件长期只在运行态卷里**。

## 0. 30 秒判定：是不是"只进容器"了

**决定性一条命令** —— 用 `docker run` 看**镜像层**（**不挂卷**）：

```bash
docker run --rm --entrypoint /bin/sh <image> -c \
  'echo "[webroot]"; ls -1 /opt/o2server/webroot/ 2>/dev/null | head -30;
   echo "[custom]";  ls -1 /opt/o2server/custom/  2>/dev/null | head -30;
   echo "[config]";  ls -1 /opt/o2server/config/  2>/dev/null | head -10;
   echo "[seed]";    ls -1 /opt/o2server/webroot.seed/ /opt/o2server/custom.seed/ 2>/dev/null'
```

拿到卷里的真实内容做对照：

```bash
docker run --rm --entrypoint /bin/sh -v o2oa_o2oa-webroot:/w <image> -c 'ls -1 /w'
docker run --rm --entrypoint /bin/sh -v o2oa_o2oa-custom:/c  <image> -c 'ls -1 /c'
```

**判定表**：

| 现象 | 结论 |
|---|---|
| 卷里有、镜像层没有、仓库也没有 | ❌ **纯运行时补漏** —— 清卷/换机即丢，必须固化 |
| 卷里有、镜像层没有、**仓库有源** | ⚠️ **半吊子** —— 有真源但**没有构建期生效路径**，重建镜像不带走 |
| 卷里有、镜像里也有 | ✅ 已固化 |

> ⚠️ **`docker exec` 在本机 QEMU 环境常失败**（`error starting setns process`）。
> 一律改用 **`docker run --rm --entrypoint /bin/sh -v <卷>:/x <image> -c '...'`** —— 挂载命名卷取数，
> 既能看卷、又能看镜像层（不挂卷即可），比 exec 更可靠。

## 1. 为什么会有这种漂移（O2OA 特有）

O2OA 的**服务（war）与自定义组件（`x_component_*`）有两条安装路径**：

1. **构建期**：`Dockerfile COPY` 进 `/opt/o2server/custom/` 与 `/opt/o2server/webroot/`；
2. **运行期**：登录 O2OA → **应用市场离线安装** `插件/*.zip`（setup.json + xapp 结构）→ 解压落进命名卷。

绝大多数自建实例都是靠 ② 装起来的（CRM/TeamWork/OnlyOffice/WPS/LibreOffice/OFD/审计…），
而 ② **在 git 里只留下插件包 zip，没有"构建期生效路径"** ⇒ `docker compose build` 出来的镜像天然残缺。

**别忘了这一条**：官方 `o2server-10.0.2-linux-x64.zip` **根本没有 `webroot/` 目录**，
所以 webroot 卷里的一切都是后加的，不存在"官方自带"的解释。

### 1.5 ★★★ 容器可写层遮蔽镜像层 —— 「`build` 了却没生效」的头号原因（2026-09-30 实证）

与 §0/§1 的"命名卷漂移"是**两个不同的遮蔽层**，别混：

| 遮蔽层 | 特征 | 触发 |
|---|---|---|
| **命名卷** | 卷挂载点整体盖住镜像目录（`webroot`/`custom`/`config`） | 设计如此 |
| **容器可写层** | **单个文件**在容器里被写过（历史 `docker cp`/`docker exec`）→ 该文件**永久遮蔽**镜像层同名文件 | 人工写入残留 |

**症状**（本案例）：改 `servers/webServer/x_desktop/admin.html` → `docker compose build o2oa` → 用户访问仍是**旧版**
（带早已废弃的 `oo_router_guard` 守卫、地址栏留 `?default=false`、"主页先冒出来点一下才稳定"）。
**为什么**：`docker compose build` **只更新镜像层**；容器没重建 ⇒ 可写层那份旧文件继续生效。
`docker compose up -d` 若配置未变，**不会**重建容器。

**决定性一条命令**：
```bash
docker diff <container>          # C=被改写(遮蔽)  A=新增  D=删除
# 本案例：
#   C .../servers/webServer/x_desktop/admin.html      ← 元凶
#   C .../servers/webServer/x_desktop/index_home.html
#   A .../servers/webServer/x_desktop/route_check.html（实验残留中转页）
#   D .../servers/webServer/x_component_Drive / _PdfViewer（webroot 卷里有，无害）
```
> 注意：`servers/webServer/**` **不在**任何命名卷里（六卷是 config/local/logs/webroot/custom/dynamic）
> ⇒ 它的遮蔽**只可能**来自容器可写层，与 §0 的卷漂移是两回事。

**三处 md5 对照（缺一不可）**：
```bash
md5sum deploy/host/x_desktop/admin.html                          # ① 本地/git 真源
docker run --rm --entrypoint sh <image> -c 'md5sum <path>'       # ② 镜像层（不挂卷）
docker exec <container> sh -c 'md5sum <path>'                    # ③ 容器内（含可写层）
```
①==② 而 ①≠③ ⇒ 命中本节。本案例 ①=②=`987dec015e`（13573B），③=`32fcfabaf502`（17827B，多 91 行旧守卫）。

**修复（两档）**：
- **① 立刻可用（治标）**：把镜像层版本覆盖回容器 + 重启
  ```bash
  docker run --rm --entrypoint sh <image> -c 'cat <path>' > /tmp/x
  docker cp /tmp/x <container>:<path>
  docker restart <container>          # 双保险：清 webServer 文件缓存
  ```
  ★ `docker cp` 覆盖已存在文件**即时生效**，不必重建镜像。
- **② 彻底归零（治本）**：`docker compose up -d --force-recreate o2oa`
  —— **命名卷 100% 保留**，只丢可写层。
  ★ 动手前先 `docker diff <container> | grep -v '/work/' | grep -v '/tmp/' | grep -v '/logs/'`，
  确认剩余改动都是"可再生"的（卷挂载点目录 / 字体缓存 / 运行时自动生成的根 `index.html` / `work/` 编译产物）。
  本案例非运行时改动仅 **60 项**，全部可再生 ⇒ 可安全重建。

**部署纪律（防复发）**：
> 改 `servers/webServer/**` 下**任何**静态文件后，必须 `docker compose up -d --force-recreate o2oa`
> （或 `docker rm -f o2oa-server && docker compose up -d o2oa`），**不能只 `build`**。
> 部署后跑一次体检：`python tools/o2_container_drift_check.py`
> （比对 9 个关键入口/品牌文件的【镜像层 vs 容器】md5，发现遮蔽即以退出码 1 报错）。

## 2. 来源闭合：用 md5 证明「zip 解包 == 卷内内容」

固化前**必须**证否"卷里那份被改过"。逐个 md5 比对：

```bash
# 卷内（一次挂载批量算）
docker run --rm --entrypoint /bin/sh -v o2oa_o2oa-custom:/c <image> -c 'md5sum /c/*.war'
```

```python
# 插件包内
import zipfile, glob, hashlib, os
for zp in sorted(glob.glob(r'D:/O2OA/插件/*.zip')):
    z = zipfile.ZipFile(zp)
    for n in z.namelist():
        if n.endswith('.war') and 'custom/' in n:
            print(hashlib.md5(z.read(n)).hexdigest(), os.path.basename(n), '<-', os.path.basename(zp))
```

逐条对齐即证明可 100% 复现，**无需把 war 二进制再入库一份**（zip 已在 git 中）。

组件层同理，且**必须逐文件比对**（本案例 2441 个文件里 15 个不同，集中在 2 个组件）：

```bash
# 把卷里的组件整体导出（tar 比逐个 docker cp 快得多）
docker run --rm --entrypoint /bin/sh -v o2oa_o2oa-webroot:/w <image> -c \
  'cd /w && tar cf - x_component_A x_component_B ...' > C:/temp/audit/live_plugins.tar
```

⚠️ **文件名编码坑**：插件包内个别中文文件名是 GBK 字节被当 latin1 存进 zip（`QQµê¬σ¢╛...`），
解出来与卷内（`QQ截图...`）对不上 —— 这属于**噪音**，别误判成"内容被改"。
真正要关注的是 **`.js` 的内容差异**。

## 3. 固化方案：seed 机制（清单驱动）

### 3.1 目录约定

```
custom.seed/   ← Σ 各插件 custom/*.war           → entrypoint cp -rn 进 /opt/o2server/custom
webroot.seed/  ← Σ 各插件 web/* + 覆盖层          → entrypoint cp -rn 进 /opt/o2server/webroot
```

**为什么必须用 seed（而非直接 COPY 到目标目录）**：命名卷会**遮蔽**镜像内同路径内容；
镜像更新对**已存在**的卷无效。seed 放在**非卷路径**，由 entrypoint 每次启动 `cp -rn` 补入。

`cp -rn`（no-clobber）⇒ **对现有生产卷零副作用**，只在缺失时补 —— 这是敢在生产上直接上这套机制的前提。

### 3.2 清单驱动（增删插件不改 Dockerfile）

`deploy/plugins.manifest`：

```
# 每行一个 `插件/` 下的 zip 文件名；# 为注释；空行忽略
ONLYOFFICE集成应用.zip
Office在线协作.zip
工作管理.zip
...
```

`Dockerfile`：

```dockerfile
COPY 插件/ /tmp/o2plugins/
COPY deploy/plugins.manifest /tmp/plugins.manifest
COPY deploy/runtime/webroot/ /tmp/o2wr/
RUN <<'PLUGEOF'
set -e
H=/opt/o2server
mkdir -p "$H/custom.seed" "$H/webroot.seed" /tmp/pe
miss=0
while IFS= read -r z; do
  case "$z" in ''|\#*) continue ;; esac
  if [ -f "/tmp/o2plugins/$z" ]; then
    unzip -qo "/tmp/o2plugins/$z" -d /tmp/pe 'custom/*' 'web/*' \
      -x '*/.DS_Store' '*.DS_Store' '*/__MACOSX/*' 2>/dev/null || true
  else
    echo "[plugins] 警告：插件包缺失 -> $z"; miss=$((miss+1))
  fi
done < /tmp/plugins.manifest
[ -d /tmp/pe/custom ] && cp -rf /tmp/pe/custom/. "$H/custom.seed/"
[ -d /tmp/pe/web ] && cp -rf /tmp/pe/web/. "$H/webroot.seed/"
cp -rf /tmp/o2wr/. "$H/webroot.seed/"          # 覆盖层最后叠加，可覆盖插件原文件
rm -rf /tmp/o2plugins /tmp/pe /tmp/o2wr /tmp/plugins.manifest
echo "[plugins] custom.seed=$(ls -1 "$H/custom.seed" | wc -l) 项  webroot.seed=$(ls -1 "$H/webroot.seed" | wc -l) 项  缺失插件包=$miss"
PLUGEOF
```

**要点**：
* `unzip` 的 `*` **跨目录**（`'web/*'` 能匹配 `web/x_component_X/$Main/y.js`）；
  某 pattern 不匹配时返回 11 但**仍解出匹配项** ⇒ 必须 `|| true`。
* heredoc 用 `<<'PLUGEOF'`（**引号**）避免 Docker 展开 `$z`；代价是 `${O2OA_HOME}` 也不展开 → 脚本内写 `H=/opt/o2server`。
* **覆盖层要放在最后** —— 它承载对插件原始文件的本地修改。

### 3.3 entrypoint 同步（幂等）

```sh
if [ -d "${O2OA_HOME}/webroot.seed" ]; then
  mkdir -p "${O2OA_HOME}/webroot"
  cp -rn "${O2OA_HOME}"/webroot.seed/. "${O2OA_HOME}/webroot/" 2>/dev/null || true
fi
if [ -d "${O2OA_HOME}/custom.seed" ]; then
  mkdir -p "${O2OA_HOME}/custom"
  cp -rn "${O2OA_HOME}"/custom.seed/. "${O2OA_HOME}/custom/" 2>/dev/null || true
fi
```

> **更新已有内容时的注意**：`cp -rn` 不覆盖 ⇒ 想让 seed 里**已改过**的文件生效，需 `docker volume rm` 该卷重铺。

## 4. ★★ 构建上下文陷阱（.dockerignore）

`.dockerignore` 常常只有几行（甚至没有），但仓库里躺着 `backups/`、`llama.cpp/`、`o2oa优化/` 这类 GB 级目录 ——
`docker build` 会把它们**全部传到 daemon**，把 5 分钟的事拖成 1 小时。

**先量一下**：

```bash
du -sh --exclude=o2server --exclude=o2oa-data --exclude=.git . | tail -1
du -sh */ | sort -h | tail -12
```

**补齐 `.dockerignore` 时必须核对所有共用一个 context 的 Dockerfile**：

```bash
grep -n -A4 "build:" docker-compose.yml      # 哪些服务是 context: .
grep -E "^COPY|^ADD" Dockerfile gateway/Dockerfile cron/Dockerfile
```

本案例踩到：`gateway/Dockerfile` 有 `COPY tools/ /app/tools/` ⇒ **`tools/` 不能排除**。
优化后 context 由 **5.0GB → ≈0.4GB**。

## 5. 调试残留识别与清理纪律

典型残留（探针/手工备份，均无源、无引用）：

| 形态 | 例子 | 判定 |
|---|---|---|
| 极小的探针文件 | `probe/readme.txt`(5B)、`probe_root.txt`(10B)、`zzprobe/index.html`(27B) | 测试"卷是否可写/可访问"留下的 |
| 探针组件 | `x_component_ProbeZ/` | 测试组件加载 |
| 孤立 war | `xci_new.war`（且在 **webroot** 下 —— O2OA 不从此处加载 war） | 用 md5 排除"它与某在用 war 相同"后即可判残留 |
| 手工备份 | `index.html.before_fix_20260928`、`index.html.container_orig_*` | 改动前的手工备份 |

**纪律**：判定残留 ≠ 可以删。生产卷属破坏性操作 —— **先 `tar` 备份 → 列出清单 → 用户确认 → 再删**。

## 6. 验证（可原样重跑）

```bash
# ① 镜像层 seed 就位
docker run --rm --entrypoint /bin/sh <image> -c \
  'ls -1 /opt/o2server/custom.seed | wc -l; ls -1 /opt/o2server/webroot.seed | wc -l'

# ② 全新空卷首启能否自动补齐（一次性容器，不碰生产卷）
docker run --rm -d --name o2verify \
  -v o2verify_wr:/opt/o2server/webroot -v o2verify_cu:/opt/o2server/custom \
  <image> sleep 120
sleep 25
docker run --rm --entrypoint /bin/sh -v o2verify_cu:/c <image> -c 'ls -1 /c/*.war | wc -l'
docker rm -f o2verify && docker volume rm o2verify_wr o2verify_cu
```

### 6.1 ★ 配置文件型漂移：自愈判据必须"全字段比对"（onlyofficeFileSettings 实证）

**症状**：改了 seed 里**某一个值**（如 `onlyofficeFileSettings.json` 的 `gobackUrl`），
重建镜像 + `--force-recreate` 容器，运行态**纹丝不动** —— "改了等于没改"。

**根因**：entrypoint selfheal 写成了**单字段守卫**：

```python
if WANT in cur:        # cur = 运行态 downLoadUrl
    sys.exit(0)        # 该字段一旦正确 → 整体跳过 ⇒ seed 的其它改动永不生效
```

**正确姿势**：读入 seed 成 `cfg`，按【种子为准】比对**关键字段集合**，任一漂移即整包回写：

```python
KEYS = ("docserviceConverter","docserviceTempstorage","docserviceApi",
        "docservicePreloader","downLoadUrl","secret","gobackUrl")
drift = [(k, cur.get(k), cfg.get(k)) for k in KEYS
         if (cur.get(k) or "") != (cfg.get(k) or "")]
if not drift: sys.exit(0)          # 幂等：全一致才跳过
for k, a, w in drift: print("漂移 %s: %r -> %r" % (k, a, w))
call("POST", SVC + "/save", cfg)   # 打印明细后再整包回写
```

**语义声明（必须写进脚本注释）**：策略从"尊重人工改动"变为
**"运行态向 git 真源收敛"** —— 这些字段的手工热改重启后会被 seed 拉回；
要长期生效就改 git 真源。

**验证（硬证据，别只看接口返回）**：故意把运行态改回旧值 → `--force-recreate` →
`docker logs` 必须打印 `漂移 <字段>: 运行态=… -> 种子=…` + `saveConfig -> 200`。

**通用性**：任何"seed + 启动时应用"的结构（配置文件 / 系统参数 / 字典）都适用；
`KEYS` 就是这份配置的**真源契约字段清单**。

## 7. 收尾清单

1. 新增/删除应用市场插件后，**必须同步更新 `deploy/plugins.manifest`** —— 否则新插件又变成"只在卷里"。
2. 对插件原文件的本地修改，一律写进**覆盖层目录**（本案例 `deploy/runtime/webroot/`），不要直接改卷。
3. `config` 卷多数文件由 O2OA 运行时生成（`general.json`/`cms.json`/`manifest.json`…），
   **没有 git 真源**，换机只能靠备份恢复（`tools/backup_o2oa_chain.bat`）—— 别指望 seed 机制。
   ★例外：**少数手写配置有真源**，如 `onlyofficeFileSettings.json` ← `deploy/host/onlyoffice/`，
   配套 entrypoint selfheal 全字段收敛（见 §6.1）—— 这类要按"有真源"对待。
4. 提交时**显式列文件**（禁 `git add -A`）；`backups/` 已在 `.gitignore`。
