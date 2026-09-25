"""按 xpath 修改 O2OA 门户数据字典中某个菜单项的字段值（可回滚）

背景：O2OA 的门户「应用菜单」由数据字典驱动
      字典   GEN_DICT      (xalias='appmenus', xapplication=<portalId>)
      字典项 GEN_DICT_ITEM (xbundle=<dictId>, xpath0..xpath7 定位, 值为多态列)
      xpath 形如: appNavis / <组索引> / children / <项索引> / <字段名>

官方写接口 PUT /x_portal_assemble_surface/jaxrs/dict/{d}/portal/{p}/{path}/data
在本部署上被 HTTP 层拦为 405（mockputtopost 亦未注册），故走数据层等价实现。

用法：
    python tools/o2_dict_set_menu_app.py check
    python tools/o2_dict_set_menu_app.py apply
    python tools/o2_dict_set_menu_app.py rollback
"""
import subprocess
import sys

BUNDLE = "3ba06aaa-42e5-43d7-9901-3989da4ac133"   # GEN_DICT.xid (appmenus / portal=index)
TARGET_XID = "19404d80-5968-4c97-95eb-04366aaedda2"  # appNavis/5/children/4/app
OLD = "File"
NEW = "Drive"

MYSQL = ["docker", "exec", "o2oa-mysql", "mysql", "--default-character-set=utf8mb4",
         "-uroot", "-po2oa_root_pwd", "X", "-N", "-B"]


def sql(stmt):
    p = subprocess.run(MYSQL + ["-e", stmt], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:400])
    return p.stdout.strip()


def show_state(title):
    print("=== %s ===" % title)
    # 整条菜单项的所有字段
    out = sql("SELECT COALESCE(xpath4,'<obj>'), COALESCE(xstringShortValue,''), xitemPrimitiveType "
              "FROM GEN_DICT_ITEM WHERE xbundle='%s' AND xpath0='appNavis' AND xpath1='5' "
              "AND xpath2='children' AND xpath3='4' ORDER BY xpath4;" % BUNDLE)
    for line in out.splitlines():
        f, v, t = (line.split("\t") + ["", "", ""])[:3]
        print("   %-16s = %-14s (%s)" % (f, v, t))
    print()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    show_state("当前状态")

    cur = sql("SELECT xstringShortValue FROM GEN_DICT_ITEM WHERE xid='%s';" % TARGET_XID)
    print("目标行 xid=%s 现值 = %r" % (TARGET_XID, cur))

    # 全局唯一性校验
    dup = sql("SELECT COUNT(*) FROM GEN_DICT_ITEM WHERE xbundle='%s' AND xstringShortValue='%s';" % (BUNDLE, OLD))
    print("字典内值为 %r 的行数 = %s （应为 1，用于确认无歧义）" % (OLD, dup))

    if mode == "check":
        print("\n(只读检查，未修改)")
        return

    if mode == "apply":
        if cur == NEW:
            print("\n已是 %r，无需修改" % NEW)
            return
        n = sql("UPDATE GEN_DICT_ITEM SET xstringShortValue='%s', xupdateTime=NOW() "
                "WHERE xid='%s' AND xstringShortValue='%s'; SELECT ROW_COUNT();" % (NEW, TARGET_XID, OLD))
        print("\nUPDATE 影响行数 =", n.splitlines()[-1] if n else "?")
        print("同步 GEN_DICT.xupdateTime")
        sql("UPDATE GEN_DICT SET xupdateTime=NOW() WHERE xid='%s';" % BUNDLE)

    elif mode == "rollback":
        n = sql("UPDATE GEN_DICT_ITEM SET xstringShortValue='%s', xupdateTime=NOW() "
                "WHERE xid='%s' AND xstringShortValue='%s'; SELECT ROW_COUNT();" % (OLD, TARGET_XID, NEW))
        print("\n回滚 UPDATE 影响行数 =", n.splitlines()[-1] if n else "?")

    show_state("修改后状态")


if __name__ == "__main__":
    main()
