# -*- coding: utf-8 -*-
"""verify_portal_live.py —— 门户页「线上可渲染」端到端验证（R1~R4）。

validate_portal.py 校验的是**构建产物**；本脚本校验的是**线上实况**：
从 O2OA 接口把门户页取回来（复刻 PortalPage.js 的解析链），确认真的能渲染。

  R1 页面接口可访问，返回 data 非空
  R2 JSON.decode 成功（复刻 PortalPage.js：json.data.data → JSON.decode）
  R3 json.type=Form，存在 Html 模块且 text 非空（白屏红线）
  R4 html 字段含 mwctype=form 骨架 + 模块节点（缺则模块拿不到 node）
  R5 门户→首页链路：portal/{id} 的 firstPage 指向的页面存在且可渲染

用法： python verify_portal_live.py
"""

import json
import os
import sys
import urllib.request

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)

import o2oa_portal as OP

BASE = "http://localhost:9090"
SURFACE = "/x_portal_assemble_surface/jaxrs"


def get(path, token):
    req = urllib.request.Request(BASE + path)
    req.add_header("x-token", token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def collect_portals():
    out = []
    for name in ("def_contract", "def_hr"):
        try:
            mod = __import__(name)
        except Exception:
            continue
        for p in getattr(mod, "PORTALS", []) or []:
            out.append(p)
    return out


def main():
    try:
        from import_xapps import get_token
        token = get_token()
    except Exception as e:
        print("[FATAL] 取不到 token：%s" % e)
        return 1

    errors = []
    n = 0
    print("%-16s %-14s %-8s %s" % ("门户", "页面", "R2", "R3/R4"))
    print("-" * 72)
    for portal in collect_portals():
        ptid = portal["id"]
        for pg in (portal.get("pageList") or []):
            n += 1
            pid, pgname = pg["id"], pg["name"]
            tag = "%s/%s" % (portal["name"], pgname)
            try:
                d = get("%s/page/%s/portal/%s" % (SURFACE, pid, ptid), token)
            except Exception as e:
                errors.append("%s R1 接口失败：%s" % (tag, e))
                continue
            data = (d.get("data") or {})
            raw = data.get("data")
            if not raw:
                errors.append("%s R1 页面数据为空" % tag)
                continue

            # R2 完整复刻 PortalPage.js 的解码链：
            #   page = JSON.decode(MWF.decodeJsonString(json.data.data))
            # 库内 data 是「转义形态」，必须先 decodeJsonString 再 JSON.decode。
            try:
                import o2oa_builder as OB
                if not OB.is_escaped_json(raw):
                    errors.append("%s R2 线上 data 不是转义形态（前端会白屏）：%r"
                                  % (tag, raw[:30]))
                    continue
                page = json.loads(OB.decode_json_string(raw))
            except Exception as e:
                errors.append("%s R2 解码失败（门户会白屏）：%s" % (tag, e))
                continue

            # R3 表单 + Html 模块
            j = page.get("json") or {}
            if j.get("type") != "Form":
                errors.append("%s R3 json.type=%r" % (tag, j.get("type")))
            mods = [m for m in (j.get("moduleList") or {}).values()
                    if isinstance(m, dict) and m.get("type") == "Html"]
            if len(mods) != 1:
                errors.append("%s R3 Html 模块数=%d" % (tag, len(mods)))
                continue
            text = mods[0].get("text") or ""
            if not text.strip():
                errors.append("%s R3 Html 模块 text 为空 → 白屏" % tag)
                continue

            # R4 表单 DOM 骨架
            ah = page.get("html") or ""
            ok4 = 'mwftype="form"' in ah and ('mwftype="%s"' % mods[0].get("moduleName")) in ah
            if not ok4:
                errors.append("%s R4 html 缺少模块节点骨架" % tag)

            print("%-16s %-14s %-8s %s (text %d, js %d)"
                  % (portal["name"], pgname, "OK",
                     "OK" if ok4 else "FAIL",
                     len(text),
                     len(((j.get("events") or {}).get("postLoad") or {}).get("code") or "")))

        # R5 门户→首页
        try:
            pt = get("%s/portal/%s" % (SURFACE, ptid), token).get("data") or {}
            fp = pt.get("firstPage")
            if not fp:
                errors.append("%s R5 门户无 firstPage" % portal["name"])
            else:
                ok = any(fx["id"] == fp for fx in (portal.get("pageList") or []))
                if not ok:
                    errors.append("%s R5 firstPage=%s 不在页面清单中"
                                  % (portal["name"], fp))
        except Exception as e:
            errors.append("%s R5 门户接口失败：%s" % (portal["name"], e))

    print("-" * 72)
    print("验证页面 %d 个" % n)
    for e in errors:
        print("  [ERROR] " + e)
    print("错误 %d 个" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
