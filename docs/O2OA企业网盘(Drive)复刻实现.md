# O2OA「企业网盘（Drive）」代码级复刻 · 实现说明

> 实测环境：O2OA 社区版 10.0.2 / Docker 自托管 / 断云 / MySQL
> 目标：在**没有官方 pan 后端**的前提下，用自研 UI + 复用内置文件服务，实现与官方应用市场「企业网盘 V2.x」一致的
> 「个人文件 / 企业文件 / 后台管理」信息架构，且**所有列表渲染真实后端数据**。

---

## 1. 结论先行

| 项 | 结论 |
|---|---|
| 官方 pan 模块（`x_pan_assemble_control` + `x_component_Drive`） | **本地发行包中不存在**，且属市场 **VIP 应用**，无法离线取得 |
| 但老的文件服务 `x_file_assemble_control` | **完整存在且可用**，实测 **111 个 REST 接口**、30+ 核心能力全部 200 |
| 因此复刻策略 | **数据层 100% 复用现有服务，UI 层自研**（不是空壳，也不是二级链接） |
| 交付物 | 组件 `x_component_Drive`（自包含，5 个源文件 + 57 个图标资源） |
| 菜单 | 门户应用字典「企业网盘」的 `app` 由 `File` → `Drive` |
| 落盘 | `patch/web/x_component_Drive/` + Dockerfile COPY（重建不丢） |

---

## 2. 为什么不是"装官方包"

1. 官方安装包 `o2server-10.0.2-linux-x64.zip`：`store/` 内 30 个服务 WAR **无 `x_pan_assemble_control.war`**；
   `servers/webServer` 24766 条目 **无 `x_component_Drive`**（`drive` 仅命中 12 张图标 png）。
2. 容器实测：`/o2_core/o2/xAction/services/x_pan_assemble_control.js` → **404**（老 `x_file_assemble_control.js` → 200）。
3. 本地 `插件/` 64 个市场离线包 + `o2oa高级应用开发/` 全扫：**0 命中**。
4. 官方市场页：企业网盘 V2.7.5，需 V9.0+，标注 **VIP 应用（需联系商务）**。

⇒ 官方包不可得，故**代码级复刻**。

---

## 3. 数据层：实测可用的接口（x_file_assemble_control）

`describe.json` 共 111 个接口。复刻实际使用：

### 个人文件
| 用途 | 方法与路径 |
|---|---|
| 顶层文件夹 | `GET /jaxrs/folder2/list/top` |
| 子文件夹 | `GET /jaxrs/folder2/list/{id}` |
| 顶层文件 | `GET /jaxrs/attachment2/list/top` |
| 夹内文件 | `GET /jaxrs/attachment2/list/folder/{folderId}` |
| 新建文件夹 | `POST /jaxrs/folder2` `{name, superior}` |
| 上传 | `POST /jaxrs/attachment2/upload/folder/{folderId}`（multipart，字段 `file`） |
| 重命名 | `PUT /jaxrs/attachment2/{id}` `{name}` ／ `PUT /jaxrs/folder2/{id}` |
| 删除（进回收站） | `DELETE /jaxrs/attachment2/{id}` ／ `/folder2/{id}` |
| 下载 | `GET /jaxrs/attachment2/{id}/download`（另有 `/download/stream`） |
| 文件夹打包下载 | `GET /jaxrs/folder2/{id}/download`（zip，`Content-Disposition: inline`；**仅文件夹主人可下**） |
| Office 预览 | `GET /jaxrs/attachment2/{id}/office/preview/type/{type}`（本机无转换器 → 原样返回，见 7.5.3） |
| 图片缩放 | `GET /jaxrs/attachment2/{id}/image/width/{w}/height/{h}/binary/base64` |
| 分类分页 | `POST /jaxrs/attachment2/list/type/{page}/size/{size}` `{fileType}` |
| 容量 | `GET /jaxrs/attachment2/user/capacity` |

