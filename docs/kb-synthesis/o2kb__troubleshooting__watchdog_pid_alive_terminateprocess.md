# 看门狗探活误杀组件（os.kill 陷阱）

> category: o2kb::troubleshooting  |  id: o2kb::troubleshooting::watchdog_pid_alive_terminateprocess

症状：网关/embed 在日志里反复 DOWN → 重新拉起 → 再 DOWN（9/21 抖动特征），但无 Python traceback，进程是被外部杀掉而非自崩。

根因：watchdog_ai_stack.py 的 pid_alive() 用 `os.kill(pid, 0)` 检测存活。在 Windows 上该调用底层走 `TerminateProcess(pid, 0)`，会直接终止目标进程——并非"仅检测"。当组件（如 embed 加载 qwen3-embed 模型）端口暂未就绪时，看门狗"探活"恰好把正在加载的组件杀掉，再 sleep 60s、判未就绪、下轮重启，形成 DOWN→重启 死循环。

修复：改用 ctypes 安全探活——
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return code != STILL_ACTIVE 判定
仅查询不终止。单测验证：对 sleeper 连续检测不杀进程；死 PID / 空 PID / 假 PID(999999) 均正确返回 False。修复后约 26 小时零抖动。
