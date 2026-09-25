# -*- coding: utf-8 -*-
"""
o2-agent-gateway - O2OA 智能体协议本地适配网关
把 O2OA 私有协议 (/ai-gateway-*, /idx-gateway-*) 翻译到本地 Bionic/LM Studio (OpenAI 兼容)。

协议契约逆向自 x_ai_assemble_control 源码（详见 D:/O2OA/docs/智能体本地化研究报告.md）：
- generate: 首帧 event=status {"generateType":..,"clueId":..}，之后 message 帧为 OpenAI chunk，终止 [DONE]
- DocIndex / McpConfig(http 型 MCP) / AiModel 结构见各 bean 源码
"""
import json
import math
import os
import re
import sqlite3
import struct
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse

# 标准 MCP client（stdio + HTTP JSON-RPC）—— 把外部 MCP 生态接入工具循环
from mcp_client import load_external_mcp, call_external_tool

BASE_DIR = Path(r"D:\O2OA\gateway")
SKILLS_DIR = BASE_DIR / "skills"
DB_PATH = BASE_DIR / "data.db"
LOG_PATH = BASE_DIR / "gateway.log"
CFG_PATH = BASE_DIR / "config.json"

DEFAULT_CFG = {
    "listen_host": "0.0.0.0",
    "listen_port": 18790,
    "token": "local-o2-agent-2026",
    "bionic_base": "http://127.0.0.1:1234",
    "embed_base": "http://127.0.0.1:1234",
    "bionic_key": "lm-studio",
    "chat_model": "glm-4.7-flash",
    "embed_models": ["text-embedding-bge-m3", "text-embedding-qwen3-embedding-0.6b",
                     "text-embedding-nomic-embed-text-v1.5"],
    "rag_top_k": 6,
    "chunk_size": 500,
    "chunk_overlap": 60,
    "max_turns": 5,
    # ---- RAG 精排 / 查询改写（18790 方案：bge-reranker / qwen3-reranker 提升精度）----
    "rerank_enable": False,
    "rerank_base": "",
    "rerank_model": "text-embedding-bge-reranker-v2-m3",
    "rag_rerank_candidate": 24,
    "rewrite_enable": False,
    "o2oa_user": "xadmin",
    "o2oa_pwd": "o2oaadmin2026",
    # 服务号：真实 person 实体，其会话 token 全模块 REST 可达
    # （xadmin 是虚拟初始管理员，不落库，业务模块受限；实测 REST 路径必须以
    #   /o2_core/o2/xAction/services/*.json 服务描述为准，路径错即 Jetty 404 HTML）
    "o2oa_svc_user": "网关服务号",
    "o2oa_svc_pwd": "Gw#svc2026",
    # ★ 服务号不可用时的回落账号（虚拟管理员）。o2oa_token() 依次试服务号 → 本账号。
    "o2oa_user": "xadmin",
    "o2oa_pwd": "o2oaadmin2026",
    # ---- 第三批：角色人设 + 行动能力（写回）----
    # 人设判定：以 user token 调 GET /x_organization_assemble_authentication/jaxrs/authentication
    # 取 roleList，按 @ 前段归一化后匹配。无 token / 未命中 = user（向导）。
    "persona_enable": True,
    "persona_manager_roles": ["manager", "systemManager", "securityManager", "auditManager"],
    "persona_analyst_roles": ["分析师", "aiAnalyst", "analyst"],
    # persona -> 可见内置工具白名单；None = 不限（管理员全量）
    # ★ 新增内置工具必须同步三个列表，否则对应角色看不见（显式白名单，最易踩的坑）
    # ★ 联网工具（web_search/web_fetch）**默认不在任何白名单里**：系统定位是内网数据闭环。
    #   若已置 web_enable=true 且希望角色可用，需显式把名字加回下面的列表。
    "persona_tools": {
        # 向导（普通用户）：查自己相关的一切 —— 待办、已办、组织、公文、数据表只读
        # task_plan/task_run_step：多步编排（只读场景也允许，如"盘点我的待办并汇总"）；
        # task_rollback 不给普通用户（破坏性操作，限 analyst/manager）
        "user": ["kb_search", "kb_read", "ocr_file",
                 "get_current_time", "calc", "search_org", "list_my_todo",
                 "todo_detail", "list_my_done", "org_unit_tree", "org_person_identity",
                 "query_table_list", "query_rows", "process_app_list",
                 "cms_list", "cms_detail", "cms_channels",
                 "task_plan", "task_run_step", "growth_report",
                 "skills_list", "skills_get", "skills_run", "feedback"],
        # 分析师：在向导基础上加写回与重型推理
        "analyst": ["kb_search", "kb_read", "kb_save", "ocr_file",
                    "get_current_time", "calc", "search_org", "list_my_todo",
                    "todo_detail", "list_my_done", "org_unit_tree", "org_person_identity",
                    "query_table_list", "query_rows", "process_app_list",
                    "cms_list", "cms_detail", "cms_channels",
                    "bionic_cli", "write_data", "design_op", "design_rollback",
                    "kb_ingest", "kb_reflect", "growth_report",
                    "task_plan", "task_run_step", "task_rollback",
                    "skills_list", "skills_get", "skills_run", "feedback"],
        "manager": None,
    },
    # 写回（行动能力）：默认仅 manager/analyst 可发起；表白名单 + 会话内二次确认 + 审计
    "write_enable": True,
    "write_personas": ["manager", "analyst"],
    "write_tables": ["aiDemoOrders"],
    "write_confirm_ttl": 600,
    # ---- 设计态能力（Phase A：门户页 / 动态表 / 数据应用 / 门户）----
    # 四层安全闸：① 角色闸门(analyst/manager) ② 草稿不落地(confirm=false只出提案)
    # ③ 过程授权(人类逐步确认即授权，不做静态白名单，按需而动) ④ 落地前快照+审计+可回滚。
    # 用户明确要求"白名单根据需要、过程授权"，故此处不列应用白名单，只保留系统级硬底线。
    "design_enable": True,
    "design_personas": ["manager", "analyst"],
    "design_denylist": ["a0000000-common-dict-app"],  # 系统级应用永不可碰
    "design_confirm_ttl": 600,
    # ---- 第四批：联网检索可靠性（多引擎降级链 + 防护 + 重试）----
    # ★★ 定位纠偏（2026-09-21）：本系统的定位是「把 Bionic 的 agent 能力在 O2OA 内落地」，
    #    即用 O2OA 自己的数据（知识库/待办/流程/组织/动态表/公文）做智能体，
    #    而不是把公网数据搬进系统。因此联网能力**默认关断**，只保留开关与实现，
    #    未来确需外部信息时才把 web_enable 置 true（代码与引擎链均保留，无需重写）。
    "web_enable": False,            # ★ 总开关：False = 不注册 web_search/web_fetch（默认）
    # 引擎优先级：searxng（本地自托管、返回结构化 JSON，最稳）→ bing（HTML 兜底）
    # 实测（2026-09-21）：本机 searxng @127.0.0.1:8080 可用；cn.bing.com=200；
    # DuckDuckGo html/lite 在国内网络 000 不可达，故不作为主引擎。
    "web_search_engines": [
        {"name": "searxng", "type": "searxng", "url": "http://127.0.0.1:8080/search",
         "timeout": 12, "enable": True},
        {"name": "bing", "type": "html", "url": "https://cn.bing.com/search",
         "timeout": 15, "enable": True},
    ],
    "web_fetch_timeout": 20,
    "web_fetch_max_chars": 6000,
    "web_retry": 2,                 # 单引擎重试次数（含首次共 web_retry+1 次）
    "web_retry_backoff": 1.0,       # 退避基数（秒），第 n 次等待 backoff*n
    "web_allow_private": False,     # 是否允许抓取内网/回环地址（SSRF 防护，默认禁止）
    "web_domain_deny": [],          # 域名黑名单（后缀匹配），如 [".evil.com"]
    "web_result_max_items": 8,      # 搜索最多返回条数
    "web_extract_max_chars": 900,   # 搜索结果单条摘要上限
    # ---- 第四批：Bionic 会话委派（bionic_cli）----
    # 把"重型子任务"（长文分析、代码审阅、深度推理）丢给一次干净的模型会话执行，
    # 避免污染主对话上下文、也避免主线被长推理拖慢。
    # 实现优先 HTTP（复用已加载模型，零额外显存）；lms.exe 子进程仅作可选兜底。
    "bionic_cli_enable": True,
    "bionic_cli_timeout": 240,      # 单次子任务超时（秒）
    "bionic_cli_max_chars": 6000,   # 返回给主模型的文本上限
    "bionic_cli_max_per_turn": 2,   # 同一轮对话最多委派次数（防递归/防拖垮）
    "bionic_cli_max_concurrent": 2, # 全局并发上限（保护 4GB 显存的推理后端）
    "bionic_cli_model": "",         # 空=用 chat_model；可指定更省的模型做子任务
    "bionic_cli_system": "你是 O2OA 智能助手的后台执行单元。请专注、准确地完成被指派的任务，"
                         "直接输出结果本身，不要寒暄、不要解释你在做什么、不要要求补充信息。",
    "bionic_cli_lms_path": "",      # 留空自动探测 ~/.lmstudio/bin/lms(.exe)

    # ---- 第五批：多步任务编排（任务账本 + 逐步落地 + 回滚）----
    # 定位：把「一句复杂指令」拆成多步**系统内操作**，逐步落地并留中间态。
    # 不引入独立的 planner 模型（4GB 显存不允许再起一份推理）；
    # 而是给主模型一套「计划账本工具」，让编排状态外置到 kv 表，可查、可续、可回滚。
    "orchestrator_enable": True,
    "orchestrator_max_steps": 12,     # 单个计划最多步骤数（防模型把计划写爆）
    "orchestrator_ttl": 7200,         # 计划有效期（秒），过期清理，防 kv 堆积
    "orchestrator_rollback": True,    # 允许对可逆步骤执行补偿（当前仅 write_data 类）
}

# 内网/保留地址前缀（SSRF 防护用；web_allow_private=True 时放行）
_PRIVATE_HOST_PREFIX = (
    "127.", "10.", "192.168.", "169.254.", "0.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.",
)
_PRIVATE_HOSTS = {"localhost", "::1", "[::1]", "metadata.google.internal"}

# bionic_cli 的全局并发闸 + 单轮计数（保护推理后端不被自己打爆）
_cli_lock = None
_cli_busy = {"n": 0}
_cli_turn = {"clue": "", "n": 0}


def _cli_sem():
    """惰性建信号量（导入期不建，避免 fork 问题）。"""
    global _cli_lock
    if _cli_lock is None:
        import threading
        _cli_lock = threading.Semaphore(int(CFG.get("bionic_cli_max_concurrent") or 2))
    return _cli_lock


def _lms_path():
    """定位 Bionic CLI（lms.exe）。不在 PATH，必须绝对路径。"""
    p = CFG.get("bionic_cli_lms_path")
    if p and os.path.exists(p):
        return p
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".lmstudio", "bin", "lms.exe"),
              os.path.join(home, ".lmstudio", "bin", "lms"),
              os.path.join(home, ".cache", "lm-studio", "bin", "lms")):
        if os.path.exists(c):
            return c
    return ""


def bionic_cli_impl(prompt: str, system: str = "", clue: str = "") -> str:
    """把独立子任务交给一次干净的模型会话执行。

    设计取舍（重要）：
    - 主路径走 HTTP /v1/chat/completions（复用已加载模型、零额外显存、无进程启动开销），
      而不是真的去 spawn `lms.exe chat`——本机是 4GB 显存核显，反复冷启进程代价过高。
    - 关键收益在"**干净上下文**"：主对话可能已经很长，把长文分析丢进独立会话，
      既不挤占主上下文窗口，也不会让主对话被中间过程污染。
    - 三层限流：单轮次数（防模型递归委派）、全局并发（护后端）、硬超时。
    """
    if not CFG.get("bionic_cli_enable", True):
        return "bionic_cli 未启用（bionic_cli_enable=false）"
    prompt = (prompt or "").strip()
    if not prompt:
        return "ERROR: prompt 不能为空"

    # 单轮次数上限（clue 维度；无 clue 时退化为进程级，避免无限委派）
    key = clue or "_global_"
    if _cli_turn.get("clue") != key:
        _cli_turn.update(clue=key, n=0)
    cap_turn = int(CFG.get("bionic_cli_max_per_turn") or 2)
    if _cli_turn["n"] >= cap_turn:
        return (f"本轮委派次数已达上限（{cap_turn} 次）。请直接使用已有的委派结果作答，"
                "不要再委派新任务。")
    _cli_turn["n"] += 1

    sem = _cli_sem()
    timeout = float(CFG.get("bionic_cli_timeout") or 240)
    max_chars = int(CFG.get("bionic_cli_max_chars") or 6000)
    model = CFG.get("bionic_cli_model") or CFG.get("chat_model")
    msgs = [{"role": "system", "content": system or CFG.get("bionic_cli_system") or ""},
            {"role": "user", "content": prompt}]
    t0 = time.time()
    acquired = sem.acquire(timeout=max(5.0, min(30.0, timeout / 4)))
    if not acquired:
        return ("bionic_cli 繁忙（并发已达上限）。请稍后重试，或直接基于现有信息作答。")
    try:
        for attempt, wait in enumerate((0, 3, 15)):   # 复用主链路的 400/断流退避策略
            if wait:
                time.sleep(wait)
            try:
                r = _client.post(f"{CFG['bionic_base']}/v1/chat/completions",
                                 headers=auth_hdr(),
                                 json={"model": model, "messages": msgs},
                                 timeout=timeout)
                if r.status_code != 200:
                    log(f"bionic_cli http {r.status_code} (attempt {attempt+1}): {r.text[:200]}")
                    continue
                m = r.json()["choices"][0]["message"]
                out = (m.get("content") or "").strip()
                if not out:
                    out = (m.get("reasoning_content") or "").strip()
                if out:
                    dt = time.time() - t0
                    log(f"bionic_cli ok model={model} {dt:.1f}s chars={len(out)}")
                    return (f"【委派结果 · 模型 {model} · {dt:.1f}s】\n" + out[:max_chars]
                            + ("\n（内容过长已截断）" if len(out) > max_chars else ""))
                log("bionic_cli 返回空内容")
            except Exception as e:
                log(f"bionic_cli attempt {attempt+1} error: {e}")
        return ("bionic_cli 执行失败：模型多次无有效返回。请改用你自身能力直接作答，"
                "或把任务拆小后重试。")
    finally:
        sem.release()

CFG = dict(DEFAULT_CFG)
if CFG_PATH.exists():
    try:
        CFG.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
    except Exception as e:
        log(f"config load fail: {e}")
else:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2), encoding="utf-8")


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- SQLite
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS docs(
          id TEXT PRIMARY KEY, title TEXT, category TEXT, content TEXT,
          creator_person TEXT, creator_unit TEXT, question_enable INTEGER DEFAULT 0,
          permission TEXT, meta TEXT, updated REAL);
        CREATE TABLE IF NOT EXISTS chunks(
          rowid_ INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, seq INTEGER,
          text TEXT, embedding BLOB);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS feedbacks(
          id TEXT PRIMARY KEY, person TEXT, kind TEXT, content TEXT,
          created_at TEXT, status TEXT DEFAULT 'open');
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, person TEXT, clue_id TEXT,
          tool TEXT, payload TEXT, status TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS growth_ledger(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, payload TEXT);
        """)


init_db()

# ---------------------------------------------------------------- Bionic
_client = httpx.Client(timeout=300, trust_env=False)


def emb_model() -> str:
    cached = kv_get("embed_model")
    if cached:
        return cached
    for m in CFG["embed_models"]:
        try:
            r = _client.post(f"{CFG.get('embed_base') or CFG['bionic_base']}/v1/embeddings",
                             headers=auth_hdr(),
                             json={"model": m, "input": "ping"})
            if r.status_code == 200:
                kv_set("embed_model", m)
                log(f"embed model selected: {m}")
                return m
            log(f"embed probe {m} -> {r.status_code}")
        except Exception as e:
            log(f"embed probe {m} err: {e}")
    return CFG["embed_models"][0]


def auth_hdr():
    return {"Authorization": f"Bearer {CFG['bionic_key']}"}


def kv_get(k):
    with db() as c:
        row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row[0] if row else None


def kv_set(k, v):
    with db() as c:
        c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def embed(texts):
    """list[str] -> list[list[float]]，失败返回 []"""
    try:
        r = _client.post(f"{CFG.get('embed_base') or CFG['bionic_base']}/v1/embeddings", headers=auth_hdr(),
                         json={"model": emb_model(), "input": texts})
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
    except Exception as e:
        log(f"embed error: {e}")
        return []


def pack_vec(v):
    return struct.pack(f"{len(v)}f", *v)


def unpack_vec(b):
    n = len(b) // 4
    return list(struct.unpack(f"{n}f", b))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


def chunk_text(text, size, overlap):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                out.append(buf)
            while len(p) > size:
                out.append(p[:size])
                p = p[size - overlap:]
            buf = p
    if buf:
        out.append(buf)
    return out


def reindex_doc(doc_id):
    with db() as c:
        row = c.execute("SELECT content FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return
    with db() as c:
        c.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
    parts = chunk_text(row[0], CFG["chunk_size"], CFG["chunk_overlap"])
    if not parts:
        return
    vecs = embed(parts)
    if not vecs:
        log(f"reindex {doc_id}: embed fail, {len(parts)} chunks skipped")
        return
    with db() as c:
        for i, (t, v) in enumerate(zip(parts, vecs)):
            c.execute("INSERT INTO chunks(doc_id,seq,text,embedding) VALUES(?,?,?,?)",
                      (doc_id, i, t, pack_vec(v)))
    log(f"reindex {doc_id}: {len(parts)} chunks")


def search_chunks(query, top_k, doc_ids=None):
    qv = embed([query])
    if not qv:
        return []
    qv = qv[0]
    with db() as c:
        if doc_ids:
            marks = ",".join("?" * len(doc_ids))
            rows = c.execute(f"SELECT doc_id,text,embedding FROM chunks WHERE doc_id IN ({marks})",
                             doc_ids).fetchall()
        else:
            rows = c.execute("SELECT doc_id,text,embedding FROM chunks").fetchall()
    scored = []
    for doc_id, text, emb in rows:
        try:
            scored.append((cosine(qv, unpack_vec(emb)), doc_id, text))
        except Exception:
            continue
    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[:top_k]


# ---------------------------------------------------------------- Rerank / Rewrite / 检索增强
def chat_complete(messages, model=None, **kw):
    """同步非流式 chat 补全，复用 bionic_base + bionic_key。供查询改写等内部调用。"""
    payload = {"model": model or CFG["chat_model"], "messages": messages,
               "stream": False, "reasoning_effort": "none"}
    payload.update(kw)
    try:
        r = _client.post(f"{CFG['bionic_base']}/v1/chat/completions",
                         headers=auth_hdr(), json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"chat_complete err: {e}")
        return ""


def rerank(query, docs):
    """调用 rerank 服务（llama.cpp /v1/rerank，Jina 兼容格式）。
    返回 [(score, original_index), ...] 按分数降序；失败返回 []。"""
    base = CFG.get("rerank_base")
    model = CFG.get("rerank_model") or "text-embedding-bge-reranker-v2-m3"
    if not base or not docs:
        return []
    try:
        r = _client.post(f"{base}/v1/rerank", headers=auth_hdr(),
                         json={"model": model, "query": query, "documents": docs,
                               "top_n": len(docs), "return_documents": False},
                         timeout=60)
        r.raise_for_status()
        res = r.json().get("results", [])
        out = []
        for it in res:
            idx = it.get("index")
            if idx is None:
                continue
            out.append((it.get("relevance_score", 0.0), idx))
        out.sort(reverse=True, key=lambda x: x[0])
        return out
    except Exception as e:
        log(f"rerank call err: {e}")
        return []


def rewrite_query(q):
    """RAG 查询改写：用 chat 模型扩展同义词/实体，提升召回。失败回退原句。"""
    if not CFG.get("rewrite_enable"):
        return q
    sys = ("你是一个检索增强(RAG)系统的查询改写器。请把用户问题改写成更适合向量检索的查询，"
           "补全关键实体与同义词，输出一行改写后的查询，不要任何解释或多余文字。")
    try:
        out = chat_complete([{"role": "system", "content": sys},
                             {"role": "user", "content": q}], max_tokens=64, temperature=0.0)
        return out.strip() or q
    except Exception as e:
        log(f"rewrite fail: {e}")
        return q


def rag_retrieve(query, doc_ids=None):
    """RAG 检索：向量召回候选池 → reranker 精排 → 加权融合排序返回 top_k。

    采用 向量分(0.6) + rerank分(0.4) 归一化加权融合（而非用 rerank 直接替换向量序）。
    原因：实测 bge-reranker 在否定/意图反转句上会被字面重叠误导（如把"牢记默认密码"
    排在"禁止使用默认密码"之前）。融合既借 reranker 提升信号/噪声分离，又避免其单点
    误判把顶部正确结果翻盘。rerank 不可用时自动回退纯向量 top_k。"""
    want_rerank = bool(CFG.get("rerank_enable") and CFG.get("rerank_base"))
    k = CFG.get("rag_top_k", 6)
    pool = CFG.get("rag_rerank_candidate", 0) or 0
    fetch_k = max(k, pool) if want_rerank else k
    cands = search_chunks(query, fetch_k, doc_ids=doc_ids)
    if not cands:
        return []
    if want_rerank:
        try:
            ranked = rerank(query, [t for _, _, t in cands])
            if ranked:
                vscores = [s for s, _, _ in cands]
                rscores = {idx: sc for sc, idx in ranked}
                vmin, vmax = min(vscores), max(vscores)
                rvals = [rscores.get(i, 0.0) for i in range(len(cands))]
                rmin, rmax = min(rvals), max(rvals)
                out = []
                for i, (vs, did, t) in enumerate(cands):
                    nv = (vs - vmin) / (vmax - vmin) if vmax > vmin else 1.0
                    nr = (rvals[i] - rmin) / (rmax - rmin) if rmax > rmin else 1.0
                    out.append(((0.6 * nv + 0.4 * nr), did, t))
                out.sort(reverse=True, key=lambda x: x[0])
                return out[:k]
        except Exception as e:
            log(f"rerank failed, fallback vector top_k: {e}")
    return cands[:k]


def visible_docs(permission_list):
    """返回允许访问的 doc_id 集合。permission_list 为空 = 管理员视角全部可见。"""
    if not permission_list:
        with db() as c:
            return {r[0] for r in c.execute("SELECT id FROM docs")}
    allow = set()
    with db() as c:
        for doc_id, perm in c.execute("SELECT id, permission FROM docs"):
            try:
                dperm = json.loads(perm) if perm else []
            except Exception:
                dperm = []
            if not dperm or set(dperm) & set(permission_list):
                allow.add(doc_id)
    return allow


# ---------------------------------------------------------------- 附件下载（多模态链路）
# O2OA 的 referenceIdList 给的是【附件 ID】（x_ai_core File 实体），不是图片字节。
# 网关需自己调 O2OA REST 把内容取回来，再决定走视觉（image_url）还是文本提取。
# 接口：GET /x_ai_assemble_control/jaxrs/file/{id}/download
#   —— ActionDownload 里：effectivePerson.isNotManager() 时要求 creator 匹配，
#      故用 manager 身份（xadmin cipher token）可下载任意附件。

IMAGE_EXT = {"png", "jpg", "jpeg", "bmp", "gif", "webp"}
IMAGE_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "bmp": "image/bmp", "gif": "image/gif", "webp": "image/webp"}


def o2oa_file_info(file_id):
    """取附件元数据（名称/扩展名）。失败返回 (None, None)。"""
    base = CFG.get("o2oa_base") or "http://127.0.0.1:9090"
    tok = CFG.get("o2oa_admin_token") or ""
    try:
        _o2_http.cookies.clear()
        r = _o2_http.get(f"{base}/x_ai_assemble_control/jaxrs/file/{file_id}",
                         headers={"x-token": tok}, timeout=30)
        if r.status_code != 200:
            return None, None
        d = r.json()
        data = d.get("data") or {}
        return data.get("name"), (data.get("extension") or "").lower()
    except Exception as e:
        log(f"o2oa_file_info {file_id} err: {e}")
        return None, None


def o2oa_file_bytes(file_id):
    """下载附件原始字节。失败返回 None。"""
    base = CFG.get("o2oa_base") or "http://127.0.0.1:9090"
    tok = CFG.get("o2oa_admin_token") or ""
    try:
        _o2_http.cookies.clear()
        r = _o2_http.get(f"{base}/x_ai_assemble_control/jaxrs/file/{file_id}/download",
                         headers={"x-token": tok}, timeout=120)
        if r.status_code != 200:
            log(f"o2oa_file_bytes {file_id} -> HTTP {r.status_code}")
            return None
        return r.content
    except Exception as e:
        log(f"o2oa_file_bytes {file_id} err: {e}")
        return None


# ---------------------------------------------------------------- O2OA 实时数据快照（报表自然语言查询支撑）
def o2oa_token(force=False):
    """以网关服务号身份换取 O2OA 会话令牌。15 分钟 TTL 自动续期（会话 token 会过期），
    force=True 强制重新登录（调用方在 401/404 时触发）。
    服务号是真实 person 实体，业务模块 REST 全可达；未配置时回落 xadmin。"""
    TTL = 15 * 60
    if not force:
        cached = kv_get("o2oa_token")
        ts = kv_get("o2oa_token_ts")
        try:
            if cached and ts and time.time() - float(ts) < TTL:
                return cached
        except Exception:
            pass
    try:
        # ★ 2026-09-21 修正：服务号「网关服务号」在某些部署里并不存在（用户不存在或密码错），
        #   旧实现只试服务号一条路，导致整条内网工具链静默失效（token 为空 → 所有工具返 HTTP 0）。
        #   现改为「服务号 → xadmin」两条候选依次尝试，谁先成功用谁，并把实际生效的账号记进 kv，
        #   便于 /gateway/capabilities 暴露与排障。
        cands = []
        svc_u = (CFG.get("o2oa_svc_user") or "").strip()
        svc_p = (CFG.get("o2oa_svc_pwd") or "").strip()
        if svc_u and svc_p:
            cands.append((svc_u, svc_p))
        adm_u = (CFG.get("o2oa_user") or "xadmin").strip()
        adm_p = (CFG.get("o2oa_pwd") or "o2oaadmin2026").strip()
        if adm_u and adm_p and (adm_u, adm_p) not in cands:
            cands.append((adm_u, adm_p))
        for cred, pwd in cands:
            try:
                _o2_http.cookies.clear()
                r = _o2_http.post(f"{CFG.get('o2oa_base','http://127.0.0.1:9090')}"
                                  "/x_organization_assemble_authentication/jaxrs/authentication",
                                  json={"credential": cred, "password": pwd}, timeout=30)
                d = r.json().get("data")
                t = d.get("token") if isinstance(d, dict) else None
                if t:
                    kv_set("o2oa_token", t)
                    kv_set("o2oa_token_ts", str(time.time()))
                    if kv_get("o2oa_token_user") != cred:
                        log(f"o2oa login ok as '{cred}'"
                            + ("（服务号不可用，已回落虚拟管理员）" if cred == adm_u else ""))
                        kv_set("o2oa_token_user", cred)
                    return t
                log(f"o2oa login '{cred}' -> HTTP {r.status_code} {r.text[:100]}")
            except Exception as e:
                log(f"o2oa login '{cred}' err: {e}")
    except Exception as e:
        log(f"o2oa login err: {e}")
    return ""


def _o2oa_get(path, token):
    _o2_http.cookies.clear()
    r = _o2_http.get(f"{CFG.get('o2oa_base','http://127.0.0.1:9090')}{path}",
                     headers={"x-token": token}, timeout=30)
    r.raise_for_status()
    return r.json()


def _extract_list(obj, key):
    """兼容 O2OA 多种返回：直接 [...]、{data:[...]}、{data:{xxxList:[...]}}。"""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        d = obj.get("data")
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in (key + "List", key, "list"):
                if k in d and isinstance(d[k], list):
                    return d[k]
        if key in obj and isinstance(obj[key], list):
            return obj[key]
    return []


def o2oa_snapshot():
    """拉取本组织 O2OA 实时目录（应用/门户等业务模块），供报表自然语言查询使用。"""
    tok = o2oa_token()
    if not tok:
        return "（无法登录 O2OA，报表数据不可用）"
    try:
        apps = _extract_list(_o2oa_get("/x_processplatform_assemble_designer/jaxrs/application/list", tok), "application")
        portals = _extract_list(_o2oa_get("/x_portal_assemble_designer/jaxrs/portal/list", tok), "portal")
        lines = ["# O2OA 实时数据快照",
                 f"- 应用(业务模块)数量: {len(apps)}",
                 f"- 门户数量: {len(portals)}", "", "## 应用清单"]
        for a in apps:
            nm = a.get("name") if isinstance(a, dict) else str(a)
            al = a.get("alias", "") if isinstance(a, dict) else ""
            lines.append(f"- {nm}（{al}）")
        lines.append(""); lines.append("## 门户清单")
        for p in portals[:50]:
            nm = p.get("name") if isinstance(p, dict) else str(p)
            lines.append(f"- {nm}")
        return "\n".join(lines)
    except Exception as e:
        return f"（获取 O2OA 数据失败: {e}）"


def build_ref_content(refs):
    """把 referenceIdList 转成 OpenAI 多模态 content 数组。
    返回 (content_parts, used_vision, note)：
      content_parts —— 形如 [{"type":"text",...}, {"type":"image_url",...}]
    """
    import base64
    parts, used_vision, notes = [], False, []
    for fid in (refs or []):
        name, ext = o2oa_file_info(fid)
        if name is None:
            notes.append(f"（附件 {fid[:8]}… 读取失败）")
            continue
        data = o2oa_file_bytes(fid)
        if data is None:
            notes.append(f"（附件 {name} 下载失败）")
            continue
        if ext in IMAGE_EXT:
            b64 = base64.b64encode(data).decode("ascii")
            mime = IMAGE_MIME.get(ext, "image/png")
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{b64}"}})
            used_vision = True
            notes.append(f"（已附加图片 {name}）")
        else:
            # 非图片：先尝试直接文本提取；扫描件/PDF 交给 OCR（若已配置）
            text = extract_text(data, ext, name)
            if text:
                parts.append({"type": "text", "text": f"【附件 {name}】\n{text}"})
                notes.append(f"（已提取文本 {name}，{len(text)} 字）")
            else:
                notes.append(f"（附件 {name} 无法提取文本，建议启用 OCR）")
    return parts, used_vision, "".join(notes)


def extract_text(data, ext, name):
    """尽力而为的文本提取。

    优先级：
      1. 纯文本类扩展名        -> 直接解码（多编码兜底）
      2. docx / xlsx          -> python-docx / openpyxl 结构化提取
      3. pdf / 图片           -> 交 OCR 服务（:8091，RapidOCR 纯 CPU）
                                 PDF 由服务侧判断文本层：有则直抽（ms 级），
                                 无则渲染 + OCR（扫描件），并把表格还原成 Markdown。
    """
    try:
        if ext in ("txt", "md", "csv", "json", "xml", "log"):
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    return data.decode(enc)
                except Exception:
                    continue
            return None
        if ext == "docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip()) or None
        if ext == "xlsx":
            import io
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(data), read_only=True)
            rows = []
            for ws in wb.worksheets:
                rows.append(f"【工作表 {ws.title}】")
                for row in ws.iter_rows(values_only=True):
                    rows.append("\t".join("" if v is None else str(v) for v in row))
            return "\n".join(rows) or None
        # PDF / 图片 -> OCR 服务（若已配置）
        ocr = CFG.get("ocr_base") or ""
        if ocr and ext in ("pdf", "png", "jpg", "jpeg", "bmp", "webp",
                           "gif", "tif", "tiff"):
            import base64
            r = _client.post(f"{ocr}/ocr", timeout=300,
                             json={"file_b64": base64.b64encode(data).decode("ascii"),
                                   "filename": name})
            if r.status_code != 200:
                log(f"ocr {name} -> HTTP {r.status_code}: {r.text[:200]}")
                return None
            j = r.json() or {}
            if not j.get("ok"):
                log(f"ocr {name} -> fail: {j.get('error')}")
                return None
            text = (j.get("text") or "").strip()
            # 表格结构还原成 Markdown，比纯文本行更能保留语义
            tbls = j.get("tables") or []
            if tbls:
                try:
                    import sys as _sys
                    if str(BASE_DIR) not in _sys.path:
                        _sys.path.insert(0, str(BASE_DIR))
                    from ocr_service import table_to_markdown
                except Exception:
                    table_to_markdown = None
                md = []
                for t in tbls:
                    if table_to_markdown:
                        s = table_to_markdown(t)
                        if s:
                            md.append(s)
                if md:
                    text = (text + "\n\n【识别到的表格】\n" + "\n\n".join(md)).strip()
            cap = int(CFG.get("ocr_max_chars") or 20000)
            if len(text) > cap:
                text = text[:cap] + f"\n……（已截断，全文 {len(text)} 字）"
            log(f"ocr {name} engine={j.get('engine')} pages={j.get('pages')} "
                f"chars={len(text)} tables={len(tbls)} ms={j.get('ms')}")
            return text or None
        return None
    except Exception as e:
        log(f"extract_text {name} err: {e}")
        return None


# ---------------------------------------------------------------- 内置工具（本地原生）
# 这些工具不依赖 O2OA 的 McpConfig 配置，网关自带、开箱即用。
# 依据：后端 llama-server 原生支持 tool calling（supports_tool_calls=true）。
# 设计原则：只放"模型自身做不到或做不可靠"的能力（时间/计算/私有数据检索）。

# ============================================================ 联网检索底座（第四批）
# 目标：让"联网"这件事在网络抖动、引擎宕机、页面改版时都不至于整链失败。
# 三件事：① 引擎降级链 ② 重试退避 ③ SSRF/黑名单防护；外加 HTML→文本的可复用抽取。

# 复用的外网客户端（trust_env=True 才会走系统代理；网关主 _client 是 False 只服务本地）
_web_client = httpx.Client(trust_env=True, follow_redirects=True, timeout=25,
                           headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/120.0 Safari/537.36",
                                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
_web_last_probe = {"ts": 0.0, "engine": "", "ok": False}


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _url_guard(url: str):
    """抓取前置校验：协议 + SSRF 内网防护 + 域名黑名单。
    返回 (ok, normalized_url, err_msg)。"""
    url = (url or "").strip()
    if not url:
        return False, "", "URL 为空"
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    host = _host_of(url)
    if not host:
        return False, url, "URL 解析不出主机名"
    if not CFG.get("web_allow_private", False):
        if host in _PRIVATE_HOSTS or host.startswith(_PRIVATE_HOST_PREFIX):
            return False, url, (f"拒绝访问内网/回环地址 {host}"
                                "（如需放开请设 web_allow_private=true）")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            return False, url, f"拒绝访问裸 IP {host}（SSRF 防护）"
    for bad in (CFG.get("web_domain_deny") or []):
        if bad and host.endswith(str(bad).lower()):
            return False, url, f"域名 {host} 在黑名单中"
    return True, url, ""


def html_to_text(html: str, max_chars: int = 6000) -> str:
    """HTML → 可读正文：去脚本/样式/注释/导航噪声，压缩空白，按 max_chars 截断。
    比单纯 re.sub('<[^>]+>') 干净得多——后者会把 <script> 里的 JS 全留下。"""
    if not html:
        return ""
    s = re.sub(r"(?is)<!--.*?-->", " ", html)
    s = re.sub(r"(?is)<(script|style|noscript|svg|canvas|iframe)[^>]*>.*?</\1>", " ", s)
    # 块级标签转行，保留段落感
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|br|section|article|header|footer)>", "\n", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)<head[^>]*>.*?</head>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    # 实体归一化
    for k, v in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&ldquo;", "“"), ("&rdquo;", "”")):
        s = s.replace(k, v)
    s = re.sub(r"[ \t\u00a0]{2,}", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    s = "\n".join(ln.strip() for ln in s.split("\n") if ln.strip())
    return s.strip()[:max_chars]


def _web_get(url: str, params=None, timeout=None, tries=None):
    """带重试退避的外网 GET。返回 (resp_or_None, err_str)。
    重试覆盖：连接错误、超时、5xx、429。4xx（除 429）立即失败不重试。"""
    tries = int(CFG.get("web_retry") or 2) + 1 if tries is None else tries
    timeout = timeout or CFG.get("web_fetch_timeout") or 20
    backoff = float(CFG.get("web_retry_backoff") or 1.0)
    last = ""
    for i in range(max(1, tries)):
        if i:
            time.sleep(backoff * i)
        try:
            r = _web_client.get(url, params=params, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                last = f"HTTP {r.status_code}"
                continue
            return r, ""
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return None, last


def _parse_bing(html: str, limit: int):
    """Bing HTML 结果解析（含宽松兜底，防页面改版后整个引擎失效）。"""
    items = []
    for m in re.finditer(r'(?is)<li class="b_algo".*?</li>', html or ""):
        blk = m.group(0)
        a = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk)
        if not a:
            continue
        href = a.group(1)
        title = re.sub(r"<[^>]+>", "", a.group(2)).strip()
        p = re.search(r"(?is)<p[^>]*>(.*?)</p>", blk)
        snip = html_to_text(p.group(1), 400) if p else ""
        items.append({"title": title, "url": href, "snippet": snip})
        if len(items) >= limit:
            break
    if not items:   # 宽松兜底：任意 <h2><a href="http...">
        for a in re.finditer(r'(?is)<h2[^>]*>\s*<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>',
                             html or ""):
            items.append({"title": re.sub(r"<[^>]+>", "", a.group(2)).strip(),
                          "url": a.group(1), "snippet": ""})
            if len(items) >= limit:
                break
    return items


def _parse_searxng(data, limit: int):
    """SearXNG JSON 结果解析（结构化，最稳）。"""
    items = []
    if isinstance(data, dict):
        for r in (data.get("results") or []):
            if not isinstance(r, dict):
                continue
            u = r.get("url") or ""
            if not u:
                continue
            items.append({"title": (r.get("title") or "").strip(),
                          "url": u,
                          "snippet": (r.get("content") or "").strip()})
            if len(items) >= limit:
                continue
    return items


def _engine_search(spec, query: str, limit: int):
    """单引擎检索。返回 (items, err)；items 非空即成功。"""
    name = spec.get("name") or "?"
    etype = (spec.get("type") or "html").lower()
    url = spec.get("url") or ""
    timeout = spec.get("timeout") or 15
    if etype == "searxng":
        r, err = _web_get(url, params={"q": query, "format": "json",
                                       "language": "zh-CN", "safesearch": 1},
                          timeout=timeout)
        if r is None:
            return [], f"{name}: {err}"
        if r.status_code != 200:
            return [], f"{name}: HTTP {r.status_code}"
        try:
            items = _parse_searxng(r.json(), limit)
        except Exception as e:
            return [], f"{name}: JSON 解析失败 {e}"
        return (items, "") if items else ([], f"{name}: 无结果")
    # html 型
    r, err = _web_get(url, params={"q": query}, timeout=timeout)
    if r is None:
        return [], f"{name}: {err}"
    if r.status_code != 200:
        return [], f"{name}: HTTP {r.status_code}"
    items = _parse_bing(r.text or "", limit)
    return (items, "") if items else ([], f"{name}: 解析不到结果")


def web_search_impl(query: str, limit: int = 5):
    """多引擎降级检索：按 web_search_engines 顺序试，首个有结果的胜出。
    全部失败时返回可读的失败摘要（含每个引擎的原因），让模型知道"是网断了"而非"没这回事"。"""
    query = (query or "").strip()
    if not query:
        return "ERROR: query 不能为空"
    limit = max(1, min(int(limit or 5), int(CFG.get("web_result_max_items") or 8)))
    cap = int(CFG.get("web_extract_max_chars") or 900)

    # 优先用配置的搜索 MCP（search_mcp）；失败继续走引擎链
    spec = CFG.get("search_mcp")
    if spec:
        try:
            defs, disp = load_external_mcp([spec])
            if disp:
                full = next(iter(disp))
                out = call_external_tool(full, disp, {"query": query, "q": query,
                                                      "keyword": query, "limit": limit})
                if out and "MCP_CALL_ERROR" not in str(out):
                    return f"搜索“{query}”结果（search_mcp）：\n" + str(out)[:cap * limit]
        except Exception as e:
            log(f"search_mcp failed: {e}")

    errs, used = [], ""
    for spec in (CFG.get("web_search_engines") or []):
        if not spec.get("enable", True):
            continue
        items, err = _engine_search(spec, query, limit)
        if items:
            used = spec.get("name") or "?"
            lines = []
            for i, it in enumerate(items):
                lines.append(f"[{i+1}] {it['title']}\n    {it['snippet'][:cap]}\n    {it['url']}")
            _web_last_probe.update(ts=time.time(), engine=used, ok=True)
            return f"搜索“{query}”结果（引擎 {used}）：\n" + "\n".join(lines)
        errs.append(err)
    _web_last_probe.update(ts=time.time(), engine="", ok=False)
    return (f"联网搜索暂时不可用（{query}）。已尝试的引擎：" + "；".join(errs)
            + "。\n这是**网络/引擎侧故障，不是“没有相关资料”**。"
              "请如实告知用户检索通道暂时不可用，或改用 web_fetch 直接抓取已知站点"
              "（如 https://www.weather.com.cn/weather/101010100.shtml 查北京天气）。"
              "不要凭记忆编造实时数据。")


def web_fetch_impl(url: str, max_chars: int = None, mode: str = "text"):
    """抓取网页/接口。mode=text 抽正文；mode=raw 保留原始文本（JSON/API 用）。
    带 SSRF 防护 + 重试退避 + 可读失败原因。"""
    ok_, url, err = _url_guard(url)
    if not ok_:
        return f"抓取被拒绝：{err}"
    max_chars = int(max_chars or CFG.get("web_fetch_max_chars") or 6000)
    max_chars = max(200, min(max_chars, 30000))
    r, err = _web_get(url)
    if r is None:
        return (f"抓取失败（{url}）：{err}\n"
                "提示：已自动重试；若持续失败多为网络或站点侧问题，"
                "请如实告知用户当前无法访问该地址。")
    ctype = (r.headers.get("content-type") or "").lower()
    body = r.text or ""
    is_json = "json" in ctype or body.lstrip()[:1] in ("{", "[")
    if mode == "raw" or is_json:
        text = body
    else:
        text = html_to_text(body, max_chars)
    head = f"HTTP {r.status_code} {url} | {ctype.split(';')[0] or 'unknown'} | {len(body)} bytes"
    if mode == "raw" or is_json:
        return head + "\n" + text[:max_chars]
    return head + "\n" + text


def web_probe():
    """/gateway/capabilities 用：探活每个搜索引擎（仅 TCP/HTTP 可达性，不做真实查询）。"""
    out = []
    for spec in (CFG.get("web_search_engines") or []):
        if not spec.get("enable", True):
            out.append({"name": spec.get("name"), "enable": False})
            continue
        u = spec.get("url") or ""
        item = {"name": spec.get("name"), "type": spec.get("type"), "url": u}
        try:
            if (spec.get("type") or "").lower() == "searxng":
                r = _web_client.get(u, params={"q": "ping", "format": "json"},
                                    timeout=spec.get("timeout") or 10)
                item["up"] = r.status_code == 200
                item["http"] = r.status_code
            else:
                r = _web_client.get(u, params={"q": "ping"},
                                    timeout=spec.get("timeout") or 10)
                item["up"] = r.status_code == 200
                item["http"] = r.status_code
        except Exception as e:
            item["up"] = False
            item["error"] = str(e)[:120]
        out.append(item)
    return out


BUILTIN_TOOLS = [
    {
        "name": "kb_search",
        "description": "检索本地知识库。当问题涉及公司内部资料、制度、文档时优先调用，"
                       "不要凭记忆回答。返回最相关的若干片段。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或问题"},
                "top_k": {"type": "integer", "description": "返回条数，默认 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_current_time",
        "description": "获取当前日期与时间。任何涉及'今天/现在/本周'的问题都必须先调用，不要依赖你的内部时钟。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "calc",
        "description": "计算数学表达式，支持 + - * / // % ** 与括号、abs/round/min/max/sum。"
                       "任何算术都必须用它，你的心算不可靠。",
        "parameters": {
            "type": "object",
            "properties": {"expr": {"type": "string", "description": "如 (1+2)*3/4"}},
            "required": ["expr"],
        },
    },
    {
        "name": "search_org",
        "description": "在 O2OA 组织架构中按名称关键词搜索人员、部门或身份，返回名称与标识（DN）。"
                       "找人和找部门的统一入口。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "姓名或部门关键词"},
                "kind": {"type": "string", "description": "person=人员（默认）/ unit=组织部门 / identity=身份"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "list_my_todo",
        "description": "列出当前用户的待办工作（流程待办），用于'我有什么要处理的'这类问题。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "最多返回条数，默认 10"},
                "page": {"type": "integer", "description": "页码，默认 1"},
            },
            "required": [],
        },
    },
    # ---- 第五批：系统内 agent 能力（只吃 O2OA 自身数据，不碰公网）----
    {
        "name": "todo_detail",
        "description": "查看某条待办的完整详情：表单数据、当前可走的路由、附件。"
                       "用于'这条待办要我做什么/该怎么处理'。请先用 list_my_todo 拿到 taskId。",
        "parameters": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "待办标识（taskId）"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "list_my_done",
        "description": "列出当前用户已办结的工作（'我处理过什么'）。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "最多返回条数，默认 10"},
                "page": {"type": "integer", "description": "页码，默认 1"},
            },
            "required": [],
        },
    },
    {
        "name": "org_unit_tree",
        "description": "查看组织架构树：不给 unit_flag 时列出顶层组织；给了则列出其全部下级组织。"
                       "用于'公司有哪些部门/某部门下面有什么'。",
        "parameters": {
            "type": "object",
            "properties": {"unit_flag": {"type": "string",
                                          "description": "组织标识，留空=从顶层开始"}},
            "required": [],
        },
    },
    {
        "name": "org_person_identity",
        "description": "查看某个人员担任的身份（所属部门、职务）。"
                       "入参必须是人员的标识（可先用 search_org 拿到），不是姓名。",
        "parameters": {
            "type": "object",
            "properties": {"person_flag": {"type": "string", "description": "人员标识（unique/id）"}},
            "required": ["person_flag"],
        },
    },
    {
        "name": "query_table_list",
        "description": "列出 O2OA 数据中心里所有自建业务表（名称、alias、所属应用）。"
                       "★ 回答'系统里有哪些数据表'，或在 query_rows 之前确认表标识时用。"
                       "★ 若已知大概名称，强烈建议传 keyword 做定向查找"
                       "（否则返回 75 行清单，容易看漏）。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string",
                            "description": "可选，按表名/alias 模糊过滤，如 'order' 或 '合同'。"
                                           "留空=返回全部（较多）"},
            },
            "required": [],
        },
    },
    {
        "name": "query_rows",
        "description": "查询 O2OA 数据中心某张自建表的数据行。这是系统内业务数据的主入口，"
                       "制度/台账/清单类问题都优先用它。",
        "parameters": {
            "type": "object",
            "properties": {
                "table_flag": {"type": "string", "description": "表标识（表名或 alias，可先用 query_table_list 查）"},
                "where": {"type": "string", "description": "可选过滤条件，jpql 语法，如 o.status='已审批'；留空=取全部"},
                "limit": {"type": "integer", "description": "最多返回行数，默认 20"},
            },
            "required": ["table_flag"],
        },
    },
    {
        "name": "process_app_list",
        "description": "列出当前用户可见的流程应用及其可启动的流程，以及应用/流程的名称与标识。"
                       "用于'系统里有哪些流程/我能在哪个应用发起什么'。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cms_list",
        "description": "检索 O2OA 内已发布的公文/信息文档（按标题关键词）。"
                       "用于'找找某份公文/通知/制度文件'。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "标题关键词，留空=列最新"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 10"},
            },
            "required": [],
        },
    },
    {
        "name": "cms_detail",
        "description": "读取某篇公文/信息文档的正文与附件清单。请先用 cms_list 拿到文档 id。",
        "parameters": {
            "type": "object",
            "properties": {"doc_id": {"type": "string", "description": "文档标识"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "cms_channels",
        "description": "列出系统里有哪些信息栏目/公文分类（及其所属应用）。"
                       "用于'有哪些公文分类/信息栏目'，或找不到文档时确认栏目是否存在。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kb_read",
        "description": "读知识库文档：不传 doc_id 时列出系统知识库里有哪些文档（可按关键词过滤）；"
                       "传 doc_id 时返回该文档全文。用于'知识库里有什么/把某份资料的具体内容给我'，"
                       "以及答案需要注明出处（引用《标题》）的场景。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "可选，按标题/正文关键词过滤文档列表"},
                "doc_id": {"type": "string", "description": "可选，指定文档标识则返回其全文"},
            },
            "required": [],
        },
    },
    {
        "name": "ocr_file",
        "description": "对 O2OA 附件（图片/PDF/扫描件）做文字识别（OCR）。"
                       "用于'这个扫描件/图片/PDF 里写了什么'。file_id 从待办详情或公文详情的附件里取。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "附件标识"},
                "name": {"type": "string", "description": "可选，附件文件名（用于判断类型，如 x.pdf）"},
            },
            "required": ["file_id"],
        },
    },
    # ---- 第五批：多步任务编排（任务账本 / 逐步落地 / 回滚）----
    # ★ 与 bionic_cli 的分工：bionic_cli 是「把一块内容丢给干净会话做推理」；
    #   task_plan 是「把一件跨多步的系统内事务编排出来、逐步执行、可回滚」。
    #   前者解决上下文污染，后者解决多步可靠性与可观测性。二者互补，不可互相替代。
    {
        "name": "task_plan",
        "description": "多步任务账本：把一件需要多步系统操作才能完成的事（如'把这份合同走完审核并归档'、"
                       "'盘点资产表里逾期未归还的并逐个催办'）拆成有序步骤，登记为可跟踪的计划。"
                       "★ 用法：复杂指令（预计需要 3 步以上工具调用）第一步先调本工具登记计划；"
                       "然后每完成一步用 action=update 回填该步状态与中间结果；"
                       "全部完成后 action=close。中途可用 action=show 查看当前进度。"
                       "★ 计划只记录与编排，真正的数据操作仍由各业务工具执行（由你逐步调用）。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "description": "create=登记新计划（需 steps）；update=回填某步状态；"
                                          "show=查看当前计划与进度；close=结项；cancel=放弃并清理"},
                "goal": {"type": "string", "description": "create 时必填：一句话目标"},
                "steps": {"type": "array", "description": "create 时必填：步骤列表，每项为字符串描述",
                          "items": {"type": "string"}},
                "step_index": {"type": "integer",
                               "description": "update 时必填：第几步（从 1 开始）"},
                "status": {"type": "string",
                           "description": "update 时的步骤状态：done=已完成 / failed=失败 / "
                                          "skipped=跳过 / doing=进行中"},
                "result": {"type": "string", "description": "update 时可选：该步的中间结果摘要"},
                "note": {"type": "string", "description": "可选备注（close/cancel 时说明原因）"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "task_run_step",
        "description": "在计划内执行一个「系统内操作」步骤，并自动把执行结果写回计划账本。"
                       "★ 所有参数都是**平铺**的字段，没有嵌套对象。"
                       "kind 只能填 read 或 write 或 notify_note 三者之一（就是一个单词）。",
        "parameters": {
            "type": "object",
            "properties": {
                "step_index": {"type": "integer", "description": "第几步（对应 task_plan 里的序号）"},
                "kind": {"type": "string", "enum": ["read", "write", "notify_note"],
                         "description": "只填一个单词：read 读数据 / write 写数据 / notify_note 留痕"},
                "source": {"type": "string",
                           "enum": ["table", "tables", "kb", "cms", "todo"],
                           "description": "kind=read 时必填，指明读哪一类："
                                          "tables=列出全部自建表（找表标识先用它）；"
                                          "table=读某张表的数据行（需同时填 flag）；"
                                          "kb=知识库；cms=公文；todo=我的待办"},
                "flag": {"type": "string",
                         "description": "kind=read 且 source=table 时填表标识（如 aiDemoOrders）；"
                                        "source=tables 时不用填。★ 只填标识本身，不要填整句描述"},
                "query": {"type": "string",
                          "description": "source=kb/cms 时的检索关键词；"
                                         "source=tables 时也可填，用于按名称/别名过滤表清单"
                                         "（★ 知道大概名字就一定要填，否则返回 75 行容易看漏）"},
                "where": {"type": "string",
                          "description": "可选，读表时的过滤条件，jpql 语法，如 o.amount>100"},
                "limit": {"type": "integer", "description": "可选，最多返回条数，默认 20"},
                "data": {"type": "object",
                         "description": "kind=write 时必填：要写入的行数据（键用英文字段名）"},
                "action": {"type": "string", "enum": ["create", "update"],
                           "description": "kind=write 时：create 新增（默认）/ update 更新"},
                "row_id": {"type": "string", "description": "kind=write 且 action=update 时填目标行 id"},
                "note_text": {"type": "string", "description": "kind=notify_note 时的留痕文本"},
                "confirm": {"type": "boolean",
                            "description": "write 类步骤：首次调用不带 confirm 会生成预案，"
                                           "经用户确认后带 confirm=true 再调一次才真正执行"},
            },
            "required": ["step_index", "kind"],
        },
    },
    {
        "name": "task_rollback",
        "description": "回滚计划中已执行的可逆步骤（补偿操作）。当某步失败导致整条流程走不通时使用。"
                       "★ 只对**可逆步骤**有效：write 类步骤若记录了下发 id，可尝试删除该行补偿；"
                       "读类步骤天然无需回滚（自动跳过）。"
                       "执行前会先列出将回滚哪些步骤，需用户 confirm=true 再执行——回滚是破坏性操作，"
                       "严禁未经用户确认执行。",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "回滚原因（会记入计划与审计）"},
                "from_step": {"type": "integer", "description": "可选：从第几步开始回滚（默认全部已执行步骤）"},
                "confirm": {"type": "boolean", "description": "用户确认后再置 true 真正执行回滚"},
            },
            "required": ["reason"],
        },
    },
    # ---- 外部信息获取（第四批）：补齐"模型无工具可调只能拒答"的缺口 ----
    # 截图实证：问"今天北京天气"→ 模型答"我无法访问外部数据"。根因不是模型不行，
    # 而是没给它检索类工具，它只能硬答。故补 web_fetch / web_search。
    {
        "name": "web_fetch",
        "description": "抓取指定 URL 的内容（自动去脚本/样式、抽正文、截断，失败自动重试）。"
                       "用于获取公开网页、公告、天气接口、API JSON 等外部信息。需要联网。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "完整 URL，如 https://www.weather.com.cn/..."},
                "max_chars": {"type": "integer", "description": "最多返回字符数，默认 6000"},
                "mode": {"type": "string", "description": "text=抽正文（默认，适合网页）；"
                                                          "raw=保留原文（适合 API JSON）"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "联网搜索关键词，返回若干条标题+摘要+链接。当问题涉及实时信息"
                       "（天气、新闻、股价、政策、外部资料）而本地知识库没有时使用。"
                       "内置多引擎自动降级，若整体不可用会明确告知（此时不要凭记忆编造）。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回条数，默认 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_data",
        "description": "查询 O2OA 数据中心的自定义数据表。需要提供表名与可选过滤条件。",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "数据表名或标识"},
                "filter": {"type": "string", "description": "过滤条件（可选）"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 10"},
            },
            "required": ["table"],
        },
    },
    # ---- 自主技能（skills）：让模型能发现/读取/创建/执行技能 ----
    {
        "name": "skills_list",
        "description": "列出当前可用的自主技能（skills）清单，含名称与一句话用途。当用户需要知道自己能复用哪些预设流程、或想了解有哪些现成技能时使用。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "skills_get",
        "description": "读取某个技能的完整内容（含指引正文），用于了解该技能的具体步骤与写法。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "技能名称"}},
            "required": ["name"],
        },
    },
    {
        "name": "skills_create",
        "description": "创建一个新的自主技能：把一套可复用的工作指引固化成文件，供以后 skills_list/skills_run 复用。当用户希望你记住某种流程、或总结出最佳实践时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能标识（英文/数字/下划线）"},
                "description": {"type": "string", "description": "一句话说明这个技能做什么"},
                "content": {"type": "string", "description": "技能的具体指引正文（markdown）"},
            },
            "required": ["name", "description", "content"],
        },
    },
    {
        "name": "skills_run",
        "description": "执行（应用）某个已存在的技能：返回该技能的指引，请按其步骤完成任务。当用户说'按某某技能做'或直接要求执行某流程时使用。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "技能名称"}},
            "required": ["name"],
        },
    },
    # ---- 知识沉淀 / 反馈闭环（第一批改进）----
    {
        "name": "kb_save",
        "description": "把有价值的信息沉淀进本地知识库（自动分块向量化，之后所有用户可用 kb_search 检索到）。"
                       "当用户说'记住这个/保存到知识库/沉淀成文档'，或对话中出现值得长期保留的制度、经验、决议、结论时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "文档标题（简明概括内容）"},
                "content": {"type": "string", "description": "文档正文（完整内容，不要省略）"},
                "category": {"type": "string", "description": "分类标签，默认'智能助手沉淀'"},
                "public": {"type": "boolean", "description": "是否公共可见，默认 true；false 则仅本人与管理员可见"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "feedback",
        "description": "记录用户对智能助手/系统的反馈（点赞、不满、改进建议），供管理员在后台查看并闭环。"
                       "当用户表达'好用/不好用/希望改进/提个意见'等情绪或建议时主动使用，并如实保留用户原话。",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "反馈内容"},
                "kind": {"type": "string", "description": "类型：like（好评）/ dislike（不满）/ suggestion（建议），默认 suggestion"},
            },
            "required": ["content"],
        },
    },
    # ---- 行动能力 / 写回（第三批）：白名单 + 会话内二次确认 + 审计 ----
    # ---- 重型子任务委派（第四批：Bionic 干净会话）----
    {
        "name": "bionic_cli",
        "description": "把一件独立的、需要专注推理的重型子任务，交给后台一个干净的新会话执行，"
                       "取回结果继续作答。适合：长文摘要/审阅、代码审查、多步推理、"
                       "大段资料提取归纳。★ 不适合简单问题（直接答更快），"
                       "也不要把整个用户问题原样丢进去（只丢其中需要独立处理的那一块）。"
                       "同一轮对话最多用几次，用完就基于结果作答。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "交给后台执行的完整任务指令"
                                                           "（要自包含：背景+要求+输出格式）"},
                "system": {"type": "string", "description": "可选角色设定，如'你是资深合同审阅律师'"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "write_data",
        "description": "向 O2OA 数据中心的数据表写入或更新一行数据（写回操作，受表白名单与二次确认保护）。"
                       "★ 必须两步执行：第一步调用本工具（不带 confirm）让系统生成写回预案；"
                       "第二步把系统返回的预案转述给用户，用户明确同意后再调用（confirm=true、参数不变）执行。"
                       "严禁跳过第一步、严禁自行编造预案文本（未经系统生成的预案在 confirm 时会被拒绝并要求重来）。"
                       "用户拒绝或要求修改时，不得执行。",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "数据表标识（须在写回白名单内，建议用 alias 英文标识）"},
                "data": {"type": "object", "description": "要写入的行数据。键必须是表的英文字段名（如 productName、amount），"
                                                          "不要用中文描述词当键；不清楚字段时可先用较小数据试探，错误信息会返回字段字典"},
                "action": {"type": "string", "description": "create=新增一行（默认）；update=更新一行（须提供 row_id）"},
                "row_id": {"type": "string", "description": "update 时的目标行 id"},
                "confirm": {"type": "boolean", "description": "第二步：用户已在对话中明确同意预案后置 true"},
            },
            "required": ["table", "data"],
        },
    },
    # ---- 设计态能力（Phase A）：门户页 / 动态表 / 数据应用 / 门户 ----
    # 四层安全闸：① 角色闸门 ② 草稿不落地(confirm=false只出提案) ③ 过程授权(人类确认即授权)
    # ④ 落地前快照+审计+可回滚。参数全平铺，避免嵌套对象（弱模型易把嵌套拼进字符串）。
    {
        "name": "design_op",
        "description": "设计态操作：在 O2OA 中创建/修改/删除 门户页、动态表、数据应用、门户。"
                       "这是结构性变更，必须两步执行：第一步（不带 confirm）生成提案（不改动任何系统）；"
                       "第二步把提案完整转述给用户，用户明确授权后再调用（confirm=true、其余参数不变）执行。"
                       "绝不自行编造预案；删除操作会特别提示风险。kind 取值：portal(门户)/page(门户页)/"
                       "data_app(数据应用)/dynamic_table(动态表)。action 取值：create/update/delete。",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "portal=门户 / page=门户页 / data_app=数据应用 / dynamic_table=动态表"},
                "action": {"type": "string", "description": "create=新建 / update=修改 / delete=删除"},
                "target_id": {"type": "string", "description": "update/delete 时的目标标识（门户id/页面id/数据应用id/表flag）"},
                "parent_id": {"type": "string", "description": "create 时所属父级：新建门户页填门户id；新建动态表填数据应用id"},
                "name": {"type": "string", "description": "create 时的名称"},
                "alias": {"type": "string", "description": "create 时的别名（英文标识，可选）"},
                "draft_json": {"type": "object", "description": "create/update 时的内容（JSON 对象）。"
                                                              "门户页 update：页面对象；动态表 create：{\"fieldList\":[{\"name\",\"type\",\"description\"}]}；"
                                                              "数据应用/门户：对应实体对象"},
                "confirm": {"type": "boolean", "description": "第二步：用户已在对话中明确同意预案后置 true"},
                "note": {"type": "string", "description": "备注（用于审计说明）"},
            },
            "required": ["kind", "action"],
        },
    },
    {
        "name": "design_rollback",
        "description": "回滚上一次 design_op 的设计态变更（对应四层闸第④层）。"
                       "create 的回滚=删除新建的实体；update 的回滚=恢复修改前的定义；"
                       "delete 的回滚较复杂，会保留删除前快照供你在设计器手动重建。"
                       "同样两步：第一步（不带 confirm）出回滚提案；第二步 confirm=true 执行。",
        "parameters": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "用户明确同意回滚后置 true"},
            },
            "required": [],
        },
    },
    # ---- 多层记忆 · 成长感知（知识库持续入库 / 经验反思合成 / 成长账本）----
    {
        "name": "kb_ingest",
        "description": "把本地文件/目录持续灌入知识库（自动分块向量化，之后所有人可用 kb_search 检索）。"
                       "用于把 O2OA 技术说明书、操作手册、版本说明、业务资料、对话沉淀等纳入多层记忆体系。"
                       "两步：第一步（不带 confirm）预览将入库的文件清单与分层；第二步用户确认后 confirm=true 执行。"
                       "category 决定记忆分层：o2oa_manual(说明书)/o2oa_api(API目录)/o2oa_ops(运维方案)/"
                       "o2oa_version(版本纪要)/ops_experience(经验)/business_process(业务SOP)/ai_synthesis(合成知识)。"
                       "仅 analyst/manager 可发起。",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "待入库的文件或目录路径列表（支持 .md/.txt/.json/.html）"},
                "category": {"type": "string", "description": "记忆分层标签，默认 o2oa_ops"},
                "confirm": {"type": "boolean", "description": "用户明确同意入库后置 true"},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "kb_reflect",
        "description": "成长感知核心：基于已沉淀的『操作经验(ops_experience)』与『用户反馈(feedbacks)』，"
                       "用大模型提炼可复用的业务规则/SOP/避坑清单，合成新知识写入 ai_synthesis 层，闭环 RAG。"
                       "两步：第一步（不带 confirm）生成反思草案预览；第二步用户确认后 confirm=true 落盘为知识库文档。"
                       "仅 analyst/manager 可发起。",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "反思聚焦主题（留空=对近期经验总体提炼）"},
                "confirm": {"type": "boolean", "description": "用户明确同意落盘后置 true"},
            },
            "required": [],
        },
    },
    {
        "name": "growth_report",
        "description": "成长感知账本：汇报当前多层记忆体系的规模与成长状态——各分层文档数、向量块数、"
                       "用户反馈统计、历次入库/反思事件，并给出下一步建议（如哪些层待补充）。只读，所有角色可用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

_BUILTIN_SPEC = {t["name"]: t for t in BUILTIN_TOOLS}

# O2OA REST 专用 HTTP 客户端（隔离全局 _client 的 cookie jar，防 x-token 串身份；
# _o2_rest/_call 每次请求前 clear，见 _o2_rest 文档）
_o2_http = httpx.Client(timeout=60, trust_env=False)


def _o2_rest(path, method="GET", body=None, timeout=30, user_token=""):
    """调用 O2OA 自身 REST（网关照会 O2OA 的容器/宿主地址）。
    user_token 非空时以该用户身份调用（服务端按其权限强制过滤，权限闭环）；
    为空则以服务号身份（o2oa_token() 自动登录续期），401/404 时刷新 token 重试一次。
    ★ 2026-09-19 认知更正：O2OA 正确 REST 路径以 /o2_core/o2/xAction/services/*.json
    服务描述为准（如 task/list/my/paging/{p}/size/{s}）；此前"业务模块 404"实为
    路径写错（list/paging/{p}/{s} 不存在 → Jetty 404 HTML），并非身份门控。
    ★ 2026-09-19 cookie 污染修复：O2OA 会对带 x-token 的响应回写 Set-Cookie，全局
    httpx Client 的 cookie jar 会残留"上一个用户"的 x-token，且 O2OA 端 Cookie 优先
    于 Header → 后续请求身份被悄悄换成别人（第三批 write_data 以服务号执行却报
    "测试用户A 权限不足" 即此根因）。故 O2OA REST 使用专用 Client 并每请求清 jar。"""
    base = CFG.get("o2oa_base") or "http://127.0.0.1:9090"

    def _call(tok):
        headers = {"Content-Type": "application/json"}
        if tok:
            headers["x-token"] = tok
        url = f"{base}{path}"
        try:
            _o2_http.cookies.clear()
            if method.upper() == "GET":
                r = _o2_http.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "PUT":
                r = _o2_http.put(url, headers=headers, json=body or {}, timeout=timeout)
            elif method.upper() == "DELETE":
                r = _o2_http.request("DELETE", url, headers=headers, timeout=timeout)
            else:
                r = _o2_http.post(url, headers=headers, json=body or {}, timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            return 0, f"O2_REST_ERROR: {e}"

    if user_token:
        return _call(user_token)
    tok = o2oa_token()
    code, text = _call(tok)
    if code in (401, 404) and tok:
        # token 失效（cipher/会话 token 过期、O2OA 重启）→ 强制重新登录重试一次
        tok2 = o2oa_token(force=True)
        if tok2 and tok2 != tok:
            code, text = _call(tok2)
    return code, text


def _safe_eval(expr):
    """极简安全求值：只放行数字与白名单运算符/函数，不用 eval 的裸用法。"""
    import ast
    allowed_ops = {
        ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b, ast.USub: lambda a: -a, ast.UAdd: lambda a: +a,
    }
    allowed_fns = {
        "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    }

    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.Call):
            fn = getattr(node.func, "id", None)
            if fn in allowed_fns and not node.keywords:
                return allowed_fns[fn](*[_ev(a) for a in node.args])
        if isinstance(node, (ast.List, ast.Tuple)):
            return [_ev(e) for e in node.elts]
        raise ValueError("expression not allowed")

    return _ev(ast.parse(expr, mode="eval"))


# ---------------------------------------------------------------- 自主技能（skills）仓库
def _skill_path(name):
    """技能文件名：只允许安全字符，避免路径穿越。"""
    safe = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]", "_", str(name))[:60]
    return SKILLS_DIR / (safe + ".md")


def _parse_skill(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {"name": "", "description": "", "body": text}
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return {"name": fm.get("name", ""), "description": fm.get("description", ""), "body": m.group(2)}


def _list_skills():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for fn in sorted(os.listdir(SKILLS_DIR)):
        if fn.endswith(".md"):
            try:
                meta = _parse_skill((SKILLS_DIR / fn).read_text(encoding="utf-8"))
                out.append({"name": meta["name"] or fn[:-3], "description": meta["description"]})
            except Exception:
                pass
    return out


def _get_skill(name):
    p = _skill_path(name)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def _create_skill(name, description, content):
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    p = _skill_path(name)
    body = content or ""
    text = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
    p.write_text(text, encoding="utf-8")
    return p


def _run_skill(name):
    full = _get_skill(name)
    if not full:
        return f"ERROR: 技能 '{name}' 不存在。可先用 skills_list 查看，或用 skills_create 创建。"
    meta = _parse_skill(full)
    return ("【技能指引｜%s】\n%s\n\n请严格按照上述指引完成任务；如需调用其他工具请自行决定。"
            % (meta["name"] or name, meta["body"]))


def _o2_rest_user_or_manager(path, method="POST", body=None, user_token="", timeout=30):
    """user token 优先（服务端按其权限强制过滤）。返回 (code, text, data)：
    data 非 None = 已以用户/本人身份取到（无需再过滤）；
    data 为 None = 回落服务号（o2oa_token()）原始结果，调用方需注意其语义。"""
    if user_token:
        code, text = _o2_rest(path, method=method, body=body, timeout=timeout, user_token=user_token)
        try:
            data = json.loads(text).get("data")
        except Exception:
            data = None
        if code == 200 and data is not None:
            return code, text, data if isinstance(data, list) else [data]
        log(f"o2 user_token fallback HTTP {code} {path[:60]}")
    code, text = _o2_rest(path, method=method, body=body, timeout=timeout)
    return code, text, None


# ---------------------------------------------------------------- 第三批：角色人设
# 三段人设（对照设计逻辑评估报告 P2）：向导=普通用户 / 分析师=数据岗 / 参谋=管理员
PERSONAS = {
    "user": ("向导",
             "语气亲切友好，回答简洁、多用步骤化指引；聚焦帮用户完成日常事务"
             "（查待办、找同事、搜资料），不主动谈及系统管理、数据表与配置细节。"),
    "analyst": ("分析师",
                "回答以数据与事实为依据，主动说明数据口径与局限；涉及数量/统计问题时"
                "优先用 query_rows/query_table_list 等工具取证后再回答，不做无依据的估计；"
                "可协助录入数据（write_data，务必走二次确认）。"),
    "manager": ("参谋",
                "面向系统管理员：专业严谨、考虑周全，可从组织、流程、数据全局视角给出建议；"
                "涉及敏感操作时主动提示风险与影响面。"),
}


def o2_user_info(user_token):
    """一次调用取当前用户的角色/人员 DN/姓名。
    ★ 人员 DN 是会话归属的关键：O2OA AI 模块查会话列表时按 personList=[人员DN] 过滤，
    因此 clue 记录必须带 DN，仅存姓名会导致历史记录永远匹配不到（实测踩坑）。
    返回 (roles, dn, name)；失败返回 ([], "", "")。"""
    if not user_token:
        return [], "", ""
    try:
        code, text = _o2_rest("/x_organization_assemble_authentication/jaxrs/authentication",
                              method="GET", user_token=user_token)
        d = json.loads(text).get("data") or {}
        person = d.get("person") if isinstance(d.get("person"), dict) else {}
        roles = [str(r).split("@")[0].strip().lower() for r in (d.get("roleList") or []) if r]
        dn = (d.get("distinguishedName") or person.get("distinguishedName") or "").strip()
        nm = (d.get("name") or person.get("name") or "").strip()
        log(f"o2_user_info HTTP {code} roles={roles} dn={dn[:12]} name={nm}")
        return roles, dn, nm
    except Exception as e:
        log(f"o2_user_info err: {e}")
        return [], "", ""


def persona_from_roles(roles):
    """按角色集合判人设；roles=None（无 token/查询失败）→ ""（中性，不启用白名单）。"""
    if not CFG.get("persona_enable") or roles is None:
        return ""
    rs = {str(r).lower() for r in roles}
    if rs & {r.lower() for r in CFG.get("persona_manager_roles") or []}:
        return "manager"
    if rs & {r.lower() for r in CFG.get("persona_analyst_roles") or []}:
        return "analyst"
    return "user"


def o2_user_roles(user_token):
    """以 user token 调 GET /jaxrs/authentication 取当前用户 roleList
    （实测该接口返回 roleList/identityList 等，role 形如 '分析师@aiAnalyst@R'）。"""
    return o2_user_info(user_token)[0]


def persona_of(user_token):
    """第三批：按 O2OA 角色判定人设。user（默认）/ analyst / manager；
    无 token（旧前端）返回 ""（中性，不启用人设与白名单，保持既有语义）。"""
    if not CFG.get("persona_enable") or not user_token:
        return ""
    return persona_from_roles(o2_user_roles(user_token))


def trace_publish(clue_id, steps):
    """第四批：把本轮工具链轨迹写入 kv，供 /gateway/trace 观测与排障。
    steps = [(tool_name, ok_bool), ...]；仅保留最近 50 条会话的轨迹。"""
    try:
        if not clue_id:
            return
        with db() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                      (f"trace:{clue_id}",
                       json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                   "steps": [{"tool": n, "ok": bool(o)} for n, o in steps]},
                                  ensure_ascii=False)))
            # 只留最近 50 条 trace，避免 kv 无界增长
            c.execute("DELETE FROM kv WHERE k LIKE 'trace:%' AND k NOT IN "
                      "(SELECT k FROM kv WHERE k LIKE 'trace:%' ORDER BY k DESC LIMIT 50)")
    except Exception as e:
        log(f"trace_publish fail: {e}")


def audit_log(person, clue_id, tool, payload, status, detail=""):
    """第三批：写回/敏感动作审计（/gateway/audit 可查）。"""
    try:
        with db() as c:
            c.execute("INSERT INTO audit_log(ts,person,clue_id,tool,payload,status,detail) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (time.strftime("%Y-%m-%d %H:%M:%S"), person or "", clue_id or "",
                       tool, json.dumps(payload, ensure_ascii=False)[:2000] if payload else "",
                       status, str(detail)[:2000]))
    except Exception as e:
        log(f"audit_log err: {e}")


def o2_table_schema(flag, force=False):
    """取数据表 schema（name/alias/fieldList），供 write_data 白名单归一化与字段字典。
    kv 缓存 10 分钟。失败返回 None。"""
    key = f"table_schema:{flag}"
    if not force:
        cached = kv_get(key)
        if cached:
            try:
                c = json.loads(cached)
                if time.time() - float(c.get("ts") or 0) < 600:
                    return c.get("schema")
            except Exception:
                pass
    try:
        code, text = _o2_rest(f"/x_query_assemble_designer/jaxrs/table/{flag}", method="GET")
        d = (json.loads(text).get("data") or {})
        if not d:
            return None
        draft = json.loads(d.get("draftData") or "{}")
        schema = {"name": d.get("name") or "", "alias": d.get("alias") or "",
                  "fields": [{"name": f.get("name"), "type": f.get("type"),
                              "desc": f.get("description") or ""}
                             for f in (draft.get("fieldList") or []) if f.get("name")]}
        with db() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                      (key, json.dumps({"ts": time.time(), "schema": schema},
                                       ensure_ascii=False)))
        return schema
    except Exception as e:
        log(f"o2_table_schema err: {e}")
        return None


def _schema_desc(sch):
    if not sch:
        return ""
    fields = "、".join(
        f"{f['name']}({f.get('type','')}" + (f",{f['desc']}" if f.get("desc") else "") + ")"
        for f in sch.get("fields") or [])
    nm, al = sch.get("name") or "", sch.get("alias") or ""
    return f"「{nm}」(alias:{al}) 字段：{fields}"


# ================================================================
# 第五批：系统内 agent 能力（定位纠偏 —— 只吃 O2OA 自己的数据）
# ----------------------------------------------------------------
# 设计原则：本系统是「把 Bionic 的 agent 能力在 O2OA 内落地」，不是公网检索器。
# 因此这里所有工具的数据源都来自 O2OA 自身的业务模块：
#   待办/已办（processplatform）、组织架构（organization）、
#   公文与信息（cms）、数据表（query）、流程应用（processplatform）
# 路径全部以 war 包 describe/sources 内的 Java 源码为权威依据（见文档第十二节）。
# ================================================================
# 业务模块 REST 前缀
_O2_PP = "/x_processplatform_assemble_surface/jaxrs"   # 流程平台 surface
_O2_ORG = "/x_organization_assemble_control/jaxrs"    # 组织架构 control
_O2_QRY = "/x_query_assemble_surface/jaxrs"           # 数据中心 surface
_O2_CMS = "/x_cms_assemble_control/jaxrs"             # 内容管理


def _o2_call(path, method="GET", body=None, person="", token=""):
    """统一 O2OA 业务模块调用。返回 (ok, json_or_text, http_status)。
    ★ token（真实用户会话）非空时直接以本人身份调用（服务端按其权限强制过滤，权限闭环），
      不再执行 switchuser；switchuser 仅用于「无用户 token、仅凭 person 名模拟指定人」的管理场景。
    注意：O2OA Cookie 优先于 Header，每次调用前必须清 cookie（历史坑）。"""
    try:
        base = CFG.get("o2oa_base", "http://127.0.0.1:9090")
        if token:
            # ★ 真实用户会话 token：直接以本人身份调用，权限由 O2OA 服务端按 token 强制过滤，
            #   这是「根据登录身份访问对应权限项目和资料」的闭环关键，绝不走服务号/模拟。
            tk = token
        else:
            # 无用户 token：用网关服务号身份；若传了 person（用户名）则 switchuser 模拟该人
            # （管理视角，例如参谋查看他人待办）。
            tk = o2oa_token()
            if not tk:
                return False, "O2OA 会话获取失败（服务号登录不上，请检查 o2oa_svc_user/pwd）", 0
            if person:
                _o2_http.cookies.clear()
                r = _o2_http.put(f"{base}/x_organization_assemble_authentication/jaxrs/authentication/switchuser",
                                 headers={"x-token": tk}, json={"credential": person}, timeout=25)
                if r.status_code == 200:
                    sw = (r.json().get("data") or {}).get("token")
                    if sw:
                        tk = sw
                else:
                    log(f"switchuser {person} -> HTTP {r.status_code}: {r.text[:120]}")
        _o2_http.cookies.clear()
        h = {"x-token": tk, "Content-Type": "application/json"}
        url = base + path
        m = method.upper()
        if m == "GET":
            r = _o2_http.get(url, headers=h, timeout=30)
        elif m == "POST":
            r = _o2_http.post(url, headers=h, json=body if body is not None else {}, timeout=30)
        elif m == "PUT":
            r = _o2_http.put(url, headers=h, json=body if body is not None else {}, timeout=30)
        elif m == "DELETE":
            r = _o2_http.delete(url, headers=h, timeout=30)
        else:
            return False, f"不支持的 method: {method}", 0
        try:
            return r.status_code == 200, r.json(), r.status_code
        except Exception:
            return r.status_code == 200, r.text, r.status_code
    except Exception as e:
        log(f"_o2_call {path} err: {e}")
        return False, f"调用异常：{e}", 0


def _o2_data_ok(j, ok, status, err_prefix="查询"):
    """统一把 O2OA 返回包成「给模型读的字符串」。
    ★ 返回 (is_error, err_msg)：调用方必须写 `if err: return err`，
      不要用 `if bad:` 的旧式写法（成功时 msg 为空串，易被误判为失败）。"""
    if isinstance(j, dict) and j.get("type") == "error":
        return True, f"{err_prefix}失败（HTTP {status}）：{j.get('message') or ''}"
    if not ok:
        return True, f"{err_prefix}失败（HTTP {status}）"
    return False, ""


# ---------------------------------------------------------------- 待办 / 已办
def todo_list_impl(person="", page=1, size=10, scope="my", user_token=""):
    """待办列表。scope=my 时用「以该用户身份」拉取其个人待办；
    服务号自身无待办，故 person 为空时返回提示。"""
    if scope == "my":
        if not person:
            return "ERROR: 需要指定用户身份才能查询个人待办。"
        path = f"{_O2_PP}/task/list/my/paging/{int(page)}/size/{int(size)}"
        ok, j, st = _o2_call(path, person=person, token=user_token)
    else:  # 管理视角：全部待办（需管理权限）
        path = f"{_O2_PP}/task/list/{'' if page==1 else ''}next/1/count/{int(size)}"
        ok, j, st = _o2_call(f"{_O2_PP}/task/list/person/{person}/exclude/draft/false/manage"
                             if person else f"{_O2_PP}/task/list/{0}/next/{int(size)}/manage")
    err, msg = _o2_data_ok(j, ok, st, "待办查询")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return f"「{person or '当前用户'}」当前没有待办。"
    lines = [f"「{person or '当前用户'}」共有 {len(items)} 条待办（第 {page} 页）："]
    for i, t in enumerate(items, 1):
        label = (t.get("title") or t.get("workTitle") or t.get("activityName")
                 or t.get("serial") or "(无标题)")
        an = t.get("activityName") or ""
        app = t.get("applicationName") or t.get("applicationAlias") or ""
        pn = t.get("processName") or t.get("processAlias") or ""
        ct = (t.get("startTime") or t.get("createTime") or "")[:19]
        lines.append(f"[{i}] {label}"
                     f"\n    活动：{an}｜流程：{pn}｜应用：{app}"
                     f"\n    到达：{ct}｜发起人：{t.get('creatorPerson') or ''}"
                     f"\n    taskId：{t.get('id') or ''}")
    return "\n".join(lines)


def todo_detail_impl(task_id, person="", user_token=""):
    """待办详情。★ 真实返回结构（实测 2026-09-21）：
       data.task            = 待办本体（activityName 才是"标题"，title 常为 null；
                              routeNameList = 可走路由，opinion = 已有意见）
       data.work            = 工作本体（表单数据在 work.data）
       data.attachmentList  = 附件
       data.workLogList     = 流转日志
    """
    if not task_id:
        return "ERROR: task_id 不能为空"
    ok, j, st = _o2_call(f"{_O2_PP}/task/{task_id}/reference", person=person, token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "待办详情")
    if err:
        return msg
    d = (j.get("data") if isinstance(j, dict) else j) or {}
    task = d.get("task") or {}
    work = d.get("work") or {}
    if not task:
        return f"未找到待办 {task_id}（可能已被处理或无权访问）。"
    label = (task.get("title") or task.get("activityName")
             or task.get("activityAlias") or task.get("serial") or "(无标题)")
    lines = [f"【待办详情】{label}",
             f"活动：{task.get('activityName') or ''}"
             f"｜流程：{task.get('processName') or task.get('processAlias') or ''}"
             f"｜应用：{task.get('applicationName') or task.get('applicationAlias') or ''}",
             f"发起人：{task.get('creatorPerson') or ''}"
             f"｜到达：{(task.get('startTime') or task.get('createTime') or '')[:19]}"
             f"｜流水号：{task.get('serial') or ''}"]
    if task.get("activityDescription"):
        lines.append(f"活动说明：{task['activityDescription']}")
    # 可走路由（模型据此建议下一步；实际流转需用户确认）
    routes = task.get("routeNameList") or []
    if routes:
        lines.append("\n可走路由（供建议，实际流转需用户确认）：")
        for r in routes:
            lines.append(f"  - {r}")
    if task.get("opinion"):
        lines.append(f"\n当前意见：{str(task['opinion'])[:300]}")
    # 表单数据（在 work.data）
    data = work.get("data") or {}
    if isinstance(data, dict) and data:
        lines.append("\n表单数据：")
        for k, v in list(data.items())[:30]:
            if k.startswith("$"):
                continue
            lines.append(f"  {k}: {str(v)[:200]}")
    # 附件
    atts = d.get("attachmentList") or []
    if atts:
        lines.append(f"\n附件（{len(atts)} 个）：")
        for a in atts[:10]:
            lines.append(f"  - {a.get('name') or ''}（id:{a.get('id') or ''}）")
    # 流转日志
    logs = d.get("workLogList") or []
    if logs:
        lines.append(f"\n流转记录（最近 {min(len(logs),5)} 条）：")
        for lg in logs[-5:]:
            lines.append(f"  - {(lg.get('arrivedActivityName') or '')}"
                         f" @{(lg.get('arrivedTime') or '')[:19]}"
                         f"（{lg.get('person') or ''}）")
    return "\n".join(lines)


def todo_done_impl(person="", page=1, size=10, user_token=""):
    """已办列表。"""
    if not person:
        return "ERROR: 需要指定用户身份才能查询个人已办。"
    ok, j, st = _o2_call(f"{_O2_PP}/taskcompleted/list/my/paging/{int(page)}/size/{int(size)}",
                         person=person, token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "已办查询")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return f"「{person}」当前没有已办记录。"
    lines = [f"「{person}」共有 {len(items)} 条已办（第 {page} 页）："]
    for i, t in enumerate(items, 1):
        label = (t.get("title") or t.get("activityName") or t.get("serial") or "(无标题)")
        lines.append(f"[{i}] {label}"
                     f"\n    活动：{t.get('activityName') or ''}"
                     f"｜流程：{t.get('processName') or t.get('processAlias') or ''}"
                     f"\n    完成：{(t.get('completedTime') or t.get('updateTime') or t.get('createTime') or '')[:19]}"
                     f"\n    id：{t.get('id') or ''}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 组织架构
def org_search_impl(keyword, kind="person", user_token=""):
    """组织架构检索。kind=person/unit/identity。
    按 war 契约：三者都有 PUT list/like（按名称模糊查询）。"""
    kw = (keyword or "").strip()
    if not kw:
        return "ERROR: keyword 不能为空"
    kw = kw.strip()
    kind = (kind or "person").lower()
    m = {"person": ("person", "人员"), "unit": ("unit", "组织"), "identity": ("identity", "身份")}
    if kind not in m:
        return f"ERROR: kind 只支持 person/unit/identity，收到 {kind}"
    seg, cn = m[kind]
    ok, j, st = _o2_call(f"{_O2_ORG}/{seg}/list/like", method="PUT", body={"key": kw},
                         token=user_token)
    err, msg = _o2_data_ok(j, ok, st, f"{cn}检索")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return f"组织架构中没有匹配「{kw}」的{cn}。"
    lines = [f"匹配「{kw}」的{cn}（{len(items)} 个）："]
    for i, o in enumerate(items[:20], 1):
        nm = o.get("name") or ""
        fl = o.get("unique") or o.get("distinguishedName") or o.get("id") or ""
        extra = ""
        if kind == "person":
            sf = o.get("superior") or ""
            extra = f"（主部门：{sf}）" if sf else ""
        elif kind == "unit":
            extra = f"（类型：{o.get('typeList') or ''}）"
        lines.append(f"[{i}] {nm}{extra}\n    标识：{fl}")
    return "\n".join(lines)


def org_unit_tree_impl(unit_flag="", user_token=""):
    """组织结构树。unit_flag 为空时列顶层组织；否则列其直接/递归下级。"""
    if unit_flag:
        ok, j, st = _o2_call(f"{_O2_ORG}/unit/list/{unit_flag}/sub/nested", token=user_token)
    else:
        ok, j, st = _o2_call(f"{_O2_ORG}/unit/list/top", token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "组织查询")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return "未查询到组织信息。"
    title = f"「{unit_flag}」的下级组织" if unit_flag else "顶层组织"
    lines = [f"{title}（{len(items)} 个）："]
    for i, u in enumerate(items[:40], 1):
        lines.append(f"[{i}] {u.get('name') or ''}"
                     f"（直属身份 {u.get('subDirectIdentityCount', 0)}，直属下级 "
                     f"{u.get('subDirectUnitCount', 0)}）\n    标识：{u.get('id') or ''}")
    return "\n".join(lines)


def org_person_identity_impl(person_flag, user_token=""):
    """某人的身份（含组织、职务）。调 identity/list/person/{personFlag}。"""
    if not person_flag:
        return "ERROR: person 不能为空"
    ok, j, st = _o2_call(f"{_O2_ORG}/identity/list/person/{person_flag}", token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "身份查询")
    if err:
        return f"{msg}（注意：person_flag 必须是人员的 unique/id，不是姓名）"
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return f"「{person_flag}」没有身份记录。"
    lines = [f"「{person_flag}」的身份（{len(items)} 个）："]
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] {it.get('name') or ''}"
                     f"｜单位：{it.get('unitName') or it.get('unit') or ''}"
                     f"｜职务：{it.get('unitDutyName') or ''}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 公文 / 信息发布（CMS）
def cms_list_impl(keyword="", page=1, size=10, user_token=""):
    """公文/信息发布检索（按 war 契约：PUT filter/list/{page}/size/{size}）。
    ★ 该接口默认只返回「已发布」文档；渠道（栏目）可用 cms_channels_impl 查。"""
    path = f"{_O2_CMS}/document/filter/list/{int(page)}/size/{int(size)}"
    body = {}
    if keyword:
        body = {"title": keyword, "keyword": keyword}
    ok, j, st = _o2_call(path, method="PUT", body=body, token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "公文检索")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return ("未检索到已发布的公文/信息文档。"
                + (f"（关键词：{keyword}）" if keyword else "")
                + "。可用 cms_channels 查看有哪些信息栏目，或确认文档是否已发布。")
    lines = [f"公文/信息文档（{len(items)} 篇）："]
    for i, d in enumerate(items[:20], 1):
        lines.append(f"[{i}] {d.get('title') or '(无标题)'}"
                     f"\n    栏目：{d.get('categoryName') or ''}｜应用：{d.get('appName') or ''}"
                     f"\n    发布：{(d.get('publishTime') or d.get('createTime') or '')[:19]}"
                     f"｜作者：{d.get('creatorPerson') or ''}"
                     f"\n    id：{d.get('id') or ''}")
    return "\n".join(lines)


def cms_channels_impl(user_token=""):
    """列出当前用户有权限查看的信息栏目（分类）及其应用归属。
    用于'系统里有哪些信息栏目/公文分类'，或为 cms_list 定位栏目。"""
    ok, j, st = _o2_call(f"{_O2_CMS}/appinfo/list/user/view", token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "栏目查询")
    if err:
        return msg
    apps = (j.get("data") if isinstance(j, dict) else j) or []
    if not apps:
        return "没有可查看的信息栏目。"
    lines = [f"可查看的信息栏目（{len(apps)} 个应用）："]
    for a in apps[:20]:
        lines.append(f"· 应用「{a.get('appName') or ''}」")
        for c in (a.get("wrapOutCategoryList") or [])[:15]:
            lines.append(f"    - 栏目：{c.get('categoryName') or ''}"
                         f"（类型：{c.get('documentType') or ''}）"
                         f"｜id：{c.get('id') or ''}")
    return "\n".join(lines)


def cms_detail_impl(doc_id, user_token=""):
    """公文/信息文档详情。★ 返回结构是嵌套的：
       data.document = 元数据（标题/栏目/作者/发布时间）
       data.data     = 表单数据（含 $attachmentList 附件），正文往往在某个字段里。
    """
    if not doc_id:
        return "ERROR: doc_id 不能为空"
    ok, j, st = _o2_call(f"{_O2_CMS}/document/{doc_id}", token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "公文详情")
    if err:
        return msg
    d = (j.get("data") if isinstance(j, dict) else j) or {}
    doc = d.get("document") or {}
    if not doc:
        return f"未找到文档 {doc_id}（可能未发布或无权访问）。"
    lines = [f"【公文/信息文档】{doc.get('title') or ''}",
             f"栏目：{doc.get('categoryName') or ''}｜应用：{doc.get('appName') or ''}"
             f"｜类型：{doc.get('documentType') or ''}",
             f"作者：{doc.get('creatorPersonShort') or doc.get('creatorPerson') or ''}"
             f"｜发布：{(doc.get('publishTime') or doc.get('createTime') or '')[:19]}"
             f"｜状态：{doc.get('docStatus') or ''}"]
    if doc.get("summary"):
        lines.append(f"摘要：{doc['summary']}")
    # 表单数据：正文/正文类字段（CMS 发布类表单字段名不固定，逐个挑长得像正文的）
    fdata = d.get("data") or {}
    if isinstance(fdata, dict):
        body_candidates = []
        for k, v in fdata.items():
            if k.startswith("$"):
                continue
            if isinstance(v, str) and len(v) > 80 and ("<" in v or len(v) > 200):
                body_candidates.append((k, v))
        if body_candidates:
            for k, v in body_candidates[:2]:
                txt = html_to_text(v, 4000)
                lines.append(f"\n正文（字段 {k}）：\n{txt}")
        else:
            simple = {k: v for k, v in fdata.items()
                      if not k.startswith("$") and isinstance(v, (str, int, float))}
            if simple:
                lines.append("\n数据字段：")
                for k, v in list(simple.items())[:20]:
                    lines.append(f"  {k}: {str(v)[:200]}")
    # 附件
    atts = (d.get("data") or {}).get("$attachmentList") or doc.get("attachmentList") or []
    if atts:
        lines.append(f"\n附件（{len(atts)} 个）：")
        for a in atts[:10]:
            lines.append(f"  - {a.get('name') or ''}（id:{a.get('id') or ''}）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 数据表（数据中心）
def query_table_list_impl(user_token="", keyword=""):
    """列出数据中心所有自建表（name/alias/id + 应用）。
    keyword 非空时按名称/别名模糊过滤 —— ★ 弱模型读不下 75 行清单，
    必须支持"我大概知道叫啥"的定向查找，否则它会在长清单里挑错标识。"""
    ok, j, st = _o2_call(f"{_O2_QRY}/table/list/paging/1/size/200",
                         method="POST", body={}, token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "数据表列表")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return "数据中心还没有自建表。"
    kw = (keyword or "").strip().lower()
    if kw:
        items = [t for t in items
                 if kw in str(t.get("name") or "").lower()
                 or kw in str(t.get("alias") or "").lower()]
        if not items:
            return (f"没有名称或别名包含「{keyword}」的自建表。"
                    "请换一个更短的关键词再试（如只取英文词根 'order'），"
                    "或留空 keyword 取全部表清单。")
    # ★ 输出形态为「查表」服务（2026-09-21 实测）：模型在 101 行清单里找不到表，
    #   因为它按表名找（t5005003_...），而它心里想的是 alias（aiDemoOrders）。
    #   故每行**以 table_flag（可直接用的标识）开头**，让"用哪个字符串去查"一眼可见。
    head = (f"匹配「{keyword}」的自建表（{len(items)} 张）" if kw
            else f"数据中心自建表（{len(items)} 张）")
    lines = [head + "。★ 查数据时 table_flag 用每行【】里的值："]
    for i, t in enumerate(items[:90], 1):
        nm = t.get("name") or ""
        al = t.get("alias") or ""
        app = t.get("queryName") or t.get("queryAlias") or ""
        flag = al or nm or t.get("id") or ""
        extra = f"　表名：{nm}" if (al and al != nm) else ""
        lines.append(f"[{i}] 【{flag}】"
                     + (f"　alias：{al}" if al else "")
                     + extra
                     + (f"　应用：{app}" if app else ""))
    return "\n".join(lines)


def query_rows_impl(table_flag, where="", limit=20, user_token=""):
    """查数据表的行。where 用 jpql 语法（o.name='xxx'），传 where 走 GET select/where，
    否则走 POST list/paging 分页。"""
    if not table_flag:
        return "ERROR: table_flag 不能为空"
    # ★ 硬护栏（2026-09-21 实测）：模型（glm-4.7-flash）会反复凭印象编表标识去查，
    #   每次都是 HTTP 500，既浪费轮次又给用户"系统里没这表"的错误印象。
    #   若标识不在真实表清单里，直接拦下并返回"该先列表"的明确指令 ——
    #   把一次注定失败的调用转化成一次有效的自我纠正。
    if not _o2_table_flag_valid(table_flag):
        return (f"ERROR: 系统中不存在标识为 '{table_flag}' 的自建表（未通过真实性校验）。\n"
                "★ 不要猜测表名。请立即改用 query_table_list 工具获取系统内**真实存在**的表清单"
                "（每行开头的【】里就是可用的 table_flag），再用其中的标识重试。")
    limit = max(1, min(int(limit or 20), 100))
    if where:
        import urllib.parse as _up
        w = _up.quote(where, safe="")
        ok, j, st = _o2_call(f"{_O2_QRY}/table/list/{table_flag}/row/select/where/{w}",
                             token=user_token)
    else:
        ok, j, st = _o2_call(f"{_O2_QRY}/table/list/table/{table_flag}/row/paging/1/size/{limit}",
                             method="POST", body={}, token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "数据查询")
    if err:
        # ★ 关键自愈提示（2026-09-21 实测踩坑）：模型常凭印象编表标识
        #   （__all_tables / o2oa_system_tables 之类），一查就 500。
        #   这里把"表标识不存在"变成一次明确的纠偏指令，逼它回到 query_table_list。
        if st == 500 or "不存在" in str(msg):
            return (f"{msg}\n★ 该表标识不存在。不要凭印象编造表名 —— "
                    "请先调用 query_table_list 获取系统内**真实存在**的自建表清单"
                    "（返回表名与 alias），再用其中的表名或 alias 作为 table_flag 重试。")
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return f"表「{table_flag}」中没有符合条件的数据。"
    # 动态表字段名不固定，取第一条的键做表头
    lines = [f"表「{table_flag}」查询结果 {len(items)} 行（where={where or '全部'}）："]
    for i, row in enumerate(items[:limit], 1):
        if isinstance(row, dict):
            kv = "，".join(f"{k}={str(v)[:80]}" for k, v in list(row.items())
                           if k not in ("id", "createTime", "updateTime"))
            lines.append(f"[{i}] id={row.get('id') or ''}｜{kv}")
        else:
            lines.append(f"[{i}] {str(row)[:200]}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 流程应用
def process_app_list_impl(user_token=""):
    """列出当前用户可见的流程应用（含可启动流程）。"""
    ok, j, st = _o2_call(f"{_O2_PP}/application/list/complex", token=user_token)
    err, msg = _o2_data_ok(j, ok, st, "流程应用查询")
    if err:
        return msg
    items = (j.get("data") if isinstance(j, dict) else j) or []
    if not items:
        return "没有可见的流程应用。"
    lines = [f"可见流程应用（{len(items)} 个）："]
    for i, a in enumerate(items[:30], 1):
        lines.append(f"[{i}] 「{a.get('name') or ''}」｜标识：{a.get('id') or ''}")
        for p in (a.get("processList") or [])[:10]:
            lines.append(f"      · 流程：{p.get('name') or ''}（id:{p.get('id') or ''}）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 知识库文档（含引用溯源）
def _fmt_ts(v):
    """把 kv/docs 里存的「epoch 秒」或「字符串时间」统一格式化为可读时间。
    历史数据里 updated 有的是 float epoch、有的是 'YYYY-mm-dd HH:MM:SS'，都得兼容。"""
    if v is None or v == "":
        return "-"
    try:
        f = float(v)
        if f > 1e8:  # 合理的 epoch 秒
            import datetime
            return datetime.datetime.fromtimestamp(f).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        pass
    return str(v)[:19]


def kb_docs_impl(perms=None, keyword="", doc_id="", user_token=""):
    """知识库治理视图。
    · 不传 doc_id：列出当前用户可见的知识库文档（可按 keyword 过滤），让模型知道"系统里有什么"
    · 传 doc_id：返回该文档的完整内容（供精读与引用）
    ★ 权限：复用 visible_docs(perms)，与 kb_search / RAG 主链路同权（管理员 perms 空=全可见）。"""
    with db() as c:
        if doc_id:
            row = c.execute("SELECT id,title,category,content,creator_person,updated "
                            "FROM docs WHERE id=?", (doc_id,)).fetchone()
            if not row:
                return f"知识库中没有 id 为 {doc_id} 的文档。"
            allow = visible_docs(perms or [])
            if allow and doc_id not in allow:
                return "你没有权限查看该文档。"
            did, title, cat, content, who, upd = row
            body = content or ""
            cap = CFG.get("web_fetch_max_chars") or 6000
            truncated = len(body) > cap
            shown = body[:cap]
            return (f"【知识库文档】《{title}》\n"
                    f"分类：{cat or '未分类'}｜创建者：{who or '-'}\n"
                    f"字数：{len(body)}｜docId：{did}\n"
                    f"（引用本答案时请注明《{title}》）\n\n{shown}"
                    + ("\n\n…（内容过长已截断，可用更具体的问题检索）" if truncated else ""))
        # 列表模式
        allow = visible_docs(perms or [])
        if keyword:
            rows = c.execute("SELECT id,title,category,length(content),creator_person,updated "
                             "FROM docs WHERE title LIKE ? OR content LIKE ? OR category LIKE ? "
                             "ORDER BY updated DESC",
                             (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")).fetchall()
        else:
            rows = c.execute("SELECT id,title,category,length(content),creator_person,updated "
                             "FROM docs ORDER BY updated DESC").fetchall()
    items = [r for r in rows if (not allow) or (r[0] in allow)]
    if not items:
        return ("知识库中没有" + (f"匹配「{keyword}」的" if keyword else "")
                + "可查看的文档。")
    lines = [f"知识库文档（{len(items)} 篇"
             + (f"，关键词：{keyword}" if keyword else "") + "）："]
    for i, (did, title, cat, clen, who, upd) in enumerate(items[:40], 1):
        when = _fmt_ts(upd)
        lines.append(f"[{i}] 《{title}》"
                     f"\n    分类：{cat or '未分类'}｜约 {clen or 0} 字｜更新：{when}"
                     f"\n    docId：{did}")
    lines.append("\n提示：要看某篇全文，用 kb_read 传它的 docId。")
    return "\n".join(lines)


def ocr_file_impl(file_id, name="", user_token=""):
    """对 O2OA 附件（图片/PDF/扫描件）做 OCR，返回识别出的文字。
    用于'这个扫描件/图片里写了什么'。file_id 来自待办附件或公文附件。"""
    if not file_id:
        return "ERROR: file_id 不能为空"
    ocr_base = CFG.get("ocr_base") or ""
    if not ocr_base:
        return "ERROR: 本系统未启用 OCR 服务（ocr_base 为空）。"
    data = o2oa_file_bytes(file_id)
    if not data:
        return f"ERROR: 无法下载附件 {file_id}（可能不存在或无权访问）。"
    ext = (name or file_id).rsplit(".", 1)[-1].lower() if "." in (name or "") else ""
    fn = name or f"{file_id}.bin"
    try:
        # ★ OCR 服务吃的是 base64 JSON（file_b64），不是 multipart —— 用 multipart 会 400
        #   "缺少 file_b64 / image_b64 / pdf_b64"（实测踩过）。
        import base64
        r = _client.post(f"{ocr_base}/ocr", timeout=300,
                         json={"file_b64": base64.b64encode(data).decode("ascii"),
                               "filename": fn})
        if r.status_code != 200:
            return f"OCR 失败（HTTP {r.status_code}）：{r.text[:200]}"
        j = r.json() or {}
        if not j.get("ok", True) and j.get("error"):
            return f"OCR 失败：{j.get('error')}"
        txt = (j.get("text") or "").strip()
        # 表格结构还原成 Markdown（比纯文本行保留更多语义）
        tbls = j.get("tables") or []
        if tbls:
            try:
                from ocr_service import table_to_markdown
                md = "\n\n".join(table_to_markdown(t) for t in tbls if t)
                if md.strip():
                    txt = (txt + "\n\n【表格】\n" + md).strip()
            except Exception as e:
                log(f"ocr_file table_to_markdown err: {e}")
        if not txt:
            return "OCR 未识别出文字（可能是纯图片或空白页）。"
        cap = int(CFG.get("ocr_max_chars") or 20000)
        meta = f"引擎 {j.get('engine') or '-'}" + (f"｜{j.get('pages')} 页" if j.get("pages") else "")
        return (f"【OCR 结果】{fn}（{meta}，{len(txt)} 字）\n\n" + txt[:cap])
    except Exception as e:
        return f"OCR 调用异常：{e}"


# ================================================================ 第五批：多步任务编排
# 设计取舍（重要）：
#   不引入独立的 planner 推理进程（4GB 显存不允许再起一份模型），而是把「编排状态」
#   外置成一份可查、可续、可回滚的**任务账本**（存 kv 表），由主模型按工具协议驱动。
#   这样做的好处：
#     1) 零额外显存 —— 编排只花主模型的 token，不占第二份 KV cache；
#     2) 可观测 —— 每步的入参/结果/成败都落账本，前端与 /gateway/trace 都能看到进度；
#     3) 可续跑 —— 会话中断后凭 plan_id 恢复，不必从头再来（长流程的关键）；
#     4) 可回滚 —— write 类步骤记录下发 id，失败时可按逆序补偿。
#   与 bionic_cli 是互补关系：bionic_cli 治「上下文污染」，task_plan 治「多步可靠性」。

def _plan_key(clue_id=""):
    """计划账本按会话维度隔离（同一会话同一时刻只有一份活动计划）。"""
    return f"task_plan:{clue_id or 'anon'}"


def _count_active_plans():
    """统计当前活跃计划数（观测用；顺带清掉过期条目）。"""
    n = 0
    ttl = int(CFG.get("orchestrator_ttl") or 7200)
    try:
        with db() as c:
            rows = c.execute("SELECT k,v FROM kv WHERE k LIKE 'task_plan:%'").fetchall()
        for k, v in rows:
            try:
                p = json.loads(v)
            except Exception:
                continue
            if p.get("state") != "active":
                continue
            if time.time() - float(p.get("ts") or 0) > ttl:
                with db() as c:
                    c.execute("DELETE FROM kv WHERE k=?", (k,))
                continue
            n += 1
    except Exception as e:
        log(f"_count_active_plans err: {e}")
    return n


def _plan_load(clue_id=""):
    raw = kv_get(_plan_key(clue_id))
    if not raw:
        return None
    try:
        p = json.loads(raw)
    except Exception:
        return None
    ttl = int(CFG.get("orchestrator_ttl") or 7200)
    if time.time() - float(p.get("ts") or 0) > ttl:
        with db() as c:
            c.execute("DELETE FROM kv WHERE k=?", (_plan_key(clue_id),))
        return None
    return p


def _plan_save(clue_id, p):
    p["ts"] = time.time()
    with db() as c:
        c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                  (_plan_key(clue_id), json.dumps(p, ensure_ascii=False)))


def _plan_render(p):
    """把计划渲染成人/模型都能读的进度视图。"""
    if not p:
        return "当前没有进行中的任务计划。"
    steps = p.get("steps") or []
    icon = {"pending": "☐", "doing": "▶", "done": "☑", "failed": "✗",
            "skipped": "⊘", "rolled_back": "↩"}
    done_n = sum(1 for s in steps if s.get("status") in ("done", "skipped"))
    lines = [f"【任务计划】{p.get('goal') or '(无目标)'}"
             f"　状态：{p.get('state') or 'active'}"
             f"　进度：{done_n}/{len(steps)}"]
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            s = {"desc": str(s), "status": "pending"}
        st = s.get("status") or "pending"
        line = f"  {icon.get(st, '?')} {i}. {s.get('desc') or '(未描述)'}"
        if s.get("result"):
            line += f"\n        └ 结果：{str(s['result'])[:300]}"
        if st == "failed" and s.get("error"):
            line += f"\n        └ 失败：{str(s['error'])[:200]}"
        lines.append(line)
    if p.get("note"):
        lines.append(f"  备注：{p['note']}")
    return "\n".join(lines)


def task_plan_impl(action, goal="", steps=None, step_index=0, status="",
                    result="", note="", clue_id="", person=""):
    """多步任务账本：create / update / show / close / cancel。"""
    if not CFG.get("orchestrator_enable", True):
        return "ERROR: 多步编排未启用（orchestrator_enable=false）。"
    action = (action or "").strip().lower()
    p = _plan_load(clue_id)

    if action == "create":
        if p and p.get("state") == "active" and p.get("steps"):
            # 已有活动计划：不硬顶掉，提示模型先收口（避免计划被静默覆盖）
            return ("ERROR: 当前会话已有进行中的计划，不能重复创建。\n" + _plan_render(p) +
                    "\n请先用 action=update 推进它，完成后 action=close，"
                    "或 action=cancel 放弃后重建。")
        if not goal:
            return "ERROR: create 需要提供 goal（一句话目标）。"
        if not steps or not isinstance(steps, list):
            return "ERROR: create 需要提供 steps（步骤字符串数组）。"
        cap = int(CFG.get("orchestrator_max_steps") or 12)
        if len(steps) > cap:
            return (f"ERROR: 步骤数 {len(steps)} 超过上限 {cap}。请合并相邻步骤后重试"
                    "（步骤过多会导致执行链路不可控）。")
        norm = []
        for s in steps:
            d = str(s).strip()
            if d:
                norm.append({"desc": d, "status": "pending", "result": "", "error": "",
                             "kind": "", "payload": None})
        if not norm:
            return "ERROR: steps 中没有有效步骤。"
        p = {"goal": str(goal).strip(), "steps": norm, "state": "active",
             "created": time.time(), "clue": clue_id or "", "person": person or "",
             "note": "", "rollback": []}
        _plan_save(clue_id, p)
        audit_log(person, clue_id, "task_plan", {"goal": goal, "n": len(norm)},
                  "created", "多步计划已登记")
        return ("已登记任务计划（尚未执行任何步骤）。请按顺序逐步推进：\n" + _plan_render(p) +
                "\n\n接下来：用相应业务工具或 task_run_step 执行第 1 步，"
                "完成后用 task_plan(action=update, step_index=1, status=done, result=...) 回填，"
                "再进入下一步。全部完成时 action=close。")

    if not p:
        return ("ERROR: 当前没有任务计划。多步任务请先用 task_plan(action=create) 登记计划；"
                "单步问题直接调用业务工具即可。")

    if action == "show":
        return _plan_render(p)

    if action == "update":
        steps_ = p.get("steps") or []
        try:
            idx = int(step_index)
        except Exception:
            return "ERROR: step_index 必须是整数。"
        if idx < 1 or idx > len(steps_):
            return f"ERROR: step_index {idx} 超出范围（本计划共 {len(steps_)} 步）。"
        st = (status or "").strip().lower()
        if st not in ("done", "failed", "skipped", "doing", "pending", "rolled_back"):
            return "ERROR: status 仅支持 done / failed / skipped / doing / pending / rolled_back。"
        s = steps_[idx - 1]
        s["status"] = st
        if result:
            s["result"] = str(result)[:2000]
        if st == "failed" and result:
            s["error"] = str(result)[:2000]
        audit_log(person, clue_id, "task_plan",
                  {"step": idx, "status": st}, "updated", str(result)[:200])
        _plan_save(clue_id, p)
        left = sum(1 for x in steps_ if x.get("status") in ("pending", "doing"))
        tail = (f"\n还剩 {left} 步未完成。" if left else
                "\n所有步骤均已处置，请用 action=close 结项。")
        return _plan_render(p) + tail

    if action == "close":
        bad = [i for i, x in enumerate(p.get("steps") or [], 1)
               if x.get("status") == "failed"]
        p["state"] = "closed"
        if note:
            p["note"] = str(note)[:500]
        _plan_save(clue_id, p)
        audit_log(person, clue_id, "task_plan", {"goal": p.get("goal")}, "closed",
                  f"失败步 {bad}" if bad else "全部完成")
        msg = ("✅ 任务计划已结项。\n" + _plan_render(p))
        if bad:
            msg += (f"\n注意：第 {bad} 步为失败状态。若这些步骤已产生副作用（写入了数据），"
                    "可用 task_rollback 按用户确认后回滚。")
        return msg

    if action == "cancel":
        p["state"] = "cancelled"
        if note:
            p["note"] = str(note)[:500]
        _plan_save(clue_id, p)
        audit_log(person, clue_id, "task_plan", {"goal": p.get("goal")}, "cancelled",
                  str(note)[:200])
        return "任务计划已标记为放弃（账本保留，便于回溯）。\n" + _plan_render(p)

    return "ERROR: action 仅支持 create / update / show / close / cancel。"


def task_run_step_impl(step_index, kind, source="", flag="", query="", where="",
                       limit=0, data=None, action="", row_id="", note_text="",
                       confirm=False, clue_id="", person="", perms=None,
                       user_token="", persona="", target=""):
    """在计划内执行一个系统内操作步骤，并自动回填账本。
    ★ 参数全部平铺（无嵌套对象）—— 弱模型（glm-4.7-flash 等）无法可靠生成嵌套
      参数对象，实测会把 params 塞成字符串甚至拼进 kind 里，故一律扁平化。
    kind: read / write / notify_note
    返回 (文本结果, 是否成功)。"""
    if not CFG.get("orchestrator_enable", True):
        return "ERROR: 多步编排未启用（orchestrator_enable=false）。", False
    p = _plan_load(clue_id)
    if not p:
        return ("ERROR: 当前没有任务计划，无法在计划内执行步骤。"
                "请先用 task_plan(action=create) 登记计划。"), False
    steps_ = p.get("steps") or []
    try:
        idx = int(step_index)
    except Exception:
        return "ERROR: step_index 必须是整数。", False
    if idx < 1 or idx > len(steps_):
        return f"ERROR: step_index {idx} 超出范围（本计划共 {len(steps_)} 步）。", False

    # ★ kind 净化：弱模型常把整段说明塞进 kind（如 "read;params:{}(待补充) - 修正…"）。
    #   这里只取开头第一个合法单词，而不是直接报错打断整条链。
    raw_kind = str(kind or "").strip()
    kind_norm = ""
    for w in ("read", "write", "notify_note"):
        if raw_kind.lower().startswith(w) or raw_kind.lower() == w:
            kind_norm = w
            break
    if not kind_norm:
        # 兜底：在乱串里找第一个出现的合法词
        low = raw_kind.lower()
        for w in ("notify_note", "read", "write"):
            if w in low:
                kind_norm = w
                break
    if not kind_norm:
        return (f"ERROR: kind 只能填 read / write / notify_note 三者之一，"
                f"收到的是 '{raw_kind[:80]}'。请只填这一个单词，不要附加说明文字。"), False
    kind = kind_norm

    # ★ source 净化（同上）；并从 flag/target/乱串里推断
    src = str(source or "").strip().lower()
    if src not in ("table", "tables", "kb", "cms", "todo"):
        low = (src + " " + raw_kind).lower()
        src = ""
        if "tables" in low or "表清单" in low or "全部表" in low or "所有表" in low:
            src = "tables"
        elif "table" in low:
            src = "table"
        elif "kb" in low or "知识库" in low:
            src = "kb"
        elif "cms" in low or "公文" in low:
            src = "cms"
        elif "todo" in low or "待办" in low:
            src = "todo"

    s = steps_[idx - 1]
    s["kind"] = kind
    s["status"] = "doing"
    _plan_save(clue_id, p)

    def _finish(mark_status, text, err=""):
        s["status"] = mark_status
        s["result"] = str(text)[:2000]
        if err:
            s["error"] = str(err)[:2000]
        _plan_save(clue_id, p)
        return text, mark_status == "done"

    # flag 兜底：模型可能把标识放在 flag 之外（target / 老的 params 位置）
    flag = str(flag or "").strip()
    if not flag:
        flag = str(target or "").strip()
    # target 常被塞长描述 → 取首个 token 当标识尝试
    if flag and (len(flag) > 60 or " " in flag):
        flag = flag.split()[0].strip("【】「」,，;；")
    flag = flag.strip("【】「」,，;；")

    # ---- read：读数据（表 / 知识库 / 公文 / 待办）----
    if kind == "read":
        # 未给 source 时按已有线索推断（只推明确的，不猜 query）
        if not src:
            if flag:
                src = "table"
            elif str(query or "").strip():
                src = ""      # query 在 kb/cms 都有意义，不猜
        if not src:
            return _finish(
                "failed",
                "ERROR: read 步骤需要指定 source（平铺字段，不是嵌套对象）。可选：\n"
                "  · source='tables' → 列出全部自建表（找表标识先用这个，不需要别的参数）\n"
                "  · source='table'  → 读某张表，同时填 flag='表标识'\n"
                "  · source='kb'     → 知识库，可选 query='关键词'\n"
                "  · source='cms'    → 公文，可选 query='关键词'\n"
                "  · source='todo'   → 我的待办\n"
                "正确示例：{\"step_index\":1,\"kind\":\"read\",\"source\":\"table\","
                "\"flag\":\"aiDemoOrders\"}",
                "read 步骤缺少 source")
        if src == "tables":
            out = query_table_list_impl(user_token=user_token,
                                        keyword=str(query or "").strip())
        elif src == "kb":
            out = kb_docs_impl(perms=perms, keyword=str(query or flag).strip(),
                               doc_id="", user_token=user_token)
        elif src == "cms":
            out = cms_list_impl(keyword=str(query or flag).strip(),
                                size=int(limit or 10), user_token=user_token)
        elif src == "todo":
            out = todo_list_impl(person=person, page=1,
                                 size=int(limit or 10), user_token=user_token)
        else:  # table
            if not flag:
                return _finish("failed",
                               "ERROR: source='table' 时必须同时填 flag='表标识'"
                               "（可先用 source='tables' 取全部表清单）。",
                               "缺少 flag")
            out = query_rows_impl(flag, str(where or "").strip(),
                                  int(limit or 20), user_token=user_token)
        failed = out.startswith(("ERROR", "查询失败", "错误"))
        s["payload"] = {"kind": kind, "source": src, "flag": flag}
        return _finish("failed" if failed else "done", out, out if failed else "")

    # ---- write：写数据（复用 write_data 全套保护：白名单 + 二次确认 + 审计）----
    if kind == "write":
        table = str(flag or target or "").strip()
        if not table:
            return _finish("failed", "ERROR: write 步骤需提供 flag='表标识'。", "缺少 flag")
        if not isinstance(data, dict) or not data:
            return _finish("failed", "ERROR: write 步骤需提供 data（对象）。", "缺少 data")
        wargs = {"table": table, "data": data,
                 "action": str(action or "create"),
                 "row_id": str(row_id or "")}
        if confirm:
            wargs["confirm"] = True
        # 直接把 write_data 的执行体交给统一入口，保证与直接调用行为完全一致
        out = exec_builtin("write_data", wargs, person=person, perms=perms,
                           user_token=user_token, persona=persona, clue_id=clue_id)
        if out.startswith("✅"):
            # ★ 写入成功后立刻反查该行 id 并落账本 —— 这是回滚唯一的可靠抓手。
            #   写接口只返回 {"value":1}（影响行数），拿不到新行 id；若等到回滚时才反查，
            #   期间数据可能被改/增，反查就不唯一了。故必须"写完就记"。
            rid = ""
            if wargs["action"] == "create":
                rid = _row_locate(table, data, token=user_token)
            else:
                rid = wargs.get("row_id") or ""
            s["payload"] = {"kind": "write", "table": table, "data": data,
                            "action": wargs["action"], "row_id": rid}
            note = f"（已记录回滚抓手 row_id={rid}）" if rid else \
                   "（未能反查唯一 row_id，回滚时将保守跳过该步）"
            return _finish("done", out + "\n" + note)
        if out.startswith("CONFIRM_REQUIRED"):
            # 预案已生成：本步回到 doing（等用户确认），不记为失败
            s["payload"] = {"kind": "write", "table": table, "data": data,
                            "action": wargs["action"], "row_id": wargs.get("row_id") or "",
                            "awaiting_confirm": True}
            return _finish("doing", out)
        return _finish("failed", out, out)

    # ---- notify_note：在账本内留痕（不产生外部副作用，天然可逆）----
    if kind == "notify_note":
        txt = (str(note_text or "").strip() or str(query or "").strip() or "已记录。")
        return _finish("done", f"留痕：{flag or target or '(未命名)'}\n{txt}")

    return _finish("failed", f"ERROR: 不支持的 kind '{kind}'。", "非法 kind")


def task_rollback_impl(reason, from_step=0, confirm=False,
                       clue_id="", person="", perms=None, user_token="", persona=""):
    """回滚计划内可逆的 write 步骤（补偿：删除已写入的行）。破坏性操作，需 confirm。"""
    if not CFG.get("orchestrator_enable", True) or not CFG.get("orchestrator_rollback", True):
        return "ERROR: 回滚能力未启用。"
    p = _plan_load(clue_id)
    if not p:
        return "ERROR: 当前没有任务计划。"
    steps_ = p.get("steps") or []
    # 挑出「已执行成功且可逆」的写步骤
    cands = []
    for i, s in enumerate(steps_):
        pl = s.get("payload") or {}
        if s.get("status") == "done" and pl.get("kind") == "write" and pl.get("table"):
            if from_step and (i + 1) < int(from_step):
                continue
            cands.append((i + 1, s))
    if not cands:
        return ("计划中没有可回滚的步骤（读类步骤天然无需回滚；"
                "写类步骤只有在'已成功写入'后才会记录补偿信息）。")

    if not confirm:
        lines = ["CONFIRM_REQUIRED：回滚是破坏性操作，尚未执行。将按**逆序**处理以下步骤："]
        for n, s in reversed(cands):
            pl = s.get("payload") or {}
            lines.append(f"  ↩ 第{n}步：删除表 '{pl.get('table')}' 中本次写入的数据 "
                         f"{json.dumps(pl.get('data'), ensure_ascii=False)}")
        lines.append(f"\n回滚原因：{reason}")
        lines.append("\n请把以上内容完整转述给用户并请求明确确认；"
                     "用户同意后再次调用 task_rollback（confirm=true、原因不变）执行。")
        return "\n".join(lines)

    done, fail = [], []
    for n, s in reversed(cands):   # 逆序补偿
        pl = s.get("payload") or {}
        table, data = pl.get("table"), pl.get("data") or {}
        rid = pl.get("row_id") or ""
        try:
            if not rid:
                # 账本没记 id（老计划/反查失败）→ 用类型感知的反查兜一次（仍要求唯一命中）
                rid = _row_locate(table, data, token=user_token)
        except Exception as e:
            log(f"rollback locate err: {e}")
        if not rid:
            fail.append(f"第{n}步：无法定位待删除行（未记录 row_id 且反查不唯一），已跳过")
            continue
        okd, jd, std = _o2_call(f"{_O2_QRY}/table/{table}/row/{rid}",
                                method="DELETE", token=user_token)
        if okd:
            done.append(f"第{n}步：已删除表 '{table}' 行 {rid}")
            s["status"] = "rolled_back"
        else:
            fail.append(f"第{n}步：删除失败（HTTP {std}）")
    _plan_save(clue_id, p)
    audit_log(person, clue_id, "task_rollback", {"reason": reason, "from": from_step},
              "executed", f"成功{len(done)} 失败{len(fail)}")
    out = [f"回滚完成（原因：{reason}）："]
    out += [f"  ✓ {x}" for x in done]
    out += [f"  ✗ {x}" for x in fail]
    if not done:
        out.append("  （没有任何步骤被回滚，请人工核对）")
    return "\n".join(out)


def _jpql_literal(v):
    """把 Python 值转成 jpql 字面量。
    ★ 坑：数字字段必须裸写（o.amount=7），加引号写成 o.amount='7' 会类型不匹配 → 恒 0 行。
    字符串字段必须单引号（o.productName='x'）。日期/时间字段 O2OA 存字符串，按字符串处理。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("'", "''")     # jpql 单引号转义
    return f"'{s}'"


def _o2_table_flag_valid(flag):
    """表标识是否真实存在（按 name 或 alias 精确匹配）。带 60s 缓存，避免反复拉清单。"""
    flag = (flag or "").strip()
    if not flag:
        return False
    now = time.time()
    cache = _tbl_flag_cache
    if now - cache.get("ts", 0) > 60 or not cache.get("set"):
        try:
            ok, j, st = _o2_call(f"{_O2_QRY}/table/list/paging/1/size/200",
                                 method="POST", body={})
            items = ((j.get("data") if isinstance(j, dict) else j) or []) if ok else []
            s = set()
            for t in items:
                for k in ("name", "alias", "id"):
                    v = (t or {}).get(k)
                    if v:
                        s.add(str(v).strip())
            cache.update({"set": s, "ts": now})
        except Exception as e:
            log(f"_o2_table_flag_valid err: {e}")
            return True   # 校验失败时放行，不因校验本身阻断业务
    return flag in (cache.get("set") or set())


_tbl_flag_cache = {"set": set(), "ts": 0}


def _row_locate(table, data, token=""):
    """按写入的字段值反查唯一样本行，返回 row_id 或 ""。
    仅当**恰好命中 1 行**时才返回——多行或 0 行都不返回，避免误删他行（保守策略）。"""
    pairs = [(k, v) for k, v in (data or {}).items()
             if isinstance(v, (str, int, float, bool)) and str(v) != ""]
    if not pairs:
        return ""
    where = " and ".join(f"o.{k}={_jpql_literal(v)}" for k, v in pairs)
    import urllib.parse
    q = urllib.parse.quote(where, safe="")
    okq, jq, _stq = _o2_call(f"{_O2_QRY}/table/list/{table}/row/select/where/{q}",
                             method="GET", token=token)
    rows = (jq.get("data") if isinstance(jq, dict) else jq) or []
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict):
        return rows[0].get("id") or ""
    log(f"rollback locate not unique: table={table} matched={len(rows) if isinstance(rows,list) else '?'}")
    return ""


# ================================================================
# 设计态能力（Phase A：门户页 / 动态表 / 数据应用 / 门户）
# ----------------------------------------------------------------
# 四层安全闸：① 角色闸门(analyst/manager) ② 草稿不落地(confirm=false只出提案)
# ③ 过程授权(人类逐步确认即授权，不做静态应用白名单，按需而动)
# ④ 落地前快照 + 审计 + 可回滚。系统级应用永不可触达(design_denylist)。
# 复用：_o2_rest(专用 client + cookie 清理) / audit_log / kv 账本 / 角色判定。
# ================================================================

def _design_double_escape(obj):
    """门户页 PUT 的 data 字段需双层转义：json.dumps(json.dumps(obj))[1:-1]。"""
    return json.dumps(json.dumps(obj, ensure_ascii=False), ensure_ascii=False)[1:-1]


def _design_rest_map(kind, action, target_id, parent_id):
    """返回 (method, path, need_body, label)。不支持的组合抛 ValueError。"""
    if kind == "portal":
        if action == "create":  return "POST",   "/x_portal_assemble_designer/jaxrs/portal", True,  "新建门户"
        if action == "update":  return "PUT",    f"/x_portal_assemble_designer/jaxrs/portal/{target_id}", True,  "修改门户"
        if action == "delete":  return "DELETE", f"/x_portal_assemble_designer/jaxrs/portal/{target_id}", False, "删除门户"
    if kind == "page":
        if action == "create":  return "POST",   "/x_portal_assemble_designer/jaxrs/page", True,  "新建门户页"
        if action == "update":  return "PUT",    f"/x_portal_assemble_designer/jaxrs/page/{target_id}", True,  "修改门户页"
        if action == "delete":  return "DELETE", f"/x_portal_assemble_designer/jaxrs/page/{target_id}", False, "删除门户页"
    if kind == "data_app":
        if action == "create":  return "POST",   "/x_query_assemble_designer/jaxrs/query", True,  "新建数据应用"
        if action == "update":  return "PUT",    f"/x_query_assemble_designer/jaxrs/query/{target_id}", True,  "修改数据应用"
        if action == "delete":  return "DELETE", f"/x_query_assemble_designer/jaxrs/query/{target_id}", False, "删除数据应用"
    if kind == "dynamic_table":
        if action == "create":  return "POST",   "/x_query_assemble_designer/jaxrs/table", True,  "新建动态表"
        if action == "update":  return "PUT",    f"/x_query_assemble_designer/jaxrs/table/{target_id}", True,  "修改动态表定义"
        if action == "delete":  return "DELETE", f"/x_query_assemble_designer/jaxrs/table/{target_id}", False, "删除动态表"
    raise ValueError(f"不支持的 kind/action：{kind}/{action}")


def _design_snapshot_path(kind, target_id):
    """执行前快照路径；(method, path)；无法快照返回 ('', '')。"""
    if kind == "portal":          return "GET", f"/x_portal_assemble_designer/jaxrs/portal/{target_id}"
    if kind == "page":            return "GET", f"/x_portal_assemble_designer/jaxrs/page/{target_id}"
    if kind == "data_app":        return "GET", f"/x_query_assemble_designer/jaxrs/query/{target_id}"
    if kind == "dynamic_table":   return "GET", f"/x_query_assemble_designer/jaxrs/table/{target_id}"
    return "", ""


def _design_proposal_text(kind, action, target_id, parent_id, name, alias,
                         draft_json, label, m, p):
    lines = [f"【{label}】", f"- 类型 kind：{kind}", f"- 操作 action：{action}（HTTP {m} {p}）"]
    if name:        lines.append(f"- 名称 name：{name}")
    if alias:       lines.append(f"- 别名 alias：{alias}")
    if target_id:   lines.append(f"- 目标标识 target_id：{target_id}")
    if parent_id:   lines.append(f"- 所属 parent_id：{parent_id}")
    if draft_json is not None:
        try:
            dj = json.dumps(draft_json, ensure_ascii=False)
        except Exception:
            dj = str(draft_json)
        lines.append(f"- 内容 draft_json（摘要）：{dj[:800]}")
    return "\n".join(lines)


def design_op_impl(kind, action, target_id="", parent_id="", name="", alias="",
                  draft_json=None, confirm=False, note="",
                  clue_id="", person="", perms=None, user_token="", persona="", *a, **kw):
    kind = (kind or "").strip().lower()
    action = (action or "").strip().lower()
    # ① 角色闸门
    if persona not in (CFG.get("design_personas") or ["manager", "analyst"]):
        audit_log(person, clue_id, "design_op", {"kind": kind, "action": action},
                  "refused", f"persona={persona} 无设计态权限")
        return ("ERROR: 当前角色没有设计态权限（仅 analyst / manager）。设计态会改动系统结构，"
                "请由具备权限的人员发起，并在确认提案后再授权执行。")
    if not CFG.get("design_enable"):
        return "ERROR: 设计态能力未开启（design_enable=false）。"
    if kind not in ("portal", "page", "data_app", "dynamic_table"):
        return "ERROR: kind 仅支持 portal / page / data_app / dynamic_table"
    if action not in ("create", "update", "delete"):
        return "ERROR: action 仅支持 create / update / delete"
    # 参数完整性
    if action in ("update", "delete") and not target_id:
        return f"ERROR: {action} 操作必须提供 target_id（要改/删的标识）"
    if action == "create" and kind == "page" and not parent_id:
        return "ERROR: 新建门户页必须提供 parent_id（所属门户 id）"
    if action == "create" and kind == "dynamic_table" and not parent_id:
        return "ERROR: 新建动态表必须提供 parent_id（所属数据应用 id）"
    if action == "create" and not name:
        return "ERROR: 新建操作必须提供 name"
    # ② 系统级应用永不触达
    denylist = CFG.get("design_denylist") or []
    for blocked in denylist:
        if blocked and (blocked in (target_id or "") or blocked in (name or "") or blocked in (alias or "")):
            audit_log(person, clue_id, "design_op", {"kind": kind, "action": action, "target": target_id},
                      "refused", f"命中 design_denylist: {blocked}")
            return f"ERROR: 目标命中系统保护清单（{blocked}），禁止任何设计态操作。"
    # 意图
    intent = {"kind": kind, "action": action, "target_id": target_id, "parent_id": parent_id,
              "name": name, "alias": alias,
              "draft": draft_json if isinstance(draft_json, (dict, list)) else None}
    canon = json.dumps(intent, sort_keys=True, ensure_ascii=False)
    pkey = f"pending_design:{clue_id or 'anon'}"
    ttl = int(CFG.get("design_confirm_ttl") or 600)
    # ③ 草稿不落地：confirm=false 只出提案
    if not confirm:
        if action in ("create", "update") and not isinstance(draft_json, (dict, list)):
            return ("ERROR: create/update 必须提供 draft_json（要创建/修改的内容，JSON 对象）。"
                    "请先收集到完整、合法的内容后再生成提案。")
        with db() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                      (pkey, json.dumps({"intent": intent, "ts": time.time()}, ensure_ascii=False)))
        audit_log(person, clue_id, "design_op", intent, "pending", "已生成设计态提案，等待人工确认")
        try:
            m, p, _nb, label = _design_rest_map(kind, action, target_id, parent_id)
        except ValueError as e:
            return f"ERROR: {e}"
        proposal = _design_proposal_text(kind, action, target_id, parent_id, name, alias,
                                         draft_json, label, m, p)
        return ("CONFIRM_REQUIRED：已生成设计态提案（尚未执行，未改动任何系统）。"
                "请向用户完整复述以下提案并请求明确授权：\n" + proposal +
                f"\n\n⚠️ 这是结构性变更，执行后可能影响业务。用户明确同意后，"
                f"再次调用 design_op 并把 confirm 置为 true（其余参数保持不变）；"
                f"预案 {ttl//60} 分钟内有效。delete 一旦执行不可简单撤销，请特别谨慎。")
    # ④ confirm=true：校验预案 → 快照 → 执行 → 审计 → 可回滚
    raw = kv_get(pkey)
    if not raw:
        if action in ("create", "update") and not isinstance(draft_json, (dict, list)):
            return "ERROR: 缺少有效预案且未提供 draft_json，无法执行。请先用 confirm=false 生成提案。"
        with db() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                      (pkey, json.dumps({"intent": intent, "ts": time.time()}, ensure_ascii=False)))
        audit_log(person, clue_id, "design_op", intent, "pending", "confirm 时无预案，已补建待二次确认")
        return ("CONFIRM_REQUIRED：此前的设计态提案不存在或已失效。已按当前参数重新生成提案"
                "（尚未执行）。请向用户复述并请求确认；用户明确同意后，再次调用 design_op"
                "（confirm=true、参数不变）即可执行。")
    try:
        pend = json.loads(raw)
    except Exception:
        return "ERROR: 设计态预案数据损坏，请重新发起。"
    if time.time() - float(pend.get("ts") or 0) > ttl:
        with db() as c:
            c.execute("DELETE FROM kv WHERE k=?", (pkey,))
        audit_log(person, clue_id, "design_op", intent, "refused", "确认超时")
        return f"ERROR: 设计态预案已超时（{ttl//60} 分钟），请重新发起确认流程。"
    pintent = pend.get("intent") or {}
    pcanon = json.dumps(pintent, sort_keys=True, ensure_ascii=False)
    if canon != pcanon:
        audit_log(person, clue_id, "design_op", intent, "refused", "确认后参数与预案不一致")
        return ("ERROR: 本次调用参数与用户已确认的预案不一致，已拒绝执行。"
                "请保持参数不变重试，或重新发起确认流程。")
    # 快照（update/delete 前先取当前定义作为回滚锚）
    rollback_snap = None
    if action in ("update", "delete"):
        try:
            gm, gp = _design_snapshot_path(kind, target_id)
            if gm and gp:
                sc, stext = _o2_rest(gp, method=gm, user_token=user_token)
                if sc == 200:
                    rollback_snap = stext
        except Exception as e:
            log(f"design snapshot err: {e}")
    # 执行
    try:
        m, p, need_body, label = _design_rest_map(kind, action, target_id, parent_id)
    except ValueError as e:
        return f"ERROR: {e}"
    body = None
    if need_body:
        if kind == "page" and action == "update":
            body = {"data": _design_double_escape(draft_json)}   # 门户页 data 双层转义
        elif kind == "dynamic_table" and action == "create":
            fd = (draft_json.get("fieldList", []) if isinstance(draft_json, dict) else [])
            body = {"name": name, "alias": alias or name, "appId": parent_id,
                    "draftData": json.dumps({"fieldList": fd}, ensure_ascii=False)}
        else:
            body = draft_json
    code, text = _o2_rest(p, method=m, body=body, user_token=user_token)
    okflag = code in (200, 201, 204)
    extra = ""
    # 动态表建表需续跑 build 链（compile + reload）
    if okflag and kind == "dynamic_table" and action == "create":
        try:
            d = json.loads(text).get("data") or {}
            tid = d.get("id") or d.get("xid") or target_id
            if not tid:
                extra = "\n  · 注意：未能从响应解析新建表 id，跳过 build 链（可稍后手动 build）"
            else:
                for step in [f"/x_query_assemble_designer/jaxrs/table/{tid}/status/build",
                             f"/x_query_assemble_designer/jaxrs/table/query/{parent_id}/build",
                             "/x_query_assemble_designer/jaxrs/table/reload/dynamic"]:
                    sc, st = _o2_rest(step, method="GET", user_token=user_token)
                    extra += f"\n  · {step.split('/')[-1]}: HTTP {sc}"
                    if sc != 200:
                        extra += f" ⚠️ {st[:120]}"
        except Exception as e:
            extra = f"\n  · build 链异常：{e}"
    # 回滚账本（含快照；create 的回滚=删除新建实体）
    try:
        rbkey = f"design_rollback:{clue_id or 'anon'}"
        rb = {"kind": kind, "action": action, "target_id": target_id or (d.get("id") if (okflag and kind=="dynamic_table" and action=="create") else ""),
              "snapshot": rollback_snap, "ts": time.time(), "person": person, "name": name}
        with db() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                      (rbkey, json.dumps(rb, ensure_ascii=False)))
    except Exception:
        pass
    with db() as c:
        c.execute("DELETE FROM kv WHERE k=?", (pkey,))
    audit_log(person, clue_id, "design_op", intent, "executed" if okflag else "failed",
              f"HTTP {code} {text[:300]}")
    if okflag:
        return (f"✅ 设计态操作成功（HTTP {code}）：{label}。{extra}\n"
                "该操作已记录审计日志并保存回滚锚点（design_rollback）。"
                "如需撤销，可调用 design_rollback（两步确认）。")
    return f"ERROR: 设计态操作失败（HTTP {code}）：{text[:600]}"


def design_rollback_impl(clue_id="", person="", user_token="", persona="", confirm=False):
    if persona not in (CFG.get("design_personas") or ["manager", "analyst"]):
        audit_log(person, clue_id, "design_rollback", {}, "refused", f"persona={persona}")
        return "ERROR: 当前角色无设计态回滚权限（仅 analyst / manager）。"
    rbkey = f"design_rollback:{clue_id or 'anon'}"
    raw = kv_get(rbkey)
    if not raw:
        return "ERROR: 没有可回滚的设计态操作（design_rollback 账本为空或已回滚）。"
    try:
        rb = json.loads(raw)
    except Exception:
        return "ERROR: 回滚账本数据损坏。"
    kind = rb.get("kind"); action = rb.get("action"); target = rb.get("target_id"); snap = rb.get("snapshot")
    label = {"portal": "门户", "page": "门户页", "data_app": "数据应用", "dynamic_table": "动态表"}.get(kind, kind)
    verb = {"create": "删除新建的", "update": "恢复修改前的", "delete": "重建被删除的"}.get(action, action)
    if not confirm:
        return ("CONFIRM_REQUIRED：发现可回滚的设计态操作："
                f"{verb}{label}（目标 {target}）。请向用户复述并请求确认；"
                "用户明确同意后，再次调用 design_rollback（confirm=true）执行回滚。")
    if action == "create":
        try:
            m, p, _nb, _lb = _design_rest_map(kind, "delete", target, "")
        except ValueError as e:
            return f"ERROR: {e}"
        code, text = _o2_rest(p, method=m, user_token=user_token)
        okflag = code in (200, 204)
        with db() as c:
            c.execute("DELETE FROM kv WHERE k=?", (rbkey,))
        audit_log(person, clue_id, "design_rollback", rb, "executed" if okflag else "failed", f"HTTP {code}")
        return (f"✅ 已回滚（删除新建的{label}）：HTTP {code}" if okflag
                else f"ERROR: 回滚失败 HTTP {code}：{text[:400]}")
    if action == "update":
        try:
            _m, p, _nb, _lb = _design_rest_map(kind, "update", target, "")
        except ValueError as e:
            return f"ERROR: {e}"
        try:
            snap_obj = json.loads(snap) if snap else {}
        except Exception:
            snap_obj = {}
        body = snap_obj
        if kind == "page":
            body = {"data": _design_double_escape(snap_obj)}
        code, text = _o2_rest(p, method="PUT", body=body, user_token=user_token)
        okflag = code in (200, 204)
        with db() as c:
            c.execute("DELETE FROM kv WHERE k=?", (rbkey,))
        audit_log(person, clue_id, "design_rollback", rb, "executed" if okflag else "failed", f"HTTP {code}")
        return (f"✅ 已回滚（恢复修改前的{label}）：HTTP {code}" if okflag
                else f"ERROR: 回滚失败 HTTP {code}：{text[:400]}")
    # delete 的重建较复杂：保留快照供人工重建
    with db() as c:
        c.execute("DELETE FROM kv WHERE k=?", (rbkey,))
    audit_log(person, clue_id, "design_rollback", rb, "manual", "delete 回滚需人工重建")
    return ("⚠️ 该操作是「删除」，自动回滚较复杂（O2OA 重建需完整对象且可能重建 id）。"
            "已为你保留删除前的完整定义快照，可据此在 O2OA 设计器手动重建；快照如下：\n"
            + (snap[:2000] if snap else "（无快照）"))


# ---------------------------------------------------------------- 多层记忆 · 成长感知
def growth_record(kind, payload):
    """向成长账本追加一条事件（入库/反思/评估）。"""
    try:
        with db() as c:
            c.execute("INSERT INTO growth_ledger(kind, payload, ts) VALUES(?,?,?)",
                      (kind, json.dumps(payload, ensure_ascii=False), time.time()))
    except Exception as e:
        log(f"growth_record err: {e}")


def memory_layer_stats():
    """统计各记忆分层文档数与向量块数，供 /gateway/capabilities 观测。"""
    try:
        with db() as c:
            cats = c.execute("SELECT category, COUNT(*) FROM docs GROUP BY category").fetchall()
            nchunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            ng = c.execute("SELECT kind, COUNT(*) FROM growth_ledger GROUP BY kind").fetchall()
        return {"chunks": nchunks, "docs_by_layer": {k: v for k, v in cats},
                "growth_events": {k: v for k, v in ng}}
    except Exception:
        return {"chunks": 0, "docs_by_layer": {}, "growth_events": {}}


def kb_ingest_impl(paths, category="o2oa_ops", user_token="", perms=None,
                   persona="", confirm=False):
    """把本地文件/目录灌入知识库（多层记忆：category 即分层）。仅 analyst/manager。"""
    if persona not in (CFG.get("design_personas") or ["manager", "analyst"]):
        return "ERROR: kb_ingest 需 analyst / manager 角色。"
    if not isinstance(paths, list):
        paths = [paths] if paths else []
    # 预览：列出将入库的文件
    plan = []
    for p in paths:
        p = str(p or "").strip()
        if not p:
            continue
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.lower().endswith((".md", ".txt", ".json", ".html")):
                    plan.append(os.path.join(p, fn))
        elif os.path.isfile(p):
            plan.append(p)
    if not confirm:
        if not plan:
            return "CONFIRM_REQUIRED: 未找到可入库文件（支持 .md/.txt/.json/.html）。请检查 paths。"
        return ("CONFIRM_REQUIRED: 将向知识库 [{}] 层新增/更新以下 {} 个文件（自动向量化）：\n"
                "{}\n确认请再次调用（confirm=true）。".format(
                    category, len(plan), "\n".join(f"  - {x}" for x in plan)))
    cnt = 0
    for fp in plan:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            log(f"kb_ingest read {fp} err: {e}")
            continue
        if len(text.strip()) < 30:
            continue
        slug = os.path.splitext(os.path.basename(fp))[0]
        doc_id = f"o2kb::{category}::{slug}"
        with db() as c:
            c.execute("""INSERT INTO docs(id,title,category,content,creator_person,creator_unit,
                         question_enable,permission,meta,updated)
                         VALUES(?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,
                         content=excluded.content,updated=excluded.updated""",
                      (doc_id, slug, category, text, "AI入库器", "",
                       1, json.dumps([], ensure_ascii=False),
                       json.dumps({"src": fp}, ensure_ascii=False), time.time()))
        reindex_doc(doc_id)
        cnt += 1
    growth_record("ingest", {"category": category, "count": cnt, "by": persona})
    return f"OK: 已入库/更新 {cnt} 篇到 [{category}] 层（已自动向量化，kb_search 现可检索）。"


def kb_reflect_impl(topic="", user_token="", perms=None, persona="", confirm=False):
    """成长感知核心：从 ops_experience + feedbacks 提炼可复用知识，合成写入 ai_synthesis。仅 analyst/manager。"""
    if persona not in (CFG.get("design_personas") or ["manager", "analyst"]):
        return "ERROR: kb_reflect 需 analyst / manager 角色。"
    with db() as c:
        rows = c.execute("SELECT content FROM docs WHERE category='ops_experience' "
                         "ORDER BY updated DESC LIMIT 30").fetchall()
        fbs = c.execute("SELECT kind,content FROM feedbacks ORDER BY created_at DESC LIMIT 20").fetchall()
    corpus = "\n\n".join(r[0] for r in rows) or "（暂无操作经验）"
    fbtext = "\n".join(f"[{k}] {t}" for k, t in fbs) or "（暂无反馈）"
    prompt = (
        "你是组织知识官。基于以下『操作经验』与『用户反馈』，提炼可复用的业务规则/SOP/避坑清单"
        f"（面向本地 O2OA 智能体）。聚焦主题：{topic or '近期经验总体'}。\n\n"
        "=== 操作经验 ===\n" + corpus + "\n\n=== 用户反馈 ===\n" + fbtext + "\n\n"
        "输出要求：\n1) 3-8 条精炼要点，每条含『场景 + 做法 + 原理』；\n"
        "2) 每条标注适用分层（business_process=业务SOP / ai_synthesis=AI行为准则）；\n"
        "3) 仅基于给定素材，不编造未出现的事实。")
    if not confirm:
        syn = chat_complete([{"role": "user", "content": prompt}], model=CFG["chat_model"])
        if not syn:
            return "ERROR: 反思生成失败（chat 模型无返回）。"
        kv_set("pending_reflect:" + (topic or "all"),
               json.dumps({"topic": topic, "text": syn}, ensure_ascii=False))
        return ("CONFIRM_REQUIRED: 已生成反思草案（未落盘），请确认后 confirm=true 写入知识库：\n\n" + syn)
    pending = kv_get("pending_reflect:" + (topic or "all"))
    if not pending:
        return "ERROR: 未找到待确认草案，请先不带 confirm 生成一次。"
    try:
        syn = json.loads(pending)["text"]
    except Exception:
        return "ERROR: 草案数据损坏，请重新生成。"
    doc_id = f"o2kb::ai_synthesis::reflect_{int(time.time())}"
    with db() as c:
        c.execute("""INSERT INTO docs(id,title,category,content,creator_person,creator_unit,
                     question_enable,permission,meta,updated)
                     VALUES(?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,
                     content=excluded.content,updated=excluded.updated""",
                  (doc_id, f"[合成] 反思:{topic or '总体'}", "ai_synthesis", syn, "AI反思器", "",
                   1, json.dumps([], ensure_ascii=False),
                   json.dumps({"topic": topic}, ensure_ascii=False), time.time()))
    reindex_doc(doc_id)
    growth_record("reflect", {"topic": topic, "doc_id": doc_id})
    return f"OK: 反思成果已沉淀为知识库文档（{doc_id}），RAG 现已可检索该合成知识。"


def growth_report_impl():
    """成长感知账本汇报：分层规模 + 反馈 + 事件 + 建议。"""
    with db() as c:
        cats = c.execute("SELECT category, COUNT(*) FROM docs GROUP BY category").fetchall()
        nchunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        nfbs = c.execute("SELECT kind, COUNT(*) FROM feedbacks GROUP BY kind").fetchall()
        ng = c.execute("SELECT kind, COUNT(*) FROM growth_ledger GROUP BY kind").fetchall()
        last = c.execute("SELECT ts,kind,payload FROM growth_ledger ORDER BY ts DESC LIMIT 5").fetchall()
    cat_line = "\n".join(f"  - {k or '(未分层)'}: {v} 篇" for k, v in cats) or "  （空）"
    fb_line = "\n".join(f"  - {k}: {v}" for k, v in nfbs) or "  （暂无）"
    g_line = "\n".join(f"  - {k}: {v}" for k, v in ng) or "  （暂无）"
    last_line = "\n".join(f"  - {time.strftime('%m-%d %H:%M', time.localtime(t))} [{k}] {p[:80]}"
                          for t, k, p in last) or "  （暂无）"
    # 建议：哪些层偏薄
    cat_map = dict(cats)
    suggest = []
    for layer in ["o2oa_manual", "o2oa_api", "o2oa_version", "ops_experience",
                 "business_process", "ai_synthesis"]:
        if cat_map.get(layer, 0) == 0:
            suggest.append(f"[{layer}] 尚为空，建议补充对应资料")
    if not suggest:
        suggest.append("各分层均已有内容，可定期用 kb_reflect 把经验合成为 SOP")
    rep = ("【O2OA 多层记忆 · 成长感知账本】\n"
           f"向量块总数：{nchunks}\n\n"
           f"一、各记忆分层文档数：\n{cat_line}\n\n"
           f"二、用户反馈统计：\n{fb_line}\n\n"
           f"三、成长事件：\n{g_line}\n\n"
           f"四、最近事件：\n{last_line}\n\n"
           f"五、下一步建议：\n" + "\n".join(f"  - {s}" for s in suggest))
    return rep


def exec_builtin(name, args, person="", perms=None, user_token="", persona="", clue_id=""):
    """执行内置工具；返回字符串结果（供模型阅读）。
    person=当前登录用户、perms=前端 permissionList、user_token=O2OA 会话 token
    （第二批：由 O2OA 服务端实填转发，REST 层按用户身份强制鉴权）。
    第三批：persona=角色人设（write_data 权限判定）、clue_id=会话标识（二次确认 pending）。"""
    args = args or {}
    # ★ 联网工具的第二道闸：即便被手工塞进调用，web_enable=False 时也一律拒绝。
    #   （第一道闸是 builtin_tool_defs() 不注册；两道闸共同保证"系统内数据闭环"定位。）
    if name in ("web_search", "web_fetch") and not web_enabled():
        return ("ERROR: 本系统未开启联网能力，无法访问外部网络。"
                "请改用系统内数据（kb_search 知识库 / query_data 数据表 / "
                "list_my_todo 待办 / search_org 组织架构）完成任务。")
    try:
        if name == "kb_search":
            q = str(args.get("query") or "").strip()
            if not q:
                return "ERROR: query 不能为空"
            k = int(args.get("top_k") or 5)
            hits = search_chunks(q, k)
            # P0：知识库工具链路与 RAG 主链路同权——按前端 permissionList 过滤
            # （perms 为空 = 管理员/旧前端视角，保持全部可见的既有语义）
            allow = visible_docs(perms or [])
            hits = [h for h in hits if h[1] in allow]
            if not hits:
                return "知识库中没有检索到相关内容。"
            with db() as c:
                titles = dict(c.execute("SELECT id,title FROM docs").fetchall())
            lines = []
            for i, (score, doc_id, text) in enumerate(hits):
                lines.append(f"[{i+1}] 《{titles.get(doc_id,'')}》 相关度{score:.3f}\n{text[:600]}")
            return "\n\n".join(lines)

        if name == "get_current_time":
            import datetime
            now = datetime.datetime.now()
            wd = "一二三四五六日"[now.weekday()]
            return now.strftime(f"%Y-%m-%d %H:%M:%S 星期{wd}")

        if name == "calc":
            expr = str(args.get("expr") or "").strip()
            if not expr:
                return "ERROR: expr 不能为空"
            val = _safe_eval(expr)
            return f"{expr} = {val}"

        if name == "search_org":
            kw = str(args.get("keyword") or "").strip()
            if not kw:
                return "ERROR: keyword 不能为空"
            kind = str(args.get("kind") or "person").strip().lower()
            if kind == "unit":
                return org_search_impl(kw, "unit", user_token=user_token)
            if kind == "identity":
                return org_search_impl(kw, "identity", user_token=user_token)
            # person：复用 org_search_impl（统一走 _o2_call，带服务号→xadmin 回落）
            out = org_search_impl(kw, "person", user_token=user_token)
            if out.startswith("组织架构中没有匹配") or out.startswith("人员检索失败"):
                # 回落旧路径（兼容 user_token 视角）
                code, text, data = _o2_rest_user_or_manager(
                    "/x_organization_assemble_control/jaxrs/person/list/like",
                    method="PUT", body={"key": kw}, user_token=user_token)
                if isinstance(data, list) and data:
                    lines = []
                    for p in data[:10]:
                        if not isinstance(p, dict):
                            continue
                        lines.append(f"- {p.get('name') or '(未命名)'}"
                                     f"｜DN:{p.get('distinguishedName') or p.get('id')}"
                                     + (f"｜手机:{p.get('mobile')}" if p.get("mobile") else "")
                                     + (f"｜邮箱:{p.get('mail')}" if p.get("mail") else ""))
                    return f"组织架构中匹配“{kw}”的人员 {len(data)} 人：\n" + "\n".join(lines)
                return f"HTTP {code}\n{text[:2000]}"
            return out

        if name == "list_my_todo":
            limit = int(args.get("limit") or 10)
            page = int(args.get("page") or 1)
            # ★ 第五批改进：优先以「当前用户身份」查询其个人待办（服务号自己没有待办，
            #   旧实现回落到服务号时永远返回空）。user_token 存在时用它换该用户上下文；
            #   否则用 switchuser 代查（person 由服务端实填，不可伪造）。
            path = f"{_O2_PP}/task/list/my/paging/{page}/size/{limit}"
            if user_token:
                code, text, data = _o2_rest_user_or_manager(path, method="GET",
                                                            user_token=user_token)
                if data is not None:
                    items = data
                    note = ""
                else:
                    items, note = None, ""
            else:
                items, note = None, ""
            if items is None:
                if not person:
                    return "ERROR: 无法确定当前用户身份，请从前端对话入口发起。"
                out = todo_list_impl(person=person, page=page, size=limit)
                return out
            if not items:
                return f"「{person or '当前用户'}」当前没有待办。"
            lines = []
            for i, t in enumerate(items[:limit]):
                lines.append(f"- [{i+1}] {t.get('title') or t.get('workTitle') or '(无标题)'}"
                             f"｜流程:{t.get('processName') or '-'}"
                             f"｜到达:{str(t.get('startTime') or t.get('createTime') or '')[:16]}"
                             f"｜id:{t.get('id') or ''}")
            return (f"当前用户 {person or '本人'} 的待办共 {len(items)} 条{note}"
                    f"（可用 todo_detail 查看某条详情）：\n" + "\n".join(lines))

        if name == "web_fetch":
            return web_fetch_impl(args.get("url"), args.get("max_chars"),
                                  str(args.get("mode") or "text").lower())

        if name == "web_search":
            return web_search_impl(args.get("query"), args.get("limit") or 5)

        # ---- 第五批：系统内 agent 能力（数据源全部是 O2OA 自身）----
        if name == "todo_detail":
            return todo_detail_impl(str(args.get("task_id") or "").strip(),
                                    person=person, user_token=user_token)

        if name == "list_my_done":
            return todo_done_impl(person=person,
                                  page=int(args.get("page") or 1),
                                  size=int(args.get("limit") or 10),
                                  user_token=user_token)

        if name == "org_unit_tree":
            return org_unit_tree_impl(str(args.get("unit_flag") or "").strip(),
                                      user_token=user_token)

        if name == "org_person_identity":
            return org_person_identity_impl(str(args.get("person_flag") or "").strip(),
                                            user_token=user_token)

        if name == "query_table_list":
            return query_table_list_impl(user_token=user_token,
                                         keyword=str(args.get("keyword") or "").strip())

        if name == "query_rows":
            return query_rows_impl(str(args.get("table_flag") or "").strip(),
                                   str(args.get("where") or "").strip(),
                                   int(args.get("limit") or 20),
                                   user_token=user_token)

        if name == "process_app_list":
            return process_app_list_impl(user_token=user_token)

        if name == "cms_list":
            return cms_list_impl(str(args.get("keyword") or "").strip(),
                                 size=int(args.get("limit") or 10),
                                 user_token=user_token)

        if name == "cms_detail":
            return cms_detail_impl(str(args.get("doc_id") or "").strip(),
                                   user_token=user_token)

        if name == "cms_channels":
            return cms_channels_impl(user_token=user_token)

        if name == "kb_read":
            return kb_docs_impl(perms=perms,
                                keyword=str(args.get("keyword") or "").strip(),
                                doc_id=str(args.get("doc_id") or "").strip(),
                                user_token=user_token)

        if name == "ocr_file":
            return ocr_file_impl(str(args.get("file_id") or "").strip(),
                                 str(args.get("name") or "").strip(),
                                 user_token=user_token)

        if name == "bionic_cli":
            return bionic_cli_impl(args.get("prompt"), args.get("system") or "", clue_id or "")

        # ---- 第五批：多步任务编排 ----
        if name == "task_plan":
            return task_plan_impl(
                str(args.get("action") or "").strip(),
                goal=str(args.get("goal") or "").strip(),
                steps=args.get("steps"),
                step_index=args.get("step_index") or 0,
                status=str(args.get("status") or "").strip(),
                result=str(args.get("result") or "").strip(),
                note=str(args.get("note") or "").strip(),
                clue_id=clue_id or "", person=person or "")

        if name == "task_run_step":
            # 兼容模型仍按旧 schema 传来的嵌套字段（尽量救回来而不是直接报错）
            legacy = args.get("params") if isinstance(args.get("params"), dict) else {}
            out, _okflg = task_run_step_impl(
                args.get("step_index") or 0,
                args.get("kind") or "",
                source=str(args.get("source") or legacy.get("kind") or "").strip(),
                flag=str(args.get("flag") or legacy.get("table_flag") or "").strip(),
                query=str(args.get("query") or legacy.get("query") or "").strip(),
                where=str(args.get("where") or legacy.get("where") or "").strip(),
                limit=args.get("limit") or legacy.get("limit") or 0,
                data=args.get("data") or legacy.get("data"),
                action=str(args.get("action") or legacy.get("action") or "").strip(),
                row_id=str(args.get("row_id") or legacy.get("row_id") or "").strip(),
                note_text=str(args.get("note_text") or legacy.get("text") or "").strip(),
                confirm=bool(args.get("confirm")),
                clue_id=clue_id or "", person=person or "",
                perms=perms, user_token=user_token, persona=persona or "",
                target=str(args.get("target") or "").strip())
            return out

        if name == "task_rollback":
            return task_rollback_impl(
                str(args.get("reason") or "").strip(),
                from_step=args.get("from_step") or 0,
                confirm=bool(args.get("confirm")),
                clue_id=clue_id or "", person=person or "",
                perms=perms, user_token=user_token, persona=persona or "")

        if name == "query_data":
            table = str(args.get("table") or "").strip()
            if not table:
                return "ERROR: table 不能为空"
            limit = int(args.get("limit") or 10)
            flt = str(args.get("filter") or "").strip()
            # 行读写统一走 designer 模块（第三批实测：surface 模块对新建表动态实体类
            # 加载滞后会 ClassNotFoundException，designer reload/dynamic 后立即可用）
            if flt:
                import urllib.parse
                where = urllib.parse.quote(flt, safe="")
                path = f"/x_query_assemble_designer/jaxrs/table/list/{table}/row/select/where/{where}"
            else:
                path = f"/x_query_assemble_designer/jaxrs/table/list/{table}/row/(0)/next/{limit}"
            code, text, _data = _o2_rest_user_or_manager(path, method="GET", user_token=user_token)
            return f"HTTP {code}\n{text[:4000]}"

        if name == "write_data":
            # 第三批行动能力：白名单角色 + 表白名单 + 会话内二次确认 + 审计。
            # 写回固定走服务号 manager 通道（服务号已被授权为演示应用 controller），
            # 不用普通 user token（普通用户通常无表权限，且写回本身就是管理动作）。
            if persona not in (CFG.get("write_personas") or ["manager"]):
                audit_log(person, clue_id, "write_data", {"table": args.get("table")},
                          "refused", f"persona={persona} 无写回权限")
                return ("ERROR: 当前角色没有数据写回权限。您可以先向管理员申请，"
                        "或让我查询数据（query_data）后口头汇总。")
            if not CFG.get("write_enable"):
                audit_log(person, clue_id, "write_data", {"table": args.get("table")},
                          "refused", "write_enable=false")
                return "ERROR: 写回功能未开启（write_enable=false），请联系管理员。"
            table = str(args.get("table") or "").strip()
            data = args.get("data")
            if not table or not isinstance(data, dict) or not data:
                return "ERROR: table 与 data（对象）不能为空"
            action = str(args.get("action") or "create").strip().lower()
            row_id = str(args.get("row_id") or "").strip()
            if action not in ("create", "update"):
                return "ERROR: action 仅支持 create / update"
            if action == "update" and not row_id:
                return "ERROR: update 操作需要提供 row_id"
            wl = CFG.get("write_tables") or []
            # 白名单归一化：模型可能用表名/别名任一写法，按 O2OA schema 归一到白名单条目
            hit = None
            if table in wl:
                hit = table
            else:
                sch = o2_table_schema(table)
                if sch and (sch.get("alias") in wl or sch.get("name") in wl):
                    hit = sch.get("alias") if sch.get("alias") in wl else sch.get("name")
            if not hit:
                audit_log(person, clue_id, "write_data", {"table": table}, "refused",
                          f"表不在白名单 {wl}")
                avail = "\n".join(f"- {_schema_desc(o2_table_schema(t)) or t}" for t in wl) or "-（白名单为空）"
                return ("ERROR: 数据表 '" + table + "' 不在写回白名单中。可写的表及字段：\n" + avail +
                        "\n请改用上列 alias 作为 table 参数、以字段 name（英文）作为 data 的键重试"
                        "（不要用中文描述词做键）。")
            confirm = bool(args.get("confirm"))
            payload = {"table": hit, "data": data, "action": action, "row_id": row_id}
            canon = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            pkey = f"pending_write:{clue_id or 'anon'}"
            ttl = int(CFG.get("write_confirm_ttl") or 600)
            if not confirm:
                with db() as c:
                    c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                              (pkey, json.dumps({"payload": payload, "ts": time.time()},
                                                ensure_ascii=False)))
                audit_log(person, clue_id, "write_data", payload, "pending",
                          "已生成写回预案，等待用户确认")
                act = f"更新行 {row_id}" if action == "update" else "新增一行"
                return ("CONFIRM_REQUIRED：已生成写回预案（尚未执行）。请向用户完整复述以下内容并请求确认：\n"
                        f"- 目标表：{hit}\n- 操作：{act}\n- 数据：{json.dumps(data, ensure_ascii=False)}\n"
                        "用户明确同意后，再次调用 write_data 并把 confirm 置为 true"
                        "（其余参数保持不变）；预案 10 分钟内有效。")
            # confirm=true：校验预案存在、未超时、参数一致
            raw = kv_get(pkey)
            if not raw:
                # 模型跳过第一步直接 confirm → 不硬报错死锁，按当前参数补建预案再要一次确认
                with db() as c:
                    c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)",
                              (pkey, json.dumps({"payload": payload, "ts": time.time()},
                                                ensure_ascii=False)))
                audit_log(person, clue_id, "write_data", payload, "pending",
                          "confirm 时无有效预案，已补建预案待二次确认")
                act = f"更新行 {row_id}" if action == "update" else "新增一行"
                return ("CONFIRM_REQUIRED：此前的写回预案不存在或已失效（预案必须由 write_data 工具生成，"
                        "不可自行编造）。已按以下参数重新生成预案（尚未执行）：\n"
                        f"- 目标表：{hit}\n- 操作：{act}\n- 数据：{json.dumps(data, ensure_ascii=False)}\n"
                        "请把该预案完整转述给用户并请求确认；用户明确同意后，再次调用 write_data"
                        "（confirm=true、参数不变）即可执行。")
            try:
                pend = json.loads(raw)
            except Exception:
                return "ERROR: 写回预案数据损坏，请重新发起。"
            if time.time() - float(pend.get("ts") or 0) > ttl:
                with db() as c:
                    c.execute("DELETE FROM kv WHERE k=?", (pkey,))
                audit_log(person, clue_id, "write_data", payload, "refused", "确认超时")
                return "ERROR: 写回预案已超时（10 分钟），请重新发起确认流程。"
            pp = pend.get("payload") or {}
            pcanon = json.dumps({k: pp.get(k) for k in ("table", "data", "action", "row_id")},
                                sort_keys=True, ensure_ascii=False)
            if canon != pcanon:
                audit_log(person, clue_id, "write_data", payload, "refused",
                          "确认后参数与预案不一致")
                return ("ERROR: 本次调用参数与用户已确认的预案不一致，已拒绝执行。"
                        "请保持参数不变重试，或重新发起确认流程。")
            # 执行写回（designer 模块 row 接口；动态实体类在该模块已热加载）
            if action == "create":
                path = f"/x_query_assemble_designer/jaxrs/table/{hit}/row"
                code, text = _o2_rest(path, method="POST", body=data)
            else:
                path = f"/x_query_assemble_designer/jaxrs/table/{hit}/row/{row_id}"
                code, text = _o2_rest(path, method="PUT", body=data)
            okflag = code in (200, 201, 204)
            audit_log(person, clue_id, "write_data", payload,
                      "executed" if okflag else "failed", f"HTTP {code} {text[:300]}")
            with db() as c:
                c.execute("DELETE FROM kv WHERE k=?", (pkey,))
            if okflag:
                act = f"更新行 {row_id}" if action == "update" else "新增一行"
                return (f"✅ 写回成功（HTTP {code}）：已向表 '{table}' {act}。"
                        f"数据：{json.dumps(data, ensure_ascii=False)}。"
                        "请向用户确认完成，并提示该操作已记录审计日志。")
            return f"ERROR: 写回失败（HTTP {code}）：{text[:600]}"

        if name == "design_op":
            # Phase A 设计态：四层安全闸（角色/草稿不落地/过程授权/快照可回滚）
            return design_op_impl(
                kind=str(args.get("kind") or "").strip(),
                action=str(args.get("action") or "").strip(),
                target_id=str(args.get("target_id") or "").strip(),
                parent_id=str(args.get("parent_id") or "").strip(),
                name=str(args.get("name") or "").strip(),
                alias=str(args.get("alias") or "").strip(),
                draft_json=args.get("draft_json"),
                confirm=bool(args.get("confirm")),
                note=str(args.get("note") or "").strip(),
                clue_id=clue_id or "", person=person or "", perms=perms,
                user_token=user_token, persona=persona or "")

        if name == "design_rollback":
            return design_rollback_impl(
                clue_id=clue_id or "", person=person or "", user_token=user_token,
                persona=persona or "", confirm=bool(args.get("confirm")))

        if name == "kb_ingest":
            return kb_ingest_impl(
                paths=args.get("paths") or [], category=str(args.get("category") or "o2oa_ops"),
                user_token=user_token, perms=perms, persona=persona or "",
                confirm=bool(args.get("confirm")))

        if name == "kb_reflect":
            return kb_reflect_impl(
                topic=str(args.get("topic") or "").strip(), user_token=user_token, perms=perms,
                persona=persona or "", confirm=bool(args.get("confirm")))

        if name == "growth_report":
            return growth_report_impl()

        if name == "skills_list":
            items = _list_skills()
            if not items:
                return "当前没有已注册的技能。可用 skills_create 创建一个可复用的流程。"
            return "\n".join(f"- {i['name']}：{i['description']}" for i in items)

        if name == "skills_get":
            n = str(args.get("name") or "").strip()
            if not n:
                return "ERROR: name 不能为空"
            full = _get_skill(n)
            return full or f"ERROR: 技能 '{n}' 不存在"

        if name == "skills_create":
            n = str(args.get("name") or "").strip()
            d = str(args.get("description") or "").strip()
            c = str(args.get("content") or "").strip()
            if not n:
                return "ERROR: name 不能为空"
            p = _create_skill(n, d, c)
            return f"已创建技能 '{n}' -> {p.name}"

        if name == "skills_run":
            n = str(args.get("name") or "").strip()
            if not n:
                return "ERROR: name 不能为空"
            return _run_skill(n)

        if name == "kb_save":
            title = str(args.get("title") or "").strip()
            content = str(args.get("content") or "").strip()
            if not title or not content:
                return "ERROR: title 与 content 不能为空"
            category = str(args.get("category") or "智能助手沉淀").strip()[:50]
            public = True if args.get("public") is None else bool(args.get("public"))
            doc_id = uuid.uuid4().hex
            if public:
                perm = "[]"  # 空 permission 列表 = 所有用户可见
            else:
                perm = json.dumps([person or "（匿名）"], ensure_ascii=False)
            with db() as c:
                c.execute("INSERT INTO docs(id,title,category,content,creator_person,"
                          "creator_unit,question_enable,permission,meta,updated) "
                          "VALUES(?,?,?,?,?,?,0,?,?,?)",
                          (doc_id, title[:200], category, content, person or "", "",
                           perm, json.dumps({"source": "kb_save", "tags": args.get("tags") or []},
                                            ensure_ascii=False), time.time()))
            reindex_doc(doc_id)
            scope = "全体用户可见" if public else f"仅 {person or '本人'} 及管理员可见"
            return (f"已保存到知识库：《{title[:60]}》（{len(content)} 字，{scope}），文档ID {doc_id}，"
                    f"已自动分块向量化。之后用 kb_search 即可检索到。")

        if name == "feedback":
            content = str(args.get("content") or "").strip()
            if not content:
                return "ERROR: content 不能为空"
            kind = str(args.get("kind") or "suggestion").strip().lower()
            if kind not in ("like", "dislike", "suggestion"):
                kind = "suggestion"
            fid = uuid.uuid4().hex[:12]
            with db() as c:
                c.execute("INSERT INTO feedbacks(id,person,kind,content,created_at,status) "
                          "VALUES(?,?,?,?,?,'open')",
                          (fid, person or "（未识别）", kind, content[:2000],
                           time.strftime("%Y-%m-%d %H:%M:%S")))
            return (f"已记录反馈（编号 {fid}，类型 {kind}），管理员可在后台查看并跟进。"
                    "请向用户表达感谢。")

    except Exception as e:
        return f"BUILTIN_TOOL_ERROR: {e}"
    return None


def web_enabled():
    """联网能力总开关。默认 False —— 本系统定位是「Bionic agent 能力 + O2OA 内网数据」，
    不把公网数据搬进系统。置 True 即恢复 web_search/web_fetch（实现完整保留）。"""
    return bool(CFG.get("web_enable"))


def builtin_tool_defs():
    """转成 OpenAI tools 格式（与 MCP 工具同构，便于合并）。
    ★ web_enable=False 时剔除联网类工具（不注册 = 模型根本看不见，比"注册后拒绝"更干净）。"""
    web_names = {"web_search", "web_fetch"}
    out = []
    for t in BUILTIN_TOOLS:
        if t["name"] in web_names and not web_enabled():
            continue
        out.append({"type": "function", "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }})
    return out


# ---------------------------------------------------------------- 工具执行（HTTP 型 MCP）
def exec_tool(mcp, args):
    ho = (mcp.get("httpOption") or {})
    url = ho.get("url") or ""
    for k, v in (args or {}).items():
        url = url.replace("${" + k + "}", str(v))
    method = (ho.get("method") or "GET").upper()
    headers = {}
    for h in (ho.get("headers") or []):
        name = h.get("name") or h.get("key")
        if not name:
            continue
        val = str(h.get("value") or h.get("val") or "")
        for k, v in (args or {}).items():
            val = val.replace("${" + k + "}", str(v))
        headers[name] = val
    body = ho.get("body") or ho.get("requestBody")
    if isinstance(body, str):
        for k, v in (args or {}).items():
            body = body.replace("${" + k + "}", json.dumps(v, ensure_ascii=False) if isinstance(v, str) else str(v))
    try:
        r = _client.request(method, url, headers=headers,
                            content=body if isinstance(body, str) else None,
                            json=body if isinstance(body, dict) else None,
                            timeout=60)
        text = r.text
        return text[:8000] if len(text) > 8000 else text
    except Exception as e:
        return f"TOOL_EXEC_ERROR: {e}"


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "tool")[:40]


# ---------------------------------------------------------------- O2OA 响应包裹
def ok(data=None, count=None):
    w = {"type": "success"}
    if data is not None:
        w["data"] = data
    if count is not None:
        w["count"] = count
    return w


def check_token(request: Request) -> bool:
    auth = request.headers.get("authorization") or ""
    return auth.endswith(CFG["token"])


# ---------------------------------------------------------------- FastAPI
app = FastAPI(title="o2-agent-gateway", docs_url=None, redoc_url=None)


@app.middleware("http")
async def _log_middleware(request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    log(f"{request.method} {request.url.path} -> {resp.status_code} ({time.time()-t0:.2f}s)")
    return resp


@app.get("/infra-auth/who")
async def who():
    return {"code": 200, "success": True, "data": {"user": "o2-agent-gateway", "service": "local"}}


@app.get("/app/api/infra-auth/who")
async def who2():
    return await who()


# ---------- generate（对话核心，SSE） ----------
def sse_frame(name: str, data: str) -> str:
    if name == "message":
        return f"data: {data}\n\n"
    return f"event: {name}\ndata: {data}\n\n"


def stream_openai(messages, extra=None):
    """转发 Bionic 流式，产出 (data_str|None, done bool)"""
    payload = {"model": CFG["chat_model"], "stream": True, "messages": messages,
               "reasoning_effort": "none"}
    payload.update(extra or {})
    with _client.stream("POST", f"{CFG['bionic_base']}/v1/chat/completions",
                        headers=auth_hdr(), json=payload) as r:
        for line in r.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            d = line[5:].strip()
            if d == "[DONE]":
                yield None, True
                return
            yield d, False


def build_history(clue_id):
    msgs = []
    if clue_id:
        with db() as c:
            rows = c.execute(
                "SELECT v FROM kv WHERE k LIKE ?", (f"hist:{clue_id}:%",)).fetchall()
        items = [json.loads(r[0]) for r in rows]
        items.sort(key=lambda x: x.get("t", 0))
        for it in items[-10:]:
            msgs.append({"role": "user", "content": it.get("input", "")})
            msgs.append({"role": "assistant", "content": it.get("content", "")})
    return msgs


@app.post("/ai-gateway-completion/generate")
async def generate(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    wi = await request.json()
    gtype = (wi.get("generateType") or "auto").lower()
    clue_id = wi.get("clueId") or ""
    # ★ 关键兜底：前端 sessionId 初始为空时首帧带空 clueId，
    #   若不加兜底，clue_touch/save_history/completion_add 全部 if not clue_id: return，
    #   导致历史记录永远存不下来（鸡生蛋死循环：前端靠回传 clueId 回填 sessionId，
    #   但回传的正是其传来的空串 → 永远空）。由网关在首帧生成稳定会话 id 打破死循环。
    if not clue_id:
        clue_id = "chat-" + str(uuid.uuid4())
    inp = wi.get("input") or ""
    perms = wi.get("permissionList") or []
    person = (wi.get("person") or "").strip()  # 服务端 ActionChat 实填（effectivePerson），前端不可伪造
    usertoken = (wi.get("token") or "").strip()  # 服务端实填的用户会话 token，REST 层按其鉴权
    refs = wi.get("referenceIdList") or []
    # ★ 前端悬浮窗只发 auto（默认）与 searchKnowledgeBase（知识库模式），mcp/chat 选项已注释。
    #   auto → 工具循环（模型自主决定是否调用工具）；
    #   searchKnowledgeBase → RAG 知识库问答（按服务端计算的 permissionList 过滤）。
    if gtype == "auto":
        gtype = "mcp"
    elif gtype in ("searchknowledgebase", "search_knowledge_base"):
        gtype = "rag"
    # 场景上下文：前端在 input 前缀注入 [场景:...]（ActionChat 协议无场景字段），
    # 网关剥离后并入 system，不污染用户提问。
    scene = ""
    m_scene = re.match(r"^\s*[【\[]\s*场景\s*[:：](.+?)[】\]]\s*", inp)
    if m_scene:
        scene = m_scene.group(1).strip()
        inp = inp[m_scene.end():]

    # 第三批：角色人设判定 + 当前人员 DN（会话归属）；一次 REST 同时取回
    roles, udn, uname = o2_user_info(usertoken)
    persona = persona_from_roles(roles) if usertoken else ""
    if persona:
        log(f"persona={persona} user={person or uname or '-'}")

    # 会话落库：保证 clue 列表里立刻出现该会话（标题取首问；带 DN 供模块按人员过滤）
    clue_touch(clue_id, person or uname, _title_of(inp) if inp else None, person_dn=udn)

    async def gen():
        yield sse_frame("extend.status", json.dumps({"generateType": gtype, "clueId": clue_id, "id": clue_id},
                                                   ensure_ascii=False))
        content_parts = []
        # 注意：Qwen3.5 等模型的 chat template 强制要求 system 必须位于最前且至多一条，
        # 因此 RAG 上下文一律【合并进首条 system】，绝不新增第二条 system 消息。
        sys_content = "你是 O2OA 智能助手，用简体中文回答，条理清晰。"
        if person:
            sys_content += (f"\n当前登录用户：{person}。涉及'我的待办/我提交的/我的'类请求时，"
                            "一律按该用户身份处理，不得涉及其他用户的私人数据。")
        if scene:
            sys_content += (f"\n用户当前页面场景：{scene}。可据此理解问题所指的对象；"
                            "不要在回答中复述该场景标记本身。")
        if persona and persona in PERSONAS:
            _pn, _pt = PERSONAS[persona]
            sys_content += (f"\n\n【角色人设】你的当前工作人设是“{_pn}”。{_pt}"
                            "请在回答的语气、详略与建议视角上始终贴合该人设。")

        # 附件 / RAG 检索
        want_rag = gtype == "rag" or refs
        if want_rag and inp:
            allow = visible_docs(perms)
            scope = [d for d in refs if d in allow] if refs else list(allow)
            rq = rewrite_query(inp) if CFG.get("rewrite_enable") else inp
            hits = rag_retrieve(rq, scope or None)
            if hits:
                with db() as c:
                    titles = dict(c.execute("SELECT id,title FROM docs").fetchall())
                ctx = "\n\n".join(
                    f"【资料{i+1}｜{titles.get(d,'')}】\n{t}" for i, (_, d, t) in enumerate(hits))
                sys_content += ("\n\n以下是知识库检索到的资料，回答时优先依据这些资料；"
                                "若资料与问题无关可忽略并如实说明：\n\n" + ctx)
            elif refs:
                yield sse_frame("message", json.dumps(
                    {"choices": [{"delta": {"content": "（未在指定附件中检索到相关内容，以下为模型直接回答）\n"}}]},
                    ensure_ascii=False))

        messages = [{"role": "system", "content": sys_content}]
        messages += build_history(clue_id)

        answered = False
        if gtype == "mcp":
            answered = from_mcp_loop(messages, inp, perms, person, usertoken,
                                     persona=persona, clue_id=clue_id)

        # ---- 用户消息：有附件则组装成多模态 content 数组 ----
        # ★ 图片只能进 user 消息（Qwen3.5 模板对 system 含图会 raise_exception）
        ref_parts, used_vision, ref_note = ([], False, "")
        if refs:
            ref_parts, used_vision, ref_note = build_ref_content(refs)
            if ref_note:
                log(f"refs assembled: vision={used_vision} {ref_note}")

        if ref_parts:
            if ref_note:
                yield sse_frame("message", json.dumps(
                    {"choices": [{"delta": {"content": ref_note + "\n"}}]}, ensure_ascii=False))
            user_content = [{"type": "text", "text": inp}] + ref_parts
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": inp})

        try:
            extra = {"tools": []} if gtype == "mcp" else None
            if gtype == "mcp":
                # mcp 模式：先缓冲完整回答，检测 <tool_call> 文本泄漏后再下发
                # （下发给 O2OA 前端后无法撤回，必须先净场）
                if answered:
                    # 模型一轮内未调工具 → 最后一条 assistant 即最终回答，省一次重复生成
                    full = next((m.get("content") or "" for m in reversed(messages)
                                 if m.get("role") == "assistant"), "")
                    if not full or _leaked_tool_xml(full):
                        full = await _final_answer_mcp(messages, extra)
                else:
                    full = await _final_answer_mcp(messages, extra)
                content_parts.append(full)
                if full:
                    yield sse_frame("message", json.dumps(
                        {"choices": [{"delta": {"content": full}}]}, ensure_ascii=False))
            else:
                async for data, done in stream_sync_gen(messages, extra):
                    if done:
                        break
                    content_parts.append(pic_content(data))
                    yield sse_frame("message", data)
        except Exception as e:
            log(f"generate stream error: {e}")
        yield "data: [DONE]\n\n"
        final_text = "".join(content_parts)
        save_history(clue_id, inp, final_text)          # 内部上下文（build_history 用）
        completion_add(clue_id, person or uname, inp, final_text,  # 前端历史记录（按会话读取）
                       "chat", refs, person_dn=udn)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def stream_sync_gen(messages, extra=None):
    """httpx 同步流在 async 里的简单桥（低并发场景够用）"""
    import anyio
    it = stream_openai(messages, extra)
    while True:
        try:
            item = await anyio.to_thread.run_sync(lambda: next_gen(it))
        except StopIteration:
            return
        if item is None:
            return
        yield item


def next_gen(it):
    try:
        return next(it)
    except StopIteration:
        return None


def pic_content(data_str):
    try:
        j = json.loads(data_str)
        ch = (j.get("choices") or [{}])[0]
        return (((ch.get("delta") or {}).get("content")) or "")
    except Exception:
        return ""


def _strip_tool_xml(text):
    """剥离模型泄漏的 <tool_call>/<function=...> 工具调用文本块。"""
    text = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", text)
    text = re.sub(r"<tool_call>[\s\S]*$", "", text)   # 未闭合
    text = re.sub(r"<function=[\s\S]*$", "", text)    # 未闭合的 function 块
    return text.replace("</tool_call>", "").replace("<tool_call>", "").strip()


def _leaked_tool_xml(s):
    return ("<tool_call" in s) or ("<function=" in s)


async def _final_answer_mcp(messages, extra):
    """mcp 模式最终回答：
    1. 先缓冲整段（不逐帧转发 O2OA，避免泄漏后无法撤回）；
    2. 检出 <tool_call> 文本泄漏 → 追加强指令重试一次；
    3. 仍泄漏 → 剥离 XML；剥完为空 → 回退为最后一个工具结果摘要。"""
    import anyio

    async def collect(msgs):
        buf = []
        last_err = None
        for attempt, wait in enumerate((0, 3, 15)):   # 后端瞬时 400/断流 → 退避重试
            if wait:
                await anyio.sleep(wait)
            try:
                buf = []
                async for data, done in stream_sync_gen(msgs, extra):
                    if done:
                        break
                    buf.append(pic_content(data))
                last_err = None
                break
            except Exception as e:
                last_err = e
        if last_err is not None:
            raise last_err
        return "".join(buf)

    full = await collect(messages)
    if _leaked_tool_xml(full):
        log("final answer leaked tool-call XML, retry once with strict instruction")
        retry = messages + [{"role": "user", "content":
            "请直接输出最终中文回答本身（不要再调用工具，不要输出任何 XML 或工具调用语法）。"}]
        try:
            full = await collect(retry)
        except Exception as e:
            log(f"final retry error: {e}")
            full = ""
    if _leaked_tool_xml(full):
        full = _strip_tool_xml(full)
    if not full.strip():
        last_tool = next((m.get("content") for m in reversed(messages)
                          if m.get("role") == "tool"), "")
        full = ("（工具调用已完成。工具返回摘要：\n" + str(last_tool)[:600] +
                "\n）如需更完整的说明请继续提问。")
    return full


def from_mcp_loop(messages, inp, perms, person="", user_token="", persona="", clue_id=""):
    """mcp 模式：函数调用循环（内部非流式），结束后把上下文留在 messages 里供最终流式回答。
    返回 True 表示模型一轮内未调工具、最后一条 assistant 已是完整最终回答（可跳过二次生成）。

    ★ 工具来源有三类，合并后一起给模型：
       1. 内置本地工具（BUILTIN_TOOLS，含 skills_* 自主技能）—— 网关自带，开箱可用
       2. O2OA 配置的 HTTP 型 MCP 工具（kv 表 mcp:*）—— 用户在前端配的
       3. 标准 MCP 生态工具（config.mcp_servers，stdio/HTTP JSON-RPC）—— 名字加前缀
    ★ 第三批：persona 非空时按 persona_tools 白名单过滤工具可见性（管理员不限）。"""
    with db() as c:
        rows = c.execute("SELECT v FROM kv WHERE k LIKE 'mcp:%'").fetchall()
    tools_cfg = [json.loads(r[0]) for r in rows if json.loads(r[0]).get("enable", True)]

    # 内置工具（始终提供）
    tools = builtin_tool_defs()
    builtin_names = set(_BUILTIN_SPEC)

    # O2OA 的 HTTP 型 MCP 工具（名字与内置冲突时以内置优先）
    for m in tools_cfg:
        nm = safe_name(m.get("name"))
        if nm in builtin_names:
            log(f"mcp tool '{nm}' 与内置工具同名，跳过")
            continue
        props, req = {}, []
        for p in (m.get("mcpParameterList") or []):
            props[p.get("name")] = {"type": p.get("type") or "string",
                                    "description": p.get("desc") or ""}
            if p.get("required"):
                req.append(p.get("name"))
        tools.append({"type": "function", "function": {
            "name": nm, "description": m.get("desc") or m.get("displayName") or "",
            "parameters": {"type": "object", "properties": props, "required": req}}})

    # 标准 MCP 生态工具（stdio/HTTP JSON-RPC），名字前缀 {server}__{tool} 天然避冲突
    ext_defs, ext_dispatch = load_external_mcp(CFG.get("mcp_servers") or [])
    tools += ext_defs

    # 第三批：persona 工具白名单（对内置与外部工具统一过滤；manager=None 不限）
    wl = (CFG.get("persona_tools") or {}).get(persona)
    if wl is not None:
        allowed = set(wl)
        before = len(tools)
        tools = [t for t in tools if t["function"]["name"] in allowed]
        if before != len(tools):
            log(f"persona '{persona or '-'}' tool whitelist: {before} -> {len(tools)}")

    if not tools:
        messages.append({"role": "system", "content": "（当前没有可用工具，请直接回答）"})
        return

    tool_names = ", ".join(t["function"]["name"] for t in tools)
    sys_msg = ("你可以调用工具完成用户任务。可用工具：" + tool_names +
               "。涉及当前时间、算术、内部资料时必须调用工具，不要凭记忆回答。"
               "★ 同一次作答中不要重复调用参数完全相同的工具（结果不会变）；"
               "某个工具报错时，换参数或换工具，不要原样重试第三次。")
    # ★ 定位声明：本系统是「Bionic agent 能力 + O2OA 内网数据」，不是公网检索器。
    if not web_enabled():
        sys_msg += ("\n★ 本系统**只使用 O2OA 内部数据**（知识库、待办流程、组织架构、数据表、公文），"
                    "**没有联网能力**。涉及外部实时信息（天气/新闻/股价/政策）时，"
                    "必须如实说明系统内无此数据来源，严禁凭记忆编造具体数值。"
                    "\n【系统内数据地图（信息不足时按此顺序用足）】"
                    "\n  · 制度/文档/资料 → kb_search（本地知识库）"
                    "\n  · 业务台账/清单类数据 → query_rows。★ 严禁凭印象编造表名："
                    "第一次查某张表前，必须先调 query_table_list 拿到系统内真实存在的表名，"
                    "再用其中的名字或 alias 作为 table_flag"
                    "\n  · 我的任务 → list_my_todo → todo_detail（看详情与可走路由）；list_my_done 看已办"
                    "\n  · 人/部门 → search_org，org_unit_tree 看组织结构，org_person_identity 看某人身份职务"
                    "\n  · 流程与应用 → process_app_list"
                    "\n  · 公文/通知/制度文件 → cms_list → cms_detail 读正文"
                    "\n  · 附件/扫描件/图片里的文字 → ocr_file（file_id 取自待办或公文详情）"
                    "\n凡问题涉及上述内容，都必须先调工具取证再回答，不要凭记忆或常识作答。")
    # ★ 多步编排指引：只对"真的需要多步"的任务下发，避免简单问题被过度规划
    if CFG.get("orchestrator_enable", True) and "task_plan" in tool_names:
        sys_msg += ("\n【多步任务编排】当一件事需要 **3 步以上**系统内操作才能完成时"
                    "（例如'盘点某表里逾期未归还的资产并逐个生成催办记录'、"
                    "'汇总我本周待办并起草一份汇报'、'把某表数据校核后写回正确值'），"
                    "先用 task_plan(action=create) 登记计划，再逐步执行、每步用 "
                    "task_plan(action=update) 回填结果，最后 action=close 结项。"
                    "★ 简单问题（单次查询/单次计算/直接问答）**不要**建计划，直接答即可。"
                    "★ 计划中每个数据操作仍要真的调用对应业务工具（或 task_run_step）执行，"
                    "计划本身不产生任何数据变更；写类步骤同样受写回白名单与用户二次确认约束。"
                    "★ 若某步失败导致流程走不通，如实告知用户断在哪一步，并说明可用 "
                    "task_rollback 回滚（需用户确认）。")
    elif "web_search" not in tool_names:
        sys_msg += ("\n★ 你当前**没有**联网能力。遇到实时信息（天气/新闻/股价/政策）时，"
                    "必须如实说明无法查询，严禁凭记忆编造具体数值。")
    if person:
        sys_msg += (f"\n【身份与权限边界】当前用户：{person}。待办等查询类工具已按该身份过滤；"
                    "你只能代表该用户查询与操作，不得冒用、查询或替他人处理数据；"
                    "知识库写入默认以该用户署名。")
    # 第三批：具备写回权限的角色，主动注入白名单表字典（模型不必猜表名/字段名）
    if persona in (CFG.get("write_personas") or ["manager"]) and CFG.get("write_enable"):
        tbls = []
        for t in (CFG.get("write_tables") or []):
            sch = o2_table_schema(t)
            if sch:
                tbls.append("- " + _schema_desc(sch))
        if tbls:
            sys_msg += ("\n\n【数据写回能力】你可以帮用户向以下数据表写入数据（write_data 工具；"
                        "必须先不带 confirm 生成预案，经用户明确确认后再 confirm=true 执行）：\n"
                        + "\n".join(tbls)
                        + "\n注意：data 的键必须用字段的英文 name（如 productName），不要用中文描述词。"
                        "★ 写回流程必须通过 write_data 工具两步完成，严禁跳过工具调用、直接向用户"
                        "输出自编的'预案'文本——那不是真的预案，confirm 时会被系统拒绝。")
    # ★ 不新增第二条 system（Qwen3.5 模板限制），改写首条 system 追加说明
    if messages and messages[0].get("role") == "system":
        base_sys = messages[0].get("content") or ""
        msg_with_tools = [{"role": "system", "content": base_sys + "\n\n" + sys_msg}] + messages[1:]
    else:
        msg_with_tools = [{"role": "system", "content": sys_msg}] + messages
    msg_with_tools.append({"role": "user", "content": inp})

    max_turns = int(CFG.get("mcp_max_turns") or 20)
    deadline = time.time() + float(CFG.get("mcp_timeout") or 180)
    answered = False  # 模型一轮内未调任何工具 → 该回答即最终回答
    # 第四批：熔断与观测
    seen = {}          # (tool, canonical_args) -> 次数，用于识别原地打转
    repeats = 0        # 重复调用累计；超阈值即中断循环，避免耗满超时
    tool_steps = []    # (name, ok) 供 trace 与前端进度
    for turn in range(max_turns):
        if time.time() > deadline:
            log(f"mcp loop timeout at turn {turn}")
            break
        # 后端偶发 400（模型换载/繁忙窗口，实测 qwen3.8-27b@LM Studio）→ 重试而非放弃
        m = None
        for attempt in range(3):
            try:
                r = _client.post(f"{CFG['bionic_base']}/v1/chat/completions",
                                 headers=auth_hdr(),
                                 json={"model": CFG["chat_model"], "messages": msg_with_tools,
                                       "tools": tools})
                if r.status_code != 200:
                    log(f"mcp loop http {r.status_code} (attempt {attempt+1}): {r.text[:300]}")
                    r.raise_for_status()
                m = r.json()["choices"][0]["message"]
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 + attempt * 2)
        if m is None:
            log("mcp loop error: model call failed after retries")
            break
        calls = m.get("tool_calls") or []
        if not calls:
            msg_with_tools.append({"role": "assistant", "content": m.get("content") or ""})
            answered = True
            break
        msg_with_tools.append({"role": "assistant", "content": m.get("content") or "",
                               "tool_calls": calls})
        for call in calls:
            fname = call["function"]["name"]
            raw_args = call["function"].get("arguments") or "{}"
            try:
                fargs = json.loads(raw_args)
            except Exception:
                fargs = {}
            # ---- 熔断①：完全相同的调用重复 ≥3 次 → 直接回灌提示，不再真的执行 ----
            try:
                sig = (fname, json.dumps(fargs, sort_keys=True, ensure_ascii=False))
            except Exception:
                sig = (fname, str(raw_args))
            seen[sig] = seen.get(sig, 0) + 1
            if seen[sig] >= 3:
                repeats += 1
                result = (f"ERROR: 你已用完全相同的参数调用 {fname} {seen[sig]-1} 次，"
                          "结果不会改变。请改用不同参数、换用其它工具，或直接基于已有信息作答。")
                log(f"tool {fname} REPEAT#{seen[sig]} args={fargs} -> blocked")
                msg_with_tools.append({"role": "tool",
                                       "tool_call_id": call.get("id") or fname,
                                       "content": result})
                tool_steps.append((fname, False))
                continue
            # 先查内置，再查标准 MCP，最后查 O2OA HTTP 型 MCP
            t_start = time.time()
            try:
                if fname in _BUILTIN_SPEC:
                    result = exec_builtin(fname, fargs, person=person, perms=perms,
                                          user_token=user_token, persona=persona, clue_id=clue_id)
                elif fname in ext_dispatch:
                    result = call_external_tool(fname, ext_dispatch, fargs)
                else:
                    target = next((t for t in tools_cfg if safe_name(t.get("name")) == fname), None)
                    result = exec_tool(target, fargs) if target else f"unknown tool {fname}"
            except Exception as e:
                # 工具自身异常不得打断整个循环（第四批：单工具失败可降级）
                result = f"ERROR: 工具 {fname} 执行异常：{type(e).__name__}: {e}"
                log(f"tool {fname} raised: {e}")
            result = "" if result is None else str(result)
            dt = time.time() - t_start
            ok_ = not result.startswith(("ERROR", "抓取被拒绝", "抓取失败",
                                         "联网搜索暂时不可用", "MCP_CALL_ERROR"))
            tool_steps.append((fname, ok_))
            log(f"tool {fname} user={person or 'anonymous'} {dt:.1f}s args={fargs} -> {result[:120]}")
            msg_with_tools.append({"role": "tool", "tool_call_id": call.get("id") or fname,
                                   "content": result[:8000]})
        # ---- 熔断②：重复调用累计过多 → 结束循环，逼模型收口 ----
        if repeats >= 3:
            log(f"mcp loop aborted: too many repeated calls ({repeats})")
            break
    # 工具轨迹落日志（可观测：/gateway/trace 可查最近一次的工具链）
    if tool_steps:
        log("mcp loop steps: " + " → ".join(f"{n}{'' if ok else '(fail)'}"
                                            for n, ok in tool_steps))
    trace_publish(clue_id, tool_steps)
    # ★ 工具循环结束后，必须明确告诉模型"停止调用工具、直接作答"。
    #   否则最终流式请求未带 tools 参数时，模型会把 tool_call 语法当成纯文本吐出来。
    if not answered:
        if msg_with_tools and msg_with_tools[0].get("role") == "system":
            msg_with_tools[0]["content"] = (msg_with_tools[0].get("content") or "") + (
                "\n\n【系统指令】工具调用已结束。现在请直接根据上面工具返回的结果，"
                "用自然语言完整回答用户的问题。不要输出任何 XML/JSON 格式的工具调用文本，"
                "不要再请求调用工具。")
        # 双保险：以"最后一条 user 指令"再压一次（部分模型对 system 后缀不敏感，
        # 但会严格服从最近的 user 指令；Qwen3.8-27B 实测会复发 <tool_call> 文本泄漏）
        msg_with_tools.append({"role": "user", "content":
            "（系统提示）所有工具调用均已完成并返回结果。请立即基于以上结果直接输出面向用户的"
            "最终中文回答；严禁再输出 <tool_call>、<function= 等任何工具调用语法。"})
    messages.clear()
    messages.extend(msg_with_tools)
    return answered



def save_history(clue_id, inp, content):
    if not clue_id:
        return
    with db() as c:
        k = f"hist:{clue_id}:{int(time.time() * 1000)}"
        c.execute("INSERT INTO kv(k,v) VALUES(?,?)",
                  (k, json.dumps({"t": time.time(), "input": inp, "content": content},
                                 ensure_ascii=False)))


# ---------- 知识库索引 ----------
@app.post("/idx-gateway-doc/update")
async def idx_update(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    d = await request.json()
    doc_id = d.get("id") or str(uuid.uuid4())
    with db() as c:
        c.execute("""INSERT INTO docs(id,title,category,content,creator_person,creator_unit,
                     question_enable,permission,meta,updated)
                     VALUES(?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET title=excluded.title, category=excluded.category,
                     content=excluded.content, creator_person=excluded.creator_person,
                     creator_unit=excluded.creator_unit, question_enable=excluded.question_enable,
                     permission=excluded.permission, meta=excluded.meta, updated=excluded.updated""",
                  (doc_id, d.get("title") or "", d.get("category") or "", d.get("content") or "",
                   d.get("creatorPerson") or "", d.get("creatorUnit") or "",
                   1 if d.get("questionEnable") else 0,
                   json.dumps(d.get("permissionList") or [], ensure_ascii=False),
                   json.dumps({k: str(v) for k, v in d.items() if k not in
                               ("permissionList", "content")}, ensure_ascii=False),
                   time.time()))
    reindex_doc(doc_id)
    return ok(d)


@app.post("/idx-gateway-doc/list/paging/{page}/size/{size}")
async def idx_list(page: int, size: int, request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await request.json() if request.headers.get("content-length", "0") not in ("", "0") else {}
    search = (body or {}).get("search") or ""
    with db() as c:
        if search:
            rows = c.execute(
                "SELECT meta FROM docs WHERE title LIKE ? OR category LIKE ? OR content LIKE ? "
                "ORDER BY updated DESC LIMIT ? OFFSET ?",
                (f"%{search}%", f"%{search}%", f"%{search}%", size, (page - 1) * size)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM docs WHERE title LIKE ? OR category LIKE ? "
                              "OR content LIKE ?",
                              (f"%{search}%", f"%{search}%", f"%{search}%")).fetchone()[0]
        else:
            rows = c.execute("SELECT meta FROM docs ORDER BY updated DESC LIMIT ? OFFSET ?",
                             (size, (page - 1) * size)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    data = []
    for (meta,) in rows:
        try:
            d = json.loads(meta)
        except Exception:
            continue
        d.pop("permissionList", None)
        data.append(d)
    return ok(data, total)


@app.post("/idx-gateway-doc/delete")
async def idx_delete(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await request.json() if request.headers.get("content-length", "0") not in ("", "0") else {}
    flag = (body or {}).get("id") or (body or {}).get("flag") or ""
    with db() as c:
        c.execute("DELETE FROM docs WHERE id=?", (flag,))
        c.execute("DELETE FROM chunks WHERE doc_id=?", (flag,))
    return ok(True)


@app.post("/gateway-doc/upload/{doc_id}/mode/{mode}")
async def doc_upload(doc_id: str, mode: str, request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    ctype = request.headers.get("content-type", "")
    if "multipart/form-data" not in ctype:
        return JSONResponse({"type": "error", "message": "expect multipart"}, status_code=400)
    from fastapi import Form  # noqa
    boundary = ctype.split("boundary=")[-1].encode()
    raw = await request.body()

    def parse_multipart(raw_body, bnd):
        parts = []
        for seg in raw_body.split(b"--" + bnd):
            seg = seg.strip(b"\r\n")
            if not seg or seg == b"--":
                continue
            if b"\r\n\r\n" not in seg:
                continue
            head, _, content = seg.partition(b"\r\n\r\n")
            content = content.rsplit(b"\r\n", 1)[0]
            fname = ""
            for hl in head.split(b"\r\n"):
                if hl.lower().startswith(b"content-disposition"):
                    m = re.search(rb'filename="([^"]*)"', hl)
                    if m:
                        fname = m.group(1).decode("utf-8", "ignore")
            parts.append((fname, content))
        return parts

    texts = []
    for fname, content in parse_multipart(raw, boundary):
        ext = os.path.splitext(fname)[1].lower()
        texts.append((fname, extract_text_index(ext, content)))
    merged = "\n\n".join(f"【附件：{fn}】\n{tx}" for fn, tx in texts if tx)
    with db() as c:
        row = c.execute("SELECT id FROM docs WHERE id=?", (doc_id,)).fetchone()
        if row:
            c.execute("UPDATE docs SET content=COALESCE(content,'')||?, updated=? WHERE id=?",
                      ("\n\n" + merged, time.time(), doc_id))
        else:
            c.execute("""INSERT INTO docs(id,title,category,content,permission,meta,updated)
                         VALUES(?,?,?,?,?,?,?)""",
                      (doc_id, f"附件集{doc_id[:8]}", "attachment", merged, "[]", "{}", time.time()))
    reindex_doc(doc_id)
    return ok({"id": doc_id, "files": [fn for fn, _ in texts]})


def extract_text_index(ext, raw: bytes) -> str:
    """文档索引（/idx-gateway-*）侧的附件文本提取。

    命名说明：不要叫 extract_text —— 上面已有一个同名的 3 参数版本
    （对话附件用），Python 后定义者会覆盖前者，曾因此踩坑报
    "extract_text() takes 2 positional arguments but 3 were given"。

    与对话侧的 extract_text(data, ext, name) 区别：这里必须返回文本（"" 表示空），
    因为索引流水线会把它入库分块。导入的附件常常是扫描件 PDF / 截图，
    所以 PDF 走"文本层优先，空则 OCR"；图片一律走 OCR。
    """
    try:
        if ext in (".txt", ".md", ".csv", ".json", ""):
            return raw.decode("utf-8", "ignore")
        if ext == ".docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if ext == ".xlsx":
            import io
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), read_only=True)
            out = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    out.append("\t".join("" if v is None else str(v) for v in row))
            return "\n".join(out)
        if ext == ".pdf":
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
            # 文本层够用就直接返回（扫描件 PDF 这里会几乎为空）
            if len(text) >= max(30, len(reader.pages) * 30):
                return text
            # 文本层稀薄 -> 交给 OCR 服务做渲染识别
            ocr = CFG.get("ocr_base") or ""
            if ocr:
                import base64
                try:
                    r = _client.post(f"{ocr}/ocr", timeout=600,
                                     json={"file_b64": base64.b64encode(raw).decode("ascii"),
                                           "filename": "index.pdf"})
                    if r.status_code == 200:
                        j = r.json() or {}
                        ocr_txt = (j.get("text") or "").strip()
                        if ocr_txt:
                            log(f"idx pdf OCR fallback: {len(ocr_txt)} chars "
                                f"(text-layer only {len(text)})")
                            return ocr_txt
                    else:
                        log(f"idx ocr pdf -> HTTP {r.status_code}")
                except Exception as e:
                    log(f"idx ocr pdf err: {e}")
            return text
        # 图片：走 OCR
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"):
            ocr = CFG.get("ocr_base") or ""
            if ocr:
                import base64
                r = _client.post(f"{ocr}/ocr", timeout=300,
                                 json={"file_b64": base64.b64encode(raw).decode("ascii"),
                                       "filename": f"index{ext}"})
                if r.status_code == 200:
                    return ((r.json() or {}).get("text") or "").strip()
                log(f"idx ocr image -> HTTP {r.status_code}")
            return ""
        return raw.decode("utf-8", "ignore")
    except Exception as e:
        log(f"extract {ext} error: {e}")
        return ""


# ---------- 通用 CRUD：endpoint / mcp / completion / clue ----------
# 说明：clue / completion 的【列表】与【删除】需要按会话聚合、级联清理，
# 故单独实现（list_routes=False / delete_routes=False 时跳过通用版注册）。
def crud_routes(prefix, store_key, list_routes=True, delete_routes=True):
    async def create(request: Request):
        if not check_token(request):
            return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
        d = await request.json()
        d.setdefault("id", str(uuid.uuid4()))
        d.setdefault("createDateTime", time.strftime("%Y-%m-%d %H:%M:%S"))
        with db() as c:
            c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                      (f"{store_key}:{d['id']}", json.dumps(d, ensure_ascii=False)))
        return ok(d)

    async def update(flag: str, request: Request):
        if not check_token(request):
            return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
        d = await request.json()
        d["id"] = flag
        d.setdefault("updateDateTime", time.strftime("%Y-%m-%d %H:%M:%S"))
        with db() as c:
            c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                      (f"{store_key}:{flag}", json.dumps(d, ensure_ascii=False)))
        return ok(d)

    async def get_one(flag: str):
        with db() as c:
            row = c.execute("SELECT v FROM kv WHERE k=?", (f"{store_key}:{flag}",)).fetchone()
        return ok(json.loads(row[0]) if row else None)

    async def delete_one(flag: str):
        with db() as c:
            c.execute("DELETE FROM kv WHERE k=?", (f"{store_key}:{flag}",))
        return ok(True)

    async def list_paging(page: int, size: int, request: Request):
        if not check_token(request):
            return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
        with db() as c:
            rows = c.execute("SELECT v FROM kv WHERE k LIKE ? ORDER BY k LIMIT ? OFFSET ?",
                             (f"{store_key}:%", size, (max(page, 1) - 1) * size)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM kv WHERE k LIKE ?",
                              (f"{store_key}:%",)).fetchone()[0]
        data = []
        for (v,) in rows:
            try:
                data.append(json.loads(v))
            except Exception:
                pass
        return ok(data, total)

    app.post(f"/ai-gateway-{prefix}/create")(create)
    app.post(f"/ai-gateway-{prefix}/update")(update)
    app.post(f"/ai-gateway-{prefix}/get/{{flag}}")(get_one)
    app.get(f"/ai-gateway-{prefix}/get/{{flag}}")(get_one)
    if delete_routes:
        app.post(f"/ai-gateway-{prefix}/delete")(delete_one)
        app.get(f"/ai-gateway-{prefix}/delete/{{flag}}")(delete_one)
    if list_routes:
        app.post(f"/ai-gateway-{prefix}/list/paging/{{page}}/size/{{size}}")(list_paging)
        app.get(f"/ai-gateway-{prefix}/list/paging/{{page}}/size/{{size}}")(list_paging)


crud_routes("endpoint", "endpoint")
crud_routes("mcp", "mcp")
# clue 的列表/删除走下方按会话聚合的专用实现（含级联清理 completion/hist）
crud_routes("clue", "clue", list_routes=False, delete_routes=False)


# ---------- 会话（clue）与问答（completion）持久化 ----------
# O2OA AI 模块在【网关模式】下把 clue/completion 的读写全部委托给本网关
# （x_ai_assemble_control 的 ActionListPaging/ActionListCompletionPaging/
#   ActionWriteCompletion/ActionDelete 分别请求 /ai-gateway-clue/* 与
#   /ai-gateway-completion/*），因此网关必须自己落库，否则前端"历史记录"永远为空。
def _o2_now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _kv_items(prefix):
    """读取 kv 中某前缀的全部 JSON 记录（解析失败的条目跳过）。"""
    with db() as c:
        rows = c.execute("SELECT v FROM kv WHERE k LIKE ?", (f"{prefix}:%",)).fetchall()
    out = []
    for (v,) in rows:
        try:
            out.append(json.loads(v))
        except Exception:
            pass
    return out


def _kv_put(key, obj):
    with db() as c:
        c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                  (key, json.dumps(obj, ensure_ascii=False)))


def _title_of(text, n=24):
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:n] or "新对话"


def clue_touch(clue_id, person, title=None, person_dn=""):
    """会话记录：首轮创建（标题取首问），后续轮次只刷新时间，不覆盖已有标题。
    personList 同时写入人员 DN 与姓名：模块按 DN 过滤，多存一份可兼容两种口径。"""
    if not clue_id:
        return
    now = _o2_now()
    ms = int(time.time() * 1000)
    with db() as c:
        row = c.execute("SELECT v FROM kv WHERE k=?", (f"clue:{clue_id}",)).fetchone()
        d = {}
        if row:
            try:
                d = json.loads(row[0])
            except Exception:
                d = {}
        d.setdefault("id", clue_id)
        d.setdefault("createDateTime", now)
        d.setdefault("createTime", ms)
        if person:
            d["person"] = person
        else:
            d.setdefault("person", "")
        if person_dn:
            d["personDn"] = person_dn
        plist = [x for x in (d.get("personList") or []) if x]
        for x in (person_dn, person, d.get("person")):
            if x and x not in plist:
                plist.append(x)
        d["personList"] = plist
        cur = d.get("title") or ""
        if title and (not cur or cur in ("新对话", "新会话", "未命名")):
            d["title"] = title
        d.setdefault("title", "新对话")
        d["updateDateTime"] = now
        d["updateTime"] = ms
        c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                  (f"clue:{clue_id}", json.dumps(d, ensure_ascii=False)))


def completion_add(clue_id, person, inp, content, generate_type="chat", refs=None, person_dn=""):
    """落一条问答记录（供前端按会话读取）。带 2 分钟内同内容去重，
    避免与模块自身可能发起的回写重复。"""
    if not clue_id:
        return
    content = content or ""
    for it in _kv_items("completion"):
        if (it.get("clueId") == clue_id and (it.get("input") or "") == (inp or "")
                and (it.get("content") or "") == content):
            try:
                if time.time() - float(it.get("createTime", 0)) / 1000.0 < 120:
                    return
            except Exception:
                pass
    now = _o2_now()
    ms = int(time.time() * 1000)
    d = {"id": str(uuid.uuid4()), "clueId": clue_id, "person": person or "",
         "personDn": person_dn or "",
         "input": inp or "", "content": content, "generateType": generate_type,
         "referenceIdList": refs or [],
         "createDateTime": now, "updateDateTime": now, "createTime": ms, "updateTime": ms}
    _kv_put(f"completion:{d['id']}", d)


def clue_drop(clue_id):
    """删除会话，并级联清理其问答与上下文历史。"""
    if not clue_id:
        return
    # 先取待删的问答 id（避免在同一个 with db() 内嵌套开连接）
    victims = [it["id"] for it in _kv_items("completion")
               if it.get("clueId") == clue_id and it.get("id")]
    with db() as c:
        c.execute("DELETE FROM kv WHERE k=?", (f"clue:{clue_id}",))
        c.execute("DELETE FROM kv WHERE k LIKE ?", (f"hist:{clue_id}:%",))
        for cid in victims:
            c.execute("DELETE FROM kv WHERE k=?", (f"completion:{cid}",))


def _int_ids(body):
    ids = []
    for k in ("clueId", "id"):
        v = body.get(k)
        if isinstance(v, str) and v.strip():
            ids.append(v.strip())
    for k in ("idList", "clueIdList"):
        v = body.get(k)
        if isinstance(v, list):
            ids += [x for x in v if isinstance(x, str) and x.strip()]
    return list(dict.fromkeys(ids))


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


@app.post("/ai-gateway-clue/list/paging/{page}/size/{size}")
async def clue_list(page: int, size: int, request: Request):
    """会话列表：按人过滤（person/personList），按创建时间倒序。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await _body(request)
    persons = []
    if isinstance(body.get("personList"), list):
        persons += [x for x in body["personList"] if isinstance(x, str) and x]
    if isinstance(body.get("person"), str) and body["person"]:
        persons.append(body["person"])
    if isinstance(request.query_params.get("person"), str):
        persons.append(request.query_params["person"])
    log(f"clue_list body_keys={sorted(body.keys())} persons={persons}")
    items = _kv_items("clue")
    if persons:
        # 模块按 personList=[人员DN] 过滤；记录里可能只有姓名（旧数据）→ 两种口径都匹配
        keys = set()
        for p in persons:
            keys.add(p.strip().lower())
            keys.add(p.split("@")[0].strip().lower())
        keys.discard("")

        def _own(x):
            cand = [x.get("person"), x.get("personDn")] + list(x.get("personList") or [])
            for v in cand:
                if not v:
                    continue
                v = str(v).strip().lower()
                if v in keys or v.split("@")[0] in keys:
                    return True
            return False

        items = [x for x in items if _own(x)]
    items.sort(key=lambda x: (x.get("createDateTime") or "", x.get("updateDateTime") or ""),
               reverse=True)
    total = len(items)
    start = (max(page, 1) - 1) * max(size, 1)
    return ok(items[start:start + max(size, 1)], total)


@app.post("/ai-gateway-clue/delete")
async def clue_delete(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await _body(request)
    ids = _int_ids(body)
    log(f"clue_delete ids={ids} body_keys={sorted(body.keys())}")
    for cid in ids:
        clue_drop(cid)
    return ok(True)


@app.get("/ai-gateway-clue/delete/{flag}")
async def clue_delete_one(flag: str, request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    clue_drop(flag)
    return ok(True)


@app.post("/ai-gateway-completion/write/extra")
async def write_extra(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    d = await request.json()
    d.setdefault("id", str(uuid.uuid4()))
    with db() as c:
        c.execute("INSERT INTO kv(k,v) VALUES(?,?)", (f"completion:{d['id']}",
                                                      json.dumps(d, ensure_ascii=False)))
    return ok(d)


@app.post("/ai-gateway-completion/list/paging/{page}/size/{size}")
async def completion_list(page: int, size: int, request: Request):
    """某会话的问答记录。clueId 可能出现在 body（clueId/clueIdList）或 query 上；
    两者都没有则返回全部（由调用方自行过滤），保证前端至少能拿到数据。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await _body(request)
    ids = _int_ids(body)
    q = request.query_params.get("clueId")
    if q:
        ids.append(q)
    log(f"completion_list body_keys={sorted(body.keys())} clue_ids={ids}")
    items = _kv_items("completion")
    if ids:
        items = [x for x in items if x.get("clueId") in ids]
    items.sort(key=lambda x: (x.get("createDateTime") or "", x.get("createTime") or 0))
    total = len(items)
    start = (max(page, 1) - 1) * max(size, 1)
    return ok(items[start:start + max(size, 1)], total)


@app.get("/ai-gateway-completion/list/paging/{page}/size/{size}")
async def completion_list_get(page: int, size: int, request: Request):
    return await completion_list(page, size, request)


# ---------- 运维 ----------
@app.get("/gateway/health")
async def health():
    return {"status": "ok", "embed_model": emb_model(), "chat_model": CFG["chat_model"]}


@app.get("/gateway/capabilities")
async def capabilities(request: Request):
    """网关能力自检：后端 / 工具 / OCR / 多模态 一览。
    方便升级后快速确认"哪一项没配起来"。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)

    def probe(url, headers=None, timeout=6):
        try:
            r = _client.get(url, headers=headers or {}, timeout=timeout)
            return {"up": r.status_code == 200, "http": r.status_code,
                    **(r.json() if r.status_code == 200 else {})}
        except Exception as e:
            return {"up": False, "error": str(e)[:120]}

    chat = probe(f"{CFG['bionic_base']}/props")
    caps = chat.get("chat_template_caps") or {}
    mods = chat.get("modalities") or {}
    ocr_base = CFG.get("ocr_base") or ""
    return ok({
        "chat_backend": {
            "base": CFG["bionic_base"], "up": chat.get("up", False),
            "model": CFG.get("chat_model"),
            "tool_calls": caps.get("supports_tool_calls"),
            "parallel_tool_calls": caps.get("supports_parallel_tool_calls"),
            "vision": mods.get("vision"),
            "video": mods.get("video"),
        },
        "embed_backend": {"base": CFG["embed_base"],
                          "up": probe(f"{CFG['embed_base']}/health").get("up", False),
                          "model": emb_model()},
        "ocr": {**probe(f"{ocr_base}/health"), "base": ocr_base,
                "enabled": bool(ocr_base)},
        # ★ 必须用过滤后的实际注册列表（web_enable=False 时不含 web_*），
        #   否则 capabilities 会谎报"有联网工具"（查了才发现是坑）。
        "builtin_tools": [d["function"]["name"] for d in builtin_tool_defs()],
        "builtin_tools_all": [t["name"] for t in BUILTIN_TOOLS],
        # 第四批：联网检索通道自检（多引擎逐个探活，一眼看出"哪个引擎挂了"）
        "web_search": {"engines": web_probe(),
                       "last_used": _web_last_probe.get("engine") or "",
                       "allow_private": bool(CFG.get("web_allow_private")),
                       "deny_domains": CFG.get("web_domain_deny") or []},
        # 第五批：系统内 agent 能力（定位纠偏 —— 只吃 O2OA 自身数据）
        "web_enable": web_enabled(),
        "positioning": ("系统内数据闭环：Bionic agent 能力 + O2OA 业务数据"
                        "（待办/组织/数据表/公文/流程），默认不联网" if not web_enabled()
                        else "已开启联网能力"),
        "internal_capability": {
            "o2oa_base": CFG.get("o2oa_base"),
            "o2oa_login_user": kv_get("o2oa_token_user") or "",   # 实际生效账号
            "o2oa_svc_user": CFG.get("o2oa_svc_user") or "",
            "groups": {
                "待办流程": ["list_my_todo", "todo_detail", "list_my_done"],
                "组织架构": ["search_org", "org_unit_tree", "org_person_identity"],
                "数据表": ["query_table_list", "query_rows"],
                "公文信息": ["cms_list", "cms_detail", "cms_channels"],
                "流程应用": ["process_app_list"],
                "知识库": ["kb_search", "kb_read", "kb_save", "ocr_file"],
                "多步编排": ["task_plan", "task_run_step", "task_rollback"],
                "设计态": ["design_op", "design_rollback"],
                "成长感知": ["kb_ingest", "kb_reflect", "growth_report"],
            },
            "memory_layers": memory_layer_stats(),
        },
        # 第五批：多步任务编排可用性（任务账本外置在 kv 表，可查/可续/可回滚）
        "orchestrator": {
            "enable": bool(CFG.get("orchestrator_enable", True)),
            "max_steps": CFG.get("orchestrator_max_steps"),
            "ttl": CFG.get("orchestrator_ttl"),
            "rollback": bool(CFG.get("orchestrator_rollback", True)),
            "active_plans": _count_active_plans(),
            "_note": "不另起 planner 模型（省显存）；编排状态外置 kv，主模型按工具协议驱动",
        },
        # 第四批：Bionic 会话委派可用性
        "bionic_cli": {"enable": bool(CFG.get("bionic_cli_enable", True)),
                       "model": CFG.get("bionic_cli_model") or CFG.get("chat_model"),
                       "timeout": CFG.get("bionic_cli_timeout"),
                       "max_per_turn": CFG.get("bionic_cli_max_per_turn"),
                       "max_concurrent": CFG.get("bionic_cli_max_concurrent"),
                       "busy": _cli_busy.get("n", 0),
                       "lms_found": bool(_lms_path()),
                       "_note": "主路径走 HTTP 复用已加载模型；lms 仅作兜底"},
        "skills": [i["name"] for i in _list_skills()],
        "external_mcp": [
            {"name": s.get("name"), "transport": s.get("transport") or "stdio",
             **({"command": s.get("command"), "args": s.get("args")}
                if (s.get("transport") or "stdio") == "stdio" else {"url": s.get("url")})}
            for s in (CFG.get("mcp_servers") or [])],
        "o2oa": {**probe(f"{CFG.get('o2oa_base','')}/x_processplatform_assemble_designer/jaxrs/application/list",
                         headers={"x-token": o2oa_token()}),
                 "base": CFG.get("o2oa_base") or "",
                 "admin_token_set": bool(o2oa_token())},
        "config": {"mcp_max_turns": CFG.get("mcp_max_turns"),
                   "mcp_timeout": CFG.get("mcp_timeout"),
                   "rag_top_k": CFG.get("rag_top_k"),
                   "rag_rerank_candidate": CFG.get("rag_rerank_candidate"),
                   "rerank_enabled": bool(CFG.get("rerank_enable") and CFG.get("rerank_base")),
                   "rerank_model": CFG.get("rerank_model"),
                   "rewrite_enabled": bool(CFG.get("rewrite_enable")),
                   "ocr_max_chars": CFG.get("ocr_max_chars"),
                   "persona_enable": bool(CFG.get("persona_enable")),
                   "write_enable": bool(CFG.get("write_enable")),
                   "write_tables": CFG.get("write_tables"),
                   "design_enable": bool(CFG.get("design_enable")),
                   "design_personas": CFG.get("design_personas"),
                   "design_denylist": CFG.get("design_denylist"),
                   "web_retry": CFG.get("web_retry"),
                   "tool_repeat_guard": 3,
                   "trace_enable": True},
    })


@app.get("/gateway/feedbacks")
async def feedbacks_list(request: Request, status: str = "", page: int = 1, size: int = 50):
    """管理员查看用户反馈（feedback 工具落库），支持按状态过滤。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    with db() as c:
        if status:
            rows = c.execute(
                "SELECT id,person,kind,content,created_at,status FROM feedbacks "
                "WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, size, (page - 1) * size)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM feedbacks WHERE status=?",
                              (status,)).fetchone()[0]
        else:
            rows = c.execute(
                "SELECT id,person,kind,content,created_at,status FROM feedbacks "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (size, (page - 1) * size)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM feedbacks").fetchone()[0]
    return ok([{"id": r[0], "person": r[1], "kind": r[2], "content": r[3],
                "createdAt": r[4], "status": r[5]} for r in rows], count=total)


@app.post("/gateway/feedbacks/update")
async def feedbacks_update(request: Request):
    """管理员处理反馈：标记状态（如 open -> done，形成闭环）。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    b = await request.json()
    fid = (b.get("id") or "").strip()
    st = (b.get("status") or "done").strip()
    if not fid:
        return JSONResponse({"type": "error", "message": "id required"}, status_code=400)
    with db() as c:
        cur = c.execute("UPDATE feedbacks SET status=? WHERE id=?", (st, fid))
    return ok({"updated": cur.rowcount, "id": fid, "status": st})


@app.get("/gateway/audit")
async def audit_list(request: Request, limit: int = 100, status: str = "",
                     person: str = "", tool: str = ""):
    """第三批：管理员查看写回/敏感动作审计日志（write_data 的 pending/executed/failed/refused）。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    limit = max(1, min(int(limit or 100), 500))
    sql, args_ = "SELECT ts,person,clue_id,tool,payload,status,detail FROM audit_log", []
    conds = []
    if status:
        conds.append("status=?"); args_.append(status)
    if person:
        conds.append("person LIKE ?"); args_.append(f"%{person}%")
    if tool:
        conds.append("tool=?"); args_.append(tool)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC LIMIT ?"
    args_.append(limit)
    with db() as c:
        rows = c.execute(sql, args_).fetchall()
    return ok([{"ts": r[0], "person": r[1], "clueId": r[2], "tool": r[3],
                "payload": r[4], "status": r[5], "detail": r[6]} for r in rows],
              count=len(rows))


@app.get("/gateway/trace")
async def trace_list(request: Request, clue_id: str = "", limit: int = 20):
    """第四批：查看最近若干会话的【工具调用链】。
    排障用途：一眼看出某次回答是"没调工具硬答"、"调了但工具失败"、还是"原地打转被熔断"。
    不传 clue_id 时返回最近若干会话的轨迹。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    limit = max(1, min(int(limit or 20), 200))
    with db() as c:
        if clue_id:
            rows = c.execute("SELECT k,v FROM kv WHERE k=?", (f"trace:{clue_id}",)).fetchall()
        else:
            rows = c.execute("SELECT k,v FROM kv WHERE k LIKE 'trace:%' ORDER BY k DESC LIMIT ?",
                             (limit,)).fetchall()
    out = []
    for k, v in rows:
        try:
            d = json.loads(v)
        except Exception:
            continue
        out.append({"clueId": k.split(":", 1)[1], **d})
    return ok(out, count=len(out))


@app.post("/ai-gateway/report-query")
async def report_query(request: Request):
    """报表自然语言查询：基于 O2OA 实时数据快照，用大模型回答用户的自然语言问题。"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    body = await request.json()
    q = (body.get("input") or body.get("query") or "").strip()
    if not q:
        return ok({"answer": "请输入你想查询的问题，例如：当前有哪些业务应用？"}, snapshot_chars=0)
    snap = o2oa_snapshot()
    sys = ("你是 O2OA 企业系统的数据分析与报表助手。下面是本组织 O2OA 实例的实时数据快照"
           "（应用/门户等业务模块目录）。请基于快照用简体中文回答用户问题；涉及多项数据时用 Markdown 表格；"
           "若快照数据不足以回答，请如实说明并建议补充哪些数据源（如流程实例量、表单数据等）。")
    answer = chat_complete([{"role": "system", "content": sys},
                           {"role": "user", "content": f"数据快照:\n{snap}\n\n用户问题: {q}"}],
                          max_tokens=1500, temperature=0.2)
    return ok({"answer": answer, "snapshot_chars": len(snap)})


@app.post("/gateway/ocr-test")
async def ocr_test(request: Request):
    """把网关的 extract_text 走一遍，用于验证附件链路是否打通。
    body: {"file_b64": "...", "filename": "a.pdf"} 或 {"path": "D:\\x.png"}"""
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    import base64
    body = await request.json()
    if body.get("path"):
        p = body["path"]
        if not os.path.isfile(p):
            return JSONResponse({"type": "error", "message": f"no such file {p}"},
                                status_code=400)
        data = Path(p).read_bytes()
        name = os.path.basename(p)
    else:
        b64 = body.get("file_b64") or body.get("image_b64") or body.get("pdf_b64") or ""
        if not b64:
            return JSONResponse({"type": "error", "message": "need file_b64 or path"},
                                status_code=400)
        data = base64.b64decode(b64)
        name = body.get("filename") or "inline.bin"
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    t0 = time.time()
    text = extract_text(data, ext, name)
    return ok({"filename": name, "ext": ext, "chars": len(text or ""),
               "ms": int((time.time() - t0) * 1000),
               "text": (text or "")[:4000], "truncated": len(text or "") > 4000})


@app.post("/gateway/reindex")
async def reindex_all(request: Request):
    if not check_token(request):
        return JSONResponse({"type": "error", "message": "bad token"}, status_code=401)
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM docs")]
    for i in ids:
        reindex_doc(i)
    return ok({"reindexed": len(ids)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CFG["listen_host"], port=CFG["listen_port"], log_level="warning")
