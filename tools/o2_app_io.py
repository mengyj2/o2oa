#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o2_app_io.py —— O2OA 应用「设计定义」读出 / 打包 / 灌入 一体化工具

用法:
  python o2_app_io.py list   --side local|demo|both [--type portal|process|query|cms|all]
  python o2_app_io.py diff   [--type all]                      # 两端全量字节级对齐比对
  python o2_app_io.py export --side demo --type portal --name 数据管理 -o 数据管理.xapp
  python o2_app_io.py leadout --side demo --app 事项审批 -o 事项审批.流程.json
  python o2_app_io.py import -f 数据管理.xapp [--method create|cover] [--dry-run]

原理（逆向自 O2OA 10.0.2 describe/sources，2026-09-22）:
  · 导出(整包)  PUT  /x_program_center/jaxrs/module/output          body={name,portalList:[...],...}
               GET  /x_program_center/jaxrs/module/output/{flag}/file      -> <name>.xapp
  · 导出(单类)  GET  /x_{portal,query}_assemble_designer/jaxrs/output/list
               PUT  .../jaxrs/output/{id}/select                     -> {flag}
               GET  .../jaxrs/output/{flag}/select/file              -> <name>.xapp
               ⚠ 门户侧 select 用 CacheKey(getClass(),flag) 而 file 用 CacheKey(flag)，键不一致→必失败；
                 故门户/流程/CMS 统一走「整包」通道（本工具默认如此）。
  · 导出(单流程) GET /x_processplatform_assemble_designer/jaxrs/process/{id}/lead/out
  · 导入        PUT  /x_program_center/jaxrs/module/compare/upload   multipart(file,fileName) -> {flag,已存在对比}
               PUT  /x_program_center/jaxrs/module/write/{flag}      body={portalList:[{id,method}],...}
                 write 内部: 先 input/prepare/{create|cover} 拿 id 替换对 → 字符串级替换 id → input/{create|cover}
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.error, uuid

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

SIDES = {
    'local': dict(base='http://localhost:9090', cred='admin', pwd='o2oaadmin2026', proxy=False),
    'demo':  dict(base='https://samplev10.o2oa.net', cred='admin', pwd='999000%o2', proxy=False),
}

DESIGNER = {
    'portal':  dict(svc='/x_portal_assemble_designer',          wrap='portalList',          root='jaxrs/portal'),
    'process': dict(svc='/x_processplatform_assemble_designer', wrap='processPlatformList', root='jaxrs/application'),
    'query':   dict(svc='/x_query_assemble_designer',           wrap='queryList',           root='jaxrs/query'),
    'cms':     dict(svc='/x_cms_assemble_control',              wrap='cmsList',             root='jaxrs/appinfo'),
}
PC = '/x_program_center/jaxrs/module'

# ---------------- HTTP 基础 ----------------
def http(base, path, method='GET', body=None, token=None, raw=False, timeout=180, form=None):
    if form is not None:
        data, ctype = _multipart(form), None
        headers = {'Content-Type': data[1]}
        data = data[0]
    else:
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {'Content-Type': 'application/json'}
    if token: headers['x-token'] = token
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            b = resp.read()
            return resp.status, (b if raw else json.loads(b.decode('utf-8', 'replace')))
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', 'replace')
        try:    return e.code, json.loads(txt)
        except Exception: return e.code, txt
    except Exception as e:
        return -1, repr(e)

def _multipart(fields):
    """fields: {name: str} 或 {name: (filename, bytes, content_type)}"""
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        if isinstance(v, tuple):
            fn, data, ct = v
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                         f'Content-Type: {ct}\r\n\r\n'.encode('utf-8') + data + b'\r\n')
        else:
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
    parts.append(f'--{b}--\r\n'.encode('utf-8'))
    return b''.join(parts), f'multipart/form-data; boundary={b}'

def login(side):
    s = SIDES[side]
    st, j = http(s['base'], '/x_organization_assemble_authentication/jaxrs/authentication', 'POST',
                 {'credential': s['cred'], 'password': s['pwd']})
    if not isinstance(j, dict) or j.get('type') != 'success':
        raise SystemExit(f'[!] {side} 登录失败 http={st} {str(j)[:200]}')
    return j['data']['token']

# ---------------- 取设计定义清单 ----------------
def list_apps(base, tok, kind):
    """返回该类型全部应用的完整 Wrap*（output/list 自带子结构，可直接用于 select/组包）"""
    d = DESIGNER[kind]
    st, r = http(base, f"{d['svc']}/jaxrs/output/list", token=tok)
    if not isinstance(r, dict) or r.get('type') != 'success':
        raise SystemExit(f"[!] {kind} output/list 失败 http={st} {str(r)[:200]}")
    return r['data']

