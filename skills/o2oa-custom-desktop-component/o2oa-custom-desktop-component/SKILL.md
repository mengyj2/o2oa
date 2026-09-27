---
name: o2oa-custom-desktop-component
description: 在 O2OA（社区版 / Docker 自托管，10.0.2 实证）上**从零自研一个桌面组件(`x_component_XXX`)并把它挂到菜单上真正打开**，或**排查"点开应用是一片空白"**。当用户说"自己写个 O2OA 应用/组件""复刻官方某应用""点开 XX 一片空白/白屏""新组件不生效""Main.js 加载了但没渲染""requireApp 加载不到""n.Main is not a constructor""改了一个入口另一个还是老界面""开始菜单的应用指向哪""**系统管理里没有我加的应用**""门户首页没有新应用""企业网盘换成自己写的"时调用。覆盖：组件目录与命名约定、**★ 必须成对提供 `*.min.js`（非调试会话会改写文件名，这是白屏的头号根因）**、`layout.openApplication` / `_requireJs` 加载链实证、**★★ 桌面有两个「开始菜单」且来源完全不同（☰ 图标网格 ← CPT_COMPONENT；门户首页应用菜单 ← 数据字典 appmenus，与 CPT_COMPONENT 无关）**、三入口全量对照表、改完何时需要 `docker restart`、以及用 playwright-core 直驱做**真机 UI 回归**的正确姿势（agent-browser daemon 卡死的替代方案 / REST 取 x-token 注入 cookie 绕过登录 / eval 只接受一个参数）。
agent_created: true
category: development
---

# O2OA 自研桌面组件（x_component_*）落地与「白屏」根治

适用 O2OA 10.x（Docker 自托管 10.0.2 实测）。**面向"官方应用拿不到，自己写一个"的场景**：
数据层尽量复用既有后端服务，只自研 UI 层；然后把**所有入口**一个个改指过去。

## 0. 两条铁律（不遵守必白屏）

### 铁律 1 · ★ 必须成对提供 `*.min.js`

`servers/webServer/o2_core/bundle.js` 里 `_requireJs` 在**非调试会话**下会改写路径：

```js
var jsPath = (compression || !this.o2.session.isDebugger) ? url.replace(/\.js/, ".min.js") : url;
```

即 `x_component_Foo/Main.js` 实际被请求成 **`Main.min.js`**。
官方组件都是 `Main.js` + `Main.min.js` **成对发布**（如 `x_component_File`：
52159B / 27629B），所以这条约定很不显眼。

**只放 `Main.js` 的后果**（症状与根因对照，照这个表反查最快）：

| 现象 | 根因 |
|---|---|
| 点开应用**一片空白**，应用窗口 `.appContent` 的 `innerHTML.length` = 0 | `Main.min.js` 404 → `MWF.xApplication.<Name>` 根本没注册 |
| 控制台 `Cannot read properties of undefined (reading 'options')` | `layout.openApplication` 里 `appNamespace.options` 拿到 undefined |
| 控制台 `n.Main is not a constructor` | 同上，`new undefined` |

**做法**：同名复制即可，**内容不必真的压缩**（O2OA 只看文件名）。

```bash
cp Main.js Main.min.js
cp lp/zh-cn.js lp/zh-cn.min.js      # 语言包同理
```

自己用 `<script src>` 显式注入的子文件（如 `drive/drive.js`）**不走** `_requireJs`，
不受影响——但仍建议成对留一份，便于将来改成框架加载。

### 铁律 2 · ★ 一个应用可能有 3 个入口，数据源各不相同

**只改一处 = 改了一半**，表现为"点某个入口还是老界面 / 另一个入口空白"。
（★ 入口 1 与入口 2 是**两个不同的菜单**：☰ 图标网格 vs 门户应用菜单，
详见「铁律 4」——只写 CPT_COMPONENT 会让用户在门户首页里找不到你的应用。）

| # | 入口 | 数据源 | 桌面/门户怎么用它 |
|---|---|---|---|
| 1 | 桌面「开始」菜单 | MySQL **`CPT_COMPONENT`**（`xname`=菜单名，**`xpath`=组件名**） | 桌面拿 `xpath` 当 app 名直接调 `layout.openApplication(null, xpath)` |
| 2 | 门户「应用列表」/「所有应用」 | **`GEN_DICT` + `GEN_DICT_ITEM`**（`appNavis/<组>/children/<项>/{title,app,actionType}`） | `actionType=app` 时用 `app` 字段开应用 |
| 3 | 桌面开始菜单深链 / 门户 `pcClient` | `$Layout/applications.json`（`"@url:"`）/ `PTL_PORTAL.xpcClient` | 流程应用深链与门户图标；**不含普通应用时无需处理** |

