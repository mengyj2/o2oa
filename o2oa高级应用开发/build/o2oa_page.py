# -*- coding: utf-8 -*-
"""
O2OA 表单「Page 树」容器模型
========================================

【为什么需要这个模块】

O2OA 表单渲染引擎（o2web/source/x_component_process_Xform/）**不按 JSON 层级递归**，
而是**遍历真实 DOM 树**来挂载组件。源码依据：

  Form.js:
    _getModuleNodes: function (dom, dollarFlag) {
        var moduleNodes = [];
        var subDom = dom.getFirst();          // ← 第一个子 DOM
        while (subDom) {
            var mwftype = subDom.get("MWFtype") || subDom.get("mwftype");
            if (mwftype) {
                ...
                moduleNodes = moduleNodes.concat(this._getModuleNodes(subDom, dollarFlag));
            }
            subDom = subDom.getNext();        // ← 沿兄弟 DOM 走
        }
        return moduleNodes;
    }
    _getDomjson: function (dom) {
        var id = dom.get("id") || dom.get("MWFId");
        return this.json.moduleList[id];      // ← 靠 id 反查 json
    }

  Table.js:
    var rows = this.table.rows;
    for (...) for (...) {
        var td = row.cells[j];
        var json = this.form._getDomjson(td); // ← td 可承载子模块
        ...
    }

结论：
  1. `moduleList` 是 **扁平字典 {id: json}**，只做 id→json 查表，
     **不表达层级**。层级完全由 DOM 决定。
  2. 容器（Div / Table / Table$Td / Tab$Content / Elcontainer）靠
     `MWFtype` + `id` 标记，子模块必须**物理嵌套在容器 DOM 内**。
  3. 因此生成 JSON 时必须构造**正确的嵌套关系**，否则导入后所有控件
     平铺堆叠、版式尽失。

【设计器的 DOM → JSON 双向流程】

  设计器导出：DOM 树 ──getModuleNodes 递归──→ 扁平 moduleList{id:json}
  渲染引擎：  扁平 moduleList ──_getDomjson(id)──→ 按 DOM 树层级挂载

【本模块的解决方案：栈式 open/close 模型】

用法：

    p = Page(FORM_NAME, form_id)
    p.open_div("div_hdr", "表头", styles={...})   # 压栈
    p.label("label_title", "项目基础信息表")
    p.field(field_obj)
    p.close()                                    # 出栈

    p.open_table("tbl_1", cols=[1,1])            # 分栏表格
    p.open_td()                                  # 第 1 列
    p.field(f1); p.field(f2); p.field(f3)
    p.open_td()                                  # 自动关上一格、开第 2 列
    p.field(f4); p.field(f5); p.field(f6)
    p.close()                                    # 关表格

所有元素在 `finish()` 时**先按嵌套树展开为 DFS 序列**，
再从中生成「按 DOM 顺序排列的扁平 moduleList + 层级关系记录」。

注意：由于 moduleList 是字典，Python dict 保序（3.7+），
因此 DFS 顺序 = 逻辑嵌套顺序，与设计器导出结果一致。
"""

from collections import OrderedDict

# --------------------------------------------------------------------------
# 控件模板默认值（对照 x_component_process_FormDesigner/Module/*/template.json）
# --------------------------------------------------------------------------

# 所有控件的公共事件表（设计器 template.json 中 events 段的并集简化版）
_BASE_EVENTS = OrderedDict([
    ("queryLoad", {"code": "", "html": ""}),
    ("postLoad", {"code": "", "html": ""}),
    ("load", {"code": "", "html": ""}),
])

_INPUT_EVENTS = OrderedDict(list(_BASE_EVENTS.items()) + [
    ("click", {"code": "", "html": ""}),
    ("dblclick", {"code": "", "html": ""}),
    ("change", {"code": "", "html": ""}),
    ("keydown", {"code": "", "html": ""}),
    ("keypress", {"code": "", "html": ""}),
    ("keyup", {"code": "", "html": ""}),
    ("mousedown", {"code": "", "html": ""}),
    ("mousemove", {"code": "", "html": ""}),
    ("mouseout", {"code": "", "html": ""}),
    ("mouseover", {"code": "", "html": ""}),
    ("mouseup", {"code": "", "html": ""}),
    ("focus", {"code": "", "html": ""}),
    ("blur", {"code": "", "html": ""}),
])

