---
name: o2oa-app-io
description: 在 O2OA（社区版 / Docker 自托管，10.0.2 实证）上**读出「设计定义」、打成 .xapp 导入包、再灌入另一套 O2OA**，以及**跨实例逐层对齐审计**。当用户说"把 demo/另一套 O2OA 的应用复刻过来""导出/导入应用""读出设计定义再组装导入包""各模块各层对齐""为什么导出报权限不足""企业网盘/门户导不出来""application/module 导入导出接口"时调用。覆盖：三层导入导出通道（designer input/output、program_center module、流程 lead/out）的确切 REST 路径与包结构、四个实测坑（门户 CacheKey 缺陷 / 流程·CMS 无 select_file / demo 禁用导出 / process 列表路径）、以及 list/diff/export/import 工具用法。
agent_created: true
category: operations
---

# O2OA 应用「设计定义」读出 → 打包 → 灌入

把一套 O2OA 的应用（门户/流程/查询/CMS）**原样搬到另一套 O2OA**，靠的不是手工重画，
而是 **读定义 → 组装 `.xapp` → 灌入** 这条官方通道。本技能记录 10.0.2 上实测验证过的
确切接口、包结构与坑。

## 0. 铁律

1. **★ 先找源码，别反编译。** O2OA 每个服务目录下都自带一份 Java 源码副本与 REST 目录：
   ```
   /opt/o2server/servers/applicationServer/work/<服务>/describe/sources/**/*.java   ← 实现源码
   /opt/o2server/servers/applicationServer/work/<服务>/describe/describe.json       ← 接口目录(path/type/ins/outs)
   /opt/o2server/servers/centerServer/work/x_program_center/...                     ← 整包导入导出在这
   ```
   任何 O2OA 接口存疑，先 `docker exec o2oa-server sh -c "cat .../describe/describe.json"`，不要猜。
2. **★ 写入前先 dry-run**：`import --dry-run` 只上传对比、不落库；确认 `exist` 与目标名再真灌。
3. **★ `create` vs `cover`**：`create` 保留源 id，冲突时由 `prepare/create` 分配新 id（重命名新建，安全）；
   `cover` **覆盖本地同 id 应用（破坏性）**，先备份、先向用户确认。
4. **★ 导出会建临时 `Structure` 记录**，用完即 `DELETE /x_program_center/jaxrs/module/remove/structure/{id}` 清理。
5. **★ `write/{flag}` 的 flag 一次有效**（取包即删）；dry-run 后要真灌，必须重新 `compare/upload` 拿新 flag。

## 1. 三层通道（全清单）

### 1.1 单应用级：各模块 designer 的 `input` / `output`（四类对称）

前缀：门户 `/x_portal_assemble_designer`、查询 `/x_query_assemble_designer`、
流程 `/x_processplatform_assemble_designer`、CMS `/x_cms_assemble_control`。

| 阶段 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 导出 | GET | `/jaxrs/output/list` | 列出全部应用，**返回对象自带完整子结构**（可直接喂 select/组包） |
| 导出 | PUT | `/jaxrs/output/{id}/select` | 选定结构 → `{flag}`（服务端缓存） |
| 导出 | GET | `/jaxrs/output/{flag}/select/file` | 下载 `<name>.xapp`（**门户/流程/CMS 见坑①）** |
| 导入 | PUT | `/jaxrs/input/compare` | 上传对比 → `{exist, existId, existName, existAlias}` |
| 导入 | PUT | `/jaxrs/input/prepare/create` | 预检新建 → `[{first:旧id, second:新id}]` |
| 导入 | PUT | `/jaxrs/input/create` | **新建落库** → `{id}` |
| 导入 | PUT | `/jaxrs/input/prepare/cover` | 预检覆盖 |
| 导入 | PUT | `/jaxrs/input/cover` | **覆盖落库** → `{id}` |

### 1.2 整包级：`x_program_center/jaxrs/module/*`（**首选，全类型通吃**）

