---
name: o2oa-portal-page-format
description: 写对 O2OA 门户页(portal page)的 page.data 格式，并让自定义 HTML 在门户里真正渲染出来；以及让门户显示【自建表真实数据】而不依赖视图引擎；以及门户内多栏目页（Tab）导航与页面间跳转的正确做法。当用户问"O2OA 门户/首页打开是空白/白屏""portal 页面不显示""门户页怎么放自己的 HTML""门户页能不能跑 script""O2OA 门户页 data 是什么格式""导入 xapp 后门户打不开""门户怎么显示自建表数据""视图执行报 ProcessPlatformPlan NPE""table 类型视图不工作""门户里的表格只有表头没有数据""门户导航点了没反应""门户怎么分类/怎么做多个栏目页""门户 tab 切换""openApplication 开新页签"时调用。覆盖 page.data 必须是表单定义 JSON 而非裸 HTML、双层 JSON 转义、Html 模块承载自定义 HTML、<script> 不执行要走 events.postLoad.code、CSS 必须限域到根节点、表单 DOM 骨架 html 字段、PortalPage.js 渲染链路实证、本版本 table 视图执行层无 TablePlan 的根因、自建表行接口直读 + 前端渲染方案、门户分类（portalCategory）与多栏目页设计惯例、toPortal vs openApplication 的页内切换差异，以及一套校验/端到端验证方法。
agent_created: true
category: development
---

# O2OA 门户页（portal page）数据格式与自定义 HTML 接入

适用 O2OA 10.x（Docker 自托管实测 10.0.2，`x_portal_assemble_surface`）。
**核心结论：门户页不是网页，是被当成「表单」渲染的数据对象。写裸 HTML 一定白屏。**

## 0. 一句话根因（★ 两层，缺一不可）

**第 1 层**：`page.data` 解码后必须是 **表单定义 JSON**：

```json
{ "json": {…表单定义…}, "html": "…表单 DOM 骨架…", "id": "", "isNewPage": false }
```

**第 2 层（更容易漏！）**：`.xapp` 里 / 库内 `xdata` 存的**不是上面这个 JSON 本身**，
而是它**再被 JSON 转义一次**的字符串（原生 `o2.encodeJsonString` 的产物）：

```
{\"json\": {…}, \"html\": \"…\", \"id\": \"\", \"isNewPage\": false}
```

为什么必须转义：前端固定链是
`JSON.decode(MWF.decodeJsonString(json.data.data))`，而
`o2.decodeJsonString(str)` 的实现（o2.js ~25896 行）是把 str **原样拼进** `["…"]`
再 parse。若 str 是未转义 JSON `{"json":…`，拼出 `["{"json":…` → 第一个 `"`
提前闭合字符串 → `SyntaxError: Unexpected identifier 'json'` → 白屏。
Python 侧：`escape_json_string(s) = json.dumps(s, ensure_ascii=False)[1:-1]`；
逆运算 `decode_json_string(s) = json.loads('"' + s + '"')`。

⚠ **不是所有实体都要转义**：只有经过 `decodeJsonString` 的字段（Form/Page 的 data、
mobileData 等）需要；QRY_VIEW / QRY_STAT / QRY_SCH_TABLE / 自建表 data 等原生存的就是
未转义 JSON。**按实体分别对待，别一刀切**。判定法：库内看原生数据形态
（`LEFT(xdata,3)='{"\'` 即 `{\` + `"` 开头 = 转义形态）。

写入裸 HTML（未转义）或裸 JSON（未转义）→ 前端解码抛错 → `this.page` 为 `null` →
`openPortal()` 静默空转 → **整页白屏，服务端日志无任何报错**。
唯一线索是「门户打开是空白」，极易误判为服务端/权限/网络问题。

⚠ **验证器教训**：端到端验证必须**完整复刻双层解码链**
（先 `decodeJsonString` 再 `JSON.decode`），只复刻一层会漏检——
曾出现「verify 全绿但浏览器白屏」，正是因为 verify 少做了一层解码。

