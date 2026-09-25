# -*- coding: utf-8 -*-
"""
HR 门户 HTML 生成器（追加模块）
================================================================
对齐 O2OA 官方「人力资源管理系统」门户版式（refs/hr/ 8 张截图实读）。

官方版式骨架：
┌──────────────────────────────────────────────────────────────┐
│ 欢迎您！崔绿华   今天是2022年05月9日(周一)     个人设置 | 退出 │  ← 顶栏
├──────────────────────────────────────────────────────────────┤
│ ▌人力资源管理系统                                             │  ← 品牌条
├──────────────────────────────────────────────────────────────┤
│ 首页  员工档案  员工管理  人才市场  积分管理  考勤管理  员工自助  个人设置 │
│ ═════                                                        │
│ 个人信息  界面配置  常用意见  外出授权  修改密码  单点登录  人脸登录 │  ← 二级标签
├──────────────────────────────────────────────────────────────┤
│  ┌────────────┬────────────┬────────────┐                    │
│  │ 新闻公告    │ 员工自助    │ 人事变动公示 │                    │
│  │ （大图卡）  │ （6彩色图标）│ （小表）    │                    │
│  ├────────────┼────────────┼────────────┤                    │
│  │ 待办工作    │ 岗位报名    │ 积分公示    │                    │
│  ├────────────┼────────────┼────────────┤                    │
│  │ 待阅工作    │ 本月考勤    │ 统计图      │                    │
│  └────────────┴────────────┴────────────┘                    │
├──────────────────────────────────────────────────────────────┤
│ 版权所有：O2OA                                               │
└──────────────────────────────────────────────────────────────┘

【注意】Page.data **不是**裸 HTML：O2OA 把门户页当表单渲染
（PortalPage.js → MWF.APPForm），数据必须是 JSON 表单定义。
本模块产出独立 HTML，再由 o2oa_portal.portal_page_data() 转换。
"""

from o2oa_portal import (
    C_BRAND, C_BRAND_DK, C_BRAND_BG, C_TEXT, C_TEXT_SUB, C_MUTED,
    C_BORDER, C_STRIPE, CHART_COLORS, BASE_CSS,
    _shell, _topbar, _pie_svg, _column_svg, _legend_html, _live_script,
    scope_css, wrap_root,
)

# 官方一级导航（照截图，共 8 项）
HR_NAV = [
    "\u9996\u9875", "\u5458\u5de5\u6863\u6848", "\u5458\u5de5\u7ba1\u7406",
    "\u4eba\u624d\u5e02\u573a", "\u79ef\u5206\u7ba1\u7406", "\u8003\u52e4\u7ba1\u7406",
    "\u5458\u5de5\u81ea\u52a9", "\u4e2a\u4eba\u8bbe\u7f6e",
]

# 官方二级标签（照截图 1652073737436）
HR_SUBNAV = [
    "\u4e2a\u4eba\u4fe1\u606f", "\u754c\u9762\u914d\u7f6e", "\u5e38\u7528\u610f\u89c1",
    "\u5916\u51fa\u6388\u6743", "\u4fee\u6539\u5bc6\u7801", "\u5355\u70b9\u767b\u5f55",
    "\u4eba\u8138\u767b\u5f55",
]

# 员工自助 6 个彩色圆角图标（照截图）
HR_QUICK = [
    ("\u6211\u7684\u6863\u6848", "#4a8fe7", "\u25A4"),
    ("\u6211\u7684\u62a5\u540d", "#38b2ac", "\u270E"),
    ("\u6211\u7684\u79ef\u5206", "#ed8936", "\u2605"),
    ("\u6211\u8981\u8bf7\u5047", "#9f7aea", "\u2708"),
    ("\u6211\u8981\u52a0\u73ed", "#f6ad55", "\u23F0"),
    ("\u6211\u8981\u51fa\u5dee", "#4299e1", "\u2708"),
]

