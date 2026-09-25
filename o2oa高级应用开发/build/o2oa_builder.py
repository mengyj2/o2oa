# -*- coding: utf-8 -*-
"""
O2OA 应用包生成器核心库
========================================

【重要 — 已从 O2OA 官方源码验证的 .xapp 格式】

`.xapp` **不是 zip 包**，而是**单个 JSON 文本文件**。

验证依据：
  o2server/x_program_center/src/main/java/com/x/program/center/jaxrs/module/
      ActionCompareUpload.java
        String json = new String(bytes, DefaultCharset.charset);
        WrapModule module = XGsonBuilder.instance().fromJson(json, WrapModule.class);

  o2web/source/x_component_AppCenter/Main.js
        "<input name=\"file\" type=\"file\" accept=\".xapp\"/>"
        formData.append('file', this.file);   // 整文件上传，不解压

因此本模块不再生成 zip / manifest.json，而是生成符合 WrapModule
层级结构的单个 JSON 文件。

结构总览（Java 类名 → JSON 字段）：
  WrapModule
    ├─ name / id / category / icon / description
    ├─ processPlatformList : [WrapProcessPlatform]   ← 流程应用
    ├─ portalList          : [WrapPortal]            ← 门户应用
    ├─ queryList           : [WrapQuery]             ← 数据中心应用
    ├─ cmsList             : [WrapCms]               ← 内容管理应用
    └─ serviceModuleList   : [WrapServiceModule]     ← 服务管理应用

  WrapProcessPlatform（继承 Application）
    ├─ id / name / alias / description / applicationCategory / icon
    ├─ processList         : [WrapProcess]
    ├─ formList            : [WrapForm]              ← 表单，data 是【字符串】
    ├─ applicationDictList : [WrapApplicationDict]   ← 流程平台数据字典
    ├─ scriptList          : [WrapScript]
    └─ fileList            : [WrapFile]

  WrapProcess（继承 Process）
    ├─ id / name / alias / description / application(=应用id) / category
    ├─ begin                       : WrapBegin        ← 单值
    ├─ endList                     : [WrapEnd]
    ├─ manualList                  : [WrapManual]     ← 人工节点
    ├─ choiceList                  : [WrapChoice]
    ├─ routeList                   : [WrapRoute]      ← 路由是独立数组，不是节点内字段
    ├─ splitList / mergeList / parallelList
    ├─ serviceList / invokeList / agentList
    └─ delayList / embedList / cancelList / publishList

  WrapManual（继承 Manual）关键字段
    id / name / alias / description / process / position / extension
    form(=表单id) / unique / opinionGroup / group
    taskIdentityList / taskUnitList / taskGroupList / taskScript / taskScriptText
    readIdentityList / readScript / reviewIdentityList / reviewScript
    allowReroute / allowRetract / allowTransfer(不存在,实为 allowRollback) / allowRollback
    allowGoBack / allowTerminate / allowReset / allowDeleteWork
    allowAddTask / allowRapid / allowAddSplit
    properties : ManualProperties
"""

from collections import OrderedDict
from datetime import datetime
import copy
import json
import os
import uuid


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def short_id():
    """生成 O2OA 风格 32 位无连字符标识。"""
    return uuid.uuid4().hex


def o2_datetime(dt=None):
    """O2OA 通用日期格式 yyyy-MM-dd HH:mm:ss。"""
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def write_json(path, obj):
    """以 UTF-8 无 BOM 写入 JSON，保持中文可读。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def compact_json(obj):
    """紧凑 JSON 字符串（用于 Form.data 内嵌）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# --------------------------------------------------------------------------
# ★ O2OA 的「双层 JSON」存储约定（2026-09-20 血泪教训）
# --------------------------------------------------------------------------
# 有些 Wrap 实体（Form / PortalPage / Widget / CMSForm …）的 data 字段，
# 在库（PP_E_FORM.xdata / PTL_PAGE.xdata …）里存的是 **JSON 文本再被 JSON 转义一次**
# 的结果 —— 即：{  "  j s o n  "  : … }   →   {\"json\":…}
#
# 为什么必须是这种「转义形态」：前端固定走这一条解码链
#     x_component_portal_Portal/PortalPage.js
#         this.page = JSON.decode(MWF.decodeJsonString(json.data.data));
#     o2_core/o2.js
#         o2.decodeJsonString = function (str) {
#             var tmp = "[\"" + str + "\"]";     // ← 直接拼进 JSON 字符串字面量
#             return JSON.decode(tmp)[0];
#         };
# 它把 str **原样**拼进 `["…"]` 里。若 str 是未转义的 JSON 文本 {"json":…，
# 拼出来是 ["{"json":… → 第一个 " 提前闭合字符串 → 抛
#     SyntaxError: Unexpected identifier 'json'
# → this.page = null → openPortal() 静默空转 → **整页白屏，服务端零报错**。
#
# 实证（库内形态普查）：
#     PP_E_FORM   转义 54 / 未转义 53   ← 53 = 我们生成的，全错
#     PTL_PAGE    转义 94 / 未转义 10   ← 10 = 我们生成的，全错
#     反过来，QRY_VIEW / QRY_STAT / QRY_SCH_TABLE 等**不经过 decodeJsonString**
#     的实体，原生存的恰恰是未转义 JSON —— 所以**必须按实体分别对待，不能一刀切**。
def escape_json_string(s):
    """JSON 文本 -> O2OA 存储所需的转义形态（对应前端 o2.encodeJsonString）。"""
    return json.dumps(s, ensure_ascii=False)[1:-1]


def decode_json_string(s):
    """escape_json_string 的逆运算（对应前端 o2.decodeJsonString）。"""
    if not isinstance(s, str) or not s:
        return s or ""
    return json.loads('"' + s + '"')


def is_escaped_json(s):
    """判断某字段是否已是 O2OA 要求的转义形态（转义 JSON 必以 {\\" 开头）。"""
    return isinstance(s, str) and s[:3] == '{\\"'


# --------------------------------------------------------------------------
# 表单字段构造器
# --------------------------------------------------------------------------

# 字段类型 -> O2OA 表单设计器 module type
FIELD_TYPE_MAP = {
    "textfield": "Textfield",
    "number": "Number",
    "currency": "Currency",
    "calendar": "Calendar",
    "textarea": "Textarea",
    "select": "Select",
    "radio": "Radio",
    "checkbox": "Checkbox",
    "combox": "Combox",
    "org": "Org",
    "opinion": "Opinion",
    "attachment": "Attachment",
    "dict": "Select",
    "identity": "Org",
    "hide": "Textfield",
    "label": "Label",
    "div": "Div",
}


# --------------------------------------------------------------------------
# 权威控件模板（对照 x_component_process_FormDesigner/Module/*/template.json）
# 关键：字段名是 styles（复数），不是 style！事件表是 events（字典）。
# --------------------------------------------------------------------------

_EV_BASE = OrderedDict([
    ("queryLoad", {"code": "", "html": ""}),
    ("postLoad", {"code": "", "html": ""}),
    ("load", {"code": "", "html": ""}),
])

