---
name: o2oa-portal-brand-guard
description: 治理并修复 O2OA（社区版 / Docker 自托管，10.0.2 实证）的「门户首页功能失效」「首页入口文件(index/admin/index_home)」与「品牌残留」。当用户说"首页点击没反应/点了没链接/失去功能""门户首页整体坏了""index 完全破坏了，要从原文件替换""改图标/换 logo 后链接失效""首页能看不能点""管理员登录跳错页面/进了后台""首页分流不对""应用标题还显示翱途/O2OA""页面名称不是协会名""公文红头/发文字号还是 demo 品牌""商标/品牌残留要清干净"时调用。覆盖：门户点击失效真根因=PTL_PAGE.xproperties.relatedScriptMap 被设计器 API 保存清空、首页入口三分流(index.html)与 Dockerfile COPY 烘镜像纪律、config.json 不可静态 COPY 的坑、logo 回退与 flag 缓存、窗口标题真源 x_component_portal_Portal/Main.js 的 setTitle(pageName)、公文字号两层存储(QRY_ITEM+PP_C_SNAP)、CMS 创建者单位名元数据、全库品牌词扫描器(scan_brand_words.py)与幂等改名脚本(rename_gongwen_brand.py + FIXUP_MAP 回纠)，以及"禁设计器 API 改设计数据 / 改前整行备份 / 改后 restart+双验"的安全纪律。
agent_created: true
category: operations
---

# O2OA 门户首页完整性 + 品牌残留治理

适用 O2OA 10.x（Docker 自托管，10.0.2 实证）。本 skill 是事故驱动沉淀，全部结论有源码/实测证据。

## 0. 三条铁律（先记住，能省几小时）

1. **改 O2OA「设计数据」禁止 UPDATE 改片段，也禁止图省事走设计器 API 存整对象**——
   两者都会**重算并清空派生字段**（`xproperties` / `relatedScriptMap` / `relatedWidgetList`）。
   改名、改标题这类动作，**只准用 SQL `REPLACE()` 动目标字段**，绝不碰 `xproperties`。
   > 事故原型：只想改页面标题，走了设计器保存 → `relatedScriptMap` 被清成 `{}` → 整站菜单点不动。
2. **改前必须整行备份、改后必须 `docker restart o2oa-server`**。
   O2OA 对页面/附件/流程配置有 **flag 级缓存**，不重启时 DB 改了、接口仍返回旧值 → 你会误判"没生效"而反复改。
3. **渲染正常 ≠ 交互正常**。能看见 ≠ 能点。渲染读 `xdata`，交互读 `xproperties`。
   报"页面没问题但点击没反应"时，直接把注意力放到 `xproperties`。

## 1. 症状分流树

```
用户报"首页不对"
├─ 能渲染但点击无反应 / 控制台报 this.xxx is not a function  → A 类（§2，数据层）
├─ 整页白屏 / 404 / 脚本语法错 / 登录后跳错页面 / ★重启后变回去了 → B 类（§3，文件层）
├─ ★多栏主页面(图1)退化成了两栏壳(图2) / "我要的首页不见了"     → B' 类（§3.1b，indexPage 开关层）
├─ 换了 logo/图标后功能或显示异常                              → C 类（§4）
└─ 显示正常，只是文案/标题/字号还是旧品牌                      → D 类（§5）
```

> ★ **A 类与 B 类症状相似但根因完全不同**，选错方向会白排查几小时。
> 一句话判定：**「能看不能点」= A 类（数据的交互字段没了）；「连看都看不到 / 重启后变回去」= B 类（文件被卷覆盖）**。
> 用户说"index 完全破坏了、没有链接"时，**先确认是哪一类**再动手。
> **B 类的头号诱因是 webroot 命名卷覆盖镜像层（§3.2），不是数据、也不是 bind mount。**
> ★ **B' 类最容易误判成 B 类**：用户说"定制的首页文件丢了、就在 x_desktop 里"，
> 但**图1 从来不是 HTML 文件**——是 `indexPage` + 门户 + 个人版式三层合成（§3.1b）。
> 判定：先 `GET /x_program_center/jaxrs/config/portal` 看 `indexPage.enable`，**是三秒能验的第一步**。

## 2. A 类（数据层）：门户首页「点击失效」（真根因固定）

**症状**：门户渲染完整（顶栏/菜单都在），点菜单无任何反应；F12 反复报
`TypeError: this.openStartMenu is not a function at MWF.Macro.scriptSpace.f_0`。
极易被误判成"改 logo 弄坏了链接"或"index.html 被改坏了"。

**真根因**：`PTL_PAGE.xproperties.relatedScriptMap` 被清空成 `{}`。

**机制链（源码实证）**：
1. 页面设计数据 `xdata.json.includeScripts` 是源数据（引用 `layout.js`/`index.js`）。
2. **保存页面时** `x_desktop/js/base_portal.js` 的 `addForm/updateForm` 把它转成
   `relatedScriptMap = {scriptId: appType}` 存进 `PTL_PAGE.xproperties`。
3. **运行时**前端读 `xproperties.relatedScriptMap` → `this.include(...)` →
   `POST /x_portal_assemble_surface/jaxrs/script/portal/{portalFlag}/name/{name}`
   → `MWF.Macro.exec(text, environment)` → 脚本内 `this.define('openStartMenu', …)` 注册宏。
4. 点击时 `MWF.Macro.exec(clickCode, environment)` 取 `this.openStartMenu`。
   脚本没加载 → 函数不存在。

> 触发点：任何"通过设计器接口保存该页面"的动作（改标题/改布局），只要提交体里没有
> `includeScripts`，服务端就把它重算为空。

