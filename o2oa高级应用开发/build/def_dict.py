# -*- coding: utf-8 -*-
"""
O2OA 应用包定义：五大应用 + 公共数据中心
=========================================
本文件定义全部应用的设计元素（流程 / 表单 / 数据字典 / 视图 / 自建表等），
由 pack.py 打包为可导入的 .xapp 文件。

【整体数据联动设计】
核心思路：以"项目"为主线，通过统一的项目编号（project_no）贯穿越
项目、预算、财务、合同、档案五大应用，辅以自建表落地关键业务数据，
实现跨应用的数据共享与联动。

    合同管理 ──签约──▶ 项目建立 ──立项──▶ 预算编制 ──执行──▶ 财务报销/付款
        │                   │                   │              │
        └──归档─────────────┴───────────────────┴──────────────┘
                            ▼
                       档案管理（统一归集）

关键关联字段（全系统统一命名）：
    project_no      项目编号     —— 五大应用共同主键类标识
    project_name    项目名称
    contract_no     合同编号
    budget_no       预算编号
    expense_no      报销/付款单号
    archive_no      档案编号
"""

from o2oa_builder import (
    Field, FormBuilder, Activity, ProcessBuilder,
    dictionary, view, table, stat, statement, importer,
    process_platform, query_application, service_module, wrap_module,
    short_id, o2_datetime,
)

# ==========================================================================
# 全局：统一编码（保证多次运行生成结构一致，便于文档引用）
# ==========================================================================

IDS = {
    # ---- 应用 ----
    "app_process": "3c8f1e02-7b41-4d9a-9e15-8a2c4f6b1001",   # 流程平台应用包
    "app_query": "3c8f1e02-7b41-4d9a-9e15-8a2c4f6b1002",     # 数据中心应用包

    # ---- 数据字典 ----
    "dict_project_type": "d1000001-project-type-dict-000000000001",
    "dict_project_status": "d1000002-project-status-dict-00000000002",
    "dict_currency_unit": "d1000003-currency-unit-dict-00000000003",
    "dict_budget_type": "d1000004-budget-type-dict-0000000000004",
    "dict_expense_type": "d1000005-expense-type-dict-000000000005",
    "dict_pay_type": "d1000006-pay-type-dict-00000000000006",
    "dict_contract_type": "d1000007-contract-type-dict-00000000007",
    "dict_contract_status": "d1000008-contract-status-dict-0000000008",
    "dict_archive_type": "d1000009-archive-type-dict-000000000009",
    "dict_archive_level": "d1000010-archive-level-dict-00000000010",
    "dict_archive_state": "d1000011-archive-state-dict-00000000011",
    "dict_fund_source": "d1000012-fund-source-dict-000000000012",

    # ---- 合同管理应用新增（7 条）----
    "dict_partner_type": "d2002001-partner-type-dict-000000000001",
    "dict_receive_type": "d2002002-receive-type-dict-000000000002",
    "dict_invoice_type": "d2002003-invoice-type-dict-000000000003",
    "dict_change_type": "d2002004-change-type-dict-0000000000004",
    "dict_ticket_type": "d2002005-ticket-type-dict-000000000005",
    "dict_plan_status": "d2002006-plan-status-dict-000000000006",
    "dict_approve_status": "d2002007-approve-status-dict-00000000007",
}

# ==========================================================================
# 一、数据字典定义
# ==========================================================================


# 应用标识
APP_ID_SERVICE = "a0000000-common-dict-app-0000000000001"

# ==========================================================================
# 一、公共数据字典（12 条）
# ==========================================================================
# 说明：这些字典由五个应用共用。
#   - 流程平台内使用：挂载到各 WrapProcessPlatform.applicationDictList
#   - 全局数据：挂载到 WrapServiceModule.dictList（服务管理应用）
# 表单中通过「数据字典下拉」控件引用，引用键是 code。

