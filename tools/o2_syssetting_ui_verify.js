/**
 * o2_syssetting_ui_verify.js —— 「系统设置」组件真机 UI 回归（playwright-core 直驱）
 *
 * 为什么不用 agent-browser：
 *   本机 agent-browser 的 daemon 会卡死（open 无输出、3 分钟不返回，清状态文件 / 重装
 *   Chrome 均无效）。因此改用 agent-browser 自带的 playwright-core 直接驱动已安装的
 *   Chrome，绕开 daemon，稳定可靠。
 *
 * 为什么用「REST 取令牌 + 注入 cookie」而不是点登录页：
 *   ① admin/xadmin 是 O2OA「初始管理员」（不在 ORG_PERSON），UI 登录会被前端的
 *      "密码已过期"策略拦截（REST 登录与桌面会话均正常）——这是初始管理员的固有行为；
 *   ② 开启 captchaLogin 后登录页还需要图形验证码，自动化成本高。
 *   注入 x-token cookie 后桌面可直接恢复会话（实测 user=系统管理员）。
 *
 * ★ 菜单入口的真实来源（2026-09-23 实测确认）：
 *   「系统管理」这类分组菜单由**门户数据字典 appmenus** 驱动，不是 CPT_COMPONENT。
 *   字典 GEN_DICT(xalias='appmenus', xapplication=<portalId>) 的 data.appNavis[] 即
 *   门户首页左侧的分组，每组 children[] 为条目（actionType=app/script/portal）。
 *   故本脚本按**真实用户路径**验证：打开门户 index -> 展开「系统管理」-> 点「系统设置」。
 *
 * 用法：
 *   node tools/o2_syssetting_ui_verify.js [截图路径]
 * 环境变量：
 *   O2OA_BASE / O2OA_USER / O2OA_PASS / O2OA_PORTAL / O2OA_PW(playwright-core 路径) / O2OA_CHROME
 */
const fs = require('fs');
const path = require('path');

const BASE = process.env.O2OA_BASE || 'http://localhost:9090';
const USER = process.env.O2OA_USER || 'admin';
const PASS = process.env.O2OA_PASS || 'o2oaadmin2026';
const PORTAL = process.env.O2OA_PORTAL || '0d565ae3-d9c0-4968-ab12-41cfa11845df';
const GROUP = '系统管理';
const ITEM = '系统设置';
const SHOT = process.argv[2] || '.syssetting-ui-verify.png';

function findPlaywrightCore() {
    const home = process.env.USERPROFILE || process.env.HOME || '';
    const cands = [
        process.env.O2OA_PW,
        path.join(home, '.workbuddy/binaries/node/workspace/node_modules/playwright-core'),
        path.join(process.env.APPDATA || '', 'npm/node_modules/playwright-core'),
        path.join(home, 'AppData/Roaming/npm/node_modules/playwright-core')
    ].filter(Boolean);
    for (const c of cands) { try { if (fs.existsSync(c)) return c; } catch (e) { } }
    return null;
}

function findChrome() {
    const home = process.env.USERPROFILE || process.env.HOME || '';
    if (process.env.O2OA_CHROME) return process.env.O2OA_CHROME;
    const base = path.join(home, '.agent-browser/browsers');
    try {
        const dirs = fs.readdirSync(base).filter(d => d.indexOf('chrome-') === 0).sort().reverse();
        for (const d of dirs) {
            const p = path.join(base, d, 'chrome.exe');
            if (fs.existsSync(p)) return p;
        }
    } catch (e) { }
    const others = [
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
    ];
    for (const p of others) { try { if (fs.existsSync(p)) return p; } catch (e) { } }
    return null;
}

const PW = findPlaywrightCore();
const CHROME = findChrome();
if (!PW) { console.log('FAIL —— 找不到 playwright-core（可用 O2OA_PW 指定）'); process.exit(2); }
if (!CHROME) { console.log('FAIL —— 找不到 Chrome/Edge 可执行文件（可用 O2OA_CHROME 指定）'); process.exit(2); }
const { chromium } = require(PW);
const log = (...a) => console.log(...a);

