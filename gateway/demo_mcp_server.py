# -*- coding: utf-8 -*-
"""最小 MCP stdio server（测试用）：实现 initialize / tools/list / tools/call。
提供两个演示工具：
  - echo(text)            原样返回文本
  - add(a, b)             两数相加
帧格式：Content-Length: N\r\n\r\n{json}
"""
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "原样返回输入文本（演示 MCP stdio 通道）",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "要回显的文本"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "计算两个数字之和（演示参数传递）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一个数"},
                "b": {"type": "number", "description": "第二个数"},
            },
            "required": ["a", "b"],
        },
    },
]


def send(msg):
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
                    length = int(line.split(b":", 1)[1].strip())
            while len(buf) < length:
                buf += sys.stdin.buffer.read(length - len(buf))
            body, buf = buf[:length], buf[length:]
            msg = json.loads(body.decode("utf-8"))
            method = msg.get("method")
            rid = msg.get("id")
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "demo-mcp", "version": "0.1"},
                }})
            elif method == "tools/list":
                send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                name = (msg.get("params") or {}).get("name")
                args = (msg.get("params") or {}).get("arguments") or {}
                if name == "echo":
                    text = f"ECHO[{args.get('text','')}]"
                elif name == "add":
                    text = f"SUM[{args.get('a')}+{args.get('b')}={float(args.get('a', 0)) + float(args.get('b', 0))}]"
                else:
                    text = f"unknown tool {name}"
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": text}]}})
            elif rid is not None:
                send({"jsonrpc": "2.0", "id": rid, "result": {}})


if __name__ == "__main__":
    main()