| 阶段 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 组包 | **PUT** | `/module/output` | body `{name, description, portalList:[Wrap*], processPlatformList, queryList, cmsList, serviceModuleList}` → `{flag,…}` |
| 下载 | **GET** | `/module/output/{flag}/file` | `<name>.xapp` |
| 列表 | GET | `/module/output/list/structure` | 本地已存的 `.xapp` |
| 结构 | GET | `/module/output/structure` | 本地模块结构 |
| 清理 | DELETE | `/module/remove/structure/{id}` | 删除已存包 |
| 上传对比 | **PUT** | `/module/compare/upload` | **multipart，字段 `file`(字节) + `fileName`(名)** → `{flag, 各应用 exist 对比}` |
| **落库** | **PUT** | `/module/write/{flag}` | body `{portalList:[{id,method:"create"\|"cover"}], processPlatformList:[…], queryList:[…], cmsList:[…], serviceModuleList:[…]}` |

内部机理（源码 `ActionOutput.execute` / `ActionWrite.execute`）：
- `output`：对每个应用**再调对应 designer 的 `output/{id}/select`**（把 body 里的对象透传）
  ⇒ **body 里每个 `Wrap*` 必须带完整子结构**（用 `output/list` 的返回对象即可）。
  另有一道门：`if (Config.general().disableExportEnable()) throw ExceptionAccessDenied;`
- `write`：① 取包（缓存 `CacheKey(flag)`，miss 则查 DB `Structure` 并**取完即删**）
  ② 逐应用 `input/prepare/{create|cover}` 收 `WrapPair{first,second}`
  ③ `StringUtils.replace(json, first, second)` **字符串级替换 id** → `input/{create|cover}`

### 1.3 流程单流程导出

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/x_processplatform_assemble_designer/jaxrs/process/{id}/lead/out` | 单流程全元素（agent/begin/manual/route/branch…），**不含表单** |

## 2. 包结构：`.xapp` = JSON 文本（`gson.toJson(WrapModule)`）

**导出产物与导入体同构直通，无需转换。**

```
{ name, description, flag,
  portalList:          [ WrapPortal   {…, pageList[], scriptList[], fileList[], widgetList[], applicationDictList[]} ],
  processPlatformList: [ WrapProcessPlatform {…, processList[], formList[], scriptList[], fileList[], applicationDictList[]} ],
  queryList:           [ WrapQuery    {…, tableList[], viewList[], statementList[], statList[], importModelList[]} ],
  cmsList:             [ WrapCms      {…, categoryInfoList[], formList[], scriptList[]} ],
  serviceModuleList:   [ … ] }
```

## 3. ★ 四个实测坑（都踩过）

| # | 现象 | 根因 | 对策 |
|---|---|---|---|
| ① | 门户 `output/{flag}/select/file` 恒 500「下载标识不存在」 | `ActionSelect` 用 `CacheKey(this.getClass(), flag)`，`ActionSelectFile` 用 `CacheKey(flag)` → **缓存键不一致**（查询侧两侧一致故正常） | 门户**改走整包** `module/output` |
| ② | 流程/CMS 找不到 `select/file` | 它们的 `output` 只有 `list` + `{flag}/select`，**根本没有 file 接口** | 流程用 `lead/out`（单流程）或整包；CMS 用整包 |
| ③ | 源端 `module/output` 报「权限不足」 | 源端 `Config.general().disableExportEnable=true`（demo 即如此） | **源端只读定义 + 本地组包**：`output/list` 仍 200，把读到的 Wrap* 喂给**本地** `module/output`（工具 `--pack-on local` 已自动化） |
| ④ | `module/list`、`module/list/category` 500 | 它们走云端 `collect.o2oa.net` | 断云环境忽略；与本地导入导出无关 |

**另：`process` 列表路径易错**
- 流程应用列表 `GET …/jaxrs/application/list`
- 某应用下的流程 `GET …/jaxrs/process/application/{应用id}` ← **不是** `process/list/application/{id}`

## 4. 工具用法（**唯一真源：`D:\O2OA\tools\o2_app_io.py`**，纯标准库）

> ⚠️ **单一真源约定（2026-09-26）**：本 skill 不再自带 `scripts/o2_app_io.py` 副本，
> 一律调用项目仓 `D:\O2OA\tools\o2_app_io.py`（与 git 仓库、`o2oa_ops_mcp` 网关工具同源，
> 避免多份漂移）。任何对导出/导入逻辑的修 bug，只改这一处。

```bash
PY="C:/Users/meng_/.workbuddy/binaries/python/versions/3.13.12/python.exe"
TOOLS="D:/O2OA/tools"

# 列应用
"$PY" "$TOOLS/o2_app_io.py" list --side local --type query
"$PY" "$TOOLS/o2_app_io.py" list --side demo  --type portal

