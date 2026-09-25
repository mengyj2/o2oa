# -*- coding: utf-8 -*-
"""
业务管理门户（跨应用聚合门户）
==============================

背景（2026-09-21）
------------------
01 项目管理 / 03 预算管理 / 04 财务管理 / 05 档案管理 四个应用此前**没有门户**，
用户只能从「流程应用工作台」进入（业务可办，但没有首页看板）。

按 OA 系统惯例，这里**不建 4 个孤立门户**，而是建 1 个聚合门户，
内部按业务域分类成 5 个栏目页（首页 + 四大业务），横向导航切换。
门户分类 portalCategory = 「业务管理」，与既有「综合管理」门户并列。

栏目页结构（OA 惯例：一级导航横向 Tab）
--------------------------------------
    首页 → 项目管理 → 预算管理 → 财务管理 → 档案管理 → 个人设置

数据通路：全部走 `table_holder` 直读自建表行接口（本版本视图引擎不支持
table 类型视图，详见技能 o2oa-portal-page-format 第 8 章）。

载体应用：本门户随 **01 项目管理应用** 打包（.xapp 的 portalList）。
门户展示其他应用的表/流程是允许的 —— 门户只是展示层，不做数据归属校验。
"""

import o2oa_portal as _PT
import o2oa_hr_portal as _HP
from o2oa_builder import portal, portal_page

# ==========================================================================
# 门户与页面 ID（沿用项目规范 o<8位序号>-<slug>-<补齐>）
# ==========================================================================
PORTAL_ID = "o1001001-biz-portal-000000000000000001"
PAGE_HOME_ID = "o1001002-biz-portal-home-page-00000001"
PAGE_PROJECT_ID = "o1001003-biz-portal-project-page-000001"
PAGE_BUDGET_ID = "o1001004-biz-portal-budget-page-0000001"
PAGE_FINANCE_ID = "o1001005-biz-portal-finance-page-0000001"
PAGE_ARCHIVE_ID = "o1001006-biz-portal-archive-page-0000001"

PORTAL_NAME = "业务管理门户"
PORTAL_CATEGORY = "业务管理"

# ==========================================================================
# 自建表 flag（来自各应用 def_*.py 的 TABLE_*_ID 常量）
# ==========================================================================
TABLE_PROJECT_MASTER = "t1001001-project-master-table-00000001"
TABLE_BUDGET_MASTER = "t3003001-budget-master-table-000000001"
TABLE_BUDGET_DETAIL = "t3003002-budget-detail-table-000000001"
TABLE_EXPENSE_MASTER = "t4004001-expense-master-table-00000001"
TABLE_PAYMENT_MASTER = "t4004002-payment-master-table-00000001"
TABLE_COST_SUMMARY = "t4004003-cost-summary-table-000000001"
TABLE_ARCHIVE_MASTER = "t5005001-archive-master-table-00000001"
TABLE_ARCHIVE_BORROW = "t5005002-archive-borrow-table-00000001"

# ==========================================================================
# 流程 id（用于「一键发起」按钮）
# ==========================================================================
PROC_PROJECT_APPROVE = "p1001001-project-approve-0000000000001"
PROC_PROJECT_PROGRESS = "p1001002-project-progress-0000000000001"
PROC_PROJECT_CLOSE = "p1001005-project-close-000000000000001"
PROC_PROJECT_CHANGE = "p1001006-project-change-00000000000001"
PROC_BUDGET_APPROVE = "p3003001-budget-approve-0000000000001"
PROC_BUDGET_ADJUST = "p3003002-budget-adjust-00000000000001"
PROC_EXPENSE = "p4004001-expense-approve-00000000001"
PROC_LOAN = "p4004002-finance-loan-00000000000001"
PROC_PAYMENT = "p4004003-finance-payment-00000000001"
PROC_ARCHIVE_CATALOG = "p5005001-archive-catalog-00000000000001"
PROC_ARCHIVE_BORROW = "p5005002-archive-borrow-0000000000001"
PROC_ARCHIVE_DISPOSE = "p5005003-archive-dispose-000000000001"

