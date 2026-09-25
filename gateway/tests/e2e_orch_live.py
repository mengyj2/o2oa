# -*- coding: utf-8 -*-
"""通过网关 SSE 全链路（LLM + 工具循环）验证多步任务编排。
真实协议：裸 data: {"choices":[{"delta":{"content":...}}]}，无外层 type 字段。"""
import sys, json, time, uuid, urllib.request

BASE = "http://127.0.0.1:18790"
TOKEN = "local-o2-agent-2026"

# 绕过系统代理（shell 代理会假 502）
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(opener)


def ask(text, clue=None, person="孟弋洁", label=""):
    clue = clue or ("orch-live-" + uuid.uuid4().hex[:10])
    body = {
        "input": text,
        "generateType": "mcp",
        "clueId": clue,
        "wi": {"person": person, "token": ""},
        "permissionList": [],
        "aiModel": "glm-4.7-flash",
    }
    req = urllib.request.Request(
        f"{BASE}/ai-gateway-completion/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + TOKEN},
        method="POST")
    print("=" * 78)
    print(f"[{label}] 问：{text[:120]}")
    print(f"    clueId={clue} person={person}")
    print("-" * 78)
    content = []
    tools = []
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            buf = b""
            for raw in r:
                buf += raw
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == b"[DONE]":
                        continue
                    try:
                        o = json.loads(payload.decode("utf-8"))
                    except Exception:
                        continue
                    # 工具调用事件（不同字段名都兜住）
                    for k in ("toolCall", "tool_call", "toolCalls"):
                        if o.get(k):
                            tools.append(o[k])
                    cont = o.get("extend") or {}
                    if isinstance(cont, dict) and cont.get("toolName"):
                        tools.append(cont.get("toolName"))
                    # ★ 真实增量在 choices[0].delta.content（裸结构，无外层 type）
                    if "choices" in o:
                        for ch in (o.get("choices") or []):
                            d = ch.get("delta") or {}
                            if d.get("content"):
                                content.append(d["content"])
    except Exception as e:
        print("  !! 请求异常：", type(e).__name__, e)
    out = "".join(content)
    print(out[:2600])
    if len(out) > 2600:
        print(f"...（共 {len(out)} 字）")
    print("-" * 78)
    print(f"  工具事件：{tools if tools else '（SSE 未单独暴露，见网关日志）'}")
    print(f"  回答长度：{len(out)} 字")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"

    if which == "1":
        # 场景①：真正的多步任务（应触发 task_plan）
        ask("帮我盘点一下系统里 aiDemoOrders 这个表的全部数据，"
            "汇总一下总金额，然后给我一份简要说明。这件事比较多步，请按步骤来。",
            label="场景1-多步盘点")

    elif which == "2":
        # 场景②：简单问题（不应触发 task_plan，防止过度规划）
        ask("现在几点了？", label="场景2-简单问题")

    elif which == "3":
        # 场景③：跨系统多源汇总（待办+数据表）
        ask("我今天有哪些待办要处理？另外系统里有哪些业务数据表？"
            "请分步查证后一起告诉我。", label="场景3-跨源汇总")
