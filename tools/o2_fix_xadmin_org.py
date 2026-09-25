#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给「业务管理员账号」补建「人员 + 组织身份」，使其可正常启动流程。

背景（2026-09-21 彻查结论）：
    xadmin 是虚拟初始管理员（Config.token().isInitialManager()），
    - 不在 ORG_PERSON 表，distinguishedName = xadmin@o2oa@P，无任何身份；
    - 因此流程引擎报「"xadmin" 没有加入任何组织，不能启动流程」。
    - 且 O2OA 有硬校验 **「不能使用初始管理员标识」**：任何 name/unique 含 xadmin
      （大小写不敏感、前缀匹配）的人员都无法创建 → xadmin 在设计上不能当业务人员。
    - 又因身份接口要求人员必须在 ORG_PERSON 中真实存在，两条路互为死锁，无法硬绕。

本脚本采用官方语义：另建一个真实业务管理员账号（默认 name=系统管理员 / unique=admin），
挂到顶层组织「中国复合材料工业协会」并设为主职，可正常发起/接收流程。

用法：
    python o2_fix_xadmin_org.py check      # 只读，列出当前状态
    python o2_fix_xadmin_org.py apply      # 建人员 + 建身份（幂等）
    python o2_fix_xadmin_org.py rollback   # 撤销（删除身份 + 人员）
    python o2_fix_xadmin_org.py password   # 给该账号设一个已知密码

