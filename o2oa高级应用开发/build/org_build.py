# -*- coding: utf-8 -*-
"""
中国复合材料工业协会 · 组织一键搭建脚本（幂等，可重跑）
通过 cipher token 调组织管理 REST，建：
  - 顶层组织（已存在则复用：唯一标识 51100000500009247D）
  - 4 个部门：综合管理部 / 行业研究部 / 会员服务部 / 国际业务部
  - 9 名人员（含主管汇报关系）
  - 13 个身份（领导在所在部门与主组织均有身份；领导主身份=部门身份）
  - 10 个组织职务（部门负责人由分管领导兼任；综合部 4 专员=李芳）
依赖：Python 标准库；token 通过环境变量 O2OA_TOKEN 传入。
"""
import os, json, sys, urllib.request, urllib.error

TOKEN = os.environ.get("O2OA_TOKEN")
if not TOKEN:
    print("ERROR: 需设置环境变量 O2OA_TOKEN"); sys.exit(1)

BASE = "http://localhost:9090/x_organization_assemble_control/jaxrs"
LOG = []
def log(*a):
    s = " ".join(str(x) for x in a); LOG.append(s); print(s)

def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-token", TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"type": "error", "message": "HTTP %s" % e.code}

def get_unit(u):    return call("GET", "/unit/%s" % u)
def get_person(u):  return call("GET", "/person/%s" % u)
def get_identity(unit_u, person_u):
    return call("GET", "/identity/%s_%s" % (unit_u, person_u))
def list_unitduty(unit_u):
    return call("GET", "/unitduty/list/unit/%s" % unit_u)

# ---------------------------------------------------------------------------
TOP_NAME = "中国复合材料工业协会"
TOP_UNIQUE = "51100000500009247D"

# 部门：唯一标识 / 排序 / 分管领导
DEPTS = [
    ("综合管理部", "zhb", 1, "mengyijie"),
    ("行业研究部", "yjyb", 2, "mengyijie"),
    ("会员服务部", "hyfwb", 3, "luhongping"),
    ("国际业务部", "gjywb", 4, "luhongping"),
]
DEPT_UNIQUE = {n: u for n, u, _, _ in DEPTS}

# 人员：姓名 / 唯一 / 手机 / 主管(unique, 空=无)
PERSONS = [
    ("孟弋洁", "mengyijie", "13700000001", ""),        # 秘书长/法人
    ("卢宏萍", "luhongping", "13700000002", "mengyijie"), # 副秘书长
    ("李芳",   "lifang",    "13700000003", "mengyijie"), # 综合管理部
    ("时晓明", "shixiaoming","13700000004", "mengyijie"), # 行业研究部
    ("杜阳",   "duyang",    "13700000005", "mengyijie"), # 行业研究部
    ("李静",   "lijing",    "13700000006", "luhongping"), # 会员服务部
    ("奚莎莎", "xishasha",  "13700000007", "luhongping"), # 会员服务部
    ("赵旭东", "zhaoxudong","13700000008", "luhongping"), # 会员服务部
    ("罗舒涵", "luoshuhan", "13700000009", "luhongping"), # 国际业务部
]
PERSON_UNIQUE = {n: u for n, u, _, _ in PERSONS}

# 身份：人员唯一 / 部门唯一 / 是否主身份
IDENTITIES = [
    ("mengyijie", TOP_UNIQUE, False),   # 顶层（秘书长职务用）
    ("mengyijie", "zhb", True),         # 主身份=综合管理部
    ("mengyijie", "yjyb", False),
    ("luhongping", TOP_UNIQUE, False),  # 顶层（副秘书长职务用）
    ("luhongping", "hyfwb", True),      # 主身份=会员服务部
    ("luhongping", "gjywb", False),
    ("lifang", "zhb", True),
    ("shixiaoming", "yjyb", True),
    ("duyang", "yjyb", True),
    ("lijing", "hyfwb", True),
    ("xishasha", "hyfwb", True),
    ("zhaoxudong", "hyfwb", True),
    ("luoshuhan", "gjywb", True),
]

def identity_dn(person_name, unit_u, person_u):
    return "%s@%s_%s@I" % (person_name, unit_u, person_u)

