#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键把「导入的应用」全部登记进桌面「开始」菜单（幂等，可反复执行）。

背景（O2OA 10.0.2 实测结论）：
    桌面开始菜单由 MWF.xDesktop.Layout.Top.loadMenu() 构造，只吃三个源：
      1) o2_core/o2/xDesktop/$Layout/applications.json  —— 静态目录（默认 []）
      2) GET /x_component_assemble_control/jaxrs/component/list/all
         —— 读 MySQL 表 CPT_COMPONENT，并过滤掉 Components.SYSTEM_NAME_NAMES
            （硬编码的 24 个内置名），因此凡是 DB 里非这 24 个名字的都算
            "custom"，也就是我们登记进去的应用。
      3) GET /x_portal_assemble_surface/jaxrs/portal/list —— 仅 pcClient=true 的
            门户会被渲染成图标。
      流程应用/查询/CMS 的 createXxxAppMenu 调用在 Layout.js 里是被注释掉的，
      所以既不会因为"已安装"就自动出现。

因此本脚本分三层补登记：
    A. WAR 组件型（工作管理/客户管理/台账/Office 协作…）
       -> 走 CPT_COMPONENT（POST /jaxrs/component，后端强制 type=custom）
       -> 点击 = openApplication(path)，在桌面内开真正的应用窗口
    B. 流程应用型（公文/合同/预算/财务/档案/HR…）
       -> 走 applications.json 的 "@url:" 条目
       -> 点击 = 新窗口深链 /x_desktop/index.html?app=process.Application&option={id,appId}
    C. 门户型：把 pcClient 为 NULL 的门户补成 true，让它们进入 (3) 的列表

幂等保证：
    A 用 name 去重，已存在跳过（不覆盖你手工调过的 allowList/orderNumber）
    B 每次整体重写 applications.json（内容由当前应用 id 决定，可重复生成）
    C 只对 pcClient != true 的做一次 PUT

用法:
    python o2_sync_startmenu.py check    # 只体检，不改动
    python o2_sync_startmenu.py apply    # 执行三层补登记
