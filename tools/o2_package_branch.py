#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 实例打包成分支脚本

用途：把当前运行的 O2OA 10.0.2 本地实例‘快照’打包成一个 git 分支，
使其可在另一台机器上通过 `git clone` + `docker compose up -d` 复现。

依赖：仅标准库 + git 二进制。所有路径相对于仓库根目录 D:\O2OA。
"""

import os
import sys
import subprocess
import json
import hashlib
import time
from datetime import datetime

# ── 仓库根目录
_THIS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_THIS)  # D:\O2OA

# ── Git 基础辅助
def git(*args, cwd=None):
    """Run git command; return (rc, stdout_str)."""
    if cwd is None:
        cwd = REPO
    try:
        r = subprocess.run(["git"] + list(args), cwd=cwd,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout or "").strip()
    except Exception as e:
        return -1, str(e)


def git_status_porcelain():
    """返回 git status --porcelain 的全部行列表。"""
    rc, out = git("status", "--porcelain", cwd=REPO)
    if rc != 0:
        return []
    return [l for l in out.splitlines() if l.strip()]


def git_add_whitelist():
    """Stage only paths under the established WHITELIST (see o2_state_guard.py)."""
    # Reuse the same whitelist logic
    whitelist = [
        "docker-compose.yml", ".env.example", ".gitignore",
        "ai-stack-hardening", "deploy", "docs", "tools",
        "gateway/config.json", "mailservice",
        ".workbuddy/memory",
    ]
    added = []
    for w in whitelist:
        rc, _ = git("add", "--", w)
        if rc == 0:
            added.append(w)
    return added


def git_commit(message):
    rc, out = git("commit", "-m", message, cwd=REPO)
    return rc, out


# ── 资产清单 / manifest

def collect_asset_manifest():
    """扫描代码级关键资产，返回相对路径的 SHA-256 指纹字典。"""
    manifest = {}
    base_dirs = ["deploy", "docs", "tools", "gateway/config.json"]
    for rel in base_dirs:
        abs_path = os.path.join(REPO, rel)
        if not os.path.isdir(abs_path) and not os.path.isfile(abs_path):
            continue
        # 计算单个文件或目录树的哈希
        if os.path.isfile(abs_path):
            # 单文件
            manifest[rel] = sha256_file(abs_path)
        else:
            # 目录树：对树内所有相对路径排序后聚合
            entries = []
            for dirpath, _, files in os.walk(abs_path):
                for fname in files:
                    full = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full, REPO)
                    # 跳过 .git 相关
                    if ".git" in rel_path:
                        continue
                    entries.append((rel_path, sha256_file(full)))
            for rp, h in sorted(entries, key=lambda x: x[0]):
                manifest[rp] = h
    return manifest


def sha256_file(path):
    """计算单个文件的 SHA-256 十六进制摘要。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 主流程

def create_branch(branch_name):
    """切出一个新分支（若已存在则返回错误）。"""
    # 先检查分支是否存在
    rc, branches = git("branch", "-a", cwd=REPO)
    if branch_name in branches.splitlines():
        return 0, f"分支 {branch_name} 已存在。"
    # 从当前 HEAD 切出
    rc, out = git("checkout", "-b", branch_name, cwd=REPO)
    return rc, out


def package_instance(branch_name="release/cncca-10.0.2-auto-{}".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"))):
    """完整打包流程：检查工作区、提交变更、切分支。

    返回 (rc, info_text)。
    """
    # 1. 检查工作区是否干净（仅针对白名单路径）
    status_lines = git_status_porcelain()
    if status_lines:
        log_msg = "检测到未提交变更，尝试自动 stage + commit（白名单内）..."
        log(log_msg)
        added = git_add_whitelist()
        if added:
            rc, msg = git_commit(
                f"watchdog(auto): {time.strftime('%Y-%m-%d %H:%M:%S')} 代码级资产自动同步 "
                f"({len(added)} 项)"
            )
            if rc != 0:
                return rc, f"git commit 失败: {msg}"
        else:
            # 没有可 stage 的白名单变更，但仍有未跟踪/修改文件
            return 1, "工作区有非白名单变更，请手动审查后再打包。详见: git status"

    # 2. 创建分支
    rc, out = create_branch(branch_name)
    if rc != 0:
        return rc, f"切出分支失败: {out}"

    # 3. 收集资产指纹快照并写入文件（便于复现时校验）
    manifest = collect_asset_manifest()
    manifest_path = os.path.join(REPO, "BRANCH_MANIFEST.json")
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        log_msg = f"资产指纹快照已写入 {manifest_path}（{len(manifest)} 条记录）"
        log(log_msg)
    except Exception as e:
        log_msg = f"警告：无法写入指纹清单: {e}"
        log(log_msg)

    # 4. 汇总信息
    info = (
        f"=== O2OA 实例分支打包完成 ===\n"
        f"分支名称: {branch_name}\n"
        f"提交时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"资产指纹: BRANCH_MANIFEST.json（{len(manifest)} 条文件哈希）\n"
        f"\n"
        f"复现步骤:\n"
        f"1. git clone <repo>\n"
        f"2. cd <repo>\n"
        f"3. docker compose up -d\n"
        f"4. python tools/ingest_o2oa_kb.py   # 重建知识库向量\n"
        f"5. 如需门户分流：deploy/home_entry_local.ps1 写盘 + docker cp 进容器\n"
        f"\n"
        f"※ 凭据（.env / mailservice 数据）不随分支走，请在目标环境单独注入。\n"
    )
    return 0, info


def log(msg, also_print=True):
    """写入日志文件并可选打印。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(os.path.join(REPO, "watchdog_o2oa_git.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if also_print:
        print(line, flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    branch = None
    for a in args:
        if a.startswith("--branch="):
            branch = a.split("=", 1)[1]
        elif a == "--once":
            pass  # 默认即一次性流程
        else:
            print(f"用法: python tools/o2_package_branch.py [--branch=<名字>]")
            print("  --branch=release/cncca-10.0.2-auto-YYYYMMDD-HHMMSS")
            sys.exit(0)

    if not branch:
        branch = f"release/cncca-10.0.2-auto-{time.strftime('%Y%m%d-%H%M%S')}"

    rc, msg = package_instance(branch)
    print(msg)
    sys.exit(rc)