_EV_INPUT = OrderedDict(list(_EV_BASE.items()) + [
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

_EV_CALENDAR = OrderedDict(list(_EV_BASE.items()) + [
    ("complete", {"code": "", "html": ""}),
    ("clear", {"code": "", "html": ""}),
    ("show", {"code": "", "html": ""}),
    ("hide", {"code": "", "html": ""}),
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

# 输入类控件公有的「分节显示」属性
_SECTION_DEFAULTS = OrderedDict([
    ("compute", "create"),          # create / show / save
    ("section", "no"),
    ("sectionBy", "person"),
    ("sectionByScript", {"code": "", "html": ""}),
    ("showSectionKey", True),
    ("sectionNodeStyles", {"overflow": "hidden"}),
    ("sectionKeyStyles", {"float": "left"}),
    ("sectionContentStyles", {"float": "left"}),
    ("keyContentSeparator", "\uff1a"),
])

# 需要「分节」属性的类型
_SECTION_TYPES = {
    "Textfield", "Number", "Currency", "Calendar",
    "Select", "Radio", "Checkbox", "Combox",
}


class Field:
    """O2OA 表单字段定义（对照设计器 template.json 生成模块 JSON）。"""

    def __init__(self, fid, name, ftype="textfield", required=False,
                 readonly=False, options=None, code=None, default="",
                 description="", colspan=2, dict_code=None,
                 placeholder="", styles=None):
        self.id = fid
        self.name = name
        self.ftype = ftype
        self.required = required
        self.readonly = readonly
        self.options = options or []
        self.code = code
        self.dict_code = dict_code or code
        self.default = default
        self.description = description
        self.colspan = colspan
        self.placeholder = placeholder
        self.styles = styles or {}

    # ------------------------------------------------------------------
    def _events(self, mtype):
        if mtype == "Calendar":
            return dict(_EV_CALENDAR)
        if mtype in ("Textfield", "Textarea", "Number", "Currency",
                     "Select", "Radio", "Checkbox", "Combox", "Org"):
            return dict(_EV_INPUT)
        return dict(_EV_BASE)

    def to_module(self):
        """
        转换为 O2OA 表单 moduleList 中的一个模块节点。

        严格对齐设计器 template.json 的字段命名：
          styles（复数） / events（字典） / defaultValue（{code,html}）
        """
        mtype = FIELD_TYPE_MAP.get(self.ftype, "Textfield")
        m = OrderedDict([
            ("id", self.id),
            ("name", self.name),
            ("type", mtype),
            # MWFType 是渲染引擎 requireApp 的依据，**必须小写且不能省**，
            # 缺失会导致该组件完全不渲染（参见 Form.js._getModuleNodes）
            ("MWFType", mtype.lower()),
            ("description", self.description),
            ("defaultValue", {"code": "", "html": ""}),
        ])

        # 分节属性（输入类控件才有）
        if mtype in _SECTION_TYPES:
            for k, v in _SECTION_DEFAULTS.items():
                m[k] = v

        # 类型专属属性
        if mtype == "Textfield":
            m["dataType"] = "text"
            m["inputType"] = "text"
        elif mtype == "Textarea":
            m["dataType"] = "text"
            m["rows"] = 4
        elif mtype in ("Number", "Currency"):
            m["dataType"] = "number"
            m["numberType"] = "number"
            m["precision"] = 2
            m["roundType"] = "halfUp"
            m["thousandths"] = mtype == "Currency"
            if mtype == "Currency":
                m["currencySymbol"] = "\u00a5"
                m["currencyPosition"] = "front"
        elif mtype == "Calendar":
            m["range"] = "single"
            m["selectType"] = "day"
            m["format"] = "%Y-%m-%d"
        elif mtype == "Select":
            m["itemType"] = "values"
            m["itemValues"] = [{"value": o, "text": o} for o in self.options]
            m["itemScript"] = {"code": "", "html": ""}
            m["buttonStyle"] = {}
            if self.dict_code and self.ftype == "dict":
                # 字典型下拉：改为字典数据源
                m["itemType"] = "dict"
                m["itemValues"] = []
                m["dictionaryCode"] = self.dict_code
        elif mtype == "Radio":
            m["itemType"] = "values"
            m["itemValues"] = [{"value": o, "text": o} for o in self.options]
            m["itemScript"] = {"code": "", "html": ""}
        elif mtype == "Checkbox":
            m["itemType"] = "values"
            m["itemValues"] = [{"value": o, "text": o} for o in self.options]
            m["itemScript"] = {"code": "", "html": ""}
        elif mtype == "Combox":
            m["itemType"] = "values"
            m["itemValues"] = [{"value": o, "text": o} for o in self.options]
            m["itemScript"] = {"code": "", "html": ""}
        elif mtype == "Org":
            m["orgType"] = "identity" if self.ftype == "identity" else "person"
            m["isMulti"] = False
            m["orgRange"] = "all"
        elif mtype == "Attachment":
            m["maxFileCount"] = 50
            m["fileTypes"] = []
        elif mtype == "Opinion":
            m["opinionGroup"] = ""

        m["events"] = self._events(mtype)
        m["properties"] = {}
        m["class"] = ""
        m["styles"] = dict(self.styles)
        m["container"] = ""

        # 必填 / 只读 / 提示
        if self.required:
            m["isRequired"] = True
        if self.readonly:
            m["isReadonly"] = True
            m["isReadonlyShow"] = True
        if self.placeholder:
            m["placeholder"] = self.placeholder
        return m


class FormBuilder:
    """
    构建 O2OA 表单定义（WrapForm）。

    注意：WrapForm.data 是【字符串】，内容为表单设计器 JSON。
    所以 to_wrap() 返回的对象中 data 字段是被 json.dumps 后的文本。
    """

    def __init__(self, fid, name, description="", fields=None,
                 datagrids=None, application="", category="",
                 page=None, groups=None, cols=2):
        self.id = fid
        self.name = name
        self.description = description
        self.fields = fields or []
        self.datagrids = datagrids or []   # [{id,name,columns:[Field]}]
        self.application = application
        self.category = category
        self.page = page                   # 显式 Page 树（优先）
        self.groups = groups or []         # [(组名, [Field,...])] 自动分组排版
        self.cols = cols                   # 自动排版列数

    # ---- 内部：构造设计器 JSON ----
    def to_design_json(self):
        """
        产出设计器 JSON。

        三条路径，优先级从高到低：
          1. self.page  —— 显式 Page 树（栈式模型构造，最精确）
          2. self.groups —— 分组 + 多列自动排版
          3. self.fields —— 单列平铺（兜底）

        【核心】无论哪条路径，最终都经过 Page 树展开，
        保证 moduleList 的 DFS 顺序与嵌套关系正确。
        """
        from o2oa_page import Page as _Page, _styles

        if self.page is not None:
            design = self.page.build()
        else:
            design = self._auto_page().build()

        # datagrid 作为独立顶层模块追加（O2OA 的 Datagrid 不参与普通容器嵌套）
        if self.datagrids:
            design = self._attach_datagrids(design)
        return design

    # ------------------------------------------------------------------
    @staticmethod
    def _is_full_row(f):
        """
        判断字段是否应独占整行。

        textarea（多行文本）在窄格子里高度会被压扁，
        附件、富文本、数据表格类控件同理，因此给它们整行宽度。
        """
        ft = getattr(f, "ftype", None)
        if ft in ("textarea",):
            return True
        mtype = FIELD_TYPE_MAP.get(ft, "")
        return mtype in ("Textarea", "Attachment", "Htmleditor", "Datatable")

    # ------------------------------------------------------------------
    def _auto_page(self):
        """
        按 groups/cols 自动生成一个带容器嵌套的 Page。

        【官方版式】复刻 O2OA 官方表单（HR 员工档案 / 合同审批表）：
          表头 → 每个业务分区（左侧蓝竖线 + 灰底标题）→
          分区内「字段名格 + 值格」表格式网格 → 附件区 → 意见区 → 操作条
        宽字段（Textarea/附件/富文本）自动独占整行。
        """
        from o2oa_page import Page as _Page

        p = _Page(self.name, self.id, self.description)
        cols = max(1, int(self.cols or 2))

        # ---- 页头：标题（官方表单顶部） ----
        p.open_section("sec_header", self.name, flatten=True)
        p.open_table("tbl_header", self.name, widths=["100%"],
                     styles={"width": "100%", "borderCollapse": "collapse"})
        p.open_td("td_header", colspan=1)
        p.label("lbl_header", self.name, styles={
            "fontSize": "15px", "fontWeight": "bold", "color": "#1a365d",
            "padding": "2px 0",
        })
        p.close(2)
        p.close()

        # ---- 业务分区（分区标题由 field_grid 以跨列标题格生成，少一层 DOM）----
        groups = self.groups or [("", list(self.fields))]
        for gi, (gname, gfields) in enumerate(groups):
            if not gfields:
                continue
            sid = "sec_g%d" % gi
            gtitle = gname or ("\u4fe1\u606f\u533a%d" % (gi + 1))
            p.open_section(sid, gtitle, flatten=True)
            p.field_grid("fg_g%d" % gi, list(gfields), cols=cols,
                         section_title=gtitle)

        # ---- 附件区 ----
        p.open_section("sec_attach", "\u9644\u4ef6", flatten=True)
        p.open_table("tbl_attach", "\u9644\u4ef6", widths=["100%"],
                     styles={"width": "100%", "borderCollapse": "collapse"})
        p.open_td("td_attach", colspan=1)
        p.add({
            "id": "attachment_main", "name": "\u9644\u4ef6", "type": "Attachment",
            "MWFType": "attachment",
            "description": "", "defaultValue": {"code": "", "html": ""},
            "events": {}, "properties": {}, "class": "",
            "styles": {"width": "100%"}, "container": "",
            "fileTypes": [], "maxFileCount": 50,
        })
        p.close(2)
        p.close()

        # ---- 审批意见区 ----
        p.open_section("sec_opinion", "\u5ba1\u6279\u610f\u89c1", flatten=True)
        p.open_table("tbl_opinion", "\u5ba1\u6279\u610f\u89c1", widths=["100%"],
                     styles={"width": "100%", "borderCollapse": "collapse"})
        p.open_td("td_opinion", colspan=1)
        p.add({
            "id": "opinion_main", "name": "\u5ba1\u6279\u610f\u89c1", "type": "Opinion",
            "MWFType": "opinion",
            "description": "", "defaultValue": {"code": "", "html": ""},
            "events": {}, "properties": {}, "class": "",
            "styles": {"width": "100%"}, "container": "",
            "opinionGroup": "",
        })
        p.close(2)
        p.close()

        p.add({
            "id": "actionbar_main", "name": "\u64cd\u4f5c\u6761", "type": "Actionbar",
            "MWFType": "actionbar",
            "description": "", "defaultValue": {"code": "", "html": ""},
            "events": {}, "properties": {}, "class": "",
            "styles": {"paddingTop": "12px"}, "container": "",
        })
        return p

    # ------------------------------------------------------------------
    def _attach_datagrids(self, design):
        """
        把 Datagrid 模块挂到表单内（每个 Datagrid 独占一个分区）。

        【为什么要挂在分区里】
        O2OA 渲染引擎遍历真实 DOM 树，叶子模块必须有容器父级，
        否则会裸挂在表单根下（validate_form_tree 的 V4 会报错）。
        因此这里为每个 Datagrid 生成一个分区：
            Div → Label(分区标题) → Table → Td → Datagrid

        【插入位置】moduleList 是扁平的 DFS 顺序字典，校验器与渲染器
        都按这个顺序还原层级，所以直接在「操作条」之前插入即可。

        Datagrid 的 Title/Data 子模块放在自身 titleList / dataList 中，
        **不进 moduleList**，渲染端由 Datagrid.js 自行处理。
        """
        ml = design["moduleList"]

        # 找到「操作条」的位置，Datagrid 分区插在它之前
        anchor = len(ml)
        for i, k in enumerate(ml.keys()):
            if ml[k].get("type") == "Actionbar":
                anchor = i
                break

        insert = OrderedDict()
        for di, dg in enumerate(self.datagrids):
            dg_id = dg["id"]
            cols = dg["columns"]
            header_row = OrderedDict()
            data_row = OrderedDict()
            for i, col in enumerate(cols):
                if getattr(col, "id", None) == "__idx__":
                    hid = "th_%s_%d" % (dg_id, i)
                    did = "td_%s_%d" % (dg_id, i)
                    header_row[hid] = {
                        "id": hid, "name": col.name, "type": "Datagrid$Title",
                        "MWFType": "datagrid$title", "isIndex": True,
                        "width": "40px", "description": "",
                        "events": {}, "properties": {}, "class": "",
                        "styles": {"textAlign": "center"}, "container": "",
                    }
                    data_row[did] = {
                        "id": did, "name": col.name, "type": "Datagrid$Data",
                        "MWFType": "datagrid$data", "isIndex": True,
                        "description": "", "events": {}, "properties": {},
                        "class": "", "styles": {"textAlign": "center"},
                        "container": "", "propertyName": "",
                    }
                    continue
                hid = "th_%s_%s" % (dg_id, col.id)
                did = "td_%s_%s" % (dg_id, col.id)
                header_row[hid] = {
                    "id": hid, "name": col.name, "type": "Datagrid$Title",
                    "MWFType": "datagrid$title",
                    "width": col.description or "auto", "description": "",
                    "events": {}, "properties": {}, "class": "",
                    "styles": {}, "container": "",
                }
                dm = col.to_module()
                dm["id"] = did
                dm["name"] = col.name
                dm["type"] = "Datagrid$Data"
                dm["MWFType"] = "datagrid$data"
                dm["propertyName"] = col.id
                dm["isRequired"] = bool(getattr(col, "required", False))
                data_row[did] = dm

            ml[dg_id] = OrderedDict([
                ("id", dg_id),
                ("name", dg["name"]),
                ("type", "Datagrid"),
                ("MWFType", "datagrid"),
                ("description", ""),
                ("defaultValue", {"code": "", "html": ""}),
                ("isTotal", dg.get("isTotal", False)),
                ("isIndex", dg.get("isIndex", True)),
                ("titleList", header_row),
                ("dataList", data_row),
                ("events", {}),
                ("properties", {}),
                ("class", ""),
                ("styles", {"marginTop": "6px", "width": "100%"}),
                ("container", ""),
            ])

            # --- 承载分区：Div → Label → Table → Td → Datagrid ---
            gid = "dgg%d" % di
            div_id = "%s_div" % gid
            lbl_id = "%s_lbl" % gid
            tbl_id = "%s_tbl" % gid
            td_id = "%s_td" % gid

            insert[div_id] = {
                "id": div_id, "name": "\u660e\u7ec6\u533a", "type": "Div",
                "MWFType": "div", "description": "",
                "defaultValue": {"code": "", "html": ""},
                "events": {}, "properties": {}, "class": "",
                "styles": {
                    "marginBottom": "14px", "border": "1px solid #e5e7eb",
                },
                "container": "",
            }
            insert[lbl_id] = {
                "id": lbl_id, "name": dg["name"], "type": "Label",
                "MWFType": "label", "description": "",
                "defaultValue": {"code": "", "html": ""}, "text": dg["name"],
                "events": {}, "properties": {}, "class": "",
                "styles": {
                    "display": "block", "padding": "8px 10px",
                    "backgroundColor": "#f3f4f6",
                    "borderLeft": "3px solid #2b6cb0",
                    "fontSize": "13px", "fontWeight": "bold",
                    "color": "#2d3748",
                },
                "container": "",
            }
            insert[tbl_id] = {
                "id": tbl_id, "name": dg["name"], "type": "Table",
                "MWFType": "table", "description": "",
                "defaultValue": {"code": "", "html": ""},
                "events": {}, "properties": {}, "class": "",
                "styles": {"width": "100%", "borderCollapse": "collapse"},
                "tableStyles": {}, "titleTdStyles": {},
                "contentTdStyles": {}, "layoutTdStyles": {},
                "container": "", "_widths": ["100%"],
            }
            insert[td_id] = {
                "id": td_id, "name": dg["name"], "type": "Table$Td",
                "MWFType": "table$td", "description": "",
                "events": {}, "properties": {}, "class": "",
                "styles": {"width": "100%", "padding": "0"},
                "container": "",
            }

        if not insert:
            return design

        # 从 moduleList 中摘出待插节点（它们已在 DFS 末尾追加，需重排）
        for k in insert:
            ml.pop(k, None)

        # 在 anchor 位置重建顺序
        new_ml = OrderedDict()
        for i, (k, v) in enumerate(ml.items()):
            if i == anchor:
                for ik, iv in insert.items():
                    new_ml[ik] = iv
            new_ml[k] = v
        if anchor >= len(ml):
            for ik, iv in insert.items():
                new_ml[ik] = iv
        design["moduleList"] = new_ml
        return design



    # ---- 对外：构造 WrapForm ----
    def to_wrap(self):
        now = o2_datetime()
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.name,
            "description": self.description,
            "category": self.category,
            "application": self.application,
            "lastUpdateTime": now,
            "lastUpdatePerson": "xadmin",
            # ★ data 必须是「转义形态」的 JSON 文本字符串：
            #   前端 FormExplorer/base_work 一律 JSON.decode(MWF.decodeJsonString(data))，
            #   写裸 JSON 会让表单打不开（详见文件头 escape_json_string 说明）。
            "data": escape_json_string(compact_json(self.to_design_json())),
            "mobileData": "",
            "hasMobile": False,
            "properties": {
                "relatedFormList": [],
                "mobileRelatedFormList": [],
                "relatedScriptMap": {},
                "mobileRelatedScriptMap": {},
            },
        }


# --------------------------------------------------------------------------
# 流程构造器
# --------------------------------------------------------------------------

class Activity:
    """
    人工节点（WrapManual / manualList）。

    注意 O2OA 把活动【按类型拆成不同数组】，不是统一 activityList。
    """

    def __init__(self, aid, name, atype="manual",
                 task_script="", task_identity_list=None,
                 form_id="", opinion_group="",
                 allow_go_back=True, allow_rollback=True, allow_terminate=True,
                 allow_reset=True, allow_reroute=True, allow_add_task=True,
                 group="", description=""):
        self.id = aid
        self.name = name
        self.atype = atype     # manual / end / begin / choice / split / merge / parallel / service
        self.task_script = task_script
        self.task_identity_list = task_identity_list or []
        self.form_id = form_id
        self.opinion_group = opinion_group
        self.allow_go_back = allow_go_back
        self.allow_rollback = allow_rollback
        self.allow_terminate = allow_terminate
        self.allow_reset = allow_reset
        self.allow_reroute = allow_reroute
        self.allow_add_task = allow_add_task
        self.group = group
        self.description = description
        self.unique = short_id()

    # 人工节点
    def to_manual(self, process_id, position):
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.name,
            "description": self.description,
            "process": process_id,
            "unique": self.unique,
            "position": position,
            "extension": "",
            "form": self.form_id,
            "group": self.group,
            "opinionGroup": self.opinion_group or self.name,
            "taskIdentityList": self.task_identity_list,
            "taskUnitList": [],
            "taskGroupList": [],
            "taskScript": "",
            "taskScriptText": self.task_script,
            "taskDuty": "",
            # —— 运行时必填（缺失会在办理时 NPE，静态校验看不见）——
            # ManualMode：single/parallel/queue/grab。Manual.toTickets() 首行即
            #   switch (getManualMode().ordinal())  → null 直接 NPE。
            # 语义：single = 多人时任一人办理即通过（或签），符合协会"负责人审核"。
            "manualMode": "single",
            # resetRange: all/topUnit/department
            "resetRange": "all",
            # taskExpireWorkTime：超时工作时间配置，自带元素为空串
            "taskExpireWorkTime": "",
            "readIdentityList": [],
            "readUnitList": [],
            "readGroupList": [],
            "readScript": "",
            "readScriptText": "",
            "reviewIdentityList": [],
            "reviewUnitList": [],
            "reviewGroupList": [],
            "reviewScript": "",
            "reviewScriptText": "",
            "allowReroute": self.allow_reroute,
            "allowRerouteTo": False,
            "allowRetract": False,
            "allowRollback": self.allow_rollback,
            "allowGoBack": self.allow_go_back,
            "allowTerminate": self.allow_terminate,
            "allowReset": self.allow_reset,
            "allowDeleteWork": False,
            "allowAddTask": self.allow_add_task,
            "allowRapid": False,
            "allowAddSplit": False,
            "properties": {
                "allowAddTask": self.allow_add_task,
                "defaultAddTaskType": "parallel",
                "defaultAddTaskMode": "single",
                "processingTaskOnceUnderSamePerson": False,
                "allowGoBack": self.allow_go_back,
                "allowTerminate": self.allow_terminate,
                "taskParticipant": {"type": "creator", "data": None},
            },
            "beforeArriveScript": "",
            "beforeArriveScriptText": "",
            "afterArriveScript": "",
            "afterArriveScriptText": "",
            "beforeExecuteScript": "",
            "beforeExecuteScriptText": "",
            "afterExecuteScript": "",
            "afterExecuteScriptText": "",
            "beforeInquireScript": "",
            "beforeInquireScriptText": "",
            "afterInquireScript": "",
            "afterInquireScriptText": "",
        }

    def to_end(self, process_id, position):
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.name,
            "description": self.description,
            "process": process_id,
            "unique": self.unique,
            "position": position,
            "extension": "",
            "properties": {"memo": "", "expireType": "never"},
            "beforeArriveScript": "",
            "beforeArriveScriptText": "",
            "afterArriveScript": "",
            "afterArriveScriptText": "",
            "beforeExecuteScript": "",
            "beforeExecuteScriptText": "",
            "afterExecuteScript": "",
            "afterExecuteScriptText": "",
        }

    def to_choice(self, process_id, position):
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.name,
            "description": self.description,
            "process": process_id,
            "unique": self.unique,
            "position": position,
            "extension": "",
            # 选择节点是自动网关，不承载表单；但 form 与四个脚本字段必须落库
            # （写空串），否则导入后为 NULL，与"自带元素全非空"的分布不符。
            "form": "",
            "beforeArriveScript": "",
            "beforeArriveScriptText": "",
            "afterArriveScript": "",
            "afterArriveScriptText": "",
            "beforeExecuteScript": "",
            "beforeExecuteScriptText": "",
            "afterExecuteScript": "",
            "afterExecuteScriptText": "",
            "properties": {},
        }


