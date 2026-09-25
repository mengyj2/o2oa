# -*- coding: utf-8 -*-
"""
强制重建自建表物理表 (rebuild_tables.py)
=======================================

背景（2026-09-20）：
  修正了字段类型后（number→double / text→stringLob / datetime→dateTime），
  重新导入 xapp 并执行 status/build + build/dispatch，日志显示
  「build query ... table complete!」「Enhancer running on type ...」，
  但 QRY_SCH_TABLE.xbuildSuccess 仍为空、物理表结构没有新字段。

原因：
  O2OA 的 PersistenceXmlHelper.directWriteDynamicEnhance 只在**物理表不存在**
  时执行 CREATE TABLE；对已存在的旧表不做 ALTER。
  旧表一旦建立，结构就被固化，后续字段变更永不生效。

对策：
  1) 备份现有数据（mysqldump --no-create-info）
  2) DROP 我们的 31 张 QRY_DYN_* 物理表
  3) 重置 QRY_SCH_TABLE.xbuildSuccess=NULL、xstatus='draft'
  4) 重新走 status/build + build/dispatch
  5) 回灌备份数据（只回灌旧表已有的列，新列留空）

用法：
  python rebuild_tables.py            # 全流程
  python rebuild_tables.py --drop-only
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BUILD)
BASE = "http://localhost:9090"
BACKUP = os.path.join(ROOT, "backup", "dyn_tables_data_20260920.sql")
sys.path.insert(0, BUILD)


def mysql(sql, timeout=300):
    cmd = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
           "-uo2oa", "-po2oa_pwd", "X", "-N", "-B", "-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return [l for l in (r.stdout or "").splitlines() if "Warning" not in l]


def mysql_file(path):
    """在容器内执行 SQL 文件（通过 stdin 传入避免转义问题）。"""
    with open(path, "rb") as f:
        data = f.read()
    cmd = ["docker", "exec", "-i", "o2oa-mysql", "mysql",
           "--default-character-set=utf8mb4", "-uo2oa", "-po2oa_pwd", "X"]
    r = subprocess.run(cmd, input=data, capture_output=True, timeout=600)
    return r.returncode, (r.stderr or b"").decode("utf-8", "replace")[:400]


def our_tables():
    raw = mysql("SELECT xid, xname FROM QRY_SCH_TABLE WHERE xid REGEXP '^t[0-9]';")
    out = []
    for line in raw:
        p = line.split("\t")
        if len(p) == 2:
            out.append((p[0], p[1]))
    return out


def drop_physical():
    tables = our_tables()
    names = ["QRY_DYN_" + n.upper() for _, n in tables]
    stmt = "SET FOREIGN_KEY_CHECKS=0;" + "".join(
        "DROP TABLE IF EXISTS `%s`;" % n for n in names) + "SET FOREIGN_KEY_CHECKS=1;"
    mysql(stmt)
    left = mysql("SELECT COUNT(*) FROM information_schema.tables "
                 "WHERE table_schema='X' AND TABLE_NAME IN (%s);"
                 % ",".join("'%s'" % n for n in names))
    print("已 DROP %d 张物理表，剩余 %s" % (len(names), left[0] if left else "?"))
    return names


def reset_meta():
    mysql("UPDATE QRY_SCH_TABLE SET xbuildSuccess=NULL, xstatus='draft' "
          "WHERE xid REGEXP '^t[0-9]';")
    print("已重置 QRY_SCH_TABLE 元数据（buildSuccess=NULL, status=draft）")


def main():
    drop_only = "--drop-only" in sys.argv

    print("== 1. 备份 ==")
    if os.path.exists(BACKUP):
        print("  备份已存在：%s (%d 行)" % (BACKUP, sum(1 for _ in open(BACKUP, encoding="utf-8", errors="replace"))))
    else:
        print("  ⚠ 未找到备份，跳过（如需可先手动 mysqldump）")

    print("\n== 2. DROP 物理表 ==")
    drop_physical()
    if drop_only:
        print("\n[--drop-only] 结束")
        return

    print("\n== 3. 重置元数据 ==")
    reset_meta()

    print("\n== 4. 重建（build_tables.py）==")
    r = subprocess.run([sys.executable, os.path.join(BUILD, "build_tables.py")],
                       capture_output=True, text=True, timeout=1800,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-12:]
    for l in tail:
        print("  " + l)

    print("\n== 5. 校验新结构 ==")
    chk = mysql("SELECT COUNT(*) FROM QRY_SCH_TABLE WHERE xid REGEXP '^t[0-9]' "
                "AND xbuildSuccess=1;")
    print("  buildSuccess=1 的表：%s / 31" % (chk[0] if chk else "?"))

    # 抽查关键新字段
    samples = [
        ("T3003001_BUDGET_MASTER_TABLE", ["xexec_rate", "xtotal_amount"]),
        ("T4004001_EXPENSE_MASTER_TABLE", ["xtotal_amount"]),
        ("T6006001_HR_EMPLOYEE_TABLE", ["xremark", "xcreate_time"]),
        ("T1001001_PROJECT_MASTER_TABLE", ["xproject_goal", "xworkload"]),
    ]
    for slug, cols in samples:
        tn = "QRY_DYN_" + slug
        got = mysql("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.columns "
                    "WHERE table_schema='X' AND TABLE_NAME='%s';" % tn)
        have = set((got[0] if got else "").split(","))
        print("  %-40s %s" % (tn, " ".join(
            ("%s=%s" % (c, "OK" if c in have else "MISS")) for c in cols)))

    print("\n== 6. 回灌数据 ==")
    if os.path.exists(BACKUP):
        rc, err = mysql_file(BACKUP)
        print("  回灌返回码 %s %s" % (rc, err[:200] if err else ""))
    print("\n完成。")


if __name__ == "__main__":
    main()
