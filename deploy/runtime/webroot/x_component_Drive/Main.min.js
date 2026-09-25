/**
 * x_component_Drive —— 企业网盘（Drive）
 *
 * 构建方式：UI 层自研复刻，数据层复用 O2OA 内置的 x_file_assemble_control 服务
 *          （个人文件 / 组织共享 / 回收站 / 容量 / Office 预览，共 30+ REST 接口）。
 * 设计目标：与官方应用市场「企业网盘 V2.x」一致的「个人文件 / 企业文件 / 后台管理」信息架构，
 *          且所有列表渲染真实后端数据，不使用任何占位或假数据。
 *
 * 目录约定（O2OA 组件规范）：
 *   x_component_Drive/
 *     Main.js                 组件主类（本文件）
 *     drive/drive.js          UI 与数据访问实现
 *     drive/drive.css         样式
 *     lp/zh-cn.js             语言包
 *     $Main/default/          图标资源（复用 x_component_File 的文件类型图标）
 */
MWF.xApplication.Drive = MWF.xApplication.Drive || {};
MWF.xApplication.Drive.LP = MWF.xApplication.Drive.LP || { "title": "企业网盘" };

(function () {
    var ROOT = "../x_component_Drive";
    var VERSION = "20260923h";

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

    MWF.xApplication.Drive.Main = new Class({
        Extends: MWF.xApplication.Common.Main,
        Implements: [Options, Events],

        options: {
            "style": "default",
            "name": "Drive",
            "icon": "icon.png",
            "width": "1100",
            "height": "700",
            "isResize": true,
            "isMax": true,
            "title": "企业网盘"
        },

        onQueryLoad: function () {
            this.lp = MWF.xApplication.Drive.LP;
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
                if (!MWF.xApplication.Drive.Viewer) {
                    var tip = document.createElement("div");
                    tip.style.cssText = "padding:30px;font:14px/1.8 sans-serif;color:#888";
                    tip.innerHTML = "企业网盘前端资源未能加载，请检查 x_component_Drive/drive/drive.js。";
                    host.appendChild(tip);
                    return;
                }
                try {
                    self.viewer = new MWF.xApplication.Drive.Viewer({
                        "container": host,
                        "app": self
                    });
                } catch (e) {
                    var t2 = document.createElement("div");
                    t2.style.cssText = "padding:30px;font:14px/1.8 sans-serif;color:#c00";
                    t2.innerHTML = "企业网盘初始化失败：" + (e && e.message ? e.message : e);
                    host.appendChild(t2);
                }
            };

            loadCss(ROOT + "/drive/drive.css?v=" + VERSION);
            if (MWF.xApplication.Drive.Viewer) { boot(); } else {
                loadJs(ROOT + "/drive/drive.js?v=" + VERSION, boot);
            }
        }
    });
})();