HR_CSS = BASE_CSS + """
/* ---------- 品牌条 ---------- */
.hr-brand {
  height: 52px; line-height: 52px; padding: 0 26px;
  font-size: 19px; font-weight: 700; color: %(brand_dk)s;
  background: linear-gradient(90deg, #f4f9ff 0%%, #ffffff 62%%);
  border-bottom: 1px solid %(border)s; letter-spacing: .5px;
}
.hr-brand .mark { color: %(brand)s; margin-right: 6px; }

/* ---------- HR 顶部一级导航 ---------- */
.hr-nav {
  height: 44px; line-height: 44px; padding: 0 26px;
  border-bottom: 1px solid %(border)s; background: #fff;
  white-space: nowrap; overflow-x: auto;
}
.hr-nav a {
  display: inline-block; height: 44px; line-height: 44px;
  padding: 0 20px; font-size: 14.5px; color: %(sub)s;
  border-bottom: 2px solid transparent;
}
.hr-nav a.on { color: %(brand_dk)s; font-weight: 600; border-bottom-color: %(brand)s; }

/* ---------- HR 二级标签 ---------- */
.hr-subnav {
  height: 38px; line-height: 38px; padding: 0 26px;
  background: #fbfdff; border-bottom: 1px solid %(border)s;
  white-space: nowrap; overflow-x: auto;
}
.hr-subnav a {
  display: inline-block; padding: 0 14px; font-size: 12.5px; color: %(sub)s;
}
.hr-subnav a.on { color: %(brand_dk)s; font-weight: 600; }

/* ---------- 矩阵卡片 ---------- */
.hr-matrix { padding: 14px 18px 22px; }
.hr-row { display: flex; gap: 14px; margin-bottom: 14px; align-items: stretch; }
.hr-col { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; }
.hr-col.wide { flex: 1.4 1 0; }

/* ---------- 大图新闻卡 ---------- */
.hr-news-img {
  height: 108px; border-radius: 3px; margin: 12px 12px 0;
  background: linear-gradient(120deg, #4a8fe7 0%%, #6fb3f2 100%%);
  position: relative; overflow: hidden;
}
.hr-news-img .cap {
  position: absolute; left: 0; right: 0; bottom: 0;
  padding: 6px 10px; font-size: 12px; color: #fff;
  background: rgba(0,0,0,.32);
}
.hr-news-list { padding: 8px 12px 12px; }
.hr-news-list li {
  list-style: none; padding: 6px 0; font-size: 12.5px; color: %(sub)s;
  border-bottom: 1px dashed #eef2f7;
}
.hr-news-list li:before {
  content: ""; display: inline-block; width: 5px; height: 5px;
  border-radius: 50%%; background: %(brand)s; margin-right: 8px;
  vertical-align: middle;
}
.hr-news-list li .d { float: right; color: %(muted)s; font-size: 11.5px; }

/* ---------- 四宫格小表 ---------- */
.hr-mini-table { width: 100%%; border-collapse: collapse; }
.hr-mini-table th, .hr-mini-table td {
  padding: 7px 10px; font-size: 12.5px; text-align: left;
  border-bottom: 1px solid #eef2f7;
}
.hr-mini-table th { color: %(sub)s; font-weight: 500; background: #fafcfe; }
.hr-mini-table tbody tr:nth-child(even) { background: %(stripe)s; }

/* ---------- 积分卡（年度/永久） ---------- */
.hr-point-box { padding: 14px 12px; display: flex; gap: 10px; }
.hr-point-box .pb {
  flex: 1 1 0; text-align: center; padding: 12px 6px;
  background: #f7fafd; border: 1px solid %(border)s; border-radius: 4px;
}
.hr-point-box .pb .n {
  font-size: 22px; font-weight: 700; color: %(brand_dk)s;
}
.hr-point-box .pb .n small { font-size: 12px; font-weight: 400; color: %(sub)s; }
.hr-point-box .pb .l { font-size: 12px; color: %(muted)s; margin-top: 4px; }
.hr-point-box .pb .r { font-size: 11.5px; color: #e07b39; margin-top: 3px; }
.hr-point-btn {
  display: block; margin: 0 12px 14px; height: 34px; line-height: 34px;
  text-align: center; font-size: 13px; color: #fff; border-radius: 3px;
  background: %(brand)s;
}

/* ---------- 排名（带蓝色排名块） ---------- */
.hr-rank-tbl { width: 100%%; border-collapse: collapse; }
.hr-rank-tbl th, .hr-rank-tbl td {
  padding: 7px 10px; font-size: 12.5px; border-bottom: 1px solid #eef2f7;
}
.hr-rank-tbl th { color: %(sub)s; font-weight: 500; background: #fafcfe; text-align: left; }
.hr-rank-tbl td.rk { width: 46px; text-align: center; }
.hr-rank-tbl td.rk span {
  display: inline-block; min-width: 22px; height: 20px; line-height: 20px;
  padding: 0 5px; border-radius: 2px; font-size: 11.5px;
  background: %(brand)s; color: #fff;
}

/* ---------- 考勤小月历 ---------- */
.hr-cal { padding: 10px 12px 14px; }
.hr-cal .hd {
  text-align: center; font-size: 13px; color: %(text)s; margin-bottom: 8px;
}
.hr-cal table { width: 100%%; border-collapse: collapse; }
.hr-cal th {
  font-size: 11.5px; color: %(muted)s; font-weight: 400; padding: 4px 0;
}
.hr-cal td {
  text-align: center; font-size: 12px; padding: 5px 0; color: %(sub)s;
  border-radius: 3px;
}
.hr-cal td.other { color: #cbd5e0; }
.hr-cal td.on { background: %(brand_bg)s; color: %(brand_dk)s; font-weight: 600; }
.hr-cal td.late { color: #e07b39; font-weight: 600; }

/* ---------- 底部版权 ---------- */
.hr-footer {
  padding: 16px 0 22px; text-align: center;
  font-size: 12px; color: %(muted)s;
}
""" % {
    "brand": C_BRAND, "brand_dk": C_BRAND_DK, "brand_bg": C_BRAND_BG,
    "text": C_TEXT, "sub": C_TEXT_SUB, "muted": C_MUTED,
    "border": C_BORDER, "stripe": C_STRIPE,
}


