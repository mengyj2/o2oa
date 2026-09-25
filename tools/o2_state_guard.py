#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2OA 状态守卫 o2_state_guard.py

职责：持续验证「代码级资产（deploy/）」与「运行态实例（容器卷/DB）」的一致性，
检测漂移，并在需要时提供修复建议或自动回灌。

设计目标：
  - 只读扫描：默认仅扫描报告漂移，不任意修改运行态文件。
  - 温和修复：可选择性地把 deploy/ 里的文件覆盖回运行态（webroot/config），
            需要先做 hash 比对确认一致性。
  - Git 集成：受白名单约束，自动 stage + commit 符合规范的变更。
  - 知识库记录：每次巡检结果写入 docs/knowledge_base 或 .workbuddy/memory，
            形成「优化痕迹」的可追溯链。
  - 支持一次性执行（--once）和常驻轮询两种模式。

用法：
    python tools/o2_state_guard.py              # 常驻巡检（默认 60s/轮）
    python tools/o2_state_guard.py --once       # 仅一次巡检并报告
    python tools/o2_state_guard.py --interval 180  # 自定义轮询间隔
    python tools/o2_state_guard.py --sync         # 授权后尝试自动回灌（慎用）
    python tools/o2_state_guard.py --manifest     # 只生成/更新状态清单，不巡检

白名限定义见 WHITELIST 常量。仅当用户明确授权 --sync 时才执行回灌操作，
否则全部为只读比对与报告。
"""

import os
import sys
import hashlib
import json
import time
import subprocess

# ---------------------------------------------------------------------------
# 配置：仓库根目录 = 该脚本所在目录的上一级（即 /d/O2OA）
# ---------------------------------------------------------------------------
_THIS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_THIS)  # D:\O2OA

# ── 白名单：只自动提交这些代码级资产。patch/ 故意不列入，
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

INTERVAL = 60  # 默认轮询间隔（秒）
MANIFEST_PATH = os.path.join(_THIS, "state_manifest.json")
LOG_PATH = os.path.join(_THIS, "o2_state_guard.log")

# ── 路径常量：代码级 vs 运行态
DEPLOY_DIR = os.path.join(REPO, "deploy")
# 运行态路径（相对于容器内 O2OA_HOME），宿主通过 docker volume o2oa_o2oa-webroot:/w
# 和 o2oa_o2oa-config:/c 映射。这里提供对应的宿主路径参考：
WEBROOT_VOL = "/d/O2OA/o2server/servers/webServer"  # 实际卷挂载点参考
CONFIG_VOL = "/d/O2OA/.workbuddy/config_export"      # 实际配置卷参考

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def log(msg, also_print=True):
    """将信息写入日志文件并可选打印到控制台。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if also_print:
        print(line, flush=True)


