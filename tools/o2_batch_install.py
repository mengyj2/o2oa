#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o2_batch_install.py —— 批量安装 O2OA 离线插件包（断云环境）

背景（2026-09-19 实测）：
  · 离线安装接口：POST /x_program_center/jaxrs/market/install/offline
  · 上传字段名必须是 "file"
  · 全部免费市场包从 https://www.o2oa.net/market/ 下载后，可直接离线安装
  · ★ 部分包（约 4 个）的 setup.json 被市场侧截断：末字段 name 缺尾部引号
    → 本工具自动修复（在最后一个 } 前补一个 "）
  · ★ 存在重复 ID：同名插件不同版本、或市场数据错位
    → 默认按 (id) 去重，保留版本号更高者；--keep-all 可全部安装

用法：
  python o2_batch_install.py scan                    # 只扫描，输出清单 + 重复/损坏报告
  python o2_batch_install.py install                 # 安装全部（去重后）
  python o2_batch_install.py install --keep-all      # 不去重，全部安装
  python o2_batch_install.py install --only-name AI助手,公文管理
  python o2_batch_install.py install --skip-name Office在线协作,PDF预览
  python o2_batch_install.py install --fix-only      # 只修复 setup.json，不安装

环境变量：O2OA_BASE / O2OA_USER / O2OA_PWD
"""

import argparse
import json
import os
import re
import sys
import uuid
import shutil
import tempfile
import zipfile
import urllib.request
import urllib.error
import mimetypes

BASE = os.environ.get("O2OA_BASE", "http://localhost:9090")
USER = os.environ.get("O2OA_USER", "xadmin")
PWD = os.environ.get("O2OA_PWD", "o2oaadmin2026")
PLUGIN_DIR = os.environ.get("O2OA_PLUGIN_DIR", r"D:\O2OA\插件")
FIXED_DIR = os.environ.get("O2OA_FIXED_DIR", r"D:\O2OA\插件\_fixed")
INSTALL_URL = BASE + "/x_program_center/jaxrs/market/install/offline"


# ---------------------------------------------------------------- http utils
def _post_multipart(url, fields, token=None, timeout=180):
    boundary = "----o2pkg" + uuid.uuid4().hex
    body = b""
    for name, (fname, fdata, ctype) in fields.items():
        body += ("--%s\r\n" % boundary).encode()
        body += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, fname)).encode("utf-8")
        body += ("Content-Type: %s\r\n\r\n" % ctype).encode()
        body += fdata
        body += b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}
    if token:
        headers["x-token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def login():
    body = json.dumps({"credential": USER, "password": PWD}).encode()
    req = urllib.request.Request(
        BASE + "/x_organization_assemble_authentication/jaxrs/authentication",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode("utf-8", "ignore"))
    if j.get("type") != "success":
        raise SystemExit("登录失败: " + json.dumps(j, ensure_ascii=False))
    return j["data"]["token"]


# ---------------------------------------------------------------- pkg inspect
def read_setup(z):
    """返回 (dict|None, how, raw_text, entry_name)。市场包末字段可能缺尾引号。"""
    entries = [n for n in z.namelist() if n.endswith("setup.json")]
    if not entries:
        return None, "no_setup", "", None
    entry = entries[0]
    raw = z.read(entry)
    txt = raw.decode("utf-8-sig", "ignore")
    try:
        return json.loads(txt), "strict", txt, entry
    except Exception:
        pass
    # 市场侧截断：末字段值缺尾部引号，最后是 ',\n    "version": "V1.0"\n}'
    # 若 'name' 行未闭合，则把行尾的逗号替换成 '",'
    fixed = re.sub(r'("name"\s*:\s*"[^"\n]*?),\s*\n', r'\1",\n', txt)
    if fixed != txt:
        try:
            return json.loads(fixed), "repaired", fixed, entry
        except Exception as e:
            return None, "unfixable:%s" % e, txt, entry
    return None, "broken", txt, entry


def _ver_key(v):
    return [int(x) if x.isdigit() else 0 for x in re.findall(r"\d+", str(v))] or [0]


def scan(d):
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(".zip"):
            continue
        fp = os.path.join(d, fn)
        try:
            z = zipfile.ZipFile(fp)
            j, how, txt, entry = read_setup(z)
            info = {"file": fn, "path": fp, "how": how, "setup_entry": entry,
                    "id": (j or {}).get("id"), "name": (j or {}).get("name"),
                    "version": (j or {}).get("version"), "setup": j, "raw": txt,
                    "size": os.path.getsize(fp)}
            # 包内是否含实际内容
            tops = sorted(set(n.split("/")[0] for n in z.namelist() if n.strip()))
            info["dirs"] = [t for t in tops if t not in ("__MACOSX", "setup.json")]
            out.append(info)
        except Exception as e:
            out.append({"file": fn, "path": fp, "how": "zip_err:%s" % e,
                        "id": None, "name": None, "version": None, "dirs": [], "size": 0})
    return out


def dedupe(items, keep_all=False):
    """按 id 去重，保留版本号最高者。返回 (keep, dropped)。"""
    if keep_all:
        return items, []
    best = {}
    for it in items:
        if not it.get("id"):
            continue
        k = it["id"]
        if k not in best or _ver_key(it.get("version")) > _ver_key(best[k].get("version")):
            best[k] = it
    keep_ids = set()
    for it in items:
        if it.get("id") and best[it["id"]] is it:
            keep_ids.add(it["file"])
    keep, drop = [], []
    for it in items:
        (keep if (it["file"] in keep_ids or not it.get("id")) else drop).append(it)
    return keep, drop


def repack_with_fix(it, out_dir):
    """把修复后的 setup.json 写回 zip，输出到 out_dir，返回新路径。"""
    os.makedirs(out_dir, exist_ok=True)
    src = it["path"]
    dst = os.path.join(out_dir, it["file"])
    zin = zipfile.ZipFile(src)
    fixed_text = it["raw"]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            if n == it["setup_entry"]:
                continue
            if n.startswith("__MACOSX/"):
                continue
            zout.writestr(n, zin.read(n))
        zout.writestr(it["setup_entry"], fixed_text.encode("utf-8"))
    zin.close()
    return dst


def install_one(token, zip_path):
    with open(zip_path, "rb") as f:
        data = f.read()
    fname = os.path.basename(zip_path)
    st, body = _post_multipart(INSTALL_URL, {"file": (fname, data, "application/zip")}, token=token)
    ok = False
    msg = body[:300]
    try:
        j = json.loads(body)
        if j.get("type") == "success" and j.get("data", {}).get("value") is True:
            ok, msg = True, "OK"
        else:
            msg = json.dumps(j, ensure_ascii=False)[:300]
    except Exception:
        pass
    return ok, st, msg


# ---------------------------------------------------------------- commands
def cmd_scan(args):
    items = scan(PLUGIN_DIR)
    keep, drop = dedupe(items, args.keep_all)
    print("共 %d 个包：可安装 %d，去重跳过 %d\n" % (len(items), len(keep), len(drop)))
    print("--- 重复 ID（被跳过） ---")
    for it in drop:
        print("  %-42s | %s %s | id=%s" % (it["file"], it["name"], it["version"], it["id"]))
    print("\n--- 待修复（setup.json 截断） ---")
    for it in items:
        if it["how"] == "repaired":
            print("  %-42s | %s" % (it["file"], it["name"]))
    print("\n--- 不可修复 ---")
    for it in items:
        if it["how"].startswith("unfixable") or it["how"].endswith("err"):
            print("  %-42s | %s" % (it["file"], it["how"]))
    print("\n--- 安装清单（%d） ---" % len(keep))
    for i, it in enumerate(keep, 1):
        print("  %2d. %-30s %-10s %s" % (i, it["name"], it["version"], it["file"]))


def cmd_install(args):
    items = scan(PLUGIN_DIR)
    only = [s.strip() for s in args.only_name.split(",")] if args.only_name else None
    skip = [s.strip() for s in args.skip_name.split(",")] if args.skip_name else []
    if only:
        items = [i for i in items if i["name"] in only or i["file"] in only]
    if skip:
        items = [i for i in items if i["name"] not in skip and i["file"] not in skip]
    keep, drop = dedupe(items, args.keep_all)
    print("计划安装 %d 个（去重跳过 %d 个）" % (len(keep), len(drop)))
    for it in drop:
        print("   skip(dup): %s | %s %s" % (it["file"], it["name"], it["version"]))

    # 修复截断的 setup.json
    prepared = []
    for it in keep:
        if it["how"] == "repaired":
            p = repack_with_fix(it, FIXED_DIR)
            it["install_path"] = p
            print("   fix: %s -> _fixed/" % it["file"])
        elif it["how"] == "strict":
            it["install_path"] = it["path"]
        else:
            print("   BAD: %s (%s) -> 跳过" % (it["file"], it["how"]))
            continue
        prepared.append(it)

    if args.fix_only:
        print("\n[fix-only] 已修复 %d 个包到 %s" % (len(prepared), FIXED_DIR))
        return

    token = login()
    ok_n = bad_n = 0
    results = []
    for i, it in enumerate(prepared, 1):
        ok, st, msg = install_one(token, it["install_path"])
        flag = "OK  " if ok else "FAIL"
        print("[%2d/%2d] %s %-30s %s" % (i, len(prepared), flag, it["name"], "" if ok else msg))
        results.append({"name": it["name"], "file": it["file"], "ok": ok, "http": st, "msg": msg})
        if ok:
            ok_n += 1
        else:
            bad_n += 1

    print("\n==== 结果：成功 %d / 失败 %d ====" % (ok_n, bad_n))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_install_result.json"),
              "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    if bad_n:
        print("\n--- 失败清单 ---")
        for r in results:
            if not r["ok"]:
                print("  %-30s HTTP %s | %s" % (r["name"], r["http"], r["msg"][:150]))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--keep-all", action="store_true")
    i = sub.add_parser("install")
    i.add_argument("--keep-all", action="store_true")
    i.add_argument("--only-name", default=None)
    i.add_argument("--skip-name", default=None)
    i.add_argument("--fix-only", action="store_true")
    args = ap.parse_args()
    if args.cmd == "scan":
        cmd_scan(args)
    else:
        cmd_install(args)


if __name__ == "__main__":
    main()
