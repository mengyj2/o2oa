#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""列出 O2OA 门户「应用菜单」(数据字典 appmenus) 的分组与条目（只读）

背景（2026-09-23 实证）：
    O2OA 桌面有 **两个**「开始菜单」，来源完全不同——
      · ☰ 开始菜单（白色图标网格，页签 应用/流程/信息/数据）← MySQL CPT_COMPONENT
      · **门户首页「应用菜单」**（左侧竖排分组 / 窄屏深蓝分栏大菜单）
        ← **只由门户数据字典 `appmenus` 驱动，与 CPT_COMPONENT 无关**
    所以"新组件在门户里看不到"时，要查的是这个字典，不是 CPT_COMPONENT。

    读接口：GET {SURFACE}/x_portal_assemble_surface/jaxrs/dict/appmenus/portal/{flag}/data
            ★ flag 是**门户 alias**（本部署「系统首页」的 alias = index）；
              写成 /portal/dict/data 会 500。
    写接口：PUT {DESIGNER}/x_portal_assemble_designer/jaxrs/dict/{dictId}  （整对象覆盖）
            surface 的 PUT 恒 405。

用法：
    python tools/o2_menu_show.py                 # 列出全部分组 + 条目
    python tools/o2_menu_show.py 系统管理        # 只看某个分组
    python tools/o2_menu_show.py --json          # 输出原始 appNavis JSON（便于改后回写）
环境变量：O2OA_BASE / O2OA_USER / O2OA_PASS / O2OA_DICT_FLAG
"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("O2OA_BASE", "http://localhost:9090")
USER = os.environ.get("O2OA_USER", "admin")
PASS = os.environ.get("O2OA_PASS", "o2oaadmin2026")
FLAG = os.environ.get("O2OA_DICT_FLAG", "index")   # 门户 alias
ALIAS = "appmenus"


def login_token():
    req = urllib.request.Request(
        BASE + "/x_organization_assemble_authentication/jaxrs/authentication",
        data=json.dumps({"credential": USER, "password": PASS}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 绕开 shell 代理
    with opener.open(req, timeout=15) as r:
        tk = r.headers.get("x-token")
    if not tk:
        raise RuntimeError("登录未取到 x-token")
    return tk


def fetch_dict():
    tk = login_token()
    url = "%s/x_portal_assemble_surface/jaxrs/dict/%s/portal/%s/data" % (BASE, ALIAS, FLAG)
    req = urllib.request.Request(url, headers={"x-token": tk})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as r:
        body = json.loads(r.read().decode("utf-8"))
    data = body.get("data")
    if isinstance(data, str):
        data = json.loads(data)
    return data


def main():
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    want = [a for a in args if not a.startswith("--")]
    data = fetch_dict()
    navis = data.get("appNavis") or []

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0

    print("字典 %s @ 门户 flag=%s  —— 共 %d 个分组" % (ALIAS, FLAG, len(navis)))
    print()
    for i, g in enumerate(navis):
        title = g.get("title") or ""
        if want and title not in want:
            continue
        kids = g.get("children") or []
        hide = " [hide]" if g.get("hide") else ""
        print("[%2d] %s%s  (%d 项)  allow=%s" % (i, title, hide, len(kids), g.get("allow") or []))
        for k, ch in enumerate(kids):
            t = ch.get("title") or ""
            at = ch.get("actionType") or ""
            app = ch.get("app") or ""
            allow = ch.get("allow") or []
            h = " [hide]" if ch.get("hide") else ""
            tail = ("allow=%s" % ",".join(a.split("@")[0] for a in allow)) if allow else "allow=不限"
            print("      %2d. %-16s %-7s %-18s %s%s" % (k, t, at, app, tail, h))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
