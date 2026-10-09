---
name: o2oa-onlyoffice-editor-features
description: 讲清 O2OA（社区版 / Docker 自托管，10.0.2 实证）里 OnlyOffice 编辑器**自身菜单与页签**的语义、以及离线部署下的能力边界。当用户说"打开文件所在位置点了跳到主页/主页面""打开文件所在位置不对""应该存储到存储器""rclone 有没有起作用""文件存哪了""视图/插件/AI 页签用不了""编辑器里的插件点了没反应""AI 助手点不动/没有模型""AI 配好了吗怎么还不能用""AI 页签点开是空的""AI 页签怎么指向本地网关""AI 插件怎么预置/开箱可用""AI 页签里聊天机器人点了没反应""预览里 AI 打不开但编辑能打开""AI 配置是对的为什么窗口不出来""OnlyOffice 文档列表里为什么没有我的文件""别人的附件进了列表我的没进""能不能只看自己用过的 OnlyOffice 文件""文档列表只有管理员能看""在线文档列表点不开下级目录""在线文档里混进了网盘文件""在线文档要跟流程状态绑定只读"时调用。含：①「打开文件所在位置」= OnlyOffice customization.goback（官方定义 + O2OA 源码证据），URL 由 onlyofficeFileSettings.json 的 gobackUrl 统一下发 → 跳主页属设计而非故障；★两条前端路径（表单内嵌控件整覆盖 customization ⇒ 配置无效；独立编辑器吃配置）+ 按钮显隐判据 canBack（⇒ 隐藏按钮只需 gobackUrl 置空，不必改 jar）；②文件确实落在 rclone 存储器（externalStorageSources.json 全 WebDAV → o2oa-storage:5000 → SMB → NAS）及其验证手法；③三页签浏览器级实测结论（视图=本地可用；插件/AI=云功能，离线不可用）；④AI 页签本地化路径（内置 lmstudio/ollama/customProviders 适配器 + ★路线 B 已落地：网关 `/v1` OpenAI 兼容门面 + 宽松 CORS + 自定义 provider 的 addon/URL 拼接契约）；⑤不依赖登录的 headless 页签探测法；⑥「文档列表」真实来源（只有 edit 落表 + 接口仅管理员，故"别人的进了我的没进"）；⑦★自建「我的在线文档」组件（`x_component_MyOnlineDocs`）的实测接口、打开方式与入口注册；⑧★三条产品规则（流程状态只读 / 模块·流程·单据三级目录 / 只收流程文档不当网盘）与其两个"静默失效"坑（树展开键发散、`.min.js`+`VERSION` 未同步）与"不当网盘"的反证方法；⑨★★AI 页签「开箱可用」的预置注入：配置只在浏览器 localStorage 两键、官方 aiSettings 通道为何在本版插件被 eventsMap 短路、插件目录不在镜像内（启动期由 pluginsmanager 现装 ⇒ 构建期烤补丁不可能）、薄镜像+启动包装方案、`.js`/`.gz` gzip_static 硬坑、以及"插件帧内真实对话"才算通过的验证法 + DS 无封网从 CDN 装插件的合规提醒；⑩★★「配置全对、点了却没反应」的真根因与修法：DS 编辑器 `Plugins.js:1267` 的 `visible` 判据要求 `variation.isViewer`，官方插件没给 ⇒ **只读预览下窗口被静默丢弃**；修法 = 注入器第二处补丁给 `register.js` 补 `isViewer/isDisplayedInViewer`（幂等 + 同步 `.gz`）；含预览下**只认独立弹窗、panelRight 停靠会被忽略**的形态差异，以及五层逐级排查表与 `tools/o2_ai_chat_e2e.js` 取证脚本。
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

### 1.5 修法四选一（★2026-09-30 已采纳 B 并落地）

| 方案 | 做法 | 成本 | 评价 |
|---|---|---|---|
| A 保持现状 | 不动（`gobackUrl` = 门户首页**绝对** URL） | 0 | 与官方一致；但必须写死绝对地址 ⇒ 多入口（IP/域名/端口）必有一个跳错 |
| **B 改指向（★本实例已采纳）** | `gobackUrl` → `http://<host>:9090/x_desktop/app.html?app=MyOnlineDocs`（自建「我的在线文档」组件，见 §7） | 低 | 语义贴近"我用过的文件"、一键见效；**仍是全局固定 URL、不会定位到该文件**；★勿指向 `:5000` 裸 WebDAV（越权 + 合规） |
| C 隐藏按钮 | `gobackUrl` = `""` | **极低** | ★**纯配置，无需改 jar**（判据见 §1.4）；上轮"须改 jar"的判断**已被推翻** |
| D 真"打开文件所在目录" | 改 jar：`FileModel` 按文件动态生成 goback | 高 | 唯一能兑现原始诉求；需 Route B 构建期 + 文件→存储目录映射 |

