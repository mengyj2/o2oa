# 声明式状态层：把"只活在运行态里的改动"抽成可 diff 的文本

> 适用：任何"容器 + 数据库 + 挂载卷"形态的私有化部署（本项目为 O2OA 10.0.2）。
> 目标：让这套跑着的系统**可以 diff、可以 review、可以重放、可以打包成分支**。

## 1. 问题：改动散落在三个地方，且没有任何版本记录

| 改动类型 | 原先活在哪 | 容器重建 / 换机器 |
|---|---|---|
| 配置文件（登录策略、通道开关、连接开关） | 容器挂载卷 `config/*.json` | 丢 |
| 业务数据（组件条目、菜单字典） | MySQL 表 | 丢 |
| 自研前端产物（组件目录） | 容器 webroot 命名卷 | 丢 |
| 宿主侧补充文件（首页分流入口等） | 宿主目录 | 可能丢 |

而且**没有人能说清"我们到底改了什么"**。

## 2. 解法：三层 + 三条命令

```
snapshot   运行态 ──反抽──▶ deploy/state/    （进版本库，可 diff / 可 review）
verify     deploy/state/ ⟷ 运行态            （只读比对，列出漂移 drift）
apply      deploy/state/ ──重放──▶ 运行态    （幂等，末尾重启服务）
```

目录分工：

```
deploy/
├── state/o2oa-config/     # 容器挂载卷里的配置文件
├── state/db/              # MySQL 业务表行（声明式 JSON）
├── state/dict/            # 门户数据字典（整对象）
├── runtime/webroot/       # 容器 webroot 里的自研前端产物
└── host/                  # 宿主侧被 bind mount 的文件
```

## 3. 六条设计原则

### 3.1 幂等
`apply` 跑 N 次 = 跑 1 次。
- 文件：整文件覆盖；
- 表行：按业务主键**先删后插**，且**只碰清单里列出的名字，绝不整表重写**。

### 3.2 敏感值占位符化 —— 但绝不能写空
快照时把凭据换成 `${VAR}`；重放时：① 环境变量 → ② **继承目标侧现值** → ③ 都拿不到才保留占位符（便于人工发现）。

### 3.3 ★ 脱敏判定"宁漏勿误"
第一版用正则 `(password|token|secret)` 匹配键名，结果把
`passwordPeriod`、`firstLoginModifyPwd`、`tokenName`、`appTokenExpiredMinutes`
等**业务配置**全误判成密钥（`person.json` 一处误判 15 个字段）。

代价：重放到新环境会写成字面量 `"${...}"`，**直接把登录策略搞坏**。

正确规则（三条同时成立才算凭据）：

1. 键名不以 `###` 开头 —— O2OA 用 `###<key>` 存**中文说明**，值是文案不是凭据；
2. 值是**非空字符串且不含中文** —— 排除说明文本、布尔、数字配置项；
3. 键名归一化后命中凭据名单，或以凭据词**结尾**（`xxxToken`/`xxxPassword`）。

### 3.4 比对前必须先还原占位符
快照里是 `${VAR}`，运行态是真实值 —— 直接比会**永远报差异**。
`verify` 必须 `unsanitize(snapshot, live)` 之后再比。

### 3.5 `docker exec` 不可靠时，换通道
本机 ARM64 + QEMU 下对主容器的 `exec` 常报
`OCI runtime exec failed: ... fork/exec /proc/self/fd/6`。
⇒ **文件搬运一律 `docker cp`**；数据库操作走**独立的 mysql 容器**（它的 exec 是好的）。

### 3.6 工具本身的兼容性
- `docker cp` 目标路径必须是 **Windows 形式**：`C:/temp/x` ✅ ／ `/c/temp/x` ❌
- 比对函数要兼容 **dict / list / 标量**（配置文件顶层可能是数组，`set()` 会炸）
- 涉及 shell 的 DB 批量语句，**写文件 + stdin 喂给 mysql**，别拼超长 `-e` 参数

## 4. 与 git 的关系

`deploy/` 是**唯一**需要入库的"运行态"表达。配合一份严格的 `.gitignore`：

- 不入库：安装包、推理框架二进制、解压出的服务器目录、日志、pid、`*-wal`、`__pycache__`、一次性诊断输出；
- 入库：`Dockerfile` / `compose` / `deploy/` / `patch/` / `tools/` / `gateway/` / `docs/` / 记忆。

于是"打包成分支"= `git branch` + 已有的这套文件结构，**换台机器 `clone` + `apply` 即可复现**。

## 5. 典型循环

```
改完系统  ──▶ verify（看漂移） ──▶ snapshot（固化为文本） ──▶ git commit
换台机器  ──▶ git clone ──▶ apply（重放） ──▶ verify（确认无漂移）
评估改动  ──▶ git diff deploy/   ← 一眼看清"我们到底改了什么"
```

## 6. 一句话总结

> **能 diff 的才算资产，只活在容器里的只能算运气。**