# ---------------- 导出 ----------------
def export(src_side, kind, name=None, app_id=None, out=None, pack_side='local'):
    """读定义(源端) -> 组包(本地，源端禁用导出时自动降级) -> 落 .xapp

    说明: demo 端 Config.general().disableExportEnable=true，其 /module/output 会报「权限不足」；
          但 designer 的 output/list 只读可读，故由「源端读定义 + 本地组包」完成导出。
    """
    src = SIDES[src_side]; stok = login(src_side)
    apps = list_apps(src['base'], stok, kind)
    pick = None
    for a in apps:
        if app_id and a.get('id') == app_id: pick = a; break
        if name and a.get('name') == name:    pick = a; break
    if pick is None:
        raise SystemExit(f'[!] 未找到 {kind} 应用 name={name!r} id={app_id!r}')

    pack_name = f"{pick.get('name')}_{kind}"
    body = {'name': pack_name, 'description': f'export from {src_side}',
            DESIGNER[kind]['wrap']: [pick]}

    order = [pack_side] if pack_side == src_side else [src_side, pack_side]
    last = None
    for ps in order:
        ptok = stok if ps == src_side else login(ps)
        pbase = SIDES[ps]['base']
        st, r = http(pbase, PC + '/output', 'PUT', body, ptok)
        if isinstance(r, dict) and r.get('type') == 'success':
            flag = r['data']['flag']
            st2, b = http(pbase, f'{PC}/output/{flag}/file', token=ptok, raw=True)
            http(pbase, f'{PC}/remove/structure/{flag}', 'DELETE', token=ptok)  # 清理临时结构
            if not isinstance(b, bytes) or b[:1] != b'{':
                raise SystemExit(f'[!] 下载失败 http={st2} {str(b)[:200]}')
            out = out or f'{pack_name}.xapp'
            open(out, 'wb').write(b)
            n = len(json.loads(b.decode('utf-8')).get(DESIGNER[kind]['wrap']) or [])
            print(f'[OK] 导出 {kind}/{pick.get("name")} -> {out}  {len(b)} bytes, 包内 {n} 个应用'
                  f'  (读定义={src_side}, 组包={ps})')
            return out
        last = (ps, st, r)
    ps, st, r = last
    raise SystemExit(f'[!] module/output 在 {ps} 失败 http={st} {str(r)[:300]}\n'
                     f'    （源端禁用导出属正常，本地应可用；请检查本地 admin 权限）')

def leadout(side, app_name, out=None):
    """单流程导出：GET /x_processplatform_assemble_designer/jaxrs/process/{id}/lead/out"""
    s = SIDES[side]; tok = login(side)
    st, r = http(s['base'], '/x_processplatform_assemble_designer/jaxrs/application/list', token=tok)
    apps = r['data'] if isinstance(r, dict) else []
    target = [a for a in apps if a.get('name') == app_name or a.get('id') == app_name]
    if not target: raise SystemExit(f'[!] 未找到流程应用 {app_name!r}')
    payload = {}
    for a in target:
        st, r2 = http(s['base'], f'/x_processplatform_assemble_designer/jaxrs/process/application/{a["id"]}', token=tok)
        for p in (r2.get('data', []) if isinstance(r2, dict) else []):
            st, r3 = http(s['base'], f'/x_processplatform_assemble_designer/jaxrs/process/{p["id"]}/lead/out', token=tok)
            if isinstance(r3, dict) and r3.get('type') == 'success':
                payload[p['name']] = r3['data']
    out = out or f'{app_name}.流程.json'
    json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[OK] 单流程导出 {app_name} -> {out}  ({len(payload)} 个流程)')
    return out

# ---------------- 导入 ----------------
def do_import(path, method='create', dry_run=False):
    if not os.path.isfile(path): raise SystemExit(f'[!] 文件不存在 {path}')
    raw = open(path, 'rb').read()
    pkg = json.loads(raw.decode('utf-8'))
    s = SIDES['local']; tok = login('local')
    st, r = http(s['base'], PC + '/compare/upload', 'PUT', token=tok,
                 form={'file': (os.path.basename(path), raw, 'application/octet-stream'),
                       'fileName': os.path.basename(path)})
    if not (isinstance(r, dict) and r.get('type') == 'success'):
        raise SystemExit(f'[!] compare/upload 失败 http={st} {str(r)[:300]}')
    flag = r['data']['flag']; data = r['data']
    print(f'[对比] 包={os.path.basename(path)}  flag={flag}')
    cmds = {}
    any_exist = False
    for kind, d in DESIGNER.items():
        wrap = d['wrap']
        items = data.get(wrap) or []
        if not items: continue
        cmds[wrap] = []
        for it in items:
            ex = it.get('exist')
            any_exist = any_exist or bool(ex)
            print(f"   {kind:8s} {it.get('name')!r:22s} id={str(it.get('id'))[:8]} "
                  f"已存在={'是' if ex else '否'}"
                  + (f" (本地: {it.get('existName')!r} {str(it.get('existId'))[:8]})" if ex else ''))
            cmds[wrap].append({'id': it.get('id'), 'method': method})
    if dry_run:
        print(f'[dry-run] 未落库。可用 /remove/structure/{flag} 清理临时结构。')
        return flag
    if not cmds:
        print('[!] 包内无可导入项'); return flag
    if any_exist and method == 'create':
        print('[提示] 存在同名/同 id 项，create 会重命名新建；如需覆盖请用 --method cover')
    st, r = http(s['base'], f'{PC}/write/{flag}', 'PUT', cmds, tok, timeout=600)
    if isinstance(r, dict) and r.get('type') == 'success':
        d = r['data']
        print('[OK] 导入完成:')
        for k, v in d.items():
            if v: print(f'   {k}: {v}')
    else:
        print(f'[!] 导入失败 http={st} {str(r)[:400]}')
    return flag