DICTIONARIES = [
    dictionary(
        IDS["dict_project_type"], "\u9879\u76ee\u7c7b\u522b", "projectType",
        [
            ("\u7814\u53d1\u9879\u76ee", "\u7814\u53d1\u9879\u76ee"),
            ("\u4fe1\u606f\u5316\u9879\u76ee", "\u4fe1\u606f\u5316\u9879\u76ee"),
            ("\u5de5\u7a0b\u5efa\u8bbe\u9879\u76ee", "\u5de5\u7a0b\u5efa\u8bbe\u9879\u76ee"),
            ("\u6807\u51c6\u5316\u9879\u76ee", "\u6807\u51c6\u5316\u9879\u76ee"),
            ("\u8bfe\u9898\u7814\u7a76", "\u8bfe\u9898\u7814\u7a76"),
            ("\u54a8\u8be2\u670d\u52a1", "\u54a8\u8be2\u670d\u52a1"),
            ("\u5176\u4ed6\u9879\u76ee", "\u5176\u4ed6\u9879\u76ee"),
        ],
        "\u9879\u76ee\u7c7b\u522b\u5206\u7c7b"),
    dictionary(
        IDS["dict_project_status"], "\u9879\u76ee\u72b6\u6001", "projectStatus",
        [
            ("\u7b56\u5212\u4e2d", "\u7b56\u5212\u4e2d"),
            ("\u5df2\u7acb\u9879", "\u5df2\u7acb\u9879"),
            ("\u5b9e\u65bd\u4e2d", "\u5b9e\u65bd\u4e2d"),
            ("\u5df2\u6682\u505c", "\u5df2\u6682\u505c"),
            ("\u5df2\u5ef6\u671f", "\u5df2\u5ef6\u671f"),
            ("\u6536\u5c3e\u4e2d", "\u6536\u5c3e\u4e2d"),
            ("\u5df2\u7ed3\u9879", "\u5df2\u7ed3\u9879"),
            ("\u5df2\u7ec8\u6b62", "\u5df2\u7ec8\u6b62"),
        ],
        "\u9879\u76ee\u5168\u751f\u547d\u5468\u671f\u72b6\u6001"),
    dictionary(
        IDS["dict_currency_unit"], "\u5e01\u79cd", "currencyUnit",
        [("CNY", "CNY \u4eba\u6c11\u5e01"), ("USD", "USD \u7f8e\u5143"),
         ("EUR", "EUR \u6b27\u5143"), ("HKD", "HKD \u6e2f\u5143")],
        "\u5e01\u79cd"),
    dictionary(
        IDS["dict_budget_type"], "\u9884\u7b97\u7c7b\u522b", "budgetType",
        [
            ("\u9879\u76ee\u9884\u7b97", "\u9879\u76ee\u9884\u7b97"),
            ("\u90e8\u95e8\u9884\u7b97", "\u90e8\u95e8\u9884\u7b97"),
            ("\u5e74\u5ea6\u9884\u7b97", "\u5e74\u5ea6\u9884\u7b97"),
            ("\u4e13\u9879\u9884\u7b97", "\u4e13\u9879\u9884\u7b97"),
            ("\u9884\u7b97\u8c03\u6574", "\u9884\u7b97\u8c03\u6574"),
        ],
        "\u9884\u7b97\u7c7b\u522b"),
    dictionary(
        IDS["dict_expense_type"], "\u8d39\u7528\u7c7b\u578b", "expenseType",
        [
            ("\u5dee\u65c5\u8d39", "\u5dee\u65c5\u8d39"),
            ("\u4f1a\u8bae\u8d39", "\u4f1a\u8bae\u8d39"),
            ("\u529e\u516c\u8d39", "\u529e\u516c\u8d39"),
            ("\u6750\u6599\u8d39", "\u6750\u6599\u8d39"),
            ("\u8bbe\u5907\u8d39", "\u8bbe\u5907\u8d39"),
            ("\u52b3\u52a1\u8d39", "\u52b3\u52a1\u8d39"),
            ("\u54a8\u8be2\u8d39", "\u54a8\u8be2\u8d39"),
            ("\u6d4b\u8bd5\u5316\u9a8c\u8d39", "\u6d4b\u8bd5\u5316\u9a8c\u8d39"),
            ("\u59d4\u6258\u4e1a\u52a1\u8d39", "\u59d4\u6258\u4e1a\u52a1\u8d39"),
            ("\u5176\u4ed6\u8d39\u7528", "\u5176\u4ed6\u8d39\u7528"),
        ],
        "\u8d39\u7528\u7c7b\u578b"),
    dictionary(
        IDS["dict_pay_type"], "\u4ed8\u6b3e\u7c7b\u578b", "payType",
        [
            ("\u9884\u4ed8\u6b3e", "\u9884\u4ed8\u6b3e"),
            ("\u8fdb\u5ea6\u6b3e", "\u8fdb\u5ea6\u6b3e"),
            ("\u5c3e\u6b3e", "\u5c3e\u6b3e"),
            ("\u8d28\u4fdd\u91d1", "\u8d28\u4fdd\u91d1"),
            ("\u5168\u989d\u4ed8\u6b3e", "\u5168\u989d\u4ed8\u6b3e"),
        ],
        "\u4ed8\u6b3e\u7c7b\u578b"),
    dictionary(
        IDS["dict_contract_type"], "\u5408\u540c\u7c7b\u578b", "contractType",
        [
            ("\u91c7\u8d2d\u5408\u540c", "\u91c7\u8d2d\u5408\u540c"),
            ("\u670d\u52a1\u5408\u540c", "\u670d\u52a1\u5408\u540c"),
            ("\u6280\u672f\u5f00\u53d1\u5408\u540c", "\u6280\u672f\u5f00\u53d1\u5408\u540c"),
            ("\u54a8\u8be2\u5408\u540c", "\u54a8\u8be2\u5408\u540c"),
            ("\u79df\u8d41\u5408\u540c", "\u79df\u8d41\u5408\u540c"),
            ("\u6846\u67b6\u534f\u8bae", "\u6846\u67b6\u534f\u8bae"),
            ("\u5176\u4ed6\u5408\u540c", "\u5176\u4ed6\u5408\u540c"),
        ],
        "\u5408\u540c\u7c7b\u578b"),
    dictionary(
        IDS["dict_contract_status"], "\u5408\u540c\u72b6\u6001", "contractStatus",
        [
            ("\u8349\u62df", "\u8349\u62df"),
            ("\u5ba1\u6279\u4e2d", "\u5ba1\u6279\u4e2d"),
            ("\u5df2\u751f\u6548", "\u5df2\u751f\u6548"),
            ("\u5c65\u884c\u4e2d", "\u5c65\u884c\u4e2d"),
            ("\u5df2\u5b8c\u6210", "\u5df2\u5b8c\u6210"),
            ("\u5df2\u7ec8\u6b62", "\u5df2\u7ec8\u6b62"),
            ("\u5df2\u89e3\u9664", "\u5df2\u89e3\u9664"),
            ("\u5df2\u4e2d\u6b62", "\u5df2\u4e2d\u6b62"),
        ],
        "\u5408\u540c\u72b6\u6001\uff08\u5b98\u65b9\u53e3\u5f84 \u5c65\u884c\u4e2d/\u5df2\u7ec8\u6b62/\u5df2\u89e3\u9664/\u5df2\u4e2d\u6b62 + \u6d41\u7a0b\u4e2d\u95f4\u6001\uff09"),
    dictionary(
        IDS["dict_archive_type"], "\u6863\u6848\u7c7b\u522b", "archiveType",
        [
            ("\u9879\u76ee\u6863\u6848", "\u9879\u76ee\u6863\u6848"),
            ("\u5408\u540c\u6863\u6848", "\u5408\u540c\u6863\u6848"),
            ("\u8d22\u52a1\u6863\u6848", "\u8d22\u52a1\u6863\u6848"),
            ("\u9884\u7b97\u6863\u6848", "\u9884\u7b97\u6863\u6848"),
            ("\u6587\u4e66\u6863\u6848", "\u6587\u4e66\u6863\u6848"),
            ("\u4eba\u4e8b\u6863\u6848", "\u4eba\u4e8b\u6863\u6848"),
            ("\u79d1\u6280\u6863\u6848", "\u79d1\u6280\u6863\u6848"),
            ("\u5176\u4ed6\u6863\u6848", "\u5176\u4ed6\u6863\u6848"),
        ],
        "\u6863\u6848\u7c7b\u522b"),
    dictionary(
        IDS["dict_archive_level"], "\u4fdd\u5bc6\u7b49\u7ea7", "archiveLevel",
        [
            ("\u516c\u5f00", "\u516c\u5f00"),
            ("\u5185\u90e8", "\u5185\u90e8"),
            ("\u79d8\u5bc6", "\u79d8\u5bc6"),
            ("\u673a\u5bc6", "\u673a\u5bc6"),
        ],
        "\u4fdd\u5bc6\u7b49\u7ea7"),
    dictionary(
        IDS["dict_archive_state"], "\u6863\u6848\u72b6\u6001", "archiveState",
        [
            ("\u5f85\u5f52\u6863", "\u5f85\u5f52\u6863"),
            ("\u5df2\u5f52\u6863", "\u5df2\u5f52\u6863"),
            ("\u501f\u9605\u4e2d", "\u501f\u9605\u4e2d"),
            ("\u5df2\u9500\u6bc1", "\u5df2\u9500\u6bc1"),
        ],
        "\u6863\u6848\u72b6\u6001"),
    dictionary(
        IDS["dict_fund_source"], "\u8d44\u91d1\u6765\u6e90", "fundSource",
        [
            ("\u8d22\u653f\u62e8\u6b3e", "\u8d22\u653f\u62e8\u6b3e"),
            ("\u81ea\u7b79\u8d44\u91d1", "\u81ea\u7b79\u8d44\u91d1"),
            ("\u4e13\u9879\u8d44\u91d1", "\u4e13\u9879\u8d44\u91d1"),
            ("\u4f1a\u8d39\u6536\u5165", "\u4f1a\u8d39\u6536\u5165"),
            ("\u670d\u52a1\u6536\u5165", "\u670d\u52a1\u6536\u5165"),
            ("\u5176\u4ed6\u6765\u6e90", "\u5176\u4ed6\u6765\u6e90"),
        ],
        "\u8d44\u91d1\u6765\u6e90"),
]

