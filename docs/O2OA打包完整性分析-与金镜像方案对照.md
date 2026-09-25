# O2OA 打包完整性分析 —— 这个 git 仓库能独立「完整打包」吗？

> 背景：用户在多台电脑、多个地点对 O2OA 做了优化/插件/脚本改良，资产分散。
> 桌面上《O2OA引擎终态打包方案-解答与先例.html》主张用 `docker commit`+`save` 把
> **运行终态**冻结成「金镜像（Golden Image）」来搬运，而不是回官方镜像、也不是翻脚本历史。
> 本文用本仓库（`D:\O2OA`，分支 `feature/o2oa-ai-stack`）的**实际状态**做实证对照。

---

## 一、直接结论

**git 仓库单独不能完整打包；但 git 仓库 + 它自己的 `backup_o2oa_state.sh` 产物 = 完整且可迁移的包。**

| 维度 | git 仓库是否覆盖 | 说明 |
|---|---|---|
| 引擎层加固（脚本沙箱/console.jar JNDI/断云封锁/AI war/网盘/开始菜单） | ✅ 已覆盖 | 全部在 Dockerfile 构建期烤入，patch jar 已入库 |
| 代码/构建输入/Dockerfile/compose | ✅ 已覆盖 | 5423 个被跟踪文件 |
| 配置**模板**（deploy/config/\*） | ✅ 已覆盖 | externalDataSources.json 等 30+ 个 |
| AI 栈 / 看门狗 / 工具脚本 / 文档 / 记忆 | ✅ 已覆盖 | gateway/ tools/ docs/ .workbuddy/ |
| 应用市场插件 zip（插件/\*） | ✅ 已覆盖 | 64 个，含 PDF预览/ONLYOFFICE/Office协作 等 |
| **业务数据（组织/门户/流程/字典/菜单，全部在 MySQL `X` 库）** | ❌ **完全不覆盖** | 0% 入库，只能靠备份 |
| **运行期部署的组件（webroot 命卷里的散件）** | ⚠️ 部分缺失 | 见下文 3 个孤儿组件 |
| **运行期配置真值**（DB 连接/管理员密/节点注册） | ⚠️ 仅模板 | 真值在命卷 + `.env`（刻意不入库） |
| **安装包本体**（o2server-10.0.2-linux-x64.zip，563MB） | ❌ 不入库 | `.gitignore` 排除，构建必备，须随包携带 |
| **密钥**（.env / mailservice/data/mail.json） | ❌ 刻意不入库 | 正确做法，但需人工交付 |

> 关键认知：**真正决定「这是哪一套实例」的，是 MySQL 里的业务数据 + 命卷里的运行态，
> 这两样 git 一行都没有。** 所以「git 能复现代码，但不能复现这套系统在跑什么」。

---

## 二、实证：运行期 webroot 命卷 vs git 侧 `deploy/runtime/webroot`

运行容器 `docker diff` 显示 `/opt/o2server/webroot` 是 **命名卷**（`o2oa_o2oa-webroot`）挂载，
且 `deploy/runtime/webroot` 里 18 个组件已入库。逐一对卷内文件后，卷里多出的、且**不在 git 任何位置**的有：

| 运行期组件 | git 内是否有源码/定义 | 结论 |
|---|---|---|
| `x_component_PdfViewer` | 有（`插件/PDF预览.zip`） | 可从插件 zip 重新部署，但**部署态未入库** |
| `x_component_ProbeZ` | **无** | 真孤儿，仅存在于运行卷 |
| `x_component_learn-online` | **无** | 真孤儿，仅存在于运行卷 |
| `cms_publish / probe / zzprobe / x_desktop / favicon / index.html` | 来自基础安装包 | 官方自带，构建即生成，非散落件 |

**含义**：`x_component_ProbeZ`、`x_component_learn-online` 是典型「在另一台机器上 docker cp / 应用市场装进去、
没回写 git」的散落件。一旦只靠 git + `docker build` 上新机，这俩会**静默消失**——
和 HTML 里警告的「挂载粒度错了会静默退回补丁前」是同一类陷阱，只是这里栽在 webroot 命卷的
「卷遮蔽镜像 COPY」上（命卷首次从镜像初始化后，Dockerfile 后续 COPY 进镜像的 webroot 内容不再生效）。

---

## 三、与 HTML「金镜像方案」的对照与修正

HTML 的核心论点我**基本认同**（抓终态而非翻脚本、金镜像是业界主流、不能回官方镜像），
但用本仓库实测后，有三点必须修正/补充：

