---
name: o2oa-local-ai-assistant
description: 让 O2OA（开源版 / Docker 自托管）的 AI 助手在不连云、不用官方密钥的前提下，接入本机/局域网的 OpenAI 兼容推理端点（官方 llama.cpp standalone / LM Studio / Bionic / vLLM），并根治推理模型 "界面空白" 的 reasoning_content 陷阱。含：智能体私有协议本地适配网关（对话/知识库RAG/MCP 全离线）、用本机 GGUF 完全脱离 Bionic（官方 llama-server 组装 + ROCm，含 0xC0E90002 SxS 打包缺陷的绕法）、RAG "System message must be at the beginning" 修复、升级后自愈。当用户问"O2OA 智能体密钥是什么""系统里有模型吗""怎么接本地模型""AI 助手回复空白/没内容""开启智能体功能""reasoning_content 没有 content""reasoning_effort none""内置模型能直接用吗""不依赖 bionic/lm studio 能驱动吗""本地下好的 gguf 怎么用""官方 llama.cpp / llama-server.exe 怎么装""llama-server 启动报错 0xC0E90002 / 退出码 -1058471934""RAG 报 system message 错误"时调用。
agent_created: true
category: integration

---

# O2OA 本地 AI 助手接入（离线 / 无密钥 / 含推理模型补丁）

覆盖三件事：**① 搞清官方密钥机制** → **② 建本地模型条目** → **③ 打 reasoning 补丁让它真的能用**。
只做完 ①② 会出现"链路通了但界面空白"，③ 才是关键。

## 0. 先判定：现在卡在哪一步

| 症状 | 根因 | 跳转 |
|---|---|---|
| 不知道 `o2AiToken` 是啥 / 系统里 4 个模型都是空壳 | 官方网关认证三件套 + 模型表都是模板 | §1 §2 |
| 模型建好了，但回复空白 / 只有思考没有正文 | `reasoning_content` 陷阱（本文核心） | §3 §4 |
| 容器连不上本地后端，SSE 超时 | iptables 白名单缺失或顺序错 | §5 |
| 想启用「智能体」并让知识库/MCP 真正离线可用（原 7080 Connection refused） | 开源版无智能体服务端，需本地适配网关 | §9 §10 |
| 想用本机 GGUF、不装/不开 Bionic（LM Studio） | O2OA 无推理引擎，须自备后端进程 | §11 |
| 官方 `llama-server.exe` 跑不起来（退出码 `-1058471934` / `0xC0E90002`） | 官方 release 包的 DLL 打包缺陷，换 DLL 集 | §11 |
| RAG 报 `System message must be at the beginning` | 多加了第二条 system，Qwen3.5 模板不允许 | §12 |
| 升级 / 容器重建后 AI 失效 | netlock 白名单 + AI 配置 + 补丁丢失 | §13 |

---

## 1. 官方密钥机制（`o2AiToken` 是什么）

**结论：那不是一个"你需要去申请的密钥"，而是 O2OA 官方云端 AI 网关的签名 token。**

- 字段定义：`x_ai_assemble_control/.../bean/AiConfig.java` → `o2AiToken`（默认 `""`）
- 生成逻辑：`.../quartz/InitConfigTask.java` —— 每 4 分钟探 `127.0.0.1:7080`，
  读到 `o2.license` 就取 `token = "sk-" + MD5Tool.md5(license)`
- 消费点：`ActionChat.execute()` 的 if 分支
  ```java
  if (isTrue(aiConfig.getO2AiEnable())
        && isNotBlank(aiConfig.getO2AiBaseUrl())
        && isNotBlank(aiConfig.getO2AiToken())) {
      o2Chat(...);                        // 走官方云，需要 token
  } else {
      AiModel model = getActiveModel(wi.getEndpointName());
      if (model != null) aiChat(...);     // ★ 直连 model.getCompletionUrl()
  }
  ```

**关键推论**：开源版没有 `o2.license` → token 永远为空 → `o2AiEnable` 也默认 false
→ **必然走 `aiChat()` 分支**，也就是"自定义模型"直连路径。
所以接本地模型**根本不需要任何密钥**，也不会外连（`ActionCreateModel.saveToO2Ai()`
有 `if (isNotBlank(token))` 守卫，token 空即 no-op）。

⚠️ 不要为了"补上密钥"去设一个假的 `o2AiToken` —— 那会让 if 分支成立，
把请求推向不存在的官方网关，反而弄坏。

---

## 2. 建本地模型条目

表结构：`X.AI_MODEL`，列名全部带 `x` 前缀（`xname`/`xmodel`/`xcompletionUrl`/`xapiKey`/`xasDefault`/`xenable`/`xtype`）。

**必带 `/v1/chat/completions` 全路径**（`aiChat()` 直接 `client.target(model.getCompletionUrl())`，不拼路径）。

```bash
# 登录取 token（xadmin 密码见 O2OA admin README；虚拟账号，不在 ORG_PERSON 表）
curl -s -X POST -H "Content-Type: application/json" \
  --data-binary '{"credential":"xadmin","password":"<密码>"}' \
  http://127.0.0.1:9090/x_organization_assemble_authentication/jaxrs/authentication
# → data.token 即 x-token；后续用 -b/-H "x-token: <token>"
```

