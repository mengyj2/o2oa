#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 本地部署 —— 声明式状态层（Declarative State Layer）
=========================================================

问题
----
我们这几天对 O2OA 做的改动，有一大半只存在于**运行态**里：
  · 容器 config 卷里的 person.json / collect.json / custom_sms.json / components.json …
  · MySQL 里的 CPT_COMPONENT 行、门户字典 appmenus
  · 容器 webroot 里的自研组件目录

这些地方**没有任何版本记录**。容器一重建、换一台机器、切一个分支，
就全部丢失，而且没人能说清"我们到底改了什么"。这正是"打包成分支"卡住的点。

解法
----
把运行态与代码库之间补一层可 diff 的文本：

    snapshot   运行态 ──反抽──▶  deploy/state/      （进版本库，可 review / 可 diff）
    apply      deploy/state/ ──重放──▶ 运行态       （幂等，任意一套 O2OA 都能重建）
    verify     比对两侧，列出漂移（drift），不改动任何东西

设计原则
--------
1. 幂等：apply 跑 N 次与跑 1 次等价（按业务主键先删后插 / 整对象覆盖）。
2. 只碰自己的东西：DB 只按**明确列出的 xname** 操作，绝不整表重写。
3. 敏感值不落库：快照时把 password/secret/key 类字段换成 ${VAR} 占位符；
   重放时优先取环境变量，缺失则**继承目标侧现值**（绝不把密码写成空）。
4. docker exec 不可靠（本机 QEMU 下 setns 常失败）→ 文件搬运一律走 docker cp，
   数据库一律走 o2oa-mysql 容器（它的 exec 是好的）。

用法
----
    python deploy/o2_deploy.py snapshot          # 运行态 → deploy/state/
    python deploy/o2_deploy.py diff              # 看两侧漂移
    python deploy/o2_deploy.py apply             # deploy/state/ → 运行态
    python deploy/o2_deploy.py apply --no-restart
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, "deploy", "state")

O2OA_BASE = os.environ.get("O2OA_BASE", "http://localhost:9090")
O2OA_CONTAINER = os.environ.get("O2OA_CONTAINER", "o2oa-server")
MYSQL_CONTAINER = os.environ.get("O2OA_MYSQL_CONTAINER", "o2oa-mysql")
MYSQL_ROOT_PWD = os.environ.get("MYSQL_ROOT_PASSWORD", "o2oa_root_pwd")
DB_NAME = os.environ.get("O2OA_DB_NAME", "X")

ADMIN = os.environ.get("O2OA_ADMIN", "admin")
ADMIN_PWD = os.environ.get("O2OA_ADMIN_PASSWORD", "o2oaadmin2026")


# ---------------------------------------------------------------------------
# 1. 声明：哪些东西属于"我们的改动"
# ---------------------------------------------------------------------------
# 容器 config 目录里我们改动过 / 运行必需的文件。
# 判定依据：文件 mtime 晚于镜像构建时间，或内容含我们的定制项。
CONFIG_FILES = [
    "externalDataSources.json",   # 外部 MySQL 连接（含密码 → 占位符化）
    "person.json",                # 登录策略：captchaLogin / codeLogin
    "collect.json",               # 云平台连接（enable）与登录页标题
    "custom_sms.json",            # 自定义短信通道开关（本服务生效的三条件之一）
    "components.json",            # 桌面「系统管理」分组种子
    "general.json",               # 通用设置
    "o2oa_ai.json",               # AI 助手接入
    "portal.json",                # 门户默认配置
    "ternaryManagement.json",     # 三员管理开关
    "workTime.json",              # 工作时间
    "node_127.0.0.1.json",        # 节点端口
]

# 自动生成的密钥文件，绝不入库
CONFIG_SKIP = ["token.json", "keystore", "keystore.json"]

