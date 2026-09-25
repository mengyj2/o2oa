# AI栈排障总方法论

> category: o2kb::methodology  |  id: o2kb::methodology::ai_stack_troubleshooting

O2OA AI 栈（网关18790 / embed8089 / ocr8091 / LM Studio聊天1234 / O2OA9090）的通用排障顺序：

1. 分层定位：端口 → 进程 → 日志 → 依赖服务。先 curl --noproxy "*" 探各端口 HTTP 码，再 tasklist 看 python 进程，最后看 watchdog.log / gateway.log / llama_*.log。
2. 端口全绿 ≠ 可用：必须做一次端到端 SSE 真实对话（/ai-gateway-completion/generate）验证，且 RAG 问题要能引用资料。
3. 进程存活 ≠ 健康：看门狗必须做 HTTP 探活（GET /health 返 200），而非仅 pid 存活。
4. Windows 探活陷阱：os.kill(pid,0) 实为 TerminateProcess(pid,0)，会直接杀目标。安全做法是 ctypes.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)+GetExitCodeProcess 仅查询不终止。
5. 代理劫持：本地探测一律 curl --noproxy "*"；否则 shell 注入的 HTTPS_PROXY(如52068) 会把 localhost 请求转代理伪装 502。Python httpx 用 trust_env=False。
6. docker exec 在 ARM64+QEMU 常因 setns 失败（OCI runtime exec failed: fork/exec /proc/self/fd/6），改用 docker cp / HTTP / 临时容器 docker run -v <volume>。
7. 进程回收：沙箱 Bash 起的进程（含 DETACHED_PROCESS）会话结束被 Job Object 整树回收；常驻只能由用户侧完成（双击 bat / 登录自启 VBS）。schtasks / WMI Win32_Process.Create / Start-Process 均被安全策略拦截。
8. 善用 GET /gateway/capabilities（带 Authorization 令牌）确认新工具（design_op/kb_reflect/growth_report 等）已注册，用 status 帧确认对话流未卡死。
