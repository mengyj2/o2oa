# -*- coding: utf-8 -*-
"""临时切换 O2OA 登录开关（captchaLogin / codeLogin），用于自动化 UI 验证。
用法: python toggle_login.py off|on|show
"""
import json, sys, urllib.request, urllib.error

B = "http://127.0.0.1:9090"
AUTH = B + "/x_organization_assemble_authentication/jaxrs/authentication"
CFG = B + "/x_program_center/jaxrs/config/person"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method, path, body=None, token=None):
    r = urllib.request.Request(path, method=method)
    if token:
        r.add_header("x-token", token)
    data = None
    if body is not None:
        r.add_header("Content-Type", "application/json;charset=UTF-8")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        with OP.open(r, data, timeout=25) as x:
            return x.status, json.loads(x.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:200]


def login():
    r = urllib.request.Request(
        AUTH, method="POST",
        data=json.dumps({"credential": "admin", "password": "o2oaadmin2026"}).encode())
    r.add_header("Content-Type", "application/json")
    with OP.open(r, timeout=20) as x:
        return x.headers.get("x-token")


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "show").lower()
    tk = login()
    st, d = call("GET", CFG, None, tk)
    if st != 200 or not isinstance(d, dict) or not d.get("data"):
        print("读取失败:", st, str(d)[:200]); return 1
    p = d["data"]
    print("当前: captchaLogin=%s  codeLogin=%s" % (p.get("captchaLogin"), p.get("codeLogin")))
    if mode == "show":
        return 0
    want = (mode == "on")
    if p.get("captchaLogin") == want and p.get("codeLogin") == want:
        print("已是目标状态，无需修改")
        return 0
    p["captchaLogin"] = want
    p["codeLogin"] = want
    st2, d2 = call("PUT", CFG, p, tk)
    if st2 == 200:
        nd = (d2.get("data") or {}) if isinstance(d2, dict) else {}
        print("已切换 -> captchaLogin=%s  codeLogin=%s" % (nd.get("captchaLogin"), nd.get("codeLogin")))
        return 0
    print("写入失败:", st2, str(d2)[:250])
    return 1


if __name__ == "__main__":
    sys.exit(main())