### 企业文件（组织级共享 —— 真实能力，非空壳）
| 用途 | 方法与路径 |
|---|---|
| 共享给我的 | `GET /jaxrs/share/list/to/me`（`to/me2/{fileType}` 可按类型） |
| 我分享出去的 | `GET /jaxrs/share/list/my`（`my2/{shareType}/{fileType}`） |
| 创建共享 | `POST /jaxrs/share` `{fileId, shareType, shareUserList[], shareOrgList[], shareGroupList[]}` |
| 取消共享 | `DELETE /jaxrs/share/{id}` |
| 浏览共享文件夹 | `GET /jaxrs/share/list/att/share/{shareId}/folder/{folderId}/` |
| 下载共享文件 | `GET /jaxrs/share/download/share/{shareId}/file/{fileId}` |
| 保存到我的网盘 | `POST /jaxrs/share/share/{shareId}/file/{fileId}/folder/{folderId}` |

**共享模型的三种作用域**（`ShareFactory` 源码确认）：`shareUserList`（指定人）、
**`shareOrgList`（按组织 → 全员可见）**、`shareGroupList`（按群组）。
「收到的共享」= 我 + 我所属全部上级组织的 unique + 我的群组 − `shieldUserList`。
⇒ 这正是"企业文件"栏的成立依据：把文件共享给顶层组织，全员可见。

### 回收站
`GET /jaxrs/recycle/list`、`POST /jaxrs/recycle/{id}/resume`、
`DELETE /jaxrs/recycle/{id}/delete`、`DELETE /jaxrs/recycle/empty`

### 关键语义（踩过的坑）
| 项 | 正确值 | 说明 |
|---|---|---|
| 顶层目录常量 | `$$TOP_FOLD` | 建顶层文件夹时 `superior` **留空**，服务端自动填；不是 `(0)` |
| `list/top` 语义 | `person=我` AND `status=VALID` AND `folder=$$TOP_FOLD` | 传错 folder 会"存进去但列不出来" |
| 返回 `count` | list 类接口 `count` 恒为 0 | 用 `data.length` 判断；分页接口才填 count |
| 上传字段名 | `file` | multipart |
| 鉴权 | cookie `x-token`（`o2.tokenName`） | 同源自动携带；也可显式放 header |
| 组织 unique | `GET /x_organization_assemble_control/jaxrs/unit/list/top` | 分享给组织需 **unique**（非 id） |
| **目录端点必须配对** | 建目录用 `folder2`，删/改也必须用 `folder2` | `/folder/{id}` 走旧表 `FILE_FOLDER`，对 `folder2` 目录恒报「指定的目录不存在」 |
| **`role/list/like`** | `PUT`（非 GET），body `{key}`，`key` 为空返回空数组 | 本组织只有系统角色，故按中文名搜不到属正常 |
| **`person/list/like`** | `PUT`，body `{key}` | 返回含 `distinguishedName`，权限名单存此值 |

---

## 4. 组件结构

```
patch/web/x_component_Drive/
├── Main.js / Main.min.js       ★ 组件主类（薄壳）——两个文件都必须有，见第 4.1 节
├── lp/zh-cn.js / .min.js       语言包（title=企业网盘）
├── $Main/
│   ├── icon.json               扩展名→图标映射
│   ├── flatlnk.png
│   └── default/
│       ├── css.wcss            O2OA 框架要求（内容为 {}）
│       ├── icon.png            应用图标
│       ├── file/               43 个文件类型图标
│       └── icon/               导航/操作图标
└── drive/
    ├── drive.js                UI + 数据访问（自包含，原生 DOM/XHR）
    └── drive.css               样式（全部 .drive-root 前缀限定）
```

**加载链**：开始菜单项（`CPT_COMPONENT.xpath='Drive'`）或门户应用菜单（字典 `app='Drive'`）
→ 前端 `o2.requireApp("Drive","Main")`
→ `/x_component_Drive/Main.min.js`
→ `loadApplication()` 内注入 `drive.css` + `drive.js`
→ `new MWF.xApplication.Drive.Viewer({container, app})` 渲染。

> `Main.js` 不依赖 MWF 的 UI 组件体系，`Viewer` 只用原生 DOM/XHR，
> 因此同一份 `drive.js` 也可嵌到门户页等其它宿主中复用。

### 4.1 ★ 必须同时提供 `*.min.js`（本次"一片空白"的根因）

O2OA 前端加载器（`o2_core/bundle.js` 内 `_requireJs`）在**非调试会话**下会改写文件名：

```js
var jsPath = (compression || !this.o2.session.isDebugger) ? url.replace(/\.js/, ".min.js") : url;
```