**打开行为（DS 未压缩源码实证）**：`documenteditor/main/app/controller/Main.js:1006-1018` `goBack()` 中
`goback.blank` 未定义（O2OA 只下发 url）⇒ 走 `window.open(href, "_blank")` —— **新标签打开**、不顶掉编辑器；
仅当 `blank===false` 才 `parent.location.href = href`。⇒ 两条硬约束：
1. URL **必须是绝对地址**（新标签重新解析；相对路径会按 DS 域 `:8800` 解析 → 404）；
2. 新标签要带得上登录态 ⇒ **访问地址的域必须与 `gobackUrl` 一致**（用 IP 访问就填同一 IP；
   本机用 `localhost` 测会因 cookie 域不符落登录页 —— 回归脚本 `O2_BASE` 因此默认 LAN IP）。

**落地三处（缺一即"改了等于没改"）**：
① 真源 `deploy/host/onlyoffice/onlyofficeFileSettings.json` → Dockerfile COPY 为 `onlyoffice.seed.json`；
② entrypoint `onlyoffice-selfheal` **按【种子为准】比对关键字段**（converter / tempstorage / api / preloader /
   downLoadUrl / secret / **gobackUrl**），任一漂移即整包回写。★2026-09-30 升级：旧版只比 `downLoadUrl`，
   ⇒ "只改 seed、重建容器不生效"（正是要杜绝的"改了等于没改"）；
③ 即时生效（免重启）：`POST /x_onlyofficefile_assemble_control/jaxrs/onlyofficeconfig/save`。

验证：`GET {SVC}/onlyofficeconfig/get` 逐字段比对；端到端见 `tools/o2_mydocs_ui_verify.js` **第 6 步**
（进编辑器 → 点 `#btn-text-from-file` → 点 `.btn-goback` → 断言新标签 URL 含 `app=MyOnlineDocs` 且渲染出列表）。

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

**调用路径**：插件 iframe（浏览器侧直连）→ `AI._getEndpointUrl()`（`engine/engine.js:341`）
= `provider.url`（去尾斜杠）+（`addon` 非空且 url 尾部没有它时 `"/"+addon`）+ 相对端点
（`"/chat/completions"` / `"/models"`）。
★ **addon 只对"已注册的提供方名"存在**：`internal/lmstudio.js` 是 `super(..., "v1")`；
而**自定义提供方**（新名字）在 `base.js:AI.createProviderInstance()` 里回落到 `new AI.Provider(name,url,key)`
⇒ addon=**空串** ⇒ 最终 URL = 界面填的 URL + `/chat/completions`。
⇒ **用自定义提供方时 URL 必须自带 `/v1`**。
请求头 `provider.js:159`：`Content-Type: application/json`，仅当 key 非空才带 `Authorization: Bearer`。
请求体 `provider.js:201`：`{model, messages}`，流式时 `engine.js:814` 加 `stream:true`。
⇒ **模型端点必须"访问者浏览器可达" + 允许跨域**（插件 origin = O2OA `:9090` 或 DS `:8800`）。

本机端点实测：

| 端点 | 监听 | LAN 浏览器可达 | OpenAI 兼容 |
|---|---|---|---|
| LM Studio `:1234` | `127.0.0.1`（仅回环） | ❌ | ✅ `/v1/models` 200 |
| O2OA AI 网关 `:18790`（**改造前**） | `0.0.0.0` | ✅ | ❌ `/v1/*` 404（只有 `/gateway/*` 自有路由） |
| O2OA AI 网关 `:18790`（**2026-09-30 起**） | `0.0.0.0` | ✅ | ✅ `/v1/models`、`/v1/chat/completions`（含宽松 CORS） |

**两条路线：**
- **路线 A（零改动最快，不推荐长期用）**：LM Studio 开 *Serve on Local Network*（绑 `0.0.0.0:1234`）
  → AI 页签 `设置` 选内置 **LM Studio**，URL 填 `http://<宿主LAN IP>:1234`。
  缺点：配置只活在 LM Studio 本地设置里，换机/重建不带走。