## 1. 渲染链路（源码实证，不要凭猜）

`webServer/x_component_portal_Portal/PortalPage.js`：

```js
this.loadPortal = function(par){
  this.action.getApplication(portalId, ...)                     // 取门户
  this.action[layout.mobile?"getPageByNameMobile":"getPageByName"](pageId, portalId, function(json){
      this.page = (json.data.data) ? JSON.decode(MWF.decodeJsonString(json.data.data)) : null;
      this.openPortal(par);
  })
}
this.openPortal = function(par){
  if (this.page){                                               // ← null 就什么都不做
      MWF.xDesktop.requireApp("process.Xform", "Form", function(){
          this.appForm = new MWF.APPForm(this.formNode, this.page, {"macro":"PageContext","parameters":par});
          this.appForm.load();
      })
  }
}
```

即门户页 = **一个 Form**。内容由表单引擎按 `page.json.moduleList` 产出。

### 1.1 表单怎么找到模块

`x_component_process_Xform/Form.js`：

```js
_getDomjson: function(dom){
  var mwftype = dom.get("MWFtype") || dom.get("mwftype");
  switch (mwftype){
      case "form": return this.json;
      case "":     return null;
      default:     var id = dom.get("id"); return this.json.moduleList[id];   // ← 靠节点 id 取定义
  }
},
_getModuleNodes: function(dom, dollarFlag){ …扫描子节点的 mwftype… }
```

→ **顶层 `html` 必须给出每个模块的占位节点**，否则模块拿不到 `node`。

### 1.2 事件脚本执行

`Form._loadEvents()`：
```js
Object.each(this.json.events, function(e, key){
  if (e.code){
    if (this.options.moduleEvents.indexOf(key) !== -1)          // ["load","queryLoad","postLoad"]
        this.addEvent(key, function(event){ return this.Macro.fire(e.code, this, event); });
    else if (key === "load")  this.addEvent("postLoad", function(){ … });
    else if (key === "submit")this.addEvent("beforeProcess", function(){ … });
    else this.node.addEvent(key, function(event){ … });
  }
});
```
→ **`json.events.postLoad.code` 会被执行**，且时序在模块 `load()` 之后。

## 2. 承载自定义 HTML 的模块类型

`x_component_process_Xform/` 下每个模块一个文件。用 **Html 模块**：

```js
// Html.js
load: function(){
    this._queryLoaded();
    if (!this.isReadable){ this.node?.addClass('hide'); }
    else {
        this.node.insertAdjacentHTML("beforebegin", this.json.text);   // ← 正文放 json.text
        this.node.destroy();
    }
}
```

设计器模板 `Module/Html/template.json`：`{id,name,type:"Html",description,text,container}`。

**三个必须记住的后果：**

| 事实 | 后果 |
|---|---|
| `insertAdjacentHTML` **不执行 `<script>`** | 运行时 JS 必须放 `events.postLoad.code` |
| `<style>` 经 `insertAdjacentHTML` **会生效**，但注入的是**桌面同一个 document** | CSS 必须全部限域，否则污染整个 O2OA 桌面 |
| `insertAdjacentHTML` 注入到父节点（非 iframe） | 没有同源问题；`window` 就是桌面窗口，可直接用 `layout.session.user.token` |

**不要用 Iframe 模块**：它只接受 `src` URL；用 `data:` URL 会变成 opacity origin，
`fetch` 与 `parent` 访问全被浏览器拦住，活数据拿不到。

## 3. 正确的最小页面数据结构

