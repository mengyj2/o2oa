# -*- coding: utf-8 -*-
"""_flow_smoke.py —— 流程端到端冒烟：发起 → 逐级办理 → 走完。

为什么必须做这件事
------------------
结构校验（表单树/DOM/拓扑/路由 id）**看不到运行态缺陷**。本项目已两次踩坑：
  · Route.activityType 为空 → Processing.arrive() switch(null) NPE
  · Manual.manualMode 为空  → Manual.toTickets() ordinal() NPE
两者都只在"真的发起一条流程"时才暴露。

本脚本因此做真实压测：
  1. 以真实员工身份发起流程实例（cipher token 可直接指定 identity）
  2. 取当前待办 → 选一条「前向」路由 → 提交
  3. 重复直到流程结束或达到上限
  4. 输出每一步的 活动 / 处理人 / 路由，人眼可核对审批链是否符合组织分工

用法：python _flow_smoke.py [--limit N]
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:9090"
S = "/x_processplatform_assemble_surface/jaxrs"

# 退回语义的路由名——冒烟时一律走"前进"分支
BACK_WORDS = ("退回", "驳回", "不批准", "拒绝", "否决", "退回修改")


def call(path, token, method="GET", body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("x-token", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        return {"type": "http-error", "code": e.code, "message": raw[:300]}
    except Exception as e:
        return {"type": "error", "message": str(e)}


def start(token, pid, title, identity, data=None):
    d = call(S + "/work/process/" + pid, token, "POST",
             {"identity": identity, "title": title, "data": data or {}})
    if d.get("type") != "success":
        return None, d
    return d["data"][0], None


def tasks_of_work(token, work_id):
    d = call(S + "/task/list/work/" + work_id, token)
    return (d.get("data") or []) if d.get("type") == "success" else []


def work_of(token, work_id):
    d = call(S + "/work/" + work_id, token)
    return d.get("data") if d.get("type") == "success" else None


def pick_forward(task):
    """从待办的可选路由中挑一条前进路由。"""
    names = task.get("routeNameList") or []
    cand = [n for n in names if n and not any(w in n for w in BACK_WORDS)]
    if cand:
        return cand[0]
    return names[0] if names else ""


def run_case(token, pid, pname, title, identity, max_step=12):
    print("\n" + "-" * 70)
    print("流程：%s" % pname)
    print("标题：%s    拟稿人：%s" % (title, identity))
    print("-" * 70)

    w, err = start(token, pid, title, identity)
    if err:
        print("  [发起失败] %s" % json.dumps(err, ensure_ascii=False)[:220])
        return False, 0
    wid = w["work"]
    print("  发起 OK  work=%s" % wid[:8])

    steps = 0
    for _ in range(max_step):
        ts = tasks_of_work(token, wid)
        if not ts:
            cur = work_of(token, wid)
            state = "已结束" if (cur or {}).get("completed") else "无待办(可能卡在自动节点)"
            print("  → %s" % state)
            return True, steps
        t = ts[0]
        rn = pick_forward(t)
        steps += 1
        print("  %2d) [%s] 处理人=%s  路由→「%s」"
              % (steps, t.get("activityName"), t.get("person"), rn))
        r = call(S + "/task/%s/processing" % t["id"], token, "POST",
                 {"routeName": rn, "opinion": "同意（冒烟测试）"})
        if r.get("type") != "success":
            print("      提交失败：%s" % json.dumps(r, ensure_ascii=False)[:260])
            return False, steps
    print("  → 达到步数上限 %d" % max_step)
    return True, steps


def main():
    limit = 4
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    from import_xapps import get_token
    token = get_token()
    print("[token] 长度 %d" % len(token))

    # 覆盖六大应用的骨干流程（每条取第一个会真实推进的起点）
    CASES = [
        ("p2002001-contract-approve-000000000001", "合同审批流程",
         "HT2026-001 轻量化结构件工艺攻关技术服务合同", "yjyb_shixiaoming"),
        ("p6006003-hr-regular-000000000001", "员工转正流程",
         "杜阳 转正申请", "yjyb_duyang"),
        ("p6006008-hr-leave-apply-00000000000001", "请假申请流程",
         "李静 请假申请", "hyfwb_lijing"),
        ("p4004003-finance-payment-00000000001", "财务付款审批流程",
         "2026年9月服务费付款", "zhb_lifang"),
    ][:limit]

    ok_n, total_steps = 0, 0
    for pid, pname, title, ident in CASES:
        ok, st = run_case(token, pid, pname, title, ident)
        ok_n += 1 if ok else 0
        total_steps += st

    print("\n" + "=" * 70)
    print("冒烟结果：%d/%d 条流程走通，累计办理 %d 步" % (ok_n, len(CASES), total_steps))
    print("=" * 70)
    return 0 if ok_n == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
