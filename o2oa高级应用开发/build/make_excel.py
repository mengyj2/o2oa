# -*- coding: utf-8 -*-
"""
生成自建表 Excel 导入模板
========================

O2OA 数据中心的「自建表」支持通过 Excel 导入数据。
本脚本按各应用定义的自建表字段生成 .xlsx 模板，每个表一个文件，含：
  - 工作表「说明」：导入方法与字段类型约定
  - 工作表 = 自建表名：第 1 行是字段名（导入列头，不可改），
    第 2 行是「中文标题（类型）」说明行，导入前需整行删除

【依赖】使用自研 xlsx_writer（zipfile + 手写 OOXML），**零第三方依赖**。
    环境装不上 openpyxl（无外网 PyPI），故不引入。

【用法】
    python make_excel.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xlsx_writer import (
    XlsxBook, verify, ST_HEADER, ST_SUBTITLE, ST_TITLE, ST_BOLD, ST_TEXT,
)

import def_project as P
import def_contract as C
import def_budget as B
import def_finance as F
import def_archive as A
import def_hr as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL_DIR = os.path.join(ROOT, "deliverables", "_excel")

APPS = [
    ("01_项目管理", P),
    ("02_合同管理", C),
    ("03_预算管理", B),
    ("04_财务管理", F),
    ("05_档案管理", A),
    ("06_人力资源管理", H),
]

# 各应用对外关联主键（写进说明页，提示导入时必须编号一致）
KEY_HINT = {
    "01_项目管理": "project_no",
    "02_合同管理": "contract_no",
    "03_预算管理": "budget_no",
    "04_财务管理": "expense_no",
    "05_档案管理": "archive_no",
    "06_人力资源管理": "employee_no",
}

README_LINES = [
    ("O2OA 自建表 Excel 导入模板 —— 使用说明", ST_TITLE),
    ("", ST_TEXT),
    ("1. 本文件每个工作表对应一张 O2OA「数据中心 → 自建表」。", ST_BOLD),
    ("   工作表名称 = 自建表名称。", ST_TEXT),
    ("", ST_TEXT),
    ("2. 第 1 行是【字段名】，必须与自建表字段名完全一致，请勿修改。", ST_BOLD),
    ("   第 2 行是【中文标题（类型）】，仅作说明，导入前请整行删除。", ST_TEXT),
    ("", ST_TEXT),
    ("3. 导入步骤：", ST_BOLD),
    ("   O2OA 首页 → 数据中心 → 选择对应应用 → 自建表 →", ST_TEXT),
    ("   选择目标表 → 右上角「导入」→ 上传本 Excel → 映射字段 → 校验 → 导入。", ST_TEXT),
    ("", ST_TEXT),
    ("4. 字段类型约定：", ST_BOLD),
    ("   string   —— 字符串（默认长度见第 2 行标注）", ST_TEXT),
    ("   number   —— 数值", ST_TEXT),
    ("   date     —— 日期（yyyy-MM-dd）", ST_TEXT),
    ("   datetime —— 日期时间（yyyy-MM-dd HH:mm:ss）", ST_TEXT),
    ("   boolean  —— true / false", ST_TEXT),
    ("   text     —— 长文本", ST_TEXT),
    ("", ST_TEXT),
    ("5. 跨应用关联主键（导入时必须编号一致，否则跨应用联动查询失效）：", ST_BOLD),
    ("   project_no   项目管理应用", ST_TEXT),
    ("   contract_no  合同管理应用", ST_TEXT),
    ("   budget_no    预算管理应用", ST_TEXT),
    ("   expense_no   财务管理应用", ST_TEXT),
    ("   archive_no   档案管理应用", ST_TEXT),
    ("   employee_no  人力资源管理应用 ← 该主键向上述五大应用辐射", ST_TEXT),
    ("", ST_TEXT),
    ("6. 建议导入顺序：项目 → 合同 → 预算 → 财务 → 档案 → 人力资源，", ST_BOLD),
    ("   保证引用关系完整；人力资源的员工主表应最先导入。", ST_TEXT),
    ("", ST_TEXT),
    ("7. 人力资源管理应用的多数表带 employee_no / apply_no 外键，", ST_BOLD),
    ("   请先导「员工主表」，再导转岗/转正/离职/岗位/积分/考勤等业务表。", ST_TEXT),
]


def build_readme(wb, prefix, table_names):
    """说明页：导入方法 + 本应用表清单。"""
    ws = wb.add_sheet("说明")
    ws.set_col_width(1, 100)
    r = 1
    for text, style in README_LINES:
        ws.set_text(r, 1, text, style=style)
        r += 1

    r += 1
    ws.set_text(r, 1, "本文件包含的自建表（%d 张）：" % len(table_names), style=ST_BOLD)
    r += 1
    for i, n in enumerate(table_names, start=1):
        ws.set_text(r, 1, "   %2d. %s" % (i, n), style=ST_TEXT)
        r += 1

    r += 1
    ws.set_text(r, 1, "关联主键：%s" % KEY_HINT.get(prefix, "—"), style=ST_BOLD)
    return ws


def build_table_sheet(wb, t):
    """为一张自建表建 sheet：第 1 行字段名，第 2 行中文标题（类型）。

    注意：o2oa_builder.table() 返回的是 WrapTable 字典，
    字段清单在 t["data"]（JSON 字符串，键为 name/description/type），
    不是 t["fieldList"]。此处兼容两种形态。
    """
    ws = wb.add_sheet(t["name"])
    if "fieldList" in t:
        fields = t["fieldList"]
    else:
        fields = json.loads(t["data"]).get("fieldList", [])

    # 第 1 行：字段名（导入列头，不可改）
    for i, f in enumerate(fields, start=1):
        ws.set_text(1, i, f["name"], style=ST_HEADER)
        ws.set_col_width(i, max(12, min(28, len(f["name"]) * 2 + 6)))

    # 第 2 行：中文标题（说明用，导入前删除）
    for i, f in enumerate(fields, start=1):
        title = f.get("title") or f.get("description") or f["name"]
        ftype = f.get("type", "")
        extra = ""
        if ftype == "string" and f.get("length"):
            extra = ",%s" % f["length"]
        ws.set_text(2, i, "%s（%s%s）" % (title, ftype, extra),
                    style=ST_SUBTITLE)

    ws.freeze(2)
    return ws


def main():
    os.makedirs(EXCEL_DIR, exist_ok=True)
    total = ok_n = 0
    lines = []
    for prefix, module in APPS:
        for t in getattr(module, "TABLES", []):
            wb = XlsxBook()
            names = [x["name"] for x in getattr(module, "TABLES", [])]
            build_readme(wb, prefix, names)
            build_table_sheet(wb, t)

            fn = "%s_%s.xlsx" % (prefix, t["name"])
            path = os.path.join(EXCEL_DIR, fn)
            wb.save(path)
            ok, miss, nsheet = verify(path)
            total += 1
            if ok:
                ok_n += 1
            size = os.path.getsize(path)
            lines.append("  %s  %-42s %2d 字段  %5.1f KB  %s"
                         % ("OK " if ok else "BAD", fn,
                            len(json.loads(t["data"]).get("fieldList", [])),
                            size / 1024.0, "" if ok else ("缺:%s" % miss)))

    for s in lines:
        print(s)
    print("\n共生成 Excel 模板 %d 个（自检通过 %d 个），目录：%s"
          % (total, ok_n, EXCEL_DIR))
    return 0 if ok_n == total else 1


if __name__ == "__main__":
    sys.exit(main())