```jsonc
{
  "json": {
    "id": "<pageId>", "name": "<页面名>", "type": "Form", "mode": "PC",
    "application": "<portalId>", "applicationName": "<门户名>",
    "styles": {}, "properties": {}, "cssLinks": [], "scriptSrc": [],
    "jsheader": {"code": "", "html": ""},
    "events": { "queryLoad": {"code":"","html":""}, "beforeLoad": {…},
                "beforeModulesLoad": {…}, "afterModulesLoad": {…},
                "postLoad": {"code": "<你的运行时JS>", "html": ""},   // ★ 脚本放这
                "load": {…}, "afterLoad": {…}, "beforeClose": {…}, "help": {…},
                "unload": {…}, "click": {…}, "dblclick": {…}, "keydown": {…},
                "keypress": {…}, "keyup": {…}, "mousedown": {…}, "mousemove": {…},
                "mouseout": {…}, "mouseover": {…}, "mouseup": {…}, "focus": {…},
                "blur": {…}, "submit": {…}, "reset": {…} },
    "moduleList": {
      "html": {
        "id": "html", "name": "", "type": "Html", "description": "",
        "text": "<style>…限域CSS…</style>\n<div id=\"op-root\">…正文标记…</div>",  // ★ 正文放这
        "container": "", "properties": {}, "class": "", "styles": {},
        "recoveryStyles": null, "isSaved": true,
        "pid": "PC<pageId>html", "moduleName": "html"
      }
    },
    "fieldList": {}, "css": {"code": ""},
    "pageStyleType": "blue-simple", "formStyleType": "default",
    "pid": "PC<pageId><pageId>", "widgetList": [],
    "languageType": "none", "languageScript": {"code": "", "html": ""}
  },
  "html": "<div mwftype=\"form\" id=\"<pageId>\" class=\"css css<pageId去横线>\" style=\"\"><div mwftype=\"html\" id=\"html\" style=\"\"></div></div>",
  "id": "",
  "isNewPage": false
}
```

要点：
- 顶层 `html` 的**节点 id 必须等于 `moduleList` 的键**，`mwftype` 等于模块的 `moduleName`。
- `events` 24 个键补齐（照抄原生页面），缺哪个都可能被别处读到。
- `xdata` 长度会到 15~40KB，`mediumtext` 够用。

## 4. CSS 必须限域

因为注入的是桌面 document，`body{}` / `*{}` 会把整个 O2OA 界面改花。
做法：所有规则加 `#<root> ` 前缀，`body`→根节点自身，`*`→根节点及其后代。

参考实现（纯行处理即可，我们的 CSS 每条选择器独占一行、含 `{` 且 `{` 前无 `;`）：

```python
def scope_css(css, scope="#op-root"):
    out = []
    for line in css.split("\n"):
        if "{" not in line:
            out.append(line); continue
        head, sep, tail = line.partition("{")
        if ";" in head:                          # 单行样式的属性片段
            out.append(line); continue
        sels = [s.strip() for s in head.split(",") if s.strip()]
        fixed = []
        for s in sels:
            if s in ("body", "html", ":root"): fixed.append(scope)
            elif s == "*":                     fixed.append("%s, %s *" % (scope, scope))
            else:                              fixed.append("%s %s" % (scope, s))
        out.append(", ".join(fixed) + " " + sep + tail)
    out.append(scope + " { min-height: 100%; }")
    out.append(scope + " { display: block; }")
    return "\n".join(out)
```

正文统一包一层 `<div id="op-root">`，运行时 JS 里的 `document.getElementById`/`querySelector`
全部改走根节点，避免多页并存时串页。

## 5. 一键诊断清单（白屏时按顺序查）

