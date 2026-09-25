#!/usr/bin/env node
// ai_smoke.js —— O2OA AI 智能体端到端冒烟（经 9090 → 本地适配网关 → 本地推理后端）
//
// 用法：
//   node ai_smoke.js                 # 默认 chat：用一句话解释什么是防火墙
//   AI_GEN=rag node ai_smoke.js     # RAG 模式
//   O2OA_PWD=xxx node ai_smoke.js   # 指定 xadmin 密码
//
// 输出 JSON：{ ok, status, content, reasoning, first }
//   ok=true  ⟺  HTTP 200 且 content 分片 > 0（即界面不会空白）
//
// 退出码：0=通过 / 3=登录失败 / 4=冒烟未通过

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

(async () => {
  const HOST = '127.0.0.1';
  const PORT = process.env.O2OA_PORT || 9090;
  const PWD = process.env.O2OA_PWD || 'o2oaadmin2026';
  const GEN = process.env.AI_GEN || 'chat';
  const INPUT = process.env.AI_INPUT || '用一句话解释什么是防火墙';

  // 1) 登录 xadmin
  const login = await req(
    {
      host: HOST, port: PORT,
      path: '/x_organization_assemble_authentication/jaxrs/authentication',
      method: 'POST', headers: { 'content-type': 'application/json' },
    },
    JSON.stringify({ credential: 'xadmin', password: PWD })
  );
  let token = '';
  try { token = JSON.parse(login.body).data.token; } catch (e) {}
  if (!token) {
    console.log(JSON.stringify({ ok: false, stage: 'login', status: login.status, detail: (login.body || '').slice(0, 200) }));
    process.exit(3);
  }

  // 2) chat（经网关回源本地推理后端）
  const sm = await req(
    {
      host: HOST, port: PORT,
      path: '/x_ai_assemble_control/jaxrs/chat/completion',
      method: 'POST', headers: { 'x-token': token, 'content-type': 'application/json' },
    },
    JSON.stringify({ input: INPUT, generateType: GEN })
  );

  let content = 0, reasoning = 0;
  for (const line of sm.body.split(/\r?\n/)) {
    if (!line.startsWith('data: ')) continue;
    const d = line.slice(6);
    if (d === '[DONE]') continue;
    try {
      const j = JSON.parse(d);
      const de = ((j.choices || [{}])[0] || {}).delta || {};
      if (de.content) content++;
      if (de.reasoning_content) reasoning++;
    } catch (e) {}
  }

  const ok = sm.status === 200 && content > 0;
  console.log(JSON.stringify({
    ok, status: sm.status, content, reasoning,
    first: sm.body.replace(/\s+/g, ' ').slice(0, 160),
  }));
  process.exit(ok ? 0 : 4);
})();
