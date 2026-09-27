# 技能目录索引（本机 WorkBuddy user-level skills）

> 位置：`~/.workbuddy/skills/`（= `C:\Users\meng_\.workbuddy\skills\`），跨项目可用。
> 本文件**不是 skill**（根目录 README，不参与加载），只作导航与边界说明。
> 最后整理：2026-09-27（含 Clawith 相关技能下线，见 §7；新增 `o2oa-mcp-tool-hardening`）。
> **镜像**：本目录已同步进两个 O2OA 仓（`D:\O2OA\skills\`、`D:\o2oaccia\skills\`），
> 同步用 `D:\O2OA\tools\sync_skills_to_repos.sh`（随每日双仓同步自动跑）。

## 0. 目录纪律（新增/导入 skill 时必须遵守）

1. **一层目录 + `SKILL.md` 直放**。禁止 `xxx/xxx/SKILL.md` 这种导入多套的一层（本目录 2026-09-27 修过一例）。
2. frontmatter **四个字段必须齐**：`name` / `description` / `agent_created` / `category`。
   - 缺 `agent_created: true` → 后续无法被自动维护（SkillManage 只改自己建的）。
   - `description` 是**每次会话都注入**的，越短越好；**保留触发词，砍掉叙述**（建议 ≤ 300 字符）。
3. 导入的 zip / 临时包统一丢 `_archive/`（下划线开头，不会被当 skill 扫描）。
4. **一 skill 一职责**；职责相邻的用「相关 skill」小节互指，而不是互相抄内容。

## 1. operations —— 会改变 O2OA 状态的操作

| skill | 一句话定位 | 何时**不要**用它 |
|---|---|---|
| `o2oa-ops` | ★ **O2OA 写入总入口**：克隆应用、批量装插件、删模块、注册开始菜单、改门户菜单/字典、改网盘指向、会议楼宇房间播种与会议链路重放 | 只读盘点 → `o2oa-app-io`；拆一整套应用 → `o2oa-app-teardown` |
| `o2oa-app-io` | 只读导出：读出设计定义 → 打 `.xapp` 导入包 → 灌入另一套 O2OA；跨实例逐层对齐审计 | 要**改**线上 → `o2oa-ops` |
| `o2oa-app-teardown` | 安全彻底删**一整套**应用（流程实例→流程应用→自建表→动态表→数据应用→门户子页→门户→菜单项） | 删单个对象 → `o2oa-ops` |
| `o2oa-local-admin-account` | 登录/建号/批量改手机邮箱/批量重置密码/补组织归属与角色/免登录调管理员接口 | 权限边界实测见 `o2oa-ops` §1.7 |
| `o2oa-portal-brand-guard` | 门户首页功能失效（点了没反应）修复 + 入口文件三件套（index/index_home/admin）+ 品牌残留治理 | 门户**页格式/渲染**问题 → `o2oa-portal-page-format` |
| `o2oa-reveal-fix` | 首页「公文管理 Reveal 对象已存在」+ 登录 `randomWithWeight count=0` 双根因闭环 | — |
| `o2oa-market-offline-install` | 断云环境离线安装应用市场 zip 包（setup.json+xapp），含冲突判断与卸载限制 | 非市场包（自研 xapp）→ `o2oa-app-io` |

## 2. diagnostics —— 排障 / 根因定位（不改状态）

| skill | 一句话定位 |
|---|---|
| `o2oa-force-external-mysql` | 配了 externalDataSources.json 却仍用 H2 的根因与升级后补丁重放 |
| `o2oa-log-triage-health` | 问题日志 CTE 三表列名、一次性爆发 vs 持续性故障判定、审计 `CUSTOM_AUDIT_LOG` 为空的两级根因 |
| `o2oa-component-ak-fix` | 组件内硬编码第三方 AK 过期导致的开应用弹窗/白屏（服务端零报错） |
| `o2oa-ai-stack-no-popup-hardening` | AI 栈看门狗反复弹控制台窗 + 9090 看似卡死；含持续化与知识库落库 |
| `o2oa-mcp-tool-hardening` | ★ 9 个 MCP 工具（会议/日程/HR/薪资/邮件/待办/流程）报 500、静默不落库、卡片回吐 `${xxx}`、查询越权返回全量；核心是 invoke `bodyMap` 未替换占位符 |
| `o2oa-local-ai-assistant`（兼） | 推理模型「界面空白」= `reasoning_content` 陷阱（见 §4） |

## 3. development —— 写组件 / 门户 / 表单 / 服务

| skill | 一句话定位 |
|---|---|
| `o2oa-custom-desktop-component` | 从零自研 `x_component_XXX` 并挂到菜单真正打开；排查「点开一片空白」 |
| `o2oa-portal-page-format` | `page.data` 正确格式、自定义 HTML 真渲染、门户读**自建表真实数据**、多栏 Tab 与跳转 |
| `o2oa-local-sms-mail-service` | 纯 Python 平替 `x_sms_assemble_control`，让短信验证码/忘记密码在本地可用 |

## 4. integration —— 对接外部服务 / 本地 AI 栈

> ★ 这 4 个都以「本地推理」为中心，**按问题定位选**：

| skill | 一句话定位 | 边界 |
|---|---|---|
| `o2oa-local-ai-assistant` | 让 O2OA AI 助手接本机/局域网 OpenAI 兼容端点；离线网关（对话/RAG/MCP）；`reasoning_content` 空白陷阱 | **O2OA 侧**集成与协议适配 |
| `o2oa-bionic-agent-bridge` | Bionic CLI/runtime/工具调用接入网关；治「模型拒绝调工具」「调了没数据」「web_search 超时」 | **Bionic 侧**能力桥接 |
| `o2oa-local-ocr-service` | 离线 OCR（RapidOCR ONNX，纯 CPU）：扫描件/表格/PDF + 网关附件链路 | 附件进不了 AI 就找它 |
| `lmstudio-backend-install` | `lms` CLI 装/选/验 LM Studio 推理后端（ROCm/CUDA/Vulkan） | **后端本身**装不上/跑不动 |

## 5. security —— 隔离 / 加固

| skill | 一句话定位 |
|---|---|
| `o2oa-cloud-cutoff` | 切断 O2OA 与官方云的一切联系；断云影响面、License 取证、市场临时开闸 |
| `docker-container-egress-lockdown` | 让容器彻底不能出网（含 IP 直连），保留宿主端口与容器间通信 |

## 6. 已知重叠（保留但需互指，尚未合并）

| 重叠点 | 涉及 skill | 现状 |
|---|---|---|
| 删应用 | `o2oa-ops` §1.2 ↔ `o2oa-app-teardown` | `o2oa-ops` 只列脚本入口并指向 teardown；实际流程以 teardown 为准 |
| 装应用包 | `o2oa-ops` §1.1 ↔ `o2oa-market-offline-install` | 批量脚本在 ops；市场包结构/冲突判断在 market |
| 门户 | `o2oa-portal-brand-guard` / `o2oa-portal-page-format` / `o2oa-custom-desktop-component` | 分别为「入口与品牌」「页格式与数据」「组件开发」 |
| 本地 AI | 见 §4 表 | 已按"问题定位"分工 |

> 维护建议：新写 skill 前先查本索引；能扩写已有 skill 就不要新建。

## 7. 已下线（2026-09-27）

本机技能集**只服务 O2OA 项目**，与 Clawith 无关的已全部移入 `_archive/clawith/`
（保留可恢复，不再被加载）：`clawith-backend-ops`、`clawith-memory-mcp`、
`clawith-research-slow-diag` + `clawith-memory-mcp.zip`。
若将来重新接 Clawith，从 `_archive/` 移回根目录即可。
