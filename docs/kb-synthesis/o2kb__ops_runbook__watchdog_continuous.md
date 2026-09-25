# AI栈看门狗持续化运行手册（摘要）

> category: o2kb::ops_runbook  |  id: o2kb::ops_runbook::watchdog_continuous

持续化唯一机制 = 看门狗常驻 + 开机自启 VBS，全部代码纳管于 git，可随分支打包复现。

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

分支打包：git checkout -b feature/o2oa-ai-stack → git add gateway/ docs/ tools/ → commit；恢复时把 gateway/autostart/*.vbs 放到 Startup\ + 双击 start_ai_watchdog.bat。
完整版见 docs/AI栈看门狗持续化运行手册.md。