排查入口用只读 SQL（先把三处都列出来，别猜）：

```bash
# 入口 1：谁指向"企业网盘"这个名字
docker exec o2oa-mysql mysql --default-character-set=utf8mb4 -uroot -po2oa_root_pwd X -t \
  -e "SELECT xid,xname,xpath,xtype,xvisible FROM CPT_COMPONENT WHERE xname LIKE '%网盘%';"

# 入口 2：门户字典
docker exec o2oa-mysql mysql --default-character-set=utf8mb4 -uroot -po2oa_root_pwd X -t \
  -e "SELECT xid,xpath0,xpath1,xpath2,xpath3,xstringShortValue FROM GEN_DICT_ITEM \
      WHERE xbundle='<GEN_DICT.xid>' AND xstringShortValue IN ('File','Drive');"
```

改完全部入口后**必须 `docker restart o2oa-server`**（组件索引与字典都有内存缓存，
不重启实测不生效）。

### 铁律 3 · ★★ 自研 Viewer 必须用「普通构造函数 + prototype」，**不要**用 MooTools `new Class({...})`

2026-09-23 实测踩坑：把 Viewer 写成

```js
MWF.xApplication.Foo.Viewer = new Class({
    Implements: [Options, Events],           // ★ 这里开始埋雷
    options: { "container": null, "app": null },
    initialize: function (options) {
        this.setOptions(options);            // ★★ 爆点
        this.build();
    },
    build: function () { ... }
});
```

症状：窗口**打开了**（标题栏可见），但内容区只有一行红字
**`初始化失败：Maximum call stack size exceeded`**，而**控制台零报错**
（异常被 Main.js 的 try/catch 吞掉），极容易被误判成"没渲染 / 白屏"。

**根因**：`Implements:[Options]` 会让 `setOptions(opt)` 走 MooTools 的 `Object.merge`，
它是**深合并**；而传入的 `opt.app` 是 **Main 实例**（挂着 `content` 等 DOM 节点，
DOM 有 parentNode/childNodes 循环引用）⇒ 深拷贝无限递归。

**正确写法**（`x_component_Drive` 的 `drive/drive.js` 就是这么做的）：

```js
(function () {
    function Viewer(opt) {
        this.container = opt.container;   // 直接取用，不 merge
        this.app = opt.app;
        this.build();
    }
    Viewer.prototype = {
        build: function () { this.container.innerHTML = "..."; },
        // …其余方法照常写  name: function () {}
    };
    MWF.xApplication.Foo.Viewer = Viewer;   // 手动挂命名空间
})();
```

Main（`Extends: MWF.xApplication.Common.Main`）**继续用 Class 没问题** ——
它只 Extends，没把 app 实例塞进 options。

### 铁律 4 · ★★ 桌面有**两个**「开始菜单」，来源完全不同 —— 别只挂一个

2026-09-23 实证（此前"两处双写"的认知**不完整**，只挂 CPT_COMPONENT 会让用户
在门户首页里**看不到**新组件，表现为"系统管理分组下没有我加的那一项"）：

| # | 菜单 | 谁驱动 | 长什么样 |
|---|---|---|---|
| A | **☰ 开始菜单** | MySQL **`CPT_COMPONENT`**（种子 `config/components.json` 的 `systems`） | 白色**图标网格**，顶部页签 `应用/流程/信息/数据` |
| B | **门户首页「应用菜单」** | **只由门户数据字典 `appmenus` 驱动，与 `CPT_COMPONENT` 无关** | 左侧**竖排分组**（宽屏）；窄屏变成**深蓝分栏大菜单**；分组标题=字典 `appNavis[].title` |

⇒ **要"整套都有"，A、B 都要写。**

#### A. 挂进 ☰ 开始菜单（CPT_COMPONENT + 种子）

DB 是运行时累积、`config/components.json` 是种子，两者逐项一致 ⇒ 双写保险：

