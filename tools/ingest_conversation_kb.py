# -*- coding: utf-8 -*-
"""
将「O2OA AI 栈」全程对话沉淀的方法/技巧/思路/坑与修法 灌入本地知识库 data.db。
- 落盘：docs/kb-synthesis/<id>.md
- 入库：POST /idx-gateway-doc/update（网关自动切块+向量化，需 embed@8089 在线）
- 鉴权令牌从 gateway/config.json 的 "token" 字段运行时读取，不硬编码、不回显。
幂等：同 id 重复运行 = upsert。
"""
import json, os, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY_DIR = os.path.join(HERE, "..", "gateway")
CFG = json.load(open(os.path.join(GATEWAY_DIR, "config.json"), encoding="utf-8"))
TOKEN = CFG["token"]
PORT = CFG.get("listen_port", 18790)
# 始终连本机回环；listen_host 可能为 0.0.0.0（监听所有网卡，但不可作为连接目标）
BASE = f"http://127.0.0.1:{PORT}"
KB_DIR = os.path.join(HERE, "..", "docs", "kb-synthesis")
os.makedirs(KB_DIR, exist_ok=True)

DOCS = [
    dict(
        id="o2kb::methodology::ai_stack_troubleshooting",
        title="AI栈排障总方法论",
        category="o2kb::methodology",
        content="""O2OA AI 栈（网关18790 / embed8089 / ocr8091 / LM Studio聊天1234 / O2OA9090）的通用排障顺序：

1. 分层定位：端口 → 进程 → 日志 → 依赖服务。先 curl --noproxy "*" 探各端口 HTTP 码，再 tasklist 看 python 进程，最后看 watchdog.log / gateway.log / llama_*.log。
2. 端口全绿 ≠ 可用：必须做一次端到端 SSE 真实对话（/ai-gateway-completion/generate）验证，且 RAG 问题要能引用资料。
3. 进程存活 ≠ 健康：看门狗必须做 HTTP 探活（GET /health 返 200），而非仅 pid 存活。
4. Windows 探活陷阱：os.kill(pid,0) 实为 TerminateProcess(pid,0)，会直接杀目标。安全做法是 ctypes.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)+GetExitCodeProcess 仅查询不终止。
5. 代理劫持：本地探测一律 curl --noproxy "*"；否则 shell 注入的 HTTPS_PROXY(如52068) 会把 localhost 请求转代理伪装 502。Python httpx 用 trust_env=False。
6. docker exec 在 ARM64+QEMU 常因 setns 失败（OCI runtime exec failed: fork/exec /proc/self/fd/6），改用 docker cp / HTTP / 临时容器 docker run -v <volume>。
7. 进程回收：沙箱 Bash 起的进程（含 DETACHED_PROCESS）会话结束被 Job Object 整树回收；常驻只能由用户侧完成（双击 bat / 登录自启 VBS）。schtasks / WMI Win32_Process.Create / Start-Process 均被安全策略拦截。
8. 善用 GET /gateway/capabilities（带 Authorization 令牌）确认新工具（design_op/kb_reflect/growth_report 等）已注册，用 status 帧确认对话流未卡死。""",
    ),
    dict(
        id="o2kb::troubleshooting::vbs_autostart_800A01A8",
        title="自启VBS报错800A01A8（缺少对象 'sh'）",
        category="o2kb::troubleshooting",
        content="""症状：%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\O2OA_AI_stack_autostart.vbs 在登录/双击时报「800A01A8 缺少对象 'sh'」，且行号错位（实际指 sh.Run 那行），AI 栈开机后根本没被拉起。

根因：VBS 以 UTF-8 无 BOM + 中文注释 + LF 行尾保存。Windows Script Host 按 ANSI/GBK 解析，中文多字节高位字节会吞掉其后的换行符，使 `Set sh = CreateObject(...)` 那一行被并入上一行注释而未执行；后续 `sh.Run ...` 引用 sh 时对象不存在即报 800A01A8，且因换行被吞行号整体错位（如报第7行）。

修复（编码层面免疫）：整文件改写为纯 ASCII 注释 + CRLF。验证：`file` 显示 "ASCII text, with CRLF"；`grep -P '[\\x80-\\xFF]'` 非 ASCII 字节扫描为空。永不在此文件写中文。自启 VBS 的权威源应放进仓库 gateway/autostart/，Startup 仅放置副本。""",
    ),
    dict(
        id="o2kb::troubleshooting::watchdog_pid_alive_terminateprocess",
        title="看门狗探活误杀组件（os.kill 陷阱）",
        category="o2kb::troubleshooting",
        content="""症状：网关/embed 在日志里反复 DOWN → 重新拉起 → 再 DOWN（9/21 抖动特征），但无 Python traceback，进程是被外部杀掉而非自崩。

根因：watchdog_ai_stack.py 的 pid_alive() 用 `os.kill(pid, 0)` 检测存活。在 Windows 上该调用底层走 `TerminateProcess(pid, 0)`，会直接终止目标进程——并非"仅检测"。当组件（如 embed 加载 qwen3-embed 模型）端口暂未就绪时，看门狗"探活"恰好把正在加载的组件杀掉，再 sleep 60s、判未就绪、下轮重启，形成 DOWN→重启 死循环。

修复：改用 ctypes 安全探活——
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return code != STILL_ACTIVE 判定
仅查询不终止。单测验证：对 sleeper 连续检测不杀进程；死 PID / 空 PID / 假 PID(999999) 均正确返回 False。修复后约 26 小时零抖动。""",
    ),
    dict(
        id="o2kb::troubleshooting::watchdog_singleton_lock",
        title="看门狗单例锁防双击互杀",
        category="o2kb::troubleshooting",
        content="""症状：开机自启 + 手动双击 bat 同时运行，两个看门狗实例互相 free_port 杀掉对方的网关，日志剧烈抖动、端口反复横跳。

修复：看门狗启动即写 `watchdog.pid`（必须用服务自身 `os.getpid()` 写，因为 venv 的 python.exe 是重定向器，Popen(...).pid 拿到的是重定向器而非真实解释器，会写出错 PID 导致 stop/清理杀错进程）。第二实例启动时检测该 pid 存活则打印「已有看门狗在运行」并立即 sys.exit()。

关键顺序：在写单例锁之前，必须先 `taskkill /PID <各 .pid 文件中的值> /F /T` 清理上一登录遗留的陈旧进程，否则新看门狗会因锁存在而退出、却留下旧看门狗继续存活（自启 VBS 已处理：启动前依次 KillByPidFile watchdog/gateway/ocr/embed/chat/rerank.pid）。""",
    ),
    dict(
        id="o2kb::troubleshooting::proxy_hijack_noproxy",
        title="本地探测代理劫持（curl 假 502）",
        category="o2kb::troubleshooting",
        content="""症状：curl http://127.0.0.1:9090 / 18790 等本地地址返回 502，但服务实际在跑。

根因：shell 环境注入了 HTTP(S)_PROXY（本机曾见 52068 端口的代理），curl 默认把 localhost 请求也发往代理，代理连不上本地服务即返 502。

修复：
- 所有本地探测加 `--noproxy "*"`：curl --noproxy "*" -s -o /dev/null -w "%{http_code}" http://127.0.0.1:PORT/
- Python httpx：Client(trust_env=False) 或 proxy=None
- 看门狗/网关启动脚本开头 unset 全部代理变量：HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= ALL_PROXY= all_proxy= no_proxy="*"
- 判定"服务假死"前先排除代理干扰，避免误判为代码崩。""",
    ),
    dict(
        id="o2kb::architecture::gateway_rag_kernel",
        title="网关内置RAG内核复用",
        category="o2kb::architecture",
        content="""O2OA AI 网关 o2_agent_gateway.py 已内建 RAG 内核，无需另起向量库即可让 AI 具备本地检索学习能力：

存储：SQLite data.db
- docs 表：id, title, category, content, creator_person, creator_unit, question_enable, permission, meta
- chunks 表：doc_id, seq, text, embedding(BLOB, qwen3-embed 维度)

向量化：embed() 调 qwen3-embed @8089；检索 rag_retrieve() 带 rerank @8092 融合重排。

入库通道（推荐）：POST /idx-gateway-doc/update
- 鉴权：Authorization 头 = config.json 的 token（无 Bearer 前缀）
- body：{"id","title","category","content","permissionList":[]}
- 内部 ON CONFLICT(id) DO UPDATE 幂等 upsert，随后 reindex_doc() 自动切块+调 embed+写 chunks

分类用多层命名空间 category 字段，例如 o2oa_manual / o2oa_api / o2oa_ops / o2oa_version / ops_experience / ai_synthesis / o2kb::methodology 等。permissionList=[] 即全员可见。复用此内核即可让 AI 在对话中 RAG 本地 O2OA 资料。""",
    ),
    dict(
        id="o2kb::architecture::multilayer_memory_growth",
        title="多层记忆与成长感知体系",
        category="o2kb::architecture",
        content="""为让本地 O2OA AI 持续成长、可沉淀组织知识，构建三层能力：

一、多层记忆 taxonomy（category 命名空间）
- L0 对话上下文 → L1 ops_experience（操作经验/问题解决）→ L2 o2oa_manual/api/ops/version（说明书/接口/运维/版本）→ L3 business_process（SOP）→ L4 ai_synthesis（AI 合成结论）。

二、成长感知闭环（三工具，均在 analyst/manager 角色下）
- kb_ingest：把文档/经验持续入库 data.db
- kb_reflect(topic, confirm)：把零散经验合成为 SOP。confirm=false 只出提案（CONFIRM_REQUIRED）不写；confirm=true 落 o2kb::ai_synthesis::reflect_<timestamp>
- growth_report：读 growth_ledger 表，输出能力成长账本

三、设计态四层安全闸（让 AI 能建/改流程表单应用但有护栏）
1. 角色闸：analyst/manager 白名单（由 editable() 锚定）
2. 草稿不落地：confirm=false 只出提案，不写任何业务数据
3. 过程授权：人类在对话里确认即视为授权
4. 快照+审计+可回滚：design_op 执行前留快照，design_rollback 可回退
工具族：design_op / design_rollback（BUILTIN_TOOLS + exec_builtin 分发 + capabilities「设计态」分组）。""",
    ),
    dict(
        id="o2kb::ops_runbook::watchdog_continuous",
        title="AI栈看门狗持续化运行手册（摘要）",
        category="o2kb::ops_runbook",
        content="""持续化唯一机制 = 看门狗常驻 + 开机自启 VBS，全部代码纳管于 git，可随分支打包复现。

组件与端口：
- watchdog_ai_stack.py：持 watchdog.pid 单例锁，30s HTTP 探活，组件崩则脱离式重启
- 网关 o2_agent_gateway.py :18790
- 向量 embed（qwen3-embed）:8089
- OCR :8091
- 聊天后端 LM Studio（bionic_base=http://127.0.0.1:1234，qwen3.8-27b）
- O2OA :9090（docker）

操作：
- 启动：双击 gateway/start_ai_watchdog.bat（重复双击安全，单例锁拦截）
- 停止：删 watchdog.pid 后 Get-Process python | Stop-Process -Force
- 状态：for p in 18790 8089 8091 9090 1234; do curl --noproxy "*" -s -o /dev/null -w "%{http_code} " http://127.0.0.1:$p/; done
- O2OA 容器重启后必须 bash o2oa_netlock.sh 重跑断网隔离

分支打包：git checkout -b feature/o2oa-ai-stack → git add gateway/ docs/ tools/ → commit；恢复时把 gateway/autostart/*.vbs 放到 Startup\\ + 双击 start_ai_watchdog.bat。
完整版见 docs/AI栈看门狗持续化运行手册.md。""",
    ),
    dict(
        id="o2kb::architecture::o2oa_offline_localization",
        title="断云O2OA本地化部署定位",
        category="o2kb::architecture",
        content="""本机是 O2OA 社区版 10.0.2 断云（已断 collect.o2oa.net / app.o2oa.net / apppack）的「商业版平替」部署：

组织与账号：顶层组织中国复合材料工业协会；真实业务管理员 admin/o2oaadmin2026；虚拟 xadmin 同密码、tokenType=manager，但不在 ORG_PERSON、无 identity，不能当业务人员（却适合做批量运维改人）。

AI 全程不连云：推理走本地 LM Studio qwen3.8-27b @1234；向量 qwen3-embed @8089；OCR 用 RapidOCR 独立进程；网关端口 18790。

断云影响与对策：
- 应用市场/在线打包不可用 → 改离线 xapp 导入（setup.json + xapp zip）
- collect 上报失败 → 数据已落库可忽略
- express 注册查找偶发 randomWithWeight 错误 → docker restart o2oa-server 即愈（但需 5-8 分钟且重跑 o2oa_netlock.sh）
- 短信/邮件验证码已本地化（mailservice/ 平替 x_sms_assemble_control）

自建模块平替内置合同/业务/人力资源/公文/财务/资产管理等门户，要求打通底层数据层、真实渲染行数据，杜绝空壳或二级链接。""",
    ),
    dict(
        id="o2kb::methodology::code_level_persistence_branch",
        title="代码级持久化与分支打包方法",
        category="o2kb::methodology",
        content="""把「目前运行的 AI 栈」做成可随时打包的成分支的方法（对接用户"用看门狗持续化、代码级、未来打包成分支"的要求）：

1. 所有有效修改落为代码，而非仅靠会话存活。注意：沙箱 Bash 起的进程在回合结束被 Windows Job Object 整树回收，因此"常驻"只能由用户侧完成（双击 bat / 登录自启 VBS）；AI 助手负责把代码写对、验证通过，并把启动权交给看门狗。

2. 自启 VBS 的权威源放进仓库 gateway/autostart/（纯 ASCII + CRLF，绝无中文），%Startup% 仅放副本；改 VBS 改仓库那份并重新复制到 Startup。

3. 看门狗作为持续化唯一锚点：单例锁(watchdog.pid) + 安全探活(ctypes，非 os.kill) + 组件崩溃自动拉起。

4. 知识库 data.db 入库：含 -wal 时先 `PRAGMA wal_checkpoint(TRUNCATE)` 合并，再 git add；data.db 已纳入 .gitignore 白名单（仅忽略 -wal/-shm）。

5. 统一在专属分支提交：git checkout -b feature/o2oa-ai-stack → add gateway/ docs/ tools/ → commit。使 clone 后"放 VBS + 双击 bat"即可复现当前运行态。

6. 所有对话思考/方法/技巧/思路写入本地知识库 data.db（见 tools/ingest_conversation_kb.py），使其可被 RAG 检索、随分支带走。""",
    ),
]


def post_doc(d):
    payload = json.dumps({
        "id": d["id"], "title": d["title"], "category": d["category"],
        "content": d["content"], "permissionList": [],
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/idx-gateway-doc/update", data=payload,
        headers={"Authorization": TOKEN, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa
        return 0, str(e)


def main():
    ok = 0
    for d in DOCS:
        # 1) 落盘 markdown
        fn = os.path.join(KB_DIR, d["id"].replace("::", "__").replace("/", "_") + ".md")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"# {d['title']}\n\n> category: {d['category']}  |  id: {d['id']}\n\n{d['content']}\n")
        # 2) 入库 + 向量化
        st, body = post_doc(d)
        flag = "OK" if st == 200 else f"FAIL({st})"
        if st == 200:
            ok += 1
        print(f"[{flag}] {d['id']}  ->  {st} {body[:60]}")
    print(f"\n完成：{ok}/{len(DOCS)} 篇入库成功。markdown 落盘于 {KB_DIR}")


if __name__ == "__main__":
    main()
