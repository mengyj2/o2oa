# O2OA 本地 OCR 服务（o2-ocr-service）

> 落地时间：2026-09-19 ｜ 对应任务：#20 ｜ 状态：**已完成并实测通过**

## 一、为什么单独起一个进程

OCR 是 **CPU 重活**（一张 A4 扫描件 1–5 秒）。如果塞进 `o2_agent_gateway.py`：

| 问题 | 后果 |
|---|---|
| 与 SSE 流式对话共用事件循环 | 一次 OCR 卡住，用户看到回答"卡在半句" |
| 崩溃即拖垮网关 | 一个坏 PDF 能让整个 AI 能力下线 |
| 没法单独重启/调优 | 改 OCR 参数要重启整个网关 |

所以：**独立进程，网关只通过 HTTP 调它**。超时/崩溃互相隔离。

## 二、为什么选 RapidOCR（ONNX）

| 方案 | 体积 | 依赖 | 中文 | 显存 | 结论 |
|---|---|---|---|---|---|
| **RapidOCR (ONNX)** | ~15MB 模型 | 纯 pip wheel | 好（PP-OCR 模型） | **0** | ✅ 采用 |
| PaddleOCR | ~500MB+ | paddlepaddle 重 | 最好 | 可 CPU | 过重，且本机 4GB VRAM 需留给推理 |
| MinerU | 数 GB | 重，含版面模型 | 好 | 需 GPU 更佳 | 过重 |
| Tesseract | 小 | 需系统安装 | 一般 | 0 | Windows 安装麻烦，中文弱 |

**关键取舍**：本机是 AMD Radeon 8060S（约 4GB VRAM 可用），llama-server 已占满显存跑 Qwen3.5-4B。
OCR 必须 **纯 CPU、零显存** 才能共存。RapidOCR 的 ONNX Runtime 正好满足。

## 三、三场景覆盖（用户明确要求）

| 场景 | 实现 | 实测结果 |
|---|---|---|
| **① 扫描件** | RapidOCR 文字识别 | 12/12 行全对，含噪点、日期、标点 |
| **② 表格** | 投影法找横竖线 → 单元格切分 → 逐格 OCR → **Markdown 表格** | 5×4 表格完整还原，无错行 |
| **③ PDF** | 文本层优先（pypdf，**4ms**）；无文本层则 pypdfium2 渲染 + OCR（360ms） | 两条路径均通过 |

### 表格还原的坑（重要）

初版投影法用"图像尺寸的 1%"做阈值 → 列检测出 74 条假线，`_detect_grid` 返回 None。

**正确做法**（已固化在代码里）：
1. 先粗估拿到线的长度量级
2. **以最长横线/竖线的长度为"表格跨度"基准**，线必须覆盖跨度的 **50%** 才算数
3. 合并断裂间隙用 `max(4, 跨度*2%)`（抗锯齿会让 3px 粗线断成几段）
4. 去重：两条线间距 < 12px 只保留一条（边框粗细会产生假列）

修正后 `ys=[90,146,202,258,314,370]`、`xs=[60,280,500,720,940]` 与绘制坐标**完全一致**。

## 四、接口

```
GET  /health                    探活
GET  /warmup                    预热（提前建 ONNX session，避免首次卡 3s）
POST /ocr                       {"file_b64"|"image_b64"|"pdf_b64", "filename"}
POST /ocr/file                  {"path": "D:\\..."}   本机可信调用
```

响应：
```json
{ "ok": true, "text": "...", "blocks": [{"text","score","box","page"}],
  "tables": [{"rows":5,"cols":4,"cells":[[...]]}],
  "pages": 1, "engine": "rapidocr|pdf-text", "ms": 316 }
```

## 五、启动与集成

```
gateway\start_ocr.bat           单独启动（幂等：端口占用则跳过）
gateway\start_ocr.bat /f        前台运行（看日志）
gateway\start_ai_stack.bat      随 AI 栈一起拉起（第 4 个组件）
gateway\start_ai_stack.bat /noocr  跳过 OCR
stop_o2oa.bat                   会一并停掉 :8091
```

**OCR 是非致命组件**：`start_ai_stack.bat` 里 OCR 未就绪只告警，不会让整个 AI 栈失败。
理由：没有 OCR 只是扫描件/PDF 处理降级，对话和知识库检索照常可用。

