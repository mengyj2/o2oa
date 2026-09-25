/* rt5b_runner.js —— 专项：共享区上传大小限制的前端拦截 + 权限名单拦截
   前置：上一轮已把 shareLimitMb 存为 1；本脚本结束后由 bash 复位为 0。 */
(function () {
    var S = [];
    function log(k, v) { S.push(k + " = " + v); }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function q(s) { return document.querySelector(s); }
    function qa(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
    function tx(e) { return e ? (e.textContent || "").trim() : ""; }
    function clickText(sel, re) {
        var a = qa(sel);
        for (var i = 0; i < a.length; i++) { if (re.test(tx(a[i]))) { a[i].click(); return true; } }
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
    function toast() { var t = q(".drive-toast"); return t ? tx(t) : "(none)"; }

    window.__errs = window.__errs || [];
    window.addEventListener("error", function (e) { window.__errs.push("ERR: " + e.message); }, true);

    (async function () {
        try {
            /* 0) 打开企业网盘（每次都是全新浏览器会话） */
            if (!q(".drive-root")) {
                var sb = q(".layout_menu_start_button");
                if (sb) { sb.click(); }
                await sleep(7000);
                var items = qa(".layout_start_item_text");
                var hit = null;
                for (var i = 0; i < items.length; i++) { if (tx(items[i]).indexOf("企业网盘") >= 0) { hit = items[i]; } }
                if (hit) { (hit.closest(".layout_start_item") || hit.parentNode).dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); }
                log("startMenuItems", items.length);
            }
            for (var w1 = 0; w1 < 30 && !q(".drive-root"); w1++) { await sleep(1000); }
            if (!q(".drive-root")) { window.__rt5b = { done: true, out: S.join("\n") }; return; }

            /* 1) 读当前策略（应为 1 MB） */
            log("limitInCfg", (window.MWF && MWF.xApplication && MWF.xApplication.Drive && MWF.xApplication.Drive.Viewer) ? "viewer-ok" : "?");

            /* 2) 进入后台管理 -> 共享区文件 -> 打开 __RT5SHARE__ */
            clickText(".drive-nav-item", /后台管理/);
            await sleep(6000);
            clickText(".drive-nav-item", /共享区文件/);
            await sleep(7000);
            log("areaListHasRT5", !!rowByName(/__RT5SHARE__/));
            var row = rowByName(/__RT5SHARE__/);
            if (!row) { window.__rt5b = { done: true, out: S.join("\n") }; return; }
            var nm = row.querySelector(".drive-col-name");
            if (nm) { nm.click(); }
            await sleep(6000);
            log("inArea", !!q(".drive-crumb") && tx(q(".drive-crumb")).indexOf("__RT5SHARE__") >= 0);
            log("crumb", tx(q(".drive-crumb")));

            /* 3) 上传 2MB 文件 -> 期望被前端拦截（上限 1MB） */
            var big = new Uint8Array(2 * 1024 * 1024);
            var dt = new DataTransfer();
            dt.items.add(new File([big], "__rt5_big.bin", { type: "application/octet-stream" }));
            var fi = q("#drv-file");
            fi.files = dt.files;
            fi.dispatchEvent(new Event("change", { bubbles: true }));
            await sleep(1200);
            log("bigToast", toast());

            /* 4) 再传一个 10KB 小文件 -> 期望正常通过 */
            await sleep(3500);
            var small = new Uint8Array(10 * 1024);
            var dt2 = new DataTransfer();
            dt2.items.add(new File([small], "__rt5_small.txt", { type: "application/octet-stream" }));
            var fi2 = q("#drv-file");
            log("fileInputFound", !!fi2);
            fi2.files = dt2.files;
            log("inputFilesN", fi2.files ? fi2.files.length : -1);
            fi2.dispatchEvent(new Event("change", { bubbles: true }));
            await sleep(1500);
            log("smallToast", toast());
            await sleep(8000);
            log("allRows", JSON.stringify(qa(".drive-fname").map(tx).slice(0, 12)));
            log("smallUploaded", !!rowByName(/__rt5_small/));
            log("bigUploaded", !!rowByName(/__rt5_big/));
            log("jsErrs", JSON.stringify((window.__errs || []).slice(0, 6)));
        } catch (e) {
            S.push("EXCEPTION = " + (e && e.message ? e.message : e));
        }
        window.__rt5b = { done: true, out: S.join("\n") };
    })();

    return "started";
})();
