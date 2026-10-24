# CMS 移动端 v10 表单编辑器崩溃修复（「新建供应商闪一下」真身）

> doc-rev: v1.0 · 2026-10-24 · 适用：本地 Docker 自托管 O2OA 10.0.2（分支 feature/o2oa-ai-stack / cnccia-custom）
> 关联任务：供应商链路（#47）根因段；与「财务页 reading 'application'」（#49）是**不同** bug，勿混。

---

## 0. 一句话结论

「供应商-新建供应商，闪一下变成未找到数据」的真身不是数据问题、不是权限问题：**点确定后文档已创建成功（POST 200），但跳转移动端文档编辑器时 `cms_Xform/Form.js` 的 `checkDatatableClass` 引用了一个 `$all` 打包清单里根本不存在的类 `MWF.xApplication.process.Xform.DatatableV10`（undefined），`MWF.CMSDatatable.implement(...)` 抛 `TypeError: Cannot read properties of undefined (reading 'implement')`，编辑器永远停在 loading**——用户视觉上就是「闪一下就没了/回到未找到数据」。这是**上游原样 bug**（`git diff upstream/master` 无差异），全部 v10 表单的移动端编辑全崩（固定资产文档同样实证）。

---

## 1. 根因链（五环，每环有实证）

| # | 环节 | 事实 | 证据 |
|---|---|---|---|
| 1 | 打包清单缺件 | `gulpfile.js::build_concat_cms_xform` 的 src 清单**不含** `process_Xform/DatatableV10.js`，也不含 `cms_Xform/Datatable.js` | 读 gulpfile L610-703 + grep `cms/$all.js` 无 `DatatableV10 = new Class` 定义 |
| 2 | 运行态缺类 | 移动端编辑器页（`cmsdocmobilewithaction.html`）链 = `o2.min.js → base_document → o2m.api → cmsDocMobile + cms/$all(.min).js`，**不含** process Datatable 链 | 页面 script 清单 + 探针 `preDutV10="undefined"` |
| 3 | 代码裸引 | `cms_Xform/Form.js::checkDatatableClass` 在 `(layout.mobile\|\|isMobile) && formStyleType==='v10'` 时直接 `MWF.CMSDatatable = ...DatatableV10` 后 `.implement(...)` | 源码 L289-296 |
| 4 | 崩溃 | `undefined.implement` 抛 TypeError，`load()` 中断，编辑器永停 "loading..." | 浏览器栈：`at Object.checkDatatableClass → at Object.load → at base_document.min.js` |
| 5 | 上游原样 | 该代码与 upstream/master **逐字一致**，非本项目引入 | `git diff upstream/master HEAD -- o2web/source/x_component_cms_Xform/Form.js` 无差异 |

**为什么 PC 不崩**：桌面链（index.html）会加载 process.Xform 全套（含 DatatableV10），同一函数在 PC 上 `DatatableV10` 已就绪。移动端链不加载——所以只有移动端编辑器崩。

**为什么「闪一下变未找到数据」**：文档创建成功（POST `/x_cms_assemble_control/jaxrs/document` 200）→ 跳编辑器 → 崩 → 用户返回列表 → 列表按 category 查 CMS 文档（空）显示「未找到数据」。三个现象叠加被感知为一件事。

---

## 2. 修复（源码 + 产物 + 构建期三处同改）

### 2.1 源码（真源仓 D:\o2oaccia）
`o2web/source/x_component_cms_Xform/Form.js` `checkDatatableClass`：

```js
// 修复后
MWF.xDesktop.requireApp("cms.Xform", "Datatable", null, false);   // 同步补链
if( MWF.xApplication.process.Xform.DatatableV10 ){
    MWF.xApplication.cms.Xform.Datatable = MWF.CMSDatatable = MWF.xApplication.process.Xform.DatatableV10;
    if( MWF.CMSDatatableFeature ) MWF.CMSDatatable.implement(MWF.CMSDatatableFeature);
    MWF.xApplication.cms.Xform.Datatable$Title = MWF.CMSDatatable$Title = MWF.xApplication.process.Xform.DatatablePC$Title;
    MWF.xApplication.cms.Xform.Datatable$Data = MWF.CMSDatatable$Data = MWF.xApplication.process.Xform.DatatablePC$Data;
}
```

**补链原理**（依赖链实查）：`cms_Xform/Datatable.js` 首行 `requireApp("process.Xform","Datatable",null,false)`（同步）→ `process_Xform/Datatable.js` 同步带上 `$Module/DatatablePC/DatatableMobile/DatatableV10` 并定义 `MWF.CMSDatatableFeature`。即一次同步 require 同时补足「类」与「Feature」两样东西。守卫保证极端缺类时保持原状不崩溃。

