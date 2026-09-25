# -*- coding: utf-8 -*-
"""_audit_runtime_fields.py —— 审计流程元素「运行时必填字段」缺失。

问题背景
--------
O2OA 设计态元素（PP_E_*）里有一批字段：设计器一定会写、而引擎**直接使用不做兜底**。
我们的 .xapp 构建器只写了「静态校验看得见」的字段，于是这些字段落库为 NULL，
静态校验（表单树/DOM/拓扑/路由 id）全绿，但**发起流程就 NPE**：

    · PP_E_ROUTE.xactivityType   → Processing.arrive() switch(null) → NPE
    · PP_E_MANUAL.xmanualMode    → Manual.toTickets() switch(getManualMode().ordinal()) → NPE

判定方法
--------
以 O2OA **自带元素**（xid 为标准 36 位 UUID）为"标准答案"：
凡「自带元素 100% 非空」而「我们的元素 100% 为空」的列，
即为构建器漏写的高危字段。

用法：python _audit_runtime_fields.py
"""

import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

TABLES = [
    "PP_E_PROCESS", "PP_E_BEGIN", "PP_E_MANUAL", "PP_E_CHOICE",
    "PP_E_END", "PP_E_ROUTE", "PP_E_SPLIT", "PP_E_MERGE", "PP_E_PARALLEL",
]

UUID_RE = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
MYSQL = ["docker", "exec", "o2oa-mysql", "mysql", "-uo2oa", "-po2oa_pwd",
         "--default-character-set=utf8mb4", "-D", "X"]


def q(sql):
    r = subprocess.run(MYSQL + ["-e", sql], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.stdout


def columns(table):
    out = q("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA='X' AND TABLE_NAME='%s' ORDER BY ORDINAL_POSITION;" % table)
    return [l.strip() for l in out.splitlines()
            if l.strip() and l.strip() != "COLUMN_NAME"]


def scan(table):
    cols = columns(table)
    if not cols:
        return None
    # 每列输出 "空数/总数"，按 自带/我们 分组
    exprs = ",".join(
        "CONCAT(SUM(CASE WHEN `%s` IS NULL THEN 1 ELSE 0 END),'/',COUNT(*)) AS `%s`" % (c, c)
        for c in cols
    )
    sql = ("SELECT %s, CASE WHEN xid RLIKE '%s' THEN 'native' ELSE 'ours' END AS grp "
           "FROM %s GROUP BY grp\\G" % (exprs, UUID_RE, table))
    out = q(sql)
    # \G 输出按 "*** 1. row ***" 分块；grp 是最后一个字段，必须整块解析
    data = {}
    for block in re.split(r"\*{10,}\s*\d+\.\s*row\s*\*{10,}", out):
        kv = dict(re.findall(r"^\s*([A-Za-z_0-9]+):\s*(.*?)\s*$", block, re.M))
        g = kv.pop("grp", None)
        if g:
            data[g] = kv
    return cols, data


def main():
    print("=" * 74)
    print("流程元素「运行时必填字段」审计  —— 自带元素 vs 本协会应用")
    print("=" * 74)
    total_risk = 0
    for t in TABLES:
        res = scan(t)
        if not res:
            continue
        cols, data = res
        nat, our = data.get("native", {}), data.get("ours", {})
        if not nat or not our:
            continue
        n_tot = int(list(nat.values())[0].split("/")[1]) if nat else 0
        o_tot = int(list(our.values())[0].split("/")[1]) if our else 0
        risk = []
        for c in cols:
            nv, ov = nat.get(c), our.get(c)
            if not nv or not ov:
                continue
            n_null, _ = nv.split("/")
            o_null, _ = ov.split("/")
            if int(n_null) == 0 and int(o_null) == int(o_tot) and o_tot > 0:
                risk.append(c)
        flag = "!! 高危" if risk else "ok"
        print("\n[%s] %-16s 自带 %3d 条 / 本应用 %3d 条   %s"
              % (flag, t, n_tot, o_tot, ("缺: " + ", ".join(risk)) if risk else "无缺失"))
        total_risk += len(risk)
    print("\n" + "=" * 74)
    print("合计高危字段：%d" % total_risk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
