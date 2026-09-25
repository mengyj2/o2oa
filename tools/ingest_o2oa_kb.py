#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 本地知识库入库脚本（多层记忆体系 · 向量库填充器）

功能：
  1. 把 O2OA 各类资料灌入网关内置向量库（SQLite data.db），自动分块 + qwen3-embed 向量化。
  2. 走网关 HTTP 接口 /idx-gateway-doc/update（在服务进程内 reindex_doc，避免直接锁 DB）。
  3. 按 category 分层（多层记忆体系）：
       o2oa_manual      —— O2OA 技术/操作说明书（o2oa高级应用开发/docs/*.md）
       o2oa_api         —— O2OA 自身 REST API 目录（describe/describe.json 按模块展开）
       o2oa_ops         —— 我们自己的运维/方案文档（docs/*.md）
       o2oa_version     —— 版本/部署事实纪要
       ops_experience   —— 操作经验/问题解决（脚本内置 seed + 可续加）
  4. --verify 模式：用真实 embed 端点做余弦检索，验证分层 RAG 命中。

用法：
  python tools/ingest_o2oa_kb.py            # 全量入库（幂等，重复跑=更新）
  python tools/ingest_o2oa_kb.py --verify   # 仅校验检索
  python tools/ingest_o2oa_kb.py --cat o2oa_manual   # 只灌某一层
依赖：仅标准库（urllib/json/sqlite3），无需额外安装。
"""
import json
import os
import sqlite3
import sys
import urllib.request

_THIS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(_THIS)  # 仓库根 = tools/ 的父目录（不再硬编码 D:\O2OA，便于分支移植）
GATEWAY = "http://127.0.0.1:18790"
CFG_PATH = os.path.join(BASE, "gateway", "config.json")

# ---- 读取运行态 token / embed 端点 ----
def load_cfg():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

CFG = load_cfg()
TOKEN = CFG.get("token", "local-o2-agent-2026")
EMBED_BASE = CFG.get("embed_base", "http://127.0.0.1:8089")
EMBED_MODEL = (CFG.get("embed_models") or ["qwen3-embed"])[0]
DB_PATH = os.path.join(BASE, "gateway", "data.db")

stats = {"docs": 0, "errors": 0}


def post_doc(doc_id, title, category, content, permission=None):
    payload = {
        "id": doc_id,
        "title": title,
        "category": category,
        "content": content,
        "creatorPerson": "知识库构建器",
        "questionEnable": True,
        "permissionList": permission or [],
    }
    req = urllib.request.Request(
        GATEWAY + "/idx-gateway-doc/update",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read().decode("utf-8", "replace")
        stats["docs"] += 1
        return body
    except Exception as e:
        stats["errors"] += 1
        return f"ERR {e}"


def ingest_markdown_dir(folder, category, only_cat=None, recursive=True, prefix=""):
    """把目录下的 markdown 灌进知识库。

    ★ 2026-09-23 修正：原实现只 os.listdir 一层，导致 docs/knowledge_base/ 下的
      经验条目（踩坑总结/方法论）从未入库 —— 而那些恰恰是最该被检索到的内容。
      改为递归，并用「相对路径」做 slug（knowledge_base__xxx），避免不同子目录同名互相覆盖。
    """
    if only_cat and category != only_cat:
        return
    if not os.path.isdir(folder):
        print(f"  [skip] 目录不存在: {folder}")
        return
    for fn in sorted(os.listdir(folder)):
        path = os.path.join(folder, fn)
        if os.path.isdir(path):
            if recursive:
                ingest_markdown_dir(path, category, only_cat, recursive, prefix + fn + "/")
            continue
        if not fn.lower().endswith(".md"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"  [skip] 读失败 {fn}: {e}")
            continue
        if len(text.strip()) < 50:
            continue
        slug = (prefix + os.path.splitext(fn)[0]).replace("/", "__")
        doc_id = f"o2kb::{category}::{slug}"
        title = f"{slug}"
        r = post_doc(doc_id, title, category, text)
        print(f"  [ok] {category:<14} {prefix+fn:<40} -> {doc_id}  ({len(text)}字)")


def ingest_describe(path, only_cat=None):
    category = "o2oa_api"
    if only_cat and category != only_cat:
        return
    if not os.path.isfile(path):
        print(f"  [skip] 文件不存在: {path}")
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [skip] 解析失败 {path}: {e}")
        return
    jaxrs = data.get("jaxrs") if isinstance(data, dict) else None
    if not jaxrs:
        # 退化：整文件作为一个 doc
        post_doc("o2kb::o2oa_api::describe_all", "O2OA 接口描述(describe.json)", category, json.dumps(data, ensure_ascii=False))
        print("  [ok] o2oa_api describe.json(整文件)")
        return
    n = 0
    for mod in jaxrs:
        name = mod.get("name") or "unknown"
        cls = mod.get("className") or ""
        desc = mod.get("description") or ""
        methods = mod.get("methods") or []
        lines = [f"# O2OA 接口模块：{name}", f"类：{cls}", f"说明：{desc}", "", "## 方法"]
        for m in methods:
            mtype = m.get("type") or "?"
            mpath = m.get("path") or ""
            mdesc = m.get("description") or ""
            mname = m.get("name") or ""
            lines.append(f"- `{mtype} {mpath}` —— {mname}：{mdesc}")
        content = "\n".join(lines)
        if len(content.strip()) < 20:
            continue
        doc_id = f"o2kb::{category}::{name}"
        post_doc(doc_id, f"O2OA API · {name}", category, content)
        n += 1
    print(f"  [ok] o2oa_api 展开 {n} 个接口模块")


def seed_ops_experience(only_cat=None):
    """从长期运维会话中沉淀的高价值经验（多层记忆 L1）。可在此续加。"""
    if only_cat and only_cat != "ops_experience":
        return
    items = [
        ("cookie污染_服务号串用户",
         "【现象】服务号(Gw#svc2026)调用 O2OA REST 时，偶发被当成『上一个用户』，返回 500 权限不足。\n"
         "【根因】httpx 全局 _client 的 cookie jar 残留了 O2OA 回写的 Set-Cookie: x-token（上一用户的会话），"
         "而 O2OA 的 Cookie 优先级高于 Header 的 x-token，导致身份错乱。\n"
         "【修复】所有 O2OA REST 调用走专用 _o2_http 客户端，且每请求前 `_o2_http.cookies.clear()`，"
         "严格以 Header 的 x-token 鉴权。\n【加固】新增工具一律复用 _o2_http，不得用全局 _client 打 O2OA。"),
        ("REST路径_以服务描述为准",
         "【规则】O2OA 业务模块路径必须以 /o2_core/o2/xAction/services/<模块>.json 服务描述文件为准；"
         "业务模块返回 404 大多数是路径写错，而非权限问题。\n"
         "【常用路径】待办 GET /x_processplatform_assemble_surface/jaxrs/task/list/my/paging/{p}/size/{s}；"
         "人员 PUT /x_organization_assemble_control/jaxrs/person/list/like {\"key\":kw}；"
         "角色判定 GET /x_organization_assemble_authentication/jaxrs/authentication（x-token 换 roleList）；"
         "服务号真实 person=Gw#svc2026（15min TTL），写数据行需 xadmin 把它加进应用 controllerList。"),
        ("动态表_走designer不动surface",
         "【规则】动态表建表必须走 designer 模块，surface 滞后会报 ClassNotFoundException。\n"
         "【流程】建表 POST /x_query_assemble_designer/jaxrs/table（draftData 必须是字符串 "
         "{\"fieldList\":[{name,type,description}]}）→ table/{id}/status/build → table/query/{appId}/build → "
         "table/reload/dynamic；行读写 POST/PUT table/{flag}/row[/{id}]、GET table/list/{flag}/row/(0)/next/{n}。"),
        ("断云_六层网络防护",
         "【结论】本地 O2OA 已断云（collect/apppack/app.o2oa.net 全不可达）。\n"
         "【做法】compose 用 dns:[127.0.0.1] + extra_hosts 指回本机 + 普通 bridge 网络（绝不能 internal:true，"
         "否则宿主端口 502）；Docker 重启会丢 iptables，须重跑 o2oa_netlock.sh 锁容器出站。\n"
         "【影响】应用市场/打包离线装（POST .../market/install/offline，字段必须含 file）；联网工具 web_* 默认关闭。"),
        ("外部MySQL_三道门控",
         "【问题】配了 externalDataSources.json 仍静默回退 H2。\n"
         "【修复】三道门控补丁源 patch/*.java + Dockerfile COPY 固化 + upgrade_o2oa.sh 可重放"
         "（详见 UPGRADE.md）。DB 前缀约定 PP_C_*/PP_E_*/PTL_*/QRY_*。容器时间 UTC，比主机 +8h。"),
        ("容器QEMU病态_重启即愈",
         "【现象】O2OA 容器长跑后 Jersey SSE 读空、exec setns 失败等诡异错。\n"
         "【结论】QEMU(ARM64 跑 amd64 镜像) 长跑病态，docker restart 即愈。\n"
         "【规避】尽量不 exec 进容器：用 docker cp tar、HTTP 直拉 war 内资源、临时容器跑 Java。"),
        ("AI网关栈_18790唯一入口",
         "【拓扑】chat 8088 / embed 8089 / rerank 8092 / OCR 8091；统一由 18790 网关调度。\n"
         "【模型】chat=qwen3.8-27b，embed=qwen3-embed@8089，mcp_max_turns=20。rerank 8092 默认关闭"
         "（需 llama-server 加 --reranking 才启用；当前用向量+rerank 融合回退纯向量）。\n"
         "【诊断】AI 助手报 connect timed out = 网关没在跑（栈活着时容器→192.168.1.5:18790 实测 200）。"),
        ("聊天历史_协议层落账",
         "【机制】前端会话/消息全走网关 /ai-gateway-clue|completion 协议层（x_ai 模块代理转发）。\n"
         "generate 落 clue+completion（o2_user_info(token) 取 DN，clue_touch/completion_add），list 按 DN 前段过滤；"
         "模型固定 config.json 的 chat_model，前端选型被忽略。war 接口逆向：zipfile+class 常量池 UTF8 提取即可。"),
        ("设计态_四层安全闸",
         "【能力】AI 可经 design_op 创建/修改 门户页/动态表/数据应用/门户，但需四层闸：①角色闸门(analyst/manager)"
         "②草稿不落地(confirm=false 只出提案)③过程授权(人类确认即授权，无静态 deny-all 白名单)"
         "④落地前快照+审计+可回滚(design_rollback 账本)。系统级应用命中 design_denylist 直接拒绝。"),
        ("联网默认关断_内网工具16",
         "【定位】系统定位是内网数据闭环，web_search/web_fetch 默认不在任何 persona 白名单。\n"
         "【内网工具】围绕 O2OA 自建 16 个内网工具 + task_plan/run_step/rollback 多步编排（账本 kv 可回滚）。"
         "kb_search 与 RAG 主链路同权（按前端 permissionList 过滤）。"),
        ("O2OA登录态权限闭环",
         "【机制】前端 wi.token 转发到网关，全程以 x-token 调 O2OA REST，服务端按 token 权限强制过滤；"
         "_o2_call 在 token 非空时直接以本人身份调用、跳过 switchuser（DN 非 switchuser 凭据）。"
         "无 token/未命中角色=用户向导角色。"),
        ("网关RAG_向量库结构",
         "【存储】data.db 中 docs(id,title,category,content,permission,meta) + chunks(doc_id,seq,text,embedding BLOB)。"
         "category 即多层记忆命名空间；permission=[] 表示对所有人可见。rag_retrieve 采用 向量分(0.6)+rerank分(0.4)"
         "归一化融合（rerank 不可用时回退纯向量 top_k）。"),
    ]
    for slug, content in items:
        doc_id = f"o2kb::ops_experience::{slug}"
        post_doc(doc_id, f"[经验] {slug}", "ops_experience", content)
    print(f"  [ok] ops_experience 沉淀 {len(items)} 条")


