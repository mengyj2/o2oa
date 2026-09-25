@echo off
chcp 65001 >nul 2>nul
REM ============================================================================
REM 重启 O2OA AI 网关（强制重载最新代码）
REM
REM 死结根因：旧网关 python 进程一直占着 18790 端口；看门狗检测到端口已占用就跳过，
REM 于是【旧代码（无 clueId 兜底）继续运行】，聊天历史永远存不下来。无论双击多少次 start_o2oa.bat 都无效。
REM
REM 本脚本：① 按命令行精准结束旧的 网关 + 看门狗 python 进程
REM           ② 按端口 18790 兜底再杀一次（双保险）
REM           ③ 拉起干净的新看门狗 → 新看门狗首轮自动释放 18790 并加载【最新】网关代码
REM 仅结束网关/看门狗，不影响 LM Studio 的 llama-server.exe。
REM ============================================================================
set "PY=C:/Users/meng_/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
set "HERE=%~dp0"

echo [1/3] 结束旧的看门狗/网关进程（按 pid 文件 + 命令行双保险，隐藏窗口）...
powershell -NoProfile -WindowStyle Hidden -Command "$k=@(); try { $wp=Get-Content '%HERE%watchdog.pid' -Raw -ErrorAction SilentlyContinue; if($wp -match '\d+'){ Stop-Process -Id ([int]$Matches[0]) -Force -ErrorAction SilentlyContinue; $k+='pidfile='+$Matches[0] } } catch {}; $ps=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*o2_agent_gateway.py*' -or $_.CommandLine -like '*watchdog_ai_stack.py*' }; if($ps){ foreach($p in $ps){ try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; $k+='cmd='+$p.ProcessId } catch {} } }; ('[restart] killed: '+($k -join ',')) | Out-File -Append '%HERE%watchdog.log' -Encoding utf8"

echo [2/3] 按端口 18790 兜底清理（双保险）...
powershell -NoProfile -WindowStyle Hidden -Command "$ids=(Get-NetTCPConnection -LocalPort 18790 -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique; if($ids){ foreach($id in $ids){ if($id){ try { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Write-Host ('  freed port 18790, killed PID '+$id) } catch {} } } } else { Write-Host '  18790 已空闲' }"

timeout /t 3 >nul

echo [3/3] 隐藏拉起修复版看门狗（无黑窗口，自动加载最新代码 + 释放旧端口）...
REM 清除可能污染 localhost 调用的系统代理
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="
cd /d "%HERE%"
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%PY%' -ArgumentList '%HERE%watchdog_ai_stack.py' -WindowStyle Hidden -WorkingDirectory '%HERE%'"

echo.
echo [完成] 看门狗已隐藏启动（无黑窗口）。约 10~30 秒后网关就绪。
echo [验证] 打开 O2OA AI 助手聊一句：左侧「历史」应立刻出现新会话，刷新仍在、点开可见完整问答。
echo [注意] 当前 chat 走 GLM@1234，请保持 LM Studio 的 glm-4.7-flash 常驻。
timeout /t 4 >nul
