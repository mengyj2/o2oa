// vision_test.js —— 直接验证 llama-server 的视觉理解（不经 O2OA，隔离后端能力）
'use strict';
const http = require('http');
const fs = require('fs');

const PORT = process.env.PORT || 8088;
const IMG = process.argv[2] || 'D:\\O2OA\\gateway\\_test_vision.png';
const PROMPT = process.argv[3] || '这张图片里有什么？请把图片中的文字原样读出来。';

const b64 = fs.readFileSync(IMG).toString('base64');
const body = JSON.stringify({
  model: 'qwen3.5-4b',
  stream: false,
  messages: [{
    role: 'user',
    content: [
      { type: 'text', text: PROMPT },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,' + b64 } },
    ],
  }],
});

const req = http.request(
  { host: '127.0.0.1', port: PORT, path: '/v1/chat/completions', method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } },
  (res) => {
    let buf = '';
    res.setEncoding('utf8');
    res.on('data', (c) => (buf += c));
    res.on('end', () => {
      console.log('HTTP', res.statusCode);
      try {
        const j = JSON.parse(buf);
        const msg = j.choices[0].message;
        console.log('--- CONTENT ---');
        console.log(msg.content);
        if (msg.reasoning_content) console.log('--- REASONING ---\n' + msg.reasoning_content.slice(0, 400));
        console.log('--- RESULT:', (msg.content || '').length > 0 ? 'PASS' : 'FAIL', '---');
      } catch (e) {
        console.log(buf.slice(0, 800));
      }
    });
  }
);
req.on('error', (e) => { console.log('ERR', e.message); process.exit(1); });
req.write(body);
req.end();