即：`x_component_Drive/Main.js` 会被请求成 **`Main.min.js`**。
官方组件（如 `x_component_File`）都是 `Main.js` + `Main.min.js` 成对发布，所以不显眼；
自研组件若只放 `Main.js`，后果是：

| 现象 | 根因 |
|---|---|
| 点开应用是**一片空白**，应用窗口 HTML 长度为 0 | `Main.min.js` 404 → 组件命名空间未注册 |
| 控制台 `Cannot read properties of undefined (reading 'options')` / `n.Main is not a constructor` | `layout.openApplication` 拿到 undefined 的 `appNamespace` |

> 本项目的做法：`Main.js → Main.min.js`、`lp/zh-cn.js → lp/zh-cn.min.js` 直接同名复制
> （内容不必真的压缩，O2OA 只看文件名）。`drive/drive.js` 由本组件自己用
> `<script src>` 显式注入，不走 `_requireJs`，因此不受影响。

### 4.2 ★「企业网盘」共有 3 个入口，数据源各不相同

只改一处 = 改了一半，表现为"点某个入口仍是老界面/空白"。全量对照：

| # | 入口 | 数据源 | 定位于 |
|---|---|---|---|
| 1 | 桌面「开始」菜单 | MySQL `CPT_COMPONENT.xpath`（桌面拿 xpath 当 app 名调 `layout.openApplication`） | xid `57af03cd-…`（xname=企业网盘） |
| 2 | 门户「应用列表」 | 门户数据字典 `GEN_DICT` + `GEN_DICT_ITEM`（`appNavis/<组>/children/<项>/app`） | xid `19404d80-…` |
| 3 | 桌面 `$Layout/applications.json` / 门户 `pcClient` | — | **实测不含网盘项，无需处理** |

统一入口：`python tools/o2_drive_entry.py check|apply|rollback`（一次改 #1＋#2）。

---

## 5. 部署步骤（可重放）

```bash
# 1) 组件入容器（servers/webServer 在镜像内、无卷；docker cp 立即生效）
docker cp patch/web/x_component_Drive o2oa-server:/opt/o2server/servers/webServer/

# 2) 入口切换（#1 开始菜单 + #2 门户应用菜单；rollback 可回退）
python tools/o2_drive_entry.py apply

# 3) 重启使静态资源索引与组件/字典缓存刷新（不重启不生效，已实测）
docker restart o2oa-server

# 4) 按规程恢复断网隔离
bash o2oa_netlock.sh
```

**重建不丢**：Dockerfile 已加
`COPY patch/web/x_component_Drive ${O2OA_HOME}/servers/webServer/x_component_Drive`
（源/目标路径均不含 `$`，无需像 `$Layout` 那样转义）。

---

## 6. 菜单切换为什么改数据库

官方写入接口应为
`PUT /x_portal_assemble_surface/jaxrs/dict/{dictFlag}/portal/{portalFlag}/{path}/data`，
但本部署上被 HTTP 层拦为 **405**；其 POST 伪装端点
`.../data/mockputtopost` 亦未注册（**404**）。

字典的存储结构（已实测确定）：

| 表 | 说明 |
|---|---|
| `GEN_DICT` | `xalias='appmenus'`, `xapplication=<portalId>`；本例 `xid=3ba06aaa-42e5-43d7-9901-3989da4ac133` |
| `GEN_DICT_ITEM` | `xbundle=<dictId>`，用 `xpath0..xpath7` 精确定位，值为多态列 |

xpath 规则：`appNavis / <组索引> / children / <项索引> / <字段名>`

本例目标行（**全表唯一**，无歧义）：

```
xid      = 19404d80-5968-4c97-95eb-04366aaedda2
xpath    = appNavis / 5(工作协同) / children / 4 / app
xstringShortValue : File -> Drive
```

`tools/o2_dict_set_menu_app.py` 提供 `check / apply / rollback`，并在执行前校验唯一性。

---

## 7. 验证证据（实测）

