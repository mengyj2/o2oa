# -*- coding: utf-8 -*-
"""
watchdog_ai_stack.py — O2OA AI 栈常驻看门狗（健壮性硬化版）

相对旧版「PID 锁版」的硬化点（2026-09-25 实战根治抖动）：
  1. 单例锁改用「内核级 socket 互斥端口(18800)」替代 pid 文件锁：
     bind 成功=本实例独占，bind 失败(端口已占)=已有实例直接退出。
     彻底消除旧版 pid 文件锁的 TOCTOU 竞态 —— 正是它导致双看门狗同时存活、
     互相 free_port 杀对方网关、18790 反复 DOWN->重启抖动的真凶。
  2. 端口归属感知（port_state）：每轮探活先判定端口状态
       - down    : 端口完全不通 -> 直接拉起
       - ours    : TCP 通 + 健康端点 200（网关带 token 复核）-> 本栈健康服务，
                   刷新陈旧 pid 文件，**绝不误杀**
       - foreign : TCP 通但健康复核失败（外部/孤儿进程占位，或刚拉起仍在加载）
     根除了「看门狗按陈旧 pid 判活 -> free_port 误杀健康孤儿 -> 反复抖动」的死循环。
  3. 启动期防抖（START_GUARD）：对某组件执行过 free/restart 后，N 秒内
     不再重复触发 kill/restart —— 给新拉起进程加载时间，避免一次空窗被反复重启。
  4. rerank 开关解耦：优先读 config.json 的 rerank_enable，命令行 --rerank 仍可用；
     rerank 为非必需组件，拉起失败不影响主链路（网关自动回退向量 top_k）。
  5. 不再在每轮/首轮无条件 free_port 网关；仅在 foreign 时精准释放，
     最大限度保活本栈健康服务。

用法：
  python watchdog_ai_stack.py            # chat+embed+网关+OCR（按 config 决定 rerank）
  python watchdog_ai_stack.py --rerank  # 强制额外 rerank
  python watchdog_ai_stack.py --noocr   # 不拉 OCR
"""
import ctypes
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 复用一次性启动器的组件定义与工具函数
sys.path.insert(0, HERE)
from start_ai_stack_detached import (  # noqa: E402
    comps, healthy, DETACHED, LLAMA_DIR,
)

TOKEN = "local-o2-agent-2026"
WATCH_INTERVAL = 30          # 探活间隔（秒）
START_GUARD = 25             # 对某组件执行过动作后，N 秒内不重复触发 kill/restart
LOG_PATH = os.path.join(HERE, "watchdog.log")
SINGLETON_PORT = 18800       # 内核级互斥锁端口（看门狗独占，进程退出自动释放）

# 子进程加固：CREATE_NO_WINDOW 防止 powershell/netstat/taskkill 弹出可见控制台窗口；
# encoding=utf-8 + errors=replace 防止 GBK 输出触发 UnicodeDecodeError（曾被当成探活异常）。
CREATE_NO_WINDOW = 0x08000000
_RUN_KW = dict(capture_output=True, text=True, encoding="utf-8",
               errors="replace", creationflags=CREATE_NO_WINDOW)

# 清空代理环境变量：本看门狗及其拉起的所有子进程（网关/OCR 等 httpx trust_env=True）
# 一律直连本机端口，宿主系统代理开关不再影响 AI 栈。
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "ab") as f:
            f.write((line + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def pid_file(name):
    return os.path.join(HERE, name + ".pid")


def save_pid(name, pid):
    try:
        with open(pid_file(name), "w") as f:
            f.write(str(pid))
    except OSError:
        pass


def load_pid(name):
    try:
        with open(pid_file(name)) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid):
    """Windows 安全存活检测：OpenProcess(仅查询权限) + GetExitCodeProcess。

    ★ 绝不可用 os.kill(pid, 0)：
      Windows 上 os.kill 对非 CTRL 信号走 TerminateProcess(pid, 0)，
      会把「正在检测的目标进程」直接杀掉。
    """
    if not pid:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    try:
        k32 = ctypes.windll.kernel32
    except AttributeError:
        return False
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def port_up(port, timeout=1.0):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def is_up(port, path, token):
    return healthy(f"http://127.0.0.1:{port}{path}", token)


# ---- 真实监听 PID（PowerShell，权威来源，绕开过时 pid 文件）----
def real_owner_pids(port):
    try:
        ps = (f"$ids=(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue)"
              ".OwningProcess | Sort-Object -Unique; $ids -join ' '")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             timeout=15, **_RUN_KW)
        return [int(x) for x in out.stdout.split() if x.strip().isdigit()]
    except Exception:
        return []


def port_state(port, path, token):
    """返回 (state, owners)。

    - down    : 端口完全不通
    - ours    : TCP 通 + 健康端点复核通过（本栈预期服务）
    - foreign : TCP 通但健康复核失败（外部/孤儿进程，或本栈进程正在加载）
    """
    if not port_up(port):
        return ("down", [])
    if is_up(port, path, token):
        return ("ours", real_owner_pids(port))
    return ("foreign", real_owner_pids(port))


