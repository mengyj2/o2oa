#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inventory + health probe for O2OA (stdlib only). Dumps module lists with createTime."""
import json, sys
sys.path.insert(0, "D:/O2OA/tools")
from o2 import login, get, post, put, _req

def dump(label, path, token, extra=None):
    st, j = _req("GET", path, token=token)
    items = []
    if isinstance(j, dict):
        d = j.get("data")
        if isinstance(d, list):
            items = d
        elif isinstance(d, dict):
            for v in d.values():
                if isinstance(v, list):
                    items = v; break
    elif isinstance(j, list):
        items = j
    print(f"\n===== {label} ({len(items)}) status={st} =====")
    for it in items:
        if not isinstance(it, dict):
            print("  ", it); continue
        name = it.get("name") or it.get("xname") or it.get("alias") or ""
        iid = it.get("id") or it.get("xid") or ""
        ct = it.get("createTime") or it.get("xcreateTime") or it.get("xCreateTime") or ""
        extra_s = ""
        if extra:
            extra_s = " | " + " ".join(f"{k}={it.get(k)}" for k in extra if it.get(k) is not None)
        print(f"  {name!r:50} | id={iid} | ct={ct}{extra_s}")

def main():
    tok = login()
    print("token len", len(tok))
    dump("PP applications", "/x_processplatform_assemble_designer/jaxrs/application/list", tok)
    dump("Portals", "/x_portal_assemble_designer/jaxrs/portal/list", tok, extra=["alias","pcClient"])
    dump("Queries(data apps)", "/x_query_assemble_designer/jaxrs/query/list", tok)
    # tables via designer list
    st, j = _req("POST", "/x_query_assemble_designer/jaxrs/table/list/paging/1/size/200", token=tok, body={})
    tables = (j.get("data") or {}).get("data") if isinstance(j, dict) else None
    print(f"\n===== Tables ({len(tables) if tables else 0}) status={st} =====")
    for t in (tables or []):
        if not isinstance(t, dict): continue
        name = t.get("name") or t.get("xname") or ""
        iid = t.get("id") or t.get("xid") or ""
        ct = t.get("createTime") or t.get("xcreateTime") or ""
        print(f"  {name!r:45} | id={iid} | ct={ct}")
    dump("CMS categories", "/x_cms_assemble_control/jaxrs/category/list/0", tok)
    dump("Components", "/x_component_assemble_control/jaxrs/component/list/all", tok)

if __name__ == "__main__":
    main()