```bash
# ① DB 插一行（xid 用【带连字符】UUID；xvisible 是 bit(1)）
docker exec o2oa-mysql mysql --default-character-set=utf8mb4 -uroot -po2oa_root_pwd X -e \
 "INSERT INTO CPT_COMPONENT (xid,xcreateTime,xupdateTime,xname,xpath,xtitle,xtype,xiconPath,xorderNumber,xvisible)
  SELECT UUID(),NOW(),NOW(),'Foo','Foo','我的应用','system','appicon.png',28,1 FROM DUAL
  WHERE NOT EXISTS (SELECT 1 FROM CPT_COMPONENT WHERE xname='Foo');"

# ② config/components.json 的 systems 数组追加同名项，再 docker cp 回容器 + docker restart
```

**注意官方字段拼写是 `dentyList`（不是 denyList）**，照抄别改：

```json
{"name":"Foo","path":"Foo","title":"我的应用","iconPath":"appicon.png",
 "orderNumber":28.0,"type":"system","allowList":[],"dentyList":[]}
```

若只要求出现在 ☰ 开始菜单、不必归到系统分组，用官方 REST 更省事：
`POST /x_component_assemble_control/jaxrs/component {name,path,title,iconPath,orderNumber,visible}`

#### B. 挂进门户「应用菜单」（数据字典 appmenus）★

```bash
# 读（★ flag 是门户 alias，本部署「系统首页」的 alias = index；写成 /portal/dict/data 会 500）
GET {SURFACE}/x_portal_assemble_surface/jaxrs/dict/appmenus/portal/index/data
#   -> data.appNavis[]：分组数组；每组 children[]：{actionType,app,allow,icon,title,...}

# 写（surface PUT 恒 405！必须走 designer 整对象覆盖）
PUT {DESIGNER}/x_portal_assemble_designer/jaxrs/dict/{dictId}
#   body = 上一步读到的那个 data 对象本身（含 data.appNavis / id / application / name / alias）
```

新增条目的字段（`app` = **`x_component_` 后面的目录名**，不是 CPT_COMPONENT 的 xname）：

```json
{"actionType":"app","app":"Foo","allow":[],"appOptions":"","disabledGroup":[],
 "hide":false,"icon":"config","level":1.0,"notHideMainNavi":"",
 "portal":[],"portalOptions":"","reject":[],"title":"我的应用"}
```

- `allow: []` = 不限角色（对所有人可见）；填角色则只对持该角色者显示，
  格式 `Role@RoleSystemRole@R`（如 `Manager@ManagerSystemRole@R`）。
- `icon` 必须取字典里**已出现过的图标名**（官方实测可用：`config`、`m1`、`file-text`、
  `integral`、`a-flowprocess`、`platform`、`description`、`profile`…），乱填会不显示图标。
- 分组 `appNavis[i].title='系统管理'` 里的 `children` **数组顺序即显示顺序**。
- **改完刷页面即生效，不必 `docker restart`**（字典是页面渲染时拉的）。

#### 验证必须走真实路径

`☰ 开始菜单` 里的条目从 `CPT_COMPONENT` 来，**门户菜单**从字典来 ——
所以只验证一个会给出假 PASS。真机回归要**打开 `portal.html?id=<portalId>` →
展开目标分组 → 断言新条目在列 → 点它 → 断言组件真的渲染出来**。
（`ActionCreate` 会强制 `setType("custom")`）。

---

## 1. 组件目录与命名约定

```
servers/webServer/x_component_<Name>/
├── Main.js / Main.min.js        ← 必须成对！
├── lp/zh-cn.js / .min.js        ← 语言包（框架按会话语言加载，失败会回落 zh-cn）
├── $Main/
│   ├── icon.json                扩展名→图标映射（可选）
│   └── default/
│       ├── css.wcss             框架要求存在（内容 {} 即可）
│       ├── icon.png             应用图标
│       ├── file/                文件类型图标（可从别的组件复制复用）
│       └── icon/                导航/操作图标
└── <你的代码>.js / .css
```

`Main.js` 骨架（薄壳，业务全在自研 UI 文件里）：

```js
MWF.xApplication.Foo = MWF.xApplication.Foo || {};
MWF.xApplication.Foo.LP = MWF.xApplication.Foo.LP || { title: "…" };  // 兜底 LP

MWF.xApplication.Foo.Main = new Class({
    Extends: MWF.xApplication.Common.Main,
    Implements: [Options, Events],
    options: { style: "default", name: "Foo", icon: "icon.png",
               width: "1100", height: "700", title: "…" },
    onQueryLoad: function(){ this.lp = MWF.xApplication.Foo.LP; },
    loadApplication: function(callback){
        // this.content 就是窗口内容容器（可直接 appendChild 原生 DOM）
        // 需要额外 css/js 时用 <link>/<script> 显式注入，回调里再 new Viewer
        if (callback) callback();
    }
});
```