- **路线 B（★已落地，推荐）**：`gateway/o2_agent_gateway.py` 内已加 **OpenAI 兼容门面**
  （`GET /v1/models`、`POST /v1/chat/completions` + `CORSMiddleware(allow_origins=["*"], allow_credentials=False)`），
  落仓库源码、`gateway/Dockerfile` 构建期 `COPY gateway/` 烤镜像。
  客户端接法：编辑器 → AI 页签 → 设置 → 「+ 添加模型」→ **Provider URL 填 `http://<LAN IP>:18790/v1`**、key 留空
  → Model 下拉自动从 `/v1/models` 拉取（网关 `chat_model` 已置顶）。
  ★ 改完必须 `docker compose build ai-gateway && docker compose up -d ai-gateway ai-ocr ai-plan`（三服务共用镜像）。
  ★ 自定义提供方文件格式硬约束：`AI.addCustomProvider` 把内容包成 `(function(){ … return new Provider(); })()` 再 eval
  ⇒ 文件**只能顶层声明 `class Provider extends AI.Provider`**，不能自套 IIFE、不要自行注册
  （仓库内有现成件 `deploy/host/onlyoffice/ai_provider_o2_gateway.js`）。

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

- `goback` ≠ 文件目录；`gobackUrl` 是全局"回退地址"（★本实例已指向 `app.html?app=MyOnlineDocs`）。
  改它只需改 git 真源 seed —— entrypoint selfheal 会按种子收敛运行态（§1.5）；手工热改 `onlyofficeconfig/save` 即时生效。
- **配置生效与否看入口**：表单内嵌控件（`process_Xform/OnlyOffice.js`）整覆盖 customization ⇒ goback 被抹、无关配置；只有独立编辑器（`OnlyOfficeEditor` / `CloudDocumentEditor`）吃配置。
- **隐藏按钮 ≠ 改 jar**：`gobackUrl=""` 即 `canBack=false` ⇒ 按钮隐藏（DS `Main.js:493` 判据）。
- `externalStorageSources.json` 的 `enable` 为 true 且各域均 webdav ⇒ 存储已走 rclone；别把它和"预览走下载"混为一谈。
- 页签"用不了"先跑 §5 探测：**页签能开 ≠ 功能能用**；云插件离线必然不可用。
- AI 插件的模型调用在**浏览器侧**发出 → 端点必须 LAN 可达 + CORS；仅绑 127.0.0.1 的 LM Studio 对别的机器无效。
- DS 容器 `lang=zh` → locale `zh-ZH`；插件只带 `zh-CN` 时会 404（表现：部分文案英文）。

---

## 7. 「文档列表」的真实来源（★为什么别人的附件"没进去"、能不能只看自己的）

**一句话**：`ONLYOFFICE_FILE` 不是"谁用过 OnlyOffice"的账本，而是**"以编辑模式打开过的 O2O 附件"的副本索引**，
且**只对管理员开放**。

### 7.1 写入条件：只有 `edit` 落表（★根本原因）

```java
// x_onlyofficefile_assemble_control → BaseAction.getO2File()
OnlyOfficeFile record = emc.find(fileId, OnlyOfficeFile.class);
if (record == null) {
    record.setId(fileId); record.setRelevanceId(fileId); record.setCategory(appId);
    record.setDocId(woO2File.getJob()); record.setCreator(woO2File.getOwnerId());
    record.setFileVersion("1"); record.setStatus("normal"); record.setFileName(name); ...
    if (FileModel.MODE_EDIT.equals(mode)) {      // ★★ 只读预览(view) 不落表！
        record.saveContent(gfMapping, fileByte, name);
        emc.persist(record, CheckPersistType.all);
    }
}
```
⇒ `ActionFileEdit`（**附件在线预览**，mode=view）**不产生记录**；
⇒ `ActionCreateForO2`（表单 **OnlyOffice 控件**，第 86 行固定传 `FileModel.MODE_EDIT`）**一定产生记录**。

### 7.2 记录与附件的对应关系

- `ONLYOFFICE_FILE.xid` == **附件 id**（`setId(fileId)`，一一对应，可直接 join 判断）
- `xcategory` = appToken（流程 = `x_processplatform_assemble_surface`；模板 = `template`）
- `xdocId` = **流程 job id**；`xcreator` = **附件 owner**（≠ 实际打开的人）
- 表兄弟：`ONLYOFFICE_FILE_VERSION`（版本/差异）、`ONLYOFFICE_CALLBACK`
- ⚠️ `ONLYOFFICE_RECORD`（含 `readList`/`writeList`）是**历史遗留空表**，jar 源码 **0 引用**，别当数据源

### 7.3 列表接口只给管理员（所以"只看自己的"原生不可能）

```java
// ActionPaging.java:34
if(effectivePerson.isNotManager()){ throw new ExceptionAccessDenied(effectivePerson); }
```
且 Wi 里**只有显式传 `creator` 才过滤**，没有"默认当前用户"⇒ 该界面是管理员台账，不是个人视角。

### 7.4 排查 SQL（本地实测可用）