# 敏感字段判定 —— 宁可漏判也不能误判。
#
# 误判的代价很大：person.json 里 passwordPeriod / firstLoginModifyPwd 这类
# 【业务配置】一旦被当成密钥占位符化，重放到新环境就会写成字面量 "${...}"，
# 直接把登录策略搞坏。所以三条同时成立才算密钥：
#   ① 键名不以 ### 开头 —— O2OA 用 "###<key>" 存中文说明，值是文案不是凭据；
#   ② 值是字符串、非空、且不含中文 —— 排除说明文本、布尔、数字配置项；
#   ③ 键名归一化后命中凭据名单，或以凭据词结尾（xxxToken / xxxPassword）。
SECRET_KEYS = {
    "password", "passwd", "pwd", "secret", "token",
    "apikey", "accesskey", "accesskeyid", "accesskeysecret",
    "privatekey", "clientsecret", "appsecret",
}
SECRET_SUFFIX = ("password", "passwd", "pwd", "secret", "token", "accesskey")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def is_secret(key, val):
    if key.startswith("###"):
        return False
    if not isinstance(val, str) or not val or val.startswith("${"):
        return False
    if CJK_RE.search(val):
        return False
    norm = re.sub(r"[^a-z0-9]", "", key.lower())
    if norm in SECRET_KEYS:
        return True
    return any(norm.endswith(suf) and len(norm) > len(suf) for suf in SECRET_SUFFIX)


def sanitize(obj, path="$"):
    """把敏感字段替换为 ${ENV_VAR} 占位符。返回 (新对象, 占位符映射)。"""
    holes = {}

    def walk(node, p):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if is_secret(k, v):
                    var = "O2OA_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", k).upper()
                    out[k] = "${%s}" % var
                    holes[p + "." + k] = var
                else:
                    out[k] = walk(v, p + "." + k)
            return out
        if isinstance(node, list):
            return [walk(v, "%s[%d]" % (p, i)) for i, v in enumerate(node)]
        return node

    return walk(obj, path), holes

# 门户数据字典：用整对象 REST 读写（结构复杂，展开成 xpath0..7 行反而不可靠）
DICT_ALIASES = [
    # alias, 门户 flag（读用 flag，写用 dictId）
    {"alias": "appmenus", "portal": "index", "desc": "桌面门户「应用菜单」"},
]

# DB 行导出：只碰这些 xname / xtype 范围
CPT_COMPONENT_SCOPE = (
    "xname = 'SysSetting'"          # 我们加进「系统管理」分组的
    " OR xtype <> 'system'"         # 自建 custom 组件
)


# ---------------------------------------------------------------------------
# 2. 基础工具
# ---------------------------------------------------------------------------
def run(cmd, check=False, binary=False):
    r = subprocess.run(cmd, capture_output=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError("命令失败 %s\n%s" % (" ".join(map(str, cmd)),
                                               (r.stderr or b"").decode("utf-8", "replace")[:500]))
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def log(*a):
    print("  ".join(str(x) for x in a), flush=True)


def http(method, path, body=None, token=None, base=None):
    url = (base or O2OA_BASE).rstrip("/") + path
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") \
            if not isinstance(body, (bytes, bytearray)) else body
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    if token:
        req.add_header("x-token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            tk = resp.headers.get("x-token")
            try:
                return resp.status, json.loads(raw), tk
            except ValueError:
                return resp.status, raw, tk
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw), exc.headers.get("x-token")
        except ValueError:
            return exc.code, raw, exc.headers.get("x-token")


TOKEN = {"v": None}


def get_token():
    if TOKEN["v"]:
        return TOKEN["v"]
    st, data, tk = http("POST", "/x_organization_assemble_authentication/jaxrs/authentication",
                        {"credential": ADMIN, "password": ADMIN_PWD})
    if not tk:
        raise RuntimeError("登录失败，未取到 x-token（HTTP %s）：%s" % (st, str(data)[:200]))
    TOKEN["v"] = tk
    return tk


def cp_out(remote, local):
    """容器 → 宿主。docker cp 的源必须是容器内路径，目标是 Windows 形式。"""
    os.makedirs(os.path.dirname(local), exist_ok=True)
    r = run(["docker", "cp", "%s:%s" % (O2OA_CONTAINER, remote), local])
    return os.path.exists(local)


def cp_in(local, remote):
    return run(["docker", "cp", local, "%s:%s" % (O2OA_CONTAINER, remote)])


def mysql(sql, db=DB_NAME, raw=True):
    cmd = ["docker", "exec", MYSQL_CONTAINER, "mysql",
           "--default-character-set=utf8mb4", "-uroot", "-p" + MYSQL_ROOT_PWD,
           "-N", "-B"]
    if db:
        cmd += ["-D", db]
    cmd += ["-e", sql]
    return run(cmd)


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# 3. 敏感值：占位符化 / 还原
# ---------------------------------------------------------------------------
def unsanitize(new, existing):
    """把 ${VAR} 占位符还原：优先环境变量，缺失则继承 existing 同路径的现值。"""

    def get_path(node, p):
        cur = node
        for seg in p.strip("$").split(".")[1:]:
            m = re.match(r"^([^\[]+)(?:\[(\d+)\])?$", seg)
            if not m:
                return None
            cur = cur.get(m.group(1)) if isinstance(cur, dict) else None
            if m.group(2) is not None:
                cur = cur[int(m.group(2))] if isinstance(cur, list) and int(m.group(2)) < len(cur) else None
            if cur is None:
                return None
        return cur

    def walk(node, p, old):
        if isinstance(node, dict):
            return {k: walk(v, p + "." + k, (old or {}).get(k) if isinstance(old, dict) else None)
                    for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, "%s[%d]" % (p, i),
                         (old[i] if isinstance(old, list) and i < len(old) else None))
                    for i, v in enumerate(node)]
        if isinstance(node, str) and node.startswith("${") and node.endswith("}"):
            var = node[2:-1]
            if os.environ.get(var):
                return os.environ[var]
            if isinstance(old, str) and old:
                return old          # 继承现值：绝不把密码写空
            return node             # 无来源则原样保留，便于人工发现
        return node

    return walk(new, "$", existing)