## 2. 加载链（读源码得来的实证）

```
入口(xpath 或 app = Name)
  → layout.openApplication(null, Name, options)
  → _requireApp → o2.requireApp(Name, 'Main', cb, true)
  → _requireAppSingle: 若 o2.xApplication[Name].Main 已存在则直接回调，
                       否则 _requireJs("../x_component_<Name>/Main.min.js")
  → <script>/XHR 执行 → new MWF.xApplication.Name.Main(options) → loadApplication()
```

命名规则（`_requireAppSingle` 里写死的）：
`module` 的点分段用 `_` 拼成目录 —— `"portal.Portal"` → `x_component_portal/Portal.js`；
所以 `xpath` 可以写 `cms.Index`、`process.ApplicationExplorer` 这种带点的形式。

**排查用的嵌入式探针**（在浏览器控制台 / agent-browser eval 里跑）：

```js
// 1) 组件代码本身有没有问题？（绕过框架，直接执行源码）
var x=new XMLHttpRequest(); x.open('GET','/x_component_Foo/Main.js',false); x.send();
try{ (new Function(x.responseText))();
     'OK Main='+typeof(MWF.xApplication.Foo&&MWF.xApplication.Foo.Main); }
catch(e){ 'EXEC-ERR: '+e.message; }

// 2) 框架通道通不通？
MWF.xDesktop.requireApp('Foo','Main',function(){
  window.__r='cb:'+typeof(MWF.xApplication.Foo&&MWF.xApplication.Foo.Main);
},true);

// 3) 加载器到底请求了哪个文件？（看网络或直接 fetch min 文件）
```

> 若 (1) 通过而 (2) 的命名空间仍 undefined ⇒ **几乎可以断定是铁律 1（min.js）**。

## 3. 判定「白屏」的输入法

```
1. 组件静态资源能不能取到？
   curl -s --noproxy "*" -o /dev/null -w "%{http_code} %{size_download}\n" \
        http://localhost:9090/x_component_Foo/Main.min.js
   → 404 或 0 字节 ⇒ 铁律 1 / 新目录未 docker restart
2. 命名空间注册了吗？（真机 eval）
   typeof (MWF.xApplication.Foo && MWF.xApplication.Foo.Main)
   → undefined ⇒ 文件没执行（看 1）；function ⇒ 代码没问题，看渲染层
3. 应用窗口 HTML 长度
   Array.prototype.map.call(document.querySelectorAll('.appContent'), n=>n.innerHTML.length)
   → 出现 0 的那个就是白窗（O2OA 每个应用窗口一个 .appContent）
4. 挂错误收集器再点一次，看有没有被吞掉的异常
   window.addEventListener('error', e=>console.log('ERR', e.message, e.filename, e.lineno), true)
```

**别用 `document.querySelector('.xxxContentNode')` 判断老 UI 是否在渲染**——
MooTools 用 `new Element(div, {styles: this.css.xxx})` 写的是**内联样式**，
不是 class 名，选择器永远匹配不到，会得出错误结论。

## 4. 真机 UI 回归（agent-browser）

后端接口自检**不能替代**前端验证（真实教训：某次后端 20/20 全通，界面却全白）。
用 `scripts/o2_drive_ui_verify.sh` 作为模板，关键姿势：

### 4.0 ★ 先确认 agent-browser 可用；不可用时改用 playwright-core 直驱

**故障判据**：`agent-browser open about:blank` 超过 60s 无任何输出（连轻量页面也卡死）。

2026-09-23 实测该故障：清 `~/.agent-browser/default.{pid,port,engine,stream,version}`
状态文件、`agent-browser install` 重装 Chrome（成功装好 154）**均无效**；
Node 前置检查（`node -e "console.log('ok')"`）三项全过 ⇒ 不是 Node 问题。

**替代方案**：agent-browser 自带 `playwright-core`，直接驱动已装 Chrome，绕开 daemon：

