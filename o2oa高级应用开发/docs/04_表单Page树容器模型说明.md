# O2OA 表单 Page 树容器模型（技术说明）

> 本文解释 O2OA 表单的渲染机制，以及为什么必须用「树形容器模型」生成表单 JSON。
> 这是决定表单导入后是否**有版式**的关键。
> 编制日期：2026-09-19（2026-09-20 修订 V9 深度口径）
>
> **当前规模**：六个应用共 **53** 个表单，全部采用本文的栈式容器模型生成，
> 经 V1~V10 + DOM 重建双校验，**0 错误 0 警告**。

---

## 一、问题现象

早期版本生成的 26 个表单导入 O2OA 后，出现如下症状：

- 所有字段**纵向平铺堆叠**，没有任何分组、分栏
- 表单看起来像一张无限拉长的清单，无法阅读
- 但**导入过程不报任何错误**，校验也通不过任何异常提示

这类问题最难排查的地方在于：**它是静默失效的**。JSON 语法完全正确，
O2OA 也照单全收，问题只出现在最终渲染效果上。

---

## 二、根因：渲染引擎遍历的是 DOM 树，不是 JSON 层级

O2OA 表单渲染引擎位于 `o2web/source/x_component_process_Xform/`。
其工作方式与一般想象不同——**它不按 JSON 的嵌套结构递归**，
而是**遍历真实 DOM 树**来挂载组件。

### 2.1 关键源码：`Form.js`

```javascript
_getModuleNodes: function (dom, dollarFlag) {
    var moduleNodes = [];
    var subDom = dom.getFirst();           // ← 取第一个子 DOM 节点
    while (subDom) {
        var mwftype = subDom.get("MWFtype") || subDom.get("mwftype");
        if (mwftype) {
            var type = mwftype;
            if (type.indexOf("$") === -1 || dollarFlag === true) {
                moduleNodes.push(subDom);
            }
            if (mwftype !== "datagrid" && mwftype !== "datatable" &&
                mwftype !== "subSource" && mwftype !== "tab$Content" &&
                mwftype !== "datatemplate") {
                // ↓ 递归进入子 DOM
                moduleNodes = moduleNodes.concat(this._getModuleNodes(subDom, dollarFlag));
            }
        } else {
            moduleNodes = moduleNodes.concat(this._getModuleNodes(subDom, dollarFlag));
        }
        subDom = subDom.getNext();          // ← 沿兄弟 DOM 节点走
    }
    return moduleNodes;
},

_getDomjson: function (dom) {
    var mwfType = dom.get("MWFtype") || dom.get("mwftype");
    switch (mwfType) {
        case "form":
            return this.json;
        case "":
            return null;
        default:
            var id = dom.get("id");
            if (!id) id = dom.get("MWFId");
            if (id) {
                return this.json.moduleList[id];   // ← 靠 id 反查 JSON
            } else {
                return null;
            }
    }
}
```

三个要点：

1. **`dom.getFirst()` + `subDom.getNext()`** —— 遍历是 DOM 层面的，走「子 → 兄弟」
2. **`dom.get("MWFtype")`** —— 靠 `MWFtype` 属性识别这是一个 O2OA 组件
3. **`dom.get("id")` → `json.moduleList[id]`** —— **id 是 DOM 与 JSON 之间唯一的纽带**

### 2.2 关键源码：`Table.js`

表格单元格也会承载子模块：

```javascript
_afterLoaded: function(){
    if (!this.table) this.table = this.node.getElement("table");
    var rows = this.table.rows;
    for (var i=0; i<rows.length; i++){
        var row = rows[i];
        for (var j=0; j<row.cells.length; j++){
            var td = row.cells[j];
            var json = this.form._getDomjson(td);   // ← td 也能承载模块
            if (json){
                var module = this.form._loadModule(json, td, ...);
                this.form.modules.push(module);
            }
        }
    }
}
```

### 2.3 结论

| 事实 | 说明 |
|---|---|
| `moduleList` 是**扁平字典** | 键=模块 id，值=模块 JSON。**它不表达层级** |
| 层级**完全由 DOM 决定** | `<div>` 包住的才是子节点 |
| `MWFType` 决定组件类型 | 渲染引擎据此 `requireApp` 加载对应 JS |
| `id` 是唯一纽带 | DOM 元素靠 id 反查 moduleList |

**因此，如果生成的 JSON 里容器是空的、字段全平铺在顶层，
O2OA 就会照实渲染成「一堆没有分组和分栏的裸控件」。**

---

## 三、设计器是怎么做的

设计器（`x_component_process_FormDesigner/`）的导出逻辑与渲染端**互为逆操作**：

