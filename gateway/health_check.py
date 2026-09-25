# -*- coding: utf-8 -*-
"""
health_check.py — O2OA AI 栈正确探活脚本（供监控 / 人工使用）

★ 重要：不要再用 GET / 探活 embed(8089)/ocr(8091) —— 这两个服务根路径无路由，
  打 / 必然返回 404（这是监控误报「服务 DOWN」的根因，功能本身正常）。

正确端点：
  - 网关    18790  -> GET /gateway/health  (需 Bearer token，200=健康)
  - embed   8089  -> TCP 连通即健康（llama.cpp embedding，根 / 无路由）
  - ocr     8091  -> GET /health          (200=健康)
  - rerank  8092  -> TCP 连通即健康（仅当 rerank_enable=true 启用时）

输出 JSON 到 stdout；全部 healthy 退出码 0，否则 1。
可直接被 Zabbix / Prometheus / 定时任务调用，或人工排障。
"""
import json
import os
import socket
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = "local-o2-agent-2026"


def tcp_up(port, timeout=1.0):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(url, token=None, timeout=4):
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# (name, port, kind, path)
# kind: gateway(需token) / http(健康端点) / tcp(仅连通)
CHECKS = [
    ("gateway", 18790, "gateway", "/gateway/health"),
    ("embed", 8089, "tcp", None),
    ("ocr", 8091, "http", "/health"),
    ("rerank", 8092, "tcp", None),
]


def main():
    results = {}
    overall = True
    for name, port, kind, path in CHECKS:
        up = tcp_up(port)
        detail = {"port": port, "tcp": up}
        if name == "rerank" and not up:
            detail["status"] = "disabled"
            results[name] = detail
            continue
        if kind == "gateway":
            code = http_get(f"http://127.0.0.1:{port}{path}", TOKEN) if up else 0
            detail["http"] = code
            detail["health"] = (code == 200)
            overall = overall and detail["health"]
        elif kind == "http":
            code = http_get(f"http://127.0.0.1:{port}{path}") if up else 0
            detail["http"] = code
            detail["health"] = (code == 200)
            overall = overall and detail["health"]
        else:  # tcp
            detail["health"] = up
            overall = overall and up
        results[name] = detail

    results["_overall"] = "OK" if overall else "DEGRADED"
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
