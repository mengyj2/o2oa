# O2OA 首页门户化 · 第2步落地（本机直跑版 v6，已焊死路径+日志双写+回读验证，不卡死）
# 用法：右键本文件 ->「使用 PowerShell 运行」（若报拒绝访问，改「以管理员身份运行」）。
#       无需凭据、无需网络、无需外带文件。跑完显示结果并等待回车关闭。
#       日志写入脚本同目录 o2oa_deploy_log.txt 及 C:\o2oa_deploy_log.txt（不再依赖桌面）。
# 关键：ManualRoot 已焊死 D:\o2oa\o2server；本脚本不等待路径输入、不会卡死；带进度条。
$ErrorActionPreference = 'Continue'

# 已焊死 o2server 安装目录（192.168.1.5 实测路径，含 o2server 那一层）。留空则自动定位。
$ManualRoot = 'D:\o2oa\o2server'

# 日志双写：脚本同目录 + C:\ 固定路径（不再写 USERPROFILE\Desktop，避免管理员运行时桌面找不到）
$log = Join-Path $PSScriptRoot 'o2oa_deploy_log.txt'
$log2 = 'C:\o2oa_deploy_log.txt'
Set-Content -Path $log -Value ("[" + (Get-Date) + "] 启动部署 v6") -Encoding UTF8 -ErrorAction SilentlyContinue
Set-Content -Path $log2 -Value ("[" + (Get-Date) + "] 启动部署 v6") -Encoding UTF8 -ErrorAction SilentlyContinue
function Log($m){ Write-Host $m; try{ Add-Content -Path $log -Value $m -Encoding UTF8 }catch{}; try{ Add-Content -Path $log2 -Value $m -Encoding UTF8 }catch{} }

