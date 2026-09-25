# -*- coding: utf-8 -*-
"""
自建表 Excel 模板 —— 自动去除「说明行」副本
==========================================

make_excel.py 生成的模板第 2 行是「中文标题（类型）」说明行，O2OA 导入前需删除。
O2OA 数据中心的 Excel 导入入口在 x_query_assemble_designer（designer 侧的 import）。

本脚本：
  1. 读取 deliverables/_excel/*.xlsx
  2. 去掉每个数据 sheet 的第 2 行（说明行），其余原样保留
  3. 输出到 deliverables/_excel_import/

说明：xlsx 为 zip + OOXML，这里不改 OOXML，而是用「行号重写」方式——
      由于说明行必须物理删除，采用最小侵入法：
        · 读取 sheet 的 sharedStrings / rows
        · 移除 row 2，并把其后 row 的 r 属性整体 -1
      为稳妥起见，直接调用本仓库自带 xlsx_writer 无法读，故用 zipfile + 正则处理 sheetN.xml。

用法：
  python prep_excel_import.py
"""

import io
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "deliverables", "_excel")
DST = os.path.join(ROOT, "deliverables", "_excel_import")


def strip_row2(sheet_xml):
    """删除 <row r="2" ...>...</row>，并将其后所有 row 的 r 减 1。

    同时修正 cell 的 r 属性（形如 A2 -> A1）。
    """
    # 找到 row 2 的完整片段（自闭合或成对）
    m = re.search(r'<row r="2"[^>]*/>', sheet_xml)
    if m:
        block = m.group(0)
    else:
        m = re.search(r'<row r="2"[^>]*>.*?</row>', sheet_xml, re.S)
        if not m:
            return sheet_xml, False
        block = m.group(0)
    sheet_xml = sheet_xml.replace(block, "", 1)

    # 后续 row 的 r 值 -1（r>=3 -> r>=2），倒序替换避免冲突
    def _fix_row(mm):
        n = int(mm.group(1))
        return '<row r="%d"' % (n - 1) if n >= 3 else mm.group(0)

    sheet_xml = re.sub(r'<row r="(\d+)"', _fix_row, sheet_xml)

    # 修正 cell 引用 r="A3" -> r="A2"（行号 >=3）
    def _fix_cell(mm):
        col, n = mm.group(1), int(mm.group(2))
        return 'r="%s%d"' % (col, n - 1) if n >= 3 else mm.group(0)

    sheet_xml = re.sub(r'r="([A-Z]+)(\d+)"', _fix_cell, sheet_xml)
    # dimension 的 ref 也顺带修正（可选，不影响导入）
    return sheet_xml, True


def process(src_path, dst_path):
    """重写 xlsx，去掉各数据 sheet 第 2 行。"""
    zin = zipfile.ZipFile(src_path, "r")
    items = zin.namelist()
    zout = zipfile.ZipFile(dst_path, "w", zipfile.ZIP_DEFLATED)
    changed = 0
    for name in items:
        data = zin.read(name)
        # 只处理 workbook 的 sheet xml（sheet1.xml..），跳过 说明 sheet 之外的无所谓，
        # 说明 sheet 第 2 行不是字段行，但删除它也无害（说明页本就非数据）。
        if re.match(r"xl/worksheets/sheet\d+\.xml$", name):
            xml = data.decode("utf-8")
            xml2, did = strip_row2(xml)
            if did:
                changed += 1
                data = xml2.encode("utf-8")
        zout.writestr(name, data)
    zout.close()
    zin.close()
    return changed


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("找不到模板目录：%s" % SRC)
    os.makedirs(DST, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".xlsx"))
    total = 0
    for fn in files:
        sp = os.path.join(SRC, fn)
        dp = os.path.join(DST, fn)
        n = process(sp, dp)
        total += 1
        print("  %-46s 处理 sheet %d 个" % (fn, n))
    print("\n共处理 %d 个模板，输出目录：%s" % (total, DST))
    print("（第 2 行说明行已删除，可直接用于 O2OA 自建表导入）")


if __name__ == "__main__":
    main()