# 布局容器（非控件、非事件）用的精简事件表
_CONTAINER_EVENTS = OrderedDict(list(_BASE_EVENTS.items()) + [
    ("click", {"code": "", "html": ""}),
    ("dblclick", {"code": "", "html": ""}),
])

# 可作容器的类型（可含子模块）
CONTAINER_TYPES = {
    "Div", "Table", "Table$Td", "Tab", "Tab$Page", "Tab$Content",
    "Elcontainer", "Elcontainer$Container",
}

# MWFType 取值表（渲染引擎据此 requireApp 对应组件）
# 注意：MWFType 是**小写**，且 $ 保留
MWFTYPE = {
    "Div": "div",
    "Table": "table",
    "Table$Td": "table$td",
    "Label": "label",
    "Textfield": "textfield",
    "Textarea": "textarea",
    "Number": "number",
    "Currency": "currency",
    "Calendar": "calendar",
    "Select": "select",
    "Radio": "radio",
    "Checkbox": "checkbox",
    "Combox": "combox",
    "Org": "org",
    "Opinion": "opinion",
    "Attachment": "attachment",
    "Actionbar": "actionbar",
    "Tab": "tab",
    "Tab$Page": "tab$page",
    "Tab$Content": "tab$content",
    "Datagrid": "datagrid",
    "Datagrid$Title": "datagrid$title",
    "Datagrid$Data": "datagrid$data",
    "Datatable": "datatable",
    "Datatemplate": "datatemplate",
    "Elcontainer": "elcontainer",
    "Elcontainer$Container": "elcontainer$container",
    "Subform": "subform",
    "View": "view",
    "Stat": "stat",
    "Html": "html",
    "Button": "button",
    "Image": "image",
}

# 输入类控件（带 label 前缀、支持 section 分节）
_INPUT_TYPES = {
    "Textfield", "Textarea", "Number", "Currency", "Calendar",
    "Select", "Radio", "Checkbox", "Combox", "Org",
}


def _styles(**kw):
    """把 snake_case 关键字转成 O2OA 的 CSS camelCase 字符串值。"""
    out = {}
    for k, v in kw.items():
        parts = k.split("_")
        camel = parts[0] + "".join(w.capitalize() for w in parts[1:])
        out[camel] = v
    return out


class _Node:
    """Page 树节点。"""

    __slots__ = ("json", "children", "parent")

    def __init__(self, json, parent=None):
        self.json = json
        self.children = []
        self.parent = parent


