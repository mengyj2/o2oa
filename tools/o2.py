#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal O2OA REST helper (stdlib only)."""
import json, urllib.request, urllib.error, sys

BASE = "http://127.0.0.1:9090"
USER = "xadmin"
PWD  = "o2oaadmin2026"

def _req(method, path, token=None, body=None, headers=None, raw=False, timeout=60):
    url = BASE + path
    data = None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["x-token"] = token
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            if raw:
                return r.status, content
            txt = content.decode("utf-8", "replace")
            try:
                return r.status, json.loads(txt)
            except Exception:
                return r.status, txt
    except urllib.error.HTTPError as e:
        content = e.read()
        txt = content.decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt
    except Exception as e:
        return -1, str(e)

def login():
    st, j = _req("POST", "/x_organization_assemble_authentication/jaxrs/authentication",
                 body={"credential": USER, "password": PWD})
    if st == 200 and isinstance(j, dict):
        tok = (j.get("data") or {}).get("token")
        return tok
    raise RuntimeError(f"login failed: {st} {j}")

def get(path, token=None):
    return _req("GET", path, token=token)

def post(path, body=None, token=None):
    return _req("POST", path, token=token, body=body)

def put(path, body=None, token=None):
    return _req("PUT", path, token=token, body=body)

def getlist(path, token):
    """return the list from O2OA response variants"""
    st, j = _req("GET", path, token=token)
    return extract_list(j)

def extract_list(j):
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        d = j.get("data")
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, list):
                    return v
    return []

if __name__ == "__main__":
    tok = login()
    print("token ok, len", len(tok))
    for label, path in [
        ("apps", "/x_processplatform_assemble_designer/jaxrs/application/list"),
        ("portals", "/x_portal_assemble_designer/jaxrs/portal/list"),
        ("queries", "/x_query_assemble_designer/jaxrs/query/list"),
        ("cms", "/x_cms_assemble_control/jaxrs/category/list/0"),
    ]:
        lst = getlist(path, tok)
        print(f"\n=== {label} ({len(lst)}) ===")
        for it in lst:
            if isinstance(it, dict):
                print("  ", it.get("name"), "|", it.get("id"), "| alias=", it.get("alias"))
