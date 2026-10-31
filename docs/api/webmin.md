# 极简模式插件系统 `/api/webmin`

> 源码：`src/server/api/webmin.py` ｜ 前缀：`/api/webmin` ｜ 端点：9 个

极简模式（web-minimal）宿主为纯静态页面（`ui/web-minimal`），通过本路由获取插件清单、按需读取插件静态文件（热插拔）、持久化宿主配置，并转发插件自带后端的 RPC 调用。宿主专用，插件一般经 `callAction` 间接使用（见文末「极简宿主与插件的接入方式」）。

**约定**

- 插件来源与优先级：`用户插件`（`~/.purrcat/webmin-plugins`，优先级最高）> `沙盒插件`（`{AGENT_VM_DIR}/ui-plugin`）> `内置插件`（`ui/web-minimal/plugins/builtin`，只读）。同名 `id` 先命中者生效。
- 宿主配置持久化于 `~/.purrcat/settings.json` 的 `webminConfig`，结构为 `{ "plugins": { plugin_id: config }, "rail": {...}, "active": {...} }`。
- 本文件只新增路由，不修改任何现有 `/api/*` 路由行为。
- 所有 `/api/webmin` 响应经中间件附加 `Cache-Control: no-store`（便于热插拔与调试）。

---

## GET `/api/webmin/manifest`

返回当前已扫描到的全部插件列表。新增插件后无需重启，刷新页面即可感知。

**请求**

无请求参数。

**响应**

```json
{
  "plugins": [
    {
      "id": "builtin-history",
      "name": "历史",
      "icon": "history",
      "slot": "panel",
      "slotDef": { "type": "panel", "area": "panel" },
      "entry": "index.html",
      "configSchema": [],
      "config": {},
      "builtin": true,
      "backend": { "kind": "npm" },
      "root": "builtin",
      "origin": "builtin",
      "rootOk": true,
      "dependency": [{ "type": "skill", "id": "xxx" }]
    }
  ],
  "rail": { "stage": 0, "hidden": {}, "opacity": 1 },
  "panelContainer": {},
  "active": { "panel": "builtin-history" }
}
```

每条插件附：`configSchema`（插件自声明）与 `config`（`webminConfig` 中已存值，有效配置 = schema 默认值 ∪ config 覆盖）、`builtin`（是否位于内置根）、`backend`（是否自带后端，有 `server/server.js` 则为 `{ "kind": "npm" }`，否则 `null`）；`root`（声明的期望位置）、`origin`（后端回填的实际所在根）、`rootOk`（两者是否一致）；`dependency` 归一化为 `[{ "type", "id" }]`（类型限定白名单：`skill` / `plugin` / `mcp` / `agentloop` / `sensor` / `graph`）；`slot` 归一化为字符串 id，完整语义见 `slotDef`。

顶层另返回 `rail`（最左图标栏状态：`stage`、`hidden`、`opacity`）、`panelContainer`（宿主中栏容器配置）、`active`（单例槽当前选中的插件 id）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/webmin/manifest'
```

---

## POST `/api/webmin/plugin-rpc/{plugin_id}/{handler}`

调用插件自带后端子进程（`server/server.js`）的 handler。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 | 插件 id（不得含 `/`、`\`、`..`） |
| handler | path | string | 是 | 后端 handler 名 |
| payload | body | object | 否 | 传给 handler 的参数，默认 `{}` |
| timeout | body | number | 否 | 超时秒数，默认 `30.0` |

**响应**

```json
{ "status": "ok", "result": {} }
```

`plugin_id` 缺失或含非法字符返回 `400`；插件不存在返回 `404` 与 `{ "detail": "插件 <plugin_id> 不存在" }`；插件进程执行异常（`PluginProcessError`）返回 `502`，`detail` 为异常信息。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/webmin/plugin-rpc/my-plugin/echo' \
  -H 'Content-Type: application/json' \
  -d '{"payload": {"msg": "hi"}, "timeout": 30}'
```

---

## POST `/api/webmin/plugin-backend/{plugin_id}/{action}`

管理插件自带后端子进程（`server/server.js`）的生命周期。宿主在面板标签打开（iframe 挂载）时自动 `start`，标签关闭（iframe 卸载）时自动 `stop`；
所以改完 `server/server.js` 只需关掉再打开标签就能加载新代码，**无需重启 PurrCat**。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 | 插件 id（不得含 `/`、`\`、`..`） |
| action | path | string | 是 | `start` / `stop` / `restart` / `status` |

- `start`：拉起进程（已在运行则直接返回），响应带 `pid`。
- `stop`：停掉进程（未运行视为成功）。
- `restart`：先停后起，标签页开着也能重启后端。
- `status`：只查询是否在运行，不会拉起进程。

**响应**

```json
{ "status": "ok", "running": true, "pid": 12345 }
```

`stop` / `status` 未运行时为 `{ "status": "ok", "running": false }`。

`plugin_id` 非法或 `action` 未知返回 `400`；插件不存在返回 `404` 与 `{ "detail": "插件 <plugin_id> 不存在" }`；启动失败（如插件没有后端或 `server.js` 未在 15 秒内输出 `ready`）返回 `502`，`detail` 为异常信息。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/webmin/plugin-backend/my-plugin/restart'
```