# 跨实例逐层对齐审计（剔除时间戳后字节级比对）
"$PY" "$TOOLS/o2_app_io.py" diff --type all

# 导出：读定义(源) → 组包(本地) → .xapp
"$PY" "$TOOLS/o2_app_io.py" export --side demo  --type portal --name 数据管理 -o 数据管理.xapp
"$PY" "$TOOLS/o2_app_io.py" export --side local --type query  --name 员工管理 -o 员工管理.xapp

# 单流程导出
"$PY" "$TOOLS/o2_app_io.py" leadout --side demo --app 事项审批 -o 事项审批.流程.json

# 灌入本地：先 dry-run 看冲突，再真灌（★写入/破坏性，须用户确认）
"$PY" "$TOOLS/o2_app_io.py" import -f 数据管理.xapp --dry-run
"$PY" "$TOOLS/o2_app_io.py" import -f 数据管理.xapp --method cover    # 覆盖同名(破坏性)
"$PY" "$TOOLS/o2_app_io.py" import -f 数据管理.xapp --method create   # 重命名新建
```

脚内侧默认两端：`local = http://localhost:9090 (admin/o2oaadmin2026)`、
`demo = https://samplev10.o2oa.net (admin/999000%o2)`；改 SIDES 字典即可复用其它实例。

## 5. 手工调用（不依赖工具时的最小命令序列）

```bash
T=$(curl -s --noproxy "*" -X POST http://localhost:9090/x_organization_assemble_authentication/jaxrs/authentication \
     -H "Content-Type: application/json" -d '{"credential":"admin","password":"o2oaadmin2026"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")

# 导出（整包）
curl -s --noproxy "*" -X PUT "http://localhost:9090/x_program_center/jaxrs/module/output" \
  -H "x-token: $T" -H "Content-Type: application/json" \
  -d '{"name":"pack1","portalList":[<从 output/list 复制的完整 WrapPortal>]}'   # → {flag}
curl -s --noproxy "*" -H "x-token: $T" \
  "http://localhost:9090/x_program_center/jaxrs/module/output/<flag>/file" -o pack1.xapp

# 导入（上传对比 → 落库）
curl -s --noproxy "*" -X PUT "http://localhost:9090/x_program_center/jaxrs/module/compare/upload" \
  -H "x-token: $T" -F 'file=@pack1.xapp' -F 'fileName=pack1.xapp'          # → {flag, exist 对比}
curl -s --noproxy "*" -X PUT "http://localhost:9090/x_program_center/jaxrs/module/write/<flag>" \
  -H "x-token: $T" -H "Content-Type: application/json" \
  -d '{"portalList":[{"id":"<包内门户id>","method":"create"}]}'
```

## 6. 对齐审计基线（2026-09-22，本地 vs samplev10）

| 类型 | 共有 | 一致 | 不一致 | 仅 demo |
|---|---|---|---|---|
| portal | 41 | 41 | 0 | 0 |
| process | 65 | 64 | 1 | 0 |
| query | 38 | 35 | 3 | 0 |
| cms | 37 | 37 | 0 | 0 |

- 比对须**剔除** `createTime/updateTime/lastUpdateTime/lastUpdatePerson/creatorPerson/distributeFactor`，否则全是噪声。
- 本基线全部"不一致"**均为本地超集**（本地多 `importModelList`/`statList`/`tableList[newTable_localSample]`，及流程 `begin.allowReroute`、`manualList[].defaultAddTaskType·Mode` 默认值）→ 本地是导入重建，新版 schema 自动补默认字段。
- 清单层面 demo 唯一独有：空壳流程应用「测试」`d78e479c-f3ef-45ae-823c-b412bb9391c2`（`processList=[]`、`formList=[]`）→ 无复刻价值。
- **判读规则：先比"清单是否同 id 同数"，再比"内容是否一致"。差异优先判断超集/子集，别一看到 hash 不同就当缺失。**

## 7. 完成后必须清理

```bash
curl -s --noproxy "*" -X DELETE "http://localhost:9090/x_program_center/jaxrs/module/remove/structure/<id>" -H "x-token: $T"
curl -s --noproxy "*" -H "x-token: $T" "http://localhost:9090/x_program_center/jaxrs/module/output/list/structure"
```
`import --dry-run` 也会留一条 `Structure`，记得清。
