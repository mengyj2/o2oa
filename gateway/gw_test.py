# -*- coding: utf-8 -*-
# 全模式自测: chat / rag / mcp / 首帧
import json
import httpx

GW = "http://127.0.0.1:18790"
H = {"Authorization": "Bearer local-o2-agent-2026"}


def ask(payload):
    r = httpx.post(GW + "/ai-gateway-completion/generate", headers=H, json=payload, timeout=300)
    frames = r.text.splitlines()
    out = ""
    for l in frames:
        if l.startswith("data: ") and not l.endswith("[DONE]"):
            try:
                out += ((json.loads(l[6:]).get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
            except Exception:
                pass
    return r.status_code, frames[0][:40] if frames else "(empty)", out


st, first, out = ask({"input": "用15个字以内回答：什么是防火墙", "generateType": "chat"})
print(f"CHAT  {st} | 首帧[{first}] | {out[:60]}")

st, first, out = ask({"input": "O2OA 数据库有多少张表？只答数字", "generateType": "rag"})
print(f"RAG   {st} | 首帧[{first}] | {out[:60]}")

st, first, out = ask({"input": "你好", "generateType": "mcp"})
print(f"MCP   {st} | 首帧[{first}] | {out[:60]}")
