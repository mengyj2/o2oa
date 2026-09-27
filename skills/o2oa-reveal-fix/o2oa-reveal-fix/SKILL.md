---
name: o2oa-reveal-fix
description: O2OA 首页「公文管理 Reveal 对象已存在」+ 登录 randomWithWeight 双根因闭环修复、ActionGet文案硬化+Lucene索引重建路径。覆盖：Reveal配置丢失/门户硬编码id悬空真根因、ExceptionEntityExist→NotExist war层固化、entrypoint等MySQL就绪根治、Lucene索引建立GUI路径。
agent_created: true
category: operations
---
# O2OA 公文管理 Reveal 双根因与闭环修复技能

## 1. 故障现象
- **首页门户「公文管理」**：打开报 toast `标识为 8dcfe604-b179-47e9-8879-86435b173706 的 Reveal 对象已存在.`
- **同日全员登录**：`randomWithWeight error: com.x.base.core.project.x_organization_assemble_express. count=0`，且一天内**复发三次**（第三次即本次排查）

## 2. Reveal 报错真根因（不是\"已存在\",是\"不存在\"）
- 自建 war `x_custom_index_assemble_control` 的 `ActionGet.java:36` 在 `null == reveal` 时误抛 `ExceptionEntityExist(flag, Reveal.class)`——基类文案「…对象已存在」与语义完全相反（实际是查不到）。
- 门户部件 `PTL_WIDGET`（id `3606910b-9154-49c1-819b-621d002dd63c`，名「部件-公文台账」）脚本**硬编码**：
  `new MWF.xApplication.StandingBook.RevealView(node, app, {}, [{id:'d8cfe604-bf79-47e9-8879-86435b173706'}])`
- 数据表 `X.CUS_INDEX_REVEAL` **0 行**（配置从未成功持久化或早已丢失）→ 门户入口引用悬空，导致前端报"对象已存在"（实为对象根本不在表里）。

### 修复（已执行，可复用）
1. `POST /x_custom_index_assemble_control/jaxrs/reveal`（注意根路径，非 `/create`），body包含 name/enable/ignorePermission/availableList/cmsList/processPlatformList + data 6字段（标题/流程/文号/拟稿人/拟稿部门/到达时间），公文管理应用 id `204be54d-c00a-45e7-8f69-30261defe214`。
2. API 返回新 id 后，`UPDATE X.CUS_INDEX_REVEAL SET xid='d8cfe604-bf79-47e9-8879-86435b173706'` 并同步重算 `xsequence`（=14位时间戳+xid），保持门户硬编码引用有效；浏览器缓存零影响。
3. 重启 o2oa 刷新 Guava 缓存；`GET reveal/<旧id>` 回读 200 success，`listEditable` count=1。

**长期建议**：把 `ActionGet` 的 `ExceptionEntityExist` 改为 `ExceptionEntityNotExist`（本次已完成 war层覆盖，见下节）。

## 3. randomWithWeight 复发的真根因（启动竞态，非数据坏）
- 取证：`out.log` 显示 o2oa 启动瞬间 `DruidDataSource - init datasource error, url: jdbc:mysql://mysql:3306/X` + `get entityManager for class com.x.organization.core.entity.Role error`（OpenJPA 连接不可得）。
- **因果链**：整机/Docker daemon 重启 → 容器按 `restart: unless-stopped` 各自拉起，**compose 的 `depends_on: condition: service_healthy` 不被重新评估** → o2oa 首建 EntityManager 时 mysql 未就绪 → `x_organization_assemble_express` 等组织模块带 DB 失败加载出【空内存组织缓存且不重试】 → 登录计算角色列表拿到空集合 → `randomWithWeight count:0` 500。
- 手工 `docker restart` 恰好发生在 mysql 已就绪之后，所以\"看起来治好”。**真根因是启动竞态，非 H2 损坏或 express 缓存病。**