```sql
-- 谁进了列表
SELECT xid,xfileName,xcategory,xcreator,xdocId,xcreateTime FROM X.ONLYOFFICE_FILE;
-- 某附件是否进了列表（记录 id == 附件 id）
SELECT COUNT(*) FROM X.ONLYOFFICE_FILE WHERE xid='<附件id>';
-- 该附件在流程侧的真相（site=attachment 表示是附件控件上传的）
SELECT xid,xname,xperson,xjob,xsite,xlength,xcreateTime FROM X.PP_C_ATTACHMENT WHERE xid='<附件id>';
```

**实测对照（2026-09-30，同一个「用印申请单」流程，xprocessName 相同）**

| 单子 | 附件 | 是否在 ONLYOFFICE_FILE |
|---|---|---|
| 李静（10:26 启动） | `dc9a4929…` 214KB | ✅ 在（曾以 **edit** 打开过） |
| 卢宏萍（11:27 启动，谦宜贺信.doc） | `cb3d0fa7…` 14KB | ❌ 不在（只 **view** 预览 / 未打开） |

⇒ "同样的流程、别人的进了我的没进" = **打开模式不同（edit vs view）**，不是故障、也不是存储问题。

### 7.5 想做"只显示自己用过的 OnlyOffice 文件"（原生做不到，三条路线）

| 路线 | 做法 | 成本 | 说明 |
|---|---|---|---|
| **1 自建列表（推荐）** | 门户页/桌面组件：取"我经手的流程"（`WorkAction`/`WorkCompletedAction` 分页，**普通用户 token 可用**）→ 逐单 `attachment/list/workorworkcompleted/{id}` → 过滤 doc/xls/ppt 系扩展名 → 点击直进 OnlyOffice 预览 | 中 | 绕开 `x_onlyofficefile` 权限；**预览过的也算**；100% 本地、可落仓库 + Dockerfile 烘焙 |
| 2 改 jar 加接口 | `x_onlyofficefile` 增 `paging/mine`：放开非管理员但**强制** `creator=effectivePerson`；并把落表条件从 `MODE_EDIT` 放宽到 view（加 `xstatus` 区分 viewed/edited） | 中高 | 语义最准（真"用过"），走 Route B 构建期 |
| 3 零改动折中 | `gobackUrl` 指向 O2OA 网盘/文件应用中自己的空间 | 极低 | 是"文件库"不是"使用记录"，语义打折 |

> ★ **已与 §1.5 合并落地**：`gobackUrl` 现指向 `http://<host>:9090/x_desktop/app.html?app=MyOnlineDocs`，
> 点「打开文件所在位置」= 新标签打开"自己参与单据里的在线文档列表"。
> ⇒ 点「打开文件所在位置」= 到自己用过的文件列表（这才贴近用户对按钮的真实期待）。
> ⚠️ 流程平台**没有**"按人列附件"的接口（全是 `attachment/list/work/{workId}`），路线 1 必须**按 work 汇总**（分页 + 去重）。

### 7.6 ★ 路线 1 已落地：`x_component_MyOnlineDocs`（「我的在线文档」）

2026-09-30 交付。真源 `deploy/runtime/webroot/x_component_MyOnlineDocs/`（构建期 `webroot.seed` 收录，
清卷重建会自动补种）；回归脚本 `tools/o2_mydocs_ui_verify.js`。

**实测可用的 4 个接口**（`PP = x_processplatform_assemble_surface`）：

| 用途 | 调用 | 备注 |
|---|---|---|
| 我的待办 | `GET  {PP}/jaxrs/task/list/my/paging/{p}/size/{s}` | ★ 是 **GET**；POST 会 405 |
| 我的已办 | `POST {PP}/jaxrs/taskcompleted/list/my/filter/{p}/size/{s}` body `{}` | 返回数组（非分页对象） |
| 我参与/发起 | `POST {PP}/jaxrs/work/list/my/paging/{p}/size/{s}` body `{}` | 每项 `id` 即 workId |
| 单据附件 | `GET  {PP}/jaxrs/attachment/list/workorworkcompleted/{workId}` | 返回 `id/name/extension/length/person/activityName/control.allowEdit` |

- `my` 前缀是**服务端强制当前用户**语义（不传 person）⇒ 天然"只看自己看得见的"，
  普通用户与管理员行为一致，**不需要也不应该**自己传 person。
- 打开：`layout.openApplication(null,"OnlyOfficeEditor",{documentId:<attId>, mode:"view"|"edit",
  jars:"x_processplatform_assemble_surface", appId:"MyOnlineDocs_"+id})`
  —— 与表单内「附件→在线预览」逐字一致（`x_component_process_Xform/$all.js:27290`）。
- 量级控制：`PAGE_SIZE=200` + 附件请求并发 6（9 人规模下 1–2 秒出结果）。
- 入口注册踩的坑（字典 `data` 必须传对象、分组折叠要先 click）见
  技能 `o2oa-custom-desktop-component` 的铁律 4B 与「验证必须走真实路径」。