### 数据层闭环（真实读写）
| 环节 | 结果 |
|---|---|
| 建文件夹 | 200，`企业文件` id 生成 |
| 上传（夹内 / 顶层 `$$TOP_FOLD`） | 200，返回文件 id |
| `folder2/list/top` | 返回 `企业文件`，files=1 size=39 |
| `attachment2/list/top` | 返回 `顶层文件.txt` len=39 |
| `attachment2/list/folder/{id}` | 返回 `夹内文件.txt` |
| `user/capacity` | 78 字节（39+39） |
| `download/stream` | 39 字节，内容一致 |
| `list/type(office)` | count=2 |
| 删除 → `recycle/list` | 回收站可见 2 条 |

### 组织级共享闭环（"企业文件"栏的依据）
| 环节 | 结果 |
|---|---|
| `unit/list/top` | 组织 `中国复合材料工业协会` unique=`51100000500009247D` |
| `POST /share`（shareOrgList=[该 unique]） | 200 |
| `share/list/my` | 1 条，org=[51100000500009247D] |
| `share/list/to/me` | 1 条（组织维度可见） |
| `share/list/to/me2/attachment` | 1 条 |

### 部署结果
| 检查 | 结果 |
|---|---|
| `/x_component_Drive/Main.js` | 200，3949B（与本地一致） |
| `/x_component_Drive/Main.min.js` | 200，3949B（**必需**，见 4.1） |
| `/x_component_Drive/drive/drive.js` | 200，51756B（一致） |
| `/x_component_Drive/drive/drive.css` | 200，10319B（一致） |
| `/x_component_Drive/lp/zh-cn.js` / `.min.js` | 200，1462B（一致） |
| 编码 | `application/javascript`，UTF-8 中文完好 |
| 门户字典 GET | `分组=工作协同 app=Drive actionType=app portal=Drive` |
| `CPT_COMPONENT.xpath` | `Drive`（开始菜单入口） |

### ★ 前端 UI 真机验证（真实浏览器 + 真实用户路径）

`tools/o2_drive_selftest.py` 只覆盖后端数据层——本次"一片空白"正是它的盲区：
后端 20/20 全通，前端却因缺 `Main.min.js` 完全不渲染。故补一个 UI 层回归工具：

```bash
bash tools/o2_drive_ui_verify.sh            # PASS/FAIL + 截图
```

它用 agent-browser 走**真实路径**：登录桌面 → 办公中心 → 开始菜单「企业网盘」→ 断言：

| 断言 | 实测 |
|---|---|
| 命中入口 `.layout_start_item`「企业网盘」 | `clicked` |
| `.drive-root` 已渲染 | `true` |
| `MWF.xApplication.Drive.Viewer` 已加载 | `function` |
| 前端 JS 报错 | `[]`（0 条） |
| 渲染文本 | 系统管理员 / 中国复合材料工业协会 / 个人文件·企业文件·我的分享·回收站 / 后台管理 / 上传·新建文件夹·刷新 / 全部·图片·文档·视频·音乐·其它 / 已使用 0 B / 数据源：x_file_assemble_control |

截图存档：`docs/artifacts/drive-ui-verified.png`、`docs/artifacts/drive-ui-verify-run.png`。

> 复用要点（否则会白跑）：
> ① agent-browser 的浏览器会话**不跨命令存活**，整条流程必须写在一次调用里；
> ② `screenshot` 的第 1 个位置参数是**选择器**而非路径，要用 `screenshot body <path>`；
> ③ `eval` 返回值是 JSON 转义字符串，断言前先去掉反斜杠。

---

## 7.5 第五批：删除修复 / 文件夹共享 / 在线预览 / 网盘策略（2026-09-23）

### 7.5.1 文件夹删除报「指定的目录不存在」——根因与修复

- **现象**：个人文件里删除文件夹，底部报 `指定的目录: <uuid> 不存在.`，服务端 500。
- **根因**：O2OA 存在**两套目录表 + 两套 REST**：

  | 表 | 端点 | 实体 |
  |---|---|---|
  | `FILE_FOLDER`（旧） | `DELETE /jaxrs/folder/{id}` | `Folder` |
  | `FILE_FOLDER2`（新） | `DELETE /jaxrs/folder2/{id}` | `Folder2` |

  前端 `remove("folder", id)` 拼的是 `/folder/{id}`，而目录是用 `folder2` 建的、落在 `FILE_FOLDER2`，
  旧接口 `emc.find(id, Folder.class)` 自然找不到 → 抛 `ExceptionFolderNotExist`。
