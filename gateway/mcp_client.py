# -*- coding: utf-8 -*-
"""标准 MCP client：支持 stdio 与 HTTP(JSON-RPC) 两种传输。

网关用它把外部 MCP server 的 tools/list 动态注入 from_mcp_loop()，
从而把"整个 MCP 生态"接入 O2OA 的对话/工具循环。

MCP 协议要点（https://modelcontextprotocol.io）：
  - 先 initialize（带 protocolVersion），再发 notifications/initialized
  - tools/list 取工具清单；tools/call 调用工具
  - stdio 用 LSP 帧：b"Content-Length: N\r\n\r\n" + json（UTF-8）
  - HTTP 用 POST application/json，返回 JSON（最简形态，覆盖大多数桥接实现）

本模块不依赖网关其余部分，可独立 import 测试。
"""
import json
import os
import re
import subprocess
import sys
import threading
import queue

import httpx

DEFAULT_PROTOCOL = "2024-11-05"
HTTP_TIMEOUT = 30


def log(m):
    # 网关以 `python o2_agent_gateway.py 2>&1` 运行时，stderr 进入 gateway.log
    print(f"[mcp] {m}", file=sys.stderr, flush=True)


class MCPError(Exception):
    pass


class _BaseClient:
    def __init__(self, name):
        self.name = name
        self.tools = []
        self._id = 0
        self._lock = threading.Lock()

    def _next_id(self):
        with self._lock:
            self._id += 1
            return self._id

    # ---- 高层 API ----
    def initialize(self):
        self._rpc("initialize", {
            "protocolVersion": DEFAULT_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "o2-gateway", "version": "1.0"},
        })
        self._notify("notifications/initialized", {})

    def tools_list(self):
        resp = self._rpc("tools/list", {})
        self.tools = (resp.get("result") or {}).get("tools") or []
        return self.tools

    def call_tool(self, tool_name, arguments):
        resp = self._rpc("tools/call", {"name": tool_name, "arguments": arguments or {}})
        res = resp.get("result") or {}
        parts = []
        for c in (res.get("content") or []):
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                elif "data" in c:
                    parts.append(str(c.get("data")))
        text = "\n".join(parts)
        if res.get("isError"):
            text = "TOOL_ERROR: " + text
        return text

    # 子类实现
    def _rpc(self, method, params):
        raise NotImplementedError

    def _notify(self, method, params):
        raise NotImplementedError

    def close(self):
        pass


class StdioMCPClient(_BaseClient):
    """通过子进程 stdin/stdout 走 MCP JSON-RPC（Content-Length 帧）。"""

    def __init__(self, name, command, args=None, env=None, timeout=HTTP_TIMEOUT):
        super().__init__(name)
        self.timeout = timeout
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        try:
            self.proc = subprocess.Popen(
                [command] + (args or []),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=full_env, bufsize=0)
        except Exception as e:
            raise MCPError(f"spawn {command} failed: {e}")
        self._resp = {}
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        try:
            self.initialize()
        except Exception as e:
            raise MCPError(f"initialize failed: {e}")

    def _write_frame(self, msg):
        data = json.dumps(msg).encode("utf-8")
        frame = b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data
        with self._lock:
            self.proc.stdin.write(frame)
            self.proc.stdin.flush()

    def _rpc(self, method, params):
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        q = queue.Queue()
        self._resp[rid] = q
        try:
            self._write_frame(msg)
            resp = q.get(timeout=self.timeout)
        except queue.Empty:
            raise MCPError(f"timeout waiting {method}")
        finally:
            self._resp.pop(rid, None)
        if "error" in resp:
            raise MCPError(f"{method} error: {resp['error']}")
        return resp

    def _notify(self, method, params):
        try:
            self._write_frame({"jsonrpc": "2.0", "method": method, "params": params})
        except Exception:
            pass

    def _read_loop(self):
        try:
            while True:
                header = b""
                while b"\r\n\r\n" not in header:
                    ch = self.proc.stdout.read(1)
                    if not ch:
                        return
                    header += ch
                length = 0
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        try:
                            length = int(line.split(b":", 1)[1].strip())
                        except Exception:
                            length = 0
                body = b""
                while len(body) < length:
                    chunk = self.proc.stdout.read(length - len(body))
                    if not chunk:
                        return
                    body += chunk
                try:
                    msg = json.loads(body.decode("utf-8"))
                except Exception:
                    continue
                rid = msg.get("id")
                if rid is not None and rid in self._resp:
                    self._resp[rid].put(msg)
        except Exception:
            return

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass

    @property
    def alive(self):
        return self.proc.poll() is None


