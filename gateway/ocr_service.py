# -*- coding: utf-8 -*-
"""
o2-ocr-service - O2OA 本地 OCR 服务（独立进程 :8091）

设计原则
--------
1. 独立进程：不塞进 o2_agent_gateway，OCR 是 CPU 重活（一张 A4 扫描件 1-5s），
   放进网关会堵塞 SSE 流式对话。分开后网关只用 HTTP 调它，超时/崩溃互不影响。
2. 纯 CPU + 不占 VRAM：用 RapidOCR (ONNX Runtime)，模型只有几 MB，
   与本机 4GB 显存/ROCm 推理完全隔离。
3. 三场景覆盖（用户诉求）：
   - 扫描件  -> RapidOCR 文字识别
   - 图片表格 -> 表格结构还原（横竖线检测 + 单元格切分 + 逐格 OCR）
   - PDF    -> pypdfium2 渲染成图（文本层优先，无文本层自动落 OCR）

接口
----
POST /ocr
  body(JSON): {"file_b64": "...", "filename": "x.pdf"}   或
              {"image_b64": "..."}  / {"pdf_b64": "..."}
  resp(JSON): {"ok": true, "text": "...", "blocks": [...],
               "tables": [...], "pages": N, "engine": "rapidocr|pdf-text",
               "ms": 123}
GET  /health -> {"ok": true, "engine": "rapidocr", "version": "..."}

网关接入点（o2_agent_gateway.py）：
  config.json 的 "ocr_base": "http://127.0.0.1:8091"
  - extract_text(data, ext, name)  对话附件
  - extract_text(ext, raw)         知识库索引
"""
import base64
import io
import json
import os
import re
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "ocr_service.log"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".log"}

# 单张图最长边上限（太大既慢又容易被内存打爆）
MAX_SIDE = 2600
# PDF 最多渲染页数（防止 300 页 PDF 把服务拖死）
MAX_PDF_PAGES = 30


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


# ---------------------------------------------------------------- 引擎加载（懒加载）
_engine = None
_engine_err = None


def get_engine():
    """RapidOCR 懒加载。首次调用约 1-3s（建 ONNX session），之后常驻复用。"""
    global _engine, _engine_err
    if _engine is not None:
        return _engine
    if _engine_err:
        raise RuntimeError(_engine_err)
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
        log("RapidOCR engine ready")
    except Exception as e:  # 兼容 rapidocr>=2.x 的新包名
        try:
            from rapidocr import RapidOCR  # type: ignore
            _engine = RapidOCR()
            log("RapidOCR(v2) engine ready")
        except Exception as e2:
            _engine_err = f"rapidocr unavailable: {e} / {e2}"
            log(_engine_err)
            raise RuntimeError(_engine_err)
    return _engine


def _to_np(img_bytes: bytes):
    """bytes -> RGB numpy 数组，并按 MAX_SIDE 等比缩放。"""
    import numpy as np
    from PIL import Image
    im = Image.open(io.BytesIO(img_bytes))
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    scale = min(1.0, MAX_SIDE / float(max(w, h)))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return np.array(im)


def ocr_image_bytes(img_bytes: bytes):
    """对单张图做全量 OCR。返回 (lines, raw_result)
    lines: [{"text":..,"score":..,"box":[[x,y]*4]}, ...]
    """
    eng = get_engine()
    arr = _to_np(img_bytes)
    res, _ = eng(arr)
    lines = []
    for item in (res or []):
        # rapidocr 1.x: (box, text, score)
        box, text, score = item[0], item[1], item[2]
        lines.append({
            "text": (text or "").strip(),
            "score": round(float(score or 0), 4),
            "box": [[int(p[0]), int(p[1])] for p in box],
        })
    return lines, arr


