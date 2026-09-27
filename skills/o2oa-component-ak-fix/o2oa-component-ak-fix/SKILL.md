---
name: o2oa-component-ak-fix
description: 修复 O2OA 桌面组件（应用）里**硬编码第三方服务密钥（AK/SK/Token）过期**导致的前端阻塞弹窗（如百度地图「APP被您禁用啦。」），或同类"打开应用就弹窗/白屏但服务端零报错"的问题。当用户问"打开 XX 应用弹窗""应用里弹 APP被禁用""百度地图 AK 失效""硬编码 AK 过期怎么改""min.js 怎么打补丁不坏""改了 JS 没生效""应用重装后问题又来了"时调用。覆盖：全目录 grep 定位、双份 min 文件、优雅降级补丁、幂等补丁器、zip 固化、Playwright E2E 断言。
agent_created: true
category: diagnostics

---

# O2OA 组件第三方 AK 失效 — 排查与修复

## 一、识别症状

典型话术：**打开某个应用（不是门户）立刻弹出原生 alert**，文案类似：

- 百度地图：`APP被您禁用啦。详情查看：http://lbsyun.baidu.com/apiconsole/key#。`
- 高德：`INVALID_USER_SCODE` / `USERKEY_PLAT_NOMATCH`
- 其它 SDK：各种 `error code` 中文提示

特征：
1. 弹窗是**原生 `alert()`**（模态，阻塞）。Playwright 里表现为 `page.on("dialog")`。
2. **服务端零报错**，O2OA 日志干净。
3. **应用主体功能全正常**，只是某个模块（地图/定位/OCR/支付）不可用。
4. URL 形如 `/x_desktop/app.html?app=XXX&status={}`，title 是应用名。

## 二、根因模型（几乎总是一样的）

```
应用组件内硬编码第三方服务密钥（常见于 2016 年前后申请的 AK）
  → 该密钥已过期/被删除/被禁用
  → 第三方 SDK 前端拿到错误码，命中内置错误提示表
  → alert(错误文案)  ← 阻塞
```

**关键认知：弹窗是「附着副作用」，不是应用坏了。** 别去查数据库、别去查流程。

## 三、五步排查法

### ① 全目录 grep 定位命中文件

```bash
docker cp o2oa-server:/opt/o2server/webroot/x_component_XXX ./crm_live
cd crm_live
grep -rl "<疑似 AK 字面量>" .
grep -rl "api\.map\.baidu\.com" .        # 按服务域名找更准
```

> ★ **别只 grep 顶层 `*.js`**。打包器会产出 `X.js` / `X.min.js` / `X.min.min.js`
> **三份**，功能模块也可能是独立文件（如 `AddressExplorer.js` 而非只在 `BaiduMap.js` 里）。
> 只查主文件必漏 → 修完弹窗还在。

### ② 判定是哪个文件触发（★ 最容易错的一步）

浏览器加载的是 **min 版**。所以：

- 改 `Main.js` 而没改 `Main.min.js` → **完全无效**。
- 触发点常在 **Main（进入应用即加载脚本）**，而不是功能模块文件。

**验证哪个文件真正被加载**：Playwright 里监听 `request` 事件，看实际 URL。

### ③ 服务端验证密钥状态（拿到铁证）

```bash
# 百度地图
curl "http://api.map.baidu.com/?qt=verify&v=2.1&ak=<AK>"
# → {"error":201,"error_msg":"APP被用户自己删除","popup":0}   201=被禁用
```

把 AK 换成已验证失效的值去 grep，比猜哪段代码有问题快得多。

### ④ 判断能否"优雅降级"

**优先降级，不要试图换 AK**（协会/内网环境拿不到新 AK，且换 AK 后仍可能触发 Referer 校验）：

- 切断"进入应用即加载第三方脚本"的分支 → 弹窗消失
- 给功能模块加守卫 → 无 SDK 时渲染占位提示而非抛错
- **业务主体功能不受影响**（这是最重要的验收点）

### ⑤ 补丁 + 固化 + 验证

见下方第 4~6 节。

## 四、补丁范式（★ 三个必踩的坑）

### 坑 1：只把 URL 置空**不够**

```js
// 原
window.BDMapApiLoaded || COMMON.AjaxModule.loadDom(t, function(){ ...load("BDMarkerTool.js")... })
// 错误改法：t = ""  → loadDom("") 仍执行 → 请求空 URL 拿回 HTML
//   → SyntaxError: Unexpected token '<'
//   → 回调再加载依赖 SDK 的模块 → ReferenceError: BMap is not defined
```