```js
const PW = '<...>/node_modules/playwright-core';        // tools/o2_syssetting_ui_verify.js 有自动探测
const CHROME = '<USERPROFILE>/.agent-browser/browsers/chrome-*/chrome.exe';
const { chromium } = require(PW);
const b = await chromium.launch({ executablePath: CHROME, headless: true,
                                  args: ['--no-sandbox', '--disable-gpu'] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
```

**落地脚本**：`tools/o2_syssetting_ui_verify.js`（playwright-core / Chrome 自动探测）
+ `tools/o2_syssetting_ui_verify.sh` 包装。**下面 1–9 条的姿势在 playwright 下同样适用**
（轮询登录、轮询菜单项数）。

**★ 断言入口要走"真实用户路径"**（2026-09-23 修正）：只查 `.layout_start_item_text`
（☰ 网格，源自 `CPT_COMPONENT`）会给出**假 PASS** —— 用户看的却是门户应用菜单（源自字典）。
正确流程：`goto portal.html?id=<portalId>` → 找到 `textContent === '系统管理'` 的叶子节点 →
对 `closest('li')||parentNode` 依次派发 `mouseenter/mouseover/click` → 读 `.subsource`
里的可见文本断言新条目在列并含全部同级条目 → 再点它并断言 `.ss-wrap` 出现。

**★ 两个 playwright 专属的坑**：

| 坑 | 症状 | 正解 |
|---|---|---|
| O2OA 登录页是 Vue，`page.fill` 只改 DOM 的 `value`，**不触发 v-model 绑定** | 填完用户名，截图里仍是 placeholder「用户名」；点「登录」**连 POST 都不发**，页面毫无反应 | 用**真实键盘输入**：`click(input)` → `keyboard.type(text,{delay:40})`，并回读 `input.value` 做断言 |
| `admin`/`xadmin` 是「初始管理员」（**不在 `ORG_PERSON`**） | UI 登录被前端 **"密码已过期"** 策略拦截，前端随即 `DELETE /authentication`；但 REST 登录与桌面会话都正常 | **REST 取 `x-token` → `ctx.addCookies([{name:'x-token',value:tk,url:BASE,httpOnly:true}])`**，再打开桌面即恢复会话（实测 `layout.session.user.name = 系统管理员`） |
| `page.evaluate(fn, a, b)` 传了两个实参 | 整条脚本崩在 `Too many arguments. If you need to pass more than 1 argument…`，断言前就挂 | playwright 的 `evaluate` **只接受一个参数**：把多个值打包成对象，`page.evaluate(a => {...a.g...}, {g:G, i:I})` |
| `portal.html` 打开门户 → 点击 `actionType=app` 的条目 | 可能**同页**渲染，也可能开**新窗口**，只盯当前 page 会误判"点了没反应" | 点击前 `ctx.waitForEvent('page',{timeout:15000}).catch(()=>null)`，拿到 popup 就切过去再断言 |

⇒ `captchaLogin=true`（登录页有图形验证码）时，**用令牌注入完全绕开登录页**，最省事。

1. **浏览器会话不跨命令存活** → 整条流程（open→fill→click→eval→screenshot）
   必须写在**一次 Bash 调用 / 一个脚本**里；拆成多条命令会拿到 SIGTERM。
2. **★ 开头先 `agent-browser close` 再 `open`**。被 SIGTERM 杀掉的上一次运行会留下
   **脏守护进程**，之后每次 `eval` 都返回 `{}`，整轮验证全线误判（本项目踩过两次）。
3. **★ 轮询登录结果，不要固定 `sleep`**：登录耗时随机器负载波动。用
   `layout.session.user.name` 做哨兵，4s 一次最多 8 次。
   **未登录就继续往下跑，后面所有断言全是假的**（会白跑 5 分钟）。
4. `screenshot` 的第 1 个位置参数是**选择器**，不是路径 →
   要指定输出文件必须写 `agent-browser screenshot body out.png`。
5. **优先用稳定 CSS 选择器，不要用 `snapshot` 的 `@eN`**（序号随页面结构变化失效）：
   - 登录：`input[name=credential]` / `input[name=password]`，按钮用
     `querySelectorAll('button,a,div,span')` 找 `textContent === '登录'` 再 `.click()`
   - 桌面开始菜单按钮：**`.layout_menu_start_button`**（不必先点「办公中心」）
   - 菜单项：`.layout_start_item_text`（本项目实测 72 项）
