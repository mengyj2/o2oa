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
├─ 能渲染但点击无反应 / 控制台报 this.xxx is not a function  → A 类（§2，数据层，最高危）
├─ 整页白屏 / 404 / 脚本语法错 / 登录后跳错页面               → B 类（§3，文件层）
├─ 换了 logo/图标后功能或显示异常                              → C 类（§4）
└─ 显示正常，只是文案/标题/字号还是旧品牌                      → D 类（§5）
```

> ★ **A 类与 B 类症状相似但根因完全不同**，选错方向会白排查几小时。
> 一句话判定：**「能看不能点」= A 类（数据的交互字段没了）；「连看都看不到」= B 类（文件坏了）**。
> 用户说"index 完全破坏了、没有链接"时，**先确认是哪一类**再动手。

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

### 3.2 ★★ 生效纪律：真源在 git，镜像靠 COPY（这是最容易白干的地方）

- **git 真源 = `deploy/host/x_desktop/` 三份**（`index.html` / `index_home.html` / `admin.html`）。
- `Dockerfile` 用 `COPY` 把它们烤进镜像：
  ```
  COPY deploy/host/x_desktop/index.html      ${O2OA_HOME}/servers/webServer/x_desktop/index.html
  COPY deploy/host/x_desktop/index_home.html ${O2OA_HOME}/servers/webServer/x_desktop/index_home.html
  COPY deploy/host/x_desktop/admin.html      ${O2OA_HOME}/servers/webServer/x_desktop/admin.html
  ```
- ★ **bind mount 单文件覆盖对 O2OA 无效**：实测挂载了覆盖层、线上仍返回官方版 index.html。
  所以**必须 COPY 烤镜像**。
- **正确改法**：
  ```bash
  # ① 只改 git 真源三份，不要在容器里改
  # ② 重建镜像（这一步才能让定制进 webServer）
  docker compose build o2oa && docker compose up -d
  ```
  **应急**（不推荐，重建即丢）：`docker cp` 进容器 `/opt/o2server/servers/webServer/x_desktop/` + `docker restart o2oa-server`。

### 3.3 ★ 坑：`res/config/config.json` **不可**静态 COPY

- 该文件由服务端 `WebServers.updateWebServerConfigJson()` 在 **web 服务每次启动时**
  按「系统配置（`collect.json` 的 title/footer）」**动态生成**；前端 `bundle.js` 读它设置 `document.title`。
- **静态 COPY 会劫持这条链路** → 系统配置与登录页标题/页脚不一致
  （2026-09-26 实证后**已从 Dockerfile 移除**）。留在 `deploy/host/x_desktop/res/config/` 仅作参考快照。
- 要改标题/页脚 → 改**系统配置**，不是改这个文件。

### 3.4 诊断与恢复

**先证明"线上到底返回了哪份文件"**：
```bash
# 容器内文件 vs git 真源 逐份比对
docker exec o2oa-server md5sum /opt/o2server/servers/webServer/x_desktop/{index,index_home,admin}.html
md5sum deploy/host/x_desktop/{index,index_home,admin}.html
# 再看 HTTP 实际返回（别只看文件）
curl -s http://localhost:9090/x_desktop/index.html | grep -n "<title>\|_HOME_ENTRY_USERS\|location.replace"
```
**恢复**：把真源三份 `git checkout -- deploy/host/x_desktop/`（或从备份取）→ `docker compose build o2oa && up -d`
→ 再用上面的 md5/curl 双验。
> 若是"整页白屏/语法错"，也可用浏览器控制台报错行号定位是哪份文件被改坏；
> 若"渲染正常但点不动"，**立刻回到 §2 A 类**，别在文件上耗。

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
- ✗ 在容器里改 `x_desktop/*.html` 当成持久修复（bind mount 无效、重建即丢；真源是 git）。
- ✗ 把 `res/config/config.json` 静态 COPY 进镜像（劫持动态生成链路）。
- ✗ 用 `GROUP_CONCAT` 拼扫描 SQL、用 md5 比"无差异"。
- ✗ 改完不重启就下结论。
- ✗ 未获用户确认就动关联字段（`xshortUrlCode` 等）。
- ✗ 把软件产品自身品牌（O2OA/翱途发行包文案）当残留清掉。

## 8. 证据出处

`D:\O2OA\ai-stack-hardening\docs\knowledge-base.md` 第 13~19 章（含源码行号、SQL、实测数据）；
`docs\knowledge_base\portal_brand_guard.md`（同一总纲的 KB 版，已入 RAG 库）。
工具：`tools/scan_brand_words.py`、`tools/rename_gongwen_brand.py`、`tools/fix_wenzhong_orgname.py`。
文件真源：`deploy/host/x_desktop/`（三份）+ `Dockerfile` 第 150~162 行。