def ingest_api_json(path, only_cat=None):
    """api.json：jaxrs[].methods[].{name,uri,method}，无 description，结构更精简。"""
    category = "o2oa_api"
    if only_cat and category != only_cat:
        return
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [skip] api.json 解析失败: {e}")
        return
    jaxrs = data.get("jaxrs") or []
    n = 0
    for mod in jaxrs:
        name = mod.get("name") or "unknown"
        methods = mod.get("methods") or []
        lines = [f"# O2OA 接口模块（api.json）：{name}", "", "## 方法"]
        for m in methods:
            mtype = m.get("method") or "?"
            muri = m.get("uri") or ""
            mname = m.get("name") or ""
            lines.append(f"- `{mtype} {muri}` —— {mname}")
        content = "\n".join(lines)
        if len(content.strip()) < 20:
            continue
        post_doc(f"o2kb::{category}::{name}::api", f"O2OA API · {name}", category, content)
        n += 1
    if n:
        print(f"  [ok] o2oa_api(api.json) 展开 {n} 个接口模块")


def ingest_version_doc(only_cat=None):
    category = "o2oa_version"
    if only_cat and category != only_cat:
        return
    content = (
        "# O2OA 本地部署版本与改进纪要\n\n"
        "## 当前版本\n"
        "- O2OA 社区版 10.0.2（Docker 自托管，docker-compose 含 mysql + o2oa-server）。\n"
        "- 已断云：与官方云 collect.o2oa.net / apppack.o2oa.net / app.o2oa.net 一切联系已切断，"
        "非 SaaS、不需要 License、应用市场改为离线安装。\n\n"
        "## 本机关键改造（相对官方社区版）\n"
        "- 强制外部 MySQL：三道门控补丁(patch/*.java) + Dockerfile COPY 固化 + upgrade_o2oa.sh 可重放。\n"
        "- 网络六层隔离：dns 指回本机 + extra_hosts + 普通 bridge（非 internal）+ o2oa_netlock.sh 锁出站。\n"
        "- AI 网关栈：18790 统一入口，chat=qwen3.8-27b@8088、embed=qwen3-embed@8089、OCR@8091；"
        "rag 向量库 data.db。\n"
        "- 设计态能力：design_op/design_rollback 四层安全闸（角色/草稿不落地/过程授权/快照回滚）。\n"
        "- 多层记忆体系：docs.category 命名空间（o2oa_manual/o2oa_api/o2oa_ops/o2oa_version/"
        "ops_experience/ai_synthesis）+ kb_ingest/kb_reflect/growth_report 成长闭环。\n\n"
        "## 已知限制\n"
        "- rerank(8092) 默认关闭，需 llama-server --reranking 才启用。\n"
        "- 容器为 QEMU 模拟 amd64，长跑易病态，docker restart 即愈。\n"
        "- 容器时间 UTC，比主机 +8 小时。\n"
    )
    post_doc("o2kb::o2oa_version::local_deploy", "O2OA 本地部署版本与改进纪要", category, content)
    print("  [ok] o2oa_version 本地部署纪要")