```javascript
// Module/Form.js
getModuleNodes: function (dom, ignoreMultipleModule) {
    var moduleNodes = [];
    var subDom = dom.getFirst();
    while (subDom) {
        var mwftype = subDom.get("MWFtype") || subDom.get("mwftype");
        if (mwftype) {
            ...
            moduleNodes = moduleNodes.concat(this.getModuleNodes(subDom));
        }
        subDom = subDom.getNext();
    }
    return moduleNodes;
},

load: function(json, node, parent){
    this.json = json;
    this.node = node;
    this.node.store("module", this);
    this._loadTreeNode(parent);
    if (!this.json.id){
        var id = this._getNewId(...);
        this.json.id = id;
    }
    if (!this.form.json.moduleList[this.json.id]){
        this.form.json.moduleList[this.json.id] = this.json;   // ← 扁平入表
    }
    this.parseModules();     // ← 递归处理子 DOM
    this.json.moduleName = this.moduleName;
}
```

**双向流程**：

```
设计：  DOM 树  ──getModuleNodes 递归──→  扁平 moduleList{id: json}
渲染：  扁平 moduleList  ──_getDomjson(id)──→  按 DOM 树层级挂载
```

`load()` 里有一句 `_setNodeProperty`（在 `$Container.js`）：
容器节点会同时登记进三个列表——`moduleList`、`moduleNodeList`、`moduleContainerNodeList`。
这进一步说明**容器与普通模块在结构上是区别对待的**。

---

## 四、控件模板的权威字段名

从 `x_component_process_FormDesigner/Module/*/template.json` 可直接读到每个控件的标准字段集。

**以 Textfield 为例（节选）**：

```json
{
    "id": "",
    "name": "",
    "type": "Textfield",
    "description": "",
    "dataType": "text",
    "defaultValue": { "code": "", "html": "" },
    "compute": "create",
    "section": "no",
    "sectionBy": "person",
    "sectionByScript": { "code": "", "html": "" },
    "events": {
        "queryLoad": { "code": "", "html": "" },
        "postLoad": { "code": "", "html": "" },
        "load": { "code": "", "html": "" },
        "click": { "code": "", "html": "" },
        "change": { "code": "", "html": "" },
        "...": {}
    },
    "inputType": "text",
    "properties": {},
    "class": "",
    "styles": {},
    "container": "",
    "showSectionKey": true,
    "sectionNodeStyles": { "overflow": "hidden" },
    "sectionKeyStyles": { "float": "left" },
    "sectionContentStyles": { "float": "left" },
    "keyContentSeparator": "："
}
```

### 4.1 两个高频踩坑点

**坑一：是 `styles`（复数），不是 `style`。**

模板里统一用 `styles`。写成单数 `style` 会导致样式完全不生效——
而且**不报错**，只是界面素面朝天。

**坑二：`events` 是嵌套字典，不是数组。**

```json
"events": {
    "load": { "code": "", "html": "" },
    "click": { "code": "", "html": "" }
}
```

每个事件本身又是一个 `{code, html}` 对象。`code` 是脚本内容，`html` 是脚本的 HTML 展示形式。

### 4.2 各控件补充字段

| 控件 | 特有字段 |
|---|---|
| `Textfield` | `dataType`、`inputType` |
| `Textarea` | `dataType`、`rows` |
| `Number` | `dataType`、`numberType`、`precision`、`roundType` |
| `Currency` | 同上 + `currencySymbol`、`currencyPosition`、`thousandths` |
| `Calendar` | `range`、`selectType`、`format`（如 `%Y-%m-%d`） |
| `Select` | `itemType`、`itemValues`、`itemScript`、`buttonStyle`；字典型另有 `dictionaryCode` |
| `Radio` / `Checkbox` / `Combox` | `itemType`、`itemValues`、`itemScript` |
| `Org` | `orgType`、`isMulti`、`orgRange` |
| `Attachment` | `maxFileCount`、`fileTypes` |
| `Div` | 无特有字段（纯容器） |
| `Table` | `tableStyles`、`titleTdStyles`、`contentTdStyles`、`layoutTdStyles` |
| `Label` | `valueType`、`text`、`script` |

### 4.3 输入类控件的「分节」属性

`Textfield` / `Number` / `Currency` / `Calendar` / `Select` / `Radio` / `Checkbox` / `Combox`
这八类控件带一组「分节」属性：

```json
"compute": "create",           // create / show / save
"section": "no",               // 是否分节显示
"sectionBy": "person",
"sectionByScript": {"code":"","html":""},
"showSectionKey": true,
"sectionNodeStyles": {"overflow": "hidden"},
"sectionKeyStyles": {"float": "left"},
"sectionContentStyles": {"float": "left"},
"keyContentSeparator": "："
```

`sectionNodeStyles` / `sectionKeyStyles` / `sectionContentStyles` 这三个是**浮层样式**，
用来在只读态折叠显示。不填不影响功能，但填全更规范。

---