- **实测对照**：`DELETE /folder/{id}` → **500 指定的目录不存在**；`DELETE /folder2/{id}` → **200**。
- **修复**：`remove()` 中 `kind === "folder"` 时改用 `folder2` 段。
- **取证手法**：`docker logs o2oa-server --since 3h | grep -i "指定的目录\|FolderNotExist"`
  会直接打印 `method:DELETE, request:.../jaxrs/folder/...` 与异常类，一步定位。

### 7.5.2 共享支持文件夹（不只文件）

- `POST /jaxrs/share` 传 `fileId` = **文件夹 id** 时，服务端自动把 `fileType` 置为 `folder`
  （实测 `share/list/my` 返回 `('__PRB2_x', 'folder', ['51100000500009247D'])`）。
- 文件夹共享后同样可浏览：`share/list/folder/share/{sid}/folder/{fid}/`（子夹）+
  `share/list/att/share/{sid}/folder/{fid}/`（文件）；单文件下载/预览走
  `share/download/share/{sid}/file/{aid}`（返回 `Content-Disposition: inline`）。
- **UI**：「企业文件 / 我的分享」中的文件夹行可「浏览」，进入后与后台管理共用同一套
  共享浏览视图（面包屑 + 返回列表）。他人共享的文件夹不提供「打包下载」
  （`folder2/{id}/download` 只对文件夹主人放行），进入后按文件逐个下载。

### 7.5.3 在线预览（真实内嵌，非占位）

- **关键**：`attachment2/{id}/download` 返回**真实 MIME**（`text/plain;charset=utf-8`、`image/png`、
  `application/pdf`…），且同源请求自动带 `x-token` cookie，可直接作为
  `<img src>` / `<iframe src>` / `<audio|video src>` 使用。
- **落地**：图片 `<img>`、PDF `<iframe>`、文本经 XHR 取回后 `<pre>`、音视频 `<audio|video controls>`；
  共享上下文统一走 `share/download/...`（inline，尊重共享范围）。
- **★ Office 不做伪预览**：`attachment2/{id}/office/preview/type/{html|pdf|image}` 实测
  **把原文件原样返回**（`bytes` 与源文件相同、`Content-Type` 仍是 docx），说明本机没有
  LibreOffice / OnlyOffice 转换器。UI 因此**明确提示**"未安装 Office 转换组件，请下载查看"，
  不假报成功。

### 7.5.4 网盘策略（本地替代官方 pan 的两项专有配置）

**存储** = 门户数据字典 `driveSetting`（portal = `index`）。★ **读写通道不对称**（本部署实测）：

| 操作 | 端点 | 结果 |
|---|---|---|
| 读 | `GET /x_portal_assemble_surface/jaxrs/dict/driveSetting/portal/index/data` | **200**（任意登录用户可读） |
| 写 | `PUT /x_portal_assemble_surface/jaxrs/dict/{alias}/portal/{p}/{path}/data` | **405**（HTTP 层拦截，与既有结论一致） |
| 写 | `PUT /x_portal_assemble_designer/jaxrs/dict/{dictId}`（整对象覆盖，含 `data`） | **200** ✅ |
| 建 | `POST /x_portal_assemble_designer/jaxrs/dict` `{application:<portalId>, alias, name, data}` | **200** |

策略字段：`{shareLimitMb, creatorPersonList[], creatorRoleList[]}`（前端缺失时自动建字典并解析 `portalId/dictId`）。

- **共享区可创建权限列表**：名单非空时，只有名单内**人员**（`distinguishedName`）或**角色**
  （`unique` / `name`；当前用户角色形如 `Manager@ManagerSystemRole@R`，按 `@` 拆分匹配）
  才能「共享到企业」/「新建共享区」；名单为空 = 不限制（默认）。
- **共享区文件上传大小限制**：前端在**开始上传前**按 `file.size` 校验，超限文件直接拦截并提示
  `超过共享区上传上限 N MB，已跳过：xxx（2.0 MB）`；`0` = 不限制。仅对共享区上传生效。
- **安全闸**：designer 写需门户管理权限（admin 的 `Manager` 角色满足），普通用户只能读。

### 7.5.5 顺带修掉的隐藏 bug