### 1. 本仓库的「引擎」其实已在构建期入库，并非必须靠 `docker commit`
HTML 的前提是「引擎在运行期被改过，所以回官方镜像=全丢，必须 commit 运行容器」。
但本仓库里所有引擎层修改（脚本沙箱硬化、console.jar 的 JNDI、collect 断云封锁、
AI war reasoning 补丁、`x_component_Drive`、开始菜单 `applications.json`）**全部在 Dockerfile
构建期烤入，patch jar 已入库**。→ `docker build` 即可复现引擎，**git 比金镜像更可审计**，
金镜像那种 1.5GB 黑盒反而是劣势。这是比 HTML 假设更好的状态。

### 2. `docker commit` 同样抓不到命卷和 MySQL —— HTML 对这点「轻描淡写」了
HTML 自己也写了「commit 不含卷内容」，并加了 `09_mounts` 采集器（针对 bind 挂载）。
但**本部署的数据全在命名卷（config/local/webroot/custom/dynamic）+ MySQL**，
`commit` 一个都抓不到。也就是说：
- 纯 git → 缺业务数据 + 缺 2~3 个运行期组件
- 纯金镜像 → **同样**缺命卷 + 缺 MySQL

**两边都不完整，真正补全「缺失 80%」的是 `tools/backup_o2oa_state.sh`**
（它 dump MySQL `X` 库 + tar 五个命卷）。这份脚本是本仓库已有的，恰恰是 HTML 方案里
「数据分包」那一半的工程实现。

### 3. 挂载粒度陷阱对 git 路线同样致命
HTML 第 7 节把「挂载粒度」列为路径 C 的命门（整卷挂 `/o2server` 会盖掉镜像引擎）。
实测发现**更隐蔽的同构陷阱**：webroot 是命卷，挂载后**遮蔽**了 Dockerfile 烤进镜像的
`x_component_Drive`；后续加进卷里的组件（ProbeZ/learn-online）只活在卷中。
这条若不处理，git 路线也会「能启动、能登录，但少几个组件」。

---

## 四、多机分散的真正风险点

用户说「多个电脑、多个地方改的，插件脚本分散」。按本仓库实测，风险排序：

1. **运行期组件散落**（ProbeZ / learn-online 等只在某台机的卷里）→ 最高危，静默丢失。
2. **业务数据只在一台机的 MySQL**（git 完全没有）→ 必须靠备份，不能靠 git。
3. **配置真值分散**（哪台机改过 `externalDataSources.json` / `o2oa_ai.json` 没回写 git）→ 中危。
4. **安装包 zip 不入库**（563MB，断云后可能无法重新下载）→ 必须随包携带。

> HTML 提到的 `collect_state.ps1` / `docker diff` 思路是对的「发现差异」工具，
> 但它针对的是 `d:\o2oanew@192.168.1.5` **另一套实例**。要把多机成果合并进本仓库，
> 正确做法是：**对每一台源机跑 `docker diff` + 命卷比对，把差异回写 git**。
> 这一步我无法代劳（跨机），需你在各源机上执行后将产物交回。

---

## 五、推荐的最终打包公式（最小可信闭环）

```
完整可迁移包 = git 仓库（代码/构建/配置模板/AI栈/插件zip）
             + 随包携带 o2server-10.0.2-linux-x64.zip（563MB，构建必备）
             + backup_o2oa_state.sh 产物（MySQL X 库 + 5 个命卷）
             + 人工交付 .env / mailservice/data/mail.json（密钥，不入 git）
```

新机落地：`git clone` → 放好安装包 → `docker build` → 跑 `restore_o2oa_state.sh`。
这是「两包制」：骨架由 git 提供（可审计、可 diff），数据由备份提供（随业务增长）。
金镜像仅作为「reverse-engineer 不回 git 时的安全网」，不作为主交付。

---

## 六、立即可做的最小闭环（建议下一步）

1. **把 2 个真孤儿组件回写 git**：将运行卷里的 `x_component_ProbeZ`、
   `x_component_learn-online`（及部署态的 `x_component_PdfViewer`）拷入
   `deploy/runtime/webroot/`，并在 Dockerfile 增加 COPY，使 git 成为唯一真源、消除卷遮蔽陷阱。
2. **固化打包 SOP 文档**：把上面第五节的公式写成 `docs/打包与迁移SOP.md`。
3. **多机合并**：在 `192.168.1.5` 等源机执行 `docker diff` + 命卷比对，差异回写本仓库。
4. **审计 `o2oa高级应用开发/`（1044 个文件）**：疑似含构建产物/嵌套项目，确认哪些该入库。