# ==========================================================================
# 一级导航（OA 惯例：横向 Tab）
# ==========================================================================
NAV = [
    "\u9996\u9875", "\u9879\u76ee\u7ba1\u7406", "\u9884\u7b97\u7ba1\u7406",
    "\u8d22\u52a1\u7ba1\u7406", "\u6863\u6848\u7ba1\u7406", "\u4e2a\u4eba\u8bbe\u7f6e",
]
NAV_HOME, NAV_PROJECT, NAV_BUDGET, NAV_FINANCE, NAV_ARCHIVE, NAV_PROFILE = NAV

NAV_TARGETS = {
    NAV_HOME: (PORTAL_ID, PAGE_HOME_ID),
    NAV_PROJECT: (PORTAL_ID, PAGE_PROJECT_ID),
    NAV_BUDGET: (PORTAL_ID, PAGE_BUDGET_ID),
    NAV_FINANCE: (PORTAL_ID, PAGE_FINANCE_ID),
    NAV_ARCHIVE: (PORTAL_ID, PAGE_ARCHIVE_ID),
    NAV_PROFILE: ("profile",),
}

BRAND = "\u4e1a\u52a1\u7ba1\u7406\u7cfb\u7edf"

# 顶栏日期（与 HR/合同门户同风格；门户是静态页，日期取交付日）
DATE_TEXT = "2026\u5e7409\u670821\u65e5(\u5468\u4e00)"

# ==========================================================================
# 首页：四大业务总览（KPI + 各域数据表）
# ==========================================================================
PAGE_HOME_HTML = _HP.biz_view_page_html(
    "\u4e1a\u52a1\u603b\u89c8",
    BRAND, NAV, NAV_TARGETS,
    subtitle="\u9879\u76ee / \u9884\u7b97 / \u8d22\u52a1 / \u6863\u6848 \u56db\u5927\u4e1a\u52a1\u5b9e\u65f6\u6570\u636e",
    nav_active=0,
    sections=[
        ("\u5728\u5efa\u9879\u76ee\u6e05\u5355", TABLE_PROJECT_MASTER, [
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("project_name", "\u9879\u76ee\u540d\u79f0"),
            ("project_type", "\u7c7b\u522b"),
            ("project_status", "\u72b6\u6001"),
            ("dept_name", "\u4e3b\u529e\u90e8\u95e8"),
            ("manager", "\u8d1f\u8d23\u4eba"),
            ("total_budget", "\u603b\u9884\u7b97", "money"),
            ("start_date", "\u5f00\u59cb\u65e5\u671f", "date"),
            ("end_date", "\u7ed3\u675f\u65e5\u671f", "date"),
        ], 330),
        ("\u9884\u7b97\u6267\u884c\u603b\u89c8", TABLE_BUDGET_MASTER, [
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("budget_name", "\u9884\u7b97\u540d\u79f0"),
            ("budget_type", "\u9884\u7b97\u7c7b\u578b"),
            ("budget_year", "\u5e74\u5ea6"),
            ("dept_name", "\u90e8\u95e8"),
            ("total_amount", "\u9884\u7b97\u91d1\u989d", "money"),
            ("executed_amount", "\u5df2\u6267\u884c", "money"),
            ("remain_amount", "\u5269\u4f59", "money"),
            ("exec_rate", "\u6267\u884c\u7387"),
            ("budget_status", "\u72b6\u6001"),
        ], 330),
        ("\u8d39\u7528\u62a5\u9500\u53f0\u8d26", TABLE_EXPENSE_MASTER, [
            ("expense_no", "\u62a5\u9500\u5355\u53f7"),
            ("expense_title", "\u4e8b\u7531"),
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("expense_type", "\u8d39\u7528\u7c7b\u578b"),
            ("applicant", "\u7533\u8bf7\u4eba"),
            ("total_amount", "\u91d1\u989d", "money"),
            ("pay_status", "\u72b6\u6001"),
        ], 300),
        ("\u6863\u6848\u53f0\u8d26", TABLE_ARCHIVE_MASTER, [
            ("archive_no", "\u6863\u6848\u7f16\u53f7"),
            ("archive_name", "\u6863\u6848\u540d\u79f0"),
            ("archive_type", "\u7c7b\u578b"),
            ("archive_level", "\u5bc6\u7ea7"),
            ("archive_state", "\u72b6\u6001"),
            ("source_app", "\u6765\u6e90\u5e94\u7528"),
            ("project_no", "\u5173\u8054\u9879\u76ee"),
            ("archive_year", "\u5e74\u5ea6"),
            ("storage_location", "\u5b58\u653e\u4f4d\u7f6e"),
        ], 300),
    ],
    date_text=DATE_TEXT,
)