```bash
# ① 数据格式（★ 必须区分「未转义 JSON」和「转义形态」两层）：
#    转义形态开头是 {\ + " （三个字符 {\\"），未转义 JSON 开头是 {" 。
docker exec <mysql> mysql -u<u> -p<w> --default-character-set=utf8mb4 -D X -e "
SELECT CASE WHEN xdata IS NULL OR xdata='' THEN 'empty'
            WHEN LEFT(TRIM(xdata),3)=CONCAT('{',CHAR(92),'\"') THEN 'escaped-JSON'
            WHEN LEFT(TRIM(xdata),1)='{' THEN 'raw-JSON'
            WHEN LEFT(TRIM(xdata),1)='<' THEN 'HTML' ELSE 'other' END kind,
       CASE WHEN xid RLIKE '^[0-9a-f]{8}-' THEN 'native' ELSE 'ours' END who,
       COUNT(*) c FROM PTL_PAGE GROUP BY kind, who;"
# 期望：native 全 escaped-JSON；ours 也全 escaped-JSON。
# 出现 HTML 行 = 第 0 层错误（裸 HTML）；出现 raw-JSON 行 = 第 2 层错误（未转义）。

# ② 页面→门户引用是否闭合（引错会抛 ExceptionPortalNotExist）
docker exec <mysql> mysql … -e "
SELECT p.xid, p.xportal, pt.xid, (p.xportal=pt.xid) ok
FROM PTL_PAGE p LEFT JOIN PTL_PORTAL pt ON pt.xid=p.xportal WHERE p.xid LIKE 'o%';"
```

③ 用桌面同款接口把页面取回来，**自己复刻一遍 JSON.decode**：

```
GET /x_portal_assemble_surface/jaxrs/page/{pageId}/portal/{portalId}
    → data.data        （PortalPage.js 用的路径）
GET /x_portal_assemble_surface/jaxrs/page/v2/{pageId}/portal/{portalId}
    → data.page.data   （v2 结构不同，别混用）
```

## 6. 常见误判（都踩过）

- **「首页空白」先怀疑服务端坏了**：先看 `/x_desktop/index.html` 能不能正常返回、
  `portal/list` 带 token 是否 200。若服务端正常，就是 page.data 格式问题。
- **健康检查失败≠服务不可用**：ARM64/QEMU 下 `docker exec` 可能报
  `error starting setns process` 且 healthcheck 一直 starting，但 HTTP 端口照常响应。
  用 `curl` 判活，别用 `docker inspect .State.Health`。
- **`docker exec` 挂了但 `docker cp` 还能用**：需要看容器内文件（war 源码、日志、
  webServer 前端）时用 `docker cp <ctr>:/path D:/temp/x` 拷出来读。
- **别信「门户 HTML 注入 iframe」的旧结论**：O2OA 10 是注入桌面同一个 document。
- **`xdata` 存的是改后数据**：重新导入 xapp 会覆盖，改完必须重新打包导入，
  不能只改库（否则下次导入打回原形）。
- 原生门户页的 `xdata` 结构可从库里随便挑一个 UUID 页面 dump 出来当模板：
  它自带全部 24 个 events 键和正确的 `pid`/`pageStyleType`。

## 7. 上游（生成侧）建议的流水线

```
独立 HTML（自身可离线打开、含 <style> + <script>）
   ├─ 预览：直接用
   └─ 转换 portal_page_data(html, pageId, pageName, portalId, portalName)
           ├─ <style> → 留在 Html 模块 text 内（已限域）
           ├─ 正文   → Html 模块 text
           ├─ <script> → events.postLoad.code
           └─ html   → mwftype="form" 骨架
```

转换保持**幂等**，并配三个校验器：
1. 构建产物校验（顶层键/type/Html 模块/text 非空/CSS 限域/骨架齐全/idx 对齐/`node --check` 脚本语法）
2. `.xapp` 结构校验（**必须删掉「data 是否为完整 HTML 文档」这种旧检查**，
   改成「data 是否为门户页 JSON」）
3. 线上端到端验证（把接口数据取回来复刻 `JSON.decode`）

---

## 8. ★ 门户里显示「自建表真实数据」：不要走视图，直读表行接口

> **血泪结论：本版本（10.0.2 / 社区版）的门户**不可能**通过 `table` 类型视图拿到数据。
> 门户里要显示自建表数据，唯一可靠通路是「前端 `fetch` 表行接口 + 自己渲染表格」。**

### 8.1 为什么 table 视图走不通（源码实证）

`x_query_assemble_surface` 的 `BaseAction.dealPlan()` 是个 switch：

