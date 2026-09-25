# -*- coding: utf-8 -*-
"""
业务数据批量装载器（种子数据）—— 字段名严格对齐 def_*.py
======================================================

用途：通过 O2OA 数据中心官方接口 `POST {tableFlag}/row`（ActionRowInsert）
      向自建表批量写入**彼此可关联**的示范数据，验证：
        · 物理表可写（中文 / 日期 / 数值 / 布尔）
        · project_no 主干贯通（项目 → 合同 → 预算 → 财务 → 档案）
        · employee_no 向 HR 各表辐射

为什么不用 Excel 导入界面：
      经反编译确认 x_query_assemble_designer.war 中**没有 Excel 导入 action**，
      该功能由前端在浏览器解析 xlsx 后逐行调用 `{tableFlag}/row` 落库。
      这里直接调用同一接口，等价且可脚本化。

约定：
  · 字段名 = def_*.py 里 table(...) 的字段名（服务端映射为 x<name> 列）
  · date 用 "yyyy-MM-dd"，datetime 用 "yyyy-MM-dd HH:mm:ss"，boolean 用 JSON true/false
  · 不要写 id（服务端自动生成 UUID）

用法：
  python seed_data.py            # 写入种子数据
  python seed_data.py --clear    # 先清空 31 张表再写
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:9090"
sys.path.insert(0, BUILD)
from import_xapps import get_token

NOW = "2026-09-20 10:00:00"

# ---------------- 项目主表 ----------------
PROJECTS = [
    dict(project_no="XM2026-001", project_name="复合材料轻量化结构件工艺攻关",
         project_type="科研课题", project_status="执行中", project_level="A级",
         dept_name="行业研究部", manager="时晓明",
         start_date="2026-01-10", end_date="2026-12-31",
         total_budget=1200000, fund_source="协会自筹",
         project_goal="形成轻量化结构件成型工艺规范并完成中试验证",
         contract_no="HT2026-001", budget_no="YS2026-001", create_time=NOW, update_time=NOW),
    dict(project_no="XM2026-002", project_name="碳纤维回收再利用技术研究",
         project_type="科研课题", project_status="执行中", project_level="B级",
         dept_name="行业研究部", manager="杜阳",
         start_date="2026-03-01", end_date="2027-02-28",
         total_budget=860000, fund_source="政府专项资金",
         project_goal="建立碳纤维回收工艺路线，回收率不低于85%",
         contract_no="HT2026-002", budget_no="YS2026-002", create_time=NOW, update_time=NOW),
    dict(project_no="XM2026-003", project_name="会员企业技术需求普查",
         project_type="调研专项", project_status="已结项", project_level="C级",
         dept_name="会员服务部", manager="李静",
         start_date="2026-02-01", end_date="2026-06-30",
         total_budget=180000, fund_source="协会自筹",
         project_goal="完成200家会员企业技术需求画像报告",
         contract_no="", budget_no="YS2026-003", create_time=NOW, update_time=NOW),
]

# ---------------- 合同主表 ----------------
CONTRACTS = [
    dict(contract_no="HT2026-001", contract_name="轻量化结构件工艺攻关技术服务合同",
         contract_type="技术服务", project_no="XM2026-001",
         project_name="复合材料轻量化结构件工艺攻关",
         partner_no="HZ2026-001", sign_unit="北京中复新材料科技有限公司",
         sign_person="王建国", sign_date="2026-01-05", handle_dept="行业研究部",
         handle_person="时晓明", contract_amount=1180000, tax_rate=6.0,
         tax_amount=66792.45, net_amount=1113207.55, currency="人民币",
         pay_type="分期付款", start_date="2026-01-10", end_date="2026-12-31",
         contract_status="履行中", perform_rate=45.0, receive_total=590000,
         pay_total=0, invoice_total=590000, archive_no="DA2026-001",
         remark="按里程碑分两期付款", create_time=NOW, update_time=NOW),
    dict(contract_no="HT2026-002", contract_name="碳纤维回收工艺联合研发合同",
         contract_type="合作研发", project_no="XM2026-002",
         project_name="碳纤维回收再利用技术研究",
         partner_no="HZ2026-002", sign_unit="上海复材再生资源有限公司",
         sign_person="陈立", sign_date="2026-02-20", handle_dept="行业研究部",
         handle_person="杜阳", contract_amount=850000, tax_rate=6.0,
         tax_amount=48113.21, net_amount=801886.79, currency="人民币",
         pay_type="里程碑付款", start_date="2026-03-01", end_date="2027-02-28",
         contract_status="履行中", perform_rate=32.0, receive_total=300000,
         pay_total=0, invoice_total=300000, archive_no="DA2026-002",
         remark="", create_time=NOW, update_time=NOW),
]

# ---------------- 签约方档案 ----------------
PARTNERS = [
    dict(partner_no="HZ2026-001", partner_name="北京中复新材料科技有限公司",
         partner_type="技术服务商", credit_code="91110108MA01XXXX1A",
         legal_person="王建国", reg_capital=5000.0, found_date="2015-06-18",
         address="北京市海淀区中关村南大街XX号", contact_name="王建国",
         contact_phone="01088886001", contact_email="wang@zf-material.com",
         bank_name="工商银行北京海淀支行", bank_account="02000045XXXXXXXX123",
         tax_no="91110108MA01XXXX1A", qualification="高新技术企业",
         partner_level="A级", partner_status="合作中", remark="", create_time=NOW),
    dict(partner_no="HZ2026-002", partner_name="上海复材再生资源有限公司",
         partner_type="合作研发方", credit_code="91310115MA01YYYY2B",
         legal_person="陈立", reg_capital=3000.0, found_date="2018-09-25",
         address="上海市浦东新区张江高科技园区XX路", contact_name="陈立",
         contact_phone="02166668002", contact_email="chen@sh-recycle.com",
         bank_name="建设银行上海张江支行", bank_account="31000151XXXXXXXX456",
         tax_no="91310115MA01YYYY2B", qualification="科技型中小企业",
         partner_level="A级", partner_status="合作中", remark="", create_time=NOW),
]

# ---------------- 合同收款 ----------------
RECEIVES = [
    dict(receive_no="SK2026-001", contract_no="HT2026-001",
         contract_name="轻量化结构件工艺攻关技术服务合同", project_no="XM2026-001",
         plan_no="SKJH2026-001", receive_type="合同首款", receive_amount=590000,
         receive_date="2026-04-15", payer_name="北京中复新材料科技有限公司",
         bank_account="02000045XXXXXXXX123", voucher_no="PZ2026-0415-01",
         receive_status="已到账", remark="", create_time=NOW),
    dict(receive_no="SK2026-002", contract_no="HT2026-002",
         contract_name="碳纤维回收工艺联合研发合同", project_no="XM2026-002",
         plan_no="SKJH2026-002", receive_type="里程碑款", receive_amount=300000,
         receive_date="2026-05-20", payer_name="上海复材再生资源有限公司",
         bank_account="31000151XXXXXXXX456", voucher_no="PZ2026-0520-01",
         receive_status="已到账", remark="", create_time=NOW),
]

# ---------------- 预算主表 ----------------
BUDGETS = [
    dict(budget_no="YS2026-001", budget_name="轻量化结构件工艺攻关项目预算",
         budget_type="科研项目预算", budget_year="2026", project_no="XM2026-001",
         dept_name="行业研究部", fund_source="协会自筹", total_amount=1200000,
         executed_amount=412000, remain_amount=788000, exec_rate=34.33,
         budget_status="执行中", create_time=NOW),
    dict(budget_no="YS2026-002", budget_name="碳纤维回收技术研究项目预算",
         budget_type="科研项目预算", budget_year="2026", project_no="XM2026-002",
         dept_name="行业研究部", fund_source="政府专项资金", total_amount=860000,
         executed_amount=196000, remain_amount=664000, exec_rate=22.79,
         budget_status="执行中", create_time=NOW),
    dict(budget_no="YS2026-003", budget_name="会员企业技术需求普查预算",
         budget_type="调研专项预算", budget_year="2026", project_no="XM2026-003",
         dept_name="会员服务部", fund_source="协会自筹", total_amount=180000,
         executed_amount=176500, remain_amount=3500, exec_rate=98.06,
         budget_status="已关闭", create_time=NOW),
]

# ---------------- 预算明细 ----------------
BUDGET_DETAILS = [
    dict(budget_no="YS2026-001", project_no="XM2026-001", expense_type="差旅费",
         budget_item="调研差旅", budget_amount=120000, exec_amount=48600, exec_rate=40.5),
    dict(budget_no="YS2026-001", project_no="XM2026-001", expense_type="设备购置费",
         budget_item="试验设备", budget_amount=480000, exec_amount=121600, exec_rate=25.33),
    dict(budget_no="YS2026-001", project_no="XM2026-001", expense_type="材料费",
         budget_item="原材料采购", budget_amount=360000, exec_amount=168000, exec_rate=46.67),
    dict(budget_no="YS2026-001", project_no="XM2026-001", expense_type="劳务费",
         budget_item="专家咨询", budget_amount=240000, exec_amount=73800, exec_rate=30.75),
    dict(budget_no="YS2026-002", project_no="XM2026-002", expense_type="设备购置费",
         budget_item="回收中试线", budget_amount=520000, exec_amount=156000, exec_rate=30.0),
    dict(budget_no="YS2026-002", project_no="XM2026-002", expense_type="材料费",
         budget_item="试验耗材", budget_amount=340000, exec_amount=40000, exec_rate=11.76),
    dict(budget_no="YS2026-003", project_no="XM2026-003", expense_type="会议费",
         budget_item="调研会议", budget_amount=60000, exec_amount=60000, exec_rate=100.0),
    dict(budget_no="YS2026-003", project_no="XM2026-003", expense_type="差旅费",
         budget_item="企业走访", budget_amount=120000, exec_amount=116500, exec_rate=97.08),
]

# ---------------- 报销主表 ----------------
EXPENSES = [
    dict(expense_no="BX2026-001", expense_title="轻量化项目工艺调研差旅",
         project_no="XM2026-001", budget_no="YS2026-001", contract_no="HT2026-001",
         expense_type="差旅费", applicant="时晓明", apply_dept="行业研究部",
         apply_date="2026-03-18", total_amount=18600, payee_name="时晓明",
         pay_status="已支付", create_time=NOW),
    dict(expense_no="BX2026-002", expense_title="中试线试验设备采购报销",
         project_no="XM2026-001", budget_no="YS2026-001", contract_no="HT2026-001",
         expense_type="设备购置费", applicant="杜阳", apply_dept="行业研究部",
         apply_date="2026-04-02", total_amount=121600, payee_name="北京精工试验设备有限公司",
         pay_status="已支付", create_time=NOW),
    dict(expense_no="BX2026-003", expense_title="会员需求普查工作会议费",
         project_no="XM2026-003", budget_no="YS2026-003", contract_no="",
         expense_type="会议费", applicant="李静", apply_dept="会员服务部",
         apply_date="2026-05-11", total_amount=32000, payee_name="北京会议中心",
         pay_status="已支付", create_time=NOW),
]

# ---------------- 付款主表 ----------------
PAYMENTS = [
    dict(payment_no="FK2026-001", payment_title="轻量化项目首期技术款",
         project_no="XM2026-001", budget_no="YS2026-001", contract_no="HT2026-001",
         pay_type="合同付款", payee_name="北京中复新材料科技有限公司",
         payment_amount=590000, plan_pay_date="2026-04-15",
         actual_pay_date="2026-04-15", voucher_no="PZ2026-0415-02"),
    dict(payment_no="FK2026-002", payment_title="碳纤维回收项目里程碑款",
         project_no="XM2026-002", budget_no="YS2026-002", contract_no="HT2026-002",
         pay_type="合同付款", payee_name="上海复材再生资源有限公司",
         payment_amount=300000, plan_pay_date="2026-05-20",
         actual_pay_date="2026-05-20", voucher_no="PZ2026-0520-02"),
]

# ---------------- 项目成本汇总 ----------------
COST_SUMMARY = [
    dict(project_no="XM2026-001", project_name="复合材料轻量化结构件工艺攻关",
         budget_total=1200000, expense_total=140200, payment_total=590000,
         actual_cost=730200, variance=469800, variance_rate=39.15, update_time=NOW),
    dict(project_no="XM2026-002", project_name="碳纤维回收再利用技术研究",
         budget_total=860000, expense_total=0, payment_total=300000,
         actual_cost=300000, variance=560000, variance_rate=65.12, update_time=NOW),
    dict(project_no="XM2026-003", project_name="会员企业技术需求普查",
         budget_total=180000, expense_total=32000, payment_total=0,
         actual_cost=32000, variance=148000, variance_rate=82.22, update_time=NOW),
]

# ---------------- 档案主表（五方挂靠）----------------
ARCHIVES = [
    dict(archive_no="DA2026-001", archive_name="轻量化结构件工艺攻关项目档案",
         archive_type="科研档案", archive_level="重要", archive_state="在库",
         source_app="项目管理", project_no="XM2026-001", contract_no="HT2026-001",
         budget_no="YS2026-001", expense_no="BX2026-001", fonds_no="FZ2026",
         archive_year="2026", retention_period="永久", carrier_type="纸质+电子",
         pages=186, storage_location="档案室A区01架", archive_date="2026-07-05",
         keywords="轻量化,结构件,工艺,中试", create_time=NOW),
    dict(archive_no="DA2026-002", archive_name="碳纤维回收工艺联合研发档案",
         archive_type="科研档案", archive_level="一般", archive_state="在库",
         source_app="合同管理", project_no="XM2026-002", contract_no="HT2026-002",
         budget_no="YS2026-002", expense_no="", fonds_no="FZ2026",
         archive_year="2026", retention_period="30年", carrier_type="电子",
         pages=92, storage_location="档案室A区02架", archive_date="2026-07-06",
         keywords="碳纤维,回收,再利用", create_time=NOW),
]

# ---------------- 档案关联关系 ----------------
ARCHIVE_LINKS = [
    dict(archive_no="DA2026-001", biz_type="项目", biz_no="XM2026-001",
         project_no="XM2026-001", link_time=NOW),
    dict(archive_no="DA2026-001", biz_type="合同", biz_no="HT2026-001",
         project_no="XM2026-001", link_time=NOW),
    dict(archive_no="DA2026-001", biz_type="预算", biz_no="YS2026-001",
         project_no="XM2026-001", link_time=NOW),
    dict(archive_no="DA2026-002", biz_type="项目", biz_no="XM2026-002",
         project_no="XM2026-002", link_time=NOW),
    dict(archive_no="DA2026-002", biz_type="合同", biz_no="HT2026-002",
         project_no="XM2026-002", link_time=NOW),
]

# ---------------- 档案借阅 ----------------
ARCHIVE_BORROWS = [
    dict(borrow_no="JY2026-001", archive_no="DA2026-001", borrower="时晓明",
         borrow_dept="行业研究部", borrow_type="查阅", borrow_reason="项目结项材料核对",
         borrow_date="2026-08-10", plan_return_date="2026-08-20",
         actual_return_date="2026-08-15", borrow_status="已归还"),
    dict(borrow_no="JY2026-002", archive_no="DA2026-002", borrower="杜阳",
         borrow_dept="行业研究部", borrow_type="复印", borrow_reason="技术方案引用",
         borrow_date="2026-09-01", plan_return_date="2026-09-10",
         actual_return_date="", borrow_status="借出中"),
]

# ---------------- 员工主表 ----------------
EMPLOYEES = [
    dict(employee_no="YG001", employee_name="孟弋洁", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1980-05-12", nation="汉族",
         political_status="中共党员", marital_status="已婚", mobile="13700000001",
         email="mengyj@cfrp.org.cn", education="硕士", degree="硕士",
         graduate_school="北京化工大学", major="高分子材料",
         dept="综合管理部", position="秘书长", grade="正处级",
         join_date="2018-03-01", regular_date="2018-06-01", year_point=0, total_point=0,
         home_address="北京市朝阳区", emergency_contact="家属", emergency_phone="13700000000",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG002", employee_name="卢宏萍", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1983-09-20", nation="汉族",
         political_status="群众", marital_status="已婚", mobile="13700000002",
         email="luhp@cfrp.org.cn", education="本科", degree="学士",
         graduate_school="北京工业大学", major="工商管理",
         dept="会员服务部", position="副秘书长", grade="副处级",
         join_date="2019-06-15", regular_date="2019-09-15", year_point=0, total_point=0,
         home_address="北京市海淀区", emergency_contact="家属", emergency_phone="13700000010",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG003", employee_name="李芳", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1992-02-08", nation="汉族",
         political_status="群众", marital_status="未婚", mobile="13700000003",
         email="lifang@cfrp.org.cn", education="本科", degree="学士",
         graduate_school="首都经济贸易大学", major="会计学",
         dept="综合管理部", position="综合部专员", grade="科员",
         join_date="2020-09-01", regular_date="2020-12-01", year_point=0, total_point=0,
         home_address="北京市丰台区", emergency_contact="家属", emergency_phone="13700000011",
         remark="兼人事/财务/档案/合同管理", create_time=NOW, update_time=NOW),
    dict(employee_no="YG004", employee_name="时晓明", gender="男", employee_status="在职",
         work_nature="全职", birth_date="1988-11-25", nation="汉族",
         political_status="群众", marital_status="已婚", mobile="13700000004",
         email="shixm@cfrp.org.cn", education="硕士", degree="硕士",
         graduate_school="哈尔滨工业大学", major="材料科学与工程",
         dept="行业研究部", position="研究员", grade="中级",
         join_date="2021-04-12", regular_date="2021-07-12", year_point=0, total_point=0,
         home_address="北京市昌平区", emergency_contact="家属", emergency_phone="13700000012",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG005", employee_name="杜阳", gender="男", employee_status="在职",
         work_nature="全职", birth_date="1995-07-14", nation="汉族",
         political_status="共青团员", marital_status="未婚", mobile="13700000005",
         email="duyang@cfrp.org.cn", education="硕士", degree="硕士",
         graduate_school="东华大学", major="纺织复合材料",
         dept="行业研究部", position="助理研究员", grade="初级",
         join_date="2022-07-01", regular_date="2022-10-01", year_point=0, total_point=0,
         home_address="北京市朝阳区", emergency_contact="家属", emergency_phone="13700000013",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG006", employee_name="李静", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1990-04-30", nation="汉族",
         political_status="群众", marital_status="已婚", mobile="13700000006",
         email="lijing@cfrp.org.cn", education="本科", degree="学士",
         graduate_school="北京物资学院", major="市场营销",
         dept="会员服务部", position="会员服务主管", grade="中级",
         join_date="2020-11-03", regular_date="2021-02-03", year_point=0, total_point=0,
         home_address="北京市通州区", emergency_contact="家属", emergency_phone="13700000014",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG007", employee_name="奚莎莎", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1998-06-11", nation="汉族",
         political_status="共青团员", marital_status="未婚", mobile="13700000007",
         email="xiss@cfrp.org.cn", education="本科", degree="学士",
         graduate_school="北京第二外国语学院", major="英语",
         dept="会员服务部", position="会员服务专员", grade="科员",
         join_date="2023-03-06", regular_date="2023-06-06", year_point=0, total_point=0,
         home_address="北京市西城区", emergency_contact="家属", emergency_phone="13700000015",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG008", employee_name="赵旭东", gender="男", employee_status="在职",
         work_nature="全职", birth_date="1996-12-03", nation="汉族",
         political_status="群众", marital_status="未婚", mobile="13700000008",
         email="zhaoxd@cfrp.org.cn", education="本科", degree="学士",
         graduate_school="天津科技大学", major="材料成型与控制",
         dept="会员服务部", position="会员服务专员", grade="科员",
         join_date="2023-08-14", regular_date="2023-11-14", year_point=0, total_point=0,
         home_address="北京市大兴区", emergency_contact="家属", emergency_phone="13700000016",
         remark="", create_time=NOW, update_time=NOW),
    dict(employee_no="YG009", employee_name="罗舒涵", gender="女", employee_status="在职",
         work_nature="全职", birth_date="1997-03-22", nation="汉族",
         political_status="群众", marital_status="未婚", mobile="13700000009",
         email="luosh@cfrp.org.cn", education="硕士", degree="硕士",
         graduate_school="对外经济贸易大学", major="国际贸易",
         dept="国际业务部", position="国际业务专员", grade="初级",
         join_date="2024-02-19", regular_date="2024-05-19", year_point=0, total_point=0,
         home_address="北京市朝阳区", emergency_contact="家属", emergency_phone="13700000017",
         remark="", create_time=NOW, update_time=NOW),
]

# ---------------- 员工积分 ----------------
POINTS = [
    dict(employee_no="YG004", employee_name="时晓明", dept="行业研究部", position="研究员",
         point_year="2026", point_type="科研贡献", year_point=120, total_point=320,
         point_source="项目立项", relate_biz="XM2026-001", grant_date="2026-01-15",
         honor_level="季度之星", rank_no=1, grant_reason="牵头完成轻量化项目立项",
         point_status="已生效", dept_avg_point=85, dept_rank=1, create_time=NOW, update_time=NOW),
    dict(employee_no="YG005", employee_name="杜阳", dept="行业研究部", position="助理研究员",
         point_year="2026", point_type="科研贡献", year_point=90, total_point=190,
         point_source="里程碑达成", relate_biz="XM2026-002", grant_date="2026-07-10",
         honor_level="", rank_no=2, grant_reason="回收工艺路线提前达成",
         point_status="已生效", dept_avg_point=85, dept_rank=2, create_time=NOW, update_time=NOW),
    dict(employee_no="YG006", employee_name="李静", dept="会员服务部", position="会员服务主管",
         point_year="2026", point_type="服务贡献", year_point=110, total_point=260,
         point_source="会员普查", relate_biz="XM2026-003", grant_date="2026-07-01",
         honor_level="", rank_no=1, grant_reason="完成200家会员需求普查",
         point_status="已生效", dept_avg_point=82, dept_rank=1, create_time=NOW, update_time=NOW),
]

# ---------------- 岗位池 ----------------
JOBS = [
    dict(job_no="GW2026-001", job_name="复合材料工艺研究员", recruit_dept="行业研究部",
         recruit_count=1, standard_grade="中级", bid_type="内部竞聘", job_type="技术岗",
         job_category="科研序列", publish_date="2026-05-06", deadline="2026-05-20",
         interview_date="2026-05-25", job_status="已结束", work_place="北京",
         salary_range="15-20万/年", education_req="硕士及以上", experience_req="3年以上",
         job_duty="承担复合材料成型工艺研发与中试", job_require="材料相关专业，熟悉RTM/热压罐工艺",
         apply_count=2, create_time=NOW, update_time=NOW),
    dict(job_no="GW2026-002", job_name="国际业务专员", recruit_dept="国际业务部",
         recruit_count=1, standard_grade="初级", bid_type="公开招聘", job_type="业务岗",
         job_category="业务序列", publish_date="2026-08-01", deadline="2026-08-20",
         interview_date="2026-08-28", job_status="招聘中", work_place="北京",
         salary_range="10-14万/年", education_req="本科及以上", experience_req="2年以上",
         job_duty="负责国际会员拓展与国际交流项目", job_require="英语熟练，国际贸易相关专业优先",
         apply_count=0, create_time=NOW, update_time=NOW),
]

# ---------------- 岗位报名 ----------------
JOB_APPLIES = [
    dict(apply_no="BM2026-001", job_no="GW2026-001", job_name="复合材料工艺研究员",
         recruit_dept="行业研究部", employee_no="YG005", employee_name="杜阳",
         dept="行业研究部", position="助理研究员", grade="初级",
         join_date="2022-07-01", apply_date="2026-05-08",
         apply_reason="希望承担更核心的工艺研发任务",
         self_advantage="主导碳纤维回收工艺路线设计，熟悉多种成型工艺",
         career_plan="3年内成长为工艺方向骨干研究员", is_summary=False,
         apply_status="已通过", interview_score=88.5, apply_result="竞聘成功",
         remark="", create_time=NOW),
    dict(apply_no="BM2026-002", job_no="GW2026-001", job_name="复合材料工艺研究员",
         recruit_dept="行业研究部", employee_no="YG007", employee_name="奚莎莎",
         dept="会员服务部", position="会员服务专员", grade="科员",
         join_date="2023-03-06", apply_date="2026-05-09",
         apply_reason="希望转向技术研究岗位",
         self_advantage="英语能力强，可支撑国际文献检索",
         career_plan="转向复合材料技术研究", is_summary=False,
         apply_status="未通过", interview_score=72.0, apply_result="未通过",
         remark="专业背景与岗位要求匹配度不足", create_time=NOW),
]

# ---------------- 请假记录 ----------------
LEAVES = [
    dict(leave_no="QJ2026-001", employee_no="YG005", employee_name="杜阳",
         dept="行业研究部", leave_type="年休假", start_time="2026-04-06 09:00:00",
         end_time="2026-04-08 18:00:00", leave_days=3.0, leave_reason="个人年假",
         handover_person="时晓明", leave_status="已批准", create_time=NOW),
    dict(leave_no="QJ2026-002", employee_no="YG007", employee_name="奚莎莎",
         dept="会员服务部", leave_type="病假", start_time="2026-06-11 09:00:00",
         end_time="2026-06-12 18:00:00", leave_days=2.0, leave_reason="感冒发热",
         handover_person="赵旭东", leave_status="已批准", create_time=NOW),
]

# ---------------- 加班记录 ----------------
OVERTIMES = [
    dict(overtime_no="JB2026-001", employee_no="YG004", employee_name="时晓明",
         dept="行业研究部", overtime_type="工作日加班",
         start_time="2026-03-25 18:00:00", end_time="2026-03-25 21:30:00",
         overtime_hours=3.5, overtime_reason="工艺方案评审材料准备",
         project_no="XM2026-001", compensate_type="调休", overtime_status="已确认",
         create_time=NOW),
    dict(overtime_no="JB2026-002", employee_no="YG003", employee_name="李芳",
         dept="综合管理部", overtime_type="休息日加班",
         start_time="2026-07-04 09:00:00", end_time="2026-07-04 17:00:00",
         overtime_hours=8.0, overtime_reason="半年财务结账",
         project_no="", compensate_type="加班费", overtime_status="已确认",
         create_time=NOW),
]

# ---------------- 出差记录 ----------------
TRAVELS = [
    dict(travel_no="CC2026-001", employee_no="YG004", employee_name="时晓明",
         dept="行业研究部", travel_type="国内出差", destination="上海",
         start_date="2026-03-16", end_date="2026-03-19", travel_days=4.0,
         budget_amount=20000, actual_amount=18600, project_no="XM2026-001",
         travel_reason="中试线设备选型考察", travel_status="已报销", create_time=NOW),
    dict(travel_no="CC2026-002", employee_no="YG009", employee_name="罗舒涵",
         dept="国际业务部", travel_type="国内出差", destination="广州",
         start_date="2026-08-12", end_date="2026-08-14", travel_days=3.0,
         budget_amount=12000, actual_amount=0, project_no="",
         travel_reason="国际复合材料展会前期对接", travel_status="审批中", create_time=NOW),
]

# ---------------- 考勤记录 ----------------
ATTENDS = [
    dict(attend_no="KQ2026-001", employee_no="YG004", employee_name="时晓明",
         dept="行业研究部", attend_period="2026-03", period_start="2026-03-01",
         period_end="2026-03-31", should_days=21, actual_days=21, late_count=0,
         early_count=0, absent_count=0, leave_days=0, overtime_hours=3.5,
         travel_days=4, attend_status="待确认", emp_confirm=False, create_time=NOW),
    dict(attend_no="KQ2026-002", employee_no="YG003", employee_name="李芳",
         dept="综合管理部", attend_period="2026-03", period_start="2026-03-01",
         period_end="2026-03-31", should_days=21, actual_days=21, late_count=1,
         early_count=0, absent_count=0, leave_days=0, overtime_hours=0,
         travel_days=0, attend_status="已确认", emp_confirm=True, create_time=NOW),
]

# ---------------- 积分悬赏 ----------------
BOUNTIES = [
    dict(bounty_no="XS2026-001", bounty_title="编制复合材料回收工艺企业标准草案",
         bounty_score=150, score_tag="技术攻关", bounty_type="任务悬赏",
         publish_dept="行业研究部", publisher="孟弋洁", publish_date="2026-06-01",
         deadline="2026-08-31", bounty_status="已完成", bounty_desc="形成标准草案初稿",
         bounty_require="熟悉复合材料回收工艺，具备标准编写经验",
         taker_no="YG005", finish_date="2026-08-25", remark="", create_time=NOW),
    dict(bounty_no="XS2026-002", bounty_title="整理国际复合材料行业年报摘要",
         bounty_score=80, score_tag="资料整理", bounty_type="任务悬赏",
         publish_dept="国际业务部", publisher="卢宏萍", publish_date="2026-07-01",
         deadline="2026-09-30", bounty_status="进行中", bounty_desc="翻译并摘要核心数据",
         bounty_require="英语读写熟练", taker_no="", finish_date="", remark="",
         create_time=NOW),
]

# ---------------- 员工自助申请 ----------------
SELFS = [
    dict(self_no="ZZ2026-001", employee_no="YG003", employee_name="李芳",
         dept="综合管理部", self_type="收入证明", apply_title="开具在职收入证明",
         start_time="2026-08-05 09:00:00", end_time="", current_step="人事专员处理",
         self_status="已办结", apply_content="用于办理住房贷款，需开具近6个月收入证明",
         contact_phone="13700000003", create_time=NOW, update_time=NOW),
    dict(self_no="ZZ2026-002", employee_no="YG008", employee_name="赵旭东",
         dept="会员服务部", self_type="名片印制", apply_title="印制新职务名片",
         start_time="2026-09-10 09:00:00", end_time="", current_step="部门负责人审批",
         self_status="审批中", apply_content="因职务调整需重新印制名片200张",
         contact_phone="13700000008", create_time=NOW, update_time=NOW),
]

# ---------------- 人事变动 ----------------
CHANGES = [
    dict(change_no="BD2026-001", change_type="转正", employee_no="YG009",
         employee_name="罗舒涵", gender="女", old_dept="国际业务部",
         old_position="国际业务专员", new_dept="国际业务部",
         new_position="国际业务专员", old_grade="试用", new_grade="初级",
         old_status="试用", new_status="在职", work_nature="全职",
         effect_date="2026-05-19", apply_date="2026-05-06",
         change_reason="试用期满考核合格", approve_status="已通过",
         publish_flag=False, remark="", create_time=NOW),
]

# ---------------- 员工履历明细 ----------------
EMP_DETAILS = [
    dict(employee_no="YG004", employee_name="时晓明", detail_type="教育经历",
         school="哈尔滨工业大学", major="材料科学与工程", education="硕士",
         degree="硕士", start_date="2011-09-01", end_date="2014-06-30",
         work_desc="", remark="", create_time=NOW),
    dict(employee_no="YG004", employee_name="时晓明", detail_type="工作经历",
         company="某航空材料研究院", position="工程师", start_date="2014-07-01",
         end_date="2021-03-31", work_desc="从事树脂基复合材料成型工艺研究",
         remark="", create_time=NOW),
    dict(employee_no="YG004", employee_name="时晓明", detail_type="职称",
         tech_name="工程师（中级）", start_date="2018-12-01", end_date="",
         remark="", create_time=NOW),
]

# 表 id -> 行数据
SEED = {
    "t1001001-project-master-table-00000001": PROJECTS,
    "t2002001-contract-main-table-0000000001": CONTRACTS,
    "t2002007-contract-partner-table-0000000001": PARTNERS,
    "t2002003-contract-receive-table-000000001": RECEIVES,
    "t3003001-budget-master-table-000000001": BUDGETS,
    "t3003002-budget-detail-table-000000001": BUDGET_DETAILS,
    "t4004001-expense-master-table-00000001": EXPENSES,
    "t4004002-payment-master-table-00000001": PAYMENTS,
    "t4004003-cost-summary-table-000000001": COST_SUMMARY,
    "t5005001-archive-master-table-00000001": ARCHIVES,
    "t5005003-archive-link-table-000000001": ARCHIVE_LINKS,
    "t5005002-archive-borrow-table-00000001": ARCHIVE_BORROWS,
    "t6006001-hr-employee-table-000000000001": EMPLOYEES,
    "t6006006-hr-point-table-0000000000001": POINTS,
    "t6006004-hr-job-table-0000000000000001": JOBS,
    "t6006005-hr-job-apply-table-00000000001": JOB_APPLIES,
    "t6006009-hr-leave-table-000000000000001": LEAVES,
    "t6006010-hr-overtime-table-00000000001": OVERTIMES,
    "t6006011-hr-travel-table-0000000000001": TRAVELS,
    "t6006008-hr-attend-table-0000000000001": ATTENDS,
    "t6006007-hr-bounty-table-0000000000001": BOUNTIES,
    "t6006012-hr-self-table-0000000000000001": SELFS,
    "t6006003-hr-change-table-0000000000001": CHANGES,
    "t6006002-hr-emp-detail-table-0000000001": EMP_DETAILS,
}


def mysql(sql):
    cmd = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
           "-uo2oa", "-po2oa_pwd", "X", "-N", "-B", "-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                       encoding="utf-8", errors="replace")
    return [l for l in (r.stdout or "").splitlines() if "Warning" not in l]


def insert_rows(tid, rows, token):
    url = "%s/x_query_assemble_designer/jaxrs/table/%s/row" % (BASE, tid)
    data = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"x-token": token,
                                          "Content-Type": "application/json"},
                                 method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=180)
        body = json.loads(r.read().decode("utf-8", "ignore"))
        return True, body.get("data", {}).get("value", 0)
    except urllib.error.HTTPError as e:
        return False, e.read().decode("utf-8", "ignore")[:300].replace("\n", " ")
    except Exception as e:
        return False, str(e)


def clear_all():
    """清空全部 31 张自建表的物理表数据。"""
    rows = mysql("SELECT xname FROM QRY_SCH_TABLE WHERE xid LIKE 't%';")
    for n in rows:
        n = n.strip()
        if n:
            mysql("DELETE FROM QRY_DYN_%s;" % n.upper())
    print("  已清空 %d 张物理表\n" % len(rows))


def main():
    if "--clear" in sys.argv:
        print("清空目标表 ...")
        clear_all()

    token = get_token()
    print("[token] 长度 %d\n" % len(token))

    ok = fail = 0
    total_rows = 0
    for tid, rows in SEED.items():
        good, n = insert_rows(tid, rows, token)
        if good:
            ok += 1
            total_rows += (n if isinstance(n, int) else 0)
            print("  OK  %-46s %s 行" % (tid, n))
        else:
            fail += 1
            print("  ERR %-46s %s" % (tid, n))
    print("\n共 %d 张表：成功 %d，失败 %d，累计写入 %d 行"
          % (len(SEED), ok, fail, total_rows))


if __name__ == "__main__":
    main()