# ==========================================================================
# 项目管理栏目
# ==========================================================================
PAGE_PROJECT_HTML = _HP.biz_view_page_html(
    "\u9879\u76ee\u7ba1\u7406",
    BRAND, NAV, NAV_TARGETS,
    subtitle="\u9879\u76ee\u53f0\u8d26\u4e0e\u5168\u5468\u671f\u6d41\u7a0b\u5165\u53e3",
    nav_active=1,
    sections=[
        ("\u9879\u76ee\u53f0\u8d26", TABLE_PROJECT_MASTER, [
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("project_name", "\u9879\u76ee\u540d\u79f0"),
            ("project_type", "\u7c7b\u522b"),
            ("project_level", "\u7ea7\u522b"),
            ("project_status", "\u72b6\u6001"),
            ("dept_name", "\u4e3b\u529e\u90e8\u95e8"),
            ("manager", "\u9879\u76ee\u8d1f\u8d23\u4eba"),
            ("fund_source", "\u8d44\u91d1\u6765\u6e90"),
            ("contract_no", "\u5173\u8054\u5408\u540c"),
            ("budget_no", "\u5173\u8054\u9884\u7b97"),
            ("total_budget", "\u603b\u9884\u7b97", "money"),
            ("start_date", "\u5f00\u59cb\u65e5\u671f", "date"),
            ("end_date", "\u7ed3\u675f\u65e5\u671f", "date"),
            ("project_goal", "\u9879\u76ee\u76ee\u6807"),
        ], 430),
        ("\u9879\u76ee\u6210\u672c\u6838\u7b97", TABLE_COST_SUMMARY, [
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("project_name", "\u9879\u76ee\u540d\u79f0"),
            ("budget_total", "\u9884\u7b97\u603b\u989d", "money"),
            ("expense_total", "\u62a5\u9500\u603b\u989d", "money"),
            ("payment_total", "\u4ed8\u6b3e\u603b\u989d", "money"),
            ("actual_cost", "\u5b9e\u9645\u6210\u672c", "money"),
            ("variance", "\u504f\u5dee", "money"),
            ("variance_rate", "\u504f\u5dee\u7387"),
        ], 300),
    ],
    actions=[
        ("\u9879\u76ee\u7acb\u9879\u7533\u8bf7", "startone", PROC_PROJECT_APPROVE, False),
        ("\u8fdb\u5ea6\u98ce\u9669\u8bc4\u5ba1", "startone", PROC_PROJECT_PROGRESS, True),
        ("\u9879\u76ee\u53d8\u66f4", "startone", PROC_PROJECT_CHANGE, True),
        ("\u9879\u76ee\u7ed3\u9879", "startone", PROC_PROJECT_CLOSE, True),
    ],
    date_text=DATE_TEXT,
)

# ==========================================================================
# 预算管理栏目
# ==========================================================================
PAGE_BUDGET_HTML = _HP.biz_view_page_html(
    "\u9884\u7b97\u7ba1\u7406",
    BRAND, NAV, NAV_TARGETS,
    subtitle="\u9884\u7b97\u7f16\u5236 / \u8c03\u6574 / \u6267\u884c\u76d1\u63a7",
    nav_active=2,
    sections=[
        ("\u9884\u7b97\u53f0\u8d26", TABLE_BUDGET_MASTER, [
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("budget_name", "\u9884\u7b97\u540d\u79f0"),
            ("budget_type", "\u9884\u7b97\u7c7b\u578b"),
            ("budget_year", "\u5e74\u5ea6"),
            ("project_no", "\u5173\u8054\u9879\u76ee"),
            ("dept_name", "\u90e8\u95e8"),
            ("fund_source", "\u8d44\u91d1\u6765\u6e90"),
            ("total_amount", "\u9884\u7b97\u91d1\u989d", "money"),
            ("executed_amount", "\u5df2\u6267\u884c", "money"),
            ("remain_amount", "\u5269\u4f59", "money"),
            ("exec_rate", "\u6267\u884c\u7387"),
            ("budget_status", "\u72b6\u6001"),
        ], 380),
        ("\u9884\u7b97\u660e\u7ec6", TABLE_BUDGET_DETAIL, [
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("expense_type", "\u8d39\u7528\u7c7b\u578b"),
            ("budget_item", "\u9884\u7b97\u79d1\u76ee"),
            ("budget_amount", "\u9884\u7b97\u91d1\u989d", "money"),
            ("exec_amount", "\u5df2\u6267\u884c", "money"),
            ("exec_rate", "\u6267\u884c\u7387"),
        ], 300),
    ],
    actions=[
        ("\u9884\u7b97\u7f16\u5236\u7533\u8bf7", "startone", PROC_BUDGET_APPROVE, False),
        ("\u9884\u7b97\u8c03\u6574", "startone", PROC_BUDGET_ADJUST, True),
    ],
    date_text=DATE_TEXT,
)