可调参数见下方常量（改 name/unique 即可）。
"""
import sys, json, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

from o2 import login, get, post, put, extract_list

ORG = "/x_organization_assemble_control/jaxrs"
TOP_UNIT_ID = "9e8b0b36-dff7-4a2c-8964-11b360d7776e"      # 中国复合材料工业协会
TOP_UNIT_UNIQUE = "51100000500009247D"

PERSON_NAME = "系统管理员"
PERSON_UNIQUE = "admin"
PERSON_MOBILE = "13900000000"      # 占位手机号：mobile 必填且需过格式校验
PERSON_MAIL = "admin@o2oa.local"
PERSON_PASSWORD = "o2oaadmin2026"  # 与 xadmin 同密码，便于记忆


def _msg(j):
    if isinstance(j, dict):
        return f"{j.get('type')}/{j.get('message')}"
    return str(j)[:120]


def find_person(tok, key=PERSON_UNIQUE):
    """按 unique 查人员（返回真实记录，虚拟管理员回退态不算）"""
    st, j = get(f"{ORG}/person/{key}", tok)
    if st == 200 and isinstance(j, dict):
        d = j.get("data")
        if isinstance(d, dict) and d.get("id"):
            pid = str(d.get("id"))
            if pid == "xadmin" or not d.get("distinguishedName"):
                return None        # 虚拟管理员回退态，非真实记录
            return d
    return None


def find_identity(tok, person_unique=PERSON_UNIQUE, unit_unique=TOP_UNIT_UNIQUE):
    """用组织端点列出成员身份，找出目标人员的身份"""
    st, j = get(f"{ORG}/unit/{TOP_UNIT_ID}", tok)
    if st != 200 or not isinstance(j, dict):
        return None
    d = j.get("data") or {}
    for ident in (d.get("woSubDirectIdentityList") or []) + (d.get("woIdentityList") or []):
        p = ident.get("woPerson") or {}
        if p.get("unique") == person_unique or ident.get("unique") == f"{unit_unique}_{person_unique}":
            return ident
    return None


def check(tok):
    p = find_person(tok)
    i = find_identity(tok)
    print(f"[person ] {PERSON_NAME}: {'存在 id=' + p['id'] if p else '不存在'}")
    print(f"[identity] {PERSON_NAME} @ 中国复合材料工业协会: "
          f"{'存在 dN=' + str(i.get('distinguishedName')) if i else '不存在'}")
    return p, i


def apply_(tok):
    p = find_person(tok)
    if p:
        print(f"[person ] 已存在，跳过创建 (id={p['id']}, unique={p.get('unique')})")
    else:
        body = {
            "name": PERSON_NAME,
            "unique": PERSON_UNIQUE,
            "mobile": PERSON_MOBILE,
            "mail": PERSON_MAIL,
            "description": "系统初始管理员（由 o2_fix_xadmin_org.py 创建）",
        }
        st, j = post(f"{ORG}/person", body, tok)
        print(f"[person ] POST -> {st} {_msg(j)}")
        if st != 200:
            raise SystemExit("创建人员失败，中止")
        for _ in range(6):
            time.sleep(1.5)
            p = find_person(tok)
            if p:
                break
        if not p:
            raise SystemExit("创建人员后复查失败，中止（可能被唯一性校验拒绝）")
        print(f"[person ] 创建成功 id={p['id']} unique={p.get('unique')} dN={p.get('distinguishedName')}")

    i = find_identity(tok)
    if i:
        print(f"[identity] 已存在，跳过创建 (id={i['id']}, dN={i.get('distinguishedName')})")
    else:
        person_dn = p.get("distinguishedName") or f"{PERSON_NAME}@{PERSON_UNIQUE}@P"
        body = {
            "person": person_dn,
            "unit": TOP_UNIT_ID,
            "major": True,          # 主职
            "name": PERSON_NAME,
        }
        st, j = post(f"{ORG}/identity", body, tok)
        print(f"[identity] POST -> {st} {_msg(j)}")
        if st != 200:
            raise SystemExit("创建身份失败，中止")
        for _ in range(6):
            time.sleep(1.5)
            i = find_identity(tok)
            if i:
                break
        if not i:
            raise SystemExit("创建身份后复查失败，中止")
        print(f"[identity] 创建成功 id={i['id']} dN={i.get('distinguishedName')}")

    set_password(tok)
    grant_manager_role(tok)

    print("\n=== 完成 ===")
    check(tok)
    print(f"\n登录账号: {PERSON_UNIQUE}    密码: {PERSON_PASSWORD}")
    print("提示：首次登录后建议在「个人设置」里改密码。")


def set_password(tok):
    """给人员设置密码。

    ⚠️ 正确端点（从 xAction/services/x_organization_assemble_control.json 查到）：
       changePassword: PUT /jaxrs/person/{name}/set/password   字段名是 value（不是 password！）
       resetPassword : PUT /jaxrs/person/{flag}/reset/password（不带 body）
    """
    p = find_person(tok)
    if not p:
        print("[password] 人员不存在，跳过")
        return
    st, j = put(f"{ORG}/person/{PERSON_UNIQUE}/set/password", {"value": PERSON_PASSWORD}, tok)
    print(f"[password] set/password -> {st} {_msg(j)}")


# 业务管理员需要的系统角色：unique -> roleId
# （roleId 是 O2OA 内置角色的固定 id，见 ORG_ROLE 表；如镜像重置可改走 list 接口）
ROLE_IDS = {
    "ManagerSystemRole": "794455a8-3b6a-4573-8e46-047ff21cd7e0",
    "OrganizationManagerSystemRole": "e6031766-60c8-4eb5-8e9e-289d922b5c72",
    "ProcessPlatformManagerSystemRole": "394a788d-210e-4376-ab25-a04cd72d5512",
}


def grant_manager_role(tok):
    """给业务管理员授予系统角色。

    ⚠️ 角色成员维护在 role 侧：PUT /jaxrs/role/{roleId}，
       且必须提交完整对象（name/unique 缺一即报「角色名称不能为空」）；
       personList 存的是人员 **id**（写入后会归一化为 id 列表）。
    ⚠️ 查角色列表别用 role/list/like + 空 key（返回空数组），直接用已知 roleId。
    """
    p = find_person(tok)
    if not p:
        print("[role] 人员不存在，跳过")
        return

    for uniq, rid in ROLE_IDS.items():
        st, j = get(f"{ORG}/role/{rid}", tok)
        if st != 200 or not isinstance(j, dict):
            print(f"[role] {uniq}: 读取失败 {st}")
            continue
        d = dict(j.get("data") or {})
        if d.get("unique") != uniq:
            print(f"[role] {uniq}: id 不匹配（实际 {d.get('unique')}），跳过")
            continue
        plist = list(d.get("personList") or [])
        if p["id"] in plist:
            print(f"[role] {uniq}: 已有该成员，跳过")
            continue
        plist.append(p["id"])
        d["personList"] = plist
        for k in ("woPersonList", "woGroupList", "control", "isSystemRole"):
            d.pop(k, None)
        st, j = put(f"{ORG}/role/{rid}", d, tok)
        print(f"[role] {uniq}: PUT -> {st} {_msg(j)}")


def rollback(tok):
    i = find_identity(tok)
    if i:
        st, j = _delete(f"{ORG}/identity/{i['id']}", tok)
        print(f"[identity] DELETE -> {st} {_msg(j)}")
    else:
        print("[identity] 不存在，跳过")
    p = find_person(tok)
    if p:
        st, j = _delete(f"{ORG}/person/{p['id']}", tok)
        print(f"[person ] DELETE -> {st} {_msg(j)}")
    else:
        print("[person ] 不存在，跳过")


def _delete(path, tok):
    """urllib 的 DELETE（o2.py 未提供）"""
    import urllib.request, urllib.error
    from o2 import BASE
    req = urllib.request.Request(BASE + path, headers={"x-token": tok}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(t)
            except Exception:
                return r.status, t
    except urllib.error.HTTPError as e:
        t = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(t)
        except Exception:
            return e.code, t


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    tok = login()
    print(f"--- mode={mode} ---")
    if mode == "check":
        check(tok)
    elif mode == "apply":
        apply_(tok)
    elif mode == "rollback":
        rollback(tok)
    else:
        print("用法: check | apply | rollback")