# ==========================================================================
# 二、合同管理应用专有字典（7 条）
# --------------------------------------------------------------------------
# 官方合同应用状态口径（截图 1656385113300 门户饼图图例）：
#   履行中 / 已终止 / 已解除 / 已中止
# 上述 4 个已并入 dict_contract_status（第 8 项「已中止」为本轮新增）。
# 以下 7 条为合同业务链条专有枚举。
# ==========================================================================

DICTIONARIES += [
    dictionary(
        IDS["dict_partner_type"], "\u7b7e\u7ea6\u65b9\u7c7b\u578b", "partnerType",
        [
            ("\u4f9b\u5e94\u5546", "\u4f9b\u5e94\u5546"),
            ("\u5ba2\u6237", "\u5ba2\u6237"),
            ("\u5408\u4f5c\u4f19\u4f34", "\u5408\u4f5c\u4f19\u4f34"),
            ("\u670d\u52a1\u5546", "\u670d\u52a1\u5546"),
            ("\u59d4\u6258\u65b9", "\u59d4\u6258\u65b9"),
            ("\u5176\u4ed6", "\u5176\u4ed6"),
        ],
        "\u7b7e\u7ea6\u5bf9\u65b9\u7c7b\u578b\uff08\u5b98\u65b9\u7b7e\u7ea6\u65b9\u6863\u6848\uff09"),
    dictionary(
        IDS["dict_receive_type"], "\u6536\u6b3e\u7c7b\u578b", "receiveType",
        [
            ("\u9884\u6536\u6b3e", "\u9884\u6536\u6b3e"),
            ("\u8fdb\u5ea6\u6b3e", "\u8fdb\u5ea6\u6b3e"),
            ("\u9a8c\u6536\u6b3e", "\u9a8c\u6536\u6b3e"),
            ("\u8d28\u4fdd\u91d1\u9000\u8fd8", "\u8d28\u4fdd\u91d1\u9000\u8fd8"),
            ("\u5168\u989d\u6536\u6b3e", "\u5168\u989d\u6536\u6b3e"),
            ("\u5176\u4ed6\u6536\u6b3e", "\u5176\u4ed6\u6536\u6b3e"),
        ],
        "\u5408\u540c\u56de\u6b3e\u7c7b\u578b"),
    dictionary(
        IDS["dict_invoice_type"], "\u53d1\u7968\u7c7b\u578b", "invoiceType",
        [
            ("\u589e\u503c\u7a0e\u4e13\u7528\u53d1\u7968", "\u589e\u503c\u7a0e\u4e13\u7528\u53d1\u7968"),
            ("\u589e\u503c\u7a0e\u666e\u901a\u53d1\u7968", "\u589e\u503c\u7a0e\u666e\u901a\u53d1\u7968"),
            ("\u7535\u5b50\u4e13\u7528\u53d1\u7968", "\u7535\u5b50\u4e13\u7528\u53d1\u7968"),
            ("\u7535\u5b50\u666e\u901a\u53d1\u7968", "\u7535\u5b50\u666e\u901a\u53d1\u7968"),
            ("\u673a\u52a8\u8f66\u9500\u552e\u7edf\u4e00\u53d1\u7968", "\u673a\u52a8\u8f66\u9500\u552e\u7edf\u4e00\u53d1\u7968"),
            ("\u4e0d\u5f00\u7968", "\u4e0d\u5f00\u7968"),
        ],
        "\u53d1\u7968\u7c7b\u578b"),
    dictionary(
        IDS["dict_change_type"], "\u5408\u540c\u53d8\u66f4\u7c7b\u578b", "changeType",
        [
            ("\u4fe1\u606f\u53d8\u66f4", "\u4fe1\u606f\u53d8\u66f4"),
            ("\u91d1\u989d\u53d8\u66f4", "\u91d1\u989d\u53d8\u66f4"),
            ("\u5c65\u884c\u671f\u53d8\u66f4", "\u5c65\u884c\u671f\u53d8\u66f4"),
            ("\u4e3b\u4f53\u53d8\u66f4", "\u4e3b\u4f53\u53d8\u66f4"),
            ("\u72b6\u6001\u53d8\u66f4", "\u72b6\u6001\u53d8\u66f4"),
            ("\u7ec8\u6b62", "\u7ec8\u6b62"),
            ("\u89e3\u9664", "\u89e3\u9664"),
            ("\u4e2d\u6b62", "\u4e2d\u6b62"),
        ],
        "\u5408\u540c\u53d8\u66f4\u7c7b\u578b\uff08\u5b98\u65b9\u300c\u4fe1\u606f\u53d8\u66f4 / \u72b6\u6001\u53d8\u66f4\u300d\uff09"),
    dictionary(
        IDS["dict_ticket_type"], "\u7968\u636e\u7c7b\u578b", "ticketType",
        [
            ("\u589e\u503c\u7a0e\u4e13\u7968", "\u589e\u503c\u7a0e\u4e13\u7968"),
            ("\u589e\u503c\u7a0e\u666e\u7968", "\u589e\u503c\u7a0e\u666e\u7968"),
            ("\u673a\u52a8\u8f66\u7968", "\u673a\u52a8\u8f66\u7968"),
            ("\u5dee\u65c5\u8fd0\u8f93\u7968", "\u5dee\u65c5\u8fd0\u8f93\u7968"),
            ("\u5176\u4ed6\u7968\u636e", "\u5176\u4ed6\u7968\u636e"),
        ],
        "\u8fdb\u9879\u7968\u636e\u7c7b\u578b"),
    dictionary(
        IDS["dict_plan_status"], "\u8ba1\u5212\u72b6\u6001", "planStatus",
        [
            ("\u8349\u62df", "\u8349\u62df"),
            ("\u5ba1\u6279\u4e2d", "\u5ba1\u6279\u4e2d"),
            ("\u5df2\u751f\u6548", "\u5df2\u751f\u6548"),
            ("\u5df2\u6267\u884c", "\u5df2\u6267\u884c"),
            ("\u5df2\u4f5c\u5e9f", "\u5df2\u4f5c\u5e9f"),
        ],
        "\u6536\u6b3e/\u4ed8\u6b3e\u8ba1\u5212\u72b6\u6001"),
    dictionary(
        IDS["dict_approve_status"], "\u5ba1\u6279\u72b6\u6001", "approveStatus",
        [
            ("\u5f85\u63d0\u4ea4", "\u5f85\u63d0\u4ea4"),
            ("\u5ba1\u6279\u4e2d", "\u5ba1\u6279\u4e2d"),
            ("\u5df2\u901a\u8fc7", "\u5df2\u901a\u8fc7"),
            ("\u5df2\u9000\u56de", "\u5df2\u9000\u56de"),
            ("\u5df2\u64a4\u9500", "\u5df2\u64a4\u9500"),
        ],
        "\u5408\u540c\u53d8\u66f4/\u5f00\u7968\u7533\u8bf7\u7684\u5ba1\u6279\u72b6\u6001"),
]