# ===== 分流版 index.html 内容（base64 内嵌，运行时解码，无需外带文件）=====
$b64 = @'
PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9InpoLUNOIj4KICAgIDxoZWFkPgogICAgICAgIDxtZXRhIGh0dHAtZXF1aXY9IlgtVUEtQ29tcGF0aWJsZSIgY29udGVudD0iSUU9ZWRnZSIgLz4KICAgICAgICA8bWV0YSBodHRwLWVxdWl2PSJDYWNoZS1Db250cm9sIiBjb250ZW50PSJuby1jYWNoZSwgbm8tc3RvcmUsIG11c3QtcmV2YWxpZGF0ZSIgLz4KICAgICAgICA8bWV0YSBodHRwLWVxdWl2PSJQcmFnbWEiIGNvbnRlbnQ9Im5vLWNhY2hlIiAvPgogICAgICAgIDxtZXRhIGh0dHAtZXF1aXY9IkV4cGlyZXMiIGNvbnRlbnQ9IjAiIC8+CiAgICAgICAgPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiB0eXBlPSJ0ZXh0L2NzcyIgaHJlZj0iY3NzL3N0eWxlLmNzcz92PTEwLjAuMjc2YWI0ODZjNDEiIGNoYXJzZXQ9IlVURi04IiAvPgogICAgICAgIDxsaW5rIHJlbD0ic3R5bGVzaGVldCIgdHlwZT0idGV4dC9jc3MiIGhyZWY9ImNzcy92MTAvcm9vdC5jc3M/dj0xMC4wLjI3NmFiNDg2YzQxIiBjaGFyc2V0PSJVVEYtOCIgLz4KICAgICAgICA8bGluayByZWw9InN0eWxlc2hlZXQiIHR5cGU9InRleHQvY3NzIiBocmVmPSJjc3MvdjEwL3N0eWxlLmNzcz92PTEwLjAuMjc2YWI0ODZjNDEiIGlkPSJvby1jc3Mtc2tpbiIgY2hhcnNldD0iVVRGLTgiIC8+CiAgICAgICAgPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSJjc3MvbUJveE5vdGljZS5jc3M/dj0xMC4wLjI3NmFiNDg2YzQxIiBjaGFyc2V0PSJVVEYtOCIgLz4KICAgICAgICA8bGluayByZWw9InN0eWxlc2hlZXQiIGhyZWY9ImNzcy9tQm94VG9vbHRpcC5jc3M/dj0xMC4wLjI3NmFiNDg2YzQxIiBjaGFyc2V0PSJVVEYtOCIgLz4KICAgICAgICA8bGluayByZWw9Imljb24iIGhyZWY9ImRhdGE6OyIgLz4KCiAgICAgICAgPHRpdGxlPjwvdGl0bGU+CgogICAgICAgIDxtZXRhIGh0dHAtZXF1aXY9IkNvbnRlbnQtVHlwZSIgY29udGVudD0idGV4dC9odG1sOyBjaGFyc2V0PVVURi04IiAvPgogICAgICAgIDxtZXRhIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAsIG1heGltdW0tc2NhbGU9MS4wLCB1c2VyLXNjYWxhYmxlPTAiIG5hbWU9InZpZXdwb3J0IiAvPgogICAgICAgIDxtZXRhIGNvbnRlbnQ9InllcyIgbmFtZT0iYXBwbGUtbW9iaWxlLXdlYi1hcHAtY2FwYWJsZSIgLz4KICAgICAgICA8bWV0YSBjb250ZW50PSJibGFjayIgbmFtZT0iYXBwbGUtbW9iaWxlLXdlYi1hcHAtc3RhdHVzLWJhci1zdHlsZSIgLz4KICAgICAgICA8bWV0YSBjb250ZW50PSJ0ZWxlcGhvbmU9bm8iIG5hbWU9ImZvcm1hdC1kZXRlY3Rpb24iIC8+CiAgICA8L2hlYWQ+CiAgICA8Ym9keSBzdHlsZT0ib3ZlcmZsb3c6IGF1dG87IG1hcmdpbjogMHB4OyBoZWlnaHQ6IDEwMCUiPgogICAgICAgIDxkaXYgaWQ9ImFwcENvbnRlbnQiIGNsYXNzPSJhcHBDb250ZW50IiBzdHlsZT0ib3ZlcmZsb3c6IGhpZGRlbjsgaGVpZ2h0OiAxMDAlIj4KICAgICAgICAgICAgPGRpdgogICAgICAgICAgICAgICAgaWQ9ImxvYWRkaW5nQXJlYSIKICAgICAgICAgICAgICAgIHN0eWxlPSJvdmVyZmxvdzogaGlkZGVuOyB3aWR0aDogMHB4OyBoZWlnaHQ6IDJweDsgYmFja2dyb3VuZC1jb2xvcjogIzRlODJiZDsgcG9zaXRpb246IGFic29sdXRlOyB0b3A6IDA7IHotaW5kZXg6IDEwMDAwIgogICAgICAgICAgICA+PC9kaXY+CiAgICAgICAgPC9kaXY+CgogICAgICAgIDxzY3JpcHQgc3JjPSIuLi9vMl9jb3JlL28yLmpzP3Y9MTAuMC4yNzZhYjQ4NmM0MSI+PC9zY3JpcHQ+CiAgICAgICAgPHNjcmlwdCBzcmM9Ii4uL28yX2xpYi9EZWNpbWFsLmpzP3Y9MTAuMC4yNzZhYjQ4NmM0MSI+PC9zY3JpcHQ+CiAgICAgICAgPHNjcmlwdCBzcmM9ImpzL2Jhc2VfcG9ydGFsLmpzP3Y9MTAuMC4yLTc2YWI0ODZjNDEiPjwvc2NyaXB0PgogICAgICAgIDxzY3JpcHQ+CiAgICAgICAgICAgIGxheW91dC5hZGRSZWFkeShmdW5jdGlvbigpewogICAgICAgICAgICAgICAgKGZ1bmN0aW9uKGxheW91dCl7CiAgICAgICAgICAgICAgICAgICAgdmFyIHVyaSA9IG5ldyBVUkkod2luZG93LmxvY2F0aW9uLmhyZWYpOwogICAgICAgICAgICAgICAgICAgIHZhciBhcHBOYW1lcyA9ICJwb3J0YWwuUG9ydGFsIjsKICAgICAgICAgICAgICAgICAgICB2YXIgb3B0aW9ucyA9IHsicG9ydGFsSWQiOiAiaW5kZXgifTsKCiAgICAgICAgICAgICAgICAgICAgdmFyIF9sb2FkID0gZnVuY3Rpb24oKXsKICAgICAgICAgICAgICAgICAgICAgICAgbGF5b3V0LmFwcHMgPSBbXTsKICAgICAgICAgICAgICAgICAgICAgICAgbGF5b3V0Lm5vZGUgPSAkKCJsYXlvdXQiKSB8fCAkKCJhcHBDb250ZW50IikgfHwgZG9jdW1lbnQuYm9keTsKICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgIGxheW91dC5vcGVuQXBwbGljYXRpb24obnVsbCwgYXBwTmFtZXMsIG9wdGlvbnMpOwoKICAgICAgICAgICAgICAgICAgICAgICAgaWYgKCFsYXlvdXQuc2Vzc2lvbi51c2VyIHx8IGxheW91dC5zZXNzaW9uLnVzZXIubmFtZSA9PT0gImFub255bW91cyIpewogICAgICAgICAgICAgICAgICAgICAgICAgICAgbzIubG9hZENzcygiLi4vbzJfY29yZS9vMi94RGVza3RvcC8kRGVmYXVsdC9ibHVlL3N0eWxlLXNraW4uY3NzIik7CiAgICAgICAgICAgICAgICAgICAgICAgIH1lbHNlewogICAgICAgICAgICAgICAgICAgICAgICAgICAgbzIueERlc2t0b3AuZ2V0VXNlckxheW91dChmdW5jdGlvbigpewogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHZhciBzdHlsZSA9IGxheW91dC51c2VyTGF5b3V0LmZsYXRTdHlsZTsKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBvMi5sb2FkQ3NzKCIuLi9vMl9jb3JlL28yL3hEZXNrdG9wLyREZWZhdWx0LyIrc3R5bGUrIi9zdHlsZS1za2luLmNzcyIpOwogICAgICAgICAgICAgICAgICAgICAgICAgICAgfSk7CiAgICAgICAgICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgICAgICB9OwoKICAgICAgICAgICAgICAgICAgICAvKiAtLS0tIOacrOWcsOWinuW8uu+8mueZu+W9leWQjuaMiei6q+S7veWIhua1gSAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgICAgICAgICAgICAgICAgICAgIOeuoeeQhuWRmO+8iHRva2VuVHlwZSA9IG1hbmFnZXLvvIzmiJblkKsgTWFuYWdlckBNYW5hZ2VyU3lzdGVtUm9sZUBSIOinkuiJsu+8iQogICAgICAgICAgICAgICAgICAgICAgICAgLT4g6LezIGFkbWluLmh0bWzvvIjml6fniYjkuZ3lrqvmoLzmoYzpnaLvvIkKICAgICAgICAgICAgICAgICAgICAgICDlhbbkvZnnlKjmiLcKICAgICAgICAgICAgICAgICAgICAgICAgIC0+IOmXqOaIt+mmlumhte+8iOS4juWumOaWuSBpbmRleC5odG1sIOaViOaenOS4gOiHtO+8iQogICAgICAgICAgICAgICAgICAgICAgIOWIpOaNruWPluiHqiBPMk9BIOiHqui6q+S8muivneWvueixoSBsYXlvdXQuc2Vzc2lvbi51c2Vy77yM5LiN5L6d6LWW5aSW6YOo5o6l5Y+j44CCICovCiAgICAgICAgICAgICAgICAgICAgdmFyIF9pc01hbmFnZXJVc2VyID0gZnVuY3Rpb24odSl7CiAgICAgICAgICAgICAgICAgICAgICAgIHRyeSB7CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBpZiAoIXUpIHsgcmV0dXJuIGZhbHNlOyB9CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBpZiAodS50b2tlblR5cGUgPT09ICJtYW5hZ2VyIikgeyByZXR1cm4gdHJ1ZTsgfQogICAgICAgICAgICAgICAgICAgICAgICAgICAgdmFyIHJvbGVzID0gdS5yb2xlTGlzdCB8fCBbXTsKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGZvciAodmFyIGkgPSAwOyBpIDwgcm9sZXMubGVuZ3RoOyBpKyspewogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIChTdHJpbmcocm9sZXNbaV0pLmluZGV4T2YoIk1hbmFnZXJATWFuYWdlclN5c3RlbVJvbGVAUiIpID4gLTEpIHsgcmV0dXJuIHRydWU7IH0KICAgICAgICAgICAgICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgICAgICAgICAgfSBjYXRjaChlKXt9CiAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybiBmYWxzZTsKICAgICAgICAgICAgICAgICAgICB9OwoKICAgICAgICAgICAgICAgICAgICB2YXIgX2dvQWRtaW4gPSBmdW5jdGlvbigpewogICAgICAgICAgICAgICAgICAgICAgICB3aW5kb3cubG9jYXRpb24ucmVwbGFjZSgiYWRtaW4uaHRtbCIpOwogICAgICAgICAgICAgICAgICAgIH07CgogICAgICAgICAgICAgICAgICAgIFByb21pc2UucmVzb2x2ZShsYXlvdXQuc2Vzc2lvblByb21pc2UgfHwgJycpLnRoZW4oZnVuY3Rpb24oanNvbil7CiAgICAgICAgICAgICAgICAgICAgICAgIHZhciB1ID0gKGxheW91dC5zZXNzaW9uIHx8IHt9KS51c2VyOwogICAgICAgICAgICAgICAgICAgICAgICBpZiAodSkgewogICAgICAgICAgICAgICAgICAgICAgICAgICAgaWYgKF9pc01hbmFnZXJVc2VyKHUpKSB7IF9nb0FkbWluKCk7IHJldHVybjsgfQogICAgICAgICAgICAgICAgICAgICAgICAgICAgX2xvYWQoKTsKICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybjsKICAgICAgICAgICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgICAgICAgICAvKiDlhZzlupXvvJrkvJror53lr7nosaHlsJrmnKrlsLHnu6rml7bvvIznm7TmjqXor6Lpl67orqTor4HmjqXlj6MgKi8KICAgICAgICAgICAgICAgICAgICAgICAgdHJ5IHsKICAgICAgICAgICAgICAgICAgICAgICAgICAgIHZhciBfeCA9IG5ldyBYTUxIdHRwUmVxdWVzdCgpOwogICAgICAgICAgICAgICAgICAgICAgICAgICAgX3gub3BlbigiR0VUIiwgIi4uL3hfb3JnYW5pemF0aW9uX2Fzc2VtYmxlX2F1dGhlbnRpY2F0aW9uL2pheHJzL2F1dGhlbnRpY2F0aW9uIiwgdHJ1ZSk7CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBfeC5vbnJlYWR5c3RhdGVjaGFuZ2UgPSBmdW5jdGlvbigpewogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIChfeC5yZWFkeVN0YXRlID09PSA0KXsKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgdHJ5IHsKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHZhciBfZCA9IEpTT04ucGFyc2UoX3gucmVzcG9uc2VUZXh0KSB8fCB7fTsKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIChfaXNNYW5hZ2VyVXNlcihfZC5kYXRhKSkgeyBfZ29BZG1pbigpOyByZXR1cm47IH0KICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgfSBjYXRjaChlKXt9CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIF9sb2FkKCk7CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgICAgICAgICAgICAgfTsKICAgICAgICAgICAgICAgICAgICAgICAgICAgIF94LnNlbmQoKTsKICAgICAgICAgICAgICAgICAgICAgICAgfSBjYXRjaChlKXsgX2xvYWQoKTsgfQogICAgICAgICAgICAgICAgICAgIH0pOwogICAgICAgICAgICAgICAgfSkobGF5b3V0KTsKICAgICAgICAgICAgfSk7CiAgICAgICAgPC9zY3JpcHQ+CiAgICA8L2JvZHk+CjwvaHRtbD4K
'@
$bytes = [System.Convert]::FromBase64String($b64)
Log ("分流版字节数: " + $bytes.Length + " (应 5532)")

