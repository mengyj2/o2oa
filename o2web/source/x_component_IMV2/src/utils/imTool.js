/* ============================================================================
 * imTool.js —— 聊聊(IMV2)「个人网盘取件 + office 在线编辑」能力（源码级）
 * ----------------------------------------------------------------------------
 * ★ 2026-10-15 源码级重构：本文件取代早期构建期注入的独立脚本
 *   patch/imdrive/o2im.js（原挂在 window.o2IMTool，由 Python 补丁把
 *   x_component_IMV2/$Main/js/main.js 里已压缩的代码串改掉）。
 *   旧做法的问题：改的是【构建产物】的 minified 字符串，锚点一漂移就静默失效，
 *   且改动无法在源码层审阅/回归。现在能力本体是源码模块，随 vite 一起构建。
 *
 * 能力：
 *   ① pickDrive({ onPick })   ——「个人网盘文件选择器」
 *      点聊聊输入框工具栏的网盘图标 → 弹出「企业网盘→个人文件」浏览框
 *      （真实后端数据，可进目录/返回上级）→ 选中文件 → 回传 File 对象。
 *   ② editOffice({ url, name, ext, size, fromIM })
 *      office 附件「在线编辑」：下载附件二进制 → 送入 OnlyOffice 文档库
 *      （POST /x_onlyofficefile_assemble_control/jaxrs/onlyoffice/upload）→
 *      以「可编辑」模式打开 OnlyOfficeEditor；编辑器侧按 syncDrive 选项
 *      在保存/关闭时把最新版自动回存到「个人文件」。
 *   ③ saveToDrive(file)       —— 把 Blob/File 存进个人文件（同名先删后建）。
 *   ④ isOfficeEditable/isOfficeAny/toast —— 类型判定与统一提示。
 *
 * 设计约束（与项目既有自研组件一致）：
 *   · 自包含：不依赖任何第三方库，只用原生 DOM / fetch / XMLHttpRequest。
 *   · 同源 + x-token：所有请求走同源并带 token，失败必须显式提示，不静默吞。
 *   · 幂等：重复调用安全；对外仍暴露 window.o2IMTool（老调用方兼容）。
 * ==========================================================================*/
const FILE_API = '/x_file_assemble_control/jaxrs';
const OO_API = '/x_onlyofficefile_assemble_control/jaxrs';
const TOP_FOLD = '$$TOP_FOLD';
const ICON_BASE = '../x_component_Drive/$Main/default/file/';

/* office 可编辑类型（与 OnlyOffice docserviceEditedDocs 对齐） */
const OFFICE_EDITABLE = ['doc', 'docx', 'docm', 'dot', 'dotx', 'txt', 'csv',
    'xls', 'xlsx', 'xlsm', 'ppt', 'pptx', 'pps', 'rtf', 'odt', 'ods', 'odp'];
/* OnlyOffice 可查看（非可编辑）的补充类型 */
const OFFICE_VIEWONLY = ['pdf', 'dotm', 'xlt', 'xltx', 'xltm', 'pot', 'potx',
    'potm', 'pptm', 'ppsm', 'ppsx', 'epub', 'mht', 'html', 'htm', 'fodt', 'xps'];

const EXT_ICON = {
    doc: 'docx_win.png', docx: 'docx_win.png', dot: 'docx_win.png', dotx: 'docx_win.png', rtf: 'docx_win.png',
    xls: 'xlsx_win.png', xlsx: 'xlsx_win.png', xlsm: 'xlsx_win.png', xlt: 'xlsx_win.png', csv: 'xlsx_win.png',
    ppt: 'pptx_win.png', pptx: 'pptx_win.png', pot: 'pptx_win.png', potx: 'pptx_win.png', pps: 'pptx_win.png',
    pdf: 'pdf.png', ofd: 'ofd.png',
    txt: 'text.png', text: 'text.png', md: 'text.png', log: 'text.png',
    jpg: 'jpeg.png', jpeg: 'jpeg.png', png: 'png.png', gif: 'gif.png', bmp: 'bmp.png',
    zip: 'zip.png', rar: 'rar.png', mp3: 'mp3.png', mp4: 'mpeg.png'
};

/* ---------------------------------------------------------------- 工具 */
function token() {
    const m = document.cookie.match(/(?:^|;\s*)x-token=([^;]*)/);
    if (m) {
        try {
            return decodeURIComponent(m[1]);
        } catch (e) {
            return m[1];
        }
    }
    try {
        return (window.layout && layout.session && layout.session.token) || '';
    } catch (e) {
        return '';
    }
}

