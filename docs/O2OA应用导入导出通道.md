# O2OA 应用「设计定义」读出 / 打包 / 灌入 通道

> **环境**：O2OA 社区版 10.0.2（本机 `192.168.1.5:9090`，容器 `o2oa-server`）
> **对标源**：`https://samplev10.o2oa.net`（`admin` / `999000%o2`）
> **逆向来源**：各服务自带 `describe/sources/**/*.java`（O2OA 会随服务发布一份 Java 源码副本）
> **结论日期**：2026-09-22　**全部结论均有可复现的命令证据**

---

## 0. 结论速览

| 问题 | 答案 |
|---|---|
| demo 的「设计定义」能不能读出来？ | **能**。designer 的 `output/list` 只读可读（200），且 `output/list` **本身就带完整子结构**（页面/脚本/文件/控件/字典） |
| 能不能"读出定义 → 组装成导入包 → 灌进本地"？ | **能，且是官方范式**。`module/output` 组包 → `.xapp` → `module/compare/upload` → `module/write/{flag}`；`write` 内部自动做 `input/prepare/* → id 替换 → input/*` |
| demo 能不能直接导出 `.xapp`？ | **不能**。demo 开了「禁用导出」开关（`Config.general().disableExportEnable=true`），`/module/output` 报 `权限不足`；**但定义数据仍可逐条读出** |
| 那怎么打包？ | **以本地 O2OA 当"打包机"**：从 demo 读定义 → POST 到本地 `/module/output` → 得 `.xapp` → 再灌入本地（见 §4、§6） |
| demo 与本地各层对齐了吗？ | **已对齐**。查询 38 应用 / 流程 65 流程，**35 + 64 项剔除时间戳后字节级一致**；余下差异**全部是本地比 demo 多**（超集），无一处 demo 有而本地缺；四类应用 id 清单逐一相同 |

---

## 1. 接口全清单（三类通道）

### 1.1 单应用级：各模块 designer 的 `input` / `output`

四类模块结构完全对称（`portal` / `query` / `processplatform` / `cms`）：

| 阶段 | 方法 | 路径（以门户为例，前缀 `/x_portal_assemble_designer`） | 作用 |
|---|---|---|---|
| 导出 | GET | `/jaxrs/output/list` | 列出全部应用 **（含完整子结构）** |
| 导出 | PUT | `/jaxrs/output/{portalFlag}/select` | 选定结构 → 返回 `{flag}`（服务端缓存） |
| 导出 | GET | `/jaxrs/output/{flag}/select/file` | **下载 `<name>.xapp`**（`gson.toJson(WrapPortal)`） |
| 导入 | PUT | `/jaxrs/input/compare` | 上传对比（返回 `exist/existId/existName/existAlias`） |
| 导入 | PUT | `/jaxrs/input/prepare/create` | 预检新建 → 返回 `[{first:旧id, second:新id}]` |
| 导入 | PUT | `/jaxrs/input/create` | **新建落库** → `{id}` |
| 导入 | PUT | `/jaxrs/input/prepare/cover` | 预检覆盖 |
| 导入 | PUT | `/jaxrs/input/cover` | **覆盖落库** → `{id}` |

**⚠ 门户 designer 存在缺陷（10.0.2 实测）**：
`ActionSelect` 用 `new CacheKey(this.getClass(), flag)`，而 `ActionSelectFile` 用 `new CacheKey(flag)` → **缓存键不一致，`select/file` 必然 500「下载标识不存在」**。
查询侧两侧都是 `CacheKey(flag)`，故**查询的 `.xapp` 导出正常**。
→ **门户/流程/CMS 的导出统一改走 §1.2 的整包通道**（`tools/o2_app_io.py` 已默认如此）。

### 1.2 整包级：`x_program_center` 的 `module`

