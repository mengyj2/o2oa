---
name: o2oa-onlyoffice-editor-features
description: 讲清 O2OA（社区版 / Docker 自托管，10.0.2 实证）里 OnlyOffice 编辑器**自身菜单与页签**的语义、以及离线部署下的能力边界。当用户说"打开文件所在位置点了跳到主页/主页面""打开文件所在位置不对""应该存储到存储器""rclone 有没有起作用""文件存哪了""视图/插件/AI 页签用不了""编辑器里的插件点了没反应""AI 助手点不动/没有模型""插件管理器打不开"时调用。含：①「打开文件所在位置」= OnlyOffice customization.goback（官方定义 + O2OA 源码证据），URL 由 onlyofficeFileSettings.json 的 gobackUrl 统一下发 → 跳主页属设计而非故障；★两条前端路径（表单内嵌控件整覆盖 customization ⇒ 配置无效；独立编辑器吃配置）+ 按钮显隐判据 canBack（⇒ 隐藏按钮只需 gobackUrl 置空，不必改 jar）；②文件确实落在 rclone 存储器（externalStorageSources.json 全 WebDAV → o2oa-storage:5000 → SMB → NAS）及其验证手法；③三页签浏览器级实测结论（视图=本地可用；插件/AI=云功能，离线不可用）；④AI 页签本地化路径（内置 lmstudio/ollama/customProviders 适配器）；⑤不依赖登录的 headless 页签探测法。
agent_created: true
category: troubleshooting
---

# O2OA × OnlyOffice：编辑器菜单/页签的语义与离线能力边界

> 实证环境：O2OA 10.0.2 社区版 / Docker（`o2oa-server` 172.22.0.20）+ OnlyOffice DocumentServer 9.4.0.129
> （`o2oa-onlyoffice` 172.22.0.50，宿主 `8800`）+ rclone WebDAV 存储（`o2oa-storage` 172.22.0.40:5000）。
> 配套技能：`o2oa-onlyoffice-attachment-preview`（附件"走下载/白板"四层根因）。

## 0. 一句话判定

```
点「打开文件所在位置」→ 跳到门户首页？
└─ 是 → 不是故障：该菜单项 = OnlyOffice goback，URL 由 O2OA 的 gobackUrl 统一给定（§1）
       "文件到底存哪了" → 查 externalStorageSources.json + WebDAV PROPFIND（§2）
       想改行为 → §1.5；★隐藏按钮只需把 gobackUrl 置空，不必改 jar（§1.4）

编辑器里 视图 / 插件 / AI 页签 "用不了"？
└─ 先别改配置：三页签本身都能打开（§3 有浏览器级截图结论）
   真正的不可用出现在【页签里的功能】：插件=云插件市场/在线翻译/朗读；AI=云模型需密钥
   → AI 可本地化（§4）；插件只能裁剪或接受
```

---

## 1. 「打开文件所在位置」跳主页 = 设计如此（不是存储故障）

### 1.1 官方定义（ONLYOFFICE Docs API → Customization → goback）

```
goback (object)   The settings for the Open file location menu button and upper right corner button.
  goback.url   string   The absolute URL opened when clicking the Open file location menu button.
  goback.text  string   Label of that menu button.
  goback.blank boolean  new tab(true) / current tab(false)；O2OA 不下发该字段，走 DS 默认
```

**`goback` 是「回退锚点」，不是「文件物理目录」。**
编辑器只拿到 `document.url`（下载地址），**从不持有也不暴露文件存储路径** ⇒ OnlyOffice 设计上
就不存在"打开底层存储文件夹"的能力；`goback.url` 是**整站单一 URL**，对所有文件/用户一致。

编辑器本地化旁证（DS `web-apps/apps/documenteditor/main/locale/zh.json`）：
```
"Common.Views.Header.textBack"       : "打开文件所在位置"
"DE.Views.FileMenu.btnBackCaption"   : "打开文件所在位置"
（en.json 同键 = "Open file location"）
```

### 1.2 O2OA 源码证据（war 内自带源码，可直接读）

`x_onlyofficefile_assemble_control.war` → `describe/sources/...`：