"""
import sys, os, json, subprocess, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2 import login, get, post, put, extract_list

HOST = "http://localhost:9090"
CONTAINER = "o2oa-server"
CONTAINER_APPS_JSON = "/opt/o2server/servers/webServer/o2_core/o2/xDesktop/$Layout/applications.json"
PATCH_APPS_JSON = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "patch", "web", "applications.json"))

COMP = "/x_component_assemble_control/jaxrs/component"
# 读门户列表用 surface（只读）；改 pcClient 必须用 designer —— surface 的
# /jaxrs/portal/{id} 不接受 PUT（实测 405 Method Not Allowed）。
PORTAL_LIST = "/x_portal_assemble_surface/jaxrs/portal/list"
PORTAL_DESIGNER_LIST = "/x_portal_assemble_designer/jaxrs/portal/list"
PORTAL_DESIGNER = "/x_portal_assemble_designer/jaxrs/portal"

# ---- A 层：要登记成开始菜单图标的 WAR 组件 ----
# key = x_component_<path> 目录名 = xDesktop 应用命名空间
COMPONENTS = [
    ("TeamWork",         "工作管理",       101),
    ("CRM",              "客户管理",       102),
    ("StandingBook",     "台账管理",       103),
    ("TableTool",        "自建表维护工具", 104),
    ("ProcessTool",      "流程维护",       105),
    ("DocumentTool",     "内容管理维护",   106),
    ("CloudDocument",    "O2 在线协作",    107),
    ("OnlyOffice",       "OnlyOffice 协作", 108),
    ("WpsOffice",        "WPS 协作",       109),
    ("OfficeOnline",     "Office 在线协作", 110),
    ("WebServerResource", "WebServer 资源", 111),
]

# ---- C 层：pcClient 为空、需要补 true 的门户 ----
PORTAL_FIX = ["办公用品管理", "总经理信箱", "自定义APP通讯录页"]

# ---- B 层：不登记进开始菜单的流程应用（字典/基础数据，不是业务入口）----
SKIP_PROCESS = {"公共数据（全局）"}


def _dl(path, token):
    st, j = get(path, token)
    return extract_list(j)


def check(token):
    print("=" * 62)
    print("A 层 · WAR 组件（CPT_COMPONENT）")
    print("=" * 62)
    comps = _dl(f"{COMP}/list/all", token)
    names = {c.get("name") for c in comps}
    customs = [c for c in comps if c.get("type") == "custom"]
    print(f"  component/list/all 共 {len(comps)} 条，其中 custom {len(customs)} 条")
    for ns, title, order in COMPONENTS:
        mark = "OK  " if ns in names else "缺失"
        print(f"    [{mark}] {title:16s} {ns}")

    print()
    print("=" * 62)
    print("B 层 · 流程应用（applications.json @url 深链）")
    print("=" * 62)
    apps = [a for a in _dl("/x_processplatform_assemble_surface/jaxrs/application/list", token)
            if isinstance(a, dict) and a.get("name") not in SKIP_PROCESS]
    try:
        r = subprocess.run(["docker", "cp",
                            f"{CONTAINER}:{CONTAINER_APPS_JSON}", "C:/temp/_apps_chk.json"],
                           capture_output=True, text=True)
        with open(r"C:\temp\_apps_chk.json", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = []
    print(f"  待登记流程应用 {len(apps)} 个；applications.json 现有 {len(cur)} 条")
    titles = {x.get("title") for x in cur}
    for a in apps:
        mark = "OK  " if a.get("name") in titles else "缺失"
        print(f"    [{mark}] {a.get('name')}")

    print()
    print("=" * 62)
    print("C 层 · 门户（pcClient）")
    print("=" * 62)
    for p in _dl(PORTAL_LIST, token):
        if p.get("name") in PORTAL_FIX:
            pc = p.get("pcClient")
            mark = "OK  " if pc is True else "需修"
            print(f"    [{mark}] {p.get('name'):16s} pcClient={pc}")


def apply_all(token):
    # ---- A 层 ----
    print("[A] 登记 WAR 组件 ...")
    names = {c.get("name") for c in _dl(f"{COMP}/list/all", token)}
    for ns, title, order in COMPONENTS:
        if ns in names:
            print(f"    跳过（已存在）: {title}")
            continue
        st, r = post(COMP, {"name": ns, "path": ns, "title": title,
                            "iconPath": "appicon.png", "orderNumber": order,
                            "visible": True}, token)
        ok = st == 200 and isinstance(r, dict) and r.get("type") == "success"
        print(f"    {'已登记' if ok else '失败  '}: {title:16s} {'' if ok else str(r)[:120]}")

    # ---- B 层 ----
    print("[B] 写 applications.json ...")
    apps = [a for a in _dl("/x_processplatform_assemble_surface/jaxrs/application/list", token)
            if isinstance(a, dict) and a.get("name") not in SKIP_PROCESS and a.get("id")]
    entries = []
    for a in apps:
        aid = a["id"]
        option = json.dumps({"id": aid, "appId": "process.Application" + aid}, ensure_ascii=False)
        entries.append({
            "title": a.get("name"),
            "path": "@url:" + f"{HOST}/x_desktop/index.html?app=process.Application"
                              f"&option={urllib.parse.quote(option)}",
            "iconPath": f"{HOST}/x_component_process_ApplicationExplorer/$Main/default/icon/application.png",
            "allowList": [],
            "denyList": [],
        })
    content = json.dumps(entries, ensure_ascii=False, indent=2)
    with open(PATCH_APPS_JSON, "w", encoding="utf-8") as f:
        f.write(content)
    r = subprocess.run(["docker", "cp", PATCH_APPS_JSON,
                        f"{CONTAINER}:{CONTAINER_APPS_JSON}"], capture_output=True, text=True)
    print(f"    {'已写入' if r.returncode == 0 else '写入失败'} 容器：{len(entries)} 条"
          f"{'' if r.returncode == 0 else ' ' + r.stderr[:200]}")

    # ---- C 层 ----
    print("[C] 修正门户 pcClient ...")
    byname = {p.get("name"): p for p in _dl(PORTAL_DESIGNER_LIST, token)}
    for nm in PORTAL_FIX:
        p = byname.get(nm)
        if not p:
            print(f"    {nm:16s} 未找到，跳过")
            continue
        if p.get("pcClient") is True:
            print(f"    {nm:16s} 已是 True，跳过")
            continue
        body = dict(p)
        body["pcClient"] = True
        body.pop("id", None)
        st, r = put(f"{PORTAL_DESIGNER}/{p.get('id')}", body, token)
        print(f"    {nm:16s} -> True  status={st}")

    print("\n完成。前端需强制刷新（Ctrl+F5）后打开「开始」菜单查看。")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    tok = login()
    {"check": check, "apply": apply_all}.get(cmd, lambda t: print("use check|apply"))(tok)