**诊断（2 条 SQL 定位）**：
```sql
SELECT xid, xname, xproperties FROM X.PTL_PAGE WHERE xid='<firstPageId>';
-- 正常页面（拿同门户其它页做对照）
SELECT xid, xname, xproperties FROM X.PTL_PAGE WHERE xid='<healthyPageId>';
```
`xproperties` 里 `relatedScriptMap` 为空 = 确诊。
再证服务端无罪（**必须 POST，GET 405**）：
```bash
POST /x_portal_assemble_surface/jaxrs/script/portal/index/name/index.js   # 200 且 text 非空
```
脚本接口正常 → 问题 100% 在前端关联数据。

**修复（首选整行还原，别手拼字段）**：
```sql
-- 从当日备份库整行取回（含 xproperties）
UPDATE X.PTL_PAGE a JOIN X_restore.PTL_PAGE b ON a.xid=b.xid
   SET a.xproperties=b.xproperties
 WHERE a.xid='<firstPageId>';
```
> 只有 `xproperties` 被破坏时可只还原该字段；若不确定破坏范围，**逐字段整行还原**更安全。
> 手改前把整行 `SELECT` 出来存 `backups/PTL_PAGE_<xid>_broken_<date>.sql`。

**验证**：`GET` 页面 API → `properties.relatedScriptMap` 恢复含 `{"<layoutId>":"portal","<indexId>":"portal"}`；
`docker restart o2oa-server` 后真机点菜单。

## 3. B 类（文件层）：首页入口文件 index / index_home / admin

### 3.1 三分流机制（`index.html` 的真实逻辑）

O2OA 登录后落到 `x_desktop/index.html`，本项目已定制成**按身份三分流**：

| 身份 | 判定依据 | 去向 |
|---|---|---|
| 名单内管理员（`mengyijie`） | `_HOME_ENTRY_USERS = ["mengyijie"]`，匹配 `unique`/`name`/`distinguishedName` | **`index_home.html`**（仍进用户门户首页入口） |
| 其余管理员 | `tokenType==="manager"` ∨ 含 `Manager@ManagerSystemRole@R` ∨ 账号名 `admin`/`xadmin` | **`admin.html`**（旧版九宫格桌面） |
| 普通用户 | 以上都不命中 | **门户首页**（`layout.openApplication(null,"portal.Portal",{"portalId":"index"})`） |

- 判据是**多源取并集**：`layout.session.user` / `session.userDetail` / `session.tokenType`
  ——因为 `roleList` 在浏览器常落在 `userDetail` 而非 `user`。**别只读一处**。
- `index_home.html` = 管理员仍进"用户门户首页入口"（不分流去 admin 后台）。
- `admin.html` = 官方版仅改 `<title>`。

### 3.1b ★★★ 入口职责分离（**2026-09-28 修订版**）+ 「图1 主页面」的真身

> **修订说明**：本节原先描述"三分流"（按角色在 index.html 内 `location.href` 跳 admin/index_home）。
> **该方案已废弃**。用户 2026-09-28 明确要求改为「**职责分离**」：
> index.html 对所有人一视同仁渲染多栏仪表盘；admin.html 自己做管理员守卫。
> 依赖前端跳转分流有三个固有缺陷：① 跳转前有白屏/闪烁；② 角色判据要读多个来源易错；
> ③ 一旦某个入口文件被 webroot 卷旧版覆盖，"分流逻辑整个消失"却看不出来（§3.2 的真实事故）。

**项目约定（修订版，永久有效，勿再搞混）**：

| 入口 | 职责 | 谁能进 |
|---|---|---|
| `/x_desktop/index.html` | **主页面 = 多栏仪表盘**（图1：13 组件）。**已取消任何分流** | **所有人**（含管理员） |
| `/x_desktop/admin.html` | **九宫格桌面**（后台图标工作台） | **仅管理员**；非管理员被守卫弹回 `index.html` |
| `/x_desktop/index_home.html` | 备用入口（与 index.html 等价，当前无人引用） | — |
| `/x_desktop/portal.html` | 官方门户壳（带 `?id=` 参数，一般不用） | — |

**关键差异（对照旧方案）**：
- 旧：`index.html` 里按 `_isManager()` 决定"跳 admin.html / 跳 index_home.html / 原地渲染"。
- 新：`index.html` 删光 `_HOME_ENTRY_USERS`/`_MANAGER_ROLE`/`_isManager`/`_goAdmin`/`_goHomeEntry`，
  `_load()` 直接 `layout.openApplication(null, "portal.Portal", {"portalId":"index"})` —— **无分支、无跳转**。
- 新：权限闸门搬到 `admin.html` 内（§3.1c），**只有需要保护的那一个入口承担守卫职责**。
  这样 `index.html` 永远不会因为角色判错而把管理员关在门外。

**★ 关键认知：「图1 的主页面」不是一个 HTML 文件，而是三层配置合成的。**
用户常误记"定制文件就在 x_desktop 中"——**x_desktop 下没有任何一版 HTML 能渲染出图1**。
图1 = 以下三层叠加：

1. **开关层**：`config/portal.json` 的 `indexPage = {enable:true, portal:"<内容门户id>", page:""}`
2. **门户层**：内容门户（本项目 `62cc80f7`，name=主页内容，alias=**homepage**）→ `firstPage` 指向某页面
3. **版式层**：个人数据 `custom/v10_homepage_layout`（13 列 3 区、13 个组件）

```bash
# 查/改开关层（无需重启，实时生效）
GET/PUT /x_program_center/jaxrs/config/portal        # data.indexPage
# 查门户层
GET /x_portal_assemble_designer/jaxrs/portal/{id}    # 看 name/alias/firstPage
# 查版式层（用本人 token）
GET /x_organization_assemble_personal/jaxrs/custom/v10_homepage_layout
```

