# O2OA 桌面「菜单入口」的三个数据源（附一次"假 PASS"的教训）

## 1. 问题

新增一个自研桌面组件后，**组件能打开，但菜单里找不到入口**。
或者更隐蔽：菜单里能看到，但**换个入口进去就没了**。

根因：O2OA 桌面有**三套互相独立**的菜单，数据源完全不同。只改一处 = 只改了一半。

## 2. 三套菜单对照表

| 菜单 | 长什么样 | 数据源 | 写入方式 |
|---|---|---|---|
| ☰ 开始菜单 | 白色**图标网格**，页签「应用/流程/信息/数据」 | MySQL `CPT_COMPONENT` 表 | SQL INSERT，或官方 REST |
| **门户首页「应用菜单」** | 左侧竖排分组；窄屏变**深蓝分栏大菜单** | 门户数据字典 `appmenus`（`GEN_DICT`/`GEN_DICT_ITEM`） | 门户设计器 REST（整对象 PUT） |
| 桌面「系统管理」分组 | 系统管理类应用的归类列表 | `config/components.json` 的 `systems` 数组（**种子**） | 改 JSON 文件 + DB 行，重启 |

> ★ 关键：**门户首页那份菜单完全不看 `CPT_COMPONENT` 和 `components.json`**。
> 写错地方时，☰ 网格里能看到（于是自测"通过"），但门户首页永远看不到 —— 这正是"假 PASS"的来源。

## 3. 判定：菜单到底由谁驱动

不要猜，用**顺序 + 数量**三重互证：

1. 截图里各栏的**标题顺序**，与字典 `appNavis[i].title` 的顺序逐项对照；
2. 某一栏的**子项个数**，与字典 `appNavis[i].children.length` 对照；
3. 直接渲染 `portal.html?id=<portalId>`，打印分组标题，与字典比对。

本项目实测：截图 8 栏的顺序 = 字典分组 2–9 的顺序；「人事管理」栏 9 项 = `appNavis[2].children` 的 9 项。⇒ 确认为字典驱动。

## 4. 读写门户字典

### 4.1 读（任意登录用户可用）

```bash
# flag 是「门户 alias」，通常为 index —— 写 /portal/dict/data 会 500
GET /x_portal_assemble_surface/jaxrs/dict/{alias}/portal/{flag}/data
```

返回体里 `data.appNavis[]` 就是分组数组，每项含 `title / icon / children[]`，
`children[]` 项含 `actionType / app / title / icon / allow[] / hide`。

### 4.2 写（surface 侧 PUT 恒 405，必须走 designer）

```bash
PUT /x_portal_assemble_designer/jaxrs/dict/{dictId}
Body: { "id", "name", "alias", "application", "data": "<字符串化的内层 data>" }
```

★ 整对象覆盖，**必须先 GET 完整对象、只改目标字段、再 PUT 回去**。
改完**刷新页面即生效，不需要重启**。

### 4.3 新增一个入口项

```json
{
  "actionType": "app",
  "app": "SysSetting",
  "title": "系统设置",
  "icon": "config",
  "allow": [],
  "hide": false,
  "level": 1.0
}
```

- `app` = `x_component_` 之后的**目录名**（先用 `curl` 验证 `x_component_<app>/Main.js` 是否为 200）；
- `allow: []` = 不限角色；
- `icon` 选字典里**已出现过的名字**（如 `config`），避免图标裂图。

## 5. 验证：必须走真实用户路径

```
打开 portal.html?id=<portalId>
  → 展开目标分组
  → 断言条目在列
  → 点击该条目
  → 断言组件真的渲染出来（容器节点存在 + 无 JS 报错）
```

**只查 `.layout_start_item_text`（☰ 网格）会给出假 PASS。**
本项目第一版验证脚本就是这么写的，结果用户一眼看穿"菜单里根本没有"。

## 6. 顺带记的两个坑

- **官方字段拼写是 `dentyList`（不是 denyList）**，`components.json` 里照抄别改。
- 只要求出现在**开始菜单**、不要求归类时，用官方 REST 最省事：
  `POST /x_component_assemble_control/jaxrs/component {name,path,title,iconPath,orderNumber,visible}`
  （该接口强制 `setType("custom")`）。
