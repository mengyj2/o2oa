# -*- coding: utf-8 -*-
"""
O2OA 自建表（QRY_SCH_TABLE）批量构建器
=====================================

背景（已实测确认）：
  导入 .xapp 后，31 张自建表落在 QRY_SCH_TABLE，xstatus='draft'（项目主表已手动建过=build）。
  物理表 QRY_DYN_<NAME> 的 DDL **不是在** {table}/execute 触发
  （ActionExecute 实为 JPQL 执行器，body 需 {type,data}，与建表无关），
  而是在 status/build -> build/dispatch 这条链里由 Business.buildQuery 完成的。

构建三步（对应 query designer 的三个 action）：
  1) GET  {qry}/jaxrs/table/{tid}/status/build       -> 置 xstatus='build'
  2) GET  {qry}/jaxrs/table/{qid}/build/dispatch     -> 编译 DynamicEntity + 落 dynamic_<qid>.jar
                                                         + PersistenceXmlHelper 增强 -> 建 QRY_DYN_* 物理表
  3) （可选）GET {qry}/jaxrs/table/{tid}             -> 回读确认 xstatus

注意：一张表 build 后必须 dispatch 它所属 query app；同 app 多表可合并 dispatch 一次，
      但为便于定位失败，默认逐表执行。

用法：
  python build_tables.py            # 构建全部 draft 表
  python build_tables.py --check    # 只查状态，不构建
  python build_tables.py --only t6006  # 只构建 xid 含该子串的表
"""

import json
import os
import sys
import subprocess
import time
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:9090"
MYSQL = "o2oa-mysql"
DB = "X"

sys.path.insert(0, BUILD)
from import_xapps import get_token


def mysql(sql, utf8=True):
    """在 o2oa-mysql 容器内执行 SQL，返回 stdout 文本。"""
    cmd = ["docker", "exec", MYSQL, "mysql"]
    if utf8:
        cmd.append("--default-character-set=utf8mb4")
    cmd += ["-uo2oa", "-po2oa_pwd", DB, "-N", "-B", "-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "").splitlines()
    return [ln for ln in out if "Warning" not in ln]


def list_tables(only=None):
    """返回 [(xid, xname, xstatus, xquery)]。"""
    sql = ("SELECT xid, xname, xstatus, xquery FROM QRY_SCH_TABLE "
           "WHERE xid LIKE 't1%' OR xid LIKE 't2%' OR xid LIKE 't3%' "
           "OR xid LIKE 't4%' OR xid LIKE 't5%' OR xid LIKE 't6%' ORDER BY xid;")
    rows = []
    for ln in mysql(sql):
        parts = ln.split("\t")
        if len(parts) >= 4:
            rows.append(tuple(parts[:4]))
    if only:
        rows = [r for r in rows if only in r[0]]
    return rows


def http_get(url, token, timeout=300):
    req = urllib.request.Request(url, headers={"x-token": token}, method="GET")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return -1, str(e)


def physical_tables():
    """返回已存在的 QRY_DYN 物理表名集合（大写）。"""
    sql = ("SELECT table_name FROM information_schema.tables "
           "WHERE table_schema='%s' AND table_name LIKE 'QRY_DYN_%%';" % DB)
    return set(ln.strip().upper() for ln in mysql(sql) if ln.strip())


def build_one(tid, qid, token):
    """对单表执行 status/build + build/dispatch。返回 (ok, msg)。"""
    b_url = "%s/x_query_assemble_designer/jaxrs/table/%s/status/build" % (BASE, tid)
    s1, _ = http_get(b_url, token)
    if not (200 <= s1 < 300):
        return False, "status/build HTTP %s" % s1

    d_url = "%s/x_query_assemble_designer/jaxrs/table/%s/build/dispatch" % (BASE, qid)
    t0 = time.time()
    s2, body = http_get(d_url, token, timeout=600)
    dt = time.time() - t0
    if not (200 <= s2 < 300):
        return False, "dispatch HTTP %s | %s" % (s2, body[:200].replace("\n", " "))
    return True, "dispatch HTTP %s (%.1fs)" % (s2, dt)


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        only = args[args.index("--only") + 1]

    rows = list_tables(only)
    if not rows:
        print("未找到匹配的自建表")
        return

    print("自建表共 %d 张，状态分布：" % len(rows))
    from collections import Counter
    for k, v in sorted(Counter(r[2] for r in rows).items()):
        print("  %-8s %d" % (k, v))

    if "--check" in args:
        for r in rows:
            print("  %-42s %s" % (r[0], r[2]))
        return

    fail = []
    todo = [r for r in rows if r[2] != "build"]
    if not todo:
        print("\n全部已是 build 状态，无需构建。")
    else:
        print("\n待构建 %d 张，获取 token ..." % len(todo))
        token = get_token()
        print("[token] 长度 %d\n" % len(token))

        ok_cnt, fail = 0, []
        for i, (tid, xname, status, qid) in enumerate(todo, 1):
            ok, msg = build_one(tid, qid, token)
            # 幂等重试一次（dispatch 偶发超时）
            if not ok:
                time.sleep(2)
                ok, msg = build_one(tid, qid, token)
            print("[%2d/%d] %-42s %s" % (i, len(todo), xname[:42], msg))
            if ok:
                ok_cnt += 1
            else:
                fail.append((tid, msg))

    # ---- 回读状态 + 物理表核对 ----
    print("\n==== 状态回读 ====")
    rows2 = list_tables(only)
    from collections import Counter
    for k, v in sorted(Counter(r[2] for r in rows2).items()):
        print("  %-8s %d" % (k, v))

    phys = physical_tables()
    print("\n==== 物理表核对 ====")
    print("QRY_DYN_* 物理表总数：%d" % len(phys))
    missing = []
    for tid, xname, status, qid in rows2:
        pname = ("QRY_DYN_" + xname).upper()
        if pname not in phys:
            missing.append((xname, status))
    if missing:
        print("缺少物理表 %d 张：" % len(missing))
        for n, s in missing:
            print("  %-45s (状态=%s)" % (n, s))
    else:
        print("31 张自建表物理表全部就绪 ✔")
    if fail:
        print("\n构建失败 %d 张：" % len(fail))
        for t, m in fail:
            print("  %s | %s" % (t, m))


if __name__ == "__main__":
    main()
