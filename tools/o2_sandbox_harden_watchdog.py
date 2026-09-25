#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 服务端脚本沙箱硬化 · 看门狗（持续化守护进程）
====================================================

为什么需要它（背景）
--------------------
脚本沙箱反射越权（CVE 类沙箱逃逸）已通过两条代码级通道固化：
  ① Dockerfile 把合并版 patch/x_base_core_project.patched.jar 烤进镜像；
  ② patch/o2oa_rebuild_patches.sh 的【步骤 2b】在升级时自动重放硬化。
但运行态仍可能因以下原因漂移：
  · 有人手工 `docker cp` 覆盖 store/jars/x_base_core_project.jar 做回滚/调试；
  · 一次异常升级 / 运维操作重置了 jar；
  · 未来某次 `docker compose up` 拉到了未含硬化的旧镜像（分支没切对）。
这些 "./docker cp + restart" 动作不会触发升级脚本，于是硬化会静默丢失，
而 O2OA 侧毫无报错——这正是「声明式固化」补不到的盲区。

本看门狗以【声明式基线 + 周期巡检 + 自动重放】把硬化持续化：
  每 POLL_INTERVAL 秒：
    1. 把运行容器内 store/jars/x_base_core_project.jar 拉到本地临时文件；
    2. 用 zipfile 计算 GraalvmScriptingFactory.class 的 SHA-256，
       并检查 ScriptHostAccessPolicy.class 是否存在；
    3. 与代码级黄金副本 patch/x_base_core_project.patched.jar 比对：
         - 哈希一致 且 含策略类  → 健康，仅记心跳；
         - 不一致 / 缺策略类     → 判定漂移，自动从黄金副本重放：
           docker cp 黄金 jar → 容器 → docker restart → 重跑 o2oa_netlock.sh。

规避本机 ARM64/QEMU 已知坑（这是此前排查出的铁律）：
  · 不依赖 `docker exec`——本机重启后偶发 setns 失败
    （fork/exec /proc/self/fd/6: no such file or directory），exec 不可靠；
  · 全程用 `docker cp` 拉文件 + zipfile 算哈希，零 exec、零 JVM 依赖。

用法
----
  python tools/o2_sandbox_harden_watchdog.py              # 前台循环（Ctrl-C 退出）
  python tools/o2_sandbox_harden_watchdog.py --once       # 只校验一次（返回 0=健康 / 1=漂移，CI 用）
  python tools/o2_sandbox_harden_watchdog.py --interval=600   # 自定义轮询间隔（秒）
  python tools/o2_sandbox_harden_watchdog.py --install    # 注册为系统服务（Windows 计划任务 / Linux systemd），开机自启持续化

依赖：仅标准库（subprocess / zipfile / hashlib / tempfile / argparse）。
"""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# 配置（全部相对仓库根，保证随分支走、可复现）
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTAINER = "o2oa-server"
JAR_IN_CONTAINER = "/opt/o2server/store/jars/x_base_core_project.jar"
GOLD_JAR = os.path.join(REPO_ROOT, "patch", "x_base_core_project.patched.jar")
NETLOCK = os.path.join(REPO_ROOT, "o2oa_netlock.sh")

TARGET_CLASS = "com/x/base/core/project/scripting/GraalvmScriptingFactory.class"
POLICY_CLASS = "com/x/base/core/project/scripting/ScriptHostAccessPolicy.class"

POLL_INTERVAL = 300  # 秒
LOG_FILE = os.path.join(REPO_ROOT, "tools", "o2_sandbox_harden_watchdog.log")
STATE_FILE = os.path.join(REPO_ROOT, "tools", ".watchdog_state.json")

DRIFT_COUNT = 0  # 进程内累计漂移次数


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd, **kw):
    """跑子进程，返回 (rc, stdout, stderr)。失败不抛，交由调用方判断。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=kw.get("timeout", 120), shell=kw.get("shell", False))
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # docker 不在 PATH / 容器不存在等
        return 1, "", str(e)


def class_sha(jar_path: str, class_name: str):
    """从 jar 内取某 class 的 SHA-256；不存在返回 None。"""
    import zipfile
    try:
        with zipfile.ZipFile(jar_path) as z:
            return hashlib.sha256(z.read(class_name)).hexdigest()
    except KeyError:
        return None
    except Exception:
        return None


def jar_has_class(jar_path: str, class_name: str) -> bool:
    import zipfile
    try:
        with zipfile.ZipFile(jar_path) as z:
            return class_name in z.namelist()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 核心：校验 + 重放
# ---------------------------------------------------------------------------
def gold_valid() -> bool:
    if not os.path.isfile(GOLD_JAR):
        log(f"[FAIL] 黄金副本不存在：{GOLD_JAR}")
        return False
    if not jar_has_class(GOLD_JAR, POLICY_CLASS):
        log(f"[FAIL] 黄金副本未含 ScriptHostAccessPolicy（不是硬化版），拒绝用它重放：{GOLD_JAR}")
        return False
    return True


def check_hardening():
    """拉出 live jar，比对硬化签名。返回 (ok: bool, detail: str)。"""
    if not gold_valid():
        return False, "GOLD_INVALID"
    tmp = os.path.join(tempfile.gettempdir(), f"o2_live_jar_{os.getpid()}.jar")
    rc, out, err = run(["docker", "cp", f"{CONTAINER}:{JAR_IN_CONTAINER}", tmp])
    if rc != 0:
        return False, f"DOCKER_CP_FAIL rc={rc} err={err.strip()[:200]}"
    try:
        live_target = class_sha(tmp, TARGET_CLASS)
        live_policy = jar_has_class(tmp, POLICY_CLASS)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    if live_target is None:
        return False, "LIVE_JAR_MISSING_TARGET_CLASS"
    gold_target = class_sha(GOLD_JAR, TARGET_CLASS)
    if live_target == gold_target and live_policy:
        return True, "OK"
    return False, (f"DRIFT target_hash={live_target[:12]}.. != gold "
                   f"{gold_target[:12]}.. policy_present={live_policy}")