```bash
# 创建模型（注意 asDefault:true 会自动把原默认模型降级）
curl -s -X POST -H "Content-Type: application/json" -b cookie.txt \
  --data-binary '{
    "name":"本地GLM", "type":"local", "model":"glm-4.7-flash",
    "completionUrl":"http://192.168.1.5:1234/v1/chat/completions",
    "apiKey":"sk-local", "asDefault":true, "enable":true
  }' \
  http://127.0.0.1:9090/x_ai_assemble_control/jaxrs/config/create/model
```

其他配置接口（`ConfigAction`，`@Path("config")`）：
- `GET  /jaxrs/config/get`
- `GET  /jaxrs/config/list/model/paging/{page}/size/{size}`
- `POST /jaxrs/config/update/model/{flag}`
- `GET  /jaxrs/config/delete/model/{flag}`

`apiKey` 填什么都行（llama.cpp / LM Studio 不校验），但**不能留空**——留空会拼出
`Authorization: Bearer `，个别端会 400。

**LM Studio 必须监听 `0.0.0.0`**，否则 Docker 虚拟网卡（如 `172.22.0.1`）连不上。

---

## 3. ★ 核心：`reasoning_content` 陷阱

### 症状
链路全通（日志见 SSE 正常收包），但 O2OA 界面**一片空白**，`X.AI_CHAT` 里
`xcontent` 为空。

### 根因（两层）
1. `ActionChat.aiChat()` 发的请求体字段是
   `data.put("enable_thinking", BooleanUtils.isTrue(wi.getThinkingEnabled()))`
   —— **LM Studio 的 OpenAI 兼容端点不认 `enable_thinking`**，静默忽略。
2. 推理模型于是把 token 全烧在 `reasoning_content` 里，而
   `ActionChat.picContent()` **只读 `delta.content`**：
   ```java
   data = XGsonBuilder.extractString(choices.get(0), "delta.content");
   ```

### 实测结论矩阵（LM Studio / glm-4.7-flash）
| 尝试 | reasoning_tokens | content | 结论 |
|---|---|---|---|
| `enable_thinking=false` | 200 | `""` | ❌ 键名不被识别 |
| `chat_template_kwargs{enable_thinking:false}` | 63 | 被污染 | ❌ |
| `thinking:{type:"disabled"}` | 61 | 被污染 | ❌ |
| system 里加 `/no_think` | 53 | 部分输出但污染 | ❌ |
| user 消息里加 `/no_think` | 197 | `""` | ❌ |
| **`reasoning_effort:"none"`** | **0** | **完整正常** | ✅ **唯一有效** |

> 该模型 chat template 未实现 thinking 开关，只有 `reasoning_effort` 被推理控制层接管。
> **先查模型能力再选方案**：`GET http://<host>:1234/api/v0/models`
> （看 `arch`、`capabilities`）。开源的模型如 qwen3 系可能认 `/no_think`。

### 快速诊断命令（不改任何东西就能确认是这个问题）
```bash
curl -s -N -X POST http://127.0.0.1:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<模型>","stream":true,"max_tokens":100,
       "reasoning_effort":"none",
       "messages":[{"role":"user","content":"1+1=?"}]}' | head -5
# 若加了 reasoning_effort 后 delta 里全是 content → 就是它
```

---

## 4. 打补丁（字节码级，幂等 + 可回滚）

把请求体里的 `"enable_thinking" -> Boolean` 换成
`"reasoning_effort" -> "none"`。

### 产物
```
D:\O2OA\patch\ai\
  PatchActionChat.py        # 字节码补丁器（幂等，带 --verify 自校验）
  patch_ai_nothink.sh       # 总编排: apply | verify | restore | rebuild
  ActionChat.orig.class
  ActionChat.patched.class
```

### 用法
```bash
cd /d/O2OA/patch/ai
./patch_ai_nothink.sh apply     # 幂等：已是补丁版会自动跳过
./patch_ai_nothink.sh verify
./patch_ai_nothink.sh restore   # 从容器 /tmp/ActionChat.class.bak_orig 还原
```

### 目标位置
```
/opt/o2server/servers/applicationServer/work/x_ai_assemble_control/
  WEB-INF/classes/com/x/ai/assemble/control/jaxrs/chat/ActionChat.class
```
`work/` 是 war 解包目录。**实测 `docker restart` 不会用 war 覆盖它**，无需改 war。
（若某版本会覆盖，则需改 `store/x_ai_assemble_control.war` 内的同名 class。）

### 补丁的三处改动 —— ★ 关键设计，勿"简化"
1. **绝不修改已有 Utf8 的长度**。若把 `enable_thinking`(15B) 直接改名成
   `reasoning_effort`(16B)，常量池之后**所有方法的 `attribute_length` 都要跟着平移**，
   漏掉任何一处就 `unexpected end of file while reading`（此坑已踩过）。
   → 改为把新常量**追加**到常量池尾部。
