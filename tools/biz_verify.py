# -*- coding: utf-8 -*-
"""biz_verify.py — 经营管理平台 5 应用端到端验证（安装后）"""
import json, sys, glob, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2

TOK = o2.login()
print('login ok')

# 期望应用（从生成目录读 xapp）
EXPECT = {}
for p in sorted(glob.glob('C:/temp/biz/*.xapp.json')):
    x = json.load(open(p, encoding='utf-8'))
    EXPECT[x['name']] = x

fails = []
def chk(name, ok, detail=''):
    print(('  ✅' if ok else '  ❌'), name, detail)
    if not ok:
        fails.append(name)

# 1. 流程平台应用
st, j = o2.get('/x_processplatform_assemble_designer/jaxrs/application/list', TOK)
apps = (j.get('data') or []) if isinstance(j, dict) else []
app_by_name = {a.get('name'): a for a in apps}
print('== 流程平台应用 ==')
for name in EXPECT:
    chk(name, name in app_by_name, app_by_name.get(name, {}).get('id', ''))

# 2. 每应用：流程/表单/门户页/视图/统计
print('== 资源计数 ==')
portals = {}
st, j = o2.get('/x_portal_assemble_designer/jaxrs/portal/list', TOK)
for p in (j.get('data') or []):
    portals[p.get('name')] = p
queries = {}
st, j = o2.get('/x_query_assemble_designer/jaxrs/query/list/all', TOK)
for q in (j.get('data') or []):
    queries[q.get('name')] = q

for name, x in EXPECT.items():
    want_p = len(x['processPlatformList'][0]['processList'])
    want_f = len(x['processPlatformList'][0]['formList'])
    a = app_by_name.get(name, {})
    aid = a.get('id', '')
    st, j2 = o2.get('/x_processplatform_assemble_designer/jaxrs/process/application/%s' % aid, TOK)
    procs = (j2.get('data') or []) if isinstance(j2, dict) else []
    st, j2 = o2.get('/x_processplatform_assemble_designer/jaxrs/form/list/application/%s' % aid, TOK)
    forms = (j2.get('data') or []) if isinstance(j2, dict) else []
    portal = portals.get(name + '门户', {})
    q = queries.get(name + '查询', {})
    nv = len(q.get('viewList') or [])
    ns = len(q.get('statList') or [])
    # 门户页数：page/list/portal/{pid}
    npg = 0
    if portal.get('id'):
        st, j2 = o2.get('/x_portal_assemble_designer/jaxrs/page/list/portal/%s' % portal['id'], TOK)
        npg = len((j2.get('data') or [])) if isinstance(j2, dict) else 0
    chk('%s:流程' % name, len(procs) == want_p, '%d/%d' % (len(procs), want_p))
    chk('%s:表单' % name, len(forms) == want_f, '%d/%d' % (len(forms), want_f))
    chk('%s:门户页' % name, npg == len(x['portalList'][0]['pageList']), '%d' % npg)
    chk('%s:视图' % name, nv == len(x['queryList'][0]['viewList']), '%d' % nv)
    chk('%s:统计' % name, ns == len(x['queryList'][0]['statList']), '%d' % ns)

# 3. 视图 execute（PM 项目台账 + FM 付款台账）
print('== 视图 execute ==')
def view_exec(qname, vname):
    q = queries.get(qname, {})
    for v in (q.get('viewList') or []):
        if v.get('name') == vname:
            st, j2 = o2.put('/x_query_assemble_surface/jaxrs/view/%s/execute' % v['id'],
                            {"filterList": []}, TOK)
            ok = st == 200 and isinstance(j2, dict) and j2.get('type') == 'success'
            return ok, st
    return False, 'notfound'
chk('PM 项目台账 execute', *view_exec('项目管理查询', '项目台账'))
chk('FM 付款台账 execute', *view_exec('财务管理查询', '付款台账'))

# 4. 发起流程实测（PM 项目立项）
print('== 发起流程实测（switchuser 测试用户A）==')
aid = app_by_name['项目管理']['id']
st, j2 = o2.get('/x_processplatform_assemble_designer/jaxrs/process/application/%s' % aid, TOK)
proc = [p for p in (j2.get('data') or []) if p.get('name') == '项目立项'][0]
pid = proc['id']
# xadmin 是虚拟管理员无组织身份，须切到真实用户发起
st, j2 = o2.put('/x_organization_assemble_authentication/jaxrs/authentication/switchuser',
                {'credential': '测试用户A'}, TOK)
utok = (j2.get('data') or {}).get('token') if isinstance(j2, dict) else None
chk('switchuser 测试用户A', bool(utok))
ok = bool(utok)
detail = ''
if ok:
    st, j2 = o2.post('/x_processplatform_assemble_surface/jaxrs/work/application/%s/process/%s'
                     % (aid, pid), {}, utok)
    ok = st == 200 and isinstance(j2, dict) and j2.get('type') == 'success'
    if ok:
        dd = j2.get('data') or []
        o0 = dd[0] if dd else {}
        wid = o0.get('work') or o0.get('workId') or o0.get('id')
        detail = 'work=%s' % wid
        # 断言：待办生成且活动=填报
        st3, j3 = o2.get('/x_processplatform_assemble_surface/jaxrs/task/list/work/%s' % wid, utok)
        tasks = j3.get('data') or [] if isinstance(j3, dict) else []
        if isinstance(tasks, dict):
            tasks = tasks.get('taskList') or []
        t_ok = bool(tasks) and tasks[0].get('activityName') == '填报'
        detail += ' task=%s' % (tasks[0].get('activityName') if tasks else '无')
        chk('发起后待办生成(填报)', t_ok)
        # 清理：删除测试 work（DELETE /work/{id}/manage 是 GET 查询路由，须用 single/manage）
        if wid:
            st2, _ = o2._req('DELETE', '/x_processplatform_assemble_surface/jaxrs/work/%s/single/manage' % wid, TOK)
            detail += ' cleanup=%s' % st2
chk('发起 项目立项', ok, detail)

# 5. 门户页面 HTTP 可达
print('== 门户可达 ==')
import urllib.request
pm_portal = portals.get('项目管理门户', {})
u = 'http://localhost:9090/x_desktop/portal.html?id=%s' % pm_portal.get('id', '')
req = urllib.request.Request(u, headers={'Cookie': 'x-token=%s' % TOK})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        chk('portal.html 200', r.status == 200, str(r.status))
except Exception as e:
    chk('portal.html 200', False, str(e))

print()
print('FAILS:', fails if fails else '无 — 全部通过')
