# -*- coding: utf-8 -*-
"""preview_portal.py —— 导出门户页为可离线打开的 HTML 预览。

为什么要「快照垫片」：
  门户页的活数据靠浏览器同源 fetch O2OA 接口。把 HTML 单独拷出来打开时
  拿不到会话，脚本会静默退回静态兜底 —— 看到的不是真实效果。
  这里在生成预览时**先按真实接口抓一遍数据**，把响应内联成 fetch 垫片，
  于是离线打开看到的与 O2OA 里完全一致（数据是抓取时刻的真实快照）。

输出： deliverables/_portal/
        index.html              门户总览（分页切换）
        <app>_<page>.html       各门户页
"""

import json
import os
import re
import sys
import urllib.request

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)

import o2oa_builder as OB
import o2oa_portal as OP

ROOT = os.path.dirname(BUILD)
OUT = os.path.join(ROOT, "deliverables", "_portal")
BASE = "http://localhost:9090"

SPEC_RE = re.compile(r"var SPEC = (\{.*?\});", re.DOTALL)


# ---------------------------------------------------------------- 数据快照
def snapshot(token, specs):
    """按 SPEC 里用到的接口抓一份真实数据，返回 {url片段: 响应对象}。"""
    snap = {}

    def get(path):
        req = urllib.request.Request(BASE + path)
        req.add_header("x-token", token)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            return {"type": "error", "message": str(e)}

    def post(path):
        req = urllib.request.Request(BASE + path, data=b"{}", method="POST")
        req.add_header("x-token", token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            return {"type": "error", "message": str(e)}

    n = max([sp.get("todo_page", 8) for sp in specs] + [8])
    key = "/x_processplatform_assemble_surface/jaxrs/task/list/my/paging/"
    snap[key + "1/size/" + str(n)] = get(key + "1/size/" + str(n))
    k2 = "/x_processplatform_assemble_surface/jaxrs/read/count/my"
    snap[k2] = get(k2)

    sids = set()
    for sp in specs:
        for c in (sp.get("charts") or []):
            if c.get("statement"):
                sids.add(c["statement"])
    for sid in sorted(sids):
        sk = "/x_query_assemble_surface/jaxrs/statement/%s/execute/" % sid
        snap[sk + "page/1/size/500"] = post(sk + "page/1/size/500")
    return snap


def shim(snap):
    """覆盖 fetch 的垫片：命中快照直接返回，未命中交给真 fetch。"""
    return (
        "<script>\n(function(){\n"
        "  var SNAP = " + json.dumps(snap, ensure_ascii=False) + ";\n"
        "  var orig = window.fetch;\n"
        "  window.fetch = function(url, opts){\n"
        "    var u = String(url);\n"
        "    for (var k in SNAP){\n"
        "      if (u.indexOf(k) >= 0){\n"
        "        return Promise.resolve({ json: function(){\n"
        "          return Promise.resolve(SNAP[k]); } });\n"
        "      }\n"
        "    }\n"
        "    return orig ? orig.apply(this, arguments)\n"
        "                : Promise.reject(new Error('offline'));\n"
        "  };\n"
        "})();\n</script>\n"
    )


BANNER = (
    '<div style="position:fixed;left:0;right:0;bottom:0;z-index:99999;'
    'background:#1a5fa8;color:#fff;font:12px/26px \'Microsoft YaHei\',sans-serif;'
    'text-align:center;letter-spacing:.5px">'
    '\u79bb\u7ebf\u9884\u89c8\u5feb\u7167\u00b7\u6570\u636e\u53d6\u81ea\u672c\u673a O2OA '
    '(localhost:9090)\u00b7\u4ec5\u4f9b\u7248\u5f0f\u6838\u5bf9'
    '</div>'
)


def inject(html, snap):
    """把垫片插到门户脚本之前（垫片必须先定义 fetch）。"""
    if "<script>" in html:
        i = html.index("<script>")
        return html[:i] + shim(snap) + html[i:]
    return html.replace("</body>", shim(snap) + "</body>")


def collect():
    """收集所有门户页：(appLabel, portalName, pageName, html)。"""
    items = []
    for modname, label in (("def_contract", "\u5408\u540c\u7ba1\u7406"),
                           ("def_hr", "\u4eba\u529b\u8d44\u6e90\u7ba1\u7406")):
        try:
            mod = __import__(modname)
        except Exception as e:
            print("[WARN] 导入 %s 失败：%s" % (modname, e))
            continue
        for p in getattr(mod, "PORTALS", []) or []:
            for pg in (p.get("pageList") or []):
                # page.data 是 O2OA 门户页数据（表单定义 JSON），
                # 预览需要还原成独立 HTML。
                items.append((label, p.get("name"), pg.get("name"),
                              OP.page_data_to_html(
                                  OB.decode_json_string(pg.get("data") or ""),
                                  pg.get("name"))))
    return items


def main():
    os.makedirs(OUT, exist_ok=True)
    try:
        from import_xapps import get_token
        token = get_token()
        print("[token] 长度 %d" % len(token))
    except Exception as e:
        token = ""
        print("[WARN] 取不到 token，快照将为空：%s" % e)

    items = collect()
    if not items:
        print("[FATAL] 未收集到任何门户页")
        return 1

    files = []
    for label, pname, pgname, html in items:
        ms = SPEC_RE.search(html)
        spec = json.loads(ms.group(1)) if ms else {}
        snap = snapshot(token, [spec]) if token else {}
        out = inject(html, snap).replace("</body>", BANNER + "</body>")
        fn = "%s_%s.html" % (label, pgname)
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write(out)
        files.append((label, pname, pgname, fn, len(out)))
        print("  OK  %-12s %-16s %s" % (label, pgname, fn))

    # 总览页
    tabs, panes = [], []
    for i, (label, pname, pgname, fn, _n) in enumerate(files):
        on = " on" if i == 0 else ""
        tabs.append('<button class="tab%s" data-i="%d">%s\u00b7%s</button>'
                    % (on, i, label, pgname))
        panes.append('<iframe class="pane%s" data-i="%d" src="%s"></iframe>'
                     % (on, i, fn))
    index = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>'
        '<title>O2OA \u95e8\u6237\u9884\u89c8</title><style>'
        'html,body{margin:0;height:100%;font-family:"Microsoft YaHei",sans-serif}'
        'body{display:flex;flex-direction:column;background:#eef2f7}'
        '.bar{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;'
        'background:#fff;border-bottom:1px solid #dbe3ec}'
        '.tab{border:1px solid #cbd5e0;background:#fff;border-radius:3px;'
        'padding:5px 12px;font-size:12.5px;color:#2d3748;cursor:pointer}'
        '.tab.on{background:#2b6cb0;border-color:#2b6cb0;color:#fff}'
        '.wrap{flex:1;position:relative}'
        '.pane{position:absolute;inset:0;width:100%;height:100%;border:0;'
        'display:none;background:#f5f7fa}'
        '.pane.on{display:block}'
        '</style></head><body>'
        '<div class="bar">__TABS__</div><div class="wrap">__PANES__</div>'
        '<script>var ts=document.querySelectorAll(".tab"),'
        'ps=document.querySelectorAll(".pane");'
        'for(var i=0;i<ts.length;i++){(function(i){ts[i].onclick=function(){'
        'for(var j=0;j<ts.length;j++){ts[j].className="tab";ps[j].className="pane";}'
        'ts[i].className="tab on";ps[i].className="pane on";};})(i);}</script>'
        '</body></html>'
    ).replace("__TABS__", "".join(tabs)).replace("__PANES__", "".join(panes))
    idx = os.path.join(OUT, "index.html")
    with open(idx, "w", encoding="utf-8") as f:
        f.write(index)

    total = sum(x[4] for x in files)
    print("\n共 %d 页，合计 %.1f KB" % (len(files), total / 1024.0))
    print("总览 ->", idx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
