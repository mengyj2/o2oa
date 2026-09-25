#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o2_pkg.py —— O2OA 离线安装包构造器 / 导出器

用途：在断云环境下，构造可分发的 O2OA 离线安装包（zip），
      或用 install/offline 接口把包装到本地 O2OA。

背景与坑（2026-09-19 实测）：
  · 离线安装接口：POST /x_program_center/jaxrs/market/install/offline
  · 上传字段名必须是 "file"（files/upload/attachment 等全部无效）
  · zip 内路径必须用正斜杠（反斜杠会导致解包异常）
  · 包结构：setup.json(必填) + 可选 custom/ xapp/ web/ config/
  · .xapp 是 JSON，结构见 WrapModule（processPlatformList/portalList/queryList/cmsList/serviceModuleList）

用法：
  # 构造一个最小离线包
  python o2_pkg.py build --out my-app.zip --id my-app --name "我的应用"

  # 安装到本地 O2OA
  python o2_pkg.py install --zip my-app.zip

  # 一键：构造 + 安装
  python o2_pkg.py build-install --out my-app.zip --id my-app --name "我的应用"

环境变量：
  O2OA_BASE   O2OA 地址，默认 http://localhost:9090
  O2OA_USER   管理员账号，默认 xadmin
  O2OA_PWD    密码，默认 o2oaadmin2026
"""

import argparse
import json
import os
import sys
import tempfile
import zipfile
import uuid

try:
    import urllib.request
    import urllib.error
except ImportError:
    sys.exit("需要 Python 3")

BASE = os.environ.get("O2OA_BASE", "http://localhost:9090")
USER = os.environ.get("O2OA_USER", "xadmin")
PWD = os.environ.get("O2OA_PWD", "o2oaadmin2026")


def http_json(url, method="GET", data=None, token=None, raw=False):
    """极简 JSON HTTP 客户端（避免依赖 requests）"""
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["x-token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
            if raw:
                return r.status, content
            return r.status, json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as e:
        content = e.read()
        if raw:
            return e.code, content
        try:
            return e.code, json.loads(content.decode("utf-8"))
        except Exception:
            return e.code, {"raw": content.decode("utf-8", "ignore")}


def login():
    """登录取 token"""
    st, js = http_json(
        f"{BASE}/x_organization_assemble_authentication/jaxrs/authentication",
        method="POST",
        data={"credential": USER, "password": PWD},
    )
    if js.get("type") != "success":
        sys.exit(f"登录失败: {json.dumps(js, ensure_ascii=False)[:300]}")
    return js["data"]["token"]


def build_package(out_path, app_id, name, category="自建", version="1.0",
                  describe="", xapps=None, with_custom=False):
    """
    构造离线安装包。
    xapps: [{"filename": "demo.xapp", "content": {...}}]  可选
    """
    tmp = tempfile.mkdtemp(prefix="o2pkg_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)

    # setup.json —— 应用元信息（必填）
    setup = {
        "id": app_id,
        "name": name,
        "category": category,
        "version": version,
        "describe": describe or f"{name}（离线包）",
        "abort": describe or name,
        "installSteps": "离线安装，无需额外配置",
        "vipApp": False,
        "restart": False,
    }
    with open(os.path.join(data_dir, "setup.json"), "w", encoding="utf-8") as f:
        json.dump(setup, f, ensure_ascii=False, indent=2)

    # xapp/ —— 模块文件
    if xapps:
        xapp_dir = os.path.join(data_dir, "xapp")
        os.makedirs(xapp_dir, exist_ok=True)
        for item in xapps:
            fn = item["filename"]
            if not fn.endswith(".xapp"):
                fn += ".xapp"
            with open(os.path.join(xapp_dir, fn), "w", encoding="utf-8") as f:
                json.dump(item["content"], f, ensure_ascii=False, indent=2)

    # custom/ —— 自定义应用占位
    if with_custom:
        os.makedirs(os.path.join(data_dir, "custom"), exist_ok=True)
        with open(os.path.join(data_dir, "custom", ".keep"), "w") as f:
            f.write("")

    # 打包（关键：斜杠必须是 /）
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(data_dir):
            for fn in files:
                fp = os.path.join(root, fn)
                arc = os.path.relpath(fp, data_dir).replace(os.sep, "/")
                z.write(fp, arc)
    return out_path


def install(zip_path, token=None):
    """用 multipart 上传到 install/offline（字段名必须是 file）"""
    token = token or login()
    boundary = "----o2pkg" + uuid.uuid4().hex
    with open(zip_path, "rb") as f:
        file_data = f.read()
    fname = os.path.basename(zip_path)

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
    ).encode()
    body += b"Content-Type: application/zip\r\n\r\n"
    body += file_data
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE}/x_program_center/jaxrs/market/install/offline",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": "unparseable"}


def cmd_build(args):
    xapps = None
    if args.xapp_file:
        with open(args.xapp_file, encoding="utf-8") as f:
            xapps = [{"filename": os.path.basename(args.xapp_file),
                      "content": json.load(f)}]
    p = build_package(args.out, args.id, args.name, args.category,
                      args.version, args.describe, xapps, args.with_custom)
    print(f"✅ 已生成离线包: {p}")
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            print(f"   - {n}")


def cmd_install(args):
    st, js = install(args.zip)
    ok = js.get("type") == "success"
    print(("✅ 安装成功" if ok else "❌ 安装失败") + f" (HTTP {st})")
    print(json.dumps(js, ensure_ascii=False)[:600])
    return 0 if ok else 1


def cmd_build_install(args):
    cmd_build(args)
    print()
    st, js = install(args.out)
    ok = js.get("type") == "success"
    print(("✅ 安装成功" if ok else "❌ 安装失败") + f" (HTTP {st})")
    print(json.dumps(js, ensure_ascii=False)[:600])
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="O2OA 离线安装包构造器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_build_args(p):
        p.add_argument("--out", required=True, help="输出 zip 路径")
        p.add_argument("--id", required=True, help="应用唯一标识")
        p.add_argument("--name", required=True, help="应用名称")
        p.add_argument("--category", default="自建")
        p.add_argument("--version", default="1.0")
        p.add_argument("--describe", default="")
        p.add_argument("--xapp-file", default=None, help="可选 .xapp/JSON 文件")
        p.add_argument("--with-custom", action="store_true")

    p1 = sub.add_parser("build", help="仅构造离线包")
    add_build_args(p1)
    p1.set_defaults(func=cmd_build)

    p2 = sub.add_parser("install", help="安装已有离线包")
    p2.add_argument("--zip", required=True)
    p2.set_defaults(func=cmd_install)

    p3 = sub.add_parser("build-install", help="构造并安装")
    add_build_args(p3)
    p3.set_defaults(func=cmd_build_install)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
