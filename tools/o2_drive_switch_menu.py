"""把门户应用菜单「企业网盘」的 app 从 File 切到 Drive（本地自研组件）

字典位置：GET/PUT /x_portal_assemble_surface/jaxrs/dict/appmenus/portal/index/data
"""
import json, sys, urllib.request, urllib.error

BASE = "http://localhost:9090"
DICT = "/x_portal_assemble_surface/jaxrs/dict/appmenus/portal/index/data"
TARGET_TITLE = "企业网盘"


def login(cred="admin", pwd="o2oaadmin2026"):
    r = urllib.request.Request(BASE + "/x_organization_assemble_authentication/jaxrs/authentication",
                               data=json.dumps({"credential": cred, "password": pwd}).encode(), method="POST")
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=15) as x:
        return json.loads(x.read().decode())["data"]["token"]


def call(tk, method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("x-token", tk)
    d = None
    if body is not None:
        r.add_header("Content-Type", "application/json")
        d = json.dumps(body, ensure_ascii=False).encode()
    try:
        with urllib.request.urlopen(r, d, timeout=25) as x:
            raw = x.read().decode("utf-8", "replace")
            try:
                return x.status, json.loads(raw)
            except Exception:
                return x.status, raw[:300]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300]


def find_target(navis):
    hits = []
    for n in navis:
        for c in (n.get("children") or []):
            if c.get("title") == TARGET_TITLE:
                hits.append((n.get("title"), c))
    return hits


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    tk = login()

    s, d = call(tk, "GET", DICT)
    data = d.get("data") if isinstance(d, dict) else None
    if not isinstance(data, dict) or "appNavis" not in data:
        print("读取字典失败：", s, str(d)[:200])
        return

    hits = find_target(data["appNavis"])
    print("命中「%s」条目 %d 个：" % (TARGET_TITLE, len(hits)))
    for g, c in hits:
        print("   分组=%-10s app=%-8s actionType=%-8s portal=%s" %
              (g, c.get("app"), c.get("actionType"), c.get("portal")))

    if mode == "check":
        print("\n(只读检查，未修改)")
        return

    changed = 0
    for g, c in hits:
        if c.get("app") != "Drive":
            c["app"] = "Drive"
            c["actionType"] = "app"
            changed += 1
            print("   已改：%s -> app=Drive" % g)

    if not changed:
        print("无需修改")
        return

    s2, d2 = call(tk, "PUT", DICT, data)
    print("\nPUT 结果：", s2, str(d2)[:200])

    s3, d3 = call(tk, "GET", DICT)
    hits3 = find_target(d3["data"]["appNavis"]) if isinstance(d3, dict) else []
    print("复核：")
    for g, c in hits3:
        print("   分组=%-10s app=%-8s actionType=%s" % (g, c.get("app"), c.get("actionType")))


if __name__ == "__main__":
    main()
