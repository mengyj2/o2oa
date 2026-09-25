# -*- coding: utf-8 -*-
"""
.xapp 结构校验器
================
对照 O2OA Java 实体字段名，检查生成的 .xapp 是否符合 WrapModule 规范。
任何「多余字段」都不致命（Gson 会忽略），但「缺失关键字段」会导致导入后
功能异常，因此重点检查必填项是否存在。
"""
import json
import os
import sys

DELIV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "deliverables")

# --- 必需字段表（依据 Java 源码中的 _FIELDNAME 常量）---
REQ_MODULE = ["name", "name", "processPlatformList", "queryList",
              "portalList", "cmsList", "serviceModuleList"]

REQ_PP = ["id", "name", "processList", "formList", "applicationDictList"]
REQ_FORM = ["id", "name", "alias", "application", "data", "properties"]
REQ_PROC = ["id", "name", "application", "begin", "manualList", "routeList",
            "endList"]
REQ_MANUAL = ["id", "name", "process", "position", "form", "taskScriptText",
              "taskIdentityList", "allowReroute", "allowGoBack",
              "allowRollback", "properties"]
REQ_ROUTE = ["id", "process", "activity", "activityType", "properties"]
REQ_QUERY = ["id", "name", "viewList", "statList", "tableList",
             "statementList", "importModelList"]
REQ_VIEW = ["id", "name", "query", "type", "columnList"]
REQ_TABLE = ["id", "name", "query", "data", "draftData"]
REQ_STAT = ["id", "name", "query", "viewId", "categoryPath", "valuePath"]
REQ_STMT = ["id", "name", "query", "statement"]
REQ_DICT = ["id", "name", "data"]
REQ_SVC = ["id", "name", "dictList"]

# --- 门户（源码：x_portal_core_entity Portal.java / Page.java / WrapPortal.java）---
REQ_PORTAL = ["id", "name", "alias", "portalCategory", "firstPage",
              "creatorPerson", "lastUpdateTime", "pcClient", "mobileClient",
              "availableIdentityList", "availableUnitList", "controllerList",
              "pageList", "scriptList", "fileList", "widgetList"]
REQ_PAGE = ["id", "name", "alias", "portal", "data", "mobileData", "hasMobile", ]

errors = []
warns = []


def chk(obj, req, label, soft=None):
    soft = soft or []
    for k in req:
        if k not in obj:
            if k in soft:
                warns.append("%s 缺少可选字段 %s" % (label, k))
            else:
                errors.append("%s 缺少必需字段 %s" % (label, k))


def _chk_page_data(data, LG, errors):
    """门户页 data 必须是 O2OA 门户页 JSON，而不是裸 HTML。

    ★ 实证：O2OA 把门户页当表单渲染
      （x_component_portal_Portal/PortalPage.js）：
          page = JSON.decode(MWF.decodeJsonString(json.data.data))
          new MWF.APPForm(formNode, page)
      裸 HTML 过不了 JSON.decode → this.page 为 null → **门户白屏**。
      94 个原生门户页的 xdata 100% 是 JSON，可作对照。
    """
    s = (data or "").strip()
    if not s:
        errors.append("%s data 为空" % LG)
        return
    # ★ data 在 .xapp 里必须是「转义形态」（前端 decodeJsonString 解码），
    #   裸 JSON/HTML 都会导致白屏。先验形态，再解码后验内容。
    import o2oa_builder as OB
    if not OB.is_escaped_json(s):
        errors.append("%s data 不是转义形态（裸 JSON/HTML 会导致门户白屏），"
                      "应以 {\\\" 开头，实际 %r" % (LG, s[:20]))
        return
    try:
        s = OB.decode_json_string(s)
        obj = json.loads(s)
    except Exception as e:
        errors.append("%s data 解码后不是合法 JSON：%s" % (LG, str(e)[:70]))
        return
    if not isinstance(obj, dict) or "json" not in obj:
        errors.append("%s data 缺少 json 段" % LG)
        return
    j = obj.get("json") or {}
    if j.get("type") != "Form":
        errors.append("%s data.json.type 应为 Form，实际 %r" % (LG, j.get("type")))
    mods = [m for m in (j.get("moduleList") or {}).values()
            if isinstance(m, dict) and m.get("type") == "Html"]
    if len(mods) != 1:
        errors.append("%s data 需恰好 1 个 Html 模块，实际 %d 个" % (LG, len(mods)))
        return
    if not (mods[0].get("text") or "").strip():
        errors.append("%s data 的 Html 模块 text 为空 → 门户白屏" % LG)
    ah = obj.get("html") or ""
    if 'mwftype="form"' not in ah:
        errors.append("%s data.html 缺少表单 DOM 骨架（Form 靠它挂模块节点）" % LG)


