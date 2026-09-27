// 复验（8 文件版）：CRM「客户管理」/x_desktop/app.html?app=CRM&status={}
// 断言：
//   1. 打开 CRM 无 alert 弹窗
//   2. 无 pageerror
//   3. 不再请求 BDMarkerTool.js
//   4. 不再请求 api.map.baidu.com（关键：全程零百度外网请求）
//   5. AddressExplorer.js / BaiduMap.js 被真实加载后无语法/运行错误
const { chromium } = require("playwright-core");
const BASE = "http://127.0.0.1:9090";
const USER = "mengyijie", PWD = "#Myj884856";

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();

  const dialogs = [], errs = [], watched = [], baiduHits = [];

  page.on("dialog", async (d) => {
    dialogs.push(d.message());
    console.log(">>> DIALOG:", d.message());
    try { await d.accept(); } catch (e) {}
  });
  page.on("pageerror", e => errs.push(String(e)));
  page.on("request", r => {
    const u = r.url();
    if (/x_component_CRM\/(Main|BaiduMap|AddressExplorer|BDMarkerTool)/.test(u)) watched.push(u.replace(BASE, "").replace(/\?.*$/, ""));
    if (/api\.map\.baidu\.com/.test(u)) baiduHits.push(u);
  });
  page.on("response", async r => {
    if (/api\.map\.baidu\.com/.test(r.url())) baiduHits.push("RESP " + r.status() + " " + r.url());
  });

  // 登录
  await page.goto(BASE + "/x_desktop/index.html", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const login = await page.evaluate(async ({ user, pwd }) => {
    const r = await fetch("/x_organization_assemble_authentication/jaxrs/authentication", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: user, password: pwd, mode: "" })
    });
    return await r.json();
  }, { user: USER, pwd: PWD });
  console.log("token:", login.data ? login.data.token.slice(0, 12) + "..." : "(FAIL)");
  await ctx.addCookies([{ name: "x-token", value: login.data.token, url: BASE }]);

  // 打开 CRM
  await page.goto(BASE + "/x_desktop/app.html?app=CRM&status={}", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(11000);

  console.log("--- CRM 加载的组件 JS ---");
  [...new Set(watched)].forEach(u => console.log("   " + u));

  // 主动去点「客户分布」等含地图的页签，逼出 AddressExplorer / BaiduMap
  const tabs = ["客户分布", "信息", "线索", "客户", "公海", "联系人", "销售简报"];
  for (const t of tabs) {
    try {
      const el = page.locator(`text=${t}`).first();
      if (await el.count() > 0) {
        await el.click({ timeout: 3000, force: true });
        await page.waitForTimeout(2500);
      }
    } catch (e) { /* 页签可能不存在，忽略 */ }
  }

  console.log("--- 点击各页签后的组件 JS ---");
  [...new Set(watched)].forEach(u => console.log("   " + u));

  const body = await page.evaluate(() => (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 200));
  console.log("--- body:", body);

  await page.screenshot({ path: "C:/temp/o2dbg/crm_fixed2.png", fullPage: false });

  console.log("");
  console.log("=== DIALOGS:", dialogs.length, JSON.stringify(dialogs));
  console.log("=== PAGEERRORS:", errs.length);
  errs.forEach(e => console.log("   " + e.slice(0, 160)));
  console.log("=== BDMarkerTool 请求:", watched.filter(u => /BDMarkerTool/.test(u)).length, "(期望 0)");
  console.log("=== 百度地图外网请求:", baiduHits.length, "(期望 0)");
  baiduHits.forEach(u => console.log("   " + u));

  const pass = dialogs.length === 0 && errs.length === 0 &&
               watched.filter(u => /BDMarkerTool/.test(u)).length === 0 &&
               baiduHits.length === 0;
  console.log("");
  console.log(pass ? "########## ALL PASS ##########" : "########## FAILED ##########");
  await browser.close();
  process.exit(pass ? 0 : 1);
})().catch(e => { console.log("FATAL", e); process.exit(1); });