# 组织职务：(部门唯一, 职务名, [人员唯一...])
DUTIES = [
    (TOP_UNIQUE, "秘书长",   ["mengyijie"]),
    (TOP_UNIQUE, "副秘书长", ["luhongping"]),
    ("zhb",  "部门负责人", ["mengyijie"]),
    ("zhb",  "人事专员", ["lifang"]),
    ("zhb",  "财务专员", ["lifang"]),
    ("zhb",  "档案管理员", ["lifang"]),
    ("zhb",  "合同管理员", ["lifang"]),
    ("yjyb", "部门负责人", ["mengyijie"]),
    ("hyfwb","部门负责人", ["luhongping"]),
    ("gjywb","部门负责人", ["luhongping"]),
]

# ---------------------------------------------------------------------------
def main():
    # 1) 部门
    log("=== 部门 ===")
    for name, u, order, lead in DEPTS:
        r = get_unit(u)
        if r.get("type") == "success":
            log("  复用部门", name, r["data"].get("distinguishedName")); continue
        r = call("POST", "/unit", {"name": name, "unique": u,
                                   "orderNumber": order, "superior": TOP_UNIQUE,
                                   "typeList": ["部门"]})
        if r.get("type") == "success":
            log("  创建部门", name, "OK")
        else:
            log("  !! 部门", name, "失败:", r.get("message"))

    # 2) 人员
    log("=== 人员 ===")
    for name, u, mobile, sup in PERSONS:
        r = get_person(u)
        if r.get("type") == "success":
            log("  复用人员", name); continue
        body = {"name": name, "unique": u, "mobile": mobile,
                "password": "O2oa@2026", "mail": "%s@cfia.local" % u}
        if sup:
            body["superior"] = sup   # 主管汇报关系（驱动 listSupPerson）
        r = call("POST", "/person", body)
        if r.get("type") == "success":
            log("  创建人员", name, "OK")
        else:
            log("  !! 人员", name, "失败:", r.get("message"))

    # 3) 身份
    log("=== 身份 ===")
    for pu, uu, major in IDENTITIES:
        pname = [n for n, x, _, _ in PERSONS if x == pu][0]
        r = get_identity(uu, pu)
        if r.get("type") == "success":
            log("  复用身份", pname, "@", uu); continue
        r = call("POST", "/identity", {"name": pname, "person": pu, "unit": uu,
                                       "unitName": (TOP_NAME if uu == TOP_UNIQUE else
                                                    [n for n, x, _, _ in DEPTS if x == uu][0]),
                                       "major": major})
        if r.get("type") == "success":
            log("  创建身份", pname, "@", uu, "major=%s" % major, "OK")
        else:
            log("  !! 身份", pname, "@", uu, "失败:", r.get("message"))

    # 4) 修正 孟弋洁 顶层身份 major=false（主身份应为部门身份）
    log("=== 修正主身份 ===")
    r = get_identity(TOP_UNIQUE, "mengyijie")
    if r.get("type") == "success" and r["data"].get("major") is True:
        flag = r["data"]["distinguishedName"]
        r2 = call("PUT", "/identity/%s" % flag, {"major": False})
        log("  孟弋洁顶层身份 major->false:", r2.get("type"))
        r = get_identity(TOP_UNIQUE, "luhongping")
        if r.get("type") == "success" and r["data"].get("major") is True:
            flag2 = r["data"]["distinguishedName"]
            r3 = call("PUT", "/identity/%s" % flag2, {"major": False})
            log("  卢宏萍顶层身份 major->false:", r3.get("type"))

    # 5) 组织职务
    log("=== 组织职务 ===")
    for uu, dname, members in DUTIES:
        lst = list_unitduty(uu)
        exist = [d for d in (lst.get("data") or []) if d.get("name") == dname]
        if exist:
            log("  复用职务", dname, "@", uu); continue
        idns = []
        for m in members:
            mname = [n for n, x, _, _ in PERSONS if x == m][0]
            idns.append(identity_dn(mname, uu, m))
        r = call("POST", "/unitduty", {"name": dname, "unit": uu, "identityList": idns})
        if r.get("type") == "success":
            log("  创建职务", dname, "@", uu, "->", idns)
        else:
            log("  !! 职务", dname, "@", uu, "失败:", r.get("message"))

    log("=== 完成 ===")

if __name__ == "__main__":
    main()
    with open(os.path.join(os.path.dirname(__file__), "_org_build.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))