def check_file(path):
    d = json.load(open(path, encoding="utf-8"))
    name = os.path.basename(path)
    chk(d, ["name", "processPlatformList", "queryList"], "%s<WrapModule>" % name)

    for pp in d.get("processPlatformList", []):
        L = "%s / 流程应用[%s]" % (name, pp.get("name"))
        chk(pp, REQ_PP, L)

        for fm in pp.get("formList", []):
            LF = "%s / 表单[%s]" % (L, fm.get("name"))
            chk(fm, REQ_FORM, LF)
            # data 必须是字符串、转义形态，且可解析为含 moduleList 的 JSON
            if not isinstance(fm.get("data"), str):
                errors.append("%s data 不是字符串" % LF)
            else:
                try:
                    import o2oa_builder as OB
                    if not OB.is_escaped_json(fm["data"]):
                        errors.append("%s data 不是转义形态（前端"
                                      "decodeJsonString 会失败→表单白屏）" % LF)
                    inner = json.loads(OB.decode_json_string(fm["data"]))
                    if "moduleList" not in inner:
                        errors.append("%s data 内缺 moduleList" % LF)
                except Exception as e:
                    errors.append("%s data 不是合法 JSON: %s" % (LF, e))

        form_ids = {f["id"] for f in pp.get("formList", [])}
        for pr in pp.get("processList", []):
            LP = "%s / 流程[%s]" % (L, pr.get("name"))
            chk(pr, REQ_PROC, LP)
            for m in pr.get("manualList", []):
                LM = "%s / 节点[%s]" % (LP, m.get("name"))
                chk(m, REQ_MANUAL, LM)
                if m.get("form") and m["form"] not in form_ids:
                    errors.append("%s form 指向不存在的表单 %s" % (LM, m["form"]))
                if not isinstance(m.get("position"), str):
                    errors.append("%s position 应为字符串坐标" % LM)
            for r in pr.get("routeList", []):
                chk(r, REQ_ROUTE, "%s / 路由" % LP)
            # 路由目标必须存在（Route.activity = 目标活动 id）
            act_ids = set()
            if pr.get("begin"):
                act_ids.add(pr["begin"]["id"])
            for k in ("manualList", "endList", "choiceList", "serviceList",
                      "splitList", "mergeList", "parallelList", "invokeList",
                      "agentList", "delayList", "embedList"):
                for a in pr.get(k, []):
                    act_ids.add(a["id"])
            for r in pr.get("routeList", []):
                if r.get("arriveActivity"):
                    errors.append("%s 路由仍含废弃字段 arriveActivity"
                                  "（O2OA 中不存在该字段，应为 activity）" % LP)
                if r.get("activity") and r["activity"] not in act_ids:
                    errors.append("%s 路由指向不存在的节点 %s"
                                  % (LP, r["activity"]))
            # 出口路由：Begin.route（单值）与 Manual/Choice.routeList（多值）
            route_ids = {r["id"] for r in pr.get("routeList", [])}
            if pr.get("begin") is not None:
                br = pr["begin"].get("route")
                if not br:
                    errors.append("%s 开始活动缺少出口路由 route" % LP)
                elif br not in route_ids:
                    errors.append("%s 开始活动 route 指向不存在的路由 %s" % (LP, br))
            for k in ("manualList", "choiceList", "splitList", "mergeList",
                      "parallelList", "serviceList", "invokeList", "agentList",
                      "delayList", "embedList"):
                for a in pr.get(k, []):
                    for rid in a.get("routeList", []) or []:
                        if rid not in route_ids:
                            errors.append("%s 节点[%s] routeList 含不存在的路由 %s"
                                          % (LP, a.get("name"), rid))

        for dc in pp.get("applicationDictList", []):
            chk(dc, REQ_DICT, "%s / 字典[%s]" % (L, dc.get("name")))
            if not isinstance(dc.get("data"), list):
                errors.append("%s / 字典[%s] data 应为数组"
                              % (L, dc.get("name")))

    for q in d.get("queryList", []):
        LQ = "%s / 数据中心[%s]" % (name, q.get("name"))
        chk(q, REQ_QUERY, LQ)
        view_ids = {v["id"] for v in q.get("viewList", [])}
        for v in q.get("viewList", []):
            chk(v, REQ_VIEW, "%s / 视图[%s]" % (LQ, v.get("name")))
        for t in q.get("tableList", []):
            chk(t, REQ_TABLE, "%s / 自建表[%s]" % (LQ, t.get("name")))
            check_table_fields(t, LQ, errors)
        for s in q.get("statList", []):
            chk(s, REQ_STAT, "%s / 统计[%s]" % (LQ, s.get("name")))
            if s.get("viewId") and s["viewId"] not in view_ids:
                warns.append("%s / 统计[%s] viewId 未在本应用视图内"
                             % (LQ, s.get("name")))
        for st in q.get("statementList", []):
            chk(st, REQ_STMT, "%s / 查询配置[%s]" % (LQ, st.get("name")))

    for s in d.get("serviceModuleList", []):
        LS = "%s / 服务应用[%s]" % (name, s.get("name"))
        chk(s, REQ_SVC, LS)
        for dc in s.get("dictList", []):
            chk(dc, REQ_DICT, "%s / 字典[%s]" % (LS, dc.get("name")))

    # ---- 门户应用 ----
    for pt in d.get("portalList", []):
        LP = "%s / 门户[%s]" % (name, pt.get("name"))
        chk(pt, REQ_PORTAL, LP)
        pages = pt.get("pageList", [])
        page_ids = {pg.get("id") for pg in pages}
        if not pages:
            errors.append("%s 没有任何页面（pageList 为空）" % LP)
        if pt.get("firstPage") and pt["firstPage"] not in page_ids:
            errors.append("%s firstPage=%s 不在 pageList 内"
                          % (LP, pt["firstPage"]))
        for pg in pages:
            LG = "%s / 页面[%s]" % (LP, pg.get("name"))
            chk(pg, REQ_PAGE, LG)
            if pg.get("portal") != pt.get("id"):
                errors.append("%s portal 字段未指回门户 id" % LG)
            if not isinstance(pg.get("data"), str):
                errors.append("%s data 不是字符串" % LG)
            else:
                _chk_page_data(pg["data"], LG, errors)


