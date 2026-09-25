# O2OA 脚本沙箱硬化 · 看门狗（持续化守护）

> 配套脚本：`tools/o2_sandbox_harden_watchdog.py`
> 适用：本地 Docker 自托管 O2OA 10.0.2（社区版，已断云）

## 0. 它解决什么问题

脚本沙箱反射越权（CVE 类沙箱逃逸）已通过两条**声明式**通道固化：

1. **Dockerfile** 把合并版 `patch/x_base_core_project.patched.jar` 烤进 `o2oa:10.0.2` 镜像；
2. **`patch/o2oa_rebuild_patches.sh`【步骤 2b】**在 `upgrade_o2oa.sh` 升级时自动重放硬化。

但运行态仍会因以下动作**静默漂移**（这些动作不触发升级脚本，O2OA 侧零报错）：

- 有人手工 `docker cp` 覆盖 `store/jars/x_base_core_project.jar` 做回滚/调试；
- 一次异常升级 / 运维操作重置了 jar；
- `docker compose up` 误拉到未含硬化的旧镜像（分支没切对）。

看门狗把硬化**持续化**：周期巡检运行容器的 live jar，发现漂移立刻从代码级黄金副本自动重放。

## 1. 工作原理（规避本机 ARM64/QEMU 坑）

- **不依赖 `docker exec`**：本机重启后偶发 `setns` 失败（`fork/exec /proc/self/fd/6: no such file or directory`），exec 不可靠；
- 全程 **`docker cp` 拉文件 + `zipfile` 算哈希**，零 exec、零 JVM 依赖；
- 每 `POLL_INTERVAL`（默认 300s）校验：
  1. `docker cp` 拉出容器内 `store/jars/x_base_core_project.jar` 到本地临时文件；
  2. 算 `com/x/base/core/project/scripting/GraalvmScriptingFactory.class` 的 SHA-256，并检查 `ScriptHostAccessPolicy.class` 是否存在；
  3. 与黄金副本 `patch/x_base_core_project.patched.jar` 比对 → 一致且含策略类 = 健康；否则 = 漂移；
- 漂移时自动重放：`docker cp` 黄金 jar → 容器 → `docker restart` → 重跑 `o2oa_netlock.sh`（Docker 重启会丢 iptables，必须重锁）。

## 2. 用法

```bash
# 前台循环（Ctrl-C 退出）
python tools/o2_sandbox_harden_watchdog.py

# 只校验一次（CI / 手动），返回 0=健康 / 1=漂移
python tools/o2_sandbox_harden_watchdog.py --once

# 自定义轮询间隔（秒）
python tools/o2_sandbox_harden_watchdog.py --interval=600

# 注册为系统服务（开机自启，真·持续化）
python tools/o2_sandbox_harden_watchdog.py --install
```

配套：

- `tools/run_sandbox_watchdog.bat` —— 双击在后台拉起（当前开机会话内持续）；
- `tools/install_watchdog_task.bat` —— 以管理员运行，注册 Windows 计划任务（跨重启持续化）；
- `tools/o2_sandbox_harden_watchdog.service` —— Linux 主机 systemd 参考模板（`--install` 会自动写并 enable）。

## 3. 状态与日志

- 日志：`tools/o2_sandbox_harden_watchdog.log`（每次巡检一行 `[HEALTHY]` / `[DRIFT]` / `[REAPPLY]`）；
- 状态快照：`tools/.watchdog_state.json`（最近一次检查结果 + 累计漂移次数）；
- 退出码：`--once` 模式下 `0`=健康，`1`=漂移（适合接入 CI / 监控告警）。

## 4. 与固化通道的关系

| 层 | 机制 | 防什么 |
|---|---|---|
| 镜像层 | Dockerfile 烤入合并 jar | 容器重建丢硬化 |
| 升级层 | o2oa_rebuild_patches.sh 步骤 2b | 升级冲掉硬化 |
| 运行层 | **本看门狗** | 运行态手工/异常漂移 |

三层互补：前两层是「声明式基线」，看门狗补上「运行态持续守护」，构成完整闭环。

## 5. 回滚 / 停用

- 停用看门狗：结束进程（或 `schtasks /Delete /TN O2OA_SandboxHardenWatchdog /F`）；
- 回滚硬化本身：把 `patch/x_base_core_project.before_harden.jar`（或 `live_before_deploy.jar`）
  `docker cp` 回 `store/jars/` + 重启 + 重跑 `o2oa_netlock.sh`；看门狗若仍在跑会再次把它「修回」硬化——
  故回滚前应先停用看门狗。
