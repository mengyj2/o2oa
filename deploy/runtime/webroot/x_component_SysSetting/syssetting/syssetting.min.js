/**
 * x_component_SysSetting / syssetting.js —— UI 与数据访问实现
 *
 * 全部数据均来自真实后端：
 *   · 邮件 + 验证码服务：http://<当前主机>:8095/api/*  （mailservice/o2oa_mail_service.py）
 *   · 登录安全开关：/x_program_center/jaxrs/config/person（整对象回写）
 */
MWF.xApplication.SysSetting = MWF.xApplication.SysSetting || {};

(function () {
    function val(id) {
        var e = document.getElementById(id);
        return e ? String(e.value == null ? "" : e.value).trim() : "";
    }

    // ★★ 必须用「普通构造函数 + prototype」，**不能**用 MooTools `new Class({...})`。
    //    原因（实测踩坑）：MooTools 的 Class 一旦 Implements:[Options]，构造函数里的
    //    setOptions(opt) 会走 Object.merge 做【深合并】，而 opt.app 是 Main 实例
    //    （挂着 DOM 节点 / 双向引用）⇒ 无限递归 ⇒ "Maximum call stack size exceeded"，
    //    窗口里只剩一行报错文字。x_component_Drive 的 Viewer 同样是普通构造函数。
    function Viewer(opt) {
        this.container = opt.container;
        this.app = opt.app;
        this.lp = MWF.xApplication.SysSetting.LP || {};

        this._tk = "";
        this.mailCfg = null;      // GET /api/config 的 config
        this.svc = null;          // GET /api/status
        this.personRaw = null;    // config/person.json 全量（整对象回写用）
        this.codes = [];
        this.tab = "email";

        // 服务地址：跟随当前访问主机，避免写死 localhost
        var h = location.hostname || "localhost";
        this.mailBase = location.protocol + "//" + h + ":8095/api";

        this.build();
        this.refresh();
    }

    Viewer.prototype = {

        // ================= 基础工具 =================
        esc: function (s) {
            return String(s == null ? "" : s)
                .replace(/&/g, "&amp;").replace(/</g, "&lt;")
                .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        },

        token: function () {
            if (this._tk) return this._tk;
            var m = document.cookie.match(/(?:^|;\s*)x-token=([^;]+)/);
            this._tk = m ? decodeURIComponent(m[1]) : "";
            return this._tk;
        },

        xhr: function (method, url, body, cb) {
            var tk = this.token();
            var x = new XMLHttpRequest();
            x.open(method, url, true);
            x.timeout = 25000;
            if (tk) { try { x.setRequestHeader("x-token", tk); } catch (e) { } }
            if (body !== null && body !== undefined) {
                x.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
            }
            x.onreadystatechange = function () {
                if (x.readyState !== 4) return;
                var d = null;
                try { d = JSON.parse(x.responseText); } catch (e) { d = x.responseText; }
                cb(x.status, d, x);
            };
            x.onerror = function () { cb(-1, null, x); };
            x.ontimeout = function () { cb(-2, null, x); };
            try { x.send(body === null || body === undefined ? null : JSON.stringify(body)); }
            catch (e) { cb(-3, null, x); }
        },

        q: function (sel, root) { return (root || this.container).querySelector(sel); },
        qa: function (sel, root) { return Array.prototype.slice.call((root || this.container).querySelectorAll(sel)); },

        toast: function (msg, kind) {
            var t = this.q("#ssToast");
            if (!t) return;
            t.className = "ss-toast show" + (kind ? " " + kind : "");
            t.innerHTML = this.esc(msg);
            if (this._toastT) clearTimeout(this._toastT);
            this._toastT = setTimeout(function () { t.className = "ss-toast"; }, 3200);
        },

        fmtLeft: function (sec) {
            sec = parseInt(sec, 10) || 0;
            var m = Math.floor(sec / 60), s = sec % 60;
            return m + ":" + (s < 10 ? "0" + s : s);
        },

        // ================= 构建 =================
        build: function () {
            var html = ''
                + '<div class="ss-wrap">'
                + '  <div class="ss-side">'
                + '    <div class="ss-brand"><span class="ss-brand-ico">&#9881;</span><span>系统设置</span></div>'
                + '    <div class="ss-nav">'
                + '      <div class="ss-nav-item active" data-tab="email">' + this.esc(this.lp.navEmail) + '</div>'
                + '      <div class="ss-nav-item" data-tab="login">' + this.esc(this.lp.navLogin) + '</div>'
                + '      <div class="ss-nav-item" data-tab="sms">' + this.esc(this.lp.navSms) + '</div>'
                + '      <div class="ss-nav-item" data-tab="about">' + this.esc(this.lp.navAbout) + '</div>'
                + '    </div>'
                + '    <div class="ss-side-foot"><span class="ss-dot" id="ssSideDot"></span><span id="ssSideText">检测中…</span></div>'
                + '  </div>'
                + '  <div class="ss-body">'
                + '    <div class="ss-scroll">'
                + '      <div class="ss-pane" data-pane="email">' + this.tplEmail() + '</div>'
                + '      <div class="ss-pane" data-pane="login" style="display:none">' + this.tplLogin() + '</div>'
                + '      <div class="ss-pane" data-pane="sms" style="display:none">' + this.tplSms() + '</div>'
                + '      <div class="ss-pane" data-pane="about" style="display:none">' + this.tplAbout() + '</div>'
                + '    </div>'
                + '  </div>'
                + '</div>'
                + '<div class="ss-toast" id="ssToast"></div>';

            this.container.innerHTML = html;
            this.bind();
        },

        tplHead: function (title, desc) {
            return '<div class="ss-head"><div class="ss-head-t">' + this.esc(title) + '</div>'
                + '<div class="ss-head-d">' + this.esc(desc) + '</div></div>';
        },

        row: function (label, fieldHtml, hint) {
            return '<div class="ss-row"><div class="ss-label">' + label + '</div>'
                + '<div class="ss-field"><div class="ss-field-line">' + fieldHtml + '</div>'
                + (hint ? '<div class="ss-hint">' + hint + '</div>' : '')
                + '</div></div>';
        },

        swRow: function (label, id, hint) {
            return '<div class="ss-row"><div class="ss-label">' + label + '</div>'
                + '<div class="ss-field"><div class="ss-field-line">'
                + '<div class="ss-switch" id="' + id + '"><i></i></div></div>'
                + (hint ? '<div class="ss-hint">' + hint + '</div>' : '')
                + '</div></div>';
        },

        // ---------- 面板①：系统邮箱 ----------
        tplEmail: function () {
            var L = this.lp;
            return ''
                + this.tplHead(L.emailTitle, L.emailDesc)
                + '<div class="ss-card">'
                + this.swRow(L.enableMail, "ssEnableMail", L.enableMailHint)
                + this.row(L.smtpHost,
                    '<input class="ss-inp ss-inp-lg" id="ssSmtpHost" placeholder="' + this.esc(L.smtpHostPh) + '">'
                    + '<span class="ss-sep"></span><span class="ss-mini">' + this.esc(L.smtpPort) + '</span>'
                    + '<input class="ss-inp ss-inp-xs" id="ssSmtpPort">')
                + this.swRow(L.ssl, "ssSsl", L.sslHint)
                + this.row(L.senderMail, '<input class="ss-inp ss-inp-lg" id="ssSenderMail" placeholder="' + this.esc(L.senderMailPh) + '">')
                + this.row(L.senderName, '<input class="ss-inp ss-inp-lg" id="ssSenderName" placeholder="' + this.esc(L.senderNamePh) + '">')
                + this.row(L.smtpUser, '<input class="ss-inp ss-inp-lg" id="ssSmtpUser">', this.esc(L.smtpUserHint))
                + this.row(L.smtpPassword,
                    '<input class="ss-inp ss-inp-lg" type="password" id="ssSmtpPassword" placeholder="' + this.esc(L.smtpPasswordPh) + '">'
                    + '<button class="ss-btn ss-btn-ghost ss-btn-inline" id="ssPwToggle" type="button">显示</button>',
                    this.esc(L.smtpPasswordKeep))
                + this.row(L.redirectTo, '<input class="ss-inp ss-inp-lg" id="ssRedirectTo">', this.esc(L.redirectToHint))
                + '</div>'

                + '<div class="ss-card ss-card-sub">'
                + '<div class="ss-sub-t">' + this.esc(L.testMail) + '</div>'
                + this.row(L.testTo, '<input class="ss-inp ss-inp-lg" id="ssTestTo" placeholder="' + this.esc(L.testToPh) + '">')
                + '<div class="ss-actions"><button class="ss-btn" id="ssTestMailBtn" type="button">' + this.esc(L.testMail) + '</button></div>'
                + '</div>'

                + '<div class="ss-actions ss-actions-main">'
                + '<button class="ss-btn ss-btn-primary" id="ssSaveMailBtn" type="button">' + this.esc(L.save) + '</button>'
                + '<button class="ss-btn" id="ssReloadMailBtn" type="button">' + this.esc(L.reset) + '</button>'
                + '</div>'

                + '<div class="ss-fold" id="ssTplFold">'
                + '<div class="ss-fold-head" data-fold="ssTplFold"><span class="ss-caret">&#9656;</span>' + this.esc(L.tplPanel) + '</div>'
                + '<div class="ss-fold-body" style="display:none">'
                + '<div class="ss-hint ss-hint-block">' + this.esc(L.tplHint) + '</div>'
                + this.tplItem("code", L.tplCode)
                + this.tplItem("reset", L.tplReset)
                + this.tplItem("invite", L.tplInvite)
                + '</div></div>';
        },

        tplItem: function (key, title) {
            var L = this.lp;
            return '<div class="ss-subfold">'
                + '<div class="ss-subfold-head" data-sub="' + key + '"><span class="ss-caret">&#9656;</span>' + this.esc(title) + '</div>'
                + '<div class="ss-subfold-body" style="display:none">'
                + '<div class="ss-subrow"><div class="ss-sublabel">' + this.esc(L.tplSubject) + '</div>'
                + '<input class="ss-inp ss-inp-full" id="ssTplSubj_' + key + '"></div>'
                + '<div class="ss-subrow"><div class="ss-sublabel">' + this.esc(L.tplBody) + '</div>'
                + '<textarea class="ss-ta" id="ssTplBody_' + key + '" rows="8"></textarea></div>'
                + '<div class="ss-actions"><button class="ss-btn ss-btn-ghost" data-tplreset="' + key + '" type="button">' + this.esc(L.tplRestore) + '</button></div>'
                + '</div></div>';
        },

        // ---------- 面板②：登录与安全 ----------
        tplLogin: function () {
            var L = this.lp;
            return ''
                + this.tplHead(L.loginTitle, L.loginDesc)
                + '<div class="ss-card">'
                + this.swRow(L.captchaLogin, "ssCaptchaLogin", L.captchaLoginHint)
                + this.swRow(L.codeLogin, "ssCodeLogin", L.codeLoginHint)
                + this.row(L.codeLoginChannel, '<span class="ss-tag ss-tag-ok" id="ssChannelTag">' + this.esc(L.channelLocal) + '</span>')
                + '</div>'
                + '<div class="ss-actions ss-actions-main">'
                + '<button class="ss-btn ss-btn-primary" id="ssSaveLoginBtn" type="button">' + this.esc(L.save) + '</button>'
                + '<button class="ss-btn" id="ssReloadLoginBtn" type="button">' + this.esc(L.reset) + '</button>'
                + '</div>';
        },

        // ---------- 面板③：验证码服务 ----------
        tplSms: function () {
            var L = this.lp;
            return ''
                + this.tplHead(L.smsTitle, L.smsDesc)
                + '<div class="ss-card" id="ssSvcCard">'
                + '<div class="ss-kv"><div class="ss-k">' + this.esc(L.svcStatus) + '</div><div class="ss-v" id="ssSvcStatus">—</div></div>'
                + '<div class="ss-kv"><div class="ss-k">' + this.esc(L.svcRegistered) + '</div><div class="ss-v" id="ssSvcReg">—</div></div>'
                + '<div class="ss-kv"><div class="ss-k">' + this.esc(L.svcNode) + '</div><div class="ss-v" id="ssSvcNode">—</div></div>'
                + '<div class="ss-kv"><div class="ss-k">' + this.esc(L.svcPort) + '</div><div class="ss-v" id="ssSvcPort">—</div></div>'
                + '</div>'
                + '<div class="ss-card ss-card-sub">'
                + '<div class="ss-sub-t">' + this.esc(L.pendingTitle) + '</div>'
                + '<div id="ssCodesBox"><div class="ss-empty">' + this.esc(L.loading) + '</div></div>'
                + '</div>'
                + '<div class="ss-card ss-card-sub">'
                + '<div class="ss-sub-t">' + this.esc(L.sendTestCode) + '</div>'
                + this.row("", '<input class="ss-inp ss-inp-lg" id="ssTestMobile" placeholder="' + this.esc(L.sendTestCodePh) + '">'
                    + '<button class="ss-btn" id="ssSendCodeBtn" type="button">' + this.esc(L.sendTestCode) + '</button>')
                + '</div>'
                + '<div class="ss-actions ss-actions-main">'
                + '<button class="ss-btn" id="ssRefreshSvcBtn" type="button">' + this.esc(L.refresh) + '</button>'
                + '</div>';
        },

        // ---------- 面板④：运行环境 ----------
        tplAbout: function () {
            var L = this.lp;
            return ''
                + this.tplHead(L.aboutTitle, L.aboutDesc)
                + '<div class="ss-card">'
                + '<div class="ss-kv"><div class="ss-k">运行模式</div><div class="ss-v"><span class="ss-tag ss-tag-ok">' + this.esc(L.localOnly) + '</span></div></div>'
                + '<div class="ss-kv"><div class="ss-k">邮件/验证码服务</div><div class="ss-v">' + this.esc(this.mailBase) + '</div></div>'
                + '<div class="ss-kv"><div class="ss-k">服务端脚本</div><div class="ss-v">mailservice/o2oa_mail_service.py</div></div>'
                + '<div class="ss-kv"><div class="ss-k">配置落盘</div><div class="ss-v">mailservice/mail.json · mailservice/codes.json</div></div>'
                + '<div class="ss-kv"><div class="ss-k">本地 LLM 网关</div><div class="ss-v">127.0.0.1:18790</div></div>'
                + '<div class="ss-kv"><div class="ss-k">O2OA</div><div class="ss-v">10.0.2 · Docker 自托管 · 已断云</div></div>'
                + '</div>';
        },

        // ================= 绑定 =================
        bind: function () {
            var self = this;

            this.qa(".ss-nav-item").forEach(function (it) {
                it.onclick = function () { self.switchTab(it.getAttribute("data-tab")); };
            });

            // 开关
            this.qa(".ss-switch").forEach(function (s) {
                s.onclick = function () {
                    if (s.className.indexOf("off") >= 0) return;
                    s.className = ("ss-switch" + (s.className.indexOf("on") >= 0 ? "" : " on"));
                };
            });

            // 折叠面板
            this.qa("[data-fold]").forEach(function (h) {
                h.onclick = function () {
                    var box = document.getElementById(h.getAttribute("data-fold"));
                    var body = box ? box.querySelector(".ss-fold-body") : null;
                    var caret = h.querySelector(".ss-caret");
                    if (!body) return;
                    var open = body.style.display !== "none";
                    body.style.display = open ? "none" : "block";
                    if (caret) caret.innerHTML = open ? "&#9656;" : "&#9662;";
                };
            });
            this.qa("[data-sub]").forEach(function (h) {
                h.onclick = function () {
                    var body = h.parentNode.querySelector(".ss-subfold-body");
                    var caret = h.querySelector(".ss-caret");
                    if (!body) return;
                    var open = body.style.display !== "none";
                    body.style.display = open ? "none" : "block";
                    if (caret) caret.innerHTML = open ? "&#9656;" : "&#9662;";
                };
            });

            // 密码显隐
            var pt = this.q("#ssPwToggle");
            if (pt) pt.onclick = function () {
                var p = self.q("#ssSmtpPassword");
                if (!p) return;
                var showing = p.type === "text";
                p.type = showing ? "password" : "text";
                pt.innerHTML = showing ? "显示" : "隐藏";
            };

            var sm = this.q("#ssSaveMailBtn"); if (sm) sm.onclick = function () { self.saveMail(); };
            var rm = this.q("#ssReloadMailBtn"); if (rm) rm.onclick = function () { self.loadMail(true); };
            var tm = this.q("#ssTestMailBtn"); if (tm) tm.onclick = function () { self.testMail(); };
            var sl = this.q("#ssSaveLoginBtn"); if (sl) sl.onclick = function () { self.saveLogin(); };
            var rl = this.q("#ssReloadLoginBtn"); if (rl) rl.onclick = function () { self.loadLogin(true); };
            var rf = this.q("#ssRefreshSvcBtn"); if (rf) rf.onclick = function () { self.loadSvc(); self.loadCodes(); };
            var sc = this.q("#ssSendCodeBtn"); if (sc) sc.onclick = function () { self.sendTestCode(); };

            this.qa("[data-tplreset]").forEach(function (b) {
                b.onclick = function () { self.restoreTpl(b.getAttribute("data-tplreset")); };
            });
        },

        switchTab: function (key) {
            this.tab = key;
            var self = this;
            this.qa(".ss-nav-item").forEach(function (it) {
                it.className = "ss-nav-item" + (it.getAttribute("data-tab") === key ? " active" : "");
            });
            this.qa(".ss-pane").forEach(function (p) {
                p.style.display = (p.getAttribute("data-pane") === key) ? "" : "none";
            });
            if (key === "sms") { this.loadSvc(); this.loadCodes(); }
        },

        setSwitch: function (id, on) {
            var e = document.getElementById(id);
            if (!e) return;
            e.className = "ss-switch" + (on ? " on" : "");
        },
        getSwitch: function (id) {
            var e = document.getElementById(id);
            return !!(e && e.className.indexOf("on") >= 0);
        },

        // ================= 数据 =================
        refresh: function () {
            this.loadSvc();
            this.loadMail();
            this.loadLogin();
            this.loadCodes();
        },

        setSide: function (ok, text) {
            var d = this.q("#ssSideDot"), t = this.q("#ssSideText");
            if (d) d.className = "ss-dot" + (ok ? " ok" : " bad");
            if (t) t.innerHTML = this.esc(text);
        },

        // ----- 邮件配置 -----
        loadMail: function (notify) {
            var self = this;
            this.xhr("GET", this.mailBase + "/config", null, function (st, d) {
                if (st !== 200 || !d || !d.config) {
                    self.setSide(false, "邮件服务未运行");
                    if (notify) self.toast(self.lp.loadFailed + " (" + st + ")", "err");
                    return;
                }
                self.mailCfg = d.config;
                self.fillMail(d.config);
                self.setSide(true, "服务运行中");
                if (notify) self.toast(self.lp.loading === "加载中…" ? "已重新载入" : "已重新载入", "ok");
            });
        },

        fillMail: function (c) {
            var set = function (id, v) { var e = document.getElementById(id); if (e) e.value = (v == null ? "" : v); };
            this.setSwitch("ssEnableMail", !!c.enabled);
            this.setSwitch("ssSsl", !!c.ssl);
            set("ssSmtpHost", c.smtpHost);
            set("ssSmtpPort", c.smtpPort);
            set("ssSenderMail", c.senderMail);
            set("ssSenderName", c.senderName);
            set("ssSmtpUser", c.smtpUser);
            set("ssRedirectTo", c.redirectTo);
            var pw = document.getElementById("ssSmtpPassword");
            if (pw) pw.value = c.smtpPassword || "";

            var t = c.templates || {};
            ["code", "reset", "invite"].forEach(function (k) {
                var o = t[k] || {};
                var s = document.getElementById("ssTplSubj_" + k);
                var b = document.getElementById("ssTplBody_" + k);
                if (s) s.value = o.subject || "";
                if (b) b.value = o.body || "";
            });
        },

        collectMail: function () {
            var out = {
                enabled: this.getSwitch("ssEnableMail"),
                ssl: this.getSwitch("ssSsl"),
                smtpHost: val("ssSmtpHost"),
                smtpPort: parseInt(val("ssSmtpPort"), 10) || 465,
                senderMail: val("ssSenderMail"),
                senderName: val("ssSenderName"),
                smtpUser: val("ssSmtpUser"),
                redirectTo: val("ssRedirectTo"),
                templates: {}
            };
            var pw = val("ssSmtpPassword");
            if (pw && pw !== "******") out.smtpPassword = pw;
            ["code", "reset", "invite"].forEach(function (k) {
                out.templates[k] = {
                    subject: val("ssTplSubj_" + k),
                    body: val("ssTplBody_" + k)
                };
            });
            return out;
        },

        saveMail: function () {
            var self = this, L = this.lp;
            this.xhr("PUT", this.mailBase + "/config", this.collectMail(), function (st, d) {
                if (st === 200 && d && d.ok) {
                    self.toast(L.saved, "ok");
                    if (d.config) { self.mailCfg = d.config; self.fillMail(d.config); }
                } else {
                    self.toast(L.saveFailed + " (" + st + ")", "err");
                }
            });
        },

        testMail: function () {
            var self = this, L = this.lp;
            this.toast(L.testing);
            this.xhr("POST", this.mailBase + "/test/mail", { to: val("ssTestTo") }, function (st, d) {
                if (d && d.ok) self.toast(L.testOk, "ok");
                else self.toast(L.testFail + "：" + ((d && d.message) || st), "err");
            });
        },

        restoreTpl: function (key) {
            var DEF = {
                code: {
                    subject: "【中国复合材料工业协会】登录验证码",
                    body: "{name}，您好：\n\n您正在登录「{app}」，验证码为：\n\n    {code}\n\n验证码 {ttl} 分钟内有效，请勿泄露给他人。\n\n如非本人操作，请忽略本邮件。"
                },
                reset: {
                    subject: "【中国复合材料工业协会】密码重置验证码",
                    body: "{name}，您好：\n\n您正在重置「{app}」的登录密码，验证码为：\n\n    {code}\n\n验证码 {ttl} 分钟内有效。如非本人操作，请立即联系系统管理员。"
                },
                invite: {
                    subject: "【中国复合材料工业协会】账号开通通知",
                    body: "{name}，您好：\n\n您的「{app}」账号已开通，登录账号为 {mobile}。\n首次登录请按提示修改密码。"
                }
            };
            var d = DEF[key];
            if (!d) return;
            var s = document.getElementById("ssTplSubj_" + key);
            var b = document.getElementById("ssTplBody_" + key);
            if (s) s.value = d.subject;
            if (b) b.value = d.body;
            this.toast("已恢复默认模板（需保存后生效）");
        },

        // ----- 登录与安全 -----
        loadLogin: function (notify) {
            var self = this;
            this.xhr("GET", "/x_program_center/jaxrs/config/person", null, function (st, d) {
                if (st !== 200 || !d || !d.data) {
                    if (notify) self.toast(self.lp.noPerm + " (" + st + ")", "err");
                    return;
                }
                self.personRaw = d.data;
                self.setSwitch("ssCaptchaLogin", !!d.data.captchaLogin);
                self.setSwitch("ssCodeLogin", !!d.data.codeLogin);
                if (notify) self.toast("已重新载入", "ok");
            });
        },

        saveLogin: function () {
            var self = this, L = this.lp;
            var obj = JSON.parse(JSON.stringify(this.personRaw || {}));
            obj.captchaLogin = this.getSwitch("ssCaptchaLogin");
            obj.codeLogin = this.getSwitch("ssCodeLogin");
            this.xhr("PUT", "/x_program_center/jaxrs/config/person", obj, function (st, d) {
                if (st === 200) {
                    self.toast(L.saved, "ok");
                    if (d && d.data) { self.personRaw = d.data; }
                } else {
                    self.toast(L.saveFailed + " (" + st + ")" + (st === 403 ? " — " + L.noPerm : ""), "err");
                }
            });
        },

        // ----- 验证码服务 -----
        loadSvc: function () {
            var self = this, L = this.lp;
            this.xhr("GET", this.mailBase + "/status", null, function (st, d) {
                var box = self.q("#ssSvcStatus"), reg = self.q("#ssSvcReg"),
                    node = self.q("#ssSvcNode"), port = self.q("#ssSvcPort");
                if (st !== 200 || !d || !d.ok) {
                    self.setSide(false, "验证码服务未运行");
                    if (box) box.innerHTML = '<span class="ss-tag ss-tag-bad">' + self.esc(L.svcDown) + '</span>';
                    if (reg) reg.innerHTML = "—";
                    self.svc = null;
                    var c = self.q("#ssSvcCard");
                    if (c && !c.querySelector(".ss-start-hint")) {
                        var tip = document.createElement("div");
                        tip.className = "ss-start-hint";
                        tip.innerHTML = self.esc(L.svcStartHint) + ' <code>start_mail_service.bat</code>';
                        c.appendChild(tip);
                    }
                    return;
                }
                self.svc = d;
                self.setSide(true, "服务运行中");
                if (box) box.innerHTML = '<span class="ss-tag ss-tag-ok">' + self.esc(L.svcRunning) + '</span>';
                if (reg) reg.innerHTML = d.registered
                    ? '<span class="ss-tag ss-tag-ok">' + self.esc(L.svcRegistered) + '</span>'
                    : '<span class="ss-tag ss-tag-bad">' + self.esc(L.svcUnregistered) + '</span>';
                if (node) node.innerHTML = self.esc((d.node || "") + ":" + (d.port || ""));
                if (port) port.innerHTML = self.esc(d.listen || "");
            });
        },

        loadCodes: function () {
            var self = this, L = this.lp;
            this.xhr("GET", this.mailBase + "/codes", null, function (st, d) {
                var box = self.q("#ssCodesBox");
                if (!box) return;
                if (st !== 200 || !d || !d.ok) { box.innerHTML = '<div class="ss-empty">—</div>'; return; }
                var rows = d.codes || [];
                self.codes = rows;
                if (!rows.length) { box.innerHTML = '<div class="ss-empty">' + self.esc(L.pendingEmpty) + '</div>'; return; }
                var h = '<table class="ss-table"><thead><tr>'
                    + '<th>' + self.esc(L.pendingMobile) + '</th>'
                    + '<th>验证码</th>'
                    + '<th>' + self.esc(L.pendingExpire) + '</th>'
                    + '</tr></thead><tbody>';
                rows.forEach(function (r) {
                    h += '<tr><td>' + self.esc(r.mobile) + '</td><td><code>' + self.esc(r.code)
                        + '</code></td><td>' + self.fmtLeft(r.expireIn) + '</td></tr>';
                });
                box.innerHTML = h + '</tbody></table>';
            });
        },

        sendTestCode: function () {
            var self = this, L = this.lp;
            var m = val("ssTestMobile");
            if (!m) { this.toast(L.sendTestCodePh, "err"); return; }
            this.xhr("POST", this.mailBase + "/test/code", { mobile: m }, function (st, d) {
                if (d && d.ok) {
                    self.toast(L.sendTestCodeOk + (d.code ? "（" + d.code + "）" : ""), "ok");
                    self.loadCodes();
                } else {
                    self.toast("失败：" + ((d && d.message) || st), "err");
                }
            });
        }
    };

    MWF.xApplication.SysSetting.Viewer = Viewer;
})();
