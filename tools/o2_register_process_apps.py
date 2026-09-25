#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把「流程应用型 / 门户型」应用注册进桌面「开始」菜单。

为什么不能全用 CPT_COMPONENT：
    CPT_COMPONENT 那条路走 openApplication(path)，只能传一个命名空间字符串，
    无法传 {id, appId} 参数 —— 流程应用/门户/查询都依赖 options 才能定位到具体应用。

所以流程应用走 applications.json + "@url:" 深链：
    Layout.initData() 支持
        /x_desktop/index.html?app=<namespace>&option=<urlencoded json>
    它会写 status.apps[app] = options 且 window={isMax:true, isHide:false}，
    因此点开就新开窗口、目标应用最大化直接可见。
    createApplicationMenu 对 path 以 "@url" 开头的条目：图标取 value.iconPath，
    点击 -> openApplication(e,"@url:...") -> 新窗口直跳。

落地点（重要）：
    servers/webServer 在镜像里、不在卷里，所以 applications.json 必须
    ① 写进容器运行时路径 /opt/o2server/servers/webServer/o2_core/o2/xDesktop/$Layout/applications.json
       （立即生效，但 docker 重建镜像会丢）
    ② 同时导出 patch/web/applications.json，供 Dockerfile COPY 固化
       （见 Dockerfile 中 COPY patch/web/applications.json ...）

用法:
    python o2_register_process_apps.py gen      # 只生成 patch/web/applications.json
    python o2_register_process_apps.py push     # 生成 + 写入运行中的容器（立即生效）
    python o2_register_process_apps.py show     # 显示当前容器内的内容
    python o2_register_process_apps.py reset    # 清空为 []
"""
import sys, os, json, subprocess, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2 import login, get, extract_list

HOST = "http://localhost:9090"
CONTAINER = "o2oa-server"
CONTAINER_JSON = "/opt/o2server/servers/webServer/o2_core/o2/xDesktop/$Layout/applications.json"
PATCH_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patch", "web", "applications.json")
PATCH_OUT = os.path.normpath(PATCH_OUT)

SKIP_NAMES = {"公共数据（全局）"}

# 额外手工条目（不来自流程应用接口）
EXTRA = []


def dl(path, token):
    st, j = get(path, token)
    return extract_list(j)


def build_entry(aid, name, ns="process.Application"):
    option = json.dumps({"id": aid, "appId": ns + aid}, ensure_ascii=False)
    url = f"{HOST}/x_desktop/index.html?app={ns}&option={urllib.parse.quote(option)}"
    return {
        "title": name,
        "path": "@url:" + url,
        "iconPath": f"{HOST}/x_component_process_ApplicationExplorer/$Main/default/icon/application.png",
        "allowList": [],
        "denyList": [],
    }


def build_all(token):
    apps = [a for a in dl("/x_processplatform_assemble_surface/jaxrs/application/list", token)
            if isinstance(a, dict) and a.get("name") not in SKIP_NAMES]
    entries = [build_entry(a["id"], a["name"]) for a in apps if a.get("id")]
    return entries, apps


def cmd_gen(token):
    entries, apps = build_all(token)
    content = json.dumps(entries, ensure_ascii=False, indent=2)
    with open(PATCH_OUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"已生成 {PATCH_OUT}")
    print(f"  流程应用 {len(apps)} 个 -> {len(entries)} 条目")
    for e in entries:
        print("   ", e["title"])


def cmd_push(token):
    entries, apps = build_all(token)
    content = json.dumps(entries, ensure_ascii=False, indent=2)
    # 1) 写 patch（固化用）
    with open(PATCH_OUT, "w", encoding="utf-8") as f:
        f.write(content)
    # 2) 写容器（立即生效）—— 用 docker exec 直接落文件
    payload = content.replace("'", "'\\''")
    cmd = (f"mkdir -p \"$(dirname '{CONTAINER_JSON}')\" && "
           f"printf '%s' '{payload}' > '{CONTAINER_JSON}' && wc -c '{CONTAINER_JSON}'")
    r = subprocess.run(["docker", "exec", CONTAINER, "sh", "-c", cmd],
                       capture_output=True, text=True)
    print("容器写入 rc=", r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:300])


def cmd_show(token):
    r = subprocess.run(["docker", "exec", CONTAINER, "cat", CONTAINER_JSON],
                       capture_output=True, text=True)
    txt = r.stdout.strip()
    if not txt:
        print("(容器内为空或读取失败)", r.stderr.strip()[:200])
        return
    try:
        data = json.loads(txt)
        print(f"容器内 applications.json 共 {len(data)} 条：")
        for it in data:
            print("  ", it.get("title"), "|", (it.get("path") or "")[:80])
    except Exception as e:
        print("解析失败:", e, txt[:300])


def cmd_reset(token):
    r = subprocess.run(["docker", "exec", CONTAINER, "sh", "-c",
                        f"printf '[]' > '{CONTAINER_JSON}'"], capture_output=True, text=True)
    print("已重置 rc=", r.returncode, r.stderr.strip()[:200])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "gen"
    tok = login()
    {"gen": cmd_gen, "push": cmd_push, "show": cmd_show, "reset": cmd_reset}.get(
        cmd, lambda t: print("unknown cmd: use gen|push|show|reset")
    )(tok)