`renderToolbar()` 中 `this.state.isAreaMine()` —— `isAreaMine` 定义在 `Viewer.prototype` 上而非
`state` 上。一旦进入「后台管理 → 共享区文件 → 进入共享区」就抛
`TypeError: this.state.isAreaMine is not a function`，工具栏渲染中断（上传/新建文件夹按钮消失）。
上一批验证未走到该路径故未暴露；已改为 `this.isAreaMine()`。

### 7.5.6 真机回归结果（agent-browser · 真实桌面路径）

| 断言 | 实测 |
|---|---|
| 组件渲染 / Viewer / 导航项 | `true` / `function` / 5 |
| 新建文件夹 → 删除 | 建成功；**删除后不存在、无 JS 报错**（folder2 修复生效） |
| 上传 png + txt | `true / true` |
| png 在线预览 | `open=true`，`naturalWidth=1`（真加载出图），带下载按钮 |
| txt 在线预览 | `open=true`，内容 `hello 中文预览 line2`（中文正常） |
| 文件夹「共享到企业」 | 「我的分享」`found=true`，标签「文件夹 / 全员 1」 |
| 设置页 | 标题 `[网盘策略, 系统设置]`，6 行配置，权限编辑器存在，**嵌套数 0** |
| 角色搜索 / 加标签 | `UnitManager·TeamWorkManager·ServiceManager·RoleManager` / `UnitManager×` |
| 保存（上限=1MB） | 服务端字典读回 `{shareLimitMb:1.0, creatorRoleList:['UnitManagerSystemRole']}` |
| **超限拦截** | `超过共享区上传上限 1 MB，已跳过：__rt5_big.bin（2.0 MB）` |
| 前端 JS 报错 | **0 条** |

> 正向对照说明：换 `.txt` 小文件即正常通过；先前用 `.bin` 被拒是**服务端后缀白名单**
> （`fileTypeIncludes`）所致，与大小限制无关。

**回归脚本（可重放，已归档进 `tools/`，不必再手搓临时 runner）**：

```bash
bash tools/o2_drive_ui_verify.sh              # 冒烟：能否打开 / 有无 JS 报错
bash tools/o2_drive_regression.sh main        # 功能回归：上面整张表
bash tools/o2_drive_regression.sh uploadlimit # 专项：共享区上传大小上限拦截
```

> 注意回归会在网盘里留残留（测试文件夹 / 文件 / 共享），跑完需在界面里清理。

### 7.5.7 ★ 服务端「文件后缀白名单」是硬闸门（影响在线预览的可用范围）

`FILE_CONFIG.properties.fileTypeIncludes` 会在**上传时**强制校验，与本组件无关：

| 后缀 | 结果 |
|---|---|
| `doc docx xls xlsx ppt pptx pdf xapp text zip rar mp3 mp4 png jpg gif` | **200 通过** |
| `txt` `md` `py` `log` `json` `bin` | **500 【name】文件类型不符合上传要求** |

- **确定性验证**：`POST /config` 写入原列表 → `.txt` 仍 500；**列表追加 `txt`** → `.txt` 200；
  再还原原列表 → 又 500。（实验后已还原原列表）
- **注意**：注意列表里是 `text` 而**不是** `txt`——`.text` 能传，`.txt` 不能。这是 O2OA 自带的
  默认值，容易误判成"预览坏了"。
- **影响**：文本类文件（txt/md/json/log/代码文件）默认**传不进来**，于是"文本在线预览"形同虚设。
  如需文本类文件，请在「后台管理 → 设置 → 只允许上传的文件后缀」里补上（例：`text,txt,md,json,log`）。
- 该实验也解释了早期出现过的"同一 `.txt` 有时能传有时不能"——是配置缓存尚未生效前的窗口期假象。

### 7.5.8 真机验证的工程注意（再踩一次）

- `agent-browser` 的浏览器**每次 Bash 调用都是全新会话**，且**被 SIGTERM 杀掉的前一次运行会留下脏守护进程**
  → 脚本开头务必 `agent-browser close` 再 `open`，并**轮询** `layout.session.user` 确认登录成功再继续。
- 「一个 eval 一步」的写法极易受进程往返抖动影响（本次出现过 eval 返回 `{}`）；改为
  **一次 eval 注入整段异步流程**（结果写 `window.__rt5`，bash 只轮询）后稳定复现。
- 页面内 `eval` 的 JS 片段请**避免 `$` 与反引号**，便于用双引号安全传入 CLI。

