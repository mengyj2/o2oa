#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o2_clone_app.py —— O2OA 应用克隆改造器（离线包 → 克隆改名 → 重新安装）

用途：把官方市场/已装的某个 `.xapp` 应用整包克隆成一个**新应用**，
      重映射全部自有 UUID（避免与原件冲突/覆盖），再按映射表批量改名，
      最后用离线包方式安装。

背景与关键坑（实测）：
  · O2OA 安装离线包**保留 xapp 内的 id**，所以克隆必须先重映射 id，
    否则 import/create 会覆盖原应用。
  · 页面/表单的 `data` 字段是"双层转义 designer JSON"，其中同时含
    `json.moduleList[].text`（结构化文案）与 `html`（渲染镜像）两份文案，
    因此**直接对原始文本做整串替换**即可一次改净两处。
  · 该字段**绝不可 json.loads→json.dumps 往返**：与原串不等长
    （实测 111854 vs 125771），会破坏结构。只能做文本级替换。
  · 只能重映射"本应用自有 id"：xapp 内还含**外部引用**（其他应用 id、
    原作者服务器绝对 URL），误改会破坏引用。

用法：
  python o2_clone_app.py --src "D:/O2OA/插件/公文管理.zip" \\
      --out C:/temp/pms.zip --new-name 项目管理 --new-alias PMS \\
      --rename-map C:/temp/rename.json --dry-run

  rename.json = [["旧文案","新文案"], ...]  （按长度降序自动应用）
"""

import argparse
import json
import os
import re
import sys
import uuid
import zipfile
from collections import OrderedDict

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
UUID_FULL = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


# ---------------------------------------------------------------- helpers
def read_xapp(src):
    """从 zip 或裸 .xapp/.json 读取 xapp 原始文本"""
    if src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if n.endswith(".xapp")]
            if not names:
                sys.exit(f"包内没有 .xapp 文件: {src}")
            if len(names) > 1:
                print(f"⚠ 包内有 {len(names)} 个 xapp，取第一个: {names[0]}")
            return z.read(names[0]).decode("utf-8", "replace")
    with open(src, encoding="utf-8") as f:
        return f.read()


def collect_own_ids(obj, foreign):
    """收集解析后对象里所有 uuid（键名为 id / 各类引用键），排除外部 id"""
    own = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and UUID_FULL.match(v):
                    if k == "id" or k in ("application", "portal", "query", "process",
                                          "form", "script", "file", "view", "widget",
                                          "category", "parent", "dict"):
                        own.add(v)
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(obj)
    return own - set(foreign)


def make_id_map(ids):
    return {old: str(uuid.uuid4()) for old in sorted(ids)}


def apply_text_edits(raw, id_map, renames, url_rules):
    """全部改动都在**文本域**完成，保证 data 内层字符串不被重新序列化"""
    stats = OrderedDict()
    for old, new in id_map.items():
        n = raw.count(old)
        if n:
            raw = raw.replace(old, new)
            stats[f"id:{old[:8]}"] = n
    # 改名：长串优先，避免子串误伤
    for old, new in sorted(renames, key=lambda p: -len(p[0])):
        if old == new or not old:
            continue
        n = raw.count(old)
        if n:
            raw = raw.replace(old, new)
            stats[f"name:{old}→{new}"] = n
    for old, new in url_rules:
        n = raw.count(old)
        if n:
            raw = raw.replace(old, new)
            stats[f"url:{old}"] = n
    return raw, stats


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="O2OA 应用克隆改造器")
    ap.add_argument("--src", required=True, help="源 .zip 或 .xapp")
    ap.add_argument("--out", required=True, help="输出 .xapp JSON 路径")
    ap.add_argument("--new-name", required=True, help="新应用名")
    ap.add_argument("--new-alias", default="", help="新应用 alias")
    ap.add_argument("--new-id", default="", help="指定新应用 id（默认随机）")
    ap.add_argument("--rename-map", default="", help="JSON: [[old,new],...]")
    ap.add_argument("--foreign-ids", default="", help="JSON: [id,...] 禁止重映射")
    ap.add_argument("--url-rules", default="", help="JSON: [[old,new],...]")
    ap.add_argument("--plan-out", default="", help="把 id 映射表写到文件")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = read_xapp(args.src)
    obj = json.loads(raw)
    print(f"源包: {args.src}")
    print(f"顶层键: {list(obj.keys())}")

    renames = json.loads(open(args.rename_map, encoding="utf-8").read()) if args.rename_map else []
    foreign = json.loads(args.foreign_ids) if args.foreign_ids else []
    url_rules = json.loads(args.url_rules) if args.url_rules else []

    own = collect_own_ids(obj, foreign)
    print(f"自有 id 数: {len(own)} | 排除外部 id: {len(foreign)}")
    id_map = make_id_map(own)

    # 新应用 id：替换掉 app 自身 id
    app_obj = (obj.get("processPlatformList") or [{}])[0]
    old_app_id = app_obj.get("id")
    new_app_id = args.new_id or id_map.get(old_app_id) or str(uuid.uuid4())
    if old_app_id in id_map:
        id_map[old_app_id] = new_app_id
    print(f"应用 id: {old_app_id} → {new_app_id}")

    raw, stats = apply_text_edits(raw, id_map, renames, url_rules)
    print("\n--- 替换统计（前 60 条） ---")
    for i, (k, v) in enumerate(stats.items()):
        if i >= 60:
            print(f"  ... 共 {len(stats)} 条")
            break
        print(f"  {k}  ×{v}")

    # 校验 JSON 仍然合法
    try:
        new_obj = json.loads(raw)
    except Exception as e:
        sys.exit(f"❌ 文本替换后 JSON 解析失败，已中止: {e}")

    # 显式设定应用名/别名
    new_obj["processPlatformList"][0]["name"] = args.new_name
    if args.new_alias:
        new_obj["processPlatformList"][0]["alias"] = args.new_alias

    out = raw if False else json.dumps(new_obj, ensure_ascii=False, indent=2)
    if args.dry_run:
        print("\n[dry-run] 未写文件。新应用名:", new_obj["processPlatformList"][0]["name"],
              "| id:", new_obj["processPlatformList"][0]["id"])
        print("新包顶层清单:")
        a = new_obj["processPlatformList"][0]
        print("  表单:", [f.get("name") for f in a.get("formList", [])])
        print("  流程:", [p.get("name") for p in a.get("processList", [])])
        for po in new_obj.get("portalList") or []:
            print("  门户:", po.get("name"), "页:", [p.get("name") for p in po.get("pageList", [])])
        for q in new_obj.get("queryList") or []:
            print("  查询:", q.get("name"), "视图数:", len(q.get("viewList", [])))
        return

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\n✅ 已写出: {args.out}")
    print(f"新应用 id: {new_app_id}")
    if args.plan_out:
        with open(args.plan_out, "w", encoding="utf-8") as f:
            json.dump({"app_id": new_app_id, "id_map": id_map}, f, ensure_ascii=False, indent=2)
        print(f"id 映射表: {args.plan_out}")


if __name__ == "__main__":
    main()
