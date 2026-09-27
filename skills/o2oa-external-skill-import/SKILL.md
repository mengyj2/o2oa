---
name: o2oa-external-skill-import
description: 把外部 skill 目录（LM Studio / Claude 风格：`SKILL.md` + `chapters/` + `kb/chunks/` 多层多文件）导入 O2OA 本地 AI 助手，让 `skills_list/skills_get/skills_run` 与 `kb_search/kb_read` 两条链路都能用上。当用户说"把这个 skill 导入 o2oa ai""LM Studio 的技能给 O2OA AI 用""外部技能怎么接进 AI 助手""技能导入了但 AI 看不到/搜不到""skills_list 里没有我放的技能"时调用。
agent_created: true
category: integration
---

# 外部 Skill 导入 O2OA AI 助手

## ★★ 一句话根因

O2OA 网关的自主技能是**单文件平铺**（`gateway/skills/*.md`），
外部 skill 是**多层目录**（靠模型自己 read 子文件）。
网关**没有 read_file 工具**，所以子目录里的东西一个都读不到。
正解是把"文件读取"转译成"知识库按 id 精读"——三通道并行。

## 1. 三条通道（缺一不算导入完成）

| 通道 | 落地位置 | 服务的工具 | 内容 |
|---|---|---|---|
| ① 自主技能 | **`gateway/skills/<name>.md`** | `skills_list` / `skills_get` / `skills_run` | 只放框架 + 章节→docId 索引表（≤15KB） |
| ② 知识库 | `data.db` 的 `docs` 表 | `kb_search` / `kb_read` / RAG 主链路 | 逐章 (摘要+原文) + 配套速查 |
| ③ 原始资产 | `docs/imported_skills/<name>/` | 人工核查 / 幂等再导入 | 完整目录副本（剔除 5MB `full_text.md`） |

只灌知识库不给技能 → 模型不知道有这能力；
只给技能不灌知识库 → `skills_run` 拿到框架但查不到数据。

## 2. ★★ 三个必踩的坑（先看再做）

### 坑① 技能目录是 `gateway/skills/`，不是仓库根
`o2_agent_gateway.py:27` 有 `BASE_DIR = Path(r"D:\O2OA\gateway")`，
line 28 `SKILLS_DIR = BASE_DIR / "skills"` → 真实目录 = **`D:\O2OA\gateway\skills\`**。
放成 `<仓库>/skills/` 或 `~/.workbuddy/skills/` 的表现是：
**文件明明在，`_list_skills()` 却返回 0 条**——极难一眼看出。
（`<仓库>/skills/` 那个目录是给 `sync_skills_to_repos.sh` 做仓间镜像用的，两回事。）

### 坑② 原始资产会被日常灌库脚本二次灌入 → 同源重复
`tools/ingest_o2oa_kb.py` 递归灌 `docs/`（category=`o2oa_ops`），
而通道③的资产就在 `docs/imported_skills/` 下 → 实测一次导入冒出 **67 篇**
`o2oa_ops::imported_skills__*` 重复项，内容完全相同，稀释检索。
✅ 已修：脚本内置 `SKIP_DIRS = {"imported_skills"}` 递归时跳过。
存量重复用 `POST /idx-gateway-doc/delete` 逐条清（实测 67/67 成功）。

### 坑③ 端到端验证时长连接被重置，别据此判失败
直连 `/ai-gateway-completion/generate` 发 mcp 对话，工具跑完（~25s）后客户端拿到
`[WinError 10054]`、`frames=1`、回答为空 —— **这是客户端侧被掐，不是网关故障**。
服务端日志照常打出 `tool kb_search ... -> 命中第4章 相关度0.705`。
✅ 取证办法：**别靠 socket 收完整流，读网关自己落库的结果**：
```python
sqlite3.connect('gateway/data.db').execute(
    "select v from kv where k like 'completion:%' order by rowid desc limit 3")
# 每个 v 是 JSON，.content 就是模型最终回答
```

## 3. 操作 SOP

```bash
# 幂等导入（重复跑 = 更新，不产生重复文档）
python tools/o2_import_external_skill.py --src "C:/Users/<user>/.lmstudio/skills/<skill>"

# 只看会做什么
python tools/o2_import_external_skill.py --src <...> --dry-run

# 只更新某一通道（如改了正文不动知识库）
python tools/o2_import_external_skill.py --src <...> --channels skill
```

## 4. 验证清单

```bash
# ① 技能被识别（必须用带 fastapi 的 venv，系统 python 会 ModuleNotFoundError: fastapi）
C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe -c \
  "import sys;sys.path.insert(0,'gateway');import o2_agent_gateway as g;print(g._list_skills())"

# ② 内置工具实测走 exec_builtin，不是 exec_tool
#    exec_tool(mcp_dict, args) 传字符串会 AttributeError: 'str' object has no attribute 'get'
g.exec_builtin("skills_run", {"name": "<技能名>"})
g.exec_builtin("kb_search", {"query": "主题词", "top_k": 3})
g.exec_builtin("kb_read", {"doc_id": "o2kb::ext::<name>::ch09-summary"})

# ③ 落库与向量化
sqlite3: select count(*) from docs where category like 'o2kb::ext::%'
         select count(*) from chunks where doc_id like 'o2kb::ext::%'
         -- 必须确认 embedding 非空的 chunk 数为 0 例外
```

**检索质量判据**：正样本（领域问题）余弦 0.60~0.76，负样本（O2OA 待办/会议室）0.34~0.36
→ 区分度够。若正负样本差距 <0.1，说明分块或内容有问题。

## 5. 关键接口事实

- 知识库写入走 HTTP：`POST http://127.0.0.1:18790/idx-gateway-doc/update`，
  Header `Authorization: Bearer <config.json 的 token>`。
  网关内部 `reindex_doc()` **先 DELETE 旧 chunks 再重切**，天然幂等。
  **不要直连 SQLite 写 docs**——不触发向量化，检索不到。
- chunk 参数：`config.json` 的 `chunk_size=500` / `chunk_overlap=60`。
  2.2MB 原文 → ~4564 chunks → embed(8089) 全量约 4-8 分钟，**必须放后台跑**。
- 中途若出现 `WinError 10054 / 10061`：是看门狗自愈重启了网关，**重跑脚本即可补洞**
  （幂等，已入库的会被覆盖更新，不会重复）。
- `permissionList: []` = 全员可见。
- 技能正文由 `_parse_skill()` 用正则 `^---\n(.*?)\n---\n(.*)$` 解析，
  只取 frontmatter 的 `name` / `description`，其余全进 body。

## 6. 内容取舍原则

- **技能正文 ≤15KB**：它每次 `skills_run` 都进上下文。
  原书的 5MB OCR 全文 + 33 章摘要一律走知识库，技能只放核心框架 + 索引表。
- **技能正文里必须有「章节 → docId」对照表**，否则模型拿不到精读入口。
- `kb_read` 单篇有截断（`web_fetch_max_chars` 默认 6000 字符），
  超长章节读不全 → 大章节用 `kb_search` 定位具体片段。

## 7. 相关文件

- 导入器：`tools/o2_import_external_skill.py`
- 方法论知识库：`docs/knowledge_base/external_skill_import_to_o2oa_ai.md`
- 网关技能实现：`gateway/o2_agent_gateway.py` line 27-28 (`BASE_DIR`/`SKILLS_DIR`)、
  line 1679-1730 (`_skill_path`/`_parse_skill`/`_list_skills`/`_run_skill`)、
  line 399 (`reindex_doc`)