# ==========================================================================
# 自动插入「同人跳过」选择节点
# ==========================================================================
# 背景：协会没有专职部门负责人，由两位分管领导兼任；而秘书长既是
#       「部门负责人」（对其分管的综合管理部 / 行业研究部）又是「终审人」。
#       若流程不做判断，秘书长会为同一个单子连签两次。
#
# 官方口径（O2OA 论坛管理员，forum.o2oa.net/thread-20946）：
#   「您也可以在审批前添加一个选择活动，计算两个节点的处理人是否相同，
#     如果相同就跳过这个节点直接到合并」
#   「选择节点出来的路由上，右侧属性有条件设置，return true 走这条，
#     return false 不走。条件必须互斥，只能一条 return true」
#
# 因此：凡是「申请 → 部门负责人 → …」形态的流程，自动在申请与部门负责人
#       之间插入一个选择节点，按「部门负责人是否与终审人同人」分流。
#       同人 → 免签，直接进入综合管理部；不同人 → 正常送部门负责人。
# ==========================================================================

def _inject_skip_choice(activities, routes):
    """自动在「部门负责人」级之前插入同人跳过选择节点。

    识别依据：人工节点的 taskScriptText 同时含 '部门负责人' 与 'getDuty'
    （即 o2oa_org.SCRIPT_DEPT_MGR）。
    识别不到、或拓扑不是单入单出时，原样返回 —— 不破坏任何现有流程。
    """
    from o2oa_org import ROUTE_NEED_DEPT_HEAD, ROUTE_SKIP_DEPT_HEAD

    dept = None
    for a in activities:
        ts = getattr(a, "task_script", "") or ""
        if getattr(a, "atype", "") == "manual" and "部门负责人" in ts and "getDuty" in ts:
            dept = a
            break
    if dept is None or not routes:
        return activities, routes

    # 多级审批流程里每个节点往往同时有「同意（前向）」和「退回（回向）」两条
    # 出边，因此不能简单要求单入单出。这里按 activities 的排列先后判定方向：
    #   activities 是按业务推进顺序书写的，所以「前向」= 目标节点排序更靠后。
    # 起点（begin_*）不在 activities 里，视作最靠前（pos = -1）。
    idx = {a.id: i for i, a in enumerate(activities)}
    di = idx[dept.id]

    def pos(x):
        return idx.get(x, -1)

    preds = [r for r in routes if r[1] == dept.id and pos(r[0]) < di]
    succs = [r for r in routes if r[0] == dept.id and pos(r[1]) > di]
    if len(preds) != 1 or len(succs) != 1:
        return activities, routes

    pred_from = preds[0][0]
    next_id = succs[0][1]
    choice_id = "choice_skip_%s" % dept.id

    new_acts = []
    for a in activities:
        if a.id == dept.id:
            new_acts.append(Activity(choice_id, "是否需部门负责人审核", "choice"))
        new_acts.append(a)

    new_routes = []
    for r in routes:
        frm, to, rname, rscript = r
        if frm == pred_from and to == dept.id:
            new_routes.append((pred_from, choice_id, "", ""))
            new_routes.append((choice_id, dept.id, "送部门负责人审核",
                               ROUTE_NEED_DEPT_HEAD))
            new_routes.append((choice_id, next_id, "负责人兼终审 · 免签",
                               ROUTE_SKIP_DEPT_HEAD))
        else:
            new_routes.append(r)
    return new_acts, new_routes


