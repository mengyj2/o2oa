# -*- coding: utf-8 -*-
"""_chk_org.py —— 只读核对线上组织架构是否符合「4 部门 / 9 人」新版。"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)
BASE = "http://localhost:9090/x_organization_assemble_control/jaxrs"

EXPECT_DEPT = ["综合管理部", "行业研究部", "会员服务部", "国际业务部"]
EXPECT_PERSON = ["孟弋洁", "卢宏萍", "李芳", "时晓明", "杜阳", "李静",
                 "奚莎莎", "赵旭东", "罗舒涵"]


def call(path, token):
    req = urllib.request.Request(BASE + path)
    req.add_header("x-token", token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"type": "error", "message": "HTTP %s" % e.code}


def main():
    from import_xapps import get_token
    t = get_token()
    print("token len", len(t))

    print("\n=== 部门（组织单元）===")
    r = call("/unit/list/all", t)
    units = r.get("data", []) if r.get("type") == "success" else []
    got = {}
    for u in units:
        got[u.get("name")] = u
    for name in EXPECT_DEPT:
        u = got.get(name)
        print("  %-10s %s  (dn=%s)" % (name, "OK" if u else "缺失",
                                       (u or {}).get("distinguishedName", "")[:44]))
    extra = [n for n in got if n not in EXPECT_DEPT and n != "中国复合材料工业协会"]
    if extra:
        print("  额外单元:", extra)

    print("\n=== 人员 ===")
    r = call("/person/list/all", t)
    persons = r.get("data", []) if r.get("type") == "success" else []
    names = {}
    for p in persons:
        names[p.get("name")] = p
    for name in EXPECT_PERSON:
        p = names.get(name)
        print("  %-8s %s  (mobile=%s)" % (name, "OK" if p else "缺失",
                                          (p or {}).get("mobile", "")))
    extra = [n for n in names if n not in EXPECT_PERSON]
    if extra:
        print("  额外人员:", extra)

    print("\n=== 部门职务（UnitDuty）===")
    for name in EXPECT_DEPT:
        u = got.get(name)
        if not u:
            continue
        dn = u.get("distinguishedName")
        r2 = call("/unitduty/list/unit/%s" % urllib.parse.quote(dn, safe=""), t)
        ds = r2.get("data", []) if r2.get("type") == "success" else []
        print("  %-10s -> %s" % (name, ", ".join(
            "%s(%d人)" % (d.get("name"), len(d.get("identityList") or []))
            for d in ds) or "无"))

    print("\n=== 顶层单元职务 ===")
    top = got.get("中国复合材料工业协会")
    if top:
        dn = top.get("distinguishedName")
        r3 = call("/unitduty/list/unit/%s" % urllib.parse.quote(dn, safe=""), t)
        ds = r3.get("data", []) if r3.get("type") == "success" else []
        for d in ds:
            print("  %s -> %d 人" % (d.get("name"), len(d.get("identityList") or [])))


if __name__ == "__main__":
    main()
