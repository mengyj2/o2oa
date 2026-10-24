# 2026-10-24 财务门户 view.js 无参打开崩溃修复（`reading 'application'` 真身）

> 级别：P1（功能阻断——财务页在 App/无参直开时只剩残页）
> 关联：秘书长要求④后半「财务页 `Cannot read properties of undefined (reading 'application')` JS 报错需立项修」
> 提交：驱动仓 `d6a3100`；源：`deliverables/04_财务管理应用.xapp` portalList[0].scriptList[0]（view.js, `ba109bfc-4ba4-452c-ada6-bc676b2a21cc`）

## 1. 现象

移动端打开「财务管理」门户首页（付款申请 `ea6548e4`）：
- 控制台报 `TypeError: Cannot read properties of undefined (reading 'application')`
- 页面渲染中断，只剩「付款申请 / 未找到数据」残页（表头在、内容空）

## 2. 根因（探针实证，非推断）

### 2.1 崩溃点

财务管理 portal（`97e0d459`）的 **view.js** `setWorkCount()`：

```js
this.define("setWorkCount",function(){
    const parameter = {
        "application":this.page.parameters.parameters.application,   // ← 崩这里
        "processList":this.page.parameters.parameters.processList
    };
    this.Actions.load("x_query_assemble_surface").StatementAction.execute("common-task",1,2000,parameter).then(...)
})
this.page.addEvent("postLoad",function(){ this.setWorkCount(); })
```

页面**无 parameters 传入**时 `this.page.parameters` 为默认空对象 → `.parameters` 为 `undefined` → 读 `.application` 抛错。错误发生在 `postLoad` 事件回调里，**后续加载链全部中断** → 残页。

无参场景 = App 侧 `openAppNaviLeaf` 忽略 portalOptions（已知缺陷，Kotlin 侧待修）+ 任何直连无 `&parameters=` 的打开方式。

### 2.2 定位手法（浏览器仪器探针，可复现）

报错栈里帧全落在 `<anonymous>:653` —— 是 **MWF.Macro.exec 的 eval 态**（`Browser.exec` 包 `MWF.Macro.scriptSpace["f_N"] = function(){try{ code }catch(e){console.error(e)}}`，注意宏代码内的错会被 try/c 吞成 console.error；本例是从事件回调逃逸出来的未捕获错）。

仪器探针（`C:/temp/e2e_fin_trace.js`，playwright + `addInitScript` 轮询）：
1. 包裹 `MWF.xScript.PageEnvironment.prototype` 全部方法（try/catch 记方法名）
2. 包裹 `Browser.exec` 记录所有 eval 脚本原文
3. 移动 UA + cookie 注入登录后打开 `portalmobile.html?id=<portal>&page=<page>`

结果：eval 脚本 #15（24274 字符/676 行）第 653 行 = `"application":this.page.parameters.parameters.application,`。

**串联真相**：页面 xdata 的 `includeScripts` 挂 5 个脚本（主页 `widget.js`/`start_process.js`/`widget_task.js` + 公文 `document.js` + 财务 `view.js`），框架按序拼接成一个 eval 脚本；前 4 个占 616 行，view.js 排最后，其第 37 行 = 串联后第 653 行。

### 2.3 连带确认

- 财务页 xdata 自身无事件脚本、widget 只有 5 行 queryLoad（include homepage/index.js）——错误不在页面/widget 自身，在 includeScripts 的 view.js；
- 全库扫描 `parameters.parameters` 无保护读**仅此一处**（费控/固定资产/办公用品/用车的同名 setWorkCount 脚本无此模式）；
- 服务端**有脚本缓存**：改完 `PTL_SCRIPT.xtext` 后 API 的 `relatedScriptMap` 仍返回旧文本，**重启 o2oa-server 后才生效**。

## 3. 修复（源文件改 + DB 同步，未走 designer API）

按「门户设计严禁 designer API 保存」纪律，改源文件 xapp + SQL 同步 DB：

```js
// [cnccia-patch 2026-10-24] App openAppNaviLeaf 未传 portalOptions 或无参直开页面时
// this.page.parameters.parameters 为 undefined，旧写法抛
// Cannot read properties of undefined (reading 'application')，postLoad 链中断、财务页只剩残页。
// 解构兜底；application 默认 finance（与 reimburseConfig 域标识一致）。
const pageParameters = (this.page.parameters && this.page.parameters.parameters) || {};
const parameter = {
    "application": pageParameters.application || "finance",
    "processList": pageParameters.processList
};
```

产物与工具（`patches/财务-viewjs-parameters兜底/`）：
- `patch_fin_viewjs.py`：xapp 外科补丁（锚点唯一性断言 + 自动备份 `.pre-viewjs-fix.bak`）
- `update_viewjs.sql`：DB 同步（`UPDATE PTL_SCRIPT SET xtext=... WHERE xid='ba109bfc...'`）
- **xapp 的 JSON 转义是非标准 O2 约定**：`\"` `\\` `\n` `\r` `\u0026`(&) `\u0027`(') `\u003c`(<) `\u003d`(=) `\u003e`(>)，文本行尾 CRLF——补丁脚本的 `esc_o2()` 按此实现（曾因 `'\\r\n'` 少写一个反斜杠导致锚点不命中，教训：Python 里 `\n` 永远是换行符，要写 `'\\r\\n'`）

## 4. 验证矩阵

| 探针 | 场景 | 结果 |
|---|---|---|
| e2e_fin_error.js（复现） | 无参打开财务页（修复前） | 必崩 `reading 'application'`，栈 653:55/673:10 一字不差 |
| e2e_fin_error.js（修复后） | 无参打开财务页 | **ERRORS 0**，加载链完整 |
| e2e_fin_withpar.js（正向对照） | 带 `parameters={application:"finance",processList:[...]}` 打开 | ERRORS 0，且 `x_query_assemble_surface/jaxrs/statement/common-task/execute/page/1/size/2000` 请求**正常发出**（修复前构造 parameter 即崩、请求发不出） |
| API 层 | mobile 页接口 relatedScriptMap | 重启后返回 1267 字符修复版（fix=True bug=False） |
| 全库扫描 | `parameters.parameters` 无保护读 | 仅此一处，修复即全覆盖 |

「未找到数据」文案 = 查询返回空的正常表现（无测试数据），归 Task #48 造数据解决，非缺陷。

## 5. 遗留与关联

- **App 侧 openAppNaviLeaf 忽略 portalOptions**（Kotlin）：本例的触发条件之一。JS 兜底已保证不崩，但 App 应补传 parameters 才能让待办数量等按门户过滤——列 cnccia.12 候选。
- 改 DB 的纪律说明：本例源（xapp）在仓、 designer API 禁用、整包重新导入有 relatedScriptMap 重算风险，故采用「源文件改 + 单字段 SQL 同步 + 重启清缓存」，并在提交信息中完整披露。