class ProcessBuilder:
    """构建 O2OA 流程定义（WrapProcess）。"""

    def __init__(self, pid, name, description="", form_id="",
                 activities=None, routes=None, application="",
                 category="", startable_identity_list=None):
        self.id = pid
        self.name = name
        self.description = description
        self.form_id = form_id
        self.activities = activities or []
        self.routes = routes or []   # [(from_id, to_id, name, script)]
        self.application = application
        self.category = category
        self.startable_identity_list = startable_identity_list or []

    def to_wrap(self):
        now = o2_datetime()
        # 「部门负责人」与终审同人时自动免签（分管领导兼任部门负责人的情形）
        activities, routes = _inject_skip_choice(self.activities, self.routes)

        # 【唯一性修复】O2OA 把流程活动按类型存进【全局】表
        # （PP_E_BEGIN / PP_E_END / PP_E_MANUAL / PP_E_CHOICE …），主键即活动 id。
        # 原逻辑中人工/结束/选择节点使用裸逻辑串（a_end、a_finance、choice_skip_*），
        # 跨流程、跨应用必撞主键，导入报 "Duplicate entry 'a_end' for key PP_E_END.PRIMARY"。
        # 此处统一加「流程 id 前缀」使每个活动 id 全局唯一，并同步改写所有路由 from/to。
        prefix = self.id
        id_map = {a.id: "%s_%s" % (prefix, a.id) for a in activities}
        raw_begin_id = "begin_%s" % self.id[:12]
        id_map[raw_begin_id] = "%s_%s" % (prefix, raw_begin_id)
        for a in activities:
            a.id = id_map[a.id]
        routes = [(id_map.get(f, f), id_map.get(t, t), n, s) for (f, t, n, s) in routes]

        # 布局：起点 -> 人工节点纵向排列 -> 结束
        begin_id = id_map[raw_begin_id]
        begin = {
            "id": begin_id,
            "name": "\u5f00\u59cb",
            "alias": "\u5f00\u59cb",
            "description": "",
            "process": self.id,
            "unique": short_id(),
            "position": "{'x': 100, 'y': 60}",
            "extension": "",
            "form": "",
            "properties": {},
            "beforeArriveScript": "",
            "beforeArriveScriptText": "",
            "afterArriveScript": "",
            "afterArriveScriptText": "",
        }

        manual_list = []
        end_list = []
        choice_list = []
        y = 160
        for a in activities:
            pos = "{'x': 100, 'y': %d}" % y
            y += 90
            if a.atype == "end":
                end_list.append(a.to_end(self.id, pos))
            elif a.atype == "choice":
                choice_list.append(a.to_choice(self.id, pos))
            else:
                # 关键修复：节点未显式绑定表单时，回退到流程级主表单，
                # 否则导入后人工节点 form='' ，办理时无表单可渲染。
                if not a.form_id:
                    a.form_id = self.form_id or ""
                manual_list.append(a.to_manual(self.id, pos))

        if not end_list:
            end_list.append({
                "id": "end_%s" % self.id[:12],
                "name": "\u7ed3\u675f",
                "alias": "\u7ed3\u675f",
                "description": "",
                "process": self.id,
                "unique": short_id(),
                "position": "{'x': 100, 'y': %d}" % y,
                "extension": "",
                "properties": {"memo": "", "expireType": "never"},
                "beforeArriveScript": "",
                "beforeArriveScriptText": "",
                "afterArriveScript": "",
                "afterArriveScriptText": "",
                "beforeExecuteScript": "",
                "beforeExecuteScriptText": "",
                "afterExecuteScript": "",
                "afterExecuteScriptText": "",
            })

        # 路由
        # ==================================================================
        # 【关键·已从 O2OA 源码验证】流程拓扑由两处共同表达，缺一不可：
        #   · Route.activity           = **目标**活动 id
        #   · Manual / Choice.routeList = 本活动的【出口】路由 id 列表
        #   · Begin.route               = 开始活动的【出口】路由 id（单值）
        #
        # 源码依据（x_processplatform_core_entity）：
        #   Route.java
        #     @FieldDescribe("目标活动节点标识符.")
        #     @IdReference({..., Manual.class, Choice.class, End.class, ...})
        #     private String activity;
        #   Manual.java / Choice.java
        #     @FieldDescribe("出口路由,多值.")
        #     @IdReference(Route.class)
        #     private List<String> routeList;
        #   Begin.java
        #     @FieldDescribe("出口路由.")  private String route;
        #     （并 override getRouteList() 由 route 派生）
        #
        # ⚠ 早期版本写的是 "arriveActivity" —— **该字段在 O2OA 中不存在**，
        #   且活动上未写出口路由，导致「源」与「目标」双空、流程无法流转。
        #   本次修正：目标改名 activity + 为每个活动回填出口路由。
        # ==================================================================
        # ------------------------------------------------------------------
        # 【关键·运行态】Route.activityType = **目标活动的类型**，缺它流程跑不动。
        #
        # 源码链路（x_processplatform_service_processing）：
        #   AbstractProcessor.selectRoute()
        #       work.setDestinationActivityType(selectRoute.getActivityType());  ← 唯一来源
        #   Processing.arrive()
        #       switch (work.getDestinationActivityType()) { case manual: ... }   ← 开关值
        #
        # 因此 activityType 为空 → switch(null) 抛 NullPointerException
        #   → "processing arrive failure" → work 永远停在开始节点，
        #     数据库：PP_C_WORK.xdestinationActivityType 为 NULL、PP_C_TASK 无记录。
        #
        # ⚠ 这类缺陷**任何静态校验都看不到**（表单树/DOM/拓扑/路由 id 全对），
        #   只有真正发起一条流程实例才会暴露。属于本项目第 2 个「阻断级」坑。
        # ------------------------------------------------------------------
        atype_of = {begin_id: "begin"}
        for a in activities:
            atype_of[a.id] = getattr(a, "atype", "") or "manual"
        for e in end_list:
            atype_of.setdefault(e["id"], "end")

        out_routes = {}          # 源活动 id -> [出口路由 id]（保序）
        route_list = []
        if routes:
            for i, r in enumerate(routes):
                frm, to, rname, rscript = r
                rid = "route_%d_%s" % (i, short_id()[:10])
                out_routes.setdefault(frm, []).append(rid)
                route_list.append({
                    "id": rid,
                    "name": rname or "",
                    "alias": rname or "",
                    "description": "",
                    "process": self.id,
                    "unique": short_id(),
                    "position": "{'x': 100, 'y': %d}" % (200 + i * 60),
                    "extension": "",
                    "activity": to,
                    "activityType": atype_of.get(to, ""),
                    "script": "",
                    "scriptText": rscript or "",
                    "properties": {"hide": False},
                })
        else:
            # 自动串联：begin -> manual/choice... -> end
            chain = ([begin_id] + [m["id"] for m in manual_list]
                     + [c["id"] for c in choice_list]
                     + [e["id"] for e in end_list])
            for i in range(len(chain) - 1):
                rid = "route_%d_%s" % (i, short_id()[:10])
                out_routes.setdefault(chain[i], []).append(rid)
                route_list.append({
                    "id": rid,
                    "name": "",
                    "alias": "",
                    "description": "",
                    "process": self.id,
                    "unique": short_id(),
                    "position": "{'x': 100, 'y': %d}" % (200 + i * 60),
                    "extension": "",
                    "activity": chain[i + 1],
                    "activityType": atype_of.get(chain[i + 1], ""),
                    "script": "",
                    "scriptText": "",
                    "properties": {"hide": False},
                })

        # —— 补起点边 ——
        # begin_id 是构建时按流程 id 自动生成的，def_*.py 里的 routes 无法引用它，
        # 因此这里自动补一条 begin → 「首个没有入边的活动」的路由。
        # 同样属于早期缺失：没有这条边，流程实例根本不会离开开始节点。
        if not out_routes.get(begin_id):
            targets = {r["activity"] for r in route_list}
            entry = None
            for a in activities:
                if a.id in targets:
                    continue
                if getattr(a, "atype", "") in ("manual", "choice"):
                    entry = a.id
                    break
            if entry is None and manual_list:
                entry = manual_list[0]["id"]
            if entry:
                rid = "route_begin_%s" % short_id()[:10]
                out_routes.setdefault(begin_id, []).append(rid)
                route_list.insert(0, {
                    "id": rid,
                    "name": "\u63d0\u4ea4",
                    "alias": "\u63d0\u4ea4",
                    "description": "",
                    "process": self.id,
                    "unique": short_id(),
                    "position": "{'x': 100, 'y': 120}",
                    "extension": "",
                    "activity": entry,
                    "activityType": atype_of.get(entry, ""),
                    "script": "",
                    "scriptText": "",
                    "properties": {"hide": False},
                })

        # 回填「出口路由」——没有这一步，引擎不知道每条路由从哪个活动出发
        begin["route"] = (out_routes.get(begin_id) or [""])[0]
        for m in manual_list:
            m["routeList"] = out_routes.get(m["id"], [])
        for c in choice_list:
            c["routeList"] = out_routes.get(c["id"], [])

        return {
            "id": self.id,
            "name": self.name,
            "alias": self.name,
            "description": self.description,
            "application": self.application,
            "category": self.category,
            "creatorPerson": "xadmin",
            "lastUpdatePerson": "xadmin",
            "lastUpdateTime": now,
            "controllerList": [],
            "startableIdentityList": self.startable_identity_list,
            "startableUnitList": [],
            "startableGroupList": [],
            "startableRoleList": [],
            "startableTerminal": "all",
            "expireType": "never",
            # 流程级超时 / 流水号配置：自带元素一律有值（7/0/""/arrive/[]），
            # 缺失即落库为 NULL。expireType=never 时 expiresDay 不生效，
            # 但字段仍须落值以保持与设计器一致。
            "expireDay": 7,
            "expireHour": 0,
            "expireWorkTime": "",
            "serialPhase": "arrive",
            "serialTexture": "[]",
            "checkDraft": False,
            "routeNameAsOpinion": True,
            "beforeArriveScript": "",
            "beforeArriveScriptText": "",
            "afterArriveScript": "",
            "afterArriveScriptText": "",
            "beforeExecuteScript": "",
            "beforeExecuteScriptText": "",
            "afterExecuteScript": "",
            "afterExecuteScriptText": "",
            "afterEndScript": "",
            "afterEndScriptText": "",
            # 活动按类型分数组
            "begin": begin,
            "endList": end_list,
            "manualList": manual_list,
            "choiceList": choice_list,
            "routeList": route_list,
            "splitList": [],
            "mergeList": [],
            "parallelList": [],
            "serviceList": [],
            "invokeList": [],
            "agentList": [],
            "delayList": [],
            "embedList": [],
            "cancelList": [],
            "publishList": [],
            "itemAccessList": [],
        }