### 根治（已固化进镜像 `o2oa:10.0.2`）
`entrypoint.sh` 在 `exec java` 前新增阻塞探测 MySQL 就绪：
```bash
DB_HOST="${O2OA_DB_HOST}"
DB_PORT="${O2OA_DB_PORT}"
echo "[entrypoint] 等待数据库就绪 ${DB_HOST}:${DB_PORT} ..."
DB_WAIT_OK=""
for i in $(seq 1 60); do
  if (exec 3<>\"/dev/tcp/${DB_HOST}/${DB_PORT}\") 2>/dev/null; then
    exec 3>&- 3<&- || true
    DB_WAIT_OK=1
    echo "[entrypoint] 数据库端口已就绪（第 ${i} 次探测）"
    break
  fi
  sleep 2
done
if [ -z "$DB_WAIT_OK" ]; then
  echo "[entrypoint] ! 等待数据库超时（120s），仍尝试启动 O2OA..."
else
  sleep 3
fi
```
- 已提交 git `4a65877`（feature/o2oa-ai-stack），随 `docker compose build` 自动烤入镜像。
- 启动日志出现 `[entrypoint] 数据库端口已就绪（第 1 次探测）` 即生效，登录 30s 内 200 success。

## 4. ActionGet 文案硬化（war 层）
- **改写**：把 `x_custom_index_assemble_control` 的 `ActionGet.java` 中的 `if (null == reveal) throw new ExceptionEntityExist(flag, Reveal.class);` 改为 `throw new ExceptionEntityNotExist(flag, Reveal.class);`
- 同样替换 import 行：`import com.x.base.core.project.exception.ExceptionEntityExist;` → `ExceptionEntityNotExist`
- 已 repack war 并覆盖至容器 `/opt/o2server/webroot/`。查不到实体时不再报误导性\"已存在\",而正确抛\"找不到\"。

## 5. 「环节」动态列补齐（Lucene索引 → 数据配置）
- 现状：`dynamicFieldList=0`（Lucene索引未建，故无「环节」列等 dynamic 字段）。
- 路径：
  1. **门户 GUI**：进入 O2OA 首页→「数据配置」→选择公文管理应用 id `204be54d-c00a-45e7-8f69-30261defe214` → 重建全文 Lucene 索引。
  2. **完成后**：通过 `/jaxrs/reveal/directory/field` 读取固定/facet/dynamic 三组字段，把「环节」等 dynamic 列映射到 Reveal 页面展示。
  3. **验证**：`GET reveal/<旧id>` 回读 `count ≥ 1`，「环节」列出现且可编辑。

> **显存提醒**：本机 4GB VRAM。embed(~0.6B) + rerank(1.2G) 若强制开启可能 OOM embed/网关。默认 `rerank_enable:false`（config.json），保稳定；仅在显存余量充足时开启。

## 6. 方法论沉淀
1. **报错文案 ≠ 根因语义**：O2OA 生态里 `ExceptionEntityExist`/`NotExist` 常被混用，自研代码更甚——以堆栈 + SQL 行数为准。
2. **\"偶发\"故障先查时间线**：把故障时刻与容器启动/重启时刻对齐（`docker ps` RunningFor、日志起始时间），往往一眼看出竞态。
3. **depends_on 只管 compose 编排，不管 daemon 重启**：开机自愈场景必须用 entrypoint 级 wait-for 或应用层重试兜底。
4. **门户部件硬编码实体 id 是悬空引用隐患**：组件重建/配置丢失后表现为\"对象已存在\"这类误导性报错；配置应尽量走菜单/字典引用。
5. `CUS_INDEX_REVEAL` 空 + 门户硬编码 id 的组合，用「API 建配置 + SQL 改回旧 xid」可以零前端改动修复，且浏览器缓存无需清理。

## 7. 已灌入本地 RAG
- 文档 `docs/knowledge_base/o2oa_reveal_missing_and_boot_race.md` 已经通过 `tools/ingest_o2oa_kb.py` 的 `post_doc` 灌入本地知识库（`o2kb::o2oa_ops::reveal_missing_and_boot_race`，type:success，已向量化入 `data.db`）。
- 检索路径：向量分(0.6)+rerank分(0.4)，失败自动回退向量 top_k。
