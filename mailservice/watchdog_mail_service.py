# -*- coding: utf-8 -*-
"""
watchdog_mail_service.py — O2OA 邮件验证码服务（8095）常驻看门狗

与 D:\\O2OA\\gateway\\watchdog_ai_stack.py 同构：PID 锁 + 脱离式启动 + 周期探活自愈。

职责：
  - 首轮：探活 8095，不在就拉起 o2oa_mail_service.py（脱离式，无控制台窗口）
  - 之后每 WATCH_INTERVAL 秒用 HTTP /api/health 探活；掉线即重启
  - 「端口被占但健康检查不通」= 僵死进程 -> 先释放端口再拉
  - 看门狗自身 PID 锁：同一时刻只有一个看门狗

不做什么：
  - 不碰 O2OA 容器、不改注册表、不需要管理员权限
  - 不动 iptables（断网隔离由 o2oa_netlock.sh 负责）

用法：
  python watchdog_mail_service.py          # 前台跑（调试用，Ctrl+C 退出）
  pythonw watchdog_mail_service.py         # 后台跑（启动文件夹 VBS 即用此方式）

日志：mailservice\\watchdog.log（看门狗自身） / mailservice\\mailservice.log（服务）
"""
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = os.path.join(HERE, "o2oa_mail_service.py")
SERVICE_LOG = os.path.join(HERE, "mailservice.log")
WD_LOG = os.path.join(HERE, "watchdog.log")
SERVICE_PID = os.path.join(HERE, "mailservice.pid")
WD_PID = os.path.join(HERE, "watchdog.pid")

HOST = "127.0.0.1"
PORT = 8095
HEALTH_URL = "http://127.0.0.1:%d/api/health" % PORT

WATCH_INTERVAL = 30          # 探活间隔（秒）
READY_TIMEOUT = 30           # 拉起后等待就绪的上限（秒）

# 子进程加固：CREATE_NO_WINDOW 防 taskkill/netstat 弹窗；
# encoding=utf-8 + errors=replace 防 GBK 输出触发 UnicodeDecodeError
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
_RUN_KW = dict(capture_output=True, text=True, encoding="utf-8",
               errors="replace", creationflags=CREATE_NO_WINDOW)

# 清空代理环境变量：宿主系统代理会劫持 127.0.0.1 探活（本机实测 shell 代理 52068）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(WD_LOG, "ab") as fh:
            fh.write((line + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# PID 工具
# ---------------------------------------------------------------------------
def save_pid(path, pid):
    try:
        with open(path, "w", encoding="ascii") as fh:
            fh.write(str(pid))
    except OSError:
        pass


def load_pid(path):
    try:
        with open(path) as fh:
            return int((fh.read() or "").strip())
    except (OSError, ValueError):
        return 0


def pid_alive(pid):
    if not pid or pid <= 0:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             timeout=15, **_RUN_KW)
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 探活 / 端口
# ---------------------------------------------------------------------------
def health_ok(timeout=5):
    """HTTP 探活（比只看端口准：能发现"端口在但服务卡死"）。

    ★ 必须显式清空代理 —— urllib 默认读 Windows IE 代理设置。
    """
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(HEALTH_URL, timeout=timeout) as resp:
            return int(getattr(resp, "status", resp.getcode())) == 200
    except Exception:
        return False


def port_listening():
    """只看端口是否有 LISTENING（不判健康）。"""
    try:
        out = subprocess.run(["netstat", "-ano"], timeout=15, **_RUN_KW)
        for line in (out.stdout or "").splitlines():
            if (":%d " % PORT) in line and "LISTENING" in line:
                return True
    except Exception:
        pass
    return False


def free_port():
    """杀掉占用 PORT 的僵死进程（仅在健康检查失败后调用）。"""
    killed = []
    try:
        out = subprocess.run(["netstat", "-ano"], timeout=15, **_RUN_KW)
        for line in (out.stdout or "").splitlines():
            if (":%d " % PORT) in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                                   timeout=15, **_RUN_KW)
                    killed.append(pid)
    except Exception:
        pass
    if killed:
        log("已释放僵死进程 pid=%s" % ",".join(killed))
        time.sleep(2)
    return bool(killed)


# ---------------------------------------------------------------------------
# 启动服务
# ---------------------------------------------------------------------------
def find_python():
    """按优先级挑选解释器：venv（与 AI 栈 VBS 一致）-> 本进程 -> 系统 python。

    本服务只依赖标准库，任一 python3 均可。
    """
    cands = [
        r"C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe",
        sys.executable,
        r"C:\Users\meng_\.workbuddy\binaries\python\versions\3.13.12\python.exe",
        r"C:\Python314\python.exe",
        r"C:\Python313\python.exe",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return "python"


def wait_ready(secs=READY_TIMEOUT):
    deadline = time.time() + secs
    while time.time() < deadline:
        if health_ok():
            return True
        time.sleep(2)
    return False


def launch():
    """脱离式拉起服务（绝不弹窗、跟随看门狗生命周期之外独立存活）。

    ★ 不写 mailservice.pid：venv 的 python.exe 是重定向器，Popen 拿到的是
      重定向器的 pid 而非真实解释器 pid，写进去会造成竞态。
      PID 文件由服务自身用 os.getpid() 写入（唯一写入者）。
    """
    py = find_python()
    log("邮件验证码服务 :%d DOWN -> 拉起（%s）" % (PORT, py))
    # 清掉陈旧 PID 文件，避免下次读到时指向已退出的进程
    try:
        if os.path.exists(SERVICE_PID):
            os.remove(SERVICE_PID)
    except OSError:
        pass
    logf = open(SERVICE_LOG, "ab", buffering=0)
    try:
        p = subprocess.Popen(
            [py, SERVICE], cwd=HERE,
            stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW, close_fds=True,
        )
        log("  - started o2oa_mail_service.py (launcher pid %d，真实 pid 见 mailservice.pid)" % p.pid)
    except Exception as exc:  # noqa: BLE001
        log("  [ERROR] 启动失败：%s" % exc)
        return False
    finally:
        try:
            logf.close()
        except Exception:
            pass
    return wait_ready()


def cycle():
    if health_ok():
        return
    # 端口有人占但健康检查不通 = 僵死进程
    if port_listening():
        log("端口 %d 被占用但健康检查失败（僵死），先释放" % PORT)
        free_port()
    if not launch():
        log("[WARN] 本轮未能就绪，%ds 后重试" % WATCH_INTERVAL)


def watchdog_singleton():
    old = load_pid(WD_PID)
    if pid_alive(old) and old != os.getpid():
        log("已有看门狗在运行 (pid %d)，本进程退出" % old)
        return False
    save_pid(WD_PID, os.getpid())
    return True


def main():
    if not watchdog_singleton():
        return 0
    log("=" * 60)
    log("邮件验证码看门狗启动 (pid %d)：探活 %s 每 %ds，掉线即自愈" % (os.getpid(), HEALTH_URL, WATCH_INTERVAL))
    cycle()
    while True:
        time.sleep(WATCH_INTERVAL)
        try:
            cycle()
        except Exception as exc:  # noqa: BLE001
            log("探活轮异常（继续）：%s" % exc)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("看门狗收到中断，退出")