## 五、解决方案：栈式 open/close 模型

在 `build/o2oa_page.py` 中实现了 `Page` 类，用**显式的栈操作**构造嵌套树。

### 5.1 基本用法

```python
from o2oa_page import Page

p = Page("项目基础信息表", "f1001001-...")

# 打开一个 Div（压栈）
p.open_div("div_title", "表单标题区", styles={
    "padding": "12px 16px",
    "backgroundColor": "#f7fafc",
    "borderLeft": "4px solid #2b6cb0",
})
p.label("label_title", "项目基础信息表")
p.close()                      # 出栈，关闭 Div

# 分栏表格
p.open_table("tbl_1", "基本信息", widths=[1, 1],
             styles={"width": "100%", "borderCollapse": "collapse"})
p.open_td(); p.field(f_project_no)      # 第 1 行第 1 格
p.open_td(); p.field(f_project_name)    # 第 1 行第 2 格（自动关上一格）
p.new_row()                             # 换行
p.open_td(colspan=2); p.field(f_goal)   # 第 2 行整行
p.close(2)                     # 关 Table + 关外层 Div

design = p.build()             # 产出设计器 JSON
```

### 5.2 栈语义

| 操作 | 效果 |
|---|---|
| `open_div(id, name, styles=...)` | 压入一个 Div 容器 |
| `open_table(id, name, widths=[...])` | 压入一个 Table 容器 |
| `open_td(colspan=..., rowspan=...)` | **自动关闭上一个 td**，然后在当前行追加新单元格 |
| `new_row()` | 结束当前行，下一个 `open_td()` 落入新行 |
| `close(n=1)` | 出栈 n 层 |
| `field(fld)` | 在当前栈顶容器内追加一个字段（不改变栈） |
| `label(id, text)` | 追加一个纯文本标签 |
| `hr(id)` | 追加一条分隔线 |
| `build()` | 把嵌套树展开为 DFS 顺序的扁平 `moduleList` |

### 5.3 关键实现：DFS 展开

栈只用来**记录构造过程**，最终产出时一次性展开为扁平字典：

```python
def _dfs(self):
    out = []
    def walk(node):
        for ch in node.children:
            out.append(ch.json)
            walk(ch)
    walk(self.root)
    return out

def build(self):
    modules = self._dfs()
    module_list = OrderedDict()
    for m in modules:
        module_list[m["id"]] = m          # 保持 DFS 顺序
    return OrderedDict([
        ("id", self.form_id),
        ("name", self.form_name),
        ...
        ("moduleList", module_list),
    ])
```

因为 Python 3.7+ 的 `dict` 保序，**输出顺序即 DFS 顺序**，
与设计器导出的结果一致。

### 5.4 为什么这样能还原 DOM

`moduleList` 的 DFS 顺序 + 类型规则，足以唯一还原 DOM 树：

```
DFS 序列：Div → Table → Table$Td → 字段A → Table$Td → 字段B → Div → 字段C
还原规则：
  Div      → 开 <div>
  Table    → 开 <table>
  Table$Td → 若上一个未闭合项是 td，先关它；再开 <td>
  字段     → 插入当前 td 内
  Div      → 先关 td/table，再开新 <div>
```

这套规则与 `Form.js._getModuleNodes` 的遍历顺序严格互补，
因此能被 O2OA 正确渲染。

---

## 六、自动排版策略

`FormBuilder` 提供两条路径：

### 6.1 显式 Page（最精确）

```python
FormBuilder(fid, name, description="", page=my_page)
```

完全控制结构，适合需要精细版式的表单。

### 6.2 分组自动排版（默认）

```python
FormBuilder(fid, name, description="",
            groups=[("基本信息", [...]), ("预算信息", [...])],
            cols=2)
```

自动生成如下结构：

```
Div[表单标题区]
    └─ Label
Div[基本信息]                       ← 每组一个 Div
    ├─ Label（组标题）
    └─ Table
        ├─ Table$Td → 字段  ├─ Table$Td → 字段     ← cols=2，一行两格
        ├─ Table$Td → 字段  ├─ Table$Td → 字段
        └─ Table$Td(colspan=2) → Textarea          ← 宽字段独占整行
Div[附件区] → Attachment
Div[审批意见区] → Opinion
Actionbar
```

### 6.3 宽字段自动整行

以下类型自动获得 `colspan=cols`，独占整行：

- `Textarea`（多行文本，窄格里高度会被压扁）
- `Attachment`（附件）
- `Htmleditor`（富文本）
- `Datatable`（数据表格）

判定逻辑在 `FormBuilder._is_full_row()`。

---

## 七、校验机制

新增两道独立校验，缺一不可。

### 7.1 `validate_form_tree.py` —— 静态结构校验

