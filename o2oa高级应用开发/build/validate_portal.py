# -*- coding: utf-8 -*-
"""validate_portal.py —— 门户页数据与活数据接线校验（P0~P9）。

为什么需要它：
  门户页有两类「不报错、只白屏/只显示兜底」的缺陷，结构校验完全看不见：

  ① 数据格式：O2OA 把门户页**当表单渲染**
     （x_component_portal_Portal/PortalPage.js → JSON.decode → MWF.APPForm），
     写入裸 HTML 会 JSON 解析失败 → this.page 为 null → **整个页面白屏**。
  ② 活数据接线：骨架里 `data-op-chart="N"` 与脚本 SPEC 一旦错位，
     页面不报错，只是静静显示静态兜底。

校验项：
  P0 页面数据必须是 O2OA 门户页 JSON：{json,html,id,isNewPage}，
     json.type=Form，恰好一个 Html 模块且 text 非空   ← 白屏拦截
  P1 页面含 op-todo-body / op-date 挂点
  P2 data-op-chart 的 idx 集合 == SPEC.charts 的 idx 集合
  P3 SPEC 引用的 statement id 在同应用 STATEMENTS 中真实存在
  P4 postLoad 脚本包含必需接口路径（待办/已办/语句执行）
  P5 静态兜底行不得出现「非协会人员」（对照组织 9 人白名单）
  P6 SPEC 的 field/value 必须出现在对应语句的 SELECT 别名中
  P7 CSS 必须全部限域在 #op-root 之下（否则污染整个 O2OA 桌面）
  P8 标记必须包在 <div id="op-root"> 根节点内（P7 的前提）
  P9 postLoad 脚本语法（有 node 时用 `node --check`）

用法： python validate_portal.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)

import o2oa_builder as OB
import o2oa_portal as OP

# 协会真实人员白名单（组织 4 部门 / 9 人）
REAL_PEOPLE = {"孟弋洁", "卢宏萍", "李芳", "时晓明", "杜阳",
               "李静", "奚莎莎", "赵旭东", "罗舒涵"}
REAL_DEPTS = {"综合管理部", "行业研究部", "会员服务部", "国际业务部",
              "中国复合材料工业协会"}

REQ_APIS = [
    "/x_processplatform_assemble_surface/jaxrs/task/list/my/paging/",
    "/x_processplatform_assemble_surface/jaxrs/read/count/my",
    "/x_query_assemble_surface/jaxrs/statement/",
]

# 官方版式里出现过、但协会并不存在的名字（早期静态样张遗留）
KNOWN_FAKE = ["苏娜", "杨苏", "谢军", "赵娜", "常明", "史杰", "张超", "郑洋",
              "李婷", "复合材料部", "检测中心", "信息部", "供应部", "生产部",
              "人力资源部", "采购部", "咨询部", "会展部", "综合办公室"]

SPEC_RE = re.compile(r"var SPEC = (\{.*?\});", re.DOTALL)
CHART_ATTR_RE = re.compile(r'data-op-chart="(\d+)"')
STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)
BARE_BODY_RE = re.compile(r"^\s*(?:body|html|\*)\s*\{", re.M)


def iter_portal_pages(module):
    """产出 (portalName, pageName, data)。data 为 .xapp 里的**线格式**原值。"""
    for p in getattr(module, "PORTALS", []) or []:
        for pg in (p.get("pageList") or []):
            yield p.get("name"), pg.get("name"), pg.get("data") or ""


def select_aliases(module, stmt_id):
    """取语句的 SELECT 输出别名集合（用于校验 spec.field 有效）。"""
    for s in getattr(module, "STATEMENTS", []) or []:
        if s.get("id") != stmt_id:
            continue
        sql = s.get("sql") or ""
        m = re.search(r"\bselect\b(.*?)\bfrom\b", sql, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        out = set()
        for item in m.group(1).split(","):
            it = item.strip()
            ma = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", it, re.IGNORECASE)
            if ma:
                out.add(ma.group(1))
                continue
            mb = re.match(r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)?x?([A-Za-z_][A-Za-z0-9_]*)$", it)
            if mb:
                out.add(mb.group(1))
        return out
    return None


def node_available():
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


HAS_NODE = node_available()


def js_syntax_error(js):
    """用 node --check 校验脚本语法；不可用则返回 None。"""
    if not HAS_NODE or not js.strip():
        return None
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        os.write(fd, js.encode("utf-8"))
        os.close(fd)
        r = subprocess.run(["node", "--check", path],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", timeout=60)
        if r.returncode != 0:
            return (r.stderr or "").strip().split("\n")[0][:160]
        return None
    except Exception as e:
        return str(e)[:120]
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def main():
    errors, warns = [], []
    mods = []
    for name in ("def_project", "def_contract", "def_budget", "def_finance",
                 "def_archive", "def_hr"):
        try:
            mods.append(__import__(name))
        except Exception as e:
            print("[WARN] 无法导入 %s: %s" % (name, e))

    n_pages = n_live = 0
    print("%-22s %-14s %-6s %s" % ("门户页面", "页", "活数据", "校验"))
    print("-" * 78)
    for mod in mods:
        for pname, pgname, data in iter_portal_pages(mod):
            n_pages += 1
            tag = "%s/%s" % (pname, pgname)

            # ---------- P0 数据必须是 O2OA 门户页 JSON（双层：先转义、再 JSON） ----------
            wire = data or ""
            if not wire.strip():
                errors.append("%s P0 页面数据为空" % tag)
                continue
            # ★ P0a 线格式必须是「转义形态」——PortalPage.js 固定
            #    JSON.decode(MWF.decodeJsonString(data))，裸 JSON 会抛
            #    SyntaxError: Unexpected identifier 'json' → 整页白屏。
            if not OB.is_escaped_json(wire):
                errors.append("%s P0a data 不是转义形态（裸 JSON/HTML）→ 门户必白屏；"
                              "应以 %s 开头，实际 %r" % (tag, '{\\"', wire[:20]))
                continue
            # ★ P0b 复刻前端 o2.decodeJsonString 的解码链，能过才保证真渲染
            try:
                s = OB.decode_json_string(wire).strip()
            except Exception as e:
                errors.append("%s P0b decodeJsonString 失败：%s" % (tag, str(e)[:80]))
                continue
            if not s.startswith("{"):
                errors.append("%s P0b 解码后不是 JSON 文本：%r" % (tag, s[:40]))
                continue
            try:
                obj = json.loads(s)
            except Exception as e:
                errors.append("%s P0b 解码后不是合法 JSON：%s" % (tag, str(e)[:80]))
                continue
            if set(obj.keys()) != {"json", "html", "id", "isNewPage"}:
                errors.append("%s P0 顶层键异常：%s" % (tag, sorted(obj.keys())))
            j = obj.get("json") or {}
            if j.get("type") != "Form":
                errors.append("%s P0 json.type 应为 Form，实际 %r"
                              % (tag, j.get("type")))
            html_mods = [m for m in (j.get("moduleList") or {}).values()
                         if isinstance(m, dict) and m.get("type") == "Html"]
            if len(html_mods) != 1:
                errors.append("%s P0 需恰好 1 个 Html 模块，实际 %d 个"
                              % (tag, len(html_mods)))
                continue
            text = html_mods[0].get("text") or ""
            if not text.strip():
                errors.append("%s P0 Html 模块 text 为空 → 门户白屏" % tag)
                continue

            js = ((j.get("events") or {}).get("postLoad") or {}).get("code") or ""
            html = OP.page_data_to_html(s, pgname)

            # ---------- P1 挂点 ----------
            # op-todo-body 仅在 SPEC 配了 todo_page（页面渲染待办卡片）时要求；
            # 视图页 SPEC 为空不含待办区。op-date 挂点要求顶栏存在。
            sm = re.search(r"var SPEC = (\{.*?\});", js)
            spec_has_todo = bool(sm and "todo_page" in (sm.group(1) or ""))
            if spec_has_todo and "op-todo-body" not in text:
                errors.append("%s P1 运行时引用 op-todo-body 但页面缺少挂点" % tag)
            if 'id="op-date"' not in text:
                errors.append("%s P1 缺少挂点 id=\"op-date\"" % tag)

            # ---------- P7 CSS 限域 ----------
            cm = STYLE_RE.search(text)
            css = cm.group(1) if cm else ""
            if not css.strip():
                errors.append("%s P7 未找到样式（页面会无版式）" % tag)
            bare = BARE_BODY_RE.findall(css)
            if bare:
                errors.append("%s P7 CSS 存在未限域选择器 %s —— 会污染 O2OA 桌面"
                              % (tag, sorted(set(x.strip() for x in bare))))
            if "#op-root" not in css:
                errors.append("%s P7 CSS 未按 #op-root 限域" % tag)

            # ---------- P8 根节点 ----------
            if '<div id="op-root"' not in text:
                errors.append("%s P8 标记未包在 <div id=\"op-root\"> 内" % tag)

            # ---------- P10 表单 DOM 骨架 ----------
            # Form._getModuleNodes() 靠 html 里的 mwftype 节点找到模块，
            # 再按节点 id 去 moduleList 取定义。骨架缺失 = 模块拿不到 node。
            ah = obj.get("html") or ""
            if 'mwftype="form"' not in ah:
                errors.append("%s P10 html 字段缺少 mwftype=\"form\" 根骨架" % tag)
            for mid, m in (j.get("moduleList") or {}).items():
                if not isinstance(m, dict):
                    continue
                if ('mwftype="%s"' % m.get("moduleName")) not in ah or \
                        ('id="%s"' % mid) not in ah:
                    errors.append("%s P10 html 缺少模块 %s 的节点"
                                  "（mwftype=%s id=%s）"
                                  % (tag, mid, m.get("moduleName"), mid))

            if not js.strip():
                print("%-22s %-14s %-6s (无运行时脚本)" % (pname, pgname, "-"))
                continue

            n_live += 1
            ms = SPEC_RE.search(js)
            spec = json.loads(ms.group(1)) if ms else {}
            specs = spec.get("charts", [])

            # ---------- P2 idx 对齐 ----------
            boxes = set(int(x) for x in CHART_ATTR_RE.findall(text))
            idxs = set(int(c.get("idx")) for c in specs)
            if boxes != idxs:
                errors.append("%s P2 图表 idx 不匹配：容器%s vs SPEC%s"
                              % (tag, sorted(boxes), sorted(idxs)))

            # ---------- P3 / P6 语句与字段 ----------
            ids = set(s0.get("id") for s0 in (getattr(mod, "STATEMENTS", []) or []))
            for c in specs:
                sid = c.get("statement")
                if sid not in ids:
                    errors.append("%s P3 语句不存在：%s" % (tag, sid))
                    continue
                aliases = select_aliases(mod, sid)
                if aliases is not None and c.get("field") not in aliases:
                    errors.append("%s P6 字段 %s 不在语句 %s 的输出别名中 %s"
                                  % (tag, c.get("field"), sid, sorted(aliases)))
                if c.get("value") and aliases is not None and c["value"] not in aliases:
                    errors.append("%s P6 取值字段 %s 不在语句输出中"
                                  % (tag, c.get("value")))

            # ---------- P4 接口路径 ----------
            for api in REQ_APIS:
                if api not in js:
                    errors.append("%s P4 脚本缺少接口 %s" % (tag, api))

            # ---------- P5 真实人员 ----------
            left = [f for f in KNOWN_FAKE if f in text]
            if left:
                errors.append("%s P5 静态兜底含不存在的名称：%s"
                              % (tag, "、".join(left)))

            # ---------- P9 脚本语法 ----------
            se = js_syntax_error(js)
            if se:
                errors.append("%s P9 运行时脚本语法错误：%s" % (tag, se))

            print("%-22s %-14s %-6s OK (图 %d)" % (pname, pgname, "有", len(specs)))

    print("-" * 78)
    print("门户页 %d 个（其中 %d 个已接活数据）" % (n_pages, n_live))
    if not HAS_NODE:
        warns.append("未检测到 node，跳过 P9 脚本语法校验")
    for e in errors:
        print("  [ERROR] " + e)
    for w in warns:
        print("  [WARN ] " + w)
    print("错误 %d 个，警告 %d 个" % (len(errors), len(warns)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
