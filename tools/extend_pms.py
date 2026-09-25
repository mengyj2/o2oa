#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extend_pms.py —— 在克隆基座上扩展出 10 模块 PMS

输入：o2_clone_app.py 产出的 xapp（已重映射 id + 全局改名）
产出：10 页签门户 + 模块台账视图 + 4 条生命周期流程 的最终 xapp

关键约束（实测）：
  · 门户页/表单 data 是"双层转义 designer JSON"，绝不可 json 往返
    （与原串不等长，会破坏结构）——全部改动走**文本域**。
  · data 内转义层级：结构引号 = \" ；字符串值内引号 = \\\"（3 反斜杠）。
  · 页签导航 = this.page.toPage("页面名")，按**页面名**跳转。
  · 流程/视图对象是普通 JSON，可直接深拷贝改 id。
"""
import argparse
import copy
import json
import os
import re
import sys
import uuid

Q = chr(92)                 # 反斜杠
SQ = Q + '"'                # data 内结构引号        -> \"
VQ = Q * 3 + '"'            # data 内字符串值内引号  -> \\\"


def esc_obj_to_d(obj):
    """python对象 -> 内层JSON文本 -> 转义进 data 字符串"""
    inner = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return inner.replace(Q, Q + Q).replace('"', SQ)


def esc_html_to_d(s):
    """html 片段 -> 转义进 data 字符串（值内引号升到 3 反斜杠层）"""
    s = s.replace(Q, Q + Q + Q).replace('"', VQ)
    return s


MODULES = ["项目管理门户", "项目全景", "项目启动", "进度管控", "成本管理",
           "质量管理", "风险管理", "相关方管理", "合同管理", "项目收尾"]

# 模块 -> (基础视图名, scope, 绑定流程名或 None)
MODULE_VIEW = {
    "项目管理门户": ("门户-待办项目", "work", None),
    "项目全景":     ("全景-全部项目", "all", None),
    "项目启动":     ("启动-立项在办", "work", "立项管理"),
    "进度管控":     ("进度-在办", "work", "进度汇报流程"),
    "成本管理":     ("成本-台账", "all", None),
    "质量管理":     ("质量-在办", "work", "质量检查流程"),
    "风险管理":     ("风险-在办", "work", "风险上报流程"),
    "相关方管理":   ("相关方-台账", "all", None),
    "合同管理":     ("合同-台账", "all", None),
    "项目收尾":     ("收尾-已完成", "workCompleted", "项目验收流程"),
}

# 额外补的"已完成"视图
EXTRA_VIEWS = [
    ("进度-已完成", "workCompleted", "进度汇报流程"),
    ("质量-已完成", "workCompleted", "质量检查流程"),
    ("风险-已完成", "workCompleted", "风险上报流程"),
    ("收尾-在办", "work", "项目验收流程"),
]

NEW_PROCESSES = ["进度汇报流程", "风险上报流程", "质量检查流程", "项目验收流程"]

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ------------------------------------------------------------------ tabs
def find_tab_module_span(d, mid):
    """返回 (起始,结束) 覆盖 moduleList 里 mid 条目的 \"key\":{...}（含键名）"""
    start_marker = SQ + mid + SQ + ":" + "{" + SQ + "id" + SQ + ":" + SQ + mid + SQ
    i = d.find(start_marker)
    if i < 0:
        return None
    end_marker = SQ + "recoveryStyles" + SQ + ":null}"
    j = d.find(end_marker, i)
    if j < 0:
        return None
    return i, j + len(end_marker)


