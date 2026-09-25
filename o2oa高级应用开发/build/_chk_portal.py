# -*- coding: utf-8 -*-
"""检查门户 HTML 页是否真正绑定数据源。"""
import glob
import json
import os
import re

BUILD = os.path.dirname(os.path.abspath(__file__))
PAT = os.path.join(os.path.dirname(BUILD), "deliverables", "_xapp_json", "*.json")

API = re.compile(r"(o2\.api\.[A-Za-z.]+|/jaxrs/[A-Za-z0-9_/\-]{0,80}|statement/[A-Za-z0-9\-]+|"
                 r"table/[A-Za-z0-9\-]+|\.json|fetch\s*\(|XMLHttpRequest)", re.IGNORECASE)


def walk_pages(obj):
    if isinstance(obj, dict):
        for p in (obj.get("portalList") or []):
            for pg in (p.get("pageList") or []):
                yield p.get("name"), pg
        for v in obj.values():
            for x in walk_pages(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in walk_pages(v):
                yield x


def main():
    for fp in sorted(glob.glob(PAT)):
        data = json.load(open(fp, encoding="utf-8"))
        mods = data if isinstance(data, list) else [data]
        for m in mods:
            for pname, pg in walk_pages(m):
                html = pg.get("data") or ""
                hits = []
                for h in API.findall(html):
                    if h not in hits:
                        hits.append(h)
                print("%-28s | %-16s | %-14s | html=%-6d | 绑定=%d"
                      % (os.path.basename(fp), pname, pg.get("name"),
                         len(html), len(hits)))
                for h in hits[:6]:
                    print("        ", h)


if __name__ == "__main__":
    main()
