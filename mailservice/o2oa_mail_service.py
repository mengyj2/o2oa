#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 本地邮件验证码服务 —— 「x_sms_assemble_control」平替（纯本地 / 断云可用）

背景
----
O2OA 的短信验证码有两条下发通道（源码：x_program_center/jaxrs/code/ActionCreate.java、
x_organization_assemble_authentication/.../ActionCode.java、x_organization_assemble_personal/.../reset/ActionCode.java）：

    String customSms = applications().findApplicationName("x_sms_assemble_control");
    if (isNotBlank(customSms) && Config.customConfig("custom_sms") != null) {
        // 通道① 转给自定义短信服务
        getQuery(customSms, "sms/send/code/mobile/{mobile}/token/(0)");
        -> 期望 {"value": true}
    } else if (collect().getEnable() != true) {
        throw new ExceptionDisableCollect();          // 通道②未启用（本机已断云）
    } else { ... O2OA 云 ... }

且 Applications.findApplicationName(String) 的匹配规则（反编译字节码确认）：
    key.equalsIgnoreCase(name)  ||  key.endsWithIgnoreCase(".x_" + name)

因此：只要服务注册表里存在 className 以 ".x_sms_assemble_control" 结尾的条目，
      O2OA 就会把「发码 / 校验」全部转交给该服务。
本机不需要写一行 Java —— 通过 PUT x_program_center/jaxrs/center/regist/applications
注册一个指向本进程的「应用」即可。

本服务职责
----------
1. 实现 O2OA 契约（由 O2OA 服务端主动调用本进程，非浏览器）：
     GET /x_sms_assemble_control/jaxrs/sms/send/code/mobile/{mobile}/token/{token}
     GET /x_sms_assemble_control/jaxrs/sms/validate/mobile/{mobile}/answer/{answer}/token/{token}
   —— 验证码的生成与校验都在本进程完成（通道①下 O2OA 自己的 Code 表不参与）。
2. 验证码投递：通过手机号反查 O2OA 人员 → 取其注册邮箱 → SMTP 发送。
3. 管理接口（供自研「系统设置」桌面组件调用，带 CORS）：
     GET  /api/health      GET/PUT /api/config     POST /api/test/mail
     POST /api/test/code   GET /api/log            GET /api/status
     POST /api/register    POST /api/revoke
4. 启动时自动把自身注册进 O2OA 服务表，并周期性重注册（防被节点心跳清理）。

