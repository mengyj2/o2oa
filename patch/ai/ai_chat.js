// 端到端聊天测试: node ai_chat.js "问题"
const BASE = 'http://127.0.0.1:9090';
async function main() {
  const q = process.argv[2] || '用一句话说明什么是容器';
  const lr = await fetch(BASE + '/x_organization_assemble_authentication/jaxrs/authentication', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: 'xadmin', password: 'o2oaadmin2026' })
  });
  const tok = (await lr.json()).data.token;
  const r = await fetch(BASE + '/x_ai_assemble_control/jaxrs/chat/completion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-token': tok },
    body: JSON.stringify({ input: q })
  });
  const t = await r.text();
  let out = '', n = 0, rt = 0, err = '';
  for (const line of t.split(/\r?\n/)) {
    if (!line.startsWith('data: ')) continue;
    const d = line.slice(6);
    if (d === '[DONE]') continue;
    try {
      const j = JSON.parse(d);
      if (j.choices) {
        const de = j.choices[0].delta || {};
        if (de.reasoning_content) rt++;
        if (de.content) { out += de.content; n++; }
      } else if (j.prompt || j.message) { err = JSON.stringify(j).slice(0, 200); }
    } catch (e) { }
  }
  console.log('content分片 =', n, '| reasoning分片 =', rt);
  if (err) console.log('错误帧 =', err);
  console.log('--- 回复 ---');
  console.log(out.slice(0, 400));
}
main().catch(e => console.log('ERR', e.message));
