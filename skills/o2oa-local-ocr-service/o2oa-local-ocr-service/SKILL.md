---
name: o2oa-local-ocr-service
description: 为 O2OA（或任意本地 LLM 栈）搭建「扫描件 / 表格 / PDF」三场景的离线 OCR 服务（RapidOCR ONNX，纯 CPU、零显存、独立进程）。当用户问"扫描件怎么转文字""图片表格怎么提取成表格""PDF 是扫描版读不出字""OCR 怎么接进来""上传的附件 AI 读不了""RapidOCR 怎么装""PaddleOCR 太重""pip 装不上包 镜像源报找不到"时调用。含：投影法表格结构还原的正确阈值做法、PDF 文本层优先策略、网关附件链路接入、bat/进程常驻/镜像源的踩坑。
agent_created: true
category: integration

---

# 本地 OCR 服务（扫描件 / 表格 / PDF）

**一句话**：起一个独立 FastAPI 进程跑 RapidOCR（ONNX），网关通过 HTTP 调它。
纯 CPU、零显存，与 llama-server 的 4GB VRAM 完全隔离。

## 0. 先判定场景

| 症状 | 根因 | 跳转 |
|---|---|---|
| 装了包但 `pip` 说"找不到版本" | **镜像源坏了** | §1 |
| 图片表格识别出来是一坨文字、行列错乱 | 只做了文字识别，没做结构还原 | §3 |
| OCR 接进来后对话卡顿/半句卡住 | OCR 塞进网关事件循环了 | §2 |
| 扫描版 PDF 读不出字 | 只抽了文本层（为空） | §4 |
| 附件 AI 读不了 | 网关 `extract_text` 没接 OCR | §5 |
| 压测/长 PDF 把服务拖死 | 没限页数、没限图片尺寸 | §6 |

---

## 1. 装依赖：先换源，别怀疑架构

```bash
PY="C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
"$PY" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ \
    "rapidocr_onnxruntime==1.2.3" pypdfium2 opencv-python-headless
```

**踩过的坑（高优先级）**：
- 曾在 `pypi.tuna.tsinghua.edu.cn`（清华）上连 `fastapi` 都报 `No matching distribution found`。
  **镜像源本身坏了**，不是包名/架构问题。换阿里源立即正常。
- 判断镜像是否可用：`pip index versions fastapi -i <源>` —— 连 fastapi 都查不到就是源的问题。
- 确认平台：`python -c "import platform,sysconfig;print(platform.machine(), sysconfig.get_platform())"`
  - 本机（Windows ARM64）：`AMD64` / `win-amd64` → 跑的是 **x64 Python**，`onnxruntime` 可装。
  - 若真是 `win-arm64`：`onnxruntime` 装不上，需 `onnxruntime-qnn` 或改装 x64 Python。

## 2. 为什么必须独立进程

| 若塞进网关 | 后果 |
|---|---|
| 与 SSE 流式对话共用事件循环 | 一次 OCR 卡住，用户看到回答"卡在半句" |
| 崩溃即拖垮网关 | 一个坏 PDF 让所有 AI 能力下线 |
| 无法单独重启/调参 | 改 OCR 参数要重启网关 |

**结论**：独立进程 + HTTP 调用。且 OCR 应作为**非致命组件**接入启动栈
（未就绪只告警，不让整个 AI 栈失败）。

## 3. 表格结构还原（核心难点）

### 正解：投影法 + 相对跨度阈值

```python
# 1) 自适应二值后取反（线条为白）
bw = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
# 2) 形态学分离横竖线（核长取图像 1/30，至少 20px）
horiz = cv2.dilate(cv2.erode(bw, hp), hp)   # hp = (w//30, 1)
vert  = cv2.dilate(cv2.erode(bw, vp), vp)   # vp = (1, h//30)
# 3) 投影：横线看「每行白像素数」，竖线看「每列白像素数」
rp = horiz.sum(axis=1)/255.0
cp = vert.sum(axis=0)/255.0
```

**★ 阈值必须用「相对跨度」，不能用「图像尺寸百分比」**：

```
第一遍：以图像尺寸为跨度粗估，拿到线的长度量级
第二遍：span_y = max(rp[y] for y in 粗估横线)     ← 最长横线的长度 = 表格跨度
        span_x = max(cp[x] for x in 粗估竖线)
        th = max(3.0, span * 0.5)                 ← 线须覆盖跨度的 50%
        合并断裂间隙 gap = max(4, span * 0.02)     ← 抗锯齿会把 3px 粗线断成几段
        去重：相邻线间距 < 12px 只保留一条         ← 边框粗细会产生假列
```

**坑的量化**：初版用 `h*0.01`（=4）当列阈值 → 1000×460 的表检出 **74 条假列** → 返回 None。
修正后：`ys=[90,146,202,258,314,370]`、`xs=[60,280,500,720,940]`，与绘制坐标**完全一致**。

### 切格

```python
for i in range(len(ys)-1):
    for j in range(len(xs)-1):
        # 取文本行 box 的中心点落在单元格内 → 按 (cy, cx) 排序拼接
        cell = _assign_cell(lines, xs[j], ys[i], xs[j+1], ys[i+1])
```

输出同时给两样：`text`（纯文本行）+ `tables[].cells`（结构），
再由 `table_to_markdown()` 转 Markdown 管道表塞进 RAG 上下文 —— 保留行列语义。

**局限**：只支持**有框线**的表。无线表（纯空格对齐）只能走纯文本行。
复杂版面（多栏/图文混排/跨页表）需 PP-StructureV3 或 MinerU，**一般场景不必上**。

