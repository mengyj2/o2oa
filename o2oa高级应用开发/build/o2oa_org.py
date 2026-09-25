# -*- coding: utf-8 -*-
"""
中国复合材料工业协会 · 组织架构常量与处理人脚本（**唯一来源**）

================================================================================
一、为什么要有这个模块
================================================================================
六个应用（项目/合同/预算/财务/档案/人力）的流程节点都要"自动找处理人"。
处理人是写在 .xapp 里的 JS 脚本，运行时去 O2OA 组织库按名字查人。
**脚本里的部门名/职务名与 O2OA 里建的名字必须逐字一致。**

以前这些名字散落在 6 个 def_*.py 里各写一遍 —— 改一处漏五处。
现在全部收敛到本模块，六个应用统一 `from o2oa_org import *`。

================================================================================
二、组织树（需在 O2OA「组织管理 → 组织架构」中建好）
================================================================================
  中国复合材料工业协会                              [顶层组织]
  ├─ 职务：秘书长 / 副秘书长
  ├─ 综合部          1 人 · 人事 / 行政 / 财务 / 综合
  │   职务：部门负责人（秘书长兼）· 人事专员 · 财务专员 · 档案管理员 · 合同管理员
  ├─ 研究技术部      2 人 · 研究 / 行业 / 标准
  │   职务：部门负责人（秘书长兼）
  ├─ 会员服务部         会议 / 培训 / 展览
  │   职务：部门负责人（副秘书长兼）
  └─ 行业发展部         行业推进
      职务：部门负责人（副秘书长兼）

  分管关系：秘书长分管 综合部 · 研究技术部
            副秘书长分管 会员服务部 · 行业发展部

================================================================================
三、API 权威依据（2026-09 核对，两个独立来源）
================================================================================
① 官方 API 文档 https://www.o2oa.net/api/module-org.html
   · getDuty(dutyName, unit, asyncOrCallback?)  → 按「职务名 + 组织」取身份数组
   · getUnitByIdentity(name, flag?, async?)     → 由身份取组织（UnitData 含 name 字段）
   · listSupPerson(name, nested?, async?)       → 按 superior 汇报关系取上级人员
   · listIdentityWithUnit(unit, nested?)        → 按组织取身份数组
② O2OA 官方论坛管理员原话（forum.o2oa.net）
   · 「获取拟稿人所在部门的主管，首先需要在部门上维护好主管这个职务，
      再获取职务 var identityList = this.org.getDuty(dutyName, unit)」

【重要】以下两个方法名 **在 O2OA 中不存在**，早期版本曾误用，已全部修正：
   ✗ listIdentityWithUnitWithName(unit, duty)   → 正确：getDuty(duty, unit)
   ✗ listLeaderByIdentity(identity, bool)       → 正确：listSupPerson(person, bool)
   源码依据：x_organization_core_express/.../Organization.java 无这两个方法。

================================================================================
四、为什么「部门负责人」能自动对应到分管领导
================================================================================
您的情况：部门没有专职负责人，由两位分管领导兼任。
O2OA 的表达方式：**在部门上挂「部门负责人」职务，把分管领导选为该职务成员**。
（依据官方文档：「职务表示工作的类别，一个部门可以有多个职务」；
  「相关人员的变更只需要变更职务的设定，可以使流程和人员解耦」）

这样脚本 `getDuty('部门负责人', 发起人所在部门)` 会自动得到：
    综合管理部 / 行业研究部 的人发起  →  秘书长
    会员服务部 / 国际业务部 的人发起 →  副秘书长
**组织怎么调整，脚本都不用改。** 这就是官方所说的"动态计算职位"。
"""

# ==========================================================================
# 组织（单位 / 部门）
# ==========================================================================

ORG_UNIT = "中国复合材料工业协会"      # 顶层组织

DEPT_COMPREHENSIVE = "综合管理部"      # 人事 / 行政 / 财务 / 综合
DEPT_RESEARCH = "行业研究部"           # 研究 / 行业 / 标准
DEPT_MEMBER = "会员服务部"             # 会议 / 培训 / 展览
DEPT_INDUSTRY = "国际业务部"           # 国际业务

DEPARTMENTS = [DEPT_COMPREHENSIVE, DEPT_RESEARCH, DEPT_MEMBER, DEPT_INDUSTRY]

# 分管关系（脚本不写死，仅在文档与门户中呈现）
SECRETARY_GENERAL_DEPTS = [DEPT_COMPREHENSIVE, DEPT_RESEARCH]      # 秘书长分管
DEPUTY_SECRETARY_DEPTS = [DEPT_MEMBER, DEPT_INDUSTRY]              # 副秘书长分管

# ==========================================================================
# 职务
# ==========================================================================

DUTY_SECRETARY_GENERAL = "秘书长"          # 顶层组织职务 · 终审
DUTY_DEPUTY_SECRETARY = "副秘书长"         # 顶层组织职务
DUTY_DEPT_HEAD = "部门负责人"              # 部门职务 · 由分管领导兼任

DUTY_HR = "人事专员"                       # 综合部 · 人事 / 考勤 / 员工自助
DUTY_FINANCE = "财务专员"                  # 综合部 · 财务 / 出纳 / 预算
DUTY_ARCHIVE = "档案管理员"                # 综合部 · 档案
DUTY_CONTRACT = "合同管理员"               # 综合部 · 合同

# ==========================================================================
# 处理人脚本
# ==========================================================================
# 说明：脚本在 O2OA 后端以 Nashorn/GraalVM 执行，return 身份对象/数组即可。
#      O2OA 官方口径：「找不到处理人时就是送给拟稿人」——
#      因此下列脚本都做了空值保护，避免意外回落到拟稿人。

