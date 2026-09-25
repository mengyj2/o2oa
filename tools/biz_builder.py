# -*- coding: utf-8 -*-
"""biz_builder.py — 经营管理平台 5 应用生成器（项目管理/合同/预算/财务/档案）
声明式定义 → 5 个独立 xapp（portal + process + query 自包含）
"""
import json, uuid, copy, sys, os

TS = "2026-09-19 22:30:00"
BY = "xadmin@P"
SRC_XAPP = 'D:/O2OA/tools/pms_final.xapp.json'

def nid(): return str(uuid.uuid4())

# ---------------- 模板加载 ----------------
_TPL = json.load(open(SRC_XAPP, encoding='utf-8'))
_PP = _TPL['processPlatformList'][0]
_PORTAL = _TPL['portalList'][0]
_QUERY = _TPL['queryList'][0]

def _page_data(page):
    return json.loads(json.loads('"' + page['data'] + '"'))

# 页面/表单顶层骨架
_PG = [p for p in _PORTAL['pageList'] if p['name'] == '项目管理门户'][0]
PG_JSON = _page_data(_PG)['json']
FRM = [f for f in _PP['formList'] if f['name'] == '任务登记表'][0]
FRM_JSON = _page_data(FRM)['json']

def _find_mod(ml, mtype):
    for m in ml.values():
        if isinstance(m, dict) and m.get('type') == mtype:
            return m
    return None

VIEW_TPL = _find_mod(PG_JSON['moduleList'], 'View')
STAT_TPL = _find_mod(PG_JSON['moduleList'], 'Stat')
PROC_TPL = json.load(open('C:/temp/tpl_process.json', encoding='utf-8'))
P_BEGIN = copy.deepcopy(PROC_TPL['begin'])
P_MANUAL = copy.deepcopy([m for m in PROC_TPL['manualList'] if m['name'] == '风险登记'][0])
P_ROUTE = copy.deepcopy(PROC_TPL['routeList'][0])
P_END = copy.deepcopy(PROC_TPL['endList'][0])

EVT_KEYS = ("click", "dblclick", "mousedown", "mouseup", "mousemove",
            "mouseout", "mouseover", "load", "change", "select")
def evts(**kw):
    d = {k: {"code": "", "html": ""} for k in EVT_KEYS}
    for k, v in kw.items():
        d[k] = {"code": v, "html": v}
    return d

def esc_d(obj):
    """对象 → 双层转义 data 字符串"""
    s = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return json.dumps(s, ensure_ascii=False)[1:-1]

# ---------------- 页面生成 ----------------
class Page:
    """树形容器模型：open_div/close_div 栈式嵌套，html() 递归渲染真实层级"""
    def __init__(self, app, name):
        self.app = app
        self.name = name
        self.pid = nid()
        self.mods = {}              # id -> module dict
        self.kids = {}              # parent_mid -> [child_mid...]
        self.roots = []
        self.stack = []
        self.node_style = {}        # mid -> style str
        self.node_mwt = {}          # mid -> mwftype
        self.node_text = {}         # mid -> inner text（label）

    def _attach(self, mid):
        if self.stack:
            self.kids.setdefault(self.stack[-1], []).append(mid)
        else:
            self.roots.append(mid)

    def add(self, mid, module, mwftype, style='', inner=''):
        module['pid'] = 'PC' + self.pid + mid
        self.mods[mid] = module
        self.node_mwt[mid] = mwftype
        self.node_style[mid] = style or ''
        self.node_text[mid] = inner or ''
        self._attach(mid)
        return mid

    def open_div(self, mid, styles=None, click=None, load=None):
        m = {"id": mid, "name": "", "type": "Div", "description": "",
             "defaultValue": {"code": "", "html": ""},
             "events": evts(**({"click": click} if click else ({})),
                            **({"load": load} if load else ({}))),
             "properties": {}, "styles": styles or {},
             "script": {"code": "", "html": ""},
             "sections": {}, "isSaved": True, "moduleName": "div",
             "recoveryStyles": {}}
        self.add(mid, m, 'div', style_str(styles or {}))
        self.stack.append(mid)
        return mid

    def div(self, mid, styles=None, click=None, load=None):
        self.open_div(mid, styles, click, load)
        self.close_div()
        return mid

    def close_div(self):
        if self.stack:
            self.stack.pop()

    def label(self, mid, text, styles=None, click=None):
        m = {"id": mid, "name": "", "type": "Label", "description": "",
             "valueType": "text", "text": text,
             "script": {"code": "", "html": ""},
             "events": evts(**({"click": click} if click else ({}))),
             "properties": {}, "styles": styles or {},
             "class": "", "isSaved": True, "moduleName": "label",
             "recoveryStyles": {}}
        return self.add(mid, m, 'label', style_str(styles or {}), inner=text)

    def view_mod(self, mid, view_id, view_name, styles=None):
        m = copy.deepcopy(VIEW_TPL)
        m['id'] = mid
        m['queryView'] = {"name": view_name, "id": view_id,
                          "appName": self.app['name'], "application": self.app['query_id']}
        m['styles'] = styles or {}
        return self.add(mid, m, 'view', style_str(styles or {}))

    def stat_mod(self, mid, stat_id, stat_name, styles=None, chart='yes'):
        m = copy.deepcopy(STAT_TPL)
        m['id'] = mid
        m['queryStat'] = {"name": stat_name, "id": stat_id,
                          "appName": self.app['name'], "application": self.app['query_id']}
        m['isChart'] = chart
        m['isLegend'] = chart
        m['isTable'] = 'no'
        m['styles'] = styles or {}
        return self.add(mid, m, 'stat', style_str(styles or {}))

    def render_node(self, mid):
        st = self.node_style.get(mid, '')
        mwt = self.node_mwt.get(mid, 'div')
        inner = self.node_text.get(mid, '')
        for c in self.kids.get(mid, []):
            inner += self.render_node(c)
        return '<div id="%s" mwftype="%s" style="%s">%s</div>' % (mid, mwt, st, inner)

    def html(self):
        return ''.join(self.render_node(mid) for mid in self.roots)

    def build(self, load_script=None):
        j = copy.deepcopy(PG_JSON)
        j['id'] = self.pid
        j['name'] = self.name
        j['alias'] = ''
        j['application'] = self.app['portal_id']
        j['applicationName'] = self.app['name']
        j['moduleList'] = self.mods
        j['css'] = {"code": ""}
        j['pid'] = self.pid
        if load_script:
            j.setdefault('events', {})['load'] = {"code": load_script, "html": ""}
        return {"id": self.pid, "name": self.name, "alias": "",
                "data": esc_d({"json": j, "html": self.html(), "id": self.pid,
                               "isNewPage": False})}

# ---------------- UI 组件 ----------------
NAV_W = 220
def nav_html(app, pages, active):
    """左侧导航 html（纯 html，点击跳转用 onclick 属性? 页面渲染时 mwftype=div+模块事件；
    导航子项用 Label 模块（click 事件）——所以导航也要进 moduleList。
    为控制模块数量：导航直接以 Label 模块生成。"""
    parts = []
    mods = []
    return parts, mods

def style_str(d):
    return '; '.join(f'{k}: {v}' for k, v in d.items() if v is not None)

