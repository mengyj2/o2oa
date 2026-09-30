---
name: o2oa-onlyoffice-attachment-preview
description: 诊断并修复 O2OA（社区版 / Docker 自托管，10.0.2 实证）里「表单附件点开是下载（用本地阅读器打开）而不是在线预览」，以及「附件控件 officeTool 选了 OnlyOffice 却打不开编辑器」。当用户说"附件在线打开却走下载""预览按钮是灰的/点了没反应""双击附件直接下载""onlyoffice 在系统里预览不了""改了表单配置没生效/验证了还是下载""本机能打开但其它机器打开是白板""白板是不是缓存原因"时调用。含四层真根因：①附件控件配置（isPreviewAtt / dblclick / officeTool）②前端组件 x_component_OnlyOfficeEditor 缺失（社区版 zip 不自带）③★★ 表单 HTTP 强缓存 cacheTag=CRC32(表单id+updateTime)——直接改库不动 updateTime 等于没改 ④★★ 浏览器侧地址 docserviceApi/gobackUrl 写死 localhost——单机能用、局域网其它机器白板（服务端地址走容器内网 172.22.0.x，浏览器地址必须填宿主 LAN IP，两类别混）。
agent_created: true
category: troubleshooting
---

# O2OA 附件「在线打开 / 在线预览」四层根因与修复

> 实证环境：O2OA 10.0.2 社区版 / Docker（`o2oa-server`）+ MySQL 8（库 `X`）+ 独立 OnlyOffice DocumentServer 容器（同 `o2oa-net`）。
> 首个案例：流程「用印申请单」附件点开一直下载（Windows 用本地 Word 打开）。

## 0. 30 秒判定树（先定位在哪一层，别猜）

```
点附件 → 浏览器下载文件？
├─ 是 → 第 1 层：表单附件控件配置（isPreviewAtt="n" / dblclick="open" / 无 officeTool）
│        改完库还是下载 → 第 3 层：前端 HTTP 强缓存（cacheTag 没变）
├─ 否，但"预览/打开"点了没反应（或控制台 404 x_component_*） → 第 2 层：前端组件缺失
└─ 否，编辑器区域白板/空白？
     ├─ 宿主本机能预览、局域网其它机器白板 → ★ 第 4 层：docserviceApi / gobackUrl 写死 localhost
     └─ 所有机器（含宿主）都白板 → 查 DocumentServer / 端口映射 / 防火墙（见 §3）
```

四层**互相独立**，必须**逐层验证**，否则会出现"改完验证了还是老样子"的假失败。

## 1. 链路全景（代码级，10.0.2 行号实证）

点击/双击附件 → `o2_core/o2/widget/AttachmentController.js`

```js
dblclickAttachment(e, node, attachment){          // 第 1349 行
    if (... this.options.dblclick === "disable") return;
    else if (this.options.dblclick === "preview") {
        if (this.checkPreviewAttachment) this.checkPreviewAttachment(...);   // 1353
        else this.module.openAttachment(...);                                // ★下载
    } else this.module.openAttachment(...);                                  // ★下载
}
```

* `checkPreviewAttachment` 定义在 **Xform 子类** `x_component_process_Xform/Attachment.js:1482`
  （类 `MWF.xApplication.process.Xform.AttachmentController`，`Extends: MWF.widget.ATTER`）。
  它对 `doc/docx/xls/xlsx/ppt/pptx` 一律 `flag=true` → `module.previewAttachment()`。
* `module.previewAttachment`（同文件 `:2224`，属类 `Xform.Attachment`，文件 1546 行起）
  → `new AttachmenPreview(att, this)`（类定义 `:2828`，`initialize(att, app)` 里 `this.app = app`）
* `AttachmenPreview.load()`（`:2834`）按扩展名分流 → `previewOffice()`（`:3046`）