def retext_module(d, mid, old, new, count_only=False):
    """按模块 id 锚定，替换该模块内的 text / toPage 目标 / html 文本"""
    n = 0
    span = find_tab_module_span(d, mid)
    if span:
        seg = d[span[0]:span[1]]
        for pat, rep in ((SQ + old + SQ, SQ + new + SQ),
                         ("toPage(" + VQ + old + VQ + ")", "toPage(" + VQ + new + VQ + ")")):
            c = seg.count(pat)
            n += c
            seg = seg.replace(pat, rep)
        d = d[:span[0]] + seg + d[span[1]:]
    i = d.find("<div id=" + VQ + mid + VQ)
    if i >= 0:
        j = d.find("</div>", i)
        seg = d[i:j]
        pat, rep = ">" + old + "</div>", ">" + new + "</div>"
        c = seg.count(pat)
        n += c
        seg = seg.replace(pat, rep)
        d = d[:i] + seg + d[j:]
    if count_only:
        return d, n
    return d, n


def build_tab_module(mid, text, page_id, active=False):
    styles = {"float": "right", "height": "80px", "line-height": "80px",
              "padding": "0px 20px", "font-size": "18px", "cursor": "pointer",
              "text-align": "center"}
    if active:
        styles["background-color"] = "#4381cb"
    ev = {}
    for k in ["dblclick", "keydown", "keypress", "keyup", "mousedown",
              "mousemove", "mouseout", "mouseover", "mouseup", "focus", "blur"]:
        ev[k] = {"code": "", "html": ""}
    code = 'this.page.toPage(\\"%s\\")' % text
    ev["click"] = {"code": code, "html": code}
    return {"id": mid, "name": "", "type": "Label", "description": "",
            "valueType": "text", "text": text,
            "script": {"code": "", "html": ""}, "events": ev,
            "properties": {}, "class": "", "styles": styles, "container": "",
            "isSaved": True, "pid": "PC" + page_id + mid,
            "moduleName": "label", "recoveryStyles": None}


def retab_page(d, page_id, page_name):
    """把页面上 3 个旧页签改成前 3 个模块，注入其余 7 个，并修面包屑"""
    n0 = len(d)
    # 1) 旧 3 页签 + 首页按钮（id 锚定，避免误伤面包屑/左树）
    for mid, old, new in [("label_2", "项目档案", MODULES[0]),
                          ("label_3", "执行管理", MODULES[1]),
                          ("label_4", "立项管理", MODULES[2]),
                          ("label_7", "首页", MODULES[0])]:
        d, n = retext_module(d, mid, old, new)
        if n == 0:
            print(f"  ⚠ {mid} 未命中: {old}→{new}")

    # 2) 注入其余 7 个页签模块（挂在 label_4 条目之后）
    mods = []
    for idx, name in enumerate(MODULES[3:], start=1):
        mods.append(build_tab_module("label_4_%d" % idx, name, page_id))
    inject = "".join("," + SQ + m["id"] + SQ + ":" + esc_obj_to_d(m) for m in mods)
    span = find_tab_module_span(d, "label_4")
    if not span:
        raise RuntimeError("找不到 label_4 模块条目")
    d = d[:span[1]] + inject + d[span[1]:]

    # 3) html 里补 7 个页签 div（挂在 label_4 的 div 之后）
    html_marker = ("<div id=" + VQ + "label_4" + VQ + " mwftype=" + VQ + "label" + VQ)
    i = d.find(html_marker)
    if i < 0:
        print("  ⚠ 未找到 html 页签锚点，跳过 html 注入")
    else:
        j = d.find("</div>", i) + len("</div>")
        extra = "".join('<div id=' + VQ + m["id"] + VQ + ' mwftype=' + VQ + 'label' + VQ +
                        ' style=' + VQ + VQ + '>' + m["text"] + '</div>' for m in mods)
        d = d[:j] + extra + d[j:]

    # 4) 面包屑残留文案 → 本页模块名
    STALE = ["立项管理", "执行管理", "项目档案", "项目档案中心", "首页 >", "> "]
    try:
        real = json.loads(json.loads('"' + d + '"'))
        ml = real["json"]["moduleList"]
        for k, v in ml.items():
            if v.get("type") == "Label" and v.get("text") in STALE:
                d, _ = retext_module(d, k, v["text"], page_name)
    except Exception as e:
        print("  ⚠ 面包屑处理跳过:", str(e)[:60])

    print(f"  页签注入完成（data {n0} → {len(d)} 字符）")
    return d