function esc(s) {
    return String(s === undefined || s === null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function extOf(name) {
    const i = String(name || '').lastIndexOf('.');
    return i > -1 ? String(name).substring(i + 1).toLowerCase() : '';
}

function iconOf(ext) {
    return ICON_BASE + (EXT_ICON[String(ext || '').toLowerCase()] || 'unknow.png');
}

function fmtSize(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1073741824) return (n / 1048576).toFixed(1) + ' MB';
    return (n / 1073741824).toFixed(2) + ' GB';
}

/**
 * 统一提示：优先用 O2OA 全局 $OOUI.notice（与系统其它提示同风格），
 * 不可用时退化为自绘浮层，绝不静默吞掉失败。
 */
function toast(msg, isErr) {
    try {
        if (window.$OOUI && $OOUI.notice) {
            if (isErr) {
                $OOUI.notice.error('提示', String(msg));
            } else {
                $OOUI.notice.success('提示', String(msg));
            }
            return;
        }
    } catch (e) { /* 落到自绘浮层 */ }
    try {
        const n = document.createElement('div');
        n.style.cssText = 'position:fixed;z-index:999999;right:26px;top:76px;max-width:380px;' +
            "padding:10px 14px;border-radius:6px;font:13px/1.6 system-ui,'Microsoft YaHei';color:#fff;" +
            'box-shadow:0 6px 22px rgba(0,0,0,.22);background:' + (isErr ? '#e64545' : '#3a8ee6') + ';';
        n.textContent = msg;
        document.body.appendChild(n);
        setTimeout(() => {
            try {
                n.remove();
            } catch (e) { /* ignore */ }
        }, isErr ? 6000 : 3000);
    } catch (e) { /* ignore */ }
}

function xj(method, url, body) {
    return new Promise((resolve, reject) => {
        const x = new XMLHttpRequest();
        x.open(method, url, true);
        const t = token();
        if (t) {
            x.setRequestHeader('x-token', t);
        }
        if (body !== undefined && body !== null) {
            x.setRequestHeader('Content-Type', 'application/json');
        }
        x.onload = () => {
            let d = null;
            try {
                d = JSON.parse(x.responseText);
            } catch (e) { /* ignore */ }
            if (x.status >= 200 && x.status < 300 && (!d || d.type !== 'error')) {
                resolve(d);
            } else {
                reject(new Error((d && d.message) ? d.message : ('HTTP ' + x.status)));
            }
        };
        x.onerror = () => reject(new Error('网络请求失败'));
        try {
            x.send(body !== undefined && body !== null ? JSON.stringify(body) : null);
        } catch (e) {
            reject(e);
        }
    });
}

function fetchBlob(url) {
    return fetch(url, {headers: {'x-token': token()}, credentials: 'same-origin'})
        .then((r) => {
            if (!r.ok) {
                throw new Error('下载失败 HTTP ' + r.status);
            }
            return r.blob();
        });
}

function uploadForm(url, file, fields) {
    return new Promise((resolve, reject) => {
        const fd = new FormData();
        if (fields) {
            for (const k in fields) {
                fd.append(k, fields[k]);
            }
        }
        fd.append('file', file, file.name);
        try {
            fd.append('fileName', file.name);
        } catch (e) { /* ignore */ }
        const x = new XMLHttpRequest();
        x.open('POST', url, true);
        const t = token();
        if (t) {
            x.setRequestHeader('x-token', t);
        }
        x.onload = () => {
            let d = null;
            try {
                d = JSON.parse(x.responseText);
            } catch (e) { /* ignore */ }
            if (x.status >= 200 && x.status < 300 && (!d || d.type !== 'error')) {
                resolve(d);
            } else {
                reject(new Error((d && d.message) ? d.message : ('HTTP ' + x.status)));
            }
        };
        x.onerror = () => reject(new Error('上传失败（网络错误）'));
        x.send(fd);
    });
}

/* ================================================================ ① 网盘选择器 */
const MASK_STYLE = 'position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.35);z-index:999998;';
const DIALOG_STYLE = 'position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:680px;' +
    'max-width:92vw;height:520px;max-height:86vh;background:#fff;border-radius:8px;display:flex;' +
    'flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.28);';

function pickDrive(opts) {
    opts = opts || {};
    const onPick = opts.onPick || function () { /* noop */ };

    const mask = document.createElement('div');
    mask.style.cssText = MASK_STYLE;
    mask.innerHTML =
        '<div style="' + DIALOG_STYLE + '">' +
        '  <div style="padding:12px 16px;border-bottom:1px solid #e8eaee;display:flex;align-items:center;gap:8px;">' +
        '    <span style="font:600 15px system-ui,\'Microsoft YaHei\';color:#1f2329;">选择我的网盘文件</span>' +
        '    <span data-r="crumb" style="font:12px system-ui;color:#8a9099;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>' +
        '    <span data-r="up" style="cursor:pointer;font:12px system-ui;color:#3a8ee6;">返回上级</span>' +
        '    <span data-r="close" style="cursor:pointer;font:18px system-ui;color:#98a0a8;line-height:1;">×</span>' +
        '  </div>' +
        '  <div data-r="list" style="flex:1;overflow:auto;padding:6px 0;"></div>' +
        '  <div style="padding:10px 16px;border-top:1px solid #e8eaee;display:flex;align-items:center;justify-content:space-between;">' +
        '    <span style="font:12px system-ui;color:#8a9099;">选中文件后将发送到当前聊天</span>' +
        '    <span data-r="cancel" style="cursor:pointer;font:13px system-ui;color:#5b6068;border:1px solid #dcdfe4;border-radius:4px;padding:5px 14px;">取消</span>' +
        '  </div>' +
        '</div>';
    document.body.appendChild(mask);

    const listEl = mask.querySelector('[data-r="list"]');
    const crumbEl = mask.querySelector('[data-r="crumb"]');
    const path = [];      /* [{id,name}] */
    let busy = false;

    function close() {
        try {
            mask.remove();
        } catch (e) { /* ignore */ }
    }

    mask.querySelector('[data-r="close"]').onclick = close;
    mask.querySelector('[data-r="cancel"]').onclick = close;
    mask.addEventListener('click', (e) => {
        if (e.target === mask) {
            close();
        }
    });
    mask.querySelector('[data-r="up"]').onclick = () => {
        if (!path.length) {
            toast('已在「个人文件」根目录');
            return;
        }
        path.pop();
        load();
    };

    function row(folder, f) {
        const r = document.createElement('div');
        const isFolder = !!folder;
        const ext = f.extension || extOf(f.name);
        r.style.cssText = 'display:flex;align-items:center;gap:10px;padding:9px 18px;cursor:pointer;border-bottom:1px solid #f4f6f8;';
        r.onmouseenter = () => {
            r.style.background = '#f5f9ff';
        };
        r.onmouseleave = () => {
            r.style.background = '';
        };
        r.innerHTML =
            '<img src="' + (isFolder ? ICON_BASE + 'folder.png' : iconOf(ext)) + '" style="width:20px;height:20px;flex:none;">' +
            '<span style="flex:1;font:13px system-ui,\'Microsoft YaHei\';color:#24282e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(f.name) + '</span>' +
            '<span style="font:12px system-ui;color:#98a0a8;flex:none;">' + (isFolder ? '文件夹' : esc(fmtSize(f.length))) + '</span>';
        r.onclick = () => {
            if (busy) {
                return;
            }
            if (isFolder) {
                path.push({id: f.id, name: f.name});
                load();
                return;
            }
            /* 文件：下载为 File 后回传 */
            busy = true;
            r.style.opacity = '.5';
            const url = FILE_API + '/attachment2/' + encodeURIComponent(f.id) + '/download';
            fetchBlob(url).then((blob) => {
                const file = new File([blob], f.name, {type: blob.type || 'application/octet-stream'});
                close();
                busy = false;
                onPick(file);
            }).catch((e) => {
                busy = false;
                r.style.opacity = '';
                toast('读取网盘文件失败：' + (e && e.message ? e.message : e), true);
            });
        };
        return r;
    }

    function load() {
        const fid = path.length ? path[path.length - 1].id : null;
        crumbEl.textContent = '个人文件' + path.map((p) => ' / ' + p.name).join('');
        listEl.innerHTML = '<div style="padding:32px;text-align:center;font:13px system-ui;color:#98a0a8;">加载中…</div>';
        const pFolders = xj('GET', FILE_API + (fid ? '/folder2/list/' + encodeURIComponent(fid) : '/folder2/list/top'));
        const pFiles = xj('GET', FILE_API + (fid ? '/attachment2/list/folder/' + encodeURIComponent(fid) : '/attachment2/list/top'));
        Promise.all([pFolders, pFiles]).then((r) => {
            const folders = (r[0] && r[0].data) || [];
            const files = (r[1] && r[1].data) || [];
            listEl.innerHTML = '';
            if (!folders.length && !files.length) {
                listEl.innerHTML = '<div style="padding:40px;text-align:center;font:13px system-ui;color:#98a0a8;">此目录没有内容</div>';
                return;
            }
            folders.forEach((f) => listEl.appendChild(row(true, f)));
            files.forEach((f) => listEl.appendChild(row(false, f)));
        }).catch((e) => {
            listEl.innerHTML = '<div style="padding:32px;text-align:center;font:13px system-ui;color:#e64545;">' +
                esc(e && e.message ? e.message : e) + '</div>';
        });
    }

    load();
}

/* ================================================================ ② office 在线编辑 */
function isOfficeEditable(ext) {
    return OFFICE_EDITABLE.indexOf(String(ext || '').toLowerCase()) > -1;
}

function isOfficeAny(ext) {
    const e = String(ext || '').toLowerCase();
    return OFFICE_EDITABLE.indexOf(e) > -1 || OFFICE_VIEWONLY.indexOf(e) > -1;
}

/* 打开在线编辑：url 为可下载到原始文件的地址（IM 附件 / 网盘附件均可） */
function editOffice(opt) {
    opt = opt || {};
    const name = opt.name || 'document';
    const ext = opt.ext || extOf(name);
    if (!isOfficeEditable(ext)) {
        toast('该类型（.' + ext + '）不支持在线编辑，请下载后查看。', true);
        return;
    }
    toast('正在准备在线编辑…');
    fetchBlob(opt.url).then((blob) => {
        const f = new File([blob], name, {type: blob.type || 'application/octet-stream'});
        return uploadForm(OO_API + '/onlyoffice/upload', f);
    }).then((res) => {
        const d = (res && res.data) || {};
        const id = d.id;
        if (!id) {
            throw new Error('在线文档创建失败（未返回文档标识）');
        }
        if (!window.layout || !layout.openApplication) {
            throw new Error('桌面环境不可用，无法打开编辑器');
        }
        layout.openApplication(null, 'OnlyOfficeEditor', {
            documentId: id,
            mode: 'edit',
            jars: '',
            appId: 'OnlyOfficeEditor' + id,
            title: name,
            /* ★ 回存约定：编辑器保存/关闭时把最新版写回「个人文件」（同名覆盖） */
            syncDrive: {fileName: name, ext: ext, fromIM: opt.fromIM || ''}
        });
    }).catch((e) => {
        toast('在线编辑打开失败：' + (e && e.message ? e.message : e), true);
    });
}

/* 供编辑器/网盘复用的回存能力：把 Blob/File 存进个人文件（同名先删后建） */
function saveToDrive(file) {
    return xj('GET', FILE_API + '/attachment2/list/top').then((d) => {
        const list = (d && d.data) || [];
        const dup = list.filter((x) => x.name === file.name);
        let chain = Promise.resolve();
        dup.forEach((x) => {
            chain = chain.then(() => xj('DELETE', FILE_API + '/attachment2/' + encodeURIComponent(x.id)).catch(() => { /* ignore */ }));
        });
        return chain;
    }).catch(() => { /* 列表失败不阻断上传 */ }).then(() => {
        return uploadForm(FILE_API + '/attachment2/upload/folder/' + encodeURIComponent(TOP_FOLD), file);
    });
}

const imTool = {
    __version: '20261015a-src',
    pickDrive,
    editOffice,
    isOfficeEditable,
    isOfficeAny,
    saveToDrive,
    toast,
    api: {
        FILE_API,
        OO_API,
        TOP_FOLD,
        token,
        xj,
        uploadForm,
        fetchBlob,
        fmtSize
    }
};

/* 兼容早期由构建期脚本注入的 window.o2IMTool 调用方（网盘「转发到聊聊」等） */
try {
    window.o2IMTool = imTool;
} catch (e) { /* ignore */ }

export {
    pickDrive,
    editOffice,
    isOfficeEditable,
    isOfficeAny,
    saveToDrive,
    toast,
    fmtSize,
    imTool
};
export default imTool;
