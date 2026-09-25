#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Delete all HR work instances then retry HR app deletion."""
import sys, urllib.request, urllib.error
sys.path.insert(0, "D:/O2OA/tools")
from o2 import login, BASE

HR_APP = "a6006000-hr-app-0000000000000000001"

def _delete(path, tok, timeout=300):
    req = urllib.request.Request(BASE + path, headers={"x-token": tok}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")

def main():
    tok = login()
    with open("D:/O2OA/tools/hr_works.txt", encoding="utf-8") as f:
        ids = [l.strip() for l in f if l.strip()]
    print(f"deleting {len(ids)} HR work instances")
    ok = 0
    for wid in ids:
        st, body = _delete(f"/x_processplatform_assemble_surface/jaxrs/work/{wid}", tok)
        if st in (200, 201, 204):
            ok += 1
        else:
            print(f"  WORK FAIL {wid} -> {st} {body[:120]}")
    print(f"works deleted ok={ok}/{len(ids)}")
    st, body = _delete(f"/x_processplatform_assemble_designer/jaxrs/application/{HR_APP}/false", tok)
    print(f"app delete retry -> {st} {body[:200]}")

if __name__ == "__main__":
    main()
