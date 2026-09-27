---
name: o2oa-market-offline-install
description: 断云 O2OA 10.0.2（Docker）上离线安装应用市场应用包（setup.json+xapp 结构 zip）的完整链路：接口、鉴权、批量安装、冲突判断、卸载限制。触发词：离线安装、应用市场、导入 zip 应用、安装应用没反应、组件资源、确定按钮无反应、卸载应用、InstallLog。
agent_created: true
category: operations

---

# O2OA 市场应用离线安装（断云可用）

## 0. 一句话

市场应用包（`setup.json` + `xapp/*.xapp` + `data/` `web/` `custom/`）的正确安装入口是
**`POST /x_program_center/jaxrs/market/install/offline`**（multipart 字段 `file`），
**绝不是** 系统设置→组件资源（那个「确定」按钮在 10.0.2 必挂，见技能 o2oa-local-admin-account 同目录经验）。

## 1. 包结构鉴定（先看装的是什么）

用 python zipfile 列顶层 + 读 `setup.json`：

| 顶层结构 | 类型 | 安装方式 |
|---|---|---|
| `setup.json` + `xapp/`(+data/web/custom) | 应用市场包 | 本技能 market/install/offline |
| 只有前端资源（无 setup.json） | 组件/web 资源 | deployWebResource + ComponentAction.create |

注意同 id 重复包：不同文件名的 zip 可能 `setup.json` id 完全相同（如 PDF预览 与 webserver资源管理），
安装即覆盖同一应用，不会产生第二个实例。

## 2. 鉴权：cipher token（免登录，20 分钟有效）

MkToken.java 常驻容器 `/tmp/work`（源码见技能 o2oa-local-admin-account）：

```bash
docker exec o2oa-server sh -c 'D=/opt/o2server; CLS="."; for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do CLS="$CLS:$j"; done; $D/jvm/linux_java11/bin/java -cp "/tmp/work:$CLS" -Duser.dir=$D MkToken'
```

请求头 `x-token: <输出值>`。**超过 20 分钟必 401，重新生成即可**。

## 3. 安装（★中文路径必须走容器内 curl）

宿主 Git Bash 的 curl 读不了中文路径的 `@file`（curl 26）。
正确姿势：**docker cp 进容器 → 容器内 curl 127.0.0.1:9090**（center/app/web 同端口）：

```bash
docker exec o2oa-server mkdir -p /tmp/pkg
docker cp "E:/某目录/应用包.zip" o2oa-server:/tmp/pkg/app.zip
docker exec o2oa-server sh -c '
  TK=$(/opt/o2server/jvm/linux_java11/bin/java -cp "/tmp/work:$CLS" -Duser.dir=/opt/o2server MkToken)
  curl -s --noproxy "*" -X POST -H "x-token: $TK" -F "file=@/tmp/pkg/app.zip" \
    http://127.0.0.1:9090/x_program_center/jaxrs/market/install/offline'
```

成功响应：`{"type":"success","data":{"value":true}}`（大包 8~10s）。批量就 for 循环，token 生成一次够用。

服务端行为（源码 ActionInstallOffline/BaseAction）：解包到 `local/temp/install/{id}/data/`
→ 读 `setup.json` → 按 `custom/`(war) `xapp/`(应用) `web/`(前端资源) `config/` 分目录部署
→ 写 `InstallLog`。**断云安全**：loginCollect 取云市场信息失败会被吞掉。

## 4. 验证与冲突判断（勿被 InstallLog 骗）

- 安装记录：`POST /x_program_center/jaxrs/market/list/install/log/paging/1/size/200`（**POST** 带 `{}`，GET 会 405）。
- **InstallLog 每装一次新增一条（不同 id），但模块层是幂等的**——重复安装更新同一流程/门户实例。
  判断"重复冲突"必须查模块层，不能数 InstallLog：
  - 流程平台应用：`GET /x_processplatform_assemble_designer/jaxrs/application/list`（GET）
  - 门户：`GET /x_portal_assemble_designer/jaxrs/portal/list`
  - 同名应用各只有 1 个实例 ⇒ 只是安装记录冗余，**没有功能重复，不要删**。

## 5. 卸载的限制（★）

`GET /x_program_center/jaxrs/market/{flag}/uninstall` 要求 x_program_center 的
`Application` 实体与 InstallLog 同 id —— **离线安装根本不创建 Application 实体**（只写 InstallLog），
所以对离线装的应用调用必 500「Application 对象不存在」。本版本卸载离线应用没有可用 API；
模块层删除（`DELETE /x_processplatform_assemble_designer/jaxrs/application/{id}/{onlyRemoveNotCompleted}`）
会连好应用一起删，慎用。

## 6. 浏览器冒烟验证（playwright-core + Edge）

登录用 API 换 token 注 cookie，别走 UI 表单：

```js
const r = await fetch('http://127.0.0.1:9090/x_organization_assemble_authentication/jaxrs/authentication',
  {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential:'mengyijie',password:'…'})});
await ctx.addCookies([{name:'x-token', value:(await r.json()).data.token, domain:'127.0.0.1', path:'/'}]);
await page.goto('http://127.0.0.1:9090/x_desktop/');
```

验证"应用真跑起来了"看**办公中心**（点顶栏 `text=办公中心` 页签）：
待办列表里出现各应用的流程单据（报销申请/用车管理/固定资产…）即为活数据。
注意普通用户（非管理员）打开"门户管理"等设计器页签会显示"没有门户或没有权限"，属正常。