**必须让整个分支恒假**：

```js
0 && !window.BDMapApiLoaded && COMMON.AjaxModule.loadDom(t, ...)
// 或
if (false /* PATCH */ && !window.BDMapApiLoaded) { ... }
```

### 坑 2：压缩 JS **严禁**插 `/* */` 块注释

与相邻注释嵌套冲突 → `SyntaxError: Invalid regular expression: missing /`。
标记只放**文件头单行**：

```python
MIN_LOG = "/*%s min-patched*/\n" % MARK
```

### 坑 3：同名功能模块可能**结构不同**

例：`BaiduMap.js` 里是 `        this.map = new BMap.Map(this.mapNode);`
（8 空格缩进，可作锚点）；
但 `AddressExplorer.js` 里是多赋值 `var map = this.map = new BMap.Map(this.mapNode);`
且 `createMap()` 一进来就 `new BMap.Point(...)`。

→ **守卫必须插在方法入口**（`createMap: function( position ){` 之后），
不能沿用缩进字符串锚点。**每个文件都要单独读一遍再写补丁。**

### 参考实现

`scripts/fix_crm_bmap.py`（幂等补丁器，8 文件全覆盖）+ `scripts/bake_into_zip.py`（zip 固化）
已随本技能提供，改 `OLD_AK` / `TARGETS` 即可复用到其它应用。

## 五、幂等补丁器写法

```python
MARK = "O2OA-NOMAP-PATCH"

def patch_x(s):
    if MARK in s:          # ★ 幂等：已打过就跳过
        return s, 0
    n = 0
    if OLD in s:
        s = s.replace(OLD, NEW); n += 1
    return s, n

TARGETS = {                # ★ 8 项，不是一个
    "Main.js": "main",   "Main.min.js": "mainmin",  "Main.min.min.js": "mainmin",
    "BMap.js": "bmap",   "BMap.min.js": "min",      "BMap.min.min.js": "min",
    "Addr.js": "bmap",   "Addr.min.js": "min",
}
```

**输入一律用「从原 zip 提取的 pristine 文件」**，不要用容器里已是补丁版的文件
（否则全是 `nochange` 假象）。

## 六、部署与固化

### 部署（无需重启 O2OA）

```bash
for f in work/*.js; do docker cp "$f" o2oa-server:/opt/o2server/webroot/x_component_XXX/"$(basename $f)"; done
# 浏览器 Ctrl+F5 硬刷新
```

> 组件 JS 带 `?v=10.0.2-<hash>`，hash 未变可能命中缓存 → 在 DevTools Network 面板
> 对比实际字节数确认。

### 固化进 zip（防重装覆盖）

用 `zipfile` 就地替换同名条目，**保持其它条目原样 + 保持压缩方式 + 先备份**：

```python
shutil.copy2(ZIP, ZIP + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
# 读全部 → 替换目标 → 按原 infolist 顺序重写（compress_type/external_attr/date_time 原样）
z.testzip()  # 校验完整性
```

## 七、验收断言（Playwright，缺一不可）

```js
page.on("dialog",  d => dialogs.push(d.message()));
page.on("pageerror", e => errs.push(String(e)));
page.on("request", r => {
  if (/BDMarkerTool/.test(r.url())) bdCount++;
  if (/api\.map\.baidu\.com/.test(r.url())) baiduHits.push(r.url());  // ← 常被忽略
});

// 进入应用
await page.goto(BASE + "/x_desktop/app.html?app=XXX&status={}", {...});
// ★ 主动点遍各功能页签，逼出按需加载的模块
for (const t of ["信息","客户","联系人","分布"]) { await page.locator(`text=${t}`).first().click(); }
```

**四项全 0 才算通过**：`DIALOGS=0` / `PAGEERRORS=0` / `功能模块请求=0` / **`外网请求=0`**。

最后 `grep -rn "<AK>" <组件目录>` 确认残留**只在注释里**（`//` 或 `/* */`）——那不影响运行。

## 八、注意事项

1. **同类风险面要扫全**：修复后扫一遍所有应用包（`grep -rl "<域名>" 各包`），
   确认是否只有这一个应用命中，别漏批量修复。
2. **恢复功能**：取得有效 AK 后，把 `var apiPath = "";` 填回 + 去掉 `if(false && …)`
   里的 `false`；min 版建议由非 min 版重新压缩。
3. **告知用户降级范围**：明确说明"哪些功能不可用、哪些完全正常"，
   不要含糊说"修好了"。
