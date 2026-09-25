#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cascade-delete the HR module (6006) from O2OA. Verified safe order.
HR app has 0 in-flight works (15 completed), so app delete won't be blocked.
Steps: app -> 12 table defs -> data app -> 7 portal pages -> portal -> menu json.
Physical DROP of QRY_DYN_T6006xxx is done separately in bash (deleteTable only drops metadata).
"""
import json, sys, urllib.request, urllib.error
sys.path.insert(0, "D:/O2OA/tools")
from o2 import login, BASE, _req

HR_APP = "a6006000-hr-app-0000000000000000001"
HR_DATAAPP = "a6006001-hr-dataapp-00000000000000001"
HR_PORTAL = "o6006001-hr-portal-00000000000000001"
HR_TABLE_FLAGS = [f"t600600{i}-hr-xxx-table-00000000000{i}" for i in range(1, 13)]
# real flags from inventory:
HR_TABLE_FLAGS = [
 "t6006001-hr-employee-table-000000000001",
 "t6006002-hr-emp-detail-table-0000000001",
 "t6006003-hr-change-table-0000000000001",
 "t6006004-hr-job-table-0000000000000001",
 "t6006005-hr-job-apply-table-00000000001",
 "t6006006-hr-point-table-0000000000001",
 "t6006007-hr-bounty-table-0000000000001",
 "t6006008-hr-attend-table-0000000000001",
 "t6006009-hr-leave-table-000000000000001",
 "t6006010-hr-overtime-table-00000000001",
 "t6006011-hr-travel-table-0000000000001",
 "t6006012-hr-self-table-0000000000000001",
]

def _delete(path, tok, timeout=600):
    req = urllib.request.Request(BASE + path, headers={"x-token": tok}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")

def main():
    tok = login()
    print("== 1) delete HR process app ==")
    st, body = _delete(f"/x_processplatform_assemble_designer/jaxrs/application/{HR_APP}/false", tok)
    print(f"  app delete -> {st} {body[:160]}")

    print("== 2) delete 12 HR table defs ==")
    for t in HR_TABLE_FLAGS:
        st, body = _delete(f"/x_query_assemble_designer/jaxrs/table/{t}", tok)
        print(f"  table {t[:30]:30} -> {st}")

    print("== 3) delete HR data app ==")
    st, body = _delete(f"/x_query_assemble_designer/jaxrs/query/{HR_DATAAPP}", tok)
    print(f"  dataapp delete -> {st} {body[:120]}")

    print("== 4) delete HR portal pages + portal ==")
    st, j = _req("GET", f"/x_portal_assemble_designer/jaxrs/page/list/portal/{HR_PORTAL}", token=tok)
    pages = (j.get("data") or []) if isinstance(j, dict) else []
    print(f"  portal pages found: {len(pages)}")
    for pg in pages:
        pid = pg.get("id")
        st, body = _delete(f"/x_portal_assemble_designer/jaxrs/page/{pid}", tok)
        print(f"  page {pid[:20]:20} -> {st}")
    st, body = _delete(f"/x_portal_assemble_designer/jaxrs/portal/{HR_PORTAL}", tok)
    print(f"  portal delete -> {st} {body[:120]}")

    print("== 5) remove HR from applications.json ==")
    p = "D:/O2OA/patch/web/applications.json"
    with open(p, encoding="utf-8") as f:
        arr = json.load(f)
    before = len(arr)
    arr2 = [x for x in arr if "a6006000-hr-app" not in (x.get("path") or "")]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(arr2, f, ensure_ascii=False, indent=1)
    print(f"  applications.json {before} -> {len(arr2)} (removed HR entry)")

    print("DONE-REST")

if __name__ == "__main__":
    main()
