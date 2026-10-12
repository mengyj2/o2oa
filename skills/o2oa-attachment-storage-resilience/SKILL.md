---
name: o2oa-attachment-storage-resilience
description: 诊断并根治 O2OA（Docker 自托管，10.0.2 实证）附件/聊聊图片「传不过来、收不到、破图、点开无法预览、上传后记录回滚」，以及「存储后端 NAS 抖动/离线、重装换机后附件丢失」。核心是 rclone WebDAV 存储层 + 应用层元数据：本地权威架构（WebDAV 永远 serve 本地目录 + NAS 异步镜像）、写后读竞态、NAS SMB STATUS_INSUFFICIENT_RESOURCES 抖动、IM 图片元数据记录缺失（MSG_IM_MESSAGE_FILE 无 image 记录）、rclone obscure 非确定性缓存漂移、前端 img onerror 重试、持久化与重装恢复、rclone 版本钉死。当用户说"图片传不过来""附件收不到/破图""传了对方没有""看不了图片""重装/升级后附件没了""存储后端不可达""聊聊发图失败""dufs 上传丢失"时调用。
agent_created: true
category: troubleshooting
---

# O2OA 附件存储层韧性（本地权威架构 / 元数据 / 前端重试 / 持久化）

> 实证环境：O2OA 10.0.2 社区版 / Docker（`o2oa-server`）+ **rclone WebDAV 存储容器 `o2oa-storage`**。
> 后端 = NAS SMB（`192.168.1.2`，即用户口中的「.2」）**仅作镜像/冷备**；在线服务由**本地权威目录**承载。
> 首个案例：2026-10-12「李静在聊聊中传图片传不过来、不能预览」，v1.0 误判为"仅写后读竞态"，v2.0 深挖出**四层叠加根因**。

## 0. 架构事实（先对齐心智模型，别猜）

O2OA 附件 = **「先落库、后异步写文件」**：DB 先写 `IMMsgFile` 记录 → 经 **dufs/rclone WebDAV** 落文件 →
再**立即回读校验字节数**（commit）→ 校验失败则**回滚 DB 记录**（消息里只剩孤儿 `fileId`）。

**读侧强依赖 DB 记录**：`ActionFileDownload.execute()` 先 `emc.find(id, IMMsgFile.class)`，
`null == file → throw ExceptionFileNotExist`。**文件在存储里 ≠ 能打开** —— 元数据缺失会伪装成"文件不存在"。

存储容器拓扑（现架构 = **本地权威 + NAS 异步镜像**，`docker-compose.yml` 的 `storage` 服务）：

```
O2OA ──WebDAV(http://o2oa-storage:5000)──▶ rclone serve webdav "$DATA"
                                              $DATA = /data  ← bind ./dufs-data（本地权威，重启/升级不丢）
                              启动后后台：rclone copy NAS ─▶ $DATA   （回源/补齐历史）
                                        rclone copy $DATA ─▶ NAS   （上行镜像，失败仅重试）
                              NAS = :smb,host=192.168.1.2,...:$NAS_SHARE/o2oa-minio  （仅镜像/冷备）
```

> ★ **为什么"本地权威"**：NAS SMB 服务端会间歇返回 `STATUS_INSUFFICIENT_RESOURCES`，旧的
> 「NORMAL/DEGRADED 双模式 guard」因此每 30s 横跳、每次切换重启 WebDAV、且两模式 serve 的目录不同
> （`/cache` vs `/degraded`）→ 在 NORMAL 写的图切到 DEGRADED 就 404。改为 WebDAV**永远** serve 本地固定目录 +
> NAS 只在后台参与 ⇒ **NAS 抖动不再影响在线服务**，也顺带消除写后读竞态与 `obscure` 缓存漂移。
> 与用户心智模型一致：「先在本地落地，再异步传到 .2」—— 只是把"本地"从易漂移的 VFS 缓存换成了**固定权威目录**。

> ⚠️ `./dufs-data`（及历史 `./dufs-cache`、`./dufs-degraded`）在 `.gitignore` 里（运行数据不入库），
> 但它们是 **bind mount**，容器重建/镜像升级**不丢**；只有"整机重装 + 清目录"才丢 → 靠备份兜底（见 §6）。

## 1. 四层根因速查（叠加，缺一不治）

