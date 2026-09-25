# -*- coding: utf-8 -*-
"""多跳问答测试：验证 qwen3.8-27b 在需要"看清单→选标识→再查→汇总"链路上的表现。
真实 SSE 协议：裸 data: {"choices":[{"delta":{"content":...}}]}"""
import sys, json, uuid, urllib.request

BASE = "http://127.0.0.1:18790"
TOKEN = "local-o2-agent-2026"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def ask(text, label="", person="孟弋洁"):
    clue = "mh-" + uuid.uuid4().hex[:10]
    body = {"input": text, "generateType": "mcp", "clueId": clue,
            "wi": {"person": person, "token": ""},
            "permissionList": [], "aiModel": "qwen3.8-27b"}
    req = urllib.request.Request(f"{BASE}/ai-gateway-completion/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN},
        method="POST")
    print("=" * 78)
    print(f"[{label}] {text[:110]}")
    print("-" * 78)
    buf, content = b"", []
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            buf += raw
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                p = line[5:].strip()
                if not p or p == b"[DONE]":
                    continue
                try:
                    o = json.loads(p.decode("utf-8"))
                except Exception:
                    continue
                if "choices" in o:
                    for ch in (o.get("choices") or []):
                        d = ch.get("delta") or {}
                        if d.get("content"):
                            content.append(d["content"])
    out = "".join(content)
    print(out[:3000])
    if len(out) > 3000:
        print(f"...（共 {len(out)} 字）")
    print("-" * 78)
    return out


if __name__ == "__main__":
    w = sys.argv[1] if len(sys.argv) > 1 else "1"
    if w == "1":
        # 多跳①：待办 → 详情 → 判断该做什么
        ask("我现在有哪些待办？挑其中那条合同相关的，告诉我它现在该走什么流程。",
            label="多跳1-待办到详情")
    elif w == "2":
        # 多跳②：找表 → 查数据 → 汇总（跨工具链）
        ask("系统里有哪些跟'合同'有关的业务数据表？其中主表里现在有多少条记录？",
            label="多跳2-找表到查数")
    elif w == "3":
        # 多跳③：组织 → 身份 → 交叉
        ask("协会下面有哪些部门？综合管理部下面有谁？",
            label="多跳3-组织到人员")