# --------------------------------------------------------------------------
# 数据字典（流程平台：WrapApplicationDict）
# --------------------------------------------------------------------------

def dictionary(did, name, code, items, description="", application=""):
    """
    构建【流程平台】数据字典（WrapApplicationDict）。
    API 路径：流程应用 -> 数据字典，脚本中 this.data.dict('code').get(...)
    """
    now = o2_datetime()
    norm = []
    for it in items:
        if isinstance(it, (list, tuple)):
            norm.append({"value": it[0], "text": it[1]})
        else:
            norm.append(it)
    return {
        "id": did,
        "name": name,
        "alias": name,
        "description": description or name,
        "application": application,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "data": norm,
        "properties": {},
    }


# --------------------------------------------------------------------------
# 数据中心：视图 / 统计 / 自建表 / 查询配置 / 导入模型
# --------------------------------------------------------------------------

def view(vid, name, description="", query="", source="process",
         process_list=None, table_list=None, columns=None,
         filter_script="", order_by="", is_export=True, cache=True,
         cache_access=True):
    """
    构建 View（WrapView 继承 View）。
      字段名以 View.java 为准：
        name / alias / description / query(所属查询id) / enableCache /
        layout / data / code / display / type / cacheAccess

    ⚠ cacheAccess 在 View.java 中是 **Boolean**（是否允许缓存访问），
      早期误写为数字 300，导致 query 应用导入报
      "Expected BOOLEAN but was NUMBER at path $.viewList[0].cacheAccess"。
    """
    process_list = process_list or []
    table_list = table_list or []
    columns = columns or []
    col_list = []
    for i, c in enumerate(columns):
        title, path = c[0], c[1]
        width = c[2] if len(c) > 2 else "120px"
        col_list.append({
            "id": "col_%d" % i,
            "title": title,
            "path": path,
            "name": path,
            "width": width,
            "isSort": True,
            "sortType": "asc",
            "hidden": False,
            "isTitle": i == 0,
        })
    now = o2_datetime()
    # 视图设计 JSON（存入实体 data 字段，前端 Viewer 与服务端执行器都读它）。
    # 结构照抄官方设计器模板 view.json：where/selectList/orderList/group/...
    # 此前缺 data → QRY_VIEW.xdata 为 NULL → 视图执行 500、门户嵌入空白。
    col_entries = []
    for i, c in enumerate(columns):
        title, path = c[0], c[1]
        col_entries.append({
            "column": "col_%d" % i,
            "displayName": title,
            "path": path,
            "id": "%s_col%d" % (vid, i),
            "hideColumn": False,
            "orderType": "original",
        })
    view_data = {
        "where": {"accessible": True, "scope": "all"},
        "noDataText": "\u672a\u627e\u5230\u6570\u636e",
        "selectList": col_entries,
        "filterList": [],
        "customFilterList": [],
        "orderList": [],
        "group": {},
        "columnList": [],
        "calculate": {},
        "afterGridScriptText": "",
        "afterGroupGridScriptText": "",
        "afterCalculateGridScriptText": "",
        "exportGrid": True,
        "isExpand": "no",
        "isSequence": False,
        "events": {},
        "viewStyleType": "list",
        "viewStyles": {},
        "actionbarList": [],
        "pagingList": [],
        "actionbarHidden": False,
        "select": "none",
        "selectBoxShow": False,
        "allowSelectAll": False,
        "firstTdHidden": True,
        "pagingbarHidden": False,
        "searchbarHidden": False,
        "languageType": "default",
    }
    return {
        "id": vid,
        "name": name,
        "alias": name,
        "description": description,
        "query": query,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "enableCache": cache,
        # ★ data 必须是【字符串】（xdata 是 mediumtext）。
        #   服务端 ActionCover$Wi 反序列化要求 viewList[].data 为 STRING，
        #   传对象 → "Expected STRING but was BEGIN_OBJECT" → 整个 query 应用导入 500。
        #   落库后即 QRY_VIEW.xdata，原生视图设计 JSON 正是此形态。
        "data": json.dumps(view_data, ensure_ascii=False),
        "type": source,
        "display": True,
        "cacheAccess": bool(cache_access),
        "processList": process_list,
        "cmsCategoryList": [],
        "tableList": table_list,
        "filterScript": filter_script,
        "orderBy": order_by,
        "columnList": col_list,
        "columns": col_list,
        "afterGridScriptText": "",
        "afterGroupGridScriptText": "",
        "afterCalculateGridScriptText": "",
        "code": "",
        "properties": {
            "isExport": is_export,
            "isSearch": True,
            "isPage": True,
            "pageSize": 20,
            "showOperateBar": True,
            "operateBarWidth": "120px",
        },
    }