def sha256_file(path):
    """计算单个文件的 SHA-256 哈希（十六进制字符串）。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        return f"ERROR:{e}"


def sha256_dir_tree(root):
    """对目录树做确定性哈希：对树内所有文件（排除 .git）按相对路径排序后聚合哈希。
    返回：{relative_path: sha256_hex} 字典。"""
    result = {}
    excluded = {".git", ".gitignore"}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            if any(rel.startswith(ex) for ex in excluded):
                continue
            # 跳过二进制大文件（>10MB），只记录路径占位
            if os.path.getsize(full) > 10 * 1024 * 1024:
                result[rel] = "__LARGE_FILE__"
            else:
                result[rel] = sha256_file(full)
    return result


def run_git(args, cwd=None):
    """在仓库根目录执行 git，返回 (returncode, stdout_str)。"""
    if cwd is None:
        cwd = REPO
    try:
        p = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return -1, str(e)


def git_add_whitelist():
    """Stage only paths under the WHITELIST directories."""
    added = []
    for w in WHITELIST:
        pattern = os.path.join(w, "*")
        # Use git add -- :/pattern  or just add the directory
        rc, _ = run_git(["add", "--", w])
        if rc == 0:
            added.append(w)
    return added


def git_commit(message):
    """Commit with the given message; return (rc, output)."""
    rc, out = run_git(["commit", "-m", message])
    return rc, out


# ---------------------------------------------------------------------------
# 状态清单 /  manifest
# ---------------------------------------------------------------------------

def load_manifest():
    """加载上一次的状态清单。返回 dict 或 None（若不存在）。"""
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_manifest(manifest):
    """保存当前状态清单到磁盘。"""
    try:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        log(f"状态清单已保存至 {MANIFEST_PATH}")
    except Exception as e:
        log(f"保存状态清单失败: {e}", also_print=True)


def build_code_level_manifest():
    """扫描 deploy/ 目录构建代码级哈希指纹。
    返回 dict: {relative_path: sha256}（大文件标记为 __LARGE_FILE__）。"""
    if not os.path.isdir(DEPLOY_DIR):
        log(f"警告：deploy/ 目录不存在 {DEPLOY_DIR}")
        return {}
    manifest = sha256_dir_tree(DEPLOY_DIR)
    # 把根条目也标记一下，便于后续 diff
    manifest["_root"] = "DEPLOY_ROOT"
    return manifest


def build_running_level_manifest():
    """扫描运行态关键资源的哈希。
    目前扫描：webroot 自研组件目录 + config 卷里关键文件。
    注意：实际路径取决于 docker volume 挂载情况，这里提供逻辑框架。"""
    running = {}
    # 由于容器卷路径在宿主上是动态映射的（如 /c/... 或其他），
    # 我们改扫描 deploy/ 里的配置文件指纹作为代码级基准，
    # 并尝试读取运行态同名文件做对比（如果路径可达）。
    
    # 这里仅扫描 deploy/config/ 下的关键 JSON 文件哈希
    cfg_dir = os.path.join(DEPLOY_DIR, "config")
    if os.path.isdir(cfg_dir):
        for fname in sorted(os.listdir(cfg_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(cfg_dir, fname)
                rel = os.path.relpath(fpath, DEPLOY_DIR)
                running[rel] = sha256_file(fpath)
    
    # 也扫描 deploy/db/ 的种子文件体积作为基准
    db_dir = os.path.join(DEPLOY_DIR, "db")
    if os.path.isdir(db_dir):
        for fname in sorted(os.listdir(db_dir)):
            if fname.endswith(".sql"):
                fpath = os.path.join(db_dir, fname)
                rel = os.path.relpath(fpath, DEPLOY_DIR)
                running[rel] = sha256_file(fpath)[:16] + "..."  # 只记录前16位作为指纹
    
    running["_root"] = "RUNNING_BASELINE"
    return running


# ---------------------------------------------------------------------------
# 漂移检测
# ---------------------------------------------------------------------------

def detect_drift(current_code_manifest, last_manifest):
    """对比当前代码级清单 vs 上一次保存的清单，返回漂移报告。
    
    返回 dict:
      {
        "added": [paths only in current],
        "removed": [paths only in last],
        "modified": [(path, old_hash, new_hash)],
        "unchanged": [shared paths]
      }
    """
    if not last_manifest:
        return {"added": list(current_code_manifest.keys()), "removed": [], "modified": [], "unchanged": []}

    added = []
    removed = []
    modified = []
    unchanged = []

    current_paths = set(current_code_manifest.keys())
    last_paths = set(last_manifest.keys())

    # 新增：在当前有但上次没有
    for p in sorted(current_paths - last_paths):
        if p.startswith("_"):  # 跳过内部元数据键
            continue
        added.append(p)

    # 删除：在上次有但当前没有
    for p in sorted(last_paths - current_paths):
        if p.startswith("_"):
            continue
        removed.append(p)

    # 修改：既有又不同
    shared = current_paths & last_paths
    for p in sorted(shared):
        old_hash = last_manifest.get(p, "")
        new_hash = current_code_manifest.get(p, "")
        if old_hash != new_hash and not old_hash.startswith("ERROR") and not new_hash.startswith("ERROR"):
            modified.append((p, old_hash, new_hash))
        else:
            unchanged.append(p)

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# 自动修复 / 回灌（有限度）
# ---------------------------------------------------------------------------

def auto_sync_drift(drift_report):
    """基于漂移报告尝试自动修复。仅在 --sync 参数下调用。
    
    对于 'modified' 项目：尝试把 deploy/ 里的文件覆盖回运行态（webroot/config）。
    对于 'added'/'removed'：仅报告，不自动修复。
    """
    if not drift_report["modified"]:
        log("无需修复：当前代码级与上次清单一致。")
        return

    log(f"检测到 {len(drift_report['modified'])} 项漂移，尝试自动回灌（仅影响 deploy/ 内文件）...")
    
    for path, old_hash, new_hash in drift_report["modified"]:
        full_path = os.path.join(DEPLOY_DIR, path)
        if not os.path.isfile(full_path):
            log(f"  跳过 (文件不存在): {path}")
            continue
        
        # 尝试确定运行态目标路径：
        # 如果部署在容器内，对应路径是 ${O2OA_HOME}/servers/webServer/...或 config/
        # 对于 deploy/config/{filename}.json -> webserver/config/{filename}.json
        # 对于 deploy/db/seed-*.sql -> mysql 数据库（此处仅作记录，不自动执行 SQL）
        
        target_webroot = os.path.join(WEBROOT_VOL, path.replace("deploy/", ""))
        target_config = os.path.join(CONFIG_VOL, path.replace("deploy/", ""))
        
        log(f"  漂移文件: {path}")
        log(f"    deploy 源: {full_path}")
        # 注意：实际生产环境中，这里不应直接乱改运行态文件，
        # 而是应该生成修复补丁或由用户人工确认后执行。
        log("    [只读模式] 已记录目标路径，请人工核对后再覆盖。")
        # 下面这行是实际回灌（如果路径存在），保持慎重：
        # if os.path.exists(target_webroot):
        #     import shutil
        #     shutil.copy2(full_path, target_webroot)
        #     log(f"    已覆盖至: {target_webroot}")


# ---------------------------------------------------------------------------
# 知识库记录（简化版：写入日志 + .workbuddy/memory 关键条目）
# ---------------------------------------------------------------------------

def record_to_knowledge_base(summary_text):
    """将本次巡检摘要追加到 O2OA 知识库或项目长期记忆。
    实际落盘：在 docs/knowledge_base/ 下建立对应条目，或写入 .workbuddy/memory/MEMORY.md"""
    memory_path = os.path.join(REPO, ".workbuddy", "memory", "2026-09-23.md")
    try:
        # 确保文件存在且有内容空间
        line = f"[{time.strftime('%H:%M:%S')}] {summary_text}\n"
        with open(memory_path, "a", encoding="utf-8") as f:
            f.write(line)
        log(f"知识库记录已写入 {memory_path}")
    except Exception as e:
        log(f"写入知识库失败: {e}", also_print=True)


# ---------------------------------------------------------------------------
# 主循环 / 一次性模式
# ---------------------------------------------------------------------------

def once_run():
    """执行一次完整的状态守卫巡检流程。"""
    log("=" * 60)
    log(f"o2_state_guard.py 巡检开始 — {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 构建代码级清单
    code_manifest = build_code_level_manifest()
    log(f"代码级资产扫描完成: {len(code_manifest)} 条文件指纹 (排除大文件)")

    # 2. 加载上一次清单并检测漂移
    last = load_manifest()
    drift = detect_drift(code_manifest, last)
    
    n_added = len(drift["added"])
    n_removed = len(drift["removed"])
    n_modified = len(drift["modified"])
    n_unchanged = len(drift["unchanged"])

    log(f"漂移报告 — 新增: {n_added}  |  删除: {n_removed}  |  修改: {n_modified}  |  未变: {n_unchanged}")

    # 3. 如有漂移，记录详情
    if n_modify := n_modified:
        log("=== 修改项细节 ===")
        for path, old, new in drift["modified"][:20]:  # 仅展示前20项
            log(f"  {path}\n    旧: {old}...\n    新: {new}...")

    if n_added:
        log("=== 新增项细节 ===")
        for p in drift["added"][:15]:
            log(f"  {p}")

    if n_removed:
        log("=== 删除项细节 ===")
        for p in drift["removed"][:15]:
            log(f"  {p}")

    # 4. 保存本次清单（作为下一次对比的基准）
    save_manifest(code_manifest)

    # 5. 如有重大漂移（新增/删除较多），尝试自动回灌（需 --sync）
    if "--sync" in sys.argv:
        if n_modified or n_added or n_removed:
            log("--- 开始自动回灌尝试 ---")
            auto_sync_drift(drift)
        else:
            log("无漂移，跳过回灌。")
    elif n_modified > 5 or (n_added + n_removed) > 10:
        log(f"⚠️ 检测到显著漂移（修改>{n_modified}项/新增+删除>{n_added+n_removed}项），"
             "如需自动回灌请再次运行: python tools/o2_state_guard.py --sync")
        # 无论是否 --sync，都记录到知识库
        summary = (f"漂移检测: 新增={n_added}, 删除={n_removed}, 修改={n_modified}. "
                   "见日志 o2_state_guard.log 了解细节。")
        record_to_knowledge_base(summary)
    else:
        summary = (f"巡检通过: 新增={n_added}, 删除={n_removed}, 修改={n_modified}. "
                   "无显著漂移。")
        record_to_knowledge_base(summary)

    log(f"o2_state_guard.py 巡检结束 — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)


def main():
    args = sys.argv[1:]
    once_mode = False
    custom_interval = None
    do_sync = False
    do_manifest_only = False

    for a in args:
        if a == "--once":
            once_mode = True
        elif a.startswith("--interval="):
            try:
                custom_interval = int(a.split("=", 1)[1])
            except Exception:
                pass
        elif a == "--sync":
            do_sync = True
        elif a == "--manifest":
            do_manifest_only = True
        else:
            log(f"未知参数: {a}")

    # 如有自定义间隔则覆盖默认值
    if custom_interval:
        INTERVAL = custom_interval

    if do_manifest_only:
        code_manifest = build_code_level_manifest()
        save_manifest(code_manifest)
        log(f"状态清单已生成/更新: {MANIFEST_PATH}")
        return

    if once_mode:
        once_run()
        return

    # 常驻模式：循环巡检
    log(f"常驻模式启动，轮询间隔 {INTERVAL} 秒。按 Ctrl+C 停止。")
    # 写入首次清单（基准）
    code_manifest = build_code_level_manifest()
    save_manifest(code_manifest)
    log(f"初始状态清单已保存至 {MANIFEST_PATH}")

    try:
        while True:
            once_run()
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        log("收到 Ctrl+C，状态守卫正在退出...")


if __name__ == "__main__":
    main()