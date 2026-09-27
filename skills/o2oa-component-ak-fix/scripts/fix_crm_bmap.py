#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 O2OA「客户管理」(CRM) 应用中百度地图 AK 失效导致的 alert 弹窗。

════════════════════ 根因（已实证，非推测） ════════════════════
弹窗文案：  "APP被您禁用啦。详情查看：http://lbsyun.baidu.com/apiconsole/key#。"

完整因果链：
  1. CRM 组件内硬编码百度地图 jsapi v2.0 的旧 AK（2016 年申请）：
         Qac4WmBvHXiC87z3HjtRrbotCE3sC9Zg
     出现位置：
       · Main.js      createContent()  → 进入应用即 loadDom(apiPath)   ←★真正的触发点
       · BaiduMap.js  loadResource() / MaxMap.loadResource()
       · Main.min.js / BaiduMap.min.js / BaiduMap.min.min.js
  2. 该 AK 已被删除。百度 verify 接口实测返回：
         {"error":201,"error_msg":"APP被用户自己删除","popup":0}
  3. 百度前端 SDK 内置错误表：
         ta = {…, 201:"APP被您禁用啦。", 202:"APP被管理员删除啦。", 220:"APP Referer校验失败。", …}
     命中 201 → alert(b) → 阻塞式原生弹窗。
  4. 弹窗是【附着副作用】：CRM 主体界面（客户/线索/公海/联系人）照常渲染，
     仅地图相关功能不可用。

════════════════════ 修复策略 ════════════════════
不引入新 AK、不依赖外网、不删功能，只做优雅降级：

  ① Main.js / Main.min.js —— 切断"进入应用即拉百度脚本"：
     apiPath 置空 + if(false) 短路该分支。

  ② BaiduMap.js —— 整块重写 loadResource()：
     · 不再 loadDom 百度脚本
     · 不再加载依赖 window.BMap 的 BDMarkerTool.js
       （否则报 ReferenceError: BMap is not defined）
     · 直接走 _loadMap()
     另给 `new BMap.Map()` 加守卫，无 BMap 时渲染占位提示而非抛错。

  ★ 为什么必须连 loadDom 和 BDMarkerTool 一起切：
     - loadDom("") 会请求空 URL，拿到 HTML 页 → SyntaxError: Unexpected token '<'
     - BDMarkerTool.js 末尾是自执行块，依赖 window.BMap → ReferenceError

  ③ *.min.js —— 只做 URL 字符串替换。压缩文件严禁插入 /* */ 块注释
     （会与相邻注释嵌套冲突），标记放文件头部单行。

幂等：以 MARK 判定，重复执行不叠加。

