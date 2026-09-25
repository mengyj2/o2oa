# -*- coding: utf-8 -*-
"""
应用六：人力资源管理应用（完全对齐 O2OA 官方「人力资源管理系统」）
====================================================================

【官方结构参考】
来源：https://www.o2oa.net/market/app-b11ead15-5243-4e93-bdf0-cb854671b9b2.html
配图：refs/hr/1652073737656.png  HR 首页门户（矩阵式卡片）
      refs/hr/1652073737623.png  员工档案表单（六分区表格式）
      refs/hr/1652073737639.png  人才市场门户（岗位池）
      refs/hr/1652073737630.png  积分管理门户
      refs/hr/1652073737709.png  员工管理门户（四宫格公示）
      refs/hr/1652073737547.png  考勤管理页（考勤日历）
      refs/hr/1652073737833.png  员工自助列表页
      refs/hr/1652073737436.png  个人设置页

官方顶部一级导航（截图实读，共 8 项）：
    首页 | 员工档案 | 员工管理 | 人才市场 | 积分管理 | 考勤管理 |
    员工自助 | 个人设置

官方二级标签（截图 1652073737436 实读）：
    个人信息 | 界面配置 | 常用意见 | 外出授权 | 修改密码 | 单点登录 | 人脸登录

官方左侧导航树（截图实读）：
    员工档案页：
        我的档案 / 新建档案 / 导入档案
        ▼ 档案查询：全部档案 · 正式员工 · 试用期员工 · 实习期员工 · 离职员工
        ▼ 员工档案配置：用户权限设置 · 员工档案管理员
    考勤管理页：
        我的考勤 / 考勤统计 / ▼ 维护（数据导入 · 员工休假记录）
        / ▼ 权限和人员 / ▼ 配置

官方员工档案表单（截图 1652073737623 实读）——六大分区：
    ① 基本信息（两列表格式：姓名|性别、员工编号|员工状态、民族|政治面貌、
       出生日期|出生地、婚姻状态|移动电话|办公电话、微信|QQ|电子邮件、
       最高学历|最高学位|毕业院校、部门|职位|参加本单位时间）
    ② 本单位工作经历（Datagrid：部门|岗位|开始日期|结束日期|工作描述|类型）
    ③ 工作经历（Datagrid：公司|部门/岗位|开始日期|结束日期|工作描述）
    ④ 教育背景（Datagrid：入学日期|毕业日期|学校名称|专业|学历|学位）
    ⑤ 专业技术资格（Datagrid：专业技术资格名称|取得日期）
    ⑥ 奖励情况（Datagrid：获奖日期|获奖名称|颁发单位|奖励类型|获奖级别）

官方门户卡片矩阵（截图 1652073737656 实读，3 列 × 多行）：
    第 1 行：新闻公告（大图卡） | 员工自助（6 个彩色圆角图标）
    第 2 行：人事变动公示 | 待办工作 | 岗位报名
    第 3 行：积分公示 | 待阅工作 | 本月考勤（小月历）

【数据联系】
employee_no 是人力资源应用的主键，同时作为**全局人员标识**向外辐射：
    employee_no ──▶ 项目管理应用  项目负责人 / 项目组成员
    employee_no ──▶ 合同管理应用  我方负责人 / 经办人员
    employee_no ──▶ 财务管理应用  报销人 / 领款人
    employee_no ──▶ 档案管理应用  经办人 / 归档人
反向：五大应用的**流程实例（process_id）**汇入「员工自助」统一列表，
    实现官方截图中「流程类型 | 标题 | 发起人 | 开始时间 | 当前步骤」的
    一站式待办视图。

部门 / 岗位 通过 org（组织架构）控件与 O2OA 平台组织同步，
不重复建表，避免与平台组织数据冲突。
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
)
from o2oa_page import Page

APP_NAME = "\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u5e94\u7528"
APP_ID = "a6006000-hr-app-0000000000000000001"
APP_ID_QUERY = "a6006001-hr-dataapp-00000000000000001"

# ==========================================================================
# 公共处理人脚本
# --------------------------------------------------------------------------
# 全部从 o2oa_org 引入（组织架构唯一来源）。
# 组织树：中国复合材料工业协会 → 综合管理部 / 行业研究部 / 会员服务部 / 国际业务部
# 职务  ：顶层 秘书长 · 副秘书长；各部门 部门负责人（分管领导兼任）；
#         综合管理部另有 人事专员 / 财务专员 / 档案管理员 / 合同管理员
# ==========================================================================
from o2oa_org import *  # noqa: F401,F403

# 员工状态（官方档案查询分组口径）
EMP_STATUS_PROBATION = "\u8bd5\u7528\u671f\u5458\u5de5"
EMP_STATUS_FORMAL = "\u6b63\u5f0f\u5458\u5de5"
EMP_STATUS_INTERN = "\u5b9e\u4e60\u671f\u5458\u5de5"
EMP_STATUS_LEAVE = "\u79bb\u804c\u5458\u5de5"

# 流程状态
FLOW_STATUS_DRAFT = "\u8349\u62df"
FLOW_STATUS_APPROVING = "\u5ba1\u6279\u4e2d"
FLOW_STATUS_DONE = "\u5df2\u5b8c\u6210"
FLOW_STATUS_REJECT = "\u5df2\u9a73\u56de"


# ==========================================================================
# 通用构件：Datagrid / 分区 / 附件区 / 意见区 / 操作条
# （与合同应用同源，保证两套应用版式与 DOM 深度完全一致）
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
    在分区内放入一个 Datagrid（官方 DOM 深度：
    form > Div > Table > Table$Td > Datagrid = 4 层）。
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


def view_block(p, vid, title):
    """在分区内放入一个引用视图的 Html 模块（官方「视图区块」用法）。"""
    p.open_section("%s_sec" % vid, title, flatten=True)
    p.open_table("%s_tbl" % vid, title, widths=["100%"],
                 styles={"width": "100%", "borderCollapse": "collapse"})
    p.open_td("%s_td" % vid, colspan=1)
    p.add({
        "id": vid, "name": title, "type": "Html", "MWFType": "html",
        "description": "", "defaultValue": {"code": "", "html": ""},
        "events": {}, "properties": {"viewId": vid, "height": "320px"},
        "class": "", "styles": {"width": "100%"}, "container": "",
        "code": "<div class=\"o2-view-holder\" data-view=\"%s\"></div>" % vid,
        "html": "<div class=\"o2-view-holder\" data-view=\"%s\"></div>" % vid,
    })
    p.close(2)
    p.close()
    return p


# ==========================================================================
# 表单 1：员工档案表（官方「员工档案」—— 六大分区）
# --------------------------------------------------------------------------
# 这是 HR 应用的核心表单，版式完全照抄官方截图 1652073737623：
#   基本信息为两列表格式；后五个分区各挂一个 Datagrid 明细表。
# ==========================================================================

FORM_EMP_ID = "f6006001-hr-employee-form-0000000000001"
PROC_EMP_ONBOARD_ID = "p6006001-hr-onboard-00000000000001"
PROC_EMP_TRANSFER_ID = "p6006002-hr-transfer-0000000000001"
PROC_EMP_REGULAR_ID = "p6006003-hr-regular-000000000001"
PROC_EMP_LEAVE_ID = "p6006004-hr-leave-job-000000000001"

# --- ① 基本信息字段（顺序严格照官方截图）---------------------------------
FE_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FE_GENDER = Field("gender", "\u6027\u522b", "dict", code="genderType")
FE_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
              required=True, description="\u5168\u5c40\u4eba\u5458\u6807\u8bc6")
FE_STATUS = Field("employee_status", "\u5458\u5de5\u72b6\u6001", "dict",
                  code="employeeStatus", default=EMP_STATUS_PROBATION)
FE_NATION = Field("nation", "\u6c11\u65cf", "textfield")
FE_POLITICS = Field("political_status", "\u653f\u6cbb\u9762\u8c8c", "dict",
                    code="politicalStatus")
FE_BIRTH = Field("birth_date", "\u51fa\u751f\u65e5\u671f", "calendar")
FE_BIRTHPLACE = Field("birth_place", "\u51fa\u751f\u5730", "textfield")
FE_MARRIAGE = Field("marital_status", "\u5a5a\u59fb\u72b6\u6001", "dict",
                    code="maritalStatus")
FE_MOBILE = Field("mobile", "\u79fb\u52a8\u7535\u8bdd", "textfield")
FE_OFFICE_TEL = Field("office_phone", "\u529e\u516c\u7535\u8bdd", "textfield")
FE_WECHAT = Field("wechat", "\u5fae\u4fe1", "textfield")
FE_QQ = Field("qq", "QQ", "textfield")
FE_EMAIL = Field("email", "\u7535\u5b50\u90ae\u4ef6", "textfield")
FE_EDU = Field("education", "\u6700\u9ad8\u5b66\u5386", "dict", code="educationLevel")
FE_DEGREE = Field("degree", "\u6700\u9ad8\u5b66\u4f4d", "dict", code="degreeType")
FE_SCHOOL = Field("graduate_school", "\u6bd5\u4e1a\u9662\u6821", "textfield")
FE_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FE_POSITION = Field("position", "\u804c\u4f4d", "textfield")
FE_JOIN_DATE = Field("join_date", "\u53c2\u52a0\u672c\u5355\u4f4d\u65f6\u95f4", "calendar")
FE_WORK_NATURE = Field("work_nature", "\u7528\u5de5\u6027\u8d28", "dict",
                       code="workNature")
FE_ID_CARD = Field("id_card", "\u8eab\u4efd\u8bc1\u53f7", "textfield")
FE_NATIVE_PLACE = Field("native_place", "\u7c4d\u8d2f", "textfield")
FE_EMERGENCY = Field("emergency_contact", "\u7d27\u6025\u8054\u7cfb\u4eba", "textfield")
FE_EMERGENCY_TEL = Field("emergency_phone", "\u7d27\u6025\u8054\u7cfb\u7535\u8bdd", "textfield")
FE_ADDRESS = Field("home_address", "\u5bb6\u5ead\u4f4f\u5740", "textarea")
FE_REMARK = Field("remark", "\u5907\u6ce8", "textarea")

# --- ② 本单位工作经历（照官方截图列顺序）---------------------------------
DG_INNER_WORK = datagrid("dg_inner_work", "\u672c\u5355\u4f4d\u5de5\u4f5c\u7ecf\u5386", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "dept", "name": "\u90e8\u95e8", "width": "140px"},
    {"id": "position", "name": "\u5c97\u4f4d", "width": "140px"},
    {"id": "start_date", "name": "\u5f00\u59cb\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "end_date", "name": "\u7ed3\u675f\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "work_desc", "name": "\u5de5\u4f5c\u63cf\u8ff0", "width": "220px"},
    {"id": "work_type", "name": "\u7c7b\u578b", "width": "110px"},
])

# --- ③ 工作经历（照官方截图列顺序）---------------------------------------
DG_WORK = datagrid("dg_work", "\u5de5\u4f5c\u7ecf\u5386", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "company", "name": "\u516c\u53f8", "width": "200px"},
    {"id": "dept_position", "name": "\u90e8\u95e8/\u5c97\u4f4d", "width": "180px"},
    {"id": "start_date", "name": "\u5f00\u59cb\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "end_date", "name": "\u7ed3\u675f\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "work_desc", "name": "\u5de5\u4f5c\u63cf\u8ff0", "width": "240px"},
])

# --- ④ 教育背景（照官方截图列顺序）---------------------------------------
DG_EDU = datagrid("dg_edu", "\u6559\u80b2\u80cc\u666f", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "start_date", "name": "\u5165\u5b66\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "end_date", "name": "\u6bd5\u4e1a\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "school", "name": "\u5b66\u6821\u540d\u79f0", "width": "200px"},
    {"id": "major", "name": "\u4e13\u4e1a", "width": "160px"},
    {"id": "education", "name": "\u5b66\u5386", "width": "100px"},
    {"id": "degree", "name": "\u5b66\u4f4d", "width": "100px"},
])

# --- ⑤ 专业技术资格（照官方截图列顺序）-----------------------------------
DG_TECH = datagrid("dg_tech", "\u4e13\u4e1a\u6280\u672f\u8d44\u683c", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "tech_name", "name": "\u4e13\u4e1a\u6280\u672f\u8d44\u683c\u540d\u79f0",
     "width": "260px"},
    {"id": "get_date", "name": "\u53d6\u5f97\u65e5\u671f", "mtype": "Calendar",
     "width": "120px"},
])

# --- ⑥ 奖励情况（照官方截图列顺序）---------------------------------------
DG_AWARD = datagrid("dg_award", "\u5956\u52b1\u60c5\u51b5", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "award_date", "name": "\u83b7\u5956\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "award_name", "name": "\u83b7\u5956\u540d\u79f0", "width": "220px"},
    {"id": "award_org", "name": "\u9881\u53d1\u5355\u4f4d", "width": "180px"},
    {"id": "award_type", "name": "\u5956\u52b1\u7c7b\u578b", "width": "110px"},
    {"id": "award_level", "name": "\u83b7\u5956\u7ea7\u522b", "width": "110px"},
])


def build_form_employee():
    """员工档案表 —— 官方六大分区（基本信息 + 5 个 Datagrid 明细）。"""
    p = Page("\u5458\u5de5\u6863\u6848\u8868", FORM_EMP_ID,
             "\u5458\u5de5\u57fa\u672c\u4fe1\u606f\u4e0e\u5c65\u5386\u6863\u6848")

    # ① 基本信息（两列表格式）
    p.open_section("sec_e_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_e_basic", [
        FE_NAME, FE_GENDER, FE_NO, FE_STATUS, FE_NATION, FE_POLITICS,
        FE_BIRTH, FE_BIRTHPLACE, FE_MARRIAGE, FE_MOBILE, FE_OFFICE_TEL,
        FE_WECHAT, FE_QQ, FE_EMAIL, FE_EDU, FE_DEGREE, FE_SCHOOL,
        FE_DEPT, FE_POSITION, FE_JOIN_DATE,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    # 任职与身份信息
    p.open_section("sec_e_job", "\u4efb\u804c\u4e0e\u8eab\u4efd\u4fe1\u606f", flatten=True)
    p.field_grid("fg_e_job", [
        FE_WORK_NATURE, FE_ID_CARD, FE_NATIVE_PLACE,
        FE_EMERGENCY, FE_EMERGENCY_TEL, FE_ADDRESS,
    ], cols=2, section_title="\u4efb\u804c\u4e0e\u8eab\u4efd\u4fe1\u606f")
    p.close()

    # ② 本单位工作经历
    p.open_section("sec_e_inner", "\u672c\u5355\u4f4d\u5de5\u4f5c\u7ecf\u5386", flatten=True)
    grid_block(p, "fg_e_inner", DG_INNER_WORK)

    # ③ 工作经历
    p.open_section("sec_e_work", "\u5de5\u4f5c\u7ecf\u5386", flatten=True)
    grid_block(p, "fg_e_work", DG_WORK)

    # ④ 教育背景
    p.open_section("sec_e_edu", "\u6559\u80b2\u80cc\u666f", flatten=True)
    grid_block(p, "fg_e_edu", DG_EDU)

    # ⑤ 专业技术资格
    p.open_section("sec_e_tech", "\u4e13\u4e1a\u6280\u672f\u8d44\u683c", flatten=True)
    grid_block(p, "fg_e_tech", DG_TECH)

    # ⑥ 奖励情况
    p.open_section("sec_e_award", "\u5956\u52b1\u60c5\u51b5", flatten=True)
    grid_block(p, "fg_e_award", DG_AWARD)

    # 备注
    p.open_section("sec_e_remark", "\u5176\u4ed6", flatten=True)
    p.field_grid("fg_e_remark", [FE_REMARK], cols=1, section_title="\u5176\u4ed6")
    p.close()

    attach_block(p, "att_emp", "\u6863\u6848\u9644\u4ef6\uff08\u8eab\u4efd\u8bc1/\u5b66\u5386\u8bc1\u4e66/\u5408\u540c\u626b\u63cf\u4ef6\uff09")
    opinion_block(p, "opinion_emp")
    p.add(actionbar("actionbar_emp"))

    return FormBuilder(FORM_EMP_ID, "\u5458\u5de5\u6863\u6848\u8868",
                       "\u5458\u5de5\u57fa\u672c\u4fe1\u606f\u4e0e\u5c65\u5386\u6863\u6848",
                       page=p)


FORM_EMP = build_form_employee()


# ==========================================================================
# 表单 2：员工入职表（官方「员工入职公示」）
# ==========================================================================

FORM_ONBOARD_ID = "f6006002-hr-onboard-form-00000000000001"

FO_APPLY_NO = Field("onboard_no", "\u5165\u804c\u5355\u53f7", "textfield",
                    required=True, readonly=True, description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210")
FO_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FO_GENDER = Field("gender", "\u6027\u522b", "dict", code="genderType")
FO_ID_CARD = Field("id_card", "\u8eab\u4efd\u8bc1\u53f7", "textfield")
FO_MOBILE = Field("mobile", "\u8054\u7cfb\u7535\u8bdd", "textfield")
FO_EMAIL = Field("email", "\u7535\u5b50\u90ae\u4ef6", "textfield")
FO_DEPT = Field("dept", "\u62df\u5165\u804c\u90e8\u95e8", "org", required=True)
FO_POSITION = Field("position", "\u62df\u4efb\u5c97\u4f4d", "textfield", required=True)
FO_GRADE = Field("grade", "\u804c\u7ea7", "textfield")
FO_NATURE = Field("work_nature", "\u7528\u5de5\u6027\u8d28", "dict",
                  code="workNature", required=True)
FO_STATUS = Field("employee_status", "\u5458\u5de5\u72b6\u6001", "dict",
                  code="employeeStatus", default=EMP_STATUS_PROBATION)
FO_PROBATION = Field("probation_months", "\u8bd5\u7528\u671f\uff08\u6708\uff09",
                     "number", default="3")
FO_START = Field("start_date", "\u5165\u804c\u65e5\u671f", "calendar", required=True)
FO_END = Field("end_date", "\u8bd5\u7528\u5230\u671f\u65e5", "calendar")
FO_EDU = Field("education", "\u6700\u9ad8\u5b66\u5386", "dict", code="educationLevel")
FO_SCHOOL = Field("graduate_school", "\u6bd5\u4e1a\u9662\u6821", "textfield")
FO_MAJOR = Field("major", "\u6240\u5b66\u4e13\u4e1a", "textfield")
FO_RECRUIT = Field("recruit_channel", "\u62db\u8058\u6e20\u9053", "select",
                   options=["\u6821\u56ed\u62db\u8058", "\u793e\u4f1a\u62db\u8058",
                            "\u5185\u90e8\u63a8\u8350", "\u730e\u5934\u63a8\u8350",
                            "\u5185\u90e8\u8f6c\u5c97"])
FO_SALARY = Field("salary", "\u8f6c\u6b63\u540e\u6708\u85aa\uff08\u5143\uff09", "currency")
FO_OPINION_F = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FO_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_ONBOARD_DOC = datagrid("dg_onboard_doc", "\u5165\u804c\u6750\u6599\u6e05\u5355", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "doc_name", "name": "\u6750\u6599\u540d\u79f0", "width": "220px"},
    {"id": "doc_count", "name": "\u4efd\u6570", "mtype": "Number", "width": "80px"},
    {"id": "submit_status", "name": "\u63d0\u4ea4\u72b6\u6001", "width": "110px"},
    {"id": "check_person", "name": "\u6838\u9a8c\u4eba", "width": "100px"},
    {"id": "note", "name": "\u5907\u6ce8", "width": "200px"},
])


def build_form_onboard():
    p = Page("\u5458\u5de5\u5165\u804c\u8868", FORM_ONBOARD_ID,
             "\u65b0\u5458\u5165\u804c\u7533\u8bf7\u4e0e\u5ba1\u6279")

    p.open_section("sec_o_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_o_basic", [
        FO_APPLY_NO, FO_NAME, FO_GENDER, FO_ID_CARD,
        FO_MOBILE, FO_EMAIL, FO_START, FO_END,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_o_job", "\u4efb\u804c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_o_job", [
        FO_DEPT, FO_POSITION, FO_GRADE, FO_NATURE,
        FO_STATUS, FO_PROBATION, FO_SALARY, FO_RECRUIT,
    ], cols=2, section_title="\u4efb\u804c\u4fe1\u606f")
    p.close()

    p.open_section("sec_o_edu", "\u6559\u80b2\u80cc\u666f", flatten=True)
    p.field_grid("fg_o_edu", [FO_EDU, FO_SCHOOL, FO_MAJOR],
                 cols=2, section_title="\u6559\u80b2\u80cc\u666f")
    p.close()

    p.open_section("sec_o_doc", "\u5165\u804c\u6750\u6599\u6e05\u5355", flatten=True)
    grid_block(p, "fg_o_doc", DG_ONBOARD_DOC)

    p.open_section("sec_o_hr", "\u4eba\u4e8b\u5904\u7406\u610f\u89c1", flatten=True)
    p.field_grid("fg_o_hr", [FO_OPINION_F, FO_NOTE], cols=1,
                 section_title="\u4eba\u4e8b\u5904\u7406\u610f\u89c1")
    p.close()

    attach_block(p, "att_onboard", "\u5165\u804c\u6750\u6599\u9644\u4ef6")
    opinion_block(p, "opinion_onboard")
    p.add(actionbar("actionbar_onboard"))

    return FormBuilder(FORM_ONBOARD_ID, "\u5458\u5de5\u5165\u804c\u8868",
                       "\u65b0\u5458\u5165\u804c\u7533\u8bf7\u4e0e\u5ba1\u6279", page=p)


FORM_ONBOARD = build_form_onboard()


# ==========================================================================
# 表单 3：员工转岗表（官方「员工转岗公示」）
# ==========================================================================

FORM_TRANSFER_ID = "f6006003-hr-transfer-form-0000000000001"

FT_APPLY_NO = Field("transfer_no", "\u8f6c\u5c97\u5355\u53f7", "textfield",
                    required=True, readonly=True)
FT_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield", required=True)
FT_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FT_TYPE = Field("transfer_type", "\u8f6c\u5c97\u7c7b\u578b", "dict",
                code="transferType", required=True)
FT_OLD_DEPT = Field("old_dept", "\u539f\u90e8\u95e8", "org", required=True)
FT_OLD_POS = Field("old_position", "\u539f\u5c97\u4f4d", "textfield", required=True)
FT_OLD_GRADE = Field("old_grade", "\u539f\u804c\u7ea7", "textfield")
FT_NEW_DEPT = Field("new_dept", "\u65b0\u90e8\u95e8", "org", required=True)
FT_NEW_POS = Field("new_position", "\u65b0\u5c97\u4f4d", "textfield", required=True)
FT_NEW_GRADE = Field("new_grade", "\u65b0\u804c\u7ea7", "textfield")
FT_EFFECT = Field("effect_date", "\u751f\u6548\u65e5\u671f", "calendar", required=True)
FT_REASON = Field("transfer_reason", "\u8f6c\u5c97\u539f\u56e0", "textarea",
                  required=True)
FT_DUTY = Field("new_duty", "\u65b0\u5c97\u4f4d\u804c\u8d23", "textarea")
FT_TRAIN = Field("train_arrange", "\u57f9\u8bad\u5b89\u6392", "textarea")
FT_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_transfer():
    p = Page("\u5458\u5de5\u8f6c\u5c97\u8868", FORM_TRANSFER_ID,
             "\u5458\u5de5\u5c97\u4f4d\u53d8\u52a8\u7533\u8bf7\u4e0e\u5ba1\u6279")

    p.open_section("sec_t_apply", "\u7533\u8bf7\u4fe1\u606f", flatten=True)
    p.field_grid("fg_t_apply", [FT_APPLY_NO, FT_NO, FT_NAME, FT_TYPE],
                 cols=2, section_title="\u7533\u8bf7\u4fe1\u606f")
    p.close()

    p.open_section("sec_t_old", "\u539f\u4efb\u804c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_t_old", [FT_OLD_DEPT, FT_OLD_POS, FT_OLD_GRADE],
                 cols=2, section_title="\u539f\u4efb\u804c\u4fe1\u606f")
    p.close()

    p.open_section("sec_t_new", "\u65b0\u4efb\u804c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_t_new", [FT_NEW_DEPT, FT_NEW_POS, FT_NEW_GRADE, FT_EFFECT],
                 cols=2, section_title="\u65b0\u4efb\u804c\u4fe1\u606f")
    p.close()

    p.open_section("sec_t_reason", "\u8f6c\u5c97\u8bf4\u660e", flatten=True)
    p.field_grid("fg_t_reason", [FT_REASON, FT_DUTY, FT_TRAIN],
                 cols=1, section_title="\u8f6c\u5c97\u8bf4\u660e")
    p.close()

    p.open_section("sec_t_note", "\u5176\u4ed6", flatten=True)
    p.field_grid("fg_t_note", [FT_NOTE], cols=1, section_title="\u5176\u4ed6")
    p.close()

    attach_block(p, "att_transfer", "\u8f6c\u5c97\u4f9d\u636e\u9644\u4ef6")
    opinion_block(p, "opinion_transfer")
    p.add(actionbar("actionbar_transfer"))

    return FormBuilder(FORM_TRANSFER_ID, "\u5458\u5de5\u8f6c\u5c97\u8868",
                       "\u5458\u5de5\u5c97\u4f4d\u53d8\u52a8\u7533\u8bf7\u4e0e\u5ba1\u6279",
                       page=p)


FORM_TRANSFER = build_form_transfer()


# ==========================================================================
# 表单 4：员工转正表（官方「员工转正公示」）
# ==========================================================================

FORM_REGULAR_ID = "f6006004-hr-regular-form-00000000000001"

FR_APPLY_NO = Field("regular_no", "\u8f6c\u6b63\u5355\u53f7", "textfield",
                    required=True, readonly=True)
FR_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield", required=True)
FR_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FR_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FR_POSITION = Field("position", "\u5c97\u4f4d", "textfield")
FR_JOIN = Field("join_date", "\u5165\u804c\u65e5\u671f", "calendar", required=True)
FR_PROBATION_END = Field("probation_end", "\u8bd5\u7528\u5230\u671f\u65e5", "calendar")
FR_APPLY_DATE = Field("apply_date", "\u7533\u8bf7\u65e5\u671f", "calendar",
                      required=True)
FR_RESULT = Field("regular_result", "\u8f6c\u6b63\u7ed3\u679c", "radio",
                  options=["\u540c\u610f\u8f6c\u6b63", "\u5ef6\u957f\u8bd5\u7528\u671f",
                           "\u4e0d\u4e88\u8f6c\u6b63"])
FR_NEW_STATUS = Field("new_status", "\u8f6c\u6b63\u540e\u72b6\u6001", "dict",
                      code="employeeStatus", default=EMP_STATUS_FORMAL)
FR_NEW_GRADE = Field("new_grade", "\u8f6c\u6b63\u540e\u804c\u7ea7", "textfield")
FR_NEW_SALARY = Field("new_salary", "\u8f6c\u6b63\u540e\u6708\u85aa\uff08\u5143\uff09",
                      "currency")
FR_DEPT_EVAL = Field("dept_evaluate", "\u90e8\u95e8\u8bc4\u4ef7", "textarea",
                     required=True)
FR_HR_EVAL = Field("hr_evaluate", "\u4eba\u4e8b\u8bc4\u4ef7", "textarea")
FR_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_REGULAR_SCORE = datagrid("dg_regular_score", "\u8f6c\u6b63\u8003\u8bc4\u8bb0\u5f55", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "item", "name": "\u8003\u8bc4\u9879\u76ee", "width": "200px"},
    {"id": "weight", "name": "\u6743\u91cd%", "mtype": "Number", "width": "90px"},
    {"id": "score", "name": "\u5f97\u5206", "mtype": "Number", "width": "90px"},
    {"id": "evaluator", "name": "\u8bc4\u4ef7\u4eba", "width": "100px"},
    {"id": "comment", "name": "\u8bc4\u8bed", "width": "220px"},
], is_total=True)


def build_form_regular():
    p = Page("\u5458\u5de5\u8f6c\u6b63\u8868", FORM_REGULAR_ID,
             "\u8bd5\u7528\u671f\u5458\u5de5\u8f6c\u6b63\u8003\u8bc4\u4e0e\u5ba1\u6279")

    p.open_section("sec_r_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_r_basic", [
        FR_APPLY_NO, FR_NO, FR_NAME, FR_DEPT,
        FR_POSITION, FR_JOIN, FR_PROBATION_END, FR_APPLY_DATE,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_r_score", "\u8f6c\u6b63\u8003\u8bc4\u8bb0\u5f55", flatten=True)
    grid_block(p, "fg_r_score", DG_REGULAR_SCORE)

    p.open_section("sec_r_result", "\u8f6c\u6b63\u7ed3\u679c", flatten=True)
    p.field_grid("fg_r_result", [
        FR_RESULT, FR_NEW_STATUS, FR_NEW_GRADE, FR_NEW_SALARY,
    ], cols=2, section_title="\u8f6c\u6b63\u7ed3\u679c")
    p.close()

    p.open_section("sec_r_eval", "\u8bc4\u4ef7\u610f\u89c1", flatten=True)
    p.field_grid("fg_r_eval", [FR_DEPT_EVAL, FR_HR_EVAL, FR_NOTE],
                 cols=1, section_title="\u8bc4\u4ef7\u610f\u89c1")
    p.close()

    attach_block(p, "att_regular", "\u8003\u8bc4\u4f9d\u636e\u9644\u4ef6")
    opinion_block(p, "opinion_regular")
    p.add(actionbar("actionbar_regular"))

    return FormBuilder(FORM_REGULAR_ID, "\u5458\u5de5\u8f6c\u6b63\u8868",
                       "\u8bd5\u7528\u671f\u5458\u5de5\u8f6c\u6b63\u8003\u8bc4\u4e0e\u5ba1\u6279",
                       page=p)


FORM_REGULAR = build_form_regular()


# ==========================================================================
# 表单 5：员工离职表（官方「员工离职公示」）
# ==========================================================================

FORM_RESIGN_ID = "f6006005-hr-resign-form-000000000000001"

FQ_APPLY_NO = Field("resign_no", "\u79bb\u804c\u5355\u53f7", "textfield",
                    required=True, readonly=True)
FQ_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield", required=True)
FQ_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FQ_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FQ_POSITION = Field("position", "\u5c97\u4f4d", "textfield")
FQ_JOIN = Field("join_date", "\u5165\u804c\u65e5\u671f", "calendar")
FQ_TYPE = Field("resign_type", "\u79bb\u804c\u7c7b\u578b", "dict",
                code="resignType", required=True)
FQ_LAST_DAY = Field("last_work_date", "\u6700\u540e\u5de5\u4f5c\u65e5", "calendar",
                    required=True)
FQ_HANDOVER = Field("handover_date", "\u4ea4\u63a5\u5b8c\u6210\u65e5", "calendar")
FQ_HANDOVER_TO = Field("handover_person", "\u63a5\u4ea4\u4eba", "textfield")
FQ_REASON = Field("resign_reason", "\u79bb\u804c\u539f\u56e0", "textarea",
                  required=True)
FQ_LEADER_OP = Field("leader_opinion", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u610f\u89c1",
                     "textarea")
FQ_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FQ_SETTLE = Field("settle_note", "\u85aa\u916c\u7ed3\u7b97\u8bf4\u660e", "textarea")
FQ_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_HANDOVER = datagrid("dg_handover", "\u5de5\u4f5c\u4ea4\u63a5\u6e05\u5355", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "item", "name": "\u4ea4\u63a5\u4e8b\u9879", "width": "240px"},
    {"id": "handover_to", "name": "\u63a5\u4ea4\u4eba", "width": "100px"},
    {"id": "finish_date", "name": "\u5b8c\u6210\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "status", "name": "\u72b6\u6001", "width": "100px"},
    {"id": "note", "name": "\u5907\u6ce8", "width": "200px"},
])


def build_form_resign():
    p = Page("\u5458\u5de5\u79bb\u804c\u8868", FORM_RESIGN_ID,
             "\u5458\u5de5\u79bb\u804c\u7533\u8bf7\u3001\u4ea4\u63a5\u4e0e\u5ba1\u6279")

    p.open_section("sec_q_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_q_basic", [
        FQ_APPLY_NO, FQ_NO, FQ_NAME, FQ_DEPT,
        FQ_POSITION, FQ_JOIN, FQ_LAST_DAY, FQ_HANDOVER,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_q_type", "\u79bb\u804c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_q_type", [FQ_TYPE, FQ_HANDOVER_TO],
                 cols=2, section_title="\u79bb\u804c\u4fe1\u606f")
    p.close()

    p.open_section("sec_q_handover", "\u5de5\u4f5c\u4ea4\u63a5\u6e05\u5355", flatten=True)
    grid_block(p, "fg_q_handover", DG_HANDOVER)

    p.open_section("sec_q_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_q_op", [FQ_REASON, FQ_LEADER_OP, FQ_HR_OP, FQ_SETTLE],
                 cols=1, section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    p.open_section("sec_q_note", "\u5176\u4ed6", flatten=True)
    p.field_grid("fg_q_note", [FQ_NOTE], cols=1, section_title="\u5176\u4ed6")
    p.close()

    attach_block(p, "att_resign", "\u79bb\u804c\u4ea4\u63a5\u9644\u4ef6")
    opinion_block(p, "opinion_resign")
    p.add(actionbar("actionbar_resign"))

    return FormBuilder(FORM_RESIGN_ID, "\u5458\u5de5\u79bb\u804c\u8868",
                       "\u5458\u5de5\u79bb\u804c\u7533\u8bf7\u3001\u4ea4\u63a5\u4e0e\u5ba1\u6279",
                       page=p)


FORM_RESIGN = build_form_resign()


# ==========================================================================
# 表单 6：岗位需求表（官方「人才市场 -> 岗位池」发布）
# ==========================================================================

FORM_JOB_ID = "f6006006-hr-job-form-00000000000000001"
PROC_JOB_PUBLISH_ID = "p6006005-hr-job-publish-000000000001"
PROC_JOB_APPLY_ID = "p6006006-hr-job-apply-0000000000001"

FJ_JOB_NO = Field("job_no", "\u5c97\u4f4d\u7f16\u53f7", "textfield",
                  required=True, readonly=True)
FJ_JOB_NAME = Field("job_name", "\u5c97\u4f4d\u540d\u79f0", "textfield", required=True)
FJ_DEPT = Field("recruit_dept", "\u62db\u8058\u90e8\u95e8", "org", required=True)
FJ_COUNT = Field("recruit_count", "\u62db\u8058\u4eba\u6570", "number", required=True)
FJ_GRADE = Field("standard_grade", "\u6807\u51c6\u804c\u7ea7", "textfield")
FJ_BID_TYPE = Field("bid_type", "\u7ade\u8058\u7c7b\u578b", "dict",
                    code="bidType", required=True)
FJ_TYPE = Field("job_type", "\u5c97\u4f4d\u7c7b\u578b", "dict", code="jobType")
FJ_CATEGORY = Field("job_category", "\u5c97\u4f4d\u5e8f\u5217", "dict",
                    code="jobCategory")
FJ_PUBLISH_DATE = Field("publish_date", "\u53d1\u5e03\u65f6\u95f4", "calendar",
                        required=True)
FJ_DEADLINE = Field("deadline", "\u622a\u6b62\u65f6\u95f4", "calendar")
FJ_INTERVIEW = Field("interview_date", "\u9762\u8bd5\u65f6\u95f4", "calendar")
FJ_STATUS = Field("job_status", "\u72b6\u6001", "dict", code="jobStatus",
                  default="\u62a5\u540d\u4e2d")
FJ_WORK_PLACE = Field("work_place", "\u5de5\u4f5c\u5730\u70b9", "textfield")
FJ_SALARY = Field("salary_range", "\u85aa\u916c\u8303\u56f4", "textfield")
FJ_EDU_REQ = Field("education_req", "\u5b66\u5386\u8981\u6c42", "dict",
                   code="educationLevel")
FJ_EXP_REQ = Field("experience_req", "\u7ecf\u9a8c\u8981\u6c42", "textfield")
FJ_DUTY = Field("job_duty", "\u5c97\u4f4d\u804c\u8d23", "textarea", required=True)
FJ_REQUIRE = Field("job_require", "\u4efb\u804c\u8981\u6c42", "textarea",
                   required=True)
FJ_DEPT_OP = Field("dept_opinion", "\u90e8\u95e8\u610f\u89c1", "textarea")
FJ_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FJ_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_job():
    p = Page("\u5c97\u4f4d\u9700\u6c42\u8868", FORM_JOB_ID,
             "\u5185\u90e8\u7ade\u8058\u5c97\u4f4d\u53d1\u5e03\u4e0e\u5ba1\u6838")

    p.open_section("sec_j_basic", "\u5c97\u4f4d\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_j_basic", [
        FJ_JOB_NO, FJ_JOB_NAME, FJ_DEPT, FJ_COUNT,
        FJ_GRADE, FJ_BID_TYPE, FJ_TYPE, FJ_CATEGORY,
    ], cols=2, section_title="\u5c97\u4f4d\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_j_time", "\u53d1\u5e03\u4e0e\u65f6\u95f4\u5b89\u6392", flatten=True)
    p.field_grid("fg_j_time", [
        FJ_PUBLISH_DATE, FJ_DEADLINE, FJ_INTERVIEW, FJ_STATUS,
    ], cols=2, section_title="\u53d1\u5e03\u4e0e\u65f6\u95f4\u5b89\u6392")
    p.close()

    p.open_section("sec_j_cond", "\u4efb\u804c\u6761\u4ef6", flatten=True)
    p.field_grid("fg_j_cond", [
        FJ_WORK_PLACE, FJ_SALARY, FJ_EDU_REQ, FJ_EXP_REQ,
    ], cols=2, section_title="\u4efb\u804c\u6761\u4ef6")
    p.close()

    p.open_section("sec_j_desc", "\u5c97\u4f4d\u63cf\u8ff0", flatten=True)
    p.field_grid("fg_j_desc", [FJ_DUTY, FJ_REQUIRE], cols=1,
                 section_title="\u5c97\u4f4d\u63cf\u8ff0")
    p.close()

    p.open_section("sec_j_op", "\u5ba1\u6838\u610f\u89c1", flatten=True)
    p.field_grid("fg_j_op", [FJ_DEPT_OP, FJ_HR_OP, FJ_NOTE], cols=1,
                 section_title="\u5ba1\u6838\u610f\u89c1")
    p.close()

    attach_block(p, "att_job", "\u5c97\u4f4d\u8bf4\u660e\u4e66\u9644\u4ef6")
    opinion_block(p, "opinion_job")
    p.add(actionbar("actionbar_job"))

    return FormBuilder(FORM_JOB_ID, "\u5c97\u4f4d\u9700\u6c42\u8868",
                       "\u5185\u90e8\u7ade\u8058\u5c97\u4f4d\u53d1\u5e03\u4e0e\u5ba1\u6838",
                       page=p)


FORM_JOB = build_form_job()


# ==========================================================================
# 表单 7：岗位报名表（官方「人才市场 -> 我的报名表」）
# ==========================================================================

FORM_JOB_APPLY_ID = "f6006007-hr-job-apply-form-00000000001"

FA_APPLY_NO = Field("apply_no", "\u62a5\u540d\u5355\u53f7", "textfield",
                    required=True, readonly=True)
FA_JOB_NO = Field("job_no", "\u5c97\u4f4d\u7f16\u53f7", "textfield", required=True)
FA_JOB_NAME = Field("job_name", "\u5c97\u4f4d\u540d\u79f0", "textfield",
                    readonly=True)
FA_JOB_DEPT = Field("recruit_dept", "\u62db\u8058\u90e8\u95e8", "textfield",
                    readonly=True)
FA_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield", required=True)
FA_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FA_DEPT = Field("dept", "\u73b0\u6240\u5c5e\u90e8\u95e8", "org")
FA_POSITION = Field("position", "\u73b0\u4efb\u5c97\u4f4d", "textfield")
FA_GRADE = Field("grade", "\u73b0\u804c\u7ea7", "textfield")
FA_JOIN = Field("join_date", "\u5165\u804c\u65e5\u671f", "calendar")
FA_APPLY_DATE = Field("apply_date", "\u62a5\u540d\u65f6\u95f4", "calendar",
                      required=True)
FA_REASON = Field("apply_reason", "\u62a5\u540d\u7406\u7531", "textarea",
                  required=True)
FA_ADVANTAGE = Field("self_advantage", "\u81ea\u6211\u4f18\u52bf", "textarea")
FA_CAREER = Field("career_plan", "\u804c\u4e1a\u89c4\u5212", "textarea")
FA_IS_SUMMARY = Field("is_summary", "\u662f\u5426\u6c47\u603b", "radio",
                      options=["\u662f", "\u5426"], default="\u5426")
FA_STATUS = Field("apply_status", "\u72b6\u6001", "dict", code="applyStatus",
                  default="\u5df2\u62a5\u540d")
FA_SCORE = Field("interview_score", "\u7ade\u8058\u5f97\u5206", "number")
FA_RESULT = Field("apply_result", "\u7ade\u8058\u7ed3\u679c", "radio",
                  options=["\u5f85\u5b9a", "\u5165\u9009", "\u672a\u5165\u9009"])
FA_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FA_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_job_apply():
    p = Page("\u5c97\u4f4d\u62a5\u540d\u8868", FORM_JOB_APPLY_ID,
             "\u5458\u5de5\u7ade\u8058\u5c97\u4f4d\u62a5\u540d\u4e0e\u8bc4\u4f30")

    p.open_section("sec_a_job", "\u62a5\u540d\u5c97\u4f4d", flatten=True)
    p.field_grid("fg_a_job", [FA_APPLY_NO, FA_JOB_NO, FA_JOB_NAME, FA_JOB_DEPT],
                 cols=2, section_title="\u62a5\u540d\u5c97\u4f4d")
    p.close()

    p.open_section("sec_a_self", "\u62a5\u540d\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_a_self", [
        FA_NO, FA_NAME, FA_DEPT, FA_POSITION,
        FA_GRADE, FA_JOIN, FA_APPLY_DATE, FA_IS_SUMMARY,
    ], cols=2, section_title="\u62a5\u540d\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_a_reason", "\u62a5\u540d\u8bf4\u660e", flatten=True)
    p.field_grid("fg_a_reason", [FA_REASON, FA_ADVANTAGE, FA_CAREER],
                 cols=1, section_title="\u62a5\u540d\u8bf4\u660e")
    p.close()

    p.open_section("sec_a_result", "\u7ade\u8058\u7ed3\u679c", flatten=True)
    p.field_grid("fg_a_result", [FA_STATUS, FA_SCORE, FA_RESULT],
                 cols=2, section_title="\u7ade\u8058\u7ed3\u679c")
    p.close()

    p.open_section("sec_a_op", "\u5ba1\u6838\u610f\u89c1", flatten=True)
    p.field_grid("fg_a_op", [FA_HR_OP, FA_NOTE], cols=1, section_title="\u5ba1\u6838\u610f\u89c1")
    p.close()

    attach_block(p, "att_job_apply", "\u62a5\u540d\u9644\u4ef6")
    opinion_block(p, "opinion_job_apply")
    p.add(actionbar("actionbar_job_apply"))

    return FormBuilder(FORM_JOB_APPLY_ID, "\u5c97\u4f4d\u62a5\u540d\u8868",
                       "\u5458\u5de5\u7ade\u8058\u5c97\u4f4d\u62a5\u540d\u4e0e\u8bc4\u4f30",
                       page=p)


FORM_JOB_APPLY = build_form_job_apply()


# ==========================================================================
# 表单 8：员工积分表（官方「积分管理」——年度积分 / 永久积分）
# ==========================================================================

FORM_POINT_ID = "f6006008-hr-point-form-0000000000000001"
PROC_POINT_GRANT_ID = "p6006007-hr-point-grant-0000000000001"

FP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield", required=True)
FP_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FP_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FP_POSITION = Field("position", "\u5c97\u4f4d", "textfield")
FP_YEAR = Field("point_year", "\u5e74\u5ea6", "textfield", required=True)
FP_TYPE = Field("point_type", "\u79ef\u5206\u7c7b\u578b", "dict",
                code="pointType", required=True)
FP_YEAR_POINT = Field("year_point", "\u5e74\u5ea6\u79ef\u5206", "number",
                      required=True)
FP_TOTAL_POINT = Field("total_point", "\u6c38\u4e45\u79ef\u5206", "number",
                       readonly=True)
FP_SOURCE = Field("point_source", "\u79ef\u5206\u6765\u6e90", "textfield")
FP_RELATE = Field("relate_biz", "\u5173\u8054\u4e1a\u52a1", "textfield")
FP_DATE = Field("grant_date", "\u6388\u4e88\u65e5\u671f", "calendar",
                required=True)
FP_HONOR = Field("honor_level", "\u8363\u8a89\u7b49\u7ea7", "select",
                 options=["\u4e00\u7ea7", "\u4e8c\u7ea7", "\u4e09\u7ea7",
                          "\u4e0d\u5206\u7ea7"])
FP_RANK = Field("rank_no", "\u6392\u540d", "number", readonly=True)
FP_REASON = Field("grant_reason", "\u6388\u4e88\u539f\u56e0", "textarea",
                  required=True)
FP_STATUS = Field("point_status", "\u72b6\u6001", "dict", code="approveStatus",
                  default=FLOW_STATUS_DRAFT)
FP_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FP_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_point():
    p = Page("\u5458\u5de5\u79ef\u5206\u8868", FORM_POINT_ID,
             "\u5458\u5de5\u79ef\u5206\u6388\u4e88\u4e0e\u53f0\u8d26")

    p.open_section("sec_p_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_p_basic", [
        FP_NO, FP_NAME, FP_DEPT, FP_POSITION,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_p_point", "\u79ef\u5206\u4fe1\u606f", flatten=True)
    p.field_grid("fg_p_point", [
        FP_YEAR, FP_TYPE, FP_YEAR_POINT, FP_TOTAL_POINT,
        FP_SOURCE, FP_RELATE, FP_DATE, FP_HONOR,
    ], cols=2, section_title="\u79ef\u5206\u4fe1\u606f")
    p.close()

    p.open_section("sec_p_reason", "\u6388\u4e88\u8bf4\u660e", flatten=True)
    p.field_grid("fg_p_reason", [FP_REASON, FP_NOTE], cols=1,
                 section_title="\u6388\u4e88\u8bf4\u660e")
    p.close()

    p.open_section("sec_p_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_p_op", [FP_STATUS, FP_RANK, FP_HR_OP], cols=2,
                 section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    attach_block(p, "att_point", "\u79ef\u5206\u4f9d\u636e\u9644\u4ef6")
    opinion_block(p, "opinion_point")
    p.add(actionbar("actionbar_point"))

    return FormBuilder(FORM_POINT_ID, "\u5458\u5de5\u79ef\u5206\u8868",
                       "\u5458\u5de5\u79ef\u5206\u6388\u4e88\u4e0e\u53f0\u8d26", page=p)


FORM_POINT = build_form_point()


# ==========================================================================
# 表单 9：积分悬赏表（官方「积分悬赏」—— 分数标签 | 课题 | 日期）
# ==========================================================================

FORM_BOUNTY_ID = "f6006009-hr-bounty-form-000000000000001"

FB_NO = Field("bounty_no", "\u60ac\u8d4f\u7f16\u53f7", "textfield",
              required=True, readonly=True)
FB_TITLE = Field("bounty_title", "\u8bfe\u9898\u540d\u79f0", "textfield",
                 required=True)
FB_SCORE = Field("bounty_score", "\u60ac\u8d4f\u5206\u6570", "number",
                 required=True)
FB_SCORE_TAG = Field("score_tag", "\u5206\u6570\u6807\u7b7e", "select",
                     options=["1-10 \u5206", "11-30 \u5206",
                              "31-50 \u5206", "51-100 \u5206"])
FB_TYPE = Field("bounty_type", "\u8bfe\u9898\u7c7b\u578b", "dict",
                code="bountyType")
FB_PUBLISH_DEPT = Field("publish_dept", "\u53d1\u5e03\u90e8\u95e8", "org")
FB_PUBLISHER = Field("publisher", "\u53d1\u5e03\u4eba", "textfield")
FB_PUBLISH_DATE = Field("publish_date", "\u53d1\u5e03\u65e5\u671f", "calendar",
                        required=True)
FB_DEADLINE = Field("deadline", "\u622a\u6b62\u65e5\u671f", "calendar")
FB_STATUS = Field("bounty_status", "\u72b6\u6001", "dict", code="bountyStatus",
                  default="\u5f85\u9886\u53d6")
FB_DESC = Field("bounty_desc", "\u8bfe\u9898\u8bf4\u660e", "textarea",
                required=True)
FB_REQUIRE = Field("bounty_require", "\u4ea4\u4ed8\u8981\u6c42", "textarea")
FB_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_BOUNTY_APPLY = datagrid("dg_bounty_apply", "\u9886\u53d6\u8bb0\u5f55", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "employee_no", "name": "\u5458\u5de5\u7f16\u53f7", "width": "110px"},
    {"id": "employee_name", "name": "\u9886\u53d6\u4eba", "width": "100px"},
    {"id": "apply_date", "name": "\u9886\u53d6\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "finish_date", "name": "\u5b8c\u6210\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "get_score", "name": "\u83b7\u5f97\u79ef\u5206", "mtype": "Number",
     "width": "100px"},
    {"id": "status", "name": "\u72b6\u6001", "width": "100px"},
])


def build_form_bounty():
    p = Page("\u79ef\u5206\u60ac\u8d4f\u8868", FORM_BOUNTY_ID,
             "\u79ef\u5206\u60ac\u8d4f\u8bfe\u9898\u53d1\u5e03\u4e0e\u9886\u53d6")

    p.open_section("sec_b_basic", "\u60ac\u8d4f\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_b_basic", [
        FB_NO, FB_TITLE, FB_SCORE, FB_SCORE_TAG,
        FB_TYPE, FB_PUBLISH_DEPT, FB_PUBLISHER, FB_PUBLISH_DATE,
        FB_DEADLINE, FB_STATUS,
    ], cols=2, section_title="\u60ac\u8d4f\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_b_desc", "\u8bfe\u9898\u8bf4\u660e", flatten=True)
    p.field_grid("fg_b_desc", [FB_DESC, FB_REQUIRE], cols=1,
                 section_title="\u8bfe\u9898\u8bf4\u660e")
    p.close()

    p.open_section("sec_b_apply", "\u9886\u53d6\u8bb0\u5f55", flatten=True)
    grid_block(p, "fg_b_apply", DG_BOUNTY_APPLY)

    p.open_section("sec_b_note", "\u5176\u4ed6", flatten=True)
    p.field_grid("fg_b_note", [FB_NOTE], cols=1, section_title="\u5176\u4ed6")
    p.close()

    attach_block(p, "att_bounty", "\u8bfe\u9898\u9644\u4ef6")
    opinion_block(p, "opinion_bounty")
    p.add(actionbar("actionbar_bounty"))

    return FormBuilder(FORM_BOUNTY_ID, "\u79ef\u5206\u60ac\u8d4f\u8868",
                       "\u79ef\u5206\u60ac\u8d4f\u8bfe\u9898\u53d1\u5e03\u4e0e\u9886\u53d6",
                       page=p)


FORM_BOUNTY = build_form_bounty()


# ==========================================================================
# 表单 10：积分兑换表（官方「积分兑换」按钮）
# ==========================================================================

FORM_EXCHANGE_ID = "f6006010-hr-exchange-form-0000000000001"

FX_NO = Field("exchange_no", "\u5151\u6362\u5355\u53f7", "textfield",
              required=True, readonly=True)
FX_EMP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                  required=True)
FX_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FX_DEPT = Field("dept", "\u90e8\u95e8", "org")
FX_GOODS = Field("goods_name", "\u5151\u6362\u54c1\u540d", "textfield",
                 required=True)
FX_TYPE = Field("goods_type", "\u5151\u6362\u7c7b\u578b", "select",
                options=["\u5b9e\u7269\u5956\u54c1", "\u7ea2\u5305\u7968\u5238",
                         "\u5e74\u5047\u5956\u52b1", "\u57f9\u8bad\u673a\u4f1a",
                         "\u4f18\u5148\u8bc4\u4f18"])
FX_COST = Field("cost_point", "\u6d88\u8017\u79ef\u5206", "number", required=True)
FX_BALANCE = Field("balance_point", "\u5151\u6362\u540e\u4f59\u989d", "number",
                   readonly=True)
FX_COUNT = Field("goods_count", "\u6570\u91cf", "number", default="1")
FX_APPLY_DATE = Field("apply_date", "\u7533\u8bf7\u65e5\u671f", "calendar",
                      required=True)
FX_DELIVERY = Field("delivery_date", "\u53d1\u653e\u65e5\u671f", "calendar")
FX_STATUS = Field("exchange_status", "\u72b6\u6001", "dict", code="approveStatus",
                  default=FLOW_STATUS_DRAFT)
FX_REASON = Field("exchange_reason", "\u5151\u6362\u539f\u56e0", "textarea")
FX_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FX_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_exchange():
    p = Page("\u79ef\u5206\u5151\u6362\u8868", FORM_EXCHANGE_ID,
             "\u5458\u5de5\u79ef\u5206\u5151\u6362\u7533\u8bf7\u4e0e\u53d1\u653e")

    p.open_section("sec_x_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_x_basic", [FX_NO, FX_EMP_NO, FX_NAME, FX_DEPT],
                 cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_x_goods", "\u5151\u6362\u4fe1\u606f", flatten=True)
    p.field_grid("fg_x_goods", [
        FX_GOODS, FX_TYPE, FX_COST, FX_BALANCE,
        FX_COUNT, FX_APPLY_DATE, FX_DELIVERY, FX_STATUS,
    ], cols=2, section_title="\u5151\u6362\u4fe1\u606f")
    p.close()

    p.open_section("sec_x_reason", "\u8bf4\u660e", flatten=True)
    p.field_grid("fg_x_reason", [FX_REASON, FX_NOTE], cols=1,
                 section_title="\u8bf4\u660e")
    p.close()

    p.open_section("sec_x_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_x_op", [FX_HR_OP], cols=1, section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    attach_block(p, "att_exchange", "\u5151\u6362\u9644\u4ef6")
    opinion_block(p, "opinion_exchange")
    p.add(actionbar("actionbar_exchange"))

    return FormBuilder(FORM_EXCHANGE_ID, "\u79ef\u5206\u5151\u6362\u8868",
                       "\u5458\u5de5\u79ef\u5206\u5151\u6362\u7533\u8bf7\u4e0e\u53d1\u653e",
                       page=p)


FORM_EXCHANGE = build_form_exchange()


# ==========================================================================
# 表单 11：请假申请表（官方「员工自助 -> 我要请假」）
# ==========================================================================

FORM_LEAVE_ID = "f6006011-hr-leave-form-0000000000000001"
PROC_LEAVE_ID = "p6006008-hr-leave-apply-00000000000001"

FL_NO = Field("leave_no", "\u8bf7\u5047\u5355\u53f7", "textfield",
              required=True, readonly=True)
FL_NO_EMP = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                  required=True)
FL_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FL_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FL_POSITION = Field("position", "\u5c97\u4f4d", "textfield")
FL_TYPE = Field("leave_type", "\u5047\u671f\u7c7b\u578b", "dict",
                code="leaveType", required=True)
FL_START = Field("start_time", "\u5f00\u59cb\u65f6\u95f4", "calendar",
                 required=True)
FL_END = Field("end_time", "\u7ed3\u675f\u65f6\u95f4", "calendar", required=True)
FL_DAYS = Field("leave_days", "\u8bf7\u5047\u5929\u6570", "number", required=True)
FL_REASON = Field("leave_reason", "\u8bf7\u5047\u4e8b\u7531", "textarea",
                  required=True)
FL_HANDOVER = Field("handover_person", "\u5de5\u4f5c\u4ea4\u4ee3\u4eba", "textfield")
FL_HANDOVER_MATTER = Field("handover_matter", "\u4ea4\u4ee3\u4e8b\u9879", "textarea")
FL_CONTACT = Field("contact_phone", "\u8bf7\u5047\u671f\u95f4\u8054\u7cfb\u7535\u8bdd",
                   "textfield")
FL_STATUS = Field("leave_status", "\u72b6\u6001", "dict", code="approveStatus",
                  default=FLOW_STATUS_DRAFT)
FL_LEADER_OP = Field("leader_opinion", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u610f\u89c1",
                     "textarea")
FL_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FL_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_leave():
    p = Page("\u8bf7\u5047\u7533\u8bf7\u8868", FORM_LEAVE_ID,
             "\u5458\u5de5\u8bf7\u5047\u7533\u8bf7\u4e0e\u5ba1\u6279")

    p.open_section("sec_l_basic", "\u7533\u8bf7\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_l_basic", [
        FL_NO, FL_NO_EMP, FL_NAME, FL_DEPT, FL_POSITION,
    ], cols=2, section_title="\u7533\u8bf7\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_l_leave", "\u8bf7\u5047\u4fe1\u606f", flatten=True)
    p.field_grid("fg_l_leave", [
        FL_TYPE, FL_DAYS, FL_START, FL_END,
        FL_HANDOVER, FL_CONTACT,
    ], cols=2, section_title="\u8bf7\u5047\u4fe1\u606f")
    p.close()

    p.open_section("sec_l_reason", "\u8bf7\u5047\u8bf4\u660e", flatten=True)
    p.field_grid("fg_l_reason", [FL_REASON, FL_HANDOVER_MATTER],
                 cols=1, section_title="\u8bf7\u5047\u8bf4\u660e")
    p.close()

    p.open_section("sec_l_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_l_op", [FL_LEADER_OP, FL_HR_OP, FL_STATUS, FL_NOTE],
                 cols=2, section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    attach_block(p, "att_leave", "\u8bf7\u5047\u9644\u4ef6\uff08\u75c5\u5047\u8bc1\u660e\u7b49\uff09")
    opinion_block(p, "opinion_leave")
    p.add(actionbar("actionbar_leave"))

    return FormBuilder(FORM_LEAVE_ID, "\u8bf7\u5047\u7533\u8bf7\u8868",
                       "\u5458\u5de5\u8bf7\u5047\u7533\u8bf7\u4e0e\u5ba1\u6279", page=p)


FORM_LEAVE = build_form_leave()


# ==========================================================================
# 表单 12：加班申请表（官方「员工自助 -> 我要加班」）
# ==========================================================================

FORM_OVERTIME_ID = "f6006012-hr-overtime-form-000000000001"
PROC_OVERTIME_ID = "p6006009-hr-overtime-000000000000001"

FW_NO = Field("overtime_no", "\u52a0\u73ed\u5355\u53f7", "textfield",
              required=True, readonly=True)
FW_EMP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                  required=True)
FW_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FW_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FW_TYPE = Field("overtime_type", "\u52a0\u73ed\u7c7b\u578b", "dict",
                code="overtimeType", required=True)
FW_START = Field("start_time", "\u5f00\u59cb\u65f6\u95f4", "calendar",
                 required=True)
FW_END = Field("end_time", "\u7ed3\u675f\u65f6\u95f4", "calendar", required=True)
FW_HOURS = Field("overtime_hours", "\u52a0\u73ed\u65f6\u957f\uff08\u5c0f\u65f6\uff09",
                 "number", required=True)
FW_REASON = Field("overtime_reason", "\u52a0\u73ed\u4e8b\u7531", "textarea",
                  required=True)
FW_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7",
                   "textfield", description="\u4e0e\u9879\u76ee\u7ba1\u7406\u5e94\u7528\u8054\u52a8")
FW_COMPENSATE = Field("compensate_type", "\u8865\u507f\u65b9\u5f0f", "radio",
                      options=["\u8c03\u4f11", "\u52a0\u73ed\u8d39",
                               "\u8c03\u4f11+\u52a0\u73ed\u8d39"])
FW_STATUS = Field("overtime_status", "\u72b6\u6001", "dict",
                  code="approveStatus", default=FLOW_STATUS_DRAFT)
FW_LEADER_OP = Field("leader_opinion", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u610f\u89c1",
                     "textarea")
FW_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FW_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_overtime():
    p = Page("\u52a0\u73ed\u7533\u8bf7\u8868", FORM_OVERTIME_ID,
             "\u5458\u5de5\u52a0\u73ed\u7533\u8bf7\u4e0e\u5ba1\u6279")

    p.open_section("sec_w_basic", "\u7533\u8bf7\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_w_basic", [FW_NO, FW_EMP_NO, FW_NAME, FW_DEPT],
                 cols=2, section_title="\u7533\u8bf7\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_w_ot", "\u52a0\u73ed\u4fe1\u606f", flatten=True)
    p.field_grid("fg_w_ot", [
        FW_TYPE, FW_HOURS, FW_START, FW_END,
        FW_PROJECT, FW_COMPENSATE,
    ], cols=2, section_title="\u52a0\u73ed\u4fe1\u606f")
    p.close()

    p.open_section("sec_w_reason", "\u52a0\u73ed\u8bf4\u660e", flatten=True)
    p.field_grid("fg_w_reason", [FW_REASON], cols=1,
                 section_title="\u52a0\u73ed\u8bf4\u660e")
    p.close()

    p.open_section("sec_w_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_w_op", [FW_LEADER_OP, FW_HR_OP, FW_STATUS, FW_NOTE],
                 cols=2, section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    attach_block(p, "att_overtime", "\u52a0\u73ed\u4f9d\u636e\u9644\u4ef6")
    opinion_block(p, "opinion_overtime")
    p.add(actionbar("actionbar_overtime"))

    return FormBuilder(FORM_OVERTIME_ID, "\u52a0\u73ed\u7533\u8bf7\u8868",
                       "\u5458\u5de5\u52a0\u73ed\u7533\u8bf7\u4e0e\u5ba1\u6279", page=p)


FORM_OVERTIME = build_form_overtime()


# ==========================================================================
# 表单 13：出差申请表（官方「员工自助 -> 我要出差」）
# ==========================================================================

FORM_TRAVEL_ID = "f6006013-hr-travel-form-000000000000001"
PROC_TRAVEL_ID = "p6006010-hr-travel-00000000000000001"

FV_NO = Field("travel_no", "\u51fa\u5dee\u5355\u53f7", "textfield",
              required=True, readonly=True)
FV_EMP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                  required=True)
FV_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FV_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FV_TYPE = Field("travel_type", "\u51fa\u5dee\u7c7b\u578b", "select",
                options=["\u56fd\u5185\u51fa\u5dee", "\u5883\u5916\u51fa\u5dee",
                         "\u672c\u5e02\u516c\u52a1"])
FV_DEST = Field("destination", "\u51fa\u5dee\u5730\u70b9", "textfield",
                required=True)
FV_START = Field("start_date", "\u51fa\u53d1\u65e5\u671f", "calendar",
                 required=True)
FV_END = Field("end_date", "\u8fd4\u56de\u65e5\u671f", "calendar", required=True)
FV_DAYS = Field("travel_days", "\u51fa\u5dee\u5929\u6570", "number", required=True)
FV_BUDGET = Field("budget_amount", "\u9884\u4f30\u8d39\u7528\uff08\u5143\uff09",
                  "currency")
FV_PROJECT = Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7",
                   "textfield", description="\u4e0e\u9879\u76ee\u7ba1\u7406/\u9884\u7b97\u5e94\u7528\u8054\u52a8")
FV_REASON = Field("travel_reason", "\u51fa\u5dee\u4e8b\u7531", "textarea",
                  required=True)
FV_STATUS = Field("travel_status", "\u72b6\u6001", "dict",
                  code="approveStatus", default=FLOW_STATUS_DRAFT)
FV_LEADER_OP = Field("leader_opinion", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u610f\u89c1",
                     "textarea")
FV_FIN_OP = Field("finance_opinion", "\u8d22\u52a1\u610f\u89c1", "textarea")
FV_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_TRAVEL_PLAN = datagrid("dg_travel_plan", "\u884c\u7a0b\u5b89\u6392", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "date", "name": "\u65e5\u671f", "mtype": "Calendar", "width": "110px"},
    {"id": "place", "name": "\u5730\u70b9", "width": "160px"},
    {"id": "matter", "name": "\u5de5\u4f5c\u5185\u5bb9", "width": "240px"},
    {"id": "transport", "name": "\u4ea4\u901a\u5de5\u5177", "width": "110px"},
    {"id": "cost", "name": "\u9884\u8ba1\u8d39\u7528\uff08\u5143\uff09",
     "mtype": "Currency", "width": "120px"},
], is_total=True)


def build_form_travel():
    p = Page("\u51fa\u5dee\u7533\u8bf7\u8868", FORM_TRAVEL_ID,
             "\u5458\u5de5\u51fa\u5dee\u7533\u8bf7\u4e0e\u5ba1\u6279")

    p.open_section("sec_v_basic", "\u7533\u8bf7\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_v_basic", [FV_NO, FV_EMP_NO, FV_NAME, FV_DEPT],
                 cols=2, section_title="\u7533\u8bf7\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_v_travel", "\u51fa\u5dee\u4fe1\u606f", flatten=True)
    p.field_grid("fg_v_travel", [
        FV_TYPE, FV_DEST, FV_START, FV_END,
        FV_DAYS, FV_BUDGET, FV_PROJECT, FV_STATUS,
    ], cols=2, section_title="\u51fa\u5dee\u4fe1\u606f")
    p.close()

    p.open_section("sec_v_plan", "\u884c\u7a0b\u5b89\u6392", flatten=True)
    grid_block(p, "fg_v_plan", DG_TRAVEL_PLAN)

    p.open_section("sec_v_reason", "\u51fa\u5dee\u8bf4\u660e", flatten=True)
    p.field_grid("fg_v_reason", [FV_REASON], cols=1,
                 section_title="\u51fa\u5dee\u8bf4\u660e")
    p.close()

    p.open_section("sec_v_op", "\u5ba1\u6279\u610f\u89c1", flatten=True)
    p.field_grid("fg_v_op", [FV_LEADER_OP, FV_FIN_OP, FV_NOTE], cols=1,
                 section_title="\u5ba1\u6279\u610f\u89c1")
    p.close()

    attach_block(p, "att_travel", "\u51fa\u5dee\u9644\u4ef6")
    opinion_block(p, "opinion_travel")
    p.add(actionbar("actionbar_travel"))

    return FormBuilder(FORM_TRAVEL_ID, "\u51fa\u5dee\u7533\u8bf7\u8868",
                       "\u5458\u5de5\u51fa\u5dee\u7533\u8bf7\u4e0e\u5ba1\u6279", page=p)


FORM_TRAVEL = build_form_travel()


# ==========================================================================
# 表单 14：考勤月报表（官方「考勤管理 -> 我的考勤月报」）
# ==========================================================================

FORM_ATTEND_ID = "f6006014-hr-attend-form-0000000000001"

FTT_NO = Field("attend_no", "\u8003\u52e4\u5355\u53f7", "textfield",
               required=True, readonly=True)
FTT_EMP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                   required=True)
FTT_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FTT_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FTT_PERIOD = Field("attend_period", "\u8003\u52e4\u5468\u671f", "textfield",
                   required=True, description="\u5982 2026\u5e7405\u6708")
FTT_START = Field("period_start", "\u5468\u671f\u5f00\u59cb", "calendar")
FTT_END = Field("period_end", "\u5468\u671f\u7ed3\u675f", "calendar")
FTT_SHOULD = Field("should_days", "\u5e94\u51fa\u52e4\u5929\u6570", "number")
FTT_ACTUAL = Field("actual_days", "\u5b9e\u51fa\u52e4\u5929\u6570", "number")
FTT_LATE = Field("late_count", "\u8fdf\u5230\u6b21\u6570", "number")
FTT_EARLY = Field("early_count", "\u65e9\u9000\u6b21\u6570", "number")
FTT_ABSENT = Field("absent_count", "\u65f7\u5de5\u6b21\u6570", "number")
FTT_LEAVE_DAYS = Field("leave_days", "\u8bf7\u5047\u5929\u6570", "number")
FTT_OT_HOURS = Field("overtime_hours", "\u52a0\u73ed\u65f6\u957f", "number")
FTT_TRAVEL_DAYS = Field("travel_days", "\u51fa\u5dee\u5929\u6570", "number")
FTT_STATUS = Field("attend_status", "\u72b6\u6001", "dict",
                   code="attendStatus", default="\u5f85\u786e\u8ba4")
FTT_HR_OP = Field("hr_opinion", "\u4eba\u4e8b\u610f\u89c1", "textarea")
FTT_EMP_CONFIRM = Field("employee_confirm", "\u5458\u5de5\u786e\u8ba4", "radio",
                        options=["\u5df2\u786e\u8ba4", "\u6709\u5f02\u8bae"])
FTT_NOTE = Field("remark", "\u5f02\u8bae\u8bf4\u660e", "textarea")

DG_ATTEND_DAY = datagrid("dg_attend_day", "\u65e5\u8003\u52e4\u660e\u7ec6", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "attend_date", "name": "\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "week_day", "name": "\u661f\u671f", "width": "70px"},
    {"id": "on_time", "name": "\u4e0a\u73ed\u65f6\u95f4", "width": "100px"},
    {"id": "off_time", "name": "\u4e0b\u73ed\u65f6\u95f4", "width": "100px"},
    {"id": "attend_type", "name": "\u8003\u52e4\u7c7b\u578b", "width": "110px"},
    {"id": "result", "name": "\u7ed3\u679c", "width": "100px"},
    {"id": "note", "name": "\u8bf4\u660e", "width": "180px"},
])


def build_form_attend():
    p = Page("\u8003\u52e4\u6708\u62a5\u8868", FORM_ATTEND_ID,
             "\u5458\u5de5\u6708\u5ea6\u8003\u52e4\u6c47\u603b\u4e0e\u786e\u8ba4")

    p.open_section("sec_tt_basic", "\u57fa\u672c\u4fe1\u606f", flatten=True)
    p.field_grid("fg_tt_basic", [
        FTT_NO, FTT_EMP_NO, FTT_NAME, FTT_DEPT,
        FTT_PERIOD, FTT_START, FTT_END, FTT_STATUS,
    ], cols=2, section_title="\u57fa\u672c\u4fe1\u606f")
    p.close()

    p.open_section("sec_tt_stat", "\u8003\u52e4\u6c47\u603b", flatten=True)
    p.field_grid("fg_tt_stat", [
        FTT_SHOULD, FTT_ACTUAL, FTT_LATE, FTT_EARLY,
        FTT_ABSENT, FTT_LEAVE_DAYS, FTT_OT_HOURS, FTT_TRAVEL_DAYS,
    ], cols=2, section_title="\u8003\u52e4\u6c47\u603b")
    p.close()

    p.open_section("sec_tt_day", "\u65e5\u8003\u52e4\u660e\u7ec6", flatten=True)
    grid_block(p, "fg_tt_day", DG_ATTEND_DAY)

    p.open_section("sec_tt_confirm", "\u786e\u8ba4\u4e0e\u5f02\u8bae", flatten=True)
    p.field_grid("fg_tt_confirm", [FTT_EMP_CONFIRM, FTT_HR_OP, FTT_NOTE],
                 cols=2, section_title="\u786e\u8ba4\u4e0e\u5f02\u8bae")
    p.close()

    attach_block(p, "att_attend", "\u8003\u52e4\u5f02\u5e38\u8bf4\u660e\u9644\u4ef6")
    opinion_block(p, "opinion_attend")
    p.add(actionbar("actionbar_attend"))

    return FormBuilder(FORM_ATTEND_ID, "\u8003\u52e4\u6708\u62a5\u8868",
                       "\u5458\u5de5\u6708\u5ea6\u8003\u52e4\u6c47\u603b\u4e0e\u786e\u8ba4",
                       page=p)


FORM_ATTEND = build_form_attend()


# ==========================================================================
# 表单 15：员工自助申请表
# --------------------------------------------------------------------------
# 官方截图 1652073737833 的列表列：流程类型 | 标题 | 发起人 | 开始时间 | 当前步骤
# 本表单是「员工自助」统一入口的承载表单。
# ==========================================================================

FORM_SELF_ID = "f6006015-hr-self-form-00000000000000001"

FS_APPLY_NO = Field("self_no", "\u7533\u8bf7\u5355\u53f7", "textfield",
                    required=True, readonly=True)
FS_EMP_NO = Field("employee_no", "\u5458\u5de5\u7f16\u53f7", "textfield",
                  required=True)
FS_NAME = Field("employee_name", "\u59d3\u540d", "textfield", required=True)
FS_DEPT = Field("dept", "\u90e8\u95e8", "org", required=True)
FS_TYPE = Field("self_type", "\u7533\u8bf7\u7c7b\u578b", "dict",
                code="selfServiceType", required=True)
FS_TITLE = Field("apply_title", "\u7533\u8bf7\u6807\u9898", "textfield",
                 required=True)
FS_START = Field("start_time", "\u5f00\u59cb\u65f6\u95f4", "calendar")
FS_END = Field("end_time", "\u7ed3\u675f\u65f6\u95f4", "calendar")
FS_CURRENT = Field("current_step", "\u5f53\u524d\u6b65\u9aa4", "textfield",
                   readonly=True)
FS_STATUS = Field("self_status", "\u72b6\u6001", "dict", code="approveStatus",
                  default=FLOW_STATUS_DRAFT)
FS_CONTENT = Field("apply_content", "\u7533\u8bf7\u5185\u5bb9", "textarea",
                   required=True)
FS_CONTACT = Field("contact_phone", "\u8054\u7cfb\u7535\u8bdd", "textfield")
FS_ATTACH_DESC = Field("attach_desc", "\u9644\u4ef6\u8bf4\u660e", "textarea")
FS_HR_OP = Field("hr_opinion", "\u5904\u7406\u610f\u89c1", "textarea")
FS_NOTE = Field("remark", "\u5907\u6ce8", "textarea")


def build_form_self():
    p = Page("\u5458\u5de5\u81ea\u52a9\u7533\u8bf7\u8868", FORM_SELF_ID,
             "\u5458\u5de5\u81ea\u52a9\u7efc\u5408\u7533\u8bf7\u7edf\u4e00\u5165\u53e3")

    p.open_section("sec_s_basic", "\u7533\u8bf7\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_s_basic", [FS_APPLY_NO, FS_EMP_NO, FS_NAME, FS_DEPT],
                 cols=2, section_title="\u7533\u8bf7\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_s_apply", "\u7533\u8bf7\u4fe1\u606f", flatten=True)
    p.field_grid("fg_s_apply", [
        FS_TYPE, FS_TITLE, FS_START, FS_END,
        FS_CURRENT, FS_STATUS, FS_CONTACT,
    ], cols=2, section_title="\u7533\u8bf7\u4fe1\u606f")
    p.close()

    p.open_section("sec_s_content", "\u7533\u8bf7\u5185\u5bb9", flatten=True)
    p.field_grid("fg_s_content", [FS_CONTENT, FS_ATTACH_DESC],
                 cols=1, section_title="\u7533\u8bf7\u5185\u5bb9")
    p.close()

    p.open_section("sec_s_op", "\u5904\u7406\u610f\u89c1", flatten=True)
    p.field_grid("fg_s_op", [FS_HR_OP, FS_NOTE], cols=1,
                 section_title="\u5904\u7406\u610f\u89c1")
    p.close()

    attach_block(p, "att_self", "\u7533\u8bf7\u9644\u4ef6")
    opinion_block(p, "opinion_self")
    p.add(actionbar("actionbar_self"))

    return FormBuilder(FORM_SELF_ID, "\u5458\u5de5\u81ea\u52a9\u7533\u8bf7\u8868",
                       "\u5458\u5de5\u81ea\u52a9\u7efc\u5408\u7533\u8bf7\u7edf\u4e00\u5165\u53e3",
                       page=p)


FORM_SELF = build_form_self()


# ==========================================================================
# 表单 16：个人设置表（官方「个人设置」，截图 1652073737436）
# --------------------------------------------------------------------------
# 官方字段顺序：姓名 / 工号 / 邮件地址 / 手机号码 / 办公电话 /
#               微信号 / QQ / 论坛昵称 / 个人签名 / 语言设置
# 页面顶部另有「头像 + 更换头像」按钮（非表单字段，由门户页承载）。
# ==========================================================================

FORM_PROFILE_ID = "f6006016-hr-profile-form-0000000000001"

FPR_NAME = Field("employee_name", "\u59d3\u540d", "textfield",
                 required=True, readonly=True)
FPR_NO = Field("employee_no", "\u5de5\u53f7", "textfield",
               required=True, readonly=True)
FPR_EMAIL = Field("email", "\u90ae\u4ef6\u5730\u5740", "textfield")
FPR_MOBILE = Field("mobile", "\u624b\u673a\u53f7\u7801", "textfield")
FPR_OFFICE_TEL = Field("office_phone", "\u529e\u516c\u7535\u8bdd", "textfield")
FPR_WECHAT = Field("wechat", "\u5fae\u4fe1\u53f7", "textfield")
FPR_QQ = Field("qq", "QQ", "textfield")
FPR_FORUM = Field("forum_nickname", "\u8bba\u575b\u6635\u79f0", "textfield")
FPR_SIGN = Field("personal_sign", "\u4e2a\u4eba\u7b7e\u540d", "textarea")
FPR_LANG = Field("language", "\u8bed\u8a00\u8bbe\u7f6e", "dict",
                 code="languageType", default="\u4e2d\u6587\u7b80\u4f53")
FPR_AVATAR = Field("avatar", "\u5934\u50cf\u5730\u5740", "textfield")


def build_form_profile():
    p = Page("\u4e2a\u4eba\u8bbe\u7f6e\u8868", FORM_PROFILE_ID,
             "\u5458\u5de5\u4e2a\u4eba\u4fe1\u606f\u7ef4\u62a4")

    p.open_section("sec_pr_basic", "\u4e2a\u4eba\u4fe1\u606f", flatten=True)
    p.field_grid("fg_pr_basic", [
        FPR_NAME, FPR_NO, FPR_EMAIL, FPR_MOBILE,
        FPR_OFFICE_TEL, FPR_WECHAT, FPR_QQ, FPR_FORUM,
        FPR_LANG, FPR_AVATAR,
    ], cols=2, section_title="\u4e2a\u4eba\u4fe1\u606f")
    p.close()

    p.open_section("sec_pr_sign", "\u4e2a\u4eba\u7b7e\u540d", flatten=True)
    p.field_grid("fg_pr_sign", [FPR_SIGN], cols=1, section_title="\u4e2a\u4eba\u7b7e\u540d")
    p.close()

    attach_block(p, "att_profile", "\u9644\u4ef6")
    p.add(actionbar("actionbar_profile"))

    return FormBuilder(FORM_PROFILE_ID, "\u4e2a\u4eba\u8bbe\u7f6e\u8868",
                       "\u5458\u5de5\u4e2a\u4eba\u4fe1\u606f\u7ef4\u62a4", page=p)


FORM_PROFILE = build_form_profile()


# ==========================================================================
# 表单 17：考勤配置表（官方「考勤管理 -> 配置」）
# ==========================================================================

FORM_ATTCFG_ID = "f6006017-hr-attend-cfg-form-00000000001"

FAC_PERIOD = Field("period_name", "\u8003\u52e4\u5468\u671f\u540d\u79f0",
                   "textfield", required=True)
FAC_MONTH = Field("belong_month", "\u6240\u5c5e\u6708\u4efd", "textfield",
                  required=True)
FAC_START = Field("period_start", "\u5468\u671f\u5f00\u59cb\u65e5", "calendar")
FAC_END = Field("period_end", "\u5468\u671f\u7ed3\u675f\u65e5", "calendar")
FAC_WORK_START = Field("work_start_time", "\u4e0a\u73ed\u65f6\u95f4", "textfield",
                       default="08:30")
FAC_WORK_END = Field("work_end_time", "\u4e0b\u73ed\u65f6\u95f4", "textfield",
                     default="17:30")
FAC_FLEX = Field("flex_minutes", "\u5f39\u6027\u79d2\u6570\uff08\u5206\u949f\uff09",
                 "number", default="30")
FAC_LATE_RULE = Field("late_rule", "\u8fdf\u5230\u89c4\u5219", "textarea")
FAC_ABSENT_RULE = Field("absent_rule", "\u65f7\u5de5\u89c4\u5219", "textarea")
FAC_WORK_DAYS = Field("work_days", "\u5de5\u4f5c\u65e5", "checkbox",
                      options=["\u5468\u4e00", "\u5468\u4e8c", "\u5468\u4e09",
                               "\u5468\u56db", "\u5468\u4e94", "\u5468\u516d",
                               "\u5468\u65e5"])
FAC_HR_ADMIN = Field("attend_admin", "\u8003\u52e4\u7ba1\u7406\u5458", "org")
FAC_ENABLE = Field("is_enable", "\u662f\u5426\u542f\u7528", "radio",
                   options=["\u542f\u7528", "\u505c\u7528"], default="\u542f\u7528")
FAC_NOTE = Field("remark", "\u5907\u6ce8", "textarea")

DG_HOLIDAY = datagrid("dg_holiday", "\u8282\u5047\u65e5\u8bbe\u7f6e", [
    {"id": "__idx__", "name": "\u5e8f\u53f7"},
    {"id": "holiday_name", "name": "\u8282\u5047\u65e5\u540d\u79f0", "width": "180px"},
    {"id": "start_date", "name": "\u5f00\u59cb\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "end_date", "name": "\u7ed3\u675f\u65e5\u671f", "mtype": "Calendar",
     "width": "110px"},
    {"id": "days", "name": "\u5929\u6570", "mtype": "Number", "width": "80px"},
    {"id": "holiday_type", "name": "\u7c7b\u578b", "width": "110px"},
])


def build_form_attend_cfg():
    p = Page("\u8003\u52e4\u914d\u7f6e\u8868", FORM_ATTCFG_ID,
             "\u8003\u52e4\u5468\u671f\u3001\u89c4\u5219\u4e0e\u8282\u5047\u65e5\u914d\u7f6e")

    p.open_section("sec_ac_basic", "\u8003\u52e4\u5468\u671f", flatten=True)
    p.field_grid("fg_ac_basic", [
        FAC_PERIOD, FAC_MONTH, FAC_START, FAC_END,
        FAC_WORK_START, FAC_WORK_END, FAC_FLEX, FAC_WORK_DAYS,
    ], cols=2, section_title="\u8003\u52e4\u5468\u671f")
    p.close()

    p.open_section("sec_ac_rule", "\u8003\u52e4\u89c4\u5219", flatten=True)
    p.field_grid("fg_ac_rule", [FAC_LATE_RULE, FAC_ABSENT_RULE],
                 cols=1, section_title="\u8003\u52e4\u89c4\u5219")
    p.close()

    p.open_section("sec_ac_holiday", "\u8282\u5047\u65e5\u8bbe\u7f6e", flatten=True)
    grid_block(p, "fg_ac_holiday", DG_HOLIDAY)

    p.open_section("sec_ac_admin", "\u7ba1\u7406\u4e0e\u542f\u7528", flatten=True)
    p.field_grid("fg_ac_admin", [FAC_HR_ADMIN, FAC_ENABLE, FAC_NOTE],
                 cols=2, section_title="\u7ba1\u7406\u4e0e\u542f\u7528")
    p.close()

    attach_block(p, "att_attend_cfg", "\u914d\u7f6e\u4f9d\u636e\u9644\u4ef6")
    p.add(actionbar("actionbar_attend_cfg"))

    return FormBuilder(FORM_ATTCFG_ID, "\u8003\u52e4\u914d\u7f6e\u8868",
                       "\u8003\u52e4\u5468\u671f\u3001\u89c4\u5219\u4e0e\u8282\u5047\u65e5\u914d\u7f6e",
                       page=p)


FORM_ATTCFG = build_form_attend_cfg()


# ==========================================================================
# 流程（11 个）
# --------------------------------------------------------------------------
# 【注意】ProcessBuilder.to_wrap() 在人工节点未显式指定 form_id 时，
# 会回退到流程级 form_id。此处仍显式传入，避免后续重构踩坑。
# ==========================================================================

# --- 1. 员工入职流程（官方「员工入职公示」）-------------------------------
PROC_ONBOARD = ProcessBuilder(
    PROC_EMP_ONBOARD_ID, "\u5458\u5de5\u5165\u804c\u6d41\u7a0b",
    "\u65b0\u5458\u5165\u804c\u7533\u8bf7\u3001\u4eba\u4e8b\u5ba1\u6838\u4e0e\u5165\u804c\u529e\u7406",
    form_id=FORM_ONBOARD_ID,
    activities=[
        Activity("a_o_apply", "\u5165\u804c\u7533\u8bf7", "manual",
                 form_id=FORM_ONBOARD_ID, task_script=SCRIPT_SELF),
        Activity("a_o_dept", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u786e\u8ba4", "manual",
                 form_id=FORM_ONBOARD_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_o_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_ONBOARD_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_o_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_ONBOARD_ID, task_script=SCRIPT_GM),
        Activity("a_o_reg", "\u5efa\u7acb\u5458\u5de5\u6863\u6848", "manual",
                 form_id=FORM_ONBOARD_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_o_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_o_apply", "a_o_dept", "\u63d0\u4ea4", ""),
        ("a_o_dept", "a_o_hr", "\u540c\u610f", ""),
        ("a_o_dept", "a_o_apply", "\u9000\u56de", ""),
        ("a_o_hr", "a_o_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_o_hr", "a_o_dept", "\u9000\u56de", ""),
        ("a_o_gm", "a_o_reg", "\u6279\u51c6", ""),
        ("a_o_reg", "a_o_end", "\u5f52\u6863", ""),
    ],
)

# --- 2. 员工转岗流程（官方「员工转岗公示」）-------------------------------
PROC_TRANSFER = ProcessBuilder(
    PROC_EMP_TRANSFER_ID, "\u5458\u5de5\u8f6c\u5c97\u6d41\u7a0b",
    "\u5458\u5de5\u5c97\u4f4d\u53d8\u52a8\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_TRANSFER_ID,
    activities=[
        Activity("a_t_apply", "\u8f6c\u5c97\u7533\u8bf7", "manual",
                 form_id=FORM_TRANSFER_ID, task_script=SCRIPT_SELF),
        Activity("a_t_old", "\u539f\u90e8\u95e8\u610f\u89c1", "manual",
                 form_id=FORM_TRANSFER_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_t_new", "\u65b0\u90e8\u95e8\u610f\u89c1", "manual",
                 form_id=FORM_TRANSFER_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_t_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_TRANSFER_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_t_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_TRANSFER_ID, task_script=SCRIPT_GM),
        Activity("a_t_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_t_apply", "a_t_old", "\u63d0\u4ea4", ""),
        ("a_t_old", "a_t_new", "\u540c\u610f\u8f6c\u51fa", ""),
        ("a_t_old", "a_t_apply", "\u9000\u56de", ""),
        ("a_t_new", "a_t_hr", "\u540c\u610f\u63a5\u6536", ""),
        ("a_t_new", "a_t_apply", "\u9000\u56de", ""),
        ("a_t_hr", "a_t_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_t_gm", "a_t_end", "\u6279\u51c6", ""),
    ],
)

# --- 3. 员工转正流程（官方「员工转正公示」）-------------------------------
PROC_REGULAR = ProcessBuilder(
    PROC_EMP_REGULAR_ID, "\u5458\u5de5\u8f6c\u6b63\u6d41\u7a0b",
    "\u8bd5\u7528\u671f\u5458\u5de5\u8f6c\u6b63\u8003\u8bc4\u4e0e\u5ba1\u6279",
    form_id=FORM_REGULAR_ID,
    activities=[
        Activity("a_r_apply", "\u8f6c\u6b63\u7533\u8bf7", "manual",
                 form_id=FORM_REGULAR_ID, task_script=SCRIPT_SELF),
        Activity("a_r_dept", "\u90e8\u95e8\u8003\u8bc4", "manual",
                 form_id=FORM_REGULAR_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_r_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_REGULAR_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_r_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_REGULAR_ID, task_script=SCRIPT_GM),
        Activity("a_r_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_r_apply", "a_r_dept", "\u63d0\u4ea4", ""),
        ("a_r_dept", "a_r_hr", "\u8bc4\u4ef7\u5b8c\u6210", ""),
        ("a_r_dept", "a_r_apply", "\u9000\u56de", ""),
        ("a_r_hr", "a_r_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_r_gm", "a_r_end", "\u6279\u51c6", ""),
    ],
)

# --- 4. 员工离职流程（官方「员工离职公示」）-------------------------------
PROC_RESIGN = ProcessBuilder(
    PROC_EMP_LEAVE_ID, "\u5458\u5de5\u79bb\u804c\u6d41\u7a0b",
    "\u5458\u5de5\u79bb\u804c\u7533\u8bf7\u3001\u5de5\u4f5c\u4ea4\u63a5\u4e0e\u5ba1\u6279",
    form_id=FORM_RESIGN_ID,
    activities=[
        Activity("a_q_apply", "\u79bb\u804c\u7533\u8bf7", "manual",
                 form_id=FORM_RESIGN_ID, task_script=SCRIPT_SELF),
        Activity("a_q_hand", "\u5de5\u4f5c\u4ea4\u63a5", "manual",
                 form_id=FORM_RESIGN_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_q_dept", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u610f\u89c1", "manual",
                 form_id=FORM_RESIGN_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_q_hr", "\u4eba\u4e8b\u5ba1\u6838\u4e0e\u7ed3\u7b97", "manual",
                 form_id=FORM_RESIGN_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_q_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_RESIGN_ID, task_script=SCRIPT_GM),
        Activity("a_q_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_q_apply", "a_q_hand", "\u63d0\u4ea4", ""),
        ("a_q_hand", "a_q_dept", "\u4ea4\u63a5\u5b8c\u6210", ""),
        ("a_q_dept", "a_q_hr", "\u540c\u610f", ""),
        ("a_q_dept", "a_q_apply", "\u9000\u56de", ""),
        ("a_q_hr", "a_q_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_q_gm", "a_q_end", "\u6279\u51c6", ""),
    ],
)

# --- 5. 岗位发布流程（官方「人才市场 -> 岗位池」）-------------------------
PROC_JOB_PUBLISH = ProcessBuilder(
    PROC_JOB_PUBLISH_ID, "\u5c97\u4f4d\u53d1\u5e03\u6d41\u7a0b",
    "\u5185\u90e8\u7ade\u8058\u5c97\u4f4d\u53d1\u5e03\u5ba1\u6838",
    form_id=FORM_JOB_ID,
    activities=[
        Activity("a_j_apply", "\u5c97\u4f4d\u7533\u62a5", "manual",
                 form_id=FORM_JOB_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_j_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_JOB_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_j_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_JOB_ID, task_script=SCRIPT_GM),
        Activity("a_j_pub", "\u5c97\u4f4d\u53d1\u5e03", "manual",
                 form_id=FORM_JOB_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_j_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_j_apply", "a_j_hr", "\u63d0\u4ea4", ""),
        ("a_j_hr", "a_j_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_j_hr", "a_j_apply", "\u9000\u56de", ""),
        ("a_j_gm", "a_j_pub", "\u6279\u51c6", ""),
        ("a_j_pub", "a_j_end", "\u53d1\u5e03\u5b8c\u6210", ""),
    ],
)

# --- 6. 岗位竞聘报名流程（官方「我的报名表」）-----------------------------
PROC_JOB_APPLY = ProcessBuilder(
    PROC_JOB_APPLY_ID, "\u5c97\u4f4d\u7ade\u8058\u62a5\u540d\u6d41\u7a0b",
    "\u5458\u5de5\u7ade\u8058\u62a5\u540d\u3001\u9762\u8bd5\u4e0e\u5165\u9009\u516c\u793a",
    form_id=FORM_JOB_APPLY_ID,
    activities=[
        Activity("a_a_apply", "\u7ade\u8058\u62a5\u540d", "manual",
                 form_id=FORM_JOB_APPLY_ID, task_script=SCRIPT_SELF),
        Activity("a_a_dept", "\u73b0\u90e8\u95e8\u610f\u89c1", "manual",
                 form_id=FORM_JOB_APPLY_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_a_hr", "\u4eba\u4e8b\u8d44\u683c\u5ba1\u67e5", "manual",
                 form_id=FORM_JOB_APPLY_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_a_interview", "\u7ade\u8058\u9762\u8bd5\u8bc4\u4f30", "manual",
                 form_id=FORM_JOB_APPLY_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_a_result", "\u5165\u9009\u7ed3\u679c\u516c\u793a", "manual",
                 form_id=FORM_JOB_APPLY_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_a_apply", "a_a_dept", "\u63d0\u4ea4", ""),
        ("a_a_dept", "a_a_hr", "\u540c\u610f\u62a5\u540d", ""),
        ("a_a_dept", "a_a_apply", "\u9000\u56de", ""),
        ("a_a_hr", "a_a_interview", "\u8d44\u683c\u5408\u683c", ""),
        ("a_a_hr", "a_a_apply", "\u8d44\u683c\u4e0d\u7b26", ""),
        ("a_a_interview", "a_a_result", "\u8bc4\u4f30\u5b8c\u6210", ""),
        ("a_a_result", "a_a_end", "\u516c\u793a\u65e0\u5f02\u8bae", ""),
    ],
)

# --- 7. 积分授予流程（官方「积分管理 -> 积分录入」）-----------------------
PROC_POINT_GRANT = ProcessBuilder(
    PROC_POINT_GRANT_ID, "\u79ef\u5206\u6388\u4e88\u6d41\u7a0b",
    "\u5458\u5de5\u79ef\u5206\u6388\u4e88\u4e0e\u5ba1\u6279",
    form_id=FORM_POINT_ID,
    activities=[
        Activity("a_p_apply", "\u79ef\u5206\u7533\u62a5", "manual",
                 form_id=FORM_POINT_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_p_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_POINT_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_p_gm", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual",
                 form_id=FORM_POINT_ID, task_script=SCRIPT_GM),
        Activity("a_p_pub", "\u79ef\u5206\u516c\u793a", "manual",
                 form_id=FORM_POINT_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_p_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_p_apply", "a_p_hr", "\u63d0\u4ea4", ""),
        ("a_p_hr", "a_p_gm", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_p_hr", "a_p_apply", "\u9000\u56de", ""),
        ("a_p_gm", "a_p_pub", "\u6279\u51c6", ""),
        ("a_p_pub", "a_p_end", "\u516c\u793a\u5b8c\u6210", ""),
    ],
)

# --- 8. 积分悬赏流程（官方「积分悬赏」）-----------------------------------
PROC_BOUNTY_ID = "p6006011-hr-bounty-00000000000000001"

PROC_BOUNTY = ProcessBuilder(
    PROC_BOUNTY_ID, "\u79ef\u5206\u60ac\u8d4f\u6d41\u7a0b",
    "\u79ef\u5206\u60ac\u8d4f\u8bfe\u9898\u53d1\u5e03\u4e0e\u9886\u53d6\u786e\u8ba4",
    form_id=FORM_BOUNTY_ID,
    activities=[
        Activity("a_b_pub", "\u60ac\u8d4f\u53d1\u5e03", "manual",
                 form_id=FORM_BOUNTY_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_b_take", "\u8bfe\u9898\u9886\u53d6", "manual",
                 form_id=FORM_BOUNTY_ID, task_script=SCRIPT_SELF),
        Activity("a_b_done", "\u63d0\u4ea4\u6210\u679c\u786e\u8ba4", "manual",
                 form_id=FORM_BOUNTY_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_b_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_b_pub", "a_b_take", "\u53d1\u5e03\u5b8c\u6210", ""),
        ("a_b_take", "a_b_done", "\u63d0\u4ea4\u6210\u679c", ""),
        ("a_b_done", "a_b_take", "\u9000\u56de\u4fee\u6539", ""),
        ("a_b_done", "a_b_end", "\u786e\u8ba4\u5b8c\u6210", ""),
    ],
)

# --- 9. 积分兑换流程（官方「积分兑换」按钮）-------------------------------
PROC_EXCHANGE_ID = "p6006012-hr-exchange-000000000000001"

PROC_EXCHANGE = ProcessBuilder(
    PROC_EXCHANGE_ID, "\u79ef\u5206\u5151\u6362\u6d41\u7a0b",
    "\u5458\u5de5\u79ef\u5206\u5151\u6362\u7533\u8bf7\u4e0e\u53d1\u653e",
    form_id=FORM_EXCHANGE_ID,
    activities=[
        Activity("a_x_apply", "\u5151\u6362\u7533\u8bf7", "manual",
                 form_id=FORM_EXCHANGE_ID, task_script=SCRIPT_SELF),
        Activity("a_x_hr", "\u4eba\u4e8b\u5ba1\u6838", "manual",
                 form_id=FORM_EXCHANGE_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_x_deliver", "\u7269\u54c1\u53d1\u653e", "manual",
                 form_id=FORM_EXCHANGE_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_x_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_x_apply", "a_x_hr", "\u63d0\u4ea4", ""),
        ("a_x_hr", "a_x_deliver", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_x_hr", "a_x_apply", "\u9000\u56de", ""),
        ("a_x_deliver", "a_x_end", "\u53d1\u653e\u5b8c\u6210", ""),
    ],
)

# --- 10. 请假申请流程（官方「员工自助 -> 我要请假」）-----------------------
PROC_LEAVE = ProcessBuilder(
    PROC_LEAVE_ID, "\u8bf7\u5047\u7533\u8bf7\u6d41\u7a0b",
    "\u5458\u5de5\u8bf7\u5047\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_LEAVE_ID,
    activities=[
        Activity("a_l_apply", "\u8bf7\u5047\u7533\u8bf7", "manual",
                 form_id=FORM_LEAVE_ID, task_script=SCRIPT_SELF),
        Activity("a_l_leader", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u5ba1\u6279", "manual",
                 form_id=FORM_LEAVE_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_l_hr", "\u4eba\u4e8b\u5907\u6848", "manual",
                 form_id=FORM_LEAVE_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_l_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_l_apply", "a_l_leader", "\u63d0\u4ea4", ""),
        ("a_l_leader", "a_l_hr", "\u540c\u610f", ""),
        ("a_l_leader", "a_l_apply", "\u9000\u56de", ""),
        ("a_l_hr", "a_l_end", "\u5907\u6848\u5b8c\u6210", ""),
    ],
)

# --- 11. 加班申请流程（官方「员工自助 -> 我要加班」）-----------------------
PROC_OVERTIME = ProcessBuilder(
    PROC_OVERTIME_ID, "\u52a0\u73ed\u7533\u8bf7\u6d41\u7a0b",
    "\u5458\u5de5\u52a0\u73ed\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_OVERTIME_ID,
    activities=[
        Activity("a_w_apply", "\u52a0\u73ed\u7533\u8bf7", "manual",
                 form_id=FORM_OVERTIME_ID, task_script=SCRIPT_SELF),
        Activity("a_w_leader", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u5ba1\u6279", "manual",
                 form_id=FORM_OVERTIME_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_w_hr", "\u4eba\u4e8b\u5907\u6848", "manual",
                 form_id=FORM_OVERTIME_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_w_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_w_apply", "a_w_leader", "\u63d0\u4ea4", ""),
        ("a_w_leader", "a_w_hr", "\u540c\u610f", ""),
        ("a_w_leader", "a_w_apply", "\u9000\u56de", ""),
        ("a_w_hr", "a_w_end", "\u5907\u6848\u5b8c\u6210", ""),
    ],
)

# --- 12. 出差申请流程（官方「员工自助 -> 我要出差」）-----------------------
PROC_TRAVEL = ProcessBuilder(
    PROC_TRAVEL_ID, "\u51fa\u5dee\u7533\u8bf7\u6d41\u7a0b",
    "\u5458\u5de5\u51fa\u5dee\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_TRAVEL_ID,
    activities=[
        Activity("a_v_apply", "\u51fa\u5dee\u7533\u8bf7", "manual",
                 form_id=FORM_TRAVEL_ID, task_script=SCRIPT_SELF),
        Activity("a_v_leader", "\u90e8\u95e8\u8d1f\u8d23\u4eba\u5ba1\u6279", "manual",
                 form_id=FORM_TRAVEL_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_v_fin", "\u8d22\u52a1\u5ba1\u6838", "manual",
                 form_id=FORM_TRAVEL_ID, task_script=SCRIPT_FINANCE),
        Activity("a_v_hr", "\u4eba\u4e8b\u5907\u6848", "manual",
                 form_id=FORM_TRAVEL_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_v_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_v_apply", "a_v_leader", "\u63d0\u4ea4", ""),
        ("a_v_leader", "a_v_fin", "\u540c\u610f", ""),
        ("a_v_leader", "a_v_apply", "\u9000\u56de", ""),
        ("a_v_fin", "a_v_hr", "\u6838\u7b97\u901a\u8fc7", ""),
        ("a_v_hr", "a_v_end", "\u5907\u6848\u5b8c\u6210", ""),
    ],
)

# --- 13. 考勤确认流程（官方「考勤管理 -> 我的考勤月报」）-------------------
PROC_ATTEND_ID = "p6006013-hr-attend-000000000000000001"

PROC_ATTEND = ProcessBuilder(
    PROC_ATTEND_ID, "\u8003\u52e4\u786e\u8ba4\u6d41\u7a0b",
    "\u5458\u5de5\u6708\u5ea6\u8003\u52e4\u786e\u8ba4\u4e0e\u5f02\u8bae\u5904\u7406",
    form_id=FORM_ATTEND_ID,
    activities=[
        Activity("a_tt_pub", "\u8003\u52e4\u53d1\u5e03", "manual",
                 form_id=FORM_ATTEND_ID, task_script=SCRIPT_ATTEND_ADMIN),
        Activity("a_tt_confirm", "\u5458\u5de5\u786e\u8ba4", "manual",
                 form_id=FORM_ATTEND_ID, task_script=SCRIPT_SELF),
        Activity("a_tt_hr", "\u5f02\u8bae\u5904\u7406", "manual",
                 form_id=FORM_ATTEND_ID, task_script=SCRIPT_ATTEND_ADMIN),
        Activity("a_tt_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_tt_pub", "a_tt_confirm", "\u53d1\u5e03\u5b8c\u6210", ""),
        ("a_tt_confirm", "a_tt_end", "\u786e\u8ba4\u65e0\u5f02\u8bae", ""),
        ("a_tt_confirm", "a_tt_hr", "\u63d0\u51fa\u5f02\u8bae", ""),
        ("a_tt_hr", "a_tt_end", "\u5904\u7406\u5b8c\u6210", ""),
    ],
)

# --- 14. 员工自助流程（官方「员工自助」统一入口）---------------------------
PROC_SELF_ID = "p6006014-hr-self-0000000000000000001"

PROC_SELF = ProcessBuilder(
    PROC_SELF_ID, "\u5458\u5de5\u81ea\u52a9\u7533\u8bf7\u6d41\u7a0b",
    "\u5458\u5de5\u81ea\u52a9\u7efc\u5408\u7533\u8bf7\uff08\u4e00\u7ad9\u5f0f\u5165\u53e3\uff09",
    form_id=FORM_SELF_ID,
    activities=[
        Activity("a_s_apply", "\u7533\u8bf7\u63d0\u4ea4", "manual",
                 form_id=FORM_SELF_ID, task_script=SCRIPT_SELF),
        Activity("a_s_dept", "\u90e8\u95e8\u5904\u7406", "manual",
                 form_id=FORM_SELF_ID, task_script=SCRIPT_DEPT_MGR),
        Activity("a_s_hr", "\u4eba\u4e8b\u5904\u7406", "manual",
                 form_id=FORM_SELF_ID, task_script=SCRIPT_HR_ADMIN),
        Activity("a_s_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_s_apply", "a_s_dept", "\u63d0\u4ea4", ""),
        ("a_s_dept", "a_s_hr", "\u5904\u7406\u5b8c\u6210", ""),
        ("a_s_dept", "a_s_apply", "\u9000\u56de", ""),
        ("a_s_hr", "a_s_end", "\u529e\u7ed3", ""),
    ],
)


# ==========================================================================
# 自建表（10 张）
# ==========================================================================

TABLE_EMP_ID = "t6006001-hr-employee-table-000000000001"
TABLE_EMP_DETAIL_ID = "t6006002-hr-emp-detail-table-0000000001"
TABLE_CHANGE_HR_ID = "t6006003-hr-change-table-0000000000001"
TABLE_JOB_ID = "t6006004-hr-job-table-0000000000000001"
TABLE_JOB_APPLY_ID = "t6006005-hr-job-apply-table-00000000001"
TABLE_POINT_ID = "t6006006-hr-point-table-0000000000001"
TABLE_BOUNTY_ID = "t6006007-hr-bounty-table-0000000000001"
TABLE_ATTEND_ID = "t6006008-hr-attend-table-0000000000001"
TABLE_LEAVE_ID = "t6006009-hr-leave-table-000000000000001"
TABLE_OVERTIME_ID = "t6006010-hr-overtime-table-00000000001"
TABLE_TRAVEL_ID = "t6006011-hr-travel-table-0000000000001"
TABLE_SELF_ID = "t6006012-hr-self-table-0000000000000001"

# --- 1. 员工主表（档案台账，employee_no 为全局人员标识）-------------------
TABLE_EMP = table(
    TABLE_EMP_ID, "\u5458\u5de5\u4e3b\u8868",
    [
        ("id", "string", "ID", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("gender", "string", "\u6027\u522b", 16),
        ("employee_status", "string", "\u5458\u5de5\u72b6\u6001", 32),
        ("work_nature", "string", "\u7528\u5de5\u6027\u8d28", 32),
        ("id_card", "string", "\u8eab\u4efd\u8bc1\u53f7", 32),
        ("birth_date", "date", "\u51fa\u751f\u65e5\u671f", 20),
        ("birth_place", "string", "\u51fa\u751f\u5730", 128),
        ("native_place", "string", "\u7c4d\u8d2f", 128),
        ("nation", "string", "\u6c11\u65cf", 32),
        ("political_status", "string", "\u653f\u6cbb\u9762\u8c8c", 32),
        ("marital_status", "string", "\u5a5a\u59fb\u72b6\u6001", 32),
        ("mobile", "string", "\u79fb\u52a8\u7535\u8bdd", 32),
        ("office_phone", "string", "\u529e\u516c\u7535\u8bdd", 32),
        ("email", "string", "\u7535\u5b50\u90ae\u4ef6", 128),
        ("wechat", "string", "\u5fae\u4fe1", 64),
        ("qq", "string", "QQ", 32),
        ("education", "string", "\u6700\u9ad8\u5b66\u5386", 32),
        ("degree", "string", "\u6700\u9ad8\u5b66\u4f4d", 32),
        ("graduate_school", "string", "\u6bd5\u4e1a\u9662\u6821", 128),
        ("major", "string", "\u6240\u5b66\u4e13\u4e1a", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("position", "string", "\u804c\u4f4d", 128),
        ("grade", "string", "\u804c\u7ea7", 64),
        ("join_date", "date", "\u53c2\u52a0\u672c\u5355\u4f4d\u65f6\u95f4", 20),
        ("regular_date", "date", "\u8f6c\u6b63\u65e5\u671f", 20),
        ("leave_date", "date", "\u79bb\u804c\u65e5\u671f", 20),
        ("year_point", "double", "\u5e74\u5ea6\u79ef\u5206", 2),
        ("total_point", "double", "\u6c38\u4e45\u79ef\u5206", 2),
        ("home_address", "string", "\u5bb6\u5ead\u4f4f\u5740", 255),
        ("emergency_contact", "string", "\u7d27\u6025\u8054\u7cfb\u4eba", 64),
        ("emergency_phone", "string", "\u7d27\u6025\u8054\u7cfb\u7535\u8bdd", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
        ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u6863\u6848\u53f0\u8d26\uff0cemployee_no \u4e3a\u5168\u5c40\u4eba\u5458\u6807\u8bc6\uff0c\u5411\u4e94\u5927\u5e94\u7528\u8f90\u5c04",
)

# --- 2. 员工履历明细表（五个 Datagrid 统一落库）---------------------------
TABLE_EMP_DETAIL = table(
    TABLE_EMP_DETAIL_ID, "\u5458\u5de5\u5c65\u5386\u660e\u7ec6\u8868",
    [
        ("id", "string", "ID", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("detail_type", "string", "\u5c65\u5386\u7c7b\u578b", 32),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("position", "string", "\u5c97\u4f4d", 128),
        ("company", "string", "\u516c\u53f8", 200),
        ("school", "string", "\u5b66\u6821\u540d\u79f0", 200),
        ("major", "string", "\u4e13\u4e1a", 128),
        ("education", "string", "\u5b66\u5386", 32),
        ("degree", "string", "\u5b66\u4f4d", 32),
        ("tech_name", "string", "\u4e13\u4e1a\u6280\u672f\u8d44\u683c\u540d\u79f0", 200),
        ("award_name", "string", "\u83b7\u5956\u540d\u79f0", 200),
        ("award_org", "string", "\u9881\u53d1\u5355\u4f4d", 200),
        ("start_date", "date", "\u5f00\u59cb\u65e5\u671f", 20),
        ("end_date", "date", "\u7ed3\u675f\u65e5\u671f", 20),
        ("work_desc", "text", "\u63cf\u8ff0", 2000),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u672c\u5355\u4f4d\u5de5\u4f5c\u7ecf\u5386/\u5de5\u4f5c\u7ecf\u5386/\u6559\u80b2\u80cc\u666f/\u4e13\u4e1a\u6280\u672f\u8d44\u683c/\u5956\u52b1\u60c5\u51b5\u4e94\u7c7b\u660e\u7ec6\u7edf\u4e00\u5b58\u50a8",
)

# --- 3. 人事变动记录表（入职/转岗/转正/离职统一台账）---------------------
TABLE_CHANGE_HR = table(
    TABLE_CHANGE_HR_ID, "\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("change_no", "string", "\u53d8\u52a8\u5355\u53f7", 64),
        ("change_type", "string", "\u53d8\u52a8\u7c7b\u578b", 32),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("gender", "string", "\u6027\u522b", 16),
        ("old_dept", "string", "\u539f\u90e8\u95e8", 128),
        ("old_position", "string", "\u539f\u5c97\u4f4d", 128),
        ("new_dept", "string", "\u65b0\u90e8\u95e8", 128),
        ("new_position", "string", "\u65b0\u5c97\u4f4d", 128),
        ("old_grade", "string", "\u539f\u804c\u7ea7", 64),
        ("new_grade", "string", "\u65b0\u804c\u7ea7", 64),
        ("old_status", "string", "\u539f\u5458\u5de5\u72b6\u6001", 32),
        ("new_status", "string", "\u65b0\u5458\u5de5\u72b6\u6001", 32),
        ("work_nature", "string", "\u7528\u5de5\u6027\u8d28", 32),
        ("effect_date", "date", "\u751f\u6548\u65e5\u671f", 20),
        ("apply_date", "date", "\u7533\u8bf7\u65e5\u671f", 20),
        ("change_reason", "text", "\u53d8\u52a8\u539f\u56e0", 2000),
        ("approve_status", "string", "\u5ba1\u6279\u72b6\u6001", 32),
        ("publish_flag", "string", "\u662f\u5426\u516c\u793a", 8),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5165\u804c/\u8f6c\u5c97/\u8f6c\u6b63/\u79bb\u804c\u56db\u7c7b\u4eba\u4e8b\u53d8\u52a8\u7edf\u4e00\u53f0\u8d26\uff0c\u652f\u6491\u5b98\u65b9\u56db\u5bab\u683c\u516c\u793a",
)

# --- 4. 岗位池表（官方「人才市场 -> 岗位池」）-----------------------------
TABLE_JOB = table(
    TABLE_JOB_ID, "\u5c97\u4f4d\u6c60\u8868",
    [
        ("id", "string", "ID", 64),
        ("job_no", "string", "\u5c97\u4f4d\u7f16\u53f7", 64),
        ("job_name", "string", "\u5c97\u4f4d\u540d\u79f0", 200),
        ("recruit_dept", "string", "\u62db\u8058\u90e8\u95e8", 128),
        ("recruit_count", "integer", "\u62db\u8058\u4eba\u6570", 11),
        ("standard_grade", "string", "\u6807\u51c6\u804c\u7ea7", 64),
        ("bid_type", "string", "\u7ade\u8058\u7c7b\u578b", 32),
        ("job_type", "string", "\u5c97\u4f4d\u7c7b\u578b", 32),
        ("job_category", "string", "\u5c97\u4f4d\u5e8f\u5217", 64),
        ("publish_date", "date", "\u53d1\u5e03\u65f6\u95f4", 20),
        ("deadline", "date", "\u622a\u6b62\u65f6\u95f4", 20),
        ("interview_date", "date", "\u9762\u8bd5\u65f6\u95f4", 20),
        ("job_status", "string", "\u72b6\u6001", 32),
        ("work_place", "string", "\u5de5\u4f5c\u5730\u70b9", 128),
        ("salary_range", "string", "\u85aa\u916c\u8303\u56f4", 64),
        ("education_req", "string", "\u5b66\u5386\u8981\u6c42", 32),
        ("experience_req", "string", "\u7ecf\u9a8c\u8981\u6c42", 128),
        ("job_duty", "text", "\u5c97\u4f4d\u804c\u8d23", 2000),
        ("job_require", "text", "\u4efb\u804c\u8981\u6c42", 2000),
        ("apply_count", "integer", "\u62a5\u540d\u4eba\u6570", 11),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
        ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 20),
    ],
    description="\u5185\u90e8\u7ade\u8058\u5c97\u4f4d\u6c60\uff0c\u4f9b\u201c\u5c97\u4f4d\u6c60/\u8d44\u6e90\u6c60/\u5f85\u5c97\u6c60\u201d\u89c6\u56fe\u5c55\u793a",
)

# --- 5. 岗位报名表（官方「人才市场 -> 我的报名表」）-----------------------
TABLE_JOB_APPLY = table(
    TABLE_JOB_APPLY_ID, "\u5c97\u4f4d\u62a5\u540d\u8868",
    [
        ("id", "string", "ID", 64),
        ("apply_no", "string", "\u62a5\u540d\u5355\u53f7", 64),
        ("job_no", "string", "\u5c97\u4f4d\u7f16\u53f7", 64),
        ("job_name", "string", "\u5c97\u4f4d\u540d\u79f0", 200),
        ("recruit_dept", "string", "\u62db\u8058\u90e8\u95e8", 128),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u73b0\u6240\u5c5e\u90e8\u95e8", 128),
        ("position", "string", "\u73b0\u4efb\u5c97\u4f4d", 128),
        ("grade", "string", "\u73b0\u804c\u7ea7", 64),
        ("join_date", "date", "\u5165\u804c\u65e5\u671f", 20),
        ("apply_date", "date", "\u62a5\u540d\u65f6\u95f4", 20),
        ("apply_reason", "text", "\u62a5\u540d\u7406\u7531", 2000),
        ("self_advantage", "text", "\u81ea\u6211\u4f18\u52bf", 2000),
        ("career_plan", "text", "\u804c\u4e1a\u89c4\u5212", 2000),
        ("is_summary", "string", "\u662f\u5426\u6c47\u603b", 8),
        ("apply_status", "string", "\u72b6\u6001", 32),
        ("interview_score", "double", "\u7ade\u8058\u5f97\u5206", 2),
        ("apply_result", "string", "\u7ade\u8058\u7ed3\u679c", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u7ade\u8058\u62a5\u540d\u8bb0\u5f55\uff0cjob_no \u5173\u8054\u5c97\u4f4d\u6c60\u8868",
)

# --- 6. 员工积分表（官方「积分管理」）-------------------------------------
TABLE_POINT = table(
    TABLE_POINT_ID, "\u5458\u5de5\u79ef\u5206\u8868",
    [
        ("id", "string", "ID", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("position", "string", "\u5c97\u4f4d", 128),
        ("point_year", "string", "\u5e74\u5ea6", 16),
        ("point_type", "string", "\u79ef\u5206\u7c7b\u578b", 32),
        ("year_point", "double", "\u5e74\u5ea6\u79ef\u5206", 2),
        ("total_point", "double", "\u6c38\u4e45\u79ef\u5206", 2),
        ("point_source", "string", "\u79ef\u5206\u6765\u6e90", 128),
        ("relate_biz", "string", "\u5173\u8054\u4e1a\u52a1", 128),
        ("grant_date", "date", "\u6388\u4e88\u65e5\u671f", 20),
        ("honor_level", "string", "\u8363\u8a89\u7b49\u7ea7", 32),
        ("rank_no", "integer", "\u6392\u540d", 11),
        ("grant_reason", "text", "\u6388\u4e88\u539f\u56e0", 2000),
        ("point_status", "string", "\u72b6\u6001", 32),
        ("dept_avg_point", "double", "\u90e8\u95e8\u4eba\u5747\u79ef\u5206", 2),
        ("dept_rank", "integer", "\u90e8\u95e8\u6708\u5ea6\u6392\u540d", 11),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
        ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u79ef\u5206\u53f0\u8d26\uff0c\u652f\u6491\u5e74\u5ea6/\u6c38\u4e45\u79ef\u5206\u3001\u4e2a\u4eba\u6392\u540d\u3001\u90e8\u95e8\u4eba\u5747\u6392\u540d",
)

# --- 7. 积分悬赏表（官方「积分悬赏」）-------------------------------------
TABLE_BOUNTY = table(
    TABLE_BOUNTY_ID, "\u79ef\u5206\u60ac\u8d4f\u8868",
    [
        ("id", "string", "ID", 64),
        ("bounty_no", "string", "\u60ac\u8d4f\u7f16\u53f7", 64),
        ("bounty_title", "string", "\u8bfe\u9898\u540d\u79f0", 255),
        ("bounty_score", "double", "\u60ac\u8d4f\u5206\u6570", 2),
        ("score_tag", "string", "\u5206\u6570\u6807\u7b7e", 32),
        ("bounty_type", "string", "\u8bfe\u9898\u7c7b\u578b", 32),
        ("publish_dept", "string", "\u53d1\u5e03\u90e8\u95e8", 128),
        ("publisher", "string", "\u53d1\u5e03\u4eba", 64),
        ("publish_date", "date", "\u53d1\u5e03\u65e5\u671f", 20),
        ("deadline", "date", "\u622a\u6b62\u65e5\u671f", 20),
        ("bounty_status", "string", "\u72b6\u6001", 32),
        ("bounty_desc", "text", "\u8bfe\u9898\u8bf4\u660e", 2000),
        ("bounty_require", "text", "\u4ea4\u4ed8\u8981\u6c42", 2000),
        ("taker_no", "string", "\u9886\u53d6\u4eba\u7f16\u53f7", 64),
        ("finish_date", "date", "\u5b8c\u6210\u65e5\u671f", 20),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u79ef\u5206\u60ac\u8d4f\u8bfe\u9898\u53f0\u8d26\uff0c\u5bf9\u5e94\u5b98\u65b9\u201c\u79ef\u5206\u60ac\u8d4f\uff1a\u5206\u6570\u6807\u7b7e|\u8bfe\u9898|\u65e5\u671f\u201d",
)

# --- 8. 考勤记录表（官方「考勤管理」）-------------------------------------
TABLE_ATTEND = table(
    TABLE_ATTEND_ID, "\u8003\u52e4\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("attend_no", "string", "\u8003\u52e4\u5355\u53f7", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("attend_period", "string", "\u8003\u52e4\u5468\u671f", 32),
        ("period_start", "date", "\u5468\u671f\u5f00\u59cb", 20),
        ("period_end", "date", "\u5468\u671f\u7ed3\u675f", 20),
        ("attend_date", "date", "\u65e5\u671f", 20),
        ("week_day", "string", "\u661f\u671f", 16),
        ("on_time", "string", "\u4e0a\u73ed\u65f6\u95f4", 20),
        ("off_time", "string", "\u4e0b\u73ed\u65f6\u95f4", 20),
        ("attend_type", "string", "\u8003\u52e4\u7c7b\u578b", 32),
        ("attend_result", "string", "\u7ed3\u679c", 32),
        ("should_days", "double", "\u5e94\u51fa\u52e4\u5929\u6570", 2),
        ("actual_days", "double", "\u5b9e\u51fa\u52e4\u5929\u6570", 2),
        ("late_count", "integer", "\u8fdf\u5230\u6b21\u6570", 11),
        ("early_count", "integer", "\u65e9\u9000\u6b21\u6570", 11),
        ("absent_count", "integer", "\u65f7\u5de5\u6b21\u6570", 11),
        ("leave_days", "double", "\u8bf7\u5047\u5929\u6570", 2),
        ("overtime_hours", "double", "\u52a0\u73ed\u65f6\u957f", 2),
        ("travel_days", "double", "\u51fa\u5dee\u5929\u6570", 2),
        ("attend_status", "string", "\u72b6\u6001", 32),
        ("emp_confirm", "string", "\u5458\u5de5\u786e\u8ba4", 16),
        ("remark", "text", "\u5f02\u8bae\u8bf4\u660e", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u65e5\u8003\u52e4\u4e0e\u6708\u6c47\u603b\u53f0\u8d26\uff0c\u652f\u6491\u201c\u672c\u6708\u8003\u52e4\u201d\u5c0f\u6708\u5386",
)

# --- 9. 请假记录表（官方「员工自助 -> 我要请假」）-------------------------
TABLE_LEAVE = table(
    TABLE_LEAVE_ID, "\u8bf7\u5047\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("leave_no", "string", "\u8bf7\u5047\u5355\u53f7", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("leave_type", "string", "\u5047\u671f\u7c7b\u578b", 32),
        ("start_time", "datetime", "\u5f00\u59cb\u65f6\u95f4", 20),
        ("end_time", "datetime", "\u7ed3\u675f\u65f6\u95f4", 20),
        ("leave_days", "double", "\u8bf7\u5047\u5929\u6570", 2),
        ("leave_reason", "text", "\u8bf7\u5047\u4e8b\u7531", 2000),
        ("handover_person", "string", "\u5de5\u4f5c\u4ea4\u4ee3\u4eba", 64),
        ("leave_status", "string", "\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u8bf7\u5047\u8bb0\u5f55\uff0c\u6c47\u5165\u8003\u52e4\u7edf\u8ba1",
)

# --- 10. 加班记录表（官方「员工自助 -> 我要加班」）------------------------
TABLE_OVERTIME = table(
    TABLE_OVERTIME_ID, "\u52a0\u73ed\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("overtime_no", "string", "\u52a0\u73ed\u5355\u53f7", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("overtime_type", "string", "\u52a0\u73ed\u7c7b\u578b", 32),
        ("start_time", "datetime", "\u5f00\u59cb\u65f6\u95f4", 20),
        ("end_time", "datetime", "\u7ed3\u675f\u65f6\u95f4", 20),
        ("overtime_hours", "double", "\u52a0\u73ed\u65f6\u957f", 2),
        ("overtime_reason", "text", "\u52a0\u73ed\u4e8b\u7531", 2000),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("compensate_type", "string", "\u8865\u507f\u65b9\u5f0f", 32),
        ("overtime_status", "string", "\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u52a0\u73ed\u8bb0\u5f55\uff0c\u901a\u8fc7 project_no \u5173\u8054\u9879\u76ee\u7ba1\u7406\u5e94\u7528",
)

# --- 11. 出差记录表（官方「员工自助 -> 我要出差」）------------------------
TABLE_TRAVEL = table(
    TABLE_TRAVEL_ID, "\u51fa\u5dee\u8bb0\u5f55\u8868",
    [
        ("id", "string", "ID", 64),
        ("travel_no", "string", "\u51fa\u5dee\u5355\u53f7", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("travel_type", "string", "\u51fa\u5dee\u7c7b\u578b", 32),
        ("destination", "string", "\u51fa\u5dee\u5730\u70b9", 128),
        ("start_date", "date", "\u51fa\u53d1\u65e5\u671f", 20),
        ("end_date", "date", "\u8fd4\u56de\u65e5\u671f", 20),
        ("travel_days", "double", "\u51fa\u5dee\u5929\u6570", 2),
        ("budget_amount", "double", "\u9884\u4f30\u8d39\u7528", 2),
        ("actual_amount", "double", "\u5b9e\u9645\u8d39\u7528", 2),
        ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
        ("travel_reason", "text", "\u51fa\u5dee\u4e8b\u7531", 2000),
        ("travel_status", "string", "\u72b6\u6001", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u51fa\u5dee\u8bb0\u5f55\uff0cproject_no \u4e0e\u9879\u76ee\u7ba1\u7406/\u9884\u7b97\u5e94\u7528\u8054\u52a8",
)

# --- 12. 员工自助申请表（官方「员工自助」统一入口）------------------------
TABLE_SELF = table(
    TABLE_SELF_ID, "\u5458\u5de5\u81ea\u52a9\u7533\u8bf7\u8868",
    [
        ("id", "string", "ID", 64),
        ("self_no", "string", "\u7533\u8bf7\u5355\u53f7", 64),
        ("employee_no", "string", "\u5458\u5de5\u7f16\u53f7", 64),
        ("employee_name", "string", "\u59d3\u540d", 128),
        ("dept", "string", "\u90e8\u95e8", 128),
        ("self_type", "string", "\u7533\u8bf7\u7c7b\u578b", 32),
        ("apply_title", "string", "\u7533\u8bf7\u6807\u9898", 255),
        ("start_time", "datetime", "\u5f00\u59cb\u65f6\u95f4", 20),
        ("end_time", "datetime", "\u7ed3\u675f\u65f6\u95f4", 20),
        ("current_step", "string", "\u5f53\u524d\u6b65\u9aa4", 128),
        ("self_status", "string", "\u72b6\u6001", 32),
        ("apply_content", "text", "\u7533\u8bf7\u5185\u5bb9", 2000),
        ("contact_phone", "string", "\u8054\u7cfb\u7535\u8bdd", 32),
        ("remark", "text", "\u5907\u6ce8", 2000),
        ("process_id", "string", "\u6d41\u7a0b\u5b9e\u4f8bID", 64),
        ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 20),
        ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 20),
    ],
    description="\u5458\u5de5\u81ea\u52a9\u7efc\u5408\u7533\u8bf7\u53f0\u8d26\uff0c\u652f\u6491\u5b98\u65b9\u201c\u6d41\u7a0b\u7c7b\u578b|\u6807\u9898|\u53d1\u8d77\u4eba|\u5f00\u59cb\u65f6\u95f4|\u5f53\u524d\u6b65\u9aa4\u201d\u5217\u8868",
)

TABLES = [
    TABLE_EMP, TABLE_EMP_DETAIL, TABLE_CHANGE_HR, TABLE_JOB, TABLE_JOB_APPLY,
    TABLE_POINT, TABLE_BOUNTY, TABLE_ATTEND, TABLE_LEAVE, TABLE_OVERTIME,
    TABLE_TRAVEL, TABLE_SELF,
]


# ==========================================================================
# 视图（13 个）
# --------------------------------------------------------------------------
# 严格对齐官方列表页实测规范（截图 1652073737833）：
#   顶部      工具栏按钮组
#   工具栏下  搜索栏：输入关键字搜索视图 + [高级搜索]
#   中部      表格（列顺序 = 官方表格列顺序）
#   底部      分页：第一页 ◀ ●1 ▶ 最后一页 1/1
# ==========================================================================

VIEW_EMP_ALL_ID = "v6006001-hr-employee-all-view-0000000001"
VIEW_EMP_FORMAL_ID = "v6006002-hr-employee-formal-view-000000001"
VIEW_EMP_PROBATION_ID = "v6006003-hr-employee-prob-view-0000000001"
VIEW_EMP_INTERN_ID = "v6006004-hr-employee-intern-view-00000001"
VIEW_EMP_LEAVE_ID = "v6006005-hr-employee-leave-view-000000001"
VIEW_CHANGE_ID = "v6006006-hr-change-view-0000000000000001"
VIEW_JOB_POOL_ID = "v6006007-hr-job-pool-view-000000000000001"
VIEW_JOB_APPLY_ID = "v6006008-hr-job-apply-view-0000000000001"
VIEW_POINT_ID = "v6006009-hr-point-view-00000000000000001"
VIEW_POINT_RANK_ID = "v6006010-hr-point-rank-view-000000000001"
VIEW_ATTEND_ID = "v6006011-hr-attend-view-0000000000000001"
VIEW_SELF_ID = "v6006012-hr-self-view-00000000000000001"
VIEW_LEAVE_REC_ID = "v6006013-hr-leave-record-view-0000000001"


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


# --- 员工档案主表工具栏（对齐官方「员工档案」页）--------------------------
EMP_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("new", "\u65b0\u5efa\u6863\u6848", "process", PROC_EMP_ONBOARD_ID),
    ("import", "\u5bfc\u5165\u6863\u6848", "toolbar", ""),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
    ("transfer", "\u53d1\u8d77\u8f6c\u5c97", "process", PROC_EMP_TRANSFER_ID),
    ("regular", "\u53d1\u8d77\u8f6c\u6b63", "process", PROC_EMP_REGULAR_ID),
    ("resign", "\u53d1\u8d77\u79bb\u804c", "process", PROC_EMP_LEAVE_ID),
]

CHANGE_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
    ("publish", "\u516c\u793a", "toolbar", ""),
]

JOB_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("publish", "\u53d1\u5e03\u5c97\u4f4d", "process", PROC_JOB_PUBLISH_ID),
    ("apply", "\u7ade\u8058\u62a5\u540d", "process", PROC_JOB_APPLY_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
]

POINT_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("grant", "\u79ef\u5206\u5f55\u5165", "process", PROC_POINT_GRANT_ID),
    ("exchange", "\u79ef\u5206\u5151\u6362", "process", PROC_EXCHANGE_ID),
    ("bounty", "\u79ef\u5206\u60ac\u8d4f", "process", PROC_BOUNTY_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
]

ATTEND_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("import", "\u6570\u636e\u5bfc\u5165", "toolbar", ""),
    ("confirm", "\u53d1\u8d77\u786e\u8ba4", "process", PROC_ATTEND_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
]

SELF_TOOLBAR = [
    ("exportExcel", "\u5bfc\u51faExcel", "toolbar", ""),
    ("leave", "\u6211\u8981\u8bf7\u5047", "process", PROC_LEAVE_ID),
    ("overtime", "\u6211\u8981\u52a0\u73ed", "process", PROC_OVERTIME_ID),
    ("travel", "\u6211\u8981\u51fa\u5dee", "process", PROC_TRAVEL_ID),
    ("self", "\u7efc\u5408\u7533\u8bf7", "process", PROC_SELF_ID),
    ("edit", "\u7f16\u8f91", "edit", ""),
    ("delete", "\u5220\u9664", "delete", ""),
]

# --- 1. 全部档案（官方「档案查询 -> 全部档案」）---------------------------
VIEW_EMP_ALL = _apply_toolbar(view(
    VIEW_EMP_ALL_ID, "\u5168\u90e8\u6863\u6848",
    description="\u5458\u5de5\u6863\u6848\u5168\u91cf\u5217\u8868\uff0c\u652f\u6301\u5173\u952e\u5b57\u4e0e\u9ad8\u7ea7\u641c\u7d22",
    source="table", table_list=[TABLE_EMP_ID],
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u6027\u522b", "gender", "70px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u804c\u4f4d", "position", "140px"),
        ("\u5458\u5de5\u72b6\u6001", "employee_status", "110px"),
        ("\u7528\u5de5\u6027\u8d28", "work_nature", "100px"),
        ("\u6700\u9ad8\u5b66\u5386", "education", "100px"),
        ("\u53c2\u52a0\u672c\u5355\u4f4d\u65f6\u95f4", "join_date", "130px"),
        ("\u79fb\u52a8\u7535\u8bdd", "mobile", "120px"),
    ],
), EMP_TOOLBAR)
VIEW_EMP_ALL["properties"] = _list_props(20)

# --- 2~5. 按员工状态分组的四个档案视图（官方档案查询子项）-----------------
VIEW_EMP_FORMAL = _apply_toolbar(view(
    VIEW_EMP_FORMAL_ID, "\u6b63\u5f0f\u5458\u5de5",
    description="\u5458\u5de5\u72b6\u6001 = \u6b63\u5f0f\u5458\u5de5",
    source="table", table_list=[TABLE_EMP_ID],
    filter_script="return this.data.employee_status == '%s';" % EMP_STATUS_FORMAL,
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u804c\u4f4d", "position", "140px"),
        ("\u804c\u7ea7", "grade", "90px"),
        ("\u8f6c\u6b63\u65e5\u671f", "regular_date", "120px"),
        ("\u79fb\u52a8\u7535\u8bdd", "mobile", "120px"),
    ],
), EMP_TOOLBAR)
VIEW_EMP_FORMAL["properties"] = _list_props(20)

VIEW_EMP_PROBATION = _apply_toolbar(view(
    VIEW_EMP_PROBATION_ID, "\u8bd5\u7528\u671f\u5458\u5de5",
    description="\u5458\u5de5\u72b6\u6001 = \u8bd5\u7528\u671f\u5458\u5de5",
    source="table", table_list=[TABLE_EMP_ID],
    filter_script="return this.data.employee_status == '%s';" % EMP_STATUS_PROBATION,
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u804c\u4f4d", "position", "140px"),
        ("\u5165\u804c\u65e5\u671f", "join_date", "120px"),
        ("\u8bd5\u7528\u5230\u671f\u65e5", "leave_date", "120px"),
    ],
), EMP_TOOLBAR)
VIEW_EMP_PROBATION["properties"] = _list_props(20)

VIEW_EMP_INTERN = _apply_toolbar(view(
    VIEW_EMP_INTERN_ID, "\u5b9e\u4e60\u671f\u5458\u5de5",
    description="\u5458\u5de5\u72b6\u6001 = \u5b9e\u4e60\u671f\u5458\u5de5",
    source="table", table_list=[TABLE_EMP_ID],
    filter_script="return this.data.employee_status == '%s';" % EMP_STATUS_INTERN,
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u5c97\u4f4d", "position", "140px"),
        ("\u6bd5\u4e1a\u9662\u6821", "graduate_school", "180px"),
        ("\u5165\u804c\u65e5\u671f", "join_date", "120px"),
    ],
), EMP_TOOLBAR)
VIEW_EMP_INTERN["properties"] = _list_props(20)

VIEW_EMP_LEAVE = _apply_toolbar(view(
    VIEW_EMP_LEAVE_ID, "\u79bb\u804c\u5458\u5de5",
    description="\u5458\u5de5\u72b6\u6001 = \u79bb\u804c\u5458\u5de5",
    source="table", table_list=[TABLE_EMP_ID],
    filter_script="return this.data.employee_status == '%s';" % EMP_STATUS_LEAVE,
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u539f\u90e8\u95e8", "dept", "140px"),
        ("\u539f\u5c97\u4f4d", "position", "140px"),
        ("\u5165\u804c\u65e5\u671f", "join_date", "120px"),
        ("\u79bb\u804c\u65e5\u671f", "leave_date", "120px"),
    ],
), EMP_TOOLBAR)
VIEW_EMP_LEAVE["properties"] = _list_props(20)

# --- 6. 人事变动记录（官方四宫格公示的数据源）-----------------------------
VIEW_CHANGE = _apply_toolbar(view(
    VIEW_CHANGE_ID, "\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55",
    description="\u5165\u804c/\u8f6c\u5c97/\u8f6c\u6b63/\u79bb\u804c\u56db\u7c7b\u53d8\u52a8\u7edf\u4e00\u5217\u8868",
    source="table", table_list=[TABLE_CHANGE_HR_ID],
    columns=[
        ("\u53d8\u52a8\u7c7b\u578b", "change_type", "110px"),
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u539f\u90e8\u95e8", "old_dept", "130px"),
        ("\u65b0\u90e8\u95e8", "new_dept", "130px"),
        ("\u539f\u5c97\u4f4d", "old_position", "130px"),
        ("\u65b0\u5c97\u4f4d", "new_position", "130px"),
        ("\u751f\u6548\u65e5\u671f", "effect_date", "120px"),
        ("\u5ba1\u6279\u72b6\u6001", "approve_status", "100px"),
    ],
), CHANGE_TOOLBAR)
VIEW_CHANGE["properties"] = _list_props(20)

# --- 7. 岗位池（官方「人才市场 -> 岗位池」表格列顺序）---------------------
VIEW_JOB_POOL = _apply_toolbar(view(
    VIEW_JOB_POOL_ID, "\u5c97\u4f4d\u6c60",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u5c97\u4f4d|\u62db\u8058\u90e8\u95e8|\u62db\u8058\u4eba\u6570|\u6807\u51c6\u804c\u7ea7|\u7ade\u8058\u7c7b\u578b|\u53d1\u5e03\u65f6\u95f4|\u72b6\u6001",
    source="table", table_list=[TABLE_JOB_ID],
    columns=[
        ("\u5c97\u4f4d", "job_name", "180px"),
        ("\u62db\u8058\u90e8\u95e8", "recruit_dept", "140px"),
        ("\u62db\u8058\u4eba\u6570", "recruit_count", "100px"),
        ("\u6807\u51c6\u804c\u7ea7", "standard_grade", "110px"),
        ("\u7ade\u8058\u7c7b\u578b", "bid_type", "110px"),
        ("\u53d1\u5e03\u65f6\u95f4", "publish_date", "120px"),
        ("\u72b6\u6001", "job_status", "100px"),
    ],
), JOB_TOOLBAR)
VIEW_JOB_POOL["properties"] = _list_props(20)

# --- 8. 我的报名表（官方「我的报名表」列：岗位 | 状态 | 是否汇总）---------
VIEW_JOB_APPLY = _apply_toolbar(view(
    VIEW_JOB_APPLY_ID, "\u6211\u7684\u62a5\u540d\u8868",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u5c97\u4f4d|\u72b6\u6001|\u662f\u5426\u6c47\u603b",
    source="table", table_list=[TABLE_JOB_APPLY_ID],
    columns=[
        ("\u5c97\u4f4d", "job_name", "200px"),
        ("\u62a5\u540d\u5355\u53f7", "apply_no", "130px"),
        ("\u72b6\u6001", "apply_status", "110px"),
        ("\u662f\u5426\u6c47\u603b", "is_summary", "100px"),
        ("\u62a5\u540d\u65f6\u95f4", "apply_date", "120px"),
        ("\u7ade\u8058\u5f97\u5206", "interview_score", "110px"),
        ("\u7ade\u8058\u7ed3\u679c", "apply_result", "110px"),
    ],
), JOB_TOOLBAR)
VIEW_JOB_APPLY["properties"] = _list_props(20)

# --- 9. 我的积分（官方「积分管理 -> 我的积分」）---------------------------
VIEW_POINT = _apply_toolbar(view(
    VIEW_POINT_ID, "\u6211\u7684\u79ef\u5206",
    description="\u5e74\u5ea6\u79ef\u5206 / \u6c38\u4e45\u79ef\u5206\u53f0\u8d26",
    source="table", table_list=[TABLE_POINT_ID],
    columns=[
        ("\u5458\u5de5\u7f16\u53f7", "employee_no", "120px"),
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u5e74\u5ea6", "point_year", "80px"),
        ("\u79ef\u5206\u7c7b\u578b", "point_type", "110px"),
        ("\u5e74\u5ea6\u79ef\u5206", "year_point", "100px"),
        ("\u6c38\u4e45\u79ef\u5206", "total_point", "100px"),
        ("\u8363\u8a89\u7b49\u7ea7", "honor_level", "100px"),
        ("\u6388\u4e88\u65e5\u671f", "grant_date", "120px"),
    ],
), POINT_TOOLBAR)
VIEW_POINT["properties"] = _list_props(20)

# --- 10. 个人年度排名（官方「个人年度排名」，姓名|积分|排名）---------------
VIEW_POINT_RANK = _apply_toolbar(view(
    VIEW_POINT_RANK_ID, "\u4e2a\u4eba\u5e74\u5ea6\u6392\u540d",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u59d3\u540d|\u79ef\u5206|\u6392\u540d",
    source="table", table_list=[TABLE_POINT_ID],
    columns=[
        ("\u59d3\u540d", "employee_name", "120px"),
        ("\u79ef\u5206", "total_point", "100px"),
        ("\u6392\u540d", "rank_no", "90px"),
        ("\u90e8\u95e8", "dept", "140px"),
        ("\u90e8\u95e8\u4eba\u5747\u79ef\u5206", "dept_avg_point", "130px"),
        ("\u90e8\u95e8\u6708\u5ea6\u6392\u540d", "dept_rank", "130px"),
    ],
), POINT_TOOLBAR)
VIEW_POINT_RANK["properties"] = _list_props(20)

# --- 11. 本月考勤（官方「本月考勤」小月历 + 考勤统计）---------------------
VIEW_ATTEND = _apply_toolbar(view(
    VIEW_ATTEND_ID, "\u672c\u6708\u8003\u52e4",
    description="\u5458\u5de5\u65e5\u8003\u52e4\u660e\u7ec6\uff0c\u652f\u6491\u6708\u5386\u5c55\u793a",
    source="table", table_list=[TABLE_ATTEND_ID],
    columns=[
        ("\u65e5\u671f", "attend_date", "110px"),
        ("\u661f\u671f", "week_day", "70px"),
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u90e8\u95e8", "dept", "130px"),
        ("\u4e0a\u73ed\u65f6\u95f4", "on_time", "100px"),
        ("\u4e0b\u73ed\u65f6\u95f4", "off_time", "100px"),
        ("\u8003\u52e4\u7c7b\u578b", "attend_type", "110px"),
        ("\u7ed3\u679c", "attend_result", "90px"),
    ],
), ATTEND_TOOLBAR)
VIEW_ATTEND["properties"] = _list_props(31)

# --- 12. 员工自助（官方列表页五列）---------------------------------------
VIEW_SELF = _apply_toolbar(view(
    VIEW_SELF_ID, "\u5458\u5de5\u81ea\u52a9",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u6d41\u7a0b\u7c7b\u578b|\u6807\u9898|\u53d1\u8d77\u4eba|\u5f00\u59cb\u65f6\u95f4|\u5f53\u524d\u6b65\u9aa4",
    source="table", table_list=[TABLE_SELF_ID],
    columns=[
        ("\u6d41\u7a0b\u7c7b\u578b", "self_type", "130px"),
        ("\u6807\u9898", "apply_title", "280px"),
        ("\u53d1\u8d77\u4eba", "employee_name", "110px"),
        ("\u5f00\u59cb\u65f6\u95f4", "start_time", "150px"),
        ("\u5f53\u524d\u6b65\u9aa4", "current_step", "160px"),
        ("\u72b6\u6001", "self_status", "100px"),
    ],
), SELF_TOOLBAR)
VIEW_SELF["properties"] = _list_props(20)

# --- 13. 请假记录（官方「员工休假记录」）----------------------------------
VIEW_LEAVE_REC = _apply_toolbar(view(
    VIEW_LEAVE_REC_ID, "\u5458\u5de5\u4f11\u5047\u8bb0\u5f55",
    description="\u5458\u5de5\u8bf7\u5047\u8bb0\u5f55\u660e\u7ec6\uff0c\u6c47\u5165\u8003\u52e4\u7edf\u8ba1",
    source="table", table_list=[TABLE_LEAVE_ID],
    columns=[
        ("\u59d3\u540d", "employee_name", "100px"),
        ("\u90e8\u95e8", "dept", "130px"),
        ("\u5047\u671f\u7c7b\u578b", "leave_type", "110px"),
        ("\u5f00\u59cb\u65f6\u95f4", "start_time", "150px"),
        ("\u7ed3\u675f\u65f6\u95f4", "end_time", "150px"),
        ("\u8bf7\u5047\u5929\u6570", "leave_days", "100px"),
        ("\u5de5\u4f5c\u4ea4\u4ee3\u4eba", "handover_person", "110px"),
        ("\u72b6\u6001", "leave_status", "100px"),
    ],
), ATTEND_TOOLBAR)
VIEW_LEAVE_REC["properties"] = _list_props(20)

VIEWS = [
    VIEW_EMP_ALL, VIEW_EMP_FORMAL, VIEW_EMP_PROBATION, VIEW_EMP_INTERN,
    VIEW_EMP_LEAVE, VIEW_CHANGE, VIEW_JOB_POOL, VIEW_JOB_APPLY,
    VIEW_POINT, VIEW_POINT_RANK, VIEW_ATTEND, VIEW_SELF, VIEW_LEAVE_REC,
]


# ==========================================================================
# 统计（10 个）
# --------------------------------------------------------------------------
# 对齐官方门户图表需求：
#   HR 首页   —— 按部门统计员工人数 / 按员工状态统计人数
#   积分管理  —— 按年度统计积分 / 部门月度人均积分排名
#   员工管理  —— 按变动类型统计人次（四宫格公示）
#   考勤管理  —— 按结果统计考勤次数 / 按假期类型统计天数
# ==========================================================================

STAT_EMP_DEPT_ID = "s6006001-hr-emp-by-dept-000000000000001"
STAT_EMP_STATUS_ID = "s6006002-hr-emp-by-status-000000000001"
STAT_EMP_EDU_ID = "s6006003-hr-emp-by-education-00000000001"
STAT_EMP_NATURE_ID = "s6006004-hr-emp-by-nature-000000000001"
STAT_CHANGE_TYPE_ID = "s6006005-hr-change-by-type-00000000001"
STAT_JOB_DEPT_ID = "s6006006-hr-job-by-dept-0000000000001"
STAT_POINT_PERIOD_ID = "s6006007-hr-point-by-period-0000000001"
STAT_POINT_DEPT_ID = "s6006008-hr-point-dept-rank-0000000001"
STAT_LEAVE_TYPE_ID = "s6006009-hr-leave-by-type-00000000001"
STAT_ATTEND_RESULT_ID = "s6006010-hr-attend-by-result-000000001"

# --- 1. 按部门统计员工人数（HR 首页）--------------------------------------
STAT_EMP_DEPT = stat(
    STAT_EMP_DEPT_ID, "\u6309\u90e8\u95e8\u7edf\u8ba1\u5458\u5de5\u4eba\u6570",
    VIEW_EMP_ALL_ID, "dept", "count",
    description="\u5404\u90e8\u95e8\u5728\u804c\u5458\u5de5\u6570\u91cf\u5206\u5e03",
    category_title="\u90e8\u95e8", value_title="\u5458\u5de5\u4eba\u6570",
)
STAT_EMP_DEPT["properties"].update({
    "chartTypes": ["column", "pie", "bar"],
    "defaultChartType": "column",
    "showLegend": True, "showLabel": True,
    "isRowColumnConvert": True, "moreLink": VIEW_EMP_ALL_ID,
})

# --- 2. 按员工状态统计人数（官方档案查询分组口径）-------------------------
STAT_EMP_STATUS = stat(
    STAT_EMP_STATUS_ID, "\u6309\u5458\u5de5\u72b6\u6001\u7edf\u8ba1\u4eba\u6570",
    VIEW_EMP_ALL_ID, "employee_status", "count",
    description="\u6b63\u5f0f\u5458\u5de5 / \u8bd5\u7528\u671f\u5458\u5de5 / \u5b9e\u4e60\u671f\u5458\u5de5 / \u79bb\u804c\u5458\u5de5",
    category_title="\u5458\u5de5\u72b6\u6001", value_title="\u4eba\u6570",
)
STAT_EMP_STATUS["chartType"] = "pie"
STAT_EMP_STATUS["properties"].update({
    "chartTypes": ["pie", "column"], "defaultChartType": "pie",
    "legendPosition": "bottom", "showLegend": True, "showLabel": True,
    "moreLink": VIEW_EMP_ALL_ID,
})

# --- 3. 按学历统计人数 ----------------------------------------------------
STAT_EMP_EDU = stat(
    STAT_EMP_EDU_ID, "\u6309\u5b66\u5386\u7edf\u8ba1\u5458\u5de5\u4eba\u6570",
    VIEW_EMP_ALL_ID, "education", "count",
    description="\u4e13\u79d1/\u672c\u79d1/\u7855\u58eb/\u535a\u58eb\u5b66\u5386\u5206\u5e03",
    category_title="\u6700\u9ad8\u5b66\u5386", value_title="\u4eba\u6570",
)
STAT_EMP_EDU["properties"].update({"defaultChartType": "pie"})

# --- 4. 按用工性质统计人数 ------------------------------------------------
STAT_EMP_NATURE = stat(
    STAT_EMP_NATURE_ID, "\u6309\u7528\u5de5\u6027\u8d28\u7edf\u8ba1\u5458\u5de5\u4eba\u6570",
    VIEW_EMP_ALL_ID, "work_nature", "count",
    description="\u6b63\u5f0f\u7f16\u5236/\u52b3\u52a1\u6d3e\u9063/\u987e\u95ee\u7b49\u7528\u5de5\u6027\u8d28\u5206\u5e03",
    category_title="\u7528\u5de5\u6027\u8d28", value_title="\u4eba\u6570",
)
STAT_EMP_NATURE["properties"].update({"defaultChartType": "pie"})

# --- 5. 按变动类型统计人次（官方员工管理四宫格）---------------------------
STAT_CHANGE_TYPE = stat(
    STAT_CHANGE_TYPE_ID, "\u6309\u53d8\u52a8\u7c7b\u578b\u7edf\u8ba1\u4eba\u6b21",
    VIEW_CHANGE_ID, "change_type", "count",
    description="\u5165\u804c / \u8f6c\u5c97 / \u8f6c\u6b63 / \u79bb\u804c\u56db\u7c7b\u53d8\u52a8\u4eba\u6b21",
    category_title="\u53d8\u52a8\u7c7b\u578b", value_title="\u4eba\u6b21",
)
STAT_CHANGE_TYPE["properties"].update({
    "chartTypes": ["column", "pie"], "defaultChartType": "column",
    "showLegend": True, "showLabel": True, "moreLink": VIEW_CHANGE_ID,
})

# --- 6. 按部门统计岗位数（人才市场）---------------------------------------
STAT_JOB_DEPT = stat(
    STAT_JOB_DEPT_ID, "\u6309\u90e8\u95e8\u7edf\u8ba1\u62db\u8058\u5c97\u4f4d\u6570",
    VIEW_JOB_POOL_ID, "recruit_dept", "count",
    description="\u5404\u90e8\u95e8\u53d1\u5e03\u7684\u7ade\u8058\u5c97\u4f4d\u6570\u91cf",
    category_title="\u62db\u8058\u90e8\u95e8", value_title="\u5c97\u4f4d\u6570",
)
STAT_JOB_DEPT["properties"].update({"defaultChartType": "column"})

# --- 7. 按年度统计积分（官方「我的积分」年度/永久）-----------------------
STAT_POINT_PERIOD = stat(
    STAT_POINT_PERIOD_ID, "\u6309\u5e74\u5ea6\u7edf\u8ba1\u79ef\u5206",
    VIEW_POINT_ID, "point_year", "total_point",
    description="\u5e74\u5ea6\u79ef\u5206\u4e0e\u6c38\u4e45\u79ef\u5206\u7684\u5e74\u5ea6\u5206\u5e03",
    category_title="\u5e74\u5ea6", value_title="\u79ef\u5206",
)
STAT_POINT_PERIOD["properties"].update({
    "chartTypes": ["column", "line"], "defaultChartType": "column",
    "showLegend": True, "showLabel": True, "moreLink": VIEW_POINT_ID,
})

# --- 8. 部门月度人均积分排名（官方「部门月度人均积分排名」）---------------
STAT_POINT_DEPT = stat(
    STAT_POINT_DEPT_ID, "\u90e8\u95e8\u6708\u5ea6\u4eba\u5747\u79ef\u5206\u6392\u540d",
    VIEW_POINT_RANK_ID, "dept", "dept_avg_point",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u90e8\u95e8|\u4eba\u5747\u79ef\u5206|\u6708\u6392\u540d",
    category_title="\u90e8\u95e8", value_title="\u4eba\u5747\u79ef\u5206",
)
STAT_POINT_DEPT["properties"].update({
    "chartTypes": ["bar", "column"], "defaultChartType": "bar",
    "showLegend": True, "showLabel": True, "moreLink": VIEW_POINT_RANK_ID,
})

# --- 9. 按假期类型统计天数（考勤管理）-------------------------------------
STAT_LEAVE_TYPE = stat(
    STAT_LEAVE_TYPE_ID, "\u6309\u5047\u671f\u7c7b\u578b\u7edf\u8ba1\u8bf7\u5047\u5929\u6570",
    VIEW_LEAVE_REC_ID, "leave_type", "leave_days",
    description="\u4e8b\u5047/\u75c5\u5047/\u5e74\u5047/\u8c03\u4f11\u7b49\u5047\u671f\u5929\u6570\u5206\u5e03",
    category_title="\u5047\u671f\u7c7b\u578b", value_title="\u8bf7\u5047\u5929\u6570",
)
STAT_LEAVE_TYPE["properties"].update({"defaultChartType": "pie"})

# --- 10. 按考勤结果统计次数 -----------------------------------------------
STAT_ATTEND_RESULT = stat(
    STAT_ATTEND_RESULT_ID, "\u6309\u7ed3\u679c\u7edf\u8ba1\u8003\u52e4\u6b21\u6570",
    VIEW_ATTEND_ID, "attend_result", "count",
    description="\u6b63\u5e38/\u8fdf\u5230/\u65e9\u9000/\u65f7\u5de5\u7b49\u8003\u52e4\u7ed3\u679c\u5206\u5e03",
    category_title="\u8003\u52e4\u7ed3\u679c", value_title="\u6b21\u6570",
)
STAT_ATTEND_RESULT["chartType"] = "pie"
STAT_ATTEND_RESULT["properties"].update({
    "chartTypes": ["pie", "column"], "defaultChartType": "pie",
    "legendPosition": "bottom", "showLegend": True, "showLabel": True,
    "moreLink": VIEW_ATTEND_ID,
})

STATS = [
    STAT_EMP_DEPT, STAT_EMP_STATUS, STAT_EMP_EDU, STAT_EMP_NATURE,
    STAT_CHANGE_TYPE, STAT_JOB_DEPT, STAT_POINT_PERIOD, STAT_POINT_DEPT,
    STAT_LEAVE_TYPE, STAT_ATTEND_RESULT,
]


# ==========================================================================
# 查询配置（11 条，其中 9 条 JOIN）
# --------------------------------------------------------------------------
# 命名与字段沿用全局规范：employee_no / dept / project_no / process_id
# ==========================================================================

STMT_EMP_FULL_ID = "q6006001-hr-employee-full-0000000000001"
STMT_EMP_CHANGE_ID = "q6006002-hr-emp-change-join-00000000001"
STMT_EMP_POINT_ID = "q6006003-hr-emp-point-join-000000000001"
STMT_EMP_ATTEND_ID = "q6006004-hr-emp-attend-join-00000000001"
STMT_JOB_APPLY_ID = "q6006005-hr-job-apply-join-000000000001"
STMT_POINT_RANK_ID = "q6006006-hr-point-rank-00000000000001"
STMT_DEPT_POINT_ID = "q6006007-hr-dept-point-avg-0000000000001"
STMT_SELF_PANORAMA_ID = "q6006008-hr-self-panorama-00000000001"
STMT_ATTEND_STAT_ID = "q6006009-hr-attend-stat-0000000000001"
STMT_LEAVE_OT_ID = "q6006010-hr-leave-overtime-join-000000001"
STMT_EMP_RESUME_ID = "q6006011-hr-emp-resume-join-00000000001"

# --- 1. 员工档案全量（单一主表，带枚举译名）-------------------------------
STMT_EMP_FULL = statement(
    STMT_EMP_FULL_ID,
    "\u5458\u5de5\u6863\u6848\u5168\u91cf",
    "SELECT e.id AS id, e.employee_no AS employee_no, "
    "e.employee_name AS employee_name, e.gender AS gender, "
    "e.employee_status AS employee_status, e.work_nature AS work_nature, "
    "e.id_card AS id_card, e.birth_date AS birth_date, "
    "e.nation AS nation, e.political_status AS political_status, "
    "e.marital_status AS marital_status, e.mobile AS mobile, "
    "e.email AS email, e.wechat AS wechat, e.qq AS qq, "
    "e.education AS education, e.degree AS degree, "
    "e.graduate_school AS graduate_school, e.major AS major, "
    "e.dept AS dept, e.position AS position, e.grade AS grade, "
    "e.join_date AS join_date, e.regular_date AS regular_date, "
    "e.leave_date AS leave_date, e.year_point AS year_point, "
    "e.total_point AS total_point, e.process_id AS process_id "
    "FROM hr_employee e",
    description="\u5458\u5de5\u6863\u6848\u53f0\u8d26\u5168\u91cf\uff0c\u652f\u6491\u5168\u90e8\u6863\u6848\u4e0e\u56db\u7c7b\u72b6\u6001\u67e5\u8be2",
    query_type="sql",
)

# --- 2. 人事变动 ⟕ 员工档案 ----------------------------------------------
STMT_EMP_CHANGE = statement(
    STMT_EMP_CHANGE_ID,
    "\u4eba\u4e8b\u53d8\u52a8\u5168\u91cf",
    "SELECT c.id AS id, c.change_no AS change_no, "
    "c.change_type AS change_type, c.employee_no AS employee_no, "
    "c.employee_name AS employee_name, c.old_dept AS old_dept, "
    "c.new_dept AS new_dept, c.old_position AS old_position, "
    "c.new_position AS new_position, c.old_grade AS old_grade, "
    "c.new_grade AS new_grade, c.old_status AS old_status, "
    "c.new_status AS new_status, c.effect_date AS effect_date, "
    "c.apply_date AS apply_date, c.approve_status AS approve_status, "
    "c.publish_flag AS publish_flag, c.process_id AS process_id, "
    "e.dept AS current_dept, e.position AS current_position, "
    "e.employee_status AS current_status, e.education AS education, "
    "e.join_date AS join_date "
    "FROM hr_change c "
    "LEFT JOIN hr_employee e ON e.employee_no = c.employee_no",
    description="\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55\u5e26\u5f53\u524d\u6863\u6848\u4fe1\u606f\uff0c\u652f\u6491\u5b98\u65b9\u56db\u5bab\u683c\u516c\u793a",
    query_type="sql",
)

# --- 3. 员工积分 ⟕ 员工档案 ----------------------------------------------
STMT_EMP_POINT = statement(
    STMT_EMP_POINT_ID,
    "\u5458\u5de5\u79ef\u5206\u5168\u91cf",
    "SELECT p.id AS id, p.employee_no AS employee_no, "
    "p.employee_name AS employee_name, p.point_year AS point_year, "
    "p.point_type AS point_type, p.year_point AS year_point, "
    "p.total_point AS total_point, p.point_source AS point_source, "
    "p.relate_biz AS relate_biz, p.grant_date AS grant_date, "
    "p.honor_level AS honor_level, p.rank_no AS rank_no, "
    "p.point_status AS point_status, "
    "p.dept_avg_point AS dept_avg_point, p.dept_rank AS dept_rank, "
    "e.dept AS dept, e.position AS position, "
    "e.employee_status AS employee_status "
    "FROM hr_point p "
    "LEFT JOIN hr_employee e ON e.employee_no = p.employee_no",
    description="\u79ef\u5206\u53f0\u8d26\u5e26\u5458\u5de5\u5f53\u524d\u90e8\u95e8\u4e0e\u5c97\u4f4d",
    query_type="sql",
)

# --- 4. 考勤记录 ⟕ 员工档案 ----------------------------------------------
STMT_EMP_ATTEND = statement(
    STMT_EMP_ATTEND_ID,
    "\u8003\u52e4\u8bb0\u5f55\u5168\u91cf",
    "SELECT a.id AS id, a.attend_no AS attend_no, "
    "a.employee_no AS employee_no, a.employee_name AS employee_name, "
    "a.attend_period AS attend_period, a.attend_date AS attend_date, "
    "a.week_day AS week_day, a.on_time AS on_time, a.off_time AS off_time, "
    "a.attend_type AS attend_type, a.attend_result AS attend_result, "
    "a.should_days AS should_days, a.actual_days AS actual_days, "
    "a.late_count AS late_count, a.early_count AS early_count, "
    "a.absent_count AS absent_count, a.leave_days AS leave_days, "
    "a.overtime_hours AS overtime_hours, a.travel_days AS travel_days, "
    "a.attend_status AS attend_status, a.emp_confirm AS emp_confirm, "
    "e.dept AS dept, e.position AS position "
    "FROM hr_attend a "
    "LEFT JOIN hr_employee e ON e.employee_no = a.employee_no",
    description="\u8003\u52e4\u660e\u7ec6\u5e26\u5458\u5de5\u90e8\u95e8\u4e0e\u5c97\u4f4d",
    query_type="sql",
)

# --- 5. 岗位报名 ⟕ 岗位池 ------------------------------------------------
STMT_JOB_APPLY = statement(
    STMT_JOB_APPLY_ID,
    "\u5c97\u4f4d\u62a5\u540d\u5168\u91cf",
    "SELECT a.id AS id, a.apply_no AS apply_no, a.job_no AS job_no, "
    "a.job_name AS job_name, a.recruit_dept AS recruit_dept, "
    "a.employee_no AS employee_no, a.employee_name AS employee_name, "
    "a.dept AS dept, a.position AS position, a.grade AS grade, "
    "a.join_date AS join_date, a.apply_date AS apply_date, "
    "a.is_summary AS is_summary, a.apply_status AS apply_status, "
    "a.interview_score AS interview_score, a.apply_result AS apply_result, "
    "a.process_id AS process_id, "
    "j.standard_grade AS standard_grade, j.bid_type AS bid_type, "
    "j.recruit_count AS recruit_count, j.publish_date AS publish_date, "
    "j.deadline AS deadline, j.job_status AS job_status "
    "FROM hr_job_apply a "
    "LEFT JOIN hr_job j ON j.job_no = a.job_no",
    description="\u62a5\u540d\u8bb0\u5f55\u5e26\u5c97\u4f4d\u6807\u51c6\u804c\u7ea7/\u7ade\u8058\u7c7b\u578b/\u622a\u6b62\u65f6\u95f4",
    query_type="sql",
)

# --- 6. 个人年度积分排名（聚合）-------------------------------------------
STMT_POINT_RANK = statement(
    STMT_POINT_RANK_ID,
    "\u4e2a\u4eba\u5e74\u5ea6\u79ef\u5206\u6392\u540d",
    "SELECT e.employee_no AS employee_no, e.employee_name AS employee_name, "
    "e.dept AS dept, e.position AS position, "
    "SUM(p.total_point) AS total_point, "
    "SUM(p.year_point) AS year_point, "
    "COUNT(p.id) AS point_count, "
    "MAX(p.rank_no) AS rank_no "
    "FROM hr_employee e "
    "LEFT JOIN hr_point p ON p.employee_no = e.employee_no "
    "GROUP BY e.employee_no, e.employee_name, e.dept, e.position "
    "ORDER BY total_point DESC",
    description="\u5b98\u65b9\u201c\u4e2a\u4eba\u5e74\u5ea6\u6392\u540d\uff1a\u59d3\u540d|\u79ef\u5206|\u6392\u540d\u201d\u7684\u6570\u636e\u6e90",
    query_type="sql",
)

# --- 7. 部门月度人均积分排名（聚合）---------------------------------------
STMT_DEPT_POINT = statement(
    STMT_DEPT_POINT_ID,
    "\u90e8\u95e8\u6708\u5ea6\u4eba\u5747\u79ef\u5206\u6392\u540d",
    "SELECT e.dept AS dept, COUNT(DISTINCT e.employee_no) AS emp_count, "
    "SUM(p.total_point) AS dept_point, "
    "ROUND(SUM(p.total_point) / COUNT(DISTINCT e.employee_no), 2) "
    "  AS avg_point, "
    "MAX(p.dept_rank) AS dept_rank "
    "FROM hr_employee e "
    "LEFT JOIN hr_point p ON p.employee_no = e.employee_no "
    "GROUP BY e.dept "
    "ORDER BY avg_point DESC",
    description="\u5b98\u65b9\u201c\u90e8\u95e8\u6708\u5ea6\u4eba\u5747\u79ef\u5206\u6392\u540d\uff1a\u90e8\u95e8|\u4eba\u5747\u79ef\u5206|\u6708\u6392\u540d\u201d",
    query_type="sql",
)

# --- 8. 员工自助全景（自助 ⟕ 员工档案，跨应用待办）-----------------------
STMT_SELF_PANORAMA = statement(
    STMT_SELF_PANORAMA_ID,
    "\u5458\u5de5\u81ea\u52a9\u5168\u666f",
    "SELECT s.id AS id, s.self_no AS self_no, s.employee_no AS employee_no, "
    "s.employee_name AS employee_name, s.self_type AS self_type, "
    "s.apply_title AS apply_title, s.start_time AS start_time, "
    "s.end_time AS end_time, s.current_step AS current_step, "
    "s.self_status AS self_status, s.contact_phone AS contact_phone, "
    "s.process_id AS process_id, "
    "e.dept AS dept, e.position AS position, "
    "e.employee_status AS employee_status, "
    "IFNULL(l.days, 0) AS leave_days, "
    "IFNULL(o.hours, 0) AS overtime_hours, "
    "IFNULL(t.days, 0) AS travel_days "
    "FROM hr_self s "
    "LEFT JOIN hr_employee e ON e.employee_no = s.employee_no "
    "LEFT JOIN (SELECT leave_no AS biz_no, leave_days AS days "
    "           FROM hr_leave) l ON l.biz_no = s.self_no "
    "LEFT JOIN (SELECT overtime_no AS biz_no, "
    "           overtime_hours AS hours "
    "           FROM hr_overtime) o ON o.biz_no = s.self_no "
    "LEFT JOIN (SELECT travel_no AS biz_no, travel_days AS days "
    "           FROM hr_travel) t ON t.biz_no = s.self_no",
    description="\u5b98\u65b9\u5217\u987a\u5e8f\uff1a\u6d41\u7a0b\u7c7b\u578b|\u6807\u9898|\u53d1\u8d77\u4eba|\u5f00\u59cb\u65f6\u95f4|\u5f53\u524d\u6b65\u9aa4",
    query_type="sql",
)

# --- 9. 考勤月度统计（聚合）-----------------------------------------------
STMT_ATTEND_STAT = statement(
    STMT_ATTEND_STAT_ID,
    "\u8003\u52e4\u6708\u5ea6\u7edf\u8ba1",
    "SELECT a.employee_no AS employee_no, "
    "a.employee_name AS employee_name, a.attend_period AS attend_period, "
    "SUM(a.should_days) AS should_days, SUM(a.actual_days) AS actual_days, "
    "SUM(a.late_count) AS late_count, SUM(a.early_count) AS early_count, "
    "SUM(a.absent_count) AS absent_count, SUM(a.leave_days) AS leave_days, "
    "SUM(a.overtime_hours) AS overtime_hours, "
    "SUM(a.travel_days) AS travel_days, "
    "e.dept AS dept, e.position AS position "
    "FROM hr_attend a "
    "LEFT JOIN hr_employee e ON e.employee_no = a.employee_no "
    "GROUP BY a.employee_no, a.employee_name, a.attend_period, "
    "e.dept, e.position",
    description="\u5b98\u65b9\u201c\u8003\u52e4\u7edf\u8ba1\u201d\u7684\u6570\u636e\u6e90\uff1a\u6309\u5458\u5de5+\u5468\u671f\u6c47\u603b",
    query_type="sql",
)

# --- 10. 请假 ⟕ 加班 ⟕ 员工档案（自助三类业务合并）-----------------------
STMT_LEAVE_OT = statement(
    STMT_LEAVE_OT_ID,
    "\u8bf7\u5047\u52a0\u73ed\u51fa\u5dee\u5408\u5e76",
    "SELECT l.id AS id, 'lv' AS biz_flag, l.leave_no AS biz_no, "
    "l.employee_no AS employee_no, l.employee_name AS employee_name, "
    "l.leave_type AS biz_type, l.leave_days AS biz_days, "
    "l.start_time AS start_time, l.end_time AS end_time, "
    "l.leave_status AS biz_status, l.process_id AS process_id, "
    "e.dept AS dept, e.position AS position "
    "FROM hr_leave l "
    "LEFT JOIN hr_employee e ON e.employee_no = l.employee_no",
    description="\u8bf7\u5047\u8bb0\u5f55\u5e26\u5458\u5de5\u6863\u6848\uff08\u4e0e\u52a0\u73ed/\u51fa\u5dee\u8868\u7ed3\u6784\u5bf9\u9f50\uff0c\u4f9b UNION \u5408\u5e76\uff09",
    query_type="sql",
)

# --- 11. 员工简历全景（档案 ⟕ 履历明细，一对多）---------------------------
STMT_EMP_RESUME = statement(
    STMT_EMP_RESUME_ID,
    "\u5458\u5de5\u7b80\u5386\u5168\u666f",
    "SELECT e.employee_no AS employee_no, e.employee_name AS employee_name, "
    "e.gender AS gender, e.dept AS dept, e.position AS position, "
    "e.employee_status AS employee_status, e.education AS education, "
    "e.join_date AS join_date, "
    "IFNULL(d1.detail_count, 0) AS inner_work_count, "
    "IFNULL(d2.detail_count, 0) AS work_count, "
    "IFNULL(d3.detail_count, 0) AS edu_count, "
    "IFNULL(d4.detail_count, 0) AS tech_count, "
    "IFNULL(d5.detail_count, 0) AS award_count, "
    "IFNULL(p.point_total, 0) AS point_total "
    "FROM hr_employee e "
    "LEFT JOIN (SELECT employee_no, COUNT(*) AS detail_count "
    "           FROM hr_emp_detail WHERE detail_type = 'inner_work' "
    "           GROUP BY employee_no) d1 ON d1.employee_no = e.employee_no "
    "LEFT JOIN (SELECT employee_no, COUNT(*) AS detail_count "
    "           FROM hr_emp_detail WHERE detail_type = 'work' "
    "           GROUP BY employee_no) d2 ON d2.employee_no = e.employee_no "
    "LEFT JOIN (SELECT employee_no, COUNT(*) AS detail_count "
    "           FROM hr_emp_detail WHERE detail_type = 'edu' "
    "           GROUP BY employee_no) d3 ON d3.employee_no = e.employee_no "
    "LEFT JOIN (SELECT employee_no, COUNT(*) AS detail_count "
    "           FROM hr_emp_detail WHERE detail_type = 'tech' "
    "           GROUP BY employee_no) d4 ON d4.employee_no = e.employee_no "
    "LEFT JOIN (SELECT employee_no, COUNT(*) AS detail_count "
    "           FROM hr_emp_detail WHERE detail_type = 'award' "
    "           GROUP BY employee_no) d5 ON d5.employee_no = e.employee_no "
    "LEFT JOIN (SELECT employee_no, SUM(total_point) AS point_total "
    "           FROM hr_point GROUP BY employee_no) p "
    "  ON p.employee_no = e.employee_no",
    description="\u6863\u6848\u4e0e\u4e94\u7c7b\u5c65\u5386\u660e\u7ec6\u3001\u79ef\u5206\u7684\u4e00\u89c8\u805a\u5408",
    query_type="sql",
)

STATEMENTS = [
    STMT_EMP_FULL, STMT_EMP_CHANGE, STMT_EMP_POINT, STMT_EMP_ATTEND,
    STMT_JOB_APPLY, STMT_POINT_RANK, STMT_DEPT_POINT, STMT_SELF_PANORAMA,
    STMT_ATTEND_STAT, STMT_LEAVE_OT, STMT_EMP_RESUME,
]


# ==========================================================================
# 导出清单
# ==========================================================================

FORMS = [
    FORM_EMP, FORM_ONBOARD, FORM_TRANSFER, FORM_REGULAR, FORM_RESIGN,
    FORM_JOB, FORM_JOB_APPLY, FORM_POINT, FORM_BOUNTY, FORM_EXCHANGE,
    FORM_LEAVE, FORM_OVERTIME, FORM_TRAVEL, FORM_ATTEND, FORM_SELF,
    FORM_PROFILE, FORM_ATTCFG,
]

PROCESSES = [
    PROC_ONBOARD, PROC_TRANSFER, PROC_REGULAR, PROC_RESIGN,
    PROC_JOB_PUBLISH, PROC_JOB_APPLY, PROC_POINT_GRANT, PROC_BOUNTY,
    PROC_EXCHANGE, PROC_LEAVE, PROC_OVERTIME, PROC_TRAVEL,
    PROC_ATTEND, PROC_SELF,
]


# ==========================================================================
# 门户应用（Portal / Page）
# --------------------------------------------------------------------------
# 官方门户截图 refs/hr/1652073737656.png 实测版式：
#   顶栏（欢迎您！XX / 个人设置 / 退出）+ 品牌条「人力资源管理系统」
#   + 顶部一级导航 8 项 + 二级标签 7 项 + 矩阵式卡片区 + 底部版权
#
# 卡片矩阵（3 列 × 4 行）：
#   ① 新闻公告（大图卡） | 员工自助（6 彩图标） | 人事变动公示
#   ② 待办工作           | 岗位报名              | 积分公示
#   ③ 待阅工作           | 本月考勤（小月历）     | 部门月度人均积分排名
#   ④ 我的积分与积分悬赏  | 统计图 × 2
#
# 页面 HTML 由 o2oa_hr_portal 生成，Page.data 存储该 HTML **字符串**。
# ==========================================================================

import o2oa_hr_portal as _HRPT
import o2oa_portal as _PT
from o2oa_builder import portal, portal_page

PORTAL_ID = "o6006001-hr-portal-00000000000000001"
PAGE_HOME_ID = "o6006002-hr-portal-home-page-000000000001"
PAGE_EMP_ID = "o6006003-hr-portal-emp-page-0000000000001"
PAGE_JOB_ID = "o6006004-hr-portal-job-page-0000000000001"
PAGE_POINT_ID = "o6006005-hr-portal-point-page-00000000001"
PAGE_ATTEND_ID = "o6006006-hr-portal-attend-page-0000000001"
PAGE_SELF_ID = "o6006007-hr-portal-self-page-000000000001"
PAGE_CHG_ID = "o6006008-hr-portal-chg-page-0000000000001"

# --- 导航 / 自助图标 → 真实业务目标 ---------------------------------------
#   (portalId, pageId)  → 页面直达
#   ("startone", 流程id) → 一键发起指定流程（取当前人身份直接 startWork）
#   ("profile",)        → 个人设置（改密页签）
HR_NAV_TARGETS = {
    "\u9996\u9875": (PORTAL_ID, PAGE_HOME_ID),
    "\u5458\u5de5\u6863\u6848": (PORTAL_ID, PAGE_EMP_ID),
    "\u5458\u5de5\u7ba1\u7406": (PORTAL_ID, PAGE_CHG_ID),
    "\u4eba\u624d\u5e02\u573a": (PORTAL_ID, PAGE_JOB_ID),
    "\u79ef\u5206\u7ba1\u7406": (PORTAL_ID, PAGE_POINT_ID),
    "\u8003\u52e4\u7ba1\u7406": (PORTAL_ID, PAGE_ATTEND_ID),
    "\u5458\u5de5\u81ea\u52a9": (PORTAL_ID, PAGE_SELF_ID),
    "\u4e2a\u4eba\u8bbe\u7f6e": ("profile",),
    # 员工自助 6 图标
    "\u6211\u7684\u6863\u6848": (PORTAL_ID, PAGE_SELF_ID),
    "\u6211\u7684\u62a5\u540d": (PORTAL_ID, PAGE_JOB_ID),
    "\u6211\u7684\u79ef\u5206": (PORTAL_ID, PAGE_POINT_ID),
    "\u6211\u8981\u8bf7\u5047": ("startone", PROC_LEAVE_ID),
    "\u6211\u8981\u52a0\u73ed": ("startone", PROC_OVERTIME_ID),
    "\u6211\u8981\u51fa\u5dee": ("startone", PROC_TRAVEL_ID),
}
_HRPT.HR_NAV_TARGETS.update(HR_NAV_TARGETS)

# --- 左侧导航树（照官方截图）----------------------------------------------
PORTAL_TREE = [
    (1, "\u6211\u7684\u6863\u6848", None, True),
    (1, "\u65b0\u5efa\u6863\u6848", None, False),
    (1, "\u5bfc\u5165\u6863\u6848", None, False),
    (1, "\u6863\u6848\u67e5\u8be2", None, False),
    (2, "\u5168\u90e8\u6863\u6848", None, False),
    (2, "\u6b63\u5f0f\u5458\u5de5", None, False),
    (2, "\u8bd5\u7528\u671f\u5458\u5de5", None, False),
    (2, "\u5b9e\u4e60\u671f\u5458\u5de5", None, False),
    (2, "\u79bb\u804c\u5458\u5de5", None, False),
    (1, "\u5458\u5de5\u6863\u6848\u914d\u7f6e", None, False),
    (2, "\u7528\u6237\u6743\u9650\u8bbe\u7f6e", None, False),
    (2, "\u5458\u5de5\u6863\u6848\u7ba1\u7406\u5458", None, False),
]

ATTEND_TREE = [
    (1, "\u6211\u7684\u8003\u52e4", None, True),
    (1, "\u8003\u52e4\u7edf\u8ba1", None, False),
    (1, "\u7ef4\u62a4", None, False),
    (2, "\u6570\u636e\u5bfc\u5165", None, False),
    (2, "\u5458\u5de5\u4f11\u5047\u8bb0\u5f55", None, False),
    (1, "\u6743\u9650\u548c\u4eba\u5458", None, False),
    (1, "\u914d\u7f6e", None, False),
]

# --- 门户数据（示例初始值，正式使用由统计与视图实时替换）------------------
PORTAL_DATE_TEXT = "2026\u5e7405\u670809\u65e5(\u5468\u516d)"

PORTAL_NEWS = [
    ("\u534f\u4f1a\u53d1\u5e032026\u5e74\u5ea6\u4eba\u624d\u53d1\u5c55\u89c4\u5212",
     "05-08"),
    ("\u590d\u5408\u6750\u6599\u4ea7\u4e1a\u4eba\u624d\u9700\u6c42\u62a5\u544a\u53d1\u5e03",
     "05-06"),
    ("2026\u5e74\u5ea6\u804c\u79f0\u8bc4\u5ba1\u5de5\u4f5c\u542f\u52a8", "05-04"),
    ("\u65b0\u5458\u5de5\u5165\u804c\u57f9\u8bad\u8ba1\u5212\u5b89\u6392", "05-02"),
]

# 人事变动公示 —— 取员工主表的真实转正/入职记录（数据来自组织 9 人）
PORTAL_CHANGE = {
    "transfer": [                                   # 转正记录（regular_date）
        ("罗舒涵", "2024-05-19", "国际业务部", "国际业务专员"),
        ("赵旭东", "2023-11-14", "会员服务部", "会员服务专员"),
        ("奚莎莎", "2023-06-06", "会员服务部", "会员服务专员"),
        ("杜阳", "2022-10-01", "行业研究部", "助理研究员"),
        ("时晓明", "2021-07-12", "行业研究部", "研究员"),
    ],
    "regular": [
        ("罗舒涵", "2024-05-19", "国际业务部", "国际业务专员"),
        ("赵旭东", "2023-11-14", "会员服务部", "会员服务专员"),
        ("奚莎莎", "2023-06-06", "会员服务部", "会员服务专员"),
    ],
    "onboard": [                                    # 入职记录（join_date）
        ("罗舒涵", "2024-02-19", "国际业务部", "国际业务专员"),
        ("赵旭东", "2023-08-14", "会员服务部", "会员服务专员"),
        ("奚莎莎", "2023-03-06", "会员服务部", "会员服务专员"),
        ("杜阳", "2022-07-01", "行业研究部", "助理研究员"),
        ("时晓明", "2021-04-12", "行业研究部", "研究员"),
    ],
    "resign": [],                                   # 协会暂无离职记录
}

PORTAL_TODO = [
    ("《员工转正申请》审批 - 罗舒涵", "综合管理部", "09-18"),
    ("《请假申请》审批 - 奚莎莎", "会员服务部", "09-18"),
    ("《岗位需求》审核 - 国际业务部", "综合管理部", "09-17"),
    ("《员工入职》审批 - 赵旭东", "综合管理部", "09-17"),
    ("《出差申请》审批 - 杜阳", "行业研究部", "09-16"),
    ("《加班申请》审批 - 时晓明", "行业研究部", "09-16"),
]

PORTAL_READ = [
    ("2026年度员工培训计划", "综合管理部", "09-15"),
    ("新版考勤管理制度宣贯", "综合管理部", "09-12"),
    ("职称评审申报通知", "综合管理部", "09-10"),
]

PORTAL_JOB = [
    ("国际业务专员", "国际业务部", "2026-08-01", "招聘中"),
    ("复合材料工艺研究员", "行业研究部", "2026-05-06", "已结束"),
]

# 我的积分 —— 取积分表中最高分员工（时晓明）的真实数值作兜底
PORTAL_MY_POINT = {"year_point": 120, "year_rank": 1,
                   "total_point": 320, "total_rank": 1}

PORTAL_BOUNTY = [
    ("51-100 分", "编制复合材料回收工艺企业标准草案", "2026-09-12"),
    ("31-50 分", "整理国际复合材料行业年报摘要", "2026-09-08"),
]

# 个人年度积分排名（积分表真实数据）
PORTAL_RANK = [
    ("时晓明", "320", "1"),
    ("李静", "260", "1"),
    ("杜阳", "190", "2"),
]

# 部门月度人均积分排名（按部门归集积分表）
PORTAL_DEPT_RANK = [
    ("行业研究部", "255.0", "1"),
    ("会员服务部", "260.0", "1"),
]

PORTAL_CALENDAR = {"year": 2026, "month": 9, "today": 20,
                   "late_days": [],
                   "period_text": "09月01日-09月30日"}

PORTAL_CHARTS = [
    ("按部门统计员工人数", "column",
     [("综合管理部", 2), ("行业研究部", 2),
      ("会员服务部", 4), ("国际业务部", 1)], True),
    ("按员工状态统计人数", "pie",
     [("在职", 9), ("试用期", 0), ("实习期", 0), ("离职", 0)], True),
]

# 门户活数据源：待办 + 两张图挂到「员工档案全量」语句
_HR_Q = "q6006001-hr-employee-full-0000000000001"
_HR_CHART_SRC = {
    "按部门统计员工人数": {"statement": _HR_Q, "field": "dept", "value": ""},
    "按员工状态统计人数": {"statement": _HR_Q, "field": "employee_status", "value": ""},
}


def _hr_live(charts=(), todo_page=6):
    """按当前页实际渲染的图表列表生成活数据源（idx 必须与本页图表顺序一致）。

    各页只渲染 PORTAL_CHARTS 的子集，因此不能共用一份固定 idx 的 spec。
    """
    out = []
    for i, item in enumerate(charts):
        title, ctype = item[0], item[1]
        src = _HR_CHART_SRC.get(title)
        if not src:
            continue
        d = {"idx": i, "type": ctype, "title": title}
        d.update(src)
        out.append(d)
    return {"todo_page": todo_page, "charts": out}

# --- HR 导航点击映射（o2oa_hr_portal._hr_header / _hr_quick_card 消费）---
# 值为 (portalId, pageId) → 打开对应页面；("profile",) → 个人设置；
# ("start",) → 任务中心「发起流程」；未命中 → 待办中心。
_HRPT.HR_NAV_TARGETS = {
    "首页": (PORTAL_ID, PAGE_HOME_ID),
    "员工档案": (PORTAL_ID, PAGE_EMP_ID),
    "人才市场": (PORTAL_ID, PAGE_JOB_ID),
    "积分管理": (PORTAL_ID, PAGE_POINT_ID),
    "考勤管理": (PORTAL_ID, PAGE_ATTEND_ID),
    "员工自助": (PORTAL_ID, PAGE_SELF_ID),
    "个人设置": ("profile",),
    "我的档案": (PORTAL_ID, PAGE_EMP_ID),
    "我的积分": (PORTAL_ID, PAGE_POINT_ID),
    "修改密码": ("profile",),
}

PAGE_HOME_HTML = _HRPT.hr_portal_html(
    date_text=PORTAL_DATE_TEXT,
    news=PORTAL_NEWS, change_public=PORTAL_CHANGE,
    todo_rows=PORTAL_TODO, read_rows=PORTAL_READ,
    job_rows=PORTAL_JOB, my_point=PORTAL_MY_POINT,
    bounty_rows=PORTAL_BOUNTY, rank_rows=PORTAL_RANK,
    dept_rank_rows=PORTAL_DEPT_RANK, calendar_args=PORTAL_CALENDAR,
    charts=PORTAL_CHARTS, active_nav=0,
    live=_hr_live(PORTAL_CHARTS, todo_page=6),
)

# 第二页：员工档案（一级导航「员工档案」高亮）—— 真实档案视图 + 入职/转正/调动/离职
PAGE_EMP_HTML = _HRPT.hr_view_page_html(
    "\u5458\u5de5\u6863\u6848",
    subtitle="\u5168\u90e8\u5728\u804c\u5458\u5de5\u6863\u6848\u4e0e\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55\uff08\u5b9e\u65f6\u6570\u636e\uff0c\u884c\u70b9\u51fb\u53ef\u6253\u5f00\u5bf9\u5e94\u6d41\u7a0b\uff09",
    nav_active=1,
    sections=[
        ("\u5168\u90e8\u5458\u5de5\u6863\u6848", TABLE_EMP_ID, [
            ("employee_no", "\u5de5\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("gender", "\u6027\u522b"), ("dept", "\u90e8\u95e8"),
            ("position", "\u804c\u52a1"), ("mobile", "\u624b\u673a"),
            ("education", "\u5b66\u5386"), ("join_date", "\u5165\u804c\u65e5\u671f", "date"),
            ("employee_status", "\u72b6\u6001"),
        ], 420),
        ("\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55", TABLE_CHANGE_HR_ID, [
            ("change_no", "\u53d8\u52a8\u5355\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("change_type", "\u53d8\u52a8\u7c7b\u578b"), ("old_dept", "\u539f\u90e8\u95e8"),
            ("new_dept", "\u73b0\u90e8\u95e8"), ("new_position", "\u73b0\u804c\u52a1"),
            ("effect_date", "\u751f\u6548\u65e5\u671f", "date"),
            ("approve_status", "\u5ba1\u6279\u72b6\u6001"),
        ], 300),
    ],
    actions=[
        ("\u5458\u5de5\u5165\u804c\u767b\u8bb0", "startone", PROC_EMP_ONBOARD_ID, False),
        ("\u5458\u5de5\u8f6c\u6b63", "startone", PROC_EMP_REGULAR_ID, True),
        ("\u5458\u5de5\u8c03\u52a8", "startone", PROC_EMP_TRANSFER_ID, True),
        ("\u5458\u5de5\u79bb\u804c", "startone", PROC_EMP_LEAVE_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

# 员工管理（一级导航「员工管理」）—— 人事变动视图 + 四类变动一键发起
PAGE_CHG_HTML = _HRPT.hr_view_page_html(
    "\u5458\u5de5\u7ba1\u7406",
    subtitle="\u5165\u804c / \u8f6c\u6b63 / \u8c03\u52a8 / \u79bb\u804c\u4e00\u7ad9\u5f0f\u529e\u7406\uff0c\u53d8\u52a8\u8bb0\u5f55\u5b9e\u65f6\u516c\u793a",
    nav_active=2,
    sections=[
        ("\u5728\u804c\u5458\u5de5\u540d\u518c", TABLE_EMP_ID, [
            ("employee_no", "\u5de5\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("gender", "\u6027\u522b"), ("dept", "\u90e8\u95e8"),
            ("position", "\u804c\u52a1"), ("grade", "\u804c\u7ea7"),
            ("join_date", "\u5165\u804c\u65e5\u671f", "date"),
            ("employee_status", "\u72b6\u6001"),
        ], 300),
        ("\u4eba\u4e8b\u53d8\u52a8\u8bb0\u5f55", TABLE_CHANGE_HR_ID, [
            ("change_no", "\u53d8\u52a8\u5355\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("change_type", "\u53d8\u52a8\u7c7b\u578b"), ("old_dept", "\u539f\u90e8\u95e8"),
            ("new_dept", "\u73b0\u90e8\u95e8"), ("new_position", "\u73b0\u804c\u52a1"),
            ("effect_date", "\u751f\u6548\u65e5\u671f", "date"),
            ("approve_status", "\u5ba1\u6279\u72b6\u6001"),
        ], 320),
    ],
    actions=[
        ("\u5458\u5de5\u5165\u804c\u767b\u8bb0", "startone", PROC_EMP_ONBOARD_ID, False),
        ("\u5458\u5de5\u8f6c\u6b63", "startone", PROC_EMP_REGULAR_ID, True),
        ("\u5458\u5de5\u8c03\u52a8", "startone", PROC_EMP_TRANSFER_ID, True),
        ("\u5458\u5de5\u79bb\u804c", "startone", PROC_EMP_LEAVE_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

# 第三页：人才市场 —— 岗位池 + 报名记录视图
PAGE_JOB_HTML = _HRPT.hr_view_page_html(
    "\u4eba\u624d\u5e02\u573a",
    subtitle="\u5c97\u4f4d\u6c60\u4e0e\u62db\u8058\u62a5\u540d\u5b9e\u65f6\u6570\u636e",
    nav_active=3,
    sections=[
        ("\u62db\u8058\u5c97\u4f4d\u6c60", TABLE_JOB_ID, [
            ("job_no", "\u5c97\u4f4d\u7f16\u53f7"), ("job_name", "\u5c97\u4f4d\u540d\u79f0"),
            ("recruit_dept", "\u62db\u8058\u90e8\u95e8"), ("recruit_count", "\u4eba\u6570", "num"),
            ("standard_grade", "\u804c\u7ea7"), ("salary_range", "\u85aa\u916c\u533a\u95f4"),
            ("deadline", "\u622a\u6b62\u65e5\u671f", "date"), ("job_status", "\u72b6\u6001"),
        ], 330),
        ("\u62a5\u540d\u8bb0\u5f55", TABLE_JOB_APPLY_ID, [
            ("apply_no", "\u62a5\u540d\u5355\u53f7"), ("job_name", "\u5c97\u4f4d"),
            ("employee_name", "\u62a5\u540d\u4eba"), ("dept", "\u6240\u5728\u90e8\u95e8"),
            ("apply_date", "\u62a5\u540d\u65e5\u671f", "date"),
            ("interview_score", "\u9762\u8bd5\u5f97\u5206", "num"),
            ("apply_status", "\u72b6\u6001"),
        ], 300),
    ],
    actions=[
        ("\u53d1\u5e03\u62db\u8058\u5c97\u4f4d", "startone", PROC_JOB_PUBLISH_ID, False),
        ("\u5458\u5de5\u62a5\u540d", "startone", PROC_JOB_APPLY_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

# 第四页：积分管理 —— 积分明细 + 排行榜视图
PAGE_POINT_HTML = _HRPT.hr_view_page_html(
    "\u79ef\u5206\u7ba1\u7406",
    subtitle="\u79ef\u5206\u660e\u7ec6\u4e0e\u6392\u884c\u699c\u5b9e\u65f6\u6570\u636e",
    nav_active=4,
    sections=[
        ("\u79ef\u5206\u660e\u7ec6", TABLE_POINT_ID, [
            ("employee_name", "\u59d3\u540d"), ("dept", "\u90e8\u95e8"),
            ("point_year", "\u5e74\u5ea6"), ("point_type", "\u79ef\u5206\u7c7b\u578b"),
            ("year_point", "\u5f53\u5e74\u79ef\u5206", "num"),
            ("total_point", "\u7d2f\u8ba1\u79ef\u5206", "num"),
            ("honor_level", "\u8363\u8a89"), ("grant_date", "\u53d1\u653e\u65e5\u671f", "date"),
        ], 330),
        ("\u79ef\u5206\u6392\u884c\u699c", TABLE_POINT_ID, [
            ("rank_no", "\u540d\u6b21", "num"), ("employee_name", "\u59d3\u540d"),
            ("dept", "\u90e8\u95e8"), ("position", "\u804c\u52a1"),
            ("year_point", "\u5f53\u5e74\u79ef\u5206", "num"),
            ("total_point", "\u7d2f\u8ba1\u79ef\u5206", "num"),
            ("dept_rank", "\u90e8\u95e8\u6392\u540d", "num"),
        ], 300),
    ],
    actions=[
        ("\u79ef\u5206\u53d1\u653e", "startone", PROC_POINT_GRANT_ID, False),
        ("\u79ef\u5206\u5151\u6362", "startone", PROC_EXCHANGE_ID, True),
        ("\u60ac\u8d4f\u7533\u8bf7", "startone", PROC_BOUNTY_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

# 第五页：考勤管理 —— 考勤记录 + 请假记录视图
PAGE_ATTEND_HTML = _HRPT.hr_view_page_html(
    "\u8003\u52e4\u7ba1\u7406",
    subtitle="\u8003\u52e3\u4e0e\u8bf7\u5047\u8bb0\u5f55\u5b9e\u65f6\u6570\u636e",
    nav_active=5,
    sections=[
        ("\u8003\u52e4\u8bb0\u5f55", TABLE_ATTEND_ID, [
            ("attend_period", "\u8003\u52e4\u671f\u95f4"), ("employee_name", "\u59d3\u540d"),
            ("dept", "\u90e8\u95e8"), ("should_days", "\u5e94\u51fa\u52e4", "num"),
            ("actual_days", "\u5b9e\u51fa\u52e4", "num"), ("late_count", "\u8fdf\u5230", "num"),
            ("absent_count", "\u65f7\u5de5", "num"),
            ("overtime_hours", "\u52a0\u73ed\u65f6\u957f", "num"),
            ("attend_status", "\u72b6\u6001"),
        ], 330),
        ("\u8bf7\u5047\u8bb0\u5f55", TABLE_LEAVE_ID, [
            ("leave_no", "\u8bf7\u5047\u5355\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("dept", "\u90e8\u95e8"), ("leave_type", "\u5047\u522b"),
            ("leave_days", "\u5929\u6570", "num"),
            ("leave_reason", "\u4e8b\u7531"), ("leave_status", "\u72b6\u6001"),
        ], 300),
    ],
    actions=[
        ("\u8bf7\u5047\u7533\u8bf7", "startone", PROC_LEAVE_ID, False),
        ("\u52a0\u73ed\u7533\u8bf7", "startone", PROC_OVERTIME_ID, True),
        ("\u51fa\u5dee\u7533\u8bf7", "startone", PROC_TRAVEL_ID, True),
        ("\u8003\u52e4\u8865\u767b", "startone", PROC_ATTEND_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

# 第六页：员工自助 —— 我的自助台账 + 请假记录
PAGE_SELF_HTML = _HRPT.hr_view_page_html(
    "\u5458\u5de5\u81ea\u52a9",
    subtitle="\u6211\u7684\u6863\u6848 / \u79ef\u5206 / \u8003\u52e4\u81ea\u52a9\u5165\u53e3",
    nav_active=6,
    sections=[
        ("\u6211\u7684\u81ea\u52a9\u6570\u636e", TABLE_SELF_ID, [
            ("self_no", "\u7533\u8bf7\u5355\u53f7"), ("employee_name", "\u7533\u8bf7\u4eba"),
            ("dept", "\u90e8\u95e8"), ("self_type", "\u7c7b\u578b"),
            ("apply_title", "\u4e8b\u9879"), ("current_step", "\u5f53\u524d\u73af\u8282"),
            ("self_status", "\u72b6\u6001"),
        ], 340),
        ("\u6211\u7684\u8bf7\u5047\u8bb0\u5f55", TABLE_LEAVE_ID, [
            ("leave_no", "\u8bf7\u5047\u5355\u53f7"), ("employee_name", "\u59d3\u540d"),
            ("leave_type", "\u5047\u522b"), ("start_time", "\u5f00\u59cb\u65f6\u95f4", "date"),
            ("end_time", "\u7ed3\u675f\u65f6\u95f4", "date"),
            ("leave_days", "\u5929\u6570", "num"), ("leave_status", "\u72b6\u6001"),
        ], 300),
    ],
    actions=[
        ("\u6211\u8981\u8bf7\u5047", "startone", PROC_LEAVE_ID, False),
        ("\u6211\u8981\u52a0\u73ed", "startone", PROC_OVERTIME_ID, True),
        ("\u6211\u8981\u51fa\u5dee", "startone", PROC_TRAVEL_ID, True),
        ("\u79ef\u5206\u5151\u6362", "startone", PROC_EXCHANGE_ID, True),
    ],
    date_text=PORTAL_DATE_TEXT,
)

def _pg(pid, name, html, desc):
    """独立 HTML 门户页 -> O2OA 门户页数据（表单定义 JSON）。

    O2OA 把门户页当表单渲染（PortalPage.js -> MWF.APPForm），
    裸 HTML 过不了 JSON.decode，门户里直接白屏。
    """
    return portal_page(pid, name, PORTAL_ID,
                       _PT.portal_page_data(html, pid, name, PORTAL_ID,
                                            "人力资源管理门户"),
                       description=desc)


PAGES = [
    _pg(PAGE_HOME_ID, "\u4eba\u529b\u8d44\u6e90\u9996\u9875", PAGE_HOME_HTML, "\u5b98\u65b9\u77e9\u9635\u5f0f\u9996\u9875"),
    _pg(PAGE_EMP_ID, "\u5458\u5de5\u6863\u6848", PAGE_EMP_HTML, "\u5458\u5de5\u6863\u6848\u4e0e\u6863\u6848\u67e5\u8be2"),
    _pg(PAGE_JOB_ID, "\u4eba\u624d\u5e02\u573a", PAGE_JOB_HTML, "\u5c97\u4f4d\u6c60\u4e0e\u7ade\u8058\u62a5\u540d"),
    _pg(PAGE_POINT_ID, "\u79ef\u5206\u7ba1\u7406", PAGE_POINT_HTML, "\u6211\u7684\u79ef\u5206\u4e0e\u6392\u540d\u516c\u793a"),
    _pg(PAGE_ATTEND_ID, "\u8003\u52e4\u7ba1\u7406", PAGE_ATTEND_HTML, "\u8003\u52e4\u6708\u5386\u4e0e\u7edf\u8ba1"),
    _pg(PAGE_SELF_ID, "\u5458\u5de5\u81ea\u52a9", PAGE_SELF_HTML, "\u5458\u5de5\u81ea\u52a9\u4e00\u7ad9\u5f0f\u5165\u53e3"),
    _pg(PAGE_CHG_ID, "\u5458\u5de5\u7ba1\u7406", PAGE_CHG_HTML, "\u5165\u804c/\u8f6c\u6b63/\u8c03\u52a8/\u79bb\u804c\u529e\u7406"),
]

PORTAL = portal(
    PORTAL_ID, "\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u95e8\u6237",
    category="\u7efc\u5408\u7ba1\u7406",
    description="\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u5e94\u7528\u95e8\u6237"
                "\uff08\u5bf9\u9f50 O2OA \u5b98\u65b9\u4eba\u529b\u8d44\u6e90\u7cfb\u7edf\u7248\u5f0f\uff09",
    first_page_id=PAGE_HOME_ID,
    pages=PAGES,
)

PORTALS = [PORTAL]

__all__ = [
    "APP_NAME", "APP_ID", "APP_ID_QUERY",
    "FORMS", "PROCESSES", "VIEWS", "STATS", "TABLES", "STATEMENTS",
    "PORTALS", "PORTAL_TREE",
]
