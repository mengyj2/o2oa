# -*- coding: utf-8 -*-
"""
应用四：财务管理应用
====================
覆盖：费用报销 -> 借款/还款 -> 付款审批 -> 财务记账 -> 财务分析

关键联动：
  - 报销/付款单据均带 project_no，回写项目管理应用的成本核算
  - 实际支出回写预算管理应用形成预算执行率
  - 合同付款与合同管理应用的付款申请单双向关联（合同编号）
  - 会计凭证自动归集到档案管理应用
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
)

APP_NAME = "\u8d22\u52a1\u7ba1\u7406\u5e94\u7528"
APP_ID = "a4004000-finance-app-00000000000000001"
APP_ID_QUERY = "a4004001-finance-dataapp-000000000000001"

from o2oa_org import *  # noqa: F401,F403
SCRIPT_PROJECT_MGR = "return this.data.expense_context.project_manager;"

# ==========================================================================
# 表单
# ==========================================================================

# ---- 1. 费用报销表单（核心）----
FORM_EXPENSE_ID = "f4004001-expense-claim-form-00000000001"

EXPENSE_FIELDS = [
    Field("expense_no", "\u62a5\u9500\u5355\u53f7", "textfield", required=True,
          readonly=True, description="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210"),
    Field("expense_title", "\u62a5\u9500\u4e8b\u9879", "textfield", required=True),
    Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield",
          description="\u586b\u5199\u540e\u53ef\u56de\u5199\u9879\u76ee\u6210\u672c"),
    Field("project_name", "\u5173\u8054\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield",
          description="\u586b\u5199\u540e\u53ef\u56de\u5199\u9884\u7b97\u6267\u884c"),
    Field("contract_no", "\u5173\u8054\u5408\u540c\u7f16\u53f7", "textfield",
          description="\u5408\u540c\u4ed8\u6b3e\u7c7b\u62a5\u9500\u5fc5\u586b"),
    Field("expense_type", "\u62a5\u9500\u7c7b\u578b", "dict", code="expenseType", required=True),
    Field("applicant", "\u62a5\u9500\u4eba", "org", required=True),
    Field("apply_dept", "\u6240\u5728\u90e8\u95e8", "org"),
    Field("apply_date", "\u7533\u8bf7\u65e5\u671f", "calendar", required=True),
    Field("total_amount", "\u62a5\u9500\u603b\u91d1\u989d\uff08\u5143\uff09", "currency",
          required=True, readonly=True, description="\u7531\u660e\u7ec6\u81ea\u52a8\u6c47\u603b"),
    Field("amount_upper", "\u91d1\u989d\u5927\u5199", "textfield", readonly=True),
    Field("expense_reason", "\u62a5\u9500\u4e8b\u7531", "textarea", required=True),
    Field("payee_name", "\u6536\u6b3e\u4eba/\u5355\u4f4d", "textfield"),
    Field("payee_bank", "\u5f00\u6237\u94f6\u884c", "textfield"),
    Field("payee_account", "\u6536\u6b3e\u8d26\u53f7", "textfield"),
]

EXPENSE_DATAGRID = {
    "id": "dg_expense",
    "name": "\u62a5\u9500\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("expense_date", "\u8d39\u7528\u53d1\u751f\u65e5\u671f", "calendar", description="120px"),
        Field("expense_type", "\u8d39\u7528\u7c7b\u578b", "select",
              options=["差旅费", "会议费", "办公费", "材料费", "设备费",
                       "劳务费", "咨询费", "测试化验费", "委托业务费", "其他费用"],
              description="120px"),
        Field("expense_desc", "\u8d39\u7528\u8bf4\u660e", "textfield", description="200px"),
        Field("amount", "\u91d1\u989d\uff08\u5143\uff09", "currency", description="120px"),
        Field("invoice_no", "\u53d1\u7968\u53f7", "textfield", description="140px"),
        Field("remark", "\u5907\u6ce8", "textfield", description="140px"),
    ],
}

FORM_EXPENSE = FormBuilder(
    FORM_EXPENSE_ID, "\u8d39\u7528\u62a5\u9500\u5355",
    "\u8d39\u7528\u62a5\u9500\u7533\u8bf7\u4e0e\u5ba1\u6279\uff0c\u652f\u6301\u9879\u76ee/\u9884\u7b97/\u5408\u540c\u5173\u8054",
    fields=EXPENSE_FIELDS,
    datagrids=[EXPENSE_DATAGRID],
)

# ---- 2. 借款申请表单 ----
FORM_LOAN_ID = "f4004002-finance-loan-form-000000000001"

FORM_LOAN = FormBuilder(
    FORM_LOAN_ID, "\u501f\u6b3e\u7533\u8bf7\u5355",
    "\u5907\u7528\u91d1\u501f\u6b3e\u4e0e\u5f52\u8fd8\u7533\u8bf7",
    fields=[
        Field("loan_no", "\u501f\u6b3e\u5355\u53f7", "textfield", readonly=True),
        Field("borrower", "\u501f\u6b3e\u4eba", "org", required=True),
        Field("borrow_dept", "\u6240\u5728\u90e8\u95e8", "org"),
        Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield"),
        Field("loan_type", "\u501f\u6b3e\u7c7b\u578b", "select",
              options=["差旅备用金", "采购备用金", "会议备用金", "其他借款"]),
        Field("loan_amount", "\u501f\u6b3e\u91d1\u989d\uff08\u5143\uff09", "currency", required=True),
        Field("loan_purpose", "\u501f\u6b3e\u7528\u9014", "textarea", required=True),
        Field("plan_return_date", "\u8ba1\u5212\u5f52\u8fd8\u65e5\u671f", "calendar"),
        Field("loan_status", "\u501f\u6b3e\u72b6\u6001", "select",
              options=["待审批", "已借款", "部分归还", "已归还"]),
    ],
)

# ---- 3. 财务付款申请表单 ----
FORM_PAYMENT_ID = "f4004003-finance-payment-form-000000001"

PAYMENT_FIELDS = [
    Field("payment_no", "\u4ed8\u6b3e\u5355\u53f7", "textfield", readonly=True),
    Field("payment_title", "\u4ed8\u6b3e\u4e8b\u9879", "textfield", required=True),
    Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield"),
    Field("project_name", "\u5173\u8054\u9879\u76ee\u540d\u79f0", "textfield", readonly=True),
    Field("budget_no", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", "textfield"),
    Field("contract_no", "\u5173\u8054\u5408\u540c\u7f16\u53f7", "textfield"),
    Field("pay_type", "\u4ed8\u6b3e\u7c7b\u578b", "dict", code="payType", required=True),
    Field("payee_name", "\u6536\u6b3e\u5355\u4f4d", "textfield", required=True),
    Field("payee_bank", "\u5f00\u6237\u94f6\u884c", "textfield"),
    Field("payee_account", "\u6536\u6b3e\u8d26\u53f7", "textfield"),
    Field("payment_amount", "\u4ed8\u6b3e\u91d1\u989d\uff08\u5143\uff09", "currency", required=True),
    Field("payment_desc", "\u4ed8\u6b3e\u4f9d\u636e", "textarea", required=True),
    Field("plan_pay_date", "\u8ba1\u5212\u4ed8\u6b3e\u65e5\u671f", "calendar"),
    Field("actual_pay_date", "\u5b9e\u9645\u4ed8\u6b3e\u65e5\u671f", "calendar"),
    Field("voucher_no", "\u4f1a\u8ba1\u51ed\u8bc1\u53f7", "textfield"),
]

FORM_PAYMENT = FormBuilder(
    FORM_PAYMENT_ID, "\u8d22\u52a1\u4ed8\u6b3e\u7533\u8bf7\u5355",
    "\u8d22\u52a1\u4ed8\u6b3e\u7533\u8bf7\u4e0e\u5ba1\u6279",
    fields=PAYMENT_FIELDS,
)

# ---- 4. 会计记账凭证表单 ----
FORM_VOUCHER_ID = "f4004004-finance-voucher-form-00000001"

FORM_VOUCHER = FormBuilder(
    FORM_VOUCHER_ID, "\u4f1a\u8ba1\u8bb0\u8d26\u51ed\u8bc1\u8868",
    "\u4f1a\u8ba1\u51ed\u8bc1\u5236\u5355\u4e0e\u767b\u8d26",
    fields=[
        Field("voucher_no", "\u51ed\u8bc1\u53f7", "textfield", required=True),
        Field("voucher_date", "\u51ed\u8bc1\u65e5\u671f", "calendar", required=True),
        Field("voucher_type", "\u51ed\u8bc1\u7c7b\u578b", "select",
              options=["收款凭证", "付款凭证", "转账凭证"]),
        Field("summary", "\u6458\u8981", "textfield", required=True),
        Field("project_no", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", "textfield"),
        Field("debit_total", "\u501f\u65b9\u5408\u8ba1\uff08\u5143\uff09", "currency"),
        Field("credit_total", "\u8d37\u65b9\u5408\u8ba1\uff08\u5143\uff09", "currency"),
        Field("maker", "\u5236\u5355\u4eba", "org"),
        Field("auditor", "\u5ba1\u6838\u4eba", "org"),
        Field("poster", "\u8bb0\u8d26\u4eba", "org"),
    ],
)

VOUCHER_DATAGRID = {
    "id": "dg_voucher",
    "name": "\u5206\u5f55\u660e\u7ec6",
    "isTotal": True,
    "columns": [
        Field("__idx__", "\u5e8f\u53f7"),
        Field("summary_line", "\u6458\u8981", "textfield", description="200px"),
        Field("account_subject", "\u4f1a\u8ba1\u79d1\u76ee", "textfield", description="160px"),
        Field("debit_amount", "\u501f\u65b9\u91d1\u989d\uff08\u5143\uff09", "currency", description="130px"),
        Field("credit_amount", "\u8d37\u65b9\u91d1\u989d\uff08\u5143\uff09", "currency", description="130px"),
    ],
}

FORM_VOUCHER_REAL = FormBuilder(
    FORM_VOUCHER_ID, "\u4f1a\u8ba1\u8bb0\u8d26\u51ed\u8bc1\u8868",
    "\u4f1a\u8ba1\u51ed\u8bc1\u5236\u5355\u4e0e\u767b\u8d26",
    fields=FORM_VOUCHER.fields,
    datagrids=[VOUCHER_DATAGRID],
)

# ---- 5. 财务分析报告表单 ----
FORM_ANALYSIS_ID = "f4004005-finance-analysis-form-0000001"

FORM_ANALYSIS = FormBuilder(
    FORM_ANALYSIS_ID, "\u8d22\u52a1\u5206\u6790\u62a5\u544a\u8868",
    "\u8d22\u52a1\u652f\u51fa\u5206\u6790\u4e0e\u51b3\u7b56\u652f\u6301",
    fields=[
        Field("analysis_period", "\u5206\u6790\u671f\u95f4", "textfield", required=True),
        Field("analysis_type", "\u5206\u6790\u7c7b\u578b", "select",
              options=["月度分析", "季度分析", "年度分析", "专项分析"]),
        Field("total_income", "\u6536\u5165\u5408\u8ba1\uff08\u5143\uff09", "currency"),
        Field("total_expense", "\u652f\u51fa\u5408\u8ba1\uff08\u5143\uff09", "currency"),
        Field("balance", "\u6536\u652f\u7ed3\u4f59\uff08\u5143\uff09", "currency"),
        Field("budget_exec_rate", "\u9884\u7b97\u6267\u884c\u7387\uff08%\uff09", "number"),
        Field("analysis_desc", "\u8d22\u52a1\u5206\u6790", "textarea", required=True),
        Field("suggestion", "\u5efa\u8bae\u4e0e\u63aa\u65bd", "textarea"),
    ],
)

# ==========================================================================
# 流程
# ==========================================================================

# ---- 1. 费用报销流程（分级审批）----
PROC_EXPENSE_ID = "p4004001-expense-approve-00000000001"

PROC_EXPENSE = ProcessBuilder(
    PROC_EXPENSE_ID, "\u8d39\u7528\u62a5\u9500\u5ba1\u6279\u6d41\u7a0b",
    "\u8d39\u7528\u62a5\u9500\u5206\u7ea7\u5ba1\u6279\u4e0e\u51fa\u7eb3\u652f\u4ed8",
    form_id=FORM_EXPENSE_ID,
    activities=[
        Activity("a_draft", "\u62a5\u9500\u7533\u8bf7", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_manager", "\u5206\u7ba1\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_leader", "\u4e3b\u8981\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", task_script=SCRIPT_FINANCE),
        Activity("a_cashier", "\u51fa\u7eb3\u652f\u4ed8", "manual", task_script=SCRIPT_CASHIER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_dept", "\u63d0\u4ea4\u5ba1\u6279", ""),
        ("a_dept", "a_manager", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_dept", "a_draft", "\u9000\u56de\u4fee\u6539", ""),
        # 金额分级路由：>= 5000 元上报主要领导
        ("a_manager", "a_leader", "\u8d85\u989d\u4e0a\u62a5",
         "return this.data.expense_main.total_amount >= 5000;"),
        ("a_manager", "a_finance", "\u8d22\u52a1\u6838\u5b9e",
         "return this.data.expense_main.total_amount < 5000;"),
        ("a_manager", "a_draft", "\u9a73\u56de", ""),
        ("a_leader", "a_finance", "\u6279\u51c6", ""),
        ("a_finance", "a_cashier", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_finance", "a_draft", "\u4e0d\u901a\u8fc7", ""),
        ("a_cashier", "a_end", "\u652f\u4ed8\u5b8c\u6210", ""),
    ],
)

# ---- 2. 借款审批流程 ----
PROC_LOAN_ID = "p4004002-finance-loan-00000000000001"

PROC_LOAN = ProcessBuilder(
    PROC_LOAN_ID, "\u501f\u6b3e\u5ba1\u6279\u6d41\u7a0b",
    "\u5907\u7528\u91d1\u501f\u6b3e\u7533\u8bf7\u4e0e\u5ba1\u6279",
    form_id=FORM_LOAN_ID,
    activities=[
        Activity("a_draft", "\u501f\u6b3e\u7533\u8bf7", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", task_script=SCRIPT_FINANCE),
        Activity("a_cashier", "\u51fa\u7eb3\u4ed8\u6b3e", "manual", task_script=SCRIPT_CASHIER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_dept", "\u63d0\u4ea4", ""),
        ("a_dept", "a_finance", "\u901a\u8fc7", ""),
        ("a_dept", "a_draft", "\u9000\u56de", ""),
        ("a_finance", "a_cashier", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_cashier", "a_end", "\u4ed8\u6b3e\u5b8c\u6210", ""),
    ],
)

# ---- 3. 财务付款审批流程 ----
PROC_PAYMENT_ID = "p4004003-finance-payment-00000000001"

PROC_PAYMENT = ProcessBuilder(
    PROC_PAYMENT_ID, "\u8d22\u52a1\u4ed8\u6b3e\u5ba1\u6279\u6d41\u7a0b",
    "\u8d22\u52a1\u4ed8\u6b3e\u7533\u8bf7\u3001\u5ba1\u6279\u4e0e\u6267\u884c",
    form_id=FORM_PAYMENT_ID,
    activities=[
        Activity("a_draft", "\u4ed8\u6b3e\u7533\u8bf7", "manual", task_script="return this.workContext.getWork().creatorIdentityDn;"),
        Activity("a_dept", "\u90e8\u95e8\u5ba1\u6838", "manual", task_script=SCRIPT_DEPT_LEADER),
        Activity("a_finance", "\u8d22\u52a1\u5ba1\u6838", "manual", task_script=SCRIPT_FINANCE),
        Activity("a_leader", "\u9886\u5bfc\u5ba1\u6279", "manual", task_script=SCRIPT_LEADER),
        Activity("a_cashier", "\u51fa\u7eb3\u4ed8\u6b3e", "manual", task_script=SCRIPT_CASHIER),
        Activity("a_end", "\u7ed3\u675f", "end"),
    ],
    routes=[
        ("a_draft", "a_dept", "\u63d0\u4ea4", ""),
        ("a_dept", "a_finance", "\u901a\u8fc7", ""),
        ("a_dept", "a_draft", "\u9000\u56de", ""),
        ("a_finance", "a_leader", "\u5ba1\u6838\u901a\u8fc7", ""),
        ("a_leader", "a_cashier", "\u6279\u51c6", ""),
        ("a_leader", "a_draft", "\u4e0d\u6279\u51c6", ""),
        ("a_cashier", "a_end", "\u4ed8\u6b3e\u5b8c\u6210", ""),
    ],
)

# ==========================================================================
# 视图
# ==========================================================================

VIEW_EXPENSE_LIST_ID = "v4004001-expense-list-view-000000000001"
VIEW_PAYMENT_LIST_ID = "v4004002-payment-list-view-00000000001"
VIEW_LOAN_LIST_ID = "v4004003-loan-list-view-0000000000001"
VIEW_VOUCHER_LIST_ID = "v4004004-voucher-list-view-0000000001"

VIEWS = [
    view(VIEW_EXPENSE_LIST_ID, "\u62a5\u9500\u53f0\u8d26\u89c6\u56fe",
         "\u5168\u91cf\u8d39\u7528\u62a5\u9500\u8bb0\u5f55",
         source="process", process_list=[PROC_EXPENSE_ID],
         columns=[
             ("\u62a5\u9500\u5355\u53f7", "expense_no", "130px"),
             ("\u62a5\u9500\u4e8b\u9879", "expense_title", "200px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u5173\u8054\u9884\u7b97\u7f16\u53f7", "budget_no", "130px"),
             ("\u5173\u8054\u5408\u540c\u7f16\u53f7", "contract_no", "130px"),
             ("\u62a5\u9500\u7c7b\u578b", "expense_type", "110px"),
             ("\u62a5\u9500\u4eba", "applicant", "110px"),
             ("\u62a5\u9500\u603b\u91d1\u989d", "total_amount", "130px"),
             ("\u7533\u8bf7\u65e5\u671f", "apply_date", "110px"),
         ]),
    view(VIEW_PAYMENT_LIST_ID, "\u4ed8\u6b3e\u53f0\u8d26\u89c6\u56fe",
         "\u8d22\u52a1\u4ed8\u6b3e\u8bb0\u5f55",
         source="process", process_list=[PROC_PAYMENT_ID],
         columns=[
             ("\u4ed8\u6b3e\u5355\u53f7", "payment_no", "130px"),
             ("\u4ed8\u6b3e\u4e8b\u9879", "payment_title", "200px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u5173\u8054\u5408\u540c\u7f16\u53f7", "contract_no", "130px"),
             ("\u4ed8\u6b3e\u7c7b\u578b", "pay_type", "110px"),
             ("\u6536\u6b3e\u5355\u4f4d", "payee_name", "180px"),
             ("\u4ed8\u6b3e\u91d1\u989d", "payment_amount", "130px"),
             ("\u5b9e\u9645\u4ed8\u6b3e\u65e5", "actual_pay_date", "120px"),
         ]),
    view(VIEW_LOAN_LIST_ID, "\u501f\u6b3e\u53f0\u8d26\u89c6\u56fe",
         "\u5907\u7528\u91d1\u501f\u6b3e\u4e0e\u5f52\u8fd8\u8bb0\u5f55",
         source="process", process_list=[PROC_LOAN_ID],
         columns=[
             ("\u501f\u6b3e\u5355\u53f7", "loan_no", "130px"),
             ("\u501f\u6b3e\u4eba", "borrower", "110px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u501f\u6b3e\u7c7b\u578b", "loan_type", "120px"),
             ("\u501f\u6b3e\u91d1\u989d", "loan_amount", "130px"),
             ("\u8ba1\u5212\u5f52\u8fd8\u65e5", "plan_return_date", "120px"),
             ("\u501f\u6b3e\u72b6\u6001", "loan_status", "100px"),
         ]),
    view(VIEW_VOUCHER_LIST_ID, "\u4f1a\u8ba1\u51ed\u8bc1\u53f0\u8d26",
         "\u4f1a\u8ba1\u51ed\u8bc1\u8bb0\u5f55",
         source="process", process_list=[PROC_PAYMENT_ID],
         columns=[
             ("\u51ed\u8bc1\u53f7", "voucher_no", "120px"),
             ("\u51ed\u8bc1\u65e5\u671f", "voucher_date", "110px"),
             ("\u51ed\u8bc1\u7c7b\u578b", "voucher_type", "110px"),
             ("\u6458\u8981", "summary", "220px"),
             ("\u5173\u8054\u9879\u76ee\u7f16\u53f7", "project_no", "130px"),
             ("\u4ed8\u6b3e\u91d1\u989d", "payment_amount", "130px"),
             ("\u5b9e\u9645\u4ed8\u6b3e\u65e5", "actual_pay_date", "120px"),
         ]),
]

# ==========================================================================
# 自建表
# ==========================================================================

TABLE_EXPENSE_MASTER_ID = "t4004001-expense-master-table-00000001"
TABLE_PAYMENT_MASTER_ID = "t4004002-payment-master-table-00000001"
TABLE_COST_SUMMARY_ID = "t4004003-cost-summary-table-000000001"

TABLES = [
    table(TABLE_EXPENSE_MASTER_ID, "\u62a5\u9500\u4e3b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("expense_no", "string", "\u62a5\u9500\u5355\u53f7", 64),
              ("expense_title", "string", "\u62a5\u9500\u4e8b\u9879", 255),
              ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
              ("budget_no", "string", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", 64),
              ("contract_no", "string", "\u5173\u8054\u5408\u540c\u7f16\u53f7", 64),
              ("expense_type", "string", "\u62a5\u9500\u7c7b\u578b", 64),
              ("applicant", "string", "\u62a5\u9500\u4eba", 255),
              ("apply_dept", "string", "\u6240\u5728\u90e8\u95e8", 255),
              ("apply_date", "date", "\u7533\u8bf7\u65e5\u671f", 0),
              ("total_amount", "number", "\u62a5\u9500\u603b\u91d1\u989d", 0),
              ("payee_name", "string", "\u6536\u6b3e\u4eba", 255),
              ("pay_status", "string", "\u652f\u4ed8\u72b6\u6001", 32),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
              ("create_time", "datetime", "\u521b\u5efa\u65f6\u95f4", 0),
          ],
          "\u62a5\u9500\u4e3b\u6570\u636e\uff0c\u4e0e\u9879\u76ee/\u9884\u7b97/\u5408\u540c\u5e94\u7528\u5171\u4eab"),
    table(TABLE_PAYMENT_MASTER_ID, "\u4ed8\u6b3e\u4e3b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("payment_no", "string", "\u4ed8\u6b3e\u5355\u53f7", 64),
              ("payment_title", "string", "\u4ed8\u6b3e\u4e8b\u9879", 255),
              ("project_no", "string", "\u5173\u8054\u9879\u76ee\u7f16\u53f7", 64),
              ("budget_no", "string", "\u5173\u8054\u9884\u7b97\u7f16\u53f7", 64),
              ("contract_no", "string", "\u5173\u8054\u5408\u540c\u7f16\u53f7", 64),
              ("pay_type", "string", "\u4ed8\u6b3e\u7c7b\u578b", 32),
              ("payee_name", "string", "\u6536\u6b3e\u5355\u4f4d", 255),
              ("payment_amount", "number", "\u4ed8\u6b3e\u91d1\u989d", 0),
              ("plan_pay_date", "date", "\u8ba1\u5212\u4ed8\u6b3e\u65e5", 0),
              ("actual_pay_date", "date", "\u5b9e\u9645\u4ed8\u6b3e\u65e5", 0),
              ("voucher_no", "string", "\u4f1a\u8ba1\u51ed\u8bc1\u53f7", 64),
              ("process_id", "string", "\u5173\u8054\u6d41\u7a0b\u5b9e\u4f8bID", 64),
          ],
          "\u4ed8\u6b3e\u4e3b\u6570\u636e\uff0c\u652f\u6301\u9884\u7b97\u6267\u884c\u4e0e\u6210\u672c\u5f52\u96c6"),
    table(TABLE_COST_SUMMARY_ID, "\u9879\u76ee\u6210\u672c\u6c47\u603b\u8868",
          [
              ("id", "string", "\u4e3b\u952eID", 64),
              ("project_no", "string", "\u9879\u76ee\u7f16\u53f7", 64),
              ("project_name", "string", "\u9879\u76ee\u540d\u79f0", 255),
              ("budget_total", "number", "\u9884\u7b97\u603b\u989d", 0),
              ("expense_total", "number", "\u62a5\u9500\u5408\u8ba1", 0),
              ("payment_total", "number", "\u4ed8\u6b3e\u5408\u8ba1", 0),
              ("actual_cost", "number", "\u5b9e\u9645\u6210\u672c", 0),
              ("variance", "number", "\u504f\u5dee", 0),
              ("variance_rate", "number", "\u504f\u5dee\u7387", 0),
              ("update_time", "datetime", "\u66f4\u65b0\u65f6\u95f4", 0),
          ],
          "\u9879\u76ee\u6210\u672c\u5f52\u96c6\u6c47\u603b\uff0c\u4f9b\u9879\u76ee\u5e94\u7528\u6210\u672c\u6838\u7b97\u4f7f\u7528"),
]

STATS = [
    stat("s4004001-expense-type-stat-00000000001",
         "\u62a5\u9500\u7c7b\u578b\u5206\u5e03\u7edf\u8ba1", VIEW_EXPENSE_LIST_ID,
         "expense_type", "total_amount",
         "\u6309\u62a5\u9500\u7c7b\u578b\u7edf\u8ba1\u91d1\u989d",
         category_title="\u62a5\u9500\u7c7b\u578b", value_title="\u62a5\u9500\u91d1\u989d"),
    stat("s4004002-expense-dept-stat-000000000001",
         "\u90e8\u95e8\u62a5\u9500\u7edf\u8ba1", VIEW_EXPENSE_LIST_ID,
         "apply_dept", "total_amount",
         "\u6309\u90e8\u95e8\u7edf\u8ba1\u62a5\u9500\u91d1\u989d",
         category_title="\u90e8\u95e8", value_title="\u62a5\u9500\u91d1\u989d"),
    stat("s4004003-expense-project-stat-0000000001",
         "\u9879\u76ee\u62a5\u9500\u7edf\u8ba1", VIEW_EXPENSE_LIST_ID,
         "project_no", "total_amount",
         "\u6309\u9879\u76ee\u7edf\u8ba1\u62a5\u9500\u91d1\u989d",
         category_title="\u9879\u76ee\u7f16\u53f7", value_title="\u62a5\u9500\u91d1\u989d"),
    stat("s4004004-payment-type-stat-00000000001",
         "\u4ed8\u6b3e\u7c7b\u578b\u7edf\u8ba1", VIEW_PAYMENT_LIST_ID,
         "pay_type", "payment_amount",
         "\u6309\u4ed8\u6b3e\u7c7b\u578b\u7edf\u8ba1\u91d1\u989d",
         category_title="\u4ed8\u6b3e\u7c7b\u578b", value_title="\u4ed8\u6b3e\u91d1\u989d"),
]

STATEMENTS = [
    statement(
        "q4004001-project-cost-summary-0000000001",
        "\u9879\u76ee\u6210\u672c\u6c47\u603b\u67e5\u8be2",
        "SELECT p.project_no, p.project_name, p.total_budget, "
        "SUM(e.total_amount) AS expense_total, "
        "SUM(e.total_amount) - p.total_budget AS variance, "
        "ROUND((SUM(e.total_amount) - p.total_budget) * 100.0 / p.total_budget, 2) AS variance_rate "
        "FROM \u9879\u76ee\u4e3b\u8868 p LEFT JOIN \u62a5\u9500\u4e3b\u8868 e "
        "ON p.project_no = e.project_no GROUP BY p.project_no",
        "\u6309\u9879\u76ee\u6c47\u603b\u62a5\u9500\u6210\u672c\u5e76\u8ba1\u7b97\u504f\u5dee\u7387"),
    statement(
        "q4004002-budget-exec-check-00000000000001",
        "\u9884\u7b97\u6267\u884c\u6838\u67e5",
        "SELECT b.budget_no, b.budget_name, b.total_amount AS budget_amount, "
        "SUM(e.total_amount) AS expense_amount, "
        "b.total_amount - SUM(e.total_amount) AS remain "
        "FROM \u9884\u7b97\u4e3b\u8868 b LEFT JOIN \u62a5\u9500\u4e3b\u8868 e "
        "ON b.budget_no = e.budget_no GROUP BY b.budget_no",
        "\u6838\u67e5\u9884\u7b97\u4f59\u989d\uff0c\u9632\u6b62\u8d85\u9884\u7b97\u652f\u51fa"),
    statement(
        "q4004003-contract-pay-check-0000000000001",
        "\u5408\u540c\u4ed8\u6b3e\u6838\u67e5",
        "SELECT c.contract_no, c.contract_name, c.contract_amount, "
        "SUM(p.payment_amount) AS paid_total "
        "FROM \u5408\u540c\u4e3b\u8868 c LEFT JOIN \u4ed8\u6b3e\u4e3b\u8868 p "
        "ON c.contract_no = p.contract_no GROUP BY c.contract_no",
        "\u6838\u67e5\u5408\u540c\u5df2\u4ed8\u91d1\u989d\uff0c\u9632\u6b62\u8d85\u5408\u540c\u4ed8\u6b3e"),
]

FORMS = [FORM_EXPENSE, FORM_LOAN, FORM_PAYMENT, FORM_VOUCHER_REAL, FORM_ANALYSIS]
PROCESSES = [PROC_EXPENSE, PROC_LOAN, PROC_PAYMENT]