2. `#415 String` 条目**原地**改指向新 Utf8 `"reasoning_effort"`（String 条目长度不变，
   只改 2 字节操作数）。
3. 字节码 **10 字节等长替换**：
   ```
   原: aload_1 | invokevirtual #417 | invokestatic #65 | invokestatic #176   (10B)
   新: ldc_w #n | nop × 7                                                    (10B)
   ```
   即 `Map.put("reasoning_effort", "none")`。等长替换避免所有偏移/栈帧重算。

### 三层验证（缺一不可）
1. `javap -p -v` rc=0，确认 `ldc_w #415 // String reasoning_effort` + `ldc_w #1001 // String none`
2. `java -Xverify:all` 加载通过（`VERIFY_OK`）
3. **端到端**：`POST /x_ai_assemble_control/jaxrs/chat/completion`
   body `{"input":"..."}` → 统计 `content 分片 > 0` 且 `reasoning 分片 = 0`

---

## 5. 容器 → 宿主 LLM 的网络白名单

O2OA 常态是封网状态（见 skill `o2oa-cloud-cutoff`）。
接本地 LLM 时要在 `iptables FORWARD` 加一条 ACCEPT 白名单。

**★ 顺序陷阱**：ACCEPT 必须排在封网 DROP **之前**。两者都用 `-I FORWARD` 时，
后插的会占位 1，把 ACCEPT 挤到 DROP 后面 → 容器连 LLM 超时。
正确做法 —— DROP 插到**位置 2**，ACCEPT 插**位置 1**：
```bash
iptables -I FORWARD 1 -s <容器IP> -d <LLM_HOST> -p tcp --dport <LLM_PORT> \
  -m comment --comment 'o2oa-netlock-allow' -j ACCEPT
iptables -I FORWARD 2 -s <容器IP> ! -d 172.16.0.0/12 \
  -m comment --comment 'o2oa-netlock' -j DROP
```
期望结果：
```
1  ACCEPT  tcp  172.22.0.3 → 192.168.1.5 dpt:1234 /* o2oa-netlock-allow */
2  DROP    all  172.22.0.3 → !172.16.0.0/12        /* o2oa-netlock */
```
这条规则要**固化进 `o2oa_netlock.sh`**，否则 Docker 重启/容器重建后丢失。

---

## 6. 本机环境特有的坑

### `docker exec` 间歇性 setns 失败（ARM64 + QEMU）
```
error starting setns process: fork/exec /proc/self/fd/6: no such file or directory
```
**绕过**：`docker cp`（走 Docker API）和 `docker logs` 不受影响。
脚本里统一写重试 + 降级：
```bash
dex() {  # 带重试的 docker exec
  local i out
  for i in 1 2 3 4 5 6; do
    out=$(docker exec "$C" bash -c "$1" 2>&1)
    case "$out" in *"setns"*|*"fork/exec /proc"*) sleep 3; continue;; esac
    printf '%s' "$out"; return 0
  done
  return 1
}
```

### `docker exec ... sh -c "cat > f" < localfile` 会产生空文件
WorkBuddy shim 干扰重定向。**改用 `docker cp`**，或在容器内用 here-doc。

### healthcheck 误报 unhealthy
O2OA 常有 `DirectoryNotEmptyException: .../x_component_PdfViewer`（既有告警，非致命）。
**别只看 healthcheck**，看 `docker logs` 里有没有 `web server is started in the application server`，
并用 `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:9090/...` 验证（401/200 都算活）。

### 别用 Bash 工具做 base64/中文比对
Git Bash + shim 下 `grep -c`、`head` 的编码/计数会错。统计流式分片用 Node：
```bash
node -e "const t=require('fs').readFileSync('chat_re.txt','utf8');
let c=0,r=0;
for(const l of t.split(/\r?\n/)){ if(!l.startsWith('data: '))continue;
  const d=l.slice(6); if(d==='[DONE]')continue;
  try{const j=JSON.parse(d); const de=(j.choices||[{}])[0].delta||{};
    if(de.content)c++; if(de.reasoning_content)r++;}catch(e){}}
console.log('content',c,'reasoning',r);"
```

---

## 7. 完整验收清单

- [ ] `GET /x_ai_assemble_control/jaxrs/config/get` → 目标模型 `asDefault:true`、`enable:true`
- [ ] `completionUrl` 带 `/v1/chat/completions` 全路径
- [ ] 容器内 `curl http://<LLM_HOST>:<PORT>/v1/models` 通（验证白名单）
- [ ] `iptables -L FORWARD -n --line-numbers`：ACCEPT 在 DROP **之前**
- [ ] `patch_ai_nothink.sh verify` → 显示补丁已生效
- [ ] 端到端 `chat/completion`：`content 分片 > 0`、`reasoning 分片 = 0`
- [ ] 封网未被破坏：容器 `curl http://www.o2oa.net` → `000`

## 8. 常见误判