6. `eval` 返回的是**被 JSON 转义过的字符串**（形如 `"{\"a\":true}"`），
   shell 里断言前先 `tr -d '\\'`。
7. **★ 别"一个 eval 一步"**：进程往返回抖动会让某几步莫名返回 `{}`。
   稳妥做法 = **一次 `eval` 注入整段异步流程**（IIFE 里 `async/await` + 自己 `sleep`），
   结果写 `window.__rtN = {done:true, out:...}`，bash 只做**轮询**。
   写这段 JS 时**避免 `$` 和反引号**，才能安全地用双引号传给 CLI。
8. 在页面里构造上传测试文件用 `DataTransfer`：
   `dt.items.add(new File([bytes], 'x.png', {type:'image/png'})); input.files = dt.files;
   input.dispatchEvent(new Event('change', {bubbles:true}))`。
   **★ 注意服务端还有后缀白名单**（见下），用 `.bin`/`.txt` 做"正面对照"会被白名单拒，
   误判成上传功能坏了。
9. 点击"开始菜单"里的应用项要等它渲染：菜单项是懒渲染的。
   JS 派发用 `el.closest('.layout_start_item').dispatchEvent(new MouseEvent('click',{bubbles:true,view:window}))`。
   **★ 且必须轮询**：面板异步渲染，固定 `sleep 7` 后只查一次会偶发拿到 `n=0`。
   补点开始按钮前**先查当前菜单项数**——面板会 toggle，0 项时才点，否则越点越没有：
   ```bash
   for att in 1 2 3 4 5 6; do
     N="$(ev "document.querySelectorAll('.layout_start_item_text').length")"
     [ "$N" = "0" ] && ev "document.querySelector('.layout_menu_start_button').click()"
     sleep 5
     CLICKED="$(ev "...找 '企业网盘' 并派发 click...")"
     case "$CLICKED" in *clicked*) break ;; esac
   done
   ```
10. **★ 给 `agent-browser eval` 的片段一定要自校验结尾的 `})()`**。
    写成 `(function(){...})`（少一对调用括号）时，CLI **不报错**、静默返回一个对象，
    等价于整步 no-op。本项目实际踩过：`登录用户：系统管理员`（登录 OK）
    + `NOT-FOUND(n=0)` + `.drive-root 未渲染` + `viewer:"undefined"`，
    看起来像"组件挂了 / 入口没登记"，真凶只是脚本少了个 `()`。
    **判据：登录成功但所有 DOM 断言全 0/false ⇒ 先怀疑脚本本身，再怀疑产品。**
12. **★ 回归脚本里的"正面对照"必须落在服务端白名单内**。本项目用 `.txt` 当正面对照，
    而 `fileTypeIncludes` 放行的是 `text` 不是 `txt` ⇒ 被 500 拒，
    表现为「上传功能坏了」，白白排查一轮。选对照文件前先查白名单：
    ```bash
    curl -s --noproxy '*' -X GET "http://localhost:9090/x_file_assemble_control/jaxrs/config/system/config" \
      -H "x-token:$TK" | grep -o 'fileTypeIncludes.*'
    ```
13. **★ 「批量操作里单个失败」要单独验证**。批量上传中一个文件被拒，若失败分支直接
    `return`（不调 `next()`），会表现为「后续文件根本没传 + 列表不刷新 + 只有一条 toast」，
    很像"功能整体失效"。断言里要区分**部分成功**与**全部失败**，别只判 true/false。

### 4.2 ★ 组织接口的两个高频陷阱（做"按人统计"类功能必踩）

| 陷阱 | 表现 | 正确做法 |
|---|---|---|
| **人员 dN ≠ 身份 dN**（字段名都叫 `distinguishedName`） | 逐人数据全为空 / "是否我本人"判断恒 false | `authentication.data.distinguishedName` = `x@u@P` → **人员 dN**（= `attachment.person`）；`data.identityList[0].distinguishedName` = `x@unit_u@I` → 身份 dN，**不能**当作 person 使用 |
| **分页/列表查询多为 POST / PUT** | `GET person/list/filter/{page}/{size}` → **404** | 看 `describe/sources/**/XxxAction.java` 上的 `@POST`/`@PUT`：`listFilterPaging` 是 POST，`role|person/list/like` 是 PUT |

按人查容量的官方姿态（服务端只在管理员时认 `person` 参数，非管理员强制回落查自己，无越权）：
```bash
GET {SVC}/attachment2/user/capacity?person=<人员dN>
# 口径 sum(length) where person=? and status=VALID（不含回收站）
```