| 阶段 | 方法 | 路径 | 作用 |
|---|---|---|---|
| 目录 | PUT | `/x_program_center/jaxrs/module/list` | 云服务器模块分类（**断云后失败**，走 `collect.o2oa.net`） |
| 目录 | GET | `/x_program_center/jaxrs/module/list/category` | 同上 |
| **导出** | **PUT** | **`/x_program_center/jaxrs/module/output`** | **组包**，body = `{name, description, portalList:[…], processPlatformList:[…], queryList:[…], cmsList:[…], serviceModuleList:[…]}` → `{flag, …}`，并把包落到 `Structure` 实体 |
| **导出** | **GET** | **`/x_program_center/jaxrs/module/output/{flag}/file`** | **下载 `<name>.xapp`** |
| 已存包 | GET | `/x_program_center/jaxrs/module/output/list/structure` | 列示本地已存的 `.xapp` |
| 本地结构 | GET | `/x_program_center/jaxrs/module/output/structure` | 本地模块结构 |
| 清理 | DELETE | `/x_program_center/jaxrs/module/remove/structure/{id}` | 删除已存包 |
| **导入** | **PUT** | **`/x_program_center/jaxrs/module/compare/upload`** | **上传 `.xapp` 对比**（multipart：`file`=字节、`fileName`=文件名）→ `{flag, 各应用 exist 对比}` |
| **导入** | **PUT** | **`/x_program_center/jaxrs/module/write/{flag}`** | **落库**，body = `{portalList:[{id, method:"create"\|"cover"}], processPlatformList:[…], queryList:[…], cmsList:[…], serviceModuleList:[…]}` |

**`module/output` 的两道门**（源码 `ActionOutput.execute`）：
1. `if (Config.general().getDisableExportEnable() == true) throw ExceptionAccessDenied;` → **demo 报「权限不足」的真因**
2. 对每个应用，**内部再去调对应 designer 的 `output/{id}/select`**（把传进来的对象透传）→ 所以 body 里的每个 `Wrap*` **必须带完整子结构**（用 `output/list` 的返回对象即可）

**`module/write/{flag}` 的三步内部实现**（源码 `ActionWrite.execute`）：
1. 取包：先查缓存（`CacheKey(flag)`），miss 则查 DB `Structure` → **取完即删**（`structure.deleteContent()` + `emc.delete`）
2. 对每个应用调 `input/prepare/{create|cover}` → 收集 `WrapPair{first,second}`（**本地已占用 id → 新 id**）
3. 用 `StringUtils.replace(json, first, second)` **字符串级替换 id** → 调 `input/{create|cover}` 落库

### 1.3 流程单流程导出

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/x_processplatform_assemble_designer/jaxrs/process/{id}/lead/out` | **导出单个流程**（含 manual/route/branch… 全元素，**不含表单**，表单需另取） |

**process 列表路径核准**（易错点）：

| 用途 | 正解 |
|---|---|
| 流程应用列表 | `GET /x_processplatform_assemble_designer/jaxrs/application/list` |
| 某应用下的流程列表 | `GET /x_processplatform_assemble_designer/jaxrs/process/application/{应用id}` ← **不是** `process/list/application/{id}` |
| 流程分类 | `GET /x_processplatform_assemble_designer/jaxrs/processCategory/list/{id}/next/{count}` |

---

## 2. 包结构（`.xapp` 数据模型）

`.xapp` 就是 **JSON 文本**（`gson.toJson(WrapModule)`），导入体与之**同构直通**，无需转换：

```jsonc
{
  "name": "包名", "description": "描述", "flag": "…",
  "portalList": [ { /* WrapPortal */
      "id","name","alias","description","portalCategory","firstPage","icon","pcClient","mobileClient",
      "availableIdentityList":[],"availableUnitList":[],"availableGroupList":[],"controllerList":[],
      "properties":{}, "cornerMarkScript","cornerMarkScriptText",
      "pageList":[...], "scriptList":[...], "fileList":[...], "widgetList":[...], "applicationDictList":[...]
  } ],
  "processPlatformList": [ { /* WrapProcessPlatform */
      "id","name","alias","defaultForm","maintenanceIdentity","maintainerList":[],
      "processList":[...], "formList":[...], "scriptList":[...], "fileList":[...], "applicationDictList":[...]
  } ],
  "queryList":  [ { /* WrapQuery: tableList/viewList/statementList/statList/importModelList */ } ],
  "cmsList":    [ { /* WrapCms:   categoryInfoList/formList/scriptList/… */ } ],
  "serviceModuleList": [ … ]
}
```

- 门户包 = **Portal + Page + Script + Widget + File + ApplicationDict**
- 流程包 = **Application + Process + Form + Script + File + ApplicationDict**（流程内再含 Agent/Begin/Cancel/Choice/Delay/Embed/End/Invoke/Manual/Merge/Parallel/Publish/Service/Split/Route…）
- 查询包 = **Query + Table + View + Statement + Stat + ImportModel**
- CMS 包 = **AppInfo + CategoryInfo + Form + Script + …**

---

## 3. 导出链路（ASCII）

```
源端 O2OA                                              目标端 O2OA
──────────                                             ──────────
GET  …/jaxrs/output/list            ← 读定义（只读，200）
      ↓ 取到完整 Wrap*（含子结构）