# ---------------------------------------------------------------- 表格还原
def _detect_grid(arr):
    """用投影法找表格横竖线，返回 (ys, xs) 分割坐标；找不到线返回 None。

    要点（踩过的坑）：
    - 投影阈值不能用图像尺寸的百分比（小图/大图差异太大）。
      正确做法：一条线至少覆盖表格跨度的一定比例。先取最长的强投影行/列
      作为"表格跨度"基准，再按基准的 50% 判线。
    - 合并间隙要放宽（>= max(4, 跨度*2%)），否则抗锯齿导致的 1-2px 断点
      会把一条线拆成多段，段数虚高。
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    try:
        h, w = arr.shape[:2]
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # 自适应二值后取反：线条为白
        bw = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY, 15, -2)
        hp = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 30), 1))
        vp = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 30)))
        horiz = cv2.dilate(cv2.erode(bw, hp), hp)
        vert = cv2.dilate(cv2.erode(bw, vp), vp)

        rp = horiz.sum(axis=1) / 255.0   # 每行有多少个白像素 = 横线长度
        cp = vert.sum(axis=0) / 255.0    # 每列有多少个白像素 = 竖线高度

        def _lines(proj, span_hint):
            """proj -> 线的中心坐标。span_hint = 表格跨度（另一维的线长）。"""
            if proj.size == 0 or proj.max() <= 0:
                return []
            span = float(span_hint)
            th = max(3.0, span * 0.5)      # 线至少要覆盖跨度的一半
            idx = np.where(proj >= th)[0]
            if idx.size == 0:
                return []
            gap = max(4, int(span * 0.02))  # 合并断裂间隙
            runs, start, prev = [], idx[0], idx[0]
            for i in idx[1:]:
                if i - prev > gap:
                    runs.append((start, prev))
                    start = i
                prev = i
            runs.append((start, prev))
            # 去重：两条线挨得太近（< 12px）只保留一条，避免边框粗细产生假列
            centers = [int((a + b) / 2) for a, b in runs]
            merged = []
            for c in centers:
                if merged and c - merged[-1] < 12:
                    merged[-1] = int((merged[-1] + c) / 2)
                else:
                    merged.append(c)
            return merged

        # 第一遍：以图像尺寸为跨度的粗估，拿到线的长度量级
        ys0 = _lines(rp, w)
        xs0 = _lines(cp, h)
        if not ys0 or not xs0:
            return None
        # 第二遍：表格真实跨度 = 最长横线 / 最长竖线
        span_y = float(max(rp[y] for y in ys0))
        span_x = float(max(cp[x] for x in xs0))
        ys = _lines(rp, span_y)
        xs = _lines(cp, span_x)
        if len(ys) >= 3 and len(xs) >= 3:
            return ys, xs
        log(f"grid too few lines: ys={len(ys)} xs={len(xs)}")
        return None
    except Exception as e:
        log(f"grid detect fail: {e}")
        return None


def _assign_cell(lines, x0, y0, x1, y1):
    """取出中心点落在单元格内的所有文本行，按先上后左拼接。"""
    picked = []
    for ln in lines:
        if not ln["text"]:
            continue
        bx = [p[0] for p in ln["box"]]
        by = [p[1] for p in ln["box"]]
        cx, cy = (min(bx) + max(bx)) / 2.0, (min(by) + max(by)) / 2.0
        if x0 <= cx < x1 and y0 <= cy < y1:
            picked.append((cy, cx, ln["text"]))
    picked.sort()
    return " ".join(t for _, _, t in picked).strip()


def extract_tables(lines, arr):
    """表格结构还原。返回 [{"rows": N, "cols": M, "cells": [[..],[..]]}]"""
    g = _detect_grid(arr)
    if not g:
        return []
    ys, xs = g
    rows = []
    for i in range(len(ys) - 1):
        row = []
        for j in range(len(xs) - 1):
            row.append(_assign_cell(lines, xs[j], ys[i], xs[j + 1], ys[i + 1]))
        if any(c for c in row):
            rows.append(row)
    if len(rows) < 2:
        return []
    ncols = max(len(r) for r in rows)
    if ncols < 2:
        return []
    for r in rows:
        r += [""] * (ncols - len(r))
    return [{"rows": len(rows), "cols": ncols, "cells": rows}]


def table_to_markdown(tbl):
    """表格 -> Markdown 管道表，便于塞进 RAG 上下文。"""
    cells = tbl["cells"]
    if not cells:
        return ""
    head = cells[0]
    out = ["| " + " | ".join(c or " " for c in head) + " |",
           "|" + "|".join([" --- "] * len(head)) + "|"]
    for r in cells[1:]:
        out.append("| " + " | ".join((c or " ").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- PDF
def _pdf_text_layer(raw: bytes):
    """先用 pypdf 抽文本层。返回 (text, page_count, has_text)"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        n = len(reader.pages)
        chunks = []
        for pg in reader.pages:
            chunks.append(pg.extract_text() or "")
        text = "\n".join(chunks).strip()
        # 有意义的文本层：平均每页 >= 30 字
        has = len(text) >= max(30, n * 30)
        return text, n, has
    except Exception as e:
        log(f"pypdf fail: {e}")
        return "", 0, False


def _pdf_render_pages(raw: bytes, max_pages=MAX_PDF_PAGES, dpi=200):
    """pypdfium2 渲染 PDF 每页为 PNG bytes。纯 Python wheel，无系统依赖。"""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(io.BytesIO(raw))
    n = len(doc)
    out = []
    for i in range(min(n, max_pages)):
        page = doc[i]
        img = page.render(scale=dpi / 72.0).to_pil()
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out, n


