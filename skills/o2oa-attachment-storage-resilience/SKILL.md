---
name: o2oa-attachment-storage-resilience
description: 诊断并根治 O2OA（Docker 自托管，10.0.2 实证）附件存储层的「聊聊图片/附件传不过来、收不到、破图、点开无法预览、上传后记录回滚」，以及「存储后端 NAS 抖动/离线、重装换机后附件丢失」。核心是 rclone WebDAV(dufs) 存储层：写后读竞态（--vfs-cache-mode writes→full）、NAS SMB i/o timeout 降级、degraded 暂存补传、启动阻塞、缓存/数据持久化与恢复、rclone 版本钉死。当用户说"图片传不过来""附件收不到/破图""传了对方没有""重装/升级后附件没了""存储后端不可达""聊聊发图失败""dufs 上传丢失"时调用。
agent_created: true
category: troubleshooting
---

# O2OA 附件存储层韧性（写后读竞态 / NAS 抖动 / 持久化）

> 实证环境：O2OA 10.0.2 社区版 / Docker（`o2oa-server`）+ **rclone WebDAV 存储容器 `o2oa-storage`**
> 后端 = NAS SMB（`192.168.1.2:445`，即用户口中的「.2」）+ 本地 50G 热缓存 + 本地 degraded 暂存。
> 首个案例：2026-10-12「李静在聊聊中传图片传不过来、不能预览」，追根到 dufs 写后读竞态。

## 0. 架构事实（先对齐心智模型，别猜）

O2OA 附件 = **「先落库、后异步写文件」**：DB 先写记录 → 经 **dufs/rclone WebDAV** 落文件 →
再**立即回读校验字节数**（commit）→ 校验失败则**回滚 DB 记录**（此时消息里只剩孤儿 `fileId`）。

存储容器拓扑（`docker-compose.yml` 的 `storage` 服务）：

```
O2OA ──WebDAV(http://o2oa-storage:5000)──▶ rclone serve webdav
                                              ├─ 后端: :smb,host=$NAS_HOST,...:$NAS_SHARE/o2oa-minio   （.2 = 权威冷存储）
                                              ├─ 本地热缓存: --vfs-cache-mode full --vfs-cache-max-size 50G  → ./dufs-cache (bind mount)
                                              └─ 降级暂存:   NAS 掉线时切 /degraded → ./dufs-degraded (bind mount)
```

**用户心智模型 = 实现**：「先在本地（50G 缓存）落地，再异步传到 .2」—— 这正是 `--vfs-cache-mode full`
的行为（写先落本地缓存、后台异步上传 NAS）。**别**把它讲成"直写 NAS"，也别"修"成 writes 模式。

> ⚠️ `./dufs-cache`、`./dufs-degraded` 在 `.gitignore` 里（运行数据不入库），但它们是 **bind mount**，
> 容器重建/镜像升级**不丢**；只有"整机重装 + 清目录"才丢 → 靠备份兜底（见 §5）。

## 1. 30 秒判定：症状 → 根因

| 症状 | 首要怀疑 | 判据 |
|---|---|---|
| 对方**收不到**图 / 消息只剩一个打不开的附件 | ① 写后读竞态（§2） | `docker logs o2oa-storage` 有 `vfs cache: failed to upload` / `commit error` |
| 上传**瞬间**破图，刷新/过几秒又好了 | 异步写时序（§4 尾注） | 刷新即恢复 = 正常，非故障 |
| 以前好过、**某次之后**就不行了 | 是否被"改回去"了 | `docker inspect o2oa-storage` 的 Cmd 是否仍含 `--vfs-cache-mode full`（§2.3） |
| 所有附件都读不出、连热缓存的也读不出 | 存储后端整体不可达 | 见 §3 降级模式；`ping 192.168.1.2` 通但 SMB 超时是**常态** |
| **重装/换机后**附件全没了 | 缓存未备份 / NAS 未同步 | 见 §5 |

**决定性一圈取证**（一次跑完）：