# HR_NAV / HR_SUBNAV 各项的点击行为，由 def_hr.py 注入：
#   {文本: (portalId, pageId)}  → data-op="portal"
#   {文本: ("profile",)}        → data-op="profile"
#   {文本: ("start",)}          → data-op="start"
#   {文本: ("startone", 流程id)} → data-op="startone"（一键发起指定流程）
# 未命中的导航项 → task（待办中心）；自助图标 → start。
HR_NAV_TARGETS = {}


def _op_attrs_of(t):
    if not t:
        return 'data-op="task"'
    if t[0] == "profile":
        return 'data-op="profile"'
    if t[0] == "start":
        return 'data-op="start"'
    if t[0] == "startone":
        return 'data-op="startone" data-process="%s"' % (t[1] if len(t) > 1 else "")
    return 'data-op="portal" data-target="%s" data-page="%s"' % (t[0], t[1] if len(t) > 1 else "")


def _hr_op_attrs(text):
    return _op_attrs_of(HR_NAV_TARGETS.get(text))


def _hr_header(active_nav=0, active_sub=0):
    nav = "".join(
        '<a href="#" class="%s" %s>%s</a>'
        % ("on" if i == active_nav else "", _hr_op_attrs(t), t)
        for i, t in enumerate(HR_NAV)
    )
    # 二级导航均为「个人设置」类入口（与官方一致），统一开 Profile 组件。
    sub = "".join(
        '<a href="#" class="%s" data-op="profile">%s</a>'
        % ("on" if i == active_sub else "", t)
        for i, t in enumerate(HR_SUBNAV)
    )
    return (
        '<div class="hr-nav">%s</div>'
        '<div class="hr-subnav">%s</div>' % (nav, sub)
    )


