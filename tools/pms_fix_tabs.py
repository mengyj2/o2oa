# -*- coding: utf-8 -*-
"""修复 PMS 10 个门户页面的页签问题
根因：
 A. 门户页/启动页 label_4_1 与原有模块 id 冲突 -> 注入的「进度管控」页签被覆盖丢失
 B. 克隆页 label_3 文本被误改成本页名（重复页签 + click 指向项目全景）
 C. 注入页签 click code 含字面反斜杠 toPage(\"X\") -> 非法 JS，点击必报错
 D. active 高亮错位（每页都没落在本页页签上）
 E. 页签 fs=18px/pad=20px 太宽 -> 10 页签溢出换行且 float:right 换行破碎
"""
import o2, json, sys

tok = o2.login()

PAGES = {
 '项目管理门户':'ac658a6c-7490-45f2-a58d-2a393449407b',
 '项目启动':'2645f984-dfea-4227-b073-adfc038bb65d',
 '项目全景':'803cf71c-19e5-40d4-b3d8-f83375eee343',
 '进度管控':'da33e5b4-4ef6-4c21-a448-22e400f316ca',
 '成本管理':'4791e4bf-f453-4bbc-8cd7-57a777dae48d',
 '质量管理':'0037c97d-69c2-4721-aead-b1467656f521',
 '风险管理':'59befd75-45a8-487c-872c-a099cb9066bc',
 '相关方管理':'780d611b-562c-4b47-b9b5-d35668c9d1cf',
 '合同管理':'f5d65824-950e-4bff-baae-73aa9c0722be',
 '项目收尾':'05d50fcf-2a27-4611-8f8e-37b3bf98176a',
}
CLONE_PAGES = ['进度管控','成本管理','质量管理','风险管理','相关方管理','合同管理','项目收尾']
TAB_IDS = ['label_2','label_3','label_4','label_4_1','label_4_2','label_4_3',
           'label_4_4','label_4_5','label_4_6','label_4_7']

def load(pid):
    st, j = o2._req('GET', '/x_portal_assemble_designer/jaxrs/page/'+pid, tok)
    inner = json.loads(json.loads('"'+j['data']['data']+'"'))
    return inner

def save(pid, inner):
    inner_str = json.dumps(inner, ensure_ascii=False, separators=(',',':'))
    data_field = json.dumps(inner_str, ensure_ascii=False)[1:-1]
    st, r = o2._req('PUT', '/x_portal_assemble_designer/jaxrs/page/'+pid, tok,
                    body={'data': data_field})
    return st, r

def fix(page_name, pid, dry=True):
    inner = load(pid)
    ml = inner['json']['moduleList']
    log = []
    # --- A/B 前置修复 ---
    if page_name in ('项目管理门户','项目启动'):
        m = ml['label_4_1']
        m['text'] = '进度管控'
        m['styles'] = {'float':'right','font-size':'14px','padding':'0px 7px'}
        ev = m.setdefault('events',{}).setdefault('click',{})
        ev['code'] = ev['html'] = 'this.page.toPage("进度管控")'
        log.append('A: label_4_1 改造为「进度管控」页签')
    if page_name in CLONE_PAGES:
        m3 = ml['label_3']
        if m3.get('text') == page_name:
            m3['text'] = '项目全景'
            log.append('B: label_3 文本恢复「项目全景」')
    # --- C/D/E 统一规范 ---
    for tid in TAB_IDS:
        m = ml.get(tid)
        if not isinstance(m, dict): continue
        txt = str(m.get('text') or '')
        if txt not in PAGES:  # 不是 10 模块页签（如残留「项目名称」）跳过
            continue
        stys = m.setdefault('styles', {})
        stys['float'] = 'right'
        stys['font-size'] = '14px'
        stys['padding'] = '0px 7px'
        if txt == page_name:
            stys['background-color'] = '#4381cb'
        else:
            stys.pop('background-color', None)
        ev = m.setdefault('events',{}).setdefault('click',{})
        clean = 'this.page.toPage("%s")' % txt
        if ev.get('code') and 'toPage' in ev['code']:
            ev['code'] = clean
            log.append('C: %s click 规范化' % tid)
        elif not ev.get('code'):
            ev['code'] = clean  # 无 click 的页签（不该有，兜底）
            log.append('C+: %s click 补齐' % tid)
        if ev.get('html') and 'toPage' in ev['html']:
            ev['html'] = clean
    # label_1 空占位清 padding
    l1 = ml.get('label_1')
    if isinstance(l1, dict):
        l1.setdefault('styles', {})['padding'] = '0px'
    # logo 标题字号
    lg = ml.get('label')
    if isinstance(lg, dict):
        lg.setdefault('styles', {})['font-size'] = '22px'
    # 门户页面包屑一级
    if page_name == '项目管理门户':
        l7 = ml.get('label_7')
        if isinstance(l7, dict) and l7.get('text') == '项目管理门户':
            l7['text'] = '项目管理'
            log.append('面包屑: label_7 -> 项目管理')
    # 校验页签完整性
    got = sorted([str(ml[t]['text']) for t in TAB_IDS
                  if isinstance(ml.get(t), dict) and str(ml[t].get('text') or '') in PAGES])
    expect = sorted(PAGES.keys())
    ok = (got == expect)
    print('== %s == tabs_ok=%s' % (page_name, ok))
    if not ok:
        print('  got:', got)
    for l in log:
        print('  ', l)
    if dry:
        print('  [dry-run] 未保存')
        return ok
    st, r = save(pid, inner)
    ok2 = isinstance(r, dict) and r.get('type') == 'success'
    print('   save:', st, ok2)
    return ok and ok2

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'dry'
    if mode == 'one-dry':
        fix('项目管理门户', PAGES['项目管理门户'], dry=True)
    elif mode == 'one':
        fix('项目管理门户', PAGES['项目管理门户'], dry=False)
    elif mode == 'all':
        bad = []
        for pname, pid in PAGES.items():
            if not fix(pname, pid, dry=False):
                bad.append(pname)
        print('FAILED:', bad if bad else 'none')