| 编号 | 校验项 |
|---|---|
| V1 | 模块 id 唯一，且键与 `id` 字段一致 |
| V2 | 每个模块有 `type` 和 `MWFType` |
| V3 | **容器必须有子节点**（空容器 = 排版失效） |
| V4 | **每个字段的父链上必须有容器**（裸字段会直接挂在表单根下） |
| V5 | Table 至少有一个 `Table$Td` 子节点 |
| V6 | 每个 `Table$Td` 至少含一个字段 |
| V7 | 用 `styles`（复数）而非 `style` |
| V8 | 字段必须有 `events` 字典 |
| V9 | 嵌套深度不超过 14 层（只计 `Div`/`Table`/`Datagrid`，**`Table$Td` 不计入**） |
| V10 | `moduleList` 不为空 |

> **V9 的深度口径必须澄清**：`Table$Td` 是网格单元、不是嵌套层级，计入会让深度虚高。
> 按官方版式，任意表单的正常深度都是 **2~3 层**：
> `form > Div(分区) > Table > Table$Td > Label/Field`。
> 早期版本的校验器曾把「员工档案表」的 10 个**平级**分区算成 21 层而误报 ——
> 根因是推算父子关系时，进入新 `Div` 没有弹掉**上一个分区残留的 `Table`**。
> 修复后深度归位，53 个表单全部 0 警告。
>
> 另需注意两个易踩边界：
> - **只弹上一个分区的 `Div`/`Table`，不能弹刚入栈的当前 `Div` 自身** ——
>   它的 `Table`/`Td` 子节点紧随其后，弹了会让子节点失去父级，
>   瞬间产生上千处 V3「空容器」误报（实测踩过 1703 处）。
> - **`Table$Td` 必须入栈** —— `Label`/`Field` 的直接父级就是 td，
>   叶子靠它认父；不入栈会导致 V6「单元格内无字段」大面积误报。

### 7.2 `validate_dom_rebuild.py` —— DOM 重建模拟

复刻 `Form.js._getModuleNodes` 的遍历逻辑，把 `moduleList` 还原成 DOM 树，
检查三项：

| 编号 | 校验项 |
|---|---|
| R1 | 还原后每个字段都落在容器内（非裸挂） |
| R2 | 遍历顺序与 `moduleList` 顺序一致（渲染顺序正确） |
| R3 | 所有模块都被遍历到（无孤儿模块） |

**R2 与 R3 是关键**——它们验证的是「O2OA 拿到这份 JSON 后
能否按预期还原出界面」，比单纯的 JSON 结构检查更接近真实渲染行为。

### 7.3 修复前后的对比

| 阶段 | `validate_form_tree` | `validate_dom_rebuild` |
|---|---|---|
| 修复前（扁平结构） | 446 错误 / 412 警告 | 大量孤儿模块与裸挂字段 |
| 修复后（Page 树） | **0 错误 / 0 警告** | **0 问题** |

---

## 八、踩坑记录

### 坑一：`style` 与 `styles`

设计器模板统一用 `styles`。写成 `style` 不报错，样式静默失效。
**校验项 V7 已覆盖。**

### 坑二：漏掉 `MWFType`

`MWFType` 是渲染引擎 `requireApp` 的依据。漏掉后该组件**完全不渲染**——
不是显示为空，而是根本不出现。**校验项 V2 已覆盖。**

### 坑三：容器 id 冲突

`open_td()` 自动生成 id 时，若按「表 id + 行内序号」命名，
跨表格会产生重复（如两张表都有 `xxx_td0`）。
`moduleList` 是字典，**后写覆盖先写，直接丢模块**。

解决：改用**全局递增序号** `_global_seq`。

### 坑四：`new_row()` 的语义

O2OA 的设计器 JSON **不显式存储 `<tr>`**。行的边界由 td 的排列与
Table 的列数隐式决定。因此 `new_row()` 只是重置列计数，
不产生新的 JSON 节点。

### 坑五：控件模板字段不能想当然

例如 `Calendar` 的日期格式字段是 `format`，值是 `%Y-%m-%d`（**类 strftime 语法**），
不是 `datePattern`；`Select` 的静态选项字段是 `itemValues`
（元素形如 `{"value":..., "text":...}`），不是 `optionValue`。

**结论：所有字段名必须以 `Module/*/template.json` 为准，不能凭印象写。**

---

## 九、重新生成

改动 `o2oa_page.py` 或 `FormBuilder` 后，按顺序执行：

```bash
cd build
python pack.py                  # 1. 打包
python validate_xapp.py         # 2. WrapModule 结构校验
python validate_form_tree.py    # 3. 表单嵌套校验（必跑）
python validate_dom_rebuild.py  # 4. DOM 重建模拟（必跑）
```

**第 3、4 步不能省。** 表单嵌套问题是静默失效的，
只有这两道校验能在打包阶段拦住它，避免导入后才发现版式全乱。
