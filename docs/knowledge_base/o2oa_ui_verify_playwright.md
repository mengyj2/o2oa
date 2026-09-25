# 真机 UI 验证的正确姿势（O2OA 桌面 + Playwright）

> 铁律：**数据层验证通过 ≠ 界面能用**。本项目多次出现"接口 20/20 通过，界面一片空白"。
> 凡是交付前端产物，必须真机点开验证。

## 1. 工具链：`agent-browser` 卡死时怎么办

**现象**：`agent-browser open about:blank` 三分钟无任何输出（daemon 卡死）。
**试过但无效**：清 `~/.agent-browser/default.*`、`agent-browser install`（重装 Chrome）—— Node 三项前置检查全过，仍然卡。

**替代方案：用 agent-browser 自带的 `playwright-core` 直驱 Chrome。**

```js
// NODE_PATH=.../node_modules node script.js
const { chromium } = require('playwright-core');
```

自动探测浏览器可执行文件路径 + PW 模块路径，脚本里做回落，避免依赖固定路径。

## 2. 绕过登录页：用 REST 取 token 注入 Cookie

**问题一**：O2OA 登录页是 **Vue**，`page.fill()` 只改 DOM 的 `value`，**不触发 `v-model`** ⇒
点「登录」**连 POST 都不发**。
**做法**：`click(input)` + `keyboard.type(text, {delay: 40})`（真实键盘事件）。

**问题二**：`admin` / `xadmin` 是「初始管理员」（**不在 `ORG_PERSON`**），
UI 登录被前端 **"密码已过期"** 策略拦截，前端随即 `DELETE /authentication`。
**但 REST 登录与桌面会话完全正常**。

⇒ 干脆绕过登录页：

```js
// 1) REST 登录，从【响应头】取 x-token
POST /x_organization_assemble_authentication/jaxrs/authentication
     {"credential":"admin","password":"..."}
// 2) 注入 Cookie
ctx.addCookies([{ name: 'x-token', value: tk, url: BASE, httpOnly: true }]);
// 3) 直接打开桌面 —— 会话已恢复
```

## 3. 自研桌面组件的两个致命坑

### 3.1 ★ Viewer 必须用「普通构造函数 + prototype」

**不能**用 MooTools 的 `new Class({Implements:[Options], options:{...}, initialize(){ this.setOptions(options) }})`。

**根因**：`setOptions` 会**深合并** `opt.app`，而 `app` 是 Main 实例，**带 DOM 循环引用**
⇒ `Maximum call stack size exceeded`。
且**控制台零报错**（被 Main 的 try/catch 吞掉），窗口只剩一行红字。

**正确写法**：

```js
function Viewer(opt) {
    this.container = opt.container;   // 注意不是 this.host
    this.app = opt.app;
    this.build(); this.refresh();
}
Viewer.prototype = { /* 全部方法 */ };
MWF.xApplication.Xxx.Viewer = Viewer;   // 手动挂命名空间
```

### 3.2 ★★ 必须成对提供 `*.min.js`

非调试会话下 `_requireJs` 会把 `.js` 改写成 `.min.js`。
**只放 `.js` ⇒ 404 ⇒ 命名空间未注册 ⇒ 窗口全白**。同名复制一份即可（不必真压缩）。

## 4. 脚本本身的坑

| 坑 | 表现 | 正确做法 |
|---|---|---|
| `page.evaluate` 只接受**一个**参数 | 传两个参数时静默不执行 | 包成一个对象 `evaluate(a => ..., {g, it})` |
| 会话不跨命令存活 | 上一条命令登录、下一条就掉线 | 每条命令开头重新 `close` 再 `open` |
| 面板是 toggle | 点两次反而关掉 | **轮询**目标项数量，0 项才点按钮 |
| `eval` 片段结尾少括号 | **静默 no-op**，无任何报错 | 片段结尾必须是 `})()`，一次注入整段异步流程 |
| 片段里的 `$` 与反引号 | 被外层 shell 吃掉 | 片段内避免使用，或换写法 |

## 5. 验证脚本应该断言什么

**不是**"页面能打开"，而是**真实用户路径 + 可证伪的证据**：

```
1. 展开目标菜单分组
2. 断言目标条目【在列】                      ← 只此一条就能防住"假 PASS"
3. 点击该条目
4. 断言组件的容器节点存在（如 document.querySelector('.ss-wrap')）
5. 断言 viewer 是 function、导航项数量正确
6. 断言无 JS 报错（收集 page.on('pageerror')）
7. 截图留证（菜单一张 + 组件一张）
```

本项目第一版脚本只查了"开始菜单网格里有这个名字"，于是**给出了假 PASS**，被用户一眼看穿。
**教训：验证必须覆盖用户实际会走的那个入口。**

## 6. 收尾：用户侧"仍空白"的最后一招

组件、入口、静态资源全部核对无误，界面还是白 —— 大概率是
**用户会话里持着修复前的死窗口**。
⇒ 让用户 **F5 / Ctrl+F5** 或关掉标签重开即可。