依赖：仅 Python 标准库（smtplib / ssl / http.server / urllib / json）。
"""

import json
import os
import re
import ssl
import sys
import time
import uuid
import random
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import smtplib
import socket
from collections import deque
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# 常量 / 路径
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))

# 运行期数据目录（可写）：所有可变状态（配置 / 验证码 / 日志 / PID）都落这里。
#   · 容器化部署：挂载到 /data（见 mailservice/Dockerfile 与 docker-compose.yml）
#   · 宿主直跑：默认就是源码目录，行为与历史版本完全一致
# 用环境变量而非硬编码，是为了让「同一份代码」既能跑容器也能跑宿主（配置即代码）。
DATA_DIR = os.environ.get("O2OA_MAIL_DATA_DIR") or HERE
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass

CONFIG_PATH = os.environ.get("O2OA_MAIL_CONFIG") or os.path.join(DATA_DIR, "mail.json")
CODES_PATH = os.path.join(DATA_DIR, "codes.json")
LOG_PATH = os.path.join(DATA_DIR, "mailservice.log")
# 本进程 PID 落盘：供外部运维脚本（status/stop bat）判活
PID_PATH = os.path.join(DATA_DIR, "mailservice.pid")

DEFAULT_PORT = 8095
APP_NAME = "x_sms_assemble_control"
# className 必须以 ".x_sms_assemble_control" 结尾才会被 findApplicationName 命中
APP_CLASS_NAME = "com.x.ccia.sms.assemble.control.x_sms_assemble_control"
APP_TITLE = "邮件验证码服务"
CTX_PATH = "/x_sms_assemble_control"
# 容器 -> 宿主机本进程的访问地址；用 node 字段承载（getUrlJaxrsRoot 只用 node+port 拼 URL）。
# ★★ 实测（2026-09-23）：O2OA 容器为断云把 dns 指向 127.0.0.1，导致容器内
#    「host.docker.internal」这类域名【完全无法解析】，O2OA 日志表现为：
#      connect connection error, address: http://host.docker.internal:8095/...,
#      because: host.docker.internal.        ← UnknownHostException
#    因此 node 必须用【IP 直连】。Docker Desktop(Windows) 上宿主网关恒为
#    192.168.65.254，已实测该地址从 o2oa-server 网络命名空间可直接访问本服务。
#    可用 mail.json 的 "node" 覆盖（如 Linux 原生 Docker 上用 172.17.0.1）。
#    ★ 容器化部署（推荐）下本服务与 o2oa-server 同在 o2oa-net 网络，
#      node 应设为容器名 o2oa-mailservice:8095 —— 由 compose 的
#      O2OA_MAIL_NODE 环境变量注入，代码默认值仅作宿主直跑的兜底。
NODE_FOR_O2OA = "192.168.65.254"

# 心跳间隔（秒）。★★ 实测：O2OA 的 RefreshApplicationsEvent 约每 30s 扫一次，
# 按 reportDate 超时把"僵尸应用"踢出服务表（日志：cluster dropped application: ...）。
# 因此必须【无条件】定期重注册刷新 reportDate —— 仅判断"条目是否存在"不够，
# 条目在但 reportDate 过期照样被 drop。取 20s 留足余量。
KEEPALIVE_INTERVAL = 20

REPORT_TYPE = {"type": "success"}

LOG_LINES = deque(maxlen=400)
CODES = {}          # mobile -> {"code":str, "expire":ts, "tries":int, "sentAt":ts}
SEND_GUARD = {}     # mobile -> last send ts（频率限制）
LOCK = threading.RLock()

TOKEN_CACHE = {"token": None, "at": 0.0}


def log(*parts):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), " ".join(str(p) for p in parts))
    LOG_LINES.append(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def write_pid():
    """把自己的 PID 写到 mailservice.pid（看门狗据此判活）。"""
    try:
        with open(PID_PATH, "w", encoding="ascii") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


def clear_pid():
    """正常退出时清掉 PID 文件。"""
    try:
        if os.path.exists(PID_PATH):
            os.remove(PID_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "enabled": True,
    "o2oaBase": "http://localhost:9090",
    "o2oaAdmin": "admin",
    "o2oaPassword": "o2oaadmin2026",
    "port": DEFAULT_PORT,
    # 容器访问本服务的地址（留空则用 NODE_FOR_O2OA 默认 IP）。
    # 不要填域名：容器内 DNS 被断云策略掐断，域名一律解析失败。
    "node": "",

    # SMTP
    "senderMail": "o2oa@ccia.xin",
    "senderName": "o2oa_admin",
    "smtpHost": "smtp.ym.163.com",
    "smtpPort": 465,
    "smtpUser": "o2oa@ccia.xin",
    "smtpPassword": "",
    "timeout": 15,
    "ssl": True,
    "starttls": False,

    # 行为
    "codeLength": 6,
    "codeTtlMinutes": 5,
    "resendSeconds": 60,
    "redirectTo": "",          # 非空时所有验证码邮件改投到该邮箱（无真实邮箱环境的联调开关）
    "showCodeInLog": True,     # 记录验证码到服务日志 / /api/log（本地无邮件时靠它取码）

    # 邮件模板（支持 {code} {name} {mobile} {ttl} {app} 占位）
    "templates": {
        "code": {
            "subject": "【中国复合材料工业协会】登录验证码",
            "body": "{name}，您好：\n\n您正在登录「{app}」，验证码为：\n\n    {code}\n\n"
                    "验证码 {ttl} 分钟内有效，请勿泄露给他人。\n\n如非本人操作，请忽略本邮件。"
        },
        "reset": {
            "subject": "【中国复合材料工业协会】密码重置验证码",
            "body": "{name}，您好：\n\n您正在重置「{app}」的登录密码，验证码为：\n\n    {code}\n\n"
                    "验证码 {ttl} 分钟内有效。如非本人操作，请立即联系系统管理员。"
        },
        "invite": {
            "subject": "【中国复合材料工业协会】账号开通通知",
            "body": "{name}，您好：\n\n您的「{app}」账号已开通，登录账号为 {mobile}。\n"
                    "首次登录请按提示修改密码。"
        },
    },
}

_config_cache = {"data": None, "mtime": 0.0}


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 环境变量覆盖层 —— 容器化部署的「配置即代码」入口
#
# 优先级： DEFAULT_CONFIG  <  O2OA_MAIL_* 环境变量  <  mail.json（运行时文件）
#
#   为什么文件 > 环境变量：
#     界面「系统设置 → 系统邮箱」保存时写的是 mail.json。若环境变量优先级更高，
#     用户在界面上填的授权码会被静默忽略 —— 那是极难排查的坑。故显式文件优先，
#     环境变量只承担「首次自举」与「部署期声明」（镜像里不带 mail.json 时生效）。
#
#   环境相关的地址走环境变量（换环境只改 docker-compose.yml，代码零改动）：
#     o2oaBase 容器内是 http://o2oa-server:9090（服务名解析）
#     node     容器内是 o2oa-mailservice:8095 （容器名，配合 o2oa 的 extra_hosts）
# ---------------------------------------------------------------------------
ENV_MAP = {
    # —— 部署拓扑（随环境变化，必须由部署描述声明）——
    "O2OA_MAIL_ENABLED":       ("enabled", "bool"),
    "O2OA_MAIL_O2OA_BASE":     ("o2oaBase", "str"),
    "O2OA_MAIL_NODE":          ("node", "str"),
    "O2OA_MAIL_PORT":          ("port", "int"),
    # —— 凭据 / 渠道（可选，便于纯环境变量部署；未设则用 mail.json）——
    "O2OA_MAIL_O2OA_ADMIN":    ("o2oaAdmin", "str"),
    "O2OA_MAIL_O2OA_PASSWORD": ("o2oaPassword", "str"),
    "O2OA_MAIL_SMTP_HOST":     ("smtpHost", "str"),
    "O2OA_MAIL_SMTP_PORT":     ("smtpPort", "int"),
    "O2OA_MAIL_SMTP_USER":     ("smtpUser", "str"),
    "O2OA_MAIL_SMTP_PASSWORD": ("smtpPassword", "str"),
    "O2OA_MAIL_SENDER_MAIL":   ("senderMail", "str"),
    "O2OA_MAIL_SENDER_NAME":   ("senderName", "str"),
    "O2OA_MAIL_REDIRECT_TO":   ("redirectTo", "str"),
    "O2OA_MAIL_SHOW_CODE":     ("showCodeInLog", "bool"),
}


def _coerce(raw, kind):
    """环境变量字符串 -> 目标类型；无法转换返回 None（等同未设置）。"""
    if kind == "int":
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return str(raw)


def env_override():
    """收集当前环境变量覆盖项。"""
    out = {}
    for env_key, (cfg_key, kind) in ENV_MAP.items():
        if env_key in os.environ:
            val = _coerce(os.environ[env_key], kind)
            if val is not None:
                out[cfg_key] = val
    return out


def _env_signature():
    """环境变量指纹：用于缓存失效判断（env 变化时无需重启也能感知）。"""
    return tuple(sorted((k, os.environ.get(k, "")) for k in ENV_MAP))


def load_config(force=False):
    with LOCK:
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            mtime = 0.0
        sig = (mtime, _env_signature())
        if not force and _config_cache["data"] is not None and sig == _config_cache.get("sig"):
            return _config_cache["data"]
        raw = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
            except Exception as exc:
                log("配置读取失败，使用默认值：", exc)
        # 顺序即优先级：默认值 < 配置文件 < 环境变量（部署描述 > 运行期文件）
        cfg = _deep_merge(_deep_merge(DEFAULT_CONFIG, raw), env_override())
        _config_cache["data"] = cfg
        _config_cache["mtime"] = mtime
        _config_cache["sig"] = sig
        return cfg


def config_source():
    """各配置项的有效来源，供 /api/status 自证（排查「界面改了不生效」用）。"""
    env_keys = set(env_override())
    file_keys = set()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                file_keys = set(json.load(fh))
        except Exception:
            pass
    src = {}
    for k in DEFAULT_CONFIG:
        src[k] = "file" if k in file_keys else ("env" if k in env_keys else "default")
    return src


def save_config(patch):
    """把 patch 合并写入 mail.json（仅保存用户可改项，避免把默认值全部固化）。"""
    with LOCK:
        raw = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
            except Exception:
                raw = {}
        raw = _deep_merge(raw, patch or {})
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
    load_config(force=True)
    return load_config()


# ---------------------------------------------------------------------------
# 验证码存储
# ---------------------------------------------------------------------------
def _persist_codes():
    try:
        with open(CODES_PATH, "w", encoding="utf-8") as fh:
            json.dump(CODES, fh, ensure_ascii=False)
    except Exception:
        pass


def _load_codes():
    if not os.path.exists(CODES_PATH):
        return
    try:
        with open(CODES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        now = time.time()
        for k, v in (data or {}).items():
            if isinstance(v, dict) and v.get("expire", 0) > now:
                CODES[k] = v
    except Exception:
        pass


def _gc_codes():
    now = time.time()
    for k in [k for k, v in CODES.items() if v.get("expire", 0) <= now]:
        CODES.pop(k, None)


def make_code(n):
    return "".join(random.choice("0123456789") for _ in range(int(n or 6)))


# ---------------------------------------------------------------------------
# O2OA 客户端（服务端到服务端）
# ---------------------------------------------------------------------------
def _http(method, url, body=None, token=None, timeout=20):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["x-token"] = token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), resp.headers
            except Exception:
                return resp.status, raw, resp.headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw), exc.headers
        except Exception:
            return exc.code, raw, exc.headers
    except Exception as exc:
        return -1, {"_err": str(exc)}, {}


def o2oa_login(force=False):
    cfg = load_config()
    base = cfg["o2oaBase"].rstrip("/")
    with LOCK:
        if not force and TOKEN_CACHE["token"] and time.time() - TOKEN_CACHE["at"] < 600:
            return TOKEN_CACHE["token"]
    st, data, hdr = _http("POST", base + "/x_organization_assemble_authentication/jaxrs/authentication",
                          {"credential": cfg["o2oaAdmin"], "password": cfg["o2oaPassword"]})
    token = (hdr.get("x-token") if hdr else None) or None
    if not token and isinstance(data, dict):
        token = ((data.get("data") or {}).get("token")) if isinstance(data.get("data"), dict) else None
    if not token:
        raise RuntimeError("O2OA 管理员登录失败：%s %s" % (st, str(data)[:200]))
    with LOCK:
        TOKEN_CACHE["token"] = token
        TOKEN_CACHE["at"] = time.time()
    return token


def o2oa_call(method, path, body=None):
    cfg = load_config()
    base = cfg["o2oaBase"].rstrip("/")
    token = o2oa_login()
    st, data, _ = _http(method, base + path, body, token)
    if st == 401:
        token = o2oa_login(force=True)
        st, data, _ = _http(method, base + path, body, token)
    return st, data


def o2oa_now():
    """取 O2OA 服务器时间（注册接口要求时间差 <30s）。"""
    st, data = o2oa_call("GET", "/x_program_center/jaxrs/config/list")
    if isinstance(data, dict):
        t = (data.get("data") or {}).get("time")
        if t:
            return t
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_person_by_mobile(mobile):
    """手机号 -> {name, mail, unique, distinguishedName}；找不到返回 None。"""
    if not mobile:
        return None
    st, data = o2oa_call("PUT", "/x_organization_assemble_control/jaxrs/person/list/like", {"key": mobile})
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    for p in rows:
        if str(p.get("mobile") or "") == str(mobile):
            return p
    return rows[0] if rows else None


def resolve_node():
    """容器访问本服务的地址：配置优先，否则用默认 IP（禁域名解析，见 NODE_FOR_O2OA 注释）。"""
    try:
        node = (load_config().get("node") or "").strip()
    except Exception:
        node = ""
    return node or NODE_FOR_O2OA


def register_application():
    """把本服务注册进 O2OA 服务表（findApplicationName 依赖它）。"""
    cfg = load_config()
    port = int(cfg.get("port") or DEFAULT_PORT)
    node = resolve_node()
    now = o2oa_now()
    app = {
        "className": APP_CLASS_NAME,
        "name": APP_TITLE,
        "node": node,
        "contextPath": CTX_PATH,
        "port": port,
        "sslEnable": False,
        "proxyHost": "",
        "proxyPort": port,
        "reportDate": now,
        "scheduleRequestList": [],
        "scheduleLocalRequestList": [],
    }
    body = {"value": json.dumps([app], ensure_ascii=False), "node": "127.0.0.1", "serverTime": now}
    st, data = o2oa_call("PUT", "/x_program_center/jaxrs/center/regist/applications", body)
    ok = isinstance(data, dict) and (data.get("data") or {}).get("value") is True
    if ok:
        log("已注册到 O2OA：%s -> %s:%s%s" % (APP_CLASS_NAME, node, port, CTX_PATH))
    else:
        log("注册失败：", st, str(data)[:200])
    return ok


def app_registered():
    st, data = o2oa_call("GET", "/x_program_center/jaxrs/center/applications")
    apps = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(apps, dict):
        return False
    return any(k.endswith(".x_sms_assemble_control") for k in apps)


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------
def send_mail(to_mail, subject, body):
    """返回 (ok, message)。"""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return False, "邮件通道已在设置中关闭"
    host = (cfg.get("smtpHost") or "").strip()
    if not host:
        return False, "未配置 SMTP 主机"
    sender = (cfg.get("senderMail") or cfg.get("smtpUser") or "").strip()
    if not sender:
        return False, "未配置发件人邮箱"
    target = (cfg.get("redirectTo") or "").strip() or to_mail
    if not target:
        return False, "收件人为空（该用户未登记邮箱）"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg.get("senderName") or "O2OA", "utf-8")), sender))
    msg["To"] = target

    port = int(cfg.get("smtpPort") or 465)
    timeout = int(cfg.get("timeout") or 15)
    password = cfg.get("smtpPassword") or ""
    try:
        if cfg.get("ssl", True):
            ctx = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            if cfg.get("starttls"):
                server.starttls(context=ssl.create_default_context())
        try:
            user = (cfg.get("smtpUser") or "").strip()
            if user:
                server.login(user, password)
            server.sendmail(sender, [target], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
        note = "" if target == to_mail else "（重定向自 %s）" % to_mail
        return True, "已发送至 %s%s" % (target, note)
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def render_template(kind, ctx):
    cfg = load_config()
    tpl = ((cfg.get("templates") or {}).get(kind)
           or (cfg.get("templates") or {}).get("code")
           or DEFAULT_CONFIG["templates"]["code"])
    subject, body = tpl.get("subject", ""), tpl.get("body", "")
    for k, v in (ctx or {}).items():
        subject = subject.replace("{%s}" % k, str(v))
        body = body.replace("{%s}" % k, str(v))
    return subject, body


# ---------------------------------------------------------------------------
# 业务：发码 / 校验
# ---------------------------------------------------------------------------
def issue_code(mobile, kind="code"):
    """生成验证码并投递到该手机号对应用户的注册邮箱。返回 (ok, message, code)。"""
    cfg = load_config()
    now = time.time()
    with LOCK:
        last = SEND_GUARD.get(mobile, 0)
        gap = int(cfg.get("resendSeconds") or 60)
        if now - last < gap:
            return False, "发送过于频繁，请 %d 秒后重试" % int(gap - (now - last)), None
        SEND_GUARD[mobile] = now

    code = make_code(cfg.get("codeLength") or 6)
    ttl = int(cfg.get("codeTtlMinutes") or 5)
    with LOCK:
        CODES[mobile] = {"code": code, "expire": now + ttl * 60, "tries": 0, "sentAt": now}
        _gc_codes()
        _persist_codes()

    person = None
    try:
        person = find_person_by_mobile(mobile)
    except Exception as exc:
        log("查人失败 mobile=%s：%s" % (mobile, exc))
    name = (person or {}).get("name") or "用户"
    mail = (person or {}).get("mail") or ""
    app_title = load_config().get("appTitle") or "中国复合材料工业协会内部管理系统"

    ctx = {"code": code, "name": name, "mobile": mobile, "ttl": ttl, "app": app_title}
    subject, body = render_template(kind, ctx)

    if cfg.get("showCodeInLog", True):
        log("生成验证码 mobile=%s user=%s code=%s (未投递前)" % (mobile, name, code))

    if not mail and not (cfg.get("redirectTo") or "").strip():
        log("用户 %s(%s) 未登记邮箱，验证码无法投递" % (name, mobile))
        return False, "该账号未登记邮箱，请联系管理员", code

    ok, note = send_mail(mail, subject, body)
    log("投递 mobile=%s mail=%s ok=%s %s" % (mobile, mail or "(重定向)", ok, note))
    return ok, note if ok else ("邮件发送失败：" + note), code


def verify_code(mobile, answer):
    cfg = load_config()
    now = time.time()
    with LOCK:
        item = CODES.get(mobile)
        if not item:
            return False, "验证码不存在或已失效"
        if item.get("expire", 0) <= now:
            CODES.pop(mobile, None)
            _persist_codes()
            return False, "验证码已过期"
        if str(item.get("code")) != str(answer or "").strip():
            item["tries"] = int(item.get("tries") or 0) + 1
            if item["tries"] >= 8:
                CODES.pop(mobile, None)
                _persist_codes()
                return False, "错误次数过多，请重新获取"
            return False, "验证码不正确"
        CODES.pop(mobile, None)          # 一次性
        _persist_codes()
        return True, "ok"


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------
def jresp(value):
    return json.dumps({"value": bool(value)}, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "O2OAMailService/1.0"
    protocol_version = "HTTP/1.1"

    # ---- 基础工具 ----
    def log_message(self, fmt, *args):
        pass  # 用自有日志

    def _send(self, code, payload, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = str(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    # ---- 路由 ----
    def _route(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            # ===== O2OA 契约 =====
            m = re.match(r"^" + re.escape(CTX_PATH) + r"/jaxrs/sms/send/code/mobile/([^/]+)/token/([^/]+)$", path)
            if m:
                mobile = m.group(1)
                ok, note, code = issue_code(mobile, "code")
                log("O2OA 请求发码 mobile=%s -> %s (%s)" % (mobile, ok, note))
                return self._send(200, {"value": bool(ok)}, extra={"X-Code-Note": urllib.parse.quote(note or "")})

            m = re.match(r"^" + re.escape(CTX_PATH) + r"/jaxrs/sms/validate/mobile/([^/]+)/answer/([^/]+)/token/([^/]+)$", path)
            if m:
                ok, note = verify_code(m.group(1), m.group(2))
                log("O2OA 请求校验 mobile=%s answer=%s -> %s (%s)" % (m.group(1), m.group(2), ok, note))
                return self._send(200, {"value": bool(ok)})

            # 兼容：某些版本可能用 reset 前缀
            m = re.match(r"^" + re.escape(CTX_PATH) + r"/jaxrs/sms/([a-zA-Z]+)/mobile/([^/]+)/token/([^/]+)$", path)
            if m:
                act, mobile = m.group(1), m.group(2)
                if act == "sendcode" or act == "code":
                    ok, note, _ = issue_code(mobile, "reset")
                    return self._send(200, {"value": bool(ok)})

            # eslint 友好
            if path == CTX_PATH + "/jaxrs/sms/ping":
                return self._send(200, {"value": True})

            # ===== 管理 API =====
            if path == "/api/health":
                cfg = load_config()
                return self._send(200, {"ok": True, "service": APP_TITLE, "port": int(cfg.get("port") or DEFAULT_PORT),
                                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

            if path == "/api/status":
                return self._send(200, self.status_payload())

            if path == "/api/config":
                if method == "GET":
                    cfg = dict(load_config())
                    cfg["smtpPassword"] = "******" if cfg.get("smtpPassword") else ""
                    return self._send(200, {"ok": True, "config": cfg})
                if method == "PUT":
                    patch = self._read_json()
                    if patch.get("smtpPassword") == "******":
                        patch.pop("smtpPassword", None)
                    if not patch.get("smtpPassword"):
                        patch.pop("smtpPassword", None)
                    cfg = save_config(patch)
                    log("配置已更新：", ", ".join(sorted(patch.keys())))
                    out = dict(cfg)
                    out["smtpPassword"] = "******" if out.get("smtpPassword") else ""
                    return self._send(200, {"ok": True, "config": out})
                return self._send(405, {"ok": False, "message": "method not allowed"})

            if path == "/api/test/mail" and method == "POST":
                body = self._read_json()
                to = (body.get("to") or "").strip()
                cfg = load_config()
                if not to:
                    to = (cfg.get("senderMail") or cfg.get("smtpUser") or "").strip()
                subject = body.get("subject") or "【测试】O2OA 系统邮件配置自检"
                text = body.get("body") or (
                    "这是一封来自 O2OA 本地邮件服务（端口 %s）的测试邮件。\n"
                    "收到即表示 SMTP 配置可用。\n\nSMTP: %s:%s\n发送时间: %s"
                    % (cfg.get("port"), cfg.get("smtpHost"), cfg.get("smtpPort"),
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                ok, note = send_mail(to, subject, text)
                log("测试邮件 -> %s ok=%s %s" % (to, ok, note))
                return self._send(200, {"ok": ok, "message": note})

            if path == "/api/test/code" and method == "POST":
                body = self._read_json()
                mobile = (body.get("mobile") or "").strip()
                ok, note, code = issue_code(mobile, body.get("kind") or "code")
                return self._send(200, {"ok": ok, "message": note, "code": code if ok else None})

            if path == "/api/log":
                n = int((query.get("n") or ["80"])[0])
                return self._send(200, {"ok": True, "lines": list(LOG_LINES)[-n:]})

            if path == "/api/codes":
                _gc_codes()
                rows = [{"mobile": k, "code": v.get("code"),
                         "expireIn": max(0, int(v.get("expire", 0) - time.time()))}
                        for k, v in CODES.items()]
                return self._send(200, {"ok": True, "codes": rows})

            if path == "/api/register" and method == "POST":
                ok = register_application()
                return self._send(200, {"ok": ok, "registered": app_registered()})

            if path == "/api/revoke" and method == "POST":
                ok = revoke_application()
                return self._send(200, {"ok": ok})

            return self._send(404, {"ok": False, "message": "not found", "path": path})
        except Exception as exc:
            log("请求处理异常：", path, exc)
            log(traceback.format_exc()[-600:])
            return self._send(500, {"ok": False, "message": "%s: %s" % (type(exc).__name__, exc)})

    # ---- 状态 ----
    def status_payload(self):
        cfg = load_config()
        registered = False
        person = None
        try:
            registered = app_registered()
        except Exception as exc:
            log("查询注册状态失败：", exc)
        with LOCK:
            pend = [{"mobile": k, "expireIn": max(0, int(v.get("expire", 0) - time.time()))}
                    for k, v in CODES.items()]
        return {
            "ok": True,
            "service": APP_TITLE,
            "appName": APP_NAME,
            "className": APP_CLASS_NAME,
            "contextPath": CTX_PATH,
            "node": resolve_node(),
            "port": int(cfg.get("port") or DEFAULT_PORT),
            "registered": registered,
            "enabled": bool(cfg.get("enabled")),
            "smtp": {
                "host": cfg.get("smtpHost"), "port": cfg.get("smtpPort"),
                "user": cfg.get("smtpUser"), "sender": cfg.get("senderMail"),
                "ssl": bool(cfg.get("ssl")), "passwordSet": bool(cfg.get("smtpPassword")),
            },
            "redirectTo": cfg.get("redirectTo") or "",
            "pendingCodes": pend,
            "listen": "%s:%s" % (HOST_BIND, int(cfg.get("port") or DEFAULT_PORT)),
            "since": START_TIME,
        }


HOST_BIND = "0.0.0.0"
START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
_HTTPD = {"srv": None}


def revoke_application():
    """从注册表移除本服务（恢复 O2OA 原生行为）。"""
    try:
        o2oa_call("PUT", "/x_program_center/jaxrs/center/regist/applications",
                  {"value": "[]", "node": "127.0.0.1", "serverTime": o2oa_now()})
        log("已请求移除注册（下次节点心跳后会自然刷新）")
        return True
    except Exception as exc:
        log("移除注册失败：", exc)
        return False


def _keepalive_loop():
    """周期重注册：刷新 reportDate，防止被 center 的 RefreshApplicationsEvent 清理。

    注意：必须【无条件】定期重注册。O2OA 按 reportDate 判超时，条目在但
    reportDate 过期同样会被 drop（实测 27s 未续报即被踢），故不能只在"条目不存在"时补。
    """
    time.sleep(3)
    while True:
        try:
            if load_config().get("enabled", True):
                if not app_registered():
                    log("注册条目不在服务表中，重新注册…")
                register_application()
        except Exception as exc:
            log("心跳注册异常：", exc)
        time.sleep(KEEPALIVE_INTERVAL)


def main():
    cfg = load_config()
    _load_codes()
    port = int(cfg.get("port") or DEFAULT_PORT)

    # ★ 单例保护：端口被占说明已有实例（可能是看门狗拉起的那个）。
    #   直接 exit(0) 而不是抛栈 —— 双击两次 bat / 自启+手动 同时发生时不产生崩溃噪音。
    try:
        httpd = ThreadingHTTPServer((HOST_BIND, port), Handler)
    except OSError as exc:
        log("启动中止：%s:%s 已被占用（%s）—— 已有实例在运行，本进程退出。" % (HOST_BIND, port, exc))
        return 1
    httpd.daemon_threads = True
    _HTTPD["srv"] = httpd
    write_pid()

    log("=" * 64)
    log("O2OA 邮件验证码服务启动：监听 %s:%s (pid %s)" % (HOST_BIND, port, os.getpid()))
    log("  契约：GET %s/jaxrs/sms/send/code/mobile/{mobile}/token/{token}" % CTX_PATH)
    log("        GET %s/jaxrs/sms/validate/mobile/{mobile}/answer/{answer}/token/{token}" % CTX_PATH)
    log("  作为 %s 注册到 O2OA（node=%s）" % (APP_CLASS_NAME, resolve_node()))
    try:
        if register_application():
            log("注册成功；O2OA 侧还需 config/custom_sms.json 存在 且 captchaLogin/codeLogin 视需要开启")
    except Exception as exc:
        log("首次注册失败（服务仍可用，将自动重试）：", exc)
    threading.Thread(target=_keepalive_loop, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("收到中断，退出")
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
        clear_pid()
    return 0


if __name__ == "__main__":
    main()