def table(tid, name, fields, description="", query=""):
    """
    构建自建表（WrapTable 继承 Table）。
    fields: [(name, type, title, length), ...]
    type: 白名单 string / stringLob / boolean / double / long / integer /
          date / time / dateTime（别名 number/text/datetime 会被自动归一化）

    ⚠ 关键 1（表名必须是合法 Java 标识符）：
      O2OA 建表时会用 Table.name 生成动态实体类
      （com.x.query.dynamic.entity.<name>），**中文名会导致建表 500**：
          {"message":"com.x.query.dynamic.entity.项目主表"}
      O2OA 自带表 name 均为英文（note_person / newTable …），物理表为
      QRY_DYN_<NAME大写>。因此这里从表 id 中提取英文 slug 作为 name
      （id 形如 t1001001-project-master-table-00000001），中文名放 alias。

    ⚠ 关键 2（字段定义格式，经 O2OA 自带自建表反查验证）：
      Table.data 是 **String**（mediumtext），内容形如
          {"fieldList":[{"name":"xxx","description":"标题","type":"string"}]}
      —— 每个字段只认 name / description / type 三个键；
      早期误把 fieldList 作为【对象数组】直接挂在包装对象上（并附带
      id/columnName/title/length/isNull/isPrimary 等无关键），被 Jackson
      静默丢弃 → 落库 xdata='{}' → 无法建表。

    ⚠ 关键 3（字段类型白名单，2026-09-20 经反编译 DynamicEntity 确认）：
      com.x.base.core.entity.dynamic.DynamicEntity 内部按类型字符串分发，
      合法取值 **仅** 以下几种：
          string, stringLob, stringMap, stringList,
          boolean, booleanList,
          double, doubleList,
          long, longList,
          integer, integerList,
          date, time, dateTime
      **其余类型一律被静默忽略，字段直接丢失**（不报错、不提示）。
      历史误用映射表（→ 曾丢失字段共 96 个）：
          number   → double      （金额类；O2OA 无 number 类型）
          text     → stringLob   （长文本）
          datetime → dateTime    （注意大小写）
          QQ       → string      （误写，侥幸被当 string 处理）
      丢失表现：build/dispatch 返回 200、jar 正常产出，但物理表里没有该列，
      后续所有引用该列的 SQL 语句报 Unknown column。
    """

    # ---- 字段类型规范化（白名单外一律归一化，防止再次丢字段）----
    TYPE_ALIAS = {
        "number": "double",
        "float": "double",
        "decimal": "double",
        "int": "integer",
        "bigint": "long",
        "text": "stringLob",
        "clob": "stringLob",
        "longtext": "stringLob",
        "datetime": "dateTime",
        "timestamp": "dateTime",
        "qq": "string",
        "bool": "boolean",
        "varchar": "string",
    }
    VALID = {"string", "stringLob", "stringMap", "stringList", "boolean",
             "booleanList", "double", "doubleList", "long", "longList",
             "integer", "integerList", "date", "time", "dateTime"}

    def _norm_type(t):
        t = str(t or "string").strip()
        low = t.lower()
        if low in TYPE_ALIAS:
            return TYPE_ALIAS[low]
        if t in VALID:
            return t
        if low in VALID:
            # 大小写纠正（dateTime）
            return {"datetime": "dateTime", "datetimem": "dateTime"}.get(low, low)
        return "string"      # 兜底：未知类型按字符串存，绝不丢字段

    def _slug(t):
        """从表 id 中取英文标识符，须为合法 Java 标识符（**不能以数字开头**）。
        t1001001-project-master-table-00000001 → project_master_table
        """
        parts = []
        for p in str(t).split("-"):
            # 跳过空白、纯数字段（t1001001 / 00000001 等）
            if not p or p[0].isdigit() or not any(c.isalpha() for c in p):
                continue
            # 去掉内嵌的前导字母+数字前缀（如 t1001001 已在上面跳过，这里兜底）
            parts.append(p)
        s = "_".join(parts).strip("_")
        s = "".join(ch for ch in s if ch.isalnum() or ch == "_")
        if not s or s[0].isdigit():
            s = "tbl_" + s
        return s

    flist = []
    for f in fields:
        fname, ftype = f[0], f[1]
        # ⚠ 必须跳过 id：O2OA 的 DynamicEntity 基类已自带 id 主键，
        #   若 fieldList 再声明 id，动态类编译会直接失败：
        #     error: variable id is already defined in class ...（line 98）
        #   表现为 build/dispatch 返回 200 但 buildSuccess 不置位、jar 不产出。
        if str(fname).lower() == "id":
            continue
        ftitle = f[2] if len(f) > 2 else fname
        flist.append({
            "name": fname,
            "description": ftitle,
            "type": _norm_type(ftype),
        })
    now = o2_datetime()
    tbl_name = _slug(tid)
    # data / draftData 必须是同一份结构 JSON 字符串：
    #   建表三连（status/draft → status/build → execute）的第二、三步读取 draftData，
    #   若为空会报「实体类: ...Table , 字段: draftData 值无效.」。
    data_json = json.dumps({"fieldList": flist}, ensure_ascii=False)
    return {
        "id": tid,
        "name": tbl_name,
        "alias": name,
        "description": description or name,
        "query": query,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "data": data_json,
        "draftData": data_json,
        "status": "draft",
        "display": True,
        "properties": {},
    }


