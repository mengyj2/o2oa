# -*- coding: utf-8 -*-
"""
应用二：合同管理应用（对齐 O2OA 官方「合同管理」应用市场版本）
================================================================

【官方结构参考】
来源：https://www.o2oa.net/market/app-77482a3d-1164-483b-9fa3-5cdbf91e8306.html
配图：res.o2oa.net/pic/1656385113222.png（合同档案导入）
      res.o2oa.net/pic/1656385113266.png（合同档案列表 + 工具栏按钮组）
      res.o2oa.net/pic/1656385113280.png（签约方档案导入）
      res.o2oa.net/pic/1656385113300.jpg（合同管理门户首页）

官方左侧导航树（截图实读）：
    合同管理首页
    ▼ 档案管理
        发起合同审批流程
        合同档案
        合同补录
        合同档案导入
    ▼ 过程管理
        信息变更
        状态变更
    ▼ 收款管理
        收款计划编制
        收款计划变更
        合同收款
        开票申请
    ▼ 付款管理
        付款计划编制
        付款计划变更
        合同付款
        收票记录

官方列表页工具栏（截图 1656385113266 实读）：
    导出Excel | 合同补录 | 发起信息变更 | 发起状态变更 | 编辑 | 删除 |
    发起收款计划编制 | 发起收款计划变更 | 合同收款 | 开票申请 |
    发起付款计划编制 | 发起付款计划变更 | 合同付款 | 收票记录
    → 搜索栏：输入关键字搜索视图 + [高级搜索]
    → 分页：第一页 · 上一页 · (1) · 下一页 · 最后一页

官方门户首页（截图 1656385113300 实读）：
    左侧：合同管理 | 合同管理首页 / 档案管理 / 过程管理(07) / 收款管理(08) / 付款管理
    右侧上：待办事项(12) | 已办事项(6)  ← 待办列表卡片
    右侧下：按状态统计合同数量（饼图）| 按状态统计合同金额（柱图）
            「更多 >>」+ 图表切换按钮（饼状图 / 行列转换）

官方合同状态口径：履行中 / 已终止 / 已解除 / 已中止
（本应用采用「两者结合」：官方口径为业务终态，另保留流程中间态）
草拟 → 审批中 → 已生效 → 履行中 → 已完成 / 已终止 / 已解除 / 已中止

【数据联系】
合同通过 project_no 与项目管理应用关联；
付款/收款向财务管理应用推送；
签约方档案独立成表，供合同引用；
合同归档后向档案管理应用推送档案主表。
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
)
from o2oa_page import Page

APP_NAME = "\u5408\u540c\u7ba1\u7406\u5e94\u7528"
APP_ID = "a2002000-contract-app-0000000000000001"
APP_ID_QUERY = "a2002001-contract-dataapp-00000000000001"

# ==========================================================================
# 公共处理人脚本
# ==========================================================================

from o2oa_org import *  # noqa: F401,F403

# 表单数据派生的处理人（非组织架构，保留在应用内）
SCRIPT_PROJECT_MGR = "return this.data.project_manager;"

# 合同状态（官方口径 + 流程中间态）
CONTRACT_STATUS_DRAFT = "\u8349\u62df"
CONTRACT_STATUS_APPROVING = "\u5ba1\u6279\u4e2d"
CONTRACT_STATUS_EFFECTIVE = "\u5df2\u751f\u6548"
CONTRACT_STATUS_PERFORMING = "\u5c65\u884c\u4e2d"
CONTRACT_STATUS_DONE = "\u5df2\u5b8c\u6210"
CONTRACT_STATUS_TERMINATED = "\u5df2\u7ec8\u6b62"
CONTRACT_STATUS_RELEASED = "\u5df2\u89e3\u9664"
CONTRACT_STATUS_SUSPENDED = "\u5df2\u4e2d\u6b62"


# ==========================================================================
# 通用构件：Datagrid / 分区 / 附件区 / 意见区 / 操作条
# ==========================================================================

def datagrid(dg_id, dg_name, columns, is_total=False):
    """
    构造 Datagrid 模块 JSON。

    Datagrid 的 Title/Data 子模块放在自身的 titleList / dataList 字段中，
    **不进入 moduleList**，渲染端由 Datagrid.js 自行处理。
    """
    header_row = {}
    data_row = {}
    for i, col in enumerate(columns):
        cid = col["id"]
        if cid == "__idx__":
            hid, did = "th_%s_%d" % (dg_id, i), "td_%s_%d" % (dg_id, i)
            header_row[hid] = {
                "id": hid, "name": col["name"], "type": "Datagrid$Title",
                "MWFType": "datagrid$title", "isIndex": True,
                "width": "40px", "description": "",
                "events": {}, "properties": {}, "class": "",
                "styles": {"textAlign": "center"}, "container": "",
            }
            data_row[did] = {
                "id": did, "name": col["name"], "type": "Datagrid$Data",
                "MWFType": "datagrid$data", "isIndex": True,
                "description": "", "events": {}, "properties": {}, "class": "",
                "styles": {"textAlign": "center"}, "container": "",
                "propertyName": "",
            }
            continue
        hid, did = "th_%s_%s" % (dg_id, cid), "td_%s_%s" % (dg_id, cid)
        header_row[hid] = {
            "id": hid, "name": col["name"], "type": "Datagrid$Title",
            "MWFType": "datagrid$title",
            "width": col.get("width", "auto"), "description": "",
            "events": {}, "properties": {}, "class": "",
            "styles": {}, "container": "",
        }
        mtype = col.get("mtype", "Textfield")
        dm = {
            "id": did, "name": col["name"], "type": "Datagrid$Data",
            "MWFType": "datagrid$data",
            "description": "", "defaultValue": {"code": "", "html": ""},
            "events": {}, "properties": {}, "class": "", "styles": {},
            "container": "", "propertyName": cid,
            "isRequired": col.get("required", False),
        }
        if mtype == "Number":
            dm.update({"dataType": "number", "numberType": "number",
                       "precision": 2, "roundType": "halfUp"})
        elif mtype == "Currency":
            dm.update({"dataType": "number", "numberType": "number",
                       "precision": 2, "roundType": "halfUp",
                       "thousandths": True, "currencySymbol": "\u00a5",
                       "currencyPosition": "front"})
        elif mtype == "Calendar":
            dm.update({"range": "single", "selectType": "day",
                       "format": "%Y-%m-%d"})
        elif mtype == "Textarea":
            dm.update({"dataType": "text", "rows": 3})
        elif mtype == "Textfield":
            dm.update({"dataType": "text", "inputType": "text"})
        data_row[did] = dm

    return {
        "id": dg_id, "name": dg_name, "type": "Datagrid", "MWFType": "datagrid",
        "description": "", "defaultValue": {"code": "", "html": ""},
        "isTotal": is_total, "isIndex": True,
        "titleList": header_row, "dataList": data_row,
        "events": {}, "properties": {}, "class": "",
        "styles": {"width": "100%", "marginTop": "6px"},
        "container": "",
    }


def grid_block(p, gid, dg):
    """
    在分区内放入一个 Datagrid。

    分区已经是一个 Div，这里只再套「Table → Table$Td → Datagrid」，
    与官方「付款计划明细」的 DOM 深度一致
    （form > Div > Table > Table$Td > Datagrid = 4 层）。
    调用方需先调用 open_section()。
    """
    p.open_table("%s_tbl" % gid, gid, widths=["100%"],
                 styles={"width": "100%", "borderCollapse": "collapse"})
    p.open_td("%s_td" % gid, colspan=1)
    p.add(dg)
    p.close(2)      # 关 td + 关 table
    p.close()       # 关 section
    return p


def attach_block(p, aid, title):
    """通用附件区（官方表单底部）。"""
    p.open_section("%s_sec" % aid, title)
    p.open_table("%s_tbl" % aid, title, widths=["100%"],
                 styles={"width": "100%", "borderCollapse": "collapse"})
    p.open_td("%s_td" % aid, colspan=1)
    p.add({
        "id": aid, "name": title, "type": "Attachment",
        "MWFType": "attachment", "description": "",
        "defaultValue": {"code": "", "html": ""},
        "events": {}, "properties": {}, "class": "",
        "styles": {"width": "100%"}, "container": "",
        "fileTypes": [], "maxFileCount": 50,
    })
    p.close(2)
    p.close()
    return p


def opinion_block(p, oid, title="\u5ba1\u6279\u610f\u89c1"):
    p.open_section("%s_sec" % oid, title)
    p.open_table("%s_tbl" % oid, title, widths=["100%"],
                 styles={"width": "100%", "borderCollapse": "collapse"})
    p.open_td("%s_td" % oid, colspan=1)
    p.add({
        "id": oid, "name": title, "type": "Opinion", "MWFType": "opinion",
        "description": "", "defaultValue": {"code": "", "html": ""},
        "events": {}, "properties": {}, "class": "",
        "styles": {"width": "100%"}, "container": "",
        "opinionGroup": "",
    })
    p.close(2)
    p.close()
    return p


def actionbar(aid):
    return {
        "id": aid, "name": "\u64cd\u4f5c\u6761", "type": "Actionbar",
        "MWFType": "actionbar", "description": "",
        "defaultValue": {"code": "", "html": ""},
        "events": {}, "properties": {}, "class": "",
        "styles": {"paddingTop": "10px"}, "container": "",
    }


# ==========================================================================
# 表单 1：合同审批表（官方「发起合同审批流程」）
# ==========================================================================

FORM_CONTRACT_ID = "f2002001-contract-main-form-00000000001"
PROC_CONTRACT_ID = "p2002001-contract-approve-000000000001"

F_NO = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield",
             required=True, readonly=True,
             description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210")
F_NAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", required=True)
F_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                  required=True, description="\u4e0e\u9879\u76ee\u7ba1\u7406\u5e94\u7528\u8054\u52a8")
F_PROJECT_NAME = Field("project_name", "\u5173\u8054\u9879\u76ee\u540d\u79f0",
                       "textfield", readonly=True)
F_CTYPE = Field("contract_type", "\u5408\u540c\u7c7b\u578b", "dict",
                code="contractType", required=True)
F_CSTATUS = Field("contract_status", "\u5408\u540c\u72b6\u6001", "dict",
                  code="contractStatus", readonly=True, default=CONTRACT_STATUS_DRAFT)
F_PARTY_A = Field("party_a", "\u7532\u65b9\uff08\u672c\u5355\u4f4d\uff09", "textfield",
                  required=True)
F_PARTY_B = Field("party_b", "\u4e59\u65b9\uff08\u7b7e\u7ea6\u5355\u4f4d\uff09", "textfield",
                  required=True, description="\u5f15\u81ea\u7b7e\u7ea6\u65b9\u6863\u6848")
F_PARTY_B_CODE = Field("party_b_code", "\u4e59\u65b9\u7f16\u7801", "textfield", readonly=True)
F_SIGN_DATE = Field("sign_date", "\u7b7e\u8ba2\u65e5\u671f", "calendar")
F_EFFECT_DATE = Field("effect_date", "\u751f\u6548\u65e5\u671f", "calendar")
F_EXPIRE_DATE = Field("expire_date", "\u5230\u671f\u65e5\u671f", "calendar")
F_AMOUNT = Field("contract_amount", "\u5408\u540c\u91d1\u989d\uff08\u5143\uff09",
                 "currency", required=True)
F_TAX_RATE = Field("tax_rate", "\u7a0e\u7387\uff08%\uff09", "number")
F_CURRENCY = Field("currency", "\u5e01\u79cd", "dict", code="currencyUnit",
                   default="CNY")
F_OUR_MGR = Field("our_manager", "\u6211\u65b9\u8d1f\u8d23\u4eba", "org")
F_BIZ_DEPT = Field("biz_dept", "\u7ecf\u529e\u90e8\u95e8", "org")
F_PAY_TERMS = Field("pay_terms", "\u4ed8\u6b3e\u6761\u6b3e", "textarea", required=True)
F_CONTENT = Field("contract_content", "\u5408\u540c\u4e3b\u8981\u5185\u5bb9",
                  "textarea", required=True)
F_PERFORM = Field("performance_terms", "\u5c65\u7ea6\u4e49\u52a1", "textarea")
F_BREACH = Field("breach_terms", "\u8fdd\u7ea6\u8d23\u4efb", "textarea")
F_REMARK = Field("remark", "\u5907\u6ce8", "textarea")

DG_PAYPLAN = datagrid("dg_payplan", "\u4ed8\u6b3e\u8ba1\u5212\u660e\u7ec6", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "pay_stage", "name": "\u4ed8\u6b3e\u9636\u6bb5", "width": "140px"},
    {"id": "pay_ratio", "name": "\u4ed8\u6b3e\u6bd4\u4f8b\uff08%\uff09",
     "mtype": "Number", "width": "110px"},
    {"id": "pay_amount", "name": "\u4ed8\u6b3e\u91d1\u989d\uff08\u5143\uff09",
     "mtype": "Currency", "width": "130px"},
    {"id": "plan_pay_date", "name": "\u8ba1\u5212\u4ed8\u6b3e\u65e5\u671f",
     "mtype": "Calendar", "width": "120px"},
    {"id": "pay_condition", "name": "\u4ed8\u6b3e\u6761\u4ef6", "width": "180px"},
], is_total=True)


def build_form_contract():
    """合同审批表 —— 官方「字段名格 + 值格」表格式 6 分区结构。"""
    p = Page("\u5408\u540c\u5ba1\u6279\u8868", FORM_CONTRACT_ID,
             "\u5408\u540c\u8349\u62df\u3001\u4f1a\u7b7e\u4e0e\u5ba1\u6279")

    p.open_section("sec_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_basic", [F_NO, F_NAME, F_PROJECT, F_PROJECT_NAME,
                              F_CTYPE, F_CSTATUS, F_AMOUNT, F_CURRENCY,
                              F_TAX_RATE, F_OUR_MGR], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_party", "\u7b7e\u7ea6\u65b9\u4fe1\u606f", flatten=True)
    p.field_grid("fg_party", [F_PARTY_A, F_PARTY_B, F_PARTY_B_CODE,
                              F_BIZ_DEPT], cols=2, section_title="\u7b7e\u7ea6\u65b9\u4fe1\u606f")
    p.close()

    p.open_section("sec_term", "\u5408\u540c\u671f\u9650", flatten=True)
    p.field_grid("fg_term", [F_SIGN_DATE, F_EFFECT_DATE, F_EXPIRE_DATE], cols=2, section_title="\u5408\u540c\u671f\u9650")
    p.close()

    p.open_section("sec_terms", "\u6761\u6b3e\u7ea6\u5b9a", flatten=True)
    p.field_grid("fg_terms", [F_PAY_TERMS, F_CONTENT, F_PERFORM, F_BREACH],
                 cols=1, section_title="\u6761\u6b3e\u7ea6\u5b9a")
    p.close()

    p.open_section("sec_payplan", "\u4ed8\u6b3e\u8ba1\u5212\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_payplan", DG_PAYPLAN)

    p.open_section("sec_other", "\u5176\u4ed6", flatten=True)
    p.field_grid("fg_other", [F_REMARK], cols=1, section_title="\u5176\u4ed6")
    p.close()

    attach_block(p, "att_contract", "\u5408\u540c\u9644\u4ef6\u53ca\u626b\u63cf\u4ef6")
    p.add(actionbar("actionbar_contract"))
    return FormBuilder(FORM_CONTRACT_ID, "\u5408\u540c\u5ba1\u6279\u8868",
                       "\u5408\u540c\u8349\u62df\u3001\u4f1a\u7b7e\u4e0e\u5ba1\u6279",
                       page=p)


FORM_CONTRACT = build_form_contract()


# ==========================================================================
# 表单 2：合同补录表（官方「合同补录」）
# ==========================================================================

FORM_CONTRACT_SUPPLEMENT_ID = "f2002002-contract-supplement-form-000001"

FS_NO = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
FS_NAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", required=True)
FS_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield")
FS_CTYPE = Field("contract_type", "\u5408\u540c\u7c7b\u578b", "dict", code="contractType")
FS_PARTY_A = Field("party_a", "\u7532\u65b9", "textfield")
FS_PARTY_B = Field("party_b", "\u4e59\u65b9", "textfield")
FS_AMOUNT = Field("contract_amount", "\u5408\u540c\u91d1\u989d\uff08\u5143\uff09", "currency")
FS_PAID = Field("paid_amount", "\u5df2\u4ed8\u91d1\u989d\uff08\u5143\uff09", "currency")
FS_SIGN = Field("sign_date", "\u7b7e\u8ba2\u65e5\u671f", "calendar")
FS_EXPIRE = Field("expire_date", "\u5230\u671f\u65e5\u671f", "calendar")
FS_STATUS = Field("contract_status", "\u5408\u540c\u72b6\u6001", "dict",
                  code="contractStatus", default=CONTRACT_STATUS_PERFORMING)
FS_ARCHIVE = Field("archive_no", "\u5f52\u6863\u6863\u6848\u53f7", "textfield")
FS_SOURCE = Field("source_type", "\u6570\u636e\u6765\u6e90", "select",
                  options=["\u5386\u53f2\u53f0\u8d26\u5bfc\u5165", "\u7ebf\u4e0b\u8865\u5f55",
                           "\u7cfb\u7edf\u5bfc\u5165"])
FS_REMARK = Field("remark", "\u8865\u5f55\u8bf4\u660e", "textarea")


def build_form_supplement():
    p = Page("\u5408\u540c\u8865\u5f55\u8868", FORM_CONTRACT_SUPPLEMENT_ID,
             "\u5386\u53f2\u5408\u540c\u53f0\u8d26\u8865\u5f55\u4e0e\u5bfc\u5165")
    p.open_section("sec_s_basic", "\u5408\u540c\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_s_basic", [FS_NO, FS_NAME, FS_PROJECT, FS_CTYPE,
                                FS_PARTY_A, FS_PARTY_B, FS_AMOUNT, FS_PAID,
                                FS_SIGN, FS_EXPIRE], cols=2, section_title="\u5408\u540c\u57fa\u672c\u4fe1\u606f")
    p.close()
    p.open_section("sec_s_meta", "\u53f0\u8d26\u5c5e\u6027", flatten=True)
    p.field_grid("fg_s_meta", [FS_STATUS, FS_ARCHIVE, FS_SOURCE, FS_REMARK],
                 cols=2, section_title="\u53f0\u8d26\u5c5e\u6027")
    p.close()
    attach_block(p, "att_supplement", "\u5408\u540c\u626b\u63cf\u4ef6")
    p.add(actionbar("actionbar_supplement"))
    return FormBuilder(FORM_CONTRACT_SUPPLEMENT_ID, "\u5408\u540c\u8865\u5f55\u8868",
                       "\u5386\u53f2\u5408\u540c\u53f0\u8d26\u8865\u5f55\u4e0e\u5bfc\u5165",
                       page=p)


FORM_CONTRACT_SUPPLEMENT = build_form_supplement()


# ==========================================================================
# 表单 3：合同信息变更表（官方「信息变更」）
# ==========================================================================

FORM_CONTRACT_CHANGE_ID = "f2002003-contract-change-form-00000001"

FC_NO = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
FC_NAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
FC_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
FC_TYPE = Field("change_type", "\u53d8\u66f4\u7c7b\u578b", "dict",
                code="changeType", required=True)
FC_BEFORE = Field("change_before", "\u53d8\u66f4\u524d\u5185\u5bb9", "textarea",
                  required=True)
FC_AFTER = Field("change_after", "\u53d8\u66f4\u540e\u5185\u5bb9", "textarea",
                 required=True)
FC_REASON = Field("change_reason", "\u53d8\u66f4\u539f\u56e0", "textarea", required=True)
FC_AMOUNT = Field("amount_change", "\u91d1\u989d\u53d8\u5316\uff08\u5143\uff09", "currency")
FC_NEW_EXPIRE = Field("new_expire_date", "\u53d8\u66f4\u540e\u5230\u671f\u65e5",
                      "calendar")
FC_ATTACH_DESC = Field("attach_desc", "\u9644\u4ef6\u6e05\u5355\u8bf4\u660e", "textarea")


def build_form_change():
    p = Page("\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u8868", FORM_CONTRACT_CHANGE_ID,
             "\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u3001\u8865\u5145\u534f\u8bae")
    p.open_section("sec_c_target", "\u53d8\u66f4\u5bf9\u8c61", flatten=True)
    p.field_grid("fg_c_target", [FC_NO, FC_NAME, FC_PROJECT, FC_TYPE], cols=2, section_title="\u53d8\u66f4\u5bf9\u8c61")
    p.close()
    p.open_section("sec_c_content", "\u53d8\u66f4\u5185\u5bb9", flatten=True)
    p.field_grid("fg_c_content", [FC_BEFORE, FC_AFTER, FC_REASON,
                                  FC_AMOUNT, FC_NEW_EXPIRE, FC_ATTACH_DESC],
                 cols=2, section_title="\u53d8\u66f4\u5185\u5bb9")
    p.close()
    attach_block(p, "att_change", "\u53d8\u66f4\u4f9d\u636e\u9644\u4ef6")
    opinion_block(p, "opinion_change")
    p.add(actionbar("actionbar_change"))
    return FormBuilder(FORM_CONTRACT_CHANGE_ID, "\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u8868",
                       "\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u3001\u8865\u5145\u534f\u8bae",
                       page=p)


FORM_CONTRACT_CHANGE = build_form_change()


# ==========================================================================
# 表单 4：合同状态变更表（官方「状态变更」）
# ==========================================================================

FORM_CONTRACT_STATUS_ID = "f2002004-contract-status-form-0000001"

FST_NO = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
FST_NAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
FST_OLD = Field("old_status", "\u53d8\u66f4\u524d\u72b6\u6001", "dict",
                code="contractStatus", readonly=True)
FST_NEW = Field("new_status", "\u53d8\u66f4\u540e\u72b6\u6001", "dict",
                code="contractStatus", required=True)
FST_DATE = Field("change_date", "\u53d8\u66f4\u65e5\u671f", "calendar", required=True)
FST_REASON = Field("change_reason", "\u53d8\u66f4\u539f\u56e0", "textarea", required=True)
FST_SETTLE = Field("settle_amount", "\u7ed3\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency")
FST_LIAB = Field("liability_desc", "\u8fdd\u7ea6\u8d23\u4efb\u5904\u7406", "textarea")


def build_form_status():
    p = Page("\u5408\u540c\u72b6\u6001\u53d8\u66f4\u8868", FORM_CONTRACT_STATUS_ID,
             "\u5408\u540c\u5c65\u884c\u72b6\u6001\u53d8\u66f4")
    p.open_section("sec_st_target", "\u5408\u540c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_st_target", [FST_NO, FST_NAME, FST_OLD, FST_NEW,
                                  FST_DATE], cols=2, section_title="\u5408\u540c\u4fe1\u606f")
    p.close()
    p.open_section("sec_st_detail", "\u53d8\u66f4\u8bf4\u660e", flatten=True)
    p.field_grid("fg_st_detail", [FST_REASON, FST_SETTLE, FST_LIAB], cols=1, section_title="\u53d8\u66f4\u8bf4\u660e")
    p.close()
    attach_block(p, "att_status", "\u53d8\u66f4\u4f9d\u636e")
    opinion_block(p, "opinion_status")
    p.add(actionbar("actionbar_status"))
    return FormBuilder(FORM_CONTRACT_STATUS_ID, "\u5408\u540c\u72b6\u6001\u53d8\u66f4\u8868",
                       "\u5408\u540c\u5c65\u884c\u72b6\u6001\u53d8\u66f4", page=p)


FORM_CONTRACT_STATUS = build_form_status()


# ==========================================================================
# 表单 5：收款计划编制表（官方「收款计划编制」）
# ==========================================================================

FORM_RECEIVE_PLAN_ID = "f2002005-contract-receive-plan-form-00001"

RP_NO = Field("plan_no", "\u8ba1\u5212\u7f16\u53f7", "textfield", readonly=True)
RP_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
RP_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
RP_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
RP_CTOTAL = Field("contract_total", "\u5408\u540c\u603b\u989d\uff08\u5143\uff09",
                  "currency", readonly=True)
RP_PLAN_TOTAL = Field("plan_total", "\u8ba1\u5212\u6536\u6b3e\u603b\u989d\uff08\u5143\uff09",
                      "currency")
RP_MAKER = Field("plan_maker", "\u7f16\u5236\u4eba", "org")
RP_MAKE_DATE = Field("make_date", "\u7f16\u5236\u65e5\u671f", "calendar")
RP_REMARK = Field("remark", "\u8bf4\u660e", "textarea")

DG_RECEIVE_PLAN = datagrid(
    "dg_receive_plan", "\u6536\u6b3e\u8ba1\u5212\u660e\u7ec6", [
        {"id": "__idx__", "name": "\u5e8f\u53f7"},
        {"id": "stage_no", "name": "\u9636\u6bb5\u5e8f\u53f7", "width": "80px"},
        {"id": "stage_name", "name": "\u6536\u6b3e\u9636\u6bb5", "width": "140px"},
        {"id": "ratio", "name": "\u6bd4\u4f8b\uff08%\uff09", "mtype": "Number",
         "width": "100px"},
        {"id": "amount", "name": "\u8ba1\u5212\u91d1\u989d\uff08\u5143\uff09",
         "mtype": "Currency", "width": "130px"},
        {"id": "plan_date", "name": "\u8ba1\u5212\u6536\u6b3e\u65e5\u671f",
         "mtype": "Calendar", "width": "120px"},
        {"id": "condition", "name": "\u6536\u6b3e\u6761\u4ef6", "width": "180px"},
    ], is_total=True)


def build_form_receive_plan():
    p = Page("\u6536\u6b3e\u8ba1\u5212\u7f16\u5236\u8868", FORM_RECEIVE_PLAN_ID,
             "\u5408\u540c\u6536\u6b3e\u8ba1\u5212\u7f16\u5236")
    p.open_section("sec_rp_basic", "\u5408\u540c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_rp_basic", [RP_NO, RP_CONTRACT, RP_CNAME, RP_PROJECT,
                                  RP_CTOTAL, RP_PLAN_TOTAL], cols=2, section_title="\u5408\u540c\u4fe1\u606f")
    p.close()
    p.open_section("sec_rp_plan", "\u6536\u6b3e\u8ba1\u5212\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_rp", DG_RECEIVE_PLAN)
    p.open_section("sec_rp_meta", "\u7f16\u5236\u4fe1\u606f", flatten=True)
    p.field_grid("fg_rp_meta", [RP_MAKER, RP_MAKE_DATE, RP_REMARK], cols=2, section_title="\u7f16\u5236\u4fe1\u606f")
    p.close()
    p.add(actionbar("actionbar_rp"))
    return FormBuilder(FORM_RECEIVE_PLAN_ID, "\u6536\u6b3e\u8ba1\u5212\u7f16\u5236\u8868",
                       "\u5408\u540c\u6536\u6b3e\u8ba1\u5212\u7f16\u5236", page=p)


FORM_RECEIVE_PLAN = build_form_receive_plan()


# ==========================================================================
# 表单 6：收款计划变更表（官方「收款计划变更」）
# ==========================================================================

FORM_RECEIVE_CHANGE_ID = "f2002006-contract-receive-change-form-0001"

RC_NO = Field("change_no", "\u53d8\u66f4\u5355\u53f7", "textfield", readonly=True)
RC_PLAN = Field("plan_no", "\u539f\u8ba1\u5212\u7f16\u53f7", "textfield", required=True)
RC_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
RC_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
RC_REASON = Field("change_reason", "\u53d8\u66f4\u539f\u56e0", "textarea", required=True)
RC_OLD = Field("old_plan_desc", "\u539f\u8ba1\u5212\u6458\u8981", "textarea")
RC_NEW = Field("new_plan_desc", "\u65b0\u8ba1\u5212\u6458\u8981", "textarea")
RC_DIFF = Field("diff_amount", "\u91d1\u989d\u5dee\u5f02\uff08\u5143\uff09", "currency")
RC_NEW_DATE = Field("new_plan_date", "\u8c03\u6574\u540e\u6536\u6b3e\u65e5", "calendar")

DG_RECEIVE_CHANGE = datagrid(
    "dg_receive_change", "\u53d8\u66f4\u540e\u6536\u6b3e\u8ba1\u5212", [
        {"id": "__idx__", "name": "\u5e8f\u53f7"},
        {"id": "stage_name", "name": "\u6536\u6b3e\u9636\u6bb5", "width": "140px"},
        {"id": "amount", "name": "\u53d8\u66f4\u540e\u91d1\u989d\uff08\u5143\uff09",
         "mtype": "Currency", "width": "140px"},
        {"id": "plan_date", "name": "\u53d8\u66f4\u540e\u65e5\u671f",
         "mtype": "Calendar", "width": "120px"},
    ], is_total=True)


def build_form_receive_change():
    p = Page("\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4\u8868", FORM_RECEIVE_CHANGE_ID,
             "\u6536\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4")
    p.open_section("sec_rc_basic", "\u53d8\u66f4\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_rc_basic", [RC_NO, RC_PLAN, RC_CONTRACT, RC_CNAME,
                                  RC_DIFF, RC_NEW_DATE], cols=2, section_title="\u53d8\u66f4\u57fa\u672c\u4fe1\u606f")
    p.close()
    p.open_section("sec_rc_content", "\u53d8\u66f4\u5185\u5bb9", flatten=True)
    p.field_grid("fg_rc_content", [RC_REASON, RC_OLD, RC_NEW], cols=1, section_title="\u53d8\u66f4\u5185\u5bb9")
    p.close()
    p.open_section("sec_rc_plan", "\u53d8\u66f4\u540e\u8ba1\u5212\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_rc", DG_RECEIVE_CHANGE)
    opinion_block(p, "opinion_rc")
    p.add(actionbar("actionbar_rc"))
    return FormBuilder(FORM_RECEIVE_CHANGE_ID, "\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4\u8868",
                       "\u6536\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4", page=p)


FORM_RECEIVE_CHANGE = build_form_receive_change()


# ==========================================================================
# 表单 7：合同收款表（官方「合同收款」）
# ==========================================================================

FORM_RECEIVE_ID = "f2002007-contract-receive-form-000000001"

RE_NO = Field("receive_no", "\u6536\u6b3e\u5355\u53f7", "textfield", readonly=True)
RE_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
RE_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
RE_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
RE_PLAN = Field("plan_no", "\u5173\u8054\u8ba1\u5212\u7f16\u53f7", "textfield")
RE_TYPE = Field("receive_type", "\u6536\u6b3e\u7c7b\u578b", "dict",
                code="receiveType", required=True)
RE_CTOTAL = Field("contract_total", "\u5408\u540c\u603b\u989d\uff08\u5143\uff09",
                  "currency", readonly=True)
RE_RECEIVED = Field("received_amount", "\u7d2f\u8ba1\u5df2\u6536\uff08\u5143\uff09",
                    "currency", readonly=True)
RE_AMOUNT = Field("receive_amount", "\u672c\u6b21\u6536\u6b3e\u91d1\u989d\uff08\u5143\uff09",
                  "currency", required=True)
RE_DATE = Field("receive_date", "\u5b9e\u9645\u6536\u6b3e\u65e5\u671f", "calendar",
                required=True)
RE_PAYER = Field("payer_name", "\u4ed8\u6b3e\u5355\u4f4d", "textfield")
RE_BANK = Field("payer_bank", "\u4ed8\u6b3e\u94f6\u884c", "textfield")
RE_ACCOUNT = Field("payer_account", "\u4ed8\u6b3e\u8d26\u53f7", "textfield")
RE_VOUCHER = Field("voucher_no", "\u6536\u6b3e\u51ed\u8bc1\u53f7", "textfield")
RE_INVOICE = Field("need_invoice", "\u662f\u5426\u5f00\u7968", "select",
                   options=["\u662f", "\u5426"], default="\u662f")
RE_DESC = Field("receive_desc", "\u6536\u6b3e\u8bf4\u660e", "textarea")


def build_form_receive():
    p = Page("\u5408\u540c\u6536\u6b3e\u8868", FORM_RECEIVE_ID,
             "\u5408\u540c\u5230\u6b3e\u767b\u8bb0\uff0c\u4e0e\u8d22\u52a1\u5e94\u7528\u8054\u52a8")
    p.open_section("sec_re_basic", "\u5408\u540c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_re_basic", [RE_NO, RE_CONTRACT, RE_CNAME, RE_PROJECT,
                                  RE_PLAN, RE_TYPE], cols=2, section_title="\u5408\u540c\u4fe1\u606f")
    p.close()
    p.open_section("sec_re_amount", "\u6536\u6b3e\u4fe1\u606f", flatten=True)
    p.field_grid("fg_re_amount", [RE_CTOTAL, RE_RECEIVED, RE_AMOUNT, RE_DATE,
                                   RE_INVOICE, RE_VOUCHER], cols=2, section_title="\u6536\u6b3e\u4fe1\u606f")
    p.close()
    p.open_section("sec_re_payee", "\u4ed8\u6b3e\u65b9\u4fe1\u606f", flatten=True)
    p.field_grid("fg_re_payee", [RE_PAYER, RE_BANK, RE_ACCOUNT], cols=2, section_title="\u4ed8\u6b3e\u65b9\u4fe1\u606f")
    p.close()
    p.open_section("sec_re_desc", "\u8bf4\u660e", flatten=True)
    p.field_grid("fg_re_desc", [RE_DESC], cols=1, section_title="\u8bf4\u660e")
    p.close()
    attach_block(p, "att_receive", "\u6536\u6b3e\u51ed\u8bc1")
    p.add(actionbar("actionbar_receive"))
    return FormBuilder(FORM_RECEIVE_ID, "\u5408\u540c\u6536\u6b3e\u8868",
                       "\u5408\u540c\u5230\u6b3e\u767b\u8bb0", page=p)


FORM_RECEIVE = build_form_receive()


# ==========================================================================
# 表单 8：开票申请表（官方「开票申请」）
# ==========================================================================

FORM_INVOICE_ID = "f2002008-contract-invoice-form-000000001"

IV_NO = Field("invoice_apply_no", "\u5f00\u7968\u7533\u8bf7\u5355\u53f7",
              "textfield", readonly=True)
IV_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
IV_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
IV_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
IV_TYPE = Field("invoice_type", "\u53d1\u7968\u7c7b\u578b", "dict",
                code="invoiceType", required=True)
IV_AMOUNT = Field("invoice_amount", "\u5f00\u7968\u91d1\u989d\uff08\u5143\uff09",
                  "currency", required=True)
IV_RATE = Field("tax_rate", "\u7a0e\u7387\uff08%\uff09", "number")
IV_TAX = Field("tax_amount", "\u7a0e\u989d\uff08\u5143\uff09", "currency")
IV_NET = Field("net_amount", "\u4e0d\u542b\u7a0e\u91d1\u989d\uff08\u5143\uff09",
               "currency", readonly=True)
IV_BUYER = Field("buyer_name", "\u8d2d\u65b9\u540d\u79f0", "textfield", required=True)
IV_BUYER_TAX = Field("buyer_tax_no", "\u8d2d\u65b9\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
                     "textfield")
IV_BUYER_ADDR = Field("buyer_address", "\u8d2d\u65b9\u5730\u5740\u7535\u8bdd", "textfield")
IV_BUYER_BANK = Field("buyer_bank", "\u8d2d\u65b9\u5f00\u6237\u884c\u53f7", "textfield")
IV_MAIL = Field("mail_info", "\u90ae\u5bc4\u4fe1\u606f", "textfield")
IV_DESC = Field("invoice_desc", "\u5f00\u7968\u8bf4\u660e", "textarea")


def build_form_invoice():
    p = Page("\u5f00\u7968\u7533\u8bf7\u8868", FORM_INVOICE_ID,
             "\u5408\u540c\u5f00\u7968\u7533\u8bf7\u4e0e\u5ba1\u6279")
    p.open_section("sec_iv_basic", "\u7533\u8bf7\u4fe1\u606f", flatten=True)
    p.field_grid("fg_iv_basic", [IV_NO, IV_CONTRACT, IV_CNAME, IV_PROJECT,
                                  IV_TYPE, IV_AMOUNT], cols=2, section_title="\u7533\u8bf7\u4fe1\u606f")
    p.close()
    p.open_section("sec_iv_tax", "\u7a0e\u989d\u4fe1\u606f", flatten=True)
    p.field_grid("fg_iv_tax", [IV_RATE, IV_TAX, IV_NET], cols=2, section_title="\u7a0e\u989d\u4fe1\u606f")
    p.close()
    p.open_section("sec_iv_buyer", "\u8d2d\u65b9\u4fe1\u606f", flatten=True)
    p.field_grid("fg_iv_buyer", [IV_BUYER, IV_BUYER_TAX, IV_BUYER_ADDR,
                                  IV_BUYER_BANK, IV_MAIL], cols=2, section_title="\u8d2d\u65b9\u4fe1\u606f")
    p.close()
    p.open_section("sec_iv_desc", "\u8bf4\u660e", flatten=True)
    p.field_grid("fg_iv_desc", [IV_DESC], cols=1, section_title="\u8bf4\u660e")
    p.close()
    attach_block(p, "att_invoice", "\u5f00\u7968\u8d44\u6599")
    opinion_block(p, "opinion_invoice")
    p.add(actionbar("actionbar_invoice"))
    return FormBuilder(FORM_INVOICE_ID, "\u5f00\u7968\u7533\u8bf7\u8868",
                       "\u5408\u540c\u5f00\u7968\u7533\u8bf7\u4e0e\u5ba1\u6279", page=p)


FORM_INVOICE = build_form_invoice()


# ==========================================================================
# 表单 9：付款计划编制表（官方「付款计划编制」）
# ==========================================================================

FORM_PAY_PLAN_ID = "f2002009-contract-pay-plan-form-00000001"

PP_NO = Field("plan_no", "\u8ba1\u5212\u7f16\u53f7", "textfield", readonly=True)
PP_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
PP_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
PP_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
PP_BUDGET = Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield",
                  description="\u4e0e\u9884\u7b97\u7ba1\u7406\u5e94\u7528\u8054\u52a8")
PP_CTOTAL = Field("contract_total", "\u5408\u540c\u603b\u989d\uff08\u5143\uff09",
                  "currency", readonly=True)
PP_PLAN_TOTAL = Field("plan_total", "\u8ba1\u5212\u4ed8\u6b3e\u603b\u989d\uff08\u5143\uff09",
                      "currency")
PP_SUPPLIER = Field("supplier_name", "\u4f9b\u5e94\u5546", "textfield")
PP_MAKER = Field("plan_maker", "\u7f16\u5236\u4eba", "org")
PP_MAKE_DATE = Field("make_date", "\u7f16\u5236\u65e5\u671f", "calendar")
PP_REMARK = Field("remark", "\u8bf4\u660e", "textarea")

DG_PAY_PLAN = datagrid(
    "dg_pay_plan", "\u4ed8\u6b3e\u8ba1\u5212\u660e\u7ec6", [
        {"id": "__idx__", "name": "\u5e8f\u53f7"},
        {"id": "stage_no", "name": "\u9636\u6bb5\u5e8f\u53f7", "width": "80px"},
        {"id": "stage_name", "name": "\u4ed8\u6b3e\u9636\u6bb5", "width": "140px"},
        {"id": "ratio", "name": "\u6bd4\u4f8b\uff08%\uff09", "mtype": "Number",
         "width": "100px"},
        {"id": "amount", "name": "\u8ba1\u5212\u91d1\u989d\uff08\u5143\uff09",
         "mtype": "Currency", "width": "130px"},
        {"id": "plan_date", "name": "\u8ba1\u5212\u4ed8\u6b3e\u65e5\u671f",
         "mtype": "Calendar", "width": "120px"},
        {"id": "condition", "name": "\u4ed8\u6b3e\u6761\u4ef6", "width": "180px"},
    ], is_total=True)


def build_form_pay_plan():
    p = Page("\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236\u8868", FORM_PAY_PLAN_ID,
             "\u5408\u540c\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236")
    p.open_section("sec_pp_basic", "\u5408\u540c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pp_basic", [PP_NO, PP_CONTRACT, PP_CNAME, PP_PROJECT,
                                  PP_BUDGET, PP_SUPPLIER, PP_CTOTAL,
                                  PP_PLAN_TOTAL], cols=2, section_title="\u5408\u540c\u4fe1\u606f")
    p.close()
    p.open_section("sec_pp_plan", "\u4ed8\u6b3e\u8ba1\u5212\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_pp", DG_PAY_PLAN)
    p.open_section("sec_pp_meta", "\u7f16\u5236\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pp_meta", [PP_MAKER, PP_MAKE_DATE, PP_REMARK], cols=2, section_title="\u7f16\u5236\u4fe1\u606f")
    p.close()
    p.add(actionbar("actionbar_pp"))
    return FormBuilder(FORM_PAY_PLAN_ID, "\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236\u8868",
                       "\u5408\u540c\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236", page=p)


FORM_PAY_PLAN = build_form_pay_plan()


# ==========================================================================
# 表单 10：付款计划变更表（官方「付款计划变更」）
# ==========================================================================

FORM_PAY_CHANGE_ID = "f2002010-contract-pay-change-form-0000001"

PC_NO = Field("change_no", "\u53d8\u66f4\u5355\u53f7", "textfield", readonly=True)
PC_PLAN = Field("plan_no", "\u539f\u8ba1\u5212\u7f16\u53f7", "textfield", required=True)
PC_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
PC_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
PC_REASON = Field("change_reason", "\u53d8\u66f4\u539f\u56e0", "textarea", required=True)
PC_OLD = Field("old_plan_desc", "\u539f\u8ba1\u5212\u6458\u8981", "textarea")
PC_NEW = Field("new_plan_desc", "\u65b0\u8ba1\u5212\u6458\u8981", "textarea")
PC_DIFF = Field("diff_amount", "\u91d1\u989d\u5dee\u5f02\uff08\u5143\uff09", "currency")
PC_NEW_DATE = Field("new_plan_date", "\u8c03\u6574\u540e\u4ed8\u6b3e\u65e5", "calendar")

DG_PAY_CHANGE = datagrid(
    "dg_pay_change", "\u53d8\u66f4\u540e\u4ed8\u6b3e\u8ba1\u5212", [
        {"id": "__idx__", "name": "\u5e8f\u53f7"},
        {"id": "stage_name", "name": "\u4ed8\u6b3e\u9636\u6bb5", "width": "140px"},
        {"id": "amount", "name": "\u53d8\u66f4\u540e\u91d1\u989d\uff08\u5143\uff09",
         "mtype": "Currency", "width": "140px"},
        {"id": "plan_date", "name": "\u53d8\u66f4\u540e\u65e5\u671f",
         "mtype": "Calendar", "width": "120px"},
    ], is_total=True)


def build_form_pay_change():
    p = Page("\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4\u8868", FORM_PAY_CHANGE_ID,
             "\u4ed8\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4")
    p.open_section("sec_pc_basic", "\u53d8\u66f4\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pc_basic", [PC_NO, PC_PLAN, PC_CONTRACT, PC_CNAME,
                                  PC_DIFF, PC_NEW_DATE], cols=2, section_title="\u53d8\u66f4\u57fa\u672c\u4fe1\u606f")
    p.close()
    p.open_section("sec_pc_content", "\u53d8\u66f4\u5185\u5bb9", flatten=True)
    p.field_grid("fg_pc_content", [PC_REASON, PC_OLD, PC_NEW], cols=1, section_title="\u53d8\u66f4\u5185\u5bb9")
    p.close()
    p.open_section("sec_pc_plan", "\u53d8\u66f4\u540e\u8ba1\u5212\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_pc", DG_PAY_CHANGE)
    opinion_block(p, "opinion_pc")
    p.add(actionbar("actionbar_pc"))
    return FormBuilder(FORM_PAY_CHANGE_ID, "\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4\u8868",
                       "\u4ed8\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4", page=p)


FORM_PAY_CHANGE = build_form_pay_change()


# ==========================================================================
# 表单 11：合同付款表（官方「合同付款」）
# ==========================================================================

FORM_PAY_ID = "f2002011-contract-pay-form-00000000001"

PY_NO = Field("pay_apply_no", "\u4ed8\u6b3e\u5355\u53f7", "textfield", readonly=True)
PY_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
PY_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
PY_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
                   readonly=True)
PY_BUDGET = Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield")
PY_PLAN = Field("plan_no", "\u5173\u8054\u8ba1\u5212\u7f16\u53f7", "textfield")
PY_TYPE = Field("pay_type", "\u4ed8\u6b3e\u7c7b\u578b", "dict", code="payType",
                required=True)
PY_CTOTAL = Field("contract_total", "\u5408\u540c\u603b\u989d\uff08\u5143\uff09",
                  "currency", readonly=True)
PY_PAID = Field("paid_amount", "\u7d2f\u8ba1\u5df2\u4ed8\uff08\u5143\uff09",
                "currency", readonly=True)
PY_AMOUNT = Field("apply_amount", "\u672c\u6b21\u4ed8\u6b3e\u91d1\u989d\uff08\u5143\uff09",
                  "currency", required=True)
PY_RATIO = Field("pay_ratio", "\u672c\u6b21\u4ed8\u6b3e\u6bd4\u4f8b\uff08%\uff09", "number")
PY_DATE = Field("plan_pay_date", "\u8ba1\u5212\u4ed8\u6b3e\u65e5\u671f", "calendar",
                required=True)
PY_ACTUAL = Field("actual_pay_date", "\u5b9e\u9645\u4ed8\u6b3e\u65e5\u671f", "calendar")
PY_ACCEPT = Field("acceptance_status", "\u9a8c\u6536\u60c5\u51b5", "select",
                  options=["\u5df2\u9a8c\u6536", "\u90e8\u5206\u9a8c\u6536",
                           "\u672a\u9a8c\u6536"])
PYEE_NAME = Field("payee_name", "\u6536\u6b3e\u5355\u4f4d", "textfield")
PYEE_BANK = Field("payee_bank", "\u5f00\u6237\u94f6\u884c", "textfield")
PYEE_ACCT = Field("payee_account", "\u6536\u6b3e\u8d26\u53f7", "textfield")
PY_DESC = Field("payment_desc", "\u4ed8\u6b3e\u4f9d\u636e\u8bf4\u660e", "textarea",
                required=True)


def build_form_pay():
    p = Page("\u5408\u540c\u4ed8\u6b3e\u8868", FORM_PAY_ID,
             "\u5408\u540c\u7ed3\u7b97\u4e0e\u4ed8\u6b3e\uff0c\u4e0e\u8d22\u52a1\u5e94\u7528\u8054\u52a8")
    p.open_section("sec_py_basic", "\u5408\u540c\u4e0e\u9884\u7b97\u4fe1\u606f", flatten=True)
    p.field_grid("fg_py_basic", [PY_NO, PY_CONTRACT, PY_CNAME, PY_PROJECT,
                                  PY_BUDGET, PY_PLAN, PY_TYPE], cols=2, section_title="\u5408\u540c\u4e0e\u9884\u7b97\u4fe1\u606f")
    p.close()
    p.open_section("sec_py_amount", "\u4ed8\u6b3e\u4fe1\u606f", flatten=True)
    p.field_grid("fg_py_amount", [PY_CTOTAL, PY_PAID, PY_AMOUNT, PY_RATIO,
                                   PY_DATE, PY_ACTUAL, PY_ACCEPT], cols=2, section_title="\u4ed8\u6b3e\u4fe1\u606f")
    p.close()
    p.open_section("sec_py_payee", "\u6536\u6b3e\u65b9\u4fe1\u606f", flatten=True)
    p.field_grid("fg_py_payee", [PYEE_NAME, PYEE_BANK, PYEE_ACCT], cols=2, section_title="\u6536\u6b3e\u65b9\u4fe1\u606f")
    p.close()
    p.open_section("sec_py_desc", "\u4ed8\u6b3e\u4f9d\u636e", flatten=True)
    p.field_grid("fg_py_desc", [PY_DESC], cols=1, section_title="\u4ed8\u6b3e\u4f9d\u636e")
    p.close()
    attach_block(p, "att_pay", "\u4ed8\u6b3e\u51ed\u8bc1\u4e0e\u53d1\u7968")
    opinion_block(p, "opinion_pay")
    p.add(actionbar("actionbar_pay"))
    return FormBuilder(FORM_PAY_ID, "\u5408\u540c\u4ed8\u6b3e\u8868",
                       "\u5408\u540c\u7ed3\u7b97\u4e0e\u4ed8\u6b3e", page=p)


FORM_PAY = build_form_pay()


# ==========================================================================
# 表单 12：收票记录表（官方「收票记录」）
# ==========================================================================

FORM_TICKET_ID = "f2002012-contract-ticket-form-00000000001"

TK_NO = Field("ticket_no", "\u6536\u7968\u8bb0\u5f55\u5355\u53f7", "textfield",
              readonly=True)
TK_CONTRACT = Field("contract_no", "\u5408\u540c\u7f16\u53f7", "textfield", required=True)
TK_CNAME = Field("contract_name", "\u5408\u540c\u540d\u79f0", "textfield", readonly=True)
TK_INVOICE = Field("invoice_no", "\u53d1\u7968\u53f7\u7801", "textfield", required=True)
TK_TYPE = Field("invoice_type", "\u53d1\u7968\u7c7b\u578b", "dict",
                code="invoiceType", required=True)
TK_AMOUNT = Field("invoice_amount", "\u53d1\u7968\u91d1\u989d\uff08\u5143\uff09",
                  "currency", required=True)
TK_TAX = Field("tax_amount", "\u7a0e\u989d\uff08\u5143\uff09", "currency")
TK_SELLER = Field("seller_name", "\u9500\u65b9\u540d\u79f0", "textfield")
TK_SELLER_TAX = Field("seller_tax_no", "\u9500\u65b9\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
                      "textfield")
TK_DATE = Field("invoice_date", "\u5f00\u7968\u65e5\u671f", "calendar")
TK_RECEIVE = Field("receive_date", "\u6536\u7968\u65e5\u671f", "calendar", required=True)
TK_CHECK = Field("verify_status", "\u9a8c\u771f\u72b6\u6001", "select",
                 options=["\u5df2\u9a8c\u771f", "\u5f85\u9a8c\u771f", "\u9a8c\u771f\u5931\u8d25"],
                 default="\u5f85\u9a8c\u771f")
TK_REMARK = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_ticket():
    p = Page("\u6536\u7968\u8bb0\u5f55\u8868", FORM_TICKET_ID,
             "\u5408\u540c\u53d1\u7968\u6536\u7968\u767b\u8bb0\u4e0e\u9a8c\u771f")
    p.open_section("sec_tk_basic", "\u5408\u540c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_tk_basic", [TK_NO, TK_CONTRACT, TK_CNAME], cols=2, section_title="\u5408\u540c\u4fe1\u606f")
    p.close()
    p.open_section("sec_tk_invoice", "\u53d1\u7968\u4fe1\u606f", flatten=True)
    p.field_grid("fg_tk_invoice", [TK_INVOICE, TK_TYPE, TK_AMOUNT, TK_TAX,
                                    TK_DATE, TK_RECEIVE, TK_CHECK], cols=2, section_title="\u53d1\u7968\u4fe1\u606f")
    p.close()
    p.open_section("sec_tk_seller", "\u9500\u65b9\u4fe1\u606f", flatten=True)
    p.field_grid("fg_tk_seller", [TK_SELLER, TK_SELLER_TAX], cols=2, section_title="\u9500\u65b9\u4fe1\u606f")
    p.close()
    p.open_section("sec_tk_remark", "\u5907\u6ce8", flatten=True)
    p.field_grid("fg_tk_remark", [TK_REMARK], cols=1, section_title="\u5907\u6ce8")
    p.close()
    attach_block(p, "att_ticket", "\u53d1\u7968\u626b\u63cf\u4ef6")
    p.add(actionbar("actionbar_ticket"))
    return FormBuilder(FORM_TICKET_ID, "\u6536\u7968\u8bb0\u5f55\u8868",
                       "\u5408\u540c\u53d1\u7968\u6536\u7968\u767b\u8bb0", page=p)


FORM_TICKET = build_form_ticket()


# ==========================================================================
# 表单 13：签约方档案表（官方「签约方档案」）
# ==========================================================================

FORM_PARTNER_ID = "f2002013-contract-partner-form-000000001"

PT_CODE = Field("partner_code", "\u7b7e\u7ea6\u65b9\u7f16\u7801", "textfield",
                required=True, readonly=True)
PT_NAME = Field("partner_name", "\u7b7e\u7ea6\u65b9\u540d\u79f0", "textfield",
                required=True)
PT_SHORT = Field("partner_short", "\u7b80\u79f0", "textfield")
PT_TYPE = Field("partner_type", "\u7b7e\u7ea6\u65b9\u7c7b\u578b", "dict",
                code="partnerType", required=True)
PT_TAX_NO = Field("tax_no", "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7", "textfield")
PT_CREDIT = Field("credit_code", "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801",
                  "textfield")
PT_LEGAL = Field("legal_person", "\u6cd5\u5b9a\u4ee3\u8868\u4eba", "textfield")
PT_CAPITAL = Field("registered_capital", "\u6ce8\u518c\u8d44\u672c\uff08\u4e07\u5143\uff09",
                   "number")
PT_ADDR = Field("address", "\u6ce8\u518c\u5730\u5740", "textfield")
PT_SCOPE = Field("business_scope", "\u7ecf\u8425\u8303\u56f4", "textarea")
PT_CONTACT = Field("contact_person", "\u8054\u7cfb\u4eba", "textfield")
PT_PHONE = Field("contact_phone", "\u8054\u7cfb\u7535\u8bdd", "textfield")
PT_EMAIL = Field("contact_email", "\u7535\u5b50\u90ae\u7bb1", "textfield")
PT_FAX = Field("fax", "\u4f20\u771f", "textfield")
PT_BANK = Field("bank_name", "\u5f00\u6237\u94f6\u884c", "textfield")
PT_ACCOUNT = Field("bank_account", "\u94f6\u884c\u8d26\u53f7", "textfield")
PT_TAX_ADDR = Field("tax_address", "\u5f00\u7968\u5730\u5740\u7535\u8bdd", "textfield")
PT_LICENSE = Field("license_no", "\u8425\u4e1a\u6267\u7167\u53f7", "textfield")
PT_LICENSE_EXP = Field("license_expire", "\u6267\u7167\u6709\u6548\u671f", "calendar")
PT_QUALIFY = Field("qualify_desc", "\u8d44\u8d28\u8bc1\u4e66", "textarea")
PT_EVAL = Field("eval_level", "\u4fe1\u7528\u8bc4\u7ea7", "select",
                options=["A", "B", "C", "D"], default="B")
PT_STATUS = Field("partner_status", "\u6863\u6848\u72b6\u6001", "select",
                  options=["\u6b63\u5e38", "\u51bb\u7ed3", "\u9ed1\u540d\u5355"],
                  default="\u6b63\u5e38")
PT_REMARK = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_partner():
    p = Page("\u7b7e\u7ea6\u65b9\u6863\u6848\u8868", FORM_PARTNER_ID,
             "\u7b7e\u7ea6\u65b9\u57fa\u672c\u4fe1\u606f\u3001\u8054\u7cfb\u4fe1\u606f\u3001"
             "\u8d22\u52a1\u4fe1\u606f\u4e0e\u8bc1\u4e66\u4fe1\u606f")
    p.open_section("sec_pt_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pt_basic", [PT_CODE, PT_NAME, PT_SHORT, PT_TYPE,
                                  PT_TAX_NO, PT_CREDIT, PT_LEGAL, PT_CAPITAL,
                                  PT_EVAL, PT_STATUS, PT_ADDR, PT_SCOPE],
                 cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()
    p.open_section("sec_pt_contact", "\u8054\u7cfb\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pt_contact", [PT_CONTACT, PT_PHONE, PT_EMAIL, PT_FAX],
                 cols=2, section_title="\u8054\u7cfb\u4fe1\u606f")
    p.close()
    p.open_section("sec_pt_finance", "\u8d22\u52a1\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pt_finance", [PT_BANK, PT_ACCOUNT, PT_TAX_ADDR], cols=2, section_title="\u8d22\u52a1\u4fe1\u606f")
    p.close()
    p.open_section("sec_pt_cert", "\u8bc1\u4e66\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pt_cert", [PT_LICENSE, PT_LICENSE_EXP, PT_QUALIFY],
                 cols=2, section_title="\u8bc1\u4e66\u4fe1\u606f")
    p.close()
    p.open_section("sec_pt_remark", "\u5907\u6ce8", flatten=True)
    p.field_grid("fg_pt_remark", [PT_REMARK], cols=1, section_title="\u5907\u6ce8")
    p.close()
    attach_block(p, "att_partner", "\u8bc1\u7167\u53ca\u8d44\u8d28\u626b\u63cf\u4ef6")
    p.add(actionbar("actionbar_partner"))
    return FormBuilder(FORM_PARTNER_ID, "\u7b7e\u7ea6\u65b9\u6863\u6848\u8868",
                       "\u7b7e\u7ea6\u65b9\u6863\u6848\u7ba1\u7406", page=p)


FORM_PARTNER = build_form_partner()


# ==========================================================================
# 表单 14：合同管理配置表（官方「合同管理配置」）
# ==========================================================================

FORM_CONFIG_ID = "f2002014-contract-config-form-0000000001"

CFG_KEY = Field("config_key", "\u914d\u7f6e\u9879", "textfield", required=True)
CFG_VALUE = Field("config_value", "\u914d\u7f6e\u503c", "textfield", required=True)
CFG_TYPE = Field("config_type", "\u914d\u7f6e\u7c7b\u578b", "select",
                 options=["\u57fa\u7840\u914d\u7f6e", "\u6d41\u7a0b\u914d\u7f6e",
                          "\u4eba\u5458\u914d\u7f6e", "\u63d0\u9192\u914d\u7f6e"])
CFG_DESC = Field("config_desc", "\u914d\u7f6e\u8bf4\u660e", "textarea")
CFG_ADMIN = Field("contract_admin", "\u5408\u540c\u7ba1\u7406\u5458", "org")
CFG_WARN = Field("expire_warn_days", "\u5230\u671f\u9884\u8b66\u5929\u6570",
                 "number", default="30")
CFG_NUMBER_RULE = Field("number_rule", "\u7f16\u53f7\u89c4\u5219", "textfield",
                        default="HT-{yyyy}{mm}-{seq}")


def build_form_config():
    p = Page("\u5408\u540c\u7ba1\u7406\u914d\u7f6e\u8868", FORM_CONFIG_ID,
             "\u5408\u540c\u7ba1\u7406\u5e94\u7528\u57fa\u7840\u914d\u7f6e")
    p.open_section("sec_cfg_basic", "\u57fa\u7840\u914d\u7f6e", flatten=True)
    p.field_grid("fg_cfg_basic", [CFG_KEY, CFG_VALUE, CFG_TYPE,
                                   CFG_NUMBER_RULE, CFG_WARN, CFG_ADMIN],
                 cols=2, section_title="\u57fa\u7840\u914d\u7f6e")
    p.close()
    p.open_section("sec_cfg_desc", "\u8bf4\u660e", flatten=True)
    p.field_grid("fg_cfg_desc", [CFG_DESC], cols=1, section_title="\u8bf4\u660e")
    p.close()
    p.add(actionbar("actionbar_config"))
    return FormBuilder(FORM_CONFIG_ID, "\u5408\u540c\u7ba1\u7406\u914d\u7f6e\u8868",
                       "\u5408\u540c\u7ba1\u7406\u5e94\u7528\u57fa\u7840\u914d\u7f6e",
                       page=p)


FORM_CONFIG = build_form_config()


# ==========================================================================
# 流程（对齐官方业务动作：档案管理 4 + 过程管理 2 + 收款管理 4 + 付款管理 4）
# ==========================================================================

# ---- 1. 合同审批流程（官方「发起合同审批流程」）----
PROC_CONTRACT = ProcessBuilder(
    PROC_CONTRACT_ID, "\u5408\u540c\u5ba1\u6279\u6d41\u7a0b",
    "\u5408\u540c\u8349\u62df\u3001\u4f1a\u7b7e\u3001\u5ba1\u6279\u4e0e\u7b7e\u8ba2\u5168\u8fc7\u7a0b",
    form_id=FORM_CONTRACT_ID,
    activities=[
        Activity("a_draft", "\u5408\u540c\u8349\u62df", "manual", form_id=FORM_CONTRACT_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_legal", "\u6cd5\u52a1\u5ba1\u6838", "manual", form_id=FORM_CONTRACT_ID,
                 task_script=SCRIPT_LEGAL),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", form_id=FORM_CONTRACT_ID,
                 task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", form_id=FORM_CONTRACT_ID,
                 task_script=SCRIPT_LEADER),
        Activity("a_sign", "\u7b7e\u7f72\u767b\u8bb0", "manual", form_id=FORM_CONTRACT_ID,
                 task_script=SCRIPT_LEGAL),
        Activity("a_archive", "\u5408\u540c\u5f52\u6863", "manual",
                 form_id=FORM_CONTRACT_SUPPLEMENT_ID, task_script=SCRIPT_ARCHIVE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_legal", "\u63d0\u4ea4\u5ba1\u6838", ""),
        ("a_legal", "a_finance", "\u6cd5\u52a1\u901a\u8fc7", ""),
        ("a_legal", "a_draft", "\u9000\u56de\u4fee\u6539", ""),
        ("a_finance", "a_leader", "\u8d22\u52a1\u901a\u8fc7", ""),
        ("a_finance", "a_draft", "\u9a73\u56de", ""),
        ("a_leader", "a_sign", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_sign", "a_archive", "\u7b7e\u7f72\u5b8c\u6210", ""),
        ("a_archive", "a_end", "\u5f52\u6863\u5b8c\u6210", ""),
    ],
)

# ---- 2. 合同补录流程（官方「合同补录」）----
PROC_SUPPLEMENT_ID = "p2002002-contract-supplement-0000000001"

PROC_SUPPLEMENT = ProcessBuilder(
    PROC_SUPPLEMENT_ID, "\u5408\u540c\u8865\u5f55\u6d41\u7a0b",
    "\u5386\u53f2\u5408\u540c\u53f0\u8d26\u8865\u5f55\u4e0e\u5ba1\u6838",
    form_id=FORM_CONTRACT_SUPPLEMENT_ID,
    activities=[
        Activity("a_input", "\u53f0\u8d26\u8865\u5f55", "manual",
                 form_id=FORM_CONTRACT_SUPPLEMENT_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_admin", "\u5408\u540c\u7ba1\u7406\u5458\u5ba1\u6838", "manual",
                 form_id=FORM_CONTRACT_SUPPLEMENT_ID,
                 task_script=SCRIPT_CONTRACT_ADMIN),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_input", "a_admin", "\u63d0\u4ea4", ""),
        ("a_admin", "a_end", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_admin", "a_input", "\u9000\u56de", ""),
    ],
)

# ---- 3. 合同信息变更流程（官方「信息变更」）----
PROC_CONTRACT_CHANGE_ID = "p2002003-contract-change-00000000001"

PROC_CONTRACT_CHANGE = ProcessBuilder(
    PROC_CONTRACT_CHANGE_ID, "\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u6d41\u7a0b",
    "\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u3001\u8865\u5145\u534f\u8bae\u5ba1\u6279",
    form_id=FORM_CONTRACT_CHANGE_ID,
    activities=[
        Activity("a_draft", "\u53d8\u66f4\u7533\u8bf7", "manual",
                 form_id=FORM_CONTRACT_CHANGE_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_legal", "\u6cd5\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_CONTRACT_CHANGE_ID, task_script=SCRIPT_LEGAL),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_CONTRACT_CHANGE_ID, task_script=SCRIPT_LEADER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_legal", "\u63d0\u4ea4", ""),
        ("a_legal", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_legal", "a_draft", "\u9000\u56de", ""),
        ("a_leader", "a_end", "\u6279\u51c6", ""),
    ],
)

# ---- 4. 合同状态变更流程（官方「状态变更」，到期自动发起）----
PROC_CONTRACT_STATUS_ID = "p2002004-contract-status-000000000001"

PROC_CONTRACT_STATUS = ProcessBuilder(
    PROC_CONTRACT_STATUS_ID, "\u5408\u540c\u72b6\u6001\u53d8\u66f4\u6d41\u7a0b",
    "\u5408\u540c\u5c65\u884c\u72b6\u6001\u53d8\u66f4\uff08\u5b8c\u6210/\u7ec8\u6b62/\u89e3\u9664/\u4e2d\u6b62\uff09",
    form_id=FORM_CONTRACT_STATUS_ID,
    activities=[
        Activity("a_apply", "\u72b6\u6001\u53d8\u66f4\u7533\u8bf7", "manual",
                 form_id=FORM_CONTRACT_STATUS_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_admin", "\u5408\u540c\u7ba1\u7406\u5458\u786e\u8ba4", "manual",
                 form_id=FORM_CONTRACT_STATUS_ID, task_script=SCRIPT_CONTRACT_ADMIN),
        Activity("a_finance", "\u8d22\u52a1\u6838\u5bf9", "manual",
                 form_id=FORM_CONTRACT_STATUS_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_admin", "\u63d0\u4ea4", ""),
        ("a_admin", "a_finance", "\u786e\u8ba4", ""),
        ("a_admin", "a_apply", "\u9000\u56de", ""),
        ("a_finance", "a_end", "\u6838\u5bf9\u5b8c\u6210", ""),
    ],
)

# ---- 5. 收款计划编制流程（官方「收款计划编制」）----
PROC_RECEIVE_PLAN_ID = "p2002005-contract-receive-plan-00000001"

PROC_RECEIVE_PLAN = ProcessBuilder(
    PROC_RECEIVE_PLAN_ID, "\u6536\u6b3e\u8ba1\u5212\u7f16\u5236\u6d41\u7a0b",
    "\u5408\u540c\u6536\u6b3e\u8ba1\u5212\u7f16\u5236\u4e0e\u5ba1\u6279",
    form_id=FORM_RECEIVE_PLAN_ID,
    activities=[
        Activity("a_make", "\u8ba1\u5212\u7f16\u5236", "manual",
                 form_id=FORM_RECEIVE_PLAN_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_RECEIVE_PLAN_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_make", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_end", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_make", "\u9000\u56de", ""),
    ],
)

# ---- 6. 收款计划变更流程（官方「收款计划变更」）----
PROC_RECEIVE_CHANGE_ID = "p2002006-contract-receive-change-000001"

PROC_RECEIVE_CHANGE = ProcessBuilder(
    PROC_RECEIVE_CHANGE_ID, "\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4\u6d41\u7a0b",
    "\u6536\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4\u5ba1\u6279",
    form_id=FORM_RECEIVE_CHANGE_ID,
    activities=[
        Activity("a_apply", "\u53d8\u66f4\u7533\u8bf7", "manual",
                 form_id=FORM_RECEIVE_CHANGE_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_RECEIVE_CHANGE_ID, task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_RECEIVE_CHANGE_ID, task_script=SCRIPT_LEADER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_apply", "\u9000\u56de", ""),
        ("a_leader", "a_end", "\u6279\u51c6", ""),
    ],
)

# ---- 7. 合同收款流程（官方「合同收款」）----
PROC_RECEIVE_ID = "p2002007-contract-receive-0000000000001"

PROC_RECEIVE = ProcessBuilder(
    PROC_RECEIVE_ID, "\u5408\u540c\u6536\u6b3e\u6d41\u7a0b",
    "\u5408\u540c\u5230\u6b3e\u767b\u8bb0\u4e0e\u786e\u8ba4",
    form_id=FORM_RECEIVE_ID,
    activities=[
        Activity("a_reg", "\u6536\u6b3e\u767b\u8bb0", "manual",
                 form_id=FORM_RECEIVE_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u786e\u8ba4", "manual",
                 form_id=FORM_RECEIVE_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_reg", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_end", "\u786e\u8ba4\u5230\u8d26", ""),
        ("a_finance", "a_reg", "\u9000\u56de", ""),
    ],
)

# ---- 8. 开票申请流程（官方「开票申请」）----
PROC_INVOICE_ID = "p2002008-contract-invoice-000000000001"

PROC_INVOICE = ProcessBuilder(
    PROC_INVOICE_ID, "\u5f00\u7968\u7533\u8bf7\u6d41\u7a0b",
    "\u5408\u540c\u5f00\u7968\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_INVOICE_ID,
    activities=[
        Activity("a_apply", "\u5f00\u7968\u7533\u8bf7", "manual",
                 form_id=FORM_INVOICE_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_INVOICE_ID, task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_INVOICE_ID, task_script=SCRIPT_LEADER),
        Activity("a_issue", "\u5f00\u7968\u767b\u8bb0", "manual",
                 form_id=FORM_INVOICE_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_apply", "\u9000\u56de", ""),
        ("a_leader", "a_issue", "\u6279\u51c6", ""),
        ("a_issue", "a_end", "\u5f00\u7968\u5b8c\u6210", ""),
    ],
)

# ---- 9. 付款计划编制流程（官方「付款计划编制」）----
PROC_PAY_PLAN_ID = "p2002009-contract-pay-plan-0000000001"

PROC_PAY_PLAN = ProcessBuilder(
    PROC_PAY_PLAN_ID, "\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236\u6d41\u7a0b",
    "\u5408\u540c\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236\u4e0e\u5ba1\u6279",
    form_id=FORM_PAY_PLAN_ID,
    activities=[
        Activity("a_make", "\u8ba1\u5212\u7f16\u5236", "manual",
                 form_id=FORM_PAY_PLAN_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_PAY_PLAN_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_make", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_end", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_make", "\u9000\u56de", ""),
    ],
)

# ---- 10. 付款计划变更流程（官方「付款计划变更」）----
PROC_PAY_CHANGE_ID = "p2002010-contract-pay-change-00000001"

PROC_PAY_CHANGE = ProcessBuilder(
    PROC_PAY_CHANGE_ID, "\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4\u6d41\u7a0b",
    "\u4ed8\u6b3e\u8ba1\u5212\u8c03\u6574\u4e0e\u53d8\u66f4\u5ba1\u6279",
    form_id=FORM_PAY_CHANGE_ID,
    activities=[
        Activity("a_apply", "\u53d8\u66f4\u7533\u8bf7", "manual",
                 form_id=FORM_PAY_CHANGE_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_PAY_CHANGE_ID, task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_PAY_CHANGE_ID, task_script=SCRIPT_LEADER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_apply", "\u9000\u56de", ""),
        ("a_leader", "a_end", "\u6279\u51c6", ""),
    ],
)

# ---- 11. 合同付款流程（官方「合同付款」）----
PROC_PAY_ID = "p2002011-contract-pay-000000000000001"

PROC_PAY = ProcessBuilder(
    PROC_PAY_ID, "\u5408\u540c\u4ed8\u6b3e\u6d41\u7a0b",
    "\u5408\u540c\u7ed3\u7b97\u4ed8\u6b3e\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_PAY_ID,
    activities=[
        Activity("a_apply", "\u4ed8\u6b3e\u7533\u8bf7", "manual",
                 form_id=FORM_PAY_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_pm", "\u9879\u76ee\u7ecf\u7406\u786e\u8ba4", "manual",
                 form_id=FORM_PAY_ID, task_script=SCRIPT_PROJECT_MGR),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_PAY_ID, task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_PAY_ID, task_script=SCRIPT_LEADER),
        Activity("a_pay", "\u8d22\u52a1\u4ed8\u6b3e", "manual",
                 form_id=FORM_PAY_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_finance", "\u786e\u8ba4", ""),
        ("a_pm", "a_apply", "\u9000\u56de", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_leader", "a_pay", "\u6279\u51c6", ""),
        ("a_leader", "a_apply", "\u4e0d\u6279\u51c6", ""),
        ("a_pay", "a_end", "\u4ed8\u6b3e\u5b8c\u6210", ""),
    ],
)

# ---- 12. 收票记录流程（官方「收票记录」）----
PROC_TICKET_ID = "p2002012-contract-ticket-0000000000001"

PROC_TICKET = ProcessBuilder(
    PROC_TICKET_ID, "\u6536\u7968\u8bb0\u5f55\u6d41\u7a0b",
    "\u5408\u540c\u53d1\u7968\u6536\u7968\u767b\u8bb0\u4e0e\u9a8c\u771f",
    form_id=FORM_TICKET_ID,
    activities=[
        Activity("a_reg", "\u6536\u7968\u767b\u8bb0", "manual",
                 form_id=FORM_TICKET_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u9a8c\u771f", "manual",
                 form_id=FORM_TICKET_ID, task_script=SCRIPT_FINANCE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_reg", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_end", "\u9a8c\u771f\u901a\u8fc7", ""),
        ("a_finance", "a_reg", "\u9000\u56de", ""),
    ],
)

# ---- 13. 签约方档案流程（官方「签约方档案」）----
PROC_PARTNER_ID = "p2002013-contract-partner-00000000001"

PROC_PARTNER = ProcessBuilder(
    PROC_PARTNER_ID, "\u7b7e\u7ea6\u65b9\u6863\u6848\u767b\u8bb0\u6d41\u7a0b",
    "\u7b7e\u7ea6\u65b9\u6863\u6848\u5efa\u7acb\u4e0e\u5ba1\u6838",
    form_id=FORM_PARTNER_ID,
    activities=[
        Activity("a_apply", "\u6863\u6848\u7533\u62a5", "manual",
                 form_id=FORM_PARTNER_ID,
                 task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_admin", "\u5408\u540c\u7ba1\u7406\u5458\u5ba1\u6838", "manual",
                 form_id=FORM_PARTNER_ID, task_script=SCRIPT_CONTRACT_ADMIN),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_apply", "a_admin", "\u63d0\u4ea4", ""),
        ("a_admin", "a_end", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_admin", "a_apply", "\u9000\u56de", ""),
    ],
)

# ==========================================================================
# 自建表（8 张）
# --------------------------------------------------------------------------
# 命名规范：t2002NNN-contract-<name>-table-<补零>
# 关联主线：contract_no 为主干，project_no 挂项目管理，partner_no 挂签约方，
#           receive_no / pay_no / invoice_no 挂收付款，archive_no 挂档案应用。
# ==========================================================================

TABLE_CONTRACT_ID = "t2002001-contract-main-table-0000000001"
TABLE_RECEIVE_PLAN_ID = "t2002002-contract-receive-plan-table-0001"
TABLE_RECEIVE_ID = "t2002003-contract-receive-table-000000001"
TABLE_INVOICE_ID = "t2002004-contract-invoice-table-000000001"
TABLE_PAY_ID = "t2002005-contract-pay-table-0000000000001"
TABLE_TICKET_ID = "t2002006-contract-ticket-table-00000000001"
TABLE_PARTNER_ID = "t2002007-contract-partner-table-0000000001"
TABLE_CHANGE_ID = "t2002008-contract-change-table-00000000001"

# --- 8.1 合同主表 ---------------------------------------------------------
TABLE_CONTRACT = table(
    TABLE_CONTRACT_ID, "\u5408\u540c\u4e3b\u8868",
    [
        ("id", "string", "ID", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("contract_type", "string", "\u5408\u540c\u7c7b\u578b", 64),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("project_name", "string", "\u5173\u8054\u9879\u76ee\u540d\u79f0", 255),
        ("partner_no", "string", "\u7b7e\u7ea6\u5bf9\u65b9\u7f16\u53f7", 64),
        ("sign_unit", "string", "\u7b7e\u7ea6\u5355\u4f4d", 255),
        ("sign_date", "date", "\u7b7e\u8ba2\u65e5\u671f", 20),
        ("handle_dept", "string", "\u7ecf\u529e\u90e8\u95e8", 128),
        ("handle_person", "string", "\u7ecf\u529e\u4eba\u5458", 64),
        ("contract_amount", "double", "\u5408\u540c\u91d1\u989d", 2),
        ("tax_rate", "double", "\u7a0e\u7387", 2),
        ("tax_amount", "double", "\u7a0e\u989d", 2),
        ("net_amount", "double", "\u4e0d\u542b\u7a0e\u91d1\u989d", 2),
        ("currency", "string", "\u5e01\u79cd", 16),
        ("pay_type", "string", "\u4ed8\u6b3e\u65b9\u5f0f", 64),
        ("start_date", "date", "\u751f\u6548\u65e5\u671f", 20),
        ("end_date", "date", "\u5230\u671f\u65e5\u671f", 20),
        ("contract_status", "string", "\u5408\u540c\u72b6\u6001", 32),
        ("perform_rate", "double", "\u5c65\u7ea6\u8fdb\u5ea6%", 2),
        ("receive_total", "double", "\u5df2\u6536\u91d1\u989d", 2),
        ("pay_total", "double", "\u5df2\u4ed8\u91d1\u989d", 2),
        ("invoice_total", "double", "\u5df2\u5f00\u7968\u91d1\u989d", 2),
        ("archive_no", "string", "\u5f52\u6863\u53f7", 64),
        ("sign_person", "string", "\u5bf9\u65b9\u7b7e\u7f72\u4eba", 64),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
        ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u53f0\u8d26\uff0ccontract_no \u4e3a\u4e1a\u52a1\u4e3b\u952e\uff0cproject_no \u5173\u8054\u9879\u76ee\u7ba1\u7406\u5e94\u7528",
)

# --- 8.2 收款计划表 -------------------------------------------------------
TABLE_RECEIVE_PLAN = table(
    TABLE_RECEIVE_PLAN_ID, "\u6536\u6b3e\u8ba1\u5212\u8868",
    [
        ("id", "string", "ID", 64),
        ("plan_no", "string", "\u8ba1\u5212\u7f16\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("period_index", "integer", "\u671f\u6b21", 11),
        ("period_name", "string", "\u671f\u6b21\u540d\u79f0", 128),
        ("plan_ratio", "double", "\u5360\u6bd4%", 2),
        ("plan_amount", "double", "\u8ba1\u5212\u91d1\u989d", 2),
        ("plan_date", "date", "\u8ba1\u5212\u6536\u6b3e\u65e5\u671f", 20),
        ("receive_condition", "string", "\u6536\u6b3e\u6761\u4ef6", 255),
        ("received_amount", "double", "\u5df2\u6536\u91d1\u989d", 2),
        ("plan_status", "string", "\u8ba1\u5212\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u5206\u671f\u6536\u6b3e\u8ba1\u5212\u660e\u7ec6",
)

# --- 8.3 合同收款表 -------------------------------------------------------
TABLE_RECEIVE = table(
    TABLE_RECEIVE_ID, "\u5408\u540c\u6536\u6b3e\u8868",
    [
        ("id", "string", "ID", 64),
        ("receive_no", "string", "\u6536\u6b3e\u5355\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("plan_no", "string", "\u5173\u8054\u8ba1\u5212\u7f16\u53f7", 64),
        ("receive_type", "string", "\u6536\u6b3e\u7c7b\u578b", 64),
        ("receive_amount", "double", "\u6536\u6b3e\u91d1\u989d", 2),
        ("receive_date", "date", "\u6536\u6b3e\u65e5\u671f", 20),
        ("payer_name", "string", "\u4ed8\u6b3e\u65b9\u540d\u79f0", 255),
        ("bank_account", "string", "\u6536\u6b3e\u8d26\u53f7", 64),
        ("voucher_no", "string", "\u51ed\u8bc1\u53f7", 64),
        ("receive_status", "string", "\u6536\u6b3e\u72b6\u6001", 32),
        ("expense_no", "string", "\u5173\u8054\u8d22\u52a1\u51ed\u8bc1\u53f7", 64),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u56de\u6b3e\u767b\u8bb0\uff0cexpense_no \u5411\u8d22\u52a1\u5e94\u7528\u63a8\u9001\u51ed\u8bc1",
)

# --- 8.4 开票申请表 -------------------------------------------------------
TABLE_INVOICE = table(
    TABLE_INVOICE_ID, "\u5f00\u7968\u7533\u8bf7\u8868",
    [
        ("id", "string", "ID", 64),
        ("invoice_apply_no", "string", "\u5f00\u7968\u7533\u8bf7\u5355\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("invoice_type", "string", "\u53d1\u7968\u7c7b\u578b", 64),
        ("invoice_amount", "double", "\u5f00\u7968\u91d1\u989d", 2),
        ("tax_rate", "double", "\u7a0e\u7387", 2),
        ("tax_amount", "double", "\u7a0e\u989d", 2),
        ("net_amount", "double", "\u4e0d\u542b\u7a0e\u91d1\u989d", 2),
        ("buyer_name", "string", "\u8d2d\u65b9\u540d\u79f0", 255),
        ("buyer_tax_no", "string", "\u8d2d\u65b9\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7", 64),
        ("invoice_no", "string", "\u53d1\u7968\u53f7\u7801", 64),
        ("invoice_date", "date", "\u5f00\u7968\u65e5\u671f", 20),
        ("apply_status", "string", "\u7533\u8bf7\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u5f00\u7968\u7533\u8bf7\u4e0e\u53d1\u7968\u767b\u8bb0",
)

# --- 8.5 合同付款表 -------------------------------------------------------
TABLE_PAY = table(
    TABLE_PAY_ID, "\u5408\u540c\u4ed8\u6b3e\u8868",
    [
        ("id", "string", "ID", 64),
        ("pay_no", "string", "\u4ed8\u6b3e\u5355\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("budget_no", "string", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", 64),
        ("pay_plan_no", "string", "\u5173\u8054\u4ed8\u6b3e\u8ba1\u5212\u7f16\u53f7", 64),
        ("pay_type", "string", "\u4ed8\u6b3e\u7c7b\u578b", 64),
        ("pay_amount", "double", "\u4ed8\u6b3e\u91d1\u989d", 2),
        ("pay_date", "date", "\u4ed8\u6b3e\u65e5\u671f", 20),
        ("payee_name", "string", "\u6536\u6b3e\u65b9\u540d\u79f0", 255),
        ("bank_account", "string", "\u4ed8\u6b3e\u8d26\u53f7", 64),
        ("voucher_no", "string", "\u51ed\u8bc1\u53f7", 64),
        ("pay_status", "string", "\u4ed8\u6b3e\u72b6\u6001", 32),
        ("expense_no", "string", "\u5173\u8054\u8d22\u52a1\u51ed\u8bc1\u53f7", 64),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u4ed8\u6b3e\u767b\u8bb0\uff0c\u4e09\u65b9\u6302\u9760 project_no + budget_no + expense_no",
)

# --- 8.6 收票记录表 -------------------------------------------------------
TABLE_TICKET = table(
    TABLE_TICKET_ID, "\u6536\u7968\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("ticket_no", "string", "\u6536\u7968\u5355\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("invoice_no", "string", "\u53d1\u7968\u53f7\u7801", 64),
        ("invoice_code", "string", "\u53d1\u7968\u4ee3\u7801", 64),
        ("ticket_type", "string", "\u7968\u636e\u7c7b\u578b", 64),
        ("ticket_amount", "double", "\u7968\u636e\u91d1\u989d", 2),
        ("tax_amount", "double", "\u7a0e\u989d", 2),
        ("ticket_date", "date", "\u6536\u7968\u65e5\u671f", 20),
        ("supplier_name", "string", "\u5f00\u7968\u65b9\u540d\u79f0", 255),
        ("check_status", "string", "\u6838\u9a8c\u72b6\u6001", 32),
        ("pay_no", "string", "\u5173\u8054\u4ed8\u6b3e\u5355\u53f7", 64),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u76f8\u5173\u8fdb\u9879\u7968\u636e\u767b\u8bb0\u4e0e\u6838\u9a8c",
)

# --- 8.7 签约方档案表 -----------------------------------------------------
TABLE_PARTNER = table(
    TABLE_PARTNER_ID, "\u7b7e\u7ea6\u65b9\u6863\u6848\u8868",
    [
        ("id", "string", "ID", 64),
        ("partner_no", "string", "\u7b7e\u7ea6\u65b9\u7f16\u53f7", 64),
        ("partner_name", "string", "\u7b7e\u7ea6\u65b9\u540d\u79f0", 255),
        ("partner_type", "string", "\u7b7e\u7ea6\u65b9\u7c7b\u578b", 64),
        ("credit_code", "string", "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801", 64),
        ("legal_person", "string", "\u6cd5\u5b9a\u4ee3\u8868\u4eba", 64),
        ("reg_capital", "double", "\u6ce8\u518c\u8d44\u672c", 2),
        ("found_date", "date", "\u6210\u7acb\u65e5\u671f", 20),
        ("address", "string", "\u6ce8\u518c\u5730\u5740", 255),
        ("contact_name", "string", "\u8054\u7cfb\u4eba", 64),
        ("contact_phone", "string", "\u8054\u7cfb\u7535\u8bdd", 64),
        ("contact_email", "string", "\u8054\u7cfb\u90ae\u7bb1", 128),
        ("bank_name", "string", "\u5f00\u6237\u884c", 255),
        ("bank_account", "string", "\u94f6\u884c\u8d26\u53f7", 64),
        ("tax_no", "string", "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7", 64),
        ("qualification", "text", "\u8d44\u8d28\u8bc1\u4e66", 2000),
        ("partner_level", "string", "\u4fe1\u7528\u7b49\u7ea7", 32),
        ("partner_status", "string", "\u6863\u6848\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u7b7e\u7ea6\u5bf9\u65b9\uff08\u4f9b\u5e94\u5546/\u5ba2\u6237\uff09\u6863\u6848\u4e3b\u8868\uff0c\u4f9b\u5408\u540c\u3001\u91c7\u8d2d\u3001\u4ed8\u6b3e\u5f15\u7528",
)

# --- 8.8 合同变更记录表 ---------------------------------------------------
TABLE_CHANGE = table(
    TABLE_CHANGE_ID, "\u5408\u540c\u53d8\u66f4\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("change_no", "string", "\u53d8\u66f4\u5355\u53f7", 64),
        ("contract_no", "string", "\u5408\u540c\u7f16\u53f7", 64),
        ("contract_name", "string", "\u5408\u540c\u540d\u79f0", 255),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("change_type", "string", "\u53d8\u66f4\u7c7b\u578b", 64),
        ("before_status", "string", "\u53d8\u66f4\u524d\u72b6\u6001", 32),
        ("after_status", "string", "\u53d8\u66f4\u540e\u72b6\u6001", 32),
        ("before_amount", "double", "\u53d8\u66f4\u524d\u91d1\u989d", 2),
        ("after_amount", "double", "\u53d8\u66f4\u540e\u91d1\u989d", 2),
        ("change_amount", "double", "\u53d8\u66f4\u5dee\u989d", 2),
        ("change_date", "date", "\u53d8\u66f4\u65e5\u671f", 20),
        ("change_reason", "text", "\u53d8\u66f4\u539f\u56e0", 2000),
        ("approve_status", "string", "\u5ba1\u6279\u72b6\u6001", 32),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5408\u540c\u4fe1\u606f\u53d8\u66f4\u4e0e\u72b6\u6001\u53d8\u66f4\u7684\u5168\u91cf\u7559\u75d5\u8bb0\u5f55",
)

TABLES = [
    TABLE_CONTRACT, TABLE_RECEIVE_PLAN, TABLE_RECEIVE, TABLE_INVOICE,
    TABLE_PAY, TABLE_TICKET, TABLE_PARTNER, TABLE_CHANGE,
]

# ==========================================================================
# 视图（9 个）
# --------------------------------------------------------------------------
# 严格对齐官方列表页实测规范（截图 1656385113266）：
#   顶部      工具栏按钮组（14 个，顺序照抄官方）
#   工具栏下  搜索栏：输入关键字搜索视图 + [高级搜索]
#   中部      表格（列顺序 = 官方表格列顺序）
#   底部      分页：第一页 · 上一页 · (1) · 下一页 · 最后一页
# ==========================================================================

VIEW_CONTRACT_LIST_ID = "v2002001-contract-list-view-0000000001"
VIEW_RECEIVE_PLAN_ID = "v2002002-contract-receive-plan-view-00001"
VIEW_RECEIVE_ID = "v2002003-contract-receive-view-0000000001"
VIEW_INVOICE_ID = "v2002004-contract-invoice-view-0000000001"
VIEW_PAY_PLAN_ID = "v2002005-contract-pay-plan-view-00000001"
VIEW_PAY_ID = "v2002006-contract-pay-view-0000000000001"
VIEW_TICKET_ID = "v2002007-contract-ticket-view-0000000001"
VIEW_PARTNER_ID = "v2002008-contract-partner-view-000000001"
VIEW_EXPIRE_ID = "v2002009-contract-expire-view-0000000001"


def _list_props(page_size=20):
    """官方列表页标准属性：搜索栏 + 分页 + 操作条 + 导出Excel。"""
    return {
        "isExport": True,
        "isSearch": True,
        "searchPlaceholder": "\u8f93\u5165\u5173\u952e\u5b57\u641c\u7d22\u89c6\u56fe",
        "isAdvanceSearch": True,
        "isSelectAll": True,
        "isPage": True,
        "pageSize": page_size,
        "showPageBar": True,
        "pageBarButtons": [
            "\u7b2c\u4e00\u9875", "\u4e0a\u4e00\u9875", "\u4e0b\u4e00\u9875", "\u6700\u540e\u4e00\u9875",
        ],
        "showOperateBar": True,
        "operateBarWidth": "150px",
        "rowHeight": "36px",
        "striped": True,
        "bordered": True,
        "hoverable": True,
    }


# --- 工具栏按钮组（官方截图 1656385113266 顺序）---------------------------
CONTRACT_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("supplement", "\u5408\u540c\u8865\u5f55", "process", PROC_SUPPLEMENT_ID),
    ("change", "\u53d1\u8d77\u4fe1\u606f\u53d8\u66f4", "process", PROC_CONTRACT_CHANGE_ID),
    ("status", "\u53d1\u8d77\u72b6\u6001\u53d8\u66f4", "process", PROC_CONTRACT_STATUS_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
    ("receivePlan", "\u53d1\u8d77\u6536\u6b3e\u8ba1\u5212\u7f16\u5236", "process", PROC_RECEIVE_PLAN_ID),
    ("receiveChange", "\u53d1\u8d77\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4", "process", PROC_RECEIVE_CHANGE_ID),
    ("receive", "\u5408\u540c\u6536\u6b3e", "process", PROC_RECEIVE_ID),
    ("invoice", "\u5f00\u7968\u7533\u8bf7", "process", PROC_INVOICE_ID),
    ("payPlan", "\u53d1\u8d77\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236", "process", PROC_PAY_PLAN_ID),
    ("payChange", "\u53d1\u8d77\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4", "process", PROC_PAY_CHANGE_ID),
    ("pay", "\u5408\u540c\u4ed8\u6b3e", "process", PROC_PAY_ID),
    ("ticket", "\u6536\u7968\u8bb0\u5f55", "process", PROC_TICKET_ID),
]


def _toolbar_buttons(items):
    out = []
    for i, (bid, title, btype, target) in enumerate(items):
        out.append({
            "id": "btn_%s" % bid,
            "name": title,
            "title": title,
            "type": btype,
            "target": target,
            "icon": "",
            "order": i,
            "style": {
                "border": "1px solid #a8c7e8",
                "background": "#f2f7fd",
                "color": "#1a5fa8",
                "borderRadius": "3px",
                "padding": "4px 12px",
                "marginRight": "6px",
                "height": "28px",
                "lineHeight": "20px",
                "fontSize": "13px",
                "cursor": "pointer",
            },
        })
    return out


def _apply_toolbar(v, items):
    v["toolbarButtonList"] = _toolbar_buttons(items)
    v["properties"]["toolbarButtonList"] = v["toolbarButtonList"]
    return v


# --- 9.1 合同档案（主台账）------------------------------------------------
VIEW_CONTRACT_LIST = _apply_toolbar(view(
    VIEW_CONTRACT_LIST_ID, "\u5408\u540c\u6863\u6848",
    description="\u5408\u540c\u53f0\u8d26\u5217\u8868\uff0c\u5217\u987a\u5e8f\u4e25\u683c\u5bf9\u9f50\u5b98\u65b9\u622a\u56fe",
    source="process",
    process_list=[PROC_CONTRACT_ID, PROC_SUPPLEMENT_ID,
                  PROC_CONTRACT_CHANGE_ID, PROC_CONTRACT_STATUS_ID],
    table_list=[TABLE_CONTRACT_ID],
    columns=[
        ("\u5408\u540c\u540d\u79f0", "contract_name", "220px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u7b7e\u7ea6\u5355\u4f4d", "sign_unit", "200px"),
        ("\u7b7e\u8ba2\u65e5\u671f", "sign_date", "120px"),
        ("\u7ecf\u529e\u90e8\u95e8", "handle_dept", "140px"),
        ("\u7ecf\u529e\u4eba\u5458", "handle_person", "120px"),
        ("\u5408\u540c\u72b6\u6001", "contract_status", "110px"),
        ("\u5408\u540c\u91d1\u989d", "contract_amount", "140px"),
        ("\u5173\u8054\u9879\u76ee", "project_no", "160px"),
    ],
    order_by="sign_date desc",
), CONTRACT_TOOLBAR)
VIEW_CONTRACT_LIST["properties"] = _list_props(20)


# --- 9.2 收款计划 ---------------------------------------------------------
VIEW_RECEIVE_PLAN = view(
    VIEW_RECEIVE_PLAN_ID, "\u6536\u6b3e\u8ba1\u5212",
    description="\u5408\u540c\u5206\u671f\u6536\u6b3e\u8ba1\u5212\u5217\u8868",
    source="process",
    process_list=[PROC_RECEIVE_PLAN_ID, PROC_RECEIVE_CHANGE_ID],
    table_list=[TABLE_RECEIVE_PLAN_ID],
    columns=[
        ("\u8ba1\u5212\u7f16\u53f7", "plan_no", "160px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u671f\u6b21", "period_index", "70px"),
        ("\u671f\u6b21\u540d\u79f0", "period_name", "150px"),
        ("\u5360\u6bd4%", "plan_ratio", "90px"),
        ("\u8ba1\u5212\u91d1\u989d", "plan_amount", "140px"),
        ("\u8ba1\u5212\u6536\u6b3e\u65e5\u671f", "plan_date", "140px"),
        ("\u5df2\u6536\u91d1\u989d", "received_amount", "140px"),
        ("\u8ba1\u5212\u72b6\u6001", "plan_status", "110px"),
    ],
    order_by="plan_date asc",
)
VIEW_RECEIVE_PLAN["properties"] = _list_props(20)
_apply_toolbar(VIEW_RECEIVE_PLAN, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
    ("receiveChange", "\u53d1\u8d77\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4", "process", PROC_RECEIVE_CHANGE_ID),
    ("receive", "\u5408\u540c\u6536\u6b3e", "process", PROC_RECEIVE_ID),
])


# --- 9.3 合同收款 ---------------------------------------------------------
VIEW_RECEIVE = view(
    VIEW_RECEIVE_ID, "\u5408\u540c\u6536\u6b3e",
    description="\u5408\u540c\u56de\u6b3e\u767b\u8bb0\u5217\u8868",
    source="process",
    process_list=[PROC_RECEIVE_ID],
    table_list=[TABLE_RECEIVE_ID],
    columns=[
        ("\u6536\u6b3e\u5355\u53f7", "receive_no", "160px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u5408\u540c\u540d\u79f0", "contract_name", "200px"),
        ("\u6536\u6b3e\u7c7b\u578b", "receive_type", "120px"),
        ("\u6536\u6b3e\u91d1\u989d", "receive_amount", "140px"),
        ("\u6536\u6b3e\u65e5\u671f", "receive_date", "120px"),
        ("\u4ed8\u6b3e\u65b9\u540d\u79f0", "payer_name", "200px"),
        ("\u51ed\u8bc1\u53f7", "voucher_no", "140px"),
        ("\u6536\u6b3e\u72b6\u6001", "receive_status", "110px"),
    ],
    order_by="receive_date desc",
)
VIEW_RECEIVE["properties"] = _list_props(20)
_apply_toolbar(VIEW_RECEIVE, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("receive", "\u5408\u540c\u6536\u6b3e", "process", PROC_RECEIVE_ID),
    ("invoice", "\u5f00\u7968\u7533\u8bf7", "process", PROC_INVOICE_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
])


# --- 9.4 开票申请 ---------------------------------------------------------
VIEW_INVOICE = view(
    VIEW_INVOICE_ID, "\u5f00\u7968\u7533\u8bf7",
    description="\u5408\u540c\u5f00\u7968\u7533\u8bf7\u4e0e\u53d1\u7968\u767b\u8bb0\u5217\u8868",
    source="process",
    process_list=[PROC_INVOICE_ID],
    table_list=[TABLE_INVOICE_ID],
    columns=[
        ("\u5f00\u7968\u7533\u8bf7\u5355\u53f7", "invoice_apply_no", "170px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u53d1\u7968\u7c7b\u578b", "invoice_type", "120px"),
        ("\u5f00\u7968\u91d1\u989d", "invoice_amount", "140px"),
        ("\u7a0e\u989d", "tax_amount", "120px"),
        ("\u8d2d\u65b9\u540d\u79f0", "buyer_name", "200px"),
        ("\u53d1\u7968\u53f7\u7801", "invoice_no", "150px"),
        ("\u5f00\u7968\u65e5\u671f", "invoice_date", "120px"),
        ("\u7533\u8bf7\u72b6\u6001", "apply_status", "110px"),
    ],
    order_by="invoice_date desc",
)
VIEW_INVOICE["properties"] = _list_props(20)
_apply_toolbar(VIEW_INVOICE, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("invoice", "\u5f00\u7968\u7533\u8bf7", "process", PROC_INVOICE_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
])


# --- 9.5 付款计划 ---------------------------------------------------------
VIEW_PAY_PLAN = view(
    VIEW_PAY_PLAN_ID, "\u4ed8\u6b3e\u8ba1\u5212",
    description="\u5408\u540c\u5206\u671f\u4ed8\u6b3e\u8ba1\u5212\u5217\u8868",
    source="process",
    process_list=[PROC_PAY_PLAN_ID, PROC_PAY_CHANGE_ID],
    table_list=[TABLE_PAY_ID],
    columns=[
        ("\u8ba1\u5212\u7f16\u53f7", "pay_plan_no", "160px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u5173\u8054\u9884\u7b97", "budget_no", "160px"),
        ("\u4ed8\u6b3e\u7c7b\u578b", "pay_type", "120px"),
        ("\u8ba1\u5212\u91d1\u989d", "plan_amount", "140px"),
        ("\u8ba1\u5212\u4ed8\u6b3e\u65e5\u671f", "plan_date", "140px"),
        ("\u5df2\u4ed8\u91d1\u989d", "paid_amount", "140px"),
        ("\u8ba1\u5212\u72b6\u6001", "plan_status", "110px"),
    ],
    order_by="plan_date asc",
)
VIEW_PAY_PLAN["properties"] = _list_props(20)
_apply_toolbar(VIEW_PAY_PLAN, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
    ("payChange", "\u53d1\u8d77\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4", "process", PROC_PAY_CHANGE_ID),
    ("pay", "\u5408\u540c\u4ed8\u6b3e", "process", PROC_PAY_ID),
])


# --- 9.6 合同付款 ---------------------------------------------------------
VIEW_PAY = view(
    VIEW_PAY_ID, "\u5408\u540c\u4ed8\u6b3e",
    description="\u5408\u540c\u4ed8\u6b3e\u767b\u8bb0\u5217\u8868\uff08\u4e09\u65b9\u6302\u9760\uff09",
    source="process",
    process_list=[PROC_PAY_ID],
    table_list=[TABLE_PAY_ID],
    columns=[
        ("\u4ed8\u6b3e\u5355\u53f7", "pay_no", "160px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u5408\u540c\u540d\u79f0", "contract_name", "200px"),
        ("\u5173\u8054\u9884\u7b97", "budget_no", "160px"),
        ("\u4ed8\u6b3e\u7c7b\u578b", "pay_type", "120px"),
        ("\u4ed8\u6b3e\u91d1\u989d", "pay_amount", "140px"),
        ("\u4ed8\u6b3e\u65e5\u671f", "pay_date", "120px"),
        ("\u6536\u6b3e\u65b9\u540d\u79f0", "payee_name", "200px"),
        ("\u4ed8\u6b3e\u72b6\u6001", "pay_status", "110px"),
    ],
    order_by="pay_date desc",
)
VIEW_PAY["properties"] = _list_props(20)
_apply_toolbar(VIEW_PAY, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("pay", "\u5408\u540c\u4ed8\u6b3e", "process", PROC_PAY_ID),
    ("ticket", "\u6536\u7968\u8bb0\u5f55", "process", PROC_TICKET_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
])


# --- 9.7 收票记录 ---------------------------------------------------------
VIEW_TICKET = view(
    VIEW_TICKET_ID, "\u6536\u7968\u8bb0\u5f55",
    description="\u5408\u540c\u8fdb\u9879\u7968\u636e\u767b\u8bb0\u5217\u8868",
    source="process",
    process_list=[PROC_TICKET_ID],
    table_list=[TABLE_TICKET_ID],
    columns=[
        ("\u6536\u7968\u5355\u53f7", "ticket_no", "160px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u53d1\u7968\u53f7\u7801", "invoice_no", "150px"),
        ("\u7968\u636e\u7c7b\u578b", "ticket_type", "120px"),
        ("\u7968\u636e\u91d1\u989d", "ticket_amount", "140px"),
        ("\u7a0e\u989d", "tax_amount", "120px"),
        ("\u6536\u7968\u65e5\u671f", "ticket_date", "120px"),
        ("\u5f00\u7968\u65b9\u540d\u79f0", "supplier_name", "200px"),
        ("\u6838\u9a8c\u72b6\u6001", "check_status", "110px"),
    ],
    order_by="ticket_date desc",
)
VIEW_TICKET["properties"] = _list_props(20)
_apply_toolbar(VIEW_TICKET, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("ticket", "\u6536\u7968\u8bb0\u5f55", "process", PROC_TICKET_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
])


# --- 9.8 签约方档案 -------------------------------------------------------
VIEW_PARTNER = view(
    VIEW_PARTNER_ID, "\u7b7e\u7ea6\u65b9\u6863\u6848",
    description="\u7b7e\u7ea6\u5bf9\u65b9\u6863\u6848\u5217\u8868",
    source="process",
    process_list=[PROC_PARTNER_ID],
    table_list=[TABLE_PARTNER_ID],
    columns=[
        ("\u7b7e\u7ea6\u65b9\u540d\u79f0", "partner_name", "240px"),
        ("\u7b7e\u7ea6\u65b9\u7f16\u53f7", "partner_no", "160px"),
        ("\u7b7e\u7ea6\u65b9\u7c7b\u578b", "partner_type", "120px"),
        ("\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801", "credit_code", "190px"),
        ("\u6cd5\u5b9a\u4ee3\u8868\u4eba", "legal_person", "110px"),
        ("\u8054\u7cfb\u4eba", "contact_name", "100px"),
        ("\u8054\u7cfb\u7535\u8bdd", "contact_phone", "130px"),
        ("\u4fe1\u7528\u7b49\u7ea7", "partner_level", "100px"),
        ("\u6863\u6848\u72b6\u6001", "partner_status", "110px"),
    ],
    order_by="partner_no asc",
)
VIEW_PARTNER["properties"] = _list_props(20)
_apply_toolbar(VIEW_PARTNER, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("partner", "\u7b7e\u7ea6\u65b9\u6863\u6848\u767b\u8bb0", "process", PROC_PARTNER_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
])


# --- 9.9 合同到期预警（官方门户「更多 >>」下钻页）-------------------------
VIEW_EXPIRE = view(
    VIEW_EXPIRE_ID, "\u5408\u540c\u5230\u671f\u9884\u8b66",
    description="90 \u5929\u5185\u5230\u671f\u7684\u5c65\u884c\u4e2d\u5408\u540c\u6e05\u5355",
    source="table",
    table_list=[TABLE_CONTRACT_ID],
    columns=[
        ("\u5408\u540c\u540d\u79f0", "contract_name", "220px"),
        ("\u5408\u540c\u7f16\u53f7", "contract_no", "160px"),
        ("\u7b7e\u7ea6\u5355\u4f4d", "sign_unit", "200px"),
        ("\u5230\u671f\u65e5\u671f", "end_date", "120px"),
        ("\u5c65\u7ea6\u8fdb\u5ea6%", "perform_rate", "110px"),
        ("\u5408\u540c\u91d1\u989d", "contract_amount", "140px"),
        ("\u5408\u540c\u72b6\u6001", "contract_status", "110px"),
    ],
    filter_script=(
        "return (this.data.contract_status === '\u5c65\u884c\u4e2d') && "
        "(this.data.end_date !== null) && "
        "(new Date(this.data.end_date).getTime() - new Date().getTime() "
        "<= 90*24*3600*1000);"
    ),
    order_by="end_date asc",
)
VIEW_EXPIRE["properties"] = _list_props(20)
_apply_toolbar(VIEW_EXPIRE, [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("receivePlan", "\u53d1\u8d77\u6536\u6b3e\u8ba1\u5212\u7f16\u5236", "process", PROC_RECEIVE_PLAN_ID),
    ("payPlan", "\u53d1\u8d77\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236", "process", PROC_PAY_PLAN_ID),
])

VIEWS = [
    VIEW_CONTRACT_LIST, VIEW_RECEIVE_PLAN, VIEW_RECEIVE, VIEW_INVOICE,
    VIEW_PAY_PLAN, VIEW_PAY, VIEW_TICKET, VIEW_PARTNER, VIEW_EXPIRE,
]

# ==========================================================================
# 统计（8 个）
# --------------------------------------------------------------------------
# 官方门户首页（截图 1656385113300）实测两张图：
#   ① 按状态统计合同数量 —— 饼图，图例：履行中 / 已终止 / 已解除 / 已中止
#   ② 按状态统计合同金额 —— 柱图
# 页面切换按钮：饼状图 / 行列转换      卡片右上：更多 >>
# 本应用把这两张官方图作为 1、2 号统计，另补 6 张业务统计。
# ==========================================================================

STAT_CONTRACT_COUNT_ID = "s2002001-contract-count-by-status-00001"
STAT_CONTRACT_AMOUNT_ID = "s2002002-contract-amount-by-status-0001"
STAT_CONTRACT_TYPE_ID = "s2002003-contract-amount-by-type-000001"
STAT_CONTRACT_DEPT_ID = "s2002004-contract-amount-by-dept-000001"
STAT_RECEIVE_MONTH_ID = "s2002005-contract-receive-by-month-0001"
STAT_PAY_MONTH_ID = "s2002006-contract-pay-by-month-00000001"
STAT_INVOICE_TYPE_ID = "s2002007-contract-invoice-by-type-00001"
STAT_PARTNER_TYPE_ID = "s2002008-partner-count-by-type-0000001"

# --- 8.1 按状态统计合同数量（官方图①，饼图）-------------------------------
STAT_CONTRACT_COUNT = stat(
    STAT_CONTRACT_COUNT_ID,
    "\u6309\u72b6\u6001\u7edf\u8ba1\u5408\u540c\u6570\u91cf",
    VIEW_CONTRACT_LIST_ID, "contract_status", "count",
    description="\u5b98\u65b9\u95e8\u6237\u9996\u9875\u997c\u56fe\uff1a\u5c65\u884c\u4e2d / \u5df2\u7ec8\u6b62 / \u5df2\u89e3\u9664 / \u5df2\u4e2d\u6b62",
    category_title="\u5408\u540c\u72b6\u6001", value_title="\u5408\u540c\u6570\u91cf",
)
STAT_CONTRACT_COUNT["chartType"] = "pie"
STAT_CONTRACT_COUNT["properties"].update({
    "chartTypes": ["pie", "column"],
    "defaultChartType": "pie",
    "legendPosition": "bottom",
    "showLegend": True,
    "showLabel": True,
    "isRowColumnConvert": True,
    "moreLink": VIEW_CONTRACT_LIST_ID,
})

# --- 8.2 按状态统计合同金额（官方图②，柱图）-------------------------------
STAT_CONTRACT_AMOUNT = stat(
    STAT_CONTRACT_AMOUNT_ID,
    "\u6309\u72b6\u6001\u7edf\u8ba1\u5408\u540c\u91d1\u989d",
    VIEW_CONTRACT_LIST_ID, "contract_status", "contract_amount",
    description="\u5b98\u65b9\u95e8\u6237\u9996\u9875\u67f1\u56fe\uff1a\u5404\u72b6\u6001\u4e0b\u7684\u5408\u540c\u91d1\u989d\u5408\u8ba1",
    category_title="\u5408\u540c\u72b6\u6001", value_title="\u5408\u540c\u91d1\u989d\uff08\u5143\uff09",
)
STAT_CONTRACT_AMOUNT["chartType"] = "column"
STAT_CONTRACT_AMOUNT["properties"].update({
    "chartTypes": ["column", "pie", "bar"],
    "defaultChartType": "column",
    "showLegend": True,
    "showLabel": True,
    "isRowColumnConvert": True,
    "moreLink": VIEW_CONTRACT_LIST_ID,
})

# --- 8.3 按合同类型统计金额 -----------------------------------------------
STAT_CONTRACT_TYPE = stat(
    STAT_CONTRACT_TYPE_ID,
    "\u6309\u5408\u540c\u7c7b\u578b\u7edf\u8ba1\u91d1\u989d",
    VIEW_CONTRACT_LIST_ID, "contract_type", "contract_amount",
    description="\u91c7\u8d2d/\u9500\u552e/\u59d4\u5916/\u79df\u8d41\u7b49\u7c7b\u578b\u7684\u91d1\u989d\u5206\u5e03",
    category_title="\u5408\u540c\u7c7b\u578b", value_title="\u5408\u540c\u91d1\u989d\uff08\u5143\uff09",
)
STAT_CONTRACT_TYPE["properties"].update({"defaultChartType": "pie"})

# --- 8.4 按经办部门统计金额 -----------------------------------------------
STAT_CONTRACT_DEPT = stat(
    STAT_CONTRACT_DEPT_ID,
    "\u6309\u7ecf\u529e\u90e8\u95e8\u7edf\u8ba1\u91d1\u989d",
    VIEW_CONTRACT_LIST_ID, "handle_dept", "contract_amount",
    description="\u5404\u7ecf\u529e\u90e8\u95e8\u627f\u62c5\u7684\u5408\u540c\u91d1\u989d",
    category_title="\u7ecf\u529e\u90e8\u95e8", value_title="\u5408\u540c\u91d1\u989d\uff08\u5143\uff09",
)
STAT_CONTRACT_DEPT["properties"].update({"defaultChartType": "bar"})

# --- 8.5 收款趋势（按月）--------------------------------------------------
STAT_RECEIVE_MONTH = stat(
    STAT_RECEIVE_MONTH_ID,
    "\u5408\u540c\u6536\u6b3e\u8d8b\u52bf",
    VIEW_RECEIVE_ID, "receive_date", "receive_amount",
    description="\u6309\u6536\u6b3e\u65e5\u671f\u7edf\u8ba1\u56de\u6b3e\u91d1\u989d\uff0c\u8f93\u51fa\u8d8b\u52bf\u6298\u7ebf",
    category_title="\u6536\u6b3e\u65e5\u671f", value_title="\u6536\u6b3e\u91d1\u989d\uff08\u5143\uff09",
)
STAT_RECEIVE_MONTH["properties"].update({
    "defaultChartType": "line",
    "chartTypes": ["line", "column", "bar"],
})

# --- 8.6 付款趋势（按月）--------------------------------------------------
STAT_PAY_MONTH = stat(
    STAT_PAY_MONTH_ID,
    "\u5408\u540c\u4ed8\u6b3e\u8d8b\u52bf",
    VIEW_PAY_ID, "pay_date", "pay_amount",
    description="\u6309\u4ed8\u6b3e\u65e5\u671f\u7edf\u8ba1\u4ed8\u6b3e\u91d1\u989d\uff0c\u8f93\u51fa\u8d8b\u52bf\u6298\u7ebf",
    category_title="\u4ed8\u6b3e\u65e5\u671f", value_title="\u4ed8\u6b3e\u91d1\u989d\uff08\u5143\uff09",
)
STAT_PAY_MONTH["properties"].update({
    "defaultChartType": "line",
    "chartTypes": ["line", "column", "bar"],
})

# --- 8.7 发票类型分布 -----------------------------------------------------
STAT_INVOICE_TYPE = stat(
    STAT_INVOICE_TYPE_ID,
    "\u53d1\u7968\u7c7b\u578b\u5206\u5e03",
    VIEW_INVOICE_ID, "invoice_type", "invoice_amount",
    description="\u589e\u503c\u7a0e\u4e13\u7968/\u666e\u7968/\u7535\u5b50\u53d1\u7968\u7b49\u7c7b\u578b\u5f00\u7968\u91d1\u989d\u5206\u5e03",
    category_title="\u53d1\u7968\u7c7b\u578b", value_title="\u5f00\u7968\u91d1\u989d\uff08\u5143\uff09",
)
STAT_INVOICE_TYPE["properties"].update({"defaultChartType": "pie"})

# --- 8.8 签约方类型分布 ---------------------------------------------------
STAT_PARTNER_TYPE = stat(
    STAT_PARTNER_TYPE_ID,
    "\u7b7e\u7ea6\u65b9\u7c7b\u578b\u5206\u5e03",
    VIEW_PARTNER_ID, "partner_type", "count",
    description="\u4f9b\u5e94\u5546/\u5ba2\u6237/\u5408\u4f5c\u4f19\u4f34\u7b49\u7c7b\u578b\u7684\u7b7e\u7ea6\u65b9\u6570\u91cf",
    category_title="\u7b7e\u7ea6\u65b9\u7c7b\u578b", value_title="\u6570\u91cf",
)
STAT_PARTNER_TYPE["properties"].update({"defaultChartType": "pie"})

STATS = [
    STAT_CONTRACT_COUNT, STAT_CONTRACT_AMOUNT, STAT_CONTRACT_TYPE,
    STAT_CONTRACT_DEPT, STAT_RECEIVE_MONTH, STAT_PAY_MONTH,
    STAT_INVOICE_TYPE, STAT_PARTNER_TYPE,
]

# ==========================================================================
# 查询配置（9 条）
# --------------------------------------------------------------------------
# 注意：O2OA 校验读取的是 statement 字段（statement() 已同时写入 statement/sql）。
# 跨表 JOIN 是「数据共享」的落地载体 —— 下面 6 条为 JOIN 查询。
# 关联主干：contract_no（合同）
# ==========================================================================

STMT_CONTRACT_FULL_ID = "q2002001-contract-full-join-00000000001"
STMT_CONTRACT_PROJECT_ID = "q2002002-contract-project-join-0000001"
STMT_RECEIVE_PLAN_ID = "q2002003-receive-plan-join-0000000001"
STMT_RECEIVE_FULL_ID = "q2002004-receive-full-join-000000001"
STMT_PAY_FULL_ID = "q2002005-pay-full-join-0000000000001"
STMT_INVOICE_FULL_ID = "q2002006-invoice-full-join-000000001"
STMT_TICKET_FULL_ID = "q2002007-ticket-full-join-0000000001"
STMT_PARTNER_CONTRACT_ID = "q2002008-partner-contract-join-00001"
STMT_PERFORM_SUMMARY_ID = "q2002009-contract-perform-summary-0001"

# --- 9.1 合同台账全量（合同主表 ⟕ 签约方档案）-----------------------------
STMT_CONTRACT_FULL = statement(
    STMT_CONTRACT_FULL_ID,
    "\u5408\u540c\u53f0\u8d26\u5168\u91cf\uff08\u542b\u7b7e\u7ea6\u65b9\uff09",
    "SELECT c.id AS id, c.contract_no AS contract_no, "
    "c.contract_name AS contract_name, c.contract_type AS contract_type, "
    "c.sign_unit AS sign_unit, c.sign_date AS sign_date, "
    "c.handle_dept AS handle_dept, c.handle_person AS handle_person, "
    "c.contract_amount AS contract_amount, c.contract_status AS contract_status, "
    "c.start_date AS start_date, c.end_date AS end_date, "
    "c.perform_rate AS perform_rate, c.receive_total AS receive_total, "
    "c.pay_total AS pay_total, c.invoice_total AS invoice_total, "
    "p.partner_no AS partner_no, p.partner_type AS partner_type, "
    "p.credit_code AS credit_code, p.contact_name AS contact_name, "
    "p.contact_phone AS contact_phone, p.partner_level AS partner_level "
    "FROM contract_main c "
    "LEFT JOIN contract_partner p ON p.partner_no = c.partner_no",
    description="\u5408\u540c\u4e3b\u8868\u5de6\u8fde\u63a5\u7b7e\u7ea6\u65b9\u6863\u6848\uff0c\u4f9b\u5408\u540c\u6863\u6848\u89c6\u56fe\u4f7f\u7528",
    query_type="sql",
)

# --- 9.2 合同 ⟕ 项目（跨应用：项目管理）----------------------------------
STMT_CONTRACT_PROJECT = statement(
    STMT_CONTRACT_PROJECT_ID,
    "\u5408\u540c\u5173\u8054\u9879\u76ee\u660e\u7ec6",
    "SELECT c.contract_no AS contract_no, c.contract_name AS contract_name, "
    "c.contract_amount AS contract_amount, c.contract_status AS contract_status, "
    "c.project_no AS project_no, c.sign_unit AS sign_unit, "
    "p.project_name AS project_name, p.manager AS project_manager, "
    "p.total_budget AS project_budget, p.project_status AS project_status "
    "FROM contract_main c "
    "LEFT JOIN project_master p ON p.project_no = c.project_no",
    description="\u5408\u540c\u4e0e\u9879\u76ee\u7ba1\u7406\u5e94\u7528\u7684\u6570\u636e\u5171\u4eab\u67e5\u8be2\uff08\u6838\u5fc3\u8de8\u5e94\u7528\u5173\u8054\uff09",
    query_type="sql",
)

# --- 9.3 收款计划 ⟕ 合同 --------------------------------------------------
STMT_RECEIVE_PLAN = statement(
    STMT_RECEIVE_PLAN_ID,
    "\u6536\u6b3e\u8ba1\u5212\u5173\u8054\u5408\u540c",
    "SELECT r.id AS id, r.plan_no AS plan_no, r.contract_no AS contract_no, "
    "r.period_index AS period_index, r.period_name AS period_name, "
    "r.plan_ratio AS plan_ratio, r.plan_amount AS plan_amount, "
    "r.plan_date AS plan_date, r.received_amount AS received_amount, "
    "r.plan_status AS plan_status, "
    "c.contract_name AS contract_name, c.sign_unit AS sign_unit, "
    "c.contract_status AS contract_status, c.project_no AS project_no "
    "FROM contract_receive_plan r "
    "LEFT JOIN contract_main c ON c.contract_no = r.contract_no",
    description="\u6536\u6b3e\u8ba1\u5212\u660e\u7ec6\u5e26\u5408\u540c\u4fe1\u606f",
    query_type="sql",
)

# --- 9.4 合同收款 ⟕ 合同 ⟕ 收款计划 --------------------------------------
STMT_RECEIVE_FULL = statement(
    STMT_RECEIVE_FULL_ID,
    "\u5408\u540c\u6536\u6b3e\u5168\u91cf",
    "SELECT rv.id AS id, rv.receive_no AS receive_no, "
    "rv.contract_no AS contract_no, rv.receive_type AS receive_type, "
    "rv.receive_amount AS receive_amount, rv.receive_date AS receive_date, "
    "rv.payer_name AS payer_name, rv.voucher_no AS voucher_no, "
    "rv.receive_status AS receive_status, rv.expense_no AS expense_no, "
    "c.contract_name AS contract_name, c.project_no AS project_no, "
    "c.sign_unit AS sign_unit, c.handle_dept AS handle_dept, "
    "rp.plan_no AS plan_no, rp.period_name AS period_name, "
    "rp.plan_amount AS plan_amount "
    "FROM contract_receive rv "
    "LEFT JOIN contract_main c ON c.contract_no = rv.contract_no "
    "LEFT JOIN contract_receive_plan rp ON rp.plan_no = rv.plan_no",
    description="\u6536\u6b3e\u5355\u5e26\u5408\u540c\u4e0e\u8ba1\u5212\u4e09\u8868\u8054\u67e5\uff0cexpense_no \u5411\u8d22\u52a1\u63a8\u9001",
    query_type="sql",
)

# --- 9.5 合同付款 ⟕ 合同（三方挂靠）---------------------------------------
STMT_PAY_FULL = statement(
    STMT_PAY_FULL_ID,
    "\u5408\u540c\u4ed8\u6b3e\u5168\u91cf",
    "SELECT py.id AS id, py.pay_no AS pay_no, py.contract_no AS contract_no, "
    "py.budget_no AS budget_no, py.pay_plan_no AS pay_plan_no, "
    "py.pay_type AS pay_type, py.pay_amount AS pay_amount, "
    "py.pay_date AS pay_date, py.payee_name AS payee_name, "
    "py.pay_status AS pay_status, py.expense_no AS expense_no, "
    "c.contract_name AS contract_name, c.project_no AS project_no, "
    "c.sign_unit AS sign_unit, c.contract_amount AS contract_amount, "
    "c.pay_total AS pay_total "
    "FROM contract_pay py "
    "LEFT JOIN contract_main c ON c.contract_no = py.contract_no",
    description="\u4ed8\u6b3e\u5355\u5e26\u5408\u540c\u4e0e\u9884\u7b97\u4fe1\u606f\uff08project_no + budget_no + expense_no \u4e09\u65b9\u6302\u9760\uff09",
    query_type="sql",
)

# --- 9.6 开票申请 ⟕ 合同 --------------------------------------------------
STMT_INVOICE_FULL = statement(
    STMT_INVOICE_FULL_ID,
    "\u5f00\u7968\u7533\u8bf7\u5168\u91cf",
    "SELECT i.id AS id, i.invoice_apply_no AS invoice_apply_no, "
    "i.contract_no AS contract_no, i.invoice_type AS invoice_type, "
    "i.invoice_amount AS invoice_amount, i.tax_rate AS tax_rate, "
    "i.tax_amount AS tax_amount, i.net_amount AS net_amount, "
    "i.buyer_name AS buyer_name, i.buyer_tax_no AS buyer_tax_no, "
    "i.invoice_no AS invoice_no, i.invoice_date AS invoice_date, "
    "i.apply_status AS apply_status, "
    "c.contract_name AS contract_name, c.project_no AS project_no, "
    "c.contract_amount AS contract_amount, c.invoice_total AS invoice_total "
    "FROM contract_invoice i "
    "LEFT JOIN contract_main c ON c.contract_no = i.contract_no",
    description="\u5f00\u7968\u7533\u8bf7\u5e26\u5408\u540c\u4e0e\u7d2f\u8ba1\u5f00\u7968\u4fe1\u606f",
    query_type="sql",
)

# --- 9.7 收票记录 ⟕ 合同 ⟕ 付款 ------------------------------------------
STMT_TICKET_FULL = statement(
    STMT_TICKET_FULL_ID,
    "\u6536\u7968\u8bb0\u5f55\u5168\u91cf",
    "SELECT t.id AS id, t.ticket_no AS ticket_no, "
    "t.contract_no AS contract_no, t.invoice_no AS invoice_no, "
    "t.invoice_code AS invoice_code, t.ticket_type AS ticket_type, "
    "t.ticket_amount AS ticket_amount, t.tax_amount AS tax_amount, "
    "t.ticket_date AS ticket_date, t.supplier_name AS supplier_name, "
    "t.check_status AS check_status, t.pay_no AS pay_no, "
    "c.contract_name AS contract_name, c.project_no AS project_no, "
    "py.pay_amount AS pay_amount, py.pay_date AS pay_date "
    "FROM contract_ticket t "
    "LEFT JOIN contract_main c ON c.contract_no = t.contract_no "
    "LEFT JOIN contract_pay py ON py.pay_no = t.pay_no",
    description="\u8fdb\u9879\u7968\u636e\u5e26\u5408\u540c\u4e0e\u5bf9\u5e94\u4ed8\u6b3e\u5355",
    query_type="sql",
)

# --- 9.8 签约方履约画像（签约方 ⟕ 合同聚合）-------------------------------
STMT_PARTNER_CONTRACT = statement(
    STMT_PARTNER_CONTRACT_ID,
    "\u7b7e\u7ea6\u65b9\u5c65\u7ea6\u753b\u50cf",
    "SELECT p.partner_no AS partner_no, p.partner_name AS partner_name, "
    "p.partner_type AS partner_type, p.partner_level AS partner_level, "
    "p.credit_code AS credit_code, p.contact_name AS contact_name, "
    "p.contact_phone AS contact_phone, "
    "COUNT(c.contract_no) AS contract_count, "
    "SUM(c.contract_amount) AS total_amount, "
    "SUM(c.receive_total) AS total_receive, "
    "SUM(c.pay_total) AS total_pay "
    "FROM contract_partner p "
    "LEFT JOIN contract_main c ON c.partner_no = p.partner_no "
    "GROUP BY p.partner_no, p.partner_name, p.partner_type, "
    "p.partner_level, p.credit_code, p.contact_name, p.contact_phone",
    description="\u6bcf\u5bb6\u7b7e\u7ea6\u65b9\u7684\u5408\u540c\u6570\u91cf\u4e0e\u91d1\u989d\u805a\u5408\uff0c\u4f9b\u4f9b\u5e94\u5546\u8bc4\u4f30",
    query_type="sql",
)

# --- 9.9 合同履约汇总（单一合同收付票全景）--------------------------------
STMT_PERFORM_SUMMARY = statement(
    STMT_PERFORM_SUMMARY_ID,
    "\u5408\u540c\u5c65\u7ea6\u6c47\u603b",
    "SELECT c.contract_no AS contract_no, c.contract_name AS contract_name, "
    "c.project_no AS project_no, c.contract_amount AS contract_amount, "
    "c.contract_status AS contract_status, c.perform_rate AS perform_rate, "
    "c.receive_total AS receive_total, c.pay_total AS pay_total, "
    "c.invoice_total AS invoice_total, "
    "IFNULL(rp.plan_count, 0) AS plan_count, "
    "IFNULL(rp.plan_amount, 0) AS plan_amount, "
    "IFNULL(rc.receive_count, 0) AS receive_count, "
    "IFNULL(iv.invoice_count, 0) AS invoice_count "
    "FROM contract_main c "
    "LEFT JOIN (SELECT contract_no, COUNT(*) AS plan_count, "
    "           SUM(plan_amount) AS plan_amount "
    "           FROM contract_receive_plan GROUP BY contract_no) rp "
    "  ON rp.contract_no = c.contract_no "
    "LEFT JOIN (SELECT contract_no, COUNT(*) AS receive_count "
    "           FROM contract_receive GROUP BY contract_no) rc "
    "  ON rc.contract_no = c.contract_no "
    "LEFT JOIN (SELECT contract_no, COUNT(*) AS invoice_count "
    "           FROM contract_invoice GROUP BY contract_no) iv "
    "  ON iv.contract_no = c.contract_no",
    description="\u5355\u4e2a\u5408\u540c\u7684\u8ba1\u5212/\u6536\u6b3e/\u5f00\u7968\u5168\u666f\u6c47\u603b",
    query_type="sql",
)

STATEMENTS = [
    STMT_CONTRACT_FULL, STMT_CONTRACT_PROJECT, STMT_RECEIVE_PLAN,
    STMT_RECEIVE_FULL, STMT_PAY_FULL, STMT_INVOICE_FULL,
    STMT_TICKET_FULL, STMT_PARTNER_CONTRACT, STMT_PERFORM_SUMMARY,
]

# ==========================================================================
# 导出清单
# ==========================================================================

FORMS = [
    FORM_CONTRACT, FORM_CONTRACT_SUPPLEMENT, FORM_CONTRACT_CHANGE,
    FORM_CONTRACT_STATUS, FORM_RECEIVE_PLAN, FORM_RECEIVE_CHANGE,
    FORM_RECEIVE, FORM_INVOICE, FORM_PAY_PLAN, FORM_PAY_CHANGE,
    FORM_PAY, FORM_TICKET, FORM_PARTNER, FORM_CONFIG,
]

PROCESSES = [
    PROC_CONTRACT, PROC_SUPPLEMENT, PROC_CONTRACT_CHANGE,
    PROC_CONTRACT_STATUS, PROC_RECEIVE_PLAN, PROC_RECEIVE_CHANGE,
    PROC_RECEIVE, PROC_INVOICE, PROC_PAY_PLAN, PROC_PAY_CHANGE,
    PROC_PAY, PROC_TICKET, PROC_PARTNER,
]

# ==========================================================================
# 门户应用（Portal / Page）
# --------------------------------------------------------------------------
# 官方门户截图 refs/contract/1656385113300.jpg 实测版式：
#   左侧树导航（带角标数量）+ 右「待办事项(12) | 已办事项(6)」列表卡片
#   + 右下两张图（按状态统计合同数量饼图 / 按状态统计合同金额柱图）
# 页面 HTML 由 o2oa_portal 生成，Page.data 存储该 HTML **字符串**。
# ==========================================================================

import o2oa_portal as _PT
from o2oa_builder import portal, portal_page

PORTAL_ID = "o2002001-contract-portal-00000000000001"
PAGE_HOME_ID = "o2002002-contract-portal-home-page-000001"
PAGE_LIST_ID = "o2002003-contract-portal-list-page-000001"
PAGE_REPORT_ID = "o2002004-contract-portal-report-page-00001"
PAGE_QUICK_ID = "o2002005-contract-portal-quick-page-000001"

# --- 左侧导航树（照官方截图）----------------------------------------------
PORTAL_TREE = [
    (1, "\u5408\u540c\u7ba1\u7406\u9996\u9875", None, True),
    (1, "\u6863\u6848\u7ba1\u7406", None, False),
    (2, "\u53d1\u8d77\u5408\u540c\u5ba1\u6279\u6d41\u7a0b", None, False),
    (2, "\u5408\u540c\u6863\u6848", None, False),
    (2, "\u5408\u540c\u8865\u5f55", None, False),
    (2, "\u5408\u540c\u6863\u6848\u5bfc\u5165", None, False),
    (1, "\u8fc7\u7a0b\u7ba1\u7406", "07", False),
    (2, "\u4fe1\u606f\u53d8\u66f4", None, False),
    (2, "\u72b6\u6001\u53d8\u66f4", None, False),
    (1, "\u6536\u6b3e\u7ba1\u7406", "08", False),
    (2, "\u6536\u6b3e\u8ba1\u5212\u7f16\u5236", None, False),
    (2, "\u6536\u6b3e\u8ba1\u5212\u53d8\u66f4", None, False),
    (2, "\u5408\u540c\u6536\u6b3e", None, False),
    (2, "\u5f00\u7968\u7533\u8bf7", None, False),
    (1, "\u4ed8\u6b3e\u7ba1\u7406", None, False),
    (2, "\u4ed8\u6b3e\u8ba1\u5212\u7f16\u5236", None, False),
    (2, "\u4ed8\u6b3e\u8ba1\u5212\u53d8\u66f4", None, False),
    (2, "\u5408\u540c\u4ed8\u6b3e", None, False),
    (2, "\u6536\u7968\u8bb0\u5f55", None, False),
]

# --- 待办列表（脚本未生效时的降级内容）----------------------------------
# 全部取自协会真实业务：真实合同（HT2026-001/002）、真实流程名、真实经办人。
# 门户运行时脚本就绪后，整表会被「我的待办」实时数据替换。
PORTAL_TODO = [
    ("轻量化结构件工艺攻关技术服务合同 · 合同审批",
     "时晓明", "合同审批流程", "2026-09-18"),
    ("碳纤维回收工艺联合研发合同 · 合同审批",
     "杜阳", "合同审批流程", "2026-09-18"),
    ("轻量化结构件工艺攻关技术服务合同 · 收款计划编制",
     "李芳", "收款计划编制流程", "2026-09-17"),
    ("碳纤维回收工艺联合研发合同 · 付款计划编制",
     "罗舒涵", "付款计划编制流程", "2026-09-17"),
    ("碳纤维回收工艺联合研发合同 · 开票申请",
     "李静", "开票申请流程", "2026-09-16"),
    ("上海复材再生资源有限公司 · 签约方档案登记",
     "奚莎莎", "签约方档案登记流程", "2026-09-16"),
    ("轻量化结构件工艺攻关技术服务合同 · 收票记录",
     "赵旭东", "收票记录流程", "2026-09-15"),
    ("碳纤维回收工艺联合研发合同 · 合同信息变更",
     "李芳", "合同信息变更流程", "2026-09-15"),
]

# 官方门户两张图（图①饼图 / 图②柱图）。
# 分类与数值只是「脚本未生效」时的兜底；脚本会用
# 「合同台账全量（含签约方）」语句的实时数据重绘。
PORTAL_CHARTS = [
    ("按状态统计合同数量", "pie",
     [("履行中", 2), ("已完成", 0), ("已终止", 0), ("已解除", 0)], True),
    ("按类型统计合同金额", "column",
     [("技术服务", 118), ("合作研发", 85)], True),
]

PORTAL_QUICK = [
    ("合同台账", "#4a8fe7", "\u25A4"),
    ("收款计划", "#38b2ac", "\u25A4"),
    ("付款计划", "#ed8936", "\u25A4"),
    ("开票申请", "#9f7aea", "\u25A4"),
    ("收票记录", "#f6ad55", "\u25A4"),
    ("签约方档案", "#4299e1", "\u25A4"),
]

# 门户页面的日期文案（脚本会按当天覆写；这里只是兜底）
PORTAL_DATE_TEXT = "\u2014\u2014\u2014"

# 门户活数据源：待办 + 两张图分别挂到真实语句
_CT_Q = "q2002001-contract-full-join-00000000001"
_CT_CHART_SRC = {
    "按状态统计合同数量": {"statement": _CT_Q, "field": "contract_status", "value": ""},
    "按类型统计合同金额": {"statement": _CT_Q, "field": "contract_type",
                          "value": "contract_amount"},
}


def _ct_live(charts, todo_page=8):
    """按本页实际渲染的图表生成活数据源（idx 必须与页面图表顺序一致）。"""
    out = []
    for i, item in enumerate(charts):
        title, ctype = item[0], item[1]
        src = _CT_CHART_SRC.get(title)
        if not src:
            continue
        d = {"idx": i, "type": ctype, "title": title}
        d.update(src)
        out.append(d)
    return {"todo_page": todo_page, "charts": out}


PORTAL_LIVE = _ct_live(PORTAL_CHARTS)

# --- 门户导航点击映射：页面直达 / 发起流程 / 应用直达 --------------------
# （data-op 见 o2oa_portal._LIVE_JS 的统一点击接管层）
CONTRACT_NAV_MAP = {
    "合同管理首页": ("portal", PORTAL_ID, PAGE_HOME_ID),
    "合同台账": ("portal", PORTAL_ID, PAGE_LIST_ID),
    "统计报表": ("portal", PORTAL_ID, PAGE_REPORT_ID),
    "快捷入口": ("portal", PORTAL_ID, PAGE_QUICK_ID),
    "档案管理": ("app", "a5005000-archive-app-00000000000000001"),
    # ---- 左侧二级菜单：一键发起对应流程（真实业务直达） ----
    "发起合同审批流程": ("startone", PROC_CONTRACT_ID),
    "合同补录": ("startone", PROC_SUPPLEMENT_ID),
    "合同档案导入": ("portal", PORTAL_ID, PAGE_LIST_ID),
    "信息变更": ("startone", PROC_CONTRACT_CHANGE_ID),
    "状态变更": ("startone", PROC_CONTRACT_STATUS_ID),
    "收款计划编制": ("startone", PROC_RECEIVE_PLAN_ID),
    "收款计划变更": ("startone", PROC_RECEIVE_CHANGE_ID),
    "合同收款": ("startone", PROC_RECEIVE_ID),
    "开票申请": ("startone", PROC_INVOICE_ID),
    "付款计划编制": ("startone", PROC_PAY_PLAN_ID),
    "付款计划变更": ("startone", PROC_PAY_CHANGE_ID),
    "合同付款": ("startone", PROC_PAY_ID),
    "收票记录": ("startone", PROC_TICKET_ID),
    # ---- 快捷入口 6 图标 ----
    "收款计划": ("startone", PROC_RECEIVE_PLAN_ID),
    "付款计划": ("startone", PROC_PAY_PLAN_ID),
    "签约方档案": ("startone", PROC_PARTNER_ID),
}



PAGE_HOME_HTML = _PT.portal_page_html(
    "\u5408\u540c\u7ba1\u7406", PORTAL_TREE, PORTAL_TODO, PORTAL_CHARTS,
    PORTAL_QUICK, date_text=PORTAL_DATE_TEXT,
    live=_ct_live(PORTAL_CHARTS), nav_map=CONTRACT_NAV_MAP,
)

# 第二页：合同台账列表（数据取自真实合同主表种子）
_LEDGER_ROWS = [
    ("轻量化结构件工艺攻关技术服务合同", "HT2026-001",
     "北京中复新材料科技有限公司", "2026-01-05", "行业研究部", "时晓明", "履行中"),
    ("碳纤维回收工艺联合研发合同", "HT2026-002",
     "上海复材再生资源有限公司", "2026-02-20", "行业研究部", "杜阳", "履行中"),
]
# 合同台账页 —— 真实合同台账视图 + 到期提醒（原生 query.Viewer 加载）
PAGE_LIST_HTML = _PT.portal_page_html(
    "\u5408\u540c\u7ba1\u7406",
    [(1, "\u5408\u540c\u6863\u6848", None, True)] + PORTAL_TREE[1:],
    [], [], None, date_text=PORTAL_DATE_TEXT,
    live={k: v for k, v in _ct_live([]).items() if k != "todo_page"},
    nav_map=CONTRACT_NAV_MAP,
    content_html=_PT.action_bar([
        ("\u53d1\u8d77\u5408\u540c\u5ba1\u6279\u6d41\u7a0b", "startone", PROC_CONTRACT_ID, False),
        ("\u5408\u540c\u8865\u5f55", "startone", PROC_SUPPLEMENT_ID, True),
        ("\u4fe1\u606f\u53d8\u66f4", "startone", PROC_CONTRACT_CHANGE_ID, True),
    ])
    + _PT.table_holder(TABLE_CONTRACT_ID, [
        ("contract_no", "\u5408\u540c\u7f16\u53f7"), ("contract_name", "\u5408\u540c\u540d\u79f0"),
        ("contract_type", "\u7c7b\u578b"), ("project_no", "\u9879\u76ee\u7f16\u53f7"),
        ("sign_unit", "\u7b7e\u7ea6\u5355\u4f4d"),
        ("contract_amount", "\u5408\u540c\u91d1\u989d", "money"),
        ("receive_total", "\u5df2\u6536\u91d1\u989d", "money"),
        ("perform_rate", "\u5c65\u7ea6\u7387", "num"),
        ("contract_status", "\u72b6\u6001"),
    ], "\u5408\u540c\u53f0\u8d26\uff08\u5b9e\u65f6\u6570\u636e\uff09", height=430)
    + _PT.table_holder(TABLE_RECEIVE_ID, [
        ("receive_no", "\u6536\u6b3e\u5355\u53f7"), ("contract_no", "\u5408\u540c\u7f16\u53f7"),
        ("receive_type", "\u6536\u6b3e\u7c7b\u578b"),
        ("receive_amount", "\u6536\u6b3e\u91d1\u989d", "money"),
        ("receive_date", "\u5230\u8d26\u65e5\u671f", "date"),
        ("payer_name", "\u4ed8\u6b3e\u65b9"), ("receive_status", "\u72b6\u6001"),
    ], "\u5408\u540c\u6536\u6b3e\u8bb0\u5f55", height=280),
)

PAGE_REPORT_HTML = _PT.portal_page_html(
    "\u5408\u540c\u7ba1\u7406",
    [(1, "\u7edf\u8ba1\u62a5\u8868", None, True)] + PORTAL_TREE[1:],
    PORTAL_TODO[:4], PORTAL_CHARTS, None,
    date_text=PORTAL_DATE_TEXT, live=_ct_live(PORTAL_CHARTS),
    nav_map=CONTRACT_NAV_MAP,
)

PAGE_QUICK_HTML = _PT.portal_page_html(
    "\u5408\u540c\u7ba1\u7406",
    [(1, "\u5feb\u6377\u5165\u53e3", None, True)] + PORTAL_TREE[1:],
    PORTAL_TODO[:5], [], PORTAL_QUICK,
    date_text=PORTAL_DATE_TEXT, live=_ct_live([]),
    nav_map=CONTRACT_NAV_MAP,
)

def _pg(pid, name, html, desc):
    """独立 HTML 门户页 -> O2OA 门户页数据（表单定义 JSON）。

    O2OA 把门户页当表单渲染（PortalPage.js -> MWF.APPForm），
    裸 HTML 过不了 JSON.decode，门户里直接白屏。
    """
    return portal_page(pid, name, PORTAL_ID,
                       _PT.portal_page_data(html, pid, name, PORTAL_ID,
                                            "合同管理门户"),
                       description=desc)


PAGES = [
    _pg(PAGE_HOME_ID, "\u5408\u540c\u7ba1\u7406\u9996\u9875", PAGE_HOME_HTML, "\u5b98\u65b9\u98ce\u683c\u95e8\u6237\u9996\u9875"),
    _pg(PAGE_LIST_ID, "\u5408\u540c\u53f0\u8d26", PAGE_LIST_HTML, "\u5408\u540c\u53f0\u8d26\u5217\u8868"),
    _pg(PAGE_REPORT_ID, "\u7edf\u8ba1\u62a5\u8868", PAGE_REPORT_HTML, "\u5408\u540c\u7edf\u8ba1\u62a5\u8868"),
    _pg(PAGE_QUICK_ID, "\u5feb\u6377\u5165\u53e3", PAGE_QUICK_HTML, "\u5458\u5de5\u81ea\u52a9\u5feb\u6377\u5165\u53e3"),
]

PORTAL = portal(
    PORTAL_ID, "\u5408\u540c\u7ba1\u7406\u95e8\u6237",
    category="\u7efc\u5408\u7ba1\u7406",
    description="\u5408\u540c\u7ba1\u7406\u5e94\u7528\u95e8\u6237\uff08\u5bf9\u9f50 O2OA \u5b98\u65b9\u5408\u540c\u5e94\u7528\u95e8\u6237\u7248\u5f0f\uff09",
    first_page_id=PAGE_HOME_ID,
    pages=PAGES,
)

PORTALS = [PORTAL]

__all__ = [
    "APP_NAME", "APP_ID", "APP_ID_QUERY",
    "FORMS", "PROCESSES", "VIEWS", "STATS", "TABLES", "STATEMENTS",
    "PORTALS", "PORTAL_TREE",
]
