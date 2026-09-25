/**
 * x_component_Drive / drive.js —— 企业网盘 UI 与数据访问实现
 *
 * 数据层：O2OA 内置 x_file_assemble_control 服务（已实测全部接口可用）
 *   个人文件  folder2/list/top | folder2/list/{id} | attachment2/list/top | attachment2/list/folder/{id}
 *   上传/建夹 POST attachment2/upload/folder/{folderId} | POST folder2
 *   改删      PUT|DELETE attachment2/{id} | folder2/{id}
 *   下载预览  GET attachment2/{id}/download[|/stream] | attachment2/{id}/office/preview/type/{type}
 *   分类      POST attachment2/list/type/{page}/size/{size}   {fileType}
 *   企业共享  POST share | GET share/list/my | GET share/list/to/me | DELETE share/{id}
 *             POST share/share/{shareId}/file/{fileId}/folder/{folderId}
 *   回收站    GET recycle/list | POST recycle/{id}/resume | DELETE recycle/{id}/delete | recycle/empty
 *   容量      GET attachment2/user/capacity
 *
 * 说明：本文件为自包含实现，不依赖 MWF 的 UI 组件，只用原生 DOM/XHR，
 *       便于在 O2OA 桌面组件、门户页等任意宿主中复用。
 */
(function () {
    if (!window.MWF) { window.MWF = {}; }
    MWF.xApplication = MWF.xApplication || {};
    MWF.xApplication.Drive = MWF.xApplication.Drive || {};

    var NS = MWF.xApplication.Drive;

    /* ------------------------------------------------------------------ 常量 */
    var API = "/x_file_assemble_control/jaxrs";
    var ORG_API = "/x_organization_assemble_control/jaxrs";
    var AUTH_API = "/x_organization_assemble_authentication/jaxrs/authentication";
    /* 配置持久化通道（本部署实测）：
       读  GET  {SRF}/dict/{alias}/portal/{portalFlag}/data        —— 任意登录用户可读
       写  PUT  {DSN}/dict/{dictId}  （整对象覆盖，含 data）        —— 需门户管理权限
       surface 侧的 PUT/updateDataPath 在本部署被 HTTP 层拦为 405，故写入一律走 designer。 */
    var SRF = "/x_portal_assemble_surface/jaxrs";
    var DSN = "/x_portal_assemble_designer/jaxrs";
    var DICT_ALIAS = "driveSetting";
    var PORTAL_FLAG = "index";
    var ROOT = "../x_component_Drive";
    var ICON_BASE = ROOT + "/$Main/default/file/";
    var TOP_FOLD = "$$TOP_FOLD";

    /* 在线预览按扩展名分类（服务端 attachment2/{id}/download 返回真实 MIME，可直接内嵌渲染）。
       注意：本机未安装 LibreOffice/OnlyOffice，office/preview 接口会把原文件原样返回，
       因此 Office 类不做伪预览，改为「下载查看 + 明确提示」。 */
    var PREVIEW_KIND = {
        image: ["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico", "avif"],
        pdf: ["pdf"],
        /* ★ 必须含 "text"：服务端白名单里放行的纯文本后缀是 text（不是 txt），
           漏掉它会导致「白名单能传、但列表里没有预览入口」的错位。 */
        text: ["txt", "text", "md", "markdown", "log", "json", "xml", "csv", "ini", "conf", "yml", "yaml",
            "js", "css", "html", "htm", "java", "py", "sql", "sh", "bat", "properties"],
        audio: ["mp3", "wav", "ogg", "m4a", "aac", "flac", "wma"],
        video: ["mp4", "webm", "ogv", "mov", "m4v"],
        office: ["doc", "docx", "dot", "dotx", "rtf", "xls", "xlsx", "xlsm", "ppt", "pptx", "pps", "wps", "et", "dps"]
    };
    function previewKind(ext) {
        ext = String(ext || "").toLowerCase();
        for (var k in PREVIEW_KIND) {
            if (PREVIEW_KIND[k].indexOf(ext) > -1) return k;
        }
        return "";
    }

    var LP = NS.LP || {};
    function t(k, d) { return (LP && LP[k]) || d || k; }

    var EXT_ICON = {
        doc: "docx_win.png", docx: "docx_win.png", dot: "docx_win.png", dotx: "docx_win.png", rtf: "docx_win.png",
        xls: "xlsx_win.png", xlsx: "xlsx_win.png", xlsm: "xlsx_win.png", xlt: "xlsx_win.png", csv: "xlsx_win.png",
        ppt: "pptx_win.png", pptx: "pptx_win.png", pot: "pptx_win.png", potx: "pptx_win.png", pps: "pptx_win.png",
        pdf: "pdf.png", ofd: "ofd.png",
        txt: "text.png", text: "text.png", md: "text.png", log: "text.png", readme: "readme.png", ini: "ini.png", conf: "ini.png",
        jpg: "jpeg.png", jpeg: "jpeg.png", png: "png.png", gif: "gif.png", bmp: "bmp.png",
        tif: "tiff.png", tiff: "tiff.png",
        zip: "zip.png", rar: "rar.png", "7z": "zip.png", gz: "zip.png", tar: "zip.png",
        mp3: "mp3.png", wav: "wav.png", wma: "wma.png", midi: "midi.png", mid: "midi.png",
        mp4: "mpeg.png", mpeg: "mpeg.png", avi: "avi.png", mov: "mov.png", wmv: "wmv.png",
        mkv: "avi.png", rmvb: "avi.png", rm: "avi.png", flv: "avi.png",
        html: "html.png", htm: "html.png", xml: "html.png", css: "css.png", js: "jsf.png",
        json: "jsf.png", jsf: "jsf.png", jsp: "jsf.png",
        exe: "exe.png", msi: "exe.png", vsd: "vsd.png", psd: "psd.png", ai: "eps.png", eps: "eps.png",
        eml: "eml.png", msg: "eml.png", pst: "pst.png",
        accdb: "accdb.png", mdb: "accdb.png", fla: "fla.png", ind: "ind.png", proj: "proj.png",
        pub: "pub.png", url: "url.png", settings: "settings.png"
    };

    var CATEGORIES = [
        { k: "", n: "全部" }, { k: "image", n: "图片" }, { k: "office", n: "文档" },
        { k: "movie", n: "视频" }, { k: "music", n: "音乐" }, { k: "other", n: "其它" }
    ];

    /* ------------------------------------------------------------------ 工具 */
    function readCookie(name) {
        var m = document.cookie.match(new RegExp("(?:^|;\\s*)" + name.replace(/[-.]/g, "\\$&") + "=([^;]*)"));
        return m ? decodeURIComponent(m[1]) : "";
    }
    function token() {
        return readCookie((window.o2 && o2.tokenName) || "x-token");
    }

    function xhrJson(method, url, opt) {
        opt = opt || {};
        return new Promise(function (resolve, reject) {
            var x = new XMLHttpRequest();
            x.open(method, url, true);
            var tk = token();
            if (tk) { x.setRequestHeader("x-token", tk); }
            if (opt.json !== undefined) { x.setRequestHeader("Content-Type", "application/json"); }
            x.onload = function () {
                var d = null;
                try { d = JSON.parse(x.responseText); } catch (e) { }
                if (x.status >= 200 && x.status < 300 && (!d || d.type !== "error")) {
                    resolve(d);
                } else {
                    reject((d && d.message) ? d : { message: "HTTP " + x.status, status: x.status });
                }
            };
            x.onerror = function () { reject({ message: "网络请求失败，请检查服务是否可用" }); };
            try {
                x.send(opt.json !== undefined ? JSON.stringify(opt.json) : (opt.body || null));
            } catch (e) { reject({ message: String(e) }); }
        });
    }

    function el(tag, cls, html) {
        var d = document.createElement(tag);
        if (cls) d.className = cls;
        if (html !== undefined && html !== null) d.innerHTML = html;
        return d;
    }

    /* 取纯文本（用于 txt/md/json 等在线预览；同源请求自动带 x-token cookie） */
    function xhrText(url) {
        return new Promise(function (resolve, reject) {
            var x = new XMLHttpRequest();
            x.open("GET", url, true);
            var tk = token();
            if (tk) { x.setRequestHeader("x-token", tk); }
            x.onload = function () {
                if (x.status >= 200 && x.status < 300) { resolve(x.responseText); }
                else { reject({ message: "HTTP " + x.status, status: x.status }); }
            };
            x.onerror = function () { reject({ message: "网络请求失败" }); };
            x.send(null);
        });
    }

    function esc(s) {
        return String(s === undefined || s === null ? "" : s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function fmtSize(n) {
        n = Number(n) || 0;
        if (n < 1024) return n + " B";
        if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
        if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
        return (n / 1073741824).toFixed(2) + " GB";
    }

    function fmtTime(v) {
        if (!v) return "--";
        var s = String(v).replace("T", " ");
        return s.length > 16 ? s.substring(0, 16) : s;
    }

    function extOf(name) {
        var i = String(name || "").lastIndexOf(".");
        return i > -1 ? String(name).substring(i + 1).toLowerCase() : "";
    }

    function iconUrl(ext) {
        var f = EXT_ICON[ext] || "unknow.png";
        return ICON_BASE + f;
    }

    function svgIco(inner) {
        return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
            'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + inner + "</svg>";
    }

    var ICO = {
        personal: svgIco('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
        shared: svgIco('<path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-5h6v5"/>'),
        myshare: svgIco('<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/>'),
        recycle: svgIco('<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/>'),
        admin: svgIco('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 4.6a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 21 11a2 2 0 1 1 0 4z"/>'),
        up: svgIco('<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'),
        addfolder: svgIco('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v6M9 14h6"/>'),
        refresh: svgIco('<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>'),
        area: svgIco('<rect x="3" y="4" width="7" height="7" rx="1"/><rect x="14" y="4" width="7" height="7" rx="1"/><rect x="3" y="15" width="7" height="5" rx="1"/><rect x="14" y="15" width="7" height="5" rx="1"/>'),
        capacity: svgIco('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
        setting: svgIco('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 4.6a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 21 11a2 2 0 1 1 0 4z"/>'),
        back: svgIco('<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>')
    };

    /* 后台管理子菜单（对齐官方「个人文件 / 企业文件 / 后台管理」中的后台信息架构）
       ★ 「成员容量 / 用户总览」是管理视角：本体不展示"我自己用了多少"（那是页脚的事），
         而是展示**权限范围内每个人**的容量与使用情况 —— 数据源见 loadMembers()。 */
    var ADMIN_SUBS = [
        { k: "areafile", n: "共享区文件", d: "浏览各共享工作区内的文件", i: "area" },
        { k: "area", n: "共享区", d: "创建与维护组织级共享工作区", i: "shared" },
        { k: "capacity", n: "成员容量", d: "权限范围内每个人的容量统计", i: "capacity" },
        { k: "users", n: "用户总览", d: "所有用户的使用情况", i: "personal" },
        { k: "recycle", n: "回收站", d: "回收站数据与保留策略", i: "recycle" },
        { k: "setting", n: "设置", d: "云文件系统设置", i: "setting" }
    ];

    /* ★ 后台管理的授权锚点（与服务端 Business.controlAble 完全同源）：
       com.x.file.assemble.control.Business#controlAble =
           effectivePerson.isManager() || organization().person().hasRole(p, OrganizationDefinition.FileManager)
       ⇒ 「给某人的账号加上 FileManager 角色，他就获得后台管理」。
       前端不再自造判定，一律以 GET config/is/file/manager 的返回为准。 */
    var FILE_MANAGER_ROLE = "FileManager@FileManagerSystemRole@R";

    /* ------------------------------------------------------------------ Viewer */
    function Viewer(opt) {
        this.container = opt.container;
        this.app = opt.app;
        this.state = {
            sec: "personal",
            folder: null,
            path: [],
            fileType: "",
            me: null,
            orgUnique: "",
            orgName: "",
            counts: {},
            selected: null,
            busy: false,
            isManager: false,
            adminSub: "areafile",
            areaId: null,
            areaShare: null,
            areaPath: [],
            areaCur: null,
            sysConfig: null,
            /* 权限范围 / 授权来源（与角色对齐，见 adminBanner） */
            scopeTop: [], orgTop: [], scopeAll: false, authInfo: null,
            /* 成员容量 / 用户总览（管理视角，一次拉取两页共用） */
            members: null,          // 汇总对象：{rows:[], scopeName, scopeAll, managers:[], allShares:[], ts}
            memberBusy: false,
            memberQuery: "",
            memberSort: "used",     // used | name | unit | login
            /* 网盘策略（存于门户数据字典 driveSetting） */
            driveCfg: {
                dictId: null, portalId: null, loaded: false,
                shareLimitMb: 0, creatorPersonList: [], creatorRoleList: []
            }
        };
        this.init();
    }

    Viewer.prototype = {

        init: function () {
            this.renderShell();
            var self = this;
            this.loadMe().then(function () {
                self.go("personal");
            }).catch(function (e) {
                self.toast(e && e.message ? e.message : "初始化失败", true);
                self.go("personal");
            });
        },

        /* ---------------------------------------------------------- 骨架 */
        renderShell: function () {
            var self = this;
            var root = el("div", "drive-root");
            this.root = root;
            root.innerHTML =
                '<div class="drive-side">' +
                '  <div class="drive-side-user">' +
                '    <div class="drive-avatar" id="drv-avatar">网</div>' +
                '    <div class="drive-user-meta">' +
                '      <div class="drive-user-name" id="drv-uname">加载中…</div>' +
                '      <div class="drive-user-org" id="drv-uorg"></div>' +
                '    </div>' +
                '  </div>' +
                '  <div class="drive-nav" id="drv-nav"></div>' +
                '</div>' +
                '<div class="drive-main">' +
                '  <div class="drive-toolbar">' +
                '    <div class="drive-toolbar-row">' +
                '      <div class="drive-crumb" id="drv-crumb"></div>' +
                '      <div class="drive-actions" id="drv-actions"></div>' +
                '    </div>' +
                '    <div class="drive-tabs" id="drv-tabs"></div>' +
                '  </div>' +
                '  <div class="drive-body" id="drv-body"></div>' +
                '  <div class="drive-foot" id="drv-foot"></div>' +
                '</div>' +
                '<input type="file" id="drv-file" multiple style="display:none">';

            this.container.appendChild(root);
            this.els = {
                nav: root.querySelector("#drv-nav"),
                crumb: root.querySelector("#drv-crumb"),
                actions: root.querySelector("#drv-actions"),
                tabs: root.querySelector("#drv-tabs"),
                body: root.querySelector("#drv-body"),
                foot: root.querySelector("#drv-foot"),
                file: root.querySelector("#drv-file"),
                uname: root.querySelector("#drv-uname"),
                uorg: root.querySelector("#drv-uorg"),
                avatar: root.querySelector("#drv-avatar")
            };

            this.els.file.addEventListener("change", function () {
                if (this.files && this.files.length) { self.upload(this.files); }
                this.value = "";
            });

            this.bindDrop();
        },

        bindDrop: function () {
            var self = this;
            var b = this.els.body;
            ["dragenter", "dragover"].forEach(function (ev) {
                b.addEventListener(ev, function (e) {
                    e.preventDefault(); e.stopPropagation();
                    if (self.state.sec === "personal") { b.classList.add("dragover"); }
                });
            });
            ["dragleave", "drop"].forEach(function (ev) {
                b.addEventListener(ev, function (e) {
                    e.preventDefault(); e.stopPropagation();
                    b.classList.remove("dragover");
                });
            });
            b.addEventListener("drop", function (e) {
                if (self.state.sec !== "personal") return;
                var dt = e.dataTransfer;
                if (dt && dt.files && dt.files.length) { self.upload(dt.files); }
            });
        },

        /* ---------------------------------------------------------- 用户与上下文 */
        loadMe: function () {
            var self = this;
            return xhrJson("GET", AUTH_API).then(function (d) {
                var data = (d && d.data) || {};
                var id = (data.identityList && data.identityList[0]) || null;
                var roles = data.roleList || [];
                /* ★★ 必须区分「人员的 dN」与「身份的 dN」——踩过的坑：
                   data.distinguishedName            = 系统管理员@admin@P            ← 人员 dN（@P）
                   data.identityList[0].distinguishedName = 系统管理员@51100…_admin@I  ← 身份 dN（@I）
                   attachment.person / share.person 存的都是**人员 dN**，
                   所以凡是要跟 person 比对、或作为 ?person= 参数的地方，一律用人员 dN。
                   早期版本误用 identityList[0].distinguishedName ⇒ 逐人容量全部查空、
                   「是否我本人的分享」判断恒为 false。 */
                self.state.me = {
                    name: data.name || (id && id.name) || "未登录",
                    dn: data.distinguishedName || (id && id.distinguishedName) || "",
                    unique: data.unique || "",
                    identityDn: id ? id.distinguishedName : "",
                    unit: id ? id.unit : "",
                    unitName: (id && (id.unitLevelName || id.unitName)) || "",
                    roles: roles
                };
                self.els.uname.textContent = self.state.me.name;
                self.els.uorg.textContent = self.state.me.unitName || "";
                self.els.avatar.textContent = (self.state.me.name || "网").substring(0, 1);
                return Promise.all([self.loadOrg(), self.loadManager(), self.loadDriveCfg(),
                    self.loadScope(), self.loadAuthSource()]);
            });
        },

        /* ------------------------------------------------ 网盘策略配置（门户数据字典 driveSetting）
           读：GET SRF/dict/driveSetting/portal/index/data
           写：PUT DSN/dict/{dictId}（需先解析 portalId 与 dictId，缺失时自动创建字典）
           字典不存在/解析失败时静默降级为「不限制」，不阻断主流程。 */
        loadDriveCfg: function () {
            var self = this;
            return xhrJson("GET", SRF + "/dict/" + DICT_ALIAS + "/portal/" + PORTAL_FLAG + "/data")
                .then(function (d) {
                    var v = (d && d.data) || {};
                    self.applyDriveCfg(v);
                    self.state.driveCfg.loaded = true;
                })
                .catch(function () { /* 字典尚未创建：保持默认（不限制） */ });
        },

        applyDriveCfg: function (v) {
            var cfg = this.state.driveCfg;
            v = v || {};
            cfg.shareLimitMb = Number(v.shareLimitMb) || 0;
            cfg.creatorPersonList = (v.creatorPersonList || []).slice();
            cfg.creatorRoleList = (v.creatorRoleList || []).slice();
        },

        /* 解析门户 id 与字典 id（结果缓存在 state.driveCfg，避免重复请求） */
        ensureDict: function () {
            var self = this;
            var cfg = this.state.driveCfg;
            if (cfg.dictId && cfg.portalId) {
                return Promise.resolve({ portalId: cfg.portalId, dictId: cfg.dictId });
            }
            return xhrJson("GET", SRF + "/portal/list").then(function (d) {
                var list = (d && d.data) || [];
                var portal = null;
                for (var i = 0; i < list.length; i++) {
                    if (list[i].alias === PORTAL_FLAG) { portal = list[i]; }
                }
                if (!portal) { portal = list[0]; }
                if (!portal) { throw { message: "未找到可用门户，无法保存设置" }; }
                cfg.portalId = portal.id;
                return xhrJson("GET", DSN + "/dict/list/portal/" + encodeURIComponent(portal.id));
            }).then(function (d) {
                var list = (d && d.data) || [];
                for (var i = 0; i < list.length; i++) {
                    if (list[i].alias === DICT_ALIAS) { self.state.driveCfg.dictId = list[i].id; }
                }
                if (self.state.driveCfg.dictId) {
                    return { portalId: cfg.portalId, dictId: cfg.dictId };
                }
                /* 不存在则创建（首次打开设置页时自动建） */
                return xhrJson("POST", DSN + "/dict", {
                    json: {
                        application: cfg.portalId, alias: DICT_ALIAS, name: DICT_ALIAS,
                        data: { shareLimitMb: 0, creatorPersonList: [], creatorRoleList: [] }
                    }
                }).then(function (r) {
                    self.state.driveCfg.dictId = (r && r.data && r.data.id) || null;
                    if (!self.state.driveCfg.dictId) { throw { message: "创建配置字典失败" }; }
                    return { portalId: cfg.portalId, dictId: self.state.driveCfg.dictId };
                });
            });
        },

        saveDriveCfg: function (data) {
            var self = this;
            return this.ensureDict().then(function (ids) {
                return xhrJson("PUT", DSN + "/dict/" + encodeURIComponent(ids.dictId), {
                    json: {
                        id: ids.dictId, application: ids.portalId,
                        alias: DICT_ALIAS, name: DICT_ALIAS, data: data
                    }
                });
            }).then(function () {
                self.applyDriveCfg(data);
                self.state.driveCfg.loaded = true;
            });
        },

        /* 当前用户是否在「共享区可创建权限名单」内（名单为空 = 不限制，全员可创建） */
        canCreateShare: function () {
            var cfg = this.state.driveCfg;
            var pl = cfg.creatorPersonList || [], rl = cfg.creatorRoleList || [];
            if (!pl.length && !rl.length) { return true; }
            var me = this.state.me || {};
            if (me.dn && pl.indexOf(me.dn) > -1) { return true; }
            if (me.name && pl.indexOf(me.name) > -1) { return true; }
            var roles = me.roles || [];
            for (var i = 0; i < roles.length; i++) {
                var parts = String(roles[i]).split("@");
                for (var j = 0; j < rl.length; j++) {
                    var e = String(rl[j]);
                    if (e === roles[i]) { return true; }
                    if (parts.length > 1 && (e === parts[0] || e === parts[1])) { return true; }
                    if (e === parts[0] + "@" + parts[1]) { return true; }
                }
            }
            return false;
        },

        creatorHint: function () {
            var cfg = this.state.driveCfg;
            var pl = cfg.creatorPersonList || [], rl = cfg.creatorRoleList || [];
            if (!pl.length && !rl.length) { return "当前未限定名单（全员可创建共享区）"; }
            return "可创建共享区的人员/角色：" + pl.concat(rl).map(function (x) {
                return String(x).split("@")[0];
            }).join("、");
        },

        /* 是否云文件管理员（决定是否展示「后台管理」） */
        loadManager: function () {
            var self = this;
            return xhrJson("GET", API + "/config/is/file/manager").then(function (d) {
                self.state.isManager = !!(d && d.data && d.data.value);
            }).catch(function () { self.state.isManager = false; });
        },

        loadOrg: function () {
            var self = this;
            return xhrJson("GET", ORG_API + "/unit/list/top").then(function (d) {
                var list = (d && d.data) || [];
                if (list.length) {
                    self.state.orgUnique = list[0].unique;
                    self.state.orgName = list[0].name;
                }
            }).catch(function () { /* 组织信息缺失不阻断主流程 */ });
        },

        /* ---------------------------------------------------------- 导航 */
        renderNav: function () {
            var self = this;
            this.els.nav.innerHTML = "";

            function item(k, n, ico, active, extra, onClick) {
                var nd = el("div", "drive-nav-item" + (active ? " active" : ""));
                nd.setAttribute("data-sec", k);
                nd.innerHTML = '<span class="drive-nav-ico">' + ico + "</span>" +
                    "<span>" + esc(n) + "</span>" + (extra || "");
                nd.addEventListener("click", function () { (onClick || function () { self.go(k); })(); });
                return nd;
            }
            function group(titleHtml, nodes) {
                var g = el("div", "drive-nav-group");
                if (titleHtml) g.appendChild(el("div", "drive-nav-title", titleHtml));
                nodes.forEach(function (nd) { g.appendChild(nd); });
                return g;
            }

            /* —— 后台管理：左栏切换为后台子菜单（对齐官方 demo 的信息架构） —— */
            if (this.state.sec === "admin") {
                this.els.nav.appendChild(group("", [
                    item("personal", t("backMain", "返回主菜单"), ICO.back, false, "", function () { self.go("personal"); })
                ]));
                this.els.nav.appendChild(group(
                    '<span class="drive-nav-htitle"><span class="drive-nav-hico">' + ICO.admin + "</span>" + esc(t("admin", "后台管理")) + "</span>",
                    ADMIN_SUBS.map(function (s) {
                        return item("admin", s.n, ICO[s.i] || ICO.admin, self.state.adminSub === s.k, "",
                            (function (kk) { return function () { self.goAdmin(kk); }; })(s.k));
                    })
                ));
                return;
            }

            var defs = [
                { k: "personal", n: t("personal", "个人文件"), i: ICO.personal },
                { k: "shared", n: t("shared", "企业文件"), i: ICO.shared },
                { k: "myshare", n: t("myshare", "我的分享"), i: ICO.myshare },
                { k: "recycle", n: t("recycle", "回收站"), i: ICO.recycle }
            ];

            this.els.nav.appendChild(group("", defs.map(function (it) {
                var cnt = self.state.counts[it.k];
                return item(it.k, it.n, it.i, self.state.sec === it.k,
                    cnt ? '<span class="drive-nav-count">' + cnt + "</span>" : "");
            })));

            /* 仅云文件管理员可见「后台管理」 */
            if (this.state.isManager) {
                this.els.nav.appendChild(group("管理", [
                    item("admin", t("admin", "后台管理"), ICO.admin, false, "")
                ]));
            }
        },

        /* 进入后台管理并定位到某个子页 */
        goAdmin: function (sub) {
            this.state.sec = "admin";
            this.state.adminSub = sub;
            this.state.selected = null;
            if (sub !== "areafile") { this.state.areaId = null; this.state.areaShare = null; this.state.areaPath = []; }
            this.renderNav();
            this.renderToolbar();
            this.refresh();
        },

        go: function (sec) {
            if (this.state.busy) return;
            this.state.sec = sec;
            this.state.selected = null;
            if (sec !== "personal") { this.state.fileType = ""; }
            /* 切换任一栏目都退出共享文件夹浏览态 */
            this.state.areaId = null; this.state.areaShare = null; this.state.areaPath = []; this.state.areaCur = null;
            if (sec === "admin") { this.state.adminSub = "areafile"; }
            this.renderNav();
            this.renderToolbar();
            this.refresh();
        },

        /* ---------------------------------------------------------- 工具条 */
        renderToolbar: function () {
            var self = this;
            var sec = this.state.sec;

            // 面包屑
            var cr = this.els.crumb;
            cr.innerHTML = "";
            if (sec === "personal") {
                var seg = el("span", this.state.folder ? "drive-crumb-seg" : "drive-crumb-cur", esc(t("personal", "个人文件")));
                if (this.state.folder) seg.addEventListener("click", function () { self.enterFolder(null, null); });
                cr.appendChild(seg);
                this.state.path.forEach(function (p, i) {
                    cr.appendChild(el("span", "drive-crumb-sep", "›"));
                    var last = (i === self.state.path.length - 1);
                    var s2 = el("span", last ? "drive-crumb-cur" : "drive-crumb-seg", esc(p.name));
                    if (!last) {
                        s2.addEventListener("click", function () { self.enterFolder(p.id, null, i); });
                    }
                    cr.appendChild(s2);
                });
            } else if (sec === "admin") {
                var sub = this.adminSubDef();
                cr.appendChild(el("span", "drive-crumb-cur", esc(t("admin", "后台管理"))));
                cr.appendChild(el("span", "drive-crumb-sep", "›"));
                cr.appendChild(el("span", "drive-crumb-cur", esc(sub ? sub.n : "")));
                if (this.state.areaShare && this.state.adminSub === "areafile") {
                    this.crumbSharedFolder(cr, null);
                }
            } else {
                var map = { shared: "企业文件", myshare: "我的分享", recycle: "回收站" };
                if (this.state.areaShare && (sec === "shared" || sec === "myshare")) {
                    this.crumbSharedFolder(cr, map[sec] || "");
                } else {
                    cr.appendChild(el("span", "drive-crumb-cur", map[sec] || ""));
                }
            }

            // 操作按钮
            var ac = this.els.actions;
            ac.innerHTML = "";
            if (sec === "personal") {
                ac.appendChild(this.btn(t("upload", "上传"), "primary", function () { self.els.file.click(); }, ICO.up));
                ac.appendChild(this.btn(t("mkdir", "新建文件夹"), "", function () { self.promptFolder(); }, ICO.addfolder));
            } else if (sec === "recycle") {
                ac.appendChild(this.btn(t("clear", "清空"), "", function () { self.clearRecycle(); }));
            } else if (sec === "admin") {
                if (this.state.adminSub === "area") {
                    ac.appendChild(this.btn(t("newArea", "新建共享区"), "primary", function () { self.promptNewArea(); }, ICO.up));
                } else if (this.state.adminSub === "areafile") {
                    if (this.state.areaShare && this.isAreaMine()) {
                        ac.appendChild(this.btn(t("upload", "上传"), "primary", function () { self.els.file.click(); }, ICO.up));
                        ac.appendChild(this.btn(t("mkdir", "新建文件夹"), "", function () { self.promptAreaFolder(); }, ICO.addfolder));
                    }
                    if (this.state.areaId) {
                        ac.appendChild(this.btn(t("back", "返回列表"), "ghost", function () { self.closeSharedFolder(); }, ICO.back));
                    }
                } else if (this.state.adminSub === "recycle") {
                    ac.appendChild(this.btn(t("clear", "清空"), "", function () { self.clearRecycle(); }));
                }
            } else if (this.state.areaShare && (sec === "shared" || sec === "myshare")) {
                ac.appendChild(this.btn(t("back", "返回列表"), "ghost", function () { self.closeSharedFolder(); }, ICO.back));
            }
            ac.appendChild(this.btn(t("refresh", "刷新"), "ghost", function () { self.refresh(); }, ICO.refresh));

            // 分类标签（个人文件 / 企业文件；进入共享文件夹浏览后隐藏）
            var tb = this.els.tabs;
            tb.innerHTML = "";
            if ((sec === "personal" || sec === "shared") && !this.state.areaShare) {
                CATEGORIES.forEach(function (c) {
                    var tab = el("div", "drive-tab" + (self.state.fileType === c.k ? " active" : ""), esc(c.n));
                    tab.addEventListener("click", function () {
                        self.state.fileType = c.k;
                        self.renderToolbar();
                        self.refresh();
                    });
                    tb.appendChild(tab);
                });
            }
        },

        adminSubDef: function () {
            var k = this.state.adminSub;
            for (var i = 0; i < ADMIN_SUBS.length; i++) { if (ADMIN_SUBS[i].k === k) return ADMIN_SUBS[i]; }
            return null;
        },

        /* 共享文件夹面包屑；rootName 非空时先渲染可点击的根节点（点击返回共享列表） */
        crumbSharedFolder: function (cr, rootName) {
            var self = this;
            var sh = this.state.areaShare;
            if (!sh) { return; }
            if (rootName) {
                var root = el("span", "drive-crumb-seg", esc(rootName));
                root.addEventListener("click", function () { self.closeSharedFolder(); });
                cr.appendChild(root);
                cr.appendChild(el("span", "drive-crumb-sep", "›"));
            }
            var inSub = this.state.areaPath.length > 0;
            var nameSeg = el("span", inSub ? "drive-crumb-seg" : "drive-crumb-cur", esc(sh.name || ""));
            if (inSub) { nameSeg.addEventListener("click", function () { self.enterAreaFolder(null, null); }); }
            cr.appendChild(nameSeg);
            this.state.areaPath.forEach(function (p, i) {
                cr.appendChild(el("span", "drive-crumb-sep", "›"));
                var last = (i === self.state.areaPath.length - 1);
                var s2 = el("span", last ? "drive-crumb-cur" : "drive-crumb-seg", esc(p.name));
                if (!last) { s2.addEventListener("click", function () { self.enterAreaFolder(p.id, null, i); }); }
                cr.appendChild(s2);
            });
        },
        isAreaMine: function () {
            return !!(this.state.areaShare && this.state.me && this.state.areaShare.person === this.state.me.dn);
        },

        btn: function (label, cls, onClick, ico) {
            var b = el("button", "drive-btn " + (cls || ""));
            b.innerHTML = (ico || "") + "<span>" + esc(label) + "</span>";
            b.addEventListener("click", onClick);
            return b;
        },

        /* ---------------------------------------------------------- 数据分发 */
        refresh: function () {
            var self = this;
            this.state.busy = true;
            var p;
            switch (this.state.sec) {
                case "personal": p = this.loadPersonal(); break;
                case "shared": p = this.loadShared(); break;
                case "myshare": p = this.loadMyShare(); break;
                case "recycle": p = this.loadRecycle(); break;
                case "admin": p = this.loadAdmin(this.state.adminSub); break;
                default: p = Promise.resolve();
            }
            p.then(function () {
                self.state.busy = false;
            }).catch(function (e) {
                self.state.busy = false;
                self.renderError(e);
            });
        },

        loading: function (msg) {
            this.els.body.innerHTML = '<div class="drive-loading">' +
                esc(msg || t("loading", "加载中…")) + "</div>";
        },

        renderError: function (e) {
            var msg = (e && e.message) ? e.message : String(e);
            this.els.body.innerHTML = '<div class="drive-empty"><span class="drive-empty-ico">⚠</span>' +
                esc(msg) + "</div>";
        },

        /* ---------------------------------------------------------- 个人文件 */
        loadPersonal: function () {
            var self = this;
            this.loading();
            var fid = this.state.folder;
            var cat = this.state.fileType;

            var pFolders = xhrJson("GET", API + (fid ? "/folder2/list/" + encodeURIComponent(fid) : "/folder2/list/top"));

            var pFiles;
            if (cat) {
                pFiles = xhrJson("POST", API + "/attachment2/list/type/1/size/500", { json: { fileType: cat } })
                    .then(function (d) { return { data: (d && d.data) || [] }; });
            } else {
                pFiles = xhrJson("GET", API + (fid ? "/attachment2/list/folder/" + encodeURIComponent(fid) : "/attachment2/list/top"));
            }

            return Promise.all([pFolders, pFiles]).then(function (r) {
                var folders = (r[0] && r[0].data) || [];
                var files = (r[1] && r[1].data) || [];
                self.state.counts.personal = folders.length + files.length;
                self.renderPersonal(folders, files);
                self.loadCapacity();
            });
        },

        renderPersonal: function (folders, files) {
            var self = this;
            var body = this.els.body;
            body.innerHTML = "";

            if (!folders.length && !files.length) {
                body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">📂</span>' +
                    esc(this.state.folder ? "此文件夹为空" : t("empty", "这里还没有内容")) +
                    "<br><span style='font-size:12px;color:#c3c8d0'>可直接把文件拖到此处上传</span></div></div>";
                return;
            }

            if (folders.length) {
                var p1 = el("div", "drive-panel");
                p1.appendChild(this.headRow("folder"));
                folders.forEach(function (f) {
                    p1.appendChild(self.folderRow(f));
                });
                body.appendChild(p1);
            }

            if (files.length) {
                var p2 = el("div", "drive-panel");
                p2.appendChild(this.headRow("file"));
                files.forEach(function (f) {
                    p2.appendChild(self.fileRow(f));
                });
                body.appendChild(p2);
            }
        },

        headRow: function () {
            var h = el("div", "drive-head");
            h.innerHTML = '<div class="drive-col-name">' + esc(t("name", "名称")) + "</div>" +
                '<div class="drive-col-size">' + esc(t("size", "大小")) + "</div>" +
                '<div class="drive-col-time">' + esc(t("time", "修改时间")) + "</div>" +
                '<div class="drive-col-op">' + esc(t("operation", "操作")) + "</div>";
            return h;
        },

        folderRow: function (f) {
            var self = this;
            var row = el("div", "drive-row");
            row.innerHTML =
                '<div class="drive-col-name is-folder">' +
                '  <img class="drive-ficon" src="' + ICON_BASE + 'folder.png">' +
                '  <span class="drive-fname" title="' + esc(f.name) + '">' + esc(f.name) + "</span>" +
                "</div>" +
                '<div class="drive-col-size">' + (f.attachmentCount ? f.attachmentCount + " 项" : "-") + "</div>" +
                '<div class="drive-col-time">' + esc(fmtTime(f.updateTime || f.createTime)) + "</div>" +
                '<div class="drive-col-op"></div>';

            row.querySelector(".drive-col-name").addEventListener("click", function () {
                self.enterFolder(f.id, f.name);
            });

            var ops = row.querySelector(".drive-col-op");
            ops.appendChild(this.op(t("zip", "打包下载"), function () { self.downloadFolder(f.id); }));
            ops.appendChild(this.op(t("share", "共享到企业"), function () { self.shareToOrg(f.id, f.name, "folder"); }));
            ops.appendChild(this.op(t("rename", "重命名"), function () { self.renameFolder(f); }));
            ops.appendChild(this.op(t("delete", "删除"), function () { self.remove("folder", f.id, f.name); }, "danger"));
            return row;
        },

        fileRow: function (f) {
            var self = this;
            var ext = f.extension || extOf(f.name);
            var row = el("div", "drive-row");
            row.innerHTML =
                '<div class="drive-col-name">' +
                '  <img class="drive-ficon" src="' + iconUrl(ext) + '">' +
                '  <span class="drive-fname" title="' + esc(f.name) + '">' + esc(f.name) + "</span>" +
                "</div>" +
                '<div class="drive-col-size">' + esc(fmtSize(f.length)) + "</div>" +
                '<div class="drive-col-time">' + esc(fmtTime(f.updateTime || f.createTime)) + "</div>" +
                '<div class="drive-col-op"></div>';

            var ops = row.querySelector(".drive-col-op");
            if (previewKind(ext)) {
                ops.appendChild(this.op(t("preview", "预览"), function () { self.previewFile(f); }));
            }
            ops.appendChild(this.op(t("download", "下载"), function () { self.download(f.id); }));
            ops.appendChild(this.op(t("share", "共享到企业"), function () { self.shareToOrg(f.id, f.name, "attachment"); }));
            ops.appendChild(this.op(t("rename", "重命名"), function () { self.renameFile(f); }));
            ops.appendChild(this.op(t("delete", "删除"), function () { self.remove("attachment", f.id, f.name); }, "danger"));
            return row;
        },

        op: function (label, fn, cls) {
            var a = el("span", "drive-op " + (cls || ""), esc(label));
            a.addEventListener("click", function (e) {
                e.stopPropagation();
                fn();
            });
            return a;
        },

        enterFolder: function (id, name, pathIndex) {
            if (id === null) {
                this.state.folder = null;
                this.state.path = [];
            } else {
                if (typeof pathIndex === "number") {
                    this.state.path = this.state.path.slice(0, pathIndex + 1);
                    this.state.folder = this.state.path[this.state.path.length - 1].id;
                } else {
                    this.state.path = this.state.path.concat([{ id: id, name: name }]);
                    this.state.folder = id;
                }
            }
            this.renderToolbar();
            this.loadPersonal();
        },

        /* ---------------------------------------------------------- 企业文件（共享给我） */
        loadShared: function () {
            var self = this;
            if (this.state.areaShare) { return this.renderAreaBrowse(); }
            this.loading();
            var cat = this.state.fileType;
            var url = cat && cat !== "" ? API + "/share/list/to/me2/" + cat : API + "/share/list/to/me";
            return xhrJson("GET", url).then(function (d) {
                var list = (d && d.data) || [];
                self.state.counts.shared = list.length;
                self.renderShared(list);
                self.loadCapacity();
            }).catch(function (e) {
                // 分类维度失败时退回全量
                if (cat) {
                    return xhrJson("GET", API + "/share/list/to/me").then(function (d) {
                        var list = (d && d.data) || [];
                        self.state.counts.shared = list.length;
                        self.renderShared(list);
                    });
                }
                throw e;
            });
        },

        isFolderShare: function (s) {
            return !!(s && (s.fileType === "folder" || (!s.extension && !s.contentType)));
        },

        renderShared: function (list) {
            var self = this;
            var body = this.els.body;
            body.innerHTML = "";
            if (!list.length) {
                body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">🏢</span>暂无共享给你的文件' +
                    "<br><span style='font-size:12px;color:#c3c8d0'>" +
                    "在「个人文件」里对文件/文件夹点「共享到企业」，即可让全员在此看到</span></div></div>";
                return;
            }

            var p = el("div", "drive-panel");
            var h = el("div", "drive-head");
            h.innerHTML = '<div class="drive-col-name">' + esc(t("name", "名称")) + "</div>" +
                '<div class="drive-col-owner">' + esc(t("owner", "分享者")) + "</div>" +
                '<div class="drive-col-scope">' + esc(t("scope", "共享范围")) + "</div>" +
                '<div class="drive-col-time">' + esc(t("time", "修改时间")) + "</div>" +
                '<div class="drive-col-op">' + esc(t("operation", "操作")) + "</div>";
            p.appendChild(h);

            list.forEach(function (s) {
                var isFolder = self.isFolderShare(s);
                var ext = s.extension || extOf(s.name);
                var scope = (s.shareOrgList && s.shareOrgList.length) ? '<span class="drive-tag">全员</span>'
                    : (s.shareGroupList && s.shareGroupList.length) ? '<span class="drive-tag">群组</span>'
                        : '<span class="drive-tag gray">指定人员</span>';

                var row = el("div", "drive-row");
                row.innerHTML =
                    '<div class="drive-col-name' + (isFolder ? " is-folder" : "") + '">' +
                    '  <img class="drive-ficon" src="' + (isFolder ? ICON_BASE + "folder.png" : iconUrl(ext)) + '">' +
                    '  <span class="drive-fname" title="' + esc(s.name) + '">' + esc(s.name) + "</span>" +
                    (isFolder ? '<span class="drive-tag gray">文件夹</span>' : "") +
                    "</div>" +
                    '<div class="drive-col-owner">' + esc(String(s.person || "").split("@")[0]) + "</div>" +
                    '<div class="drive-col-scope">' + scope + "</div>" +
                    '<div class="drive-col-time">' + esc(fmtTime(s.createTime)) + "</div>" +
                    '<div class="drive-col-op"></div>';

                var ops = row.querySelector(".drive-col-op");
                if (isFolder) {
                    row.querySelector(".drive-col-name").addEventListener("click", function () { self.openSharedFolder(s); });
                    ops.appendChild(self.op(t("browse", "浏览"), function () { self.openSharedFolder(s); }));
                    /* 他人共享的文件夹不做「打包下载」：folder2/{id}/download 只对文件夹主人放行；
                       进入后可对单个文件下载。 */
                } else {
                    if (previewKind(ext)) {
                        ops.appendChild(self.op(t("preview", "预览"), function () { self.previewSharedFile(s.id, s); }));
                    }
                    ops.appendChild(self.op(t("download", "下载"), function () { self.downloadShare(s); }));
                    ops.appendChild(self.op(t("saveToMy", "保存到我的网盘"), function () { self.saveToMy(s); }));
                }
                var mine = self.state.me && s.person === self.state.me.dn;
                if (mine) {
                    ops.appendChild(self.op(t("unshare", "取消共享"), function () { self.removeShare(s); }, "danger"));
                }
                p.appendChild(row);
            });
            body.appendChild(p);
        },

        /* ---------------------------------------------------------- 我的分享 */
        loadMyShare: function () {
            var self = this;
            if (this.state.areaShare) { return this.renderAreaBrowse(); }
            this.loading();
            return xhrJson("GET", API + "/share/list/my").then(function (d) {
                var list = (d && d.data) || [];
                self.state.counts.myshare = list.length;
                self.renderMyShare(list);
            });
        },

        renderMyShare: function (list) {
            var self = this;
            var body = this.els.body;
            body.innerHTML = "";
            if (!list.length) {
                body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">🔗</span>你还没有共享任何文件或文件夹</div></div>';
                return;
            }
            var p = el("div", "drive-panel");
            var h = el("div", "drive-head");
            h.innerHTML = '<div class="drive-col-name">' + esc(t("name", "名称")) + "</div>" +
                '<div class="drive-col-scope">' + esc(t("scope", "共享范围")) + "</div>" +
                '<div class="drive-col-time">' + esc(t("time", "修改时间")) + "</div>" +
                '<div class="drive-col-op">' + esc(t("operation", "操作")) + "</div>";
            p.appendChild(h);

            list.forEach(function (s) {
                var isFolder = self.isFolderShare(s);
                var ext = s.extension || extOf(s.name);
                var orgs = (s.shareOrgList || []).length;
                var users = (s.shareUserList || []).length;
                var scope = orgs ? '<span class="drive-tag">全员 ' + orgs + "</span>"
                    : '<span class="drive-tag gray">指定 ' + users + " 人</span>";

                var row = el("div", "drive-row");
                row.innerHTML =
                    '<div class="drive-col-name' + (isFolder ? " is-folder" : "") + '">' +
                    '  <img class="drive-ficon" src="' + (isFolder ? ICON_BASE + "folder.png" : iconUrl(ext)) + '">' +
                    '  <span class="drive-fname" title="' + esc(s.name) + '">' + esc(s.name) + "</span>" +
                    (isFolder ? '<span class="drive-tag gray">文件夹</span>' : "") +
                    "</div>" +
                    '<div class="drive-col-scope">' + scope + "</div>" +
                    '<div class="drive-col-time">' + esc(fmtTime(s.createTime)) + "</div>" +
                    '<div class="drive-col-op"></div>';

                var ops = row.querySelector(".drive-col-op");
                if (isFolder) {
                    row.querySelector(".drive-col-name").addEventListener("click", function () { self.openSharedFolder(s); });
                    ops.appendChild(self.op(t("browse", "浏览"), function () { self.openSharedFolder(s); }));
                    ops.appendChild(self.op(t("zip", "打包下载"), function () { self.downloadFolder(s.fileId); }));
                } else {
                    if (previewKind(ext)) {
                        ops.appendChild(self.op(t("preview", "预览"), function () { self.previewSharedFile(s.id, s); }));
                    }
                    ops.appendChild(self.op(t("download", "下载"), function () { self.downloadShare(s); }));
                }
                ops.appendChild(self.op(t("unshare", "取消共享"), function () { self.removeShare(s); }, "danger"));
                p.appendChild(row);
            });
            body.appendChild(p);
        },

        /* ---------------------------------------------------------- 回收站 */
        loadRecycle: function () {
            var self = this;
            this.loading();
            return xhrJson("GET", API + "/recycle/list").then(function (d) {
                var list = (d && d.data) || [];
                self.state.counts.recycle = list.length;
                self.renderRecycle(list);
            });
        },

        renderRecycle: function (list) {
            var self = this;
            var body = this.els.body;
            body.innerHTML = "";
            if (!list.length) {
                body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">🗑</span>回收站是空的</div></div>';
                return;
            }
            var p = el("div", "drive-panel");
            var h = el("div", "drive-head");
            h.innerHTML = '<div class="drive-col-name">' + esc(t("name", "名称")) + "</div>" +
                '<div class="drive-col-size">' + esc(t("size", "大小")) + "</div>" +
                '<div class="drive-col-time">' + esc(t("time", "修改时间")) + "</div>" +
                '<div class="drive-col-op">' + esc(t("operation", "操作")) + "</div>";
            p.appendChild(h);

            list.forEach(function (f) {
                var ext = f.extension || extOf(f.name);
                var isFolder = !f.extension;
                var row = el("div", "drive-row");
                row.innerHTML =
                    '<div class="drive-col-name">' +
                    '  <img class="drive-ficon" src="' + (isFolder ? ICON_BASE + "folder.png" : iconUrl(ext)) + '">' +
                    '  <span class="drive-fname">' + esc(f.name) + "</span>" +
                    "</div>" +
                    '<div class="drive-col-size">' + esc(f.length ? fmtSize(f.length) : "-") + "</div>" +
                    '<div class="drive-col-time">' + esc(fmtTime(f.updateTime || f.createTime)) + "</div>" +
                    '<div class="drive-col-op"></div>';

                var ops = row.querySelector(".drive-col-op");
                ops.appendChild(self.op(t("resume", "还原"), function () { self.resumeRecycle(f.id); }));
                ops.appendChild(self.op("彻底删除", function () { self.purgeRecycle(f.id); }, "danger"));
                p.appendChild(row);
            });
            body.appendChild(p);
        },

        /* ---------------------------------------------------------- 后台管理 */
        /* 信息架构对齐官方「企业网盘」：共享区文件 / 共享区 / 个人容量 / 回收站 / 设置
           数据层全部落到 x_file_assemble_control 的真实接口：
             GET  config/is/file/manager                  是否云文件管理员（是否展示后台管理）
             GET  config/system/config                    系统设置读取
             POST config                                  系统设置保存
             GET  share/list/my | share/list/to/me         共享区（组织级共享文件夹）来源
             GET  share/list/folder/share/{sid}/folder/{fid}/  共享区内的子文件夹
             GET  share/list/att/share/{sid}/folder/{fid}/     共享区内的附件
             GET  recycle/list | POST recycle/{id}/resume | DELETE recycle/{id}/delete | recycle/empty
             GET  attachment2/user/capacity               我的已用容量
        */
        loadAdmin: function (sub) {
            switch (sub) {
                case "areafile": return this.adminAreaFiles();
                case "area": return this.adminAreas();
                case "capacity": return this.adminCapacity();
                case "users": return this.adminUsers();
                case "recycle": return this.adminRecycle();
                case "setting": return this.adminSetting();
                default: return Promise.resolve();
            }
        },

        /* 共享区集合：组织级共享的「顶层文件夹」即共享工作区 */
        loadAreas: function () {
            var self = this;
            function norm(d) { return (d && d.data) || []; }
            return Promise.all([
                xhrJson("GET", API + "/share/list/my").then(norm).catch(function () { return []; }),
                xhrJson("GET", API + "/share/list/to/me").then(norm).catch(function () { return []; })
            ]).then(function (r) {
                var seen = {}, out = [];
                r[0].concat(r[1]).forEach(function (s) {
                    if (!s || !s.id || seen[s.id]) return;
                    if (s.fileType !== "folder") return;                      // 共享区 = 文件夹
                    if (!(s.shareOrgList && s.shareOrgList.length)) return;   // 组织级共享
                    seen[s.id] = 1; out.push(s);
                });
                out.sort(function (a, b) { return String(a.name || "").localeCompare(String(b.name || "")); });
                self.state.counts.area = out.length;
                return out;
            });
        },

        /* 递归估算文件夹已用容量（owner 视角；非本人文件夹会低估） */
        calcFolderSize: function (folderId, depth) {
            var self = this;
            depth = depth || 0;
            if (depth > 5) return Promise.resolve(0);
            var pAtt = xhrJson("GET", API + "/attachment2/list/folder/" + encodeURIComponent(folderId))
                .then(function (d) {
                    var s = 0; ((d && d.data) || []).forEach(function (f) { s += Number(f.length) || 0; });
                    return s;
                }).catch(function () { return 0; });
            var pSub = xhrJson("GET", API + "/folder2/list/" + encodeURIComponent(folderId))
                .then(function (d) {
                    var subs = (d && d.data) || [];
                    return Promise.all(subs.map(function (sf) { return self.calcFolderSize(sf.id, depth + 1); }))
                        .then(function (a) { return a.reduce(function (x, y) { return x + y; }, 0); });
                }).catch(function () { return 0; });
            return Promise.all([pAtt, pSub]).then(function (r) { return r[0] + r[1]; });
        },

        /* 共享区列表（管理模式）/ 共享区文件入口（浏览模式） */
        adminAreas: function () {
            var self = this;
            this.loading();
            return this.loadAreas().then(function (list) { self.renderAreaTable(list, "mgr"); });
        },

        adminAreaFiles: function () {
            var self = this;
            this.loading();
            if (this.state.areaId && this.state.areaShare) { return this.renderAreaBrowse(); }
            return this.loadAreas().then(function (list) { self.renderAreaTable(list, "file"); });
        },

        renderAreaTable: function (list, mode) {
            var self = this;
            var body = this.els.body;
            body.innerHTML = "";
            if (!list.length) {
                body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">🗂</span>暂无共享工作区' +
                    "<br><span style='font-size:12px;color:#c3c8d0'>点击上方「新建共享区」创建，创建后会以组织级共享对所有成员可见</span></div></div>";
                return;
            }
            var p = el("div", "drive-panel");
            var h = el("div", "drive-head");
            h.innerHTML = '<div class="drive-col-name">' + esc(t("name", "名称")) + "</div>" +
                '<div class="drive-col-time">' + esc(t("updateTime", "更新时间")) + "</div>" +
                '<div class="drive-col-size">' + esc(t("usedSize", "已用容量")) + "</div>" +
                '<div class="drive-col-owner">' + esc(t("creator", "创建者")) + "</div>" +
                '<div class="drive-col-state">' + esc(t("status", "状态")) + "</div>" +
                '<div class="drive-col-op">' + esc(t("operation", "操作")) + "</div>";
            p.appendChild(h);

            list.forEach(function (s) {
                var expired = s.validTime && (new Date(String(s.validTime).replace(/-/g, "/")).getTime() < Date.now());
                var row = el("div", "drive-row");
                row.innerHTML =
                    '<div class="drive-col-name is-folder">' +
                    '  <img class="drive-ficon" src="' + ICON_BASE + 'folder.png">' +
                    '  <span class="drive-fname" title="' + esc(s.name) + '">' + esc(s.name) + "</span>" +
                    "</div>" +
                    '<div class="drive-col-time">' + esc(fmtTime(s.lastUpdateTime || s.updateTime || s.createTime)) + "</div>" +
                    '<div class="drive-col-size" data-size="1">…</div>' +
                    '<div class="drive-col-owner">' + esc(String(s.person || "").split("@")[0]) + "</div>" +
                    '<div class="drive-col-state">' + (expired ? '<span class="drive-tag warn">已过期</span>' : '<span class="drive-tag">正常</span>') + "</div>" +
                    '<div class="drive-col-op"></div>';

                row.querySelector(".drive-col-name").addEventListener("click", function () { self.enterArea(s); });

                var ops = row.querySelector(".drive-col-op");
                if (s.fileType === "folder") {
                    ops.appendChild(self.op(t("browse", "浏览文件"), function () { self.enterArea(s); }));
                }
                if (mode === "mgr") {
                    if (self.state.me && s.person === self.state.me.dn) {
                        ops.appendChild(self.op(t("unshare", "取消共享"), function () { self.removeArea(s); }, "danger"));
                    }
                }
                p.appendChild(row);

                /* 异步补算已用容量 */
                var cell = row.querySelector('[data-size="1"]');
                self.calcFolderSize(s.fileId).then(function (bytes) {
                    if (cell && cell.parentNode) { cell.textContent = fmtSize(bytes); }
                });
            });
            body.appendChild(p);
        },

        enterArea: function (s) {
            this.state.areaShare = s;
            this.state.areaId = s.fileId;
            this.state.areaPath = [];
            this.state.areaCur = s.fileId;
            this.state.adminSub = "areafile";
            this.renderNav();
            this.renderToolbar();
            this.refresh();
        },

        /* 打开共享文件夹：企业文件 / 我的分享 / 后台管理共用同一套 share 浏览接口
           （share/list/folder/share/{sid}/folder/{fid} 与 share/list/att/...，对分享者本人同样有效） */
        openSharedFolder: function (s) {
            this.state.areaShare = s;
            this.state.areaId = s.fileId;
            this.state.areaPath = [];
            this.state.areaCur = s.fileId;
            this.renderToolbar();
            this.refresh();
        },

        closeSharedFolder: function () {
            this.state.areaShare = null;
            this.state.areaId = null;
            this.state.areaPath = [];
            this.state.areaCur = null;
            this.renderToolbar();
            this.refresh();
        },

        enterAreaFolder: function (id, name, pathIndex) {
            if (id === null) { this.state.areaPath = []; }
            else if (typeof pathIndex === "number") {
                this.state.areaPath = this.state.areaPath.slice(0, pathIndex + 1);
            } else {
                this.state.areaPath = this.state.areaPath.concat([{ id: id, name: name }]);
            }
            var cur = this.state.areaPath.length ? this.state.areaPath[this.state.areaPath.length - 1].id : this.state.areaId;
            this.state.areaCur = cur;
            this.renderToolbar();
            this.renderAreaBrowse();
        },

        /* 共享区文件浏览：走 share 专用浏览接口，尊重共享范围 */
        renderAreaBrowse: function () {
            var self = this;
            var s = this.state.areaShare;
            if (!s) { return this.adminAreaFiles(); }
            var body = this.els.body;
            body.innerHTML = '<div class="drive-loading">' + esc(t("loading", "加载中…")) + "</div>";
            var folderId = this.state.areaPath.length ? this.state.areaPath[this.state.areaPath.length - 1].id : this.state.areaId;
            this.state.areaCur = folderId;

            var pF = xhrJson("GET", API + "/share/list/folder/share/" + encodeURIComponent(s.id) + "/folder/" + encodeURIComponent(folderId) + "/")
                .then(function (d) { return (d && d.data) || []; }).catch(function () { return []; });
            var pA = xhrJson("GET", API + "/share/list/att/share/" + encodeURIComponent(s.id) + "/folder/" + encodeURIComponent(folderId) + "/")
                .then(function (d) { return (d && d.data) || []; }).catch(function () { return []; });

            return Promise.all([pF, pA]).then(function (r) {
                var folders = r[0], files = r[1];
                body.innerHTML = "";
                if (!folders.length && !files.length) {
                    body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                        '<span class="drive-empty-ico">📂</span>该共享区暂无可浏览内容</div></div>';
                    return;
                }
                var p = el("div", "drive-panel");
                p.appendChild(self.headRow());
                folders.forEach(function (f) {
                    var row = el("div", "drive-row");
                    row.innerHTML =
                        '<div class="drive-col-name is-folder">' +
                        '  <img class="drive-ficon" src="' + ICON_BASE + 'folder.png">' +
                        '  <span class="drive-fname" title="' + esc(f.name) + '">' + esc(f.name) + "</span>" +
                        "</div>" +
                        '<div class="drive-col-size">-</div>' +
                        '<div class="drive-col-time">' + esc(fmtTime(f.updateTime || f.createTime)) + "</div>" +
                        '<div class="drive-col-op"></div>';
                    row.querySelector(".drive-col-name").addEventListener("click", function () {
                        self.enterAreaFolder(f.id, f.name);
                    });
                    var fops = row.querySelector(".drive-col-op");
                    fops.appendChild(self.op(t("browse", "进入"), function () { self.enterAreaFolder(f.id, f.name); }));
                    fops.appendChild(self.op(t("zip", "打包下载"), function () { self.downloadFolder(f.id); }));
                    p.appendChild(row);
                });
                files.forEach(function (f) {
                    var ext = f.extension || extOf(f.name);
                    var row = el("div", "drive-row");
                    row.innerHTML =
                        '<div class="drive-col-name">' +
                        '  <img class="drive-ficon" src="' + iconUrl(ext) + '">' +
                        '  <span class="drive-fname" title="' + esc(f.name) + '">' + esc(f.name) + "</span>" +
                        "</div>" +
                        '<div class="drive-col-size">' + esc(fmtSize(f.length)) + "</div>" +
                        '<div class="drive-col-time">' + esc(fmtTime(f.updateTime || f.createTime)) + "</div>" +
                        '<div class="drive-col-op"></div>';
                    var ops = row.querySelector(".drive-col-op");
                    /* 共享区内下载/预览统一走 share 通道，非本人共享项同样可读 */
                    if (previewKind(ext)) {
                        ops.appendChild(self.op(t("preview", "预览"), function () {
                            self.preview({
                                url: self.shareFileUrl(s.id, f.id),
                                name: f.name, ext: ext
                            });
                        }));
                    }
                    ops.appendChild(self.op(t("download", "下载"), function () {
                        self.triggerDownload(self.shareFileUrl(s.id, f.id));
                    }));
                    if (self.isAreaMine()) {
                        ops.appendChild(self.op(t("delete", "删除"), function () {
                            self.remove("attachment", f.id, f.name);
                        }, "danger"));
                    }
                    p.appendChild(row);
                });
                body.appendChild(p);
            });
        },

        promptNewArea: function () {
            var self = this;
            if (!this.canCreateShare()) {
                this.toast("你不在「共享区可创建权限名单」内，无法新建共享区。" + this.creatorHint(), true);
                return;
            }
            this.dialog(t("newArea", "新建共享区"), '<input type="text" placeholder="' + esc(t("inputFolderName", "请输入共享区名称，如：综合部文件")) + '">',
                function (value, close) {
                    var name = (value || "").trim();
                    if (!name) { self.toast("名称不能为空", true); return; }
                    if (!self.state.orgUnique) { self.toast("未能获取组织信息，无法创建共享区", true); return; }
                    xhrJson("POST", API + "/folder2", { json: { name: name, superior: "" } }).then(function (d) {
                        var fid = d && d.data && d.data.id;
                        if (!fid) { throw { message: "创建文件夹失败" }; }
                        return xhrJson("POST", API + "/share", {
                            json: {
                                fileId: fid, name: name, shareType: "member",
                                shareUserList: [], shareOrgList: [self.state.orgUnique], shareGroupList: []
                            }
                        });
                    }).then(function () {
                        close();
                        self.toast("共享区已创建，并对全体成员共享");
                        self.refresh();
                    }).catch(function (e) { self.toast((e && e.message) || "创建失败", true); });
                });
        },

        promptAreaFolder: function () {
            var self = this;
            var sup = this.state.areaCur || this.state.areaId;
            if (!sup) { this.toast("请先进入共享区", true); return; }
            this.dialog(t("mkdir", "新建文件夹"), '<input type="text" placeholder="' + esc(t("inputFolderName", "请输入文件夹名称")) + '">',
                function (value, close) {
                    var name = (value || "").trim();
                    if (!name) { self.toast("名称不能为空", true); return; }
                    xhrJson("POST", API + "/folder2", { json: { name: name, superior: sup } }).then(function () {
                        close(); self.toast("文件夹已创建");
                        if (self.state.adminSub === "areafile") { self.renderAreaBrowse(); } else { self.loadPersonal(); }
                    }).catch(function (e) { self.toast((e && e.message) || "创建失败", true); });
                });
        },

        removeArea: function (s) {
            var self = this;
            this.confirm("取消共享后，该共享区将不再对所有成员可见（文件夹本身保留在「个人文件」）。确定继续？", function (close) {
                xhrJson("DELETE", API + "/share/" + encodeURIComponent(s.id)).then(function () {
                    close(); self.toast("已取消共享"); self.refresh();
                }).catch(function (e) { self.toast((e && e.message) || "操作失败", true); });
            });
        },

        /* ================================================================
           成员容量 / 用户总览 —— 管理视角的公共数据层
           ----------------------------------------------------------------
           为什么不能直接用 attachment2/user/capacity？
             该接口不带参数只返回**当前登录人**的容量；「谁用了多少」必须逐人查。
           取证（源码 describe/sources/.../jaxrs/attachment2/ActionUseCapacity.java）：
             String queryPerson = effectivePerson.getDistinguishedName();
             if (business.controlAble(effectivePerson) && StringUtils.isNotBlank(person))
                 queryPerson = person;                       // 管理员才认 person 参数
             wo.setValue(business.attachment2().getUseCapacity(queryPerson));
           ⇒ GET attachment2/user/capacity?person=<人员distinguishedName>
             非管理员即使传了 person 也只会拿到自己的值（服务端强制回落），不存在越权。
           实测对照：上传 1MB 后 自己=1048576、?person=上传者dN=1048576、?person=他人dN=0。

           人员的两个来源（交叉合并，避免漏人）：
             ① 组织路径：unit/list/control/top（我管辖的顶层单位）
                        → unit/list/{dn}/sub/nested（含下级）
                        → identity/list/unit/{dn}（身份：personUuid + 姓名 + unitName）
             ② 名册路径：person/list/{me}/prev|next/{count}（人员对象：dN + 状态 + 最近登录）
           两者用 person 的 UUID(id) 关联，得到「人 + 部门 + 状态 + 容量」。
           ================================================================ */

        /* 我管辖的顶层单位（非组织管理员会收敛到自己所属顶层单位） */
        loadScope: function () {
            var self = this;
            return Promise.all([
                xhrJson("GET", ORG_API + "/unit/list/control/top").catch(function () { return null; }),
                xhrJson("GET", ORG_API + "/unit/list/top").catch(function () { return null; })
            ]).then(function (r) {
                self.state.scopeTop = ((r[0] && r[0].data) || []);
                self.state.orgTop = ((r[1] && r[1].data) || []);
                self.state.scopeAll = !!(self.state.orgTop.length &&
                    self.state.scopeTop.length === self.state.orgTop.length);
            });
        },

        /* 权限来源（与服务端 controlAble 同源）：系统管理员 or FileManager 角色成员 */
        loadAuthSource: function () {
            var self = this;
            return Promise.all([
                xhrJson("GET", API + "/config/is/file/manager").catch(function () { return null; }),
                xhrJson("GET", AUTH_API).catch(function () { return null; }),
                xhrJson("GET", ORG_API + "/person/list/role/" + encodeURIComponent(FILE_MANAGER_ROLE))
                    .catch(function () { return null; })
            ]).then(function (r) {
                var roles = ((r[1] && r[1].data && r[1].data.roleList) || []);
                var names = roles.map(function (x) { return String(x).split("@")[0]; });
                self.state.authInfo = {
                    can: !!(r[0] && r[0].data && r[0].data.value),
                    isSysManager: names.indexOf("Manager") >= 0 ||
                        (self.state.me && self.state.me.name === "系统管理员"),
                    hasFileRole: roles.indexOf(FILE_MANAGER_ROLE) >= 0 ||
                        names.indexOf("FileManager") >= 0,
                    roles: names,
                    holders: ((r[2] && r[2].data) || []).map(function (p) { return p.name; })
                };
            });
        },

        /* 拉取「权限范围内每个人」的容量与使用情况（结果缓存在 state.members） */
        loadMembers: function (force) {
            var self = this;
            if (this.state.memberBusy) { return Promise.resolve(this.state.members); }
            if (this.state.members && !force) { return Promise.resolve(this.state.members); }
            this.state.memberBusy = true;

            var meDn = (this.state.me && this.state.me.dn) || "";
            function norm(d) { return (d && d.data) || []; }
            function fail() { return []; }

            var pAllTop = xhrJson("GET", ORG_API + "/unit/list/top").then(norm).catch(fail);
            var pScopeTop = xhrJson("GET", ORG_API + "/unit/list/control/top").then(norm).catch(fail);
            var pMePrev = meDn
                ? xhrJson("GET", ORG_API + "/person/list/" + encodeURIComponent(meDn) + "/prev/500").then(norm).catch(fail)
                : Promise.resolve([]);
            var pMeNext = meDn
                ? xhrJson("GET", ORG_API + "/person/list/" + encodeURIComponent(meDn) + "/next/500").then(norm).catch(fail)
                : Promise.resolve([]);
            var pConfig = xhrJson("GET", API + "/config/system/config").catch(function () { return null; });
            var pShares = xhrJson("GET", API + "/share/list").then(norm).catch(fail);

            /* —— ① 组织路径：管辖顶层单位 → 含下级的全部单位 → 各单位下的身份 —— */
            var pOrgRows = pScopeTop.then(function (tops) {
                if (!tops.length) { return []; }
                var pSubs = tops.map(function (u) {
                    return xhrJson("GET", ORG_API + "/unit/list/" + encodeURIComponent(u.distinguishedName) + "/sub/nested")
                        .then(norm).catch(fail);
                });
                return Promise.all(pSubs).then(function (lists) {
                    var units = [], seenU = {};
                    function pushU(u) {
                        if (!u || !u.distinguishedName || seenU[u.distinguishedName]) return;
                        seenU[u.distinguishedName] = 1; units.push(u);
                    }
                    tops.forEach(pushU);
                    lists.forEach(function (ls) { ls.forEach(pushU); });
                    var pId = units.map(function (u) {
                        return xhrJson("GET", ORG_API + "/identity/list/unit/" + encodeURIComponent(u.distinguishedName))
                            .then(norm).catch(fail);
                    });
                    return Promise.all(pId).then(function (idLists) {
                        var out = [];
                        idLists.forEach(function (ls) {
                            ls.forEach(function (it) {
                                out.push({
                                    uuid: it.person, name: it.name, unitName: it.unitLevelName || it.unitName || ""
                                });
                            });
                        });
                        return out;
                    });
                });
            });

            return Promise.all([pAllTop, pScopeTop, pMePrev, pMeNext, pOrgRows, pConfig, pShares])
                .then(function (r) {
                    var allTop = r[0], scopeTop = r[1], prev = r[2], next = r[3],
                        orgRows = r[4], cfgWrap = r[5], allShares = r[6];

                    /* —— ② 名册路径：按 dN / UUID 建档 —— */
                    var byDn = {}, byUuid = {};
                    function putPerson(p) {
                        if (!p || !p.distinguishedName) return;
                        var rec = byDn[p.distinguishedName] || {
                            dn: p.distinguishedName, name: p.name || p.distinguishedName.split("@")[0],
                            uuid: p.id || "", unitName: "", status: p.status, lastLogin: p.lastLoginTime || "",
                            used: 0, shared: 0
                        };
                        if (p.id && !rec.uuid) { rec.uuid = p.id; }
                        if (p.lastLoginTime) { rec.lastLogin = p.lastLoginTime; }
                        if (p.status !== undefined) { rec.status = p.status; }
                        byDn[rec.dn] = rec;
                        if (rec.uuid) { byUuid[rec.uuid] = rec; }
                    }
                    prev.forEach(putPerson);
                    next.forEach(putPerson);
                    /* 自己一定在名单里 */
                    if (meDn) { putPerson({ distinguishedName: meDn, name: (self.state.me || {}).name, id: "" }); }

                    /* —— 合并部门归属（identity.person 是 UUID） —— */
                    orgRows.forEach(function (it) {
                        var rec = byUuid[it.uuid];
                        if (rec) { if (!rec.unitName) { rec.unitName = it.unitName; } return; }
                        /* 名册里没有该 UUID（例如人员被隐藏），以 identity 为准补一行 */
                        /* 用姓名做弱匹配，匹配不到就先挂 UUID 占位 */
                        for (var k in byDn) {
                            if (byDn[k].name === it.name && !byDn[k].unitName) {
                                byDn[k].unitName = it.unitName; byUuid[it.uuid] = byDn[k]; return;
                            }
                        }
                    });

                    var rows = [];
                    for (var k2 in byDn) { rows.push(byDn[k2]); }
                    if (meDn && !byDn[meDn] && self.state.me) {
                        rows.push({ dn: meDn, name: self.state.me.name, uuid: "", unitName: self.state.me.unitName,
                            status: "0", lastLogin: "", used: 0, shared: 0 });
                    }

                    /* —— 共享数（谁共享了多少） —— */
                    allShares.forEach(function (s) {
                        var r2 = byDn[s.person] || byUuid[s.person];
                        if (r2) { r2.shared = (r2.shared || 0) + 1; }
                    });

                    /* —— ③ 逐人容量：并发 6，避免打爆服务端 —— */
                    var i = 0;
                    function worker() {
                        if (i >= rows.length) { return Promise.resolve(); }
                        var row = rows[i++];
                        return xhrJson("GET", API + "/attachment2/user/capacity?person=" + encodeURIComponent(row.dn))
                            .then(function (d) { row.used = Number((d && d.data && d.data.value) || 0); })
                            .catch(function () { row.used = -1; })
                            .then(worker);
                    }
                    var lanes = [];
                    for (var w = 0; w < 6; w++) { lanes.push(worker()); }

                    return Promise.all(lanes).then(function () {
                        var cfg = (cfgWrap && cfgWrap.data) || {};
                        var quota = Number(cfg.capacity) || 0;
                        var total = 0;
                        rows.forEach(function (x) { if (x.used > 0) { total += x.used; } });
                        var scopeNames = scopeTop.map(function (u) { return u.name; });
                        self.state.members = {
                            rows: rows,
                            quota: quota,
                            total: total,
                            scopeNames: scopeNames,
                            scopeAll: !!(allTop.length && scopeNames.length === allTop.length),
                            allShares: allShares,
                            ts: new Date()
                        };
                        self.state.memberBusy = false;
                        return self.state.members;
                    });
                })
                .catch(function (e) {
                    self.state.memberBusy = false;
                    self.toast("读取成员数据失败：" + ((e && e.message) || e), true);
                    return self.state.members;
                });
        },

        statusText: function (s) {
            if (s === "0" || s === undefined || s === null || s === "") return "正常";
            if (s === "1") return "锁定";
            if (s === "2") return "禁用";
            return String(s);
        },

        /* 权限横幅：把「后台管理为什么对我可见」讲清楚（与角色对齐） */
        adminBanner: function () {
            var a = this.state.authInfo || {};
            var m = this.state.members || {};
            var who = a.isSysManager ? "系统管理员" : (a.hasFileRole ? "FileManager 角色" : "文件管理权限");
            var scope = m.scopeAll ? "全部组织（全域）"
                : (m.scopeNames && m.scopeNames.length ? m.scopeNames.join("、") : "未解析到管辖范围");
            var holders = (a.holders && a.holders.length) ? a.holders.join("、") : "（当前无人持有，仅系统管理员可用）";
            return '<div class="drive-admin-banner">' +
                '<div class="drive-ab-row"><span class="drive-ab-k">权限来源</span>' +
                '<span class="drive-ab-v">' + esc(who) + "</span>" +
                '<span class="drive-ab-tip">判定同服务端 Business.controlAble（系统管理员 或 ' + esc(FILE_MANAGER_ROLE.split("@")[0]) + " 角色）</span></div>" +
                '<div class="drive-ab-row"><span class="drive-ab-k">管辖范围</span>' +
                '<span class="drive-ab-v">' + esc(scope) + "</span></div>" +
                '<div class="drive-ab-row"><span class="drive-ab-k">授权名单</span>' +
                '<span class="drive-ab-v">' + esc(holders) + "</span>" +
                '<span class="drive-ab-tip">给账号加上该角色即获得后台管理</span></div>' +
                "</div>";
        },

        /* 成员表格（两页共用渲染） */
        memberTable: function (withShare) {
            var self = this;
            var m = this.state.members || {};
            var quota = Number(m.quota) || 0;
            var q = String(this.state.memberQuery || "").trim().toLowerCase();
            var rows = (m.rows || []).slice();

            if (q) {
                rows = rows.filter(function (r) {
                    return String(r.name).toLowerCase().indexOf(q) >= 0 ||
                        String(r.unitName).toLowerCase().indexOf(q) >= 0 ||
                        String(r.dn).toLowerCase().indexOf(q) >= 0;
                });
            }
            var sort = this.state.memberSort;
            rows.sort(function (a, b) {
                if (sort === "name") { return String(a.name).localeCompare(String(b.name), "zh"); }
                if (sort === "unit") { return String(a.unitName).localeCompare(String(b.unitName), "zh"); }
                if (sort === "login") { return String(b.lastLogin).localeCompare(String(a.lastLogin)); }
                return (b.used > 0 ? b.used : 0) - (a.used > 0 ? a.used : 0);
            });

            var max = 1;
            rows.forEach(function (r) { if (r.used > max) { max = r.used; } });

            var head = '<div class="drive-mt-head">' +
                "<span class='drive-mt-c1'>成员</span>" +
                "<span class='drive-mt-c2'>所属部门</span>" +
                "<span class='drive-mt-c3'>已用容量</span>" +
                "<span class='drive-mt-c4'>占用比例</span>" +
                (quota > 0 ? "<span class='drive-mt-c5'>配额占比</span>" : "") +
                "<span class='drive-mt-c6'>状态</span>" +
                "<span class='drive-mt-c7'>最近登录</span>" +
                (withShare ? "<span class='drive-mt-c8'>共享</span>" : "") +
                "</div>";

            var body = rows.map(function (r) {
                var pct = Math.round((r.used > 0 ? r.used : 0) / max * 100);
                var qpct = quota > 0 ? Math.round((r.used > 0 ? r.used : 0) / quota * 100) : 0;
                var over = quota > 0 && r.used > quota * 0.8;
                var bar = r.used < 0
                    ? "<span class='drive-mt-na'>无权查看</span>"
                    : '<span class="drive-cap-track drive-mt-track"><span class="drive-cap-fill' +
                      (over ? " over" : "") + '" style="width:' + Math.max(pct, r.used > 0 ? 2 : 0) + '%"></span></span>';
                return '<div class="drive-mt-row">' +
                    "<span class='drive-mt-c1'><span class='drive-mt-ava'>" + esc((r.name || "?").substring(0, 1)) + "</span>" +
                    "<span class='drive-mt-name' title='" + esc(r.dn) + "'>" + esc(r.name) + "</span></span>" +
                    "<span class='drive-mt-c2'>" + esc(r.unitName || "—") + "</span>" +
                    "<span class='drive-mt-c3'>" + (r.used < 0 ? "—" : esc(fmtSize(r.used))) + "</span>" +
                    "<span class='drive-mt-c4'>" + bar + "</span>" +
                    (quota > 0 ? "<span class='drive-mt-c5" + (over ? " over" : "") + "'>" + qpct + "%</span>" : "") +
                    "<span class='drive-mt-c6'>" + esc(self.statusText(r.status)) + "</span>" +
                    "<span class='drive-mt-c7'>" + esc(r.lastLogin || "—") + "</span>" +
                    (withShare ? "<span class='drive-mt-c8'>" + (r.shared || 0) + "</span>" : "") +
                    "</div>";
            }).join("");

            if (!rows.length) {
                body = '<div class="drive-empty">没有匹配的成员</div>';
            }
            return '<div class="drive-mt">' + head + body + "</div>";
        },

        /* —— 成员容量：权限范围内每个人的容量统计 —— */
        adminCapacity: function () {
            var self = this;
            if (!this.state.members) {
                this.loading("正在统计成员容量 ...");
                return this.loadMembers(true).then(function () { self.adminCapacity(); });
            }
            var m = this.state.members;
            var rows = m.rows || [];
            var quota = Number(m.quota) || 0;
            var n = rows.length;
            var used = m.total || 0;
            var avg = n ? Math.round(used / n) : 0;
            var over = rows.filter(function (r) { return quota > 0 && r.used > quota * 0.8; });
            var top = rows.slice().sort(function (a, b) { return (b.used > 0 ? b.used : 0) - (a.used > 0 ? a.used : 0); })[0];
            var noAuth = rows.filter(function (r) { return r.used < 0; }).length;

            var html = this.adminBanner() +
                '<div class="drive-cards">' +
                '  <div class="drive-card"><div class="drive-card-label">管辖成员</div>' +
                '    <div class="drive-card-value">' + n + "</div>" +
                '    <div class="drive-card-sub">组织接口 · 权限范围内</div></div>' +
                '  <div class="drive-card"><div class="drive-card-label">已用容量合计</div>' +
                '    <div class="drive-card-value">' + esc(fmtSize(used)) + "</div>" +
                '    <div class="drive-card-sub">逐人 capacity 求和</div></div>' +
                '  <div class="drive-card"><div class="drive-card-label">人均占用</div>' +
                '    <div class="drive-card-value">' + esc(fmtSize(avg)) + "</div>" +
                '    <div class="drive-card-sub">合计 / 人数</div></div>' +
                '  <div class="drive-card"><div class="drive-card-label">容量上限</div>' +
                '    <div class="drive-card-value small">' + (quota > 0 ? esc(fmtSize(quota)) : "不限制") + "</div>" +
                '    <div class="drive-card-sub">对每个用户生效</div></div>' +
                '  <div class="drive-card' + (over.length ? " warn" : "") + '"><div class="drive-card-label">超限预警（&gt;80%）</div>' +
                '    <div class="drive-card-value">' + (quota > 0 ? over.length : "—") + "</div>" +
                '    <div class="drive-card-sub">' + (quota > 0 ? "需关注的成员数" : "未设上限") + "</div></div>" +
                '  <div class="drive-card"><div class="drive-card-label">占用最多</div>' +
                '    <div class="drive-card-value small">' + (top && top.used > 0 ? esc(top.name) : "—") + "</div>" +
                '    <div class="drive-card-sub">' + (top && top.used > 0 ? esc(fmtSize(top.used)) : "暂无数据") + "</div></div>" +
                "</div>" +
                (noAuth
                    ? '<div class="drive-note warn">有 ' + noAuth + " 位成员的容量返回「无权查看」——" +
                      "说明当前账号在该范围内不具备读取他人容量的服务端授权（判定依据 Business.controlAble）。</div>"
                    : "") +
                '<div class="drive-toolrow">' +
                '  <input class="drive-input drive-msearch" placeholder="搜索成员 / 部门" value="' + esc(this.state.memberQuery) + '" data-r="mquery">' +
                '  <select class="drive-select" data-r="msort">' +
                '    <option value="used"' + (this.state.memberSort === "used" ? " selected" : "") + ">按占用容量</option>" +
                '    <option value="name"' + (this.state.memberSort === "name" ? " selected" : "") + ">按姓名</option>" +
                '    <option value="unit"' + (this.state.memberSort === "unit" ? " selected" : "") + ">按部门</option>" +
                '    <option value="login"' + (this.state.memberSort === "login" ? " selected" : "") + ">按最近登录</option>" +
                "  </select>" +
                '  <span class="drive-toolrow-hint">共 ' + rows.length + " 人 · 更新于 " +
                esc(String(m.ts.getHours()) + ":" + ("0" + m.ts.getMinutes()).slice(-2)) + "</span>" +
                '  <span class="spacer"></span>' +
                '  <button class="drive-btn" data-r="mrefresh">重新统计</button>' +
                "</div>" +
                this.memberTable(false);

            this.els.body.innerHTML = html;
            this.bindMemberTools();
            this.els.foot.innerHTML = "<span>统计口径：每个人 VALID 状态附件的字节合计（不含回收站）</span>" +
                '<span class="spacer"></span><span>数据源：attachment2/user/capacity?person=&lt;用户&gt;</span>';
            /* ★ 必须返回 Promise：refresh() 会 p.then(...)，命中缓存时若返回 undefined
               就会抛 "Cannot read properties of undefined (reading 'then')"（已实测踩到） */
            return Promise.resolve();
        },

        bindMemberTools: function () {
            var self = this;
            var q = this.els.body.querySelector('[data-r="mquery"]');
            if (q) {
                q.addEventListener("input", function () {
                    self.state.memberQuery = q.value;
                    /* 只重绘表格，避免每次按键都重新请求 */
                    var box = self.els.body.querySelector(".drive-mt");
                    if (box) {
                        var tmp = document.createElement("div");
                        tmp.innerHTML = self.memberTable(self.state.sec === "admin" && self.state.adminSub === "users");
                        var fresh = tmp.querySelector(".drive-mt");
                        if (fresh) { box.parentNode.replaceChild(fresh, box); }
                    }
                });
            }
            var s = this.els.body.querySelector('[data-r="msort"]');
            if (s) {
                s.addEventListener("change", function () {
                    self.state.memberSort = s.value;
                    var box = self.els.body.querySelector(".drive-mt");
                    if (box) {
                        var tmp = document.createElement("div");
                        tmp.innerHTML = self.memberTable(self.state.sec === "admin" && self.state.adminSub === "users");
                        var fresh = tmp.querySelector(".drive-mt");
                        if (fresh) { box.parentNode.replaceChild(fresh, box); }
                    }
                });
            }
            var rf = this.els.body.querySelector('[data-r="mrefresh"]');
            if (rf) {
                rf.addEventListener("click", function () {
                    self.state.members = null;
                    self.loading("正在重新统计 ...");
                    self.loadMembers(true).then(function () { self.loadAdmin(self.state.adminSub); });
                });
            }
        },

        /* —— 用户总览：所有用户的情况（容量 + 状态 + 最近登录 + 共享） —— */
        adminUsers: function () {
            var self = this;
            if (!this.state.members) {
                this.loading("正在汇总用户情况 ...");
                return this.loadMembers(true).then(function () { self.adminUsers(); });
            }
            var m = this.state.members;
            var rows = m.rows || [];
            var shares = m.allShares || [];
            var byPerson = {};
            shares.forEach(function (s) {
                var k = s.name || s.id;
                byPerson[s.person] = byPerson[s.person] || [];
                byPerson[s.person].push(s);
            });
            var locked = rows.filter(function (r) { return r.status === "1" || r.status === "2"; }).length;
            var neverLogin = rows.filter(function (r) { return !r.lastLogin; }).length;
            var withFile = rows.filter(function (r) { return r.used > 0; }).length;

            var shareHtml = shares.length
                ? '<div class="drive-mt">' +
                  '<div class="drive-mt-head"><span class="drive-mt-c1">共享名</span>' +
                  "<span class='drive-mt-c2'>属性</span><span class='drive-mt-c3'>共享范围</span>" +
                  "<span class='drive-mt-c4'>共享给</span></div>" +
                  shares.map(function (s) {
                      var scope = (s.shareOrgList && s.shareOrgList.length) ? "组织（全员）"
                          : (s.shareUserList && s.shareUserList.length) ? "指定人员" : "其他";
                      var to = (s.shareOrgList || []).concat(s.shareUserList || []).map(function (x) {
                          return String(x).split("@")[0];
                      }).join("、") || "—";
                      return '<div class="drive-mt-row">' +
                          "<span class='drive-mt-c1'>" + esc(s.name || s.id) + "</span>" +
                          "<span class='drive-mt-c2'>" + esc(s.fileType === "folder" ? "文件夹" : "文件") + "</span>" +
                          "<span class='drive-mt-c3'>" + esc(scope) + "</span>" +
                          "<span class='drive-mt-c4'>" + esc(to.substring(0, 40)) + "</span>" +
                          "</div>";
                  }).join("") + "</div>"
                : '<div class="drive-empty">当前没有任何共享（share/list 返回 0 条）</div>';

            var html = this.adminBanner() +
                '<div class="drive-cards">' +
                '  <div class="drive-card"><div class="drive-card-label">用户总数</div>' +
                '    <div class="drive-card-value">' + rows.length + "</div>" +
                '    <div class="drive-card-sub">其中 ' + neverLogin + " 人从未登录</div></div>" +
                '  <div class="drive-card"><div class="drive-card-label">有文件的用户</div>' +
                '    <div class="drive-card-value">' + withFile + "</div>" +
                '    <div class="drive-card-sub">已用容量 &gt; 0</div></div>' +
                '  <div class="drive-card"><div class="drive-card-label">共享总数</div>' +
                '    <div class="drive-card-value">' + shares.length + "</div>" +
                '    <div class="drive-card-sub">share/list</div></div>' +
                '  <div class="drive-card' + (locked ? " warn" : "") + '"><div class="drive-card-label">锁定 / 禁用</div>' +
                '    <div class="drive-card-value">' + locked + "</div>" +
                '    <div class="drive-card-sub">需处理的账号</div></div>' +
                "</div>" +
                '<div class="drive-toolrow">' +
                '  <input class="drive-input drive-msearch" placeholder="搜索成员 / 部门" value="' + esc(this.state.memberQuery) + '" data-r="mquery">' +
                '  <select class="drive-select" data-r="msort">' +
                '    <option value="used"' + (this.state.memberSort === "used" ? " selected" : "") + ">按占用容量</option>" +
                '    <option value="name"' + (this.state.memberSort === "name" ? " selected" : "") + ">按姓名</option>" +
                '    <option value="unit"' + (this.state.memberSort === "unit" ? " selected" : "") + ">按部门</option>" +
                '    <option value="login"' + (this.state.memberSort === "login" ? " selected" : "") + ">按最近登录</option>" +
                "  </select>" +
                '  <span class="drive-toolrow-hint">共 ' + rows.length + " 人</span>" +
                '  <span class="spacer"></span>' +
                '  <button class="drive-btn" data-r="mrefresh">重新汇总</button>' +
                "</div>" +
                this.memberTable(true) +
                '<div class="drive-section-title">全部共享</div>' +
                shareHtml;

            this.els.body.innerHTML = html;
            this.bindMemberTools();
            this.els.foot.innerHTML = "<span>用户情况 = 名册 + 逐人容量 + 账号状态 + 最近登录 + 共享数</span>" +
                '<span class="spacer"></span><span>数据源：x_organization_assemble_control + x_file_assemble_control</span>';
            return Promise.resolve();
        },

        /* —— 回收站（后台视角，复用真实 recycle 接口） —— */
        adminRecycle: function () {
            var self = this;
            this.loading();
            return xhrJson("GET", API + "/recycle/list").then(function (d) {
                var list = (d && d.data) || [];
                self.state.counts.recycle = list.length;
                self.renderRecycle(list);
            });
        },

        /* —— 设置：① 网盘策略（门户数据字典，本组件自有） ② 系统设置（服务端 FileConfig） —— */
        adminSetting: function () {
            var self = this;
            this.loading();
            this.initPermDraft();
            return xhrJson("GET", API + "/config/system/config").then(function (d) {
                var cfg = (d && d.data) || {};
                self.state.sysConfig = cfg;
                var props = cfg.properties || {};
                var inc = (props.fileTypeIncludes || []);
                var exc = (props.fileTypeExcludes || []);
                var dcfg = self.state.driveCfg || {};
                var html =
                    '<div class="drive-panel drive-setting">' +
                    '  <div class="drive-setting-title">网盘策略</div>' +
                    '  <div class="drive-setting-sub">本组件自有策略，保存在门户数据字典 driveSetting，全员生效</div>' +
                    self.formRow("共享区文件上传大小限制（MB）", "cfg-sharelimit",
                        String(dcfg.shareLimitMb || 0),
                        "仅对「共享区」上传生效；0 = 不限制。超限文件在开始上传前即被拦截并提示") +
                    '  <div class="drive-form-row">' +
                    '    <div class="drive-form-label">共享区可创建权限列表</div>' +
                    '    <div class="drive-form-field">' + self.permBoxHtml() +
                    '      <div class="drive-form-hint">留空 = 不限定（全员可创建共享区）。名单内的人员 / 角色才能在「个人文件」中共享到企业、或在后台新建共享区；' +
                    '不在此名单内的成员会收到明确提示。</div>' +
                    "    </div>" +
                    "  </div>" +
                    "</div>" +
                    '<div class="drive-panel drive-setting">' +
                    '  <div class="drive-setting-title">' + esc(t("systemSetting", "系统设置")) + "</div>" +
                    '  <div class="drive-setting-sub">服务端 x_file_assemble_control / FILE_CONFIG 真实字段</div>' +
                    self.formRow("只允许上传的文件后缀", "cfg-includes", inc.join(","), "留空表示不限制；多个后缀用英文逗号分隔") +
                    self.formRow("不允许上传的文件后缀", "cfg-excludes", exc.join(","), "优先级高于「只允许」；多个后缀用英文逗号分隔") +
                    self.formRow("回收站数据保留天数", "cfg-days", String(cfg.recycleDays || 15), "到期后由服务端自动清理") +
                    self.formRow("容量上限（MB）", "cfg-cap", (Number(cfg.capacity) > 0 ? String(Math.round(Number(cfg.capacity) / 1048576)) : "0"), "0 表示不限制（对所有用户生效）") +
                    '  <div class="drive-setting-note">' +
                    '    <b>以下为「企业网盘（Pan）」专有配置，本地社区版未安装 x_pan_assemble_control 模块，故不可用：</b><br>' +
                    '    libreoffice 安装目录 · 附件预览工具（onlyoffice / wps office / libreoffice / officeonline）·' +
                    ' onlyoffice 附件查看下载地址 · officeOnline 服务器 web 访问地址 · 与 libreoffice 连接端口<br>' +
                    '    <span class="drive-preview-note">「共享区可创建权限列表」「共享区文件上传大小限制」已由本组件在上表中本地实现。</span>' +
                    "  </div>" +
                    "</div>" +
                    '<div class="drive-panel" style="padding:14px 18px">' +
                    '  <button class="drive-btn primary" data-r="save">' + esc(t("save", "保存")) + "</button>" +
                    '  <button class="drive-btn" data-r="reset" style="margin-left:8px">' + esc(t("reset", "重置")) + "</button>" +
                    "</div>";
                self.els.body.innerHTML = html;
                self.els.body.querySelector('[data-r="save"]').addEventListener("click", function () { self.saveConfig(); });
                self.els.body.querySelector('[data-r="reset"]').addEventListener("click", function () { self.adminSetting(); });
                self.bindPermBox();
            }).catch(function (e) {
                self.els.body.innerHTML = '<div class="drive-panel"><div class="drive-empty">' +
                    '<span class="drive-empty-ico">⛔</span>' + esc((e && e.message) || "无权访问系统设置") + "</div></div>";
            });
        },

        /* ---- 可创建权限名单编辑器（人员 / 角色） ---- */
        initPermDraft: function () {
            var cfg = this.state.driveCfg || {};
            this.state.permDraft = {
                person: (cfg.creatorPersonList || []).map(function (dn) {
                    return { v: dn, n: String(dn).split("@")[0] };
                }),
                role: (cfg.creatorRoleList || []).map(function (u) {
                    return { v: u, n: String(u).split("@")[0] };
                })
            };
        },

        permBoxHtml: function () {
            var d = this.state.permDraft || { person: [], role: [] };
            function tags(arr, kind) {
                if (!arr.length) { return '<span class="drive-perm-empty">未添加</span>'; }
                return arr.map(function (x, i) {
                    return '<span class="drive-perm-tag" data-kind="' + kind + '" data-i="' + i + '">' +
                        esc(x.n) + '<b data-r="rm">×</b></span>';
                }).join("");
            }
            return '<div class="drive-perm">' +
                '<div class="drive-perm-row"><span class="drive-perm-k">人员</span>' +
                '<span class="drive-perm-list" data-list="person">' + tags(d.person, "person") + "</span></div>" +
                '<div class="drive-perm-row"><span class="drive-perm-k">角色</span>' +
                '<span class="drive-perm-list" data-list="role">' + tags(d.role, "role") + "</span></div>" +
                '<div class="drive-perm-add">' +
                '  <select data-r="kind"><option value="person">人员</option><option value="role">角色</option></select>' +
                '  <input data-r="kw" type="text" placeholder="输入姓名 / 拼音或角色名，回车搜索">' +
                '  <button class="drive-btn ghost" data-r="search">搜索</button>' +
                "</div>" +
                '<div class="drive-perm-results" data-r="results"></div>' +
                "</div>";
        },

        bindPermBox: function () {
            var self = this;
            var box = this.els.body.querySelector(".drive-perm");
            if (!box) { return; }
            var go = function () {
                var kk = box.querySelector('[data-r="kind"]');
                var ww = box.querySelector('[data-r="kw"]');
                self.searchPerm(kk ? kk.value : "person", ww ? ww.value : "");
            };
            box.addEventListener("click", function (e) {
                var t = e.target;
                if (t && t.getAttribute && t.getAttribute("data-r") === "rm") {
                    var tag = t.parentNode;
                    var kind = tag.getAttribute("data-kind");
                    self.state.permDraft[kind].splice(Number(tag.getAttribute("data-i")), 1);
                    self.refreshPermBox();
                    return;
                }
                if (t && t.getAttribute && t.getAttribute("data-r") === "search") { go(); return; }
                var add = t && t.getAttribute ? t.getAttribute("data-add") : null;
                if (add) {
                    var k = add, v = t.getAttribute("data-v"), n = t.getAttribute("data-n");
                    var arr = self.state.permDraft[k];
                    var dup = false;
                    for (var i = 0; i < arr.length; i++) { if (arr[i].v === v) { dup = true; } }
                    if (!dup) { arr.push({ v: v, n: n }); }
                    self.refreshPermBox();
                }
            });
            box.addEventListener("keydown", function (e) {
                if (e.key === "Enter" && e.target && e.target.getAttribute &&
                    e.target.getAttribute("data-r") === "kw") {
                    e.preventDefault(); go();
                }
            });
        },

        refreshPermBox: function () {
            var box = this.els.body.querySelector(".drive-perm");
            if (!box) { return; }
            /* 只替换 .drive-perm 的「内容」，保留容器本身 —— 这样绑定在容器上的
               事件委托仍然有效（直接替换整段 html 会嵌套出两层 .drive-perm）。 */
            var tmp = el("div", "", this.permBoxHtml());
            box.innerHTML = tmp.firstChild ? tmp.firstChild.innerHTML : "";
        },

        searchPerm: function (kind, kw) {
            var self = this;
            kw = String(kw || "").trim();
            var box = this.els.body.querySelector(".drive-perm");
            var out = box ? box.querySelector('[data-r="results"]') : null;
            if (!out) { return; }
            if (!kw) { out.innerHTML = '<span class="drive-perm-hint">请输入关键字后回车 / 点搜索</span>'; return; }
            out.innerHTML = '<span class="drive-perm-hint">搜索中…</span>';
            var p;
            if (kind === "role") {
                p = xhrJson("PUT", ORG_API + "/role/list/like", { json: { key: kw } }).then(function (d) {
                    return ((d && d.data) || []).map(function (r) { return { v: r.unique || r.name, n: r.name }; });
                });
            } else {
                p = xhrJson("PUT", ORG_API + "/person/list/like", { json: { key: kw } }).then(function (d) {
                    return ((d && d.data) || []).map(function (x) {
                        return { v: x.distinguishedName || x.name, n: x.name };
                    });
                });
            }
            p.then(function (list) {
                if (!list.length) { out.innerHTML = '<span class="drive-perm-hint">无匹配结果</span>'; return; }
                out.innerHTML = list.map(function (x) {
                    return '<span class="drive-perm-res" data-add="' + kind + '" data-v="' + esc(x.v) +
                        '" data-n="' + esc(x.n) + '">+ ' + esc(x.n) + "</span>";
                }).join("");
            }).catch(function (e) {
                out.innerHTML = '<span class="drive-perm-hint">搜索失败：' + esc((e && e.message) || "") + "</span>";
            });
        },

        formRow: function (label, id, value, hint) {
            return '<div class="drive-form-row">' +
                '  <div class="drive-form-label">' + esc(label) + "</div>" +
                '  <div class="drive-form-field">' +
                '    <input id="' + id + '" type="text" value="' + esc(value) + '">' +
                (hint ? '<div class="drive-form-hint">' + esc(hint) + "</div>" : "") +
                "  </div></div>";
        },

        saveConfig: function () {
            var self = this;
            var q = function (id) { var e = self.els.body.querySelector("#" + id); return e ? e.value : ""; };
            var splitExt = function (v) {
                return String(v || "").split(/[,，\s]+/).map(function (s) { return s.trim().replace(/^\./, ""); })
                    .filter(function (s) { return !!s; });
            };
            var capMb = Number(q("cfg-cap")) || 0;
            var filePayload = {
                capacity: capMb > 0 ? capMb * 1048576 : 0,
                recycleDays: Number(q("cfg-days")) || 15,
                fileTypeIncludes: splitExt(q("cfg-includes")),
                fileTypeExcludes: splitExt(q("cfg-excludes"))
            };
            var pd = this.state.permDraft || { person: [], role: [] };
            var drivePayload = {
                shareLimitMb: Number(q("cfg-sharelimit")) || 0,
                creatorPersonList: pd.person.map(function (x) { return x.v; }),
                creatorRoleList: pd.role.map(function (x) { return x.v; })
            };

            var errs = [];
            var pFile = xhrJson("POST", API + "/config", { json: filePayload })
                .catch(function (e) { errs.push("系统设置：" + ((e && e.message) || "失败")); });
            var pDrive = this.saveDriveCfg(drivePayload)
                .catch(function (e) { errs.push("网盘策略：" + ((e && e.message) || "失败")); });

            return Promise.all([pFile, pDrive]).then(function () {
                if (errs.length) { self.toast("部分保存失败 —— " + errs.join("；"), true); }
                else { self.toast("设置已保存"); }
                self.adminSetting();
            });
        },

        loadCapacity: function () {
            var self = this;
            xhrJson("GET", API + "/attachment2/user/capacity").then(function (d) {
                var used = (d && d.data && d.data.value) || 0;
                self.renderFoot(used);
            }).catch(function () { self.renderFoot(0); });
        },

        renderFoot: function (used) {
            var F = 1073741824;
            var pct = Math.min(100, Math.round(used / (F * 10) * 100)); // 参考刻度 10GB
            this.els.foot.innerHTML =
                "<span>" + esc(t("used", "已使用")) + "：<b style='color:#2d6fd6'>" + esc(fmtSize(used)) + "</b></span>" +
                '<span class="drive-cap-track"><span class="drive-cap-fill" style="width:' + pct + '%"></span></span>' +
                '<span class="spacer"></span>' +
                "<span>数据源：x_file_assemble_control</span>";
        },

        /* ---------------------------------------------------------- 动作：上传 / 建夹 */
        upload: function (files) {
            var self = this;
            var inArea = (this.state.sec === "admin" && this.state.adminSub === "areafile");
            var folder = inArea
                ? (this.state.areaCur || this.state.areaId || TOP_FOLD)
                : (this.state.folder || TOP_FOLD);
            var list = Array.prototype.slice.call(files);

            /* ★ 共享区文件上传大小限制（后台管理 → 设置，存于门户数据字典 driveSetting）
               仅对共享区上传生效；0 / 未设置 = 不限制。超限文件直接拦截并明确提示。 */
            var limitMb = Number(this.state.driveCfg && this.state.driveCfg.shareLimitMb) || 0;
            var limitBytes = (inArea && limitMb > 0) ? limitMb * 1048576 : 0;
            if (limitBytes > 0) {
                var over = list.filter(function (f) { return f.size > limitBytes; });
                if (over.length) {
                    list = list.filter(function (f) { return f.size <= limitBytes; });
                    this.toast("超过共享区上传上限 " + limitMb + " MB，已跳过：" +
                        over.map(function (f) { return f.name + "（" + fmtSize(f.size) + "）"; }).join("、"), true);
                }
                if (!list.length) { return; }
            }

            var i = 0, okN = 0, bad = [];
            var prog = this.showProgress();

            /* ★ 结束处理：无论成败都要收敛并刷新列表。
               早期版本在失败分支里直接 return（不调 next()）⇒ 一个文件被服务端拒
               （例如后缀不在白名单）会导致：后面的文件根本不上传、列表不刷新、
               用户只看到一条 toast 且新文件不出现 —— 已实测复现并修复。 */
            function finish() {
                if (prog) prog.remove();
                if (bad.length) {
                    self.toast(bad.length + " 个文件上传失败" + (okN ? "（" + okN + " 个成功）" : "") +
                        "：" + bad.slice(0, 3).join("；") +
                        (bad.length > 3 ? " 等" : "") +
                        "。允许的后缀可在「后台管理 → 设置 → 只允许上传的文件后缀」调整。", true);
                } else if (okN) {
                    self.toast(okN + " 个文件" + t("uploadSuccess", "上传完成"));
                }
                if (inArea) { self.renderAreaBrowse(); } else { self.loadPersonal(); }
            }

            function next() {
                if (i >= list.length) { finish(); return; }
                var f = list[i++];
                var fd = new FormData();
                fd.append("file", f, f.name);
                var x = new XMLHttpRequest();
                x.open("POST", API + "/attachment2/upload/folder/" + encodeURIComponent(folder), true);
                var tk = token();
                if (tk) x.setRequestHeader("x-token", tk);
                if (prog) { prog.name.textContent = f.name; prog.fill.style.width = "0%"; }
                x.upload.onprogress = function (e) {
                    if (e.lengthComputable && prog) {
                        prog.fill.style.width = Math.round(e.loaded * 100 / e.total) + "%";
                    }
                };
                x.onload = function () {
                    if (x.status >= 200 && x.status < 300) { okN++; }
                    else {
                        var msg = "HTTP " + x.status;
                        try { msg = JSON.parse(x.responseText).message || msg; } catch (e) { }
                        bad.push(f.name + "（" + msg + "）");
                    }
                    next();
                };
                x.onerror = function () { bad.push(f.name + "（网络错误）"); next(); };
                x.send(fd);
            }
            next();
        },

        showProgress: function () {
            var box = el("div", "drive-progress");
            box.innerHTML = '<div class="drive-progress-name">准备上传…</div>' +
                '<div class="drive-progress-track"><div class="drive-progress-fill"></div></div>';
            this.root.appendChild(box);
            return { el: box, name: box.querySelector(".drive-progress-name"), fill: box.querySelector(".drive-progress-fill"), remove: function () { box.remove(); } };
        },

        promptFolder: function () {
            var self = this;
            this.dialog(t("mkdir", "新建文件夹"), '<input type="text" placeholder="' + esc(t("inputFolderName", "请输入文件夹名称")) + '">',
                function (value, close) {
                    var name = (value || "").trim();
                    if (!name) { self.toast("名称不能为空", true); return; }
                    xhrJson("POST", API + "/folder2", {
                        json: { name: name, superior: self.state.folder || "" }
                    }).then(function () {
                        close();
                        self.toast(t("mkdirSuccess", "文件夹已创建"));
                        self.loadPersonal();
                    }).catch(function (e) { self.toast(e.message || "创建失败", true); });
                });
        },

        renameFile: function (f) {
            var self = this;
            this.dialog(t("rename", "重命名"), '<input type="text" value="' + esc(f.name) + '">', function (value, close) {
                var name = (value || "").trim();
                if (!name) { return; }
                xhrJson("PUT", API + "/attachment2/" + encodeURIComponent(f.id), { json: { name: name } })
                    .then(function () { close(); self.toast("已重命名"); self.loadPersonal(); })
                    .catch(function (e) { self.toast(e.message || "重命名失败", true); });
            });
        },

        renameFolder: function (f) {
            var self = this;
            this.dialog(t("rename", "重命名"), '<input type="text" value="' + esc(f.name) + '">', function (value, close) {
                var name = (value || "").trim();
                if (!name) { return; }
                xhrJson("PUT", API + "/folder2/" + encodeURIComponent(f.id), { json: { name: name } })
                    .then(function () { close(); self.toast("已重命名"); self.loadPersonal(); })
                    .catch(function (e) { self.toast(e.message || "重命名失败", true); });
            });
        },

        remove: function (kind, id, name) {
            var self = this;
            /* ★ 目录必须走 folder2 端点：/folder/{id} 读的是旧表 FILE_FOLDER，
               对 folder2 创建的新目录一律抛「指定的目录: xxx 不存在」。（已实测确证） */
            var seg = (kind === "folder") ? "folder2" : kind;
            this.confirm(t("confirmDelete", "确定把「" + (name || "") + "」移入回收站吗？"), function (close) {
                xhrJson("DELETE", API + "/" + seg + "/" + encodeURIComponent(id))
                    .then(function () {
                        close();
                        self.toast(t("deleteSuccess", "已移入回收站"));
                        self.refresh();
                    })
                    .catch(function (e) { self.toast(e.message || "删除失败", true); });
            });
        },

        /* ---------------------------------------------------------- 下载 / 在线预览 */
        fileUrl: function (fileId) {
            return API + "/attachment2/" + encodeURIComponent(fileId) + "/download";
        },
        /* 共享上下文统一走 share 下载通道：服务端返回 Content-Disposition: inline，
           既可直接内嵌预览，也尊重共享范围（非本人文件 attachment2/{id}/download 会被拒）。 */
        shareFileUrl: function (shareId, fileId) {
            return API + "/share/download/share/" + encodeURIComponent(shareId) +
                "/file/" + encodeURIComponent(fileId);
        },

        triggerDownload: function (url) {
            var a = document.createElement("a");
            a.href = url;
            a.setAttribute("download", "");
            a.style.display = "none";
            document.body.appendChild(a);
            a.click();
            setTimeout(function () { a.remove(); }, 1500);
        },

        download: function (fileId) { this.triggerDownload(this.fileUrl(fileId)); },

        /* 文件夹打包下载（服务端返回 zip） */
        downloadFolder: function (folderId) {
            this.triggerDownload(API + "/folder2/" + encodeURIComponent(folderId) + "/download");
        },

        downloadShare: function (s) {
            if (!s) { return; }
            if (s.fileType === "folder") { this.downloadFolder(s.fileId); return; }
            if (s.fileId) { this.triggerDownload(this.shareFileUrl(s.id, s.fileId)); }
        },

        /* 在线预览：opt = { url, name, ext }
           服务端 download 返回真实 MIME（text/plain、image/png、application/pdf…），可直接内嵌渲染。 */
        preview: function (opt) {
            var self = this;
            var ext = opt.ext || extOf(opt.name);
            var kind = previewKind(ext);
            var mask = el("div", "drive-preview-mask");
            mask.innerHTML =
                '<div class="drive-preview">' +
                '  <div class="drive-preview-head">' +
                '    <span class="drive-preview-name" title="' + esc(opt.name) + '">' + esc(opt.name) + "</span>" +
                '    <span class="spacer"></span>' +
                '    <button class="drive-btn ghost" data-r="dl">下载</button>' +
                '    <button class="drive-btn" data-r="close">关闭</button>' +
                "  </div>" +
                '  <div class="drive-preview-body" data-r="body"></div>' +
                "</div>";
            var close = function () { mask.remove(); };
            var body = mask.querySelector('[data-r="body"]');
            mask.querySelector('[data-r="close"]').addEventListener("click", close);
            mask.querySelector('[data-r="dl"]').addEventListener("click", function () { self.triggerDownload(opt.url); });
            mask.addEventListener("click", function (e) { if (e.target === mask) close(); });

            if (kind === "image") {
                body.innerHTML = '<img class="drive-preview-img" src="' + esc(opt.url) + '" alt="">';
            } else if (kind === "pdf") {
                body.innerHTML = '<iframe class="drive-preview-frame" src="' + esc(opt.url) + '"></iframe>';
            } else if (kind === "audio") {
                body.innerHTML = '<audio class="drive-preview-media" controls src="' + esc(opt.url) + '"></audio>';
            } else if (kind === "video") {
                body.innerHTML = '<video class="drive-preview-media" controls src="' + esc(opt.url) + '"></video>';
            } else if (kind === "text") {
                body.innerHTML = '<pre class="drive-preview-text">加载中…</pre>';
                xhrText(opt.url).then(function (txt) {
                    body.innerHTML = '<pre class="drive-preview-text">' + esc(txt) + "</pre>";
                }).catch(function () {
                    body.innerHTML = '<div class="drive-preview-tip">文本读取失败，请下载后查看。</div>';
                });
            } else if (kind === "office") {
                body.innerHTML = '<div class="drive-preview-tip">' +
                    "<b>本机未安装 Office 在线转换组件（LibreOffice / OnlyOffice），故不提供在线预览。</b><br>" +
                    "请点击右上角「下载」用本地 Office 打开。<br>" +
                    '<span class="drive-preview-note">官方 x_pan_assemble_control 为 VIP 模块，本社区版未安装；' +
                    "服务端 office/preview 接口会把原文件原样返回，因此不做伪预览。</span>" +
                    "</div>";
            } else {
                body.innerHTML = '<div class="drive-preview-tip">该类型（' +
                    esc(ext ? "." + ext : "未知") + "）不支持在线预览，请下载后查看。</div>";
            }
            this.root.appendChild(mask);
        },

        /* 个人文件预览 */
        previewFile: function (f) {
            this.preview({ url: this.fileUrl(f.id), name: f.name, ext: f.extension || extOf(f.name) });
        },
        /* 共享文件预览（sid = 顶层共享项 id） */
        previewSharedFile: function (sid, f) {
            this.preview({
                url: this.shareFileUrl(sid, f.id),
                name: f.name, ext: f.extension || extOf(f.name)
            });
        },

        saveToMy: function (s) {
            var self = this;
            var url = API + "/share/share/" + encodeURIComponent(s.id) +
                "/file/" + encodeURIComponent(s.fileId) +
                "/folder/" + encodeURIComponent(TOP_FOLD);
            xhrJson("POST", url, {}).then(function () {
                self.toast("已保存到「个人文件」");
            }).catch(function (e) { self.toast(e.message || "保存失败", true); });
        },

        shareToOrg: function (fileId, name, kind) {
            var self = this;
            /* 「可创建权限名单」校验（名单为空 = 不限制） */
            if (!this.canCreateShare()) {
                this.toast("你不在「共享区可创建权限名单」内，无法共享到企业。" + this.creatorHint(), true);
                return;
            }
            if (!this.state.orgUnique) {
                this.toast("未能获取组织信息，无法共享到企业", true);
                return;
            }
            var what = kind === "folder" ? "文件夹「" + name + "」及其全部内容" : "文件「" + name + "」";
            this.confirm("将" + what + "共享给【" + (this.state.orgName || "本组织") + "】全体成员？",
                function (close) {
                    xhrJson("POST", API + "/share", {
                        json: {
                            fileId: fileId, name: name, shareType: "member",
                            shareUserList: [], shareOrgList: [self.state.orgUnique], shareGroupList: []
                        }
                    }).then(function () {
                        close();
                        self.toast(t("shareSuccess", "已共享到企业文件"));
                        self.renderNav();
                    }).catch(function (e) { self.toast(e.message || "共享失败", true); });
                });
        },

        removeShare: function (s) {
            var self = this;
            this.confirm(t("confirmUnshare", "确定取消该共享吗？"), function (close) {
                xhrJson("DELETE", API + "/share/" + encodeURIComponent(s.id))
                    .then(function () { close(); self.toast("已取消共享"); self.refresh(); })
                    .catch(function (e) { self.toast(e.message || "操作失败", true); });
            });
        },

        resumeRecycle: function (id) {
            var self = this;
            xhrJson("POST", API + "/recycle/" + encodeURIComponent(id) + "/resume", {})
                .then(function () { self.toast("已还原"); self.refresh(); })
                .catch(function (e) { self.toast(e.message || "还原失败", true); });
        },

        purgeRecycle: function (id) {
            var self = this;
            this.confirm("彻底删除后不可恢复，确定继续？", function (close) {
                xhrJson("DELETE", API + "/recycle/" + encodeURIComponent(id) + "/delete")
                    .then(function () { close(); self.toast("已彻底删除"); self.refresh(); })
                    .catch(function (e) { self.toast(e.message || "删除失败", true); });
            });
        },

        clearRecycle: function () {
            var self = this;
            this.confirm(t("confirmClear", "确定清空回收站吗？此操作不可恢复。"), function (close) {
                xhrJson("DELETE", API + "/recycle/empty")
                    .then(function () { close(); self.toast("回收站已清空"); self.refresh(); })
                    .catch(function (e) { self.toast(e.message || "清空失败", true); });
            });
        },

        /* ---------------------------------------------------------- 通用 UI */
        dialog: function (title, bodyHtml, onOk) {
            var wrap = el("div", "drive-mask");
            wrap.innerHTML = '<div class="drive-dialog">' +
                '<div class="drive-dialog-title">' + esc(title) + "</div>" +
                '<div class="drive-dialog-body">' + bodyHtml + "</div>" +
                '<div class="drive-dialog-foot">' +
                '  <button class="drive-btn" data-r="cancel">取消</button>' +
                '  <button class="drive-btn primary" data-r="ok">确定</button>' +
                "</div></div>";
            var input = wrap.querySelector("input");
            var close = function () { wrap.remove(); };
            wrap.querySelector('[data-r="cancel"]').addEventListener("click", close);
            wrap.querySelector('[data-r="ok"]').addEventListener("click", function () {
                onOk(input ? input.value : true, close);
            });
            wrap.addEventListener("click", function (e) { if (e.target === wrap) close(); });
            this.root.appendChild(wrap);
            if (input) {
                setTimeout(function () { input.focus(); input.select(); }, 30);
                input.addEventListener("keydown", function (e) {
                    if (e.key === "Enter") { onOk(input.value, close); }
                    if (e.key === "Escape") { close(); }
                });
            }
        },

        confirm: function (text, onOk) {
            var wrap = el("div", "drive-mask");
            wrap.innerHTML = '<div class="drive-dialog" style="width:340px">' +
                '<div class="drive-dialog-title">请确认</div>' +
                '<div class="drive-dialog-body">' + esc(text) + "</div>" +
                '<div class="drive-dialog-foot">' +
                '  <button class="drive-btn" data-r="cancel">取消</button>' +
                '  <button class="drive-btn primary" data-r="ok">确定</button>' +
                "</div></div>";
            var close = function () { wrap.remove(); };
            wrap.querySelector('[data-r="cancel"]').addEventListener("click", close);
            wrap.querySelector('[data-r="ok"]').addEventListener("click", function () { onOk(close); });
            wrap.addEventListener("click", function (e) { if (e.target === wrap) close(); });
            this.root.appendChild(wrap);
        },

        toast: function (msg, isErr) {
            var self = this;
            var old = this.root.querySelector(".drive-toast");
            if (old) old.remove();
            var box = el("div", "drive-toast" + (isErr ? " err" : ""), esc(msg));
            this.root.appendChild(box);
            setTimeout(function () { box.remove(); }, isErr ? 4200 : 2400);
        }
    };

    NS.Viewer = Viewer;
    NS.api = { ajax: xhrJson, token: token, fmtSize: fmtSize, fmtTime: fmtTime };
})();