def stat(sid, name, view_id, category_path, value_path, description="",
         category_title="\u5206\u7c7b", value_title="\u5408\u8ba1", query=""):
    """构建统计（WrapStat 继承 Stat）。"""
    now = o2_datetime()
    return {
        "id": sid,
        "name": name,
        "alias": name,
        "description": description or name,
        "query": query,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "viewId": view_id,
        "categoryPath": category_path,
        "valuePath": value_path,
        "categoryTitle": category_title,
        "valueTitle": value_title,
        "chartType": "all",
        "properties": {
            "isCategory": True,
            "isTotal": False,
            "orderType": "none",
            "chartTypes": ["pie", "column", "line", "bar"],
        },
    }


def statement(stmt_id, name, sql, description="", query="", query_type="sql",
              table="", entity_category="dynamic", count_method="ignore",
              format=None):
    """构建查询配置（WrapStatement 继承 Statement）。

    ⚠ 字段类型（以 Statement.java 为准，导入报错验证）：
      · statement / sql : String（语句文本）
      · data            : String —— 早期误写为数组 []，导入报
                          "Expected STRING but was BEGIN_ARRAY at path
                           $.statementList[0].data"。

    ⚠ **format 是执行分支的唯一依据**（2026-09-20 反编译 Executor/ExecuteTargetBuilder 确认）：
      Executor.executeData():
        format in (sql, sqlScript) -> executeDataSql(runtime, target, **false**)
                                       ⚠ 不重写表名 → SQL 必须直接写物理表名
        SQL 同时含 " JOIN " 与 " ON " -> executeDataSql(runtime, target, true)
                                        （本分支只对 format 非 sql 的语句生效）
        否则 -> executeDataJpql() → jsqlparser 按 JPQL 解析
      历史缺陷：把纯 SQL 的语句 format 标成 'jpql'，导致
        1) 走 JPQL 分支解析 Select 失败
        2) 抛 com.x.query.core.express.statement.ExceptionDmlNotAllowed
           ("statement not allowed.")
      因此 query_type 默认 'sql'，format 跟随之。

    ⚠ SQL 文本硬性要求（format=sql 时）：
      · 表名必须写**物理表名** QRY_DYN_<NAME大写>，不能写中文别名或 slug
        （format=sql 分支不调用 joinSql 做替换）
      · 业务字段必须带 x 前缀（O2OA 所有列均为 x<field>）
    """
    fmt = format or query_type
    now = o2_datetime()
    return {
        "id": stmt_id,
        "name": name,
        "alias": name,
        "description": description or name,
        "query": query,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "statement": sql,
        "sql": sql,
        "queryType": query_type,
        "format": fmt,
        "countMethod": count_method,
        "entityCategory": entity_category,
        "table": table,
        "data": "",
        "countData": "",
        "properties": {},
    }


