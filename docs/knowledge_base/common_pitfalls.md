# O2OA 常见坑与加固措施

## 1. 容器/DB 时区陷阱

### 1.1 现象
- 容器/DB 时间是 UTC，Windows 主机是 GMT+8
- **相差 8 小时**的时区偏差会导致严重误判

### 1.2 典型错误案例
> 在 2026-09-14 诊断 Clawith 研究卡死时，误把 `claim_expires_at=15:25+00` 读作"已过期 8 小时"，实际是主机 23:25（1 分钟后）→ 错误结论："进程死锁"

### 1.3 正确做法
- 先 `SELECT now()` 对齐时间，或一律 **+8 换算**后再判断
- 所有 Docker 容器内的时间戳读取前，必须确认是否需要 +8 小时偏移

## 2. 本地 LLM 推理日志静默陷阱

### 2.1 现象
- LM Studio / llama.cpp 在流式生成期间不产生日志
- "日志静默" ≠ "进程死锁"

### 2.2 判活三处定位
1. `lms ps` - 查看后端进程状态
2. `/proc/net/tcp` - 检查网络连接
3. DB claim 心跳 - 确认数据库心跳是否正常

### 2.3 经验
- 流程卡死的第一直觉要排除"模型生成超时/静默"，再排查系统资源或配置问题

## 3. Windows Shell 调用习惯错误

### 3.1 现象
- 用户的 shell 是 PowerShell
- CWD（当前工作目录）下的 `.bat` 不能裸名调用
- 报错：`CommandNotFoundException`

### 3.2 正确做法
- **给用户的命令一律带 `.\` 前缀**
- 示例：`.\clawith_maintain.bat restore`
- 特别注意：`C:\Users\meng_\bin` 不在 PATH，也别把项目目录塞进 PATH

### 3.3 ARM64 + QEMU 双重陷阱
- Strix Halo 96GB UMA 上运行 Docker Desktop on Windows ARM
- **amd64 镜像靠 QEMU 可跑，但部分官方镜像（如 `mysql:8.0`）拉取后 `exec format error`**
- 排查手法：`docker inspect <img> --format '{{.Architecture}}'` 查看镜像架构
- 表现验证：
  - `docker run --rm --platform linux/arm64 alpine uname -m` → `aarch64`（原生可跑）
  - `docker run --rm --platform linux/amd64 alpine uname -m` → `x86_64`（模拟可跑）

### 3.4 对策
- compose 里给关键服务显式 `platform: linux/arm64`（原生跑，快）
- 本地 build 的 amd64 镜像可保留 amd64 由 QEMU 模拟跑（慢但可用）

### 3.5 Docker healthcheck 语法错误
- 健康检查用 exec 形式 `["CMD","curl",...,"||","exit","1"]` 时，**`||` 不是 shell 操作符**
- **正确写法**：`["CMD-SHELL","curl -f ... || exit 1"]`

## 4. Cookie 污染与跨用户会话风险

### 4.1 现象
- httpx 全局 client cookie jar 残留 O2OA `Set-Cookie: x-token`（上一用户）
- O2OA Cookie Header 优先 → 服务号请求被当成上一用户（返回 500）

### 4.2 根因
- 同一个浏览器/进程连续操作多个用户时，cookie 互相穿透

### 4.3 解决方案
- O2OA REST 走专用 client，每请求 `cookies.clear()`（重置 cookie jar）
- 本地开发时注意清理 cookie 会话，避免跨用户数据泄露

## 5. bat 脚本编码与环境约束

### 5.1 CRLF + UTF-8 no BOM
- Windows 批处理脚本必须使用 **CRLF** 回车换行，且文件无 BOM 头
- 生成字段是 `input` 类型，空 clueId 跨用户串味（测试带随机 clueId）
- **严禁**：在个人根目录散落临时诊断 .txt 文件

### 5.2 临时文件管理
- **全部写入 `C:\temp`**，任务结束后**立即删除**
- 背景：之前在 `C:\Users\meng_\` 根目录生成二十多个临时诊断 .txt，用户要求清理并确立约定

### 5.3 Safe-delete 钩子
- PowerShell 的 `Remove-Item` 会被 safe-delete 钩子拦截并转送回收站
- 常见日志报告：`trash-failed` 但源文件实际已被移走
- 批量删除会被沙箱限流（约每命令 2 个）
- 必要时用 `dangerouslyDisableSandbox` 或分批执行

## 6. 账号与组织模型坑

### 6.1 xadmin 登录报 "用户不存在或密码错误"
- **≠ 密码错**：先看 `config/ternaryManagement.json` 是否 enable=true 且三员密码空
- 三员接管使 `isInitialManager("xadmin")=false` 且无密码可登 → =锁死
- **修复**：将 `enable=false` 后重启

### 6.2 角色成员维护在 role 侧
- 接口：`PUT /jaxrs/role/{id}` 提交**完整对象**（含 `personList`，存人员 id）
- 误区：不要只改部分字段，必须提交完整的 role 对象

### 6.3 组织 REST 接口使用
- `list` 多走 POST 方法
- `/person` 必填 name+mobile
- `/identity` 必填 person(dN)+unit
- `role/list/like` 空 key 返回空，**别用它查**角色成员

## 7. 外网请求与代理冲突

### 7.1 配置要点
- 本机是 ARM64 + QEMU，健康检查用 `curl --noproxy "*"`（shell 代理 52068 假 502）
- O2OA 容器内 `trust_env=False`+`--noproxy "*"` 才是正确姿势
- HTML 转文本先剔 script/style/noscript/svg/iframe/注释再剥标签

### 7.2 外网请求客户端配置
- httpx.Client(trust_env=True) 用于外网请求
- 本地/trust_env=False 配合 --noproxy "*"