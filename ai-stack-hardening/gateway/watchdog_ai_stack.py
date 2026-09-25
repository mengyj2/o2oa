# -*- coding: utf-8 -*-
"""
watchdog_ai_stack.py — O2OA AI 栈常驻看门狗（稳健版，带 PID 锁防双启动）

职责：
  - 首次运行：逐组件拉起 chat+embed+网关（可选 +rerank +OCR），每个等真实 HTTP 健康再拉下一个
  - 之后每 WATCH_INTERVAL 秒探活；任一「必需」组件掉线，立即脱离式重启
  - PID 锁文件（gateway/<name>.pid）保证「同一组件同一时刻只有一个进程」，彻底杜绝双启动抢端口

为什么需要 PID 锁：
  旧版只用 port_up() 判活，组件从 fork 到真正监听有数秒延迟，探活轮询会误判 DOWN 并重复拉起，
  多个同名进程抢同一端口 -> 互相拖崩 -> 再被反复重启 -> 整栈团灭。本版用 pid 文件 + 进程存活校验，
  只在「端口 DOWN 且旧进程已死」时才重启，绝不重复拉起。

用法：
  python watchdog_ai_stack.py            # chat+embed+网关+OCR
  python watchdog_ai_stack.py --rerank  # 额外 rerank
  python watchdog_ai_stack.py --noocr   # 不拉 OCR
"""
import ctypes
import os
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
START_GUARD = 10             # 启动后多少秒内不重复尝试该组件（避免抖动）
LOG_PATH = os.path.join(HERE, "watchdog.log")

# 子进程加固：CREATE_NO_WINDOW 防止 powershell/netstat/taskkill 弹出可见控制台窗口；
# encoding=utf-8 + errors=replace 防止 GBK 输出触发 UnicodeDecodeError
# （0xbb 解码崩溃曾被当成探活异常，参与 DOWN 误判，见 watchdog_stdout.log）。
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
      会把「正在检测的目标进程」直接杀掉——组件加载中端口未就绪时，
      看门狗检测旧 pid 恰好触发误杀，再等 60s、报未就绪、下轮重启，
      这就是 2026-09-21 网关反复 DOWN->重启抖动的真凶。
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


def is_up(port, path, token):
    return healthy(f"http://127.0.0.1:{port}{path}", token)


WATCHDOG_PID_FILE = os.path.join(HERE, "watchdog.pid")


def watchdog_singleton():
    """看门狗单例锁：已有存活的看门狗则本实例直接退出。

    为什么需要：开机自启 VBS 与手动双击 bat 可能同时各起一个看门狗，
    每个实例首 cycle 都会对 18790 执行 free_port() 杀掉对方的网关再拉起，
    形成互杀抖动（2026-09-21 反复 DOWN->重启的根因）。单例锁彻底杜绝。
    """
    old = None
    try:
        with open(WATCHDOG_PID_FILE) as f:
            old = int(f.read().strip())
    except (OSError, ValueError):
        old = None
    if old and old != os.getpid() and pid_alive(old):
        log(f"已有看门狗在运行 (pid {old})，本实例退出（单例锁防双开互杀）")
        return False
    try:
        with open(WATCHDOG_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    return True


def free_port(port):
    """强制释放端口：杀掉占用该端口的进程（Windows）。
    用途：网关代码频繁改动，重启时必须清掉残留旧进程，确保加载最新代码。
    仅对网关(18790)调用。返回是否杀掉了进程。"""
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


def launch(name, port, cmd, logname, path, token, wait):
    """脱离式启动单个组件（带 PID 锁，绝不重复拉起）。返回是否就绪。"""
    # 1) 已在监听 -> 跳过
    if is_up(port, path, token):
        return True
    # 2) 有存活的旧进程（可能还在加载）-> 等其就绪，不重复拉
    old = load_pid(name)
    if pid_alive(old):
        return wait_ready(name, port, path, wait, token)
    # 3) 端口 DOWN 且旧进程已死 -> 真正重新拉起
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
    if not watchdog_singleton():
        sys.exit(0)
    rerank = "--rerank" in sys.argv
    ocr = "--noocr" not in sys.argv
    mode = "chat+embed+网关" + ("+rerank" if rerank else "") + ("+OCR" if ocr else " (无OCR)")
    log(f"看门狗启动：{mode}（探活间隔 {WATCH_INTERVAL}s，PID 锁防双启动，掉线即自愈）")

    freed = set()  # 本看门狗生命周期内，每个端口仅强制释放一次（用于加载最新代码）

    def cycle():
        for name, port, cmd, logname, mandatory, path, wait in comps(rerank, ocr):
            # 网关组件：首次拉起前强制释放端口，杀掉残留旧进程，确保加载最新代码
            if name == "gateway" and port not in freed:
                if free_port(port):
                    log(f"{name}:{port} 已释放旧进程，准备加载最新代码")
                freed.add(port)
            if is_up(port, path, TOKEN if name == "gateway" else None):
                continue
            ok = launch(name, port, cmd, logname, path,
                        TOKEN if name == "gateway" else None, wait)
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