class Page:
    """
    表单 Page 构建器（栈式模型）。

    用法见模块文档字符串。核心是三组方法：
      open_*   压栈（打开一个容器）
      close    出栈
      field/label/raw  追加叶子节点（不改变栈）
    """

    def __init__(self, form_name, form_id, description=""):
        self.form_name = form_name
        self.form_id = form_id
        self.description = description

        self.root = _Node({"id": "form", "type": "form", "MWFType": "form"})
        self._stack = [self.root]
        self._order = []       # DFS 顺序的 json 列表（不含 form 根）
        self._global_seq = 0   # 容器 id 的全局序号
        self._seen_ids = set()  # 已用过的 id，防冲突

    # ======================================================================
    # 栈操作
    # ======================================================================

    @property
    def _cur(self):
        return self._stack[-1]

    def _push(self, node):
        node.parent = self._cur
        self._cur.children.append(node)
        self._stack.append(node)
        return node

    def _pop(self):
        if len(self._stack) <= 1:
            raise RuntimeError("Page 栈已到底，出现多余的 close()")
        return self._stack.pop()

    def close(self, n=1):
        """出栈 n 层。"""
        for _ in range(n):
            self._pop()
        return self

    # ======================================================================
    # 容器：Div
    # ======================================================================

    def open_div(self, did, name, styles=None, css_class="", description=""):
        """
        打开一个 Div 容器（对应设计器左侧「布局容器」）。

        styles 传 dict，如 {"padding": "10px 0"}；
        也可用 _styles(border_bottom="1px solid #ccc") 让本函数转 camelCase。
        """
        node = {
            "id": did,
            "type": "Div",
            "MWFType": "div",
            "name": name,
            "description": description,
            "defaultValue": {"code": "", "html": ""},
            "events": dict(_CONTAINER_EVENTS),
            "properties": {},
            "class": css_class,
            "styles": styles or {},
            "container": "",
        }
        return self._push(_Node(node))

    # ======================================================================
    # 容器：Table（分栏布局）
    # ======================================================================

    def open_table(self, tid, name="", widths=None, styles=None,
                   border="0", cellpadding="8", cellspacing="0",
                   css_class="", description=""):
        """
        打开一个 Table 容器。

        注意：O2OA 的 Table 在 DOM 上是 <table><tr><td>。
        本函数只压入 Table 节点；随后每次 open_td() 会**自动关闭上一个 td**，
        从而在同一行内追加新的 <td>。
        """
        node = {
            "id": tid,
            "type": "Table",
            "MWFType": "table",
            "name": name or tid,
            "description": description,
            "defaultValue": {"code": "", "html": ""},
            "events": dict(_CONTAINER_EVENTS),
            "properties": {},
            "class": css_class,
            "styles": styles or {"width": "100%", "borderCollapse": "collapse"},
            "tableStyles": {},
            "titleTdStyles": {},
            "contentTdStyles": {},
            "layoutTdStyles": {},
            "container": "",
            # 非标准但无害：记录列宽定义，供重新编辑时参考
            "_widths": list(widths or []),
            "_border": border,
            "_cellpadding": cellpadding,
            "_cellspacing": cellspacing,
        }
        self._push(_Node(node))
        self._table_widths = list(widths or [])
        self._td_index = 0
        self._row_index = 0
        return self

    def open_td(self, td_id=None, name="", width=None, colspan=1, rowspan=1,
                styles=None, css_class="", description=""):
        """
        在**当前行**内追加一个单元格。

        自动关闭上一个 td（同一行内平级），因此可以连续调用：

            p.open_table("t", widths=[1,1,1])
            p.open_td(); p.field(a)
            p.open_td(); p.field(b)
            p.open_td(); p.field(c)
            p.close()          # 关表格

        需要换行时先调用 new_row()。
        """
        # 自动关闭上一个 td（若栈顶是 td）
        if self._stack[-1].json.get("type") == "Table$Td":
            self._stack.pop()

        # 栈顶必须是 Table
        if self._stack[-1].json.get("type") != "Table":
            raise RuntimeError("open_td() 只能在 open_table() 之后、或 new_row() 之后调用")

        # 全局唯一序号：跨表格、跨行都不复用，避免 moduleList 键冲突
        self._global_seq += 1
        tid = td_id or "%s_td%d" % (self._stack[-1].json["id"], self._global_seq)
        if tid in self._seen_ids:
            tid = "%s_%d" % (tid, self._global_seq)
        self._seen_ids.add(tid)

        w = width
        if w is None:
            if colspan and colspan > 1:
                # 跨列单元格：宽度铺满
                w = "100%"
            else:
                widths = getattr(self, "_table_widths", [])
                if widths:
                    slot = self._td_index % len(widths)
                    raw = widths[slot]
                    if isinstance(raw, str):
                        w = raw
                    else:
                        tot = sum(x for x in widths if not isinstance(x, str)) or 1
                        w = "%d%%" % int(round(100.0 * raw / tot))
        self._td_index += 1

        # 记住当前行号，供 new_row 判断
        node = {
            "id": tid,
            "type": "Table$Td",
            "MWFType": "table$td",
            "name": name or tid,
            "description": description,
            "events": dict(_CONTAINER_EVENTS),
            "properties": {},
            "class": css_class,
            "styles": dict(styles or {}, **({"width": w} if w else {})),
            "container": "",
            "_row": getattr(self, "_row_index", 0),
        }
        if colspan and colspan != 1:
            node["colspan"] = colspan
        if rowspan and rowspan != 1:
            node["rowspan"] = rowspan
        return self._push(_Node(node))

    def new_row(self):
        """
        结束当前行，后续 open_td() 落入新的一行。

        O2OA 的 Table 在 DOM 上是 <table><tr><td>，
        但设计器 JSON **不显式存储 tr**——tr 由 td 的排列还原：
        连续 td 组成一行，行内 td 数量由 Table 的列数决定。
        实际渲染时，O2OA 按 table 的列数自动折行，
        因此这里只需重置列计数即可。
        """
        if self._stack[-1].json.get("type") == "Table$Td":
            self._stack.pop()
        self._row_index = getattr(self, "_row_index", 0) + 1
        self._td_index = 0
        return self

    # ======================================================================
    # 官方风格：表单分区（Section）
    # ======================================================================

    def open_section(self, sid, title, styles=None, flatten=False):
        """
        打开一个「业务分区」——官方表单的核心视觉单元。

        官方截图（HR 员工档案）中的分区样式：
          ┌─────────────────────────────┐
          │ ▍本单位工作经历              │  ← 左侧竖线 + 浅灰底
          ├─────────────────────────────┤
          │ 字段格 | 值格 | 字段格 | 值格 │
          └─────────────────────────────┘

        本方法压入一个 Div 容器 + 一个分区标题 Label，
        分区内通常再开一个 Table 做「标签格 + 值格」网格。
        调用方负责 close()。

        :param flatten: True 时只压入 Div（分区标题由 field_grid 内部
            以「跨列标题格」形式生成），比 [Div + Label + Table] 少一层，
            更贴近官方的 DOM 深度。False 时保留独立的标题 Label。
        """
        _st = {
            "marginBottom": "14px",
            "border": "1px solid #e5e7eb",
            "borderRadius": "3px",
            "backgroundColor": "#ffffff",
        }
        if styles:
            _st.update(styles)
        self.open_div(sid, title, styles=_st)
        if title and not flatten:
            self.add({
                "id": "%s_head" % sid,
                "type": "Label",
                "MWFType": "label",
                "name": title,
                "description": "",
                "valueType": "text",
                "text": title,
                "script": {"code": "", "html": ""},
                "events": dict(_BASE_EVENTS),
                "properties": {},
                "class": "",
                "styles": {
                    "display": "block",
                    "padding": "8px 12px",
                    "backgroundColor": "#f3f4f6",
                    "borderLeft": "3px solid #2b6cb0",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "color": "#1f2937",
                },
                "container": "",
            })
        return self

    # ======================================================================
    # 官方风格：标签格 + 值格
    # ======================================================================

    # 官方表单里字段名格的统一样式（浅米色底，见 HR 员工档案截图）
    LABEL_TD_STYLE = {
        "backgroundColor": "#faf8f4",
        "border": "1px solid #e5e7eb",
        "padding": "6px 10px",
        "textAlign": "right",
        "width": "110px",
        "fontSize": "13px",
        "color": "#4b5563",
        "whiteSpace": "nowrap",
    }
    # 官方表单里值格的统一样式
    VALUE_TD_STYLE = {
        "border": "1px solid #e5e7eb",
        "padding": "4px 8px",
        "fontSize": "13px",
        "color": "#1f2937",
    }

    def open_label_td(self, td_id=None, width="110px", colspan=1):
        """
        打开一个「字段名格」——浅米色底、右对齐的纯文本格。
        紧接其后应调用 open_value_td() 放对应控件。
        """
        return self.open_td(td_id, width=width, colspan=colspan,
                            styles=dict(self.LABEL_TD_STYLE),
                            css_class="o2-field-label")

    def open_value_td(self, td_id=None, width=None, colspan=1):
        """打开一个「值格」——承载实际输入控件。"""
        return self.open_td(td_id, width=width, colspan=colspan,
                            styles=dict(self.VALUE_TD_STYLE),
                            css_class="o2-field-value")

    def field_row(self, lid, fld, label_width="110px", value_width="220px"):
        """
        便捷方法：一行 = 「字段名格 + 值格」，两个格都开好并放入字段。

            p.field_row("lbl_contract_no", field_contract_no)

        等价于：
            p.open_label_td(); p.label(...)      → 其实标签格内的文字由
                                                    O2OA 按字段 name 自动渲染
            p.open_value_td(); p.field(fld)
        """
        self.open_label_td("%s_ltd" % lid, width=label_width)
        # 标签格里放一个 Label，显示字段中文名（O2OA 不会自动加 label，
        # 必须显式放，否则只有输入框没有名称）
        self.label("%s_lbl" % lid, getattr(fld, "name", lid), styles={
            "fontSize": "13px", "color": "#4b5563",
        })
        self.open_value_td("%s_vtd" % lid, width=value_width)
        self.field(fld)
        return self

    # ======================================================================
    # 叶子节点
    # ======================================================================

    def add(self, module_json):
        """直接追加一个已构造好的模块 JSON（不改变栈）。"""
        self._cur.children.append(_Node(module_json, self._cur))
        return self

    def field(self, fld):
        """
        追加一个表单字段。

        fld 可以是 o2oa_builder.Field 实例，也可以是已构造的 dict。
        若传入 Field，则调用其 to_module() 得到符合设计器模板的 JSON。
        """
        if isinstance(fld, dict):
            self.add(fld)
        else:
            self.add(fld.to_module())
        return self

    def label(self, lid, text, styles=None, css_class="", description=""):
        """追加一个 Label（纯文本展示，无输入框）。"""
        node = {
            "id": lid,
            "type": "Label",
            "MWFType": "label",
            "name": lid,
            "description": description,
            "valueType": "text",
            "text": text,
            "script": {"code": "", "html": ""},
            "events": dict(_BASE_EVENTS),
            "properties": {},
            "class": css_class,
            "styles": styles or {},
            "container": "",
        }
        return self.add(node)

    def hr(self, hid, styles=None):
        """追加一条分隔线（用 Html 组件装一段 <hr/>，最省事且不引入依赖）。"""
        node = {
            "id": hid,
            "type": "Html",
            "MWFType": "html",
            "name": hid,
            "description": "",
            "script": "",
            "events": dict(_BASE_EVENTS),
            "properties": {},
            "class": "",
            "styles": styles or {"padding": "6px 0"},
            "container": "",
            "_html": "<hr style='border:none;border-top:1px solid #e2e8f0;margin:0'/>",
        }
        return self.add(node)

    # ======================================================================
    # 官方风格：表格式字段网格（最常用）
    # ======================================================================

    def field_grid(self, gid, fields, cols=2, label_width="110px",
                   value_width="220px", wide_types=("Textarea", "Attachment",
                                                    "Opinion", "Htmleditor"),
                   section_title=""):
        """
        生成官方风格的「字段名格 + 值格」网格。

            p.field_grid("fg_1", [f_no, f_name, f_type, f_amount], cols=2)

        布局（cols=2）：

            ┌────────┬──────────┬────────┬──────────┐
            │ 合同编号 │ [输入框]  │ 合同名称 │ [输入框]  │
            ├────────┼──────────┼────────┼──────────┤
            │ 合同类型 │ [下拉]    │ 合同金额 │ [输入框]  │
            └────────┴──────────┴────────┴──────────┘

        宽控件（Textarea / Attachment 等）自动独占整行：
        其标签格占 1 格，值格 colspan = cols*2 - 1。

        :param gid: 网格 id 前缀
        :param fields: Field 列表
        :param cols: 每行放几组「标签+值」（1 组 = 2 个 td）
        :param section_title: 非空时在表格首行插入一个跨全列的
            分区标题格（左蓝竖线 + 灰底），此时外层 Div 无需另放 Label，
            可少一层 DOM 嵌套。
        """
        from o2oa_builder import FIELD_TYPE_MAP

        cell_cols = cols * 2      # td 总数
        widths = []
        for _ in range(cols):
            widths.append(label_width)
            widths.append(value_width)

        self.open_table("%s_tbl" % gid, gid, widths=widths,
                        styles={"width": "100%", "borderCollapse": "collapse",
                                "tableLayout": "fixed"})

        # 分区标题行（跨全列）
        if section_title:
            self.open_td("%s_hd" % gid, colspan=cell_cols,
                         styles={
                             "backgroundColor": "#f3f4f6",
                             "border": "1px solid #e5e7eb",
                             "borderLeft": "3px solid #2b6cb0",
                             "padding": "8px 12px",
                             "fontSize": "14px",
                             "fontWeight": "bold",
                             "color": "#1f2937",
                         })
            self.label("%s_hd_lbl" % gid, section_title,
                       styles={"fontSize": "14px", "fontWeight": "bold",
                               "color": "#1f2937"})
            self.new_row()

        # 先整体规划行：宽的独占一行，其余按 cols 分组，最后一组若不满
        # 则把该组的值格 colspan 撑到行尾（不生成空格子，避免 V6 报错）。
        rows = []          # 每行是若干 (field, span_cells) 的列表
        cur = []
        for f in fields:
            ft = getattr(f, "ftype", None)
            mtype = FIELD_TYPE_MAP.get(ft, "")
            wide = mtype in wide_types
            if wide:
                if cur:
                    rows.append(cur)
                    cur = []
                rows.append([(f, cell_cols - 1)])      # 值格跨到行尾
            else:
                cur.append((f, 1))
                if len(cur) == cols:
                    rows.append(cur)
                    cur = []
        if cur:
            # 末行不满：最后一组的值格吃掉剩余格子
            cur[-1] = (cur[-1][0], 1 + (cols - len(cur)) * 2)
            rows.append(cur)

        for ri, row in enumerate(rows):
            if ri or section_title:
                self.new_row()
            for ci, (f, span) in enumerate(row):
                self.open_label_td("%s_%d_%d_l" % (gid, ri, ci), width=label_width)
                self.label("%s_%d_%d_ll" % (gid, ri, ci),
                           getattr(f, "name", ""),
                           styles={"fontSize": "13px", "color": "#4b5563"})
                self.open_value_td("%s_%d_%d_v" % (gid, ri, ci), colspan=span)
                self.field(f)

        self.close()      # 关 Table（Table$Td 已被 new_row/close 处理）
        return self

    # ======================================================================
    # 成品
    # ======================================================================

    def _dfs(self):
        """把嵌套树展开为 DFS 序列（不含 form 根）。"""
        out = []

        def walk(node):
            for ch in node.children:
                out.append(ch.json)
                walk(ch)
        walk(self.root)
        return out

    def build(self):
        """
        产出设计器 JSON。

        返回 {id,name,alias,description,formType,moduleList,style,properties,submit,event}
        其中 moduleList 是**扁平字典**（键=模块 id），顺序为 DFS 顺序。
        """
        modules = self._dfs()

        module_list = OrderedDict()
        for m in modules:
            mid = m.get("id")
            if not mid:
                raise ValueError("存在无 id 的模块：%r" % (m.get("name"),))
            if mid in module_list:
                raise ValueError("模块 id 重复：%s" % mid)
            # 从 moduleList 副本中剔除内部辅助键
            clean = {k: v for k, v in m.items() if not k.startswith("_")}
            module_list[mid] = clean

        return OrderedDict([
            ("id", self.form_id),
            ("name", self.form_name),
            ("alias", self.form_name),
            ("description", self.description),
            ("formType", "process"),
            ("moduleList", module_list),
            ("style", {}),
            ("properties", OrderedDict([
                ("title", self.form_name),
                ("description", self.description),
            ])),
            ("submit", OrderedDict([("isValidate", True), ("confirmType", "none")])),
            ("event", OrderedDict([
                ("queryLoad", {"code": ""}),
                ("afterLoad", {"code": ""}),
                ("beforeSave", {"code": ""}),
                ("validate", {"code": ""}),
                ("beforeSubmit", {"code": ""}),
                ("afterSubmit", {"code": ""}),
            ])),
        ])

    def depth_map(self):
        """
        返回 {模块id: 层级}，用于校验嵌套是否正确。
        form 根为 0，其直接子节点为 1，依此类推。
        """
        out = {}

        def walk(node, d):
            for ch in node.children:
                out[ch.json["id"]] = d
                walk(ch, d + 1)
        walk(self.root, 1)
        return out
