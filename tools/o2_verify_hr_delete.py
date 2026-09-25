#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify HR module fully removed and other modules intact."""
import sys
sys.path.insert(0, "D:/O2OA/tools")
from o2 import login, get, _req

def getlist(path, tok):
    st, j = _req("GET", path, token=tok)
    if isinstance(j, dict):
        d = j.get("data")
        if isinstance(d, list): return d
        if isinstance(d, dict):
            for v in d.values():
                if isinstance(v, list): return v
    return []

def names(items):
    return set(it.get("name") or it.get("xname") or "" for it in items)

tok = login()
print("login OK")

apps = getlist("/x_processplatform_assemble_designer/jaxrs/application/list", tok)
app_names = names(apps)
print("apps count:", len(apps))
print("HR app gone:", not any("人力资源" in (x.get('name') or '') or "a6006000-hr-app" in (x.get('id') or '') for x in apps) )
print("  keepers present:", all(k in app_names for k in ["档案管理应用","财务管理应用","预算管理应用","公共数据（全局）"]))

portals = getlist("/x_portal_assemble_designer/jaxrs/portal/list", tok)
print("portals count:", len(portals))
print("HR portal gone:", not any("人力" in (p.get('name') or '') for p in portals))

# tables via designer paging
st, j = _req("POST", "/x_query_assemble_designer/jaxrs/table/list/paging/1/size/300", token=tok, body={})
tables = (j.get("data") or {}).get("data") or []
print("tables count:", len(tables))
print("HR tables gone:", not any((t.get('id') or '').startswith('t6006') for t in tables))
print("  keepers present:", all(any((t.get('id') or '').startswith(p) for t in tables) for p in ['t5005','t4004','t3003']))

# in-container applications.json over HTTP
st, txt = _req("GET", "/o2_core/o2/xDesktop/$Layout/applications.json", token=tok)
import json
try:
    arr = json.loads(txt) if isinstance(txt, str) else txt
    print("container menu entries:", len(arr), "| HR in menu:", any('a6006000-hr-app' in (x.get('path') or '') for x in arr))
except Exception as e:
    print("menu fetch status", st, "parse err", e)

# admin login sanity
print("xadmin login token len:", len(tok))