```java
// 伪码，实测 x_query_assemble_surface jar
switch (type){
    case TYPE_CMS:  plan = new CmsPlan(...);       break;
    case TYPE_STAT: plan = new StatPlan(...);      break;
    default:        plan = new ProcessPlatformPlan(...);   // ← table 掉进这里
}
```

- `x_query_core_express.jar` 的 plan 包内**只有** `CmsPlan` / `ProcessPlatformPlan` / `StatPlan`，
  **没有 `TablePlan`**。
- 于是 `table` 类型视图执行时必抛：
  `NullPointerException at ProcessPlatformPlan.adjustWhere(ProcessPlatformPlan.java:94)`
  （因为 ProcessPlatformPlan 拿不到 `table` 视图该有的元数据）。
- 旁证：库里自带的 56 个 process 视图 / 36 个 cms 视图全部能跑；**14 个 table 视图全是自己导入的**，
  说明官方从不在 UI 里产 table 视图 —— 这个 xType 是半成品。

导入侧还有一个前置坑（见 8.4）。

### 8.2 可靠通路：自建表行接口（裸字段名，直读）

```
POST /x_query_assemble_surface/jaxrs/table/list/table/{tableFlag}/row/paging/{page}/size/{size}
Content-Type: application/json
x-token: <token>
body: {}
```

返回结构（`data.data` 为行数组，`data.count` 为总数）：

```json
{ "type":"success",
  "data": { "count": 9, "data": [ { "employee_no":"YG001", "employee_name":"孟弋洁", … } ] } }
```

★ **字段名是裸的**（`employee_no` / `employee_name`），**不带 `x` 前缀**；
物理列名带 `x` 前缀（`xemployee_no`），是**接口层剥掉了**。写列定义时按裸名写。

同族接口：
- `.../table/list/{flag}/row/select`（body 传过滤条件）
- `.../table/{flag}/row/{id}`（单行）

**特点**：不经视图引擎、不经 CMS、不经流程平台 → **零引擎依赖，必通**。

### 8.3 怎么在门户里用（我们的实现）

生成侧（`o2oa_portal.py`）：

```python
def table_holder(table_flag, columns, caption="", height=None, page_size=50):
    """columns = [(key, 表头), (key, 表头, "money"|"num"|"date"), …]  → 占位 div"""
    data_embed = "%s|%s" % (table_flag, json.dumps([[k,t,f] for …], ensure_ascii=False))
    return '<div class="op-tbl-wrap" data-embed-table="%s" data-page-size="%d">…占位…</div>'
```

`_LIVE_JS` 里加两段（都在 `events.postLoad.code` 内，因为 Html 模块里的 `<script>` 不执行）：

```js
function req(url, method, body){
  var opt = { method: method || "GET", credentials: "include",
    headers: {"x-token": token(), "Content-Type":"application/json", "Accept":"application/json"} };
  if (body !== undefined && body !== null) opt.body = body;      // ★ POST 表行接口要 body:"{}"
  return fetch(url, opt).then(function(r){ return r.json(); });
}
function loadTables(){
  document.querySelectorAll("#op-root [data-embed-table]").forEach(function(box){
     var parts = box.getAttribute("data-embed-table").split("|");
     var flag = parts[0], cols = JSON.parse(parts[1]);
     var size = parseInt(box.getAttribute("data-page-size")||"50",10);
     req("/x_query_assemble_surface/jaxrs/table/list/table/"+flag+"/row/paging/1/size/"+size,
         "POST", "{}")
       .then(function(j){ renderTable(box, j.data.data, cols); });
  });
}
```

渲染要点：
- 表头 sticky、数字右对齐；`fmtCell` 按第 3 列类型格式化
  （`money` → 千分位 + `¥`；`num` → 千分位；`date` → `slice(0,10)`）。
- 失败要落到 `.op-tbl-err` 占位（**别静默**，否则又变成"页面在但没数据"的假象）。
- 空结果落到 `.op-tbl-empty`。

