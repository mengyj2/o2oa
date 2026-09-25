"""
start_ai_stack_detached.py — 脱离父会话、逐个就绪后拉起 O2OA AI 栈

背景与必要性：
  start_ai_stack.bat 原用 `start /min` 拉起子进程，父控制台关闭时子进程易被整树回收；
  且一次同时拉起 3 个 llama 模型（chat+embed+rerank）在 4GB 显存机器上会相互挤崩。
  本脚本改用 DETACHED_PROCESS + CREATE_BREAKAWAY_FROM_JOB，并在拉起每个组件后“等它就绪”
  再拉下一个（错峰），显著降低显存争抢；rerank 默认关闭（网关可自动回退向量检索），OCR 可选。

用法：
  python start_ai_stack_detached.py            # chat+embed+网关+OCR（推荐，省显存）
  python start_ai_stack_detached.py --rerank  # 额外拉起 rerank（RAG 精排，显存够才开）
  python start_ai_stack_detached.py --noocr   # 不拉 OCR
  python start_ai_stack_detached.py --status  # 只查看状态，不启动
"""
import os
import json
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LLAMA_DIR = os.path.join(ROOT, "llama.cpp", "standalone")
LLAMA_EXE = os.path.join(LLAMA_DIR, "llama-server.exe")
MODELS = "D:/llm_models"
PY = r"C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
TOKEN = "local-o2-agent-2026"

CHAT_MODEL = f"{MODELS}/lmstudio-community/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q8_0.gguf"
MMPROJ = f"{MODELS}/lmstudio-community/Qwen3.5-4B-GGUF/mmproj-Qwen3.5-4B-BF16.gguf"
EMBED_MODEL = f"{MODELS}/Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"
RERANK_MODEL = f"{MODELS}/gpustack/bge-reranker-v2-m3-GGUF/bge-reranker-v2-m3-Q8_0.gguf"

# CREATE_NO_WINDOW(0x08000000) 替代 DETACHED_PROCESS：
# venv 的 Scripts\python.exe 是启动器，会再拉起基础解释器；DETACHED 下父进程无控制台，
# 孙进程会新分配一个【可见】控制台窗口（2026-09-22 实测弹窗）。
# CREATE_NO_WINDOW 的隐藏控制台可被子进程继承，整条进程树都不弹窗。
DETACHED = 0x00000200 | 0x01000000 | 0x08000000  # NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW

# 组件定义：(name, port, cmd, log, mandatory, health_path, wait_secs)
def comps(rerank, ocr):
    # 仅当网关配置使用本地 Qwen(8088) 时才拉起 chat 组件；
    # 若 chat 改走 GLM / LM Studio(1234)，则不再常驻 Qwen，避免 4GB 显存被两份大模型挤崩。
    # （2026-09-20：用户实测"用 GLM 正常、用内置 Qwen 有问题"——根因之一即 8192 上下文上限 +
    #  与 GLM 抢 4GB 显存。改走 GLM 后，Qwen 这一常驻进程应自动让出显存。）
    cfg_local_chat = True
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as _f:
            _cfg = json.load(_f)
        if "8088" not in str(_cfg.get("bionic_base", "")):
            cfg_local_chat = False
    except Exception:
        cfg_local_chat = True  # 读不到配置时保守拉起本地 Qwen
    c = []
    if cfg_local_chat:
        c.append(("chat", 8088,
         [LLAMA_EXE, "-m", CHAT_MODEL, "--mmproj", MMPROJ, "-c", "8192", "-ngl", "999",
          "--host", "127.0.0.1", "--port", "8088", "--jinja", "--alias", "qwen3.5-4b", "--no-webui"],
         "llama_chat.log", True, "/health", 150))
    c.append(
        ("embed", 8089,
         [LLAMA_EXE, "-m", EMBED_MODEL, "-c", "2048", "-ngl", "999",
          "--host", "127.0.0.1", "--port", "8089", "--embedding", "--pooling", "last",
          "--alias", "qwen3-embed", "--no-webui"],
         "llama_embed.log", True, "/health", 120),
    )
    if rerank:
        c.append(("rerank", 8092,
                  [LLAMA_EXE, "-m", RERANK_MODEL, "--alias", "bge-reranker-v2-m3", "-c", "8192",
                   "-ngl", "999", "--host", "127.0.0.1", "--port", "8092", "--reranking", "--no-webui"],
                  "llama_rerank.log", False, "/health", 90))
    c.append(("gateway", 18790,
              [PY, os.path.join(HERE, "o2_agent_gateway.py")], "gateway.log", True,
              "/gateway/health", 60))
    if ocr:
        c.append(("ocr", 8091,
                  [PY, os.path.join(HERE, "ocr_service.py")], "ocr_service.log", False,
                  "/health", 45))
    return c