```js
previewOffice: function(){
    switch (this.app.json.officeTool) {   // ★ 读的是【附件控件自己的 json】(this.app = 控件模块)
        case "OnlyOffice": this.previewOnlyOffice(); break;
        default:           this.previewLibreOffice();   // 无 officeTool 的默认分支
    }
}
previewOnlyOffice(){ layout.openApplication(null, "OnlyOfficeEditor", {documentId, mode:"view", jars, appId}); }
previewLibreOffice(){ window.open("../o2_lib/pdfjs/web/viewer.html?file=" + x_libreoffice/jaxrs/office/doc/to/pdf/<module>/<attId>); }
```

控件级配置项（表单设计器属性面板 `x_component_process_FormDesigner/Module/Attachment/attachment.html`
第 162/178/217 行实证）：

| 键 | 取值 | 作用 |
|---|---|---|
| `isPreviewAtt` | `y` / `n` / `hidden` | 工具栏「预览」按钮 启用 / 禁用 / 隐藏（默认 n） |
| `dblclick` | `open` / `preview` / `disable` | 双击+行内「打开」按钮：下载 / 走预览 / 不响应（默认 open=下载） |
| `officeTool` | `OnlyOffice`/`WpsOffice`/`YozoOffice`/`OfficeOnline`/`LibreOffice` | 预览/编辑用哪个在线套件；**缺省走 LibreOffice** |

## 2. 四层根因与修法

### 第 1 层：附件控件配置（最常见）

表单 `data` json 里 `moduleList.<控件id>` 上通常是
`{"isPreviewAtt":"n","dblclick":"open","isDownload":"y"}`（无 `officeTool`）
⇒ **双击=下载、预览按钮不可点**，服务端配得再对也没用。

修法（PC + 移动端两列都要改；存储是**双重转义** json，DB 里形如 `\"isPreviewAtt\":\"n\"`）：

```sql
-- 注意：'\\"' 在 MySQL 字面量里 = \"，正好对上库里的转义形态
UPDATE PP_E_FORM SET
  xdata = REPLACE(REPLACE(xdata,
      '\\"isPreviewAtt\\":\\"n\\"', '\\"isPreviewAtt\\":\\"y\\",\\"officeTool\\":\\"OnlyOffice\\"'),
      '\\"dblclick\\":\\"open\\"',  '\\"dblclick\\":\\"preview\\"'),
  xmobileData = REPLACE(REPLACE(xmobileData,
      '\\"isPreviewAtt\\":\\"n\\"', '\\"isPreviewAtt\\":\\"y\\",\\"officeTool\\":\\"OnlyOffice\\"'),
      '\\"dblclick\\":\\"open\\"',  '\\"dblclick\\":\\"preview\\"')
WHERE xid='<formId>';
```

* `officeTool` 是 **Gson 不序列化 null** 的键 → 必须**插入**而不是替换。
* 列名是 `xmobileData`（**不是** mobileData）。
* 预演/复验用字节差计数：`LENGTH(xdata)-LENGTH(REPLACE(xdata,'<pat>',''))`。
* 官方接口取表单核对：`GET /x_processplatform_assemble_designer/jaxrs/form/{id}`（GET 安全；
  ★**不要**用 `ActionEdit`/designer 保存链路改表单，会重算 `relatedScriptMap`）。
* 只想用本地 LibreOffice 预览（不引 OnlyOffice）→ `officeTool` 填 `LibreOffice` 即可。

### 第 2 层：前端组件 `x_component_OnlyOfficeEditor` 缺失（社区版必踩）

`previewOnlyOffice()` 走的是 `layout.openApplication(null,"OnlyOfficeEditor",...)`
→ `MWF.xDesktop.requireApp("OnlyOfficeEditor","Main")` → `o2.requireApp` 拼出
`../x_component_OnlyOfficeEditor/Main.js`。**社区版官方 zip 的 `servers/webServer/` 里没有这个组件**
（它属官方插件包 `ONLYOFFICE集成应用.zip` 的 `web/` 部分）。