def build_page_shell(page, app, title, active_page, load_script=None):
    """公共壳：左导航 + 顶栏 + 内容容器（栈式嵌套）。"""
    # 根
    page.open_div('app_root', {'display': 'flex', 'width': '100%', 'min-height': '100vh',
                               'background': '#f0f2f5',
                               'font-family': 'Microsoft YaHei, PingFang SC, sans-serif'})
    # 左导航
    page.open_div('nav_side', {'width': f'{NAV_W}px', 'min-width': f'{NAV_W}px',
                               'background': '#ffffff',
                               'box-shadow': '2px 0 8px rgba(0,0,0,0.06)',
                               'min-height': '100vh', 'position': 'relative', 'z-index': '10'})
    page.open_div('nav_logo', {'height': '60px', 'display': 'flex', 'align-items': 'center',
                               'padding': '0 16px', 'border-bottom': '1px solid #f0f0f0'})
    page.open_div('nav_logo_icon', {'width': '30px', 'height': '30px', 'border-radius': '6px',
                                    'background': app['color'], 'color': '#fff',
                                    'text-align': 'center', 'line-height': '30px',
                                    'font-size': '16px', 'font-weight': 'bold',
                                    'margin-right': '8px'})
    page.label('nav_logo_icon_t', app['icon'], {'font-size': '16px'})
    page.close_div()   # icon
    page.label('nav_logo_name', app['name'], {'font-size': '16px', 'font-weight': 'bold',
                                              'color': '#1f2d3d'})
    page.close_div()   # logo
    for g in app['nav']:
        page.label('nav_g_' + g['key'], g['name'],
                   {'display': 'block', 'padding': '10px 16px 4px', 'font-size': '12px',
                    'color': '#9aa5b1'})
        for idx, it in enumerate(g['items']):
            name, target = it[0], it[1]
            act = (target == active_page)
            st = {'display': 'block', 'padding': '9px 16px 9px 28px', 'font-size': '14px',
                  'cursor': 'pointer', 'color': '#1a66ff' if act else '#3c4653',
                  'background': '#e8f0fe' if act else 'transparent',
                  'border-left': '3px solid #1a66ff' if act else '3px solid transparent'}
            if act:
                st['font-weight'] = 'bold'
            page.label('nav_i_%s_%d' % (g['key'], idx), name, st,
                       click=f'this.page.toPage("{target}")')
    page.close_div()   # nav_side
    # 主区
    page.open_div('main_area', {'flex': '1', 'display': 'flex', 'flex-direction': 'column',
                                'min-width': '0'})
    page.open_div('topbar', {'height': '60px', 'background': '#ffffff', 'display': 'flex',
                             'align-items': 'center', 'padding': '0 24px',
                             'box-shadow': '0 1px 4px rgba(0,0,0,0.05)'})
    page.label('tb_title', title, {'font-size': '17px', 'font-weight': 'bold',
                                   'color': '#1f2d3d'})
    page.label('tb_user', '管理员', {'margin-left': 'auto', 'font-size': '13px',
                                     'color': '#5a6473'})
    page.close_div()   # topbar
    page.open_div('content', {'flex': '1', 'padding': '24px', 'overflow': 'auto'})
    # content 保持 open，由页面内容继续填充（main_area / app_root 亦保持 open）
    return 'content'

def add_app_switch(page, app):
    """页尾应用切换区（content 关闭前调用）"""
    page.label('switch_head', '— 应用切换 —',
               {'display': 'block', 'margin-top': '28px', 'font-size': '11px',
                'color': '#b6bfca', 'text-align': 'center'})
    for other in APP_SWITCH:
        if other[1] != app['portal_id']:
            page.label('sw_' + other[1][:8], other[0],
                       {'display': 'block', 'padding': '6px 28px', 'font-size': '13px',
                        'color': '#1a66ff', 'cursor': 'pointer'},
                       click=f'window.open("/x_desktop/portal.html?id={other[1]}", "_blank")')

def card(page, prefix, label, color, icon):
    """统计卡（栈式：卡>行>图标块+文字列），返回数字 label id"""
    page.open_div(prefix + '_card', {'background': '#ffffff', 'border-radius': '10px',
                                     'box-shadow': '0 2px 8px rgba(0,0,0,0.05)',
                                     'padding': '20px', 'flex': '1', 'min-width': '200px'})
    page.open_div(prefix + '_row', {'display': 'flex', 'align-items': 'center'})
    page.open_div(prefix + '_icon', {'width': '44px', 'height': '44px', 'border-radius': '10px',
                                     'background': color, 'color': '#fff', 'text-align': 'center',
                                     'line-height': '44px', 'font-size': '20px',
                                     'margin-right': '14px', 'flex-shrink': '0'})
    page.label(prefix + '_ig', icon, {'font-size': '20px'})
    page.close_div()   # icon
    page.open_div(prefix + '_col', {'flex': '1'})
    page.label(prefix + '_num', '—', {'display': 'block', 'font-size': '26px',
                                      'font-weight': 'bold', 'color': '#1f2d3d',
                                      'line-height': '32px'})
    page.label(prefix + '_lb', label, {'display': 'block', 'font-size': '13px',
                                       'color': '#8a94a3', 'margin-top': '2px'})
    page.close_div()   # col
    page.close_div()   # row
    page.close_div()   # card
    return prefix + '_num'

def panel(page, mid, title, styles=None):
    """白卡面板：open 面板并写入标题，调用方填内容后须 page.close_div() 关闭。返回面板 mid"""
    page.open_div(mid, {'background': '#ffffff', 'border-radius': '10px',
                        'box-shadow': '0 2px 8px rgba(0,0,0,0.05)', 'padding': '18px',
                        'margin-top': '16px', **(styles or {})})
    page.label(mid + '_t', title, {'display': 'block', 'font-size': '15px',
                                   'font-weight': 'bold', 'color': '#1f2d3d',
                                   'margin-bottom': '10px'})
    return mid

def section_title(page, mid, text):
    page.label(mid, text, {'display': 'block', 'font-size': '15px', 'font-weight': 'bold',
                           'color': '#1f2d3d', 'margin': '18px 0 10px'})

# 仪表盘取数脚本
DASH_JS = """
(function(){
  var page = this.page;
  function el(id){ var m = page.get(id); return (m && m.node) ? m.node : null; }
  try{
    var qa = this.Actions.load("x_query_assemble_surface");
    var va = qa.ViewAction;
    var fn = va.ExecuteV2 || va.executeV2 || va.Execute || va.execute || va.flag_query_execute;
    if(!fn){ return; }
    var jobs = __JOBS__;
    jobs.forEach(function(j){
      try{
        fn.call(va, j.view, {"filterList":[]}, function(json){
          var n = "-";
          var d = (json && json.data) || {};
          if(j.mode === "sum"){
            var g = d.grid || []; var s = 0;
            for(var i=0;i<g.length;i++){ var v = parseFloat(g[i][j.column]); if(!isNaN(v)) s += v; }
            n = Math.round(s*100)/100;
          } else {
            n = (d.count != null) ? d.count : (d.grid ? d.grid.length : "-");
          }
          var e = el(j.el); if(e) e.innerText = String(n) + (j.unit || "");
        });
      }catch(e2){}
    });
  }catch(e){}
})();
"""

# ---------------- 表单生成 ----------------
CTRL_TYPES = {}
def ctrl_textfield(fid, label):
    return {"id": fid, "name": label, "type": "Textfield", "dataType": "text",
            "defaultValue": {"code": "", "html": ""}, "compute": "create",
            "section": "no", "sectionBy": "person", "inputType": "text",
            "isSaved": True, "moduleName": "textfield", "validationConfig": [],
            "events": evts(), "styles": {}, "recoveryStyles": {}}

def ctrl_number(fid, label):
    m = ctrl_textfield(fid, label)
    m.update({"type": "Number", "moduleName": "number", "dataType": "double",
              "inputType": "number"})
    return m

def ctrl_calendar(fid, label):
    m = ctrl_textfield(fid, label)
    m.update({"type": "Calendar", "moduleName": "calendar", "dataType": "dateTime",
              "formatType": "datetime", "inputType": "datetime-local"})
    return m

def ctrl_select(fid, label, options, dict_name=None, dict_key=None):
    if dict_name:
        code = 'var dict = new this.Dict("%s");\r\nreturn dict.get("%s");' % (dict_name, dict_key)
        return {"id": fid, "name": label, "type": "Select", "itemType": "script",
                "itemValues": [], "itemScript": {"code": code, "html": code},
                "defaultValue": {"code": "", "html": ""}, "compute": "create",
                "section": "no", "isSaved": True, "moduleName": "select",
                "validationConfig": [], "events": evts(), "styles": {}, "recoveryStyles": {}}
    return {"id": fid, "name": label, "type": "Select", "itemType": "value",
            "itemValues": ["%s|%s" % (o, o) for o in options],
            "defaultValue": {"code": "", "html": ""}, "compute": "create",
            "section": "no", "isSaved": True, "moduleName": "select",
            "validationConfig": [], "events": evts(), "styles": {}, "recoveryStyles": {}}

def ctrl_person(fid, label, select_type="identity"):
    return {"id": fid, "name": label, "type": "Personfield", "moduleName": "personfield",
            "selectType": select_type, "defaultValue": {"code": "", "html": ""},
            "compute": "create", "section": "no", "isSaved": True,
            "validationConfig": [], "events": evts(), "styles": {}, "recoveryStyles": {}}

