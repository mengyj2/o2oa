# 看门狗持续化与分支打包（代码级持久化方案）

> 用户明确要求：不要「等同持久化」（只写聊天纪要/散落文件），要用**看门狗持续化**，落到**代码级**，因为未来要把「目前运行的」打包成分支。

## 一、为什么需要看门狗

- 对话里的优化曾经只沉淀在记忆/技能/零散文档，断点后易丢失、不可复现。
- 「目前运行的实例」包含：自研组件（`deploy/runtime/webroot/x_component_*`）、门户分流版（`deploy/host/x_desktop/index.html`）、compose 拓扑（`docker-compose.yml` 的 mailservice）、配置（`gateway/config.json`）、文档源（`docs/`）。
- 这些资产必须**持续进入 git**，才能随时 `git branch` / 打包成可复现分支。

## 二、仓库边界（只纳管代码级）

`.gitignore` 已划清边界：
- **入库**：Dockerfile / compose / patch / deploy / tools / gateway(config) / docs / 记忆 / 自研组件
- **不入库**：`o2server/`、`o2oa-data/`、`llama.cpp/`（大体积运行时，可重新获取）；`gateway/data.db`（知识库运行时，由 `docs/` 源 + ingest 重建）；`.env` / `mailservice/data/`（真实凭据）；`.tmp-apply/`、`deploy/state/`（瞬态）；日志。

## 三、看门狗设计

- 脚本：`tools/watchdog_o2oa_git.py`（仅标准库，无外部依赖）。
- 机制：每 60s 轮询 `git status --porcelain`，仅对**白名单目录**（`docker-compose.yml`、`.env.example`、`deploy/`、`docs/`、`tools/`、`ai-stack-hardening/`、`.gitignore`、`gateway/config.json`、`mailservice/`、`patch/`）的变更做 `git add` + `git commit`，提交信息带时间戳与变更文件摘要。
- 安全：绝不碰 gitignore 覆盖的路径（凭据/大体积），避免误提交密钥。
- 常驻：脚本自循环；通过 `start_watchdog.bat` 启动，并注册 Windows 计划任务（登录/开机触发），使「运行实例持续持久化」成为系统一部分，而非依赖某次手动提交。

## 四、声明式持久化（与看门狗呼应）

- 能写进 compose 的，优先写 compose（如 `mailservice` 用 `restart: unless-stopped`，由 Docker 引擎保障存活，可复现、可审计、随分支走）。
- 看门狗补位：那些无法声明式、却仍在持续变化的代码级资产（组件 JS、文档、配置），由看门狗自动落账。
- 二者结合 = 「系统级声明 + 代码级持续账本」，分支里即可完整重建运行实例。

## 五、分支打包 SOP

1. 确保看门狗已将这些资产提交（无未提交白名单变更）。
2. `git checkout -b release/<版本>` 切出发布分支。
3. 新机器克隆后：`docker compose up -d` 拉起（含 mailservice）；`python tools/ingest_o2oa_kb.py` 重建知识库向量；如需门户分流，`deploy/home_entry_local.ps1` 写盘 + `docker cp` 进容器。
4. 凭据（`.env` / `mailservice/data/mail.json`）不随分支走，由目标环境单独注入。

## 六、与「对话方法论」的关系

看门狗解决「**持续**。对话方法论（见 `conversation_methodology_retrospective.md`）解决「**做对**」。二者叠加：做对的每一步都被看门狗持续固化进分支，形成可审计、可回滚、可迁移的工程资产。

## 七、状态守卫与漂移检测

除了常规看门狗（`tools/watchdog_o2oa_git.py`）之外，本项目新增了 **`tools/o2_state_guard.py`**——专注于「代码级 <-> 运行态」一致性的状态守卫。

- **核心能力**：
  - 对 `deploy/`（代码级资产）进行 SHA-256 树哈希扫描，生成状态清单 (`tools/state_manifest.json`)。
  - 与上一次清单对比，检测「新增/删除/修改」三类漂移，并给出受影响文件的精确名单。
  - 把结果持久化写入 `.workbuddy/memory/2026-XX-XX.md`，形成可追溯的优化痕迹。

- **工作模式**：
  - `python tools/o2_state_guard.py --once`：一次性巡检并报告漂移。
  - `python tools/o2_state_guard.py`：常驻轮询（默认 60s/轮），实时监控代码级变更。
  - `python tools/o2_state_guard.py --sync`：（慎用）根据漂移报告尝试把 `deploy/` 内文件回灌到运行态 webroot/config。

- **设计哲学**：
  - 先只读扫描、后温和修复。默认不任意篡改运行态，仅在用户明确 `--sync` 授权时进行有限的回灌。
  - 与看门狗的关系：看门狗负责「把变更记录在案」；状态守卫负责「检测变了什么、是否可控」。二者叠加 = 完整的代码级持久化闭环。

