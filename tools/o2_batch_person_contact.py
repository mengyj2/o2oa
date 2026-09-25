#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 人员「联系方式」批量运维工具（手机号 / 邮箱 / 重置密码）

来源：2026-09-23 实名名单落地（9 人）时的一次性脚本，此文件是其**持久化通用版**。
配套技能：~/.workbuddy/skills/o2oa-local-admin-account/SKILL.md §4.3
配套记录：docs/账号信息变更与密码重置清单-2026-09-23.md

------------------------------------------------------------
为什么这样写（血泪要点，改代码前先读）
------------------------------------------------------------
1) 操作者必须用 `xadmin`，不能用 `admin`：
   ActionEdit.convertControllerList 会**无条件**把操作者写进目标人的
   controllerList；只有命中 Config.token().isInitialManager() 的 xadmin 才跳过。
   用 admin 每改一个人就给自己添一条「控制者」关系 = 无谓数据污染。
   （xadmin 登录后 tokenType=manager，Business.editable() 走 isManager() 放行，权限足够。）

2) 手机号是**单值**字段：BaseAction.checkMobile -> Config.person().isMobile(mobile)
   用 person.json.mobileRegex 对**整串** Pattern.matches，没有 split。
   ⇒ "13371637051;13371677253" 必 500。要留第二个号 → 写 PersonAttribute
     "备用手机号"（本工具 --attr-mobile 自动处理；注意值字段是 attributeList 数组！）

3) PUT 返回 200 不等于改成功，也别急着信紧跟其后的 GET：
   - ActionEdit 在 emc.commit() 之后才调 collect 上报，断网封锁 collect 可能返 500
     但数据其实已落库；
   - 紧接 PUT 的 GET 会读到旧缓存（实测首读旧值、数秒后重读才对）。
   ⇒ 本工具的回读带重试，并以回读结果为准。

4) 重置密码 = 手机号后 6 位 + "%o2"（person.json 的 password 脚本
   `return person.getMobile().slice(-6) + "%o2";`）
   ⇒ 必须**先改手机号、后 reset**，否则密码按旧号算。
   接口只回 {"value":true} 不回显密码 ⇒ 唯一铁证是**拿该密码真登录一次**。

5) admin / xadmin 受 ExceptionDenyResetInitialManagerPassword 硬保护，重置不了。

6) 初始密码有**时效性**，且失败尝试要克制（2026-09-23 15:39 实测踩到）：
   person.json 的 firstLoginModifyPwd=true ⇒ 用户首次用初始密码登录后被强制改密，
   初始密码随即失效。此时"初始密码登不上"是**正常**的，不是故障。
   判定方法（本工具 verify 已内置）：reset/password **不写** xchangePasswordTime，
   所以该列非空 == 用户本人改过密码（DB 旁证）。
   ★ 而登录失败会累计 failureCount，满 Config.person().getFailureCount()（默认 5）即
     LOCK（status=LOCK, lockExpireTime=now+failureInterval）；且**成功登录不会清零
     failureCount**，只有"距上次失败超过 failureInterval 分钟"的下一次失败才重置为 1。
   ⇒ verify 对已知改过密的账号**直接跳过登录尝试**（用 --force 才强行试）。

------------------------------------------------------------
用法
------------------------------------------------------------
名册 JSON（见 docs/artifacts/person-contact-20260923/roster.json 的示例）：
{
  "base": "http://localhost:9090",
  "operator": {"credential": "xadmin", "password": "o2oaadmin2026"},
  "people": [
    {"unique": "lijing", "mobile": "13371637052", "mail": "lijing@ccia.xin", "reset": true}
  ]
}

  python o2_batch_person_contact.py backup   --roster roster.json [-o before.json]
  python o2_batch_person_contact.py apply    --roster roster.json [--dry-run] [--no-reset]
  python o2_batch_person_contact.py verify   --roster roster.json          # 回读 + 真登录
  python o2_batch_person_contact.py rollback --snapshot before.json

  约定：手机号里含 ";" 时，第 1 段写 mobile，其余段写人员属性「备用手机号」。

依赖：仅 Python 标准库（与本项目 mailservice 一致）。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "http://localhost:9090"
ORG_PATH = "/x_organization_assemble_control/jaxrs"
AUTH_PATH = "/x_organization_assemble_authentication/jaxrs/authentication"
# 状态更新时的手机号唯一性/格式校验在此服务端完成，不需要 localhost 代理
DEFAULT_OPERATOR = {"credential": "xadmin", "password": "o2oaadmin2026"}