### 7.7 三条产品规则（2026-09-30 追加）与两个"静默失效"坑

用户明确的三条约束，已固化进组件（`mydocs/mydocs.js` 顶部注释亦写明）：

1. **与流程扭转状态绑定**：单据提交流转出我的手 ⇒ 文档**只读**、不提供编辑入口。
   判据与服务端**完全同源**：`WorkControlBuilder.computeAllowSave() = canManage() || hasTaskWithWork()`
   ⇒ 本组件取 `editable = 该 job 上有我的待办`（`task/list/my` 命中即 `todo`）。
   ★ **不能用附件接口返回的 `control.allowEdit`** —— 它来自表单控件的静态 ACL，
   `BaseAction.edit()` 在 `editIdentityList/editUnitList` 为空时**恒 true**，与流程状态无关。
   ★ 还做了**双重保险**：`openDoc(row, mode)` 里 `if (!row.editable) mode = "view"`。
2. **目录化**：左侧「模块(应用) > 流程 > 来源单据」三级，便于回溯定位（数据来自 work/task 的
   `applicationName` / `processName` / `title`）。
3. **只收录流程文档、不当网盘**：数据源全部是流程平台 REST，**不触碰** `x_file/x_pan/x_cms/x_onlyofficefile`。

#### 坑 A（★ 真 bug，静默失效、零报错）：树展开态的键两处各拼各的

```js
// 点击处理器（错）                     // renderTree 读取（对）
lv + ":" + (data-app || "") + ":" + key   "app:" + app.name + ":"
```
一级模块节点**没有 `data-app` 属性** ⇒ 写入 `app::用印申请`、读取 `app:用印申请:` ⇒ 永远读不到 ⇒
**一级点不开、二三级永远渲染不出来**（控制台无报错，只有回归脚本能抓）。
修法：抽出唯一函数 `Viewer.expandKey(lv, appName, key)`，**写入与读取都调它**。
> 教训：任何"写入键/读取键"分离的状态，都要过一次同一个工厂函数；否则必然发散。

#### 坑 B（★ 改了等于没改）：`.min.js` 副本与 `VERSION` 未同步

`Main.min.js` 是旧副本（缺 `__lastViewer`），`VERSION` 也没随功能改动递增
⇒ ① 回归脚本断言用的实例钩子取不到；② 浏览器可能命中旧 `mydocs.js` 缓存。
纪律：**改 `Main.js` / `mydocs.js` 后必须同步 `*.min.js` 并递增 `VERSION`**（本实例做法：
`cp Main.js Main.min.js`、`VERSION="20260930d"`，因为框架只需 `Main(.min).js` 二者之一存在且内容一致）。
> 回归脚本据此加了独立断言 `Main.js 暴露 __lastViewer（真机断言钩子）` —— 把"钩子丢了"变成显式失败而不是崩溃。

#### 规则 3 的验证要"反向核对"才成立（★ 方法论）

只说"没调用文件库接口"是**弱证据**。要证明"不当网盘"，必须做**反证**：

1. 枚举**企业网盘真实文件名**（`x_file_assemble_control` 的 `folder2/list/top`
   + `attachment2/list/folder/{id}`；注意 Drive 用的是 **folder2/attachment2** 这组新接口，不是 `folder/attachment`）。
2. 与在线文档列表求交，断言交集为空。
★ 关键：网盘里放了 `.txt`（**正落在组件的扩展名白名单内**）⇒ "没出现"证明的是**数据源隔离**，
而非"扩展名恰好不匹配"。另加运行时**网络取证**（`page.on('request')` 统计 `/jaxrs` 调用直方图，
本实例 `{"/x_processplatform_assemble_surface":107}`、越界 0）。

回归脚本：`tools/o2_mydocs_lock_verify.js`（①②③ 共 15 项断言，实测 15/15 PASS，控制台错误 0）。

---

## 8. ★ AI 页签"开箱可用"：预置注入（2026-09-30 落地，11/11 真机 PASS）

### 8.1 先纠正一个常见误判

「AI 配好了吗？为什么还不能用？」——**网关通 ≠ 能用**。插件配置是**浏览器端状态**：

| 键（浏览器 localStorage，DS 域） | 内容 |
|---|---|
| `onlyoffice_ai_plugin_storage_key` | 提供方（url/key）+ 模型清单，带 `version`（当前 `AI.Storage.Version = 4`） |
| `onlyoffice_ai_actions_key` | 动作→模型绑定（Chat / Summarization / Translation / TextAnalyze / …） |

用户在设置里配的东西**只在那台电脑那个浏览器**。所以"服务端预置"才是正解。
（动作合并**只覆盖 `model` 字段**：`if (AI.Actions[i] && obj[i].model) AI.Actions[i].model = obj[i].model;`
⇒ 预置 actions 只需 `{"Chat":{"model":"<id>"}}`。）