| 层 | 根因 | 表现 | 判据 |
|----|------|------|------|
| ① 存储写后读 | `--vfs-cache-mode writes` 下读绕过本地缓存直读 NAS → 撞"已建未 flush"窗口 | 上传后 0 延迟读=200/len=0 → `commit error` → 记录回滚 | 日志 `commit error`；0 延迟下载 = 200 但 len=0 |
| ② **模式抖动**（架构级） | NAS SMB 服务端间歇 `STATUS_INSUFFICIENT_RESOURCES`（建会话需 ~6 次重试，探测只给 1 次）→ 误判掉线 → 双模式每 30s 横跳 | 每次切换重启 WebDAV（端口不可用窗口）；两模式目录不同 → 图 404 | `docker logs o2oa-storage` 反复 `mode=NORMAL`/`mode=DEGRADED`；`rclone lsd` 1/6 vs `--low-level-retries 15` 6/6 |
| ③ **元数据缺失** | 历史图片 `MSG_IM_MESSAGE_FILE` **零条 `image`**（只有 file） | 应用层下载 500/404、缩略图必破 | `select count(*) from MSG_IM_MESSAGE_FILE where xtype='image'` = 0 |
| ④ 缓存漂移 | `rclone obscure` **非确定性**（同密码三次三密文）→ remote 哈希目录每次重启变 | 重启后读不到旧缓存 | `rclone obscure x` ×3 比对 |

**30 秒取证（一次跑完）**：

```bash
# 1) 是否本地权威架构（正确=含 LOCAL-AUTHORITY / serve webdav "$DATA"；出现 mode=DEGRADED 即旧架构回退）
docker inspect o2oa-storage --format '{{json .Config.Cmd}}' | tr ',' '\n' | grep -E 'LOCAL-AUTHORITY|serve webdav|mode=DEGRADED|vfs-cache-mode'
# 2) 日志：模式抖动 + 上传报错
docker logs o2oa-storage --tail 60 2>&1 | grep -iE 'LOCAL-AUTHORITY|mode=|failed to upload|i/o timeout|Insufficient'
# 3) 图片元数据是否落库（0 = 根因③）
docker exec o2oa-mysql sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N --default-character-set=utf8mb4 -e \"select xtype,count(*) from MSG_IM_MESSAGE_FILE group by xtype\" X"
# 4) NAS SMB 成功率（通 ping ≠ 通 SMB）
 docker exec o2oa-storage sh -c 'OB=$(rclone obscure "$NAS_PASSWORD"); R=":smb,host=$NAS_HOST,user=$NAS_USER,pass=$OB:$NAS_SHARE/o2oa-minio"; for i in 1 2 3 4 5 6; do rclone lsd "$R" --contimeout 5s --timeout 8s --retries 1 >/dev/null 2>&1 && echo OK || echo FAIL; done'
```

## 2. 症状 → 根因路由

| 症状 | 首要怀疑 |
|---|---|
| 对方**收不到**图 / 消息只剩打不开的附件 | ① 写后读竞态 或 ③ 元数据缺失 |
| **点开看不了 / 缩略图破图**，但消息在 | ③ 元数据缺失（先查 `MSG_IM_MESSAGE_FILE`） |
| 所有附件都读不出、连本地也读不出 | ② 模式抖动（旧架构）/ 存储容器不健康 |
| 上传**瞬间**破图，刷新/过几秒好 | 异步写时序（§5 尾注）；若频繁则用 §4 前端重试消除 |
| **重装/换机后**附件全没了 | 缓存未备份 / NAS 未同步（§6） |

## 3. 存储层修复：本地权威 + NAS 异步镜像（★ 现架构）

`docker-compose.yml` `storage` 服务（要点，完整见仓库）：

```yaml
  storage:
    image: rclone/rclone:1.75.2          # ★ 钉死版本（禁 :latest）
    volumes:
      - ./dufs-data:/data                # 本地权威目录（bind mount）
      # 历史兼容：./dufs-degraded:/degraded（旧降级暂存，首启并入 /data）
    command:
      - |
        DATA=/data
        echo "[storage] LOCAL-AUTHORITY mode: WebDAV serves $DATA"
        rclone serve webdav "$DATA" --addr :5000 --user o2oadrive --pass "$DUFS_PASSWORD" & SRV=$!
        # 后台（★ 必须在起服务之后，勿阻塞启动）：
        #   回源：rclone copy "$REMOTE" "$DATA" --ignore-existing
        #   合并历史 degraded：rclone copy /degraded "$DATA" --ignore-existing
        #   上行：rclone copy "$DATA" "$REMOTE" --ignore-existing   (失败重试，不影响服务)
```

- 生效：`docker compose up -d --no-deps --force-recreate --pull never storage` → **2~3 秒就绪**。
- 回滚包：`backups/compose-local-authority-20261012/`。

**防静默回退（★ 必做）**：`tools/o2_container_drift_check.py` **C 组**已改为「本地权威契约」——
断言运行容器含 `LOCAL-AUTHORITY` / `serve webdav "$DATA"` / 上下行 `rclone copy`，并**回归守卫**旧的
`--vfs-cache-mode writes` 与 `mode=DEGRADED` 不得复活。FAIL 即退出码 1。