def ctrl_textarea(fid, label):
    m = ctrl_textfield(fid, label)
    m.update({"type": "Textarea", "moduleName": "textarea",
              "properties": {"rows": "4"}})
    return m

FORM_MWFT = {'text': 'textfield', 'textfield': 'textfield', 'number': 'number', 'date': 'calendar',
             'select': 'select', 'person': 'personfield', 'org': 'personfield',
             'textarea': 'textarea'}

FID_SEQ = [0]
def uniq_fid(base):
    """字段 id 全局唯一化：PP_E_FORMFIELD.xid 是主键，语义短 id 会撞键"""
    FID_SEQ[0] += 1
    return '%s__f%02d' % (base, FID_SEQ[0])

def build_form(app, name, fields, title=None):
    """fields: [(fid, label, kind, opts)]  kind: text/number/date/select/person/org/textarea
    栈式布局：根容器 > actionbar + 标题 + 字段行(label+控件) + 审批记录
    返回 (form, fid_map)：fid_map = 语义id -> 实际唯一id"""
    pid = nid()
    page = Page(app, name)
    page.pid = pid
    st_label = {'display': 'inline-block', 'width': '130px', 'text-align': 'right',
                'padding-right': '12px', 'font-size': '14px', 'color': '#5a6473',
                'vertical-align': 'middle'}
    st_row = {'display': 'block', 'padding': '7px 0'}
    st_ctrl = {'display': 'inline-block', 'width': '420px', 'vertical-align': 'middle'}
    page.open_div('f_root', {'padding': '10px 16px'})
    # 操作条
    ab = {"id": "actionbar", "name": "", "type": "Actionbar", "tools": [],
          "multiTools": [], "moduleName": "actionbar", "isSaved": True,
          "actionStyles": {}, "pid": 'PC' + pid + 'actionbar'}
    page.add('actionbar', ab, 'actionbar')
    # 标题
    page.open_div('f_title', {'font-size': '18px', 'font-weight': 'bold', 'color': '#1f2d3d',
                              'padding': '4px 0 12px', 'border-bottom': '2px solid %s' % app['color'],
                              'margin-bottom': '12px'})
    page.label('f_title_t', title or name, {'font-size': '18px'})
    page.close_div()   # f_title
    field_ids = []
    fid_map = {}
    for (fid, label, kind, opts) in fields:
        ufid = uniq_fid(fid)
        fid_map[fid] = ufid
        row = 'r_' + fid
        page.open_div(row, st_row)
        page.label(row + '_l', label, st_label)
        if kind == 'text':      m = ctrl_textfield(fid, label)
        elif kind == 'number':  m = ctrl_number(fid, label)
        elif kind == 'date':    m = ctrl_calendar(fid, label)
        elif kind == 'select':
            m = ctrl_select(fid, label, opts.get('options', []),
                            opts.get('dict'), opts.get('dict_key', label))
        elif kind == 'person':  m = ctrl_person(fid, label, 'identity')
        elif kind == 'org':     m = ctrl_person(fid, label, 'unit')
        elif kind == 'textarea':m = ctrl_textarea(fid, label)
        else: m = ctrl_textfield(fid, label)
        m['id'] = ufid
        m['pid'] = 'PC' + pid + ufid
        m['styles'] = st_ctrl
        page.add(ufid, m, FORM_MWFT[kind])
        page.close_div()   # row
        field_ids.append((ufid, kind))
    # 审批记录
    lg = {"id": "f_log", "name": "", "type": "Log", "moduleName": "log", "isSaved": True,
          "pid": 'PC' + pid + 'f_log', "events": evts(), "styles": {'margin-top': '14px'}}
    page.add('f_log', lg, 'log')
    page.close_div()   # f_root
    # formFieldList
    dt = {'number': 'double', 'date': 'dateTime'}
    ffl = [{"id": fid, "name": fid, "dataType": dt.get(kind, 'string'),
            "application": app['app_id'], "form": pid} for (fid, kind) in field_ids]
    j = copy.deepcopy(FRM_JSON)
    j['id'] = pid; j['name'] = name; j['alias'] = ''
    j['application'] = app['app_id']; j['applicationName'] = app['name']
    j['moduleList'] = page.mods
    j['pid'] = pid
    data = esc_d({"json": j, "html": page.html(), "id": pid, "isNewForm": False})
    form = {"formFieldList": ffl, "id": pid, "name": name, "category": "", "alias": "",
            "application": app['app_id'], "lastUpdatePerson": BY, "lastUpdateTime": TS,
            "data": data, "mobileData": "", "hasMobile": False,
            "properties": {}, "createTime": TS, "updateTime": TS}
    return form, fid_map

# ---------------- 流程生成 ----------------
def build_process(app, name, form_id, steps):
    """steps: [(环节名, participant)]  participant: None=运行时指定 / "creator"
    拓扑: begin -> 填报(creator) -> step1..N -> end；每环节带退回上一环节路由"""
    proc_id = nid()
    begin = copy.deepcopy(P_BEGIN)
    begin['id'] = nid(); begin['process'] = proc_id
    begin['name'] = '开始'; begin['route'] = None; begin['position'] = '0,200'
    end = copy.deepcopy(P_END)
    end['id'] = nid(); end['process'] = proc_id; end['name'] = '结束'
    end['position'] = '1400,200'
    def mk_route(name, target_id, target_type='manual', back=False):
        r = copy.deepcopy(P_ROUTE)
        r['id'] = nid(); r['name'] = name; r['process'] = proc_id
        r['activity'] = target_id; r['activityType'] = target_type
        r['type'] = 'back' if back else ''
        r['position'] = ''
        return r
    def mk_manual(sname, participant, pos):
        m = copy.deepcopy(P_MANUAL)
        m['id'] = nid(); m['name'] = sname; m['process'] = proc_id
        m['form'] = form_id; m['position'] = pos
        m['routeList'] = []
        if participant == 'creator':
            m['taskParticipant'] = {"type": "creator"}
        else:
            m['taskParticipant'] = {"type": ""}
        return m
    manuals = []
    # 填报环节
    m0 = mk_manual('填报', 'creator', '180,200')
    manuals.append(m0)
    x = 380
    for sname, participant in steps:
        m = mk_manual(sname, participant, f'{x},200')
        manuals.append(m); x += 220
    routes = []
    # begin -> m0
    r = mk_route('提交', manuals[0]['id'], 'manual'); routes.append(r)
    begin['route'] = r['id']
    # manual 链 + 退回
    for i, m in enumerate(manuals):
        if i + 1 < len(manuals):
            r = mk_route('送' + manuals[i+1]['name'], manuals[i+1]['id'], 'manual')
            routes.append(r); m['routeList'].append(r['id'])
            rb = mk_route('退回', manuals[i-1]['id'] if i > 0 else begin['id'],
                          'manual' if i > 0 else 'begin', back=True)
            routes.append(rb); m['routeList'].append(rb['id'])
        else:
            r = mk_route('办结', end['id'], 'end')
            routes.append(r); m['routeList'].append(r['id'])
            if i > 0:
                rb = mk_route('退回', manuals[i-1]['id'], 'manual', back=True)
                routes.append(rb); m['routeList'].append(rb['id'])
    pr = {k: copy.deepcopy(v) for k, v in PROC_TPL.items()
          if k not in ('begin', 'manualList', 'routeList', 'endList', 'id', 'name',
                       'alias', 'edition', 'editionName', 'processList')}
    # 清空模板残留的其它活动类型（split/merge 等带固定 id，同包多流程会撞 PP_E_SPLIT 主键）
    for k in list(pr.keys()):
        if k.endswith('List') and isinstance(pr[k], list):
            pr[k] = []
    pr.update({"id": proc_id, "name": name, "alias": "",
               "application": app['app_id'], "applicationName": app['name'],
               "edition": nid(), "editionName": name + "_V1.0",
               "editionEnable": "True", "editionNumber": "1.0",
               "startableIdentityList": [], "controllerList": [],
               "createTime": TS, "updateTime": TS})
    pr['begin'] = begin; pr['manualList'] = manuals
    pr['routeList'] = routes; pr['endList'] = [end]
    return pr