def _hr_card(title, body_html, more=True):
    return (
        '<div class="op-card">'
        '<div class="hd"><span class="t">%s</span>%s</div>'
        '<div class="bd">%s</div></div>'
        % (title, '<span class="more">\u66f4\u591a \u00BB</span>' if more else "",
           body_html)
    )


def _hr_news_card(news, big_caption=""):
    img = ('<div class="hr-news-img"><div class="cap">%s</div></div>'
           % big_caption) if big_caption else ""
    lis = "".join(
        '<li>%s<span class="d">%s</span></li>' % (t, d) for t, d in news
    )
    return _hr_card("\u65b0\u95fb\u516c\u544a", img + '<ul class="hr-news-list">%s</ul>' % lis)


def _hr_quick_card(quick):
    # 快捷图标：命中 HR_NAV_TARGETS 的（如「我的档案」→ 员工档案页）直达，
    # 未命中的（如「我要请假」）→ 任务中心「发起流程」页。
    items = "".join(
        '<div class="q" %s><div class="ic" style="background:%s">%s</div>'
        '<div class="lb">%s</div></div>'
        % (_hr_quick_attrs(t), c, i, t)
        for t, c, i in quick
    )
    return _hr_card("\u5458\u5de5\u81ea\u52a9",
                    '<div class="op-quick">%s</div>' % items)


def _hr_quick_attrs(text):
    t = HR_NAV_TARGETS.get(text)
    if t and t[0] == "startone":
        return _op_attrs_of(t)
    if t and t[0] not in ("profile", "start", "startone"):
        return 'data-op="portal" data-target="%s" data-page="%s"' % (t[0], t[1] if len(t) > 1 else "")
    if t and t[0] == "profile":
        return 'data-op="profile"'
    return 'data-op="start"'


def _hr_mini_table(title, cols, rows, more=True):
    th = "".join("<th>%s</th>" % c for c in cols)
    trs = "".join(
        "<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>" for r in rows
    )
    body = ('<table class="hr-mini-table"><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table>' % (th, trs))
    return _hr_card(title, body, more)


def _hr_todo_card(title, rows, body_id=None):
    """待办工作/待阅工作：序号 + 标题 + 经办 + 日期。"""
    circled = "\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468"
    th = "<th>\u5e8f\u53f7</th><th>\u6807\u9898</th><th>\u7ecf\u529e</th><th>\u65e5\u671f</th>"
    trs = []
    for i, (t, p, d) in enumerate(rows):
        idx = circled[i] if i < len(circled) else str(i + 1)
        trs.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (idx, t, p, d))
    attr = '' if body_id is None else ' id="%s"' % body_id
    body = ('<table class="hr-mini-table"><thead><tr>%s</tr></thead>'
            '<tbody%s>%s</tbody></table>' % (th, attr, "".join(trs)))
    hd_extra = ('<span class="more">\u65b0\u5efa \u2295\u3000\u66f4\u591a \u00BB</span>')
    return (
        '<div class="op-card">'
        '<div class="hd"><span class="t">%s</span>%s</div>'
        '<div class="bd">%s</div></div>' % (title, hd_extra, body)
    )


