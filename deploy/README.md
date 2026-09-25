# deploy/ —— O2OA 本地部署的声明式状态层

> 目的：让「跑着的这套系统」变成**可以 diff、可以 review、可以重放、可以打包成分支**的文本。

---

## 1. 为什么需要这一层

我们这几天对 O2OA 做的改动，有一大半只活在**运行态**里：

| 改动 | 原先活在哪 | 容器一重建 / 换台机器 |
|---|---|---|
| `captchaLogin` / `codeLogin` 登录策略 | 容器卷 `config/person.json` | 丢 |
| 自定义短信通道开关 | 容器卷 `config/custom_sms.json` | 丢 |
| 云平台连接开关 + 登录页标题 | 容器卷 `config/collect.json` | 丢 |
| 「系统管理」分组种子 | 容器卷 `config/components.json` | 丢 |
| 自研组件条目（SysSetting / 企业网盘 / CRM …） | MySQL `CPT_COMPONENT` 表 | 丢 |
| 门户「应用菜单」里的入口 | MySQL `GEN_DICT` / `GEN_DICT_ITEM` | 丢 |
| 自研组件源码 | 容器 webroot 命名卷 | 丢 |
| 宿主侧分流入口 `x_desktop/index.html` | 宿主文件 | 丢 |

**没有任何版本记录，也没有任何文档说清"我们到底改了什么"。**
这一层的职责就是把它们抽成文本，纳入 git。

---

## 2. 目录分工

```
deploy/
├── o2_deploy.py          # 反抽 / 重放 / 比对 CLI（本目录的入口）
├── state/                # ── 配置与数据层（反抽自容器 config 卷 + MySQL）
│   ├── o2oa-config/      #    /opt/o2server/config 下我们改动过的文件
│   │   ├── externalDataSources.json   # 外部 MySQL 连接（密码已占位符化）
│   │   ├── person.json                # 登录策略 captchaLogin / codeLogin
│   │   ├── collect.json               # 云平台连接开关 + 登录页标题
│   │   ├── custom_sms.json            # 自定义短信通道开关
│   │   ├── components.json            # 桌面「系统管理」分组种子
│   │   ├── o2oa_ai.json               # AI 助手接入
│   │   ├── portal.json / general.json / workTime.json / ternaryManagement.json
│   │   └── node_127.0.0.1.json        # 节点端口
│   ├── db/
│   │   └── cpt_component.json         # 自建组件条目 + 系统分组项（13 行）
│   └── dict/
│       └── appmenus.data.json         # 门户「应用菜单」字典（整对象）
├── runtime/              # ── 容器 webroot 反抽（自建桌面组件）
│   └── webroot/x_component_*          #   CRM / 企业网盘 / 系统设置 …
└── host/                 # ── 宿主侧文件（容器以 bind mount 引用）
    └── x_desktop/index.html           #   首页分流入口
```

> `state/` 管「配置与数据」，`runtime/` 管「容器 webroot」，`host/` 管「宿主文件」。
> 三者互补，互不重叠。

---

## 3. 三条命令

```bash
python deploy/o2_deploy.py snapshot     # 运行态 ──▶ deploy/  （反抽，改文件）
python deploy/o2_deploy.py verify       # 比对两侧漂移，只读，不改任何东西
python deploy/o2_deploy.py apply        # deploy/ ──▶ 运行态（幂等，末尾重启 O2OA）
python deploy/o2_deploy.py apply --no-restart
```

典型循环：

```
改完系统  ──▶  verify 看漂移  ──▶  snapshot 固化为文本  ──▶  git commit
换台机器  ──▶  git clone  ──▶  apply 重放  ──▶  verify 确认无漂移
```

---

## 4. 设计原则（踩过的坑都写在这）

### 4.1 幂等
`apply` 跑 N 次与跑 1 次等价：
- **容器 config**：整文件覆盖（先读目标侧现值 → 还原占位符 → 写回）
- **DB 行**：按 `xname` **先删后插**，只碰清单里列出的名字，**绝不整表重写**

### 4.2 敏感值不落库，但也不能写空（★）
快照时把凭据字段换成 `${O2OA_SECRET_XXX}` 占位符，`apply` 时：
1. 优先取同名环境变量；
2. **缺失则继承目标侧现值**；
3. 都拿不到才原样保留占位符（便于人工发现，不静默写坏）。

判定"是不是凭据"必须**宁漏勿误**——三条同时成立才算：

| 条件 | 反例（必须不误判） |
|---|---|
| 键名不以 `###` 开头 | `###password` 的值是中文说明，不是凭据 |
| 值是非空字符串且**不含中文** | `passwordPeriod=0`、`firstLoginModifyPwd=true` 是业务配置 |
| 键名归一化后命中凭据名单或以凭据词**结尾** | `passwordPeriod`、`tokenName`、`userPwdLogin` 不是凭据 |

> 误判的代价：`person.json` 里 `passwordPeriod` 一旦被占位符化，重放到新环境会写成
> 字面量 `"${...}"`，**直接把登录策略搞坏**。第一版就犯了这错（15 处误判），已修正。

### 4.3 `docker exec` 不可靠 → 文件走 `docker cp`，DB 走 `o2oa-mysql`
本机是 ARM64 + QEMU，对 `o2oa-server` 的 `docker exec` 常报
`OCI runtime exec failed: ... fork/exec /proc/self/fd/6`。
所以：**文件搬运一律 `docker cp`**，数据库操作一律走 `o2oa-mysql` 容器（它的 exec 是好的）。

### 4.4 `docker cp` 的目标路径必须是 Windows 形式
`C:/temp/x` ✅ ／ `/c/temp/x` ❌（后者会静默失败或报
`invalid output path: directory "d:\c\temp" does not exist`）。

---

## 5. 与其他层的关系

| 层 | 文件 | 职责 |
|---|---|---|
| 编排 | `docker-compose.yml` + `.env.example` | 容器拓扑、端口、卷、**服务持久化策略**（`restart: unless-stopped`） |
| 声明式状态 | `deploy/`（本目录） | 运行态 O2OA 改动的权威副本 |
| 组件补丁 | `patch/web/`、`patch/*.jar` | 官方 jar 的字节码补丁、组件源码的构建源 |
| 断网 | `o2oa_netlock.sh` | 内核 FORWARD 链封网（幂等，Docker 重启后需重跑） |
| AI 栈 | `gateway/`、`ai-stack-hardening/` | 本地推理与网关 |

---

## 6. 已知边界

- `token.json`、`keystore` 等**自动生成的密钥**不进快照（已列入 `CONFIG_SKIP`）。
- `deploy/runtime/webroot/` 若为全量反抽会包含官方组件，体积偏大；
  建议只保留**自建**组件目录（`x_component_CRM` / `x_component_Drive` / `x_component_SysSetting` …）。
- 改 `deploy/state/o2oa-config/*` 后必须 `apply`（末尾会自动重启 O2OA，冷启约数分钟）。
