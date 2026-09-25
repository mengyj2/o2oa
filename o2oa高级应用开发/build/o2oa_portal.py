# -*- coding: utf-8 -*-
"""
O2OA 门户页面 HTML 生成器
==========================

【来源】官方合同管理门户截图 refs/contract/1656385113300.jpg 逐像素实测。

【官方门户版式（实测）】
整个门户是一个左右两栏布局：

  ┌───────────────────────────────────────────────────────────┐
  │ 顶栏：欢迎您！叶子 · 今天是2019年04月12日(周五)     个人设置·退出 │
  ├───────────────────────────────────────────────────────────┤
  │ 品牌条：O2OA 整合办公 智慧赋能     [右侧插画 banner]            │
  ├──────────────┬────────────────────────────────────────────┤
  │ 应用名        │  待办事项(12) | 已办事项(6)      新建流程 ▸   │
  │ 合同管理      │  ┌──────────────────────────────────────┐  │
  │              │  │ ① 标题······  苏娜  公司发文  2019-05-08│  │
  │ ≡ 合同管理首页│  │ ② 标题······  杨苏  请示审批  2019-05-08│  │
  │ ▾ 档案管理    │  │ ...                                  │  │
  │ ▾ 过程管理(07)│  │        上一页   下一页                │  │
  │ ▾ 收款管理(08)│  ├─────────────────┬────────────────────┤  │
  │   收款计划编制 │  │ 按状态统计合同数量 │ 按状态统计合同金额  │  │
  │   收款计划变更 │  │ [饼状图][行列转换] │ [饼状图][行列转换]  │  │
  │   合同收款    │  │    ╭───╮          │    ▁ █ █          │  │
  │   开票申请    │  │  ●履行中 ●已终止   │  收款合同 付款合同  │  │
  │ ▾ 付款管理    │  │  ●已解除 ●已中止   │     其他          │  │
  └──────────────┴────────────────────────────────────────────┘

【颜色（截图取色）】
  品牌蓝      #2b6cb0 / #1a5fa8
  侧栏选中底  #e8f0fa（浅蓝），左侧 3px 蓝竖线
  侧栏分组标题 #4a5568，字号 13px
  角标数量    #94a3b8
  卡片标题    #2d3748 + 左侧 3px 蓝竖线
  卡片边框    #e2e8f0，圆角 3px
  表格斑马纹  #f7fafc
  饼图配色    蓝 #4a8fe7 / 珊瑚红 #f28b82 / 深灰 #4a5568 / 黄 #f5c542
  柱图配色    #4a8fe7
  图例文字    #4a5568 12px

【技术约束】
官方门户页面由门户渲染器注入 iframe，HTML 里可用：
  - 纯 HTML/CSS（渲染器不剥离 style 标签）
  - 官方 jQuery 与 O2OA 门户 JS 桥（o2.portal / o2.widget）—— 本生成器
    只产出静态骨架 + 占位数据，避免依赖未公开的桥 API 导致白屏。
  - 因此：图表用**纯 CSS/SVG 绘制**，不引第三方图表库（离线可用）。
"""

# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------

C_BRAND = "#2b6cb0"
C_BRAND_DK = "#1a5fa8"
C_BRAND_BG = "#e8f0fa"
C_TEXT = "#2d3748"
C_TEXT_SUB = "#4a5568"
C_MUTED = "#94a3b8"
C_BORDER = "#e2e8f0"
C_STRIPE = "#f7fafc"

# 合同状态官方四色（饼图图例实测 4 色）
CHART_COLORS = ["#4a8fe7", "#f28b82", "#4a5568", "#f5c542"]


# --------------------------------------------------------------------------
# 页面骨架
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 页面根节点与 CSS 作用域
#
# ★ 关键事实（2026-09-20 从 O2OA 前端源码实证）：
#   门户页**不是**独立文档。x_component_portal_Portal/PortalPage.js 把
#   page.data JSON.decode 后交给表单引擎 MWF.APPForm 渲染；表单里的 Html
#   模块再用 node.insertAdjacentHTML("beforebegin", json.text) 把内容插进
#   **桌面同一个 document**。
#
#   因此页面 CSS 必须全部限定在自己的根节点之下，否则 body / * 之类全局
#   选择器会污染整个 O2OA 桌面。
# --------------------------------------------------------------------------

PAGE_ROOT = "op-root"


def scope_css(css, scope=None):
    """把 CSS 的所有选择器限定在 #<scope> 之下。

    选择器行判定：该行含 "{" 且 "{" 之前不含 ";"（属性行必带分号）。
    body/html → 根节点自身；* → 根节点及其全部后代。
    """
    scope = scope or ("#" + PAGE_ROOT)
    out = []
    for line in css.split("\n"):
        if "{" not in line:
            out.append(line)
            continue
        head, sep, tail = line.partition("{")
        if ";" in head:                    # 单行样式的属性片段，原样保留
            out.append(line)
            continue
        sels = [s.strip() for s in head.split(",") if s.strip()]
        if not sels:
            out.append(line)
            continue
        fixed = []
        for s in sels:
            if s in ("body", "html", ":root"):
                fixed.append(scope)
            elif s == "*":
                fixed.append("%s, %s *" % (scope, scope))
            else:
                fixed.append("%s %s" % (scope, s))
        out.append(", ".join(fixed) + " " + sep + tail)
    # 根节点自身补两条基础规则：原样位于 window 顶层时由 body 承担的撑高职责
    out.append(scope + " { min-height: 100%; }")
    out.append(scope + " { display: block; }")
    return "\n".join(out)


def wrap_root(markup):
    """把页面标记包进根节点：CSS 作用域与运行时 JS 定位都依赖它。"""
    return '<div id="%s" class="op-page-root">%s</div>' % (PAGE_ROOT, markup)


def _shell(title, css, body):
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8"/>\n'
        '<title>%s</title>\n<style>\n%s\n</style>\n</head>\n<body>\n%s\n</body>\n</html>'
        % (title, css, body)
    )