### 8.2 四条被推翻的直觉（都有源码级证据，别再走一遍）

1. **URL 填 `:18790` 就够** → 错。`engine.js:341 AI._getEndpointUrl()` = `url`+（addon 非空则 `"/"+addon`）+ 相对端点；
   **自定义提供方 addon 为空**（`base.js createProviderInstance` 回落 `new AI.Provider`）⇒ **URL 必须自带 `/v1`**。
2. **用官方 `aiSettings` 服务端下发** → 本版插件不通。DS `default.json` 顶层确有
   `aiSettings{actions,models,providers,version,timeout,allowedCorsOrigins,proxy}`，链路是
   docservice(`getPluginSettingsForInterface`) → `Asc.plugin.info.aiPluginSettings` → `code.js:717`。
   但 SDK 的注入条件是 `if (this.api.aiPluginSettings && eventMap["onAIPluginSettings"])`，
   **插件 `config.json` 的 variations 没有 `eventsMap`**（`grep -c` = 0，`.gz` 同）⇒ 恒假。
   另：`serverSettings` 一旦生效会走 `serverSettings.proxy`（`engine.js:146/338`）并**隐藏设置按钮**，直连场景更差。
3. **补丁烤进镜像（Dockerfile RUN）** → **物理上不可能**。实测官方镜像
   `sdkjs-plugins/` 只有 `marketplace v1 pluginBase.js plugin-list-default.json plugins.css`；
   `{GUID}` 插件目录是容器启动时由 `documentserver-pluginsmanager.sh`
   （官方 entrypoint **807-808 行**，`--update=plugin-list-default.json`，清单里 11 个插件名）现装的。
   → 构建阶段那个文件**不存在**（实测 `目标文件不存在`）。
4. **预置对了、插件帧内 fetch 也 200，窗口就一定会开** → 错。**只读预览下会被 DS 编辑部静默丢弃**，
   见 §8.8（用户反馈"点了没反应"的真根因，实测帧数恒 4、零报错）。

### 8.3 可行方案：薄镜像 + 启动包装（等插件落盘再注入）

```
onlyoffice/Dockerfile                  # FROM official；只 COPY 3 个小文件；ENTRYPOINT 换包装脚本
deploy/host/onlyoffice/o2_ds_entrypoint.sh   # 起官方 entrypoint → 后台等插件稳定 → 注入 → 补 zh-ZH → wait PID1
tools/o2_patch_ds_ai_plugin.py               # 幂等注入器：BEGIN/END 标记就地替换 + 同步重生成 .gz + --wait SEC
deploy/host/onlyoffice/ai-plugin/preset.json # 单点真源（提供方名/URL/默认模型/模型清单/绑定动作）
```

注入语义 = **播种**：`if (!localStorage.getItem(K)) localStorage.setItem(K, …)` —— 空库才写，
**用户自己配过的不被覆盖**；`AI.serverSettings` 保持为空 ⇒ 浏览器直连（CORS 已放）+ 设置按钮保留。
因为每次启动都跑（幂等），`docker restart` 与 `compose up -d` 重建容器都覆盖得到。

### 8.4 两个硬坑（★ 都会造成"改了等于没改、且无报错"）

- **`.js` 必须与 `.gz` 同步**：DS 的 nginx 对 `sdkjs-plugins` 走 **gzip_static**，目录里有
  `local_storage.js.gz`；只改 `.js`，浏览器继续吃旧包。⇒ 写完必重生成 `.gz`，且 `.gz` mtime 要晚于源文件。
- **锚点不存在必须报错退出**，不能"什么都没做还返回 0"。锚点：`var AI = exports.AI;`（唯一命中）。

### 8.5 验证要"插件帧内真实对话"才算数

`tools/o2_ai_plugin_verify.js`（11 项断言，实测 11/11 PASS）：登录 → 我的在线文档 → 预览第一行
→ 等 `frameEditor` → 点 **AI** 页签 → 在**插件自己的 iframe** 内断言 provider/models/actions
→ 再用**插件自己的代码路径**（`AI.Storage.getProvider` → `AI._getEndpointUrl` → `fetch`）发一次请求：
实测 `POST http://<LAN>:18790/v1/chat/completions` → 200、`content="通过"`。
★ 只测"服务端 curl 通了"不算通过 —— 必须是真实 origin + 真实 CORS + 真实插件逻辑。

### 8.6 顺手修掉的常驻 404