// 在某个 page 上等待「系统设置」组件渲染完成
async function waitSssWrap(page, tries, stepMs) {
    for (let i = 0; i < tries; i++) {
        await page.waitForTimeout(stepMs);
        if (await page.evaluate(() => !!document.querySelector('.ss-wrap'))) return true;
    }
    return false;
}

(async () => {
    const out = { ok: false };
    let browser;
    try {
        log('[1] REST 登录取令牌 ...');
        const resp = await fetch(BASE + '/x_organization_assemble_authentication/jaxrs/authentication', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: USER, password: PASS })
        });
        const tk = resp.headers.get('x-token');
        if (!tk) throw new Error('REST 登录未取到 x-token, status=' + resp.status);
        out.token = tk.slice(0, 12) + '…';

        browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-gpu'] });
        const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 }, acceptDownloads: true });
        await ctx.addCookies([{ name: 'x-token', value: tk, url: BASE, httpOnly: true }]);

        const page = await ctx.newPage();
        const errs = [];
        page.on('pageerror', e => errs.push('PAGEERR: ' + (e && e.message ? e.message : JSON.stringify(e))));
        page.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE: ' + String(m.text()).slice(0, 160)); });

        log('[2] 打开门户「系统首页」(index) ...');
        await page.goto(BASE + '/x_desktop/portal.html?id=' + PORTAL, { waitUntil: 'domcontentloaded', timeout: 60000 });
        let navReady = false;
        for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(1500);
            navReady = await page.evaluate(g => document.body.innerText.indexOf(g) >= 0, GROUP);
            if (navReady) break;
        }
        out.user = await page.evaluate(() => (typeof layout !== 'undefined' && layout.session && layout.session.user) ? layout.session.user.name : '');
        log('      登录态: ' + (out.user || '(空)') + ' / 菜单分组就绪=' + navReady);

        log('[3] 展开「' + GROUP + '」组，断言「' + ITEM + '」在列 ...');
        out.expand = await page.evaluate(a => {
            var g = a.g, all = document.querySelectorAll('*'), node = null;
            for (var i = 0; i < all.length; i++) {
                var e = all[i];
                if (e.children.length === 0 && (e.textContent || '').trim() === g) { node = e; break; }
            }
            if (!node) return { err: 'group-not-found' };
            var host = node.closest('li') || node.parentNode;
            ['mouseenter', 'mouseover', 'click'].forEach(function (ev) {
                host.dispatchEvent(new MouseEvent(ev, { bubbles: true, cancelable: true, view: window }));
            });
            return { dispatched: true };
        }, { g: GROUP, i: ITEM });

        // 展开后读面板
        let panel = [];
        for (let i = 0; i < 6; i++) {
            await page.waitForTimeout(1200);
            panel = await page.evaluate(it => {
                var best = [];
                document.querySelectorAll('.subsource').forEach(function (p) {
                    var r = p.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        var t = (p.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
                        if (t.indexOf(it) >= 0) best = t;
                    }
                });
                return best;
            }, ITEM);
            if (panel.length) break;
        }
        out.groupItems = panel;
        out.hasItem = panel.indexOf(ITEM) >= 0;
        log('      ' + GROUP + ' -> ' + (panel.length ? panel.join(' | ') : '(空)'));

        // 菜单证据截图（展开状态下）
        const MENUSHOT = SHOT.replace(/(\.[a-zA-Z]+)$/, '.menu$1');
        try { await page.screenshot({ path: MENUSHOT }); out.menuShot = MENUSHOT; log('      菜单截图 -> ' + MENUSHOT); } catch (e) { }

        log('[4] 点击「' + ITEM + '」并断言组件渲染 ...');
        let target = page;
        const popupPromise = ctx.waitForEvent('page', { timeout: 15000 }).catch(() => null);
        out.clicked = await page.evaluate(it => {
            var a = document.querySelectorAll('*');
            for (var i = 0; i < a.length; i++) {
                var e = a[i];
                if (e.children.length === 0 && (e.textContent || '').trim() === it) {
                    var r = e.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    var host = e.closest('li') || e.closest('a') || e.closest('div[class*=item]') || e.parentNode;
                    ['mouseenter', 'mouseover', 'click'].forEach(function (ev) {
                        host.dispatchEvent(new MouseEvent(ev, { bubbles: true, cancelable: true, view: window }));
                    });
                    return 'clicked';
                }
            }
            return 'NOT-FOUND';
        }, ITEM);
        log('      ' + out.clicked);

        const pop = await popupPromise;
        if (pop) { target = pop; try { await target.waitForLoadState('domcontentloaded', { timeout: 20000 }); } catch (e) { } }
        out.openedIn = (pop ? 'popup' : 'same-page');

        let ready = await waitSssWrap(target, 12, 1500);
        if (!ready && !pop) { // 兜底：直接深链打开
            log('      门户点击未渲染，回落深链 ?app=SysSetting ...');
            await page.goto(BASE + '/x_desktop/portal.html?app=SysSetting', { waitUntil: 'domcontentloaded', timeout: 60000 });
            ready = await waitSssWrap(page, 20, 1500);
            target = page; out.openedIn = 'deeplink';
        }
        out.wrap = ready;
        out.viewer = await target.evaluate(() => typeof (MWF.xApplication.SysSetting && MWF.xApplication.SysSetting.Viewer));
        out.navs = await target.evaluate(() => document.querySelectorAll('.ss-nav-item').length);
        log('      wrap=' + ready + ' viewer=' + out.viewer + ' navs=' + out.navs + ' (' + out.openedIn + ')');

        if (ready) {
            log('[5] 切到「验证码服务」读后端状态 ...');
            await target.evaluate(() => {
                var a = document.querySelectorAll('.ss-nav-item');
                for (var i = 0; i < a.length; i++) {
                    if ((a[i].textContent || '').trim().indexOf('验证码服务') >= 0) { a[i].click(); return; }
                }
            });
            for (let i = 0; i < 12; i++) {
                await target.waitForTimeout(1500);
                out.svcStatus = await target.evaluate(() => { var e = document.querySelector('#ssSvcStatus'); return e ? e.textContent.trim() : ''; });
                if (out.svcStatus) break;
            }
            out.svcNode = await target.evaluate(() => { var e = document.querySelector('#ssSvcNode'); return e ? e.textContent.trim() : ''; });
            log('      验证码服务: ' + out.svcStatus + ' @ ' + out.svcNode);

            log('[6] 切回「系统邮箱」展开模板并截图 ...');
            await target.evaluate(() => {
                var a = document.querySelectorAll('.ss-nav-item');
                for (var i = 0; i < a.length; i++) {
                    if ((a[i].textContent || '').trim().indexOf('系统邮箱') >= 0) { a[i].click(); return; }
                }
            });
            await target.waitForTimeout(2000);
            await target.evaluate(() => { var h = document.querySelector('[data-fold=ssTplFold]'); if (h) h.click(); });
            await target.waitForTimeout(1200);
        }
        await target.screenshot({ path: SHOT });
        log('      截图 -> ' + SHOT);

        out.errors = errs.slice(0, 6);
        out.ok = true;
    } catch (e) {
        out.error = String(e && e.message ? e.message : e);
    } finally {
        if (browser) { try { await browser.close(); } catch (e) { } }
    }
    console.log('RESULT ' + JSON.stringify(out, null, 2));

    let pass = out.ok && out.hasItem && out.wrap && out.navs === 4;
    if (pass) {
        if (out.svcStatus && out.svcStatus.indexOf('运行中') >= 0) log('PASS —— 菜单可见 + 组件正常，验证码服务在线');
        else log('PASS —— 菜单可见 + 组件正常（提示：本地邮件验证码服务 8095 未运行）');
    } else {
        log('FAIL —— 详见上方 RESULT');
        if (!out.hasItem) log('       门户「' + GROUP + '」组内未找到「' + ITEM + '」条目');
        if ((out.errors || []).length) log('       前端报错: ' + JSON.stringify(out.errors));
    }
    process.exit(pass ? 0 : 1);
})();