# ===== 强定位 o2server web 根（仅本地固定盘，带进度，绝不交互等待）=====
Log "开始定位 o2server web 根（仅本地固定盘）..."
$roots = @()
$drives = @([System.IO.DriveInfo]::GetDrives() |
            Where-Object { $_.DriveType -eq 'Fixed' -and $_.IsReady } |
            ForEach-Object { $_.RootDirectory.FullName })

# 0) 手动指定优先
if ($ManualRoot) {
    $c = Join-Path $ManualRoot 'servers\webServer\x_desktop'
    if (Test-Path (Join-Path $c 'index.html')) { $roots += $c; Log ("使用 ManualRoot: " + $c) }
    else { Log ("ManualRoot 下未找到 servers\webServer\x_desktop\index.html -> " + $c); Log ("日志: " + $log); exit 1 }
}

# 1a) 常见安装位置（盘根 + 常见父目录，有限列举，秒级）
if ($roots.Count -eq 0) {
    $commonParents = @('o2server','O2OA\o2server','o2oa\o2server','OA\o2server',
                       'Program Files\o2server','Program Files (x86)\o2server',
                       'software\o2server','soft\o2server')
    foreach ($drv in $drives) {
        foreach ($cp in $commonParents) {
            $c = Join-Path $drv (Join-Path $cp 'servers\webServer\x_desktop')
            if (Test-Path (Join-Path $c 'index.html')) { $roots += $c }
        }
    }
}
# 1b) 盘根一层子目录 X：查 X\o2server\... 与 X\servers\webServer\...（覆盖 D:\OA\o2server 等）
if ($roots.Count -eq 0) {
    foreach ($drv in $drives) {
        Get-ChildItem $drv -EA 0 | Where-Object { $_.PSIsContainer } | ForEach-Object {
            $c1 = Join-Path $_.FullName 'o2server\servers\webServer\x_desktop'
            $c2 = Join-Path $_.FullName 'servers\webServer\x_desktop'
            if (Test-Path (Join-Path $c1 'index.html')) { $roots += $c1 }
            if (Test-Path (Join-Path $c2 'index.html')) { $roots += $c2 }
        }
    }
}
# 1c) 盘根一层名含 o2 的子目录：再下一层找 webServer\x_desktop
if ($roots.Count -eq 0) {
    foreach ($drv in $drives) {
        Get-ChildItem $drv -EA 0 | Where-Object { $_.PSIsContainer -and $_.Name -match 'o2' } | ForEach-Object {
            Get-ChildItem $_.FullName -EA 0 | Where-Object { $_.PSIsContainer } | ForEach-Object {
                $c = Join-Path $_.FullName 'servers\webServer\x_desktop'
                if (Test-Path (Join-Path $c 'index.html')) { $roots += $c }
            }
        }
    }
}
# 1d) 受控递归（Depth 8，仅匹配目录名含 'o2'，覆盖 O2OA / o2server-v10 等非标准命名）
if ($roots.Count -eq 0) {
    foreach ($drv in $drives) {
        Log ("  受控搜索 $drv (Depth 8, 目录名含 o2)...")
        Write-Progress -Activity "搜索 o2server" -Status $drv
        try {
            Get-ChildItem $drv -Directory -Recurse -Depth 8 -EA 0 |
                Where-Object { $_.Name -match 'o2' } | ForEach-Object {
                    $c = Join-Path $_.FullName 'servers\webServer\x_desktop'
                    if (Test-Path (Join-Path $c 'index.html')) { $roots += $c }
                }
        } catch {}
        Write-Progress -Activity "搜索 o2server" -Completed
    }
}
# 1e) 兜底：直接找所有 webServer\x_desktop\index.html（Depth 8）
if ($roots.Count -eq 0) {
    foreach ($drv in $drives) {
        Log ("  兜底搜索 $drv 下的 index.html (Depth 8)...")
        Write-Progress -Activity "搜索 index.html" -Status $drv
        try {
            Get-ChildItem $drv -Recurse -Depth 8 -Filter 'index.html' -EA 0 |
                Where-Object { $_.FullName -match 'webServer\\x_desktop\\index\.html$' } |
                ForEach-Object { $roots += $_.DirectoryName }
        } catch {}
        Write-Progress -Activity "搜索 index.html" -Completed
    }
}

