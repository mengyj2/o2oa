# -*- coding: utf-8 -*-
"""
应用三：预算管理应用
====================
覆盖：预算编制 -> 预算审批 -> 预算下达 -> 预算执行/调整 -> 预算分析

关键联动：
  - 接收项目管理应用推送的项目总预算，作为项目预算编制依据
  - 接收财务管理应用推送的实际支出，形成预算执行率
  - 向项目管理应用反馈预算节超情况
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
)

APP_NAME = "\u9884\u7b97\u7ba1\u7406\u5e94\u7528"
APP_ID = "a3003000-budget-app-00000000000000001"
APP_ID_QUERY = "a3003001-budget-dataapp-000000000000001"

from o2oa_org import *  # noqa: F401,F403

# ==========================================================================
# 表单
# ==========================================================================

# ---- 1. 预算编制表单 ----
FORM_BUDGET_ID = "f3003001-budget-compile-form-0000000001"

BUDGET_FIELDS = [
    Field("budget_no", "\u9884\u7b97\u7f16\u53f7", "textfield", required=True,
          readonly=True, description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210"),
    Field("budget_name", "\u9884\u7b97\u540d\u79f0", "textfield", required=True),
    Field("budget_type", "\u9884\u7b97\u7c7b\u522b", "dict", code="budgetType", required=True),
    Field("budget_year", "\u9884\u7b97\u5e74\u5ea6", "textfield", required=True),
    Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
          description="\u9879\u76ee\u9884\u7b97\u5fc5\u586b\uff0c\u4e0e\u9879\u76ee\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
    Field("project_name", "\u5173\u8054\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("dept_name", "\u7f16\u5236\u90e8\u95e8", "org", required=True),
    Field("compiler", "\u7f16\u5236\u4eba", "org"),
    Field("compile_date", "\u7f16\u5236\u65e5\u671f", "calendar"),
    Field("fund_source", "\u8d44\u91d1\u6765\u6e90", "dict", code="fundSource"),
    Field("total_amount", "\u9884\u7b97\u603b\u989d\uff08\u5143\uff09", "currency",
          required=True, readonly=True, description="\u7531\u660e\u7ec6\u81ea\u52a8\u6c47\u603b"),
    Field("project_budget_ref", "\u9879\u76ee\u603b\u9884\u7b97\uff08\u5143\uff09", "currency",
          readonly=True, description="\u5f15\u81ea\u9879\u76ee\u7ba1\u7406\u5e94\u7528"),
    Field("budget_desc", "\u9884\u7b97\u8bf4\u660e", "textarea", required=True),
    Field("budget_basis", "\u7f16\u5236\u4f9d\u636e", "textarea"),
]

BUDGET_DATAGRID = {
    "id": "dg_budget",
    "name": "\u9884\u7b97\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("expense_type", "\u8d39\u7528\u7c7b\u578b", "select",
              options=["差旅费", "会议费", "办公费", "材料费", "设备费",
                       "劳务费", "咨询费", "测试化验费", "委托业务费", "其他费用"],
              description="130px"),
        Field("budget_item", "\u9884\u7b97\u9879\u76ee", "textfield", description="180px"),
        Field("budget_amount", "\u9884\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency", description="130px"),
        Field("calc_basis", "\u6d4b\u7b97\u4f9d\u636e", "textfield", description="180px"),
        Field("remark", "\u5907\u6ce8", "textfield", description="140px"),
    ],
}

FORM_BUDGET = FormBuilder(
    FORM_BUDGET_ID, "\u9884\u7b97\u7f16\u5236\u8868",
    "\u9884\u7b97\u7f16\u5236\u4e0e\u660e\u7ec6\u586b\u62a5",
    fields=BUDGET_FIELDS,
    datagrids=[BUDGET_DATAGRID],
)

# ---- 2. 预算调整表单 ----
FORM_BUDGET_ADJUST_ID = "f3003002-budget-adjust-form-000000001"

FORM_BUDGET_ADJUST = FormBuilder(
    FORM_BUDGET_ADJUST_ID, "\u9884\u7b97\u8c03\u6574\u7533\u8bf7\u8868",
    "\u9884\u7b97\u8c03\u6574\u7533\u8bf7\u4e0e\u5ba1\u6279",
    fields=[
        Field("budget_no", "\u9884\u7b97\u7f16\u53f7", "textfield", required=True),
        Field("budget_name", "\u9884\u7b97\u540d\u79f0", "textfield", readonly=True),
        Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield", readonly=True),
        Field("adjust_type", "\u8c03\u6574\u7c7b\u578b", "select",
              options=["预算追加", "预算调减", "科目间调剂"]),
        Field("original_amount", "\u539f\u9884\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency", readonly=True),
        Field("adjust_amount", "\u8c03\u6574\u91d1\u989d\uff08\u5143\uff09", "currency", required=True),
        Field("new_amount", "\u8c03\u6574\u540e\u91d1\u989d\uff08\u5143\uff09", "currency", readonly=True),
        Field("adjust_reason", "\u8c03\u6574\u539f\u56e0", "textarea", required=True),
        Field("adjust_detail", "\u8c03\u6574\u660e\u7ec6", "textarea"),
    ],
)

# ---- 3. 预算执行分析表单 ----
FORM_BUDGET_EXEC_ID = "f3003003-budget-exec-form-0000000000001"

FORM_BUDGET_EXEC = FormBuilder(
    FORM_BUDGET_EXEC_ID, "\u9884\u7b97\u6267\u884c\u5206\u6790\u8868",
    "\u9884\u7b97\u6267\u884c\u60c5\u51b5\u5206\u6790\u4e0e\u9884\u8b66",
    fields=[
        Field("budget_no", "\u9884\u7b97\u7f16\u53f7", "textfield", required=True),
        Field("budget_name", "\u9884\u7b97\u540d\u79f0", "textfield", readonly=True),
        Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield"),
        Field("analysis_period", "\u5206\u6790\u671f\u95f4", "textfield", required=True),
        Field("budget_total", "\u9884\u7b97\u603b\u989d\uff08\u5143\uff09", "currency", readonly=True),
        Field("executed_amount", "\u5df2\u6267\u884c\u91d1\u989d\uff08\u5143\uff09", "currency", readonly=True),
        Field("exec_rate", "\u6267\u884c\u7387\uff08%\uff09", "number", readonly=True),
        Field("remain_amount", "\u5269\u4f59\u989d\u5ea6\uff08\u5143\uff09", "currency", readonly=True),
        Field("warn_level", "\u9884\u8b66\u7b49\u7ea7", "select",
              options=["正常", "关注", "预警", "严重超支"]),
        Field("analysis_desc", "\u6267\u884c\u5206\u6790", "textarea", required=True),
    ],
)

BUDGET_EXEC_DATAGRID = {
    "id": "dg_exec",
    "name": "\u5206\u8d39\u7528\u7c7b\u578b\u6267\u884c\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("expense_type", "\u8d39\u7528\u7c7b\u578b", "textfield", description="130px"),
        Field("budget_amount", "\u9884\u7b97\u91d1\u989d\uff08\u5143\uff09", "currency", description="130px"),
        Field("exec_amount", "\u5df2\u6267\u884c\uff08\u5143\uff09", "currency", description="130px"),
        Field("exec_rate", "\u6267\u884c\u7387\uff08%\uff09", "number", description="110px"),
        Field("remain_amount", "\u5269\u4f59\uff08\u5143\uff09", "currency", description="120px"),
    ],
}

FORM_BUDGET_EXEC_REAL = FormBuilder(
    FORM_BUDGET_EXEC_ID, "\u9884\u7b97\u6267\u884c\u5206\u6790\u8868",
    "\u9884\u7b97\u6267\u884c\u60c5\u51b5\u5206\u6790\u4e0e\u9884\u8b66",
    fields=FORM_BUDGET_EXEC.fields,
    datagrids=[BUDGET_EXEC_DATAGRID],
)

# ==========================================================================
# 流程
# ==========================================================================

PROC_BUDGET_ID = "p3003001-budget-approve-0000000000001"

PROC_BUDGET = ProcessBuilder(
    PROC_BUDGET_ID, "\u9884\u7b97\u7f16\u5236\u5ba1\u6279\u6d41\u7a0b",
    "\u9884\u7b97\u7f16\u5236\u3001\u5ba1\u6838\u3001\u5ba1\u6279\u4e0e\u4e0b\u8fbe",
    form_id=FORM_BUDGET_ID,
    activities=[
        Activity("a_draft", "\u9884\u7b97\u7f16\u5236", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_pm", "\u9879\u76ee\u7ecf\u7406\u786e\u8ba4", "manual", task_script=SCRIPT_BUDGET),
        Activity("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_issue", "\u9884\u7b97\u4e0b\u8fbe", "manual", task_script=SCRIPT_BUDGET),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_pm", "\u63d0\u4ea4", ""),
        ("a_pm", "a_dept", "\u786e\u8ba4", ""),
        ("a_pm", "a_draft", "\u9000\u56de", ""),
        ("a_dept", "a_finance", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_dept", "a_draft", "\u9a73\u56de", ""),
        ("a_finance", "a_leader", "\u8d22\u52a1\u901a\u8fc7", ""),
        ("a_leader", "a_issue", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_issue", "a_end", "\u4e0b\u8fbe\u5b8c\u6210", ""),
    ],
)

PROC_BUDGET_ADJUST_ID = "p3003002-budget-adjust-00000000000001"

PROC_BUDGET_ADJUST = ProcessBuilder(
    PROC_BUDGET_ADJUST_ID, "\u9884\u7b97\u8c03\u6574\u5ba1\u6279\u6d41\u7a0b",
    "\u9884\u7b97\u8c03\u6574\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_BUDGET_ADJUST_ID,
    activities=[
        Activity("a_draft", "\u8c03\u6574\u7533\u8bf7", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_finance", "\u63d0\u4ea4", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_draft", "\u9000\u56de", ""),
        ("a_leader", "a_end", "\u6279\u51c6", ""),
    ],
)

# ==========================================================================
# 视图
# ==========================================================================

VIEW_BUDGET_LIST_ID = "v3003001-budget-list-view-00000000000001"
VIEW_BUDGET_EXEC_LIST_ID = "v3003002-budget-exec-view-00000000001"
VIEW_BUDGET_WARN_ID = "v3003003-budget-warn-view-00000000001"

VIEWS = [
    view(VIEW_BUDGET_LIST_ID, "\u9884\u7b97\u53f0\u8d26\u89c6\u56fe",
         "\u5168\u91cf\u9884\u7b97\u7f16\u5236\u4e0e\u5ba1\u6279\u8bb0\u5f55",
         source="process", process_list=[PROC_BUDGET_ID],
         columns=[
             ("\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u9884\u7b97\u540d\u79f0", "budget_name", "220px"),
             ("\u9884\u7b97\u7c7b\u522b", "budget_type", "110px"),
             ("\u9884\u7b97\u5e74\u5ea6", "budget_year", "100px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u7f16\u5236\u90e8\u95e8", "dept_name", "150px"),
             ("\u8d44\u91d1\u6765\u6e90", "fund_source", "110px"),
             ("\u9884\u7b97\u603b\u989d", "total_amount", "130px"),
         ]),
    view(VIEW_BUDGET_EXEC_LIST_ID, "\u9884\u7b97\u6267\u884c\u53f0\u8d26",
         "\u9884\u7b97\u6267\u884c\u4e0e\u504f\u63a7\u5206\u6790\u8bb0\u5f55",
         source="process", process_list=[PROC_BUDGET_ADJUST_ID],
         columns=[
             ("\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u8c03\u6574\u7c7b\u578b", "adjust_type", "110px"),
             ("\u539f\u9884\u7b97\u91d1\u989d", "original_amount", "130px"),
             ("\u8c03\u6574\u91d1\u989d", "adjust_amount", "120px"),
             ("\u8c03\u6574\u540e\u91d1\u989d", "new_amount", "130px"),
         ]),
    view(VIEW_BUDGET_WARN_ID, "\u9884\u7b97\u6267\u884c\u9884\u8b66\u89c6\u56fe",
         "\u9884\u7b97\u6267\u884c\u7387\u76d1\u63a7\u4e0e\u8d85\u652f\u9884\u8b66",
         source="process", process_list=[PROC_BUDGET_ID],
         columns=[
             ("\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u9884\u7b97\u540d\u79f0", "budget_name", "220px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u9884\u7b97\u603b\u989d", "total_amount", "130px"),
             ("\u9884\u7b97\u5e74\u5ea6", "budget_year", "100px"),
         ]),
]

# ==========================================================================
# 自建表
# ==========================================================================

TABLE_BUDGET_MASTER_ID = "t3003001-budget-master-table-000000001"
TABLE_BUDGET_DETAIL_ID = "t3003002-budget-detail-table-000000001"

TABLES = [
    table(TABLE_BUDGET_MASTER_ID, "\u9884\u7b97\u4e3b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("budget_no", "string", "\u9884\u7b97\u7f16\u53f7", 64),
              ("budget_name", "string", "\u9884\u7b97\u540d\u79f0", 255),
              ("budget_type", "string", "\u9884\u7b97\u7c7b\u522b", 64),
              ("budget_year", "string", "\u9884\u7b97\u5e74\u5ea6", 16),
              ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
              ("dept_name", "string", "\u7f16\u5236\u90e8\u95e8", 255),
              ("fund_source", "string", "\u8d44\u91d1\u6765\u6e90", 64),
              ("total_amount", "number", "\u9884\u7b97\u603b\u989d", 0),
              ("executed_amount", "number", "\u5df2\u6267\u884c\u91d1\u989d", 0),
              ("remain_amount", "number", "\u5269\u4f59\u989d\u5ea6", 0),
              ("exec_rate", "number", "\u6267\u884c\u7387", 0),
              ("budget_status", "string", "\u9884\u7b97\u72b6\u6001", 32),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
              ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 0),
          ],
          "\u9884\u7b97\u4e3b\u6570\u636e\uff0c\u4e0e\u9879\u76ee/\u8d22\u52a1\u5e94\u7528\u5171\u4eab"),
    table(TABLE_BUDGET_DETAIL_ID, "\u9884\u7b97\u660e\u7ec6\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("budget_no", "string", "\u9884\u7b97\u7f16\u53f7", 64),
              ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
              ("expense_type", "string", "\u8d39\u7528\u7c7b\u578b", 64),
              ("budget_item", "string", "\u9884\u7b97\u9879\u76ee", 255),
              ("budget_amount", "number", "\u9884\u7b97\u91d1\u989d", 0),
              ("exec_amount", "number", "\u5df2\u6267\u884c\u91d1\u989d", 0),
              ("exec_rate", "number", "\u6267\u884c\u7387", 0),
          ],
          "\u9884\u7b97\u5206\u8d39\u7528\u7c7b\u578b\u660e\u7ec6\uff0c\u652f\u6301\u9884\u7b97\u4e0e\u5b9e\u9645\u5bf9\u6bd4"),
]

STATS = [
    stat("s3003001-budget-type-stat-0000000000001",
         "\u9884\u7b97\u7c7b\u522b\u5206\u5e03\u7edf\u8ba1", VIEW_BUDGET_LIST_ID,
         "budget_type", "total_amount",
         "\u6309\u9884\u7b97\u7c7b\u522b\u7edf\u8ba1\u9884\u7b97\u603b\u989d",
         category_title="\u9884\u7b97\u7c7b\u522b", value_title="\u9884\u7b97\u603b\u989d"),
    stat("s3003002-budget-dept-stat-0000000000001",
         "\u90e8\u95e8\u9884\u7b97\u7edf\u8ba1", VIEW_BUDGET_LIST_ID,
         "dept_name", "total_amount",
         "\u6309\u7f16\u5236\u90e8\u95e8\u7edf\u8ba1\u9884\u7b97\u603b\u989d",
         category_title="\u7f16\u5236\u90e8\u95e8", value_title="\u9884\u7b97\u603b\u989d"),
    stat("s3003003-budget-fund-stat-000000000001",
         "\u8d44\u91d1\u6765\u6e90\u7edf\u8ba1", VIEW_BUDGET_LIST_ID,
         "fund_source", "total_amount",
         "\u6309\u8d44\u91d1\u6765\u6e90\u7edf\u8ba1\u9884\u7b97\u603b\u989d",
         category_title="\u8d44\u91d1\u6765\u6e90", value_title="\u9884\u7b97\u603b\u989d"),
]

STATEMENTS = [
    statement(
        "q3003001-budget-exec-summary-00000000001",
        "\u9884\u7b97\u6267\u884c\u6c47\u603b\u67e5\u8be2",
        "SELECT b.budget_no, b.budget_name, b.project_no, b.total_amount, "
        "SUM(d.exec_amount) AS executed, "
        "ROUND(SUM(d.exec_amount) * 100.0 / b.total_amount, 2) AS exec_rate "
        "FROM \u9884\u7b97\u4e3b\u8868 b LEFT JOIN \u9884\u7b97\u660e\u7ec6\u8868 d "
        "ON b.budget_no = d.budget_no GROUP BY b.budget_no",
        "\u6309\u9884\u7b97\u6c47\u603b\u5df2\u6267\u884c\u91d1\u989d\u4e0e\u6267\u884c\u7387"),
    statement(
        "q3003002-project-budget-link-000000000001",
        "\u9879\u76ee\u9884\u7b97\u5173\u8054\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, p.total_budget, "
        "b.budget_no, b.total_amount, b.executed_amount "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u9884\u7b97\u4e3b\u8868 b "
        "ON p.project_no = b.project_no",
        "\u5b9e\u73b0\u9879\u76ee\u603b\u9884\u7b97\u4e0e\u9884\u7b97\u5e94\u7528\u7684\u5173\u8054\u6bd4\u5bf9"),
]

FORMS = [FORM_BUDGET, FORM_BUDGET_ADJUST, FORM_BUDGET_EXEC_REAL]
PROCESSES = [PROC_BUDGET, PROC_BUDGET_ADJUST]
