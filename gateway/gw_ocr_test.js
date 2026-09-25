// 通过网关 /gateway/ocr-test 验证附件→OCR 全链路
const GW = 'http://127.0.0.1:18790';
const TOKEN = 'local-o2-agent-2026';
const path = require('path');

const files = process.argv.slice(2);
if (!files.length) {
  console.log('用法: node gw_ocr_test.js <文件路径> [...]');
  process.exit(1);
}

(async () => {
  for (const f of files) {
    const abs = path.resolve(f);
    const r = await fetch(GW + '/gateway/ocr-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
      body: JSON.stringify({ path: abs }),
    });
    console.log(`\n########## ${path.basename(f)} (HTTP ${r.status}) ##########`);
    const t = await r.text();
    try {
      const j = JSON.parse(t);
      const d = j.data || j;
      if (d.error || !d.chars) { console.log('ERROR:', d.error || '(no text)', t.slice(0, 300)); continue; }
      console.log(`chars=${d.chars} ms=${d.ms} ext=${d.ext}`);
      console.log(d.text);
    } catch (e) { console.log('RAW:', t.slice(0, 400)); }
  }
})().catch(e => { console.error('FAIL', e); process.exit(1); });