# ==========================================================================
# 财务管理栏目
# ==========================================================================
PAGE_FINANCE_HTML = _HP.biz_view_page_html(
    "\u8d22\u52a1\u7ba1\u7406",
    BRAND, NAV, NAV_TARGETS,
    subtitle="\u62a5\u9500 / \u501f\u6b3e / \u4ed8\u6b3e\u5168\u6d41\u7a0b\u53f0\u8d26",
    nav_active=3,
    sections=[
        ("\u8d39\u7528\u62a5\u9500\u53f0\u8d26", TABLE_EXPENSE_MASTER, [
            ("expense_no", "\u62a5\u9500\u5355\u53f7"),
            ("expense_title", "\u62a5\u9500\u4e8b\u7531"),
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("contract_no", "\u5408\u540c\u7f16\u53f7"),
            ("expense_type", "\u8d39\u7528\u7c7b\u578b"),
            ("applicant", "\u7533\u8bf7\u4eba"),
            ("apply_dept", "\u7533\u8bf7\u90e8\u95e8"),
            ("payee_name", "\u6536\u6b3e\u65b9"),
            ("total_amount", "\u62a5\u9500\u91d1\u989d", "money"),
            ("pay_status", "\u72b6\u6001"),
            ("apply_date", "\u7533\u8bf7\u65e5\u671f", "date"),
        ], 360),
        ("\u4ed8\u6b3e\u53f0\u8d26", TABLE_PAYMENT_MASTER, [
            ("payment_no", "\u4ed8\u6b3e\u5355\u53f7"),
            ("payment_title", "\u4ed8\u6b3e\u4e8b\u7531"),
            ("project_no", "\u9879\u76ee\u7f16\u53f7"),
            ("budget_no", "\u9884\u7b97\u7f16\u53f7"),
            ("contract_no", "\u5408\u540c\u7f16\u53f7"),
            ("pay_type", "\u4ed8\u6b3e\u7c7b\u578b"),
            ("payee_name", "\u6536\u6b3e\u65b9"),
            ("payment_amount", "\u4ed8\u6b3e\u91d1\u989d", "money"),
            ("plan_pay_date", "\u8ba1\u5212\u4ed8\u6b3e", "date"),
            ("actual_pay_date", "\u5b9e\u9645\u4ed8\u6b3e", "date"),
        ], 300),
    ],
    actions=[
        ("\u8d39\u7528\u62a5\u9500", "startone", PROC_EXPENSE, False),
        ("\u501f\u6b3e\u7533\u8bf7", "startone", PROC_LOAN, True),
        ("\u8d22\u52a1\u4ed8\u6b3e", "startone", PROC_PAYMENT, True),
    ],
    date_text=DATE_TEXT,
)