---

## GET `/api/webmin/config`

读取插件配置。

**请求**

无请求参数。

**响应**

```json
{ "plugins": { "my-plugin": { "key": "value" } } }
```

返回 `webminConfig` 中的插件配置分节；缺失时返回 `{ "plugins": {} }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/webmin/config'
```

---

## PUT `/api/webmin/config`

按分节更新宿主配置（`plugins` / `rail` / `active`），未提供的分节保持原值。前端每次只提交自己修改的分节（例如滑块只提交 `plugins`），避免局部保存把其他分节意外清空。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugins | body | object | 否 | `{ plugin_id: config }`，整体替换 plugins 分节 |
| rail | body | object | 否 | `{ stage, opacity, hidden }`；`stage` 归一化到 `0`–`1`（越界取 `0`），`opacity` 收敛到 `0.0`–`1.0` |
| active | body | object | 否 | `{ area: plugin_id }`，值归一化为字符串，空值项丢弃 |

**响应**

```json
{ "status": "ok" }
```

请求体非 JSON 对象时返回 `400` 与 `{ "detail": "请求体必须是 JSON 对象" }`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/webmin/config' \
  -H 'Content-Type: application/json' \
  -d '{"rail": {"stage": 1, "opacity": 0.9, "hidden": {}}, "active": {"panel": "builtin-history"}}'
```

---

## POST `/api/webmin/plugin/{plugin_id}/delete`

删除插件。用户/沙盒插件被移动为各自根目录下的 `<id>.trash`（可恢复），删除前先停掉其后端子进程；内置插件拒绝删除。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 | 插件 id（不得含 `/`、`\`、`..`） |

**响应**

```json
{ "status": "ok", "deleted": "my-plugin" }
```

`plugin_id` 缺失或含非法字符返回 `400`；位于内置根的插件返回 `403` 与 `{ "detail": "内置插件不可删除" }`；用户/沙盒根下均不存在该插件返回 `404` 与 `{ "detail": "插件 <plugin_id> 不存在" }`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/webmin/plugin/my-plugin/delete'
```

---

## POST `/api/webmin/wallpaper`

把用户选择的本地壁纸复制进托管目录 `~/.purrcat/webmin-wallpapers`（内容未变则复用已有文件），返回可访问的 URL。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | body | string | 是 | 本地壁纸的绝对路径 |

**响应**

```json
{
  "status": "ok",
  "filename": "wallpaper_a1b2c3d4e5f6.png",
  "url": "/api/webmin/wallpaper/wallpaper_a1b2c3d4e5f6.png"
}
```

文件不存在返回 `404` 与 `{ "detail": "壁纸文件不存在" }`；扩展名不在允许集合（`png/jpg/jpeg/gif/webp/bmp/mp4/webm/mov`）返回 `400` 与 `{ "detail": "不支持的壁纸格式: <ext>" }`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/webmin/wallpaper' \
  -H 'Content-Type: application/json' \
  -d '{"path": "C:/Users/me/Pictures/wall.png"}'
```

---

## GET `/api/webmin/wallpaper/{filename}`

静态托管已导入的壁纸文件，做路径穿越校验（`filename` 不得含 `/`、`\`、`..`）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| filename | path | string | 是 | 托管目录内的壁纸文件名 |

**响应**

直接返回文件流（`FileResponse`）。文件名非法返回 `400` 与 `{ "detail": "非法的文件名" }`；文件不存在返回 `404` 与 `{ "detail": "壁纸不存在" }`。

**示例**

```bash
curl -OJ 'http://127.0.0.1:8000/api/webmin/wallpaper/wallpaper_a1b2c3d4e5f6.png'
```

---

## GET `/api/webmin/plugin/{plugin_id}/{path}`

按路径读取插件目录内的静态文件（热插拔核心）。`path` 省略或未命中文件时，回退到该插件 descriptor 声明的 `entry`（默认 `index.html`）。定位在用户/沙盒/内置插件根中依次查找，并做路径穿越校验。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 | 插件 id |
| path | path | string | 否 | 插件目录内的相对文件路径；省略时回退到 `entry` |

**响应**

直接返回文件流（`FileResponse`），MIME 由文件扩展名推断。

未命中任何文件（含回退 `entry` 失败）返回 `404` 与 `{ "detail": "插件 <plugin_id> 资源不存在" }`。路径穿越（越出插件目录）一律视为未命中。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/webmin/plugin/builtin-history/index.html'
```

