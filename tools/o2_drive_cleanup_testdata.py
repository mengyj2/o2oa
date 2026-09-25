# -*- coding: utf-8 -*-
"""清理由本轮探针/回归产生的测试残留，并把被回归改动的网盘策略复位。
只删除明确属于本次测试的对象（__ 前缀 / 容量探针 / 复刻验证），不动任何真实业务数据。"""
import json, urllib.request, urllib.error, urllib.parse

BASE = "http://localhost:9090"
SVC = "/x_file_assemble_control/jaxrs"
SRF = "/x_portal_assemble_surface/jaxrs"
DSN = "/x_portal_assemble_designer/jaxrs"
AUTH = "/x_organization_assemble_authentication/jaxrs/authentication"
TOPF = urllib.parse.quote("$$TOP_FOLD", safe="")
TEST_RE = ("__rt5", "__diag", "容量探针", "复刻验证", "capacity_probe", "__RT5")


def login(c="admin", p="o2oaadmin2026"):
    r = urllib.request.Request(BASE + AUTH, method="POST",
                               data=json.dumps({"credential": c, "password": p}).encode())
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=15) as x:
        return x.headers.get("x-token")


def call(tk, m, path, body=None):
    r = urllib.request.Request(BASE + path, method=m)
    r.add_header("x-token", tk)
    d = None
    if body is not None:
        r.add_header("Content-Type", "application/json")
        d = json.dumps(body, ensure_ascii=False).encode()
    try:
        with urllib.request.urlopen(r, d, timeout=40) as x:
            raw = x.read()
            try:
                return x.status, json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return x.status, {"_bytes": len(raw)}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, None
    except Exception as e:
        return -1, {"_err": str(e)}


def is_test(n):
    v = (n or "").lower()
    return any(k.lower() in v for k in TEST_RE)


tk = login()
print("== 1. 顶层文件/文件夹残留 ==")
st, d = call(tk, "GET", SVC + "/attachment2/list/top")
files = ((d or {}).get("data") or [])
st, d = call(tk, "GET", SVC + "/folder2/list/top")
folders = ((d or {}).get("data") or [])
hits_f = [f for f in files if is_test(f.get("name"))]
hits_d = [f for f in folders if is_test(f.get("name"))]
print("  文件:", [f["name"] for f in hits_f])
print("  文件夹:", [f["name"] for f in hits_d])

print("\n== 2. 取消相关共享 ==")
st, d = call(tk, "GET", SVC + "/share/list/my")
shares = ((d or {}).get("data") or [])
for s in shares:
    if is_test(s.get("name")):
        st2, _ = call(tk, "DELETE", SVC + "/share/" + urllib.parse.quote(s["id"], safe=""))
        print("  取消共享:", s.get("name"), st2)

print("\n== 3. 删除文件与文件夹 ==")
for f in hits_f:
    st2, _ = call(tk, "DELETE", SVC + "/attachment2/" + urllib.parse.quote(f["id"], safe=""))
    print("  删文件:", f["name"], st2)
for f in hits_d:
    st2, _ = call(tk, "DELETE", SVC + "/folder2/" + urllib.parse.quote(f["id"], safe=""))
    print("  删文件夹:", f["name"], st2)

print("\n== 4. 回收站彻底删除 ==")
st, d = call(tk, "GET", SVC + "/recycle/list")
rec = ((d or {}).get("data") or [])
print("  回收站现有:", [r.get("name") for r in rec])
for r in rec:
    if is_test(r.get("name")):
        st2, _ = call(tk, "DELETE", SVC + "/recycle/" + urllib.parse.quote(r["id"], safe="") + "/delete")
        print("  彻底删除:", r.get("name"), st2)

print("\n== 5. 复位网盘策略字典 driveSetting ==")
st, d = call(tk, "GET", SRF + "/portal/list")
portals = ((d or {}).get("data") or [])
portal = None
for p in portals:
    if p.get("alias") == "index":
        portal = p
portal = portal or (portals[0] if portals else None)
if not portal:
    print("  !! 未找到门户，跳过")
else:
    st, d = call(tk, "GET", DSN + "/dict/list/portal/" + urllib.parse.quote(portal["id"], safe=""))
    dct = None
    for x in ((d or {}).get("data") or []):
        if x.get("alias") == "driveSetting":
            dct = x
    print("  字典:", (dct or {}).get("id"), "现有 data:", json.dumps((dct or {}).get("data"), ensure_ascii=False))
    if dct:
        data = dct.get("data") or {}
        data["shareLimitMb"] = 0
        data["creatorPersonList"] = []
        data["creatorRoleList"] = []
        obj = dict(dct)
        obj["data"] = data
        st2, d2 = call(tk, "PUT", DSN + "/dict/" + urllib.parse.quote(dct["id"], safe=""), obj)
        print("  写回:", st2)
        st3, d3 = call(tk, "GET", SRF + "/dict/driveSetting/portal/index/data")
        print("  读回:", json.dumps((d3 or {}).get("data"), ensure_ascii=False))

print("\n== 6. 复核最终状态 ==")
st, d = call(tk, "GET", SVC + "/attachment2/list/top")
print("  顶层文件:", [f.get("name") for f in ((d or {}).get("data") or [])])
st, d = call(tk, "GET", SVC + "/folder2/list/top")
print("  顶层文件夹:", [f.get("name") for f in ((d or {}).get("data") or [])])
st, d = call(tk, "GET", SVC + "/share/list/my")
print("  我的分享:", [f.get("name") for f in ((d or {}).get("data") or [])])
st, d = call(tk, "GET", SVC + "/recycle/list")
print("  回收站:", [f.get("name") for f in ((d or {}).get("data") or [])])
st, d = call(tk, "GET", SVC + "/attachment2/user/capacity")
print("  已用容量:", (d or {}).get("data", {}).get("value"))
st, d = call(tk, "GET", SVC + "/config/system/config")
cfg = (d or {}).get("data") or {}
print("  系统配置 capacity/recycleDays/后缀:", cfg.get("capacity"), cfg.get("recycleDays"),
      ((cfg.get("properties") or {}).get("fileTypeIncludes")))
