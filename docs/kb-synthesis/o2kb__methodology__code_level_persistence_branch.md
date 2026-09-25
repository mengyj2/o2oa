# 代码级持久化与分支打包方法

> category: o2kb::methodology  |  id: o2kb::methodology::code_level_persistence_branch

把「目前运行的 AI 栈」做成可随时打包的成分支的方法（对接用户"用看门狗持续化、代码级、未来打包成分支"的要求）：

1. 所有有效修改落为代码，而非仅靠会话存活。注意：沙箱 Bash 起的进程在回合结束被 Windows Job Object 整树回收，因此"常驻"只能由用户侧完成（双击 bat / 登录自启 VBS）；AI 助手负责把代码写对、验证通过，并把启动权交给看门狗。

2. 自启 VBS 的权威源放进仓库 gateway/autostart/（纯 ASCII + CRLF，绝无中文），%Startup% 仅放副本；改 VBS 改仓库那份并重新复制到 Startup。

3. 看门狗作为持续化唯一锚点：单例锁(watchdog.pid) + 安全探活(ctypes，非 os.kill) + 组件崩溃自动拉起。

4. 知识库 data.db 入库：含 -wal 时先 `PRAGMA wal_checkpoint(TRUNCATE)` 合并，再 git add；data.db 已纳入 .gitignore 白名单（仅忽略 -wal/-shm）。

5. 统一在专属分支提交：git checkout -b feature/o2oa-ai-stack → add gateway/ docs/ tools/ → commit。使 clone 后"放 VBS + 双击 bat"即可复现当前运行态。

6. 所有对话思考/方法/技巧/思路写入本地知识库 data.db（见 tools/ingest_conversation_kb.py），使其可被 RAG 检索、随分支带走。