# ------------------------------------------------------------------ views
def make_view(base, new_id, name, scope, process=None):
    v = copy.deepcopy(base)
    v["id"] = new_id
    v["name"] = name
    v["alias"] = name
    d = json.loads(v["data"])
    d.setdefault("where", {})["scope"] = scope
    if process:
        d["where"]["processList"] = [{"name": process, "id": PROC_ID[process]}]
    else:
        d["where"]["processList"] = []
    v["data"] = json.dumps(d, ensure_ascii=False)
    return v


PROC_ID = {}


# ------------------------------------------------------------------ process
def clone_process(base, new_id, name, act_map=None):
    p = copy.deepcopy(base)
    subtree = json.dumps(p, ensure_ascii=False)
    ids = set(UUID_RE.findall(subtree))
    m = {old: str(uuid.uuid4()) for old in ids}
    for old, new in m.items():
        subtree = subtree.replace(old, new)
    p = json.loads(subtree)
    p["id"] = new_id
    p["name"] = name
    p["alias"] = name
    p["edition"] = new_id
    p["editionName"] = name + "_V1.0"
    if act_map:
        for act in p.get("manualList") or []:
            if act.get("name") in act_map:
                act["name"] = act_map[act["name"]]
                act["alias"] = act["name"]
    return p


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    obj = json.load(open(args.src, encoding="utf-8"))
    app = obj["processPlatformList"][0]
    portal = obj["portalList"][0]
    query = obj["queryList"][0]
    pages = portal["pageList"]

    print("== 基座 ==")
    print("  应用:", app["name"], "| 门户:", portal["name"],
          "| 页:", [p["name"] for p in pages], "| 视图:", len(query["viewList"]))

    # ---------- 1. 新增 4 条生命周期流程 ----------
    base_proc = [p for p in app["processList"] if p["name"] == "执行管理"][0]
    ACT_MAP = {
        "进度汇报流程": {"任务登记": "进度填报", "任务分派": "进度汇总", "PMO意见": "PMO审核",
                    "部门执行": "部门填报", "分管领导审示": "分管领导审示",
                    "领导审示": "领导审示", "执行归档": "进度归档"},
        "风险上报流程": {"任务登记": "风险登记", "任务分派": "风险分派", "PMO意见": "PMO评估",
                    "部门执行": "风险处置", "执行归档": "风险关闭"},
        "质量检查流程": {"任务登记": "质量登记", "任务分派": "检查分派", "PMO意见": "质量评审",
                    "部门执行": "问题整改", "执行归档": "质量归档"},
        "项目验收流程": {"任务登记": "验收申请", "任务分派": "资料汇总", "PMO意见": "PMO初审",
                    "部门执行": "验收整改", "执行归档": "验收归档"},
    }
    for name in NEW_PROCESSES:
        nid = str(uuid.uuid4())
        PROC_ID[name] = nid
        app["processList"].append(
            clone_process(base_proc, nid, name, ACT_MAP.get(name)))
    for p in app["processList"]:          # 既有流程也登记，供视图过滤
        PROC_ID.setdefault(p["name"], p["id"])
    print("  新增流程:", [p["name"] for p in app["processList"]])

    # ---------- 2. 新增模块视图 ----------
    base_done = [v for v in query["viewList"] if v["name"] == "立项已完成_按类型"][0]
    base_doing = [v for v in query["viewList"] if v["name"] == "立项在办项目按名称"][0]
    new_views = []
    for name, scope, proc in list(MODULE_VIEW.values()) + EXTRA_VIEWS:
        if any(v["name"] == name for v in query["viewList"]):
            continue
        base = base_doing if scope in ("work",) else base_done
        new_views.append(make_view(base, str(uuid.uuid4()), name, scope, proc))
    query["viewList"].extend(new_views)
    print("  新增视图:", [v["name"] for v in new_views])

    # ---------- 3. 页签改造 + 页面克隆 ----------
    # 页面名 -> 模块名 映射：发文管理→项目管理门户, 档案管理→项目全景, 收文管理→项目启动
    RENAME_PAGE = {"立项管理": "项目管理门户", "项目档案": "项目全景", "执行管理": "项目启动"}
    for pg in pages:
        old = pg["name"]
        if old in RENAME_PAGE:
            pg["name"] = RENAME_PAGE[old]
            pg["alias"] = pg["name"]
    print("  页面改名:", RENAME_PAGE)

    # 先给 3 个源页注入 10 页签
    for pg in pages:
        pid = pg["id"]
        print("  · 页签注入:", pg["name"], pid)
        pg["data"] = retab_page(pg["data"], pid, pg["name"])

    # 用"项目全景"页作母版克隆其余 7 个模块页
    tpl = [p for p in pages if p["name"] == "项目全景"][0]
    tpl_view_id = [v["id"] for v in query["viewList"]
                   if v["name"] == "立项已完成_按类型"][0]
    existing = {p["name"] for p in pages}
    for module in MODULES:
        if module in existing:
            continue
        new_id = str(uuid.uuid4())
        d = tpl["data"].replace(tpl["id"], new_id)
        # 无横线形式（css class 用）
        d = d.replace(tpl["id"].replace("-", ""), new_id.replace("-", ""))
        # 视图重绑（精确串替换：模板页绑定 立项已完成_按类型）
        vname, scope, proc = MODULE_VIEW[module]
        vid = [v["id"] for v in query["viewList"] if v["name"] == vname][0]
        qid = query["id"]
        old_block = (SQ + "queryView" + SQ + ":" + "{" + SQ + "name" + SQ + ":" + SQ +
                     "立项已完成_按类型" + SQ + "," + SQ + "id" + SQ + ":" + SQ + tpl_view_id +
                     SQ + "," + SQ + "appName" + SQ + ":" + SQ + "项目管理" + SQ + "," +
                     SQ + "application" + SQ + ":" + SQ + qid + SQ + "}")
        new_block = (SQ + "queryView" + SQ + ":" + "{" + SQ + "name" + SQ + ":" + SQ +
                     vname + SQ + "," + SQ + "id" + SQ + ":" + SQ + vid + SQ + "," +
                     SQ + "appName" + SQ + ":" + SQ + "项目管理" + SQ + "," +
                     SQ + "application" + SQ + ":" + SQ + qid + SQ + "}")
        n = d.count(old_block)
        d = d.replace(old_block, new_block)
        if n < 1:
            print("  ⚠ queryView 未命中:", module)
        # 页面内标题（json.name 与面包屑）
        d = d.replace(SQ + "name" + SQ + ":" + SQ + "项目全景" + SQ,
                      SQ + "name" + SQ + ":" + SQ + module + SQ)
        d = d.replace(SQ + "text" + SQ + ":" + SQ + "项目全景" + SQ,
                      SQ + "text" + SQ + ":" + SQ + module + SQ)
        d = d.replace(">项目全景</div>", ">" + module + "</div>")
        np = copy.deepcopy(tpl)
        np["id"] = new_id
        np["name"] = module
        np["alias"] = module
        np["data"] = d
        pages.append(np)
        print("  + 克隆页:", module, new_id)

    # 门户首页指向 项目管理门户
    first = [p for p in pages if p["name"] == "项目管理门户"]
    if first:
        portal["firstPage"] = first[0]["id"]

    print("== 最终 ==")
    print("  页面:", [p["name"] for p in pages])
    print("  流程:", [p["name"] for p in app["processList"]])
    print("  视图:", len(query["viewList"]))
    print("  表单:", [f["name"] for f in app["formList"]])

    if args.dry_run:
        print("[dry-run] 未写出")
        return
    json.dump(obj, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✅ 写出:", args.out)


if __name__ == "__main__":
    main()