```bash
# 1) 运行中的存储参数（竞态修复是否还在）
docker inspect o2oa-storage --format '{{json .Config.Cmd}}' | tr ',' '\n' | grep -E 'vfs-cache-mode|dir-cache-time|vfs-write-back'
# 2) 当前模式 + 上传报错
docker logs o2oa-storage --tail 40 2>&1 | grep -iE 'guard|mode=|failed to upload|i/o timeout'
# 3) NAS SMB 是否在超时（通 ping ≠ 通 SMB）
docker logs o2oa-storage --tail 200 2>&1 | grep -c '445: i/o timeout'
# 4) 缓存 / 降级目录占用
du -sh dufs-cache dufs-degraded
```

## 2. ★★ 写后读竞态 —— 「图片传不过来」的头号根因（2026-10-12 根治）

### 2.1 机理

`--vfs-cache-mode writes`（旧配置）下，**读请求绕过本地缓存、直读 NAS(SMB)**；
而 SMB 写入存在 **「文件已创建、内容尚未 flush」** 的窗口。O2OA 上传后**立即回读校验**正好撞上：

```
PUT  → SMB 建文件（0 字节）…  内容仍在 flush
GET(立即) ← 直读 SMB → 读到 0 字节   ← 竞态窗口
O2OA: 0 字节 → commit error → DB 回滚 → 文件永久丢失（消息只剩孤儿 fileId）
```

### 2.2 修法（`full` 模式）

`--vfs-cache-mode writes` → **`full`**：读也命中本地缓存 ⇒ 写后立即可读，竞态消失。
同时 `--dir-cache-time 15s → 1s`（缩短目录列举可见性延迟）。

```yaml
# docker-compose.yml  storage 服务 NORMAL 分支
rclone serve webdav "$$REMOTE" --addr :5000 \
  --vfs-cache-mode full --vfs-cache-max-size $$HOT_CACHE_SIZE \
  --vfs-write-back 5s \
  --vfs-cache-max-age 2160h --dir-cache-time 1s --cache-dir /cache &
```

### 2.3 防静默回退（★ 必做）

改完**必须**能被门禁抓住，否则换机/误改即复发：

```bash
# 运行容器必须含 full + dir-cache-time 1s；compose 镜像必须钉死（非 :latest）
python tools/o2_container_drift_check.py --compose D:/O2OA/docker-compose.yml
#   → [存储层竞态修复契约] 若 FAIL 退出码 1
docker compose up -d --no-deps --force-recreate storage   # 应用修复
```

**实测（可原样重跑）**：写后 0 延迟 GET，6/6 字节一致（修复后）；修复前 0 延迟下载 = HTTP 200 但 `len=0`。

```bash
PW=$(grep '^DUFS_PASSWORD=' /d/O2OA/.env | cut -d= -f2-)
head -c 30000 /dev/urandom > /tmp/a.bin
curl -s -u o2oadrive:$PW -T /tmp/a.bin http://127.0.0.1:5000/__t/f.bin -o /dev/null
curl -s -u o2oadrive:$PW http://127.0.0.1:5000/__t/f.bin -o /tmp/b.bin
cmp /tmp/a.bin /tmp/b.bin && echo OK   # 必须一致（修复前 b.bin 为 0 字节）
```

## 3. NAS SMB i/o timeout = 常态，不是故障

`ping 192.168.1.2` 通，但 `445: i/o timeout` 频繁 —— **TCP 可达 ≠ SMB 服务可用**（海康 NAS 定时休眠/网络闪断）。
存储容器的"降级守卫"为此设计：

- NAS 在线 → **NORMAL**（SMB 后端 + 50G 热缓存）
- NAS 掉线 → 自动切 **DEGRADED**（`rclone serve webdav /degraded`，读写落本地 `./dufs-degraded`，**网盘不报错**）
- NAS 恢复 → **rclone copy /degraded → NAS** 补传，再切回 NORMAL

> **纪律**：不要把 SMB 超时当"存储坏了"去重启存储。**只要 full 缓存模式在，写进本地缓存的文件就不会丢**
> （后台会重试上传）。真正要治的是 NAS 侧网络/SMB 服务（建议排查：SMB 版本协商、休眠策略、网线/交换机）。

