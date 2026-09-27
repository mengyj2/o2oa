#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o2_drive_entry.py —— 把「企业网盘」的全部入口指向自研组件 x_component_Drive

背景
----
本地 O2OA 的「企业网盘」原先指向安装包自带的老版文件组件（xpath=File，前端
x_component_File）。自研组件 x_component_Drive 落地后，必须把所有"入口"逐个
改指过去，否则会出现"改了一半"——表现为点某个入口仍是老界面或空白。

已知「企业网盘」有三个入口，数据源各不相同（这是本项目最大的坑）：
  1. 桌面「开始」菜单   -> MySQL `CPT_COMPONENT` 里 xname='企业网盘' 的 `xpath` 字段
                          （桌面按 xpath 作为 app 名调 layout.openApplication）
  2. 门户「应用列表」   -> 门户数据字典 `GEN_DICT` + `GEN_DICT_ITEM`
                          （xpath0..3 = appNavis/<组>/children/<项>/app）
  3. 桌面 applications.json / 门户 pcClient —— 实测均不含网盘项，无需处理

用法
----
  python tools/o2_drive_entry.py check     # 只读：列出三个入口现状
  python tools/o2_drive_entry.py apply     # 把入口 1、2 改指 Drive
  python tools/o2_drive_entry.py rollback  # 还原为 File

说明
----
* 只按精确 id / 唯一匹配定位，改前打印 before，改后复核，不做通配更新。
* 写库后需 `docker restart o2oa-server` 才生效（组件索引与字典均有内存缓存）。
"""

import re
import subprocess
import sys

MYSQL = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
         "-uroot", "-po2oa_root_pwd", "X", "-N", "-B", "-e"]

CPT_XID = "57af03cd-4a7b-4384-a858-260b0a8115bc"   # CPT_COMPONENT: 企业网盘
DICT_ID = "3ba06aaa-42e5-43d7-9901-3989da4ac133"   # GEN_DICT: appmenus / portal index
DICT_PATH = ("appNavis", "5", "children", "4", "app")  # 工作协同 / 企业网盘 / app

OLD, NEW = "File", "Drive"


def sql(stmt):
    p = subprocess.run(MYSQL + [stmt], capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 and "Warning" not in err:
        raise RuntimeError("SQL 失败: %s\n%s" % (stmt[:120], err))
    return out


def q(v):
    """SQL 字符串字面量转义（只用单引号，避免 shell/编码问题）。"""
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


# --------------------------------------------------------------- 入口 1：开始菜单
def entry1():
    rows = sql("SELECT xid, xname, xpath, xtype, xvisible FROM CPT_COMPONENT "
               "WHERE xid=%s;" % q(CPT_XID))
    if not rows:
        return None
    f = rows.split("\t")
    return {"xid": f[0], "name": f[1], "xpath": f[2], "type": f[3], "visible": f[4]}


def entry1_set(value):
    sql("UPDATE CPT_COMPONENT SET xpath=%s, xupdateTime=NOW() WHERE xid=%s;"
        % (q(value), q(CPT_XID)))


def entry1_by_name(name="企业网盘"):
    rows = sql("SELECT xid, xpath FROM CPT_COMPONENT WHERE xname=%s;" % q(name))
    return [r.split("\t") for r in rows.splitlines() if r.strip()]


# --------------------------------------------------------------- 入口 2：门户字典
def entry2():
    cond = " AND ".join("xpath%d=%s" % (i, q(v)) for i, v in enumerate(DICT_PATH))
    rows = sql("SELECT xid, xstringShortValue FROM GEN_DICT_ITEM "
               "WHERE xbundle=%s AND %s;" % (q(DICT_ID), cond))
    out = []
    for r in rows.splitlines():
        if r.strip():
            f = r.split("\t")
            out.append({"xid": f[0], "value": f[1]})
    return out


def entry2_set(value):
    cond = " AND ".join("xpath%d=%s" % (i, q(v)) for i, v in enumerate(DICT_PATH))
    sql("UPDATE GEN_DICT_ITEM SET xstringShortValue=%s, xupdateTime=NOW() "
        "WHERE xbundle=%s AND %s;" % (q(value), q(DICT_ID), cond))


# ------------------------------------------------------------------------- 命令
def cmd_check():
    print("=" * 72)
    print("入口 1 · 桌面「开始」菜单  (MySQL CPT_COMPONENT.xpath)")
    e = entry1()
    if e is None:
        print("  !! 未找到 xid=%s 的记录" % CPT_XID)
    else:
        flag = "OK" if e["xpath"] == NEW else ("需修正(现为 %s)" % e["xpath"])
        print("  xid   = %s" % e["xid"])
        print("  xname = %s   xtype=%s   visible=%s" % (e["name"], e["type"], e["visible"]))
        print("  xpath = %-8s -> %s" % (e["xpath"], flag))

    print()
    print("入口 2 · 门户「应用列表」  (GEN_DICT_ITEM %s)" % "/".join(DICT_PATH))
    its = entry2()
    if not its:
        print("  !! 未找到匹配行")
    for it in its:
        flag = "OK" if it["value"] == NEW else ("需修正(现为 %s)" % it["value"])
        print("  xid=%s  value=%-6s -> %s" % (it["xid"], it["value"], flag))
    if len(its) > 1:
        print("  ! 匹配到多行，apply 会全部更新，请先确认唯一性")

    print()
    print("入口 3 · 桌面 applications.json / 门户 pcClient")
    print("  实测不含网盘项，无需处理（见 docs/O2OA企业网盘(Drive)复刻实现.md）")


def _switch(target):
    print("把「企业网盘」入口从 %s 切到 %s\n" % (OLD if target == NEW else NEW, target))
    e = entry1()
    if e and e["xpath"] != target:
        print("  [1] CPT_COMPONENT.xpath: %s -> %s" % (e["xpath"], target))
        entry1_set(target)
    else:
        print("  [1] CPT_COMPONENT.xpath 已是 %s，跳过" % target)

    its = entry2()
    changed = 0
    for it in its:
        if it["value"] != target:
            changed += 1
    if changed:
        print("  [2] GEN_DICT_ITEM app 字段: %d 行 -> %s" % (changed, target))
        entry2_set(target)
    else:
        print("  [2] GEN_DICT_ITEM app 字段已是 %s，跳过" % target)

    print("\n复核：")
    cmd_check()


def cmd_apply():
    _switch(NEW)
    print("\n>> 记得执行： docker restart o2oa-server   （静态组件索引与字典均有内存缓存）")


def cmd_rollback():
    _switch(OLD)
    print("\n>> 记得执行： docker restart o2oa-server")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd not in ("check", "apply", "rollback"):
        print(__doc__)
        return 2
    {"check": cmd_check, "apply": cmd_apply, "rollback": cmd_rollback}[cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
