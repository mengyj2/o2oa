/* drive_regression_runner.js —— 在页面内一次性跑完「企业网盘」功能回归（由 tools/o2_drive_regression.sh main 调用）
   约定：无 $ 、无反引号，便于用双引号包裹传给 CLI。 */
(function () {
    var S = [];
    function log(k, v) { S.push(k + " = " + v); }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function q(s) { return document.querySelector(s); }
    function qa(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
    function tx(e) { return e ? (e.textContent || "").trim() : ""; }
    function clickText(sel, re) {
        var a = qa(sel);
        for (var i = 0; i < a.length; i++) {
            if (re.test(tx(a[i]))) { a[i].click(); return true; }
        }
        return false;
    }
    function rowByName(re) {
        var r = qa(".drive-row");
        for (var i = 0; i < r.length; i++) {
            var t = r[i].querySelector(".drive-fname");
            if (t && re.test(tx(t))) { return r[i]; }
        }
        return null;
    }
    function opIn(row, re) {
        if (!row) { return false; }
        var o = row.querySelectorAll(".drive-op");
        for (var j = 0; j < o.length; j++) {
            if (re.test(tx(o[j]))) { o[j].click(); return true; }
        }
        return false;
    }
    function tail() { var t = q(".drive-toast"); return t ? tx(t) : "(none)"; }

    window.__errs = window.__errs || [];
    window.addEventListener("error", function (e) { window.__errs.push("ERR: " + e.message); }, true);

    (async function () {
        try {
            /* ---------- 0. 打开企业网盘 ---------- */
            if (!q(".drive-root")) {
                var sb = q(".layout_menu_start_button");
                if (sb) { sb.click(); }
                await sleep(7000);
                var a = qa(".layout_start_item_text");
                var hit = null;
                for (var i = 0; i < a.length; i++) { if (tx(a[i]).indexOf("企业网盘") >= 0) { hit = a[i]; } }
                if (hit) { (hit.closest(".layout_start_item") || hit.parentNode).dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); }
                log("startMenuItems", a.length);
            }
            for (var w1 = 0; w1 < 30 && !q(".drive-root"); w1++) { await sleep(1000); }
            log("driveRoot", !!q(".drive-root"));
            log("viewerType", typeof (window.MWF && MWF.xApplication && MWF.xApplication.Drive && MWF.xApplication.Drive.Viewer));
            log("navItems", qa(".drive-nav-item").length);
            if (!q(".drive-root")) { window.__rt5 = { done: true, out: S.join("\n") }; return; }

            /* ---------- 1. 新建文件夹 -> 删除 ---------- */
            clickText(".drive-actions .drive-btn", /新建文件夹/);
            await sleep(1500);
            var m = q(".drive-mask");
            if (m) { m.querySelector("input").value = "__RT5DEL__"; var ok1 = m.querySelector('[data-r="ok"]'); if (ok1) { ok1.click(); } }
            await sleep(4000);
            log("afterCreate", !!rowByName(/__RT5DEL__/));
            opIn(rowByName(/__RT5DEL__/), /^删除$/);
            await sleep(1500);
            var m2 = q(".drive-mask");
            if (m2) { var ok2 = m2.querySelector('[data-r="ok"]'); if (ok2) { ok2.click(); } }
            await sleep(5000);
            log("deleteStillThere", !!rowByName(/__RT5DEL__/));
            log("deleteToast", tail());

            /* ---------- 2. 上传 png + txt ---------- */
            var png = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 10, 73, 68, 65, 84, 120, 156, 99, 0, 1, 0, 0, 5, 0, 1, 13, 10, 45, 180, 0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130]);
            if (!rowByName(/__rt5\.png/)) {
                var dt = new DataTransfer();
                dt.items.add(new File([png], "__rt5.png", { type: "image/png" }));
                /* ★ 正面对照必须用白名单内后缀：FILE_CONFIG.properties.fileTypeIncludes 默认含
                   "text" 但不含 "txt" ⇒ 用 .txt 会被服务端 500 拒，导致误判"上传功能坏了"。 */
                dt.items.add(new File(["hello 中文预览 line2"], "__rt5.text", { type: "text/plain" }));
                var fi = q("#drv-file");
                fi.files = dt.files;
                fi.dispatchEvent(new Event("change", { bubbles: true }));
                await sleep(9000);
            }
            log("uploaded", !!rowByName(/__rt5\.png/) + "/" + !!rowByName(/__rt5\.text/));

            /* ---------- 3. 预览 png ---------- */
            opIn(rowByName(/__rt5\.png/), /预览/);
            await sleep(4000);
            var pm = q(".drive-preview-mask");
            var im = pm ? pm.querySelector(".drive-preview-img") : null;
            log("previewPng", JSON.stringify({
                open: !!pm, name: pm ? tx(pm.querySelector(".drive-preview-name")) : "",
                natW: im ? im.naturalWidth : -1, natH: im ? im.naturalHeight : -1,
                hasDownload: pm ? !!pm.querySelector('[data-r="dl"]') : false
            }));
            if (pm) { var cb = pm.querySelector('[data-r="close"]'); if (cb) { cb.click(); } }
            await sleep(1500);

            /* ---------- 4. 预览 txt ---------- */
            opIn(rowByName(/__rt5\.text/), /预览/);
            await sleep(4000);
            var pm2 = q(".drive-preview-mask");
            var pre = pm2 ? pm2.querySelector(".drive-preview-text") : null;
            log("previewTxt", JSON.stringify({ open: !!pm2, text: pre ? tx(pre).slice(0, 26) : null }));
            if (pm2) { var cb2 = pm2.querySelector('[data-r="close"]'); if (cb2) { cb2.click(); } }
            await sleep(1500);

            /* ---------- 5. 文件夹共享到企业 ---------- */
            if (!rowByName(/__RT5SHARE__/)) {
                clickText(".drive-actions .drive-btn", /新建文件夹/);
                await sleep(1500);
                var m3 = q(".drive-mask");
                if (m3) { m3.querySelector("input").value = "__RT5SHARE__"; var ok3 = m3.querySelector('[data-r="ok"]'); if (ok3) { ok3.click(); } }
                await sleep(4000);
            }
            opIn(rowByName(/__RT5SHARE__/), /共享到企业/);
            await sleep(1500);
            var m4 = q(".drive-mask");
            if (m4) { var ok4 = m4.querySelector('[data-r="ok"]'); if (ok4) { ok4.click(); } }
            await sleep(5000);
            log("shareToast", tail());

            clickText(".drive-nav-item", /^我的分享/);
            await sleep(6000);
            var ops = [], tags = [];
            qa(".drive-row .drive-op").forEach(function (x) { var s = tx(x); if (ops.indexOf(s) < 0) { ops.push(s); } });
            qa(".drive-row .drive-tag, .drive-tag").forEach(function (x) { var s = tx(x); if (tags.indexOf(s) < 0) { tags.push(s); } });
            log("myShare", JSON.stringify({ found: !!rowByName(/__RT5SHARE__/), ops: ops.slice(0, 8), tags: tags.slice(0, 5) }));

            /* ---------- 6. 后台管理 -> 设置 ---------- */
            clickText(".drive-nav-item", /后台管理/);
            await sleep(6000);
            clickText(".drive-nav-item", /^设置$/);
            await sleep(7000);
            var titles = [], rows = [];
            qa(".drive-setting-title").forEach(function (e) { titles.push(tx(e)); });
            qa(".drive-form-label").forEach(function (e) { rows.push(tx(e)); });
            log("setting", JSON.stringify({
                titles: titles, rows: rows,
                hasPerm: !!q(".drive-perm"),
                limit: (q("#cfg-sharelimit") || {}).value,
                permNest: qa(".drive-perm .drive-perm").length
            }));

            var pb = q(".drive-perm");
            if (pb) {
                pb.querySelector('[data-r="kind"]').value = "role";
                pb.querySelector('[data-r="kw"]').value = "Manager";
                pb.querySelector('[data-r="search"]').click();
                await sleep(4000);
                log("permSearch", tx(q(".drive-perm-results")).slice(0, 60));
                var res = q(".drive-perm-results .drive-perm-res");
                if (res) { res.click(); }
                await sleep(2000);
            }
            log("permTags", JSON.stringify(qa(".drive-perm-tag").map(tx)));

            /* ---------- 7. 保存 ---------- */
            var lim = q("#cfg-sharelimit");
            if (lim) { lim.value = "1"; }
            var save = q('[data-r="save"]');
            if (save) { save.click(); }
            await sleep(8000);
            log("saveToast", tail());
            await sleep(2500);
            log("afterSave", JSON.stringify({
                limit: (q("#cfg-sharelimit") || {}).value,
                tags: qa(".drive-perm-tag").map(tx),
                titles: qa(".drive-setting-title").length
            }));

            /* ---------- 8. 错误 ---------- */
            log("jsErrs", JSON.stringify((window.__errs || []).slice(0, 6)));
        } catch (e) {
            S.push("EXCEPTION = " + (e && e.message ? e.message : e));
        }
        window.__rt5 = { done: true, out: S.join("\n") };
    })();

    return "started";
})();