**调用时序**：`boot()` 里 `try{ loadViews(); }catch(e){} try{ loadTables(); }catch(e){}` ——
两个互不影响，任一失败不拖垮另一个。

### 8.4 前置坑：视图 `data` 必须是**字符串**，否则整个应用导入 500

```python
# o2oa_builder.view()
"data": json.dumps(view_data, ensure_ascii=False),   # ★ 必须是 STRING
```

- `QRY_VIEW.xdata` 是 `mediumtext`；服务端 `ActionCover$Wi` 反序列化
  `viewList[].data` 时**要求 STRING**。
- 传嵌套对象 → `can not convert jsonElement to class:...ActionCover$Wi
  Expected STRING but was BEGIN_OBJECT at path $.viewList[0].data`
  → **整个数据中心应用导入 HTTP 500**（流程/门户不受影响，只 QRY 挂）。
- 症状：库里该应用所有 `QRY_VIEW.xdata IS NULL`。
- 注意与 §0 的区别：**视图 data 是「未转义 JSON 字符串」，不要做 `escape_json_string`**。
  §0 的双层转义只针对 Form/Page 的 data。

### 8.5 若一个页面同时有「原生视图」和「表直读」

`o2oa_hr_portal.hr_view_page_html()` 支持两种 section 形态，按长度判别：

```python
for sec in sections:
    if len(sec) == 4 and isinstance(sec[2], (list, tuple)):
        cap, tflag, cols, height = sec                  # → table_holder（表直读）
    else:
        cap, app_id, view_id, height = sec              # → view_holder（原生视图，仅 process/cms 可用）
```

**迁移建议**：能直读表就别嵌视图。只有 CMS/流程类数据（原生视图支持）才用 `view_holder`。

### 8.6 端到端验证（必做）

用 playwright 驱动本机 Edge 无头登录桌面，进栏目页，断言：

```js
// 断言 1：表格行数 > 0
const rows = await page.$$eval("#op-root .op-tbl tbody tr", ns => ns.length);
// 断言 2：首行内容含预期关键字段（如工号 YG001）
const first = await page.$eval("#op-root .op-tbl tbody tr", tr => tr.innerText);
```

- 登录：调登录接口拿 token → 注入 `x-token` cookie（比填表单稳）。
- 截图留证：`C:/temp/o2dbg/e2e_hr_table.png`、`e2e_contract_start.png`。
- 陷阱：宿主 Git Bash 的 `/c/temp/...` 在 Python 里读不通，**一律写 `C:/temp/...`**。
- 陷阱：`docker exec` 在 ARM64/QEMU 下会持续 `setns` 失败，但 `docker cp` 始终可用；
  「容器内 curl 9090」跑不了就改宿主侧 Python urllib 直调 9090。

---

## 9. ★ 门户的组织惯例：一个业务域一个门户 + N 个分类栏目页

> 用户常见诉求：「按 OA 系统的惯例补门户，并分类一下」。
> **不要**给每个流程应用各开一个门户 —— 那不符合 OA 惯例，也会让门户选择器里一堆孤立条目。

### 9.1 惯例形态

1. **一个业务域 = 一个门户（portal）**，纵向挂 **多个栏目页（portal page）**，
   栏目页之间用**横向一级导航 Tab** 切换（首页 / 各业务分类 / 个人设置）。
2. 门户用 `PTL_PORTAL.xportalCategory`（前端叫 `portalCategory`）**分组**，
   门户选择器就是按它分组的。原生已有值：
   `公文首页 / 平台 / 应用 / 应用市场 / 未分类 / 移动端 / 绩效考核 / 综合管理 / 门户-部件 / 门户样式-1 / 门户样式-2`。
   自建业务门户建议单开一类（如「业务管理」），别混进「综合管理」。
3. 门户**可以从任一应用挂载**，且**能读其他应用的自建表/流程** ——
   门户只是展示层，跨应用聚合是正常的（例：业务门户挂在"项目"应用，却展示预算/财务/档案的表）。
