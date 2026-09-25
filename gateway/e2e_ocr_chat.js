// 端到端：走网关 /ai-gateway-completion/generate，验证工具调用 + OCR 附件链路
// 用法: node e2e_ocr_chat.js
const GW = 'http://127.0.0.1:18790';
const TOKEN = 'local-o2-agent-2026';

function sseParse(text) {
  const out = [];
  for (const block of text.split('\n\n')) {
    const lines = block.split('\n').filter(Boolean);
    let ev = null, data = [];
    for (const l of lines) {
      if (l.startsWith('event:')) ev = l.slice(6).trim();
      else if (l.startsWith('data:')) data.push(l.slice(5).trim());
    }
    if (data.length) out.push({ event: ev, data: data.join('\n') });
  }
  return out;
}

async function chat(prompt, opts = {}) {
  const body = {
    clueId: 'e2e-' + Date.now(),
    aiModelName: 'qwen3.5-4b',
    person: 'xadmin',
    generateType: opts.gtype || 'chat',
    input: prompt,
    referenceIdList: opts.refs || [],
    permissionList: opts.perms || [],
  };
  const t0 = Date.now();
  const r = await fetch(GW + '/ai-gateway-completion/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  const frames = sseParse(text);
  let answer = '', status = null;
  for (const f of frames) {
    try {
      const j = JSON.parse(f.data);
      if (j.generateType !== undefined && !status) status = j;
      const d = j.choices?.[0]?.delta?.content;
      if (typeof d === 'string') answer += d;
    } catch (e) { /* ignore */ }
  }
  return { answer, status, ms: Date.now() - t0, raw: text.slice(0, 1200) };
}

(async () => {
  console.log('===== 测试1：mcp 模式 + 工具调用（时间 + 计算） =====');
  let r = await chat('现在几点？另外帮我算一下 8888 * 1234 等于多少？', { gtype: 'mcp' });
  console.log('answer:', r.answer.slice(0, 500));
  console.log('ms:', r.ms);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