```java
// entities/FileModel.java:69
editorConfig.customization.goback.url = ConfigManager.init(Config.base()).getGobackUrl();
// utility/ConfigManager.java:58
@FieldDescribe("回退地址") private String gobackUrl;
```

⇒ `goback.url` 100% 取自 `onlyofficeFileSettings.json` 的 `gobackUrl`。
本实例值 `http://192.168.1.5:9090/x_desktop/index.html` → **点它必然跳门户首页**。

> ★ `FileModel` 只有"全局配置"一条 goback 路径，**没有**按文件生成的能力。
> 想做"打开该文件所在目录"必须改 jar（Route B 构建期），不是改配置能解决的。

### 1.3 ★ 三条前端路径决定"配置到底生不生效"

`goback` 由服务端 `FileModel` 下发，但**前端可以整体覆盖 `customization`**——覆盖了就等于没配。

| 入口 | 前端文件 | customization | gobackUrl |
|---|---|---|---|
| 附件预览 / 云文档独立编辑器 | `webroot/x_component_OnlyOfficeEditor/Main.js`、`webroot/x_component_CloudDocumentEditor/Main.js` | **不覆盖**（`new DocsAPI.DocEditor(id, fileModel)` 直传） | ✅ 生效 |
| 流程表单内嵌 OnlyOffice 控件 | `servers/webServer/x_component_process_Xform/OnlyOffice.js:314` | **整对象覆盖** `editorConfig.customization = {...}`（**不含 goback**） | ❌ 被抹掉 ⇒ 该入口本就没有此按钮 |

```bash
# 唯一的覆盖点（全库扫，结论稳定）
docker exec o2oa-server sh -c "grep -rln 'editorConfig.customization *=' \
  /opt/o2server/servers/webServer /opt/o2server/webroot"
# → 只有 x_component_process_Xform/OnlyOffice.js(.min.js)
```

### 1.4 ★ 按钮何时显示 = `canBack`（DS 源码实测，非"url 是否为空"）

`documenteditor/main/app/controller/Main.js:493-506`：
```js
if (typeof customization.goback == 'object' && editorConfig.canBackToFolder !== false) {
  _canback = customization.close === undefined
    ? (!_.isEmpty(customization.goback.url) || (goback.requestClose && canRequestClose))
    : (!_.isEmpty(customization.goback.url) && !goback.requestClose);
}
appOptions.canBack = !!_canback;          // ← 显隐判据
appHeader.setCanBack(appOptions.canBack, ...);
```
`view/FileMenu.js:463`：`isVisible = this.mode.canBack; this.miBack[isVisible?'show':'hide']();`

⇒ **`goback.url` 为空串、或 `goback` 不是对象 → 按钮隐藏**（同理 Toolbar 左上角返回按钮也隐藏）。

### 1.5 修法四选一（2026-09-30 修正版）

| 方案 | 做法 | 成本 | 评价 |
|---|---|---|---|
| A 保持现状 | 不动（`gobackUrl` = 门户首页**绝对** URL） | 0 | 与官方一致；但必须写死绝对地址 ⇒ 多入口（IP/域名/端口）必有一个跳错 |
| B 改指向 | `gobackUrl` → `http://<host>:9090/x_desktop/app.html?app=Drive`（网盘）/ `app=CloudDocument` | 低 | 一键见效；**仍是全局固定 URL，不会定位到该文件**；跳出 OA 到裸存储有权限/合规风险 |
| C 隐藏按钮 | `gobackUrl` = `""` | **极低** | ★**纯配置，无需改 jar**（判据见 §1.4）；上轮"须改 jar"的判断**已被推翻** |
| D 真"打开文件所在目录" | 改 jar：`FileModel` 按文件动态生成 goback | 高 | 唯一能兑现原始诉求；需 Route B 构建期 + 文件→存储目录映射 |

改任意一项都必须**双写**：
① 真源 `deploy/host/onlyoffice/onlyofficeFileSettings.json`（build 期 seed）
② 官方 `POST /x_onlyofficefile_assemble_control/jaxrs/onlyofficeconfig/save` 写运行态（免重启 + refresh）
否则重建镜像/新机首启被还原。

> `gobackUrl` 的使用点唯一：`FileModel.java:69`（fileModel 注入）；另 `ActionGetConfig.java:46` 把它回给前端配置页，实际未用于渲染。

