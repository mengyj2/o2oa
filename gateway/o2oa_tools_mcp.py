# -*- coding: utf-8 -*-
"""O2OA 排查常用工具 MCP server（stdio 传输，标准 MCP 2024-11-05）。

网关 mcp_client.py 的 StdioMCPClient 会按 `command`+`args` 拉起本进程，
通过 stdin/stdout 的 Content-Length 帧做 JSON-RPC：initialize / tools/list / tools/call。
本 server 暴露「排查 O2OA 问题」最常用的一组工具，使 AI 模型能真正调用工具而不是硬答。

工具清单（都走 localhost，不依赖外网）：
  - o2_service_health   探测 O2OA/网关/向量/OCR 各端口可达性
  - o2_login_status      用 xadmin 试登录 O2OA，返回是否拿到 x-token（不回显 token）
  - o2_org_unit_top      取顶层组织（验证组织服务是否存活）
  - o2_task_my           取我的待办（验证流程/待办链路）
  - o2_person_query      按关键字查人员（PUT person/list/like）
  - o2_dict_read        读门户数据字典（GET .../jaxrs/dict/{alias}/portal/{flag}/data）
  - o2_gateway_config    读网关 config.json 的非敏感字段（剔除 token 等）
  - o2_tail_log         读取并 tail 网关/看门狗日志，辅助排障

鉴权：REST 类工具需要 O2OA 凭据，从环境变量读取（绝不硬编码）：
  O2OA_BASE      默认 http://127.0.0.1:9090
  O2OA_USER      默认 xadmin
  O2OA_PASSWORD  必填（否则 REST 工具返回友好提示）
凭据由看门狗/网关在拉起本进程时通过 env 注入，不落盘、不入库。
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE = os.environ.get("O2OA_BASE", "http://127.0.0.1:9090").rstrip("/")
USER = os.environ.get("O2OA_USER", "xadmin")
PASSWORD = os.environ.get("O2OA_PASSWORD", "")

TOOLS = [
    {
        "name": "o2_service_health",
        "description": "探测 O2OA(9090)、AI网关(18790)、向量(8089)、OCR(8091) 各端口是否可达，返回每端口 HTTP 状态。用于判断哪个服务挂了。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "o2_login_status",
        "description": "用配置的 xadmin 凭据试登录 O2OA 认证服务，返回是否成功拿到 x-token（不回显 token 本身）、当前用户与组织。用于判断登录链路是否健康。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "o2_org_unit_top",
        "description": "调用组织服务 GET /jaxrs/unit/list/top 取顶层组织单元，验证组织(ORG)服务是否存活与可查。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "o2_task_my",
        "description": "调用流程服务 GET /jaxrs/task/list/my/paging/1/size/20 取我的待办列表，验证待办/流程链路是否正常。",
        "inputSchema": {"type": "object", "properties": {"size": {"type": "integer", "description": "返回条数，默认20"}}, "required": []},
    },
    {
        "name": "o2_person_query",
        "description": "按关键字查询人员：PUT /jaxrs/person/list/like {key}。用于排查人员/账号问题。",
        "inputSchema": {"type": "object", "properties": {"key": {"type": "string", "description": "查询关键字（姓名/拼音/手机号）"}}, "required": ["key"]},
    },
    {
        "name": "o2_dict_read",
        "description": "读取门户数据字典：GET /jaxrs/dict/{alias}/portal/{flag}/data（任意登录用户可读）。用于排查门户配置（如 appmenus 应用菜单）。",
        "inputSchema": {"type": "object", "properties": {
            "alias": {"type": "string", "description": "字典 alias，如 appmenus"},
            "flag": {"type": "string", "description": "门户 alias 或 index（系统首页填 index）"}}, "required": ["alias", "flag"]},
    },
    {
        "name": "o2_gateway_config",
        "description": "读取 AI 网关 gateway/config.json 的非敏感字段（剔除 token/password 等），返回模型名、端口、后端 base、功能开关。用于排查网关配置。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "o2_tail_log",
        "description": "读取并 tail 网关/看门狗日志文件，辅助排障。",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "日志名：gateway.log / watchdog.log / ocr.log"},
            "lines": {"type": "integer", "description": "返回末尾行数，默认 40"}}, "required": ["name"]},
    },
]


# ---------------- O2OA REST 鉴权 ----------------
def _login():
    """返回 x-token 字符串，失败抛异常。"""
    if not PASSWORD:
        raise RuntimeError("未配置 O2OA_PASSWORD（环境变量），无法调用需鉴权的 REST 工具")
    url = f"{BASE}/x_organization_assemble_authentication/jaxrs/authentication"
    req = urllib.request.Request(url, data=json.dumps(
        {"credential": USER, "password": PASSWORD}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    # O2OA 登录返回结构容错：token 可能在顶层或 data 内
    if isinstance(data, dict):
        if data.get("token"):
            return data["token"]
        d = data.get("data") or {}
        if d.get("token"):
            return d["token"]
    raise RuntimeError("登录响应中未找到 token：" + json.dumps(data, ensure_ascii=False)[:200])


def _get(path, token=None, method="GET", body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["x-token"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _put(path, body, token=None):
    return _get(path, token=token, method="PUT", body=body)


# ---------------- 工具实现 ----------------
def _run(name, args):
    if name == "o2_service_health":
        ports = {"o2oa:9090": 9090, "gateway:18790": 18790, "embed:8089": 8089, "ocr:8091": 8091}
        out = []
        for label, p in ports.items():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{p}/", timeout=3) as r:
                    out.append(f"{label} -> HTTP {r.status}")
            except urllib.error.HTTPError as e:
                out.append(f"{label} -> HTTP {e.code}")
            except Exception as e:
                out.append(f"{label} -> DOWN ({type(e).__name__}: {str(e)[:60]})")
        return "\n".join(out)

    if name == "o2_login_status":
        try:
            tok = _login()
            ok = bool(tok)
            # 不回显 token，只报长度与用户
            return f"login_ok={ok} user={USER} token_len={len(tok)}"
        except Exception as e:
            return f"login_failed: {str(e)[:200]}"

    if name == "o2_org_unit_top":
        tok = _login()
        d = _get("/x_organization_assemble_control/jaxrs/unit/list/top", token=tok)
        units = (d.get("data") or []) if isinstance(d, dict) else []
        names = [u.get("name", "?") for u in units[:15]]
        return f"top_units({len(units)}): {names}"

    if name == "o2_task_my":
        tok = _login()
        size = int((args or {}).get("size", 20))
        d = _get(f"/x_processplatform_assemble_surface/jaxrs/task/list/my/paging/1/size/{size}", token=tok)
        tasks = (d.get("data") or {}).get("data") or (d.get("data") or [])
        if isinstance(tasks, dict):
            tasks = tasks.get("data") or []
        lines = []
        for t in tasks[:size]:
            lines.append(f"- {t.get('title', t.get('activityName', '?'))} [{t.get('processName', '')}]")
        return f"my_tasks({len(tasks)}):\n" + ("\n".join(lines) if lines else "(无待办)")

    if name == "o2_person_query":
        key = (args or {}).get("key", "")
        if not key:
            return "ERROR: 缺少 key"
        tok = _login()
        d = _put("/x_organization_assemble_control/jaxrs/person/list/like", {"key": key}, token=tok)
        people = (d.get("data") or {}).get("data") or (d.get("data") or [])
        if isinstance(people, dict):
            people = people.get("data") or []
        lines = [f"{p.get('name','?')} <{p.get('distinguishedName','')}>" for p in people[:15]]
        return f"persons({len(people)}) for '{key}':\n" + ("\n".join(lines) if lines else "(无)")

    if name == "o2_dict_read":
        alias = (args or {}).get("alias", "")
        flag = (args or {}).get("flag", "")
        if not alias or not flag:
            return "ERROR: 缺少 alias/flag"
        tok = _login()
        d = _get(f"/x_portal_assemble_surface/jaxrs/dict/{alias}/portal/{flag}/data", token=tok)
        return f"dict[{alias}/{flag}] => " + json.dumps(d, ensure_ascii=False)[:1500]

    if name == "o2_gateway_config":
        try:
            cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "config.json"), encoding="utf-8"))
        except Exception as e:
            return f"read config failed: {e}"
        safe = {k: v for k, v in cfg.items()
                if k.lower() not in ("token", "password", "secret", "apikey", "api_key", "authorization")}
        return json.dumps(safe, ensure_ascii=False, indent=2)[:2000]

    if name == "o2_tail_log":
        name_ = (args or {}).get("name", "gateway.log")
        lines = int((args or {}).get("lines", 40))
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name_)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.readlines()
            return "".join(content[-lines:])
        except Exception as e:
            return f"tail {name_} failed: {e}"

    return f"unknown tool {name}"


# ---------------- MCP stdio 帧 ----------------
def _send(msg):
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
    sys.stdout.buffer.flush()


def main():
    buf = b""
    while True:
        ch = sys.stdin.buffer.read(1)
        if not ch:
            break
        buf += ch
        while b"\r\n\r\n" in buf:
            head, buf = buf.split(b"\r\n\r\n", 1)
            length = 0
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    try:
                        length = int(line.split(b":", 1)[1].strip())
                    except Exception:
                        length = 0
            while len(buf) < length:
                buf += sys.stdin.buffer.read(length - len(buf))
            body, buf = buf[:length], buf[length:]
            try:
                msg = json.loads(body.decode("utf-8"))
            except Exception:
                continue
            method = msg.get("method")
            rid = msg.get("id")
            if method == "initialize":
                _send({"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "o2oa-tools", "version": "0.1"},
                }})
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                params = msg.get("params") or {}
                tname = params.get("name")
                targs = params.get("arguments") or {}
                try:
                    text = _run(tname, targs)
                except Exception as e:
                    text = f"TOOL_ERROR: {str(e)[:300]}"
                _send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": text}]}})
            elif rid is not None:
                _send({"jsonrpc": "2.0", "id": rid, "result": {}})


if __name__ == "__main__":
    main()
