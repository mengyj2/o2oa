# -*- coding: utf-8 -*-
"""
O2OA 应用导入器（正确版）
========================

导入通道（已在 o2oa-server 镜像内验证模块存在）：
  · 流程平台应用  -> x_processplatform_assemble_designer/jaxrs/input/cover  (PUT)
  · 数据中心应用  -> x_query_assemble_designer/jaxrs/input/cover           (PUT)
  · 门户应用      -> x_portal_assemble_designer/jaxrs/input/cover           (PUT)
  · 服务模块(字典) -> 镜像无 x_service_assemble_designer，改为「纯字典流程平台应用」
                      复用 x_processplatform_assemble_designer 导入（applicationDictList）。

鉴权：用 O2OA 自带 Crypto 现算 cipher token（有效期 20 分钟），经 x-token 头免登录调用。

用法：
  python import_xapps.py            # 导入 00~06（顺序）
"""

import json
import os
import sys
import subprocess
import urllib.request
import urllib.error

BUILD = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.join(os.path.dirname(BUILD), "deliverables")
BASE = "http://localhost:9090"

sys.path.insert(0, BUILD)
from o2oa_builder import process_platform  # 仅用于 00 字典转换


def get_token():
    """在 o2oa:10.0.2 容器内用 O2OA 自带类现算 cipher token。"""
    cmd = [
        "docker", "run", "--rm", "--entrypoint", "sh",
        "-v", "o2oa_o2oa-config:/opt/o2server/config",
        "-v", "%s:/work" % BUILD, "o2oa:10.0.2", "-c",
        'D=/opt/o2server; CLS="/tmp"; '
        'for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do CLS="$CLS:$j"; done; '
        '$D/jvm/linux_java11/bin/javac -cp "$CLS" -d /tmp /work/MkToken.java; '
        'cd $D && $D/jvm/linux_java11/bin/java -cp "/tmp:$CLS" -Duser.dir=$D MkToken',
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    for line in out.splitlines():
        if line.startswith("TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("未能从 MkToken 输出解析 token，输出：\n" + out)


def put_cover(module, obj, token):
    """PUT <module>/jaxrs/input/cover，失败回退 POST。返回 (status, body)。"""
    url = "%s/%s/jaxrs/input/cover" % (BASE, module)
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    hdr = {"x-token": token, "Content-Type": "application/json"}

    def _do(method):
        req = urllib.request.Request(url, data=data, headers=hdr, method=method)
        return urllib.request.urlopen(req, timeout=180)

    try:
        r = _do("PUT")
        return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if e.code == 405:
            try:
                r = _do("POST")
                return r.status, r.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e2:
                return e2.code, e2.read().decode("utf-8", "ignore")
        return e.code, body
    except Exception as e:  # 网络等
        return -1, str(e)


def import_app_file(fn, token):
    path = os.path.join(DELIV, fn)
    d = json.load(open(path, encoding="utf-8"))
    print("\n### %s" % fn)
    ok = True
    for pp in (d.get("processPlatformList") or []):
        s, b = put_cover("x_processplatform_assemble_designer", pp, token)
        print("  PP  -> HTTP %s | %s" % (s, b[:160].replace("\n", " ")))
        ok = ok and (200 <= s < 300)
    for q in (d.get("queryList") or []):
        s, b = put_cover("x_query_assemble_designer", q, token)
        print("  QRY -> HTTP %s | %s" % (s, b[:160].replace("\n", " ")))
        ok = ok and (200 <= s < 300)
    for p in (d.get("portalList") or []):
        s, b = put_cover("x_portal_assemble_designer", p, token)
        print("  PTL -> HTTP %s | %s" % (s, b[:160].replace("\n", " ")))
        ok = ok and (200 <= s < 300)
    # 00 字典：服务模块无 designer，转成「纯字典流程平台应用」导入
    for svc in (d.get("serviceModuleList") or []):
        dicts = svc.get("dictList") or []
        pp = process_platform(
            svc.get("id"), svc.get("name", "公共数据字典"),
            description=svc.get("description", ""),
            category="公共",
            processes=[], forms=[], dicts=dicts,
        )
        s, b = put_cover("x_processplatform_assemble_designer", pp, token)
        print("  DICT-> HTTP %s | %s" % (s, b[:160].replace("\n", " ")))
        ok = ok and (200 <= s < 300)
    return ok


def main():
    token = get_token()
    print("[token] 已获取，长度 %d" % len(token))
    order = [
        "00_公共数据字典.xapp",
        "01_项目管理应用.xapp",
        "02_合同管理应用.xapp",
        "03_预算管理应用.xapp",
        "04_财务管理应用.xapp",
        "05_档案管理应用.xapp",
        "06_人力资源管理应用.xapp",
    ]
    all_ok = True
    for fn in order:
        if not os.path.exists(os.path.join(DELIV, fn)):
            print("[skip] 不存在: %s" % fn)
            continue
        all_ok = import_app_file(fn, token) and all_ok
    print("\n==== 导入完成，整体结果：%s ====" % ("全部成功" if all_ok else "存在失败项，见上"))


if __name__ == "__main__":
    main()