# ---- 发起人本人 ----
SCRIPT_SELF = "return this.workContext.getWork().creatorIdentityDn;"

# ---- 发起人所在部门的「部门负责人」--------------------------------------
# 不写死部门名：先由身份反查所在部门，再取该部门的负责人职务。
# 综合部/研究技术部 → 秘书长；会员服务部/行业发展部 → 副秘书长。
SCRIPT_DEPT_MGR = (
    "var dn = this.workContext.getWork().creatorIdentityDn;\n"
    "var unit = this.org.getUnitByIdentity(dn);\n"
    "if (unit && unit.length && !unit.name) { unit = unit[0]; }\n"
    "var unitName = (unit && unit.name) ? unit.name : '';\n"
    "return unitName ? this.org.getDuty('" + DUTY_DEPT_HEAD + "', unitName) : [];"
)

# 兼容别名（早期各文件叫法不一，统一指向同一语义：发起人所在部门的负责人）
SCRIPT_DEPT_LEADER = SCRIPT_DEPT_MGR

# ---- 终审：秘书长（顶层组织职务）----
SCRIPT_GM = (
    "return this.org.getDuty('" + DUTY_SECRETARY_GENERAL + "', '" + ORG_UNIT + "');"
)

# ---- 上级领导（按人员汇报关系 superior 逐级上溯）----
SCRIPT_LEADER = (
    "return this.org.listSupPerson(this.workContext.getWork().creatorIdentityDn, true);"
)
SCRIPT_DIRECT_LEADER = (
    "return this.org.listSupPerson(this.workContext.getWork().creatorIdentityDn, false);"
)

# ---- 综合部各职能经办人 ----
SCRIPT_HR_ADMIN = (
    "return this.org.getDuty('" + DUTY_HR + "', '" + DEPT_COMPREHENSIVE + "');"
)
SCRIPT_FINANCE = (
    "return this.org.getDuty('" + DUTY_FINANCE + "', '" + DEPT_COMPREHENSIVE + "');"
)
SCRIPT_CASHIER = SCRIPT_FINANCE          # 协会无独立出纳，由综合部同一人担任
SCRIPT_BUDGET = SCRIPT_FINANCE           # 预算编制同
SCRIPT_ARCHIVE = (
    "return this.org.getDuty('" + DUTY_ARCHIVE + "', '" + DEPT_COMPREHENSIVE + "');"
)
SCRIPT_ARCHIVE_DIR = SCRIPT_ARCHIVE      # 档案主管同
SCRIPT_CONTRACT_ADMIN = (
    "return this.org.getDuty('" + DUTY_CONTRACT + "', '" + DEPT_COMPREHENSIVE + "');"
)
SCRIPT_LEGAL = SCRIPT_CONTRACT_ADMIN     # 协会无法务部，合同审查归综合部
SCRIPT_ATTEND_ADMIN = SCRIPT_HR_ADMIN    # 考勤归人事

# ---- 综合部全体（用于"综合部经办"这类节点，需排除发起人）----
# 例：this.org.listIdentityWithUnit('综合部', false) 取该部门全部身份
SCRIPT_COMPREHENSIVE_DEPT = (
    "return this.org.listIdentityWithUnit('" + DEPT_COMPREHENSIVE + "', false);"
)

# ==========================================================================
# 路由条件脚本（选择节点用）
# ==========================================================================
# 官方口径：「选择节点出来的路由上，右侧属性有条件设置，return true 走这条，
#            return false 不走。条件必须互斥，只能一条 return true」

# 判断「部门负责人」是否与「秘书长」是同一人（兼任情形）。
# 同一人时，部门负责人这一级应跳过，避免秘书长连签两次。
_COND_PRELUDE = (
    "var dn = this.workContext.getWork().creatorIdentityDn;\n"
    "var unit = this.org.getUnitByIdentity(dn);\n"
    "if (unit && unit.length && !unit.name) { unit = unit[0]; }\n"
    "var unitName = (unit && unit.name) ? unit.name : '';\n"
    "var mgrList = unitName ? this.org.getDuty('" + DUTY_DEPT_HEAD + "', unitName) : [];\n"
    "var gmList = this.org.getDuty('" + DUTY_SECRETARY_GENERAL + "', '" + ORG_UNIT + "');\n"
    "var mgrDn = (mgrList && mgrList.length) ? mgrList[0].distinguishedName : '';\n"
    "var gmDn = (gmList && gmList.length) ? gmList[0].distinguishedName : '';\n"
)

# true  → 部门负责人与秘书长不是同一人 → **需要**走「部门负责人」这一级
ROUTE_NEED_DEPT_HEAD = (
    _COND_PRELUDE
    + "return (mgrDn !== '' && mgrDn !== gmDn);"
)

# false → 同一人（或该部门未设负责人）→ **跳过**部门负责人级，直接进综合部
ROUTE_SKIP_DEPT_HEAD = (
    _COND_PRELUDE
    + "return (mgrDn === '' || mgrDn === gmDn);"
)

# ==========================================================================
# 人工节点活动名（统一命名，便于门户与文档引用）
# ==========================================================================

ACT_APPLY = "申请提交"             # 发起人填单
ACT_DEPT_HEAD = "部门负责人审核"    # 分管领导（兼任）
ACT_COMPREHENSIVE = "综合管理部审核"    # 人事 / 财务经办
ACT_GM = "秘书长终审"
ACT_EXECUTE = "综合管理部办理"          # 秘书长批完后的执行环节
ACT_ROUTE_SKIP = "是否需部门负责人"

__all__ = [n for n in dir() if not n.startswith("_")]