def _hr_point_card(my_point, bounty_rows, more=True):
    """官方积分管理：我的积分（年度/永久） + 积分兑换按钮 + 积分悬赏表。"""
    yp = my_point.get("year_point", 0)
    yp_rank = my_point.get("year_rank", 0)
    tp = my_point.get("total_point", 0)
    tp_rank = my_point.get("total_rank", 0)

    box = (
        '<div class="hr-point-box">'
        '<div class="pb"><div class="n">%s<small> \u5206</small></div>'
        '<div class="l">\u5e74\u5ea6\u79ef\u5206</div>'
        '<div class="r">%s \u540d</div></div>'
        '<div class="pb"><div class="n">%s<small> \u5206</small></div>'
        '<div class="l">\u6c38\u4e45\u79ef\u5206</div>'
        '<div class="r">%s \u540d</div></div>'
        '</div>'
        '<a href="#" class="hr-point-btn">\u79ef\u5206\u5151\u6362</a>'
        % (yp, yp_rank, tp, tp_rank)
    )
    th = ("<th>\u5206\u6570\u6807\u7b7e</th><th>\u8bfe\u9898</th>"
          "<th>\u65e5\u671f</th>")
    trs = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % r
        for r in bounty_rows
    )
    box += ('<table class="hr-mini-table"><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table>' % (th, trs))
    return _hr_card("\u6211\u7684\u79ef\u5206\u4e0e\u79ef\u5206\u60ac\u8d4f", box, more)


def _hr_rank_card(title, rows, more=True):
    """个人年度排名（姓名|积分|排名），带蓝色排名块。"""
    th = "<th>\u59d3\u540d</th><th>\u79ef\u5206</th><th>\u6392\u540d</th>"
    trs = "".join(
        '<tr><td>%s</td><td>%s</td><td class="rk"><span>%s</span></td></tr>' % r
        for r in rows
    )
    body = ('<table class="hr-rank-tbl"><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table>' % (th, trs))
    return _hr_card(title, body, more)


def _hr_calendar(year, month, today, late_days=(), period_text=""):
    """官方考勤小月历（周一 ~ 周日 7 列网格）。"""
    import calendar as _cal
    weeks = _cal.Calendar(firstweekday=0).monthdayscalendar(year, month)
    th = "".join("<th>%s</th>" % w for w in
                 ["\u4e00", "\u4e8c", "\u4e09", "\u56db",
                  "\u4e94", "\u516d", "\u65e5"])
    trs = []
    for wk in weeks:
        tds = []
        for d in wk:
            if d == 0:
                tds.append('<td class="other">-</td>')
                continue
            cls = []
            if d == today:
                cls.append("on")
            if d in late_days:
                cls.append("late")
            tds.append('<td class="%s">%d</td>' % (" ".join(cls), d))
        trs.append("<tr>%s</tr>" % "".join(tds))
    body = (
        '<div class="hr-cal">'
        '<div class="hd">%d\u5e74%02d\u6708\u3000\u8003\u52e4\u5468\u671f\uff1a%s</div>'
        '<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
        '</div>' % (year, month, period_text, th, "".join(trs))
    )
    return _hr_card("\u672c\u6708\u8003\u52e4", body, True)


def _hr_chart_card(title, ctype, data, is_on=True, idx=None):
    tools = (
        '<div class="op-chart-tools">'
        '<span class="tg on">\u67f1\u72b6\u56fe</span>'
        '<span class="tg">\u997c\u72b6\u56fe</span>'
        '</div>'
    )
    svg = _pie_svg(data, title) if ctype == "pie" else _column_svg(data, title)
    attr = '' if idx is None else ' data-op-chart="%d"' % idx
    return _hr_card(title, tools + '<div class="op-chart-body"%s>%s</div>' % (attr, svg))


