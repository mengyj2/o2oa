// tool_call_test.js —— 验证 MCP 模式下的内置工具是否真被模型调用
// 用法: node tool_call_test.js "问题"
'use strict';
const http = require('http');

function req(opts, body) {
  return new Promise((resolve) => {
    const r = http.request(opts, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (buf += c));
      res.on('end', () => resolve({ status: res.statusCode, body: buf }));
    });
    r.on('error', (e) => resolve({ status: 0, error: e.message }));
    if (body) r.write(body);
    r.end();
  });
}

const TOKEN = 'local-o2-agent-2026';
const GW = { host: '127.0.0.1', port: 18790 };
const INPUT = process.argv[2] || '现在几点了？请告诉我具体的日期和时间。';

(async () => {
  const body = JSON.stringify({
    generateType: 'mcp',
    clueId: 'tooltest-' + Date.now(),
    input: INPUT,
    permissionList: [],
    referenceIdList: [],
  });
  const r = await req(
    {
      ...GW,
      path: '/ai-gateway-completion/generate',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ' + TOKEN,
        'Content-Length': Buffer.byteLength(body),
      },
    },
    body
  );
  console.log('HTTP', r.status);
  if (r.status !== 200) { console.log(r.body.slice(0, 500)); process.exit(1); }

  // 解析 SSE，拼出最终回答
  let content = '';
  let frames = 0;
  for (const line of (r.body || '').split('\n')) {
    if (!line.startsWith('data:')) continue;
    const d = line.slice(5).trim();
    if (d === '[DONE]') break;
    frames++;
    try {
      const j = JSON.parse(d);
      if (j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content) {
        content += j.choices[0].delta.content;
      }
    } catch (e) { /* status 帧等 */ }
  }
  console.log('frames:', frames);
  console.log('--- ANSWER ---');
  console.log(content);
  const ok = content.length > 0;
  console.log('--- RESULT:', ok ? 'PASS' : 'FAIL', '---');
  process.exit(ok ? 0 : 4);
})();
