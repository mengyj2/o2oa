# -*- coding: utf-8 -*-
"""
零依赖 .xlsx 生成器（zipfile + 手写 OOXML）
==========================================

【为什么需要】
环境里装不上 openpyxl（无外网 PyPI），但自建表导入模板必须是真 .xlsx。
.xlsx 本质就是一个 zip 包，内含若干 XML 部件，因此可以手写。

【生成的最小 xlsx 结构】
    [Content_Types].xml          部件类型声明
    _rels/.rels                  包级关系（指向 xl/workbook.xml）
    xl/workbook.xml              工作簿（sheet 清单）
    xl/_rels/workbook.xml.rels   工作簿关系（sheet + styles）
    xl/styles.xml                字体/填充/边框/单元格格式
    xl/worksheets/sheetN.xml     各工作表

【关键取舍】
- 字符串一律用 **inlineStr**（`t="inlineStr"` + `<is><t>`），
  免去 sharedStrings.xml 这一整个部件 —— 结构更简单且完全合法。
- 样式用**固定索引表**（0~5），见 STYLES_XML，不做动态样式池。

【用法】
    from xlsx_writer import XlsxBook
    wb = XlsxBook()
    ws = wb.add_sheet("说明")
    ws.set_col_width(1, 100)
    ws.set_text(1, 1, "标题", style=ST_TITLE)
    ws.freeze(2)
    wb.save("out.xlsx")
"""

import os
import re
import zipfile

# ---------- 固定样式索引（与 STYLES_XML 的 cellXfs 顺序严格对应）----------
ST_DEFAULT = 0    # 默认
ST_HEADER = 1     # 表头：白粗字 + 蓝底 + 细边框 + 居中
ST_SUBTITLE = 2   # 副标题：灰色斜体小字 + 细边框 + 居中
ST_TITLE = 3      # 说明页大标题
ST_BOLD = 4       # 说明页加粗正文
ST_TEXT = 5       # 说明页普通正文

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheets}
</sheets>
</workbook>
"""

_WB_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{items}
<Relationship Id="rId{styles_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="10"/><color theme="1"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><i/><sz val="9"/><color rgb="FF666666"/><name val="Calibri"/></font>
<font><b/><sz val="13"/><color rgb="FF1A365D"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color theme="1"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF2B6CB0"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border>
<left style="thin"><color rgb="FFBBBBBB"/></left>
<right style="thin"><color rgb="FFBBBBBB"/></right>
<top style="thin"><color rgb="FFBBBBBB"/></top>
<bottom style="thin"><color rgb="FFBBBBBB"/></bottom>
<diagonal/>
</border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""

_SHEET_HEAD = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>
{cols}<sheetData>
"""
_SHEET_TAIL = """</sheetData></worksheet>
"""

_ILLEGAL_SHEET = re.compile(r'[\[\]:*?/\\]')
_ILLEGAL_XML = re.compile(
    r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]')


def esc(s):
    """XML 转义 + 剔除非法字符（Excel 对控制字符零容忍）。"""
    if s is None:
        return ""
    s = _ILLEGAL_XML.sub("", str(s))
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


def col_letter(idx):
    """1 -> A, 26 -> Z, 27 -> AA"""
    out = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        out = chr(65 + r) + out
    return out


def safe_sheet_name(name, used):
    """Excel 工作表名限制：≤31 字符、不含 []:*?/\\ 、不可重复。"""
    n = _ILLEGAL_SHEET.sub("_", str(name)).strip() or "Sheet"
    n = n[:31]
    base, i = n, 2
    while n.lower() in used:
        suffix = "_%d" % i
        n = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(n.lower())
    return n