# ---------------- 全量对比 ----------------
def _strip(o, noise=('createTime','updateTime','lastUpdateTime','lastUpdatePerson','creatorPerson','distributeFactor')):
    if isinstance(o, dict):  return {k: _strip(v, noise) for k, v in o.items() if k not in noise}
    if isinstance(o, list):  return [_strip(x, noise) for x in o]
    return o

def diff(kinds=('portal', 'process', 'query', 'cms')):
    import hashlib
    out = {}
    for kind in kinds:
        per = {}
        for side in ('local', 'demo'):
            tok = login(side); base = SIDES[side]['base']
            try:
                apps = list_apps(base, tok, kind)
            except SystemExit as e:
                print(f'[!] {side}/{kind}: {e}'); per[side] = {}; continue
            m = {}
            for a in apps:
                key = json.dumps(_strip(a), ensure_ascii=False, sort_keys=True)
                m[a.get('id')] = (hashlib.md5(key.encode()).hexdigest()[:12], a.get('name'),
                                  len(json.dumps(a, ensure_ascii=False)))
            per[side] = m
        L, D = per.get('local', {}), per.get('demo', {})
        same = [k for k in set(L) & set(D) if L[k][0] == D[k][0]]
        diff_ = [k for k in set(L) & set(D) if L[k][0] != D[k][0]]
        only_d = [k for k in D if k not in L]
        only_l = [k for k in L if k not in D]
        print(f'\n=== {kind} ===  共有={len(set(L)&set(D))} 一致={len(same)} 不一致={len(diff_)} '
              f'仅demo={len(only_d)} 仅本地={len(only_l)}')
        for k in diff_:
            print(f'   ✗ {L[k][1]!r}  local={L[k][0]}({L[k][2]}B)  demo={D[k][0]}({D[k][2]}B)')
        for k in only_d: print(f'   + 仅demo  {D[k][1]!r}')
        for k in only_l: print(f'   - 仅本地  {L[k][1]!r}')
        out[kind] = dict(same=len(same), diff=len(diff_), only_demo=len(only_d), only_local=len(only_l))
    return out

# ---------------- CLI ----------------
def main():
    ap = argparse.ArgumentParser(description='O2OA 应用设计定义 读出/打包/灌入')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('list', help='列出应用')
    p.add_argument('--side', default='both', choices=['local', 'demo', 'both'])
    p.add_argument('--type', default='all', choices=['all', 'portal', 'process', 'query', 'cms'])

    p = sub.add_parser('diff', help='两端全量对齐对比')
    p.add_argument('--type', default='all', choices=['all', 'portal', 'process', 'query', 'cms'])

    p = sub.add_parser('export', help='导出应用为 .xapp')
    p.add_argument('--side', default='demo', choices=['local', 'demo'], help='读定义的来源端')
    p.add_argument('--type', default='portal', choices=['portal', 'process', 'query', 'cms'])
    p.add_argument('--pack-on', default='local', choices=['local', 'demo'], help='执行组包的服务端')
    p.add_argument('--name'); p.add_argument('--id'); p.add_argument('-o', '--out')

    p = sub.add_parser('leadout', help='单流程导出(JSON)')
    p.add_argument('--side', default='demo', choices=['local', 'demo'])
    p.add_argument('--app', required=True); p.add_argument('-o', '--out')

    p = sub.add_parser('import', help='把 .xapp 灌入本地')
    p.add_argument('-f', '--file', required=True)
    p.add_argument('--method', default='create', choices=['create', 'cover'])
    p.add_argument('--dry-run', action='store_true')

    a = ap.parse_args()
    if a.cmd == 'list':
        kinds = list(DESIGNER) if a.type == 'all' else [a.type]
        sides = ['local', 'demo'] if a.side == 'both' else [a.side]
        for side in sides:
            tok = login(side)
            print(f'\n######## {side} ########')
            for kind in kinds:
                apps = list_apps(SIDES[side]['base'], tok, kind)
                print(f'  [{kind}] {len(apps)} 个')
                for x in apps:
                    print(f'     {x.get("name")!r:26s} id={str(x.get("id"))[:8]} alias={x.get("alias")!r}')
    elif a.cmd == 'diff':
        diff(list(DESIGNER) if a.type == 'all' else [a.type])
    elif a.cmd == 'export':
        export(a.side, a.type, a.name, a.id, a.out, a.pack_on)
    elif a.cmd == 'leadout':
        leadout(a.side, a.app, a.out)
    elif a.cmd == 'import':
        do_import(a.file, a.method, a.dry_run)

if __name__ == '__main__':
    main()
