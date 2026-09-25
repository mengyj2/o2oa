# -*- coding: utf-8 -*-
"""
流程拓扑校验器（T1~T8）

为什么需要它
------------
O2OA 的流程「图」不是存在一个字段里的，而是由**两处**共同表达：
    · Route.activity            = 目标活动 id
    · Manual/Choice.routeList   = 本活动的**出口**路由 id 列表
    · Begin.route               = 开始活动的出口路由 id（单值）
源码依据见 o2oa_builder.ProcessBuilder.to_wrap() 内注释。

早期版本只写了目标、且写错字段名（arriveActivity 在 O2OA 中不存在），
活动上也没写出口 —— 结果「源」和「目标」双空，导入后流程无法流转。
表单树校验器只看表单 DOM，看不到这个问题，所以必须单独校验流程拓扑。

校验项
------
  T1  每条路由的 activity（目标）非空且指向真实存在的节点
  T2  每个活动 routeList 里的路由 id 都真实存在
  T3  开始活动有出口路由（否则流程实例不离开开始节点）
  T4  所有节点都从开始活动可达（无孤儿分支）
  T5  每个人工节点都绑定了表单
  T6  每条路由都有源（被某个活动的出口列表收录）
  T7  结束活动没有出口路由
  T8  并行/分支节点数 ≥ 2 的，其出口路由数也 ≥ 2

用法：python validate_flow_topology.py
"""

import json
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.join(os.path.dirname(HERE), "deliverables")

MULTI_OUT_TYPES = ("manualList", "choiceList", "splitList", "parallelList",
                   "serviceList", "invokeList", "agentList", "delayList",
                   "embedList", "mergeList")
NODE_KEYS = ("manualList", "choiceList", "endList", "splitList", "mergeList",
             "parallelList", "serviceList", "invokeList", "agentList",
             "delayList", "embedList", "cancelList", "publishList")


def check_process(proc, errs, warns):
    name = proc.get("name", "?")
    begin = proc.get("begin") or {}
    bid = begin.get("id")

    # 收集节点
    nodes = {}
    if bid:
        nodes[bid] = "begin"
    for k in NODE_KEYS:
        for a in proc.get(k) or []:
            nodes[a.get("id")] = k

    routes = proc.get("routeList") or []
    rmap = {}
    for r in routes:
        rid = r.get("id")
        if rid in rmap:
            errs.append("[T0] 流程 %s：路由 id %s 重复" % (name, rid))
        rmap[rid] = r

    # 出口表
    out = {}
    if bid and begin.get("route"):
        out[bid] = [begin.get("route")]
    for k in MULTI_OUT_TYPES:
        for a in proc.get(k) or []:
            for rid in a.get("routeList") or []:
                out.setdefault(a.get("id"), []).append(rid)

    # ---- T1 目标有效 ----
    for r in routes:
        tgt = r.get("activity")
        if not tgt:
            errs.append("[T1] 流程 %s：路由「%s」目标为空"
                        % (name, r.get("name") or r.get("id")))
        elif tgt not in nodes:
            errs.append("[T1] 流程 %s：路由「%s」目标 %s 不是本流程的节点"
                        % (name, r.get("name") or r.get("id"), tgt))
        if r.get("arriveActivity"):
            errs.append("[T1] 流程 %s：路由「%s」仍含废弃字段 arriveActivity"
                        % (name, r.get("name") or r.get("id")))

    # ---- T2 出口指向真实路由 ----
    for nid, ids in out.items():
        for rid in ids:
            if rid not in rmap:
                errs.append("[T2] 流程 %s：节点 %s 的出口 %s 不存在"
                            % (name, nid, rid))

    # ---- T3 begin 有出口 ----
    if not begin.get("route"):
        errs.append("[T3] 流程 %s：开始活动没有出口路由" % name)

    # ---- T4 可达性 ----
    if bid:
        seen, stack = set(), [bid]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            for rid in out.get(n, []):
                r = rmap.get(rid)
                if r and r.get("activity"):
                    stack.append(r["activity"])
        missed = [i for i in nodes if i not in seen]
        if missed:
            errs.append("[T4] 流程 %s：%d 个节点从开始活动不可达" % (name, len(missed)))

    # ---- T5 人工节点绑表单 ----
    for a in proc.get("manualList") or []:
        if not a.get("form"):
            errs.append("[T5] 流程 %s：人工节点「%s」未绑定表单"
                        % (name, a.get("name")))

    # ---- T6 每条路由都有源 ----
    for r in routes:
        if r.get("id") not in {x for v in out.values() for x in v}:
            errs.append("[T6] 流程 %s：路由「%s」没有源活动"
                        % (name, r.get("name") or r.get("id")))

    # ---- T7 结束节点无出口 ----
    for a in proc.get("endList") or []:
        if a.get("routeList"):
            errs.append("[T7] 流程 %s：结束节点「%s」不该有出口路由"
                        % (name, a.get("name")))

    # ---- T8 分支节点出口数 ----
    for k in ("choiceList", "splitList", "parallelList"):
        for a in proc.get(k) or []:
            n = len(a.get("routeList") or [])
            if n < 2:
                warns.append("[T8] 流程 %s：%s 节点「%s」只有 %d 条出口"
                             % (name, k, a.get("name"), n))

    # ---- 附带检查：处理人脚本不得使用不存在的 API ----
    bad_apis = ("listIdentityWithUnitWithName", "listLeaderByIdentity")
    for k in ("manualList",):
        for a in proc.get(k) or []:
            ts = a.get("taskScriptText") or ""
            for b in bad_apis:
                if b in ts:
                    errs.append("[T9] 流程 %s：节点「%s」调用了不存在的 API %s"
                                % (name, a.get("name"), b))

    return len(nodes), len(routes)


def main():
    files = sorted(glob.glob(os.path.join(DELIV, "*.xapp")))
    if not files:
        print("未找到 .xapp，请先运行 pack.py")
        return 1

    total_proc = total_err = total_warn = 0
    print("=" * 72)
    print("流程拓扑校验（T1~T9）")
    print("=" * 72)

    for fp in files:
        data = json.load(open(fp, encoding="utf-8"))
        procs = []
        for pp in data.get("processPlatformList") or []:
            procs.extend(pp.get("processList") or [])
        if not procs:
            continue

        errs, warns = [], []
        nn = nr = 0
        for p in procs:
            a, b = check_process(p, errs, warns)
            nn += a
            nr += b

        total_proc += len(procs)
        total_err += len(errs)
        total_warn += len(warns)

        flag = "OK " if not errs else "ERR"
        print("\n[%s] %-28s 流程 %2d  节点 %3d  路由 %3d"
              % (flag, os.path.basename(fp), len(procs), nn, nr))
        for e in errs:
            print("      " + e)
        for w in warns:
            print("      " + w)

    print()
    print("=" * 72)
    print("流程 %d 个，节点/路由已逐一核对 → 错误 %d 个，警告 %d 个"
          % (total_proc, total_err, total_warn))
    print("=" * 72)
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
