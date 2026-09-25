# -*- coding: utf-8 -*-
"""biz_teardown.py — 拆除自建 5 应用（项目管理/合同/预算/财务/档案）+ 门户 + 查询
用法: python tools/biz_teardown.py            # 备份确认后执行删除
      python tools/biz_teardown.py --recheck  # 仅复查残留
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2

APPS = {
    '项目管理': '9cdb2271-f56e-4ece-8308-5fa9ceebf025',
    '合同管理': '55661277-c6cf-4970-a1cc-9249eb028957',
    '预算管理': '4bd199c7-9071-4f2e-97ee-8698fa34f2e5',
    '财务管理': '52107846-8cc0-41c2-8d66-5ebd41628d7f',
    '档案管理': '18ff0664-fbf9-4743-a477-f1028bb6b9b6',
}
PORTALS = {
    '项目管理门户': 'b1652699-7c48-4d2c-917b-13f7a2016d04',
    '合同管理门户': '883aff10-689a-444d-bdcc-3856b8719903',
    '预算管理门户': 'fc3ea8bb-1da3-4bed-b7ac-b1a5c7b73d9f',
    '财务管理门户': '7506ec3a-f176-48c7-b4c3-ed77fffc397f',
    '档案管理门户': 'ad5d71e1-a260-4f45-a6b9-1d625d8c9219',
}
QUERIES = {
    '项目管理查询': 'eee23855-01aa-490e-a421-b9ed2213c3da',
    '合同管理查询': '3bbd52b0-f2fc-48f5-86ea-bf8aee4802c3',
    '预算管理查询': '94d0da9e-a1de-44bd-b17c-899062bd39ee',
    '财务管理查询': '1588be8d-ee84-403b-808d-f4838329abcd',
    '档案管理查询': 'ac55dc41-f647-4f6f-aa08-fcf37ebda5af',
}
WORKCOMPLETED = ['e5020148-facf-4248-895b-53b01a1ce722']  # 示例办结单


def brief(j, n=110):
    return json.dumps(j, ensure_ascii=False)[:n] if not isinstance(j, str) else j[:n]


def recheck():
    TOK = o2.login()
    left = {}
    st, j = o2.get('/x_processplatform_assemble_designer/jaxrs/application/list', TOK)
    left['apps'] = [a.get('name') for a in (j.get('data') or [])
                    if isinstance(a, dict) and a.get('name') in APPS]
    st, j = o2.get('/x_portal_assemble_designer/jaxrs/portal/list', TOK)
    left['portals'] = [p.get('name') for p in (j.get('data') or [])
                       if isinstance(p, dict) and p.get('name') in PORTALS]
    st, j = o2.get('/x_query_assemble_designer/jaxrs/query/list/all', TOK)
    left['queries'] = [q.get('name') for q in (j.get('data') or [])
                       if isinstance(q, dict) and q.get('name') in QUERIES]
    print('残留: %s' % json.dumps(left, ensure_ascii=False))
    return left


def teardown():
    TOK = o2.login()
    print('== 1. 清理流程实例（已办单）==')
    for wid in WORKCOMPLETED:
        st, j = o2._req('DELETE',
                        '/x_processplatform_assemble_surface/jaxrs/workcompleted/%s/delete/manage' % wid, TOK)
        print('  workcompleted %s -> %s %s' % (wid, st, brief(j)))
    print('== 2. 删流程应用 ==')
    for name, aid in APPS.items():
        st, j = o2._req('DELETE',
                        '/x_processplatform_assemble_designer/jaxrs/application/%s/false' % aid, TOK)
        ok = st in (200, 500)  # 空应用 500 属正常
        print('  %-8s -> %s %s' % (name, st, brief(j)))
    print('== 3. 删门户 ==')
    for name, pid in PORTALS.items():
        st, j = o2._req('DELETE',
                        '/x_portal_assemble_designer/jaxrs/portal/%s' % pid, TOK)
        print('  %-10s -> %s %s' % (name, st, brief(j)))
    print('== 4. 删查询 ==')
    for name, qid in QUERIES.items():
        st, j = o2._req('DELETE',
                        '/x_query_assemble_designer/jaxrs/query/%s' % qid, TOK)
        print('  %-10s -> %s %s' % (name, st, brief(j)))
    print('== 5. 复查 ==')
    left = recheck()
    clean = not any(left.values())
    print('RESULT: %s' % ('全部删除干净 ✅' if clean else '仍有残留，需重启容器后再复查 ❌'))
    return clean


if __name__ == '__main__':
    if '--recheck' in sys.argv:
        recheck()
    else:
        teardown()