# ---------------- 视图/统计/字典 ----------------
def build_view(app, name, process_id, process_name, columns, filters, scope='all', colmap=None):
    """columns: [(col_id, display)]  filters: [(col_id, title, comparison)]
    colmap: 语义字段id -> 实际唯一字段id（无映射时原样使用）"""
    cm = colmap or {}
    sels = []
    for (cid, disp) in columns:
        cid = cm.get(cid, cid)
        sels.append({"id": cid, "column": cid, "displayName": disp,
                     "orderType": "original", "pid": nid() + cid,
                     "allowOpen": True, "groupEntry": False, "hideColumn": False,
                     "isName": False, "path": cid,
                     "events": {"loadTitle": {"code": "", "html": ""},
                                "loadContent": {"code": "", "html": ""},
                                "click": {"code": "", "html": ""},
                                "mousedown": {"code": "", "html": ""},
                                "mouseup": {"code": "", "html": ""},
                                "mouseout": {"code": "", "html": ""},
                                "mouseover": {"code": "", "html": ""}}})
    cfl = [{"logic": "and", "path": cm.get(cid, cid), "title": t, "type": "custom",
            "comparison": comp, "formatType": "textValue", "value": "",
            "otherValue": ""} for (cid, t, comp) in filters]
    data = {"where": {"accessible": True, "scope": scope, "applicationList": [],
                      "processList": [{"name": process_name, "id": process_id}],
                      "dateRange": {"year": "", "month": "", "date": "", "season": 0,
                                    "week": 0, "adjust": 0, "dateRangeType": "none"},
                      "creatorPersonList": [], "creatorUnitList": [],
                      "creatorIdentityList": [], "draft": False},
            "selectList": sels, "customFilterList": cfl,
            "actions": {"export": False, "batchDelete": False, "batchImpower": False},
            "isSequence": False, "actionbarHidden": False, "select": "none",
            "selectBoxShow": False, "allowSelectAll": False, "firstTdHidden": False,
            "table": None, "group": {"isGroup": False, "groupName": "",
                                     "groupColumn": "", "groupType": "none"}}
    return {"id": nid(), "name": name, "alias": "", "query": app['query_id'],
            "data": json.dumps(data, ensure_ascii=False), "display": True,
            "type": "视图", "cacheAccess": False,
            "availableIdentityList": [], "availableUnitList": [], "availableGroupList": [],
            "count": 1000, "pageSize": 20, "createTime": TS, "updateTime": TS}

def build_stat(app, name, view_id, group_col, calc_col, calc_disp):
    data = {"calculate": {"isGroup": True, "isAmount": False, "orderType": "original",
                          "title": "分类", "groupMergeType": "item",
                          "calculateList": [{"view": view_id, "column": group_col,
                                             "calculateType": "count",
                                             "displayName": calc_disp,
                                             "orderType": "original",
                                             "id": uuid.uuid4().hex.upper()}]}}
    return {"id": nid(), "name": name, "query": app['query_id'], "view": view_id,
            "data": json.dumps(data, ensure_ascii=False),
            "availableIdentityList": [], "availableUnitList": [], "availableGroupList": [],
            "display": True, "createTime": TS, "updateTime": TS}

# ---------------- xapp 组装 ----------------
START_JS = ('(function(appId,procId){var wa=this.Actions.load('
            '"x_processplatform_assemble_surface").WorkAction;'
            'wa.createWithApplicationProcess(appId,procId,{},function(json){'
            'var d=(json&&json.data)||[];var o=(d.length?d[0]:{})||{};'
            'var wid=o.work||o.workId||o.id;'
            'if(wid){window.open("/x_desktop/work.html?workid="+wid,"_blank");}'
            'else{alert("发起失败，请到流程平台手动发起");}});})("__APPID__","__PROCID__");')

def gv(vid, vmap, G):
    """视图引用：'FM|付款台账' 跨应用走全局索引 G（vmap/G 值 = {'id':..,'cols':..}）"""
    m = G[vid] if '|' in vid else vmap[vid]
    return m['id']

def gcol(vid, col, vmap, G):
    """跨视图语义列 -> 实际字段 id（sum 卡片用）"""
    m = G[vid] if '|' in vid else vmap[vid]
    return m['cols'].get(col, col)

def build_core(defn):
    """阶段1：生成应用内 forms/procs/views/stats（自包含，无页面）"""
    app = {"code": defn['code'], "name": defn['name'], "icon": defn['icon'],
           "color": defn['color'], "nav": defn['nav'], "hue": defn.get('hue', 'blue')}
    app['app_id'] = defn['app_id']
    app['portal_id'] = defn['portal_id']
    app['query_id'] = defn['query_id']
    forms, fmap, colmaps = [], {}, {}
    proc_form = {p['name']: p['form'] for p in defn['processes']}
    for f in defn['forms']:
        fo, fimap = build_form(app, f['name'], f['fields'], f.get('title'))
        forms.append(fo); fmap[f['name']] = fo['id']; colmaps[f['name']] = fimap
    procs = [build_process(app, p['name'], fmap[p['form']], p['steps'])
             for p in defn['processes']]
    proc_ids = {p['name']: p['id'] for p in procs}
    views = []
    for v in defn['views']:
        pid_, pname = proc_ids[v['process']], v['process']
        cm = colmaps.get(proc_form.get(v['process'], ''), {})
        views.append(build_view(app, v['name'], pid_, pname, v['columns'],
                                v.get('filters', []), v.get('scope', 'all'), cm))
    # vmap: 视图名 -> {id, cols(语义->实际)}（跨应用 column 转换也需要）
    vmap = {}
    for vd, vres in zip(defn['views'], views):
        cm = colmaps.get(proc_form.get(vd['process'], ''), {})
        vmap[vres['name']] = {'id': vres['id'], 'cols': cm}
    stats = []
    for s in defn.get('stats', []):
        cm = vmap[s['view']]['cols']
        stats.append(build_stat(app, s['name'], vmap[s['view']]['id'],
                                cm.get(s['group'], s['group']), s['group'],
                                s.get('display', '数量')))
    smap = {s['name']: s['id'] for s in stats}
    return app, forms, procs, views, stats, vmap, smap, proc_ids

def build_pages(app, defn, vmap, smap, proc_ids, G):
    """阶段2：生成门户页面（G = 跨应用全局视图索引）"""
    pages = []
    for pd in defn['pages']:
        page = Page(app, pd['name'])
        build_page_shell(page, app, pd['name'], pd['name'])
        js = "void(0);"
        if pd['type'] == 'dashboard':
            page.open_div('cards_row', {'display': 'flex', 'gap': '16px', 'flex-wrap': 'wrap'})
            jobs = []
            for i, c in enumerate(pd['cards']):
                vid = gv(c['view'], vmap, G)
                num_id = card(page, 'c%d' % i, c['label'], c['color'], c['icon'])
                jobs.append({"view": vid, "el": num_id, "mode": c.get('mode', 'count'),
                             "column": gcol(c['view'], c.get('column', ''), vmap, G),
                             "unit": c.get('unit', '')})
            page.close_div()   # cards_row
            if pd.get('chart'):
                panel(page, 'chart_panel', pd['chart'].get('title', '统计图表'),
                      {'min-height': '280px'})
                page.stat_mod('chart_stat', smap[pd['chart']['stat']],
                              pd['chart']['stat'], {'width': '100%', 'height': '260px'})
                page.close_div()   # chart_panel
            if pd.get('views'):
                vd = pd['views'][0]
                panel(page, 'dash_view_panel', vd.get('title', '最新单据'),
                      {'min-height': '420px'})
                page.view_mod('dash_view', gv(vd['view'], vmap, G),
                              vd['view'].split('|')[-1], {'width': '100%'})
                page.close_div()   # panel
            js = DASH_JS.replace('__JOBS__', json.dumps(jobs, ensure_ascii=False))
        elif pd['type'] == 'ledger':
            for vi, vd in enumerate(pd['views']):
                t = vd.get('title', vd['view'].split('|')[-1])
                panel(page, 'vpanel%d' % vi, t, {'min-height': '420px'})
                page.view_mod('view%d' % vi, gv(vd['view'], vmap, G),
                              vd['view'].split('|')[-1], {'width': '100%'})
                page.close_div()   # panel
        elif pd['type'] == 'process':
            # 发起卡行
            page.open_div('start_row', {'display': 'flex', 'gap': '16px', 'flex-wrap': 'wrap'})
            for pi, pc in enumerate(pd['starts']):
                page.open_div('start%d' % pi,
                              {'background': '#ffffff', 'border-radius': '10px',
                               'box-shadow': '0 2px 8px rgba(0,0,0,0.05)', 'padding': '18px',
                               'flex': '1', 'min-width': '220px',
                               'border-top': '3px solid %s' % app['color']})
                page.label('start%d_n' % pi, pc['proc'],
                           {'display': 'block', 'font-size': '15px', 'font-weight': 'bold',
                            'color': '#1f2d3d'})
                page.label('start%d_d' % pi, pc.get('desc', ''),
                           {'display': 'block', 'font-size': '13px', 'color': '#8a94a3',
                            'margin-top': '6px', 'min-height': '20px'})
                page.open_div('start%d_btn' % pi,
                              {'margin-top': '12px', 'display': 'inline-block',
                               'padding': '7px 18px', 'background': app['color'],
                               'color': '#fff', 'border-radius': '6px', 'font-size': '13px',
                               'cursor': 'pointer'},
                              click=START_JS.replace('__APPID__', app['app_id'])
                                            .replace('__PROCID__', proc_ids[pc['proc']]))
                page.label('start%d_bt' % pi, '＋ 发起', {'font-size': '13px', 'color': '#fff'})
                page.close_div()   # btn
                page.close_div()   # card
            page.close_div()   # start_row
            if pd.get('views'):
                vd = pd['views'][0]
                panel(page, 'ap_panel', vd.get('title', '在途单据'), {'min-height': '420px'})
                page.view_mod('ap_view', gv(vd['view'], vmap, G),
                              vd['view'].split('|')[-1], {'width': '100%'})
                page.close_div()   # panel
        # 页尾应用切换区 + 收尾：content → main_area → app_root
        add_app_switch(page, app)
        page.close_div(); page.close_div(); page.close_div()
        pages.append(page.build(load_script=js))
    return pages