| 现象 | 误判 | 真相 |
|---|---|---|
| 官方 4 个模型条目都在 | "系统已有模型" | 全是空壳模板，`xapiKey` 全空，不可用 |
| 要填 `o2AiToken` 才能用 | "得去申请密钥" | 开源版走 `aiChat()` 分支，根本不需要 |
| SSE 有数据返回 | "已经能用了" | 返回的可能是纯 `reasoning_content`，界面仍空白 |
| healthcheck unhealthy | "服务挂了" | 常是 PdfViewer 目录告警误报，看日志与 HTTP 码 |

## 9. 智能体开关离线启用（AI助手设置页）

设置页"是否启用智能体"红字提示知识库/MCP 需启用。离线环境可以安全启用开关：

### 源码要点
- 保存路由：**`POST /x_ai_assemble_control/jaxrs/config/save`**（不是 update；update/model 只针对模型条目）
- `ActionUpdateConfig` 保存不校验连通性：先落库，后 syncMcp/syncModel 探测 `o2AiBaseUrl`，失败仅报错（配置已存）
- 聊天分流：`o2AiEnable && baseUrl && token` 三者齐全才走云；**token 空 → 必走本地 aiChat**
- 知识库同步（ActionSync/QueueDocumentIndex）：同样三条件，token 空 → 跳过，零外连
- `InitConfigTask`：enable=true 时跳过探测；无 `config/o2.license` → 不填 token → **手动开启后稳定不被回改**

### 操作（先 GET 完整配置再改字段回传，避免 copier 把 null 覆盖进去）
```javascript
// GET /jaxrs/config/get 取完整 cfg → cfg.o2AiEnable = true → POST /jaxrs/config/save
```
启用后回读验证：`o2AiEnable=true`、`o2AiToken=""`、其余字段无损；再跑一次端到端聊天确认仍 content>0 / reasoning=0。

### 能力边界
- 启用后设置页可保存、知识库/MCP 菜单解锁
- 但"同步到知识库"会因 token 空被 ActionSync 拦截（报"请先启用o2智能体并进行相关配置"）
- MCP 管理页打容器内 7080（不通）→ 报错但无副作用
- 仅开开关、token 留空：知识库/MCP 仍不可用（ActionSync 拦截、7080 不通）
- ✅ **完整离线方案已实现**：见 §10 本地适配网关 `o2-agent-gateway`（对话/知识库RAG/MCP 全通，已交付并端到端验证）

---

## 10. ★ 智能体本地适配网关（推荐完整方案：对话 / 知识库RAG / MCP 全离线）

O2OA 开源版"智能体"只是云 SaaS 客户端，**开源版没有服务端**。它的私有协议（基址 `o2AiBaseUrl`）：
- 对话：`/ai-gateway-completion/generate`（SSE：首帧 `event:status` → `event:message` OpenAI chunk → `[DONE]`）
- 知识库：`/idx-gateway-doc/update|list/paging|delete` + `/gateway-doc/upload/{id}/mode/replace`（multipart）
- MCP（http 型）：`/ai-gateway-mcp/*`、`/ai-gateway-endpoint/*`、`/ai-gateway-clue/*`
- 鉴权：`Authorization: Bearer <o2AiToken>`

OpenClaw / Hermes 都是 OpenAI 兼容、不能直连 O2OA 私有协议，接它们也得先过适配层。
**当前后端为官方 llama.cpp standalone（ROCm）**：聊天 `127.0.0.1:8088`、嵌入 `127.0.0.1:8089`，
覆盖网关所需的 `/v1/chat/completions` + `/v1/embeddings` 全部能力，故无需装第三方网关。
（早期曾用 LM Studio/Bionic headless :8090，已被官方 llama-server 取代，见 §11。）

### 交付物（`D:\O2OA\gateway\`）
- `o2_agent_gateway.py` —— FastAPI 适配网关（~750 行）：O2OA 私有协议 ⇄ 本地推理后端 OpenAI API
  - 四类能力：chat / rag（SQLite 向量余弦检索，embedding 走 embed_base）/ kb 索引 / mcp(http 型 tools 循环)
  - 鉴权头是 **`Authorization: Bearer <token>`**（不是 `x-token`）；错/缺 → 401
  - **路由无 `/app/api` 前缀**：O2OA 用 `o2AiBaseUrl + 路径` 拼 URL（默认 base 虽含 `/app/api`，
    但我们覆盖为纯 host:port，已核实 `ActionChat`/`QueueDocumentIndex` 源码）
- `config.json` —— token=`local-o2-agent-2026`；`bionic_base`=`http://127.0.0.1:8088`（官方 llama-server 聊天）、`embed_base`=`http://127.0.0.1:8089`（官方 llama-server 嵌入）；`chat_model=qwen3.5-4b`；`embed_models=["qwen3-embed"]`
  - ⚠️ `bionic_base` 与 `embed_base` **必须分离**：官方 llama-server 一次只能服务一种模式，聊天/嵌入是两个进程。
  - ⚠️ `config.json` 的 token 必须与 `o2_gw_cfg.js` 的 `GW_TOKEN` 一致，否则 O2OA 侧 401。
