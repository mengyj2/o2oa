// OCR 服务端到端测试：直连 :8091，验证 扫描件 / 表格 / PDF 三场景
const fs = require('fs');
const path = require('path');

const OCR = 'http://127.0.0.1:8091';
const GW = path.join(__dirname);

async function health() {
  const r = await fetch(OCR + '/health');
  console.log('[health]', r.status, await r.text());
}

async function ocrFile(p, filename) {
  const b64 = fs.readFileSync(p).toString('base64');
  const t0 = Date.now();
  const r = await fetch(OCR + '/ocr', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_b64: b64, filename: filename || path.basename(p) }),
  });
  const j = await r.json();
  console.log(`\n=== ${filename || path.basename(p)} (HTTP ${r.status}, ${Date.now() - t0}ms) ===`);
  console.log('engine :', j.engine, '| pages:', j.pages, '| ok:', j.ok);
  console.log('text   :', JSON.stringify((j.text || '').slice(0, 400)));
  if (j.blocks && j.blocks.length) {
    console.log(`blocks : ${j.blocks.length} 条`);
    j.blocks.slice(0, 6).forEach(b => console.log('   ', JSON.stringify(b.text), 'score=' + b.score));
  }
  if (j.tables && j.tables.length) {
    j.tables.forEach((t, i) => {
      console.log(`table#${i + 1}: ${t.rows} x ${t.cols}`);
      t.cells.slice(0, 8).forEach(row => console.log('   |', row.join(' | ')));
    });
  }
  if (j.error) console.log('error  :', j.error);
  return j;
}

(async () => {
  await health();
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log('\n用法: node ocr_test.js <文件1> [文件2] ...');
    console.log('  例: node ocr_test.js _test_vision.png');
    return;
  }
  for (const a of args) await ocrFile(a);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