# ---------------------------------------------------------------------------
# 4. snapshot —— 运行态 → deploy/state/
# ---------------------------------------------------------------------------
def snap_config():
    log("[config] 反抽容器 config 目录")
    out_dir = os.path.join(STATE, "o2oa-config")
    n = 0
    for name in CONFIG_FILES:
        tmp = os.path.join(out_dir, name)
        if not cp_out("/opt/o2server/config/" + name, tmp):
            log("   ! 跳过（容器内不存在）:", name)
            continue
        obj = jload(tmp)
        if obj is None:
            log("   ! 非 JSON，原样保留:", name)
            n += 1
            continue
        clean, holes = sanitize(obj)
        jdump(tmp, clean)
        n += 1
        if holes:
            log("   · %-28s 占位符 %d 处：%s" % (name, len(holes),
                                              ", ".join(sorted(holes.values()))))
        else:
            log("   · %-28s ok" % name)
    return n


def snap_db():
    log("[db] 反抽 MySQL 自建条目")
    out_dir = os.path.join(STATE, "db")
    # CPT_COMPONENT：自建组件条目 + 我们加进系统分组的
    sql = ("SELECT xid,xname,xpath,xtitle,xtype,IFNULL(xiconPath,''),"
           "IFNULL(xorderNumber,''),xvisible+0 FROM CPT_COMPONENT "
           "WHERE " + CPT_COMPONENT_SCOPE + " ORDER BY xtype, xorderNumber, xname;")
    raw = mysql(sql)
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 8:
            continue
        rows.append({
            "xid": f[0], "xname": f[1], "xpath": f[2], "xtitle": f[3],
            "xtype": f[4], "xiconPath": f[5], "xorderNumber": f[6], "xvisible": f[7],
        })
    jdump(os.path.join(out_dir, "cpt_component.json"), rows)
    log("   · cpt_component.json  %d 行" % len(rows))
    return len(rows)


def snap_dict():
    log("[dict] 反抽门户数据字典（整对象）")
    out_dir = os.path.join(STATE, "dict")
    tk = get_token()
    n = 0
    for d in DICT_ALIASES:
        st, data, _ = http("GET", "/x_portal_assemble_surface/jaxrs/dict/%s/portal/%s/data"
                           % (d["alias"], d["portal"]), token=tk)
        if st != 200 or not isinstance(data, dict):
            log("   ! %s 读取失败 HTTP %s" % (d["alias"], st))
            continue
        jdump(os.path.join(out_dir, d["alias"] + ".data.json"), data)
        log("   · %-12s ok（%s）" % (d["alias"], d["desc"]))
        n += 1
    return n


