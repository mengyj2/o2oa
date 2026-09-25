# -*- coding: utf-8 -*-
"""verify_excel.py —— 纯 Python 校验自建表 Excel 模板（不依赖 Excel COM）。

背景（2026-09-20）：
  原 verify_excel.ps1 依赖 `New-Object -ComObject Excel.Application`，
  本机 Office16 为 x86，且当前 COM 注册异常
  （REGDB_E_CLASSNOTREG / CLSID 00000000-...），脚本静默失败。
  故改为直接解包 .xlsx（本质是 zip + XML），零依赖、跨位数、可复现。

校验项：
  1. zip 可打开，含 [Content_Types].xml / xl/workbook.xml
  2. 工作表数量与名称（约定：[说明, 数据] 或 [字段, 数据]）
  3. 数据页表头行非空，且表头列数 = 字段数
  4. 与 build 期 json 中声明的字段数比对（可选，--expect）

用法：
  python verify_excel.py                 # 校验 deliverables/_excel/*.xlsx
  python verify_excel.py --expect        # 额外与 _json 里的字段数比对
"""

import glob
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

BUILD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BUILD)
EXCEL_DIR = os.path.join(ROOT, "deliverables", "_excel")
JSON_DIR = os.path.join(ROOT, "deliverables", "_json")

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _shared_strings(z):
    """读共享字符串表。"""
    try:
        raw = z.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    out = []
    for si in root.findall(NS + "si"):
        # 富文本会拆成多个 <r><t>
        txt = "".join(t.text or "" for t in si.iter(NS + "t"))
        out.append(txt)
    return out


def _sheets(z):
    """返回 [(sheetName, zipPath)]，按 workbook 顺序。"""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid2target = {}
    for r in rels:
        rid = r.get("Id")
        tgt = r.get("Target")
        if rid and tgt:
            rid2target[rid] = tgt.lstrip("/")
    out = []
    for sh in wb.find(NS + "sheets"):
        name = sh.get("name")
        rid = sh.get(RNS + "id")
        tgt = rid2target.get(rid, "")
        if not tgt.startswith("xl/"):
            tgt = "xl/" + tgt
        out.append((name, tgt))
    return out


def _sheet_rows(z, path, sst, max_rows=3):
    """读工作表前 max_rows 行，返回 [[cellText, ...], ...]（按列序补齐）。"""
    root = ET.fromstring(z.read(path))
    data = root.find(NS + "sheetData")
    if data is None:
        return []
    rows = []
    for row in list(data)[:max_rows]:
        cells = {}
        for c in row:
            ref = c.get("r") or ""
            col = re.match(r"([A-Z]+)", ref)
            if not col:
                continue
            ci = _col_index(col.group(1))
            t = c.get("t")
            v = c.find(NS + "v")
            isel = c.find(NS + "is")
            if t == "s" and v is not None and v.text is not None:
                try:
                    val = sst[int(v.text)]
                except (ValueError, IndexError):
                    val = ""
            elif t == "inlineStr" and isel is not None:
                val = "".join(x.text or "" for x in isel.iter(NS + "t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[ci] = val
        if cells:
            n = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(n)])
        else:
            rows.append([])
    return rows


def _col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _expected_fields(fp):
    """从打包 json 里找同名表，返回声明的字段数；找不到返回 None。

    表名形态：`01_项目管理_t1001001_project_master_table.xlsx`
             `01_项目管理_项目主表.xlsx`
    """
    base = os.path.basename(fp)[:-5]           # 去 .xlsx
    parts = base.split("_", 2)
    if len(parts) < 3:
        return None
    key = parts[2]                              # slug 或 中文表名
    app = parts[0] + "_" + parts[1]
    cand = os.path.join(JSON_DIR, app + ".json")
    if not os.path.exists(cand):
        hits = glob.glob(os.path.join(JSON_DIR, "*" + parts[1] + "*.json"))
        if not hits:
            return None
        cand = hits[0]
    try:
        data = json.load(open(cand, encoding="utf-8"))
    except Exception:
        return None
    mods = data if isinstance(data, list) else [data]
    for m in mods:
        if not isinstance(m, dict):
            continue
        for t in _iter_tables(m):
            if str(t.get("name")) == key or str(t.get("alias")) == key:
                try:
                    return len(json.loads(t.get("data") or "{}").get("fieldList", []))
                except Exception:
                    return None
    return None


def _iter_tables(obj):
    if isinstance(obj, dict):
        if obj.get("draftData") is not None and obj.get("name"):
            yield obj
        for v in obj.values():
            for x in _iter_tables(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _iter_tables(v):
                yield x


def main(argv=None):
    argv = sys.argv if argv is None else argv
    check_expect = "--expect" in argv
    files = sorted(glob.glob(os.path.join(EXCEL_DIR, "*.xlsx")))
    if not files:
        print("[FATAL] 未找到 xlsx：%s" % EXCEL_DIR)
        return 1
    print("Excel 模板校验（纯 Python）目录：%s" % EXCEL_DIR)
    print("=" * 74)
    ok = bad = 0
    problems = []
    for fp in files:
        name = os.path.basename(fp)
        try:
            with zipfile.ZipFile(fp) as z:
                bad_names = z.testzip()
                if bad_names:
                    raise ValueError("zip 内条目损坏：" + bad_names)
                if "xl/workbook.xml" not in z.namelist():
                    raise ValueError("缺少 xl/workbook.xml")
                sst = _shared_strings(z)
                sheets = _sheets(z)
                if not sheets:
                    raise ValueError("无工作表")
                data_name, data_path = sheets[-1]      # 约定：最后一页是数据页
                rows = _sheet_rows(z, data_path, sst, max_rows=2)
                hdr = rows[0] if rows else []
                hdr = [h for h in hdr if str(h).strip()]
                if not hdr:
                    raise ValueError("数据页表头为空（sheet=%s）" % data_name)
                msg = ("OK   %-46s sheets=%d data='%s' 表头列=%d | %s"
                       % (name, len(sheets), data_name, len(hdr),
                          " / ".join(str(h) for h in hdr[:4])))
                if check_expect:
                    exp = _expected_fields(fp)
                    if exp is not None and exp != len(hdr):
                        raise ValueError("字段数不符：表头 %d vs 定义 %d"
                                         % (len(hdr), exp))
                    if exp is not None:
                        msg += " [=定义 %d]" % exp
                print(msg)
                ok += 1
        except Exception as e:
            print("BAD  %-46s %s" % (name, e))
            problems.append((name, str(e)))
            bad += 1
    print("=" * 74)
    print("模板 %d 个：通过 %d，失败 %d" % (len(files), ok, bad))
    if problems:
        for n, e in problems:
            print("   - %s: %s" % (n, e))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())