**★★ 「首页退化成图2」的头号原因 = `indexPage.enable` 被关（false）**。
此时门户、页面、版式数据**全部完好**，只是开关关了 → 落到 `portalId:"index"` 的那个壳（图2）。
**排查顺序：先查 `indexPage` 开关，再查数据。别一上来翻文件。**

#### 机制考证：`?default=false` 是官方开关，也是 index/admin 职责分离的关键

- 文件：`servers/webServer/o2_core/o2/xDesktop/Default.js`（**注意不在 `x_desktop/js/`**）
- `:131` `this.noDefault = (uri.getData("default")||"").toString().toLowerCase()==="false"`
- `:151` `load()` → `if (!this.noDefault) this.loadDefaultPage();`
- `:343` `loadDefaultPage()` → 若 `layout.config.indexPage.enable && .portal` 成立，
  就**把内容门户当作首页 tab 打开**（于是顶掉九宫格）；否则 `appId="Homepage"` 走九宫格。

**⇒ 结论：`indexPage.enable=true` 是全局开关，会同时影响 `admin.html`。**
开了它，`admin.html` 也会被顶成门户首页 —— 与"admin 应是九宫格"的约定冲突。

**解法：让 `admin.html` 恒以 `?default=false` 运行**（跳过 `loadDefaultPage`），**但地址栏不可见该参数**：

```html
<!-- ① 放在 x.min.js 之前：同步写入参数，让 initData() 读到 -->
<script>
(function(){
  window.__adminHtmlStripDefault = true;              // 交给 ② 清 URL
  try {
    if (String(window.location.search||"").indexOf("default=") === -1) {
      var u = window.location.href;
      window.history.replaceState(null, "", u + (u.indexOf("?")>-1 ? "&" : "?") + "default=false");
    }
  } catch(e){}
})();
</script>
```
```js
/* ② boot 完成后（layout.desktop 就绪）再抹掉 —— SPA 不会因此重载（已实测） */
function stripDefaultParam(){
  if (!window.__adminHtmlStripDefault) return;
  var u = window.location.href;
  if (u.indexOf("default=") === -1) return;
  var clean = (u.indexOf("?default=false") > -1)
      ? u.replace("?default=false", "")
      : u.replace("&default=false", "").replace("default=false&", "");
  window.history.replaceState(null, "", clean);
}
```

> ★★ **用户明确要求「地址栏不能出现 `?default=false`」**（2026-09-28）。
> 单纯 `replaceState` 写进 URL 会**把参数露给用户** —— 必须「先写→boot 后抹」两步走。
> 时机是关键：**过早抹**会让 `initData()` 重算 `noDefault=false`（退回仪表盘）；
> **过晚抹**用户会看到参数闪一下。实测 boot 后 `replaceState` 换 URL **不触发 SPA 重载**，渲染不受影响。
> 备选思路（未采用）：官方 `?app=<appName>` 参数（Default.js:136-143）会清空 `status.apps` 并
> 强制 `forceCurrentApp`，也能达到"干净打开"，但同样会在地址栏留参数。

> ★★ **陷阱（实测无效的写法）**：`window.layout.noDefault = true` **不管用**。
> 因为 `initData()` 每次实例化都**无条件重算** `noDefault`（Default.js:131），把你的赋值覆盖掉。
> **唯一可行路径 = 在 `x.min.js` 执行前把参数写进 URL。**

#### 3.1d ★★ index.html 左上角 logo 的真身：门户页面内嵌 HTML 引用的 **PTL_FILE**

**症状**：index.html（多栏仪表盘）左上角显示「翱途 O2OA」白字 logo，而 admin.html（九宫格）已换协会图。
**为什么两个入口 logo 不同源**：

| 入口 | logo 载体 | 位置 |
|---|---|---|
| **admin.html**（九宫格壳） | CSS `background-image`（`.logo_o2_40`） | `$Default/<skin>/icons/logo_o2_40.png`（镜像层，§3.1f） |
| **index.html**（门户页面） | **门户页面内嵌 HTML 里的 `<img mwftype="image">`** | **`PTL_FILE.xdata`（数据库 base64）** |

**定位链路（实测）**：
```js
// 浏览器 DOM 里的真实 src：
// /x_portal_assemble_surface/jaxrs/file/0b084672-…/portal/0d565ae3-…/content
var e = document.querySelector('.index-logo-img'); e.src;
```
```sql
-- ① 找引用该文件的页面
SELECT xid, xname, xportal FROM X.PTL_PAGE
 WHERE xdata LIKE '%<fileId>%';
-- ② 找文件本体
SELECT xid, xname, xlength, CHAR_LENGTH(xdata) FROM X.PTL_FILE WHERE xid='<fileId>';
--    0b084672-…/ logo.png / 14376 / 19168（base64 字符数）
```

**替换图（白色版！顶栏是蓝底）**：
```bash
# 生成白色版（黑底素材在蓝顶栏上看不见）
python tools/o2_make_brand_assets.py --top-white       # 或见下"白色化"要点
# 写回 PTL_FILE（★ base64 用 @b64 分段 CONCAT，避免单条 SQL 过长；走 stdin 而非 -e）
#   UPDATE PTL_FILE SET xdata=@b64, xlength=<新字节数> WHERE xid='<fileId>';
```
- ★ **白色化要点**：原素材是黑字透明底；顶栏是蓝底 → 用**亮度当 alpha 掩膜**、颜色统一置白：
  ```python
  lum = int(0.299*r + 0.587*g + 0.114*b)
  op[x,y] = (255,255,255, int(a * (255-lum) / 255))   # 越黑 → alpha 越高
  ```
