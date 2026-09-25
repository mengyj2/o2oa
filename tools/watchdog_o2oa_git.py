#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 代码级看门狗：持续把运行实例的代码级变更提交进 git，使其可随时打包成分支。

设计要点：
  - 仅追踪白名单目录（代码级资产），绝不碰 gitignore 覆盖的凭据/大体积运行时。
  - 轮询 git status，有变更即自动提交（提交信息含时间戳 + 变更摘要）。
  - 自循环常驻；通过 start_watchdog.bat / 计划任务启动。

用法：
  python tools/watchdog_o2oa_git.py                # 常驻（默认每 60s 巡检）
  python tools/watchdog_o2oa_git.py --once        # 仅巡检并提交一次（测试用）
  python tools/watchdog_o2oa_git.py --interval 120
依赖：仅标准库。
"""
import os
import sys
import time
import subprocess

_THIS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_THIS)  # 仓库根 = tools/ 的父目录

# ★ 白名单：只自动提交这些代码级资产。patch/ 故意不列入，
#   因其含待人工裁决的删除（如 x_component_Drive 资产），避免看门狗误提交。
WHITELIST = [
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    "ai-stack-hardening",
    "deploy",
    "docs",
    "tools",
    "gateway/config.json",
    "mailservice",
    # ★ 项目记忆：记录「全部有效优化/修改」的溯源，随代码级资产一起持续化
    ".workbuddy/memory",
]

INTERVAL = 60
LOG_PATH = os.path.join(_THIS, "watchdog_o2oa_git.log")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def run_git(args):
    """在仓库根目录执行 git，返回 (rc, stdout)。"""
    try:
        p = subprocess.run(
            ["git"] + args,
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except Exception as e:  # pragma: no cover
        return -1, str(e)


def changed_paths():
    """返回白名单内发生变更的已跟踪/未跟踪路径列表。"""
    out = set()
    for w in WHITELIST:
        rc, so = run_git(["status", "--porcelain", "--", w])
        if rc != 0:
            continue
        for line in so.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if "->" in line:
                path = parts[-1]
            else:
                path = parts[1] if len(parts) > 1 else parts[0][3:]
            out.add(path.strip())
    return sorted(out)


def once():
    paths = changed_paths()
    if not paths:
        log("无白名单变更，跳过提交。")
        return 0
    # 仅 add 白名单内路径，避免误带凭据/大体积
    for p in paths:
        run_git(["add", "--", p])
    rc, so = run_git(["diff", "--cached", "--name-only"])
    staged = [x for x in so.splitlines() if x.strip()]
    if not staged:
        log("变更均在 gitignore 覆盖范围内，无内容可提交。")
        return 0
    summary = ", ".join(p[:60] for p in paths[:20])
    if len(paths) > 20:
        summary += f" …(+{len(paths) - 20} 项)"
    msg = f"watchdog(auto): {time.strftime('%Y-%m-%d %H:%M:%S')} 变更 {len(paths)} 项: {summary}"
    rc, so = run_git(["commit", "-m", msg])
    if rc == 0:
        log(f"已提交 {len(staged)} 个文件。{summary}")
    else:
        log(f"提交失败(rc={rc}): {so[:200]}")
    return rc


def main():
    args = sys.argv[1:]
    interval = INTERVAL
    do_once = False
    for a in args:
        if a == "--once":
            do_once = True
        elif a.startswith("--interval="):
            try:
                interval = int(a.split("=", 1)[1])
            except Exception:
                pass
    os.chdir(REPO)
    log(f"看门狗启动：仓库={REPO} 白名单={WHITELIST} interval={interval}s")
    if do_once:
        once()
        return
    while True:
        try:
            once()
        except Exception as e:  # pragma: no cover
            log(f"巡检异常: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