# ActionEdit 回写白名单：只回吐真正属于 Person 的可写字段。
# 不要整段回吐 GET 的 data（里面混有 woIdentityList/woRoleList/control/topUnitList/mobileValid 等）
PERSON_ECHO_KEYS = [
    "name", "unique", "description", "employee", "orderNumber", "status",
    "superior", "controllerList", "mail", "mobile", "distinguishedName",
]
# Wi copier 已排除、回吐也无害，但显式列出以便日后排查
PERSON_UNWRITABLE = [
    "id", "createTime", "updateTime", "pinyin", "pinyinInitial", "topUnitList",
    "password", "passwordExpiredTime", "changePasswordTime",
    "lastLoginTime", "lastLoginAddress", "lastLoginClient",
    "icon", "iconMdpi", "iconLdpi",
]


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def request(method, url, token=None, body=None, timeout=60):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["x-token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")
    except Exception as err:                                    # noqa: BLE001
        return -1, str(err)


def brief(raw):
    """把 O2OA 响应压成一行可读摘要。"""
    try:
        j = json.loads(raw)
        return "%s | %s" % (j.get("type"), (j.get("message") or "").strip()[:200])
    except Exception:                                            # noqa: BLE001
        return (raw or "")[:200]


def api(base, path, **kw):
    return request(kw.pop("method", "GET"), base + path, **kw)


def login(base, credential, password):
    st, raw = api(base, AUTH_PATH, method="POST",
                  body={"credential": credential, "password": password})
    if st != 200:
        raise SystemExit("[FATAL] 登录 %s 失败：HTTP %s %s" % (credential, st, brief(raw)))
    data = json.loads(raw)["data"]
    return data["token"], data


# --------------------------------------------------------------------------
# 人员读写
# --------------------------------------------------------------------------
def get_person(base, token, flag, retries=3, delay=1.2):
    """按 flag（unique/name/id/dN 均可）取人员；带缓存穿透重试。"""
    last = None
    for _ in range(retries):
        st, raw = api(base, "%s/person/%s" % (ORG_PATH, flag), token=token)
        if st == 200:
            return json.loads(raw)["data"]
        last = "HTTP %s %s" % (st, brief(raw))
        time.sleep(delay)
    raise SystemExit("[FATAL] 读取人员 %s 失败：%s" % (flag, last))


def _echo_body(person):
    body = {}
    for k in PERSON_ECHO_KEYS:
        v = person.get(k)
        if v is not None and v != "":
            body[k] = v
    return body


def update_person(base, token, person, mobile, mail):
    """只改 mobile/mail，其余白名单字段原样回写（组织关系不动的关键）。"""
    body = _echo_body(person)
    body["mobile"] = mobile
    body["mail"] = mail
    return api(base, "%s/person/%s" % (ORG_PATH, person["id"]),
               method="PUT", token=token, body=body)


def set_extra_mobile(base, token, person, numbers):
    """把多出来的手机号写进人员属性「备用手机号」。

    ★ 值字段是 attributeList（数组）不是 attribute —— 写 attribute 会静默建成空属性。
    """
    pid = person["id"]
    attr_id = None
    for a in (person.get("woPersonAttributeList") or []):
        if a.get("name") == "备用手机号":
            attr_id = a["id"]
            break
    if not attr_id:
        st, raw = api(base, "%s/personattribute" % ORG_PATH, method="POST", token=token,
                      body={"person": pid, "name": "备用手机号"})
        if st != 200:
            return st, "创建属性失败：%s" % brief(raw)
        attr_id = json.loads(raw)["data"]["id"]
    st, raw = api(base, "%s/personattribute/%s" % (ORG_PATH, attr_id), method="PUT", token=token,
                  body={"person": pid, "name": "备用手机号", "attributeList": list(numbers)})
    return st, brief(raw)


def reset_password(base, token, flag):
    """reset/password 无 body；返回 {"value":true}，不回显密码。"""
    return api(base, "%s/person/%s/reset/password" % (ORG_PATH, flag), token=token)


def list_identities(base, token, person_id):
    st, raw = api(base, "%s/identity/list/person/%s" % (ORG_PATH, person_id), token=token)
    return json.loads(raw).get("data", []) if st == 200 else []


def list_roles(base, token, person_id):
    st, raw = api(base, "%s/role/list/person/%s" % (ORG_PATH, person_id), token=token)
    return json.loads(raw).get("data", []) if st == 200 else []