---

## 7.6 第六批：后台管理与「角色/组」对齐 + 权限内成员容量统计（2026-09-23）

### 7.6.1 后台管理的授权锚点 = 服务端的 `controlAble`（不要自造判定）

`describe/.../Business.java`：

```java
public boolean controlAble(EffectivePerson effectivePerson) throws Exception {
    return effectivePerson.isManager()                       // 系统管理员
        || organization().person().hasRole(effectivePerson,  // 或持有 FileManager 角色
               OrganizationDefinition.FileManager);
}
```

`GET {SVC}/config/is/file/manager` 返回的就是它。**这就是「后台管理与角色对齐」的官方答案**：
给账号加上 `FileManager` 角色即获得后台管理能力，无需改代码、无需加配置项。
本组织的该角色为 `FileManager@FileManagerSystemRole@R`（`PUT {ORG}/role/list/like {"key":"File"}` 可确认）。

界面上新增**权限横幅**，把「为什么我能进后台管理 / 我管到哪 / 还有谁有权限」讲清楚：

| 行 | 取值来源 |
|---|---|
| 权限来源 | `config/is/file/manager` + 会话 `roleList`（系统管理员 / FileManager 角色） |
| 管辖范围 | `GET {ORG}/unit/list/control/top`（非组织管理员会自动收敛到本人管辖的顶层单位） |
| 授权名单 | `GET {ORG}/person/list/role/FileManager@FileManagerSystemRole@R` |

> **注意边界**：`controlAble` 是**全局**判定，不区分部门。想做「A 部门管理员只能看 A 部门」这种
> 真隔离，必须在服务端另写接口 —— 前端过滤只是体验层收窄，绕过前端直接调接口仍可读全量。

### 7.6.2 逐人容量：官方接口原生支持 `?person=`

`describe/.../jaxrs/attachment2/ActionUseCapacity.java`：

```java
String queryPerson = effectivePerson.getDistinguishedName();
if (business.controlAble(effectivePerson) && StringUtils.isNotBlank(person)) {
    queryPerson = person;              // ← 管理员才认这个参数
}
wo.setValue(business.attachment2().getUseCapacity(queryPerson));
```

口径（`Attachment2Factory#getUseCapacity`）：`sum(length) where person=? and status=VALID`
—— **不含回收站**（回收站条目不是 VALID）。

**确定性对照实验**（上传 1MB 后）：

| 查询 | 返回 |
|---|---|
| `GET attachment2/user/capacity`（自己） | 1048576 |
| `GET ...?person=系统管理员@admin@P`（上传者本人） | 1048576 |
| `GET ...?person=孟弋洁@mengyijie@P`（他人） | 0 |
| `GET ...?person=admin@admin@P`（不存在的 dN） | 0 |

⇒ 参数**精确到人**；非管理员即使传 `person`，服务端也强制回落查自己（不存在越权）。

### 7.6.3 ★★ 最大的坑：人员 dN ≠ 身份 dN（两者都是 `distinguishedName`）

`GET {ORG}/authentication` 返回：

```
data.distinguishedName                   = 系统管理员@admin@P                  ← 人员 dN（@P）
data.identityList[0].distinguishedName   = 系统管理员@51100000500009247D_admin@I ← 身份 dN（@I）
```

而 `attachment.person` / `share.person` 存的都是**人员 dN**。早期版本取了 `identityList[0]`，
导致：逐人容量全部查空（只剩自己一行）、「是否我本人的分享」判断恒为 false。
**凡是要跟 `person` 比对、或作为 `?person=` 参数的地方，一律用人员 dN。**

### 7.6.4 人员清单的两个来源（交叉合并）

本部署 **没有** `person/list/filter/{page}/{size}`（源码有、jar 里 404），因此用两条路合并：

| 路径 | 接口 | 提供 |
|---|---|---|
| 组织 | `unit/list/control/top` → `unit/list/{dn}/sub/nested` → `identity/list/unit/{dn}` | uuid + 姓名 + 部门 |
| 名册 | `person/list/{meDn}/prev\|next/500` | dN + 账号状态 + 最近登录 |

用 person 的 UUID 关联两者。逐人容量用**并发 6** 拉取，避免打爆服务端。

### 7.6.5 顺带修掉的两个真缺陷