# ---------------------------------------------------------------------------
# 5. apply —— deploy/state/ → 运行态
# ---------------------------------------------------------------------------
def apply_config():
    log("[config] 重放容器 config 目录")
    src_dir = os.path.join(STATE, "o2oa-config")
    if not os.path.isdir(src_dir):
        log("   ! 无快照，跳过")
        return 0
    n = 0
    for name in sorted(os.listdir(src_dir)):
        if name in CONFIG_SKIP:
            continue
        src = os.path.join(src_dir, name)
        want = jload(src)
        if want is None:
            cp_in(src, "/opt/o2server/config/" + name)
            log("   · %-28s 原样覆盖" % name)
            n += 1
            continue
        # 读目标侧现值，用于继承占位符
        cur_path = os.path.join(BASE, ".tmp-apply", name)
        existing = None
        if cp_out("/opt/o2server/config/" + name, cur_path):
            existing = jload(cur_path)
        rendered = unsanitize(want, existing)
        jdump(cur_path, rendered)
        cp_in(cur_path, "/opt/o2server/config/" + name)
        changed = (json.dumps(existing, sort_keys=True, ensure_ascii=False)
                   != json.dumps(rendered, sort_keys=True, ensure_ascii=False))
        log("   · %-28s %s" % (name, "已更新" if changed else "无变化"))
        n += 1
    return n


def apply_db():
    log("[db] 重放 MySQL 自建条目")
    rows = jload(os.path.join(STATE, "db", "cpt_component.json"))
    if not rows:
        log("   ! 无快照，跳过")
        return 0
    stmts = []
    for r in rows:
        # 按 xname 先删后插 —— 幂等，且只碰声明的名字，绝不整表重写
        stmts.append("DELETE FROM CPT_COMPONENT WHERE xname=%s;" % esc(r["xname"]))
        stmts.append(
            "INSERT INTO CPT_COMPONENT (xid,xcreateTime,xupdateTime,xname,xpath,xtitle,"
            "xtype,xiconPath,xorderNumber,xvisible) VALUES (%s,NOW(),NOW(),%s,%s,%s,%s,%s,%s,%s);"
            % (esc(r["xid"]), esc(r["xname"]), esc(r["xpath"]), esc(r["xtitle"]),
               esc(r["xtype"]), esc(r["xiconPath"]),
               r["xorderNumber"] if r["xorderNumber"] not in ("NULL", "") else "NULL",
               "1" if str(r["xvisible"]) == "1" else "0"))
    sql = "SET NAMES utf8mb4;\n" + "\n".join(stmts)
    tmp = os.path.join(BASE, ".tmp-apply", "cpt_component.sql")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(sql)
    # 用 mysql 客户端从 stdin 执行（避免超长 -e 参数被 shell 截断）
    with open(tmp, "rb") as fh:
        r = subprocess.run(
            ["docker", "exec", "-i", MYSQL_CONTAINER, "mysql",
             "--default-character-set=utf8mb4", "-uroot", "-p" + MYSQL_ROOT_PWD, "-D", DB_NAME],
            stdin=fh, capture_output=True)
    if r.returncode != 0:
        log("   ! 执行失败：", r.stderr.decode("utf-8", "replace")[:300])
    else:
        log("   · cpt_component 重放 %d 行（先删后插，幂等）" % len(rows))
    return len(rows)


def esc(v):
    """SQL 字符串字面量转义（单引号翻倍 + 反斜杠转义）。"""
    s = "" if v is None else str(v)
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


def apply_dict():
    log("[dict] 重放门户数据字典")
    src_dir = os.path.join(STATE, "dict")
    if not os.path.isdir(src_dir):
        log("   ! 无快照，跳过")
        return 0
    tk = get_token()
    n = 0
    for d in DICT_ALIASES:
        path = os.path.join(src_dir, d["alias"] + ".data.json")
        body = jload(path)
        if not body:
            continue
        # 需要 dictId（写接口是 designer）——先查出来
        st, data, _ = http("GET", "/x_portal_assemble_surface/jaxrs/dict/%s/portal/%s/data"
                           % (d["alias"], d["portal"]), token=tk)
        if st != 200 or not isinstance(data, dict):
            log("   ! %s 无法定位" % d["alias"])
            continue
        dict_id = data.get("id")
        if not dict_id:
            log("   ! %s 拿不到 dictId，跳过" % d["alias"])
            continue
        # 写接口吃的是「设计态对象」：{id,name,alias,application,data:<字符串>}
        design = {
            "id": dict_id,
            "name": data.get("name") or d["alias"],
            "alias": data.get("alias") or d["alias"],
            "application": data.get("application") or "",
            "data": json.dumps(body.get("data") if isinstance(body.get("data"), (dict, list))
                               else body, ensure_ascii=False),
        }
        st2, _, _ = http("PUT",
                         "/x_portal_assemble_designer/jaxrs/dict/" + dict_id,
                         design, token=tk)
        log("   · %-12s HTTP %s %s" % (d["alias"], st2, "✅" if st2 == 200 else "❌"))
        n += 1
    return n