---

## 2. 文件确实存在 rclone 存储器上（验证手法）

`o2server/config/externalStorageSources.json` → **`enable: true`**，且**每个业务域**都是 WebDAV：

| 域 | protocol | host:port | prefix |
|---|---|---|---|
| file / processPlatform / cms / im / custom / general / meeting / calendar / bbs / teamwork / structure / mind | `webdav` | `o2oa-storage:5000` | 同域名 |

`o2oa-storage` = `rclone/rclone`，跑 `rclone serve webdav`：SMB 后端 `\\NAS\<share>/o2oa-minio`
+ 本地热缓存 + NAS 掉线自动降级 `/degraded`（30s 探活）。

**验证（从同网络容器内 PROPFIND，宿主未发布 5000 端口）：**
```bash
docker exec o2oa-onlyoffice sh -c 'curl -s -m 8 -u <user>:<pass> \
  -X PROPFIND -H "Depth: 1" http://o2oa-storage:5000/processplatform/ | grep -o "<D:href>[^<]*</D:href>"'
# 期望看到 .../processplatform/YYYYMMDD/ 当天目录
docker logs o2oa-storage 2>&1 | grep -E "mode=" | tail -3   # 期望 mode=NORMAL
```
（凭据在 `externalStorageSources.json` 的 `username/password`。）

⇒ 若上面能看到当天目录，则 **rclone 生效、文件在存储器**，"打开文件所在位置"跳主页与此无关。

---

## 3. 「视图 / 插件 / AI」页签的真实可用性（浏览器级实测）

用 appFileEdit 的 `fileModel`+`token` 自建最小页面（**不需 O2OA 登录**）跑 headless Chromium：

```
FRAMES:
  .../documenteditor/main/index.html?...&mode=view&fileType=docx
  .../sdkjs-plugins/{9DC93CDB-...-FCC9C48DD007}/index.html?lang=zh-ZH   ← AI 插件 iframe 已加载
TABS: 文件/视图/插件/AI 均存在；clicked 视图 OK / 插件 OK / AI OK
```

| 页签 | 实际渲染 | 判定 |
|---|---|---|
| 视图 | 平移/选择/手型、缩放、调整至页面大小、放大至100%、始终显示工具栏、显示状态栏、界面主题、深色模式文档、多页 | ✅ **本地能力，完全可用** |
| 插件 | 工具条：插件管理器、Translator、Thesaurus、朗读 | ⚠️ 页签可用；**插件本体不可用** |
| AI | 动作条：设置、聊天机器人、摘要、翻译、拼写与语法检查、创建AI助手 | ⚠️ 页签可用；**需先配模型** |

DS 自带插件集（`sdkjs-plugins/plugin-list-default.json`）：
```
["ai","highlightcode","mendeley","ocr","photoeditor","speech",
 "speechrecognition","thesaurus","translator","youtube","zotero"]
```
离线可用性：`photoeditor`/`highlightcode` ✅ 本地；`marketplace`(Ascensio 市场)、`translator`、
`thesaurus`、`speech`、`speechrecognition`、`youtube`、`zotero`、`mendeley`、`ocr` ❌ 需外网/账号。

> ⚠️ 与"断云"不同：**DocumentServer 容器当前仍有外网出口**
> （容器内 `api.onlyoffice.com`→200、`github.com`→200；而 `o2oa-server`→000）。
> 若项目有"禁止外挂"硬约束，这是**待收紧项**（见 `docker-container-egress-lockdown` 技能）。

---

## 4. AI 页签本地化（唯一可"救活"的云功能）

AI 插件 v3.2.3 自带本地/自托管适配器，实物在
`sdkjs-plugins/{9DC93CDB-B576-4F0C-B55E-FCC9C48DD007}/scripts/engine/providers/internal/`：

```
lmstudio.js → super("LM Studio","http://localhost:1234","","v1")
ollama.js / gpt4all.js / openai.js / anthropic.js / deepseek.js / zhipu.js
openrouter.js / groq.js / mistral.js / together.ai.js / google-gemini.js / xAI.js / stabilityai.js
```
另有 `scripts/customProviders.js`——**允许上传自定义提供方 .js**（模板即 `internal/openai.js`，
需提供 model 名、endpoint URL、headers）；`scripts/engine/providers/preinstall-example.json`
给出 `providers/models/actions` 的预置范式。

