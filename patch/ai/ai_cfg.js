// 用法: node ai_cfg.js get  |  node ai_cfg.js enable  |  node ai_cfg.js disable
const fs = require('fs');
const BASE = 'http://127.0.0.1:9090';

async function main() {
  const cmd = process.argv[2] || 'get';
  // 1. 登录
  const lr = await fetch(BASE + '/x_organization_assemble_authentication/jaxrs/authentication', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: 'xadmin', password: 'o2oaadmin2026' })
  });
  const lj = await lr.json();
  if (lj.type !== 'success') { console.log('LOGIN_FAIL', JSON.stringify(lj).slice(0, 300)); return; }
  const tok = lj.data.token;
  const H = { 'Content-Type': 'application/json', 'x-token': tok };

  // 2. 读配置
  const gr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/get', { headers: H });
  const gj = await gr.json();
  const cfg = gj.data;
  if (!cfg) { console.log('GET_FAIL', JSON.stringify(gj).slice(0, 300)); return; }

  if (cmd === 'get') {
    const c = { ...cfg };
    console.log(JSON.stringify(c, null, 1));
    return;
  }

  if (cmd === 'enable' || cmd === 'disable') {
    cfg.o2AiEnable = (cmd === 'enable');
    const pr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/save', {
      method: 'POST', headers: H, body: JSON.stringify(cfg)
    });
    const txt = await pr.text();
    console.log('HTTP', pr.status, '->', txt.slice(0, 500));
    // 回读验证
    const vr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/get', { headers: H });
    const vj = await vr.json();
    console.log('VERIFY o2AiEnable =', vj.data.o2AiEnable,
      '| o2AiBaseUrl =', JSON.stringify(vj.data.o2AiBaseUrl),
      '| o2AiToken =', JSON.stringify(vj.data.o2AiToken || ''));
  }
}
main().catch(e => console.log('ERR', e.message));