4. 首页放**聚合总览**（多张表 + KPI），各分类页放**该业务的台账 + 发起入口按钮**。
5. 数据一律走 §8 的**表行接口直读**（`table_holder`）；只有 process/cms 视图才用 `view_holder`。

### 9.2 ★★ 页内 Tab 切换：必须用 `toPortal()`，`openApplication` 会另开页签

**症状**：点了导航 Tab，标题和高亮都不变，页面纹丝不动（"点了没反应"）。

**根因**：`Portal.options.multitask = true`，所以
`layout.openApplication("portal.Portal", {portalId, pageId})` 是**开一个新的页签**
（`layout.desktop.apps` 里 appId 为空 → 每次新建实例），**不是页内切换**。
用户以为没反应，其实新页签开在后面。

**正解**：找当前已打开的门户实例，调官方 `PortalPage.js` 里的
`Main.toPortal(portal, page, par)` —— 它复用**同一个窗口**重新 `loadPortal`。

```js
var _base_css_ready = false;   // 仅为示意，实际用你自己的 boot 流程
function gotoPortal(portalId, pageId){
  var L = window.layout;                       // 桌面拿 layout 的方式见 §9.3
  var apps = (L && L.desktop && L.desktop.apps) || {};
  for (var k in apps){
    var a = apps[k];
    if (!a || typeof a.toPortal !== "function") continue;      // 只有门户实例有 toPortal
    var op = (a.options && a.options.portalId) || "";
    if (op && portalId && op === portalId){                    // ★ 同一门户内才走页内切换
      try { a.toPortal(portalId, pageId); return true; } catch(e){}
    }
  }
  // 跨门户 或 当前没有该门户实例 → 退回新开页签
  return layout.openApplication("portal.Portal",
           { "portalId": portalId, "pageId": pageId });
}
```

注意点：
- **只对同一 `portalId` 用 `toPortal`**；跨门户（A 门户的页跳到 B 门户的页）没有现成实例，
  只能 `openApplication` 新开。
- `portalId` / `pageId` 用 `a.options`，不要从 DOM 里猜。
- 判"开了几个门户"= 数 `apps` 里 `typeof a.toPortal === "function"` 的实例数。
- 「个人设置」这类非门户目标（`"profile"`）用 `openApplication("profile.Profile", …)`，
  别塞进 `gotoPortal`。

### 9.3 排查用的探针

```js
// 列出桌面所有已打开实例的类型与 portalId（放在 events.postLoad.code 或控制台里跑）
var apps = (layout.desktop.apps) || {};
Object.keys(apps).forEach(function(k){
  var a = apps[k];
  console.log(k, a && a.options && a.options.appId, a && a.options && a.options.portalId,
              typeof (a && a.toPortal));
});
```

门户实例的 key 形如 `Portal-CBD2ADB3F0900001245E9D5014404010`（`Portal-` + 32 位 HEX）。
想读前端源码定位行为：

```bash
docker cp <ctr>:/opt/o2server/servers/webServer/x_component_portal_Portal/PortalPage.js .
# 其中 Main.toPortal = function(portal, page, par){ … this.loadPortal(par) … }
```

### 9.4 端到端断言（导航专项）

只开**一个**门户页，然后逐个点 Tab，每次断言标题变化 + 实例数不增：

```js
// 断言：点第 i 个导航后，页内 h1 变成对应栏目名，且门户实例数仍为 1
const n = await page.evaluate(() => Object.values(layout.desktop.apps)
    .filter(a => a && typeof a.toPortal === "function").length);
// 期望 n === 1（用 openApplication 的错误实现会 n 逐次递增）
```

> 踩坑记录：曾用 `openApplication` 实现导航，E2E 里"点 Tab 无变化"，但
> `querySelectorAll(".op-tbl")` 统计到的表格数却一路 4→6→8→10→12 ——
> 这正是"多页签并存"的特征，一看计数递增就该怀疑开新页签而非切页。