def org_fingerprint(base, token, person_id):
    """组织关系指纹：身份 + 角色。用于证明「组织关系不变」。"""
    ids = [(x.get("id"), x.get("unitName"), x.get("unique"), bool(x.get("major")))
           for x in list_identities(base, token, person_id)]
    rls = sorted(x.get("distinguishedName", "") for x in list_roles(base, token, person_id))
    return {"identities": sorted(ids), "roles": rls}


# --------------------------------------------------------------------------
# 可选：DB 旁证（区分「用户自己改了密码」与「真故障」）
# --------------------------------------------------------------------------
def db_probe(cfg, unique):
    """读 xchangePasswordTime / xlastLoginTime / xfailureCount。

    ★ 为什么需要它：reset/password **不写** xchangePasswordTime（实测：被重置但从未登录的
      账号该列为 NULL）。所以「xchangePasswordTime 非空」= **用户本人改过密码**。
       配合 firstLoginModifyPwd=true 的行为，用户首次用初始密码登录后会被强制改密
       ⇒ 初始密码随即失效，此时「初始密码登不上」是**正常且预期**的，不是故障。
    返回 None 表示取不到（未配置 mysql 段 / docker 不可用 / 查不到），此时按无法归因处理。
    """
    my = cfg.get("mysql")
    if not my:
        return None
    sql = ("SELECT xchangePasswordTime, xlastLoginTime, IFNULL(xfailureCount,0) "
           "FROM ORG_PERSON WHERE xunique='%s'" % str(unique).replace("'", ""))
    cmd = ["docker", "exec", my["container"], "mysql",
           "-u" + my.get("user", "root"), "-p" + my.get("password", ""),
           my.get("database", "X"), "-N", "-B", "-e", sql]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        lines = [l for l in out.stdout.strip().splitlines() if l.strip()]
        if not lines:
            return None
        f = lines[-1].split("\t")
        if len(f) < 3:
            return None
        return {"changePasswordTime": None if f[0] in ("NULL", "") else f[0],
                "lastLoginTime": None if f[1] in ("NULL", "") else f[1],
                "failureCount": f[2]}
    except Exception:                                            # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def load_roster(path):
    with io.open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("base", DEFAULT_BASE)
    cfg.setdefault("operator", DEFAULT_OPERATOR)
    cfg.setdefault("people", [])
    return cfg


def cmd_backup(args):
    cfg = load_roster(args.roster)
    base = cfg["base"]
    token, _ = login(base, cfg["operator"]["credential"], cfg["operator"]["password"])
    snap = {"base": base, "takenAt": time.strftime("%Y-%m-%d %H:%M:%S"), "people": []}
    for p in cfg["people"]:
        cur = get_person(base, token, p["unique"])
        snap["people"].append({
            "unique": p["unique"],
            "target": {"mobile": p.get("mobile"), "mail": p.get("mail"),
                       "reset": bool(p.get("reset", True))},
            "person": cur,                       # 完整 Person 对象，回滚就靠它
            "org": org_fingerprint(base, token, cur["id"]),
        })
        print("  [backup] %-11s id=%s mobile=%r mail=%r" % (
            p["unique"], cur["id"], cur.get("mobile"), cur.get("mail")))
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.roster)), "before.json")
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print("\n快照 -> %s（%d 人）" % (out, len(snap["people"])))


