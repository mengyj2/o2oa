# -*- coding: utf-8 -*-
"""
应用一：项目管理应用
====================
对标"项目管理系统"，覆盖：
    项目前期管理（项目基础信息、立项审核）
    项目策划管理（WBS与计划）
    项目实施监控（任务看板、进度/风险/评审）
    资源与财务管理（资金管理、物资管理、成本核算）
    收尾与档案管理（项目档案）
    数据分析与考核（对标考核）

全部流程的公共关联字段：project_no（项目编号）
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, dictionary,
)

APP_NAME = "\u9879\u76ee\u7ba1\u7406\u5e94\u7528"
APP_ID = "a1001000-project-app-000000000000001"
APP_ID_QUERY = "a1001001-project-dataapp-0000000000001"

# ==========================================================================
# 表单定义
# ==========================================================================

FORM_PROJECT_ID = "f1001001-project-base-form-00000000001"

PROJECT_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True,
          readonly=True, description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210\uff0c\u5168\u5c40\u552f\u4e00"),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", required=True),
    Field("project_type", "\u9879\u76ee\u7c7b\u522b", "dict",
          code="projectType", required=True),
    Field("project_status", "\u9879\u76ee\u72b6\u6001", "dict",
          code="projectStatus", readonly=True, default="\u7b56\u5212\u4e2d"),
    Field("project_level", "\u9879\u76ee\u7ea7\u522b", "select",
          options=["A级（重大）", "B级（重点）", "C级（常规）"]),
    Field("project_source", "\u8d44\u91d1\u6765\u6e90", "dict",
          code="fundSource"),
    Field("dept_name", "\u4e3b\u529e\u90e8\u95e8", "org"),
    Field("manager", "\u9879\u76ee\u8d1f\u8d23\u4eba", "org", required=True),
    Field("team_members", "\u9879\u76ee\u6210\u5458", "org", colspan=4),
    Field("start_date", "\u8ba1\u5212\u5f00\u59cb\u65e5\u671f", "calendar"),
    Field("end_date", "\u8ba1\u5212\u7ed3\u675f\u65e5\u671f", "calendar"),
    Field("total_budget", "\u9879\u76ee\u603b\u9884\u7b97\uff08\u5143\uff09", "currency",
          description="\u4e0e\u9884\u7b97\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
    Field("fund_source_detail", "\u8d44\u91d1\u6765\u6e90\u8bf4\u660e", "textarea"),
    Field("project_goal", "\u9879\u76ee\u76ee\u6807", "textarea", required=True),
    Field("project_scope", "\u9879\u76ee\u8303\u56f4", "textarea"),
    Field("deliverables", "\u4e3b\u8981\u4ea4\u4ed8\u7269", "textarea"),
    Field("risk_desc", "\u98ce\u9669\u5206\u6790", "textarea"),
]

FORM_PROJECT = FormBuilder(
    FORM_PROJECT_ID, "\u9879\u76ee\u57fa\u7840\u4fe1\u606f\u8868",
    "\u9879\u76ee\u57fa\u7840\u4fe1\u606f\u767b\u8bb0\u4e0e\u7acb\u9879\u4f9d\u636e",
    fields=PROJECT_FIELDS,
)

FORM_APPROVE_ID = "f1001002-project-approve-form-0000000001"

APPROVE_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True, readonly=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", required=True, readonly=True),
    Field("apply_dept", "\u7533\u62a5\u90e8\u95e8", "org"),
    Field("apply_person", "\u7533\u62a5\u4eba", "org"),
    Field("apply_date", "\u7533\u62a5\u65e5\u671f", "calendar"),
    Field("feasibility", "\u53ef\u884c\u6027\u8bba\u8bc1\u610f\u89c1", "textarea", required=True),
    Field("budget_estimate", "\u4f30\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency"),
    Field("approve_result", "\u5ba1\u6838\u7ed3\u8bba", "radio",
          options=["同意立项", "不同意立项", "修改后重新申报"]),
    Field("approve_opinion", "\u5ba1\u6838\u610f\u89c1", "textarea"),
    Field("approved_budget", "\u6838\u5b9a\u9884\u7b97\uff08\u5143\uff09", "currency"),
]

FORM_APPROVE = FormBuilder(
    FORM_APPROVE_ID, "\u9879\u76ee\u7acb\u9879\u5ba1\u6838\u8868",
    "\u9879\u76ee\u7acb\u9879\u7533\u62a5\u4e0e\u5ba1\u6279",
    fields=APPROVE_FIELDS,
)

FORM_WBS_ID = "f1001003-project-wbs-form-000000000001"

WBS_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("plan_name", "\u8ba1\u5212\u540d\u79f0", "textfield", required=True),
    Field("plan_version", "\u8ba1\u5212\u7248\u672c", "textfield", default="V1.0"),
    Field("compile_person", "\u7f16\u5236\u4eba", "org"),
    Field("compile_date", "\u7f16\u5236\u65e5\u671f", "calendar"),
    Field("plan_desc", "\u8ba1\u5212\u8bf4\u660e", "textarea"),
]

WBS_DATAGRID = {
    "id": "dg_wbs",
    "name": "WBS\u4efb\u52a1\u62c6\u89e3\u660e\u7ec6",
    "isTotal": False,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("task_no", "\u4efb\u52a1\u7f16\u53f7", "textfield", description="110px"),
        Field("task_name", "\u4efb\u52a1\u540d\u79f0", "textfield", description="200px"),
        Field("task_type", "\u4efb\u52a1\u7c7b\u578b", "select",
              options=["阶段", "任务", "子任务", "里程碑"], description="100px"),
        Field("owner", "\u8d1f\u8d23\u4eba", "org", description="120px"),
        Field("start_date", "\u5f00\u59cb\u65e5\u671f", "calendar", description="110px"),
        Field("end_date", "\u7ed3\u675f\u65e5\u671f", "calendar", description="110px"),
        Field("duration", "\u5de5\u671f\uff08\u5929\uff09", "number", description="90px"),
        Field("pre_task", "\u524d\u7f6e\u4efb\u52a1", "textfield", description="110px"),
        Field("progress", "\u5b8c\u6210\u5ea6\uff08%\uff09", "number", description="90px"),
        Field("remark", "\u5907\u6ce8", "textfield", description="140px"),
    ],
}

FORM_WBS = FormBuilder(
    FORM_WBS_ID, "WBS\u4e0e\u8ba1\u5212\u8868",
    "\u9879\u76eeWBS\u4efb\u52a1\u62c6\u89e3\u4e0e\u8ba1\u5212\u7f16\u5236",
    fields=WBS_FIELDS,
    datagrids=[WBS_DATAGRID],
)

FORM_PROGRESS_ID = "f1001004-project-progress-form-00000001"

PROGRESS_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("report_period", "\u62a5\u544a\u671f\u95f4", "textfield", required=True),
    Field("report_type", "\u62a5\u544a\u7c7b\u578b", "select",
          options=["月报", "季报", "年报", "里程碑报告", "专题报告"]),
    Field("overall_progress", "\u6574\u4f53\u5b8c\u6210\u5ea6\uff08%\uff09", "number"),
    Field("plan_progress", "\u8ba1\u5212\u5b8c\u6210\u5ea6\uff08%\uff09", "number"),
    Field("current_status", "\u5f53\u524d\u72b6\u6001", "dict", code="projectStatus"),
    Field("progress_desc", "\u8fdb\u5c55\u60c5\u51b5\u8bf4\u660e", "textarea", required=True),
    Field("risk_level", "\u98ce\u9669\u7b49\u7ea7", "radio",
          options=["无风险", "低风险", "中风险", "高风险"]),
    Field("risk_desc", "\u98ce\u9669\u63cf\u8ff0", "textarea"),
    Field("risk_measure", "\u5e94\u5bf9\u63aa\u65bd", "textarea"),
    Field("next_plan", "\u4e0b\u9636\u6bb5\u8ba1\u5212", "textarea"),
    Field("support_needed", "\u9700\u534f\u8c03\u4e8b\u9879", "textarea"),
    Field("audit_opinion", "\u5ba1\u6838\u610f\u89c1", "textarea"),
]

FORM_PROGRESS = FormBuilder(
    FORM_PROGRESS_ID, "\u9879\u76ee\u8fdb\u5ea6\u98ce\u9669\u8bc4\u5ba1\u8868",
    "\u9879\u76ee\u8fdb\u5ea6\u62a5\u544a\u3001\u98ce\u9669\u8bc4\u4f30\u4e0e\u5ba1\u6838",
    fields=PROGRESS_FIELDS,
)

FORM_FUND_ID = "f1001005-project-fund-form-0000000000001"

FUND_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("fund_no", "\u8d44\u91d1\u5355\u53f7", "textfield", readonly=True),
    Field("fund_type", "\u4e1a\u52a1\u7c7b\u578b", "select",
          options=["资金申请", "资金拨付", "资金调整", "资金结算"]),
    Field("apply_amount", "\u7533\u8bf7\u91d1\u989d\uff08\u5143\uff09", "currency", required=True),
    Field("approved_amount", "\u6279\u51c6\u91d1\u989d\uff08\u5143\uff09", "currency"),
    Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield",
          description="\u4e0e\u9884\u7b97\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
    Field("fund_source", "\u8d44\u91d1\u6765\u6e90", "dict", code="fundSource"),
    Field("use_desc", "\u8d44\u91d1\u7528\u9014", "textarea", required=True),
    Field("payee_name", "\u6536\u6b3e\u5355\u4f4d", "textfield"),
    Field("payee_account", "\u6536\u6b3e\u8d26\u53f7", "textfield"),
    Field("pay_date", "\u62df\u62e8\u4ed8\u65e5\u671f", "calendar"),
]

FORM_FUND = FormBuilder(
    FORM_FUND_ID, "\u9879\u76ee\u8d44\u91d1\u7ba1\u7406\u8868",
    "\u9879\u76ee\u8d44\u91d1\u7533\u8bf7\u3001\u62e8\u4ed8\u4e0e\u7ed3\u7b97",
    fields=FUND_FIELDS,
)

FORM_MATERIAL_ID = "f1001006-project-material-form-000000001"

MATERIAL_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("material_type", "\u7533\u8bf7\u7c7b\u578b", "select",
          options=["物资采购", "物资领用", "物资归还", "物资报废"]),
    Field("applicant", "\u7533\u8bf7\u4eba", "org"),
    Field("apply_date", "\u7533\u8bf7\u65e5\u671f", "calendar"),
    Field("use_purpose", "\u7528\u9014\u8bf4\u660e", "textarea", required=True),
    Field("receiver", "\u9886\u7528\u4eba", "org"),
    Field("receive_date", "\u9886\u7528\u65e5\u671f", "calendar"),
]

MATERIAL_DATAGRID = {
    "id": "dg_material",
    "name": "\u7269\u8d44\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("material_name", "\u7269\u8d44\u540d\u79f0", "textfield", description="180px"),
        Field("spec", "\u89c4\u683c\u578b\u53f7", "textfield", description="140px"),
        Field("unit", "\u8ba1\u91cf\u5355\u4f4d", "textfield", description="80px"),
        Field("quantity", "\u6570\u91cf", "number", description="80px"),
        Field("unit_price", "\u5355\u4ef7\uff08\u5143\uff09", "currency", description="110px"),
        Field("amount", "\u91d1\u989d\uff08\u5143\uff09", "currency", description="120px"),
        Field("remark", "\u5907\u6ce8", "textfield", description="140px"),
    ],
}

FORM_MATERIAL = FormBuilder(
    FORM_MATERIAL_ID, "\u9879\u76ee\u7269\u8d44\u7ba1\u7406\u8868",
    "\u9879\u76ee\u7269\u8d44\u91c7\u8d2d\u3001\u9886\u7528\u4e0e\u7ba1\u7406",
    fields=MATERIAL_FIELDS,
    datagrids=[MATERIAL_DATAGRID],
)

FORM_COST_ID = "f1001007-project-cost-form-0000000000001"

COST_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("cost_period", "\u6838\u7b97\u671f\u95f4", "textfield", required=True),
    Field("budget_total", "\u9884\u7b97\u603b\u989d\uff08\u5143\uff09", "currency", readonly=True),
    Field("actual_total", "\u5b9e\u9645\u6210\u672c\uff08\u5143\uff09", "currency", readonly=True),
    Field("variance", "\u504f\u5dee\uff08\u5143\uff09", "currency", readonly=True),
    Field("variance_rate", "\u504f\u5dee\u7387\uff08%\uff09", "number", readonly=True),
    Field("cost_analysis", "\u6210\u672c\u5206\u6790", "textarea", required=True),
    Field("control_measure", "\u63a7\u5236\u63aa\u65bd", "textarea"),
]

COST_DATAGRID = {
    "id": "dg_cost",
    "name": "\u6210\u672c\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("cost_item", "\u6210\u672c\u9879\u76ee", "textfield", description="180px"),
        Field("expense_type", "\u8d39\u7528\u7c7b\u578b", "select",
              options=["差旅费", "会议费", "办公费", "材料费", "设备费",
                       "劳务费", "咨询费", "测试化验费", "委托业务费", "其他费用"],
              description="120px"),
        Field("budget_amount", "\u9884\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency", description="120px"),
        Field("actual_amount", "\u5b9e\u9645\u91d1\u989d\uff08\u5143\uff09", "currency", description="120px"),
        Field("variance", "\u504f\u5dee\uff08\u5143\uff09", "currency", description="110px"),
        Field("remark", "\u5907\u6ce8", "textfield", description="140px"),
    ],
}

FORM_COST = FormBuilder(
    FORM_COST_ID, "\u9879\u76ee\u6210\u672c\u6838\u7b97\u8868",
    "\u9879\u76ee\u6210\u672c\u5f52\u96c6\u3001\u6838\u7b97\u4e0e\u504f\u5dee\u5206\u6790",
    fields=COST_FIELDS,
    datagrids=[COST_DATAGRID],
)

FORM_CLOSE_ID = "f1001008-project-close-form-0000000000001"

CLOSE_FIELDS = [
    Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
    Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("actual_start", "\u5b9e\u9645\u5f00\u59cb\u65e5\u671f", "calendar"),
    Field("actual_end", "\u5b9e\u9645\u7ed3\u675f\u65e5\u671f", "calendar"),
    Field("final_budget", "\u7ed3\u9879\u603b\u9884\u7b97\uff08\u5143\uff09", "currency"),
    Field("final_cost", "\u7ed3\u9879\u603b\u6210\u672c\uff08\u5143\uff09", "currency"),
    Field("final_result", "\u6210\u679c\u603b\u7ed3", "textarea", required=True),
    Field("achievement", "\u4e3b\u8981\u6210\u679c\u4e0e\u4ea7\u51fa", "textarea"),
    Field("close_reason", "\u7ed3\u9879\u539f\u56e0", "select",
          options=["正常结项", "提前结项", "延期结项", "终止结项"]),
    Field("archive_flag", "\u662f\u5426\u5f52\u6863", "radio", options=["是", "否"], default="是"),
    Field("archive_no", "\u5f52\u6863\u6863\u6848\u53f7", "textfield",
          description="\u4e0e\u6863\u6848\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
]

FORM_CLOSE = FormBuilder(
    FORM_CLOSE_ID, "\u9879\u76ee\u7ed3\u9879\u7533\u8bf7\u8868",
    "\u9879\u76ee\u6536\u5c3e\u3001\u7ed3\u9879\u4e0e\u6863\u6848\u5f52\u96c6",
    fields=CLOSE_FIELDS,
)

FORM_CHANGE_ID = "f1001009-project-change-form-0000000001"

FORM_CHANGE = FormBuilder(
    FORM_CHANGE_ID, "\u9879\u76ee\u53d8\u66f4\u7533\u8bf7\u8868",
    "\u9879\u76ee\u8303\u56f4\u3001\u8fdb\u5ea6\u3001\u9884\u7b97\u7b49\u53d8\u66f4\u5ba1\u6279",
    fields=[
        Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
        Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
        Field("change_type", "\u53d8\u66f4\u7c7b\u578b", "checkbox",
              options=["范围变更", "进度变更", "预算变更", "人员变更", "技术方案变更"]),
        Field("change_before", "\u53d8\u66f4\u524d\u5185\u5bb9", "textarea", required=True),
        Field("change_after", "\u53d8\u66f4\u540e\u5185\u5bb9", "textarea", required=True),
        Field("change_reason", "\u53d8\u66f4\u539f\u56e0", "textarea", required=True),
        Field("budget_impact", "\u9884\u7b97\u5f71\u54cd\uff08\u5143\uff09", "currency"),
        Field("schedule_impact", "\u8fdb\u5ea6\u5f71\u54cd\uff08\u5929\uff09", "number"),
    ],
)

FORM_TASK_ID = "f1001010-project-task-form-0000000000001"

FORM_TASK = FormBuilder(
    FORM_TASK_ID, "\u9879\u76ee\u4efb\u52a1\u5206\u6d3e\u5355",
    "\u9879\u76ee\u65e5\u5e38\u4efb\u52a1\u5206\u6d3e\u3001\u53cd\u9988\u4e0e\u786e\u8ba4",
    fields=[
        Field("project_no", "\u9879\u76ee\u7f16\u53f7", "textfield", required=True),
        Field("project_name", "\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
        Field("task_name", "\u4efb\u52a1\u540d\u79f0", "textfield", required=True),
        Field("task_type", "\u4efb\u52a1\u7c7b\u578b", "select",
              options=["常规任务", "紧急任务", "里程碑任务"]),
        Field("assignee", "\u627f\u529e\u4eba", "org", required=True),
        Field("plan_start", "\u8ba1\u5212\u5f00\u59cb", "calendar"),
        Field("plan_end", "\u8ba1\u5212\u5b8c\u6210", "calendar"),
        Field("task_desc", "\u4efb\u52a1\u63cf\u8ff0", "textarea", required=True),
        Field("task_priority", "\u4f18\u5148\u7ea7", "radio",
              options=["紧急", "高", "中", "低"]),
        Field("feedback", "\u5b8c\u6210\u60c5\u51b5\u53cd\u9988", "textarea"),
        Field("complete_rate", "\u5b8c\u6210\u5ea6\uff08%\uff09", "number"),
    ],
)


# ==========================================================================
# 处理人脚本
# ==========================================================================

from o2oa_org import *  # noqa: F401,F403

# 表单数据派生的处理人（非组织架构，保留在应用内）
SCRIPT_PROJECT_MGR = "return this.data.manager;"


# ==========================================================================
# 流程定义
# ==========================================================================
# 说明：Activity 采用「处理人脚本 + 环节表单」模型：
#   task_script       —— 处理人脚本（返回身份 DN）
#   form_id           —— 本环节显示的表单
#   allow_go_back / allow_rollback / allow_terminate / allow_reset —— 环节控制开关
# routes 为显式边列表 [(from, to, 路由名, 路由条件脚本)]


def _flow(pid, name, desc, form_id, steps, routes):
    """
    steps: [(节点id, 节点名, 类型, 处理人脚本, 表单id覆盖)]
    类型: manual / end / choice
    """
    acts = []
    for s in steps:
        sid, sname, stype = s[0], s[1], s[2]
        script = s[3] if len(s) > 3 else ""
        sform = s[4] if len(s) > 4 else form_id
        acts.append(Activity(
            sid, sname, atype=stype,
            task_script=script if stype == "manual" else "",
            form_id=sform if stype == "manual" else "",
        ))
    return ProcessBuilder(pid, name, desc, form_id=form_id,
                          activities=acts, routes=routes)


PROC_APPROVE_ID = "p1001001-project-approve-0000000000001"

PROC_APPROVE = _flow(
    PROC_APPROVE_ID,
    "\u9879\u76ee\u7acb\u9879\u5ba1\u6279\u6d41\u7a0b",
    "\u9879\u76ee\u4ece\u7533\u62a5\u5230\u6b63\u5f0f\u7acb\u9879\u7684\u5ba1\u6279\u8fc7\u7a0b",
    FORM_APPROVE_ID,
    [
        ("a_draft", "\u9879\u76ee\u7533\u62a5", "manual", SCRIPT_SELF, FORM_PROJECT_ID),
        ("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", SCRIPT_DEPT_LEADER),
        ("a_expert", "\u4e13\u5bb6\u8bc4\u5ba1", "manual", SCRIPT_LEADER),
        ("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", SCRIPT_LEADER),
        ("a_archive", "\u9879\u76ee\u6863\u6848\u5f52\u96c6", "manual", SCRIPT_ARCHIVE),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_dept", "\u63d0\u4ea4\u5ba1\u6838", ""),
        ("a_dept", "a_expert", "\u540c\u610f", ""),
        ("a_dept", "a_draft", "\u9000\u56de\u4fee\u6539", ""),
        ("a_expert", "a_leader", "\u540c\u610f\u7acb\u9879", ""),
        ("a_expert", "a_draft", "\u4e0d\u540c\u610f", ""),
        ("a_leader", "a_archive", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u9a73\u56de", ""),
        ("a_archive", "a_end", "\u5f52\u6863\u5b8c\u6210", ""),
    ],
)

PROC_PROGRESS_ID = "p1001002-project-progress-0000000000001"

PROC_PROGRESS = _flow(
    PROC_PROGRESS_ID,
    "\u9879\u76ee\u8fdb\u5ea6\u98ce\u9669\u8bc4\u5ba1\u6d41\u7a0b",
    "\u9879\u76ee\u8fdb\u5ea6\u62a5\u544a\u4e0e\u98ce\u9669\u8bc4\u5ba1",
    FORM_PROGRESS_ID,
    [
        ("a_draft", "\u8fdb\u5ea6\u586b\u62a5", "manual", SCRIPT_SELF),
        ("a_pm", "\u9879\u76ee\u7ecf\u7406\u5ba1\u6838", "manual", SCRIPT_PROJECT_MGR),
        ("a_dept", "\u4e3b\u7ba1\u90e8\u95e8\u5ba1\u6279", "manual", SCRIPT_DEPT_LEADER),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_dept", "\u901a\u8fc7", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_dept", "a_end", "\u5ba1\u6279\u901a\u8fc7", ""),
    ],
)

PROC_FUND_ID = "p1001003-project-fund-0000000000000001"

PROC_FUND = _flow(
    PROC_FUND_ID,
    "\u9879\u76ee\u8d44\u91d1\u62e8\u4ed8\u5ba1\u6279\u6d41\u7a0b",
    "\u9879\u76ee\u8d44\u91d1\u7533\u8bf7\u4e0e\u62e8\u4ed8\u5ba1\u6279",
    FORM_FUND_ID,
    [
        ("a_draft", "\u8d44\u91d1\u7533\u8bf7", "manual", SCRIPT_SELF),
        ("a_pm", "\u9879\u76ee\u7ecf\u7406\u5ba1\u6838", "manual", SCRIPT_PROJECT_MGR),
        ("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", SCRIPT_FINANCE),
        ("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", SCRIPT_LEADER),
        ("a_pay", "\u8d22\u52a1\u62e8\u4ed8", "manual", SCRIPT_FINANCE),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_finance", "\u901a\u8fc7", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_draft", "\u9a73\u56de", ""),
        ("a_leader", "a_pay", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_pay", "a_end", "\u62e8\u4ed8\u5b8c\u6210", ""),
    ],
)

PROC_MATERIAL_ID = "p1001004-project-material-000000000001"

PROC_MATERIAL = _flow(
    PROC_MATERIAL_ID,
    "\u9879\u76ee\u7269\u8d44\u7533\u8bf7\u5ba1\u6279\u6d41\u7a0b",
    "\u9879\u76ee\u7269\u8d44\u91c7\u8d2d\u3001\u9886\u7528\u4e0e\u5f52\u8fd8\u5ba1\u6279",
    FORM_MATERIAL_ID,
    [
        ("a_draft", "\u7269\u8d44\u7533\u8bf7", "manual", SCRIPT_SELF),
        ("a_pm", "\u9879\u76ee\u7ecf\u7406\u5ba1\u6838", "manual", SCRIPT_PROJECT_MGR),
        ("a_dept", "\u90e8\u95e8\u5ba1\u6279", "manual", SCRIPT_DEPT_LEADER),
        ("a_stock", "\u5e93\u7ba1\u767b\u8bb0", "manual", SCRIPT_ARCHIVE),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_dept", "\u901a\u8fc7", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_dept", "a_stock", "\u6279\u51c6", ""),
        ("a_dept", "a_draft", "\u9a73\u56de", ""),
        ("a_stock", "a_end", "\u767b\u8bb0\u5b8c\u6210", ""),
    ],
)

PROC_CLOSE_ID = "p1001005-project-close-000000000000001"

PROC_CLOSE = _flow(
    PROC_CLOSE_ID,
    "\u9879\u76ee\u7ed3\u9879\u5ba1\u6279\u6d41\u7a0b",
    "\u9879\u76ee\u6536\u5c3e\u3001\u7ed3\u9879\u4e0e\u6863\u6848\u5f52\u96c6\u5ba1\u6279",
    FORM_CLOSE_ID,
    [
        ("a_draft", "\u7ed3\u9879\u7533\u8bf7", "manual", SCRIPT_SELF),
        ("a_pm", "\u9879\u76ee\u7ecf\u7406\u786e\u8ba4", "manual", SCRIPT_PROJECT_MGR),
        ("a_finance", "\u8d22\u52a1\u7ed3\u7b97", "manual", SCRIPT_FINANCE),
        ("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", SCRIPT_LEADER),
        ("a_archive", "\u6863\u6848\u5f52\u96c6", "manual", SCRIPT_ARCHIVE),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_finance", "\u786e\u8ba4", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_finance", "a_leader", "\u7ed3\u7b97\u5b8c\u6210", ""),
        ("a_leader", "a_archive", "\u6279\u51c6\u7ed3\u9879", ""),
        ("a_leader", "a_draft", "\u9a73\u56de", ""),
        ("a_archive", "a_end", "\u5f52\u6863\u5b8c\u6210", ""),
    ],
)

PROC_CHANGE_ID = "p1001006-project-change-00000000000001"

PROC_CHANGE = _flow(
    PROC_CHANGE_ID,
    "\u9879\u76ee\u53d8\u66f4\u5ba1\u6279\u6d41\u7a0b",
    "\u9879\u76ee\u91cd\u5927\u53d8\u66f4\u7684\u7533\u62a5\u4e0e\u5ba1\u6279",
    FORM_CHANGE_ID,
    [
        ("a_draft", "\u53d8\u66f4\u7533\u8bf7", "manual", SCRIPT_SELF),
        ("a_pm", "\u9879\u76ee\u7ecf\u7406\u5ba1\u6838", "manual", SCRIPT_PROJECT_MGR),
        ("a_dept", "\u4e3b\u7ba1\u90e8\u95e8\u5ba1\u6279", "manual", SCRIPT_DEPT_LEADER),
        ("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", SCRIPT_LEADER),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_dept", "\u901a\u8fc7", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_dept", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_leader", "a_end", "\u6279\u51c6", ""),
    ],
)

PROC_TASK_ID = "p1001007-project-task-000000000000001"

PROC_TASK = _flow(
    PROC_TASK_ID,
    "\u9879\u76ee\u4efb\u52a1\u5206\u6d3e\u6d41\u7a0b",
    "\u9879\u76ee\u4efb\u52a1\u5206\u6d3e\u4e0e\u53cd\u9988\u786e\u8ba4",
    FORM_TASK_ID,
    [
        ("a_draft", "\u4efb\u52a1\u5206\u6d3e", "manual", SCRIPT_PROJECT_MGR),
        ("a_do", "\u4efb\u52a1\u627f\u529e", "manual", "return this.data.assignee;"),
        ("a_confirm", "\u4efb\u52a1\u786e\u8ba4", "manual", SCRIPT_PROJECT_MGR),
        ("a_end", "\u7ed3\u675f", "end"),
    ],
    [
        ("a_draft", "a_do", "\u6d3e\u53d1", ""),
        ("a_do", "a_confirm", "\u63d0\u4ea4\u6210\u679c", ""),
        ("a_confirm", "a_do", "\u9000\u56de\u4fee\u6539", ""),
        ("a_confirm", "a_end", "\u786e\u8ba4\u5b8c\u6210", ""),
    ],
)


# ==========================================================================
# 数据中心：视图
# ==========================================================================

VIEW_PROJECT_LIST_ID = "v1001001-project-list-view-00000000001"
VIEW_APPROVE_LIST_ID = "v1001002-project-approve-view-0000000001"
VIEW_PROGRESS_LIST_ID = "v1001003-project-progress-view-000000001"
VIEW_FUND_LIST_ID = "v1001004-project-fund-view-0000000000001"
VIEW_COST_LIST_ID = "v1001005-project-cost-view-0000000000001"
VIEW_MATERIAL_LIST_ID = "v1001006-project-material-view-000000001"
VIEW_CLOSE_LIST_ID = "v1001007-project-close-view-000000000001"
VIEW_TASK_LIST_ID = "v1001008-project-task-view-0000000000001"

VIEWS = [
    view(VIEW_PROJECT_LIST_ID, "\u9879\u76ee\u53f0\u8d26\u89c6\u56fe",
         "\u5168\u91cf\u9879\u76ee\u57fa\u7840\u4fe1\u606f\u5217\u8868",
         source="process", process_list=[PROC_APPROVE_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "220px"),
             ("\u9879\u76ee\u7c7b\u522b", "project_type", "120px"),
             ("\u9879\u76ee\u72b6\u6001", "project_status", "100px"),
             ("\u8d44\u91d1\u6765\u6e90", "project_source", "110px"),
             ("\u4e3b\u529e\u90e8\u95e8", "dept_name", "150px"),
             ("\u9879\u76ee\u8d1f\u8d23\u4eba", "manager", "110px"),
             ("\u5f00\u59cb\u65e5\u671f", "start_date", "110px"),
             ("\u7ed3\u675f\u65e5\u671f", "end_date", "110px"),
             ("\u603b\u9884\u7b97", "total_budget", "120px"),
         ]),
    view(VIEW_APPROVE_LIST_ID, "\u7acb\u9879\u5ba1\u6279\u53f0\u8d26",
         "\u9879\u76ee\u7acb\u9879\u5ba1\u6279\u8fc7\u7a0b\u8bb0\u5f55",
         source="process", process_list=[PROC_APPROVE_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "220px"),
             ("\u7533\u62a5\u90e8\u95e8", "apply_dept", "150px"),
             ("\u7533\u62a5\u4eba", "apply_person", "110px"),
             ("\u7533\u62a5\u65e5\u671f", "apply_date", "110px"),
             ("\u4f30\u7b97\u91d1\u989d", "budget_estimate", "120px"),
             ("\u5ba1\u6838\u7ed3\u8bba", "approve_result", "120px"),
             ("\u6838\u5b9a\u9884\u7b97", "approved_budget", "120px"),
         ]),
    view(VIEW_PROGRESS_LIST_ID, "\u8fdb\u5ea6\u98ce\u9669\u53f0\u8d26",
         "\u9879\u76ee\u8fdb\u5ea6\u4e0e\u98ce\u9669\u62a5\u544a\u8bb0\u5f55",
         source="process", process_list=[PROC_PROGRESS_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "200px"),
             ("\u62a5\u544a\u671f\u95f4", "report_period", "110px"),
             ("\u62a5\u544a\u7c7b\u578b", "report_type", "110px"),
             ("\u8ba1\u5212\u5b8c\u6210\u5ea6", "plan_progress", "110px"),
             ("\u6574\u4f53\u5b8c\u6210\u5ea6", "overall_progress", "110px"),
             ("\u98ce\u9669\u7b49\u7ea7", "risk_level", "100px"),
             ("\u5f53\u524d\u72b6\u6001", "current_status", "100px"),
         ]),
    view(VIEW_FUND_LIST_ID, "\u8d44\u91d1\u53f0\u8d26",
         "\u9879\u76ee\u8d44\u91d1\u7533\u8bf7\u4e0e\u62e8\u4ed8\u8bb0\u5f55",
         source="process", process_list=[PROC_FUND_ID],
         columns=[
             ("\u8d44\u91d1\u5355\u53f7", "fund_no", "130px"),
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "200px"),
             ("\u4e1a\u52a1\u7c7b\u578b", "fund_type", "110px"),
             ("\u7533\u8bf7\u91d1\u989d", "apply_amount", "120px"),
             ("\u6279\u51c6\u91d1\u989d", "approved_amount", "120px"),
             ("\u5173\u8054\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u62df\u62e8\u4ed8\u65e5\u671f", "pay_date", "110px"),
         ]),
    view(VIEW_COST_LIST_ID, "\u6210\u672c\u6838\u7b97\u53f0\u8d26",
         "\u9879\u76ee\u6210\u672c\u6838\u7b97\u4e0e\u504f\u5dee\u8bb0\u5f55",
         source="process", process_list=[PROC_CLOSE_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "200px"),
             ("\u6838\u7b97\u671f\u95f4", "cost_period", "110px"),
             ("\u9884\u7b97\u603b\u989d", "budget_total", "120px"),
             ("\u5b9e\u9645\u6210\u672c", "actual_total", "120px"),
             ("\u504f\u5dee", "variance", "110px"),
             ("\u504f\u5dee\u7387", "variance_rate", "100px"),
         ]),
    view(VIEW_MATERIAL_LIST_ID, "\u7269\u8d44\u53f0\u8d26",
         "\u9879\u76ee\u7269\u8d44\u91c7\u8d2d\u4e0e\u9886\u7528\u8bb0\u5f55",
         source="process", process_list=[PROC_MATERIAL_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u7533\u8bf7\u7c7b\u578b", "material_type", "110px"),
             ("\u7533\u8bf7\u4eba", "applicant", "110px"),
             ("\u7533\u8bf7\u65e5\u671f", "apply_date", "110px"),
             ("\u9886\u7528\u4eba", "receiver", "110px"),
             ("\u9886\u7528\u65e5\u671f", "receive_date", "110px"),
         ]),
    view(VIEW_CLOSE_LIST_ID, "\u7ed3\u9879\u53f0\u8d26",
         "\u9879\u76ee\u7ed3\u9879\u4e0e\u5f52\u6863\u8bb0\u5f55",
         source="process", process_list=[PROC_CLOSE_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9879\u76ee\u540d\u79f0", "project_name", "200px"),
             ("\u5b9e\u9645\u5f00\u59cb", "actual_start", "110px"),
             ("\u5b9e\u9645\u7ed3\u675f", "actual_end", "110px"),
             ("\u7ed3\u9879\u603b\u6210\u672c", "final_cost", "120px"),
             ("\u7ed3\u9879\u539f\u56e0", "close_reason", "110px"),
             ("\u5f52\u6863\u6863\u6848\u53f7", "archive_no", "130px"),
         ]),
    view(VIEW_TASK_LIST_ID, "\u4efb\u52a1\u53f0\u8d26",
         "\u9879\u76ee\u4efb\u52a1\u5206\u6d3e\u4e0e\u5b8c\u6210\u60c5\u51b5",
         source="process", process_list=[PROC_TASK_ID],
         columns=[
             ("\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u4efb\u52a1\u540d\u79f0", "task_name", "200px"),
             ("\u4efb\u52a1\u7c7b\u578b", "task_type", "110px"),
             ("\u627f\u529e\u4eba", "assignee", "110px"),
             ("\u8ba1\u5212\u5f00\u59cb", "plan_start", "110px"),
             ("\u8ba1\u5212\u5b8c\u6210", "plan_end", "110px"),
             ("\u4f18\u5148\u7ea7", "task_priority", "90px"),
             ("\u5b8c\u6210\u5ea6", "complete_rate", "90px"),
         ]),
]


# ==========================================================================
# 数据中心：自建表（跨应用共享的主数据落地表）
# ==========================================================================

TABLE_PROJECT_MASTER_ID = "t1001001-project-master-table-00000001"
TABLE_PROJECT_MEMBER_ID = "t1001002-project-member-table-00000001"
TABLE_PROJECT_MILESTONE_ID = "t1001003-project-milestone-table-00001"

TABLES = [
    table(TABLE_PROJECT_MASTER_ID, "\u9879\u76ee\u4e3b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("project_no", "string", "\u9879\u76ee\u7f16\u53f7", 64),
              ("project_name", "string", "\u9879\u76ee\u540d\u79f0", 255),
              ("project_type", "string", "\u9879\u76ee\u7c7b\u522b", 64),
              ("project_status", "string", "\u9879\u76ee\u72b6\u6001", 32),
              ("project_level", "string", "\u9879\u76ee\u7ea7\u522b", 32),
              ("dept_name", "string", "\u4e3b\u529e\u90e8\u95e8", 255),
              ("manager", "string", "\u9879\u76ee\u8d1f\u8d23\u4eba", 255),
              ("start_date", "date", "\u8ba1\u5212\u5f00\u59cb\u65e5\u671f", 0),
              ("end_date", "date", "\u8ba1\u5212\u7ed3\u675f\u65e5\u671f", 0),
              ("total_budget", "number", "\u603b\u9884\u7b97\uff08\u5143\uff09", 0),
              ("fund_source", "string", "\u8d44\u91d1\u6765\u6e90", 64),
              ("project_goal", "text", "\u9879\u76ee\u76ee\u6807", 0),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
              ("contract_no", "string", "\u5173\u8054\u5408\u540c\u7f16\u53f7", 64),
              ("budget_no", "string", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", 64),
              ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 0),
              ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 0),
          ],
          "\u9879\u76ee\u4e3b\u6570\u636e\uff0c\u4f5c\u4e3a\u4e94\u5927\u5e94\u7528\u7684\u5173\u8054\u57fa\u7840"),
    table(TABLE_PROJECT_MEMBER_ID, "\u9879\u76ee\u6210\u5458\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("project_no", "string", "\u9879\u76ee\u7f16\u53f7", 64),
              ("member_name", "string", "\u6210\u5458\u59d3\u540d", 64),
              ("member_identity", "string", "\u6210\u5458\u8eab\u4efd", 255),
              ("role", "string", "\u9879\u76ee\u89d2\u8272", 64),
              ("join_date", "date", "\u52a0\u5165\u65e5\u671f", 0),
              ("leave_date", "date", "\u9000\u51fa\u65e5\u671f", 0),
              ("workload", "number", "\u5de5\u4f5c\u91cf\u5360\u6bd4\uff08%\uff09", 0),
          ],
          "\u9879\u76ee\u6210\u5458\u53ca\u89d2\u8272\u5206\u914d"),
    table(TABLE_PROJECT_MILESTONE_ID, "\u9879\u76ee\u91cc\u7a0b\u7891\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("project_no", "string", "\u9879\u76ee\u7f16\u53f7", 64),
              ("milestone_name", "string", "\u91cc\u7a0b\u7891\u540d\u79f0", 255),
              ("plan_date", "date", "\u8ba1\u5212\u5b8c\u6210\u65e5\u671f", 0),
              ("actual_date", "date", "\u5b9e\u9645\u5b8c\u6210\u65e5\u671f", 0),
              ("is_done", "boolean", "\u662f\u5426\u5b8c\u6210", 0),
              ("delay_days", "number", "\u5ef6\u671f\u5929\u6570", 0),
          ],
          "\u9879\u76ee\u5173\u952e\u91cc\u7a0b\u7891\u8282\u70b9"),
]


# ==========================================================================
# 数据中心：统计
# ==========================================================================

STATS = [
    stat("s1001001-project-status-stat-0000000001",
         "\u9879\u76ee\u72b6\u6001\u5206\u5e03\u7edf\u8ba1", VIEW_PROJECT_LIST_ID,
         "project_status", "project_no",
         "\u6309\u9879\u76ee\u72b6\u6001\u7edf\u8ba1\u9879\u76ee\u6570\u91cf",
         category_title="\u9879\u76ee\u72b6\u6001", value_title="\u9879\u76ee\u6570"),
    stat("s1001002-project-type-stat-000000000001",
         "\u9879\u76ee\u7c7b\u522b\u5206\u5e03\u7edf\u8ba1", VIEW_PROJECT_LIST_ID,
         "project_type", "total_budget",
         "\u6309\u9879\u76ee\u7c7b\u522b\u7edf\u8ba1\u603b\u9884\u7b97",
         category_title="\u9879\u76ee\u7c7b\u522b", value_title="\u603b\u9884\u7b97"),
    stat("s1001003-project-budget-stat-00000000001",
         "\u90e8\u95e8\u9884\u7b97\u5206\u5e03\u7edf\u8ba1", VIEW_PROJECT_LIST_ID,
         "dept_name", "total_budget",
         "\u6309\u4e3b\u529e\u90e8\u95e8\u7edf\u8ba1\u9879\u76ee\u603b\u9884\u7b97",
         category_title="\u4e3b\u529e\u90e8\u95e8", value_title="\u603b\u9884\u7b97"),
    stat("s1001004-project-progress-stat-00000001",
         "\u9879\u76ee\u8fdb\u5ea6\u7edf\u8ba1", VIEW_PROGRESS_LIST_ID,
         "report_type", "overall_progress",
         "\u6309\u62a5\u544a\u7c7b\u578b\u7edf\u8ba1\u5e73\u5747\u5b8c\u6210\u5ea6",
         category_title="\u62a5\u544a\u7c7b\u578b", value_title="\u5e73\u5747\u5b8c\u6210\u5ea6"),
    stat("s1001005-project-risk-stat-00000000001",
         "\u9879\u76ee\u98ce\u9669\u5206\u5e03\u7edf\u8ba1", VIEW_PROGRESS_LIST_ID,
         "risk_level", "project_no",
         "\u6309\u98ce\u9669\u7b49\u7ea7\u7edf\u8ba1\u62a5\u544a\u6570\u91cf",
         category_title="\u98ce\u9669\u7b49\u7ea7", value_title="\u62a5\u544a\u6570"),
    stat("s1001006-project-cost-stat-000000000001",
         "\u9879\u76ee\u6210\u672c\u504f\u5dee\u7edf\u8ba1", VIEW_COST_LIST_ID,
         "project_name", "variance",
         "\u6309\u9879\u76ee\u7edf\u8ba1\u6210\u672c\u504f\u5dee",
         category_title="\u9879\u76ee\u540d\u79f0", value_title="\u6210\u672c\u504f\u5dee"),
]


# ==========================================================================
# 数据中心：查询配置（支持跨应用联动查询）
# ==========================================================================

STATEMENTS = [
    statement(
        "q1001001-project-fund-summary-00000001",
        "\u9879\u76ee\u8d44\u91d1\u6c47\u603b\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, p.total_budget, "
        "SUM(v.payment_amount) AS paid, SUM(v.payment_amount) AS approved "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u4ed8\u6b3e\u4e3b\u8868 v "
        "ON p.project_no = v.project_no GROUP BY p.project_no",
        "\u5173\u8054\u9879\u76ee\u4e3b\u8868\u4e0e\u4ed8\u6b3e\u4e3b\u8868\uff0c\u6c47\u603b\u9879\u76ee\u7d2f\u8ba1\u4ed8\u6b3e\u91d1\u989d"),
    statement(
        "q1001002-project-contract-link-000000001",
        "\u9879\u76ee\u5408\u540c\u5173\u8054\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, c.contract_no, c.contract_name, "
        "c.contract_amount, c.contract_status "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u5408\u540c\u4e3b\u8868 c "
        "ON p.project_no = c.project_no",
        "\u5b9e\u73b0\u9879\u76ee\u4e0e\u5408\u540c\u7684\u53cc\u5411\u5173\u8054\u67e5\u8be2"),
    statement(
        "q1001003-project-archive-link-0000000001",
        "\u9879\u76ee\u6863\u6848\u5173\u8054\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, a.archive_no, a.archive_name, "
        "a.archive_type, a.archive_state "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u6863\u6848\u4e3b\u8868 a "
        "ON p.project_no = a.project_no",
        "\u5b9e\u73b0\u9879\u76ee\u4e0e\u6863\u6848\u7684\u5173\u8054\u67e5\u8be2"),
]


FORMS = [FORM_PROJECT, FORM_APPROVE, FORM_WBS, FORM_PROGRESS, FORM_FUND,
         FORM_MATERIAL, FORM_COST, FORM_CLOSE, FORM_CHANGE, FORM_TASK]

PROCESSES = [PROC_APPROVE, PROC_PROGRESS, PROC_FUND, PROC_MATERIAL,
             PROC_CLOSE, PROC_CHANGE, PROC_TASK]

# 流程平台数据字典（本应用私有，引用自公共字典定义）
# 说明：真正落库时与 00_公共数据字典.xapp 中的同 id 字典为同一份，
#       此处仅作应用内可见性挂载。
DICTS = []

# --------------------------------------------------------------------------
# 门户：业务管理门户（跨应用聚合：项目 / 预算 / 财务 / 档案）
# --------------------------------------------------------------------------
# 01 作为载体应用承载该门户（.xapp 的 portalList）。门户内容会读其他应用的
# 自建表与流程 —— 门户只是展示层，跨应用引用是允许的。
# 定义放在 def_biz_portal.py，此处仅做挂载，避免本文件继续膨胀。
from def_biz_portal import PORTALS as _BIZ_PORTALS  # noqa: E402

PORTALS = _BIZ_PORTALS

# 门户内左侧导航树（OA 惯例）；本门户为横向 Tab 结构，树留空。
PORTAL_TREE = []