def reapply():
    """从黄金副本重放硬化并重启 + 重跑断网隔离。返回 detail。"""
    global DRIFT_COUNT
    if not gold_valid():
        return "SKIP_GOLD_INVALID"
    # 1) 覆盖 live jar
    rc, out, err = run(["docker", "cp", GOLD_JAR, f"{CONTAINER}:{JAR_IN_CONTAINER}"], timeout=180)
    if rc != 0:
        return f"CP_FAIL rc={rc} err={err.strip()[:200]}"
    log("[REAPPLY] 已用黄金副本覆盖运行容器 live jar")
    # 2) 重启容器使新 jar 生效
    rc, out, err = run(["docker", "restart", CONTAINER], timeout=180)
    if rc != 0:
        return f"RESTART_FAIL rc={rc} err={err.strip()[:200]}"
    log("[REAPPLY] 已重启容器")
    # 3) 重跑断网隔离（Docker 重启会丢 iptables，必须重锁）
    rc, out, err = run(["bash", NETLOCK], timeout=180, shell=False)
    if rc != 0:
        log(f"[WARN] netlock 返回非 0（rc={rc}），请人工确认网络隔离状态")
    else:
        log("[REAPPLY] 已重跑 o2oa_netlock.sh 恢复断网隔离")
    DRIFT_COUNT += 1
    return "REAPPLIED"


def write_state(ok: bool, detail: str):
    try:
        import json
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_check": datetime.now().isoformat(), "healthy": ok,
                       "detail": detail, "drift_total": DRIFT_COUNT}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 安装为系统服务（持续化关键）
# ---------------------------------------------------------------------------
def install_service(interval: int):
    py = sys.executable
    script = os.path.abspath(__file__)
    if sys.platform.startswith("win"):
        task = "O2OA_SandboxHardenWatchdog"
        # 用 schtasks 注册为「开机自启 / SYSTEM 账户」的持续进程。
        # 注意：/RU SYSTEM 需要以管理员身份运行本命令才会成功；失败请改用
        # run_sandbox_watchdog.bat 手动启动，或把 /RU 改为当前用户。
        tr = f'"{py}" "{script}" --interval={interval}'
        cmd = ["schtasks", "/Create", "/TN", task, "/TR", tr,
               "/SC", "ONSTART", "/RU", "SYSTEM", "/F"]
        rc, out, err = run(cmd)
        if rc == 0:
            log(f"[INSTALL] 已注册 Windows 计划任务 {task}（开机自启，持续化生效）")
        else:
            log(f"[INSTALL][FAIL] schtasks 注册失败 rc={rc} err={err.strip()[:200]}\n"
                f"          可改用管理员 PowerShell 执行，或手动运行 tools/run_sandbox_watchdog.bat")
        return rc == 0
    else:
        # Linux 主机：写 systemd unit 并尝试 enable（需 root）。
        unit = os.path.join(REPO_ROOT, "tools", "o2_sandbox_harden_watchdog.service")
        try:
            with open(unit, "w", encoding="utf-8") as f:
                f.write(
                    "[Unit]\n"
                    "Description=O2OA Script Sandbox Hardening Watchdog\n"
                    "After=docker.service\n\n"
                    "[Service]\n"
                    f"ExecStart={py} {script} --interval={interval}\n"
                    "Restart=always\n"
                    "User=root\n\n"
                    "[Install]\n"
                    "WantedBy=multi-user.target\n"
                )
            rc, out, err = run(["systemctl", "daemon-reload"])
            rc2, out2, err2 = run(["systemctl", "enable", "o2_sandbox_harden_watchdog.service"])
            log(f"[INSTALL] systemd unit 已写入并尝试 enable（daemon-reload rc={rc}, enable rc={rc2}）")
            return rc2 == 0
        except Exception as e:
            log(f"[INSTALL][FAIL] {e}")
            return False


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="O2OA 脚本沙箱硬化看门狗")
    ap.add_argument("--once", action="store_true", help="只校验一次（CI/手动）")
    ap.add_argument("--interval", type=int, default=POLL_INTERVAL, help="轮询间隔（秒）")
    ap.add_argument("--install", action="store_true", help="注册为系统服务（开机自启持续化）")
    args = ap.parse_args()

    if args.install:
        install_service(args.interval)
        return

    log(f"看门狗启动：容器={CONTAINER} 黄金副本={os.path.basename(GOLD_JAR)} 间隔={args.interval}s")

    if args.once:
        ok, detail = check_hardening()
        log(f"[CHECK] {'健康' if ok else '漂移'} -> {detail}")
        write_state(ok, detail)
        sys.exit(0 if ok else 1)

    # 循环持续化
    while True:
        try:
            ok, detail = check_hardening()
            if ok:
                log(f"[HEALTHY] {detail}")
            else:
                log(f"[DRIFT] 检测到硬化漂移：{detail} -> 触发自动重放")
                res = reapply()
                log(f"[REAPPLY] 结果：{res}")
                # 重放后立刻复检，确认已恢复
                ok2, detail2 = check_hardening()
                log(f"[RECHECK] {'已恢复' if ok2 else '仍未恢复！'} -> {detail2}")
                write_state(ok2, detail2)
                if not ok2:
                    log("[ALERT] 重放后仍未恢复，请人工介入（可能黄金副本或镜像有问题）")
            write_state(ok, detail)
        except Exception as e:
            log(f"[ERROR] 巡检异常：{e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
