# -*- coding: utf-8 -*-
"""探针：从 designer 接口读取原生实体，输出字段清单，与我们的实现对比。"""
import json, os, sys, urllib.request

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)
from import_xapps import get_token

BASE = "http://localhost:9090"


def get(path, token):
    req = urllib.request.Request(BASE + path)
    req.add_header("x-token", token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def main():
    token = get_token()
    targets = sys.argv[1:]
    for path in targets:
        print("=" * 78)
        print("GET " + path)
        try:
            d = get(path, token)
        except Exception as e:
            print("  [ERR] %s" % e)
            continue
        data = d.get("data")
        if isinstance(data, list):
            print("  list len=%d" % len(data))
            data = data[0] if data else {}
        if isinstance(data, dict):
            for k in sorted(data.keys()):
                v = data[k]
                s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                if len(s) > 160:
                    s = s[:160] + " …(%d)" % len(s)
                print("    %-28s %s" % (k, s))
        else:
            print("  data type=%s" % type(data))


if __name__ == "__main__":
    main()