if ($roots.Count -eq 0) {
    Log "!! 自动定位失败。下面列出固定盘根下名字含 'o2' 的目录，供人工确认："
    foreach ($drv in $drives) {
        Get-ChildItem $drv -EA 0 | Where-Object { $_.PSIsContainer -and $_.Name -match 'o2' } |
            ForEach-Object { Log ("  候选: " + $_.FullName) }
    }
    Log "请把上述 o2server 所在目录（含 o2server 那一层）填到脚本顶部 `$ManualRoot 后重跑。"
    Log ("日志: " + $log)
    exit 1
}
$roots = $roots | Sort-Object -Unique
Log ("找到 $($roots.Count) 个 web 根候选:")
$roots | ForEach-Object { Log ("  - " + $_) }

# ===== 写入每个候选 + 备份 + 清理残留 + 回读验证 =====
$ok = 0
foreach ($root in $roots) {
    $idx = Join-Path $root 'index.html'
    Log ("---- 处理: " + $idx)
    try {
        if (Test-Path $idx) {
            $bak = ($idx + ".server_orig_" + (Get-Date -Format 'yyyyMMddHHmmss'))
            Copy-Item $idx $bak -Force
            Log ("  已备份原 index.html -> " + $bak + " (" + (Get-Item $idx).Length + " 字节)")
        }
        [System.IO.File]::WriteAllBytes($idx, $bytes)
        $sz = (Get-Item $idx).Length
        if ($sz -eq $bytes.Length) { Log ("  ✅ 写入成功，磁盘 " + $sz + " 字节 (应 5532)"); $ok++ }
        else { Log ("  !! 写入字节不符: " + $sz + " != " + $bytes.Length) }
    } catch {
        Log ("  !! 写入失败: " + $_.Exception.Message)
        Log "     -> 请右键「以管理员身份运行」；若仍失败，先停止 O2OA 服务（o2server 目录下 stop_windows.bat）再跑本脚本，然后启动 start_windows.bat"
    }
    # 清理部署残留（每个候选下）
    foreach ($r in @('index_new.html','zz_probe.txt','zz_probe.html')) {
        $p = Join-Path $root $r
        if (Test-Path $p) { Remove-Item $p -Force; Log ("  已删残留 " + $r) }
    }
    # probe_marker.js 在 o2_core/o2/xDesktop 下（与 webServer 平级）
    $markerDir = Join-Path (Split-Path $root) '..\o2_core\o2\xDesktop'
    Get-ChildItem $markerDir -Filter 'probe_marker.js' -EA 0 | Select-Object -First 1 | ForEach-Object {
        Remove-Item $_.FullName -Force; Log ("  已删 " + $_.FullName)
    }
}
Log ("磁盘写入成功数: " + $ok + " / " + $roots.Count)