- ★★ **回写后 HTTP 仍返回旧图 → 文件级缓存，必须 `docker restart o2oa-server`**（§4 C 类铁律，本次再次验证：
  不重启 HTTP md5 = 旧图 14376B；重启后 = 新图 6320B，与本地一致）。

#### 3.1e ★★★ 入口 logo 载体总表（四个位置都要改，缺一处就"还有翱途"）

| # | 载体 | 真源 | 生效方式 |
|---|---|---|---|
| 1 | 九宫格左下角「开始」按钮 | `$Default/blue/icons/logo_o2_40.png` | 烤镜像 (§3.1f) |
| 2 | 九宫格内容区水印 | `$Default/blue/icons/pic_logo_sy.png`（+logobg/logobg1） | 烤镜像 (§3.1f) |
| 3 | **index.html 左上角 logo** | **`PTL_FILE.xdata`**（门户页面内嵌 `<img>`） | SQL 回写 + **重启** (§3.1d) |
| 4 | 浏览器 tab 标题 | ① 入口 HTML 的 `<title>`；② **门户页面 `PTL_PAGE.xname`**（打开后覆盖，§5.2） | 烤镜像 / SQL |

> ★ 用户说"logo 还没改"时，先问是**哪个入口、哪个位置** —— 四个载体互不相干，改一个不影响其它。

#### 3.1f ★★ 九宫格的两个"隐形"事实：logo 由 CSS 渲染、图标住在「开始菜单」弹层

**会话来源与判据（多源取并集，别只读一处）**：
```js
var s = (window.layout && layout.session) || {};
var u = s.user || {}, ud = s.userDetail || {};
// ① tokenType（管理员登录 token 的 tokenType === "manager"）——最可靠
if (u.tokenType === "manager" || s.tokenType === "manager") return true;
// ② 角色列表（roleList 常落在 userDetail 而非 user）
[].concat(u.roleList||[], ud.roleList||[]).some(r => String(r).includes("Manager@ManagerSystemRole@R"));
// ③ 用户名兜底
["admin","xadmin"].indexOf(String(u.unique||u.name||"").toLowerCase()) > -1;
```

**★ 三态返回，不能用布尔**：`session` 是异步填充的，过早判断会**把管理员误弹出去**。
```js
function isManager(){
  var s = (window.layout && layout.session) || {};
  var u = s.user || {};
  if (!u.unique && !u.name && !s.tokenType && !u.tokenType) return null;  // ← 未就绪，继续等
  /* …判据… */
  return true | false;   // true=管理员；false=确定非管理员 → replace("index.html")
}
// 轮询：null 继续等，false 立刻弹走，true 结束轮询；超时 MAX_WAIT 兜底放行（宁可放行不可误杀）
```

**纪律**：超时**放行**而非拦截 —— 守卫的本意是"挡普通用户"，不是"锁死管理员"。
把超时做成拦截 = 网络慢时管理员进不去自己的后台，比不守卫更糟。

#### 3.1g ★★ 残留 tab 真根因：**服务端持久化 layout 的 `apps`**（不是缓存、不是 HTML）

**症状**：admin.html 打开后顶部挂着一条旧 tab，标题是改名前的品牌词（如「翱途（O2OA）办公系统」），
虽然页面上其它位置的品牌都改对了。用户截图里"镶嵌在里面的旧品牌"就是它。

**根因链条**：
```
Default.js:441 loadStatus()
  → 读 layout.userLayout.apps（持久化在服务端）
  → 对每一条 .createTaskItem() 重建 tab
```
- `layout.userLayout` 存在 **`GET/PUT /x_organization_assemble_personal/jaxrs/custom/layout`**（个人定制数据）。
- `?default=false` **只跳过 `loadDefaultPage()`**，对 `loadStatus()` 重建历史 tab **无能为力**。
- **换浏览器/无痕窗口不复现** ← 因为它不在页面里，在**该用户的账号数据**里。
  ★ 诊断时若用全新 context 探测"DOM 里有没有旧品牌"会得到 `false`，从而**误判为缓存问题**（本会话踩过）。

**查**：
```bash
python tools/o2_desktop_layout_audit.py --audit            # 打印各用户 currentApp/apps
# 或直接看 admin 的 layout 里 apps 是否含 portal.Portal<改名前的门户id>
```
**清**：
```bash
python tools/o2_desktop_layout_audit.py --clean-apps       # 移除 apps 中 portal.Portal* 残留 + currentApp 归位空串
```
**双保险**：`admin.html` 里再加一段前端兜底（页面加载后关掉所有非首页 tab）——
因为**存量用户的 layout 各有各的残留**，脚本只能清已知账号。

#### 3.1e ★★ 九宫格的两个"隐形"事实：logo 由 CSS 渲染、图标住在「开始菜单」弹层

**① 九宫格的 logo/水印不是 HTML 里的 `<img>`，是 CSS `background-image`。**

| CSS 类 | 图片 | 尺寸/位置 |
|---|---|---|
| `.logo_o2_40` | `…/<skin>/icons/logo_o2_40.png` | 40×40，左下角「开始」按钮 |
| `.logobg` | `…/<skin>/icons/pic_logo_sy.png` | 500×300，内容区水印 |

- CSS 文件：`servers/webServer/o2_core/o2/xDesktop/$Default/<skin>/style-skin.css`
- 壳文件：`$Default/blue/layout-pc.html`（`class="layout_menu_start_button logo_o2_40"` / `class="layout_content_apps logobg"`）
- **⇒ 只改 `<title>` 或 HTML 里的文字，九宫格上的 logo 纹丝不动。必须替换 PNG。**
- 本项目替换 4 张（见 `Dockerfile`）：
  `logo_o2_40.png` / `pic_logo_sy.png` / `logobg.png` / `logobg1.png` → 协会品牌图。