def restart():
    log("[restart] 重启 o2oa-server 使 config 生效")
    run(["docker", "restart", O2OA_CONTAINER])
    log("   已发出重启；O2OA 冷启约需数分钟（QEMU 下偏慢）")


# ---------------------------------------------------------------------------
# 6. verify —— 漂移比对（只读）
# ---------------------------------------------------------------------------
def _diff_keys(want, got):
    """列出两个 JSON 对象的顶层差异键（兼容 dict / list / 标量）。"""
    if isinstance(want, dict) and isinstance(got, dict):
        return [k for k in (set(want) | set(got)) if want.get(k) != got.get(k)]
    if isinstance(want, list) and isinstance(got, list):
        if want == got:
            return []
        return ["[数组长度 %d vs %d]" % (len(want), len(got))]
    return [] if want == got else ["[值不同]"]


def verify():
    log("[verify] 比对 deploy/state 与运行态")
    drift = []
    # config
    src_dir = os.path.join(STATE, "o2oa-config")
    for name in sorted(os.listdir(src_dir)) if os.path.isdir(src_dir) else []:
        want = jload(os.path.join(src_dir, name))
        if want is None:
            continue
        tmp = os.path.join(BASE, ".tmp-apply", "verify-" + name)
        if not cp_out("/opt/o2server/config/" + name, tmp):
            drift.append("%s：容器内不存在" % name)
            continue
        got = jload(tmp)
        # ★ 快照里的密钥是 ${占位符}，必须先用现网值还原再比，否则永远误报差异
        rendered = unsanitize(want, got)
        if json.dumps(rendered, sort_keys=True, ensure_ascii=False) != \
           json.dumps(got, sort_keys=True, ensure_ascii=False):
            drift.append("%s：差异字段 %s" % (name, ", ".join(sorted(_diff_keys(rendered, got))[:8])))
    # db
    rows = jload(os.path.join(STATE, "db", "cpt_component.json")) or []
    live = mysql("SELECT xname FROM CPT_COMPONENT WHERE " + CPT_COMPONENT_SCOPE + ";")
    live_names = set(x.strip() for x in live.splitlines() if x.strip())
    want_names = set(r["xname"] for r in rows)
    for miss in sorted(want_names - live_names):
        drift.append("CPT_COMPONENT 缺少：%s" % miss)
    for extra in sorted(live_names - want_names):
        drift.append("CPT_COMPONENT 多出（快照未覆盖）：%s" % extra)
    # dict
    tk = get_token()
    for d in DICT_ALIASES:
        path = os.path.join(STATE, "dict", d["alias"] + ".data.json")
        want = jload(path)
        if not want:
            continue
        st, got, _ = http("GET", "/x_portal_assemble_surface/jaxrs/dict/%s/portal/%s/data"
                          % (d["alias"], d["portal"]), token=tk)
        if st != 200:
            drift.append("字典 %s 读取失败 HTTP %s" % (d["alias"], st))
            continue
        wn = want.get("data") if isinstance(want.get("data"), (dict, list)) else want
        gn = got.get("data") if isinstance(got.get("data"), (dict, list)) else got
        if json.dumps(wn, sort_keys=True, ensure_ascii=False) != \
           json.dumps(gn, sort_keys=True, ensure_ascii=False):
            drift.append("字典 %s：内容有差异" % d["alias"])

    if not drift:
        log("   ✅ 无漂移（运行态与声明式状态一致）")
    else:
        for d in drift:
            log("   ·", d)
    return drift


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "verify"
    if cmd == "snapshot":
        log("== snapshot：运行态 → deploy/state ==")
        snap_config()
        snap_db()
        snap_dict()
        log("完成。产物在", STATE)
    elif cmd == "apply":
        log("== apply：deploy/state → 运行态 ==")
        apply_config()
        apply_db()
        apply_dict()
        if "--no-restart" not in args:
            restart()
    elif cmd == "verify":
        verify()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
