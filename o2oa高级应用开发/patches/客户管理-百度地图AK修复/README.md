# 客户管理（CRM）百度地图 AK 失效弹窗 — 修复交付

> 修复日期：2026-09-21
> 适用环境：O2OA 社区版 10.0.2（本地 Docker 自托管，已断云）
> 交付物：8 个已修补 JS + 幂等补丁脚本 + 原始文件（回滚用）

---

## 一、用户可见现象

打开 O2OA 桌面 → 客户管理（CRM）应用，弹出**原生浏览器 alert**：

```
APP被您禁用啦。详情查看：http://lbsyun.baidu.com/apiconsole/key#。
```

- 后台 URL：`http://10.0.0.149:9090/x_desktop/app.html?app=CRM&status={}`
- 页面标题：`CRM`
- 弹窗阻塞页面交互（原生 alert 是模态的），**但 CRM 主体渲染正常**

---

## 二、根因（已实证，非推测）

### 2.1 完整因果链

```
① CRM 组件硬编码百度地图 jsapi v2.0 的旧 AK（2016 年申请）
       Qac4WmBvHXiC87z3HjtRrbotCE3sC9Zg
   出现位置：Main.js / BaiduMap.js / AddressExplorer.js（及各自 min 版）
   ★ Main.js / Main.min.js 的触发点是「进入应用即 loadDom(apiPath)」

② 该 AK 已被用户自己删除。百度 verify 接口实测返回：
       curl "http://api.map.baidu.com/?qt=verify&v=2.1&ak=Qac4WmBvHXiC87z3HjtRrbotCE3sC9Zg"
       → {"error":201,"error_msg":"APP被用户自己删除；详情信息请前往：...","popup":0}

③ 百度前端 SDK 内置错误码表（从 getscript 返回的 JS 中解出）：
       ta = { 201:"APP被您禁用啦。", 202:"APP被管理员删除啦。", 220:"APP Referer校验失败。", 240:"APP服务被禁用了。", ... }

④ 命中 201 → 走 SDK 内 B.Tw 分支 → alert(ta[201]) → 阻塞式原生弹窗
```

### 2.2 为什么必须连「脚本加载」和「BDMarkerTool」一起切

只把 AK 置空是**不够**的，会引入两个新错误：

| 半吊子改法 | 后果 |
|---|---|
| 只把 URL 置为空字符串 `""` | `window.BDMapApiLoaded \|\| loadDom("")` **仍然执行** → 请求空 URL 拿回 HTML → `SyntaxError: Unexpected token '<'` |
| 承接上一条的回调 | 回调里继续 `load("/x_component_CRM/BDMarkerTool.js")` → 该文件末尾是自执行块且依赖 `window.BMap` → `ReferenceError: BMap is not defined` |

**结论：必须让整个「是否加载百度脚本」的分支恒为假（短路），而不是只清空 URL。**

### 2.3 弹窗是「附着副作用」

CRM 的业务主体（客户管理 / 我的工作台 / 信息 / 线索 / 客户 / 公海 / 联系人 / 销售简报）**全程正常渲染**。
其中「客户分布」用的是 echarts + china.js（自带中国地图），**与百度地图无关**，不受影响。

---

## 三、修复策略

**不引入新 AK、不依赖外网、不删功能，只做优雅降级。**

| 文件 | 改法 |
|---|---|
| `Main.js` | ① `apiPath` 置空；② `if( !window.BDMapApiLoaded ){` → `if( false && !window.BDMapApiLoaded ){` |
| `Main.min.js` / `Main.min.min.js` | 整段「进入应用即拉百度脚本」短路：URL 置空 + 三元条件改成 `0&&…` |
| `BaiduMap.js` | ① `apiPath` 置空；② 守卫短路；③ `new BMap.Map()` 前加 BMap 守卫（渲染占位提示） |
| `AddressExplorer.js` | ① `apiPath` 置空；② 守卫短路；③ `createMap()` 入口整体加 BMap 守卫 |
| `*.min.js`（4 个） | 三元表达式里 `loadDom(...)` 整支替换为 `:(this._loadMap(),t&&t())` |

### 3.1 恢复地图功能的方法

取得有效百度地图 AK 后：

1. 打开 `BaiduMap.js` / `AddressExplorer.js`，把 `var apiPath = "";` 改成
   `var apiPath = "http://api.map.baidu.com/getscript?v=2.0&ak=<你的新AK>&services=&t=20161219171637";`