- 生成脚本：`tools/o2_make_brand_assets.py`（从 367×165 原图按**列**切出标识方块，再按需缩放/做水印）。
  ★ **水印陷阱**：原图标识内部是**白色不透明填充**，若按 alpha 统一着色会糊成实心圆 →
  必须保留原始黑白对比，**只整体降 alpha**（`putalpha(src_a.point(lambda v: int(v*0.35)))`）。
- ★ 只替换了 **blue 皮肤**；用户在开始菜单换皮肤会回到官方 logo（已在 Dockerfile 注释说明）。

**② 九宫格图标住在「开始菜单」弹层里，tab 全关则主区域空白。**

- 只把 tab 关掉 → 桌面区域**空空如也**（不是九宫格！本会话踩过：截到空白桌面）。
- 必须显式展开：**`layout.desktop.showStartMenu()`**（`Default.js:799`，公开方法）。
- 前端兜底逻辑（放在 §3.1d 那段 close-tabs 之后）：
  ```js
  var d = window.layout && layout.desktop;
  if (d && typeof d.showStartMenu === "function") d.showStartMenu();
  ```
- 轮询条件：等 `layout.desktop.apps` **非空**后延迟 ~350ms 再关 tab + 展开；
  若 `apps` 一直为空但 `showStartMenu` 已存在（>3s），**直接展开**（没有历史 tab 的用户走这条）。

#### 验证工具（本 skill 附带，装在 `tools/`）

```bash
# 主页面（index.html）：期望 13 组件 + 80 项左导航 + index-content 1 层 + pageerror 0
python tools/o2_verify_homepage.py mengyijie
# 九宫格（admin.html）：期望 URL 自动带 ?default=false + widgetTitle 0 + 正文为九宫格菜单
python tools/o2_verify_admin_desktop.py admin

# ★ 2026-09-28 新增（入口职责分离验证组）
python tools/o2_verify_entry_split.py          # admin/mengyijie 双入口齐备：index=13组件+80导航；admin=tabs0+无旧品牌+品牌图 md5 一致
python tools/o2_verify_admin_guard.py          # 普通用户(luoshuhan)访问 admin.html 被弹回 index.html 且渲染多栏仪表盘
python tools/o2_verify_admin_grid.py           # admin.html 打开即自动展开九宫格（.layout_start_item 计数）
python tools/o2_desktop_layout_audit.py --audit      # 查各用户 layout 的 apps 残留
python tools/o2_desktop_layout_audit.py --clean-apps # 清 apps 里的 portal.Portal* 残留
```

---

### 3.2 ★★★ 生效纪律：**webroot 命名卷 > 镜像层**（2026-09-28 重大修正，推翻此前"COPY 烤镜像即可"的结论）

**两条路径，层级不同，务必分清：**

| 路径 | 层级 | 说明 |
|---|---|---|
| `/opt/o2server/servers/webServer/x_desktop/*.html` | **镜像层** | `Dockerfile COPY` 烤进来的位置 |
| `/opt/o2server/webroot/x_desktop/*.html` | **命名卷** `o2oa_o2oa-webroot` | O2OA 的「用户自定义资源目录」 |

**★★ 关键机制：`webroot` 是命名卷，O2OA 启动时把它并入静态资源，且优先级高于镜像层。
卷内一旦存在同名文件，就会把镜像层的定制文件整个盖住。**

**真实事故（2026-09-28）**：`webroot/x_desktop/index.html` 里躺着 09-23 的旧版
（空 `<title></title>`、只有两分流、缺 `_HOME_ENTRY_USERS`/`index_home.html`），
把 09-26 烤入镜像的**三分流新版**完全覆盖 →
用户"**重启电脑后首页变回去了**"。

**为什么极难发现**：
- 看镜像层 `servers/webServer/x_desktop/index.html` → **是新的、正确的** ✅（被骗）
- 看 HTTP 返回 → 取决于卷与镜像的合并结果
- **必须单独去看卷层** `/opt/o2server/webroot/x_desktop/` 才能找到真凶

**正确改法（三步都要）**：
```bash
# ① 改 git 真源（deploy/host/x_desktop/ 三份）—— 唯一真源
# ② 同步进 webroot 卷（★关键，否则重启被打回旧版）
python tools/o2oa_sync_webroot_volume.py          # 幂等 + md5 校验
python tools/o2oa_sync_webroot_volume.py --check  # 只校验
# ③ 校验 HTTP 实际返回
curl -s http://localhost:9090/x_desktop/index.html | md5sum
```
> `Dockerfile COPY` 仍然要做（保镜像层正确），但**只做 COPY 不够** ——
> 卷里有旧同名文件时，COPY 出来的新版永远不生效。**两处都要，缺一不可。**
> 反向亦然：只改卷不改真源 → 下次重建/换机就丢，且无法回溯。

**诊断口诀（三层都要看）**：
```bash
# 镜像层
MSYS_NO_PATHCONV=1 docker exec o2oa-server md5sum /opt/o2server/servers/webServer/x_desktop/index.html
# 卷层  ★最容易漏、最可能是真凶
MSYS_NO_PATHCONV=1 docker exec o2oa-server md5sum /opt/o2server/webroot/x_desktop/index.html
# 真源
md5sum deploy/host/x_desktop/index.html
# HTTP 实际
curl -s http://localhost:9090/x_desktop/index.html | md5sum
```
三者不一致 → 按「卷优先」判定实际生效版本。**卷里有文件就信卷。**

