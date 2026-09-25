# O2OA 对话方法论与决策复盘（09-18 ~ 09-23）

> 本文是整段运维对话的「元认知」沉淀：把成功模式、失效模式、决策复盘与门户分流思路提炼为可复用的方法论，供后续分支与团队参照。

## 一、对话周期与主线

| 阶段 | 主题 | 关键产出 |
|---|---|---|
| 09-18 | xadmin 组织归属死锁 | 另建 `admin` 业务账号；`o2_fix_xadmin_org.py` |
| 09-18 | 合同/业务双门户安全拆除 | `o2oa-app-teardown` 技能、删除契约 |
| 09-20 | HR 全模块拆除 + 两日安装项目健康排查 | 基线 delta 法、健康四维 |
| 09-21 | SOP / 运维总纲 / 文档索引 | 单源权威手册 |
| 09-22 | 知识库灌入 + o2oa_api 态势 | KB 98 篇、OKR 缺口 |
| 09-23 | 看门狗持续化 + 门户分流重跑 + 代码级固化 | 本文档、watchdog |

## 二、三大铁律（必须用，不可省）

1. **xadmin 非业务账号 → 另建 `admin`**
   xadmin 是内存虚拟初始管理员，不在 `ORG_PERSON`、无 identity。任何赋予其业务身份的操作都触发硬校验死锁（建人员含 xadmin 被拒 + 建身份要真实 person，互为死锁）。正解永远是 `AskUserQuestion` 让用户选「另建业务账号」，再建 `admin`（`unique=admin` / `name=系统管理员` / 密码 `o2oaadmin2026`）挂顶层组织 + 3 系统角色。

2. **删模块必按「删除契约」顺序**
   流程实例 → 流程应用 → 自建表定义 → `DROP` 物理表 → 数据应用 → 门户子页 → 门户 → 菜单项。任何乱序都会被在流转实例 / 物理表残留拦截。

3. **`docker restart` 后必重跑 `o2oa_netlock.sh`**
   容器重启会丢 iptables，断云隔离失效。每次重启后第一件事是恢复网络锁。

## 三、成功模式（可复用）

- **先 MySQL 后 REST**：所有数据探测、基线核对走 MySQL 直查，规避 O2OA REST 层 404/500 的布尔不可信。
- **删除前拍基线、删后验证 delta**：每次删除捕获 portal/app/process/work/table/query/component/dyn 八类计数，删后对比，证明「只动目标、零误伤」。
- **AskUserQuestion 而非假设**：账号/权限/组织归属/空壳去留等灰色决策一律提问确认。
- **分批处理长流程**：15 个工作实例分步删、逐步验证，避免单一大操作的不可控风险。
- **临时文件统一 `C:\temp`、任务结束即删**：不散落个人目录（见用户级记忆约定）。
- **声明式 > 看门狗 > 裸进程**：能写进 compose（`restart: unless-stopped`）的持久化最稳；外挂看门狗只是把「进程活了」挪到另一进程，仍非系统一部分（见 mailservice 容器注释）。

## 四、失效模式（需规避）

- **盲信 REST 列表接口**：常返 404/500，尤其过滤/分页；以 MySQL 为准。
- **`completedTime` 误判**：以为 0 在流转实例，实际全是已完成 → 必须原样导出所有 xid 逐个确认状态。
- **`docker cp` + `$Layout` 变量**：Git Bash 路径与 Windows 环境变量展开冲突 → 改用显式 Windows 路径。
- **在流转实例未清就删应用**：`DELETE /jaxrs/application/{id}/false` 拦截 → 先 `DELETE /work/{id}` 清实例。
- **bat 脚本非 CRLF + UTF-8 no BOM**：Windows 下可能执行失败。
- **ARM64 + QEMU 跑 amd64 镜像**：`exec format error` 或长跑病态 → 关键服务显式 `platform: linux/arm64`，`docker restart` 即愈。

## 五、门户分流方案思路（admin vs 用户）

- 目标：管理员登录跳 `x_desktop/admin.html`（桌面工作台），普通用户见门户首页（1 层、无套娃/二级链接）。
- 实现：`x_desktop/index.html` 分流版（base64 内嵌于 `deploy/home_entry_local.ps1`），写入 `o2server/servers/webServer/x_desktop/` + `docker cp` 进容器。
- 持久化陷阱：`o2server/` 被 gitignore，分流版必须同步为仓库权威源 `deploy/host/x_desktop/index.html`，否则分支无法复现。容器未挂卷时 `restart` 重置 → 需固化进 Dockerfile 或挂卷。
- 验收：HTTP `localhost:9090/x_desktop/index.html` 返回 5532 字节分流版、F12 控制台 0 报错。

## 六、决策复盘要点

- **xadmin 死锁**：两条硬校验互咬，唯一出口是「不碰 xadmin、另建账号」。
- **三轮拆除零误伤**：靠「基线 delta + 物理表手工 DROP + 子页先于门户」三板斧。
- **空壳快速删除**：0 流程/0 表/0 实例的应用，直接删流程应用 + 数据应用即可，不必走全链路。
- **健康排查四维**：流程定义数 / 在流转实例 / 动态表真实数据 / 门户页数+内容。