def cmd_apply(args):
    cfg = load_roster(args.roster)
    base = cfg["base"]
    token, who = login(base, cfg["operator"]["credential"], cfg["operator"]["password"])
    print("[login] %s ok, tokenType=%s, id=%s\n" % (
        cfg["operator"]["credential"], who.get("tokenType"), who.get("id")))

    results = []
    for p in cfg["people"]:
        unique, mail = p["unique"], p.get("mail")
        raw_mobile = p.get("mobile") or ""
        parts = [x.strip() for x in raw_mobile.split(";") if x.strip()]
        mobile, extras = (parts[0] if parts else ""), parts[1:]
        do_reset = bool(p.get("reset", True))
        rec = {"unique": unique, "mobile": mobile, "extras": extras, "mail": mail,
               "reset": do_reset}
        print("=" * 72)
        print("### %s -> mobile=%r mail=%r reset=%s%s" % (
            unique, mobile, mail, do_reset, "  [DRY-RUN]" if args.dry_run else ""))

        cur = get_person(base, token, unique)
        rec["id"] = cur["id"]
        rec["before"] = {"mobile": cur.get("mobile"), "mail": cur.get("mail"),
                         "org": org_fingerprint(base, token, cur["id"])}

        need = (cur.get("mobile") != mobile) or (cur.get("mail") != mail)
        if not need:
            print("  mobile/mail 已与目标一致 → 跳过字段更新")
            rec["update"] = "skipped(no change)"
        elif args.dry_run:
            print("  [DRY-RUN] 将 PUT /person/%s" % cur["id"])
            rec["update"] = "dry-run"
        else:
            st, raw = update_person(base, token, cur, mobile, mail)
            rec["update_http"], rec["update_msg"] = st, brief(raw)
            print("  PUT -> %s %s" % (st, rec["update_msg"]))

            # 回读（带重试）：以回读为准，不信 PUT 的状态码
            ok = False
            for _ in range(3):
                time.sleep(1.2)
                after = get_person(base, token, cur["id"])
                if after.get("mobile") == mobile and after.get("mail") == mail:
                    ok = True
                    break
            rec["field_ok"] = ok
            rec["after"] = {"mobile": after.get("mobile"), "mail": after.get("mail"),
                            "updateTime": after.get("updateTime")}
            print("  回读: mobile=%r mail=%r -> %s" % (
                after.get("mobile"), after.get("mail"), "OK" if ok else "MISMATCH"))

            if extras and not args.dry_run:
                st2, m2 = set_extra_mobile(base, token, after, extras)
                rec["attr_http"], rec["attr_msg"] = st2, m2
                print("  备用手机号 %s -> %s %s" % (extras, st2, m2))

        if do_reset and not args.dry_run:
            st, raw = reset_password(base, token, unique)
            rec["reset_http"], rec["reset_msg"] = st, brief(raw)
            print("  reset/password -> %s %s" % (st, rec["reset_msg"]))
        elif do_reset:
            print("  [DRY-RUN] 将 reset/password")
        else:
            print("  [跳过] 按名册 reset=false")

        # 组织关系 diff：这是「组织关系不变」的硬证据
        if not args.dry_run and rec.get("before"):
            now = org_fingerprint(base, token, cur["id"])
            rec["org_unchanged"] = (now == rec["before"]["org"])
            print("  组织关系: %s" % ("未变 ✅" if rec["org_unchanged"] else "★ 有变化，请核查"))

        results.append(rec)

    if args.report:
        with io.open(args.report, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print("\n明细 -> %s" % args.report)

    print("\n" + "#" * 72)
    bad = [r for r in results if r.get("field_ok") is False or r.get("org_unchanged") is False]
    print("# 完成 %d 人；字段/组织异常 %d 人" % (len(results), len(bad)))
    for r in results:
        print("  %-12s mobile=%-14s mail=%-24s field=%s org=%s reset=%s" % (
            r["unique"], r["mobile"], r["mail"], r.get("field_ok", "-"),
            r.get("org_unchanged", "-"), r.get("reset_http", "-")))
    return 1 if bad else 0


def cmd_verify(args):
    """回读 + 用「手机号后6位+%o2」真登录一次。

    ★ 时效性警告（2026-09-23 实测踩到）：初始密码只在该用户**首次登录并改密之前**有效。
      系统 firstLoginModifyPwd=true ⇒ 用户一登录就被强制改密，初始密码随即失效。
      所以「初始密码登不上」必须区分两种含义，不能一律判 FAIL：
        · 用户本人已改密（xchangePasswordTime 非空，reset/password 并不写这一列）
          → 说明账号已被人正常启用，属**预期内的成功**
        · 用户从未改密却登不上 → 才是真故障
    """
    cfg = load_roster(args.roster)
    base = cfg["base"]
    token, _ = login(base, cfg["operator"]["credential"], cfg["operator"]["password"])
    out, n_ok, n_changed, n_fail, ntot = [], 0, 0, 0, 0
    print("（初始密码 = 手机号后6位 + %%o2；已被本人改密者不再适用）\n")
    for p in cfg["people"]:
        unique = p["unique"]
        parts = [x.strip() for x in (p.get("mobile") or "").split(";") if x.strip()]
        mobile = parts[0] if parts else ""
        expect_pwd = mobile[-6:] + "%o2"
        cur = get_person(base, token, unique)
        do_reset = bool(p.get("reset", True))
        st, typ, ttype, note = None, None, None, ""
        status = "skipped"
        if do_reset:
            ntot += 1
            # ★ 先看 DB 旁证：已知被本人改过密码的，就**不要**再拿初始密码去试 ——
            #   登录失败会累计 failureCount，满 Config.person().getFailureCount()（默认5）
            #   即 LOCK，且 **成功登录不会清零 failureCount**，只有"距上次失败超过
            #   failureInterval 分钟"的下一次失败才把计数重置为 1。所以失败尝试要克制。
            probe = db_probe(cfg, unique)
            if probe and probe.get("changePasswordTime") and not args.force:
                status = "已被本人改密(跳过尝试)"
                n_changed += 1
                note = "本人改密日=%s 最近登录=%s" % (
                    probe["changePasswordTime"], probe.get("lastLoginTime"))
            else:
                st, raw = api(base, AUTH_PATH, method="POST",
                              body={"credential": unique, "password": expect_pwd})
                try:
                    j = json.loads(raw)
                    typ, ttype = j.get("type"), (j.get("data") or {}).get("tokenType")
                    note = j.get("message", "")
                except Exception:                                # noqa: BLE001
                    note = raw[:160]
                if st == 200 and typ == "success":
                    status, n_ok = "初始密码有效", n_ok + 1
                else:
                    if probe is None:
                        probe = db_probe(cfg, unique)
                    if probe and probe.get("changePasswordTime"):
                        status = "已被本人改密(正常)"
                        n_changed += 1
                        note = "%s | 本人改密日=%s 最近登录=%s" % (
                            note, probe["changePasswordTime"], probe.get("lastLoginTime"))
                    else:
                        status, n_fail = "★ 需排查", n_fail + 1
                        note = "%s | DB旁证=%s" % (note, probe or "不可用")
        extra = ";".join("=".join([a["name"]] + a.get("attributeList", []))
                         for a in (cur.get("woPersonAttributeList") or []))
        out.append({"unique": unique, "name": cur.get("name"),
                    "mobile": cur.get("mobile"), "mail": cur.get("mail"), "attrs": extra,
                    "expect_password": expect_pwd if do_reset else "",
                    "login_http": st, "login_type": typ, "tokenType": ttype,
                    "status": status, "note": note})
        print("%-12s %-13s %-24s %-16s %s %s" % (
            unique, cur.get("mobile"), cur.get("mail"),
            expect_pwd if do_reset else "(保留原密码)", status, extra))
    if args.report:
        with io.open(args.report, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\n验证记录 -> %s" % args.report)
    print("\n初始密码仍有效 %d ｜ 已被本人改密 %d ｜ ★需排查 %d ｜ 合计 %d" % (
        n_ok, n_changed, n_fail, ntot))
    return 1 if n_fail else 0


def cmd_rollback(args):
    """用改前快照把 mobile/mail 写回。密码写不回（只能再 reset）。"""
    with io.open(args.snapshot, encoding="utf-8") as f:
        snap = json.load(f)
    base = snap["base"]
    token, _ = login(base, DEFAULT_OPERATOR["credential"], DEFAULT_OPERATOR["password"])
    for item in snap["people"]:
        cur = item["person"]
        st, raw = update_person(base, token, cur, cur.get("mobile"), cur.get("mail"))
        print("%-12s -> %s %s" % (item["unique"], st, brief(raw)))
    print("回滚完成（mobile/mail 已按快照还原；密码哈希无法还原）")


def main(argv=None):
    ap = argparse.ArgumentParser(description="O2OA 人员联系方式批量运维（手机号/邮箱/重置密码）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("backup", help="只读：抓改前全量快照（回滚用）")
    p.add_argument("--roster", required=True)
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("apply", help="执行改手机号/邮箱 + 重置密码")
    p.add_argument("--roster", required=True)
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何数据")
    p.add_argument("--no-reset", action="store_true", help="强制不重置密码")
    p.add_argument("--report", help="把逐人明细写成 JSON")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("verify", help="回读 + 用初始密码真登录验证")
    p.add_argument("--roster", required=True)
    p.add_argument("--report")
    p.add_argument("--force", action="store_true",
                   help="即使 DB 显示已被本人改密也强行尝试初始密码登录（会消耗失败配额）")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("rollback", help="按改前快照还原 mobile/mail")
    p.add_argument("--snapshot", required=True)
    p.set_defaults(func=cmd_rollback)

    args = ap.parse_args(argv)
    if args.cmd == "apply" and args.no_reset:
        cfg = load_roster(args.roster)
        for p_ in cfg["people"]:
            p_["reset"] = False
        tmp = args.roster + ".noreset.tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        args.roster = tmp
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