用法：  python fix_crm_bmap.py <目录，含 Main*.js / BaiduMap*.js>
选配：  --verify  修补后即打印每处替换的命中数
"""
import io
import os
import sys

OLD_AK = "Qac4WmBvHXiC87z3HjtRrbotCE3sC9Zg"
MARK = "O2OA-NOMAP-PATCH"

# ══════════════ ① Main.js ══════════════
MAIN_APIPATH_OLD = (
    'var apiPath = layout.protocol+"//api.map.baidu.com/getscript?v=2.0&ak=%s'
    '&services=&t=20161219171637";' % OLD_AK
)
MAIN_APIPATH_NEW = 'var apiPath = ""; /* %s: 原 ak=%s 已失效(error 201) */' % (MARK, OLD_AK)
MAIN_GUARD_OLD = "if( !window.BDMapApiLoaded ){"
MAIN_GUARD_NEW = "if( false /* %s: 停用百度地图脚本加载 */ && !window.BDMapApiLoaded ){" % MARK

# ══════════════ ② BaiduMap.js ══════════════
BM_LOADRES_OLD = """    loadResource:function(callback){
        window.BMap_loadScriptTime = (new Date).getTime();
        //var apiPath = "http://api.map.baidu.com/api?v=2.0&ak=%(ak)s";
        var apiPath = "http://api.map.baidu.com/getscript?v=2.0&ak=%(ak)s&services=&t=20161219171637";
        if( !window.BDMapApiLoaded ){
            COMMON.AjaxModule.loadDom(apiPath, function () {
                window.BDMapApiLoaded = true;
                if( !window.BDMarkerToolLoaded ){
                    COMMON.AjaxModule.load( "/x_component_CRM/BDMarkerTool.js", function(){
                        window.BDMarkerToolLoaded = true;
                        this._loadMap();
                        if (callback)callback();
                    }.bind(this) );
                }else{
                    this._loadMap();
                    if (callback)callback();
                }
            }.bind(this));
        }else{
            this._loadMap();
            if (callback)callback();
        }
    },""" % {"ak": OLD_AK}

BM_LOADRES_NEW = """    /** %(mark)s: 原实现无条件拉取百度地图脚本(getscript?ak=%(ak)s)。
     *  该 AK 已失效 —— 服务端 verify 实测返回 {"error":201}，前端 SDK 命中错误表
     *  ta[201]="APP被您禁用啦。" → alert() 阻塞弹窗。
     *  现改为：不加载百度脚本、也不加载依赖 window.BMap 的 BDMarkerTool.js，
     *  直接走 _loadMap()（其内已加 BMap 守卫，缺 BMap 时渲染占位提示）。
     *  今后取得有效 AK，填入下面 apiPath 并去掉 if(false) 即可恢复地图。 */
    loadResource:function(callback){
        window.BMap_loadScriptTime = (new Date).getTime();
        var apiPath = "";   /* 填入有效百度地图 AK 即恢复地图功能 */
        if( false /* %(mark)s */ && !window.BDMapApiLoaded && apiPath ){
            COMMON.AjaxModule.loadDom(apiPath, function () {
                window.BDMapApiLoaded = true;
                if( !window.BDMarkerToolLoaded ){
                    COMMON.AjaxModule.load( "/x_component_CRM/BDMarkerTool.js", function(){
                        window.BDMarkerToolLoaded = true;
                        this._loadMap();
                        if (callback)callback();
                    }.bind(this) );
                }else{
                    this._loadMap();
                    if (callback)callback();
                }
            }.bind(this));
        }else{
            this._loadMap();
            if (callback)callback();
        }
    },""" % {"ak": OLD_AK, "mark": MARK}

BM_MAPGUARD_OLD = "        this.map = new BMap.Map(this.mapNode);"
BM_MAPGUARD_NEW = (
    "        /* %s guard: 无 BMap 时优雅降级，不抛错 */\n"
    "        if (typeof BMap === 'undefined' || !BMap || !BMap.Map) {\n"
    "            try { this.mapNode.innerHTML = '<div style=\"padding:16px;color:#888;font-size:13px;\">"
    "地图功能不可用（内置百度地图 AK 已失效），客户/联系人/线索等其它功能均正常。</div>'; } catch (e) {}\n"
    "            return;\n"
    "        }\n"
    "        this.map = new BMap.Map(this.mapNode);" % MARK
)

# ══════════════ ②b AddressExplorer.js 形态 ══════════════
# 该文件里 BMap.Map 是多赋值形态，且 createMap() 一进来就用 BMap.Point
BM_CREATEMAP_OLD = (
    "    createMap: function( position ){\n"
    "        var point = null;"
)
BM_CREATEMAP_NEW = (
    "    /* %(mark)s guard: 无 BMap 时优雅降级，不抛 ReferenceError */\n"
    "    createMap: function( position ){\n"
    "        if (typeof BMap === 'undefined' || !BMap || !BMap.Map) {\n"
    "            try { this.mapNode.innerHTML = '<div style=\"padding:16px;color:#888;font-size:13px;\">"
    "地图功能不可用（内置百度地图 AK 已失效），客户/联系人/线索等其它功能均正常。</div>'; } catch (e) {}\n"
    "            return;\n"
    "        }\n"
    "        var point = null;" % {"mark": MARK}
)

# ══════════════ ③ min 版 ══════════════
MIN_LOG = "/*%s min-patched*/\n" % MARK

# Main.min.js 里「进入应用即拉百度脚本」那段的原始形态
MAIN_MIN_ORIG = (
    'MWF.xDesktop.requireApp("CRM","BaiduMap",function(){window.BMap_loadScriptTime=(new Date).getTime();'
    'var t=layout.protocol+"//api.map.baidu.com/getscript?v=2.0&ak=%s&services=&t=20161219171637";'
    'window.BDMapApiLoaded||COMMON.AjaxModule.loadDom(t,(function(){window.BDMapApiLoaded=!0,'
    'window.BDMarkerToolLoaded||COMMON.AjaxModule.load("/x_component_CRM/BDMarkerTool.js",'
    '(function(){window.BDMarkerToolLoaded=!0}))}))}.bind(this)),t&&t()' % OLD_AK
)

# 替换：三元条件恒 false（0&&…），并把 t 置空 —— 整段成为死代码，不请求、不加载 BDMarkerTool
MAIN_MIN_PATCHED = (
    'MWF.xDesktop.requireApp("CRM","BaiduMap",function(){window.BMap_loadScriptTime=(new Date).getTime();'
    'var t="";/*%s: baidu ak 失效(error 201)，停用脚本加载*/'
    '0&&!window.BDMapApiLoaded&&COMMON.AjaxModule.loadDom(t,(function(){window.BDMapApiLoaded=!0,'
    'window.BDMarkerToolLoaded||COMMON.AjaxModule.load("/x_component_CRM/BDMarkerTool.js",'
    '(function(){window.BDMarkerToolLoaded=!0}))}))}.bind(this)),t&&t()' % MARK
)


def patch_main_min(s):
    """Main.min.js：把「进入应用即拉百度脚本」整段短路。

    原形：  …;var t=layout.protocol+"//api.map.baidu.com/getscript?ak=<AK>…";
            window.BDMapApiLoaded||COMMON.AjaxModule.loadDom(t,(function(){…load("BDMarkerTool.js")…}))
    ★ 只置空 URL 不够：`window.BDMapApiLoaded || loadDom("")` 仍执行 → 请求空 URL 拿到 HTML
      (SyntaxError: Unexpected token '<')，回调再加载 BDMarkerTool.js
      (ReferenceError: BMap is not defined)。必须让整个 || 分支不成立。
    """
    if MARK in s:
        return s, 0
    n = 0
    if MAIN_MIN_ORIG in s:
        s = s.replace(MAIN_MIN_ORIG, MAIN_MIN_PATCHED); n += 1
    else:
        # 退化写法：兼容用户目录文件里空格/引号略有差异的情形（窄锚点替换）
        import re as _re
        s2, c = _re.subn(
            r'window\.BDMapApiLoaded\|\|COMMON\.AjaxModule\.loadDom\(',
            '0/*%s*/&&!window.BDMapApiLoaded&&COMMON.AjaxModule.loadDom(' % MARK,
            s)
        if c:
            s, n = s2, n + c
        for p in ('"//api.map.baidu.com/getscript?v=2.0&ak=%s&services=&t=20161219171637"' % OLD_AK,
                  '"http://api.map.baidu.com/getscript?v=2.0&ak=%s&services=&t=20161219171637"' % OLD_AK):
            if p in s:
                s = s.replace(p, '""'); n += 1
    return s, n


def patch_main(s):
    if MARK in s:
        return s, 0
    n = 0
    if MAIN_APIPATH_OLD in s:
        s = s.replace(MAIN_APIPATH_OLD, MAIN_APIPATH_NEW); n += 1
    if MAIN_GUARD_OLD in s:
        s = s.replace(MAIN_GUARD_OLD, MAIN_GUARD_NEW); n += 1
    return s, n


def patch_bmap(s):
    """BaiduMap.js / AddressExplorer.js（同构）：apiPath 置空 + 短路 loadDom + BMap 守卫。

    两文件结构一致，只有 `loadResource:function(` 与 `loadResource: function (` 的
    空格差异，故用正则匹配以兼容。
    """
    if MARK in s:
        return s, 0
    import re as _re
    n = 0
    # ① apiPath（含缩进，兼容行尾分号）
    s, c = _re.subn(
        r'(?m)^([ \t]*)var apiPath = "http?://api\.map\.baidu\.com/getscript\?v=2\.0&ak='
        + _re.escape(OLD_AK) + r'&services=&t=20161219171637";',
        lambda m: '%svar apiPath = "";  /* %s: 原 AK 已失效(error 201)，不再加载百度脚本 */'
                  % (m.group(1), MARK),
        s)
    n += c
    # ② 短路所有「是否需加载百度脚本」的守卫（兼容 `if(` / `if (` 与有无内层空格）
    s, c = _re.subn(
        r'(?m)^([ \t]*)if\s*\(\s*!window\.BDMapApiLoaded\s*\)\s*\{',
        lambda m: '%sif (false /* %s: 停用百度地图脚本加载 */ && !window.BDMapApiLoaded) {'
                  % (m.group(1), MARK),
        s)
    n += c
    # ③ BMap 使用处加守卫（BaiduMap.js 形态）
    g = s.count(BM_MAPGUARD_OLD)
    s = s.replace(BM_MAPGUARD_OLD, BM_MAPGUARD_NEW)
    n += g
    # ③b AddressExplorer.js 形态：createMap() 入口守卫
    #    （该文件 BMap.Map 是多赋值写法 `var map = this.map = new BMap.Map(...)`，
    #      且 createMap 一进来就 new BMap.Point —— 必须在方法入口整体拦截）
    c = s.count(BM_CREATEMAP_OLD)
    if c:
        s = s.replace(BM_CREATEMAP_OLD, BM_CREATEMAP_NEW)
        n += c
    return s, n


MIN_LOADDOM_TMPL = (
    ':COMMON.AjaxModule.loadDom("",function(){window.BDMapApiLoaded=!0,'
    'window.BDMarkerToolLoaded?(this._loadMap(),t&&t()):'
    'COMMON.AjaxModule.load("/x_component_CRM/BDMarkerTool.js",function(){'
    'window.BDMarkerToolLoaded=!0,this._loadMap(),t&&t()}.bind(this))}.bind(this))'
)


def patch_min(s):
    """min 版：把「三元里拉百度脚本 / loadDom 空 URL」整支换成直接 _loadMap()。

    min 版原形：
      window.BDMapApiLoaded?(this._loadMap(),t&&t())
        :COMMON.AjaxModule.loadDom("<url>",function(){…load("BDMarkerTool.js")…}.bind(this))

    ★ 只把 URL 换成 "" 不够 —— loadDom("") 会请求空 URL 拿到 HTML（SyntaxError:
      Unexpected token '<'），其回调仍加载 BDMarkerTool.js（ReferenceError: BMap 未定义）。
      必须把 loadDom 整段删掉，三元改为直接 _loadMap。
    """
    if MARK in s:
        return s, 0
    n = 0
    # ① 原始 AK 的 URL
    p1 = (':COMMON.AjaxModule.loadDom("http://api.map.baidu.com/getscript?v=2.0&ak=%s'
          '&services=&t=20161219171637",function(){window.BDMapApiLoaded=!0,'
          'window.BDMarkerToolLoaded?(this._loadMap(),t&&t()):'
          'COMMON.AjaxModule.load("/x_component_CRM/BDMarkerTool.js",function(){'
          'window.BDMarkerToolLoaded=!0,this._loadMap(),t&&t()}.bind(this))}.bind(this))' % OLD_AK)
    if p1 in s:
        s = s.replace(p1, ':(this._loadMap(),t&&t())'); n += 1
    # ② 已被置空的 URL 形态
    if MIN_LOADDOM_TMPL in s:
        s = s.replace(MIN_LOADDOM_TMPL, ':(this._loadMap(),t&&t())'); n += 1
    if n == 0:
        # ③ 退化：只置空 URL（不完美，但至少不请求外网）
        for p in ('"http://api.map.baidu.com/getscript?v=2.0&ak=%s&services=&t=20161219171637"' % OLD_AK,
                  '"//api.map.baidu.com/getscript?v=2.0&ak=%s&services=&t=20161219171637"' % OLD_AK):
            if p in s:
                s = s.replace(p, '""')
                n += 1
    return MIN_LOG + s, n


def patch_main_min_min(s):
    """Main.min.min.js：与 Main.min.js 同构（部分打包器输出 .min.min.js）。

    ★ 该文件同样含「进入应用即拉百度脚本」整段 → 不修则打开 CRM 仍弹窗。
    """
    return patch_main_min(s)


# 8 个文件全部覆盖（chk_crm_files.py 实测命中清单）
TARGETS = {
    "Main.js": "main",
    "Main.min.js": "mainmin",
    "Main.min.min.js": "mainmin",
    "BaiduMap.js": "bmap",
    "BaiduMap.min.js": "min",
    "BaiduMap.min.min.js": "min",
    "AddressExplorer.js": "bmap",
    "AddressExplorer.min.js": "min",
}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "."
    rep = []
    for name, kind in TARGETS.items():
        p = os.path.join(src, name)
        if not os.path.exists(p):
            rep.append("%-22s SKIP (not found)" % name)
            continue
        with io.open(p, encoding="utf-8") as f:
            s = f.read()
        fn = {"main": patch_main, "mainmin": patch_main_min,
              "bmap": patch_bmap, "min": patch_min}[kind]
        s2, n = fn(s)
        if s2 != s:
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write(s2)
            rep.append("%-22s PATCHED (hits=%d)" % (name, n))
        else:
            rep.append("%-22s nochange" % name)
    print("\n".join(rep))


if __name__ == "__main__":
    main()