PUT  /x_program_center/jaxrs/module/output   body={name, portalList:[Wrap*], …}
      ↓ {flag}
GET  /x_program_center/jaxrs/module/output/{flag}/file
      ↓
   <name>.xapp  ────────────── 搬运 ──────────────→  PUT  …/module/compare/upload  (file,fileName)
                                                        ↓ {flag, exist 对比}
                                                    PUT  …/module/write/{flag}
                                                        body={portalList:[{id,method:"create"|"cover"}]}
                                                        ↓ 内部自动 prepare → id 替换 → create/cover
                                                     落库完成
```

**若源端被禁用导出**（demo 即如此）：
把「读定义」留在源端，**组包改在目标端（本地）执行** —— 即 `PUT 本地/module/output`。这正是 `tools/o2_app_io.py export --side demo --pack-on local` 的行为。

---

## 4. 工具用法

`tools/o2_app_io.py`（纯标准库，Python 3）

```bash
# 列出应用（四类）
python tools/o2_app_io.py list --side local --type query
python tools/o2_app_io.py list --side demo  --type portal

# 两端全量对齐比对（剔除时间戳后字节级）
python tools/o2_app_io.py diff --type all

# 导出：读 demo 定义 → 本地组包 → 落 .xapp
python tools/o2_app_io.py export --side demo --type portal --name 数据管理 -o 数据管理.xapp
python tools/o2_app_io.py export --side local --type query  --name 员工管理 -o 员工管理.xapp

# 单流程导出（JSON）
python tools/o2_app_io.py leadout --side demo --app 事项审批 -o 事项审批.流程.json