def hr_portal_html(user="\u79d8\u4e66\u957f", date_text="", news=(),
                   quick=None, change_public=(),
                   todo_rows=(), read_rows=(), job_rows=(),
                   point_rows=(), my_point=None, bounty_rows=(),
                   rank_rows=(), dept_rank_rows=(), calendar_args=None,
                   charts=(), active_nav=0, active_sub=0, live=None):
    """
    生成官方 HR 门户首页 HTML。

    :param news:          [(标题, 日期)] 新闻公告
    :param quick:         [(文字, 颜色, 图标)] 员工自助 6 图标
    :param change_public: {"transfer":[(姓名,日期,部门,岗位)], "regular":[...],
                           "onboard":[...], "resign":[...]}
    :param todo_rows:     [(标题, 经办, 日期)] 待办工作
    :param read_rows:     [(标题, 经办, 日期)] 待阅工作
    :param job_rows:      [(岗位, 部门, 发布时间, 状态)] 岗位报名
    :param point_rows:    [(分数标签, 课题, 日期)] 积分悬赏
    :param my_point:      {"year_point":,"year_rank":,"total_point":,"total_rank":}
    :param rank_rows:     [(姓名, 积分, 排名)] 个人年度排名
    :param dept_rank_rows:[(部门, 人均积分, 月排名)] 部门月度人均积分排名
    :param calendar_args: {"year":,"month":,"today":,"late_days":[],"period_text":}
    :param charts:        [(标题, 类型, [(分类,数值)], 是否选中)]
    """
    quick = quick if quick is not None else HR_QUICK
    my_point = my_point or {}
    change_public = change_public or {}

    parts = []
    parts.append(_topbar(user, date_text))
    parts.append(
        '<div class="hr-brand">'
        '<span class="mark">\u258c</span>\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u7cfb\u7edf'
        '</div>'
    )
    parts.append(_hr_header(active_nav, active_sub))

    m = ['<div class="hr-matrix">']

    # ---- 第 1 行：新闻公告（大图卡） | 员工自助（6 彩图标） | 人事变动公示 ----
    m.append('<div class="hr-row">')
    m.append('<div class="hr-col wide">%s</div>'
             % _hr_news_card(news, "\u4e2d\u56fd\u590d\u6750\u534f\u4f1a\u00b7"
                                   "\u4eba\u624d\u57f9\u8bad\u4e0e\u804c\u4e1a\u53d1\u5c55"))
    m.append('<div class="hr-col">%s</div>' % _hr_quick_card(quick))
    ch = (change_public.get("transfer") or [])[:5]
    m.append('<div class="hr-col">%s</div>'
             % _hr_mini_table("\u4eba\u4e8b\u53d8\u52a8\u516c\u793a",
                              ["\u59d3\u540d", "\u65e5\u671f", "\u90e8\u95e8", "\u5c97\u4f4d"],
                              ch))
    m.append('</div>')

    # ---- 第 2 行：待办工作 | 岗位报名 | 积分公示 ----
    m.append('<div class="hr-row">')
    m.append('<div class="hr-col wide">%s</div>'
             % _hr_todo_card("\u5f85\u529e\u5de5\u4f5c", todo_rows,
                             body_id="op-todo-body"))
    jr = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % r
        for r in job_rows
    )
    m.append('<div class="hr-col">%s</div>'
             % _hr_card("\u5c97\u4f4d\u62a5\u540d",
                        '<table class="hr-mini-table"><thead><tr>'
                        '<th>\u5c97\u4f4d</th><th>\u62db\u8058\u90e8\u95e8</th>'
                        '<th>\u53d1\u5e03\u65f6\u95f4</th><th>\u72b6\u6001</th>'
                        '</tr></thead><tbody>%s</tbody></table>' % jr))
    m.append('<div class="hr-col">%s</div>'
             % _hr_rank_card("\u79ef\u5206\u516c\u793a", rank_rows[:6]))
    m.append('</div>')

    # ---- 第 3 行：待阅工作 | 本月考勤（小月历） | 部门月度人均积分排名 ----
    m.append('<div class="hr-row">')
    m.append('<div class="hr-col wide">%s</div>' % _hr_todo_card("\u5f85\u9605\u5de5\u4f5c", read_rows))
    ca = calendar_args or {}
    m.append('<div class="hr-col">%s</div>' % _hr_calendar(
        ca.get("year", 2026), ca.get("month", 5), ca.get("today", 9),
        tuple(ca.get("late_days", ())), ca.get("period_text", "")))
    dr = "".join(
        '<tr><td>%s</td><td>%s</td><td class="rk"><span>%s</span></td></tr>' % r
        for r in dept_rank_rows
    )
    m.append('<div class="hr-col">%s</div>'
             % _hr_card("\u90e8\u95e8\u6708\u5ea6\u4eba\u5747\u79ef\u5206\u6392\u540d",
                        '<table class="hr-rank-tbl"><thead><tr>'
                        '<th>\u90e8\u95e8</th><th>\u4eba\u5747\u79ef\u5206</th>'
                        '<th>\u6708\u6392\u540d</th></tr></thead>'
                        '<tbody>%s</tbody></table>' % dr))
    m.append('</div>')

    # ---- 第 4 行：我的积分（年度/永久 + 兑换 + 悬赏） | 统计图×2 ----
    if my_point or bounty_rows or charts:
        m.append('<div class="hr-row">')
        if my_point or bounty_rows:
            m.append('<div class="hr-col wide">%s</div>'
                     % _hr_point_card(my_point, bounty_rows[:4]))
        for _i, (title, ctype, data, on) in enumerate(charts):
            m.append('<div class="hr-col">%s</div>'
                     % _hr_chart_card(title, ctype, data, on, idx=_i))
        m.append('</div>')

    m.append('</div>')       # /hr-matrix
    m.append('<div class="hr-footer">\u7248\u6743\u6240\u6709\uff1aO2OA</div>')

    body = "".join(parts) + "".join(m)
    script = _live_script(live) if live else ""
    return _shell("\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u7cfb\u7edf",
                  scope_css(HR_CSS),
                  wrap_root(body) + (("\n" + script) if script else ""))


