// 配置 O2OA 指向本地智能体网关: node o2_gw_cfg.js
const BASE = 'http://127.0.0.1:9090';
const GW_URL = 'http://192.168.1.5:18790';
const GW_TOKEN = 'local-o2-agent-2026';

async function main() {
  const lr = await fetch(BASE + '/x_organization_assemble_authentication/jaxrs/authentication', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: 'xadmin', password: 'o2oaadmin2026' })
  });
  const tok = (await lr.json()).data.token;
  const H = { 'Content-Type': 'application/json', 'x-token': tok };

  const gr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/get', { headers: H });
  const cfg = (await gr.json()).data;
  cfg.o2AiBaseUrl = GW_URL;
  cfg.o2AiToken = GW_TOKEN;
  cfg.o2AiEnable = true;

  const pr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/save', {
    method: 'POST', headers: H, body: JSON.stringify(cfg)
  });
  console.log('save HTTP', pr.status, (await pr.text()).slice(0, 200));

  const vr = await fetch(BASE + '/x_ai_assemble_control/jaxrs/config/get', { headers: H });
  const v = (await vr.json()).data;
  console.log('VERIFY o2AiEnable =', v.o2AiEnable, '| baseUrl =', v.o2AiBaseUrl,
    '| token =', v.o2AiToken ? '(已设置,' + v.o2AiToken.length + '字符)' : '空');
}
main().catch(e => console.log('ERR', e.message));