- `o2_gw_cfg.js` —— 把 O2OA AI 配置指向网关：`o2AiEnable=true`、o2AiBaseUrl=`http://192.168.1.5:18790`、o2AiToken 与 `config.json` 一致，POST `/jaxrs/config/save`
- `build_llama_standalone.sh` —— 组装官方 llama.cpp standalone 运行目录（幂等，见 §11）
- `start_llama.bat` —— 启动两个官方 llama-server 进程（:8088 聊天 / :8089 嵌入，ROCm offload），**完全不依赖 Bionic/LM Studio**
- `start_ai_stack.bat` —— 一键 `start_llama.bat` + `start_gateway.bat`
- `start_gateway.bat` —— 双击启动网关（托管 venv python，监听 0.0.0.0:18790）
- `ai_smoke.js` —— 端到端冒烟（登录→经 9090→统计 content 分片），输出 `{"ok":true}`
- `gw_test.py` —— chat/rag/mcp 自检

### 配置 O2OA 指向网关
```javascript
// gateway/o2_gw_cfg.js：先 GET 完整配置 → 改三字段 → POST /jaxrs/config/save
// 验证回读：o2AiEnable=true | baseUrl=http://192.168.1.5:18790 | token=(已设置)
```
⚠️ 保存路由是 `POST /jaxrs/config/save`（**不是** update；update/model 只针对模型条目）。

### 网络白名单（容器 → 网关）
`o2oa_netlock.sh` 已内置 18790 放通（在 DROP **之前**）：
```bash
iptables -I FORWARD 1 -s <容器IP> -d 192.168.1.5 -p tcp -m multiport --dports 1234,18790 \
  -m comment --comment 'o2oa-netlock-allow' -j ACCEPT
```
重跑 `bash o2oa_netlock.sh` 生效；Docker 重启 / 容器重建后需重跑。

### 启动与验收
```bash
# 1. 启动网关（常驻，否则 AI 全不可用）
D:\O2OA\gateway\start_gateway.bat
curl http://127.0.0.1:18790/gateway/health      # {"status":"ok",...}

# 2. 端到端（经 O2OA 9090，会回源到网关再调本地推理后端）
TOKEN=$(curl -s -X POST http://127.0.0.1:9090/x_organization_assemble_authentication/jaxrs/authentication \
  -H 'content-type: application/json' -d '{"credential":"xadmin","password":"o2oaadmin2026"}' \
  | node -e "process.stdin.on('data',d=>console.log(JSON.parse(d).data.token))")
curl -sN -X POST http://127.0.0.1:9090/x_ai_assemble_control/jaxrs/chat/completion \
  -H "x-token: $TOKEN" -H 'content-type: application/json' \
  -d '{"input":"用一句话解释防火墙","generateType":"chat"}'
# 期望：event:status → event:message OpenAI chunk 流
```

### 关键决策
- 智能体开关（§9）只解锁菜单；**真正可用靠本网关**。两者配合：开关开 + baseUrl/token 指向网关。
- 网关必须常驻：宿主重启后会丢，需用 `start_gateway.bat` 重新拉起（可串进 O2OA 启动脚本）。
- 不装 OpenClaw/Hermes：本地后端已覆盖推理 + 向量 + 重排全能力，适配层成本远低于再引入一个网关。

---

## 11. ★ 用本机 GGUF 驱动、完全脱离 Bionic（官方 llama.cpp standalone）

**用户常见问法**："我在 D:\llm_models 下了 qwen3.5-4b，能直接内置吗？能不依赖 Bionic（LM Studio）驱动吗？"
"官方 llama-server.exe 和 Bionic 功能一样吗？想下官方 standalone 版。"

### 三个必须先说清的事实
1. **O2OA「内置模型」是假象**：模型设置里"私有化模型"只是**配置指针**（存模型名 + `http://host:port/v1/chat/completions`）。
   O2OA 自身**没有任何推理引擎**，不会去读 GGUF。必须有独立进程把模型跑起来暴露 OpenAI 接口。
2. **"Bionic" 就是 LM Studio 的品牌版**：`~/.lmstudio/.internal/*.json` 里 `"path":"C:\\Program Files\\Bionic\\Bionic.exe"`，
   且有 `~/.lmstudio/apps/bionic/`。"脱离 Bionic" 实际是"脱离其 GUI 进程"。
3. **功能等价性**：网关只用 `/v1/chat/completions` + `/v1/embeddings` 两个端点（`grep` 可验证，rerank 用量为 0）。
   官方 llama-server 支持这两者且更全（`/v1/rerank`、tool calling、grammar、vision 实验性等），
   **换引擎零能力损失**。结论：完全可独立，且推荐官方版。

### ★★ 关键坑：官方 Windows release 的 llama-server.exe 开箱跑不起来（0xC0E90002）
从 ggml-org/llama.cpp 下 `llama-b11046-bin-win-{rocm,cpu,vulkan}-x64.zip` 解压后直接运行：
```
llama-server.exe --version   →  退出码 -1058471934 = 0xC0E90002 (SxS 激活上下文构建失败)
```
stdout/stderr **全空**，且**会弹 Windows 错误对话框把进程挂死**（`timeout`/`WaitForExit` 都无效，
必须 `taskkill /F /IM llama-server.exe` 才能清）。

