/**
 * x_component_SysSetting —— 系统设置
 *
 * 定位：把「这几天研究出来的、影响系统运行与使用的配置项」集中到一个后台界面里。
 * 现有分组：
 *   ① 系统邮箱      —— SMTP 服务器/发件人/授权码/SSL/启用开关/测试邮件/邮件模板
 *   ② 登录与安全    —— 图形验证码、登录短信验证码（写入 O2OA config/person.json）
 *   ③ 验证码服务    —— 自研 x_sms_assemble_control 平替的运行状态 / 待投递验证码 / 测试发码
 *   ④ 运行环境      —— 离线状态概览
 *
 * 数据来源（全部真实后端，无占位数据）：
 *   · 邮件与验证码服务 -> http://<host>:8095/api/*   （mailservice/o2oa_mail_service.py）
 *   · 登录开关         -> /x_program_center/jaxrs/config/person
 *
 * 目录约定（O2OA 组件规范）：
 *   x_component_SysSetting/
 *     Main.js                 组件主类（本文件）
 *     syssetting/syssetting.js  UI 与数据访问实现
 *     syssetting/syssetting.css 样式
 *     lp/zh-cn.js             语言包
 *     $Main/default/          图标资源
 */
MWF.xApplication.SysSetting = MWF.xApplication.SysSetting || {};
MWF.xApplication.SysSetting.LP = MWF.xApplication.SysSetting.LP || { "title": "系统设置" };

(function () {
    var ROOT = "../x_component_SysSetting";
    var VERSION = "20260923b";   // 变更后务必递增：前端按 ?v= 破缓存

    function loadCss(href, cb) {
        var l = document.createElement("link");
        l.rel = "stylesheet";
        l.type = "text/css";
        l.href = href;
        if (cb) { l.onload = cb; l.onerror = cb; }
        document.getElementsByTagName("head")[0].appendChild(l);
    }

    function loadJs(src, cb) {
        var s = document.createElement("script");
        s.type = "text/javascript";
        s.src = src;
        if (cb) { s.onload = cb; s.onerror = cb; }
        document.getElementsByTagName("head")[0].appendChild(s);
    }

    function dom(el) {
        if (!el) return el;
        // MooTools Element 与原生 DOM 兼容；此处兜底取出原生元素
        if (el.toElement) { try { return el.toElement(); } catch (e) { } }
        return el;
    }

    MWF.xApplication.SysSetting.Main = new Class({
        Extends: MWF.xApplication.Common.Main,
        Implements: [Options, Events],

        options: {
            "style": "default",
            "name": "SysSetting",
            "icon": "icon.png",
            "width": "1080",
            "height": "720",
            "isResize": true,
            "isMax": true,
            "title": "系统设置"
        },

        onQueryLoad: function () {
            this.lp = MWF.xApplication.SysSetting.LP;
        },

        loadApplication: function (callback) {
            this.mountViewer();
            if (callback) callback();
        },

        mountViewer: function () {
            var self = this;
            var host = dom(this.content);
            if (!host) return;
            try { host.style.overflow = "hidden"; } catch (e) { }

            var boot = function () {
                if (!MWF.xApplication.SysSetting.Viewer) {
                    var tip = document.createElement("div");
                    tip.style.cssText = "padding:30px;font:14px/1.8 sans-serif;color:#888";
                    tip.innerHTML = "系统设置前端资源未能加载，请检查 x_component_SysSetting/syssetting/syssetting.js。";
                    host.appendChild(tip);
                    return;
                }
                try {
                    self.viewer = new MWF.xApplication.SysSetting.Viewer({
                        "container": host,
                        "app": self
                    });
                } catch (e) {
                    var t2 = document.createElement("div");
                    t2.style.cssText = "padding:30px;font:14px/1.8 sans-serif;color:#c00";
                    t2.innerHTML = "系统设置初始化失败：" + (e && e.message ? e.message : e);
                    host.appendChild(t2);
                }
            };

            loadCss(ROOT + "/syssetting/syssetting.css?v=" + VERSION);
            if (MWF.xApplication.SysSetting.Viewer) { boot(); } else {
                loadJs(ROOT + "/syssetting/syssetting.js?v=" + VERSION, boot);
            }
        }
    });
})();