def importer(imp_id, name, table_id, columns, description="", query=""):
    """构建导入模型（WrapImportModel）。"""
    col_list = []
    for i, c in enumerate(columns):
        title, path = c[0], c[1]
        ftype = c[2] if len(c) > 2 else "string"
        is_org = c[3] if len(c) > 3 else False
        col_list.append({
            "id": "imp_col_%d" % i,
            "title": title,
            "fieldPath": path,
            "fieldType": ftype,
            "isOrg": is_org,
            "isNull": True,
            "validate": True,
        })
    now = o2_datetime()
    return {
        "id": imp_id,
        "name": name,
        "alias": name,
        "description": description or name,
        "query": query,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "targetType": "table",
        "tableId": table_id,
        "columnList": col_list,
        "columns": col_list,
        "calculateList": [],
        "validate": False,
        "properties": {},
    }


# --------------------------------------------------------------------------
# 顶层装配：WrapModule
# --------------------------------------------------------------------------

def process_platform(app_id, name, description="", icon="",
                     category="", processes=None, forms=None,
                     dicts=None, scripts=None, files=None):
    """构建 WrapProcessPlatform。"""
    now = o2_datetime()
    return {
        "id": app_id,
        "name": name,
        "alias": name,
        "description": description,
        "applicationCategory": category,
        "icon": icon,
        "iconHue": "",
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "controllerList": [],
        "availableIdentityList": [],
        "availableUnitList": [],
        "availableGroupList": [],
        "properties": {
            "defaultForm": "",
            "maintenanceIdentity": "",
            "maintainerList": [],
        },
        "processList": processes or [],
        "formList": forms or [],
        "applicationDictList": dicts or [],
        "scriptList": scripts or [],
        "fileList": files or [],
    }


def query_application(app_id, name, description="", icon="",
                      category="", views=None, stats=None,
                      tables=None, statements=None, importers=None):
    """构建 WrapQuery（数据中心应用）。"""
    now = o2_datetime()
    return {
        "id": app_id,
        "name": name,
        "alias": name,
        "description": description,
        "queryCategory": category,
        "icon": icon,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "viewList": views or [],
        "statList": stats or [],
        "tableList": tables or [],
        "statementList": statements or [],
        "importModelList": importers or [],
    }


def service_module(sid, name, description="", dicts=None,
                   agents=None, invokes=None, scripts=None):
    """
    构建 WrapServiceModule（服务管理应用）。
    注意：服务管理应用用于承载【全局数据字典 dictList】。
    """
    now = o2_datetime()
    return {
        "id": sid,
        "name": name,
        "alias": name,
        "description": description,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "dictList": dicts or [],
        "agentList": agents or [],
        "invokeList": invokes or [],
        "scriptList": scripts or [],
    }


def wrap_module(name, category="", description="", icon="",
                process_platform_list=None, portal_list=None,
                query_list=None, cms_list=None, service_module_list=None):
    """构建顶层 WrapModule —— 这就是 .xapp 文件的全部内容。"""
    return {
        "name": name,
        "id": short_id(),
        "category": category,
        "icon": icon,
        "description": description,
        "downloadCount": 0,
        "processPlatformList": process_platform_list or [],
        "portalList": portal_list or [],
        "queryList": query_list or [],
        "cmsList": cms_list or [],
        "serviceModuleList": service_module_list or [],
    }


# --------------------------------------------------------------------------
# 门户应用：Portal / Page（WrapPortal / WrapPage）
# --------------------------------------------------------------------------
# 字段来源（O2OA 官方源码，逐字段核对）：
#   x_portal_core_entity/.../portal/core/entity/Portal.java
#     id / name / alias / description / availableIdentityList /
#     availableUnitList / portalCategory / icon / firstPage /
#     controllerList / creatorPerson / lastUpdateTime /
#     lastUpdatePerson / pcClient / mobileClient
#   x_portal_core_entity/.../portal/core/entity/Page.java
#     id / name / alias / description / portal / data(String,10M) /
#     mobileData(String) / hasMobile(Boolean)
#   x_portal_core_entity/.../portal/core/entity/wrap/WrapPortal.java
#     + pageList / scriptList / fileList / widgetList
#
# 【关键】Page.data 是**字符串**（长度上限 10M），内容是门户页面的
# HTML 片段（门户渲染器直接注入 iframe），不是 JSON 对象。
# --------------------------------------------------------------------------

def portal_page(pid, name, portal_id, html, description="",
                alias="", has_mobile=False, mobile_html=""):
    """构建 WrapPage。html 为门户页面的 HTML 源码（此处传入的是门户页定义 JSON 文本）。

    ★ data 必须转义：PortalPage.js 固定 JSON.decode(MWF.decodeJsonString(data))，
      写裸 JSON → SyntaxError → 整页白屏（详见 escape_json_string 说明）。
    """
    return {
        "id": pid,
        "name": name,
        "alias": alias or name,
        "description": description or name,
        "portal": portal_id,
        "data": escape_json_string(html),
        "mobileData": escape_json_string(mobile_html) if mobile_html else "",
        "hasMobile": has_mobile,
    }


def portal(portal_id, name, category="", description="", icon="",
           first_page_id="", pages=None, scripts=None, files=None,
           widgets=None):
    """构建 WrapPortal。firstPage 指向默认打开的 Page id。"""
    now = o2_datetime()
    return {
        "id": portal_id,
        "name": name,
        "alias": name,
        "description": description or name,
        "portalCategory": category,
        "icon": icon,
        "firstPage": first_page_id,
        "creatorPerson": "xadmin",
        "lastUpdatePerson": "xadmin",
        "lastUpdateTime": now,
        "controllerList": [],
        "availableIdentityList": [],
        "availableUnitList": [],
        "pcClient": True,
        "mobileClient": False,
        "pageList": pages or [],
        "scriptList": scripts or [],
        "fileList": files or [],
        "widgetList": widgets or [],
    }
