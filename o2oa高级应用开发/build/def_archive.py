# -*- coding: utf-8 -*-
"""
应用五：档案管理应用
====================
覆盖：档案著录 -> 归档审批 -> 档案入库 -> 档案借阅 -> 归还/续借
-> 档案移交/销毁

关键联动（本应用是"数据汇聚终点"）：
  - 接收项目、合同、财务、预算四大应用推送的归档数据
  - 四大应用的表单中均有 archive_no 字段回写，形成双向关联
  - 提供统一档案检索视图，支持按 project_no / contract_no 反查
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
)

APP_NAME = "\u6863\u6848\u7ba1\u7406\u5e94\u7528"
APP_ID = "a5005000-archive-app-00000000000000001"
APP_ID_QUERY = "a5005001-archive-dataapp-000000000000001"

from o2oa_org import *  # noqa: F401,F403

# ==========================================================================
# 表单
# ==========================================================================

# ---- 1. 档案著录表单（核心）----
FORM_ARCHIVE_ID = "f5005001-archive-catalog-form-000000001"

ARCHIVE_FIELDS = [
    Field("archive_no", "\u6863\u6848\u7f16\u53f7", "textfield", required=True,
          readonly=True, description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210\uff0c\u5168\u5c40\u552f\u4e00"),
    Field("archive_name", "\u6863\u6848\u540d\u79f0", "textfield", required=True),
    Field("archive_type", "\u6863\u6848\u7c7b\u522b", "dict", code="archiveType", required=True),
    Field("archive_level", "\u4fdd\u5bc6\u7b49\u7ea7", "dict", code="archiveLevel", required=True),
    Field("archive_state", "\u6863\u6848\u72b6\u6001", "dict", code="archiveState",
          readonly=True, default="待归档"),
    Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
          description="\u4e0e\u9879\u76ee\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
    Field("contract_no", "\u5173\u8054\u5408\u540c\u7f16\u53f7", "textfield",
          description="\u4e0e\u5408\u540c\u7ba1\u7406\u5e94\u7528\u8054\u52a8"),
    Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield"),
    Field("expense_no", "\u5173\u8054\u62a5\u9500\u5355\u53f7", "textfield"),
    Field("source_app", "\u6765\u6e90\u5e94\u7528", "select",
          options=["项目管理", "合同管理", "预算管理", "财务管理", "手工著录"]),
    Field("fonds_no", "\u5168\u5b97\u53f7", "textfield"),
    Field("category_no", "\u5206\u7c7b\u53f7", "textfield"),
    Field("archive_year", "\u5e74\u5ea6", "textfield"),
    Field("retention_period", "\u4fdd\u5b58\u671f\u9650", "select",
          options=["永久", "30年", "10年", "5年"]),
    Field("carrier_type", "\u8f7d\u4f53\u7c7b\u578b", "select",
          options=["纸质", "电子", "纸质+电子"]),
    Field("pages", "\u9875\u6570", "number"),
    Field("copies", "\u4efd\u6570", "number", default="1"),
    Field("archiver", "\u5f52\u6863\u4eba", "org"),
    Field("archive_date", "\u5f52\u6863\u65e5\u671f", "calendar"),
    Field("storage_location", "\u5b58\u653e\u4f4d\u7f6e", "textfield"),
    Field("archive_desc", "\u6863\u6848\u5185\u5bb9\u63cf\u8ff0", "textarea", required=True),
    Field("keywords", "\u4e3b\u9898\u8bcd", "textfield"),
]

FORM_ARCHIVE = FormBuilder(
    FORM_ARCHIVE_ID, "\u6863\u6848\u8457\u5f55\u8868",
    "\u6863\u6848\u57fa\u7840\u4fe1\u606f\u8457\u5f55\u4e0e\u5f52\u6863\u767b\u8bb0",
    fields=ARCHIVE_FIELDS,
)

# ---- 2. 档案借阅申请表单 ----
FORM_BORROW_ID = "f5005002-archive-borrow-form-0000000001"

FORM_BORROW = FormBuilder(
    FORM_BORROW_ID, "\u6863\u6848\u501f\u9605\u7533\u8bf7\u8868",
    "\u6863\u6848\u501f\u9605\u3001\u590d\u5236\u4e0e\u5bfc\u51fa\u7533\u8bf7",
    fields=[
        Field("borrow_no", "\u501f\u9605\u5355\u53f7", "textfield", readonly=True),
        Field("archive_no", "\u6863\u6848\u7f16\u53f7", "textfield", required=True),
        Field("archive_name", "\u6863\u6848\u540d\u79f0", "textfield", readonly=True),
        Field("archive_type", "\u6863\u6848\u7c7b\u522b", "dict", code="archiveType", readonly=True),
        Field("borrower", "\u501f\u9605\u4eba", "org", required=True),
        Field("borrow_dept", "\u6240\u5728\u90e8\u95e8", "org"),
        Field("borrow_type", "\u501f\u9605\u65b9\u5f0f", "radio",
              options=["\u9605\u89c8", "\u501f\u51fa", "\u590d\u5236", "\u5bfc\u51fa\u7535\u5b50\u4ef6"]),
        Field("borrow_reason", "\u501f\u9605\u4e8b\u7531", "textarea", required=True),
        Field("borrow_date", "\u501f\u9605\u65e5\u671f", "calendar", required=True),
        Field("plan_return_date", "\u8ba1\u5212\u5f52\u8fd8\u65e5\u671f", "calendar"),
        Field("actual_return_date", "\u5b9e\u9645\u5f52\u8fd8\u65e5\u671f", "calendar"),
        Field("borrow_status", "\u501f\u9605\u72b6\u6001", "select",
              options=["审批中", "借阅中", "已归还", "已逾期"]),
        Field("approve_opinion", "\u5ba1\u6279\u610f\u89c1", "textarea"),
    ],
)

# ---- 3. 档案移交/销毁表单 ----
FORM_ARCHIVE_DISPOSE_ID = "f5005003-archive-dispose-form-000001"

FORM_ARCHIVE_DISPOSE = FormBuilder(
    FORM_ARCHIVE_DISPOSE_ID, "\u6863\u6848\u79fb\u4ea4\u9500\u6bc1\u5ba1\u6279\u8868",
    "\u6863\u6848\u79fb\u4ea4\u3001\u5bc6\u7ea7\u53d8\u66f4\u4e0e\u9500\u6bc1\u5ba1\u6279",
    fields=[
        Field("dispose_no", "\u5904\u7f6e\u5355\u53f7", "textfield", readonly=True),
        Field("archive_no", "\u6863\u6848\u7f16\u53f7", "textfield", required=True),
        Field("archive_name", "\u6863\u6848\u540d\u79f0", "textfield", readonly=True),
        Field("dispose_type", "\u5904\u7f6e\u7c7b\u578b", "select",
              options=["移交上级", "移交档案馆", "销毁", "密级变更", "保管期限变更"]),
        Field("dispose_reason", "\u5904\u7f6e\u4e8b\u7531", "textarea", required=True),
        Field("receiver", "\u63a5\u6536\u5355\u4f4d/\u4eba", "textfield"),
        Field("dispose_date", "\u5904\u7f6e\u65e5\u671f", "calendar"),
        Field("new_level", "\u53d8\u66f4\u540e\u5bc6\u7ea7", "dict", code="archiveLevel"),
        Field("new_period", "\u53d8\u66f4\u540e\u671f\u9650", "select",
              options=["永久", "30年", "10年", "5年"]),
    ],
)

# ---- 4. 档案目录（内容管理型）----
FORM_ARCHIVE_CATALOG_ID = "f5005004-archive-directory-form-000001"

FORM_ARCHIVE_CATALOG = FormBuilder(
    FORM_ARCHIVE_CATALOG_ID, "\u6863\u6848\u76ee\u5f55\u767b\u8bb0\u8868",
    "\u6863\u6848\u76ee\u5f55\u7ea7\u4fe1\u606f\u767b\u8bb0\uff08\u6848\u5377\uff09",
    fields=[
        Field("archive_no", "\u6863\u6848\u7f16\u53f7", "textfield", required=True),
        Field("archive_name", "\u6863\u6848\u540d\u79f0", "textfield", required=True),
        Field("archive_type", "\u6863\u6848\u7c7b\u522b", "dict", code="archiveType"),
        Field("fonds_no", "\u5168\u5b97\u53f7", "textfield"),
        Field("archive_year", "\u5e74\u5ea6", "textfield"),
        Field("retention_period", "\u4fdd\u5b58\u671f\u9650", "select",
              options=["永久", "30年", "10年", "5年"]),
        Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield"),
        Field("storage_location", "\u5b58\u653e\u4f4d\u7f6e", "textfield"),
    ],
)

# ==========================================================================
# 流程
# ==========================================================================

# ---- 1. 档案归档流程 ----
PROC_ARCHIVE_ID = "p5005001-archive-catalog-00000000000001"

PROC_ARCHIVE = ProcessBuilder(
    PROC_ARCHIVE_ID, "\u6863\u6848\u5f52\u6863\u5ba1\u6279\u6d41\u7a0b",
    "\u6863\u6848\u8457\u5f55\u3001\u5f52\u6863\u5ba1\u6279\u4e0e\u5165\u5e93",
    form_id=FORM_ARCHIVE_ID,
    activities=[
        Activity("a_draft", "\u6863\u6848\u8457\u5f55", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_dept", "\u4ea7\u751f\u90e8\u95e8\u786e\u8ba4", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_check", "\u6863\u6848\u5ba1\u6838", "manual", task_script=SCRIPT_ARCHIVE_DIR),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_instore", "\u6863\u6848\u5165\u5e93", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_dept", "\u63d0\u4ea4", ""),
        ("a_dept", "a_check", "\u786e\u8ba4", ""),
        ("a_dept", "a_draft", "\u9000\u56de", ""),
        ("a_check", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_check", "a_draft", "\u9a73\u56de", ""),
        ("a_leader", "a_instore", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_instore", "a_end", "\u5165\u5e93\u5b8c\u6210", ""),
    ],
)

# ---- 2. 档案借阅流程 ----
PROC_BORROW_ID = "p5005002-archive-borrow-0000000000001"

PROC_ARCHIVE_BORROW = ProcessBuilder(
    PROC_BORROW_ID, "\u6863\u6848\u501f\u9605\u5ba1\u6279\u6d41\u7a0b",
    "\u6863\u6848\u501f\u9605\u7533\u8bf7\u3001\u5ba1\u6279\u4e0e\u5f52\u8fd8\u767b\u8bb0",
    form_id=FORM_BORROW_ID,
    activities=[
        Activity("a_draft", "\u501f\u9605\u7533\u8bf7", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_archive", "\u6863\u6848\u7ba1\u7406\u5458\u5ba1\u6279", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_return", "\u5f52\u8fd8\u767b\u8bb0", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_dept", "\u63d0\u4ea4", ""),
        ("a_dept", "a_archive", "\u540c\u610f", ""),
        ("a_dept", "a_draft", "\u9000\u56de", ""),
        ("a_archive", "a_return", "\u51fa\u5e93", ""),
        ("a_archive", "a_draft", "\u4e0d\u540c\u610f", ""),
        ("a_return", "a_end", "\u5f52\u8fd8\u5b8c\u6210", ""),
    ],
)

# ---- 3. 档案处置流程 ----
PROC_DISPOSE_ID = "p5005003-archive-dispose-000000000001"

PROC_ARCHIVE_DISPOSE = ProcessBuilder(
    PROC_DISPOSE_ID, "\u6863\u6848\u79fb\u4ea4\u9500\u6bc1\u5ba1\u6279\u6d41\u7a0b",
    "\u6863\u6848\u79fb\u4ea4\u3001\u9500\u6bc1\u4e0e\u5bc6\u7ea7\u53d8\u66f4\u5ba1\u6279",
    form_id=FORM_ARCHIVE_DISPOSE_ID,
    activities=[
        Activity("a_draft", "\u5904\u7f6e\u7533\u8bf7", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_check", "\u6863\u6848\u5ba1\u6838", "manual", task_script=SCRIPT_ARCHIVE_DIR),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_exec", "\u5904\u7f6e\u6267\u884c", "manual", task_script=SCRIPT_ARCHIVE),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_check", "\u63d0\u4ea4", ""),
        ("a_check", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_check", "a_draft", "\u9a73\u56de", ""),
        ("a_leader", "a_exec", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_exec", "a_end", "\u5904\u7f6e\u5b8c\u6210", ""),
    ],
)

# ==========================================================================
# 视图
# ==========================================================================

VIEW_ARCHIVE_LIST_ID = "v5005001-archive-list-view-000000000001"
VIEW_ARCHIVE_BORROW_ID = "v5005002-archive-borrow-view-0000000001"
VIEW_ARCHIVE_LINK_ID = "v5005003-archive-link-view-00000000001"

VIEWS = [
    view(VIEW_ARCHIVE_LIST_ID, "\u6863\u6848\u53f0\u8d26\u89c6\u56fe",
         "\u5168\u91cf\u6863\u6848\u8457\u5f55\u4e0e\u5f52\u6863\u4fe1\u606f",
         source="process", process_list=[PROC_ARCHIVE_ID],
         columns=[
             ("\u6863\u6848\u7f16\u53f7", "archive_no", "130px"),
             ("\u6863\u6848\u540d\u79f0", "archive_name", "220px"),
             ("\u6863\u6848\u7c7b\u522b", "archive_type", "110px"),
             ("\u4fdd\u5bc6\u7b49\u7ea7", "archive_level", "100px"),
             ("\u6765\u6e90\u5e94\u7528", "source_app", "110px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u5173\u8054\u5408\u540c\u7f16\u53f7", "contract_no", "130px"),
             ("\u4fdd\u5b58\u671f\u9650", "retention_period", "100px"),
             ("\u5f52\u6863\u65e5\u671f", "archive_date", "110px"),
             ("\u6863\u6848\u72b6\u6001", "archive_state", "100px"),
         ]),
    view(VIEW_ARCHIVE_BORROW_ID, "\u6863\u6848\u501f\u9605\u53f0\u8d26",
         "\u6863\u6848\u501f\u9605\u4e0e\u5f52\u8fd8\u8bb0\u5f55",
         source="process", process_list=[PROC_BORROW_ID],
         columns=[
             ("\u501f\u9605\u5355\u53f7", "borrow_no", "130px"),
             ("\u6863\u6848\u7f16\u53f7", "archive_no", "130px"),
             ("\u6863\u6848\u540d\u79f0", "archive_name", "200px"),
             ("\u501f\u9605\u4eba", "borrower", "110px"),
             ("\u501f\u9605\u65b9\u5f0f", "borrow_type", "110px"),
             ("\u501f\u9605\u65e5\u671f", "borrow_date", "110px"),
             ("\u8ba1\u5212\u5f52\u8fd8\u65e5", "plan_return_date", "120px"),
             ("\u501f\u9605\u72b6\u6001", "borrow_status", "100px"),
         ]),
    view(VIEW_ARCHIVE_LINK_ID, "\u6863\u6848\u5173\u8054\u67e5\u8be2\u89c6\u56fe",
         "\u6309\u9879\u76ee/\u5408\u540c\u53cd\u67e5\u5173\u8054\u6863\u6848",
         source="process", process_list=[PROC_ARCHIVE_ID],
         columns=[
             ("\u6863\u6848\u7f16\u53f7", "archive_no", "130px"),
             ("\u6863\u6848\u540d\u79f0", "archive_name", "220px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u5173\u8054\u5408\u540c\u7f16\u53f7", "contract_no", "130px"),
             ("\u5173\u8054\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u5173\u8054\u62a5\u9500\u5355\u53f7", "expense_no", "130px"),
             ("\u5b58\u653e\u4f4d\u7f6e", "storage_location", "140px"),
         ]),
]

# ==========================================================================
# 自建表
# ==========================================================================

TABLE_ARCHIVE_MASTER_ID = "t5005001-archive-master-table-00000001"
TABLE_ARCHIVE_BORROW_ID = "t5005002-archive-borrow-table-00000001"
TABLE_ARCHIVE_LINK_ID = "t5005003-archive-link-table-000000001"

TABLES = [
    table(TABLE_ARCHIVE_MASTER_ID, "\u6863\u6848\u4e3b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("archive_no", "string", "\u6863\u6848\u7f16\u53f7", 64),
              ("archive_name", "string", "\u6863\u6848\u540d\u79f0", 255),
              ("archive_type", "string", "\u6863\u6848\u7c7b\u522b", 64),
              ("archive_level", "string", "\u4fdd\u5bc6\u7b49\u7ea7", 32),
              ("archive_state", "string", "\u6863\u6848\u72b6\u6001", 32),
              ("source_app", "string", "\u6765\u6e90\u5e94\u7528", 64),
              ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
              ("contract_no", "string", "\u5173\u8054\u5408\u540c\u7f16\u53f7", 64),
              ("budget_no", "string", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", 64),
              ("expense_no", "string", "\u5173\u8054\u62a5\u9500\u5355\u53f7", 64),
              ("fonds_no", "string", "\u5168\u5b97\u53f7", 64),
              ("archive_year", "string", "\u5e74\u5ea6", 16),
              ("retention_period", "string", "\u4fdd\u5b58\u671f\u9650", 32),
              ("carrier_type", "string", "\u8f7d\u4f53\u7c7b\u578b", 32),
              ("pages", "number", "\u9875\u6570", 0),
              ("storage_location", "string", "\u5b58\u653e\u4f4d\u7f6e", 128),
              ("archive_date", "date", "\u5f52\u6863\u65e5\u671f", 0),
              ("keywords", "string", "\u4e3b\u9898\u8bcd", 255),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
              ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 0),
          ],
          "\u6863\u6848\u4e3b\u6570\u636e\uff0c\u4e94\u5927\u5e94\u7528\u7edf\u4e00\u5f52\u6863\u843d\u5e93\u8868"),
    table(TABLE_ARCHIVE_BORROW_ID, "\u6863\u6848\u501f\u9605\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("borrow_no", "string", "\u501f\u9605\u5355\u53f7", 64),
              ("archive_no", "string", "\u6863\u6848\u7f16\u53f7", 64),
              ("borrower", "string", "\u501f\u9605\u4eba", 255),
              ("borrow_dept", "string", "\u6240\u5728\u90e8\u95e8", 255),
              ("borrow_type", "string", "\u501f\u9605\u65b9\u5f0f", 32),
              ("borrow_reason", "text", "\u501f\u9605\u4e8b\u7531", 0),
              ("borrow_date", "date", "\u501f\u9605\u65e5\u671f", 0),
              ("plan_return_date", "date", "\u8ba1\u5212\u5f52\u8fd8\u65e5", 0),
              ("actual_return_date", "date", "\u5b9e\u9645\u5f52\u8fd8\u65e5", 0),
              ("borrow_status", "string", "\u501f\u9605\u72b6\u6001", 32),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
          ],
          "\u6863\u6848\u501f\u9605\u660e\u7ec6\uff0c\u652f\u6301\u501f\u9605\u7edf\u8ba1\u4e0e\u903e\u671f\u9884\u8b66"),
    table(TABLE_ARCHIVE_LINK_ID, "\u6863\u6848\u5173\u8054\u5173\u7cfb\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("archive_no", "string", "\u6863\u6848\u7f16\u53f7", 64),
              ("biz_type", "string", "\u4e1a\u52a1\u7c7b\u578b", 32),
              ("biz_no", "string", "\u4e1a\u52a1\u5355\u53f7", 64),
              ("project_no", "string", "\u9879\u76ee\u7f16\u53f7", 64),
              ("link_time", "datetime", "\u5173\u8054\u65f6\u95f4", 0),
          ],
          "\u6863\u6848\u4e0e\u5404\u4e1a\u52a1\u5355\u636e\u7684\u5173\u8054\u5173\u7cfb\uff0c\u652f\u6301\u53cd\u5411\u67e5\u8be2"),
]

STATS = [
    stat("s5005001-archive-type-stat-0000000000001",
         "\u6863\u6848\u7c7b\u522b\u5206\u5e03\u7edf\u8ba1", VIEW_ARCHIVE_LIST_ID,
         "archive_type", "archive_no",
         "\u6309\u6863\u6848\u7c7b\u522b\u7edf\u8ba1\u6863\u6848\u6570\u91cf",
         category_title="\u6863\u6848\u7c7b\u522b", value_title="\u6863\u6848\u6570\u91cf"),
    stat("s5005002-archive-source-stat-000000001",
         "\u6765\u6e90\u5e94\u7528\u5f52\u6863\u7edf\u8ba1", VIEW_ARCHIVE_LIST_ID,
         "source_app", "archive_no",
         "\u6309\u6765\u6e90\u5e94\u7528\u7edf\u8ba1\u5f52\u6863\u6570\u91cf",
         category_title="\u6765\u6e90\u5e94\u7528", value_title="\u5f52\u6863\u6570\u91cf"),
    stat("s5005003-archive-period-stat-000000001",
         "\u4fdd\u5b58\u671f\u9650\u7edf\u8ba1", VIEW_ARCHIVE_LIST_ID,
         "retention_period", "archive_no",
         "\u6309\u4fdd\u5b58\u671f\u9650\u7edf\u8ba1\u6863\u6848\u6570\u91cf",
         category_title="\u4fdd\u5b58\u671f\u9650", value_title="\u6863\u6848\u6570\u91cf"),
    stat("s5005004-archive-borrow-stat-0000000001",
         "\u6863\u6848\u501f\u9605\u7edf\u8ba1", VIEW_ARCHIVE_BORROW_ID,
         "borrow_type", "borrow_no",
         "\u6309\u501f\u9605\u65b9\u5f0f\u7edf\u8ba1\u501f\u9605\u6b21\u6570",
         category_title="\u501f\u9605\u65b9\u5f0f", value_title="\u501f\u9605\u6b21\u6570"),
]

STATEMENTS = [
    statement(
        "q5005001-archive-business-link-0000000001",
        "\u6863\u6848\u4e1a\u52a1\u5173\u8054\u67e5\u8be2",
        "SELECT a.archive_no, a.archive_name, a.archive_type, a.source_app, "
        "l.biz_type, l.biz_no, l.project_no "
        "FROM \u6863\u6848\u4e3b\u8868 a LEFT JOIN \u6863\u6848\u5173\u8054\u5173\u7cfb\u8868 l "
        "ON a.archive_no = l.archive_no",
        "\u901a\u8fc7\u5173\u8054\u8868\u53cd\u67e5\u6863\u6848\u5bf9\u5e94\u7684\u4e1a\u52a1\u5355\u636e"),
    statement(
        "q5005002-project-archive-full-00000000001",
        "\u9879\u76ee\u5168\u91cf\u6863\u6848\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, a.archive_no, a.archive_name, "
        "a.archive_type, a.retention_period, a.storage_location "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u6863\u6848\u4e3b\u8868 a "
        "ON p.project_no = a.project_no",
        "\u6c47\u603b\u67d0\u9879\u76ee\u4e0b\u5168\u90e8\u5173\u8054\u6863\u6848"),
    statement(
        "q5005003-archive-borrow-overdue-000000001",
        "\u6863\u6848\u903e\u671f\u672a\u5f52\u8fd8\u67e5\u8be2",
        "SELECT b.borrow_no, b.archive_no, b.borrower, b.borrow_date, "
        "b.plan_return_date, b.borrow_status "
        "FROM \u6863\u6848\u501f\u9605\u8868 b "
        "WHERE b.borrow_status <> '\u5df2\u5f52\u8fd8' AND b.plan_return_date < CURRENT_DATE",
        "\u67e5\u8be2\u903e\u671f\u672a\u5f52\u8fd8\u7684\u6863\u6848\u501f\u9605\u8bb0\u5f55"),
]

FORMS = [FORM_ARCHIVE, FORM_BORROW, FORM_ARCHIVE_DISPOSE, FORM_ARCHIVE_CATALOG]
PROCESSES = [PROC_ARCHIVE, PROC_ARCHIVE_BORROW, PROC_ARCHIVE_DISPOSE]