编辑器 `lang=zh` 时插件请求 `translations/helpers/zh-ZH.json`，官方只带 `zh-CN.json`
（实测 `zh-CN` 200 / `zh-ZH` 404）⇒ 控制台常驻 404、部分中文辅助文案回落英文。
用 `zh-CN` 复制出 `zh-ZH`（`translations/` 与 `translations/helpers/` 两处 + `.gz`）后 4xx 归零。

### 8.7 ★ 合规提醒：DS 容器没封网、启动期从 CDN 装插件

- 插件目录不在镜像内、且于容器启动后 ~96s 出现（实测 `StartedAt=10:28:34` / 插件目录 `mtime=10:30:10`），
  镜像内也无 43MB 级本地包源 ⇒ **启动期从网络安装 11 个插件（约 43MB）**；
- 该容器内**没有 iptables**（O2OA 主容器有 entrypoint 自愈的 egress 规则，DS 没有）。

收敛必须**两步一起做**：先把插件目录持久化（导出到卷/镜像 + `PLUGINS_ENABLED=false`）**再**封网；
只封网不做持久化 ⇒ 重建容器后插件装不上，**AI 页签会整个消失**。

### 8.8 ★★ 点了「聊天机器人」没反应：只读预览被 DS 自己的判据挡掉（2026-09-30 实证）

**症状**：预置 11/11 PASS、插件帧内 `POST …:18790/v1/chat/completions` 也 200，
但用户从「我的在线文档 → **预览**」进去点 AI → 聊天机器人：**什么也不发生**（无窗口、无报错、帧数不变）。

**排查次序**（逐层往下，别跳步）——每层都有可复跑的判据：

| 层 | 怎么验 | 结果 |
|---|---|---|
| 预置 | 插件帧内 `AI.Storage.getModelById(AI.Actions[AI.ActionType.Chat].model)` | `resolved=true` |
| 插件早退分支 | 打桩 `AI.Request.create` → 插件 `register.js:62 if (!Request.create(Chat)) return;` | `ok`，**没早退** |
| 开窗调用 | 打桩 `Asc.PluginWindow.prototype.show` | 被调用，`type=window url=chat.html` |
| 消息发送 | 打桩 `Asc.plugin.executeMethod` | **`ShowWindow` 已发出** |
| 编辑器接收 | 读 `web-apps/apps/common/main/lib/controller/Plugins.js:1267` | ★ **`visible=false` ⇒ 静默不建窗** |

**真根因（DS 编辑器侧，不是插件侧）**：

```js
// web-apps/apps/common/main/lib/controller/Plugins.js:1267
var visible = (this.appOptions.isEdit || this.appOptions.canSubmitForms
               || variation.isViewer && (variation.isDisplayedInViewer !== false))
              && _.contains(variation.EditorsSupport, this.editor) && !isSystem;
if (visible && isPanel)            this.onPluginPanelShow(...);
else if (visible && !variation.isInsideMode) this.onPluginWindowShow(...);
```

官方插件 `register.js` 的 `chatWindowShow()` 里 `variation` **没有 `isViewer`**
⇒ 只读预览（`mode=view`，`isEdit=false`）下三项取或全假 ⇒ **窗口根本不建，且不报错**。

**修法（纯加法、幂等，已并入同一个注入器）**：在 `register.js` 的锚点 `url : "chat.html",` 后插

```js
/* O2OA-AI-VIEWER-BEGIN */
      isViewer : true,
      isDisplayedInViewer : true,
/* O2OA-AI-VIEWER-END */
```

`tools/o2_patch_ds_ai_plugin.py` 的 `patch_register()` 会自动处理（`register.js` 与 `local_storage.js`
同在 `scripts/engine/`，由 `--file` 推导 ⇒ entrypoint 那条命令不用改），**同样同步重生成 `.gz`**，
锚点不唯一/不存在即报错退出。重建容器后核对（两处都应为 1）：

```bash
G='{9DC93CDB-B576-4F0C-B55E-FCC9C48DD007}'
docker exec o2oa-onlyoffice sh -c "cd …/sdkjs-plugins/$G/scripts/engine && \
  echo preset=\$(grep -c O2OA-AI-PRESET-BEGIN local_storage.js) viewer=\$(grep -c O2OA-AI-VIEWER-BEGIN register.js)"
```

**两条边界（实测，别再踩）**：

- **形态差异**：只读预览下 DS **只认独立弹窗**（`type=window`）；`panelRight`（停靠右栏）
  在预览里**不只是被忽略——是直接崩溃**（见 §8.9 坑 A）。编辑模式下两种形态都可用，
  但"两栏"统一走 §8.9 的 DOCK 块方案。
- `isViewer` 只解锁"聊天"；只读文档里**插回内容**（`InsertAsHTML` / `ReplaceTextSmart`）仍会被只读保护拒绝
  —— 预期行为，不是缺陷。