# ==========================================================================
# 人力资源管理应用专有字典（14 条，d6006001 ~ d6006014）
# --------------------------------------------------------------------------
# 口径来源：官方 HR 截图实读 + 常规人事管理规范
#   员工档案（截图 1652073737623）：性别/民族/政治面貌/婚姻状态/
#       最高学历/最高学位/员工状态/用工性质
#   员工管理（截图 1652073737709）：转岗/转正/入职/离职
#   人才市场（截图 1652073737639）：竞聘类型/岗位序列/岗位状态
#   积分管理（截图 1652073737630）：积分类型/悬赏课题类型/积分状态
#   考勤管理（截图 1652073737547）：假期类型/考勤类型/考勤结果
#   员工自助（截图 1652073737833）：自助申请类型
# ==========================================================================

IDS["dict_gender_type"] = "d6006001-gender-type-dict-0000000000001"
IDS["dict_political_status"] = "d6006002-political-status-dict-000000001"
IDS["dict_marital_status"] = "d6006003-marital-status-dict-0000000001"
IDS["dict_education_level"] = "d6006004-education-level-dict-000000001"
IDS["dict_degree_type"] = "d6006005-degree-type-dict-0000000000001"
IDS["dict_employee_status"] = "d6006006-employee-status-dict-000000001"
IDS["dict_work_nature"] = "d6006007-work-nature-dict-0000000000001"
IDS["dict_transfer_type"] = "d6006008-transfer-type-dict-00000000001"
IDS["dict_resign_type"] = "d6006009-resign-type-dict-0000000000001"
IDS["dict_bid_type"] = "d6006010-bid-type-dict-00000000000001"
IDS["dict_job_category"] = "d6006011-job-category-dict-00000000001"
IDS["dict_job_status"] = "d6006012-job-status-dict-0000000000001"
IDS["dict_job_type"] = "d6006013-job-type-dict-000000000000001"
IDS["dict_point_type"] = "d6006014-point-type-dict-0000000000001"
IDS["dict_bounty_type"] = "d6006015-bounty-type-dict-00000000001"
IDS["dict_bounty_status"] = "d6006016-bounty-status-dict-000000001"
IDS["dict_leave_type"] = "d6006017-leave-type-dict-0000000000001"
IDS["dict_overtime_type"] = "d6006018-overtime-type-dict-0000000001"
IDS["dict_attend_status"] = "d6006019-attend-status-dict-0000000001"
IDS["dict_apply_status"] = "d6006020-apply-status-dict-00000000001"
IDS["dict_self_service_type"] = "d6006021-self-service-type-dict-0000001"
IDS["dict_language_type"] = "d6006022-language-type-dict-0000000001"

