// 端到端验证：标准 MCP(stdio) 工具 + skills 自主技能，经网关 generate(generateType=mcp)
const GW = 'http://127.0.0.1:18790';
const TOKEN = 'local-o2-agent-2026';

function sseParse(text) {
  const frames = [];
  for (const block of text.split('\n\n')) {
    let ev = null, data = null;
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) ev = line.slice(6).trim();
      if (line.startsWith('data:')) data = line.slice(5).trim();
    }
    if (data) frames.push({ ev, data });
  }
  return frames;
}

async function chat(prompt, label) {
  console.log(`\n===== ${label} =====`);
  console.log('Q:', prompt);
  const t0 = Date.now();
  const r = await fetch(GW + '/ai-gateway-completion/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
    body: JSON.stringify({
      clueId: 'e2e-mcp-' + Date.now(),
      aiModelName: 'qwen3.5-4b',
      person: 'xadmin',
      prompt,
      generateType: 'mcp',
      input: prompt,
      referenceIdList: [],
      generateType: 'mcp',
    }),
  });
  const text = await r.text();
  const frames = sseParse(text);
  let answer = '';
  for (const f of frames) {
    try {
      const j = JSON.parse(f.data);
      const d = j.choices?.[0]?.delta?.content;
      if (typeof d === 'string') answer += d;
    } catch (e) { /* ignore */ }
  }
  console.log(`A (${Date.now() - t0}ms):`, answer.trim().slice(0, 600));
  return answer;
}

(async () => {
  // 1) 内置工具 + skills_list：模型应同时拿到时间和技能清单
  await chat('现在几点？另外把你可用的自主技能（skills）列出来，包括每条的一句话说明。', '测试1：时间 + skills_list');

  // 2) 标准 MCP stdio 工具：demo__add
  await chat('请调用 demo__add 工具计算 3 加 39 等于多少，只报结果。', '测试2：外部 MCP demo__add');

  // 3) skills_run：应用已有技能（模型读到指引后应按其结构回答）
  await chat('按 meeting_minutes 技能，把这段话整理成纪要：今天下午3点在A楼会议室开了项目评审会，张三和李四参加，决定下周二上线新版本，李四负责准备发布清单，周五前完成。', '测试3：skills_run 应用技能');

  // 4) skills_create：让模型自主创建一个技能
  await chat('帮我创建一个叫 weekly_report 的自主技能：用于整理周报，内容包含本周完成、下周计划、风险与求助三部分，请用技能工具保存。', '测试4：skills_create 自主创建');

  // 5) 验证创建结果：再列一次技能清单
  await chat('现在列出你所有的自主技能。', '测试5：skills_list 复核');

  console.log('\nALL DONE');
})().catch(e => { console.error('FAIL', e); process.exit(1); });