> ★ **本机 QEMU 陷阱（2026-09-28 实测）**：`docker exec` 会随机报
> `OCI runtime exec failed: ... setns process: ... /proc/self/fd/6: no such file or directory`，
> 此时**读不到文件 ≠ 文件不存在**。直接判"卷内缺失"会把人带沟里（曾误认为修复被容器重启抹掉）。
> **回退通道**：用临时容器挂同一卷读取 ——
> ```bash
> docker run --rm -v o2oa_o2oa-webroot:/wr --entrypoint sh alpine:latest -c "md5sum /wr/x_desktop/index.html"
> ```
> `tools/o2oa_sync_webroot_volume.py` 已内置双通道探测，优先用它。


### 3.3 ★ 坑：`res/config/config.json` **不可**静态 COPY

- 该文件由服务端 `WebServers.updateWebServerConfigJson()` 在 **web 服务每次启动时**
  按「系统配置（`collect.json` 的 title/footer）」**动态生成**；前端 `bundle.js` 读它设置 `document.title`。
- **静态 COPY 会劫持这条链路** → 系统配置与登录页标题/页脚不一致
  （2026-09-26 实证后**已从 Dockerfile 移除**）。留在 `deploy/host/x_desktop/res/config/` 仅作参考快照。
- 要改标题/页脚 → 改**系统配置**，不是改这个文件。
- ★★ **同理，`indexPage` 也不能改这个文件** —— 它是服务端按 `config/portal.json` 生成的**产物**。
  改 `indexPage` 的唯一正确入口：
  ```bash
  PUT /x_program_center/jaxrs/config/portal     # body = 裸对象，改 data.indexPage
  ```
  PUT 后 **无需重启**，`/x_desktop/res/config/config.json` 会实时刷新（实测 3 秒内）。
  ```bash
  # 复核（应看到 enable:true + portal:<内容门户id>）
  curl -s http://localhost:9090/x_desktop/res/config/config.json | python -m json.tool | grep -A4 indexPage
  ```
  > 事故原型：反复改 `config.json` 文件、反复 `docker cp`，全都不生效 ——
  > 因为它是**每次启动重新生成的**，且 `Dockerfile` 明确不 COPY 它。
  > 真源在数据库侧的 `config/portal.json`。

### 3.4 诊断与恢复

**先证明"线上到底返回了哪份文件"——必须三层齐看（漏一层就会误判）**：
```bash
# ① 镜像层（Dockerfile COPY 的目标）
MSYS_NO_PATHCONV=1 docker exec o2oa-server md5sum /opt/o2server/servers/webServer/x_desktop/index.html
# ② 卷层 ★★★ 最关键、最容易漏 —— 卷里有同名文件就以卷为准
MSYS_NO_PATHCONV=1 docker exec o2oa-server ls -la /opt/o2server/webroot/x_desktop/
MSYS_NO_PATHCONV=1 docker exec o2oa-server md5sum /opt/o2server/webroot/x_desktop/index.html
# ③ git 真源
md5sum deploy/host/x_desktop/index.html
# ④ HTTP 实际返回
curl -s http://localhost:9090/x_desktop/index.html | md5sum
```
一键对比（推荐）：
```bash
python tools/o2oa_sync_webroot_volume.py --check
```
**恢复**：`git checkout -- deploy/host/x_desktop/`（确保真源正确）
→ `python tools/o2oa_sync_webroot_volume.py`（同步进卷）
→ `curl` 复验 md5 → `docker restart o2oa-server` 后再验一次（确认扛得住重启）。

> ★ **"重启后变回去了"= 卷覆盖的典型症状**，不要往数据层查。
> 反向症状（改了没生效、重启才生效）也常是卷/缓存所致。


## 4. C 类：logo / 图标替换与回退

- 门户 logo 存在 `PTL_FILE`（base64 在 `xdata`，另有 `xlength`、`xshortUrlCode`）。
- **回退 = 整行字段还原**（`xdata` + `xlength` 必须成对，`xshortUrlCode` 还原为原值如 `NULL`），
  然后 `GET /x_portal_assemble_surface/jaxrs/file/{id}` 验 **200 + 字节数 + md5**。
- ★ **回写后端点仍返回旧图** → flag 级缓存，`docker restart o2oa-server` 才生效。
  （"第一次改立即生效"是因为更新后首次读取，别据此认为不需要重启。）
- 纪律：**改动后要验的是"页面功能"，不止图片端点**；**未获用户实测确认前，不要顺手"修"关联字段**，
  保持最小改动。品牌图类改动优先走"设计器导出 → 改 → 导入"的正规链路，直改 DB 属高危。

## 5. D 类：品牌残留定位与治理

### 5.1 先建"载体清单"，别只改一处

| 载体 | 字段 | 是否渲染 |
|---|---|---|
| 门户页面 | `PTL_PAGE.xname`/`xalias`/`xdata` 内嵌 `name` | **运行时窗口标题真源** |
| 门户自定义布局 | `ORG_CUSTOM.xdata`（`xname='layout'`） | 页面内文案 |
| 首页入口文件 `<title>` | `deploy/host/x_desktop/*.html`（§3） | 静态标题 |
| 系统配置（登录页标题/页脚） | `collect.json` → 动态生成 `res/config/config.json` | 登录页 |
| CMS 应用/栏目 | `CMS_APPINFO` / `CMS_CATEGORYINFO` 的 `xcreatorTopUnitName` | 元数据，信息列表可见 |
| 公文字号/红头 | `QRY_ITEM.xstringShortValue`（`xpath0`=crowns/redHeaders）+ `PP_C_SNAP.xproperties` | 表单字段 + 流程快照 |
| 附件/图片 | `PTL_FILE.xdata` | 图形 |

