# O2OA 实战：首页「Reveal 对象已存在」+ 登录 randomWithWeight 复发 —— 双根因与根治

> 2026-09-25 实测验证 · 全部结论有命令/日志证据 · 随镜像/升级自动重放

## 一、现象

1. 首页门户打开「公文管理」报 toast：`标识为8dcfe604-b179-47e9-8879-86435b173706 的 Reveal 对象已存在.`（实际日志 id 为 `d8cfe604-bf79-...`，截图识别偏差）。
2. 同日全员交互式登录 500：`randomWithWeight error: com.x.base.core.project.x_organization_assemble_express. count=0`，且一天内**复发三次**。

## 二、Reveal 报错根因（不是"已存在"，是"不存在"）

链路取证：

- 日志：`GET /x_custom_index_assemble_control/jaxrs/reveal/d8cfe604-bf79-...` →
  `ActionGet.java:36` 抛 `ExceptionEntityExist`。
- 自建 war `x_custom_index_assemble_control`（StandingBook 台账引擎后端）的 `ActionGet`：
  `if (null == reveal) throw new ExceptionEntityExist(flag, Reveal.class);`
  —— O2OA 基类 `ExceptionEntityExist` 的文案就是「…对象已存在」，
  **自研代码在"查不到"时误用了这个类**，文案完全误导（应为 NotExist）。
- 首页门户部件 `PTL_WIDGET`（`3606910b-...`，名「部件-公文台账」）的脚本**硬编码**：
  `new MWF.xApplication.StandingBook.RevealView(node, app, {}, [{id:'d8cfe604-bf79-...'}])`。
- 数据表 `X.CUS_INDEX_REVEAL` **0 行**（09-24 备份里也是 0 行，且仅在错误日志里出现该 id）
  → Reveal 展示配置**从未成功持久化或早已丢失**，门户入口引用悬空。

### 修复（已执行，可复用）

1. `POST /x_custom_index_assemble_control/jaxrs/reveal`（注意根路径，不是 /create）
   body：`{name, enable:true, ignorePermission:false, available*List:[], cmsList:[],
   processPlatformList:[{category:'processPlatform', name:'公文管理', key:<应用id>}],
   data:[{field,text,name,fieldType,display,displayDefault,filter}...]}`。
   可用字段来源：`POST /jaxrs/reveal/directory/field`（fixed/facet/dynamic 三组；
   动态字段需该应用 Lucene 索引已建，否则为空 →「环节」列等索引建好后经「数据配置」补）。
   公文管理流程应用 id：`204be54d-c00a-45e7-8f69-30261defe214`。
2. API 生成新 id 后，`UPDATE X.CUS_INDEX_REVEAL SET xid='<门户引用的旧id>'`
   并同步重算 `xsequence`（=14位时间戳+xid）——保持门户硬编码引用有效，浏览器缓存零影响。
3. 重启 o2oa 刷新 Guava 缓存；`GET reveal/<旧id>` 回读 200 success。
4. 长期建议：把 `ActionGet` 的 `ExceptionEntityExist` 改为 `ExceptionEntityNotExist`
   （本次未改 war，只修了数据）。

## 三、randomWithWeight 复发的真根因（此前"重启即愈"只是假象）

取证：`out.log` 显示 o2oa 启动瞬间
`DruidDataSource - init datasource error, url: jdbc:mysql://mysql:3306/X` +
`get entityManager for class com.x.organization.core.entity.Role error`（OpenJPA 连接不可得）。

因果链：**整机/Docker 守护进程重启 → 容器按 restart 策略各自拉起，compose 的
`depends_on: condition: service_healthy` 不被重新评估 → o2oa 首建 EntityManager 时
mysql 未就绪 → x_organization_assemble_express 等组织模块带着 DB 失败加载出
【空内存组织缓存】且不重试 → 登录计算角色列表拿到空集合 → randomWithWeight(count=0) 500**。
手工 `docker restart` 恰好发生在 mysql 已就绪之后，所以"看起来治好"。

### 根治（已固化进镜像）

`entrypoint.sh` 在 `exec java` 前新增阻塞探测：

```bash
for i in $(seq 1 60); do
  if (exec 3<>"/dev/tcp/${O2OA_DB_HOST}/${O2OA_DB_PORT}") 2>/dev/null; then break; fi
  sleep 2
done
# 端口就绪后再 sleep 3，给 InnoDB recovery/握手留余量
```

启动日志出现 `[entrypoint] 数据库端口已就绪（第 1 次探测）` 即生效。
已提交 git `4a65877`（feature/o2oa-ai-stack），随 `docker compose build` 自动烤入。

## 四、方法论沉淀

1. **报错文案 ≠ 根因语义**：O2OA 生态里 `ExceptionEntityExist`/`NotExist` 常被混用，
   自研代码更甚——以堆栈 + SQL 行数为准。
2. **"偶发"故障先查时间线**：把故障时刻与容器启动/重启时刻对齐（`docker ps` RunningFor、
   日志起始时间），往往一眼看出竞态。
3. **depends_on 只管 compose 编排，不管 daemon 重启**：开机自愈场景必须用
   entrypoint 级 wait-for 或应用层重试兜底。
4. **门户部件硬编码实体 id 是悬空引用隐患**：组件重建/配置丢失后表现为
   "对象已存在"这类误导性报错；配置应尽量走菜单/字典引用。
5. `CUS_INDEX_REVEAL` 空 + 门户硬编码 id 的组合，用「API 建配置 + SQL 改回旧 xid」
   可以零前端改动修复，且浏览器缓存无需清理。