判定：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9090/x_component_OnlyOfficeEditor/Main.js   # 404 = 缺
```

修法：把插件包 `web/x_component_OnlyOfficeEditor/` 放到 **webroot**（自定义组件真源卷），
不是 `servers/webServer/`（那里只放内置组件）：

```bash
export MSYS_NO_PATHCONV=1                      # 否则容器内 /opt/... 被 MSYS 改写
docker cp D:/O2OA/deploy/runtime/webroot/x_component_OnlyOfficeEditor o2oa-server:/opt/o2server/webroot/
docker restart o2oa-server                     # ★ 新组件目录必须重启才挂上
```

持久化（重建不丢）——Dockerfile 两处：

```dockerfile
COPY deploy/runtime/webroot/x_component_OnlyOfficeEditor ${O2OA_HOME}/webroot/x_component_OnlyOfficeEditor
RUN mkdir -p ${O2OA_HOME}/webroot.seed \
    && cp -r ${O2OA_HOME}/webroot/x_component_PlanDecompose ${O2OA_HOME}/webroot.seed/ \
    && cp -r ${O2OA_HOME}/webroot/x_component_OnlyOfficeEditor ${O2OA_HOME}/webroot.seed/
```
（`webroot` 是**命名卷**，会遮蔽镜像内目录；`webroot.seed` + entrypoint 的
 `cp -rn webroot.seed/. webroot/` 才是"卷已存在时也能补新组件"的正解。）

**注意别把 xAction 当成缺件**：`MWF.Actions.load(服务名)` 走的是
`{服务host}/{服务}/describe/api.json`（`o2_core/o2/xAction/RestActions.js:20-48`），
**不读** `o2_core/o2/xAction/services/*.json`（那是老接口 `MWF.Actions.get()` 用的）。
所以插件服务没有 `xAction/services/*.json` 是正常的，只要 `describe/api.json` 200 即可：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9090/x_onlyofficefile_assemble_control/describe/api.json
```

### 第 3 层：★★★★ 表单 HTTP 强缓存（"改了等于没改"的元凶）

前端取表单是两跳（`x_component_process_Work/Main.js:196-270`）：

```
lookupFormWithWork(workId) → GET /x_processplatform_assemble_surface/jaxrs/form/v2/lookup/workorworkcompleted/{workId}
                             → {id: formId, cacheTag: "673446602"}
getFormV2(formId, cacheTag) → GET /jaxrs/form/v2/{formId}?t={cacheTag}      ← URL 里只有 cacheTag 会变
```

```java
// x_processplatform_assemble_surface/.../jaxrs/form/V2LookupWorkOrWorkCompleted.java:57-65
list.add(this.form.getId() + this.form.getUpdateTime().getTime());   // ← 版本号 = 表单id + updateTime
CRC32 crc; crc.update(StringUtils.join(list, "#").getBytes());
this.wo.setCacheTag(crc.getValue() + "");
```

`getFormV2` 的响应头是 **`Cache-Control: no-transform, max-age=86400`**（`maxAge=86400`）。
⇒ 只要 `updateTime` 不变，`?t=` 就不变，**浏览器 24 小时内直接命中强缓存、连请求都不发**。
用 SQL 直接改 `xdata` 而不动 `xupdateTime` ⇒ 前端永远看到旧配置 ⇒ 用户"验证了还是下载"。

**修法：改完 `xdata`/`xmobileData` 必须同时顶 `xupdateTime`（写成宿主本地时间，JVM TZ=Asia/Shanghai）：**

```sql
UPDATE PP_E_FORM SET xupdateTime='2026-09-30 14:40:21' WHERE xid='<formId>';
```

自查（cacheTag 必须变化）：

```bash
# 改前 673446602 → 改后 2393565856（只要 CRC 变了，前端 URL 就变，缓存自然失效）
curl -s -H "x-token: $TOK" .../form/v2/lookup/workorworkcompleted/<workId>
```

副作用提醒：**任何**绕过 designer 直接 UPDATE `PP_E_FORM.xdata` 的操作都要带这一步；
`getFormV2` 还会返回 `fastETag = formId + updateTime(ms)`，同理依赖 updateTime。

### 第 4 层：★★★★ 别的机器打开是【白板】（浏览器侧地址写死了 `localhost`）

**现象**：宿主本机点附件能在线预览，局域网**其它机器**打开同一张单子时编辑器区域是**空白/白板**。

**先排除三件事（都不是）**：
* ❌ **不是浏览器缓存** —— 其它机器从没访问过该页面，没有旧缓存可命中；`getConfig` 实测**无 `Cache-Control`**。
* ❌ **不是表单缓存 cacheTag**（那是第 3 层的问题，且只影响表单 JSON）。
* ❌ **不是 DocumentServer / JWT / 容器网络** —— 本机能打开就证明"DocumentServer 拉 O2OA 文件"整条链路是通的。

**真根因**：`onlyofficeFileSettings.json` 里有**两类地址**，作用域完全不同，混填就会出这个问题：

| 字段 | 谁访问它 | 正确取值 | 填错的后果 |
|---|---|---|---|
| `docserviceApi` / `docservicePreloader` | **浏览器**（`o2.load(api.js)`） | ★ 访问者浏览器可达的地址，如 `http://<宿主LAN IP>:8800/...` | 填 `localhost` → **别的机器**的 localhost 是它自己 → api.js 404 → **白板** |
| `gobackUrl` | **浏览器**（编辑器"关闭"返回） | 同上，`http://<宿主LAN IP>:9090/...` | 其它机器点关闭跳到自己机器的 9090 |
| `docserviceConverter` / `docserviceTempstorage` | DocumentServer 容器 → 自己 | 容器内网 `http://172.22.0.50:80/...` | 改成 LAN IP 反而依赖宿主 NAT 回环 |
| `downLoadUrl` + `document.url`/`callbackUrl` | DocumentServer 容器 → O2OA 容器 | 容器内网 `http://172.22.0.20:9090/...` | 同上前提 |

> 一句话：**服务端↔服务端走容器内网（172.22.0.x）；浏览器→服务端必须填对外可达地址。**
> `localhost` 只在"访问者 == 宿主本机"时成立 —— 这正是单机能用、多机白板的全部原因。

**一键自查**（把 `localhost` 换成 LAN IP 访问）：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8800/web-apps/apps/api/documents/api.js   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.x.x:8800/web-apps/apps/api/documents/api.js # 必须也 200
```

两处都 200 ⇒ 端口映射/防火墙没问题（`wslrelay` + `com.docker.backend` 双栈监听，Docker Desktop 自带
"Docker Desktop Backend" 入站允许规则）；**只是配置里的 hostname 写错了**。

**修法（两处都要改，只改一处会被还原或换机复发）**：

```bash
# ① 真源（可复现：Dockerfile COPY + compose bind mount 到 /opt/o2server/onlyoffice.seed.json）
#    改 deploy/host/onlyoffice/onlyofficeFileSettings.json 的 3 个浏览器侧字段 → 宿主 LAN IP
# ② 运行态（立即生效，走官方接口，免重启；会顺带触发 refresh）
POST /x_onlyofficefile_assemble_control/jaxrs/onlyofficeconfig/save   # body = 改后的整份 JSON
```

验证：`GET .../onlyofficeconfig/get` 应回新地址；`appFileEdit` 的 `document.url`/`callbackUrl`
**仍应是 172.22.0.x 容器内网**（别手贱一起改成 LAN IP）。

**★★ 陷阱：`entrypoint.sh` 的 `onlyoffice-selfheal` 自愈会重写运行态。**
它的判据**只看 `downLoadUrl` 是否含 `172.22.0.20`**，满足就跳过、不覆盖人工改动 ——
所以改完 config 卷**不会被还原**（前提是 `downLoadUrl` 保持内网值）。
但**只管磁盘不改 seed** 的话，新机器首启 / 重建镜像仍会写入 localhost 版本 ⇒ 必须同时改 seed 真源。

**★★ 收尾提醒（DHCP）**：LAN IP 是 DHCP 分配的话会变，IP 一变白板重现。
* 稳法 A（运维层，推荐）：路由器做 DHCP 保留 / 宿主设静态 IP。
* 稳法 B（代码层，IP 无关）：改 `x_component_process_Xform/OnlyOffice.js` 的 `loadApi()`，
  把 `docserviceApi` 的 host 替换成 `location.hostname` + 固定 `:8800` —— 任意访问地址自适应。

## 3. 服务端（OnlyOffice）就位清单

| 检查项 | 命令 | 期望 |
|---|---|---|
| 服务 war | `curl -o /dev/null -w '%{http_code}' http://localhost:9090/x_onlyofficefile_assemble_control/describe/api.json` | 200 |
| 运行态配置 | `GET /x_onlyofficefile_assemble_control/jaxrs/onlyofficeconfig/get` | `docserviceApi` = **浏览器可达**地址（★ 多机访问必须用 `http://<宿主LAN IP>:8800/...`，**不能用 localhost**，见第 4 层）、`secret` 非空 |
| DocumentServer | `curl -o /dev/null -w '%{http_code}' http://localhost:8800/healthcheck` | 200 |
| JWT 一致 | 容器 env `JWT_SECRET` == 配置 `secret`（本机 `o2oa_local_onlyoffice_secret`） | 相等 |
| 容器互通 | `docker exec <onlyoffice容器> curl -s -o /dev/null -w '%{http_code}' http://<o2oa容器IP>:9090/x_desktop/index.html` | 200（编辑器配置里的 `document.url`/`callbackUrl` 是 **容器内网地址**，DocumentServer 要能取到） |
| 取编辑器配置 | `POST /x_onlyofficefile_assemble_control/jaxrs/onlyoffice/app/file/edit` body `{"appToken":"x_processplatform_assemble_surface","mode":"view","fileId":"<attId>"}` | 200 且返回 `fileModel.document.url` / `editorConfig.callbackUrl` |

## 4. 收尾清单

1. 任何静态/新组件 → `docker restart o2oa-server`（QEMU 下约 1-4 分钟，探 `x_desktop/index.html` 200 即就绪；注意静态页先 200，**服务**可能还在起，用登录接口实测）。
2. 改库前 `mysqldump` 备份整行到 `D:/O2OA/backups/form-<名>-<ts>/`。
3. 临时诊断脚本用完删（`C:/temp/...`）。
4. 提交：Dockerfile + 组件 + `docs/knowledge_base/` 复盘，显式列文件（禁 `git add -A`）。

## 5. 其它坑（本案例踩到）

* **`\\"` 转义层级**：库里是双重转义 json；用 `mysql -e "..."` 时 shell 会再吃一层反斜杠 →
  复杂 SQL 一律写成 `.sql` 文件再 `docker cp` 进 mysql 容器执行（本次 `LIKE '%\"Attachment\"%'` 在 shell 里恒 0 命中，改文件后正常）。
* **`docker cp` 双向路径**：`MSYS_NO_PATHCONV=1` 下源/目标都要写 **`C:/...` / `D:/...`** 形式；
  写 `/c/temp/...` 会被当字面量 → `invalid output path`。
* **查附件**：`PP_C_ATTACHMENT`（列 `xname/xextension/xsite/xwork/xprocess/xbusinessId`），
  表单附件控件的 `xsite` = 控件 id（如 `attachment`）；`PP_C_WORK.xform` 才是流程实例真正用的表单 id。
* `x_component_OnlyOfficeEditor/Main.js`（官方版）第 59 行留着一句 `debugger;`——
  开着 F12 时点开附件会断住。属官方代码，介意的话删这一行（记 devtools 断点假象，别误判成"卡死"）。