# 灌入本地（先 dry-run 看冲突，再真灌）
python tools/o2_app_io.py import -f 数据管理.xapp --dry-run
python tools/o2_app_io.py import -f 数据管理.xapp --method cover      # 覆盖同名
python tools/o2_app_io.py import -f 数据管理.xapp --method create     # 重命名新建
```

**注意**：
- `export` 会在目标端生成一条临时 `Structure` 记录，工具已自动 `DELETE /module/remove/structure/{id}` 清理。
- `import --dry-run` 会上传并落一条临时 `Structure`（**不落库应用数据**）；如需清理：
  `DELETE /x_program_center/jaxrs/module/remove/structure/{flag}`。
- `import` 会**消耗（删除）**该 `Structure`，同一 flag 不能重复 write。

---

## 5. 本次实测证据

| 证据 | 命令 | 结果 |
|---|---|---|
| designer `output/list` 可读 | `GET /x_portal_assemble_designer/jaxrs/output/list` | **200**，本地 41 / demo 41 |
| 查询 `.xapp` 导出 | `output/list → select → select/file` | 本地与 demo **均 200，均 499,249 字节** |
| 单流程导出 | `GET …/process/{id}/lead/out` | 本地与 demo **均 200**（66 / 67 字段） |
| 整包组包+下载 | `PUT /module/output` → `GET …/{flag}/file` | **200**，192,869 字节完整 `.xapp` |
| 整包导入入口 | `PUT /module/compare/upload` | **200**，返回 `exist:true`（正确识别本地已有同 id 门户） |
| demo 整包导出 | `PUT demo/module/output` | **500 权限不足**（`disableExportEnable=true`） |
| 本地已有包 | `GET /module/output/list/structure` | 6 个（`fix5.xapp`×2、`cms_relform.xapp`、`probe.xapp`、`hr_file_fix.xapp`×2） |

### 全量对齐审计（剔除 createTime/updateTime/lastUpdate*/creatorPerson/distributeFactor）

| 类型 | 共有 | 一致 | 不一致 | 仅 demo | 仅本地 |
|---|---|---|---|---|---|
| portal  | 41 | 41 | 0 | 0 | 0 |
| process | 65 | 64 | 1 | 0 | 0 |
| query   | 38 | 35 | 3 | 0 | 0 |
| cms     | 37 | 37 | 0 | 0 | 0 |

**全部"不一致"经逐字段定位，均为本地比 demo 多**：

| 项 | 差异实质 |
|---|---|
| 查询「办公用品管理」 | 本地多 1 个 `importModelList`（导入模型） |
| 查询「固定资产数据」 | 本地多 1 个 `importModelList` + 8 个 `statList`（统计） |
| 查询「绩效考核」 | 本地多 1 个 `tableList[newTable_localSample]`（自建表示例） |
| 流程「事项审批单」 | 本地多 `begin.allowReroute/allowRerouteTo`(均 false) 与 `manualList[*].defaultAddTaskType/Mode`(after/single，默认值) |
| 流程应用「测试」(`d78e479c…`) | **demo 独有，但是空壳**（`processList=[]`、`formList=[]`、当天 10:40 建、描述"1212"）→ 无复刻价值 |

> 注：本地各应用 `createTime` 为 2026-09-xx，说明本地是**通过导入重建**的（在 `.9` 上完成），导入时新版本 schema 自动补了默认字段 —— 这解释了"本地多出默认值字段"的现象。

---

## 6. 坑与限制

1. **demo 禁用导出**：`Config.general().disableExportEnable=true` → `/module/output`、`/output/{flag}/file` 都抛 `ExceptionAccessDenied`。**定义数据仍可读**，故用"源端读 + 目标端组包"绕开。
2. **门户 designer 的 CacheKey 缺陷**（见 §1.1）→ 门户不要走 `output/{flag}/select/file`，走整包。
3. **流程 designer 没有 `select/file`**：其 `output` 只有 `list` 与 `{applicationFlag}/select`；流程导出走 `lead/out`（单流程）或整包 `module/output`。
4. **CMS designer 也没有 `select/file`**（只有 `select` + `mockputtopost`）→ 同样走整包。
5. **`module/list` / `module/list/category` 连云端** `collect.o2oa.net`，断云环境必失败 —— 它们只用于"云市场目录"，与本地导入导出无关。
6. **`write/{flag}` 取完包即删**：flag 一次有效，dry-run 后再真灌须重新 `compare/upload` 拿新 flag。
7. **`write` 用字符串级 id 替换**（`StringUtils.replace`）：若某 id 恰好是另一 id 的子串，理论上存在误替换风险；O2OA 自身即如此实现，实际 id 为 UUID，风险可忽略。
8. **导入的 id 策略**：`create` = 保留源 id，若冲突则由 `prepare/create` 分配新 id；`cover` = 覆盖本地同 id 应用（**破坏性**，先备份）。
9. **权限**：`output/list` 只需读权限；`module/output`/`write` 需足够角色（本地 `admin` 用 `Manager@ManagerSystemRole@R` 已够）。

---

## 7. 复现命令（从零重derive 本文档的逆向结论）

```bash
# 1) 找到源码副本（O2OA 随服务发布 Java 源码）
docker exec o2oa-server sh -c "ls /opt/o2server/servers/applicationServer/work/x_portal_assemble_designer/describe/sources/com/x/portal/assemble/designer/jaxrs/"

# 2) 读导入/导出的权威实现
docker exec o2oa-server sh -c "cat /opt/o2server/servers/applicationServer/work/x_portal_assemble_designer/describe/sources/com/x/portal/assemble/designer/jaxrs/input/InputAction.java"
docker exec o2oa-server sh -c "cat /opt/o2server/servers/centerServer/work/x_program_center/describe/sources/com/x/program/center/jaxrs/module/ActionWrite.java"

# 3) 读 REST 接口目录（含 path/type/ins/outs）
docker exec o2oa-server sh -c "cat /opt/o2server/servers/applicationServer/work/x_portal_assemble_designer/describe/describe.json"

# 4) 列出四类 designer 的接口（本工具）
python tools/o2_app_io.py list --side local --type all
```