## 4. ★ 启动阻塞缺陷：degraded 补传必须放服务启动【之后】后台跑（2026-10-12 修）

**坑**：原 entrypoint 先 `rclone copy /degraded → NAS` **再** 起 WebDAV 服务。
NAS 抖动时该 copy 连续 i/o timeout **数十秒**（实测 ~30s）→ 期间 **5000 端口未监听 → 附件全不可用**。

**修**：先起服务（秒起），补传放**后台**：

```sh
rclone serve webdav "$$REMOTE" ... & SRV=$$!
if [ -n "$$(ls -A /degraded 2>/dev/null)" ]; then
  ( rclone copy /degraded "$$REMOTE" --ignore-existing --contimeout 10s --timeout 30s \
      || echo "[guard] upload failed, retry next round" ) &
fi
```

**验证**：重建容器后端口 5000 就绪时间 —— 修前 ~30s，**修后 ~3s**。

> 尾注（正常现象）：刚上传的一瞬可能短暂破图 —— O2OA 侧"异步写 + 立即读"自有毫秒级时序，
> 刷新即好，非存储故障。可选加固：前端 `img onerror` 自动重试。

## 5. 持久化：升级 / 重装不丢数据与程序（★ 用户核心诉求）

| 关注点 | 载体 | 重装是否丢 | 兜底 |
|---|---|---|---|
| 附件文件（冷） | NAS `192.168.1.2` | 否 | 权威源；rclone 持续上传 |
| 附件文件（热/降级） | `./dufs-cache` `./dufs-degraded`（bind mount） | 换机丢（未入库） | `backup_o2oa_chain.bat` 备份 **degraded**；cache 可再生 |
| 附件记录 | MySQL（命名卷 `mysql-data`） | 否 | 全量 `mysqldump` |
| 存储层配置 | `docker-compose.yml`（git 真源） | 否 | 入仓 + 备份 + 漂移门禁 |
| 程序/镜像 | git 仓 + `docker save` 镜像 tar | 否 | bundle + `_images/` |

**恢复脚本（顺序）**：
```bash
bash  tools/push_o2oa_driver_clean.sh --dry-run           # 先确认仓库/配置一致
bash  tools/o2_container_drift_check.py                   # 确认镜像层含全部固化资产
"$GIT_BASH" -c "cd /d/O2OA && bash tools/backup_o2oa_state.sh"   # 备份（含 compose/degraded/镜像 tar）
```

**rclone 版本钉死**：`image: rclone/rclone:1.75.2`（**禁用 `:latest`**）。
存储是附件唯一持久化入口，`:latest` 会在重装 `pull` 时拉到新版 → VFS 语义/重试策略可能变 → 难以回溯。
升级前须先在测试环境复验 `--vfs-cache-mode full` 的写后立即可读性。

## 6. 固化纪律（六件套）

存储层任何修复**必须**走完：
① 知识库化 `docs/knowledge_base/*.md` → `python tools/ingest_knowledge_base_docs.py`
② 技能化（本 skill）→ `bash tools/sync_skills_to_repos.sh`（镜像两仓）
③ 档案 `tools/o2_docs_audit.py --all` 刷 `docs/DOC-STATUS.md`
④ 推 `o2oa-driver`（`tools/push_o2oa_driver_clean.sh`）
⑤ 备份 `tools/backup_o2oa_chain.bat`
⑥ 改 `docker-compose.yml` **即真源**（无镜像可烘焙）→ 入仓 + 备份 + 门禁断言。
   改后务必 `docker compose up -d --no-deps --force-recreate --pull never storage` 使运行时==声明。

## 7. 相关 skill

- `o2oa-runtime-drift-hardening` —— 「改动只进容器/卷、没进镜像/仓库」的通用漂移审计（本 skill 的 §2.3 门禁由它承载）。
- `o2oa-onlyoffice-attachment-preview` —— 附件**在线预览**走下载（前端/控件/缓存层）。
- `o2oa-onlyoffice-editor-features` —— 验证文件确在 rclone 存储器的 headless 探测法。
- `o2oa-log-triage-health` —— 附件相关报错在问题日志里的排查入口。