### 5.2 窗口标题真源 = 页面名（"admin 对了、用户没对"的错觉）

`x_component_portal_Portal/Main.js` 第 131 / 207 行 `this.setTitle(pageName);`
——打开门户页面时**标题被页面名覆盖**。所以：
`admin` 走 `admin.html`、不打开门户页 → 取 config.json（对）；普通用户走 `index.html` 内联打开门户页 → 被页面名覆盖（错）。
**判断品牌残留是不是这里：拿普通用户（非 admin）看标题，或看无痕窗口；无痕仍复现就不是缓存。**

**改名（安全写法，只动名字字段）**：
```sql
UPDATE X.PTL_PAGE SET
  xname  = REPLACE(xname,  '旧品牌', '中国复合材料工业协会内部管理系统'),
  xalias = REPLACE(xalias, '旧品牌', '…'),
  xdata  = REPLACE(xdata,  '旧品牌', '…')
WHERE xdata LIKE '%旧品牌%' OR xname LIKE '%旧品牌%';
```
> ★ 绝不带上 `xproperties`。

### 5.3 公文品牌词：**两层存储**，改一层必漏

| 层 | 表.字段 | 说明 |
|---|---|---|
| 表单数据落点 | `QRY_ITEM.xstringShortValue`（`xpath0`=crowns/redHeaders/datatable） | QRY_ITEM 不只是索引，**它就是 CMS+表单/流程+表单的数据落点** |
| 流程配置快照 | `PP_C_SNAP.xproperties`（JSON） | 早期脚本只覆盖 QRY_ITEM，这里最易漏 |

工具：`D:\O2OA\tools\rename_gongwen_brand.py`（幂等 + 终态复查）。

**★ 字号类命名是「用户业务口径」，不是字面翻译**。demo 里带地域字（如「杭」）的字号，
迁移后按用户口径收敛，**先问用户再批量改**。事故原型：把 `X杭综字` 字面译成 `复协杭综字`，
用户判定应为 `复协综字` → 必须补一次回纠。

**★ 批量改名脚本必须自带「上一版映射的回纠」（`FIXUP_MAP`）**：
脚本是幂等的，**重跑不会修它自己上一版写坏的值**，会形成"幂等但不可纠偏"的死角。
范式：
```python
CROWN_MAP = [('旧A','新A'), ...]          # 正向映射（长串在前）
FIXUP_MAP = [('上一版写错的值','正确值')]  # 回纠，先执行
```

### 5.4 全库扫描（归零判据）

工具：`D:\O2OA\tools\scan_brand_words.py`
```bash
python tools/scan_brand_words.py 翱途 纵横 杭综      # CLEAN / HIT 逐词报告，退出码 0/1
```
两个实现要点（都是踩坑）：
1. **完整性自证**：先查 `information_schema` 里 blob/binary 列数，为 0 才敢说"文本列扫描=完整"。
2. **SQL 走 stdin 传给 `docker exec -i mysql`**；走 `-e "…"` 的长语句会被 argv 长度/沙箱钩子
   拦成 **SIGTERM 静默失败**；**禁用 `GROUP_CONCAT` 拼 SQL**（默认 1024 字节截断 → md5 比对无效）。

**扫描结果要分类**（不是所有命中都要清）：
- 自己的组织品牌残留 → 清（含元数据如创建者单位名）。
- 软件产品自身品牌（O2OA / 翱途 的发行包文案、初始化向导、安装日志 `CTE_INSTALL_LOG`）→ **保留**。
- ★ **DB 扫描扫不到静态文件**：首页/登录页的文案在 `x_desktop/*.html` 与 `collect.json`，要单独 grep。

## 6. 标准作业顺序

```
① 分类（§1 分流树）——先决定是数据层还是文件层，别猜
② 备份整行（backups/*.sql 或 *.txt）/ 确认 git 真源干净
③ 诊断（对应 SQL / API 自测 / md5+curl 比对）
④ 最小改动：
     数据层 → SQL REPLACE（设计数据只动名字字段）
     文件层 → 只改 deploy/host/x_desktop/ 三份 + docker compose build o2oa && up -d
⑤ docker restart o2oa-server（数据层改动必做；清 flag 缓存，不做这步必误判）
⑥ 双验：MySQL 全库复扫 + HTTP 取回值（文件层再加 md5 比对）
⑦ 真机验证（普通用户视角、关 F12、Ctrl+F5 强刷）
⑧ 沉淀：KB 章节 + 脚本入库 + git 提交
```

## 7. 反面清单（别做）

- ✗ 用设计器 API 保存页面/表单来"顺手改个标题"。
- ✗ 只比 `xdata`/`xname` 就断言"数据完好"（漏 `xproperties`）。
- ✗ 报"点了没反应"就去改 `index.html`（多半是 §2 A 类，白改）。
- ✗ **只做 `Dockerfile COPY` 就以为定制生效** —— webroot 卷里有同名旧文件时会被完全盖住（§3.2）。
- ✗ **"重启后变回去了"却去查数据库** —— 十有八九是 webroot 卷覆盖（§3.4）。
- ✗ 在容器里改 `x_desktop/*.html` 当成持久修复（bind mount 无效、重建即丢；真源是 git）。
- ✗ 只改卷不改 git 真源（换机/重建就丢，无法回溯）。
- ✗ 把 `res/config/config.json` 静态 COPY 进镜像（劫持动态生成链路）。
- ✗ **改 `indexPage` 时去动 `res/config/config.json` 文件** —— 它是启动时生成的产物，改它永远无效；
  正确入口是 `PUT /x_program_center/jaxrs/config/portal`（§3.3）。