def free_port(port):
    """强制释放端口：杀掉占用该端口的进程（Windows）。仅在 foreign/orphan 场景调用。"""
    killed = []
    try:
        ps = ("$ids=(Get-NetTCPConnection -LocalPort %d -ErrorAction SilentlyContinue)"
              ".OwningProcess | Sort-Object -Unique; "
              "foreach($id in $ids){ if($id){ Stop-Process -Id $id -Force "
              "-ErrorAction SilentlyContinue; Write-Host $id } }" % port)
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             timeout=20, **_RUN_KW)
        for tok in out.stdout.split():
            if tok.strip().isdigit():
                killed.append(tok.strip())
    except Exception:
        pass
    try:
        out = subprocess.run(["netstat", "-ano"], **_RUN_KW, timeout=15)
        for line in out.stdout.splitlines():
            if (":%d " % port) in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                                  timeout=10, **_RUN_KW)
                    killed.append(pid)
    except Exception:
        pass
    if killed:
        time.sleep(2)
    return bool(killed)


WATCHDOG_PID_FILE = os.path.join(HERE, "watchdog.pid")


def watchdog_singleton():
    """内核级互斥：bind 独占端口 18800。成功=本实例独占；失败=已有实例，退出。

    比 pid 文件锁更可靠：bind 是内核原子操作，不存在「两实例同时读到空 pid 文件」的
    TOCTOU 竞态。进程退出后端口由内核自动释放，下次 bind 立即成功。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", SINGLETON_PORT))
    except OSError:
        return None
    return s  # 持有该 socket 对象直到进程退出 = 持有锁


def cfg_bool(key, default=False):
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            return bool(json.load(f).get(key, default))
    except Exception:
        return default


def launch(name, port, cmd, logname, path, token, wait):
    """脱离式启动单个组件（带 PID 记录，绝不重复拉起）。返回是否就绪。"""
    if is_up(port, path, token):
        return True
    old = load_pid(name)
    if pid_alive(old):
        return wait_ready(name, port, path, wait, token)
    # 端口可能被非 pid 记录的进程（孤儿/外部）占用 -> 释放再拉，避免 bind 失败反复 WARN
    if port_up(port):
        log(f"{name}:{port} 端口被其他进程占用，释放后重建")
        free_port(port)
    log(f"{name}:{port} DOWN -> 重新拉起")
    logf = open(os.path.join(HERE, logname), "ab", buffering=0)
    cwd = LLAMA_DIR if name in ("chat", "embed", "rerank") else HERE
    try:
        p = subprocess.Popen(
            cmd, cwd=cwd, stdout=logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=DETACHED, close_fds=True,
        )
        save_pid(name, p.pid)
        log(f"  - started {name}:{port} (pid {p.pid}) -> {logname}")
    except Exception as e:  # noqa: BLE001
        log(f"  [ERROR] {name} 启动失败: {e}")
        return False
    return wait_ready(name, port, path, wait, token)


def wait_ready(name, port, path, secs, token=None):
    url = f"http://127.0.0.1:{port}{path}"
    deadline = time.time() + secs
    while time.time() < deadline:
        if healthy(url, token):
            log(f"  - {name} :{port} ready")
            return True
        time.sleep(3)
    log(f"  [WARN] {name} :{port} 在 {secs}s 内未就绪，下个周期重试")
    return False


def main():
    lock = watchdog_singleton()
    if lock is None:
        log("已有看门狗实例（互斥端口 18800 被占用），本实例退出（单例防双开互杀）")
        sys.exit(0)
    try:
        with open(WATCHDOG_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    rerank = "--rerank" in sys.argv or cfg_bool("rerank_enable", False)
    ocr = "--noocr" not in sys.argv and cfg_bool("ocr_enable", True)
    mode = "embed+网关" + ("+rerank" if rerank else "") + ("+OCR" if ocr else " (无OCR)")
    if cfg_bool("bionic_local_chat", False):
        mode = "chat+" + mode
    log(f"看门狗启动：{mode}（端口归属感知+互斥锁单例，探活间隔 {WATCH_INTERVAL}s）")

    last_action = {}  # name -> 上次执行 free/launch 的时间（防抖）

    def cycle():
        now = time.time()
        for name, port, cmd, logname, mandatory, path, wait in comps(rerank, ocr):
            tk = TOKEN if name == "gateway" else None
            state, owners = port_state(port, path, tk)
            if state == "ours":
                rp = owners[0] if owners else None
                if rp and rp != load_pid(name):
                    save_pid(name, rp)
                    log(f"{name}:{port} 健康，已校正 pid 为 {rp}（消除陈旧 pid 误判）")
                continue
            # down 或 foreign -> 需重建；先判防抖
            recent = name in last_action and (now - last_action[name]) < START_GUARD
            if state == "down":
                if recent:
                    log(f"{name}:{port} 防抖期内端口暂空，下一轮再拉起")
                    continue
                last_action[name] = now
                ok = launch(name, port, cmd, logname, path, tk, wait)
            else:  # foreign
                if recent:
                    # 刚动过，多半是刚拉起正在加载 -> 等待就绪，绝不误杀
                    wait_ready(name, port, path, wait, tk)
                    continue
                log(f"{name}:{port} 被外部/孤儿进程 {owners} 占用，释放后重建")
                free_port(port)
                last_action[name] = now
                ok = launch(name, port, cmd, logname, path, tk, wait)
            if not ok and mandatory:
                log(f"[ERROR] {name}:{port} 重启后仍未就绪，请检查 {logname}")

    cycle()  # 首轮拉起
    while True:
        time.sleep(WATCH_INTERVAL)
        cycle()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("看门狗收到中断，退出")