# ===== Docker 部署：把分流版真正推进运行中的容器 =====
# O2OA 跑在 Docker（容器 o2oa-server），webServer 在镜像内、未挂卷，
# 只写本地 D:\O2OA\o2server\... 对运行中容器无效 —— 必须 docker cp 进容器才生效。
$Container = 'o2oa-server'
$ContainerPath = '/opt/o2server/servers/webServer/x_desktop/index.html'
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    $alive = & docker ps --filter "name=$Container" --format '{{.Names}}' 2>$null
    if ($alive) {
        foreach ($r in $roots) {
            $src = Join-Path $r 'index.html'
            if (Test-Path $src) {
                try {
                    & docker cp $src "${Container}:${ContainerPath}" 2>$null
                    Log ("  ✅ docker cp -> ${Container}:${ContainerPath}")
                } catch {
                    Log ("  !! docker cp 失败: " + $_.Exception.Message)
                }
            }
        }
        Log "注意：webServer 在镜像内、未挂卷，容器 restart 后此改动会被重置；如需持久生效请固化进 Dockerfile 或挂卷。"
    } else {
        Log "WARN: 容器 $Container 未运行，跳过 docker cp（仅写入本地源码目录，对运行中服务无效）。"
    }
} else {
    Log "WARN: 未找到 docker，仅写入本地源码目录。该路径未挂卷，对运行中的容器无效！"
}

