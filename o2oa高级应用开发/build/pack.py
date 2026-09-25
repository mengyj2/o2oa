# -*- coding: utf-8 -*-
"""
O2OA 应用打包器（正确版）
=========================

【关键】`.xapp` 不是 zip，而是一个 JSON 文本文件，内容对应 Java 类
com.x.program.center.WrapModule。

验证依据（O2OA 官方源码）：
  x_program_center/.../jaxrs/module/ActionCompareUpload.java
    String json = new String(bytes, DefaultCharset.charset);
    WrapModule module = XGsonBuilder.instance().fromJson(json, WrapModule.class);
  x_component_AppCenter/Main.js
    <input accept=".xapp"> + formData.append('file', this.file)

因此本打包器：
  1. 为每个应用生成一个 WrapModule JSON（含 processPlatformList + queryList）
  2. 写出为 <应用名>.xapp（UTF-8 纯文本 JSON）
  3. 同时输出格式化 JSON 便于人工核对

输出：
    deliverables/*.xapp                 可直接「应用中心 -> 导入应用」的应用包
    deliverables/_json/<应用>/*.json    逐元素拆分的 JSON（便于核对）
    deliverables/_xapp_json/*.json      打包前的完整 WrapModule JSON
"""

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from o2oa_builder import (
    write_json, o2_datetime, wrap_module, process_platform,
    query_application, service_module, dictionary,
)

import def_project as P
import def_contract as C
import def_budget as B
import def_finance as F
import def_archive as A
import def_hr as H
import def_dict as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELIV = os.path.join(ROOT, "deliverables")
JSON_DIR = os.path.join(DELIV, "_json")
XAPPJSON_DIR = os.path.join(DELIV, "_xapp_json")
EXCEL_DIR = os.path.join(DELIV, "_excel")

# 应用清单：(目录名, 应用显示名, 分类, 流程应用id, 数据中心应用id, 模块)
APPS = [
    ("01_项目管理应用", "\u9879\u76ee\u7ba1\u7406\u5e94\u7528", "\u7efc\u5408\u7ba1\u7406",
     P.APP_ID, P.APP_ID_QUERY, P),
    ("02_合同管理应用", "\u5408\u540c\u7ba1\u7406\u5e94\u7528", "\u7efc\u5408\u7ba1\u7406",
     C.APP_ID, C.APP_ID_QUERY, C),
    ("03_预算管理应用", "\u9884\u7b97\u7ba1\u7406\u5e94\u7528", "\u8d22\u52a1\u7ba1\u7406",
     B.APP_ID, B.APP_ID_QUERY, B),
    ("04_财务管理应用", "\u8d22\u52a1\u7ba1\u7406\u5e94\u7528", "\u8d22\u52a1\u7ba1\u7406",
     F.APP_ID, F.APP_ID_QUERY, F),
    ("05_档案管理应用", "\u6863\u6848\u7ba1\u7406\u5e94\u7528", "\u7efc\u5408\u7ba1\u7406",
     A.APP_ID, A.APP_ID_QUERY, A),
    ("06_人力资源管理应用", "\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u5e94\u7528", "\u7efc\u5408\u7ba1\u7406",
     H.APP_ID, H.APP_ID_QUERY, H),
]


def clean_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _normalize_statement_sql(stmt, tables):
    """语句 SQL **保持 def_*.py 中的原样**，不在打包期改写。

    背景（2026-09-20 定稿）：
      format=sql 时 Executor 不调用 joinSql()，SQL 必须直接写物理表名
      QRY_DYN_<NAME大写>，业务列必须带 x 前缀。

      但「正确加 x 前缀」依赖**真实物理列清单**，打包期拿不到
      （只有 def_*.py 的字段定义，且子查询输出列需要另判）。
      早期在打包期做轻量改写，结果产出一份「表名已换、列名未换」的
      半成品，落库阶段再改一次就双重改写，把子查询输出列
      （rp.plan_count / l.leave_days / d1.detail_count）也加了 x 前缀。

    因此现在统一由 fix_statement_sql.py 在导入后基于数据库元数据做**唯一一次**
    重写（该脚本幂等）。这里仅做「表名可读性」保留，原样返回。
    """
    return stmt