# ----------------------------- 校验 -----------------------------
def embed_query(q):
    payload = {"model": EMBED_MODEL, "input": [q]}
    req = urllib.request.Request(
        EMBED_BASE + "/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return d["data"][0]["embedding"]


def verify(queries):
    if not os.path.isfile(DB_PATH):
        print("data.db 不存在，无法校验。先入库。")
        return
    conn = sqlite3.connect(DB_PATH, timeout=10)
    rows = conn.execute("SELECT doc_id, text, embedding FROM chunks").fetchall()
    docs = conn.execute("SELECT id, title, category FROM docs").fetchall()
    title_map = {d[0]: (d[1], d[2]) for d in docs}
    conn.close()
    print(f"\n=== 校验：{len(rows)} chunks / {len(docs)} docs ===")
    for q in queries:
        try:
            qv = embed_query(q)
        except Exception as e:
            print(f"  query 嵌入失败: {q} -> {e}")
            continue
        scored = []
        for doc_id, text, emb in rows:
            vec = list(__import__("struct").unpack(f"{len(emb)//4}f", emb))
            dot = sum(a*b for a, b in zip(qv, vec))
            na = sum(x*x for x in qv) ** .5 or 1e-9
            nb = sum(x*x for x in vec) ** .5 or 1e-9
            scored.append((dot/(na*nb), doc_id, text[:160]))
        scored.sort(reverse=True)
        print(f"\n● 查询：{q}")
        for sc, did, txt in scored[:3]:
            t, c = title_map.get(did, ("?", "?"))
            print(f"   {sc:.3f} [{c}] 《{t}》 {txt}")


def main():
    only = None
    do_verify = False
    for a in sys.argv[1:]:
        if a == "--verify":
            do_verify = True
        elif a.startswith("--cat="):
            only = a.split("=", 1)[1]
        elif a == "--help":
            print(__doc__)
            return
    if do_verify:
        verify([
            "O2OA 动态表怎么创建",
            "cookie 污染 服务号 上一个用户 500",
            "O2OA 待办列表查询接口 path",
            "断云 docker 网络隔离 502",
            "设计态 四层安全闸 系统应用",
        ])
        return
    print(">>> 开始入库（走网关 /idx-gateway-doc/update，服务进程内向量化）")
    ingest_markdown_dir(os.path.join(BASE, "o2oa高级应用开发", "docs"), "o2oa_manual", only)
    ingest_markdown_dir(os.path.join(BASE, "docs"), "o2oa_ops", only)
    ingest_describe(os.path.join(BASE, "describe", "describe.json"), only)
    ingest_api_json(os.path.join(BASE, "describe", "api.json"), only)
    ingest_version_doc(only)
    seed_ops_experience(only)
    print(f"\n>>> 完成：成功 {stats['docs']} 篇，失败 {stats['errors']} 篇")
    print(">>> 校验检索请加 --verify")


if __name__ == "__main__":
    main()
