# 看门狗单例锁防双击互杀

> category: o2kb::troubleshooting  |  id: o2kb::troubleshooting::watchdog_singleton_lock

症状：开机自启 + 手动双击 bat 同时运行，两个看门狗实例互相 free_port 杀掉对方的网关，日志剧烈抖动、端口反复横跳。

修复：看门狗启动即写 `watchdog.pid`（必须用服务自身 `os.getpid()` 写，因为 venv 的 python.exe 是重定向器，Popen(...).pid 拿到的是重定向器而非真实解释器，会写出错 PID 导致 stop/清理杀错进程）。第二实例启动时检测该 pid 存活则打印「已有看门狗在运行」并立即 sys.exit()。

关键顺序：在写单例锁之前，必须先 `taskkill /PID <各 .pid 文件中的值> /F /T` 清理上一登录遗留的陈旧进程，否则新看门狗会因锁存在而退出、却留下旧看门狗继续存活（自启 VBS 已处理：启动前依次 KillByPidFile watchdog/gateway/ocr/embed/chat/rerank.pid）。
