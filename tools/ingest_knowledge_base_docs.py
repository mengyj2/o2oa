# -*- coding: utf-8 -*-
"""
将 docs/knowledge_base/*.md（前序会话沉淀的 O2OA 运维/方法论/坑与加固 文档）
灌入本地知识库 data.db 并触发向量化。

- 落库：POST /idx-gateway-doc/update（网关自动切块+向量化，需 embed@8089 在线）
- 鉴权令牌从 gateway/config.json 的 "token" 字段运行时读取（不硬编码、不回显）
- 幂等：同 id 重复运行 = upsert
- 文档标题取首个 '# ' 行；id = o2kb::knowledge_base::<文件名stem>
"""
import json, os, re, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY_DIR = os.path.join(HERE, "..", "gateway")
CFG = json.load(open(os.path.join(GATEWAY_DIR, "config.json"), encoding="utf-8"))
TOKEN = CFG["token"]
PORT = CFG.get("listen_port", 18790)
BASE = f"http://127.0.0.1:{PORT}"
KB_DIR = os.path.join(HERE, "..", "docs", "knowledge_base")


def post_doc(doc_id, title, content):
    payload = json.dumps({
        "id": doc_id, "title": title, "category": "o2kb::knowledge_base",
        "content": content, "permissionList": [],
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/idx-gateway-doc/update", data=payload,
        headers={"Authorization": TOKEN, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa
        return 0


def main():
    files = sorted(f for f in os.listdir(KB_DIR) if f.endswith(".md"))
    ok = 0
    for fn in files:
        path = os.path.join(KB_DIR, fn)
        text = open(path, encoding="utf-8").read()
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = m.group(1).strip() if m else fn[:-3]
        doc_id = "o2kb::knowledge_base::" + fn[:-3]
        st = post_doc(doc_id, title, text)
        flag = "OK" if st == 200 else f"FAIL({st})"
        if st == 200:
            ok += 1
        print(f"[{flag}] {doc_id}")
    print(f"\n完成：{ok}/{len(files)} 篇入库成功（docs/knowledge_base/）。")


if __name__ == "__main__":
    main()