# ---------------------------------------------------------------- 主流程
def handle_any(data: bytes, ext: str, name: str):
    t0 = time.time()
    ext = (ext or "").lower()
    result = {"ok": True, "text": "", "blocks": [], "tables": [],
              "pages": 1, "engine": "", "ms": 0, "filename": name}

    # --- 纯文本
    if ext in TEXT_EXT:
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                result["text"] = data.decode(enc)
                result["engine"] = "plain"
                result["ms"] = int((time.time() - t0) * 1000)
                return result
            except Exception:
                continue

    # --- PDF：文本层优先，无文本层落 OCR
    if ext == ".pdf":
        text, npages, has = _pdf_text_layer(data)
        result["pages"] = npages or 1
        if has:
            result["text"] = text
            result["engine"] = "pdf-text"
            result["ms"] = int((time.time() - t0) * 1000)
            log(f"pdf(text-layer) {name} pages={npages} chars={len(text)}")
            return result
        try:
            pages, npages = _pdf_render_pages(data)
            result["pages"] = npages or len(pages)
        except Exception as e:
            log(f"pdf render fail: {e}")
            result["ok"] = False
            result["error"] = f"pdf 渲染失败（缺 pypdfium2？）: {e}"
            result["text"] = text  # 有部分文本层也返回
            result["ms"] = int((time.time() - t0) * 1000)
            return result
        all_lines, blocks, tables, texts = [], [], [], []
        for pi, png in enumerate(pages, 1):
            try:
                lines, arr = ocr_image_bytes(png)
            except Exception as e:
                log(f"ocr page {pi} fail: {e}")
                continue
            page_text = "\n".join(l["text"] for l in lines if l["text"])
            texts.append(f"【第 {pi} 页】\n{page_text}")
            for l in lines:
                l["page"] = pi
                blocks.append(l)
            for tb in extract_tables(lines, arr):
                tb["page"] = pi
                tables.append(tb)
            all_lines += lines
        result["text"] = "\n\n".join(texts)
        result["blocks"] = blocks
        result["tables"] = tables
        result["engine"] = "rapidocr"
        result["ms"] = int((time.time() - t0) * 1000)
        log(f"pdf(ocr) {name} pages={len(pages)} chars={len(result['text'])} "
            f"tables={len(tables)} ms={result['ms']}")
        return result

    # --- 图片（扫描件 / 表格截图）
    if ext in IMAGE_EXT or ext == "":
        lines, arr = ocr_image_bytes(data)
        result["text"] = "\n".join(l["text"] for l in lines if l["text"])
        result["blocks"] = lines
        result["tables"] = extract_tables(lines, arr)
        result["engine"] = "rapidocr"
        result["ms"] = int((time.time() - t0) * 1000)
        log(f"image {name} chars={len(result['text'])} tables={len(result['tables'])} "
            f"ms={result['ms']}")
        return result

    result["ok"] = False
    result["error"] = f"不支持的扩展名: {ext}"
    result["ms"] = int((time.time() - t0) * 1000)
    return result


app = FastAPI(title="o2-ocr-service", version="1.0")


@app.get("/health")
def health():
    eng, ver = None, ""
    try:
        eng = "ok" if _engine is not None else "lazy"
        import rapidocr_onnxruntime as r
        ver = getattr(r, "__version__", "")
    except Exception:
        pass
    return {"ok": True, "engine": eng or "unloaded", "version": ver,
            "error": _engine_err}


@app.post("/ocr")
async def ocr(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    b64 = body.get("file_b64") or body.get("image_b64") or body.get("pdf_b64") or ""
    name = body.get("filename") or body.get("name") or ""
    if not b64:
        return JSONResponse({"ok": False, "error": "缺少 file_b64 / image_b64 / pdf_b64"},
                            status_code=400)
    try:
        data = base64.b64decode(b64)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"base64 解码失败: {e}"}, status_code=400)

    ext = os.path.splitext(name)[1].lower()
    if not ext:
        # 用文件头猜
        if data[:4] == b"%PDF":
            ext = ".pdf"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif data[:2] == b"\xff\xd8":
            ext = ".jpg"
    try:
        res = handle_any(data, ext, name or f"inline{ext or '.bin'}")
        return JSONResponse(res)
    except Exception as e:
        log(f"ocr fatal: {e}\n{traceback.format_exc()}")
        return JSONResponse({"ok": False, "error": f"{e}"}, status_code=500)


@app.post("/ocr/file")
async def ocr_file(request: Request):
    """便捷入口：直接把宿主/容器可访问的本地路径交给服务读（仅本机可信调用）。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    p = body.get("path") or ""
    if not p or not os.path.isfile(p):
        return JSONResponse({"ok": False, "error": f"文件不存在: {p}"}, status_code=400)
    data = Path(p).read_bytes()
    ext = os.path.splitext(p)[1].lower()
    return JSONResponse(handle_any(data, ext, os.path.basename(p)))


@app.get("/warmup")
def warmup():
    """预热：提前建 ONNX session，避免首次对话卡 3s。"""
    try:
        get_engine()
        return {"ok": True, "warm": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OCR_PORT", "8091"))
    log(f"o2-ocr-service starting on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