2. 把紧随其后的 `if (false /* O2OA-NOMAP-PATCH ... */ && !window.BDMapApiLoaded) {`
   里的 `false` 去掉。
3. `Main.js` 同理（`apiPath` + `if(false …)`）。
4. min 版建议直接由对应的非 min 版重新压缩，或按同样思路手改。

> min 文件的补丁**只做了 URL 置空 + 分支短路**，没有插入多行注释 ——
> 压缩文件内插 `/* */` 块注释会与相邻注释嵌套冲突，标记只放文件头单行。

---

## 四、验证结果

### 4.1 静态校验

```
$ node --check <每个文件>
OK    Main.js / Main.min.js / Main.min.min.js
OK    BaiduMap.js / BaiduMap.min.js / BaiduMap.min.min.js
OK    AddressExplorer.js / AddressExplorer.min.js          ← 8/8 全绿

$ python fix_crm_bmap.py work      # 幂等性复跑
Main.js nochange ... AddressExplorer.min.js nochange       ← 8/8 幂等
```

### 4.2 运行时端到端（Playwright / msedge 真浏览器）

打开 `/x_desktop/app.html?app=CRM&status={}`，并主动点击
`客户分布 / 信息 / 线索 / 客户 / 公海 / 联系人 / 销售简报` 各页签：

```
token: NvcRQdBFbiiN...
--- CRM 加载的组件 JS ---
   /x_component_CRM/Main.min.js
   /x_component_CRM/BaiduMap.min.js
--- body: 客户管理 孟弋洁 快速新建 我的工作台 首页 信息 线索 客户 公海 联系人 ...

=== DIALOGS: 0 []
=== PAGEERRORS: 0
=== BDMarkerTool 请求: 0 (期望 0)
=== 百度地图外网请求: 0 (期望 0)

########## ALL PASS ##########
```

**四项断言全部通过。** 截图见 `验证截图.png`（界面完整，无任何弹窗）。

### 4.3 全目录残留扫描

```
$ grep -rl "Qac4WmBvHXiC87z3HjtRrbotCE3sC9Zg" /opt/o2server/webroot/x_component_CRM
./AddressExplorer.js   → 第 170 行，// 注释
./BaiduMap.js          → 第 145 行，// 注释
./Main.js              → 第 81 行，/* 补丁说明注释 */
```

仅 3 处，**全部位于注释内**，不会被执行 → **运行时零外网请求，闭环完整**。

---

## 五、文件清单

```
客户管理-百度地图AK修复/
├── README.md                      本文件
├── fix_crm_bmap.py                幂等补丁脚本（用法：python fix_crm_bmap.py <含JS的目录>）
├── 已修补-可直接部署/              8 个文件，可直接 docker cp 进容器
│   ├── Main.js            Main.min.js          Main.min.min.js
│   ├── BaiduMap.js        BaiduMap.min.js      BaiduMap.min.min.js
│   └── AddressExplorer.js AddressExplorer.min.js
└── 原始文件-回滚用/                同上 8 个文件的原始未修改版
```

### 部署命令

```bash
# 容器名以实际为准
for f in 已修补-可直接部署/*.js; do
  docker cp "$f" o2oa-server:/opt/o2server/webroot/x_component_CRM/"$(basename $f)"
done
# 浏览器强刷（Ctrl+F5）即可生效，无需重启 O2OA
```

### 回滚命令

```bash
for f in 原始文件-回滚用/*.js; do
  docker cp "$f" o2oa-server:/opt/o2server/webroot/x_component_CRM/"$(basename $f)"
done
```

---

## 六、注意事项

1. **浏览器缓存**：改完务必 `Ctrl+F5` 硬刷新。组件 JS 带 `?v=10.0.2-<hash>` 查询串，
   若 hash 未变可能命中缓存 —— 可在开发者工具 Network 面板确认实际字节数。
2. **重装应用会覆盖**：若从 `客户管理.zip` 重新导入该应用，补丁会被原始文件覆盖，
   需重跑 `fix_crm_bmap.py` 或改用（已固化的）zip。
3. **同类风险范围**：已扫描 `E:\OA系统上线方案` 下 19 个应用包，
   **仅「客户管理.zip」引用百度地图**，无需批量修复。
4. **仅地图功能降级**：地图区域会显示一行灰色提示文字，
   客户 / 联系人 / 线索 / 公海 / 销售简报等**全部业务功能不受影响**。