# ===== HTTP 验证：正在运行的 webServer 是否真提供分流版 =====
Log "==== HTTP 验证（正在运行的 webServer @ localhost:9090）===="
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:9090/x_desktop/index.html" -TimeoutSec 15 -UseBasicParsing
    $httpSize = $resp.Content.Length
    Log ("  http://localhost:9090/x_desktop/index.html -> HTTP " + $resp.StatusCode + ", 正文 " + $httpSize + " 字节")
    if ($httpSize -ge 5000) { Log "  ✅ webServer 已提供分流版（落地生效）" }
    else { Log "  ⚠️ webServer 仍返回旧壳（约 $httpSize 字节）。可能：①写错了副本；②O2OA 需重启以加载新文件。请重启 O2OA 服务后刷新再验证。" }
} catch {
    Log ("  HTTP 验证失败（O2OA 可能未运行或端口不是 9090）: " + $_.Exception.Message)
    Log "  若 O2OA 正在运行，请重启 O2OA 服务（stop_windows.bat -> start_windows.bat）后刷新浏览器验收。"
}
Log "=================================================="
Log "落地完成。刷新浏览器 http://192.168.1.5:9090/ 验收："
Log "  管理员登录 -> 跳 x_desktop/admin.html（桌面工作台）"
Log "  普通用户登录 -> 见门户首页（1 层，无套娃）"
Log "  F12 控制台 / Network 应 0 报错"
Log "回滚：把 .server_orig_*.bak 复制回 index.html 即可"
Log ("日志已保存: " + $log)
Log ("（同时存于 C:\o2oa_deploy_log.txt，可随时查看）")
Start-Sleep -Seconds 8; Log "部署完成（8 秒后自动关闭窗口）。"