**调用路径**：插件 iframe（浏览器侧）→ `provider.url + "/chat/completions"`。
⇒ **模型端点必须"访问者浏览器可达" + 允许跨域**（插件 origin = `http://<host>:8800`）。

本机端点实测：

| 端点 | 监听 | LAN 浏览器可达 | OpenAI 兼容 |
|---|---|---|---|
| LM Studio `:1234` | `127.0.0.1`（仅回环） | ❌ | ✅ `/v1/models` 200 |
| O2OA AI 网关 `:18790` | `0.0.0.0` | ✅ | ❌ `/v1/*` 404（只有 `/gateway/*` 自有路由） |

**两条路线：**
- **路线 A（零改动最快）**：LM Studio 开 *Serve on Local Network*（绑 `0.0.0.0:1234`）
  → AI 页签 `设置` 选内置 **LM Studio**，URL 填 `http://<宿主LAN IP>:1234`。
- **路线 B（仓库级持久化，推荐）**：给 `o2_agent_gateway.py` 加 **OpenAI 兼容门面**
  （`/v1/models`、`/v1/chat/completions` + 宽松 CORS）→ 自定义提供方指向 `http://<LAN IP>:18790/v1`。
  符合"全本地化 + 必须落仓库代码（Dockerfile 烤入）"，且浏览器与容器双向可达。

**顺带 404**：AI 插件只带 `translations/helpers/zh-CN.json`，而编辑器 `lang=zh` 解析为 `zh-ZH`
→ `.../helpers/zh-ZH.json` 404（部分中文辅助文案回落英文）。非功能性阻塞；修需在 DS 镜像补
`zh-ZH.json`（复制 `zh-CN.json`），属镜像层改动须走 Dockerfile 持久化。

---

## 5. 可复现的「页签级」探测法（不依赖 O2OA 登录）

1. Python：管理员登录 → `POST /x_onlyofficefile_assemble_control/jaxrs/onlyoffice/app/file/edit`
   body `{"appToken":"x_processplatform_assemble_surface","mode":"view","fileId":"<附件id>"}`
   header `x-token` → 取 `data.fileModel`（**已含 token**，可直接喂给 DocsAPI）。
2. 生成最小 HTML：`<script src="{fileModel.editorConfig.docserviceApi}"></script>` +
   `new DocsAPI.DocEditor("ph", <fileModel>)`，用 `python -m http.server` 起静态页。
3. Playwright（本机已有 `ms-playwright/chromium-1243` + `playwright-core`）打开，
   监听 `console` / `response>=400` / `requestfailed`；`page.frames()` 找
   `documenteditor/main` 帧，按文案点页签并逐张截图。

**关键坑**：`document.url` 是 `172.22.0.20` 容器内网地址 —— 那是给 **DocumentServer 服务端**下载用的，
浏览器无需可达；浏览器只需 `docserviceApi`（`:8800`）可达。

---

## 6. 高频坑速查

- `goback` ≠ 文件目录；`gobackUrl` 是全局"回退地址"。改它必须**双写** seed + `onlyofficeconfig/save`。
- **配置生效与否看入口**：表单内嵌控件（`process_Xform/OnlyOffice.js`）整覆盖 customization ⇒ goback 被抹、无关配置；只有独立编辑器（`OnlyOfficeEditor` / `CloudDocumentEditor`）吃配置。
- **隐藏按钮 ≠ 改 jar**：`gobackUrl=""` 即 `canBack=false` ⇒ 按钮隐藏（DS `Main.js:493` 判据）。
- `externalStorageSources.json` 的 `enable` 为 true 且各域均 webdav ⇒ 存储已走 rclone；别把它和"预览走下载"混为一谈。
- 页签"用不了"先跑 §5 探测：**页签能开 ≠ 功能能用**；云插件离线必然不可用。
- AI 插件的模型调用在**浏览器侧**发出 → 端点必须 LAN 可达 + CORS；仅绑 127.0.0.1 的 LM Studio 对别的机器无效。
- DS 容器 `lang=zh` → locale `zh-ZH`；插件只带 `zh-CN` 时会 404（表现：部分文案英文）。