**对照实验（决定性，务必照此判据）**：

| 组合 | 结果 |
|---|---|
| 官方 rocm / cpu / vulkan 包（b11046 原样） | ✗ 全部 0xC0E90002 |
| 官方 cpu 包（b11045） | ✗ 0xC0E90002 |
| LM Studio 自带后端目录（llama.cpp 2.33.0） | ✓ `status=0`，`version: 0.3.0-dev (build 1, commit 0f3a71b)` |
| LMS 全部 DLL + **官方 exe** | ✓ **`status=0`（突破口：官方 exe 本身是好的）** |
| LMS DLL + 官方 exe + 官方 impl.dll | ✗ 0xC0000135（缺 `ggml.dll`，LMS 版 impl 不需要它） |
| 官方 exe+impl + 官方 ggml.dll | ✗ 0xC0000139（ENTRYPOINT_NOT_FOUND，混搭符号不匹配） |

**根因**：官方包内 **DLL 系（`ggml-base.dll`/`ggml-hip.dll` 等）与官方 exe 组合时激活上下文构建失败**，
是**官方 Windows release 的打包缺陷**（b11045/b11046、三个后端皆然），**不是本机环境问题，也不是缺 VC 运行库**
（System32 的 `vcruntime140.dll`/`msvcp140.dll`/`vcruntime140_1.dll` 与 LMS 自带版 **md5 完全相同**）。

### ★ 可用方案（已实测落地）
**官方 `llama-server.exe` + LM Studio 那套已验证 DLL + ROCm vendor 运行时**（共 21 个文件）。
用现成脚本组装（幂等、可重跑）：
```bash
bash D:/O2OA/gateway/build_llama_standalone.sh   # → D:\O2OA\llama.cpp\standalone\
```
来源：
- `~/.lmstudio/extensions/backends/llama.cpp-win-x86_64-amd-rocm-avx2-2.33.0/*.dll`（核心）
- `~/.lmstudio/extensions/backends/vendor/win-llama-rocm-vendor-v6/bin/`（`amdhip64_7.dll`、`libhipblas.dll`→脚本**自动改名 `hipblas.dll`**、`rocblas.dll`+`rocblas/`）
- 官方包**只取 `llama-server.exe`**

★ **脚本已自带改名**（2026-09-19 补齐，此前是手工组装因此漏写）：跑完会打印
`↳ libhipblas.dll → hipblas.dll (满足 ggml-hip.dll 的硬依赖)`，输出约 22 项（多出的 `libhipblas.dll`
原件冗余无害）。**若你手工组装而跳过这一步 → 运行即 0xC0000135。**

**缺一不可的两个陷阱**：
- `ggml-hip.dll` 硬依赖名为 **`hipblas.dll`**（而 vendor 目录里叫 `libhipblas.dll`）→ 必须复制一份改名。
- 必须用 LMS 的单文件 **`ggml-cpu.dll`**，**不能**换成官方包的 `ggml-cpu-{zen4,haswell,...}.dll` 微架构分片（否则混合加载报 `0xC0000139` ENTRYPOINT_NOT_FOUND）。

**自足性验证**（换目录重跑一遍，确认不依赖上一次的产物）：
```bash
bash D:/O2OA/gateway/build_llama_standalone.sh /c/temp/llama_repro
cd /c/temp/llama_repro && ./llama-server.exe --list-devices   # 应仍见 ROCm0: 8060S
```

### 启动（聊天与嵌入必须分两个进程）
```bat
:: 聊天 :8088（ROCm 全量卸载 -ngl 999）
llama-server.exe -m <Qwen3.5-4B.gguf> -c 8192 -ngl 999 --host 127.0.0.1 --port 8088 ^
  --jinja --alias qwen3.5-4b --no-webui
:: 嵌入 :8089（--embedding 必须显式开启）
llama-server.exe -m <Qwen3-Embedding-0.6B.gguf> -c 2048 -ngl 999 --host 127.0.0.1 --port 8089 ^
  --embedding --pooling last --alias qwen3-embed --no-webui
```
一键脚本：`gateway/start_llama.bat`。

### 验证证据（实测）
```bash
cd D:/O2OA/llama.cpp/standalone && ./llama-server.exe --list-devices
#  ROCm0: AMD Radeon(TM) 8060S Graphics (110456 MiB, 110301 MiB free)   ← ROCm 生效
curl -s --noproxy '*' http://127.0.0.1:8088/health          # {"status":"ok"}
curl -s --noproxy '*' http://127.0.0.1:8089/v1/embeddings -H "Content-Type: application/json" \
     -d '{"model":"qwen3-embed","input":"测试"}'            # 1024 维向量
```
实测聊天：回答正确，`prompt 289.9 tok/s`、`generation 43.2 tok/s`（GPU 级速度），
响应含 `system_fingerprint:"b1-0f3a71b"`（官方构建标识）。

