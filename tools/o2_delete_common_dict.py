#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Delete the empty '公共数据（全局）' placeholder app + its empty data app."""
import sys, urllib.request, urllib.error
sys.path.insert(0, "D:/O2OA/tools")
from o2 import login, BASE

APP = "a0000000-common-dict-app-0000000000001"
DATAAPP = "4aa9251a55de48429467fb570ec6267f"

def _delete(path, tok, timeout=600):
    req = urllib.request.Request(BASE + path, headers={"x-token": tok}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")

def main():
    tok = login()
    st, body = _delete(f"/x_processplatform_assemble_designer/jaxrs/application/{APP}/false", tok)
    print(f"app delete -> {st} {body[:120]}")
    st, body = _delete(f"/x_query_assemble_designer/jaxrs/query/{DATAAPP}", tok)
    print(f"dataapp delete -> {st} {body[:120]}")

if __name__ == "__main__":
    main()
