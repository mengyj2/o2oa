"""企业网盘（Drive）数据层回归自检

用途：验证 x_file_assemble_control（Drive 组件所复用的数据层）是否健康，
      以及"个人文件 / 企业文件(组织共享) / 回收站 / 容量"四条链路是否可读写。

用法：
    python tools/o2_drive_selftest.py                  # 只读体检（不改数据）
    python tools/o2_drive_selftest.py --full           # 完整读写闭环，跑完自动清理
    python tools/o2_drive_selftest.py --full --keep    # 保留测试数据以便人工查看

前置：O2OA 在 localhost:9090 运行；admin 账号可登录。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://localhost:9090"
SVC = "/x_file_assemble_control/jaxrs"
ORG = "/x_organization_assemble_control/jaxrs"
AUTH = "/x_organization_assemble_authentication/jaxrs/authentication"
TOP_FOLD = urllib.parse.quote("$$TOP_FOLD", safe="")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-38s %s" % ("PASS" if ok else "FAIL", name, detail))


def login(cred="admin", pwd="o2oaadmin2026"):
    r = urllib.request.Request(BASE + AUTH, method="POST",
                               data=json.dumps({"credential": cred, "password": pwd}).encode())
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=15) as x:
        return json.loads(x.read().decode())["data"]


def call(tk, method, path, body=None, raw=None, ctype=None):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("x-token", tk)
    data = None
    if raw is not None:
        r.add_header("Content-Type", ctype or "application/octet-stream")
        data = raw
    elif body is not None:
        r.add_header("Content-Type", "application/json")
        data = json.dumps(body, ensure_ascii=False).encode()
    try:
        with urllib.request.urlopen(r, data, timeout=25) as x:
            raw = x.read()
            try:
                return x.status, json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                # 下载类接口返回二进制，非 JSON
                return x.status, {"_bytes": len(raw), "_text": raw[:60].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}


def multipart(filename, content):
    b = "----o2selftest" + uuid.uuid4().hex
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n" % (b, filename)).encode()
            + content + ("\r\n--%s--\r\n" % b).encode())
    return body, "multipart/form-data; boundary=" + b


def readonly(tk, me):
    print("\n[1] 只读体检")
    for label, path, method, body in [
        ("个人文件 · 顶层文件夹", SVC + "/folder2/list/top", "GET", None),
        ("个人文件 · 顶层文件", SVC + "/attachment2/list/top", "GET", None),
        ("个人文件 · 容量", SVC + "/attachment2/user/capacity", "GET", None),
        ("个人文件 · 分类(文档)", SVC + "/attachment2/list/type/1/size/50", "POST", {"fileType": "office"}),
        ("企业文件 · 共享给我", SVC + "/share/list/to/me", "GET", None),
        ("我的分享 · 我分享的", SVC + "/share/list/my", "GET", None),
        ("回收站 · 列表", SVC + "/recycle/list", "GET", None),
        ("组织 · 顶层单位", ORG + "/unit/list/top", "GET", None),
    ]:
        s, d = call(tk, method, path, body)
        n = len(d.get("data") or []) if isinstance(d.get("data"), list) else "-"
        check(label, s == 200, "http=%s 条数=%s" % (s, n))


def full(tk, me, keep):
    print("\n[2] 读写闭环")
    name = "自检-%s" % uuid.uuid4().hex[:6]

    s, d = call(tk, "POST", SVC + "/folder2", {"name": name})
    fid = (d.get("data") or {}).get("id")
    check("建文件夹", s == 200 and fid, "id=%s" % fid)
    if not fid:
        return

    payload = ("Drive selftest\n").encode() * 3
    mp, ct = multipart("自检文件.txt", payload)
    s, d = call(tk, "POST", SVC + "/attachment2/upload/folder/" + fid, raw=mp, ctype=ct)
    aid = (d.get("data") or {}).get("id")
    check("上传文件", s == 200 and aid, "id=%s" % aid)

    s, d = call(tk, "GET", SVC + "/attachment2/list/folder/" + fid)
    n = len(d.get("data") or [])
    check("列夹内文件", s == 200 and n >= 1, "条数=%s" % n)

    s, d = call(tk, "GET", SVC + "/folder2/list/top")
    hit = any(x.get("name") == name for x in (d.get("data") or []))
    check("顶层可见该文件夹", s == 200 and hit, "命中=%s" % hit)

    s, d = call(tk, "GET", SVC + "/attachment2/user/capacity")
    cap = (d.get("data") or {}).get("value")
    check("容量可读", s == 200 and isinstance(cap, int), "已用=%sB" % cap)

    if aid:
        s, d = call(tk, "GET", SVC + "/attachment2/%s/download/stream" % aid)
        nb = (d or {}).get("_bytes")
        check("下载文件", s == 200 and nb == len(payload), "bytes=%s 期望=%s" % (nb, len(payload)))

    # 组织级共享（"企业文件"栏的依据）
    s, d = call(tk, "GET", ORG + "/unit/list/top")
    lst = d.get("data") or []
    uniq = lst[0].get("unique") if lst else None
    check("取组织 unique", bool(uniq), "unique=%s" % uniq)

    share_id = None
    if aid and uniq:
        s, d = call(tk, "POST", SVC + "/share",
                    {"fileId": aid, "shareType": "member", "shareUserList": [],
                     "shareOrgList": [uniq], "shareGroupList": []})
        share_id = (d.get("data") or {}).get("id")
        check("共享给组织", s == 200, "shareId=%s" % share_id)

        s, d = call(tk, "GET", SVC + "/share/list/to/me")
        hit = any(x.get("fileId") == aid for x in (d.get("data") or []))
        check("共享在我处可见", s == 200 and hit, "命中=%s" % hit)

    if not keep:
        # ★ 顺序强制：先取消共享 → 再删文件（进回收站）→ 清回收站 → 删文件夹
        #   文件进回收站后 share 记录会失效，取消共享将不可用。
        if share_id:
            s, _ = call(tk, "DELETE", SVC + "/share/" + share_id)
            check("取消共享", s == 200)
        if aid:
            s, d = call(tk, "DELETE", SVC + "/attachment2/" + aid)
            check("删除进回收站", s == 200, "value=%s" % (d.get("data") or {}))

        print("\n[3] 清理测试数据")
        s, d = call(tk, "GET", SVC + "/recycle/list")
        for it in (d.get("data") or []):
            if it.get("name") == "自检文件.txt":
                call(tk, "DELETE", SVC + "/recycle/%s/delete" % it.get("id"))
        s, _ = call(tk, "DELETE", SVC + "/folder2/" + fid)
        check("删除测试文件夹", s == 200)
    else:
        print("\n[3] 保留测试数据（--keep）：文件夹=%s 文件=%s 分享=%s" % (name, aid, share_id))


def main():
    do_full = "--full" in sys.argv
    keep = "--keep" in sys.argv
    print("=" * 62)
    print("  企业网盘（Drive）数据层自检   %s" % BASE)
    print("=" * 62)

    auth = login()
    tk = auth["token"]
    ident = (auth.get("identityList") or [{}])[0]
    me = ident.get("distinguishedName", "")
    print("账号：%s  |  单位：%s\n" % (ident.get("name"), ident.get("unitName")))

    readonly(tk, me)
    if do_full:
        full(tk, me, keep)

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 62)
    print("  汇总：%d 项，通过 %d，失败 %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    if bad:
        for n, _, det in bad:
            print("    FAIL %s %s" % (n, det))
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