def biz_header(nav, nav_targets, active_nav=0, subnav=None, active_sub=0):
    """通用一级/二级导航条（OA 惯例的横向 Tab）。

    :param nav: 一级导航文字列表
    :param nav_targets: {文字: target}，target 见 _op_attrs_of 约定；
                        未命中 → 待办中心（task）。
    :param subnav: 二级标签（不传则用统一的个人设置类入口）
    """
    sub_items = subnav if subnav is not None else HR_SUBNAV
    nav_html = "".join(
        '<a href="#" class="%s" %s>%s</a>'
        % ("on" if i == active_nav else "",
           _op_attrs_of(nav_targets.get(t)), t)
        for i, t in enumerate(nav)
    )
    if subnav is None:
        sub_html = "".join(
            '<a href="#" class="%s" data-op="profile">%s</a>'
            % ("on" if i == active_sub else "", t)
            for i, t in enumerate(sub_items)
        )
    else:
        sub_html = "".join(
            '<a href="#" class="%s" %s>%s</a>'
            % ("on" if i == active_sub else "",
               _op_attrs_of(nav_targets.get(t)), t)
            for i, t in enumerate(sub_items)
        )
    return (
        '<div class="hr-nav">%s</div>'
        '<div class="hr-subnav">%s</div>' % (nav_html, sub_html)
    )