def port_up(port, timeout=0.6):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(port):
    """强制释放端口：杀掉占用该端口的进程（Windows）。
    网关代码频繁改动，启动时先清掉残留旧进程，确保加载最新代码。仅对网关(18790)调用。"""
    killed = []
    try:
        ps = ("$ids=(Get-NetTCPConnection -LocalPort %d -ErrorAction SilentlyContinue)"
              ".OwningProcess | Sort-Object -Unique; "
              "foreach($id in $ids){ if($id){ Stop-Process -Id $id -Force "
              "-ErrorAction SilentlyContinue; Write-Host $id } }" % port)
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=20)
        for tok in out.stdout.split():
            if tok.strip().isdigit():
                killed.append(tok.strip())
    except Exception:
        pass
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15)
        for line in out.stdout.splitlines():
            if (":%d " % port) in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                                  capture_output=True, text=True, timeout=10)
                    killed.append(pid)
    except Exception:
        pass
    if killed:
        time.sleep(2)
    return bool(killed)


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_NO_PROXY_OPENER)


def healthy(url, token=None, timeout=3):
    """探活本机端口：★必须绕过系统代理★

    urllib 默认读 Windows 系统代理/环境变量（HTTP_PROXY 等），宿主开 Clash 等
    代理时 127.0.0.1 探活请求被转发到代理 -> 失败 -> 看门狗误判 DOWN，
    杀掉健康服务再重启，形成 30~40s 一轮的杀-启死循环
    （2026-09-22 10:33~10:53 网关反复重启 + PowerShell 疯狂弹窗的真凶）。
    这里安装 ProxyHandler({}) 的全局 opener，强制直连。
    """
    # 先用纯 TCP 连通性判定（完全绕过系统代理 / HTTP / 鉴权）：
    # 只要 127.0.0.1:port 在 listening 就说明进程存活，绝不误杀。
    # 再对需要鉴权的网关做 HTTP 200 复核，确认是真正的网关而非其它进程占位。
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        sock = socket.create_connection(
            (p.hostname or "127.0.0.1", p.port or 0), timeout=timeout)
        sock.close()
    except OSError:
        return False
    if not token:
        return True
    try:
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + token)
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as r:
            return r.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_ready(name, port, path, secs, token=None):
    url = f"http://127.0.0.1:{port}{path}"
    deadline = time.time() + secs
    step = 0
    while time.time() < deadline:
        if healthy(url, token):
            print(f"  - {name} :{port} ready ({int(time.time())} 已就绪)")
            return True
        step += 1
        if step % 5 == 0:
            print(f"    ... {name} 仍在加载（已 {step*3}s）")
        time.sleep(3)
    return False


def main() -> int:
    rerank = "--rerank" in sys.argv
    ocr = "--noocr" not in sys.argv
    status_only = "--status" in sys.argv
    if status_only:
        up = 0
        for name, port, _, _, _, _, _ in comps(rerank, ocr):
            ok = port_up(port)
            print(f"  - {name} :{port} {'UP' if ok else 'DOWN'}")
            up += ok
        return 0 if up == len(comps(rerank, ocr)) else 1

    print(f"[AI] 启动模式: chat+embed+网关" + ("+rerank" if rerank else "") +
          ("+OCR" if ocr else " (无OCR)") + "  （逐个就绪后拉起，错峰省显存）")
    rc = 0
    for name, port, cmd, logname, mandatory, path, wait in comps(rerank, ocr):
        if name == "gateway":
            free_port(port)  # 启动前强制释放端口，确保加载最新网关代码
        if port_up(port):
            print(f"  - {name} :{port} already running, skip")
            continue
        log = open(os.path.join(HERE, logname), "ab", buffering=0)
        try:
            cwd = LLAMA_DIR if name in ("chat", "embed", "rerank") else HERE
            p = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, creationflags=DETACHED, close_fds=True)
            print(f"  - starting {name} :{port} (pid {p.pid}) -> {logname}")
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {name} 启动失败: {e}")
            if mandatory:
                rc = 1
            continue
        token = TOKEN if name == "gateway" else None
        if wait_ready(name, port, path, wait, token):
            continue
        # 未就绪
        if mandatory:
            print(f"  [ERROR] {name} :{port} 在 {wait}s 内未就绪，查看 {logname}")
            rc = 1
        else:
            print(f"  [WARN] {name} :{port} 未就绪（非必需，跳过，不影响主链路）")
    print("[AI] 启动序列结束。" + ("" if rc == 0 else " 存在必需组件未就绪，详见上方日志。"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