### ⚠️ 健康探测别踩坑（路径 + 鉴权头）
| 目标 | 正确写法 |
|---|---|
| llama-server 聊天 / 嵌入 | `GET http://127.0.0.1:8088/health`、`:8089/health`（无鉴权） |
| **网关** | `GET http://127.0.0.1:18790/gateway/health` + 头 **`Authorization: Bearer <token>`** |
| O2OA 前端 | `GET http://localhost:9090` → 200 |

**网关根路径 `/` 与 `/health` 都返回 `{"detail":"Not Found"}`**，别据此判定网关挂了。
网关鉴权头是 `Authorization: Bearer`，**不是 `x-token`**（后者返回 `{"type":"error","message":"bad token"}`）。

### 排查手法（可复用）
- 退出码换算：`printf '0x%X\n' $(( (-1058471934) & 0xFFFFFFFF ))` → `0xC0E90002`。
  `0xC0000139`=ENTRYPOINT_NOT_FOUND，`0xC0000135`=DLL 缺失，`0xC0000005`=访问冲突。
- 逐个 `LoadLibraryExW(path, 0, LOAD_WITH_ALTERED_SEARCH_PATH)` 定位失败 DLL。
  ⚠️ `0x11C7`（ERROR_SXS_CANT_GEN_ACTCTX）常是**内层加载失败的转述**，未必真是 manifest 问题。
- 提取/核对 manifest：`mt.exe -inputresource:x.dll;#2 -out:m.xml`
  （`mt.exe` 在 `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\`）。
- **必须抑制错误对话框**：`SetErrorMode(1|2|0x8000)` / `SetThreadErrorMode`，否则失败进程永久挂起。
- ⚠️ **不要用 `node -e` 内联含反斜杠的 Windows 路径**——bash 会把 `\\O` 吞成 `\O`，
  报 `ENOENT` 把你带偏。写成 `.js` 文件执行。
- ⚠️ **PowerShell 工具在部分会话会静默不执行脚本**（exit 0 但无副作用）→ 优先 bash 直调 `mt.exe`，或写到文件再读。
- `MSYS_NO_PATHCONV=1 taskkill /F /IM llama-server.exe`（用 `//F` 会报"无效参数"）。

---

## 12. ★ RAG 500 坑与推理模型配置（换 Qwen3.5 后才暴露）

### RAG `System message must be at the beginning`
- 症状：RAG 模式报 `Jinja Exception: System message must be at the beginning`。
- 根因：网关 RAG 分支**新增了第二条 `system` 消息**（把检索上下文作为新 system 追加）。
  Qwen3.5 的 chat template 强制 **system 只能出现在最前且至多一条**；glm-4.7-flash 模板宽松所以一直没暴露。
- 修复：**RAG 上下文合并进首条 system**，绝不新增 system（见 `o2_agent_gateway.py` generate 内注释）。
- 通用律：任何多轮/多来源拼 prompt，都要保证 `system` 唯一且在最前，`history` 为 user/assistant 交替。

### 推理模型必配 `reasoning_effort:"none"`
qwen3.5-4b 等推理模型默认把 token 全花在 `reasoning_content`，正文 `content` 为空、`finish_reason=length`。
请求体加 `"reasoning_effort":"none"` 后正文正常（网关 `stream_openai` 已内置）。`/no_think` 之类的 prompt 提示不可靠。

### 网关鉴权的两个易错点
- 鉴权头是 **`Authorization: Bearer <token>`**，**不是 `x-token`**（`check_token()` 用
  `request.headers.get("authorization").endswith(CFG["token"])`）。
- `config.json` 的 `token` 必须与 `gateway/o2_gw_cfg.js` 的 `GW_TOKEN` **一致**，否则 O2OA 侧会 401。
- 所有 127.0.0.1 的 curl **必须加 `--noproxy '*'`**，否则被系统代理拦截返回 502。

---

## 13. ★ 升级保证：O2OA 升级后 AI 智能体如何继续可用

用户最易踩的坑：**升级会丢掉 AI 相关的三样东西**，必须靠"重放 + 自愈"兜底。

### 升级会丢什么（按风险）
1. **`o2oa_netlock.sh` 的 18790 白名单** —— 宿主 iptables，Docker Desktop 重启 / 容器重建即丢。
   容器→网关 18790 不通 → AI 全部 502/超时。
2. **O2OA AI 配置**（`o2AiEnable`/`o2AiBaseUrl`/`o2AiToken`）—— 存库，升级若重置则网关失联。
3. **`ActionChat` 推理补丁**（`patch/ai/`）—— 原打在运行中容器 `work/` 目录 class 上，
   `docker compose up -d --force-recreate` 重解包 war 即覆盖；重建镜像更会彻底丢失。
   （该补丁只服务「禁用网关、直连本地模型」的兜底路径，网关路径不需要它。）

### 保证机制（已落地，全部幂等）
**① 升级后自愈脚本 `D:\O2OA\reassert_ai_after_upgrade.sh`**（+ `reassert_ai_after_upgrade.bat` 双击入口）：
五步全部幂等 —— ⓪ 探测/拉起本地推理后端（官方 llama-server :8088 聊天 + :8089 嵌入）→
① 网关进程不在就拉起 → ② 重放 `o2oa_netlock.sh`（恢复 18790）→
③ `node gateway/o2_gw_cfg.js` 把 O2OA 配置重指网关 → ④ `node gateway/ai_smoke.js` 端到端冒烟
（经 9090→网关→本地推理后端 断言 content>0）；若冒烟失败且网关健康，自动 `bash patch/ai/patch_ai_nothink.sh apply`
补打推理补丁并复测。