人员枚举（本部署取不到 `person/list/filter`）：
```bash
GET {ORG}/unit/list/control/top                       # 我管辖的顶层单位（权限范围锚点）
GET {ORG}/unit/list/{dn}/sub/nested                   # 展开下级
GET {ORG}/identity/list/unit/{dn}                     # 身份：personUuid + 姓名 + unitName
GET {ORG}/person/list/{meDn}/prev|next/{count}        # 名册：dN + 状态 + 最近登录
# 两条路用 person 的 UUID 关联；逐人查询并发限 6
```
11. **部署脚本的文件清单必须覆盖组件全部文件**：本项目的坑是配对 `*.min.js` 段只处理了
    `Main.js` / `lp/*.js`，同步清单里也漏了 `drive/drive.min.js` ⇒ 容器里那份
    **停在旧版本**（51756B vs 106116B）。虽然主类用显式路径 `drive.js?v=VERSION` 加载
    掩盖了症状，但一旦改走 bundle 就会静默回退旧代码。
    **校验 HTTP 200 不够，要比对字节数**：
    ```bash
    for f in Main.js Main.min.js drive/drive.js drive/drive.min.js lp/zh-cn.js lp/zh-cn.min.js; do
      echo "$(curl -s --noproxy '*' "$BASE/x_component_Drive/$f" | wc -c)  $f"
    done   # 成对的两个文件名应同字节数
    ```

### 4.1 附：两个容易误判的「服务端硬闸门」

| 闸门 | 表现 | 真相 |
|---|---|---|
| **上传后缀白名单** | 某个扩展名上传 500「文件类型不符合上传要求」 | `FILE_CONFIG.properties.fileTypeIncludes` 在**上传时**强制校验；默认是 `doc docx xls xlsx ppt pptx pdf xapp **text** zip rar mp3 mp4 png jpg gif`。**是 `text` 不是 `txt`** → `.text` 能传、`.txt` 不能 |
| **目录端点配对** | 删除/重命名文件夹报「指定的目录不存在」 | 新目录用 `folder2` 建（`FILE_FOLDER2`），就必须用 `DELETE/PUT /jaxrs/folder2/{id}`；`/folder/{id}` 走**旧表** `FILE_FOLDER`，恒找不到 |

排查手法：
```bash
# 谁抛的异常、打的哪个 URL
docker logs o2oa-server --since 3h | grep -i "指定的目录\|FolderNotExist\|文件类型不符合"
```

**自定义配置要持久化**（组件需要服务端共享的设置项）时，用门户数据字典，注意读写通道不对称：

```bash
# 读（任意登录用户）
GET  /x_portal_assemble_surface/jaxrs/dict/<alias>/portal/index/data
# 写（designer，需门户管理权限）；surface 的 PUT 在部分部署被 HTTP 层拦成 405
PUT  /x_portal_assemble_designer/jaxrs/dict/<dictId>      # 整对象覆盖，含 data
POST /x_portal_assemble_designer/jaxrs/dict               # 建：{application:<portalId>,alias,name,data}
```

## 5. 部署与回滚（本项目约定）

> **★ 关键事实**：O2OA 启动时会执行「move the unofficial directory to webroot directory」——
> 把 `servers/webServer/x_component_Foo` **整体移动到 `/opt/o2server/webroot/x_component_Foo`**。
> 所以**运行中真正被 HTTP 服务的是 `webroot/` 下的那份**：
> - 想**立刻生效** → `docker cp` 到 `/opt/o2server/webroot/x_component_Foo/...`（静态文件即时生效，**无需重启**）
> - cp 到 `servers/webServer/...` 会报 `Could not find the file`（目录已被移走）
> - `webroot` 通常是 compose 命名卷（本项目 `o2oa-webroot`），**持久化，容器重建不丢**
> - 镜像 `Dockerfile` 里仍要 `COPY` 到 `servers/webServer/`，那是**新装/重建时的播种位**

```bash
# 更新运行中的组件（即时生效）
for f in Main.js Main.min.js drive/drive.js drive/drive.css lp/zh-cn.js lp/zh-cn.min.js; do
  docker cp patch/web/x_component_Foo/$f o2oa-server:/opt/o2server/webroot/x_component_Foo/$f
done
curl -s --noproxy "*" http://localhost:9090/x_component_Foo/Main.js | head -3   # 校验已换版

python tools/o2_drive_entry.py apply     # 若入口也要改（改的是数据层，需 restart）
docker restart o2oa-server               # 仅入口/数据层改动需要
bash o2oa_netlock.sh                     # 本项目：重启后按规程恢复断网隔离
```