### 2.2 构建产物（4 文件，两条独立路径字节级一致）
- `Form.js` / `Form.min.js` / `$all.js` / `$all.min.js`（均在 `x_component_cms_Xform/`）
- 生成路径 A（真源仓）：`tools/patch_cms_xform.py`（运行时官方原件 + 外科替换）
- 生成路径 B（驱动仓构建期）：`patch/cmsxform/patch_cms_xform_datatable.py`（镜像内官方原件 + 同款替换，幂等带 `O2-CMS-DATATABLE-V10` 标记）
- **两路径产物 4/4 diff=0**（回归测试实证）
- ⚠️ `$all(.min).js` 内有两处同名 `checkDatatableClass`：另一处是 **process 版**（赋 `MWF.APPDatatable`，PC 路径，功能正常），只能改 CMS 版那处（赋 `MWF.CMSDatatable`）

### 2.3 构建期烤入（驱动仓 D:\O2OA）
- `patch/web/x_component_cms_Xform/` 放入 4 个补丁文件（沿用 2026-10-10 preview 补丁的「COPY patch/web + 构建期 RUN」机制）
- Dockerfile 追加 `RUN python3 .../patch_cmsxform/patch_cms_xform_datatable.py "${O2OA_HOME}/servers/webServer/x_component_cms_Xform"`（兜底重建，幂等）
- 真源仓 Dockerfile 同步 4 行 `COPY patch/web/x_component_cms_Xform/...`（`$all` 字面量已按 `\$Layout` 教训转义）

---

## 3. 验证矩阵（全部实跑）

| 层 | 方法 | 结果 |
|---|---|---|
| 产物语法 | `node --check` ×4 | 4/4 OK |
| 双路径一致 | diff A路径 vs B路径 | 4/4 逐字节相同 |
| 镜像层 | `docker run --rm o2oa:10.0.2 md5sum` vs 仓库 | 4/4 相同 |
| 部署态 | `docker cp` 提取运行容器 4 文件 md5 | 4/4 相同 |
| HTTP 层 | `curl /x_component_cms_Xform/$all.min.js` md5 | 与补丁版相同，守卫在位 |
| 浏览器函数级 | 双注入对照探针（`e2e_datatable_verify.js`，C:\temp） | 见下 |

**浏览器三连实证（正向+反向排除+环境真实）**：

```
A 补丁版注入（移动端真实链）: preDutV10=undefined → called=true, sameClass=true,
                              featureImplemented=true, postDutV10=function, 零 pageerror
B 官方旧版注入（同环境对照）: TypeError: Cannot read properties of undefined (reading 'implement')
判定: PASS — 崩溃环境真实复现，修复有效，官方版同环境必崩（根因唯一）
```

B 组错误信息与线上崩溃栈**一字不差**——根因闭环。

---

## 4. 复现指南

```bash
# 探针（已存 C:\temp\e2e_datatable_verify.js）
cd /c/temp && NODE_PATH='C:\Users\meng_\.workbuddy\binaries\node\workspace\node_modules' \
  '/c/Users/meng_/.workbuddy/binaries/node/versions/22.22.2-6/node.exe' e2e_datatable_verify.js
```
注：playwright 浏览器用本机 1243 headless shell（`executablePath` 已写死）；页面用真实 `cmsdocmobilewithaction.html`（无参打开，静态链+o2 基础即够）；两组唯一变量=注入的 $all 版本。

## 5. 遗留与注意

1. **登录端到端未跑**：API 登录凭据检索被沙箱敏感审批拦截（grep /c/temp 与 skill 加载均超时）。待用户提供 mengyijie 密码或授权路径后，补「登录→新建供应商→编辑器渲染出表单」全链路截图。
2. `$all.min.js` 的 preview 补丁（O2-UNIVERSAL-PREVIEW）在 min 版上**设计性跳过**——官方 min 本含 `previewUniversal:function` 定义（脚本幂等检测）。未压缩 `$all.js` 正常打入。此为 2026-10-10 既有行为，非本次回归。
3. 供应商列表「未找到数据」在补丁修复后即可通过正常新建流程产生数据；Task #48（造测试数据）在其后执行。
4. 若升级 O2OA 版本：先核对上游是否已修此函数（`git log upstream/master -- x_component_cms_Xform/Form.js`），已修则删除本项目补丁（防补丁变包袱）。