# ==========================================================================
# 档案管理栏目
# ==========================================================================
PAGE_ARCHIVE_HTML = _HP.biz_view_page_html(
    "\u6863\u6848\u7ba1\u7406",
    BRAND, NAV, NAV_TARGETS,
    subtitle="\u6863\u6848\u53f0\u8d26 / \u501f\u9605 / \u5f52\u6863\u4e0e\u9500\u6bc1",
    nav_active=4,
    sections=[
        ("\u6863\u6848\u53f0\u8d26", TABLE_ARCHIVE_MASTER, [
            ("archive_no", "\u6863\u6848\u7f16\u53f7"),
            ("archive_name", "\u6863\u6848\u540d\u79f0"),
            ("archive_type", "\u6863\u6848\u7c7b\u578b"),
            ("archive_level", "\u5bc6\u7ea7"),
            ("archive_state", "\u72b6\u6001"),
            ("source_app", "\u6765\u6e90\u5e94\u7528"),
            ("project_no", "\u5173\u8054\u9879\u76ee"),
            ("contract_no", "\u5173\u8054\u5408\u540c"),
            ("fonds_no", "\u5168\u5b97\u53f7"),
            ("archive_year", "\u5e74\u5ea6"),
            ("retention_period", "\u4fdd\u7ba1\u671f\u9650"),
            ("carrier_type", "\u8f7d\u4f53\u7c7b\u578b"),
            ("storage_location", "\u5b58\u653e\u4f4d\u7f6e"),
            ("pages", "\u9875\u6570", "num"),
            ("archive_date", "\u5f52\u6863\u65e5\u671f", "date"),
        ], 400),
        ("\u6863\u6848\u501f\u9605\u8bb0\u5f55", TABLE_ARCHIVE_BORROW, [
            ("borrow_no", "\u501f\u9605\u5355\u53f7"),
            ("archive_no", "\u6863\u6848\u7f16\u53f7"),
            ("borrower", "\u501f\u9605\u4eba"),
            ("borrow_dept", "\u501f\u9605\u90e8\u95e8"),
            ("borrow_type", "\u501f\u9605\u7c7b\u578b"),
            ("borrow_date", "\u501f\u9605\u65e5\u671f", "date"),
            ("plan_return_date", "\u8ba1\u5212\u5f52\u8fd8", "date"),
            ("borrow_status", "\u72b6\u6001"),
            ("borrow_reason", "\u501f\u9605\u4e8b\u7531"),
        ], 300),
    ],
    actions=[
        ("\u6863\u6848\u5f52\u6863", "startone", PROC_ARCHIVE_CATALOG, False),
        ("\u6863\u6848\u501f\u9605", "startone", PROC_ARCHIVE_BORROW, True),
        ("\u79fb\u4ea4\u9500\u6bc1", "startone", PROC_ARCHIVE_DISPOSE, True),
    ],
    date_text=DATE_TEXT,
)


def _pg(pid, name, html, desc):
    """独立 HTML 门户页 -> O2OA 门户页数据（表单定义 JSON）。

    O2OA 把门户页当表单渲染（PortalPage.js -> MWF.APPForm），
    裸 HTML 过不了 JSON.decode，门户里直接白屏。
    """
    return portal_page(pid, name, PORTAL_ID,
                       _PT.portal_page_data(html, pid, name, PORTAL_ID, PORTAL_NAME),
                       description=desc)


PAGES = [
    _pg(PAGE_HOME_ID, "\u4e1a\u52a1\u603b\u89c8", PAGE_HOME_HTML,
        "\u56db\u5927\u4e1a\u52a1\u603b\u89c8\u770b\u677f"),
    _pg(PAGE_PROJECT_ID, "\u9879\u76ee\u7ba1\u7406", PAGE_PROJECT_HTML,
        "\u9879\u76ee\u53f0\u8d26\u4e0e\u6210\u672c\u6838\u7b97"),
    _pg(PAGE_BUDGET_ID, "\u9884\u7b97\u7ba1\u7406", PAGE_BUDGET_HTML,
        "\u9884\u7b97\u53f0\u8d26\u4e0e\u6267\u884c\u76d1\u63a7"),
    _pg(PAGE_FINANCE_ID, "\u8d22\u52a1\u7ba1\u7406", PAGE_FINANCE_HTML,
        "\u62a5\u9500\u4e0e\u4ed8\u6b3e\u53f0\u8d26"),
    _pg(PAGE_ARCHIVE_ID, "\u6863\u6848\u7ba1\u7406", PAGE_ARCHIVE_HTML,
        "\u6863\u6848\u53f0\u8d26\u4e0e\u501f\u9605\u8bb0\u5f55"),
]

PORTAL = portal(
    PORTAL_ID, PORTAL_NAME,
    category=PORTAL_CATEGORY,
    description="\u9879\u76ee / \u9884\u7b97 / \u8d22\u52a1 / \u6863\u6848 "
                "\u56db\u5927\u4e1a\u52a1\u805a\u5408\u95e8\u6237\uff08\u6309\u4e1a\u52a1\u57df\u5206\u7c7b\uff09",
    first_page_id=PAGE_HOME_ID,
    pages=PAGES,
)

PORTALS = [PORTAL]

__all__ = ["PORTALS", "PORTAL", "PORTAL_ID", "PORTAL_NAME", "PORTAL_CATEGORY"]
