# -*- coding: utf-8 -*-
"""修正孟弋洁顶层身份主标识 + 路由正确性核查 + 清理测试用户"""
import os, json, sys, urllib.request, urllib.error, urllib.parse

TOKEN = os.environ.get("O2OA_TOKEN")
BASE = "http://localhost:9090/x_organization_assemble_control/jaxrs"
def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-token", TOKEN); req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode("utf-8"))
        except Exception: return {"type": "error", "message": "HTTP %s" % e.code}

def ident_name(dn):
    return dn.split("@")[0] if dn else "?"

print("=== 1) 修正孟弋洁顶层身份 major ===")
dn = "孟弋洁@51100000500009247D_mengyijie@I"
r = call("GET", "/identity/%s" % urllib.parse.quote(dn, safe=""))
if r.get("type") == "success":
    print("  当前 major =", r["data"].get("major"))
    if r["data"].get("major") is True:
        r2 = call("PUT", "/identity/%s" % urllib.parse.quote(dn, safe=""), {"major": False})
        print("  PUT major->false:", r2.get("type"), r2.get("message"))
    else:
        print("  无需修正")
else:
    print("  GET 失败:", r.get("message"))

print("\n=== 2) 路由核查（部门负责人 / 综合部专员 / 顶层职务）===")
TOP = "51100000500009247D"
units = [("综合管理部","zhb"),("行业研究部","yjyb"),("会员服务部","hyfwb"),("国际业务部","gjywb")]
for nm, u in units:
    lst = call("GET", "/unitduty/list/unit/%s" % u)
    duties = lst.get("data") or []
    line = "%s: " % nm
    for d in duties:
        names = "/".join(ident_name(i) for i in (d.get("identityList") or []))
        line += "[%s→%s] " % (d.get("name"), names)
    print("  " + line)
# 顶层职务
lst = call("GET", "/unitduty/list/unit/%s" % TOP)
for d in (lst.get("data") or []):
    names = "/".join(ident_name(i) for i in (d.get("identityList") or []))
    print("  中国复合材料工业协会 [%s→%s]" % (d.get("name"), names))

print("\n=== 3) 主管汇报关系核查（listSupPerson 来源）===")
for u in ["mengyijie","luhongping","lifang","shixiaoming","duyang","lijing","xishasha","zhaoxudong","luoshuhan"]:
    p = call("GET", "/person/%s" % u)
    if p.get("type") == "success":
        sup = p["data"].get("superior")
        print("  %s 主管=%s" % (p["data"].get("name"), ident_name(sup) if sup else "(无)"))

print("\n=== 4) 清理测试用户（仅删除 测试用户A/B）===")
for u in ["测试用户A","测试用户B"]:
    # 按 name 查 unique
    flt = call("POST", "/person/list/filter/1/size/20", {"name": u})
    for p in (flt.get("data") or []):
        if p.get("name") == u:
            d = call("DELETE", "/person/%s" % p.get("unique"))
            print("  删除 %s (%s): %s" % (u, p.get("unique"), d.get("type")))