DICTIONARIES += [
    dictionary(
        IDS["dict_gender_type"], "\u6027\u522b", "genderType",
        [("\u7537", "\u7537"), ("\u5973", "\u5973")],
        "\u5458\u5de5\u6863\u6848\u6027\u522b"),
    dictionary(
        IDS["dict_political_status"], "\u653f\u6cbb\u9762\u8c8c",
        "politicalStatus",
        [("\u4e2d\u5171\u515a\u5458", "\u4e2d\u5171\u515a\u5458"),
         ("\u4e2d\u5171\u9884\u5907\u515a\u5458", "\u4e2d\u5171\u9884\u5907\u515a\u5458"),
         ("\u5171\u9752\u56e2\u5458", "\u5171\u9752\u56e2\u5458"),
         ("\u6c11\u9769\u515a\u6d3e", "\u6c11\u9769\u515a\u6d3e"),
         ("\u7fa4\u4f17", "\u7fa4\u4f17")],
        "\u5458\u5de5\u6863\u6848\u653f\u6cbb\u9762\u8c8c"),
    dictionary(
        IDS["dict_marital_status"], "\u5a5a\u59fb\u72b6\u6001", "maritalStatus",
        [("\u672a\u5a5a", "\u672a\u5a5a"), ("\u5df2\u5a5a", "\u5df2\u5a5a"),
         ("\u79bb\u5f02", "\u79bb\u5f02"), ("\u4e27\u5076", "\u4e27\u5076")],
        "\u5458\u5de5\u6863\u6848\u5a5a\u59fb\u72b6\u6001"),
    dictionary(
        IDS["dict_education_level"], "\u6700\u9ad8\u5b66\u5386", "educationLevel",
        [("\u4e2d\u4e13\u53ca\u4ee5\u4e0b", "\u4e2d\u4e13\u53ca\u4ee5\u4e0b"),
         ("\u5927\u4e13", "\u5927\u4e13"), ("\u672c\u79d1", "\u672c\u79d1"),
         ("\u7855\u58eb", "\u7855\u58eb"), ("\u535a\u58eb", "\u535a\u58eb")],
        "\u5458\u5de5\u6700\u9ad8\u5b66\u5386"),
    dictionary(
        IDS["dict_degree_type"], "\u6700\u9ad8\u5b66\u4f4d", "degreeType",
        [("\u65e0", "\u65e0"), ("\u5b66\u58eb", "\u5b66\u58eb"),
         ("\u7855\u58eb", "\u7855\u58eb"), ("\u535a\u58eb", "\u535a\u58eb")],
        "\u5458\u5de5\u6700\u9ad8\u5b66\u4f4d"),
    dictionary(
        IDS["dict_employee_status"], "\u5458\u5de5\u72b6\u6001", "employeeStatus",
        [("\u8bd5\u7528\u671f\u5458\u5de5", "\u8bd5\u7528\u671f\u5458\u5de5"),
         ("\u6b63\u5f0f\u5458\u5de5", "\u6b63\u5f0f\u5458\u5de5"),
         ("\u5b9e\u4e60\u671f\u5458\u5de5", "\u5b9e\u4e60\u671f\u5458\u5de5"),
         ("\u501f\u8c03\u5458\u5de5", "\u501f\u8c03\u5458\u5de5"),
         ("\u79bb\u804c\u5458\u5de5", "\u79bb\u804c\u5458\u5de5")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u6863\u6848\u67e5\u8be2\u300d\u5206\u7ec4\u53e3\u5f84"),
    dictionary(
        IDS["dict_work_nature"], "\u7528\u5de5\u6027\u8d28", "workNature",
        [("\u6b63\u5f0f\u7f16\u5236", "\u6b63\u5f0f\u7f16\u5236"),
         ("\u52b3\u52a1\u6d3e\u9063", "\u52b3\u52a1\u6d3e\u9063"),
         ("\u987e\u95ee", "\u987e\u95ee"),
         ("\u5b9e\u4e60", "\u5b9e\u4e60"),
         ("\u517c\u804c", "\u517c\u804c")],
        "\u5458\u5de5\u7528\u5de5\u6027\u8d28"),
    dictionary(
        IDS["dict_transfer_type"], "\u8f6c\u5c97\u7c7b\u578b", "transferType",
        [("\u5185\u90e8\u8c03\u52a8", "\u5185\u90e8\u8c03\u52a8"),
         ("\u7ade\u8058\u4e0a\u5c97", "\u7ade\u8058\u4e0a\u5c97"),
         ("\u804c\u52a1\u4efb\u547d", "\u804c\u52a1\u4efb\u547d"),
         ("\u8f6e\u5c97", "\u8f6e\u5c97"),
         ("\u501f\u8c03", "\u501f\u8c03")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u5458\u5de5\u8f6c\u5c97\u516c\u793a\u300d"),
    dictionary(
        IDS["dict_resign_type"], "\u79bb\u804c\u7c7b\u578b", "resignType",
        [("\u4e3b\u52a8\u79bb\u804c", "\u4e3b\u52a8\u79bb\u804c"),
         ("\u5408\u540c\u5230\u671f", "\u5408\u540c\u5230\u671f"),
         ("\u534f\u5546\u89e3\u9664", "\u534f\u5546\u89e3\u9664"),
         ("\u8f9e\u9000", "\u8f9e\u9000"),
         ("\u9000\u4f11", "\u9000\u4f11")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u5458\u5de5\u79bb\u804c\u516c\u793a\u300d"),
    dictionary(
        IDS["dict_bid_type"], "\u7ade\u8058\u7c7b\u578b", "bidType",
        [("\u516c\u5f00\u7ade\u8058", "\u516c\u5f00\u7ade\u8058"),
         ("\u5185\u90e8\u7ade\u8058", "\u5185\u90e8\u7ade\u8058"),
         ("\u7ec4\u7ec7\u9009\u62d4", "\u7ec4\u7ec7\u9009\u62d4"),
         ("\u7ade\u8058\u4e0a\u5c97", "\u7ade\u8058\u4e0a\u5c97")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u5c97\u4f4d\u6c60\u300d\u7ade\u8058\u7c7b\u578b"),
    dictionary(
        IDS["dict_job_category"], "\u5c97\u4f4d\u5e8f\u5217", "jobCategory",
        [("\u7ba1\u7406\u5e8f\u5217", "\u7ba1\u7406\u5e8f\u5217"),
         ("\u4e13\u4e1a\u6280\u672f\u5e8f\u5217", "\u4e13\u4e1a\u6280\u672f\u5e8f\u5217"),
         ("\u5de5\u52e4\u5e8f\u5217", "\u5de5\u52e4\u5e8f\u5217"),
         ("\u6280\u80fd\u64cd\u4f5c\u5e8f\u5217", "\u6280\u80fd\u64cd\u4f5c\u5e8f\u5217")],
        "\u5458\u5de5\u5c97\u4f4d\u5e8f\u5217"),
    dictionary(
        IDS["dict_job_status"], "\u5c97\u4f4d\u72b6\u6001", "jobStatus",
        [("\u62a5\u540d\u4e2d", "\u62a5\u540d\u4e2d"),
         ("\u9762\u8bd5\u4e2d", "\u9762\u8bd5\u4e2d"),
         ("\u5df2\u622a\u6b62", "\u5df2\u622a\u6b62"),
         ("\u5df2\u5b8c\u6210", "\u5df2\u5b8c\u6210"),
         ("\u5df2\u53d6\u6d88", "\u5df2\u53d6\u6d88")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u5c97\u4f4d\u6c60\u300d\u72b6\u6001\u5217"),
    dictionary(
        IDS["dict_job_type"], "\u5c97\u4f4d\u7c7b\u578b", "jobType",
        [("\u7ba1\u7406\u5c97", "\u7ba1\u7406\u5c97"),
         ("\u6280\u672f\u5c97", "\u6280\u672f\u5c97"),
         ("\u4e1a\u52a1\u5c97", "\u4e1a\u52a1\u5c97"),
         ("\u64cd\u4f5c\u5c97", "\u64cd\u4f5c\u5c97")],
        "\u5c97\u4f4d\u7c7b\u578b"),
    dictionary(
        IDS["dict_point_type"], "\u79ef\u5206\u7c7b\u578b", "pointType",
        [("\u5e74\u5ea6\u79ef\u5206", "\u5e74\u5ea6\u79ef\u5206"),
         ("\u6c38\u4e45\u79ef\u5206", "\u6c38\u4e45\u79ef\u5206"),
         ("\u60ac\u8d4f\u79ef\u5206", "\u60ac\u8d4f\u79ef\u5206"),
         ("\u5956\u52b1\u79ef\u5206", "\u5956\u52b1\u79ef\u5206"),
         ("\u6263\u5206", "\u6263\u5206")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u79ef\u5206\u7ba1\u7406\u300d\u5e74\u5ea6/\u6c38\u4e45\u53e3\u5f84"),
    dictionary(
        IDS["dict_bounty_type"], "\u8bfe\u9898\u7c7b\u578b", "bountyType",
        [("\u6280\u672f\u653b\u5173", "\u6280\u672f\u653b\u5173"),
         ("\u6807\u51c6\u7814\u7a76", "\u6807\u51c6\u7814\u7a76"),
         ("\u5de5\u827a\u4f18\u5316", "\u5de5\u827a\u4f18\u5316"),
         ("\u4e13\u5229\u7533\u62a5", "\u4e13\u5229\u7533\u62a5"),
         ("\u8bba\u6587\u53d1\u8868", "\u8bba\u6587\u53d1\u8868"),
         ("\u57f9\u8bad\u8bb2\u5e08", "\u57f9\u8bad\u8bb2\u5e08")],
        "\u79ef\u5206\u60ac\u8d4f\u8bfe\u9898\u7c7b\u578b"),
    dictionary(
        IDS["dict_bounty_status"], "\u60ac\u8d4f\u72b6\u6001", "bountyStatus",
        [("\u5f85\u9886\u53d6", "\u5f85\u9886\u53d6"),
         ("\u5df2\u9886\u53d6", "\u5df2\u9886\u53d6"),
         ("\u5df2\u5b8c\u6210", "\u5df2\u5b8c\u6210"),
         ("\u5df2\u5931\u6548", "\u5df2\u5931\u6548")],
        "\u79ef\u5206\u60ac\u8d4f\u72b6\u6001"),
    dictionary(
        IDS["dict_leave_type"], "\u5047\u671f\u7c7b\u578b", "leaveType",
        [("\u4e8b\u5047", "\u4e8b\u5047"), ("\u75c5\u5047", "\u75c5\u5047"),
         ("\u5e74\u5047", "\u5e74\u5047"), ("\u8c03\u4f11", "\u8c03\u4f11"),
         ("\u5a5a\u5047", "\u5a5a\u5047"), ("\u4ea7\u5047", "\u4ea7\u5047"),
         ("\u966a\u4ea7\u5047", "\u966a\u4ea7\u5047"),
         ("\u4e27\u5047", "\u4e27\u5047"),
         ("\u63a2\u4eb2\u5047", "\u63a2\u4eb2\u5047")],
        "\u8003\u52e4\u7ba1\u7406\u5047\u671f\u7c7b\u578b"),
    dictionary(
        IDS["dict_overtime_type"], "\u52a0\u73ed\u7c7b\u578b", "overtimeType",
        [("\u5de5\u4f5c\u65e5\u52a0\u73ed", "\u5de5\u4f5c\u65e5\u52a0\u73ed"),
         ("\u4f11\u606f\u65e5\u52a0\u73ed", "\u4f11\u606f\u65e5\u52a0\u73ed"),
         ("\u6cd5\u5b9a\u8282\u5047\u65e5\u52a0\u73ed", "\u6cd5\u5b9a\u8282\u5047\u65e5\u52a0\u73ed"),
         ("\u5e94\u6025\u52a0\u73ed", "\u5e94\u6025\u52a0\u73ed")],
        "\u52a0\u73ed\u7c7b\u578b"),
    dictionary(
        IDS["dict_attend_status"], "\u8003\u52e4\u72b6\u6001", "attendStatus",
        [("\u5f85\u786e\u8ba4", "\u5f85\u786e\u8ba4"),
         ("\u5df2\u786e\u8ba4", "\u5df2\u786e\u8ba4"),
         ("\u5f02\u8bae\u4e2d", "\u5f02\u8bae\u4e2d"),
         ("\u5df2\u7ed3\u675f", "\u5df2\u7ed3\u675f")],
        "\u8003\u52e4\u6708\u62a5\u72b6\u6001"),
    dictionary(
        IDS["dict_apply_status"], "\u62a5\u540d\u72b6\u6001", "applyStatus",
        [("\u5df2\u62a5\u540d", "\u5df2\u62a5\u540d"),
         ("\u8d44\u683c\u5ba1\u67e5", "\u8d44\u683c\u5ba1\u67e5"),
         ("\u9762\u8bd5\u4e2d", "\u9762\u8bd5\u4e2d"),
         ("\u5df2\u5165\u9009", "\u5df2\u5165\u9009"),
         ("\u672a\u5165\u9009", "\u672a\u5165\u9009"),
         ("\u5df2\u64a4\u9500", "\u5df2\u64a4\u9500")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u6211\u7684\u62a5\u540d\u8868\u300d\u72b6\u6001"),
    dictionary(
        IDS["dict_self_service_type"], "\u81ea\u52a9\u7533\u8bf7\u7c7b\u578b",
        "selfServiceType",
        [("\u8bf7\u5047\u7533\u8bf7", "\u8bf7\u5047\u7533\u8bf7"),
         ("\u52a0\u73ed\u7533\u8bf7", "\u52a0\u73ed\u7533\u8bf7"),
         ("\u51fa\u5dee\u7533\u8bf7", "\u51fa\u5dee\u7533\u8bf7"),
         ("\u8f6c\u6b63\u7533\u8bf7", "\u8f6c\u6b63\u7533\u8bf7"),
         ("\u8f6c\u5c97\u7533\u8bf7", "\u8f6c\u5c97\u7533\u8bf7"),
         ("\u79bb\u804c\u7533\u8bf7", "\u79bb\u804c\u7533\u8bf7"),
         ("\u8bc1\u660e\u5f00\u5177", "\u8bc1\u660e\u5f00\u5177"),
         ("\u5458\u5de5\u57f9\u8bad", "\u5458\u5de5\u57f9\u8bad"),
         ("\u5176\u4ed6\u7533\u8bf7", "\u5176\u4ed6\u7533\u8bf7")],
        "\u5458\u5de5\u81ea\u52a9\u7efc\u5408\u7533\u8bf7\u7c7b\u578b"),
    dictionary(
        IDS["dict_language_type"], "\u8bed\u8a00\u8bbe\u7f6e", "languageType",
        [("\u4e2d\u6587\u7b80\u4f53", "\u4e2d\u6587\u7b80\u4f53"),
         ("\u4e2d\u6587\u7e41\u4f53", "\u4e2d\u6587\u7e41\u4f53"),
         ("English", "English")],
        "\u5bf9\u9f50\u5b98\u65b9\u300c\u4e2a\u4eba\u8bbe\u7f6e\u300d\u8bed\u8a00\u9879"),
]