def check_table_fields(t, LQ, errors):
    """校验自建表字段定义。

    ⚠ 关键：字段清单**不在**顶层 fieldList，而在 data / draftData 两个
    JSON 字符串里，形如 {"fieldList":[{"name","description","type"}]}。
    旧版校验器直接查顶层 fieldList 键，与真实结构不符（会全表报错）；
    更重要的是它无法发现「字段被 O2OA 静默丢弃」的缺陷 ——
    DynamicEntity 只认白名单类型，其余类型（number/text/datetime/QQ…）
    会被无声忽略。因此这里同时校验类型白名单。
    """
    FIELDLIST_TYPES = {"string", "stringLob", "stringMap", "stringList",
                       "boolean", "booleanList", "double", "doubleList",
                       "long", "longList", "integer", "integerList",
                       "date", "time", "dateTime"}
    tname = t.get("name")
    for key in ("data", "draftData"):
        raw = t.get(key)
        if not isinstance(raw, str) or not raw.strip():
            errors.append("%s / 自建表[%s] %s 缺失或为空" % (LQ, tname, key))
            continue
        try:
            obj = json.loads(raw)
        except Exception as e:
            errors.append("%s / 自建表[%s] %s 不是合法 JSON: %s"
                          % (LQ, tname, key, e))
            continue
        fl = obj.get("fieldList")
        if not isinstance(fl, list) or not fl:
            errors.append("%s / 自建表[%s] %s.fieldList 缺失或为空"
                          % (LQ, tname, key))
            continue
        for f in fl:
            if not isinstance(f, dict):
                errors.append("%s / 自建表[%s] 字段项非对象" % (LQ, tname))
                continue
            if not f.get("name"):
                errors.append("%s / 自建表[%s] 存在无名字段" % (LQ, tname))
            ftype = f.get("type")
            if ftype not in FIELDLIST_TYPES:
                errors.append("%s / 自建表[%s] 字段[%s] 类型 %r 不在 O2OA "
                              "白名单内（会被静默丢弃）"
                              % (LQ, tname, f.get("name"), ftype))


def main():
    files = sorted(f for f in os.listdir(DELIV) if f.endswith(".xapp"))
    for f in files:
        check_file(os.path.join(DELIV, f))
    print("=" * 70)
    print("校验文件数：%d" % len(files))
    print("错误 %d 个，警告 %d 个" % (len(errors), len(warns)))
    print("=" * 70)
    for e in errors:
        print("[ERROR]", e)
    for w in warns[:20]:
        print("[WARN ]", w)
    if len(warns) > 20:
        print("... 其余 %d 条警告省略" % (len(warns) - 20))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
