# -*- coding: utf-8 -*-
"""
自建语句 SQL 重写器 (fix_statement_sql.py)
==========================================

背景（2026-09-20 定位到的三个系统性缺陷）：

  O2OA 语句执行链：ActionExecuteV2 -> ExecuteTargetBuilder.build()
    format in (sql, sqlScript)  -> concreteExecuteTargetSql -> ExecuteTargetBuilder
    format == jpql              -> concreteExecuteTargetJpql
  然后 Executor.executeData():
    format in (sql, sqlScript)  -> executeDataSql(runtime, target, **false**)   # 不重写表名
    语句含 " JOIN " 且 " ON "   -> executeDataSql(runtime, target, **true**)    # 重写表名
    否则                        -> executeDataJpql(...)

  重写逻辑 Executor.joinSql():
    sql.replaceAll(" " + Table.name + " ", " QRY_DYN_" + name.toUpperCase() + " ")
    —— 只认 Table.name（英文 slug），且要求 SQL 中表名前后有空格。

缺陷：
  1. xformat 全被写成 'jpql'，但内容是纯 SQL -> jsqlparser 解不出 Select -> ExceptionDmlNotAllowed
  2. SQL 里用中文别名（如 `项目主表`）-> joinSql/物理层都认不出 -> Table 'X.项目主表' doesn't exist
  3. 业务字段没用 x 前缀 -> Unknown column 'p.project_no'

本脚本把每条语句的 xsql 规范化为 **物理表名 QRY_DYN_<NAME大写> + x 前缀列**，
并同时修正 xformat='sql'、xcountMethod='ignore'。这是 format=sql 路径下唯一可靠的写法。

用法：
  python fix_statement_sql.py --dry      # 只打印重写结果，不落库
  python fix_statement_sql.py            # 落库
  python fix_statement_sql.py --exec     # 落库后逐条实测执行
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:9090"
sys.path.insert(0, BUILD)

# ---------- 数据库访问 ----------


def mysql(sql, timeout=180):
    cmd = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
           "-uo2oa", "-po2oa_pwd", "X", "-N", "-B", "-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return [l for l in (r.stdout or "").splitlines() if "Warning" not in l]


def qrow(sql):
    out = mysql(sql)
    return [l.split("\t") for l in out if l.strip()]


# ---------- 映射加载 ----------


def load_maps():
    """返回 (alias2phys, slug2phys, phys2cols)

    alias2phys: 中文别名 -> QRY_DYN_XXX
    slug2phys : 英文 slug -> QRY_DYN_XXX
    phys2cols : QRY_DYN_XXX -> set(实际列名)
    """
    tables = qrow("SELECT xid, xname, xalias FROM QRY_SCH_TABLE "
                  "WHERE xid REGEXP '^t[0-9]' ORDER BY LENGTH(xname) DESC;")
    alias2phys, slug2phys = {}, {}
    # ---- 第一遍：只登记「完整名」（去 t<n>_ 前缀、去 _table 后缀）----
    # 这一步保证 contract_receive_plan 与 contract_receive 各自占住自己的全名，
    # 不会被对方派生出的短名抢先覆盖。
    shorts = []
    for row in tables:
        if len(row) < 3:
            continue
        slug, alias = row[1], row[2]
        phys = "QRY_DYN_" + slug.upper()
        slug2phys[slug.lower()] = phys
        parts = re.sub(r"^t\d+_", "", slug).split("_")
        if parts and parts[-1] == "table":
            parts = parts[:-1]
        full = "_".join(parts)
        slug2phys[full.lower()] = phys
        shorts.append((parts, phys))
        if alias:
            alias2phys[alias] = phys

    # ---- 第二遍：派生短别名（仅在唯一归属时才登记）----
    # 若某短名会被多张表争用（如 contract / project / receive），则直接弃用，
    # 宁可「查不到」也不要「静默指向错表」。
    claim = {}
    cand_map = {}
    for parts, phys in shorts:
        cands = set()
        for i in range(1, len(parts)):            # 去前缀：receive_plan
            cands.add("_".join(parts[i:]))
        for i in range(len(parts) - 1, 0, -1):    # 去后缀：contract_receive
            cands.add("_".join(parts[:i]))
        cands.add(parts[-1])                      # 末段：receive / self
        for c in cands:
            c = c.lower()
            if len(c) < 3:
                continue
            cand_map.setdefault(c, []).append(phys)
            claim.setdefault(c, set()).add(phys)

    for c, physs in claim.items():
        if c in slug2phys:
            continue                              # 已是某表全名，保留
        if len(physs) == 1:
            slug2phys[c] = list(physs)[0]

    cols = {}
    raw = mysql("SELECT TABLE_NAME, GROUP_CONCAT(COLUMN_NAME) "
                "FROM information_schema.columns WHERE table_schema='X' "
                "AND TABLE_NAME LIKE 'QRY_DYN_%' GROUP BY TABLE_NAME;")
    for line in raw:
        p = line.split("\t")
        if len(p) == 2:
            cols[p[0]] = set(p[1].split(","))
    ALLCOLS.clear()
    ALLCOLS.update(cols)
    TBLCOLS.clear()
    TBLCOLS.update(cols)
    return alias2phys, slug2phys, cols


# ---------- SQL 重写 ----------

# 物理表 -> 列集合（load_maps 时填充，供 qualify_order_by / 子查询修正使用）
ALLCOLS = {}
TBLCOLS = {}

KEYWORDS = {"select", "from", "where", "and", "or", "on", "as", "left", "right",
            "inner", "outer", "join", "group", "by", "order", "limit", "count",
            "sum", "max", "min", "avg", "distinct", "ifnull", "round", "case",
            "when", "then", "else", "end", "desc", "asc", "having", "union",
            "all", "not", "null", "is", "in", "like", "between", "current_date"}


def rewrite_sql(sql, alias2phys, slug2phys, phys2cols):
    """把 SQL 规范化成：物理表名 + x 前缀列。

    策略：
      1) 先把 SQL 中出现的表标识符（中文别名 / 英文 slug）替换成物理表名，
         并记录 alias -> 物理表（用于确定列前缀归属）。
         —— 子查询 FROM (SELECT ...) 无表名，其内部裸列需靠 2b 步推导。
      2) 再对 <alias>.<col> 形式的引用补 x 前缀（若该列在任意物理表中存在）。
      2b) 子查询输出别名推导：从 (SELECT a AS b, x AS y ...) 建立 b->a 映射，
          再把外层 <alias>.b 改写成 <alias>.<真列名>。
      3) 裸列名（无别名限定）也尝试补 x 前缀。
      4) 裸列名 + AS 别名：新增 <裸列> AS <别名> 形态（子查询里常见）。
      5) MySQL ONLY_FULL_GROUP_BY：把 SELECT 中未聚合的裸列补进 GROUP BY。
      6) ORDER BY 歧义：多表 JOIN 且列名重复时，补上其归属别名。
    """
    # --- 1. 表名替换 ---
    # 匹配 "FROM xxx" / "JOIN xxx"
    tpat = re.compile(r"\b(from|join)\s+([^\s,()]+)", re.IGNORECASE)

    alias2phys_local = {}   # SQL 内使用的表别名/表名 -> 物理表

    def repl_table(m):
        kw, name = m.group(1), m.group(2)
        # 已是物理表名
        if name.upper().startswith("QRY_DYN_"):
            alias2phys_local[name.lower()] = name.upper()
            return kw + " " + name
        phys = alias2phys.get(name) or slug2phys.get(name.lower())
        if phys:
            alias2phys_local[name.lower()] = phys
            return kw + " " + phys
        return m.group(0)   # 子查询括号等，原样保留

    sql2 = tpat.sub(repl_table, sql)
    # 表名后的别名（FROM QRY_DYN_X p / FROM QRY_DYN_X AS p）
    apat = re.compile(r"(QRY_DYN_[A-Za-z0-9_]+)\s+(?:as\s+)?([a-z][a-z0-9_]*)\b",
                      re.IGNORECASE)
    for m in apat.finditer(sql2):
        phys, al = m.group(1).upper(), m.group(2).lower()
        if al in ("where", "group", "order", "left", "right", "inner", "on",
                  "and", "or", "limit", "having"):
            continue
        alias2phys_local[al] = phys

    # --- 1b. 兜底：FROM `中文别名` 未命中时的报错前置（保留原样，便于排查）---
    def repl_unknown(m):
        kw, name = m.group(1), m.group(2)
        if name.startswith("(") or name.upper().startswith("QRY_DYN_"):
            return m.group(0)
        if alias2phys.get(name) or slug2phys.get(name.lower()):
            return m.group(0)
        if re.match(r"^[a-z]", name):
            return m.group(0)
        print("  [WARN] 无法映射的表标识符：%s（语句将执行失败）" % name)
        return m.group(0)

    sql2 = tpat.sub(repl_unknown, sql2)

    # --- 2b. 子查询输出别名推导 ----------
    # 形如 (SELECT xleave_no AS biz_no, xleave_days AS leave_days FROM ...) l
    # 外层 l.biz_no 实际列名是 biz_no（子查询输出列），不是 xbiz_no。
    #
    # 用括号配对定位所有 (SELECT ...)，再取紧随其后的标识符作为子查询别名。
    sub_out = {}      # (别名, 输出列) -> 子查询内真实列名
    SUBSTATIC = set()
    for body, al in iter_subqueries(sql2):
        alias2phys_local[al] = "SUBQUERY:" + al      # 占位，repl_qual 会先查 sub_out
        SUBSTATIC.add(al)
        m2 = re.match(r"\s*(.*?)\s+from\b", body, re.IGNORECASE | re.DOTALL)
        if not m2:
            continue
        for item in split_top_level(m2.group(1)):
            item = item.strip()
            # 形态 A：<ident> AS <alias> 或 <expr>(col) AS <alias>
            ma = re.match(
                r"^(?:\w+\.)?([A-Za-z_][A-Za-z0-9_]*)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$",
                item, re.IGNORECASE)
            if ma:
                sub_out[(al, ma.group(2).lower())] = ma.group(1)
                continue
            # 形态 B：任意表达式 AS 别名 —— 子查询输出列就是别名本身，
            # 外层引用 <子查询别名>.<别名> 时不需要再加 x 前缀。
            mb = re.match(r"^.*\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$", item, re.IGNORECASE)
            if mb:
                sub_out[(al, mb.group(1).lower())] = mb.group(1)
                continue
            # 形态 C：裸列（无 AS）
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", item):
                sub_out[(al, item.lower())] = item

    # --- 2. 保护 AS 别名：先占位，避免被后续规则污染 ---
    # 同时记录所有输出别名（在占位之前采集，否则 AS xxx 已被替换掉）。
    out_aliases = set(m.group(1).lower() for m in
                      re.finditer(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)", sql2,
                                  re.IGNORECASE))
    holders = {}

    def hold_as(m):
        key = "__AS%d__" % len(holders)
        holders[key] = m.group(0)
        return key

    sql2 = re.sub(r"\bas\s+[a-zA-Z_][a-zA-Z0-9_]*", hold_as, sql2, flags=re.IGNORECASE)

    # --- 3. 限定列补 x 前缀： alias.col ---
    allcols = set()
    for s in phys2cols.values():
        allcols |= s

    def repl_qual(m):
        al, col = m.group(1), m.group(2)
        # 子查询输出列：外层引用一律保持「输出别名」原样。
        # 子查询内部已由 _fix_one_subquery 补成 `x真列 AS 输出别名`，
        # 所以外层只需按输出别名引用即可，既不能加 x 前缀，也不能换回真列名。
        if (al.lower(), col.lower()) in sub_out:
            return m.group(0)
        if col.lower() == "id":
            return al + ".xid"        # O2OA 主键列就是 xid
        if col.startswith("x"):
            return m.group(0)
        if al.lower() in SUBSTATIC:       # 子查询别名但未收录该列 -> 不加前缀
            return m.group(0)
        phys = alias2phys_local.get(al.lower())
        cand = "x" + col
        if phys and cand in phys2cols.get(phys, set()):
            return al + "." + cand
        if cand in allcols:
            return al + "." + cand
        return m.group(0)

    sql2 = re.sub(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b", repl_qual, sql2,
                  flags=re.IGNORECASE)

    # --- 3b. 子查询内部：裸列补 x 前缀 + 裸输出列显式别名化 ---
    # 子查询 `SELECT contract_no, COUNT(*) AS n FROM QRY_DYN_X ...` 里的裸列
    # contract_no 需要补成 xcontract_no，并显式 `AS contract_no`，
    # 否则外层 ON iv.contract_no 解析不到该输出列。
    sql2 = alias_subquery_bare_columns(sql2, allcols | set())

    # --- 4. 裸列补齐（排除表别名与输出别名） ---
    alias_names = set(alias2phys_local.keys())

    def naked_pass(text):
        parts = re.split(r"(\bselect\b|\bgroup\s+by\b|\border\s+by\b)", text,
                         flags=re.IGNORECASE)
        out = []
        for i, seg in enumerate(parts):
            if re.match(r"^\s*(select|group\s+by|order\s+by)\s*$", seg, re.IGNORECASE):
                out.append(seg)
                continue
            prev = parts[i - 1].strip().lower() if i > 0 else ""
            if prev.startswith("select") or prev.startswith("group") or prev.startswith("order"):
                def repl_naked(m):
                    w = m.group(1)
                    if w.lower() in KEYWORDS or w.startswith("x"):
                        return w
                    if w.lower() in alias_names:      # 表别名，跳过
                        return w
                    if w.lower() in out_aliases:      # 输出别名，跳过
                        return w
                    if ("x" + w) in allcols:
                        return "x" + w
                    return w
                # 4a) 裸列 AS 别名：`amount AS applied` -> `xamount AS applied`
                seg = re.sub(r"(?<![\w.])\b([a-z][a-z0-9_]*)\b(?=\s+__AS\d+__)",
                             repl_naked, seg, flags=re.IGNORECASE)
                # 4b) 其余裸列（排除后面紧跟 . 的限定符与后面紧跟 ( 的函数名）
                seg = re.sub(r"(?<![\w.])\b([a-z][a-z0-9_]*)\b(?![.\w])(?!\s*\()",
                             repl_naked, seg, flags=re.IGNORECASE)
            out.append(seg)
        return "".join(out)

    sql2 = naked_pass(sql2)

    # --- 5. 还原 AS 别名 ---
    for k, v in holders.items():
        sql2 = sql2.replace(k, v)

    # --- 6. MySQL ONLY_FULL_GROUP_BY：补齐 GROUP BY ---
    sql2 = complete_group_by(sql2)

    # --- 7. ORDER BY 歧义消解 ---
    sql2 = qualify_order_by(sql2, alias2phys_local)
    # 单表却写了别名限定（rp.xplan_amount）—— 该别名不属于本层，说明子查询列名残留，
    # 这里不再兜底，交由 2b 步处理。仅做提醒。
    warn_orphan_alias(sql2, alias2phys_local)

    # --- 8. 规范化空白与逗号，保证输出字节稳定（幂等） ---
    sql2 = re.sub(r"\s+", " ", sql2)
    sql2 = re.sub(r"\s+,", ",", sql2)
    sql2 = re.sub(r",\s*", ", ", sql2)
    sql2 = re.sub(r"\(\s+", "(", sql2)
    sql2 = re.sub(r"\s+\)", ")", sql2)
    return sql2.strip()


def split_top_level(text, sep=","):
    """按顶层分隔符切分（忽略括号内）。"""
    out, depth, buf = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def iter_subqueries(sql):
    """产出 (子查询体, 子查询别名)。

    用括号配对定位所有 `( SELECT ... )`，再取紧随其后的标识符作别名。
    顺序扫描（非 re.finditer 非贪婪）以免连续子查询时丢失别名。
    """
    res = []
    i = 0
    low = sql.lower()
    while True:
        j = low.find("( select", i)
        if j < 0:
            j = low.find("(select", i)
        if j < 0:
            break
        depth, k = 0, j
        while k < len(sql):
            if sql[k] == "(":
                depth += 1
            elif sql[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = sql[j + 1:k]
        # 去掉子查询体开头的 SELECT，保证后续正则拿到的是「输出列表」
        body = re.sub(r"^\s*select\b", "", body, count=1, flags=re.IGNORECASE)
        rest = sql[k + 1:]
        m = re.match(r"\s*(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*)", rest, re.IGNORECASE)
        al = m.group(1).lower() if m else ""
        if al and al not in ("where", "group", "order", "left", "right", "inner",
                             "on", "and", "or", "limit", "having", "join", "union"):
            res.append((body, al))
        i = k + 1
    return res


AGG = re.compile(r"\b(sum|count|max|min|avg|group_concat|ifnull|round|coalesce)\s*\(",
                 re.IGNORECASE)


CLAUSE_KW = ["select", "from", "where", "group by", "having", "order by", "limit"]


def _split_clauses(sql):
    """把最外层 SQL 按子句关键词切成 [(keyword, text), ...]。

    只识别「深度 0」且前后为边界的关键词。第一个元素 keyword='' 表示
    SELECT 之前的空白，其后 keyword='select' 对应 SELECT 列表内容。
    """
    marked = mark_depth(sql)          # 与 sql 等长，深度数组
    low = sql.lower()
    cuts = []
    i = 0
    while i < len(sql):
        if marked[i] == 0:
            hit = None
            for kw in CLAUSE_KW:
                if low.startswith(kw, i):
                    before = low[i - 1] if i > 0 else " "
                    after = low[i + len(kw)] if i + len(kw) < len(low) else " "
                    if not (before.isalnum() or before == "_") and \
                       not (after.isalnum() or after == "_"):
                        hit = kw
                        break
            if hit:
                cuts.append((i, hit))
                i += len(hit)
                continue
        i += 1

    cl = []
    prev_kw, prev_pos = "", 0
    if cuts and cuts[0][0] > 0:
        cl.append(("", sql[:cuts[0][0]]))
    for n, (pos, kw) in enumerate(cuts):
        end = cuts[n + 1][0] if n + 1 < len(cuts) else len(sql)
        cl.append((kw, sql[pos + len(kw):end]))
    return cl


def mark_depth(sql):
    """返回每个字符所在括号深度（'(' 本身记为外层的深度）。"""
    dep, out = 0, []
    for ch in sql:
        if ch == ")":
            dep -= 1
        out.append(dep)
        if ch == "(":
            dep += 1
    return out


def complete_group_by(sql):
    """把 SELECT 中「未包在聚合函数里」的顶层列补进 GROUP BY。

    只在最外层做（深度 0），避免误改子查询的 GROUP BY。
    幂等：已在 GROUP BY 中的列不会重复追加。
    """
    cl = _split_clauses(sql)
    kwmap = {}
    for k, v in cl:
        kwmap.setdefault(k, []).append(v)
    if not kwmap.get("group by"):
        return sql

    sel = "".join(kwmap.get("select", []))
    if not AGG.search(sel):
        return sql

    need = []
    for item in split_top_level(sel):
        it = item.strip()
        if not it or AGG.search(it):
            continue
        it = re.sub(r"\s+as\s+\w+\s*$", "", it, flags=re.IGNORECASE).strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", it):
            need.append(it)
    if not need:
        return sql

    gb = kwmap["group by"][0]
    existing = [x.strip().lower() for x in split_top_level(gb) if x.strip()]
    add = [c for c in need if c.strip().lower() not in existing]
    if not add:
        return sql

    # 就地替换最外层第一个 GROUP BY 子句
    pos = _find_kw(sql, "group by")
    if pos < 0:
        return sql
    bs = pos + len("group by")
    out = sql[:bs] + " " + gb.strip().rstrip(",") + ", " + ", ".join(add) + " " \
        + sql[bs + len(gb):]
    return re.sub(r"\s+", " ", out).replace(" ,", ",").strip()


def _find_kw(sql, kw):
    """返回最外层（深度 0）关键词 kw 的起始位置，找不到返回 -1。"""
    marked = mark_depth(sql)
    low = sql.lower()
    i = 0
    while i < len(low):
        if marked[i] == 0 and low.startswith(kw, i):
            before = low[i - 1] if i > 0 else " "
            after = low[i + len(kw)] if i + len(kw) < len(low) else " "
            if not (before.isalnum() or before == "_") and \
               not (after.isalnum() or after == "_"):
                return i
        i += 1
    return -1


def qualify_order_by(sql, alias2phys_local):
    """ORDER BY 出现裸列且 JOIN 多表共享同名 -> 补上归属别名。

    幂等：已带别名限定的项不再处理。
    """
    real = {a: p for a, p in alias2phys_local.items()
            if not str(p).startswith("SUBQUERY:")}
    sub = {a for a, p in alias2phys_local.items() if str(p).startswith("SUBQUERY:")}
    if len(real) + len(sub) < 2:
        return sql
    cl = _split_clauses(sql)
    ob = [v for k, v in cl if k == "order by"]
    if not ob:
        return sql
    ob = ob[0]
    items = split_top_level(ob)

    def fix(it):
        it = it.strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(\s+(?:asc|desc))?$", it, re.IGNORECASE)
        if not m:
            return it
        col = m.group(1)
        if col.lower() in real or col.lower() in sub:
            return it                            # 是表别名/子查询别名，跳过
        if col.lower() in ORDERBY_SAFE:
            return it
        owners = sorted(a for a, ph in real.items() if col in ALLCOLS.get(ph, set()))
        if len(owners) == 1:
            return owners[0] + "." + col + (m.group(2) or "")
        return it

    new = ", ".join(fix(x) for x in items)
    if new == ob.strip():
        return sql
    pos = _find_kw(sql, "order by")
    if pos < 0:
        return sql
    bs = pos + len("order by")
    out = sql[:bs] + " " + new + " " + sql[bs + len(ob):]
    return re.sub(r"\s+", " ", out).replace(" ,", ",").strip()


# ORDER BY 中允许保留裸列的聚合输出别名（SQL 层面合法且无歧义）
ORDERBY_SAFE = set()


def alias_subquery_bare_columns(sql, allcols):
    """子查询内部的裸列补 x 前缀，并把裸输出列别名化。

    处理 `(SELECT contract_no, COUNT(*) AS n FROM QRY_DYN_X ...) iv`：
      1) 子查询体内部（SELECT 列表 + GROUP BY）的裸列 contract_no
         -> xcontract_no（依据子查询自身 FROM 的物理表）
      2) 再把裸输出列补成 `xcontract_no AS contract_no`，
         使外层 `iv.contract_no` 仍能解析。

    只处理「裸的 x 前缀列」，已有 AS 的项不动。
    """
    out, i = [], 0
    while i < len(sql):
        if sql[i] == "(" and re.match(r"\(\s*select\b", sql[i:], re.IGNORECASE):
            depth, k = 0, i
            while k < len(sql):
                if sql[k] == "(":
                    depth += 1
                elif sql[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            body = sql[i + 1:k]
            body = _fix_one_subquery(body, allcols)
            out.append("(" + body + ")")
            i = k + 1
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def _fix_one_subquery(body, allcols):
    """修正单层子查询体：裸列补 x 前缀 + 裸输出列显式别名化。幂等。"""
    m = re.match(r"^(\s*select\s+)(.*?)(\s+from\b)(.*)$", body,
                 re.IGNORECASE | re.DOTALL)
    if not m:
        return body
    head, sel, mid, tail = m.groups()

    # 该子查询 FROM 的物理表 -> 允许的列集合
    tm = re.search(r"\bfrom\s+(QRY_DYN_[A-Za-z0-9_]+)", tail, re.IGNORECASE)
    tcols = set()
    if tm:
        tcols = TBLCOLS.get(tm.group(1).upper(), set())

    items = split_top_level(sel)
    new = []
    for it in items:
        st = it.strip()

        def fix_col(col):
            """给单个业务列标识符补 x 前缀（带存在性校验）。"""
            if not col or col.startswith("x") or col.lower() in KEYWORDS:
                return col
            cand = "x" + col
            pool = tcols if tcols else allcols
            return cand if cand in pool else col

        # 形态 1：`<源> AS <别名>` —— 补源侧（含聚合参数内的列）
        ma = re.match(r"^(.*?)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", st,
                      re.IGNORECASE | re.DOTALL)
        if ma:
            src, ali = ma.group(1).strip(), ma.group(2)
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", src):
                src = fix_col(src)
            else:
                # 表达式：先补括号内的列，再补运算式里的列
                src = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\b(?=\s*\))",
                             lambda m: fix_col(m.group(1)), src)
                src = re.sub(r"(?<![\w.])\b([A-Za-z_][A-Za-z0-9_]*)\b(?![\w.(])",
                             lambda m: fix_col(m.group(1)), src)
            new.append(" %s AS %s " % (src, ali))
            continue

        # 形态 2：裸列 -> `x列 AS 原列名`
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", st):
            if st.lower() == "id":
                new.append(" xid AS id ")
            else:
                fixed = fix_col(st)
                if fixed != st:
                    new.append(" %s AS %s " % (fixed, st))
                else:
                    new.append(it)
            continue

        # 形态 3：纯表达式（聚合等），补括号/运算符内的列
        st2 = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\b(?=\s*\))",
                     lambda m: fix_col(m.group(1)), st)
        st2 = re.sub(r"(?<![\w.])\b([A-Za-z_][A-Za-z0-9_]*)\b(?![\w.(])",
                     lambda m: fix_col(m.group(1)), st2)
        new.append(st2)
    body2 = head + ",".join(new) + mid + tail

    # 子查询内的 GROUP BY 裸列也要补 x
    gb = re.search(r"\bgroup\s+by\s+([^)]*)$", body2, re.IGNORECASE | re.DOTALL)
    if gb:
        cols = split_top_level(gb.group(1))
        cols2 = []
        for c in cols:
            cs = c.strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cs) and not cs.startswith("x"):
                if ("x" + cs) in (tcols or allcols):
                    cs = "x" + cs
            cols2.append(cs)
        body2 = body2[:gb.start(1)] + ", ".join(cols2) + body2[gb.end(1):]
    return body2


def warn_orphan_alias(sql, alias2phys_local):
    """语句内出现的 <alias>.<col>，若 alias 不在本层表别名集合中 -> 提示。

    注意：单字母别名（p/c/e/s 等）在多层子查询里极易误报，
    这里只提示长度 >= 2 的游离别名，避免噪声淹没真实问题。
    """
    used = set(m.group(1).lower() for m in
               re.finditer(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b", sql))
    orphan = {x for x in used - set(alias2phys_local.keys()) if len(x) >= 2}
    orphan -= {"information_schema"}
    if orphan:
        print("  [WARN] 疑似游离别名（可能子查询列名残留）：%s"
              % ", ".join(sorted(orphan)))


# ---------- 主流程 ----------


def statement_sources():
    """从打包产物读回「权威源 SQL」（未改写版本）。

    为什么要走这条线：pack.py 打包时已用统一重写器处理过一次，
    但数据库里的 xsql 可能被历史版本重写器污染过（双重改写）。
    以 deliverables/_xapp_json 中的 xapp 原始内容为准，可以保证
    「源 -> 重写」只发生一次，重写器本身幂等。

    返回 {statement_id: (name, sql)}
    """
    import glob
    out = {}
    pat = os.path.join(os.path.dirname(BUILD), "deliverables", "_xapp_json", "*.json")
    for fp in sorted(glob.glob(pat)):
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        mods = data if isinstance(data, list) else [data]
        for m in mods:
            for app in _iter_query_apps(m):
                for st in app.get("statementList", []) or []:
                    sid = st.get("id")
                    sql = st.get("sql") or st.get("statement") or ""
                    if sid and sql:
                        out[sid] = (st.get("name", sid), sql)
    return out


def _iter_query_apps(obj):
    """递归找出含 statementList 的查询应用节点。"""
    if isinstance(obj, dict):
        if obj.get("statementList"):
            yield obj
        for v in obj.values():
            for x in _iter_query_apps(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _iter_query_apps(v):
                yield x


def main():
    dry = "--dry" in sys.argv
    do_exec = "--exec" in sys.argv

    alias2phys, slug2phys, phys2cols = load_maps()
    print("表映射：中文别名 %d，英文 slug %d，物理表 %d"
          % (len(alias2phys), len(slug2phys), len(phys2cols)))

    # 优先用打包产物中的源 SQL（保证只重写一次）；缺失则退回库中当前值
    src = statement_sources()
    rows = qrow("SELECT xid, xname FROM QRY_SCH_STATEMENT "
                "WHERE xquery LIKE 'a%' ORDER BY xid;")
    stmts = []
    from_src = 0
    for r in rows:
        if len(r) < 2:
            continue
        sid, name = r[0], r[1]
        if sid in src:
            name, sql = src[sid]
            from_src += 1
        else:
            got = qrow("SELECT xsql FROM QRY_SCH_STATEMENT WHERE xid='%s';" % sid)
            sql = got[0][0] if got else ""
        stmts.append((sid, name, sql))
    print("待处理语句 %d 条（其中 %d 条取自打包产物源 SQL）\n"
          % (len(stmts), from_src))

    changed = []
    for sid, name, sql in stmts:
        new = rewrite_sql(sql, alias2phys, slug2phys, phys2cols)
        if new and new != sql:
            changed.append((sid, name, sql, new))

    print("需要重写 %d 条" % len(changed))
    for sid, name, old, new in changed[:3]:
        print("\n== %s ==" % name)
        print("  OLD:", old[:170])
        print("  NEW:", new[:170])

    if dry:
        print("\n[dry-run] 未落库")
        return

    n_ok = 0
    for sid, name, old, new in changed:
        esc = new.replace("\\", "\\\\").replace("'", "\\'")
        mysql("UPDATE QRY_SCH_STATEMENT SET xformat='sql', "
              "xcountMethod='ignore', xsql='%s' WHERE xid='%s';" % (esc, sid))
        n_ok += 1
    mysql("UPDATE QRY_SCH_STATEMENT SET xformat='sql', xcountMethod='ignore' "
          "WHERE xquery LIKE 'a%' AND (xformat<>'sql' OR xcountMethod<>'ignore');")
    print("\n已重写 %d 条，并统一 format=sql / countMethod=ignore" % n_ok)

    chk = qrow("SELECT COUNT(*) , SUM(xformat='sql'), SUM(xcountMethod='ignore') "
               "FROM QRY_SCH_STATEMENT WHERE xquery LIKE 'a%';")
    print("校验：总数/format=sql/countMethod=ignore =", chk[0])

    if do_exec:
        run_all([(s[0], s[1]) for s in stmts])


def run_all(stmts):
    from import_xapps import get_token
    token = get_token()
    print("\n==== 逐条实测执行 (token %d) ====" % len(token))
    ok = bad = 0
    fails = []
    for row in stmts:
        sid, name = row[0], row[1]
        url = ("%s/x_query_assemble_designer/jaxrs/statement/%s/execute/page/1/size/5"
               % (BASE, sid))
        req = urllib.request.Request(url, data=b"{}",
                                     headers={"x-token": token,
                                              "Content-Type": "application/json"},
                                     method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=180)
            body = r.read().decode("utf-8", "ignore")
            size = ""
            m = re.search(r'"size"\s*:\s*(-?\d+)', body)
            if m:
                size = m.group(1)
            print("  OK  %-28s rows=%s" % (name[:28], size))
            ok += 1
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            mm = re.search(r'"message":\s*"([^"]{0,150})', msg)
            print("  ERR %-28s %s" % (name[:28], mm.group(1) if mm else e.code))
            bad += 1
        except Exception as e:
            print("  EXC %-28s %s" % (name[:28], e))
            bad += 1
    print("\n执行结果：成功 %d，失败 %d" % (ok, bad))


if __name__ == "__main__":
    main()