class _Sheet(object):
    def __init__(self, name, xlsx_index):
        self.name = name
        self.index = xlsx_index
        self.cells = {}          # (row, col) -> (style, kind, value)
        self.cols = {}           # col -> width
        self.freeze_rows = 0

    def set_text(self, row, col, value, style=ST_DEFAULT):
        self.cells[(row, col)] = (style, "s", "" if value is None else str(value))

    def set_number(self, row, col, value, style=ST_DEFAULT):
        self.cells[(row, col)] = (style, "n", value)

    def set_col_width(self, col, width):
        self.cols[col] = width

    def freeze(self, rows):
        self.freeze_rows = rows

    # ---------- XML 序列化 ----------
    def _cols_xml(self):
        if not self.cols:
            return ""
        parts = []
        for c in sorted(self.cols):
            parts.append('<col min="%d" max="%d" width="%.1f" customWidth="1"/>'
                         % (c, c, self.cols[c]))
        return "<cols>%s</cols>" % "".join(parts)

    def _pane_xml(self):
        if not self.freeze_rows:
            return ""
        y = self.freeze_rows
        tl = "A%d" % (y + 1)
        return ('<pane ySplit="%d" topLeftCell="%s" activePane="bottomLeft" '
                'state="frozen"/>' % (y, tl))

    def _cells_xml(self):
        if not self.cells:
            return ""
        rows = {}
        for (r, c), v in self.cells.items():
            rows.setdefault(r, []).append((c, v))
        out = []
        for r in sorted(rows):
            out.append('<row r="%d">' % r)
            for c, (style, kind, val) in sorted(rows[r]):
                ref = "%s%d" % (col_letter(c), r)
                if kind == "n":
                    out.append('<c r="%s" s="%d"><v>%s</v></c>'
                               % (ref, style, val))
                else:
                    out.append('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                               % (ref, style, esc(val)))
            out.append("</row>")
        return "".join(out)

    def to_xml(self):
        return (_SHEET_HEAD.format(pane=self._pane_xml(), cols=self._cols_xml())
                + self._cells_xml() + _SHEET_TAIL)


class XlsxBook(object):
    def __init__(self):
        self.sheets = []
        self._used = set()

    def add_sheet(self, name):
        ws = _Sheet(safe_sheet_name(name, self._used), len(self.sheets) + 1)
        self.sheets.append(ws)
        return ws

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        # 说明页排在最后定义时，用 sheets 顺序直接写（调用方自己控制顺序）
        overrides = "\n".join(
            '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            % s.index for s in self.sheets)
        sheet_tags = "\n".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
            % (esc(s.name), s.index, s.index) for s in self.sheets)

        styles_rid = len(self.sheets) + 1
        rel_items = "\n".join(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (s.index, s.index) for s in self.sheets)

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml",
                       _CONTENT_TYPES.format(sheet_overrides=overrides))
            z.writestr("_rels/.rels", _RELS)
            z.writestr("xl/workbook.xml",
                       _WORKBOOK.format(sheets=sheet_tags))
            z.writestr("xl/_rels/workbook.xml.rels",
                       _WB_RELS.format(items=rel_items, styles_rid=styles_rid))
            z.writestr("xl/styles.xml", STYLES_XML)
            for s in self.sheets:
                z.writestr("xl/worksheets/sheet%d.xml" % s.index, s.to_xml())
        return path


def verify(path):
    """自检：能否作为 zip 打开、必需部件是否齐全。"""
    need = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels", "xl/styles.xml"}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        bad = z.testzip()
    missing = need - names
    sheets = sorted(n for n in names if n.startswith("xl/worksheets/"))
    return (not missing and bad is None), missing, len(sheets)


if __name__ == "__main__":
    wb = XlsxBook()
    ws = wb.add_sheet("测试")
    ws.set_text(1, 1, "字段名", style=ST_HEADER)
    ws.set_text(1, 2, "中文", style=ST_HEADER)
    ws.set_text(2, 1, "a&b<c>", style=ST_SUBTITLE)
    ws.set_col_width(1, 18)
    ws.freeze(1)
    p = wb.save(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "_t.xlsx"))
    ok, miss, n = verify(p)
    print("自检:", "OK" if ok else "FAIL", "缺失:", miss, "sheet:", n)