## 4. 元数据修复 + 前端重试

### 4.1 补建缺失的 IM 图片记录（`tools/o2_fix_im_image_records.py`）

- 源 = `MSG_IM_MESSAGE` 中 body 含 `"type":"image"` 的消息（body 自带 `{fileId,fileName,fileExtension}`）；
- 逐条比对 `MSG_IM_MESSAGE_FILE`，缺则按模板（`xstorage=dufs-im`）INSERT；**只补记录、不动文件**；
- 幂等、默认 dry-run，`--apply` 落库；执行前 `mysqldump` 备份该表。
- 实测：11 条图片消息 → 补 **10** 条、1 条无对应文件（确丢）；补后应用层读历史图 **全部 200 + 字节精确匹配、无需重启**。
- 读侧接口：缩略图 `/x_message_assemble_communicate/jaxrs/im/msg/download/{id}/image/width/{w}/height/{h}`；原图 `…/download/{id}`。

### 4.2 前端 `img onerror` 自动重试（`patch/imgretry/patch_img_retry.py`）

构建期把通用重试器追加进 **`o2_core/o2.js`（PC）/ `o2_core/o2.min.js`（移动端 `appIM.html`）**：
`document` 捕获阶段 `error` 监听 + 同源路径白名单（`/jaxrs/im/msg/download/`、UniversalPreview）
+ 每元素最多 3 次退避重试 + `_o2r` 破缓存。标记 `O2-IMG-RETRY`。
**e2e 判据**：`window.__o2ImgRetryInstalled===true`；真实图 `naturalWidth>0` 不重试；404 的 IM 图重试并加 `_o2r`；非 IM 路径不重试。

## 5. NAS SMB 不稳 = 温床（现在已与在线服务解耦）

`ping 192.168.1.2` 通但 `:smb` 报 `STATUS_INSUFFICIENT_RESOURCES` / `i/o timeout` —— **TCP 可达 ≠ SMB 服务可用**。
本地权威架构下 NAS **只做后台镜像**，其抖动**不再影响在线读写**；仍建议排查 NAS 侧（SMB 版本协商、会话/句柄泄漏、休眠策略、网络）。

> 尾注：O2OA 上传是"异步写 + 前端立即渲染"，刚发出的一瞬可能短暂破图，刷新即好；
> §4.2 的 `img onerror` 重试即为此。

## 6. 持久化：升级 / 重装不丢数据与程序（★ 用户核心诉求）

| 关注点 | 载体 | 重装是否丢 | 兜底 |
|---|---|---|---|
| 附件文件（权威） | `./dufs-data`（bind mount） | 换机丢 | `backup_o2oa_chain.bat` 备份；NAS 为二级镜像 |
| 附件文件（冷备） | NAS `192.168.1.2` | 否 | 持续镜像 |
| 附件记录 | MySQL（命名卷 `mysql-data`） | 否 | 全量 `mysqldump` |
| 存储层配置 | `docker-compose.yml`（git 真源） | 否 | 入仓 + 备份 + 漂移门禁 |
| 程序/镜像 | git 仓 + `docker save` 镜像 tar | 否 | bundle + `_images/` |

**rclone 版本钉死**：`image: rclone/rclone:1.75.2`（**禁用 `:latest`**）。升级前须在测试环境复验写后立即可读性。

## 7. 固化纪律（六件套）

存储层任何修复**必须**走完：
① 知识库化 `docs/knowledge_base/im_image_storage_write_race_20261012.md` → `python tools/ingest_knowledge_base_docs.py`
② 技能化（本 skill）→ `bash tools/sync_skills_to_repos.sh`（镜像两仓）
③ 档案 `tools/o2_docs_audit.py --all` 刷 `docs/DOC-STATUS.md`
④ 推 `o2oa-driver`（`tools/push_o2oa_driver_clean.sh`）
⑤ 备份 `tools/backup_o2oa_chain.bat`
⑥ 改 `docker-compose.yml`/前端补丁 **即真源** → 入仓 + 备份 + 门禁断言 + `docker compose up -d --no-deps --force-recreate --pull never <svc>` 使运行时==声明。

## 8. 相关 skill

- `o2oa-runtime-drift-hardening` —— 「改动只进容器/卷、没进镜像/仓库」的通用漂移审计。
- `o2oa-onlyoffice-attachment-preview` —— 附件**在线预览**走下载（前端/控件/缓存层）。
- `o2oa-onlyoffice-editor-features` —— 验证文件确在 rclone 存储器的 headless 探测法。
- `o2oa-log-triage-health` —— 附件相关报错在问题日志里的排查入口。
- `o2oa-process-duty-governance` —— 审批人按组织职务指派（含本文提到的图片链路排查无关，但组织解析同源）。