class HTTPMCPClient(_BaseClient):
    """最简 HTTP JSON-RPC 形态：POST application/json，返回 JSON。"""

    def __init__(self, name, url, headers=None, timeout=HTTP_TIMEOUT):
        super().__init__(name)
        self.url = url
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        if headers:
            self.headers.update(headers)
        self._cli = httpx.Client(timeout=timeout)
        self.initialize()

    def _rpc(self, method, params):
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            r = self._cli.post(self.url, headers=self.headers, json=msg)
            r.raise_for_status()
            resp = r.json()
        except Exception as e:
            raise MCPError(f"{method} http error: {e}")
        if "error" in resp:
            raise MCPError(f"{method} error: {resp['error']}")
        return resp

    def _notify(self, method, params):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._cli.post(self.url, headers=self.headers, json=msg)
        except Exception:
            pass

    def close(self):
        try:
            self._cli.close()
        except Exception:
            pass


# ----------------------------- 网关侧连接管理 -----------------------------
_clients = {}  # server name -> client（进程级缓存，复用子进程）


def connect_server(spec):
    """spec: {name, transport:'stdio'|'http', command, args, url, env, headers, timeout}"""
    name = spec.get("name") or "mcp"
    transport = (spec.get("transport") or "stdio").lower()
    timeout = int(spec.get("timeout") or HTTP_TIMEOUT)
    if transport == "stdio":
        cmd = spec.get("command")
        if not cmd:
            raise MCPError("stdio server requires 'command'")
        return StdioMCPClient(name, cmd, spec.get("args"), spec.get("env"), timeout)
    else:
        url = spec.get("url")
        if not url:
            raise MCPError("http server requires 'url'")
        return HTTPMCPClient(name, url, spec.get("headers"), timeout)


def load_external_mcp(server_specs):
    """返回 (openai_tool_defs, dispatch_dict)。

    dispatch_dict: full_name -> (client, original_tool_name)
    工具名加前缀避免冲突： {server}__{tool}
    外部 MCP 工具与内置/O2OA 同名时，由调用方决定优先级（本实现里内置优先）。
    """
    defs, dispatch = [], {}
    for spec in (server_specs or []):
        name = spec.get("name") or "mcp"
        try:
            cli = _clients.get(name)
            if cli is None or (hasattr(cli, "alive") and not cli.alive):
                cli = connect_server(spec)
                _clients[name] = cli
            tools = cli.tools_list()
        except Exception as e:
            log(f"mcp server '{name}' load failed: {e}")
            continue
        for t in tools:
            tname = t.get("name")
            if not tname:
                continue
            full = f"{name}__{tname}"
            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            if "properties" not in schema:
                schema = {"type": "object", "properties": {}}
            defs.append({"type": "function", "function": {
                "name": full,
                "description": (t.get("description") or "")[:600],
                "parameters": schema,
            }})
            dispatch[full] = (cli, tname)
        log(f"mcp server '{name}' loaded {len(tools)} tools: {[t.get('name') for t in tools]}")
    return defs, dispatch


def call_external_tool(full_name, dispatch, args):
    entry = dispatch.get(full_name)
    if not entry:
        return f"unknown external tool {full_name}"
    cli, orig = entry
    try:
        return cli.call_tool(orig, args)
    except Exception as e:
        return f"MCP_CALL_ERROR: {e}"


def shutdown_all():
    for c in _clients.values():
        try:
            c.close()
        except Exception:
            pass
    _clients.clear()