### 网关侧接入点（两处）

| 位置 | 函数 | 用途 |
|---|---|---|
| 对话附件 | `extract_text(data, ext, name)` | O2OA `referenceIdList` 里的 PDF/图片 → 文本 |
| 知识库索引 | `extract_text_index(ext, raw)` | `/idx-gateway-doc/update` 导入的附件 → 入库 |

> ⚠️ **命名坑**：这两个函数**都曾叫 `extract_text`**，Python 后定义者会覆盖前者，
> 导致对话侧报 `extract_text() takes 2 positional arguments but 3 were given`。
> 已重命名为 `extract_text_index`。**改这个文件时不要再起同名函数。**

### 配置（`gateway/config.json`）

```json
{
  "ocr_base": "http://127.0.0.1:8091",
  "ocr_max_chars": 20000
}
```

`ocr_base` 为空 = 关闭 OCR（网关静默跳过，不报错）。

## 六、自检接口（新增）

```bash
curl -H "Authorization: Bearer local-o2-agent-2026" \
     http://127.0.0.1:18790/gateway/capabilities
```

一次性看清：chat 后端的 tool_calls / vision / video、embed、OCR、内置工具、关键配置。
**升级或排障时先跑这个**，比逐个端口 curl 快。

验证 OCR 附件链路：
```bash
node gateway/gw_ocr_test.js _ocr_samples/table.png      # 经网关
node gateway/ocr_test.js   _ocr_samples/table.png       # 直连服务
```

## 七、测试样本

`gateway/_ocr_samples/` 下四个自制样本（脚本 `C:\temp\gen_ocr_tests.py` 可重新生成）：

| 文件 | 用途 |
|---|---|
| `table.png` | 5×4 中文表格（含百分比、括号） |
| `scan.png` | 扫描件风格公文（9000 噪点） |
| `table_only.pdf` | 图转 PDF（无文本层，验证渲染+OCR） |
| `digital.pdf` | 有文本层 PDF（验证 4ms 快路径） |

## 八、依赖安装（踩坑记录）

```bash
PY="C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
"$PY" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ \
    "rapidocr_onnxruntime==1.2.3" pypdfium2 opencv-python-headless
```

> ⚠️ **清华镜像（pypi.tuna.tsinghua.edu.cn）当时是坏的** —— 连 `fastapi` 都"找不到"。
> 换**阿里镜像**后一切正常。装不上包时**先换源验证**，别怀疑架构或包名。
>
> 平台确认：`platform.machine()` = `AMD64`，`sysconfig.get_platform()` = `win-amd64`
> （Windows ARM64 上跑 x64 Python —— 若真在 win-arm64 下，`onnxruntime` 会装不上，
> 此时需改用 `onnxruntime-qnn` 或装 x64 Python）。

安装清单：`rapidocr_onnxruntime 1.2.3`、`onnxruntime 1.30.0`、`opencv-python(-headless) 5.0.0.93`、
`pypdfium2 5.13.0`、`Shapely`、`pyclipper`、`protobuf`、`flatbuffers`。

## 九、性能实测（CPU：AMD Radeon 8060S 主机）

| 场景 | 耗时 | engine |
|---|---|---|
| 1000×460 表格图 | 316–912ms | rapidocr |
| 900×640 扫描件 | 407–1210ms | rapidocr |
| 无文本层 PDF（1页） | 360–1826ms | rapidocr |
| 有文本层 PDF（1页） | **4–6ms** | pdf-text |

> 首次调用会多 1–3 秒（建 ONNX session）。`start_ai_stack.bat` 里没自动 warmup，
> 需要时手动 `curl http://127.0.0.1:8091/warmup`。

## 十、限制与后续

- **PDF 上限 30 页**（`MAX_PDF_PAGES`），超出部分不处理 —— 防 300 页 PDF 拖死服务
- **图片最长边缩到 2600px**（`MAX_SIDE`）—— 兼顾精度与内存
- 表格识别只支持**有框线**的表；无线表（纯空格对齐）走纯文本行
- 复杂版面（多栏、图文混排、跨页表格）目前是"能读但结构会散"，
  真要做好需要上 PP-StructureV3 或 MinerU —— **当前够用，暂不引入**
- OCR 结果已进 RAG 索引链路，扫描件 PDF 可被知识库检索到
