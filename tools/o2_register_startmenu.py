#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把「导入但不出现在开始菜单」的应用注册成 CPT_COMPONENT 记录，
使它们在 O2OA 桌面「开始」菜单里像系统应用一样可直接点击使用。

原理（见 o2_core/o2/xDesktop/Layout.js 的 MWF.xDesktop.Layout.Top.loadMenu）：
    开始菜单 = applications.json(空) + GET /x_component_assemble_control/jaxrs/component/list/all
                                              + GET /x_portal_assemble_surface/jaxrs/portal/list
    - component/list/all 读的是数据库 CPT_COMPONENT 表（ActionListAll 用 listAll(Component.class)），
      并过滤掉 Components.SYSTEM_NAME_NAMES 里的内置项。
    - ActionCreate 强制 setType("custom")，所以通过 POST /jaxrs/component 建的行一定会出现在菜单里。
    - allowList/denyList 都为空时 => isAllow=true / isDeny=false => 不做权限校验，
      不会出现「您没有权限查看该文档或该文档已被删除」。
    - 点击时调用 openApplication(e, value.path)，path 就是 xDesktop 应用命名空间
      (例如 "TeamWork" => 加载 ../x_component_TeamWork/Main.js)。

用法:
    python o2_register_startmenu.py list        # 只看当前注册了哪些
    python o2_register_startmenu.py plan        # 只看将要做什么（不改动）
    python o2_register_startmenu.py apply       # 执行注册（幂等：已存在则跳过）
    python o2_register_startmenu.py fixportal   # 修正门户 pcClient 为空的问题
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2 import login, get, post, put, extract_list

COMP = "/x_component_assemble_control/jaxrs/component"
PORTAL_LIST = "/x_portal_assemble_surface/jaxrs/portal/list"

# ---------------------------------------------------------------------------
# 需要出现在「开始」菜单里的目标应用
#   name  : 唯一键（O2OA 用 name 做去重，不能和已有 24 个 system 重名）
#   path  : xDesktop 应用命名空间 => 对应 webroot/x_component_<path>/Main.js
#   title : 菜单显示名
#   order : 排序号，从 100 起错开，排在系统应用之后
#   icon  : 相对 webroot/x_component_<path>/$Main/ 的图标
# ---------------------------------------------------------------------------
TARGETS = [
    # ---- 业务 WAR 组件（网页端组件型应用）----
    dict(name="TeamWork",        path="TeamWork",        title="工作管理",       order=101, icon="appicon.png"),
    dict(name="CRM",             path="CRM",             title="客户管理",       order=102, icon="appicon.png"),
    dict(name="StandingBook",    path="StandingBook",    title="台账管理",       order=103, icon="appicon.png"),
    dict(name="TableTool",       path="TableTool",       title="自建表维护工具", order=104, icon="appicon.png"),
    dict(name="ProcessTool",     path="ProcessTool",     title="流程维护",       order=105, icon="appicon.png"),
    dict(name="DocumentTool",    path="DocumentTool",    title="内容管理维护",   order=106, icon="appicon.png"),
    # ---- 在线协作 / 文档类 ----
    dict(name="CloudDocument",   path="CloudDocument",   title="O2 在线协作",    order=107, icon="appicon.png"),
    dict(name="OnlyOffice",      path="OnlyOffice",      title="OnlyOffice 协作", order=108, icon="appicon.png"),
    dict(name="WpsOffice",       path="WpsOffice",       title="WPS 协作",       order=109, icon="appicon.png"),
    dict(name="OfficeOnline",    path="OfficeOnline",    title="Office 在线协作", order=110, icon="appicon.png"),
    dict(name="WebServerResource", path="WebServerResource", title="WebServer 资源", order=111, icon="appicon.png"),
]

# 门户型应用（PTL_PORTAL）中 pcClient 为空(NULL) 的，需要补成 true 才会显示在开始菜单
PORTAL_FIX = ["办公用品管理", "总经理信箱", "自定义APP通讯录页"]


def cmd_list(token):
    st, j = get(f"{COMP}/list/all", token)
    data = extract_list(j)
    print(f"component/list/all 共 {len(data)} 条")
    for it in sorted(data, key=lambda x: (x.get("type") or "", x.get("orderNumber") or 0)):
        if it.get("type") == "custom":
            print(f"  [custom] {it.get('name'):22s} {it.get('path'):24s} {it.get('title')}  visible={it.get('visible')}")


def cmd_plan(token):
    st, j = get(f"{COMP}/list/all", token)
    exist = {it.get("name") for it in extract_list(j)}
    print("计划注册：")
    for t in TARGETS:
        flag = "已存在,跳过" if t["name"] in exist else "将新建"
        print(f"  {flag:10s} {t['title']:14s} path={t['path']}")
    print("\n计划修正门户 pcClient：")
    st, j = get(PORTAL_LIST, token)
    for p in extract_list(j):
        if p.get("name") in PORTAL_FIX:
            print(f"  {p.get('name'):14s} pcClient={p.get('pcClient')} -> True")


def cmd_apply(token):
    st, j = get(f"{COMP}/list/all", token)
    exist = {it.get("name"): it for it in extract_list(j)}
    ok = skip = fail = 0
    for t in TARGETS:
        if t["name"] in exist:
            print(f"  跳过（已存在）: {t['title']}")
            skip += 1
            continue
        body = {
            "name": t["name"],
            "path": t["path"],
            "title": t["title"],
            "iconPath": t["icon"],
            "orderNumber": t["order"],
            "visible": True,
        }
        st, r = post(COMP, body, token)
        if st == 200 and isinstance(r, dict) and r.get("type") == "success":
            print(f"  已注册: {t['title']:14s} -> {t['path']}")
            ok += 1
        else:
            print(f"  失败  : {t['title']:14s} {st} {str(r)[:200]}")
            fail += 1
    print(f"\n结果: 新建 {ok} / 跳过 {skip} / 失败 {fail}")


def cmd_fixportal(token):
    st, j = get(PORTAL_LIST, token)
    lst = extract_list(j)
    for p in lst:
        if p.get("name") in PORTAL_FIX and p.get("pcClient") in (None, False):
            pid = p.get("id")
            st2, r = put(f"/x_portal_assemble_surface/jaxrs/portal/{pid}", {"pcClient": True}, token)
            print(f"  {p.get('name')}: pcClient -> True  status={st2}")
            if st2 != 200:
                print("     !", str(r)[:200])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    tok = login()
    {"list": cmd_list, "plan": cmd_plan, "apply": cmd_apply, "fixportal": cmd_fixportal}.get(
        cmd, lambda t: print("unknown cmd")
    )(tok)