**② 接进升级流水线**：`upgrade_o2oa.sh` 第 9 步自动调用 `reassert_ai_after_upgrade.sh`，
每次升级重建容器后自动完成 AI 自愈，不阻断主流程（MySQL 验证失败也不影响它跑）。

**③ 推理补丁烤进镜像（兜底路径彻底固化）**：Dockerfile 加 `python3` + COPY `patch/ai/`，
在构建期内联把 `reasoning_effort` 补丁写进 `store/x_ai_assemble_control.war`
（整段 `RUN <<'AISCRIPT'` 用 `set +e` 包裹，python3 缺失 / 新版 class 结构已变 → 仅告警 exit 0，
绝不阻断构建）。这样即使只 `force-recreate` 而不跑 reassert，本地模型兜底路径的补丁也还在。

### 用户操作清单（升级 / 重启后）
- **标准升级**：双击 `upgrade_o2oa.bat` 一步到位（含 AI 自愈第 9 步）。
- **仅 Docker 重启 / 手动 force-recreate 后**：双击 `reassert_ai_after_upgrade.bat` 补跑自愈。
- **网关进程随宿主重启丢失**：先双击 `gateway/start_gateway.bat`，再跑 reassert。
- **判定 AI 是否真可用**：`node gateway/ai_smoke.js` 看是否输出 `"ok":true`（content 分片>0）。

### 仍要注意
- 网关 `o2_agent_gateway.py` 是**宿主进程**，与 O2OA 版本无关——它实现的是 O2OA 10.0.2 私有
  网关协议契约。若未来大版本（如 10→11）改了 `/ai-gateway-*` 协议，网关需相应适配；
  小版本（10.0.x）契约稳定。reassert 的冒烟步骤能在升级后第一时间暴露契约不匹配。
- 升级若改了 `ResourceFactory` / `Config.externalDataSources` 结构，数据源补丁会失败中止
  （见 §升级重放机制 skill），那是另一回事，不影响上面 AI 自愈逻辑本身。

---

## 14. ★ 能力扩展（多模态 / 内置工具 / OCR）—— 见姊妹 skill

网关在 2026-09-19 完成三项能力扩展，**详细做法已拆到独立 skill**（本 skill 只留索引）：

| 能力 | 一句话 | 详见 |
|---|---|---|
| **多模态（视觉）** | llama-server 加 `--mmproj <mmproj-*.gguf>` → `/props` 的 `modalities.vision=true`。**图片只能进 user 消息**（Qwen3.5 模板对 system 含图会 `raise_exception`）。网关把 `referenceIdList` 的附件 ID 经 `GET /x_ai_assemble_control/jaxrs/file/{id}/download` 取回（用 manager token 可下任意附件），图片转 `image_url`，其它走文本提取。 | §12 本文 + `o2oa-local-ocr-service` |
| **内置工具** | 网关自带 6 个工具（`kb_search` / `get_current_time` / `calc` / `search_org` / `list_my_todo` / `query_data`），与 O2OA 的 HTTP 型 MCP 工具合并注入。**注意：工具循环只在 `generateType == "mcp"` 时触发**（`chat`/`rag` 模式不注入 tools）。 | 本文 §10 |
| **OCR（扫描件/表格/PDF）** | 独立进程 `:8091`（RapidOCR ONNX，纯 CPU **零显存**）。网关两处接入：对话附件 + 知识库索引。 | **`o2oa-local-ocr-service` skill** |

### 两个排障利器（新增接口）

```bash
# 一屏看清所有能力是否都 up —— 升级/排障首选
curl -H "Authorization: Bearer <token>" http://127.0.0.1:18790/gateway/capabilities
# → chat_backend{tool_calls,vision,video} / embed_backend / ocr / builtin_tools / config

# 验证附件→文本提取链路（不必真在 O2OA 前端上传）
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"path":"D://xx//a.pdf"}' http://127.0.0.1:18790/gateway/ocr-test
```

### ★ 新增的坑（本文之外）

1. **同名函数覆盖**：网关里 `extract_text` 曾有两个定义（3参数=对话 / 2参数=索引），
   Python 后者覆盖前者 → 对话侧报 `takes 2 positional arguments but 3 were given`。
   索引版已改名 `extract_text_index`。**改此文件别起同名函数。**
2. **工具循环的触发条件**：请求体的 `generateType` 必须是 `"mcp"`，否则只走普通对话。
   自测时忘传这个字段会误以为"工具失效"。
3. **`spawn(detached:true).unref()` 不常驻**：网关进程会随调用方 shell 结束被回收，
   需用后台任务机制。停网关按端口找 PID 时，别用 `cmd findstr`（Git Bash 转义地狱），
   改用 Node 解析 `netstat -ano -p tcp`。
