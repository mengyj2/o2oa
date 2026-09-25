# -*- coding: utf-8 -*-
"""
模拟 O2OA 渲染引擎的 DOM 树重建，验证嵌套结构可被正确还原
========================================

O2OA 渲染流程（源码依据）：

  1. 服务端把 WrapForm.data（字符串）解析为 JSON
  2. 前端 Form.js 用 moduleList 和表单的 style/布局信息**构建 DOM**
  3. 再 **反向遍历 DOM**（_getModuleNodes）来实例化组件

本脚本模拟第 2、3 步，把 moduleList 按嵌套关系还原成 DOM 树，
再按 _getModuleNodes 的规则遍历，检查：

  R1  还原出的 DOM 树中，每个字段都在某个容器内部（非裸挂）
  R2  遍历顺序与 moduleList 的 DFS 顺序一致（说明渲染顺序正确）
  R3  所有模块都被遍历到（没有孤儿模块）

如果这三项通过，说明导入后 O2OA 会按预期渲染出带版式的界面。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONTAINER = {"Div", "Table", "Table$Td", "Tab", "Tab$Page", "Tab$Content",
             "Elcontainer", "Elcontainer$Container"}


class DomNode:
    def __init__(self, mid, mtype):
        self.id = mid
        self.mwftype = mtype
        self.children = []
        self.parent = None

    def add(self, child):
        child.parent = self
        self.children.append(child)


def rebuild_dom(module_list):
    """
    按 moduleList 的 DFS 顺序 + 类型规则还原 DOM 树。

    规则（与 Page 树构建时一致）：
      - 容器（Div/Table/Table$Td）可含子节点
      - Table$Td 是 Table 的直接子节点，且 td 之间平级
      - 叶子节点挂在最近的容器下
    """
    root = DomNode("form", "form")
    stack = [root]

    for mid, m in module_list.items():
        t = m.get("type")
        mwft = m.get("MWFType", "")

        if t == "Table$Td":
            # td 必须挂在最近的 Table 下
            while stack and stack[-1].mwftype != "table" and len(stack) > 1:
                stack.pop()
            node = DomNode(mid, mwft)
            stack[-1].add(node)
            stack.append(node)
            continue

        if t in CONTAINER:
            # 若是 Div/Table，先弹出同层 td（td 不能嵌套新容器以外的兄弟）
            while len(stack) > 1 and stack[-1].mwftype == "table$td":
                stack.pop()
            node = DomNode(mid, mwft)
            stack[-1].add(node)
            stack.append(node)
            continue

        # 叶子
        node = DomNode(mid, mwft)
        stack[-1].add(node)

    return root


def get_module_nodes(node, out=None):
    """复刻 Form.js._getModuleNodes 的遍历顺序。"""
    if out is None:
        out = []
    for ch in node.children:
        if ch.mwftype:
            out.append(ch)
            if ch.mwftype not in ("datagrid", "datatable", "subsource",
                                  "tab$content", "datatemplate"):
                get_module_nodes(ch, out)
        else:
            get_module_nodes(ch, out)
    return out


def depths(node, d=0, out=None):
    if out is None:
        out = {}
    out[node.id] = d
    for ch in node.children:
        depths(ch, d + 1, out)
    return out


def main():
    import glob
    from validate_form_tree import load_design, LEAF_TYPES

    xapps = sorted(glob.glob(os.path.join(ROOT, "deliverables", "*.xapp")))
    print("=" * 74)
    print("DOM 树重建模拟（复刻 O2OA Form.js 渲染流程）")
    print("=" * 74)

    tot_err = 0
    tot_form = 0
    for xp in xapps:
        d = json.load(open(xp, encoding="utf-8"))
        for pl in d.get("processPlatformList") or []:
            for fw in pl.get("formList") or []:
                tot_form += 1
                design = load_design(fw)
                ml = design.get("moduleList") or {}
                if not ml:
                    continue

                root = rebuild_dom(ml)
                walked = get_module_nodes(root)
                walked_ids = [n.id for n in walked]

                errs = []

                # R1 字段必须在容器内
                dep = depths(root)
                for mid, m in ml.items():
                    if m.get("type") in LEAF_TYPES:
                        # 找父节点
                        found = False
                        def find(n):
                            nonlocal found
                            if n.id == mid and n.parent and \
                               n.parent.mwftype in ("div", "table$td", "table"):
                                found = True
                            for c in n.children:
                                find(c)
                        find(root)
                        if not found:
                            errs.append("R1 字段 %s 未落在容器内" % mid)

                # R2 遍历顺序应与 moduleList 顺序一致
                if walked_ids != list(ml.keys()):
                    miss = [k for k in ml if k not in walked_ids]
                    extra = [k for k in walked_ids if k not in ml]
                    if miss:
                        errs.append("R3 有 %d 个模块没被遍历到，例如 %s"
                                    % (len(miss), miss[:3]))
                    if extra:
                        errs.append("R3 遍历出 %d 个不存在的模块" % len(extra))
                    if not miss and not extra:
                        errs.append("R2 遍历顺序与 moduleList 顺序不一致")

                if errs:
                    tot_err += len(errs)
                    print("\n##### %s" % fw.get("name"))
                    for e in errs:
                        print("   ✗ %s" % e)

    print("\n" + "=" * 74)
    print("模拟表单 %d 个：问题 %d 个" % (tot_form, tot_err))
    print("=" * 74)
    return 1 if tot_err else 0


if __name__ == "__main__":
    sys.exit(main())
