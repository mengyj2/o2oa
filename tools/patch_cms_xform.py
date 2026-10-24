# [cnccia-patch 2026-10-24] 移动端 CMS v10 表单编辑器崩溃外科补丁 v2
# v2: 未压缩版旧文本从文件动态切取（缩进自适应），修交叉断言误报（单文件本无 process 版）
import io, os, shutil, sys

SRC = 'C:/temp/webroot_list/x_component_cms_Xform'
DST = 'D:/o2oaccia/patch/web/x_component_cms_Xform'

KEY_ASSIGN = ('MWF.xApplication.cms.Xform.Datatable = MWF.CMSDatatable = '
              'MWF.xApplication.process.Xform.DatatableV10;')

def extract_old_cms(src):
    """从 CMS 版赋值行反查函数头，正查函数尾，精确切出旧函数体（保留原缩进）。"""
    i = src.find(KEY_ASSIGN)
    if i < 0:
        return None
    head = src.rfind('checkDatatableClass: function (){', 0, i)
    if head < 0:
        return None
    tail = src.find('},', i)
    if tail < 0:
        return None
    return src[head:tail + 2]

def build_new(old):
    """按行重构：守卫 requireApp + 缺类保护，缩进继承旧文本。"""
    out = []
    for ln in old.split('\n'):
        s = ln.strip()
        indent = ln[:len(ln) - len(ln.lstrip())]
        if s == KEY_ASSIGN:
            out.append(indent + '// [O2-CMS-DATATABLE-V10 2026-10-24] 同步补加载 cms.Xform/Datatable，避免 DatatableV10 未加载时 implement 崩溃')
            out.append(indent + 'MWF.xDesktop.requireApp("cms.Xform", "Datatable", null, false);')
            out.append(indent + 'if( MWF.xApplication.process.Xform.DatatableV10 ){')
            inner = indent + '    '
            out.append(inner + KEY_ASSIGN)
            out.append(inner + 'if( MWF.CMSDatatableFeature ) MWF.CMSDatatable.implement(MWF.CMSDatatableFeature);')
            out.append(inner + 'MWF.xApplication.cms.Xform.Datatable$Title = MWF.CMSDatatable$Title = MWF.xApplication.process.Xform.DatatablePC$Title;')
            out.append(inner + 'MWF.xApplication.cms.Xform.Datatable$Data = MWF.CMSDatatable$Data = MWF.xApplication.process.Xform.DatatablePC$Data;')
            out.append(indent + '}')
        elif s in ('MWF.CMSDatatable.implement(MWF.CMSDatatableFeature);',
                   'MWF.xApplication.cms.Xform.Datatable$Title = MWF.CMSDatatable$Title = MWF.xApplication.process.Xform.DatatablePC$Title;',
                   'MWF.xApplication.cms.Xform.Datatable$Data = MWF.CMSDatatable$Data = MWF.xApplication.process.Xform.DatatablePC$Data;'):
            continue  # 已被守卫版内联替代
        else:
            out.append(ln)
    return '\n'.join(out)

OLD_MIN = ('checkDatatableClass:function(){(layout.mobile||COMMON.Browser.Platform.isMobile)'
           '&&"v10"===this.json.formStyleType&&(MWF.xApplication.cms.Xform.Datatable='
           'MWF.CMSDatatable=MWF.xApplication.process.Xform.DatatableV10,'
           'MWF.CMSDatatable.implement(MWF.CMSDatatableFeature),'
           'MWF.xApplication.cms.Xform.Datatable$Title=MWF.CMSDatatable$Title='
           'MWF.xApplication.process.Xform.DatatablePC$Title,'
           'MWF.xApplication.cms.Xform.Datatable$Data=MWF.CMSDatatable$Data='
           'MWF.xApplication.process.Xform.DatatablePC$Data)}')

NEW_MIN = ('checkDatatableClass:function(){(layout.mobile||COMMON.Browser.Platform.isMobile)'
           '&&"v10"===this.json.formStyleType&&(MWF.xDesktop.requireApp("cms.Xform","Datatable",null,!1),'
           'MWF.xApplication.process.Xform.DatatableV10&&('
           'MWF.xApplication.cms.Xform.Datatable=MWF.CMSDatatable=MWF.xApplication.process.Xform.DatatableV10,'
           'MWF.CMSDatatableFeature&&MWF.CMSDatatable.implement(MWF.CMSDatatableFeature),'
           'MWF.xApplication.cms.Xform.Datatable$Title=MWF.CMSDatatable$Title='
           'MWF.xApplication.process.Xform.DatatablePC$Title,'
           'MWF.xApplication.cms.Xform.Datatable$Data=MWF.CMSDatatable$Data='
           'MWF.xApplication.process.Xform.DatatablePC$Data))}')

UNCOMPRESSED = ['Form.js', '$all.js']       # 旧文本动态切取
MINIFIED = ['Form.min.js', '$all.min.js']   # 固定 min 形态
NEED_PROC_INTACT = {'$all.min.js'}          # 仅全量 concat 含 process 版定义

os.makedirs(DST, exist_ok=True)
# 清理上一轮已落盘产物（.orig 除外，保持幂等）
for f in os.listdir(DST):
    if f.endswith('.orig'):
        continue
    os.remove(os.path.join(DST, f))

ok = True
for name in UNCOMPRESSED + MINIFIED:
    sp = os.path.join(SRC, name)
    dp = os.path.join(DST, name)
    with io.open(sp, encoding='utf-8') as f:
        s = f.read()
    if name in UNCOMPRESSED:
        old = extract_old_cms(s)
        if old is None:
            print(f'[FAIL] {name}: 未能切取 CMS 版旧函数'); ok = False; continue
        new = build_new(old)
        if s.count(old) != 1:
            print(f'[FAIL] {name}: 旧函数出现 {s.count(old)} 次'); ok = False; continue
        patched = s.replace(old, new)
    else:
        old, new = OLD_MIN, NEW_MIN
        if s.count(old) != 1:
            print(f'[FAIL] {name}: min 旧形态出现 {s.count(old)} 次'); ok = False; continue
        patched = s.replace(old, new)

    with io.open(dp, 'w', encoding='utf-8', newline='') as f:
        f.write(patched)

    # 交叉断言
    resid = patched.count(old)
    new_marker = patched.count('MWF.xDesktop.requireApp("cms.Xform", "Datatable"') \
        + patched.count('MWF.xDesktop.requireApp("cms.Xform","Datatable"')
    proc_intact = patched.count('MWF.xApplication.process.Xform.Datatable = MWF.APPDatatable = MWF.xApplication.process.Xform.DatatableV10') \
        + patched.count('MWF.xApplication.process.Xform.Datatable=MWF.APPDatatable=MWF.xApplication.process.Xform.DatatableV10')
    checks = [resid == 0, new_marker >= 1]
    if name in NEED_PROC_INTACT:
        checks.append(proc_intact == 1)
    status = 'OK' if all(checks) else 'FAIL'
    if status == 'FAIL':
        ok = False
    print(f'[{status}] {name}: residual={resid}, new_marker={new_marker}, '
          f'proc_intact={proc_intact}{"(n/a单文件)" if name not in NEED_PROC_INTACT else ""}, '
          f'size {len(s)} -> {len(patched)}')

for name in ['Form.js', '$all.js', 'Form.min.js', '$all.min.js']:
    bak = os.path.join(DST, name + '.orig')
    if not os.path.exists(bak):
        shutil.copy2(os.path.join(SRC, name), bak)

print('ALL-OK' if ok else 'HAS-FAILURES')
sys.exit(0 if ok else 1)
