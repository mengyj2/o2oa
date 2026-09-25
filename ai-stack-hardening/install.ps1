# install.ps1 — 将 ai-stack-hardening 分支部署到真实运行路径并重启看门狗（无窗）
# 以管理员 PowerShell 运行： cd D:\O2OA\ai-stack-hardening; .\install.ps1
$ErrorActionPreference = "Stop"

$PKG   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$GATE  = "D:\O2OA\gateway"
$DEPLOY= "D:\deploy_home_entry_local.ps1"
$START = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\O2OA_AI_stack_autostart.vbs"
$PY    = "C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

function Log($m){ Write-Host ("[install] " + $m) }

# 1) 复制分支文件到真实路径
Log "复制 gateway/* -> $GATE"
Copy-Item "$PKG\gateway\*" $GATE -Force -Recurse
Log "复制 deploy_home_entry_local.ps1 -> $DEPLOY"
Copy-Item "$PKG\deploy\deploy_home_entry_local.ps1" $DEPLOY -Force
Log "复制开机自启 VBS -> $START"
Copy-Item "$PKG\startup\O2OA_AI_stack_autostart.vbs" $START -Force

# 2) 按 pid 文件精准杀旧看门狗 + 各组件（含子进程 /T）
$ids = @()
'watchdog','gateway','ocr','embed','chat','rerank' | ForEach-Object {
  $pf = Join-Path $GATE ($_ + ".pid")
  if (Test-Path $pf) {
    $id = [int](Get-Content $pf -Raw -ErrorAction SilentlyContinue)
    if ($id) { $ids += $id }
    Remove-Item $pf -Force -ErrorAction SilentlyContinue
  }
}
$ids | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
# 3) 兜底按命令行再杀残留
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -like '*watchdog_ai_stack.py*' -or
  $_.CommandLine -like '*o2_agent_gateway.py*' -or
  $_.CommandLine -like '*ocr_service.py*'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 3

# 4) 清空代理环境变量，隐藏窗口拉起修复版看门狗（看门狗即持久化锚点）
foreach ($k in @('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy')) { $env:$k = '' }
Start-Process -FilePath $PY -ArgumentList "$GATE\watchdog_ai_stack.py" -WindowStyle Hidden -WorkingDirectory $GATE
Log "已按 pid 重启修复版看门狗（无窗口 + TCP 探活）。约 30 秒后弹窗消失、不再循环重启。"
Log "O2OA 9090 若浏览器仍卡，请把 localhost;127.0.0.1 加入代理『绕过』，或临时关代理刷新。"