1. **批量上传一个文件被拒 → 整批中断**：`upload()` 的失败分支直接 `return`（不调 `next()`），
   于是后续文件根本不上传、列表不刷新、只弹一条 toast 且新文件不出现。
   改为**失败也继续走完队列**，结束时汇总「N 个失败（M 个成功）：文件名（原因）…」并刷新列表。
2. **`.text` 无预览入口**：`PREVIEW_KIND.text` 只列了 `txt` 等，而服务端白名单放行的恰恰是
   `text`（放行白名单不含 `txt`）⇒ 「能传但看不到预览」。已把 `text` 补进分类表与图标映射。

### 7.6.6 真机回归结果（agent-browser）

| 断言 | 实测 |
|---|---|
| 后台管理子菜单 | 返回主菜单 / 共享区文件 / 共享区 / **成员容量** / **用户总览** / 回收站 / 设置（7 项） |
| 权限横幅 | 权限来源=系统管理员 ｜ 管辖范围=全部组织（全域）｜ 授权名单=（无持有者） |
| 成员容量统计卡 | 管辖成员 **10** ｜ 已用合计 ｜ 人均 ｜ 容量上限 ｜ 超限预警 ｜ 占用最多 |
| 成员明细表 | **10 行**，姓名/部门/已用/占比条/状态/最近登录；搜索「孟」→ 1 行；按姓名排序 → 首位「杜阳」 |
| 用户总览 | 用户总数 10 ｜ 有文件 0 ｜ 共享 0 ｜ 锁定禁用 0 ｜ 从未登录 8 |
| 全部共享区块 | 空态「当前没有任何共享（share/list 返回 0 条）」 |
| 前端 JS 报错 | **0 条** |

### 7.6.7 组织现状提示

`unit/list/top` = 「中国复合材料工业协会」，下级 4 个部门（综合管理部 / 行业研究部 / 会员服务部 / 国际业务部），
但 **10 个 identity 全部挂在顶层单位**下、4 个部门暂无身份 ⇒ 成员表的「所属部门」列统一显示顶层单位名。
若要让部门列真正区分，需要先把人员分配到各部门（组织管理里建 identity）。

---

## 8. 与官方 VIP 版的能力边界（诚实说明）

**已实现**：三栏信息架构（个人文件 / 企业文件 / 后台管理）＋ 我的分享 ＋ 回收站 ＋
分类筛选（全部/图片/文档/视频/音乐/其它）＋ 上传（按钮/拖拽，带进度 + 共享区大小上限校验）＋
新建文件夹 ＋ 重命名 ＋ 删除（进回收站）＋ 还原/彻底删除/清空 ＋ 下载 ＋ 文件夹打包下载 ＋
共享到企业（**文件与文件夹**，组织级）＋ 共享文件夹浏览 ＋ 保存到我的网盘 ＋
**在线预览**（图片 / PDF / 文本 / 音频 / 视频）＋ 容量与分类统计 ＋ 面包屑导航 ＋ 文件类型图标 ＋
后台管理 5 子页（共享区文件 / 共享区 / 个人容量 / 回收站 / 设置）＋
**共享区可创建权限名单** ＋ **共享区上传大小限制**（后两项为官方 pan 专有配置的本地替代）。

**未实现 / 依赖官方 pan（VIP）后端 `x_pan_assemble_control`**：
- Office 文档在线预览（doc/docx/xls/xlsx/ppt/pptx）——需 LibreOffice / OnlyOffice 转换器
- 文件版本历史、秒传去重 UI、企业级配额治理、后台管理员全局存储治理
- onlyOffice 回调配置（`http://host/x_pan_assemble_control/jaxrs`）

这些项在「设置」页已**明确标注为不可用**并说明原因，不做伪实现。其余缺失项
**不影响**"个人 / 企业 / 后台"主流程与真实数据读写。

---

## 9. 回滚

```bash
python tools/o2_drive_entry.py rollback    # 三个入口统一回 File（老版网盘仍完整可用）
docker restart o2oa-server                 # 必须重启才生效
bash o2oa_netlock.sh                       # 按规程恢复断网隔离
```

组件与老版 `x_component_File` **互不影响**（不同目录、不同组件名），可共存与随时切换。
`tools/o2_dict_set_menu_app.py`（仅门户字典）保留作为细粒度回退。
