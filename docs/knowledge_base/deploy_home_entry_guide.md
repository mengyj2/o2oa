# O2OA 首页门户部署脚本使用指南

## 常见错误与修正

### 1. 路径格式错误（用户最常遇到的问题）

**错误示例**：
```powershell
PS C:\Users\meng_> . /d/deploy_home_entry_local.ps1
. : 无法将“/d/deploy_home_entry_local.ps1”项识别为...
```

**根因**：
- PowerShell 不认 Git Bash 风格的 `/d/` 路径前缀
- Windows PowerShell 中的路径应使用盘符+反斜杠，或相对当前驱动器

**正确做法**（三种等价方式）：

#### 方法一：使用完整 Windows 路径（推荐）
```powershell
PS C:\Users\meng_> . "C:\d\deploy_home_entry_local.ps1"
```
或
```powershell
PS C:\Users\meng_> . "D:\deploy_home_entry_local.ps1"
```

#### 方法二：切换到 D 盘后运行
```powershell
PS C:\Users\meng_> cd /d
PS /d> .\deploy_home_entry_local.ps1
```

#### 方法三：使用 PowerShell 内置变量
```powershell
PS C:\Users\meng_> & { Set-Location D:\ ; . \deploy_home_entry_local.ps1 }
```

---

## 2. 脚本执行完整步骤

### 第一步：设置执行策略（仅第一次需要）
```powershell
# 方法 A：当前会话临时 bypass
PS C:\Users\meng_> Set-ExecutionPolicy -Scope Process Bypass

# 方法 B：永久放宽（慎用，生产环境建议保留默认策略）
PS C:\Users\meng_> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 第二步：运行部署脚本
```powershell
# 确保在 D 盘或使用完整路径
PS /d> Set-ExecutionPolicy -Scope Process Bypass
PS /d> .\deploy_home_entry_local.ps1
```

**预期输出**：
```
# O2OA 首页门户化 · 第2步落地（本机直跑版 v6，已焊死路径+日志双写+回读验证，不卡死）
# 用法：右键本文件 ->「使用 PowerShell 运行」（若报拒绝访问，改「以管理员身份运行」）。
...
Log ("落地完成。刷新浏览器 http://192.168.1.5:9090/ 验收：")
Log "  管理员登录 -> 跳 x_desktop/admin.html（桌面工作台）"
Log "  普通用户登录 -> 见门户首页（1 层，无套娃）"
Log "  F12 控制台 / Network 应 0 报错"
Log "回滚：把 .server_orig_*.bak 复制回 index.html 即可"
Log ("日志已保存: " + $log)
Log ("（同时存于 C:\o2oa_deploy_log.txt，可随时查看）")
Read-Host "部署完成，按回车关闭窗口"
```

### 第三步：验证结果
部署成功的标志：
- 控制台输出"落地完成"字样
- 日志文件写入：`d:\o2oa\o2server\o2oa_deploy_log.txt` 及 `C:\o2oa_deploy_log.txt`
- 打开浏览器访问 `http://192.168.1.5:9090/`：
  - 管理员账号 → 跳转 `x_desktop/admin.html`（桌面工作台）
  - 普通用户 → 看到门户首页（1层结构，无套娃/二级链接）
- F12控制台无报错

---

## 3. 部署原理简述

| 步骤 | 作用 |
|---|---|
| **路径定位** | 自动查找 `D:\o2oa\o2server\servers\webServer\x_desktop` 下的 `index.html` |
| **文件备份** | 原文件自动重命名为 `index.html.server_orig_YYYYMMDDHHMMSS` |
| **内容注入** | 写入 5532 字节的 base64 解码 HTML（分流版门户页） |
| **HTTP 验证** | 向 localhost:9090 确认服务已加载新文件 |
| **日志双写** | 同时记录 `d:\o2oa\o2server\o2oa_deploy_log.txt` 和 `C:\o2oa_deploy_log.txt` |

---

## 4. 回滚（如需撤销部署）

1. 找到备份文件：`index.html.server_orig_YYYYMMDDHHMMSS`
2. 复制回来：
   ```powershell
   PS /d> Copy-Item -Path "D:\o2oa\o2server\servers\webServer\x_desktop\index.html.server_orig_*.bak" -Destination "D:\o2oa\o2server\servers\webServer\x_desktop\index.html" -Force
   ```
3. 或者手动恢复：把备份文件内容覆盖回 `index.html`

---

## 5. 已知限制

- **需要 O2OA 服务运行**：HTTP验证步骤需 `localhost:9090` 可达
- **管理员权限建议**：首次运行建议右键 PowerShell → "以管理员身份运行"
- **路径焊死**：脚本顶部 `$ManualRoot = 'D:\o2oa\o2server'` 已固定，若 O2OA 安装在非默认路径需自行修改此变量
- **基础版仅**：本脚本只完成首页门户 HTML 写入，不包含后端流程、数据库等配置

---

## 6. 关联已有知识

本操作对应 SOP 中的以下章节：
- **账号模型铁律**：admin 账号登录后可跳转 admin.html（桌面工作台）
- **开始菜单三源机制**：门户页通过 `pcClient=true` 控制显示/隐藏
- **健康排查方法论**：部署失败时检查 `index.html` 大小是否为 5532 字节，日志是否写入
- **常见坑**：若 F12 控制台有报错，可能是 HTML 渲染冲突或资源路径未正确加载

---
*文档生成时间：2026-09-22*
*对应脚本版本：v6（焊死路径，带进度条，绝不交互等待）*