**取证脚本**：`tools/o2_ai_chat_e2e.js`（`O2_ACT=view|edit`）——真机走完整 UI，
判据 = 聊天窗帧(chat.html)出现 + `#chat` 内 >30 字回答 + `pageerror` 为空，并落截图。
实测：预览（浮动窗）与编辑（右栏停靠）**两态都通过**，证据见
`docs/knowledge_base/assets/ai_plugin_20260930/`（含修复前"无窗口"对照图）。

### 8.9 ★★★ 补坑二：「两栏布局 + 工具空转 Maximum iterations」（2026-09-30 深夜实证）

用户要"聊天界面在右边空白区、与文档形成两栏"，顺带暴露两个更深的坑。

#### 坑 A：panelRight 在 view 模式是【崩溃】，不是"被忽略"

playwright 取证（`tools/o2_ai_panel_probe.js`）：

```
onPluginPanelShow → RightMenu.addNewPlugin → SideMenu.insertButton
  → this.btnMoreContainer.before($button)
  → TypeError: Cannot read properties of undefined (reading 'before')   (SideMenu.js:96)
```

view 模式下右侧栏 `RightMenu` 的 view 分支 `render()` 不被调用 ⇒ `btnMoreContainer` 恒 undefined
⇒ **panel 插不进 DOM，聊天窗彻底不出现、零报错**。原生 panelRight 在 view 模式物理不可用。
⇒ `preset.json` 定 `chatPlacement: "window"`，注入器带 v1.1→v1.2 迁移
（老用户 localStorage 里的 `panelRight` 自动回退）。

#### 两栏落法 = DOCK 块（window 形态 + CSS 钉右）

不靠 DS 面板机制。注入器在 `register.js` 末尾（锚 `window.chatWindowShow = chatWindowShow;`）注入
`O2OA-AI-DOCK-BEGIN/END` 块：在插件帧里把样式注入**父文档（编辑器帧）**——
`iframe[src*="chat.html"]` 钉到 `right:0; width:420px; height:100%`、`#editor_sdk{margin-right:420px}`、
空壳 `.asc-window` 藏掉，`MutationObserver` 动态停靠/还原。view/edit 通用
（实测几何 `x=1140 w=420 h=923 / 视口 1560×923`）。

#### 坑 B：writeMacro 恒返回空 ⇒ 工具空转至 "Maximum iterations reached"

取证链（`tools/o2_ai_macro_unit.js` 隔离 C/D）：

- 命令上下文里：`typeof eval === "function"` 但 `eval("2+2") === undefined` 且不抛错；
  `Function` 不是构造函数；**Api 完全可用**。
- 插件帧里：`new Function` 可用，造出的 runner 交给 `Asc.Editor.callCommand` 正常执行、能返回值。

**根因：DS 9.4 编辑命令上下文封死动态求值**，官方 writeMacro 是 `eval(Asc.scope.macroCode)`
（helpers.js word/cell/slide 三处相同）⇒ 恒 undefined ⇒ 模型拿不到文档 ⇒ 空转 10 轮。
与 §0 的 `[functionCalling` 泄漏（协议层，capabilities 缺 Tools 位）**相互独立、两层都要修**。

修法（注入器第 5 处补丁，×3 处）：整块换成「插件帧 `new Function` 预编译 runner →
`callCommand(runner)`」；末表达式→`return (…)` 的语义变换（模型显式 `return` 亦兼容）；
无返回值时回给模型一句可行动提示（"末表达式必须是取值表达式，不要以 var/forEach/if 收尾"），
模型据此自我纠正，不再盲目重试。

**护栏教训（差点闯祸）**：helpers.js 有 **39 个** `func.call = async function(params) {`（每工具一个）。
"已注入"正则若只锚 `func.call`，非贪婪 `.*?` 会从第一个工具一路吞到 END 标记，把中间 35 个工具
全删掉（实测 296315→25981 字节，`node --check` 还能过——括号恰好平衡）。铁律：
**已注入正则必须锚 BEGIN 标记紧跟块开头** + 写前三护栏（func.call 数 1:1 / 标记数=3 / 无残留 eval 式）。

**排除记录**：`callCommand` 返回值**没有尺寸上限**（50 万字符实测完好回传）——
"读全文为空"不是传输问题，是无返回值形态问题。

**容器内核验（重建镜像后启动期自动注入，全绿）**：
`PRESET=1 / isViewer=1 / DOCK=1 / MACRO=3 / func.call=39 / 残留 eval 式=0`，`--check` 全过。
e2e：`O2_ACT=view|edit node tools/o2_ai_chat_e2e.js` —— 两态 8/8 PASS，
落定判据 = 最新消息非工具块（`$chat.prepend` ⇒ 新消息在上）+ 文本稳定 + 9 秒二次确认。
