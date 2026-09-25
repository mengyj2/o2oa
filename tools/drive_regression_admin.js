/* drive_regression_admin.js —— 后台管理（成员容量 / 用户总览）真机回归
   约定：无 $ 、无反引号，便于用双引号包裹传给 CLI。
   结果写入 window.__rt6 = {done:true, out:"..."} */
(function () {
    var S = [];
    function log(k, v) { S.push(k + " = " + v); }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function q(s) { return document.querySelector(s); }
    function qa(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
    function tx(e) { return e ? (e.textContent || "").trim() : ""; }
    function navItem(name) {
        var a = qa(".drive-nav-item");
        for (var i = 0; i < a.length; i++) { if (tx(a[i]).indexOf(name) >= 0) { return a[i]; } }
        return null;
    }
    async function waitFor(fn, ms, step) {
        var n = Math.ceil(ms / (step || 500));
        for (var i = 0; i < n; i++) { if (fn()) { return true; } await sleep(step || 500); }
        return false;
    }

    window.__errs = window.__errs || [];
    window.addEventListener("error", function (e) { window.__errs.push("ERR: " + e.message); }, true);

    (async function () {
        try {
            /* ---------- 0. 打开企业网盘（每次会话都是新的） ---------- */
            if (!q(".drive-root")) {
                var sb = q(".layout_menu_start_button");
                if (sb) { sb.click(); }
                await sleep(6000);
                var hit = null, a0 = qa(".layout_start_item_text");
                for (var i = 0; i < a0.length; i++) { if (tx(a0[i]).indexOf("企业网盘") >= 0) { hit = a0[i]; } }
                if (hit) { (hit.closest(".layout_start_item") || hit.parentNode).dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); }
                log("startMenuItems", a0.length);
            }
            log("driveRoot", await waitFor(function () { return !!q(".drive-root"); }, 30000, 1000));
            if (!q(".drive-root")) { window.__rt6 = { done: true, out: S.join("\n") }; return; }

            /* ---------- 1. 进入后台管理 ---------- */
            var adminNav = navItem("后台管理");
            log("navAdminFound", !!adminNav);
            if (adminNav) { adminNav.click(); }
            await sleep(4000);
            log("adminSubs", JSON.stringify(qa(".drive-nav-item").map(tx)));

            /* ---------- 2. 成员容量 ---------- */
            var capNav = navItem("成员容量");
            log("navCapacityFound", !!capNav);
            if (capNav) { capNav.click(); }
            var okCap = await waitFor(function () { return !!q(".drive-admin-banner"); }, 45000, 1000);
            log("capacityRendered", okCap);
            log("bannerRows", qa(".drive-ab-row").map(function (r) {
                return tx(r.querySelector(".drive-ab-k")) + ":" + tx(r.querySelector(".drive-ab-v"));
            }).join(" | "));
            log("capCards", qa(".drive-cards .drive-card").map(function (c) {
                return tx(c.querySelector(".drive-card-label")) + "=" + tx(c.querySelector(".drive-card-value"));
            }).join(" | "));
            log("capTableHead", qa(".drive-mt-head > span").map(tx).join("/"));
            var rows = qa(".drive-mt-row");
            log("capRowCount", rows.length);
            log("capFirstRows", rows.slice(0, 5).map(function (r) {
                return tx(r.querySelector(".drive-mt-c1")) + "|" + tx(r.querySelector(".drive-mt-c2")) +
                    "|" + tx(r.querySelector(".drive-mt-c3")) + "|" + tx(r.querySelector(".drive-mt-c7"));
            }).join("  ///  "));
            log("capBarRendered", qa(".drive-mt-row .drive-mt-track .drive-cap-fill").length);
            log("cssLoaded", !!q('link[href*="drive.css"]'));

            /* 搜索过滤 */
            var search = q('[data-r="mquery"]');
            if (search) {
                search.value = "孟";
                search.dispatchEvent(new Event("input", { bubbles: true }));
                await sleep(800);
                log("searchRowCount", qa(".drive-mt-row").length);
                search.value = "";
                search.dispatchEvent(new Event("input", { bubbles: true }));
                await sleep(600);
            }

            /* ---------- 3. 切换排序 ---------- */
            var sel = q('[data-r="msort"]');
            if (sel) {
                sel.value = "name";
                sel.dispatchEvent(new Event("change", { bubbles: true }));
                await sleep(800);
                var fr = q(".drive-mt-row");
                log("sortedBy", sel.value + " -> " + (fr ? tx(fr.querySelector(".drive-mt-c1")) : "(none)"));
            }

            /* ---------- 4. 用户总览 ---------- */
            var usersNav = navItem("用户总览");
            log("navUsersFound", !!usersNav);
            if (usersNav) { usersNav.click(); }
            var okU = await waitFor(function () { return qa(".drive-cards .drive-card").length > 3 && !!q(".drive-section-title"); }, 45000, 1000);
            log("usersRendered", okU);
            log("usersCards", qa(".drive-cards .drive-card").map(function (c) {
                return tx(c.querySelector(".drive-card-label")) + "=" + tx(c.querySelector(".drive-card-value"));
            }).join(" | "));
            log("usersTableHead", qa(".drive-mt-head > span").map(tx).join("/"));
            log("usersRowCount", qa(".drive-mt-row").length);
            log("allShareTitle", tx(q(".drive-section-title")));

            /* ---------- 5. 回收站 / 设置 仍在（回归） ---------- */
            var setNav = navItem("设置");
            if (setNav) { setNav.click(); }
            await waitFor(function () { return qa(".drive-setting-title").length > 0; }, 20000, 1000);
            log("settingTitles", JSON.stringify(qa(".drive-setting-title").map(tx)));
            var recNav = navItem("回收站");
            if (recNav) { recNav.click(); }
            await sleep(3000);
            log("recycleRendered", !!q(".drive-root"));

            /* 停在「成员容量」收尾，便于外层截图取证（这是本批的主交付页） */
            var back = navItem("成员容量");
            if (back) { back.click(); }
            await waitFor(function () { return !!q(".drive-admin-banner") && qa(".drive-mt-row").length > 0; }, 30000, 1000);
            log("finalPage", "成员容量");
            log("finalRowCount", qa(".drive-mt-row").length);

            log("jsErrs", JSON.stringify((window.__errs || []).slice(0, 6)));
        } catch (e) {
            S.push("EXCEPTION = " + (e && e.message ? e.message : e));
        }
        window.__rt6 = { done: true, out: S.join("\n") };
    })();

    return "started";
})();