---

## GET `/api/webmin/plugin-dir/{plugin_id}/{path}`

列出插件目录内某一层的子项（仅名字与是否为目录），供插件自动扫描自身数据目录。只返回一层、不含文件内容，并做路径穿越校验。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 | 插件 id |
| path | path | string | 否 | 插件目录内的相对子目录路径；省略时列出插件根目录 |

**响应**

```json
{
  "path": "data",
  "entries": [
    { "name": "a.json", "isDir": false },
    { "name": "sub", "isDir": true }
  ]
}
```

以 `.` 开头的条目被跳过。目录不存在（越界或未定位到）返回 `404` 与 `{ "detail": "插件 <plugin_id> 目录不存在" }`；列目录异常返回 `500` 与 `{ "detail": "读取目录失败: <err>" }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/webmin/plugin-dir/my-plugin/data'
```

---

## 极简宿主与插件的接入方式

### 两条通道

| 通道 | 适用 | 说明 |
| --- | --- | --- |
| **A. `callAction` 动作总线** | 插件 → 宿主（推荐） | 经 `postMessage` 封装，宿主统一收口（原生能力、坐标换算、配置注入）。见下 |
| **B. 同源 `fetch('/api/...')`** | 插件直连后端（高级） | 插件 iframe 与宿主同源，可直接调用任意 `/api/*` 接口，稳定性自担 |

### `callAction` 协议

插件侧（iframe）唯一通道是 `postMessage`，向后端发送动作请求：

```js
var id = ++seq;
window.parent.postMessage(
  { type: 'callAction', id: id, actionId: 'state.get', payload: {} }, '*'
);
```

宿主 → 插件（插件侧 `window.addEventListener('message', ...)` 接收）：

| 消息 | 含义 |
| --- | --- |
| `{ type: 'callActionResult', id, ok, data \| error }` | 上一次 `callAction` 的结果，按 `id` 对应 |
| `{ type: 'configApply', config }` | 用户在设置面板改了配置 → 实时下发全量 config |
| `{ type: 'event', event, data }` | 宿主广播：`host.unmount`、`host.nativeCover`（`{covered}`）、`layout.empty`（`{empty}`）、`session.switched`、`branch.switched`、`config.updated` |

### actionId 清单

（完整 payload → data 契约见 [../plugins/ui-plugin.md](../plugins/ui-plugin.md)；实现以宿主 `ui/web-minimal/assets/host.js` 的 `dispatch` 为准）

| 分类 | actionId |
| --- | --- |
| 会话／对话 | `chat.send`、`chat.sendBatch`、`chat.interrupt`、`chat.traceToSkill`、`sessions.list`、`sessions.new`、`session.switch`、`session.rename`、`session.delete`、`session.branch`、`requests.list`、`requests.resolve` |
| 配置 | `config.get`（payload `{plugin_id}`）、`config.set`、`settings.meta`、`settings.open`、`settings.close` |
| 文件／数据 | `dialog.files`、`dialog.folder`、`dialog.resolveFiles`、`dialog.pickWallpaper`、`ref.graphs` |
| 容器（float／modal 插件） | `slot.move`、`slot.close`、`slot.hide` |
| 插件自身 | `plugin.delete`、`plugin.rpc`（`{plugin_id, handler, payload}`） |
| 内置浏览器（仅 Electron 主窗口） | `browser.available`、`browser.newTab`、`browser.closeTab`、`browser.navigate`、`browser.reload`、`browser.goBack`、`browser.goForward`、`browser.bounds`、`browser.hide`、`browser.locate`、`browser.pickStart`、`browser.pickEnd`、`browser.pickElement`、`browser.openExternal`、`browser.openUrl` |
| 其它 | `state.get`、`session.setDraftParadigm`、`branch.select` |

### 约束

- 插件只能引用**插件目录内**的文件；宿主的静态路由做了路径穿越校验。
- 插件 id 冲突按 `用户 > 沙盒 > 内置` 生效；想改造内置插件请另起 id。
- 宿主 CSS 变量**不跨 iframe 继承**，插件用 `var(--wm-*, fallback)` 自带兜底。
- 新增插件或改动 `plugin.json` 后，用户按 `Ctrl+R` 刷新即可生效（无需重启应用）。
- 插件后端（`server/server.js`）的生命周期跟随面板标签：开标签 start、关标签 stop；改后端代码后关掉再打开标签即可，或用上面的 `restart` 接口主动重启。
