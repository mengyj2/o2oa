# -*- coding: utf-8 -*-
"""
自建统计语句 / 自建表 —— 权限授予
=================================

背景：
  .xapp 里的 QRY_SCH_STATEMENT 默认**没有任何 executePersonList / executeUnitList**，
  因此调用 `POST statement/{flag}/execute/page/{p}/size/{s}` 会返回：
      HTTP 500  "statement not allowed."  (ExceptionDmlNotAllowed)

  这是权限缺失，不是 SQL 错误 —— 表现为「语句写对了却跑不了」。

本脚本：把全部 31 条自建语句的**执行权限**授予：
  · 人员：秘书长(孟弋洁)、副秘书长(卢宏萍)、综合部李芳（财务/合同/档案专员）
  · 部门：四个部门 + 协会本级
  · 群组：（可留空）

同时把 31 张自建表的**读/编辑权限**授予同一批人（避免视图取不到数）。

接口：
  POST x_query_assemble_designer/jaxrs/statement/{id}/permission
  body: {"executePersonList":[...],"executeUnitList":[...],"executeGroupList":[...]}
  （自建表对应 table/{id}/permission）

用法：
  python grant_permissions.py          # 授予全部
  python grant_permissions.py --check  # 只看现状
"""

import json
import subprocess
import sys
import urllib.request
import urllib.error
import os

BUILD = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:9090"
sys.path.insert(0, BUILD)
from import_xapps import get_token

# 需授权的人员（人员 ID）
PERSONS = [
    "d7169e66-459d-4316-8497-60a6647c2d50",  # 孟弋洁 秘书长
    "500efc6b-2376-4948-bee5-0dc011cd9196",  # 卢宏萍 副秘书长
    "0de7051b-cb98-4154-9921-758ea0d4290f",  # 李芳 综合部专员
    "bb1d46de-b3f5-4a24-9938-c1e348bee045",  # 时晓明
    "664b9867-4f5b-4a36-9cbf-35a31e196180",  # 杜阳
    "edec8377-d6a2-4b00-a8b6-2128db8e42cb",  # 李静
    "fe973b18-443f-4196-9f0f-21e508a16931",  # 奚莎莎
    "ef48caf9-2a82-4181-8b34-1ade8f05dd29",  # 赵旭东
    "ea518e36-1c3b-45ab-b647-1701451b2db4",  # 罗舒涵
]

# 需授权的部门（Unit ID）
UNITS = [
    "9e8b0b36-dff7-4a2c-8964-11b360d7776e",  # 中国复合材料工业协会
    "d3e58ea3-d80a-4a12-922e-d8fee71d0171",  # 综合管理部
    "73fc25cd-7864-43c3-96d3-dd4e321b85d8",  # 行业研究部
    "5d0a3dbb-569a-4005-a950-87cb83651699",  # 会员服务部
    "0484120e-d883-41bc-9c88-3eeb08c33325",  # 国际业务部
]


def mysql(sql):
    cmd = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
           "-uo2oa", "-po2oa_pwd", "X", "-N", "-B", "-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    return [l for l in (r.stdout or "").splitlines() if "Warning" not in l]


def post(url, obj, token):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"x-token": token,
                                          "Content-Type": "application/json"},
                                 method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read().decode("utf-8", "ignore")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")[:250].replace("\n", " ")
    except Exception as e:
        return -1, str(e)


def main():
    check_only = "--check" in sys.argv

    stmts = [l.split("\t") for l in mysql(
        "SELECT xid, xname FROM QRY_SCH_STATEMENT WHERE xquery LIKE 'a%';") if "\t" in l]
    tables = [l.split("\t") for l in mysql(
        "SELECT xid, xname FROM QRY_SCH_TABLE WHERE xid LIKE 't%';") if "\t" in l]

    print("自建语句 %d 条，自建表 %d 张\n" % (len(stmts), len(tables)))

    if check_only:
        for sid, name in stmts[:5]:
            n = mysql("SELECT COUNT(*) FROM QRY_SCH_STATEMENT_executePersonList "
                      "WHERE STATEMENT_XID='%s';" % sid)
            print("  %-40s 执行人 %s" % (name, n[0] if n else "?"))
        return

    token = get_token()
    print("[token] 长度 %d\n" % len(token))

    # ---- 1. 语句执行权限 ----
    body = {
        "executePersonList": PERSONS,
        "executeUnitList": UNITS,
        "executeGroupList": [],
    }
    ok = fail = 0
    for sid, name in stmts:
        url = "%s/x_query_assemble_designer/jaxrs/statement/%s/permission" % (BASE, sid)
        s, b = post(url, body, token)
        if 200 <= s < 300:
            ok += 1
        else:
            fail += 1
            print("  ERR statement %-34s HTTP %s %s" % (name, s, b))
    print("语句执行权限：成功 %d，失败 %d" % (ok, fail))

    # ---- 2. 自建表 读/编辑 权限 ----
    tbody = {
        "readPersonList": PERSONS, "readUnitList": UNITS, "readGroupList": [],
        "editPersonList": PERSONS, "editUnitList": UNITS, "editGroupList": [],
    }
    ok2 = fail2 = 0
    for tid, name in tables:
        url = "%s/x_query_assemble_designer/jaxrs/table/%s/permission" % (BASE, tid)
        s, b = post(url, tbody, token)
        if 200 <= s < 300:
            ok2 += 1
        else:
            fail2 += 1
            print("  ERR table %-34s HTTP %s %s" % (name, s, b))
    print("自建表读写权限：成功 %d，失败 %d" % (ok2, fail2))

    # ---- 3. 校验 ----
    print("\n==== 校验 ====")
    for sid, name in stmts[:5]:
        n = mysql("SELECT COUNT(*) FROM QRY_SCH_STATEMENT_executePersonList "
                  "WHERE STATEMENT_XID='%s';" % sid)
        print("  %-40s 执行人 %s" % (name, n[0] if n else "?"))


if __name__ == "__main__":
    main()