def _rewrite_sql(sql, alias2phys):
    """表名替换 + 列名补 x 前缀（轻量版，依据 def 内部表定义）。"""
    # 1) 表名：FROM/JOIN 后的中文别名或短名 -> 物理表名
    def repl_table(m):
        kw, nm = m.group(1), m.group(2)
        if nm.upper().startswith("QRY_DYN_"):
            return kw + " " + nm
        phys = alias2phys.get(nm)
        return (kw + " " + phys) if phys else m.group(0)

    out = re.sub(r"\b(from|join)\s+([^\s,()]+)", repl_table, sql, flags=re.IGNORECASE)

    # 2) alias.col -> alias.xcol（id 特判为 xid）
    def repl_col(m):
        al, col = m.group(1), m.group(2)
        if col.startswith("x"):
            return m.group(0)
        if col.lower() == "id":
            return al + ".xid"
        return al + ".x" + col

    out = re.sub(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b", repl_col, out,
                 flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def build_app(module, app_id, app_name, app_category, qapp_id,
              with_dicts=False):
    """
    构建单个应用的 WrapModule 对象。
    返回 (wrap_module_dict, stats)
    """
    # ---- 流程平台 ----
    forms = [f.to_wrap() for f in module.FORMS]
    # 表单归属应用
    for f in forms:
        f["application"] = app_id

    processes = [p.to_wrap() for p in module.PROCESSES]
    for p in processes:
        p["application"] = app_id

    dicts = []
    if with_dicts:
        for d in D.DICTIONARIES:
            d = dict(d)
            d["application"] = app_id
            dicts.append(d)

    pp = process_platform(
        app_id, app_name,
        description="%s —— 由小复生成，可直接导入 O2OA 应用中心" % app_name,
        category=app_category,
        processes=processes, forms=forms, dicts=dicts,
    )

    # ---- 数据中心 ----
    qname = "%s（数据中心）" % app_name
    views = [dict(v) for v in getattr(module, "VIEWS", [])]
    for v in views:
        v["query"] = qapp_id
    stats = [dict(s) for s in getattr(module, "STATS", [])]
    for s in stats:
        s["query"] = qapp_id
    tables = [dict(t) for t in getattr(module, "TABLES", [])]
    for t in tables:
        t["query"] = qapp_id
    stmts = [dict(s) for s in getattr(module, "STATEMENTS", [])]
    for s in stmts:
        s["query"] = qapp_id
        _normalize_statement_sql(s, tables)

    q = query_application(
        qapp_id, qname,
        description="%s 的数据中心：视图 / 统计 / 自建表 / 查询配置" % app_name,
        category=app_category,
        views=views, stats=stats, tables=tables, statements=stmts,
    )

    # ---- 门户应用 ----
    portals = [dict(p) for p in getattr(module, "PORTALS", [])]

    wm = wrap_module(
        name=app_name,
        category=app_category,
        description="%s —— O2OA 可导入应用包（小复生成）" % app_name,
        process_platform_list=[pp],
        query_list=[q],
        portal_list=portals,
    )

    stats_info = {
        "forms": len(forms), "processes": len(processes),
        "views": len(views), "stats": len(stats),
        "tables": len(tables), "statements": len(stmts),
        "dicts": len(dicts), "portals": len(portals),
        "pages": sum(len(p.get("pageList", [])) for p in portals),
    }
    return wm, stats_info


def write_xapp(obj, path):
    """写出 .xapp —— UTF-8 纯文本 JSON（无 BOM）。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def dump_breakdown(module, app_id, qapp_id, folder):
    """把应用元素逐个写成独立 JSON，便于人工核对。"""
    base = os.path.join(JSON_DIR, folder)
    clean_dir(base)
    for f in module.FORMS:
        write_json(os.path.join(base, "form", "%s.json" % f.id), f.to_wrap())
    for p in module.PROCESSES:
        write_json(os.path.join(base, "process", "%s.json" % p.id), p.to_wrap())
    for v in getattr(module, "VIEWS", []):
        write_json(os.path.join(base, "view", "%s.json" % v["id"]), v)
    for s in getattr(module, "STATS", []):
        write_json(os.path.join(base, "stat", "%s.json" % s["id"]), s)
    for t in getattr(module, "TABLES", []):
        write_json(os.path.join(base, "table", "%s.json" % t["id"]), t)
    for s in getattr(module, "STATEMENTS", []):
        write_json(os.path.join(base, "statement", "%s.json" % s["id"]), s)
    for pt in getattr(module, "PORTALS", []):
        write_json(os.path.join(base, "portal", "%s.json" % pt["id"]), pt)
        for pg in pt.get("pageList", []):
            # 页面 data 是 HTML 字符串，单独存 .html 便于直接打开预览
            with open(os.path.join(base, "portal",
                                   "%s.html" % pg["id"]), "w",
                      encoding="utf-8") as f:
                f.write(pg.get("data") or "")
        # JSON 里把超长 HTML 截断，避免核对文件过大
        pt2 = dict(pt)
        pt2["pageList"] = [
            dict(pg, data=(pg.get("data") or "")[:200] + " ...<truncated>")
            for pg in pt.get("pageList", [])
        ]
        write_json(os.path.join(base, "portal", "%s.meta.json" % pt["id"]), pt2)


def build_all():
    # 【注意】只清理由本脚本产出的内容：_json / _xapp_json / *.xapp。
    # **不得清洗 _excel** —— 它由 make_excel.py 负责，且本函数末尾会
    # 串跑 make_excel，若在此处 rmtree 会先把上一次的模板删掉。
    if os.path.isdir(DELIV):
        for n in os.listdir(DELIV):
            p = os.path.join(DELIV, n)
            if n == "_excel":
                continue
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif n.endswith(".xapp"):
                os.remove(p)
    os.makedirs(JSON_DIR, exist_ok=True)
    os.makedirs(XAPPJSON_DIR, exist_ok=True)
    os.makedirs(EXCEL_DIR, exist_ok=True)

    results = []

    for i, (folder, app_name, app_cat, app_id, qapp_id, module) in enumerate(APPS):
        wm, st = build_app(module, app_id, app_name, app_cat, qapp_id,
                           with_dicts=(module is P))
        xapp = os.path.join(DELIV, "%02d_%s.xapp" % (i + 1, app_name))
        write_xapp(wm, xapp)
        write_json(os.path.join(XAPPJSON_DIR, "%02d_%s.json" % (i + 1, app_name)), wm)
        dump_breakdown(module, app_id, qapp_id, folder)

        results.append(dict(folder=folder, app=app_name, xapp=xapp, **st))

    # ---- 公共服务包：只含数据字典（服务管理应用）----
    svc = service_module(
        D.APP_ID_SERVICE, "\u516c\u5171\u6570\u636e\uff08\u5168\u5c40\uff09",
        description="\u516d\u5927\u5e94\u7528\u5171\u7528\u7684\u5168\u5c40\u6570\u636e\u5b57\u5178",
        dicts=[dict(d) for d in D.DICTIONARIES],
    )
    wm_svc = wrap_module(
        name="00_\u516c\u5171\u6570\u636e\u5b57\u5178",
        category="\u516c\u5171",
        description="%d \u6761\u5168\u5c40\u6570\u636e\u5b57\u5178\uff08\u4f9b\u516d\u5927\u5e94\u7528\u5171\u7528\uff09"
                    % len(D.DICTIONARIES),
        service_module_list=[svc],
    )
    write_xapp(wm_svc, os.path.join(DELIV, "00_\u516c\u5171\u6570\u636e\u5b57\u5178.xapp"))
    write_json(os.path.join(XAPPJSON_DIR, "00_\u516c\u5171\u6570\u636e\u5b57\u5178.json"), wm_svc)

    return results


def main():
    res = build_all()
    total = dict(forms=0, processes=0, views=0, stats=0,
                 tables=0, statements=0, dicts=0, portals=0, pages=0)
    print("=" * 74)
    print("O2OA 应用包生成完成（.xapp = 单文件 JSON，非 zip）")
    print("=" * 74)
    for r in res:
        print("\n[%s]  ->  %s" % (r["app"], os.path.basename(r["xapp"])))
        print("    表单 %d / 流程 %d / 视图 %d / 统计 %d / 自建表 %d / 查询 %d / 字典 %d"
              % (r["forms"], r["processes"], r["views"], r["stats"],
                 r["tables"], r["statements"], r["dicts"]))
        if r.get("portals"):
            print("    门户 %d 个 / 页面 %d 个"
                  % (r["portals"], r["pages"]))
        for k in total:
            total[k] += r[k]
    print("\n" + "-" * 74)
    print("合计：表单 %d，流程 %d，视图 %d，统计 %d，自建表 %d，查询配置 %d，字典 %d"
          % (total["forms"], total["processes"], total["views"],
             total["stats"], total["tables"], total["statements"], total["dicts"]))
    print("      门户 %d 个，门户页面 %d 个" % (total["portals"], total["pages"]))
    print("另：00_公共数据字典.xapp（服务管理应用，全局字典 %d 条）"
          % len(D.DICTIONARIES))
    print("\n输出目录：%s" % DELIV)

    # ---- 串跑 Excel 模板（必须在 .xapp 之后：本函数刚清理过目录）----
    print("\n" + "-" * 74)
    print("继续生成自建表 Excel 导入模板 ...")
    print("-" * 74)
    try:
        import make_excel
        make_excel.main()
    except Exception as e:
        print("Excel 模板生成失败（不影响 .xapp）：%s" % e)

    # ---- 串跑流程拓扑校验 ----
    # 表单树校验只看表单，看不到「路由源/目标」这类流程级缺陷，必须单独跑。
    print("\n" + "-" * 74)
    print("继续校验流程拓扑（路由源 / 目标 / 可达性 / 处理人脚本）...")
    print("-" * 74)
    try:
        import validate_flow_topology as VT
        VT.main()
    except Exception as e:
        print("流程拓扑校验未能执行：%s" % e)

    # ---- 串跑门户接线校验 ----
    # 门户是「静态骨架 + 运行时脚本」两段式：骨架的 data-op-chart 序号必须与
    # 脚本 SPEC 对齐，语句 id / 字段名也必须真实存在。错位时页面不报错、
    # 只静默显示兜底数据 —— 结构校验完全看不见，必须单独跑。
    print("\n" + "-" * 74)
    print("继续校验门户活数据接线（挂点 / idx / 语句 / 字段）...")
    print("-" * 74)
    try:
        import validate_portal as VP
        VP.main()
    except Exception as e:
        print("门户接线校验未能执行：%s" % e)

    # ---- 串跑 Excel 模板校验（纯 Python，不依赖 Excel COM / 中文路径） ----
    # 为什么不用 verify_excel.ps1：脚本路径含中文，经宿主 PowerShell 传参时
    # 编码会被破坏成乱码 → "未能找到路径"，静默失败。verify_excel.py 直接解包
    # xlsx（zip+XML），零依赖、跨位数、可复现，故改用它串跑。
    print("\n" + "-" * 74)
    print("继续校验自建表 Excel 模板（zip + XML 直读）...")
    print("-" * 74)
    try:
        import verify_excel as VE
        VE.main(["--expect"])
    except SystemExit:
        pass
    except Exception as e:
        print("Excel 模板校验未能执行：%s" % e)


if __name__ == "__main__":
    main()