BASE_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
  font-size: 13px; color: %(text)s; background: #f5f7fa;
}
a { color: %(brand)s; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ---------- 顶栏 ---------- */
.op-topbar {
  height: 34px; line-height: 34px; padding: 0 16px;
  background: #fff; border-bottom: 1px solid %(border)s;
  font-size: 12px; color: %(sub)s;
}
.op-topbar .greet { float: left; }
.op-topbar .greet b { color: %(brand_dk)s; }
.op-topbar .acts { float: right; }
.op-topbar .acts a { margin-left: 14px; color: %(sub)s; }

/* ---------- 品牌条 ---------- */
.op-brand {
  height: 96px; padding: 0 24px;
  background: linear-gradient(100deg, #eaf3fc 0%%, #dbe9f8 48%%, #cfe2f6 100%%);
  border-bottom: 1px solid %(border)s;
  position: relative; overflow: hidden;
}
.op-brand .logo {
  position: absolute; left: 24px; top: 22px;
}
.op-brand .logo-mark {
  display: inline-block; width: 30px; height: 30px; border-radius: 4px;
  background: %(brand)s; color: #fff; text-align: center;
  line-height: 30px; font-size: 11px; font-weight: 700; letter-spacing: -.5px;
  vertical-align: middle;
}
.op-brand .logo-text { display: inline-block; vertical-align: middle; margin-left: 10px; }
.op-brand .logo-text .cn { font-size: 17px; color: %(brand_dk)s; letter-spacing: 3px; font-weight: 600; }
.op-brand .logo-text .en { font-size: 10px; color: %(muted)s; letter-spacing: 1px; }
.op-brand .art {
  position: absolute; right: 26px; top: 12px; width: 300px; height: 72px;
}
.op-brand .art .dev {
  position: absolute; right: 96px; top: 8px; width: 118px; height: 58px;
  background: #2f3a4a; border-radius: 6px;
  box-shadow: 0 6px 16px rgba(43,108,176,.25);
}
.op-brand .art .dev:after {
  content: ""; position: absolute; right: 4px; bottom: 4px; width: 30px; height: 30px;
  border-radius: 50%%; background: %(brand)s;
}
.op-brand .art .plane {
  position: absolute; right: 40px; top: 0; font-size: 34px; color: %(brand)s;
  opacity: .75; transform: rotate(-12deg);
}

/* ---------- 主体两栏 ---------- */
.op-main { display: flex; align-items: stretch; min-height: 560px; }

/* ---------- 左侧导航树 ---------- */
.op-side {
  width: 186px; flex: 0 0 186px;
  background: #fff; border-right: 1px solid %(border)s;
  padding-bottom: 20px;
}
.op-side .side-title {
  padding: 12px 16px 10px; font-size: 14px; color: %(text)s; font-weight: 600;
  border-bottom: 1px solid %(border)s;
}
.op-side ul { list-style: none; margin: 0; padding: 0; }
.op-side li > a, .op-side li > span {
  display: block; position: relative;
  padding: 8px 12px 8px 26px;
  font-size: 13px; color: %(sub)s;
}
.op-side li.lv1 > a, .op-side li.lv1 > span {
  padding-left: 14px; font-weight: 600; color: %(text)s;
}
.op-side li.lv1 > a:before, .op-side li.lv1 > span:before {
  content: "\\25B8"; display: inline-block; width: 14px; color: %(muted)s;
}
.op-side li.lv1.on > a:before { content: "\\25BE"; }
.op-side li.lv2 > a { color: #5a6577; }
.op-side li.active {
  background: %(brand_bg)s;
}
.op-side li.active > a { color: %(brand_dk)s; font-weight: 600; }
.op-side li.active:before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: 3px; background: %(brand)s;
}
.op-side li { position: relative; }
.op-side .badge { color: %(muted)s; font-size: 12px; }

/* ---------- 右内容区 ---------- */
.op-content { flex: 1 1 auto; padding: 0 14px 18px; min-width: 0; }

/* ---------- 卡片 ---------- */
.op-card {
  background: #fff; border: 1px solid %(border)s; border-radius: 3px;
  margin-top: 14px;
}
.op-card > .hd {
  position: relative; height: 38px; line-height: 38px;
  padding: 0 12px 0 14px; border-bottom: 1px solid %(border)s;
}
.op-card > .hd:before {
  content: ""; position: absolute; left: 0; top: 11px; width: 3px; height: 16px;
  background: %(brand)s;
}
.op-card > .hd .t { font-size: 14px; color: %(text)s; font-weight: 600; }
.op-card > .hd .more { float: right; font-size: 12px; color: %(sub)s; }
.op-card > .bd { padding: 0; }

/* 选项卡（待办事项 / 已办事项） */
.op-tabs { border-bottom: 1px solid %(border)s; padding: 0 8px; height: 40px; }
.op-tabs .tab {
  display: inline-block; height: 40px; line-height: 40px;
  padding: 0 14px; font-size: 14px; color: %(sub)s; cursor: pointer;
  border-bottom: 2px solid transparent;
}
.op-tabs .tab.on { color: %(brand_dk)s; font-weight: 600; border-bottom-color: %(brand)s; }
.op-tabs .right { float: right; height: 40px; line-height: 40px; font-size: 12px; }

/* ---------- 数据表格 ---------- */
.op-table { width: 100%%; border-collapse: collapse; }
.op-table th, .op-table td {
  padding: 9px 10px; font-size: 12.5px; text-align: left;
  border-bottom: 1px solid #eef2f7;
}
.op-table th { color: %(sub)s; font-weight: 500; background: #fafcfe; }
.op-table tbody tr:nth-child(even) { background: %(stripe)s; }
.op-table td.idx { width: 22px; color: %(brand)s; }
.op-table td.title { color: %(text)s; }
.op-table td.ctr, .op-table td.date { color: #718096; width: 110px; }
.op-table td.tag { width: 96px; color: #718096; }

/* 分页 */
.op-page { padding: 10px 12px; text-align: center; }
.op-page .pg {
  display: inline-block; min-width: 52px; height: 24px; line-height: 22px;
  padding: 0 10px; margin: 0 5px; font-size: 12px;
  border: 1px solid %(border)s; border-radius: 2px;
  background: #fff; color: %(sub)s; cursor: pointer;
}
.op-page .pg:hover { border-color: %(brand)s; color: %(brand_dk)s; }
.op-page .op-hint { margin-left: 10px; font-size: 11px; color: %(muted)s; }

/* ---------- 图表 ---------- */
.op-charts { display: flex; gap: 14px; margin-top: 14px; align-items: stretch; }
.op-charts > .op-card { flex: 1 1 0; margin-top: 0; min-width: 0; }
.op-chart-tools { padding: 8px 12px 0; }
.op-chart-tools .tg {
  display: inline-block; height: 24px; line-height: 22px; padding: 0 12px;
  margin-right: 6px; font-size: 12px; cursor: pointer;
  border: 1px solid %(border)s; border-radius: 3px;
  background: #fff; color: %(sub)s;
}
.op-chart-tools .tg.on { background: %(brand)s; border-color: %(brand)s; color: #fff; }
.op-chart-body { padding: 12px 16px 16px; }
.op-chart-title { text-align: center; font-size: 13px; color: %(text)s; margin-bottom: 6px; }
.op-legend { margin-top: 10px; padding-left: 6px; }
.op-legend .lg {
  display: inline-block; margin: 2px 14px 2px 0; font-size: 12px; color: %(sub)s;
}
.op-legend .lg i {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%%;
  margin-right: 5px; vertical-align: middle;
}

/* ---------- 快捷入口（彩色图标） ---------- */
.op-quick { display: flex; flex-wrap: wrap; padding: 14px 10px; gap: 6px; }
.op-quick .q {
  width: 88px; text-align: center; padding: 10px 4px; border-radius: 4px;
}
.op-quick .q:hover { background: %(stripe)s; }
.op-quick .q .ic {
  width: 44px; height: 44px; line-height: 44px; margin: 0 auto 7px;
  border-radius: 50%%; color: #fff; font-size: 19px; text-align: center;
}
.op-quick .q .lb { font-size: 12px; color: %(sub)s; }

/* ---------- 真实业务视图区（嵌入原生 query.Viewer） ---------- */
.op-actbar { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 12px; }
.op-actbtn {
  display: inline-block; padding: 7px 16px; border-radius: 4px;
  background: %(brand)s; color: #fff; font-size: 13px; cursor: pointer;
  border: none; text-decoration: none;
}
.op-actbtn:hover { background: %(brand_dk)s; }
.op-actbtn.plain {
  background: #fff; color: %(brand_dk)s; border: 1px solid %(border)s;
}
.op-actbtn.plain:hover { background: %(stripe)s; }
.op-view-wrap { margin-bottom: 16px; }
.op-view-cap {
  font-size: 14px; font-weight: 700; color: %(brand_dk)s;
  padding: 0 2px 8px;
}
.op-view {
  background: #fff; border: 1px solid %(border)s; border-radius: 6px;
  overflow: auto; padding: 4px;
}
.op-view-note {
  color: %(muted)s; font-size: 12px; padding: 10px 6px;
}

/* ---------- 自建表数据直连表格 ---------- */
.op-tbl-wrap { background: #fff; border: 1px solid %(border)s;
  border-radius: 6px; overflow: auto; }
.op-tbl { width: 100%%; border-collapse: collapse; font-size: 13px; }
.op-tbl thead th {
  position: sticky; top: 0; z-index: 1;
  background: %(brand_bg)s; color: %(brand_dk)s;
  font-weight: 600; text-align: left; white-space: nowrap;
  padding: 9px 12px; border-bottom: 1px solid %(border)s;
}
.op-tbl tbody td {
  padding: 8px 12px; border-bottom: 1px solid %(stripe)s;
  color: %(text)s; white-space: nowrap;
}
.op-tbl tbody tr:hover td { background: #f7fafd; }
.op-tbl td.num { text-align: right; font-variant-numeric: tabular-nums; }
.op-tbl-empty, .op-tbl-err {
  color: %(muted)s; font-size: 12px; padding: 22px 12px; text-align: center;
}
.op-tbl-err { color: #c0392b; }
""" % {
    "brand": C_BRAND, "brand_dk": C_BRAND_DK, "brand_bg": C_BRAND_BG,
    "text": C_TEXT, "sub": C_TEXT_SUB, "muted": C_MUTED,
    "border": C_BORDER, "stripe": C_STRIPE,
}


def _topbar(user="秘书长", date_text=""):
    # id=op-user / op-date 供门户运行时脚本替换为「当前登录人 + 今天」，
    # date_text 只是脚本未生效时的降级文案。
    return (
        '<div class="op-topbar">'
        '<div class="greet">\u6b22\u8fce\u60a8\uff01<b id="op-user">%s</b>'
        '\uff01\u4eca\u5929\u662f<span id="op-date">%s</span></div>'
        '<div class="acts"><a href="#" data-op="profile">\u4e2a\u4eba\u8bbe\u7f6e</a>'
        '<a href="#" data-op="logout">\u9000\u51fa</a></div>'
        '</div>' % (user, date_text)
    )


def _brand():
    return (
        '<div class="op-brand">'
        '<div class="logo">'
        '<span class="logo-mark">O2OA</span>'
        '<span class="logo-text">'
        '<span class="cn">\u6574\u5408\u529e\u516c</span><br/>'
        '<span class="en">\u667a\u6167\u8d4b\u80fd</span>'
        '</span></div>'
        '<div class="art"><div class="plane">\u2708</div>'
        '<div class="dev"></div></div>'
        '</div>'
    )


def _side_nav(app_name, tree, nav_map=None):
    """tree: [(level, text, badge, active), ...]  level ∈ {1,2}

    nav_map: {text: (op, target[, page])} —— 点击行为映射。
    未命中时：level2 → start（任务中心-发起流程），level1 → task（任务中心）。
    op ∈ profile/logout/portal/task/start/app。
    """
    nav_map = nav_map or {}
    lis = []
    for lv, text, badge, active in tree:
        cls = "lv%d%s" % (lv, " active" if active else "")
        act = nav_map.get(text)
        if act is None:
            act = ("start", "") if lv >= 2 else ("task", "")
        if badge:
            text = "%s <span class=\"badge\">(%s)</span>" % (text, badge)
        op = act[0]
        target = act[1] if len(act) > 1 else ""
        page = act[2] if len(act) > 2 else ""
        attrs = 'data-op="%s"' % op
        if target:
            attrs += ' data-target="%s"' % target
        if page:
            attrs += ' data-page="%s"' % page
        lis.append('<li class="%s"><a href="#" %s>%s</a></li>' % (cls, attrs, text))
    return (
        '<div class="op-side">'
        '<div class="side-title">%s</div>'
        '<ul>%s</ul>'
        '</div>' % (app_name, "\n".join(lis))
    )


def view_holder(app_id, view_id, caption="", height=420, note=""):
    """真实业务视图容器：运行时由原生 query.Viewer 加载（_LIVE_JS.loadViews）。"""
    cap = '<div class="op-view-cap">%s</div>' % caption if caption else ""
    note = ('<div class="op-view-note">%s</div>' % note) if note else ""
    return (
        '<div class="op-view-wrap">%s'
        '<div class="op-view" style="height:%dpx" '
        'data-embed-view="%s|%s">%s</div></div>'
        % (cap, height, app_id, view_id, note)
    )


def table_holder(table_flag, columns, caption="", height=None, page_size=50):
    """自建表数据容器：运行时由 _LIVE_JS.loadTables() 直读表行接口渲染。

    ★ 为什么不用原生 query.Viewer（view_holder）：
      10.0.2 的 x_query_assemble_surface 的 dealPlan() 只实现了 cms / 流程两类
      Plan，**没有 TablePlan** —— `table` 类型视图执行必抛
      ProcessPlatformPlan.adjustWhere NPE。自建表数据因此改走
      「POST /x_query_assemble_surface/jaxrs/table/list/table/{flag}/row/paging/…」
      直读 + 前端渲染，零引擎依赖、必通。

    :param table_flag: 自建表 id（如 t6006001-hr-employee-table-000000000001）
    :param columns:    [(字段名, 列标题, 格式化)]，格式化 ∈ ""/"money"/"num"/"date"
    """
    import json
    cap = '<div class="op-view-cap">%s</div>' % caption if caption else ""
    spec = [[c[0], c[1], (c[2] if len(c) > 2 else "")] for c in columns]
    col_json = json.dumps([{"k": s[0], "t": s[1], "f": s[2]} for s in spec],
                          ensure_ascii=False)
    style = ' style="height:%dpx"' % height if height else ""
    return (
        '<div class="op-view-wrap">%s'
        '<div class="op-tbl-wrap" data-embed-table="%s|%s" '
        'data-page-size="%d"%s></div></div>'
        % (cap, table_flag, col_json.replace('"', "&quot;"), page_size, style)
    )


def action_bar(buttons):
    """操作按钮条：buttons = [(文字, op, arg, plain)]，op ∈ startone/portal/task/start。"""
    out = ['<div class="op-actbar">']
    for label, op, arg, plain in buttons:
        cls = "op-actbtn plain" if plain else "op-actbtn"
        attrs = 'data-op="%s"' % op
        if op == "startone" and arg:
            attrs += ' data-process="%s"' % arg
        elif arg:
            attrs += ' data-target="%s"' % arg
        out.append('<span class="%s" %s>%s</span>' % (cls, attrs, label))
    out.append("</div>")
    return "".join(out)


def portal_page_html(app_name, tree, todo_rows, charts, quick_links=None,
                     user="\u79d8\u4e66\u957f", date_text="", live=None,
                     nav_map=None, content_html=None):
    """
    生成官方风格的门户首页 HTML。

    :param tree:       左侧导航树 [(level, text, badge, active)]
    :param todo_rows:  待办列表 [(title, person, tag, date)]（脚本未生效时的降级数据）
    :param charts:     [(标题, 类型pie|column, [(分类, 数值)], 是否默认选中)]
    :param quick_links:[(文字, 颜色, 图标字符)]
    :param live:       活数据源描述 dict，见 _live_script()。None = 纯静态。
    """
    # 待办表格
    trs = []
    for i, (title, person, tag, date) in enumerate(todo_rows):
        trs.append(
            '<tr><td class="idx">\u2460</td>'
            '<td class="title">%s</td>'
            '<td class="ctr">%s</td><td class="tag">%s</td>'
            '<td class="date">%s</td></tr>'
            % (title, person, tag, date)
        )
    # 序号用 ①..⑧
    circled = "\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468"
    for i in range(min(len(trs), len(circled))):
        trs[i] = trs[i].replace("\u2460", circled[i], 1)

    todo_card = (
        '<div class="op-card">'
        '<div class="op-tabs">'
        '<span class="tab on">\u5f85\u529e\u4e8b\u9879(<b id="op-todo-count">%d</b>)</span>'
        '<span class="tab">\u5df2\u529e\u4e8b\u9879(<b id="op-done-count">%d</b>)</span>'
        '<span class="right"><a href="#" data-op="start">\u65b0\u5efa\u6d41\u7a0b \u25B8</a></span>'
        '</div>'
        '<div class="bd"><table class="op-table"><tbody id="op-todo-body">%s</tbody></table>'
        '<div class="op-page"><span class="pg">\u4e0a\u4e00\u9875</span>'
        '<span class="pg">\u4e0b\u4e00\u9875</span>'
        '<span class="op-hint" id="op-todo-hint">'
        '\u793a\u4f8b\u6570\u636e\uff0c\u5df2\u5728\u52a0\u8f7d\u5b9e\u65f6\u5f85\u529e\u2026'
        '</span></div>'
        '</div></div>' % (len(todo_rows), max(len(todo_rows) - 6, 0),
                          "".join(trs))
    )

    # 图表卡片
    chart_html = []
    for i, (title, ctype, data, is_on) in enumerate(charts):
        chart_html.append(_chart_card(title, ctype, data, is_on, idx=i))
    charts_row = (
        '<div class="op-charts">%s</div>' % "".join(chart_html)
    )

    body = []
    body.append(_topbar(user, date_text))
    body.append(_brand())
    body.append(
        '<div class="op-main">'
        + _side_nav(app_name, tree, nav_map)
        + '<div class="op-content">'
        + (content_html if content_html else todo_card)
    )
    if content_html is None and quick_links:
        body.append(_quick_card(quick_links, nav_map))
    if content_html is None:
        body.append(charts_row)
    body.append('</div></div>')

    if live:
        script = _live_script(live)
    else:
        script = ""

    return _shell(
        "%s \u95e8\u6237" % app_name,
        scope_css(BASE_CSS),
        wrap_root("\n".join(body)) + (("\n" + script) if script else ""),
    )


def _quick_card(quick_links, nav_map=None):
    nav_map = nav_map or {}
    items = []
    for label, color, icon in quick_links:
        act = nav_map.get(label, ("start", ""))
        op, target = act[0], (act[1] if len(act) > 1 else "")
        page = act[2] if len(act) > 2 else ""
        attrs = 'data-op="%s"' % op
        if target:
            attrs += ' data-target="%s"' % target
        if page:
            attrs += ' data-page="%s"' % page
        items.append(
            '<div class="q" %s><div class="ic" style="background:%s">%s</div>'
            '<div class="lb">%s</div></div>' % (attrs, color, icon, label)
        )
    return (
        '<div class="op-card"><div class="hd"><span class="t">'
        '\u5458\u5de5\u81ea\u52a9</span><span class="more">\u66f4\u591a \u00BB</span>'
        '</div><div class="bd"><div class="op-quick">%s</div></div></div>'
        % "".join(items)
    )


# --------------------------------------------------------------------------
# 纯 SVG 图表（不依赖第三方库，离线可用）
# --------------------------------------------------------------------------

def _chart_card(title, ctype, data, is_on=True, idx=None):
    """一张统计卡片：标题 + 图形 + 图例。ctype ∈ {pie, column, bar}

    idx 非 None 时给图形容器打上 data-op-chart=idx，门户运行时脚本会
    按此定位并替换为实时数据。
    """
    tools = (
        '<div class="op-chart-tools">'
        '<span class="tg%s">\u997c\u72b6\u56fe</span>'
        '<span class="tg">\u884c\u5217\u8f6c\u6362</span>'
        '</div>'
    ) % (" on" if ctype == "pie" else "")
    if ctype == "pie":
        svg = _pie_svg(data, title)
    else:
        svg = _column_svg(data, title)
    attr = '' if idx is None else ' data-op-chart="%d"' % idx
    return (
        '<div class="op-card">'
        '<div class="hd"><span class="t">%s</span>'
        '<span class="more">\u66f4\u591a \u00BB</span></div>'
        '<div class="bd">%s<div class="op-chart-body"%s>%s</div></div>'
        '</div>' % (title, tools, attr, svg)
    )


def _legend_html(data):
    out = []
    for i, (label, val) in enumerate(data):
        c = CHART_COLORS[i % len(CHART_COLORS)]
        out.append('<span class="lg"><i style="background:%s"></i>%s</span>'
                   % (c, label))
    return '<div class="op-legend">%s</div>' % "".join(out)


def _pie_svg(data, title, r=78):
    """
    纯 SVG 饼图（含引线数值标注），复刻官方「合同数量」图。
    使用 path 弧线，从 12 点方向顺时针绘制。
    """
    import math
    total = sum(v for _, v in data) or 1
    cx = cy = 130
    width = height = 260
    paths = []
    labels = []
    angle = -math.pi / 2      # 从 12 点开始
    for i, (label, val) in enumerate(data):
        frac = float(val) / total
        span = frac * 2 * math.pi
        a0, a1 = angle, angle + span
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        large = 1 if span > math.pi else 0
        c = CHART_COLORS[i % len(CHART_COLORS)]
        paths.append(
            '<path d="M%d,%d L%.2f,%.2f A%d,%d 0 %d 1 %.2f,%.2f Z" '
            'fill="%s" stroke="#fff" stroke-width="1"/>'
            % (cx, cy, x0, y0, r, r, large, x1, y1, c)
        )
        # 引线标注
        mid = (a0 + a1) / 2
        lx, ly = cx + (r + 26) * math.cos(mid), cy + (r + 26) * math.sin(mid)
        ex = lx + (22 if math.cos(mid) >= 0 else -22)
        anchor = "start" if math.cos(mid) >= 0 else "end"
        labels.append(
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#cbd5e0" '
            'stroke-width="1"/>'
            '<text x="%.2f" y="%.2f" font-size="12" fill="%s" '
            'text-anchor="%s" dominant-baseline="middle">%s</text>'
            % (cx + r * math.cos(mid), cy + r * math.sin(mid), lx, ly,
               ex, ly, C_TEXT_SUB, anchor, val)
        )
        angle = a1
    svg = (
        '<svg width="100%%" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" '
        'style="max-width:280px;display:block;margin:0 auto">'
        '<text x="%d" y="16" font-size="13" fill="%s" text-anchor="middle">%s</text>'
        '%s%s</svg>'
        % (width, height, cx, C_TEXT, title, "".join(paths), "".join(labels))
    )
    return svg + _legend_html(data)


def _column_svg(data, title):
    """
    纯 SVG 柱图，复刻官方「合同金额」图（灰底横线 + 蓝柱 + 顶部数值）。
    """
    w, h = 300, 220
    pad_l, pad_r, pad_t, pad_b = 42, 14, 30, 34
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    maxv = max([v for _, v in data] + [1])
    # 向上取整到「好看的刻度」
    step = 10 ** (len(str(int(maxv))) - 1)
    top = ((maxv // step) + 1) * step
    if top <= maxv:
        top = maxv * 1.15

    parts = []
    # 网格线 + y 轴刻度（5 条）
    for i in range(6):
        y = pad_t + plot_h * (1 - i / 5.0)
        v = top * i / 5.0
        if i:
            parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" '
                         'stroke="#eef2f7" stroke-width="1"/>'
                         % (pad_l, y, w - pad_r, y))
        else:
            parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" '
                         'stroke="#cbd5e0" stroke-width="1"/>'
                         % (pad_l, y, w - pad_r, y))
        parts.append('<text x="%d" y="%.1f" font-size="10" fill="%s" '
                     'text-anchor="end" dominant-baseline="middle">%d</text>'
                     % (pad_l - 6, y, C_MUTED, int(v)))

    n = len(data) or 1
    slot = plot_w / float(n)
    bw = min(34, slot * 0.5)
    for i, (label, val) in enumerate(data):
        cxi = pad_l + slot * (i + 0.5)
        bh = plot_h * (float(val) / max(top, 1))
        y = pad_t + plot_h - bh
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                     'fill="%s" rx="1"/>'
                     % (cxi - bw / 2, y, bw, bh, CHART_COLORS[0]))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (cxi, y - 4, C_TEXT_SUB, val))
        parts.append('<text x="%.1f" y="%d" font-size="10.5" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (cxi, h - pad_b + 16, C_TEXT_SUB, label))

    parts.append('<text x="%d" y="18" font-size="13" fill="%s" '
                 'text-anchor="middle">%s</text>'
                 % ((pad_l + w - pad_r) // 2, C_TEXT, title))
    return ('<svg width="100%%" viewBox="0 0 %d %d" '
            'preserveAspectRatio="xMidYMid meet" '
            'style="max-width:320px;display:block;margin:0 auto">%s</svg>'
            % (w, h, "".join(parts)))


# --------------------------------------------------------------------------
# 门户运行时脚本（活数据层）
# --------------------------------------------------------------------------
#
# 背景（2026-09-20）：
#   早期门户页是纯静态样张 —— 人名、日期、图表数字全部硬编码，
#   与协会真实组织/数据脱节（页面里出现的 苏娜/杨苏/谢军 等根本不在 9 人名单内）。
#
#   O2OA 门户把 HTML 页面注入 iframe 渲染，该 iframe 与桌面端**同源**，
#   因此可以带会话凭据直接调用各 assemble_surface 接口：
#     我的待办  GET  x_processplatform_assemble_surface/jaxrs/task/list/my/paging/1/size/N
#     待办数    GET  x_processplatform_assemble_surface/jaxrs/task/count/my
#     已办数    GET  x_processplatform_assemble_surface/jaxrs/read/count/my
#     语句数据  POST x_query_assemble_surface/jaxrs/statement/{id}/execute/page/1/size/500
#
#   鉴权：O2OA 前端 o2.js 用 x-token 头，token 取自 layout.session.user.token
#         （桌面端全局），并已写入同名 cookie；本脚本按
#         父窗口 → cookie → localStorage 三级回退取值。
#
#   ★ 降级原则：任何一步失败都**保持静态兜底内容**，绝不白屏。
#     静态内容是真实的协会人员/结构快照，不是假数据。

_LIVE_JS = r"""
<script>
(function(){
  "use strict";
  var SPEC = __SPEC__;
  /* 页面被插入桌面同一 document，所有查询限定在本页根节点内 */
  var ROOT = gid(SPEC.root || "op-root") || document;
  function gid(id){ try{ return ROOT.querySelector("#" + id); }catch(e){ return null; } }
  var CT = ["#4a8fe7","#f28b82","#4a5568","#f5c542","#38b2ac","#ed8936",
            "#9f7aea","#4299e1"];

  /* ---------- token 三级回退 ---------- */
  function token(){
    var names = [window, window.parent, window.top];
    for (var i=0;i<names.length;i++){
      try{ var w=names[i]; if(w && w.layout && w.layout.session &&
            w.layout.session.user && w.layout.session.user.token)
            return w.layout.session.user.token; }catch(e){}
    }
    try{ if(window.o2 && window.o2.token) return window.o2.token; }catch(e){}
    var m = document.cookie.match(/(?:^|;\s*)x-token=([^;]+)/);
    if(m) return decodeURIComponent(m[1]);
    try{
      var t = localStorage.getItem("x-token") || sessionStorage.getItem("x-token");
      if(t) return t;
    }catch(e){}
    return "";
  }

  function req(url, method, body){
    var opt = {
      method: method || "GET",
      credentials: "include",
      headers: {"x-token": token(), "Content-Type":"application/json",
                "Accept":"application/json"}
    };
    if(body !== undefined && body !== null) opt.body = body;
    return fetch(url, opt).then(function(r){ return r.json(); });
  }

  /* ---------- 顶栏：当天日期 + 当前登录人 ---------- */
  function paintTop(){
    var d = new Date();
    var wk = ["\u65e5","\u4e00","\u4e8c","\u4e09","\u56db","\u4e94","\u516d"][d.getDay()];
    var el = gid("op-date");
    if(el) el.textContent = d.getFullYear() + "\u5e74" +
      ("0"+(d.getMonth()+1)).slice(-2) + "\u6708" +
      ("0"+d.getDate()).slice(-2) + "\u65e5(\u5468" + wk + ")";
    try{
      var u = window.parent.layout.session.user;
      var nm = gid("op-user");
      if(nm && u && u.name) nm.textContent = u.name;
    }catch(e){}
  }

  /* ---------- 我的待办 ---------- */
  function paintTodo(){
    var body = gid("op-todo-body");
    if(!body) return;
    var page = SPEC.todo_page || 8;
    req("/x_processplatform_assemble_surface/jaxrs/task/list/my/paging/1/size/"+page)
      .then(function(j){
        if(j.type !== "success" || !j.data) return;
        var c = gid("op-todo-count");
        if(c) c.textContent = (j.count === undefined ? j.data.length : j.count);
        var hint = gid("op-todo-hint");
        if(hint && hint.parentNode) hint.parentNode.removeChild(hint);
        if(!j.data.length){
          body.innerHTML = '<tr><td colspan="5" style="text-align:center;'+
            'color:#94a3b8;padding:22px 0">\u5f53\u524d\u65e0\u5f85\u529e</td></tr>';
          return;
        }
        var circ = "\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468";
        var html = "";
        for(var i=0;i<j.data.length;i++){
          var t = j.data[i];
          var nm = (t.creatorPerson || "").split("@")[0];
          var st = (t.startTime || "").substring(0,10);
          var tag = t.activityName || t.processName || "";
          html += '<tr><td class="idx">'+(circ.charAt(i)||(i+1))+'</td>'+
            '<td class="title">'+esc(t.title||"")+'</td>'+
            '<td class="ctr">'+esc(nm)+'</td>'+
            '<td class="tag">'+esc(tag)+'</td>'+
            '<td class="date">'+esc(st)+'</td></tr>';
        }
        body.innerHTML = html;
      }).catch(function(){});
    req("/x_processplatform_assemble_surface/jaxrs/read/count/my")
      .then(function(j){
        var e = gid("op-done-count");
        if(e && j.type === "success" && j.data) e.textContent = j.data.count || 0;
      }).catch(function(){});
  }

  function esc(s){
    return String(s===undefined||s===null?"":s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  /* ---------- 图表：取语句数据 -> 分组聚合 -> 重绘 ---------- */
  function aggregate(rows, field, value){
    var map = {}, order = [];
    for(var i=0;i<rows.length;i++){
      var k = rows[i][field];
      if(k === undefined || k === null || k === "") k = "\u672a\u5206\u7c7b";
      k = String(k);
      if(map[k] === undefined){ map[k] = 0; order.push(k); }
      map[k] += value ? (parseFloat(rows[i][value]) || 0) : 1;
    }
    return order.map(function(k){ return [k, Math.round(map[k]*100)/100]; });
  }

  function paintCharts(){
    var specs = SPEC.charts || [];
    for(var s=0;s<specs.length;s++){
      (function(sp){
        var box = ROOT.querySelector('[data-op-chart="'+sp.idx+'"]');
        if(!box) return;
        req("/x_query_assemble_surface/jaxrs/statement/"+sp.statement+
            "/execute/page/1/size/500", "POST")
          .then(function(j){
            if(j.type !== "success" || !j.data || !j.data.length) return;
            var pairs = aggregate(j.data, sp.field, sp.value);
            if(!pairs.length) return;
            if(sp.top) pairs = pairs.slice(0, sp.top);
            var t = sp.title || "";
            box.innerHTML = (sp.type === "pie")
              ? pieSvg(pairs, t) : colSvg(pairs, t);
          }).catch(function(){});
      })(specs[s]);
    }
  }

  function pieSvg(data, title){
    var total = 0; for(var i=0;i<data.length;i++) total += data[i][1];
    if(!total) total = 1;
    var cx=130, cy=130, r=78, ang=-Math.PI/2, paths="", labels="";
    for(var i=0;i<data.length;i++){
      var frac = data[i][1]/total, span = frac*2*Math.PI, a0=ang, a1=ang+span;
      var x0=cx+r*Math.cos(a0), y0=cy+r*Math.sin(a0);
      var x1=cx+r*Math.cos(a1), y1=cy+r*Math.sin(a1);
      var lg = span>Math.PI?1:0, c = CT[i%CT.length];
      paths += '<path d="M'+cx+','+cy+' L'+x0.toFixed(2)+','+y0.toFixed(2)+
               ' A'+r+','+r+' 0 '+lg+' 1 '+x1.toFixed(2)+','+y1.toFixed(2)+
               ' Z" fill="'+c+'" stroke="#fff" stroke-width="1"/>';
      var mid=(a0+a1)/2, lx=cx+(r+26)*Math.cos(mid), ly=cy+(r+26)*Math.sin(mid);
      var ex=lx+(Math.cos(mid)>=0?22:-22);
      labels += '<line x1="'+(cx+r*Math.cos(mid)).toFixed(2)+'" y1="'+
        (cy+r*Math.sin(mid)).toFixed(2)+'" x2="'+lx.toFixed(2)+'" y2="'+
        ly.toFixed(2)+'" stroke="#cbd5e0" stroke-width="1"/>'+
        '<text x="'+ex.toFixed(2)+'" y="'+ly.toFixed(2)+'" font-size="12" '+
        'fill="#4a5568" text-anchor="'+(Math.cos(mid)>=0?"start":"end")+
        '" dominant-baseline="middle">'+data[i][1]+'</text>';
      ang = a1;
    }
    return '<svg width="100%" viewBox="0 0 260 260" '+
      'preserveAspectRatio="xMidYMid meet" style="max-width:280px;display:block;'+
      'margin:0 auto"><text x="130" y="16" font-size="13" fill="#2d3748" '+
      'text-anchor="middle">'+esc(title)+'</text>'+paths+labels+'</svg>'+
      legend(data);
  }

  function colSvg(data, title){
    var w=300,h=220,pl=42,pr=14,pt=30,pb=34;
    var pw=w-pl-pr, ph=h-pt-pb, maxv=1;
    for(var i=0;i<data.length;i++) maxv=Math.max(maxv,data[i][1]);
    var step=Math.pow(10,String(Math.floor(maxv)).length-1);
    var top=Math.floor(maxv/step+1)*step; if(top<=maxv) top=maxv*1.15;
    var s="", i;
    for(i=0;i<6;i++){
      var y=pt+ph*(1-i/5), v=top*i/5;
      s += '<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(w-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="'+(i?"#eef2f7":"#cbd5e0")+'" stroke-width="1"/>'+
        '<text x="'+(pl-6)+'" y="'+y.toFixed(1)+'" font-size="10" fill="#94a3b8" '+
        'text-anchor="end" dominant-baseline="middle">'+fmt(v)+'</text>';
    }
    var n=data.length||1, slot=pw/n, bw=Math.min(34,slot*0.5);
    for(i=0;i<data.length;i++){
      var cxi=pl+slot*(i+0.5), bh=ph*(data[i][1]/top), y2=pt+ph-bh;
      s += '<rect x="'+(cxi-bw/2).toFixed(1)+'" y="'+y2.toFixed(1)+'" width="'+
        bw.toFixed(1)+'" height="'+bh.toFixed(1)+'" fill="'+CT[0]+'" rx="1"/>'+
        '<text x="'+cxi.toFixed(1)+'" y="'+(y2-4).toFixed(1)+'" font-size="10" '+
        'fill="#4a5568" text-anchor="middle">'+fmt(data[i][1])+'</text>'+
        '<text x="'+cxi.toFixed(1)+'" y="'+(h-pb+16)+'" font-size="10.5" '+
        'fill="#4a5568" text-anchor="middle">'+esc(data[i][0])+'</text>';
    }
    s += '<text x="'+Math.floor((pl+w-pr)/2)+'" y="18" font-size="13" '+
      'fill="#2d3748" text-anchor="middle">'+esc(title)+'</text>';
    return '<svg width="100%" viewBox="0 0 '+w+' '+h+'" '+
      'preserveAspectRatio="xMidYMid meet" style="max-width:320px;display:block;'+
      'margin:0 auto">'+s+'</svg>';
  }

  function fmt(v){
    if(v >= 10000) return (v/10000).toFixed(1)+"\u4e07";
    return (Math.round(v*100)/100).toString();
  }

  function legend(data){
    var s="";
    for(var i=0;i<data.length;i++){
      s += '<span class="lg"><i style="background:'+CT[i%CT.length]+'"></i>'+
        esc(data[i][0])+'</span>';
    }
    return '<div class="op-legend">'+s+'</div>';
  }

  function boot(){ try{ paintTop(); }catch(e){}
                   try{ paintTodo(); }catch(e){}
                   try{ paintCharts(); }catch(e){}
                   try{ loadViews(); }catch(e){}
                   try{ loadTables(); }catch(e){} }

  /* ---------- 真实业务视图嵌入 ----------
     data-embed-view="<应用id>|<视图id>" 的容器由原生
     MWF.xApplication.query.Query.Viewer 加载（与表单 View 模块同源），
     行点击自动走 layout.desktop.openApplication("process.Work",{jobId})。 */
  function viewShim(holder){
    return {
      "content": holder,
      "notice": function(c, t){ try{ MWF.xDesktop.notice(t || "info", {"x": "right", "y": "top"}, c); }catch(e){} },
      "alert": function(t, w, title, text){ try{ MWF.xDesktop.notice("info", {"x": "center", "y": "center"}, text || title || t || ""); }catch(e){} },
      "confirm": function(type, e, title, text, width, height, ok){ if(typeof ok === "function") ok(); }
    };
  }
  function loadViews(){
    var holders = ROOT.querySelectorAll("[data-embed-view]");
    if(!holders || !holders.length) return;
    var done = function(){
      for(var i=0; i<holders.length; i++){
        (function(h){
          var spec = (h.getAttribute("data-embed-view") || "").split("|");
          if(spec.length < 2 || !spec[0] || !spec[1]) return;
          var vjson = {
            "application": spec[0], "viewName": spec[1],
            "isTitle": (h.getAttribute("data-view-title") === "no") ? "no" : "yes",
            "select": "none", "actionbar": "none", "showActionbar": false,
            "isExpand": "no"
          };
          try{
            new MWF.xApplication.query.Query.Viewer(
              h, vjson, {"isload": true, "resizeNode": true},
              viewShim(h), null);
          }catch(e){
            h.innerHTML = '<div class="op-view-note">视图加载失败：' + e.message + '</div>';
          }
        })(holders[i]);
      }
    };
    if(window.MWF && MWF.xApplication && MWF.xApplication.query && MWF.xApplication.query.Query && MWF.xApplication.query.Query.Viewer){ done(); return; }
    if(window.MWF && MWF.xDesktop && MWF.xDesktop.requireApp){
      MWF.xDesktop.requireApp("query.Query", "Viewer", done);
    }
  }

  /* ---------- 自建表数据直连渲染 ----------
     data-embed-table = "<表flag>|<列定义>" 的容器，运行时直接调用
       POST /x_query_assemble_surface/jaxrs/table/list/table/{flag}/row/paging/1/size/N
     取真实行，前端渲染为 HTML 表格。

     ★ 为什么不用原生 query.Viewer：本版本（10.0.2）surface 的 dealPlan()
       只认 cms / 流程两类 Plan，**没有 TablePlan** 实现 —— table 类型视图
       执行必抛 ProcessPlatformPlan.adjustWhere NPE（已实证）。故自建表
       数据走「表行接口直读 + 前端渲染」这条无依赖通路。

     列定义：JSON 数组 [{k:"字段名", t:"列标题", w:宽度px, f:格式化}]
       f: "money"(千分位) | "num" | "date" | "" */
  function fmtCell(v, f){
    if(v === null || v === undefined || v === "") return "";
    if(f === "money"){
      var n = Number(v); if(isNaN(n)) return esc(String(v));
      return n.toLocaleString("zh-CN");
    }
    if(f === "num"){ var n2 = Number(v); return isNaN(n2) ? esc(String(v)) : String(Math.round(n2*100)/100); }
    if(f === "date"){ return esc(String(v).slice(0, 10)); }
    return esc(String(v));
  }
  function renderTable(holder, cols, rows){
    if(!rows || !rows.length){
      holder.innerHTML = '<div class="op-tbl-empty">暂无可展示的数据</div>';
      return;
    }
    var h = ['<table class="op-tbl"><thead><tr>'];
    for(var i=0;i<cols.length;i++) h.push('<th>'+esc(cols[i].t||cols[i].k)+'</th>');
    h.push('</tr></thead><tbody>');
    for(var r=0;r<rows.length;r++){
      h.push('<tr>');
      for(var c=0;c<cols.length;c++){
        var col=cols[c];
        h.push('<td'+(col.f==="money"?' class="num"':(col.f==="num"?' class="num"':''))+'>'
               + fmtCell(rows[r][col.k], col.f) + '</td>');
      }
      h.push('</tr>');
    }
    h.push('</tbody></table>');
    holder.innerHTML = h.join("");
  }
  function loadTables(){
    var holders = ROOT.querySelectorAll("[data-embed-table]");
    if(!holders || !holders.length) return;
    for(var i=0;i<holders.length;i++){
      (function(h){
        var spec = (h.getAttribute("data-embed-table") || "").split("|");
        if(spec.length < 2 || !spec[0]) return;
        var flag = spec[0], cols = [];
        try{ cols = JSON.parse(spec[1] || "[]"); }catch(e){ cols = []; }
        var size = parseInt(h.getAttribute("data-page-size") || "50", 10) || 50;
        h.innerHTML = '<div class="op-tbl-empty">数据加载中…</div>';
        req("/x_query_assemble_surface/jaxrs/table/list/table/"+flag
            +"/row/paging/1/size/"+size, "POST", "{}")
          .then(function(j){
            var d = (j && j.data) || [];
            renderTable(h, cols, d);
          })
          .catch(function(e){
            h.innerHTML = '<div class="op-tbl-err">数据加载失败：'
              + ((e && e.message) || "接口无响应") + '</div>';
          });
      })(holders[i]);
    }
  }

  /* ---------- 一键发起指定流程 ----------
     data-op="startone" data-process="<流程id>"：
     取当前登录人首个身份直接 startWork，成功即打开起草界面；
     身份缺失时退回待办中心「发起流程」页。 */
  function myIdentity(L){
    var u = (L && L.session && L.session.user) || (L && L.user) || null;
    if(!u) return "";
    var il = u.identityList;
    if(il && il.length){
      var id0 = il[0];
      if(typeof id0 === "string") return id0;
      if(id0 && id0.distinguishedName) return id0.distinguishedName;
    }
    var dn = u.distinguishedName || "";
    return (dn.indexOf("@I@") >= 0) ? dn : "";
  }
  function startOne(pid){
    var L = layoutRef();
    if(!L || !window.MWF || !MWF.Actions){ return; }
    var idn = myIdentity(L);
    if(!idn){ openApp("process.TaskCenter", {"navi": "start"}); return; }
    var A = MWF.Actions.get("x_processplatform_assemble_surface");
    A.startWork(pid, {"latest": true, "identity": idn}, function(json){
      var d = (json && json.data) || {};
      openApp("process.Work", {"workId": d.id || "", "jobId": d.job || ""});
    }, function(xhr){
      try{
        var j = JSON.parse(xhr.responseText);
        MWF.xDesktop.notice("error", {"x": "right", "y": "top"}, (j && j.message) || "发起失败");
      }catch(e){}
    });
  }


  /* ---------- 交互绑定：桌面原生动作 ----------
     生成侧给可点元素打 data-op 属性，这里统一接管点击：
       profile  → 打开个人设置（改密页签）
       logout   → 登出
       portal   → 打开门户（data-target=portalId, data-page=pageId）
       task     → 打开待办中心
       start    → 打开待办中心「发起流程」页
       app      → 打开流程应用（data-target=应用id）
     布局对象在桌面同 document（Html 模块注入），window.parent 兜底。 */
  function layoutRef(){
    try{ return window.layout || (window.parent && window.parent.layout) || null; }
    catch(e){ return null; }
  }
  function openApp(name, opts){
    var L = layoutRef();
    if(L && L.openApplication){
      try{ L.openApplication(null, name, opts || {}); return true; }catch(e){}
    }
    return false;
  }

  /* 门户「页内切换」：找当前已打开的门户实例，调官方 toPortal(portal, page)。
     —— PortalPage.js 定义 toPortal 会复用同一窗口重新 loadPortal，
        而 layout.openApplication 因 Portal.options.multitask=true 会**另开页签**。
     命中条件：实例有 toPortal 方法 且 options.portalId 与目标一致（同门户内切）。
     找不到（跨门户或无实例）时退回 openApplication 新开页。 */
  function gotoPortal(portalId, pageId){
    var L = layoutRef();
    var apps = (L && L.desktop && L.desktop.apps) || {};
    for(var k in apps){
      var a = apps[k];
      if(!a || typeof a.toPortal !== "function") continue;
      var op = (a.options && a.options.portalId) || "";
      if(op && portalId && op === portalId){
        try{ a.toPortal(portalId, pageId); return true; }catch(e){}
      }
    }
    return openApp("portal.Portal", {"portalId": portalId, "pageId": pageId});
  }
  ROOT.addEventListener("click", function(ev){
    var el = ev.target;
    while(el && el !== ROOT && !(el.getAttribute && el.getAttribute("data-op")))
      el = el.parentNode;
    if(!el || el === ROOT) return;
    var op = el.getAttribute("data-op");
    if(!op) return;
    if(el.tagName === "A") ev.preventDefault();
    var t = el.getAttribute("data-target") || "";
    var pg = el.getAttribute("data-page") || "";
    if(op === "profile") openApp("Profile", {"tab": "passwordConfigPage"});
    else if(op === "logout"){
      var L = layoutRef();
      if(L && L.logout){ try{ L.logout(); }catch(e){} }
    }
    else if(op === "portal") gotoPortal(t, pg);
    else if(op === "task") openApp("process.TaskCenter");
    else if(op === "start") openApp("process.TaskCenter", {"navi": "start"});
    else if(op === "app") openApp("process.Application",
                                  {"id": t, "appId": "process.Application" + t});
    else if(op === "startone"){
      var pc = el.getAttribute("data-process") || "";
      if(pc) startOne(pc);
    }
  });

  if(document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
</script>
"""


def _live_code(live):
    """渲染为**纯 JS 源码**（无 <script> 包裹）。

    用于放进 O2OA 门户页的 json.events.postLoad.code —— 表单引擎会执行它，
    而 Html 模块 insertAdjacentHTML 注入的 <script> 是不会执行的。
    """
    import json
    live = dict(live or {})
    live.setdefault("root", PAGE_ROOT)
    spec = json.dumps(live, ensure_ascii=False)
    return (_LIVE_JS.replace("__SPEC__", spec)
                   .replace("<script>", "").replace("</script>", "").strip())


def _live_script(live):
    """把 live 描述渲染成 <script> 标签（独立 HTML 预览用）。

    live = {
      "todo_page": 8,                       # 待办取几条
      "root": "op-root",                    # 页面根节点 id
      "charts": [ {"idx":0, "type":"pie", "title":"...",
                   "statement":"<statId>", "field":"contract_status",
                   "value":"" | "contract_amount", "top":6}, ... ],
    }
    """
    return "<script>\n" + _live_code(live) + "\n</script>"


# --------------------------------------------------------------------------
# 门户页数据：O2OA 要的是「表单定义」JSON，不是裸 HTML
#
# ★ 实证（2026-09-20）：94 个原生门户页的 PTL_PAGE.xdata **100% 是 JSON**；
#   我们原先写入的 10 页裸 HTML 在门户里 100% 白屏。
#   渲染链路（x_component_portal_Portal/PortalPage.js）：
#       page = JSON.decode(MWF.decodeJsonString(json.data.data))
#       new MWF.APPForm(this.formNode, page, {...})
#   → 即门户页被当作**表单**渲染，内容由 page.json.moduleList 的模块产出。
#     裸 HTML 过不了 JSON.decode，this.page 为 null，openPortal() 直接空转 = 白屏。
#
#   本函数把独立 HTML 页面转换成该结构：
#     · 页面标记  → 一个 type=Html 的模块（运行时 json.text 会被
#                   node.insertAdjacentHTML("beforebegin", text) 注入 DOM）
#     · <style>   → 保留在 Html 模块 text 内（仍在 document 内生效，已限域）
#     · 运行时 JS → json.events.postLoad.code（表单 postLoad 时由
#                   Form._loadEvents() 执行；Html 模块注入的 <script> 不执行）
# --------------------------------------------------------------------------

_PAGE_EVENTS = (
    "queryLoad", "beforeLoad", "beforeModulesLoad", "afterModulesLoad",
    "postLoad", "load", "afterLoad", "beforeClose", "help", "unload",
    "click", "dblclick", "keydown", "keypress", "keyup", "mousedown",
    "mousemove", "mouseout", "mouseover", "mouseup", "focus", "blur",
    "submit", "reset",
)


def _blank_events(post_load_code=""):
    ev = {}
    for k in _PAGE_EVENTS:
        ev[k] = {"code": post_load_code if k == "postLoad" else "", "html": ""}
    return ev


def portal_page_data(html, page_id, page_name, portal_id, portal_name,
                     description=""):
    """把独立门户页 HTML 转换成 O2OA 门户页数据（JSON 文本）。"""
    import json
    import re as _re

    html = html or ""
    m = _re.search(r"<style>(.*?)</style>", html, _re.S)
    css = (m.group(1).strip() if m else "")

    bm = _re.search(r"<body>(.*?)</body>", html, _re.S)
    body = (bm.group(1) if bm else html)
    body = _re.sub(r"<script>.*?</script>", "", body, flags=_re.S)
    body = _re.sub(r"\n{3,}", "\n\n", body).strip()

    scripts = _re.findall(r"<script>(.*?)</script>", html, _re.S)
    js_code = scripts[-1].strip() if scripts else ""

    text = ("<style>\n%s\n</style>\n%s" % (css, body)) if css else body

    mod_id = "html"
    module = {
        "id": mod_id,
        "name": "",
        "type": "Html",
        "description": "",
        "text": text,
        "container": "",
        "properties": {},
        "class": "",
        "styles": {},
        "recoveryStyles": None,
        "isSaved": True,
        "pid": "PC" + page_id + mod_id,
        "moduleName": "html",
    }

    page_json = {
        "id": page_id,
        "name": page_name,
        "type": "Form",
        "mode": "PC",
        "description": description or "",
        "application": portal_id,
        "applicationName": portal_name,
        "styles": {},
        "properties": {},
        "cssLinks": [],
        "scriptSrc": [],
        "jsheader": {"code": "", "html": ""},
        "events": _blank_events(js_code),
        "moduleList": {mod_id: module},
        "fieldList": {},
        "css": {"code": ""},
        "pageStyleType": "blue-simple",
        "pid": "PC" + page_id + page_id,
        "formStyleType": "default",
        "widgetList": [],
        "languageType": "none",
        "languageScript": {"code": "", "html": ""},
    }

    # ★ 顶层 html 是「表单 DOM 骨架」，Form._getModuleNodes() 靠它扫出
    #   mwftype 节点，再用节点 id 去 moduleList 取模块定义。缺了这段，
    #   Html 模块拿不到 node，整页仍然白屏。
    page_html = ('<div mwftype="form" id="%s" class="css css%s" style="">'
                 '<div mwftype="%s" id="%s" style=""></div></div>'
                 % (page_id, page_id.replace("-", ""), mod_id, mod_id))

    return json.dumps({
        "json": page_json,
        "html": page_html,
        "id": "",
        "isNewPage": False,
    }, ensure_ascii=False)


def page_data_to_html(data, title="门户页"):
    """把门户页数据还原成独立 HTML（离线预览用）。已是 HTML 则原样返回。"""
    import json
    import re as _re

    s = (data or "").strip()
    if not s.startswith("{"):
        return s
    try:
        d = json.loads(s)
    except Exception:
        return s

    j = d.get("json") or {}
    text = ""
    for mm in (j.get("moduleList") or {}).values():
        if isinstance(mm, dict) and mm.get("type") == "Html":
            text = mm.get("text") or ""
            break

    m = _re.search(r"<style>(.*?)</style>", text, _re.S)
    css = m.group(1) if m else ""
    markup = _re.sub(r"<style>.*?</style>", "", text, flags=_re.S).strip()
    js = ((j.get("events") or {}).get("postLoad") or {}).get("code") or ""
    script = ("<script>\n%s\n</script>" % js) if js else ""
    return _shell(title, css, markup + ("\n" + script if script else ""))