## 4. PDF：两条路径

```python
# 路径 A（快）：pypdf 抽文本层，够用就返回 —— 实测 4-6ms
text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
has = len(text) >= max(30, page_count * 30)     # 每页平均 ≥30 字算"有文本层"

# 路径 B（慢）：无文本层 → pypdfium2 渲染成图 → OCR —— 实测 360-1826ms
img = page.render(scale=dpi/72.0).to_pil()      # dpi=200
```

**判据要点**：不要用 `if text:` 判空 —— 扫描版 PDF 常有零星页眉字符。
用"每页平均字数"判，才稳。

## 5. 网关侧接入

两个接入点（名字**不要重名**，见下方坑）：

| 位置 | 函数 | 用途 |
|---|---|---|
| 对话附件 | `extract_text(data, ext, name)` | 附件 ID → 下载 → OCR |
| 知识库索引 | `extract_text_index(ext, raw)` | `/idx-gateway-doc/update` 导入件 |

配置：`{"ocr_base": "http://127.0.0.1:8091", "ocr_max_chars": 20000}`
`ocr_base` 为空 = 关闭 OCR（静默跳过，不报错）。

> **★★ 命名坑（必踩一次）**：这两个函数**曾都叫 `extract_text`**。
> Python 同名函数**后定义者覆盖前者** → 对话侧报
> `extract_text() takes 2 positional arguments but 3 were given`。
> **改此类多入口文件时，附属函数一律加后缀**（如 `_index`）。

接入后加一个自检入口，排障效率翻倍：

```python
@app.get("/gateway/capabilities")   # 一屏看清 chat/embed/ocr/tools/config 是否都 up
@app.post("/gateway/ocr-test")      # 走网关的 extract_text，验证附件链路
```

## 6. 必须设的两道闸

```python
MAX_SIDE = 2600        # 图片最长边缩放上限（太大既慢又易 OOM）
MAX_PDF_PAGES = 30     # PDF 最多渲染页数（防 300 页 PDF 拖死服务）
```

## 7. 服务接口

```
GET  /health      探活
GET  /warmup      预热（提前建 ONNX session，首次调用会多 1-3s）
POST /ocr         {"file_b64"|"image_b64"|"pdf_b64", "filename"}
POST /ocr/file    {"path": "D:\\..."}   仅本机可信调用
```

响应：`{ok, text, blocks[{text,score,box,page}], tables[{rows,cols,cells}], pages, engine, ms}`

## 8. 启动与停止

```
gateway\start_ocr.bat              单独启动（幂等：端口占用则跳过）
gateway\start_ocr.bat /f           前台（看日志）
gateway\start_ai_stack.bat         随 AI 栈一同拉起（第 4 组件，非致命）
gateway\start_ai_stack.bat /noocr  跳过
stop_o2oa.bat                      按端口 8091 一并停
```

## 9. ★ Windows bat 编码铁律

| bat 类型 | 编码 | 换行 | 备注 |
|---|---|---|---|
| 含中文 | **UTF-8（无 BOM）** | **CRLF** | 必须配 `chcp 65001` |
| 纯 ASCII | ASCII | **CRLF** | 更保险 |

- **LF 换行会让 cmd 标签解析错乱**（报 `'xxx' 不是内部或外部命令`）。
- **把含中文的 bat 强转 ASCII，会把中文全变成 `?`** —— 曾这样毁掉 `start_o2oa.bat`。
  规范化脚本：
  ```python
  t = raw.replace(b"\r\n", b"\n").decode("utf-8")
  open(p,"wb").write(t.replace("\n","\r\n").encode("utf-8"))
  ```
  改完先 `grep` 确认中文还在。

## 10. ★ 进程常驻与端口排查

- `spawn(cmd, {detached:true}).unref()` 拉起的进程 **会随调用方 shell 结束被回收**。
  要常驻：用后台任务机制（`run_in_background`）或注册为真正的服务。
- `cmd /c netstat -ano | findstr /R /C:":18790 .*LISTENING"` 在 Git Bash 下
  极易 `unexpected EOF while looking for matching '`。
  **改用 Node 解析**：`netstat -ano -p tcp` → 按 `:PORT ` + `LISTENING` 匹配 → 取末列 PID。
- `curl` 本机地址要加 `--noproxy '*'`，否则系统代理会返回 `502 Bad Gateway`。

## 11. 实测基线（AMD Radeon 8060S 主机，纯 CPU）

| 场景 | 耗时 | engine |
|---|---|---|
| 1000×460 表格图 | 316–912ms | rapidocr |
| 900×640 扫描件（9000 噪点） | 407–1210ms | rapidocr |
| 无文本层 PDF（1页） | 360–1826ms | rapidocr |
| **有文本层 PDF（1页）** | **4–6ms** | pdf-text |

精度参考：12 行中文公文扫描件 **12/12 全对**；5×4 中文表格**无错行**。
比 4B 级 VLM 的视觉读数更准（VLM 曾把 `O2OA-9527` 的连字符读成冒号）。

## 12. 排障顺序

1. `curl --noproxy '*' http://127.0.0.1:8091/health` → 服务活着吗
2. `curl --noproxy '*' http://127.0.0.1:8091/warmup` → 引擎能加载吗
3. `node gateway/ocr_test.js <样本>` → 直连服务能识别吗
4. `node gateway/gw_ocr_test.js <样本>` → 经网关链路通吗
5. `curl -H "Authorization: Bearer <token>" .../gateway/capabilities` → `ocr.up` 是 true 吗
6. 看 `gateway/ocr_service.log` 和 `gateway/gateway.log`