- ✗ **用户说"定制首页文件丢了"，就去 x_desktop 翻 HTML** —— 图1 从来不是 HTML，是三层配置（§3.1b）。
- ✗ **用 `window.layout.noDefault = true` 想让 admin.html 跳过门户首页** ——
  `initData()` 会无条件重算并覆盖它（Default.js:131）。必须用 `history.replaceState` 写 URL 参数（§3.1b）。
- ✗ 开了 `indexPage.enable=true` 就以为 admin.html 不受影响 —— 它是全局开关，会顶掉九宫格（§3.1b）。
- ✗ 用 `docker cp` 改 `servers/webServer/x_desktop/*.html` 就当修好 —— 只改可写层，HTTP 可能仍返回旧版（实测）；
  必须 `docker compose build o2oa && up -d`（本项目该目录是镜像层，非卷）。
- ✗ **用"前端按角色 `location.href` 分流"实现入口分离** —— 白屏闪烁、判据易错，且被卷旧版覆盖后
  "分流逻辑整个消失"却看不出来。正确做法：各入口自持职责 + 只有 admin.html 做守卫（§3.1b）。
- ✗ **把 `?default=false` 直接 `replaceState` 留在地址栏** —— 用户明确要求不可见；
  必须「`x.min.js` 前写入 → boot 完成后抹掉」两步走（§3.1b）。★ 抹的时机是关键，过早会退回仪表盘。
- ✗ **以为改了 admin.html 的九宫格 logo，index.html 的 logo 也会跟着变** ——
  两者不同源：admin 是 CSS `background-image`（PNG），index 是门户页面内嵌 `<img>` 指向 `PTL_FILE`（§3.1d/§3.1e）。
- ✗ **给 index.html 顶部 logo 换成黑色版素材** —— 顶栏是蓝底，黑字看不见；须做白色版（§3.1d 白色化）。
- ✗ **改完 `PTL_FILE.xdata` 不重启就断言"没生效"** —— 文件级缓存，必须 `docker restart o2oa-server`（§3.1d）。
- ✗ **在 index.html 里判断"是不是管理员"再决定是否外跳** —— 判错就把管理员关在门外；守卫只该保护 admin.html。
- ✗ **管理员守卫用布尔返回、session 未就绪就下结论** —— 必须三态（null=再等 / false=弹走 / true=放行），
  且超时**放行**不拦截（§3.1c）。
- ✗ **看到 admin 页面残留旧品牌 tab，就去查缓存 / 改 HTML** —— 真因是该用户服务端 layout 的 `apps`
  （`…/jaxrs/custom/layout`），换无痕窗口不复现即为铁证；用 `o2_desktop_layout_audit.py --clean-apps`（§3.1d）。
- ✗ **用全新 playwright context 探测"DOM 里有没有旧品牌"** 来判残留 —— 无持久 layout 故必然为 false，会误判成"缓存问题"。
- ✗ **只改 admin.html 的 `<title>`/HTML 文字，就以为九宫格 logo 改了** —— logo 是 CSS `background-image`，
  须替换 `$Default/<skin>/icons/` 下 `logo_o2_40.png`、`pic_logo_sy.png` 等 PNG（§3.1e）。
- ✗ **只关掉历史 tab 就以为得到九宫格** —— tab 全关后主区空白，必须调 `layout.desktop.showStartMenu()` 展开（§3.1e）。
- ✗ **水印生成时按 alpha 统一着色** —— 原图标识内部为白色不透明，会糊成实心圆；应保留黑白对比、只整体降 alpha。
- ✗ 用 `GROUP_CONCAT` 拼扫描 SQL、用 md5 比"无差异"。
- ✗ 改完不重启就下结论。
- ✗ 未获用户确认就动关联字段（`xshortUrlCode` 等）。
- ✗ 把软件产品自身品牌（O2OA/翱途发行包文案）当残留清掉。

## 8. 证据出处

`D:\O2OA\ai-stack-hardening\docs\knowledge-base.md` 第 13~20 章（含源码行号、SQL、实测数据）；
`docs\knowledge_base\portal_brand_guard.md`（同一总纲的 KB 版，已入 RAG 库）。
工具：`tools/scan_brand_words.py`、`tools/rename_gongwen_brand.py`、`tools/fix_wenzhong_orgname.py`、
`tools/o2oa_sync_webroot_volume.py`（卷同步）、`tools/o2_verify_homepage.py`（主页面验证）、
`tools/o2_verify_admin_desktop.py`（九宫格验证）、`tools/o2_verify_entry_split.py`（入口分离）、
`tools/o2_verify_admin_guard.py`（守卫）、`tools/o2_verify_admin_grid.py`（九宫格展开）、
`tools/o2_desktop_layout_audit.py`（layout 残留审计/清理）、`tools/o2_make_brand_assets.py`（品牌图生成）。
文件真源：`deploy/host/x_desktop/`（index.html / admin.html / index_home.html 三份）+ `Dockerfile` 第 222~249 行（含 4 条品牌图 COPY）。
机制源码：`servers/webServer/o2_core/o2/xDesktop/Default.js`
（`:131` noDefault / `:151` load / `:343` loadDefaultPage / **`:441` loadStatus 重建 tab** /
**:799` showStartMenu 展开九宫格**）；
`$Default/<skin>/style-skin.css`（`.logo_o2_40` / `.logobg` 的 `background-image`）；
`x_desktop/js/x.min.js`（boot：`getUserLayout` → `new MWF.xDesktop.{Layout|Default}` → `.load()`，无公开钩子故须轮询）。
