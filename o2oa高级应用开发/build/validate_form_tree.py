# -*- coding: utf-8 -*-
"""
O2OA 表单嵌套结构校验器
========================================

【为什么需要】

O2OA 表单渲染引擎靠**遍历 DOM 树**挂载组件（见 o2oa_page.py 文档）。
如果 moduleList 里的容器是空的、或多列布局没有 td 承载字段，
导入后就会出现「所有控件平铺堆叠、版式尽失」——而且**不报错**，
只是在界面上难看。所以必须有一道程序化校验拦住它。

【校验项】

  V1  模块 id 唯一
  V2  每个模块有 type / MWFType
  V3  容器（Div/Table）必须有子节点（非空容器 = 排版失效）
  V4  每个字段父链上必须存在容器（裸字段会被 O2OA 直接挂在 form 根下）
  V5  Table 必须至少有一个 Table$Td 子节点
  V6  每个 Table$Td 必须至少有一个字段子节点
  V7  字段名用 styles（复数）而非 style
  V8  字段必须有 events 字典
  V9  容器嵌套深度不应超过 14 层（官方版式固有 4~13 层，见下方注释）
  V10 form 的 moduleList 不能为空

【用法】

    python validate_form_tree.py
    python validate_form_tree.py --verbose
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONTAINER_TYPES = {
    "Div", "Table", "Table$Td", "Tab", "Tab$Page", "Tab$Content",
    "Elcontainer", "Elcontainer$Container",
}
# 这些容器的子节点不走 moduleList（自行管理）
SELF_MANAGED = {"Table"}

# 叶子控件（必须有 styles/events，不能有子节点）
LEAF_TYPES = {
    "Label", "Textfield", "Textarea", "Number", "Currency", "Calendar",
    "Select", "Radio", "Checkbox", "Combox", "Org", "Opinion", "Attachment",
    "Actionbar", "Html", "Button", "Image",
}
# 「整块内容」控件：在 DOM 上表现为单个元素，但内部自带子结构
# （Datagrid 的标题行/数据行存在 titleList/dataList，不进 moduleList）。
# 它们放在 <td> 里是官方标准用法（如合同审批表的付款计划明细），
# 因此 V6 判定「td 内必须有内容」时应一并计入。
CONTENT_TYPES = LEAF_TYPES | {"Datagrid", "Subform", "Datatable", "Tab"}


def load_design(form_wrap):
    """从 WrapForm 取出设计器 JSON。

    ★ data 在 .xapp 里是「转义形态」（{\\\"json\\\":…}，前端经
      o2.decodeJsonString 解码），先转回来再 parse。
    """
    import o2oa_builder as OB
    data = form_wrap.get("data")
    if isinstance(data, str):
        if OB.is_escaped_json(data):
            data = OB.decode_json_string(data)
        return json.loads(data)
    return data


def check_form(form_wrap, verbose=False):
    """校验单个表单，返回 (errors, warnings, stats)。"""
    errors = []
    warnings = []
    name = form_wrap.get("name", "?")

    try:
        design = load_design(form_wrap)
    except Exception as e:
        return (["[致命] 表单 %s 的 data 无法解析为 JSON: %s" % (name, e)], [], {})

    ml = design.get("moduleList") or {}
    if not ml:
        errors.append("[V10] 表单 %s 的 moduleList 为空" % name)
        return (errors, warnings, {})

    # ---- V1 id 唯一（dict 天然唯一，这里查 id 字段与键是否一致） ----
    for k, v in ml.items():
        if v.get("id") and v.get("id") != k:
            errors.append("[V1] 表单 %s：键 %s 与模块 id %s 不一致" % (name, k, v.get("id")))

    # ---- V2 type / MWFType ----
    for k, v in ml.items():
        if not v.get("type"):
            errors.append("[V2] 表单 %s：模块 %s 缺 type" % (name, k))
        if not v.get("MWFType"):
            errors.append("[V2] 表单 %s：模块 %s 缺 MWFType" % (name, k))

    # ---- 建立父子关系（从 Page.tree 反推需要层级信息，这里用 id 前缀 + 类型判断） ----
    # 由于 moduleList 是扁平的，父子关系要靠「DFS 顺序 + 类型」推断：
    # 容器之后的连续非容器模块，属于该容器，直到遇到同层或上层容器。
    order = list(ml.keys())
    parent_of = {}
    # 容器栈。td **入栈**（Label/Field 的直接父级就是 td，叶子靠它认父），
    # 但计算嵌套深度时 td 不计入。
    path = []
    for mid in order:
        v = ml.get(mid, {})
        t = v.get("type")

        if t == "Table$Td":
            # td 的父 = 栈里最近的 Table（跨过已有的 td）
            tbl = None
            for pid in reversed(path):
                if ml.get(pid, {}).get("type") == "Table":
                    tbl = pid
                    break
            if not tbl:
                errors.append("[V5] 表单 %s：单元格 %s 找不到所属 Table" % (name, mid))
            else:
                parent_of[mid] = tbl
            # 同级 td 平级：先弹掉栈里已有 td，再压入自己
            while path and ml.get(path[-1], {}).get("type") == "Table$Td":
                path.pop()
            path.append(mid)
            continue

        if t in CONTAINER_TYPES:
            while path and ml.get(path[-1], {}).get("type") == "Table$Td":
                path.pop()

            # 【分区语义】官方表单里每个 Div 都是 form 的直接子节点、
            # 彼此平级（如「员工档案表」的 10 个分区）。DFS 展开顺序为
            # 「Div → Table → Td → … → 下一个 Div」，因此进入新 Div 时
            # 栈里属于**上一个分区**的 Div/Table 必须弹掉，否则第 N 个
            # 分区会被算成第 N 层（深度虚高，曾误报 V9）。
            # 但当前 Div 自身必须保留 —— 它的 Table/Td 子节点紧随其后。
            if t == "Div":
                while path and ml.get(path[-1], {}).get("type") in (
                        "Div", "Table"):
                    path.pop()
                parent_of[mid] = None
            else:
                parent_of[mid] = path[-1] if path else None
            path.append(mid)
            continue

        # 叶子模块：父级 = 栈顶容器（td / Table / Div）
        parent_of[mid] = path[-1] if path else None

    # ---- V3 容器非空 ----
    children = {}
    for mid, pid in parent_of.items():
        if pid:
            children.setdefault(pid, []).append(mid)

    for k, v in ml.items():
        t = v.get("type")
        if t in ("Div",):
            if not children.get(k):
                errors.append("[V3] 表单 %s：Div %s(%s) 是空容器，排版会失效"
                              % (name, k, v.get("name", "")))
        if t == "Table":
            tds = [c for c in children.get(k, [])
                   if ml.get(c, {}).get("type") == "Table$Td"]
            if not tds:
                errors.append("[V5] 表单 %s：Table %s 没有任何单元格" % (name, k))

    # ---- V4 字段必须有容器父级 ----
    for k, v in ml.items():
        t = v.get("type")
        if t in LEAF_TYPES:
            pid = parent_of.get(k)
            if not pid:
                errors.append("[V4] 表单 %s：字段 %s(%s) 没有容器父级，导入后会裸挂在表单根下"
                              % (name, k, v.get("name", "")))
            elif ml.get(pid, {}).get("type") not in CONTAINER_TYPES:
                warnings.append("[V4] 表单 %s：字段 %s 的父级 %s 不是容器"
                                % (name, k, pid))

    # ---- V6 每个 td 至少一个字段 ----
    for k, v in ml.items():
        if v.get("type") != "Table$Td":
            continue
        kids = children.get(k) or []
        leaves = [c for c in kids if ml.get(c, {}).get("type") in CONTENT_TYPES]
        if not leaves:
            errors.append("[V6] 表单 %s：单元格 %s 内没有任何字段" % (name, k))

    # ---- V7 styles 而非 style ----
    for k, v in ml.items():
        if "style" in v and "styles" not in v:
            errors.append("[V7] 表单 %s：模块 %s 用了 style，应改为 styles（复数）"
                          % (name, k))

    # ---- V8 字段必须有 events ----
    for k, v in ml.items():
        t = v.get("type")
        if t in LEAF_TYPES and "events" not in v:
            warnings.append("[V8] 表单 %s：模块 %s(%s) 缺 events" % (name, k, t))

    # ---- V9 嵌套深度 ----
    # 深度只统计「有版式意义的容器层级」：Div(分区) > Table > Datagrid 等。
    # Table$Td 是网格单元、不是嵌套层级（官方任意表单的 td 都在同一层），
    # 计入会把它当成额外一层，造成深度虚高。
    def depth(mid):
        d = 0
        cur = mid
        seen = set()
        while parent_of.get(cur):
            if cur in seen:
                break
            seen.add(cur)
            cur = parent_of[cur]
            if ml.get(cur, {}).get("type") != "Table$Td":
                d += 1
        return d

    max_depth = 0
    for k in ml:
        d = depth(k)
        max_depth = max(max_depth, d)
    # 【官方版式的固有深度】必须区分「设计深度」与「无谓嵌套」：
    #   普通字段   form > Div(分区) > Table > Table$Td > Label/Field      = 4
    #   Datagrid   form > Div(分区) > Table > Table$Td > Datagrid         = 4
    #   若 Datagrid 内部再放控件（官方常见），再 +2 层
    # 因此 4~6 层是官方标准形态。深度到 9~13 说明数据行内又嵌了
    # 输入类控件（官方「合同审批表的付款计划明细」就是这个形态），
    # **不是错误**，只在超过 14 层时提示。
    if max_depth > 14:
        warnings.append("[V9] 表单 %s：嵌套深度 %d 层，明显偏深，建议检查"
                        % (name, max_depth))

    # ---- 统计 ----
    types = {}
    for v in ml.values():
        types[v.get("type")] = types.get(v.get("type"), 0) + 1

    stats = {
        "name": name,
        "modules": len(ml),
        "max_depth": max_depth,
        "types": types,
        "containers": sum(1 for v in ml.values() if v.get("type") in CONTAINER_TYPES),
        "leaves": sum(1 for v in ml.values() if v.get("type") in LEAF_TYPES),
    }

    if verbose:
        print("  %-24s 模块 %3d  容器 %2d  字段 %2d  深度 %d"
              % (name, stats["modules"], stats["containers"],
                 stats["leaves"], stats["max_depth"]))
    return (errors, warnings, stats)


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    import glob

    xapps = sorted(glob.glob(os.path.join(ROOT, "deliverables", "*.xapp")))
    if not xapps:
        print("未找到 .xapp 文件")
        return 1

    print("=" * 74)
    print("O2OA 表单嵌套结构校验")
    print("=" * 74)

    tot_e = tot_w = tot_f = 0
    for xp in xapps:
        try:
            d = json.load(open(xp, encoding="utf-8"))
        except Exception as e:
            print("\n[%s] 读取失败：%s" % (os.path.basename(xp), e))
            tot_e += 1
            continue

        print("\n### %s" % os.path.basename(xp))
        for pl in d.get("processPlatformList") or []:
            for fw in pl.get("formList") or []:
                tot_f += 1
                errs, warns, stats = check_form(fw, verbose)
                tot_e += len(errs)
                tot_w += len(warns)
                for e in errs:
                    print("   ✗ %s" % e)
                for w in warns:
                    print("   ! %s" % w)

    print("\n" + "=" * 74)
    print("校验表单 %d 个：错误 %d 个，警告 %d 个" % (tot_f, tot_e, tot_w))
    print("=" * 74)
    return 1 if tot_e else 0


if __name__ == "__main__":
    sys.exit(main())