def assemble(app, defn, forms, procs, views, stats, vmap, smap, proc_ids, G):
    """core 结果 + 页面 → 完整 xapp"""
    pages = build_pages(app, defn, vmap, smap, proc_ids, G)
    # portal
    portal = {"pageList": pages, "scriptList": [], "fileList": [], "widgetList": [],
              "applicationDictList": [], "id": app['portal_id'], "name": app['name'] + '门户',
              "alias": defn['code'] + '_portal',
              "availableIdentityList": [], "availableUnitList": [], "availableGroupList": [],
              "portalCategory": "", "icon": "", "firstPage": pages[0]['id'],
              "controllerList": [], "creatorPerson": BY,
              "lastUpdateTime": TS, "lastUpdatePerson": BY,
              "pcClient": True, "mobileClient": False}
    # processPlatform
    pp = {"processList": procs, "formList": forms,
          "applicationDictList": [build_dict(app, defn['dict'])] if defn.get('dict') else [],
          "scriptList": [], "fileList": [],
          "id": app['app_id'], "defaultForm": "", "name": app['name'],
          "alias": defn['code'] + '_app', "description": defn.get('desc', ''),
          "availableIdentityList": [], "availableUnitList": [], "availableGroupList": [],
          "applicationCategory": "", "icon": "", "iconHue": defn.get('hue', 'blue'),
          "controllerList": [], "lastUpdateTime": TS, "lastUpdatePerson": BY,
          "properties": {}}
    query = {"viewList": views, "statList": stats, "tableList": [], "statementList": [],
             "importModelList": [], "id": app['query_id'], "name": app['name'] + '查询',
             "alias": defn['code'] + '_query',
             "availableIdentityList": [], "availableUnitList": [], "availableGroupList": [],
             "controllerList": [], "creatorPerson": BY,
             "lastUpdateTime": TS, "lastUpdatePerson": BY, "queryCategory": "",
             "createTime": TS, "updateTime": TS}
    return {"flag": app['app_id'], "name": app['name'],
            "processPlatformList": [pp], "portalList": [portal], "queryList": [query],
            "cmsList": [], "serviceModuleList": []}

def build_dict(app, dict_def):
    return {"id": nid(), "name": "基础数据", "alias": "", "application": app['app_id'],
            "data": json.dumps(dict_def, ensure_ascii=False),
            "lastUpdateTime": TS, "lastUpdatePerson": BY}

APP_SWITCH = []  # 运行时由 build_all 填充（应用名→门户id）