def biz_view_page_html(title, brand, nav, nav_targets, subtitle="", nav_active=0,
                       sections=(), actions=(), date_text="", live=None,
                       subnav=None, active_sub=0):
    """通用「业务栏目」页：门户框架(品牌条 + 导航) + 操作按钮条 + 真实业务数据。

    与 hr_view_page_html 同构，但品牌名与导航可配 —— 供 01/03/04/05 四个
    应用复用（这些应用此前没有门户）。

    :param brand: 品牌条文字，如「项目管理应用」
    :param nav: 一级导航文字列表（OA 惯例：首页 / 各业务栏目 / 个人设置）
    :param nav_targets: {文字: (target...)} —— target 见 _op_attrs_of：
        ("portal",) 同门户内跳转需 (portalId, pageId)；("startone", 流程id) 一键发起；
        ("start",) 发起中心；("profile",) 个人设置。
    :param sections: 两种形态混合（同 hr_view_page_html）。
    :param actions:  [(文字, op, 参数, plain)]
    """
    from o2oa_portal import view_holder, table_holder, action_bar, _topbar

    parts = []
    parts.append(_topbar("\u79d8\u4e66\u957f", date_text))
    parts.append(
        '<div class="hr-brand">'
        '<span class="mark">\u258c</span>%s</div>' % brand
    )
    parts.append(biz_header(nav, nav_targets, nav_active, subnav, active_sub))

    m = ['<div class="hr-row"><div class="hr-col" style="flex:1 1 100%">']
    head = '<div class="op-view-cap" style="font-size:17px">%s</div>' % title
    if subtitle:
        head += ('<div class="op-view-note" style="padding-top:0">%s</div>'
                 % subtitle)
    m.append(head)
    if actions:
        m.append(action_bar(actions))
    for sec in sections:
        if len(sec) == 4 and isinstance(sec[2], (list, tuple)):
            cap, tflag, cols, height = sec
            m.append(table_holder(tflag, cols, cap, height=height))
        else:
            cap, app_id, view_id, height = sec
            m.append(view_holder(app_id, view_id, cap, height=height))
    m.append('</div></div>')
    m.append('<div class="hr-footer">\u7248\u6743\u6240\u6709\uff1aO2OA</div>')

    body = "".join(parts) + "".join(m)
    live = {} if live is None else live
    script = _live_script(live)
    return _shell(title,
                  scope_css(HR_CSS),
                  wrap_root(body) + (("\n" + script) if script else ""))


def hr_view_page_html(title, subtitle="", nav_active=0, sections=(),
                      actions=(), date_text="", live=None):
    """栏目「真实业务」页：HR 门户框架 + 操作按钮条 + 嵌入真实业务数据。

    :param sections: 两种形态混合：
        · 表数据（推荐）：(小标题, 表flag, 列定义[[字段,标题,格式],...], 高度px)
          —— 由 _LIVE_JS.loadTables() 直读自建表行接口渲染（唯一可靠通路）。
        · 原生视图：     (小标题, 应用id, 视图id, 高度px)
          —— 仅流程/内容类视图可用（table 类型视图在本版本执行会 NPE）。
    :param actions:  [(文字, op, 参数, plain)] —— op ∈ startone/portal/task/start/profile
    """
    from o2oa_portal import view_holder, table_holder, action_bar, _topbar

    parts = []
    parts.append(_topbar("\u79d8\u4e66\u957f", date_text))
    parts.append(
        '<div class="hr-brand">'
        '<span class="mark">\u258c</span>\u4eba\u529b\u8d44\u6e90\u7ba1\u7406\u7cfb\u7edf'
        '</div>'
    )
    parts.append(_hr_header(nav_active))

    m = ['<div class="hr-row"><div class="hr-col" style="flex:1 1 100%">']
    head = '<div class="op-view-cap" style="font-size:17px">%s</div>' % title
    if subtitle:
        head += ('<div class="op-view-note" style="padding-top:0">%s</div>'
                 % subtitle)
    m.append(head)
    if actions:
        m.append(action_bar(actions))
    for sec in sections:
        if len(sec) == 4 and isinstance(sec[2], (list, tuple)):
            # 表数据模式：(标题, 表flag, 列定义, 高度)
            cap, tflag, cols, height = sec
            m.append(table_holder(tflag, cols, cap, height=height))
        else:
            cap, app_id, view_id, height = sec
            m.append(view_holder(app_id, view_id, cap, height=height))
    m.append('</div></div>')
    m.append('<div class="hr-footer">\u7248\u6743\u6240\u6709\uff1aO2OA</div>')

    body = "".join(parts) + "".join(m)
    live = {} if live is None else live   # 空 SPEC 也要带绑定层 + 视图加载器
    script = _live_script(live)
    return _shell(title,
                  scope_css(HR_CSS),
                  wrap_root(body) + (("\n" + script) if script else ""))
