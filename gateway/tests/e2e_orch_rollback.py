# -*- coding: utf-8 -*-
"""端到端验证：真实写一行 → 回滚删除，确认补偿链路真的能删掉。"""
import sys, os, time, json
sys.path.insert(0, r"D:\O2OA\gateway")
os.chdir(r"D:\O2OA\gateway")
import o2_agent_gateway as G

CLUE = "orch-e2e-" + str(int(time.time()))
TABLE = "aiDemoOrders"

print("== 0. 前置：确认目标表在写回白名单 ==")
print("  write_tables =", G.CFG.get("write_tables"))
print("  o2oa_token_user =", G.kv_get("o2oa_token_user"))

print("== 1. 建计划 ==")
r = G.task_plan_impl("create", goal="e2e 写回并回滚",
                     steps=["写一行测试数据"], clue_id=CLUE, person="测试甲")
print("  ", r.split("\n")[0])

print("== 2. 第一步（不带 confirm）生成预案 ==")
out, _ = G.task_run_step_impl(1, "write", TABLE,
                              params={"data": {"productName": "编排回滚验证品", "amount": 7}},
                              clue_id=CLUE, person="测试甲", persona="manager")
print("  ", out[:140])

print("== 3. 同一 payload 带 confirm=true 真正写入 ==")
out, okf = G.task_run_step_impl(1, "write", TABLE,
                                params={"data": {"productName": "编排回滚验证品", "amount": 7}},
                                confirm=True,
                                clue_id=CLUE, person="测试甲", persona="manager")
print("  ok =", okf)
print("  ", out[:220])

p = G._plan_load(CLUE)
print("  账本 step1 status =", p["steps"][0]["status"], "| payload.action =",
      (p["steps"][0].get("payload") or {}).get("action"))

print("== 4. 确认真写进去了（按字段反查）==")
okq, jq, stq = G._o2_call(
    f"{G._O2_QRY}/table/list/{TABLE}/row/select/where/"
    + __import__("urllib.parse", fromlist=["quote"]).quote("o.productName='编排回滚验证品'", safe=""),
    method="GET")
rows = (jq.get("data") if isinstance(jq, dict) else jq) or []
print("  查到行数 =", len(rows), "| HTTP", stq)
for r0 in (rows if isinstance(rows, list) else []):
    if isinstance(r0, dict):
        print("   ", r0.get("id"), r0.get("productName"), r0.get("amount"))

print("== 5. 回滚预案（不执行）==")
out = G.task_rollback_impl("e2e 验证后清理", clue_id=CLUE, person="测试甲")
print("  ", out[:200].replace("\n", "\n   "))

print("== 6. 回滚执行（confirm=true）==")
out = G.task_rollback_impl("e2e 验证后清理", confirm=True, clue_id=CLUE, person="测试甲")
print("  ", out.replace("\n", "\n   "))

print("== 7. 复查应已删除 ==")
okq, jq, stq = G._o2_call(
    f"{G._O2_QRY}/table/list/{TABLE}/row/select/where/"
    + __import__("urllib.parse", fromlist=["quote"]).quote("o.productName='编排回滚验证品'", safe=""),
    method="GET")
rows = (jq.get("data") if isinstance(jq, dict) else jq) or []
print("  剩余行数 =", len(rows), "→", "✅ 已清理" if len(rows) == 0 else "❌ 仍存在！")

p = G._plan_load(CLUE)
print("  账本 step1 status =", p["steps"][0]["status"])

print("== 8. 清理账本 ==")
with G.db() as c:
    c.execute("DELETE FROM kv WHERE k=?", (G._plan_key(CLUE),))
print("  done")