def build_all(defs, out_dir='C:/temp/biz'):
    os.makedirs(out_dir, exist_ok=True)
    for d in defs:
        d.setdefault('app_id', nid()); d.setdefault('portal_id', nid())
        d.setdefault('query_id', nid())
    global APP_SWITCH
    APP_SWITCH = [(d['name'], d['portal_id']) for d in defs]
    # 两遍构建：先 core 拿全部视图 id（跨应用引用），再生成页面
    cores = []
    G = {}
    for d in defs:
        r = build_core(d)
        cores.append(r)
        for vn, vm in r[5].items():
            G['%s|%s' % (d['code'], vn)] = vm   # {'id':..,'cols':..}
    print('全局视图索引:', len(G), '项（跨应用引用可用 code|视图名）')
    outs = []
    for d, (app, forms, procs, views, stats, vmap, smap, proc_ids) in zip(defs, cores):
        xapp = assemble(app, d, forms, procs, views, stats, vmap, smap, proc_ids, G)
        path = os.path.join(out_dir, f"{d['code']}_{d['name']}.xapp.json")
        json.dump(xapp, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        outs.append((path, app, xapp))
        print('OK', d['code'], d['name'],
              'pages=%d procs=%d forms=%d views=%d stats=%d' % (
                  len(xapp['portalList'][0]['pageList']),
                  len(xapp['processPlatformList'][0]['processList']),
                  len(xapp['processPlatformList'][0]['formList']),
                  len(xapp['queryList'][0]['viewList']),
                  len(xapp['queryList'][0]['statList'])),
              'app=%s' % app['app_id'][:8])
    return outs

# ============================================================
# 5 应用声明式定义（设计定稿：docs/经营管理平台-5应用总体设计.md §2）
# ============================================================
APPS = []

# ---------- PM 项目管理 ----------
APPS.append({
    'code': 'PM', 'name': '项目管理', 'icon': '📋', 'color': '#1a66ff', 'hue': 'blue',
    'desc': '项目立项/进度/风险/结项全周期管理',
    'dict': {'项目类型': ['信息化', '工程建设', '市场推广', '研发', '其他'],
             '项目状态': ['审批中', '在途', '已结项', '已终止'],
             '进度阶段': ['启动', '规划', '执行', '监控', '收尾'],
             '风险等级': ['低', '中', '高'],
             '风险类型': ['进度', '成本', '质量', '外部', '其他']},
    'nav': [{'key': 'ov', 'name': '总览',
             'items': [('综合仪表盘', '综合仪表盘'), ('项目台账', '项目台账')]},
            {'key': 'fl', 'name': '流程业务',
             'items': [('审批中心', '审批中心'), ('进度与风险', '进度与风险')]}],
    'pages': [
        {'name': '综合仪表盘', 'type': 'dashboard',
         'cards': [{'label': '在途项目', 'color': '#1a66ff', 'icon': '📋', 'view': '在途项目'},
                   {'label': '风险预警', 'color': '#ef476f', 'icon': '⚠', 'view': '风险台账'},
                   {'label': '预算总额(万)', 'color': '#f59e0b', 'icon': '💰',
                    'view': 'BM|预算台账', 'mode': 'sum', 'column': 'ys_amount', 'unit': ' 万'},
                   {'label': '累计付款(元)', 'color': '#00a870', 'icon': '💳',
                    'view': 'FM|付款台账', 'mode': 'sum', 'column': 'pay_amount', 'unit': ' 元'}],
         'chart': {'stat': '项目类型分布', 'title': '项目类型分布'},
         'views': [{'view': '在途项目', 'title': '在途项目一览'}]},
        {'name': '项目台账', 'type': 'ledger',
         'views': [{'view': '项目台账', 'title': '项目台账'},
                   {'view': '结项记录', 'title': '结项记录'}]},
        {'name': '审批中心', 'type': 'process',
         'starts': [{'proc': '项目立项', 'desc': '新项目申报与审批'},
                    {'proc': '进度填报', 'desc': '定期填报项目进展'},
                    {'proc': '风险上报', 'desc': '项目风险登记与处置'},
                    {'proc': '项目结项', 'desc': '项目收尾结项申请'}],
         'views': [{'view': '在途项目', 'title': '在途单据'}]},
        {'name': '进度与风险', 'type': 'ledger',
         'views': [{'view': '进度记录', 'title': '进度记录'},
                   {'view': '风险台账', 'title': '风险台账'}]},
    ],
    'forms': [
        {'name': '项目立项申请表', 'fields': [
            ('prj_code', '项目编号', 'text', {}), ('prj_name', '项目名称', 'text', {}),
            ('prj_type', '项目类型', 'select', {'dict': '基础数据', 'dict_key': '项目类型'}),
            ('prj_budget', '项目预算(万元)', 'number', {}),
            ('prj_owner', '项目负责人', 'person', {}), ('prj_dept', '申报部门', 'org', {}),
            ('prj_start', '计划开始', 'date', {}), ('prj_end', '计划结束', 'date', {}),
            ('prj_status', '项目状态', 'select', {'dict': '基础数据', 'dict_key': '项目状态'}),
            ('prj_goal', '项目目标', 'textarea', {})]},
        {'name': '进度填报单', 'fields': [
            ('prj_code', '项目编号', 'text', {}), ('prj_name', '项目名称', 'text', {}),
            ('prog_stage', '进度阶段', 'select', {'dict': '基础数据', 'dict_key': '进度阶段'}),
            ('prog_pct', '完成百分比', 'number', {}),
            ('prog_report', '本期进展', 'textarea', {}), ('prog_person', '填报人', 'person', {})]},
        {'name': '风险登记表', 'fields': [
            ('prj_code', '项目编号', 'text', {}), ('prj_name', '项目名称', 'text', {}),
            ('risk_type', '风险类型', 'select', {'dict': '基础数据', 'dict_key': '风险类型'}),
            ('risk_level', '风险等级', 'select', {'dict': '基础数据', 'dict_key': '风险等级'}),
            ('risk_desc', '风险描述', 'textarea', {}), ('risk_action', '应对措施', 'textarea', {}),
            ('risk_person', '登记人', 'person', {})]},
        {'name': '结项申请表', 'fields': [
            ('prj_code', '项目编号', 'text', {}), ('prj_name', '项目名称', 'text', {}),
            ('close_time', '实际完成时间', 'date', {}), ('close_archive', '归档编号', 'text', {}),
            ('close_desc', '结项说明', 'textarea', {})]},
    ],
    'processes': [
        {'name': '项目立项', 'form': '项目立项申请表',
         'steps': [('部门负责人审批', None), ('PMO审核', None), ('分管领导批准', None)]},
        {'name': '进度填报', 'form': '进度填报单', 'steps': [('PMO审核', None)]},
        {'name': '风险上报', 'form': '风险登记表',
         'steps': [('风险评估', None), ('处置跟进', None), ('关闭确认', None)]},
        {'name': '项目结项', 'form': '结项申请表',
         'steps': [('PMO初审', None), ('领导批准', None), ('归档确认', None)]},
    ],
    'views': [
        {'name': '项目台账', 'process': '项目立项', 'scope': 'all',
         'columns': [('prj_code', '项目编号'), ('prj_name', '项目名称'), ('prj_type', '项目类型'),
                     ('prj_owner', '项目负责人'), ('prj_budget', '项目预算(万)'),
                     ('prj_status', '状态'), ('prj_end', '计划结束')],
         'filters': [('prj_name', '项目名称', 'like'), ('prj_type', '项目类型', 'equals')]},
        {'name': '在途项目', 'process': '项目立项', 'scope': 'work',
         'columns': [('prj_code', '项目编号'), ('prj_name', '项目名称'), ('prj_type', '项目类型'),
                     ('prj_owner', '项目负责人'), ('prj_end', '计划结束')]},
        {'name': '进度记录', 'process': '进度填报', 'scope': 'all',
         'columns': [('prj_code', '项目编号'), ('prj_name', '项目名称'), ('prog_stage', '进度阶段'),
                     ('prog_pct', '完成百分比'), ('prog_person', '填报人')]},
        {'name': '风险台账', 'process': '风险上报', 'scope': 'all',
         'columns': [('prj_code', '项目编号'), ('prj_name', '项目名称'), ('risk_type', '风险类型'),
                     ('risk_level', '风险等级'), ('risk_person', '登记人')]},
        {'name': '结项记录', 'process': '项目结项', 'scope': 'all',
         'columns': [('prj_code', '项目编号'), ('prj_name', '项目名称'),
                     ('close_time', '实际完成'), ('close_archive', '归档编号')]},
    ],
    'stats': [{'name': '项目类型分布', 'view': '项目台账', 'group': 'prj_type'}],
})

# ---------- CM 合同管理 ----------
APPS.append({
    'code': 'CM', 'name': '合同管理', 'icon': '📑', 'color': '#00a870', 'hue': 'green',
    'desc': '合同审批/变更/结算全流程管理',
    'dict': {'合同类型': ['采购', '销售', '服务', '租赁', '保密', '其他'],
             '合同状态': ['审批中', '已签订', '履行中', '已变更', '已结算', '已终止']},
    'nav': [{'key': 'ov', 'name': '总览',
             'items': [('合同仪表盘', '合同仪表盘'), ('合同台账', '合同台账')]},
            {'key': 'fl', 'name': '流程业务', 'items': [('审批中心', '审批中心')]}],
    'pages': [
        {'name': '合同仪表盘', 'type': 'dashboard',
         'cards': [{'label': '合同总数', 'color': '#00a870', 'icon': '📑', 'view': '合同台账'},
                   {'label': '在途合同', 'color': '#1a66ff', 'icon': '⏳', 'view': '在途合同'},
                   {'label': '结算总额(万)', 'color': '#f59e0b', 'icon': '💰',
                    'view': '结算单台账', 'mode': 'sum', 'column': 'stl_amount', 'unit': ' 万'},
                   {'label': '变更单数', 'color': '#ef476f', 'icon': '📝', 'view': '变更单台账'}],
         'chart': {'stat': '合同类型分布', 'title': '合同类型分布'},
         'views': [{'view': '在途合同', 'title': '在途合同'}]},
        {'name': '合同台账', 'type': 'ledger',
         'views': [{'view': '合同台账', 'title': '合同台账'},
                   {'view': '结算单台账', 'title': '结算单台账'},
                   {'view': '变更单台账', 'title': '变更单台账'}]},
        {'name': '审批中心', 'type': 'process',
         'starts': [{'proc': '合同审批', 'desc': '新合同起草与审批签订'},
                    {'proc': '合同变更', 'desc': '合同内容变更申请'},
                    {'proc': '合同结算', 'desc': '合同结算申请'}],
         'views': [{'view': '在途合同', 'title': '在途单据'}]},
    ],
    'forms': [
        {'name': '合同审批表', 'fields': [
            ('ht_code', '合同编号', 'text', {}), ('ht_name', '合同名称', 'text', {}),
            ('ht_type', '合同类型', 'select', {'dict': '基础数据', 'dict_key': '合同类型'}),
            ('ht_amount', '合同金额(万元)', 'number', {}),
            ('ht_our', '我方签约单位', 'org', {}), ('ht_party', '对方单位', 'text', {}),
            ('ht_sign_date', '签订日期', 'date', {}),
            ('ht_status', '合同状态', 'select', {'dict': '基础数据', 'dict_key': '合同状态'}),
            ('ht_desc', '合同摘要', 'textarea', {})]},
        {'name': '合同变更单', 'fields': [
            ('chg_code', '变更单编号', 'text', {}), ('ht_code', '合同编号', 'text', {}),
            ('chg_content', '变更内容', 'textarea', {}),
            ('chg_amount', '变更金额(万元)', 'number', {}), ('chg_reason', '变更原因', 'textarea', {})]},
        {'name': '合同结算单', 'fields': [
            ('stl_code', '结算单编号', 'text', {}), ('ht_code', '合同编号', 'text', {}),
            ('stl_amount', '结算金额(万元)', 'number', {}), ('stl_desc', '结算说明', 'textarea', {})]},
    ],
    'processes': [
        {'name': '合同审批', 'form': '合同审批表',
         'steps': [('法务审核', None), ('财务审核', None), ('分管领导批准', None), ('签订归档', None)]},
        {'name': '合同变更', 'form': '合同变更单', 'steps': [('法务审核', None), ('领导批准', None)]},
        {'name': '合同结算', 'form': '合同结算单', 'steps': [('财务审核', None), ('领导批准', None)]},
    ],
    'views': [
        {'name': '合同台账', 'process': '合同审批', 'scope': 'all',
         'columns': [('ht_code', '合同编号'), ('ht_name', '合同名称'), ('ht_type', '合同类型'),
                     ('ht_amount', '合同金额(万)'), ('ht_party', '对方单位'), ('ht_status', '状态')],
         'filters': [('ht_name', '合同名称', 'like'), ('ht_type', '合同类型', 'equals')]},
        {'name': '在途合同', 'process': '合同审批', 'scope': 'work',
         'columns': [('ht_code', '合同编号'), ('ht_name', '合同名称'), ('ht_type', '合同类型'),
                     ('ht_amount', '合同金额(万)')]},
        {'name': '结算单台账', 'process': '合同结算', 'scope': 'all',
         'columns': [('stl_code', '结算单编号'), ('ht_code', '合同编号'),
                     ('stl_amount', '结算金额(万)'), ('stl_desc', '结算说明')]},
        {'name': '变更单台账', 'process': '合同变更', 'scope': 'all',
         'columns': [('chg_code', '变更单编号'), ('ht_code', '合同编号'),
                     ('chg_amount', '变更金额(万)'), ('chg_content', '变更内容')]},
    ],
    'stats': [{'name': '合同类型分布', 'view': '合同台账', 'group': 'ht_type'}],
})

# ---------- BM 预算管理 ----------
APPS.append({
    'code': 'BM', 'name': '预算管理', 'icon': '💰', 'color': '#f59e0b', 'hue': 'orange',
    'desc': '预算编制/调整/下达管理',
    'dict': {'预算科目': ['人力成本', '办公费用', '差旅费', '采购费用', '市场费用', '研发费用', '其他'],
             '预算状态': ['审批中', '已下达', '已调整', '已终止']},
    'nav': [{'key': 'ov', 'name': '总览',
             'items': [('预算仪表盘', '预算仪表盘'), ('预算台账', '预算台账')]},
            {'key': 'fl', 'name': '流程业务', 'items': [('审批中心', '审批中心')]}],
    'pages': [
        {'name': '预算仪表盘', 'type': 'dashboard',
         'cards': [{'label': '预算总额(万)', 'color': '#f59e0b', 'icon': '💰',
                    'view': '预算台账', 'mode': 'sum', 'column': 'ys_amount', 'unit': ' 万'},
                   {'label': '预算条目', 'color': '#1a66ff', 'icon': '📊', 'view': '预算台账'},
                   {'label': '在途预算', 'color': '#00a870', 'icon': '⏳', 'view': '在途预算'},
                   {'label': '调整单数', 'color': '#ef476f', 'icon': '📝', 'view': '调整单台账'}],
         'chart': {'stat': '预算科目分布', 'title': '预算科目分布'},
         'views': [{'view': '在途预算', 'title': '在途预算'}]},
        {'name': '预算台账', 'type': 'ledger',
         'views': [{'view': '预算台账', 'title': '预算台账'},
                   {'view': '调整单台账', 'title': '调整单台账'}]},
        {'name': '审批中心', 'type': 'process',
         'starts': [{'proc': '预算编制', 'desc': '部门年度/专项预算申报'},
                    {'proc': '预算调整', 'desc': '预算追加/调减申请'}],
         'views': [{'view': '在途预算', 'title': '在途单据'}]},
    ],
    'forms': [
        {'name': '预算编制表', 'fields': [
            ('ys_code', '预算编号', 'text', {}), ('ys_year', '预算年度', 'text', {}),
            ('ys_dept', '申报部门', 'org', {}), ('prj_code', '项目编号', 'text', {}),
            ('ys_item', '预算科目', 'select', {'dict': '基础数据', 'dict_key': '预算科目'}),
            ('ys_amount', '预算金额(万元)', 'number', {}), ('ys_desc', '用途说明', 'textarea', {})]},
        {'name': '预算调整单', 'fields': [
            ('adj_code', '调整单编号', 'text', {}), ('ys_code', '预算编号', 'text', {}),
            ('adj_type', '调整类型', 'select', {'options': ['追加', '调减']}),
            ('adj_amount', '调整金额(万元)', 'number', {}), ('adj_reason', '调整原因', 'textarea', {})]},
    ],
    'processes': [
        {'name': '预算编制', 'form': '预算编制表',
         'steps': [('财务汇总', None), ('领导批准', None), ('下达执行', None)]},
        {'name': '预算调整', 'form': '预算调整单', 'steps': [('财务审核', None), ('领导批准', None)]},
    ],
    'views': [
        {'name': '预算台账', 'process': '预算编制', 'scope': 'all',
         'columns': [('ys_code', '预算编号'), ('ys_year', '预算年度'), ('ys_dept', '申报部门'),
                     ('ys_item', '预算科目'), ('ys_amount', '预算金额(万)'), ('prj_code', '项目编号')],
         'filters': [('ys_year', '预算年度', 'equals'), ('ys_item', '预算科目', 'equals')]},
        {'name': '在途预算', 'process': '预算编制', 'scope': 'work',
         'columns': [('ys_code', '预算编号'), ('ys_year', '预算年度'), ('ys_dept', '申报部门'),
                     ('ys_item', '预算科目'), ('ys_amount', '预算金额(万)')]},
        {'name': '调整单台账', 'process': '预算调整', 'scope': 'all',
         'columns': [('adj_code', '调整单编号'), ('ys_code', '预算编号'),
                     ('adj_type', '调整类型'), ('adj_amount', '调整金额(万)')]},
    ],
    'stats': [{'name': '预算科目分布', 'view': '预算台账', 'group': 'ys_item'}],
})

# ---------- FM 财务管理 ----------
APPS.append({
    'code': 'FM', 'name': '财务管理', 'icon': '💳', 'color': '#ef476f', 'hue': 'red',
    'desc': '报销/付款/收款全流程管理',
    'dict': {'费用类别': ['交通费', '住宿费', '餐饮费', '办公费', '培训费', '其他'],
             '付款方式': ['银行转账', '现金', '票据'],
             '单据状态': ['审批中', '已付款', '已确认', '已驳回']},
    'nav': [{'key': 'ov', 'name': '总览',
             'items': [('财务仪表盘', '财务仪表盘'), ('报销与付款台账', '报销与付款台账')]},
            {'key': 'fl', 'name': '流程业务', 'items': [('审批中心', '审批中心')]}],
    'pages': [
        {'name': '财务仪表盘', 'type': 'dashboard',
         'cards': [{'label': '报销总额(元)', 'color': '#ef476f', 'icon': '💳',
                    'view': '报销台账', 'mode': 'sum', 'column': 'bx_amount', 'unit': ' 元'},
                   {'label': '付款总额(元)', 'color': '#f59e0b', 'icon': '💸',
                    'view': '付款台账', 'mode': 'sum', 'column': 'pay_amount', 'unit': ' 元'},
                   {'label': '收款总额(元)', 'color': '#00a870', 'icon': '💰',
                    'view': '收款台账', 'mode': 'sum', 'column': 'sk_amount', 'unit': ' 元'},
                   {'label': '在途付款', 'color': '#1a66ff', 'icon': '⏳', 'view': '付款在途'}],
         'chart': {'stat': '费用类别分布', 'title': '费用类别分布'},
         'views': [{'view': '付款台账', 'title': '最新付款单'}]},
        {'name': '报销与付款台账', 'type': 'ledger',
         'views': [{'view': '报销台账', 'title': '报销台账'},
                   {'view': '付款台账', 'title': '付款台账'},
                   {'view': '收款台账', 'title': '收款台账'}]},
        {'name': '审批中心', 'type': 'process',
         'starts': [{'proc': '费用报销', 'desc': '日常费用报销申请'},
                    {'proc': '付款申请', 'desc': '对外付款申请（关联合同/预算）'},
                    {'proc': '收款登记', 'desc': '到账收款登记'}],
         'views': [{'view': '付款在途', 'title': '在途付款单'}]},
    ],
    'forms': [
        {'name': '费用报销单', 'fields': [
            ('bx_code', '报销单编号', 'text', {}), ('bx_person', '报销人', 'person', {}),
            ('bx_dept', '所属部门', 'org', {}),
            ('bx_type', '费用类别', 'select', {'dict': '基础数据', 'dict_key': '费用类别'}),
            ('bx_amount', '报销金额(元)', 'number', {}), ('prj_code', '项目编号', 'text', {}),
            ('bx_desc', '报销事由', 'textarea', {})]},
        {'name': '付款申请单', 'fields': [
            ('pay_code', '付款单编号', 'text', {}), ('pay_to', '收款单位', 'text', {}),
            ('pay_type', '付款方式', 'select', {'dict': '基础数据', 'dict_key': '付款方式'}),
            ('ht_code', '合同编号', 'text', {}), ('prj_code', '项目编号', 'text', {}),
            ('ys_code', '预算编号', 'text', {}),
            ('pay_amount', '付款金额(元)', 'number', {}), ('pay_desc', '付款事由', 'textarea', {})]},
        {'name': '收款登记单', 'fields': [
            ('sk_code', '收款单编号', 'text', {}), ('sk_from', '付款方', 'text', {}),
            ('sk_amount', '收款金额(元)', 'number', {}), ('ht_code', '关联合同编号', 'text', {}),
            ('sk_desc', '款项说明', 'textarea', {})]},
    ],
    'processes': [
        {'name': '费用报销', 'form': '费用报销单',
         'steps': [('部门负责人审批', None), ('财务审核', None), ('出纳付款', None)]},
        {'name': '付款申请', 'form': '付款申请单',
         'steps': [('部门负责人审批', None), ('财务审核', None), ('领导批准', None), ('出纳付款', None)]},
        {'name': '收款登记', 'form': '收款登记单', 'steps': [('财务确认', None)]},
    ],
    'views': [
        {'name': '报销台账', 'process': '费用报销', 'scope': 'all',
         'columns': [('bx_code', '报销单编号'), ('bx_person', '报销人'), ('bx_type', '费用类别'),
                     ('bx_amount', '报销金额(元)'), ('prj_code', '项目编号')],
         'filters': [('bx_type', '费用类别', 'equals')]},
        {'name': '付款台账', 'process': '付款申请', 'scope': 'all',
         'columns': [('pay_code', '付款单编号'), ('pay_to', '收款单位'),
                     ('pay_amount', '付款金额(元)'), ('ht_code', '合同编号'), ('prj_code', '项目编号')],
         'filters': [('pay_to', '收款单位', 'like')]},
        {'name': '收款台账', 'process': '收款登记', 'scope': 'all',
         'columns': [('sk_code', '收款单编号'), ('sk_from', '付款方'),
                     ('sk_amount', '收款金额(元)'), ('ht_code', '关联合同编号')]},
        {'name': '报销在途', 'process': '费用报销', 'scope': 'work',
         'columns': [('bx_code', '报销单编号'), ('bx_person', '报销人'), ('bx_amount', '报销金额(元)')]},
        {'name': '付款在途', 'process': '付款申请', 'scope': 'work',
         'columns': [('pay_code', '付款单编号'), ('pay_to', '收款单位'), ('pay_amount', '付款金额(元)')]},
        {'name': '收款在途', 'process': '收款登记', 'scope': 'work',
         'columns': [('sk_code', '收款单编号'), ('sk_from', '付款方'), ('sk_amount', '收款金额(元)')]},
    ],
    'stats': [{'name': '费用类别分布', 'view': '报销台账', 'group': 'bx_type'}],
})

# ---------- AM 档案管理 ----------
APPS.append({
    'code': 'AM', 'name': '档案管理', 'icon': '🗄', 'color': '#6366f1', 'hue': 'purple',
    'desc': '档案登记/借阅/销毁全流程管理',
    'dict': {'档案类型': ['项目文档', '合同文本', '财务凭证', '人事档案', '其他'],
             '保管期限': ['短期', '长期', '永久'],
             '密级': ['普通', '秘密', '机密'],
             '档案状态': ['在库', '借出', '已销毁']},
    'nav': [{'key': 'ov', 'name': '总览',
             'items': [('档案仪表盘', '档案仪表盘'), ('档案台账', '档案台账')]},
            {'key': 'fl', 'name': '流程业务', 'items': [('借阅审批', '借阅审批')]}],
    'pages': [
        {'name': '档案仪表盘', 'type': 'dashboard',
         'cards': [{'label': '档案总数', 'color': '#6366f1', 'icon': '🗄', 'view': '档案台账'},
                   {'label': '借阅在途', 'color': '#f59e0b', 'icon': '⏳', 'view': '借阅在途'},
                   {'label': '借阅总数', 'color': '#1a66ff', 'icon': '📚', 'view': '借阅台账'},
                   {'label': '销毁记录', 'color': '#ef476f', 'icon': '🗑', 'view': '销毁记录'}],
         'chart': {'stat': '档案类型分布', 'title': '档案类型分布'},
         'views': [{'view': '借阅台账', 'title': '最近借阅'}]},
        {'name': '档案台账', 'type': 'ledger',
         'views': [{'view': '档案台账', 'title': '档案台账'},
                   {'view': '借阅台账', 'title': '借阅台账'},
                   {'view': '销毁记录', 'title': '销毁记录'}]},
        {'name': '借阅审批', 'type': 'process',
         'starts': [{'proc': '档案登记', 'desc': '新档案登记入库'},
                    {'proc': '档案借阅', 'desc': '档案借阅申请与归还'},
                    {'proc': '档案销毁', 'desc': '到期档案鉴定销毁'}],
         'views': [{'view': '借阅在途', 'title': '在途借阅'}]},
    ],
    'forms': [
        {'name': '档案登记表', 'fields': [
            ('da_code', '档案编号', 'text', {}), ('da_name', '档案名称', 'text', {}),
            ('da_type', '档案类型', 'select', {'dict': '基础数据', 'dict_key': '档案类型'}),
            ('prj_code', '项目编号', 'text', {}),
            ('da_term', '保管期限', 'select', {'dict': '基础数据', 'dict_key': '保管期限'}),
            ('da_level', '密级', 'select', {'dict': '基础数据', 'dict_key': '密级'}),
            ('da_desc', '档案说明', 'textarea', {})]},
        {'name': '档案借阅单', 'fields': [
            ('br_code', '借阅单编号', 'text', {}), ('da_code', '档案编号', 'text', {}),
            ('br_person', '借阅人', 'person', {}), ('br_use', '借阅用途', 'text', {}),
            ('br_back', '预计归还日期', 'date', {})]},
        {'name': '档案销毁审批表', 'fields': [
            ('ds_code', '销毁单编号', 'text', {}), ('da_code', '档案编号', 'text', {}),
            ('ds_reason', '销毁原因', 'textarea', {}), ('ds_opinion', '鉴定意见', 'textarea', {})]},
    ],
    'processes': [
        {'name': '档案登记', 'form': '档案登记表', 'steps': [('档案员审核', None), ('入库归档', None)]},
        {'name': '档案借阅', 'form': '档案借阅单',
         'steps': [('部门负责人审批', None), ('档案员借出', None), ('归还确认', None)]},
        {'name': '档案销毁', 'form': '档案销毁审批表',
         'steps': [('档案员鉴定', None), ('领导批准', None), ('销毁执行', None)]},
    ],
    'views': [
        {'name': '档案台账', 'process': '档案登记', 'scope': 'all',
         'columns': [('da_code', '档案编号'), ('da_name', '档案名称'), ('da_type', '档案类型'),
                     ('prj_code', '项目编号'), ('da_term', '保管期限'), ('da_level', '密级')],
         'filters': [('da_name', '档案名称', 'like'), ('da_type', '档案类型', 'equals')]},
        {'name': '借阅台账', 'process': '档案借阅', 'scope': 'all',
         'columns': [('br_code', '借阅单编号'), ('da_code', '档案编号'),
                     ('br_person', '借阅人'), ('br_use', '借阅用途'), ('br_back', '预计归还')]},
        {'name': '销毁记录', 'process': '档案销毁', 'scope': 'all',
         'columns': [('ds_code', '销毁单编号'), ('da_code', '档案编号'), ('ds_reason', '销毁原因')]},
        {'name': '借阅在途', 'process': '档案借阅', 'scope': 'work',
         'columns': [('br_code', '借阅单编号'), ('da_code', '档案编号'), ('br_person', '借阅人')]},
    ],
    'stats': [{'name': '档案类型分布', 'view': '档案台账', 'group': 'da_type'}],
})

if __name__ == '__main__':
    build_all(APPS)