同时把组件加进 `Dockerfile` 的 `COPY`，否则**重建即丢**：

```dockerfile
COPY patch/web/x_component_Foo ${O2OA_HOME}/servers/webServer/x_component_Foo
```

> Dockerfile 里路径含 `$Layout` 时必须转义成 `\$Layout`，否则 Docker 当变量展开为空，
> 文件会落到错位路径（本项目已踩过，深链文件因此丢失）。

### 5.1 ★★ `x_desktop` 顶层定制文件：必须 Dockerfile 烤入，bind mount 无效

`servers/webServer/x_desktop/`（含 `index.html`、`index_home.html`、`res/config/config.json`）
与 `x_component_*` 不同——它**不会被移动到 webroot**，O2OA 直接读镜像层；
而且 **compose 的 bind mount 单文件覆盖层对 O2OA 无效**（2026-09-25 实测铁证）：

- 曾把宿主 `index.html` bind 进 `.../webServer/x_desktop/index.html`，重建容器后线上 `curl`
  仍返回**官方版**（注入 `ALIGN_TEST_xxx` 标记零生效、9 分钟轮询无定制签名）；
  而 `docker cp` 出来的容器内文件确为定制版 ⇒ O2OA **不读裸挂载覆盖层**。
- 根因：O2OA 资源解析（尤其 `x_desktop` 这类顶层入口）读的是**镜像层文件**，
  bind mount 虽改了容器文件系统视图，但不在 O2OA 的查找顺序里。

**正确做法（本项目已固化进 Dockerfile + commit `eb8b45b`）**：
1. **git 真源** = `deploy/host/x_desktop/`（`o2server/servers/webServer/x_desktop/` 被
   `.gitignore:13` 排除，不能直接当真源）。
2. **Dockerfile `COPY` 烤入镜像**（构建期播种位，与 `x_component_AI`/`Drive` 同机制）：
   ```dockerfile
   COPY deploy/host/x_desktop/index.html ${O2OA_HOME}/servers/webServer/x_desktop/index.html
   COPY deploy/host/x_desktop/index_home.html ${O2OA_HOME}/servers/webServer/x_desktop/index_home.html
   COPY deploy/host/x_desktop/res/config/config.json ${O2OA_HOME}/servers/webServer/x_desktop/res/config/config.json
   ```
3. **compose 里不要再写这三条 bind mount**（写过又撤销，见 `eb8b45b`）。
4. 改动后**必须重建镜像 + 重建容器**（`docker cp` 进可写层只活到下次重建）。
5. 重建后**重跑 `bash o2oa_netlock.sh`** 恢复断网隔离。

**对齐判定（三分流线上校验）**：
```bash
curl -s --noproxy "*" http://localhost:9090/x_desktop/index.html | grep -c "_isManager\|index_home\|_isHomeEntry"  # >0
curl -s --noproxy "*" -o /dev/null -w "%{http_code}\n" http://localhost:9090/x_desktop/index_home.html            # 200
curl -s --noproxy "*" http://localhost:9090/x_desktop/res/config/config.json | grep -o "中国复合材料工业协会内部管理系统"  # 标题命中
```

**改完前端要用户刷新**：若用户浏览器仍开着**组件修复前**的窗口，点标签只 `setCurrent()` 不复载，
会一直看到旧界面 —— 让用户 F5 或关闭标签重开（这不是代码缺陷）。

## 6. 交付自检清单

- [ ] `Main.js` / `Main.min.js` 成对存在，且**线上都 200 且字节数一致**
- [ ] `lp/zh-cn.js` / `.min.js` 成对存在
- [ ] 入口 1（`CPT_COMPONENT.xpath`）、入口 2（`GEN_DICT_ITEM.app`）都已改指
- [ ] `docker restart o2oa-server` 已执行
- [ ] **真实浏览器走真实路径**点开，`.drive-root`（或你的根节点）已渲染、控制台零报错
- [ ] 截图存档作为证据
- [ ] Dockerfile 已 COPY（重建不丢）
- [ ] 回滚工具可用（rollback 后老组件应恢复原样）
