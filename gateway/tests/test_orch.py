# -*- coding: utf-8 -*-
"""多步任务编排引擎单测：直接 import 网关模块，绕开 HTTP 层。"""
import sys, os, json, time
sys.path.insert(0, r"D:\O2OA\gateway")
os.chdir(r"D:\O2OA\gateway")

import o2_agent_gateway as G

CLUE = "orch-test-" + str(int(time.time()))
FAIL = []

def chk(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ((" | " + str(extra)[:220]) if extra else ""))
    if not cond:
        FAIL.append(label)

print("== 1. 空计划时 show / update 应友好报错 ==")
r = G.task_plan_impl("show", clue_id=CLUE)
chk("无计划 show 提示", "当前没有" in r, r[:80])
r = G.task_plan_impl("update", step_index=1, status="done", clue_id=CLUE)
chk("无计划 update 拒绝", r.startswith("ERROR"), r[:80])

print("== 2. create 参数校验 ==")
chk("缺 goal", G.task_plan_impl("create", steps=["a"], clue_id=CLUE).startswith("ERROR"))
chk("缺 steps", G.task_plan_impl("create", goal="g", clue_id=CLUE).startswith("ERROR"))
r = G.task_plan_impl("create", goal="g", steps=["x"] * 20, clue_id=CLUE)
chk("超上限拒绝", "超过上限" in r, r[:100])

print("== 3. 正常 create + 渲染 ==")
r = G.task_plan_impl("create", goal="盘点逾期资产并写回", 
                     steps=["读资产表逾期行", "汇总", "写回更正"], clue_id=CLUE, person="测试甲")
chk("create 成功", "已登记任务计划" in r, r[:100])
chk("渲染含3步", r.count("☐") == 3, r)

print("== 4. 重复 create 应被阻止 ==")
r = G.task_plan_impl("create", goal="另一个", steps=["a"], clue_id=CLUE)
chk("重复 create 阻止", r.startswith("ERROR") and "已有进行中的计划" in r, r[:120])

print("== 5. update 校验与推进 ==")
chk("非法 status", G.task_plan_impl("update", step_index=1, status="xxx", clue_id=CLUE).startswith("ERROR"))
chk("越界 index", G.task_plan_impl("update", step_index=9, status="done", clue_id=CLUE).startswith("ERROR"))
r = G.task_plan_impl("update", step_index=1, status="done", result="读到 3 行逾期", clue_id=CLUE)
chk("step1 完成", "☑" in r and "3 行逾期" in r, r[:200])
chk("剩余步提示", "还剩" in r, r[-60:])

print("== 6. notify_note 步骤（无副作用）==")
out, okf = G.task_run_step_impl(2, "notify_note", note_text="共 3 台逾期", 
                                flag="催办摘要", clue_id=CLUE, person="测试甲")
chk("notify_note 成功", okf and "留痕" in out, out[:120])

print("== 7. read 步骤（走真实内网工具链：知识库）==")
out, okf = G.task_run_step_impl(3, "read", source="kb", query="制度",
                                clue_id=CLUE, person="测试甲")
chk("read/kb 有返回", bool(out) and not out.startswith("ERROR"), out[:180])

print("== 8. read 步骤：数据表 ==")
out, okf = G.task_run_step_impl(3, "read", source="tables",
                                clue_id=CLUE, person="测试甲")
chk("read/table 有返回", bool(out), out[:180])

print("== 9. 非法 kind ==")
out, okf = G.task_run_step_impl(3, "explode", flag="t", clue_id=CLUE, person="测试甲")
chk("非法 kind 拒绝", not okf and "kind 只能填" in out, out[:120])

print("== 10. failed 步骤 + close 提示回滚 ==")
G.task_plan_impl("update", step_index=3, status="failed", result="表被锁", clue_id=CLUE)
r = G.task_plan_impl("close", clue_id=CLUE, person="测试甲")
chk("close 提示失败步", "结项" in r and "task_rollback" in r, r[-200:])

print("== 11. rollback：无可回滚步骤 ==")
r = G.task_rollback_impl("测试", clue_id=CLUE, person="测试甲")
chk("无副作用时友好提示", "没有可回滚" in r, r[:150])

print("== 12. cancel 路径 ==")
CLUE2 = CLUE + "-b"
G.task_plan_impl("create", goal="g2", steps=["a", "b"], clue_id=CLUE2, person="测试甲")
r = G.task_plan_impl("cancel", clue_id=CLUE2, note="用户改主意了")
chk("cancel 成功", "放弃" in r, r[:120])
r = G.task_plan_impl("create", goal="g3", steps=["a"], clue_id=CLUE2, person="测试甲")
chk("cancel 后可重建", "已登记任务计划" in r, r[:80])

print("== 13. write 步骤：首次调用应生成预案（不落库）==")
CLUE3 = CLUE + "-w"
G.task_plan_impl("create", goal="写回测试", steps=["写一行"], clue_id=CLUE3, person="测试甲")
out, okf = G.task_run_step_impl(1, "write", flag="aiDemoOrders",
                                data={"productName": "编排测试商品", "amount": 1},
                                clue_id=CLUE3, person="测试甲", persona="manager")
chk("write 生成预案", "CONFIRM_REQUIRED" in out, out[:200])
p = G._plan_load(CLUE3)
chk("步骤停在 doing", p["steps"][0]["status"] == "doing", p["steps"][0]["status"])

print("== 14. rollback 预案（confirm=false 不执行）==")
p["steps"][0]["status"] = "done"   # 模拟写成功
G._plan_save(CLUE3, p)
r = G.task_rollback_impl("测试回滚", clue_id=CLUE3, person="测试甲")
chk("rollback 要二次确认", "CONFIRM_REQUIRED" in r and "逆序" in r, r[:200])

print("== 15. 清理测试计划 ==")
for c in (CLUE, CLUE2, CLUE3):
    with G.db() as conn:
        conn.execute("DELETE FROM kv WHERE k=?", (G._plan_key(c),))
chk("清理完成", G._plan_load(CLUE) is None)

print()
print("=== 结果：%d 项失败 ===" % len(FAIL))
for f in FAIL:
    print("  - " + f)
sys.exit(1 if FAIL else 0)
