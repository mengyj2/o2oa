# -*- coding: utf-8 -*-
"""_audit_org.py —— 组织职务(UnitDuty) → 身份(Identity) 绑定完整性审计。

背景（2026-09-20）：
  流程人工节点的处理人脚本形如 this.org.getDuty("部门负责人", "综合管理部")。
  该 API 走 UnitDuty 的 identityList；若某职务没绑身份，**不会报错**，
  O2OA 会静默把待办送给拟稿人 —— 审批链形同虚设。
  故必须逐个职务核对「绑了几个身份」。

用法：python _audit_org.py
"""
import os
import sys

BUILD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUILD)

import fix_statement_sql as F          # noqa: E402

EXPECT = {
    # 部门名 -> 应设职务
    "综合管理部": ["部门负责人", "人事专员", "财务专员", "档案管理员", "合同管理员"],
    "行业研究部": ["部门负责人"],
    "会员服务部": ["部门负责人"],
    "国际业务部": ["部门负责人"],
    "中国复合材料工业协会": ["秘书长", "副秘书长"],
}


def main():
    units = {r[0]: r[1] for r in F.qrow("SELECT xid, xname FROM ORG_UNIT;")}
    duties = F.qrow("SELECT xid, xname, xunit FROM ORG_UNITDUTY;")
    # 关联表列名：UNITDUTY_XID（外键无 x 前缀）、xidentityList（值）、xorderColumn
    ilist = F.qrow("SELECT UNITDUTY_XID, xidentityList "
                   "FROM ORG_UNITDUTY_identityList;")
    if not ilist:
        cols = F.qrow("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.columns "
                      "WHERE table_schema='X' AND TABLE_NAME='ORG_UNITDUTY_identityList';")
        print("[WARN] identityList 列名需确认：", cols)

    by_duty = {}
    for row in ilist:
        if len(row) >= 2:
            by_duty.setdefault(row[0], []).append(row[1])

    # identityList 存的是 ORG_IDENTITY.xid（UUID），需回查人名
    ident = {}
    for r in F.qrow("SELECT xid, xname, xunitName, xdistinguishedName FROM ORG_IDENTITY;"):
        if len(r) >= 3:
            ident[r[0]] = (r[1], r[2])

    print("组织单元 %d 个，职务 %d 条，职务-身份绑定 %d 条\n"
          % (len(units), len(duties), len(ilist)))
    print("%-16s %-12s %-6s %s" % ("部门", "职务", "身份数", "绑定人"))
    print("-" * 78)

    bad = 0
    seen = set()
    for did, dname, unit in duties:
        uname = units.get(unit, "(未知单元 %s)" % unit)
        ids = by_duty.get(did, [])
        people = []
        for dn in ids:
            nm = ident.get(dn, (dn, "?"))
            people.append("%s@%s" % (nm[0], nm[1]))
        flag = "" if ids else "  <<< 未绑身份！"
        if not ids:
            bad += 1
        print("%-16s %-12s %-6d %s%s"
              % (uname, dname, len(ids), "、".join(people), flag))
        seen.add((uname, dname))

    print("\n=== 期望 vs 实际 ===")
    missing = []
    for uname, want in EXPECT.items():
        for w in want:
            if (uname, w) not in seen:
                missing.append("%s / %s" % (uname, w))
    if missing:
        for m in missing:
            print("  [缺失] %s" % m)
    else:
        print("  全部到位")

    extra = [k for k in seen if k[0] in EXPECT and k[1] not in EXPECT[k[0]]]
    for e in extra:
        print("  [多余] %s / %s" % e)

    print("\n未绑身份的职务数：%d" % bad)
    return 0 if (bad == 0 and not missing) else 1


if __name__ == "__main__":
    sys.exit(main())
