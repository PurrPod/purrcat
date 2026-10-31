# UI Plugin 开发指南（极简模式界面插件）

> 落地目录：`~/.purrcat/webmin-plugins/<id>/` ｜ 市场仓库：`PurrPod/ui-plugins` ｜ 宿主：`ui/web-minimal`（`/minimal`）｜ 相关接口：[../api/webmin.md](../api/webmin.md)

UI Plugin 是极简模式（`web-minimal`）的界面插件。宿主是**纯静态页面**，插件以 **iframe** 挂载、按 `slot.area` 入驻不同区域，通过 **postMessage 的 `callAction` 动作总线**与宿主通信。

---

## 1. 插件目录结构

```text
ui-plugins/<id>/               # 市场仓库中的单元
├── plugin.json                # 清单（必需）
├── index.html                 # entry 入口页面（必需）
└── ...                        # 样式/脚本/图片等相对引用资源（可选）
```

**文件夹名 = `plugin.json` 的 `id` = 插件标识**，三者必须一致。

---

## 2. `plugin.json` 字段清单

```json
{
  "id": "doodle-chat",
  "name": "涂鸦聊天",
  "description": "English one-liner.",
  "description-en": "English one-liner.",
  "icon": "🖍️",
  "slot": { "area": "panel" },
  "entry": "index.html",
  "image": "cover.png",
  "root": "user",
  "builtin": false,
  "dependency": [],
  "configSchema": [
    { "key": "color", "type": "select", "label": "主题色",
      "options": [{ "value": "warm", "label": "暖" }, { "value": "cool", "label": "冷" }],
      "default": "warm" }
  ],
  "backend": { "kind": "npm" }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 插件标识，与文件夹名一致 |
| `name` | 是 | 展示名 |
| `description` / `description-en` | 是 | 中/英文一句话描述 |
| `icon` | 是 | 图标（emoji 或图片路径）|
| `slot` | 是 | 入驻区域，见第 3 节。旧写法 `slotDef: { "type": "panel", "area": "panel" }` 亦可，`slot` 直接写区域对象即为新版 |
| `entry` | 是 | 入口 html（默认 `index.html`）|
| `image` | 否 | 市场封面图 |
| `root` | 否 | 来源标记：`user` / `sandbox` / `builtin`（同 id 冲突时优先级 **用户 > 沙盒 > 内置**）|
| `builtin` | 否 | 是否随宿主内置（内置插件不受用户删除影响）|
| `dependency` | 否 | 依赖数组，见 [README.md](README.md#依赖机制dependency) |
| `configSchema` | 否 | 声明式配置表单，见第 4 节 |
| `backend` | 否 | 后端形态；`{ "kind": "npm" }` 表示插件自带 `server/server.js`（Node 后端）|

---

## 3. `slot.area` 区域清单（专有词汇表 · 区域）

`area` 是插件声明的唯一入驻维度；**行为（单例 / 容器抽屉 / 浮窗）由宿主按区域内置**。

| `area` | 名称 | 宿主内置行为 | 窗口类型 |
| --- | --- | --- | --- |
| `rail` | 左侧白条 | 白条图标栏本身（含两态：仅图标 / 图标+文字）| 固定 |
| `sidebar` | 会话列表 | 同区域**单例**（同时只能有一个）| 固定 |
| `session` | 会话 | 同区域**单例** | 固定 |
| `background` | 背景 | 同区域**单例**（如网状斑点背景）| 固定 |
| `panel-container` | 面板容器 | 全局唯一容器，右上角抽屉切换视图；可用 `callAction` 的 `slot.move` 等控制 | 面板 |
| `panel` | 面板 | 与聊天区并排的栏目（内容插件）| 面板 |
| `pet` | 浮窗类 | **多实例**，可拖拽 / 缩放 / 隐藏 | 浮窗 |
| `popup` | 模态弹窗 | 居中模态弹窗 | 模态 |

> 宿主在 `UI_GROUPS` 中声明各区域行为；`slot` 只声明“入驻哪个区域”，**不要试图在插件里自行声明窗口类型**。

---

## 4. `configSchema` 配置表单

宿主据此渲染配置面板并调用 `configApply` 下发。`type` 取值：`text`（默认，单行文本）、`switch`（开关）、`number`（数字）、`select`（下拉，需 `options[]`）、`range`（滑块，配 `min` / `max` / `step`）、`wallpapers`（壁纸选择）。每个字段含 `key` / `type` / `label` / `default`。

插件侧读取方式：监听宿主下发的 `configApply`（见下节事件），或主动 `callAction('config.get', { plugin_id })`。

---

## 5. `callAction` 动作总线协议（核心）

### 5.1 插件 → 宿主

```js
window.parent.postMessage({ type: 'callAction', id: 'req-1', actionId: 'config.get', payload: { plugin_id: 'doodle-chat' } }, '*');
```

- `type` 固定 `'callAction'`；`id` 为本次调用唯一标识（用于匹配响应）。

### 5.2 宿主 → 插件

| 消息 | 结构 | 说明 |
| --- | --- | --- |
| 调用结果 | `{ type: 'callActionResult', id, ok, data \| error }` | 对 `callAction` 的应答，按 `id` 匹配；`ok` 为布尔，成功取 `data`，失败取 `error` |
| 配置下发 | `{ type: 'configApply', config }` | 宿主合并后的插件配置，配置变更时推送 |
| 事件广播 | `{ type: 'event', event, data }` | 宿主主动广播，见 5.4 |

> 应答信封固定为 `{ type: 'callActionResult', id, ok, data | error }`：
> `ok: true` → 结果在 `data`（各 action 见 5.3）；`ok: false` → 失败原因在 `error`（字符串，务必据此做降级提示）；
> 未列出的 `actionId` 不会报错，但 `data` 为 `null`。

### 5.3 `actionId` 契约（payload → data）

**会话 / 对话**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `state.get` | 无 | 宿主群状态副本 `{activeSessionId, sessions, draft, draftParadigm, activeBranchId, ...}`（其中 `plugins` 为 `undefined`） |
| `chat.send` | `{session_id?, message}` | 后端 `/api/chat` 的 JSON body（含 `processed_message`） |
| `chat.sendBatch` | `{session_id?, events: [...]}` | 后端 `/api/chat/batch` 的 JSON body（含 `processed_events`） |
| `chat.interrupt` | `{session_id?}` | 后端 `/api/chat/interrupt` 的 JSON body |
| `chat.traceToSkill` | `{session_id?, name, goal, is_upgrade?}` | `{status:"ok"}`（`name` / `goal` 为空会抛错） |
| `sessions.list` | 无 | 会话数组 |
| `sessions.new` | 无 | `{status:"ok", draft:true}`；Agent 忙碌时 `{status:"busy"}`（不新建） |
| `session.switch` | `{session_id}` | `{status:"ok"}`；忙碌且切到别的会话时 `{status:"busy"}` |
| `session.rename` | `{session_id, alias}` | `{status:"ok", alias}` |
| `session.delete` | `{session_id}` | `{status:"ok"}` |
| `session.branch` | `{session_id?, alias?}` | 后端返回的会话对象（含 `id`）；忙碌时 `{status:"busy"}` |
| `session.setDraftParadigm` | `{paradigm}` | `{status:"ok", paradigm}`；非草稿态 `{status:"noop"}` |
| `branch.select` | `{branch_id?}`（默认 `main`） | `{status:"ok"}` |
| `requests.list` | 无 | 待审批请求数组 |
| `requests.resolve` | `{request_id, approved, feedback?, ignore?, duration?}` | 后端请求 JSON |

**配置 / 设置**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `config.get` | `{plugin_id}` | 该插件配置对象（无则 `{}`） |
| `config.set` | `{plugin_id, config}` | 合并后的配置对象 |
| `settings.meta` | 无 | `{plugins, config}` |
| `settings.open` / `settings.close` | 无 | `{status:"ok"}` |

**文件 / 数据**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `dialog.files` | 无 | **绝对路径字符串数组**；取消 → `[]`（Electron 外调用抛错） |
| `dialog.folder` | 无 | 同上（文件夹的绝对路径数组） |
| `dialog.resolveFiles` | `{files: [File]}`（`<input type=file>` 选好的 File） | `{paths: [...]}` |
| `dialog.pickWallpaper` | 无 | 上传后的后端 JSON；取消 → `null` |
| `ref.graphs` | 无 | 名称字符串数组 |

**容器（float 插件用；宿主只操作调用方自己的实例）**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `slot.move` | `{dx?, dy?}` | `{status:"ok"}` |
| `slot.close` | 无 | `{status:"ok"}`（隐藏调用方浮窗） |
| `slot.hide` | 无 | `{status:"ok"}`（「关闭并记住」，白条可再启用） |

**插件自身**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `plugin.delete` | `{plugin_id}` | `{status:"ok"}` |
| `plugin.rpc` | `{plugin_id, handler, payload?, timeout?}` | **handler 的 `result` 本身**（不是 `{result}` 包装） |

**内置浏览器（原生视图，仅 Electron 主窗口可用）**

| actionId | payload | data（返回） |
| --- | --- | --- |
| `browser.available` | 无 | `{available: boolean}` |
| `browser.newTab` | `{url}` | `{tabId}` |
| `browser.closeTab` | `{tabId, nextTabId?}` | `{status:"ok"}` |
| `browser.switchTab` | `{tabId}` | `{status:"ok"}` |
| `browser.navigate` | `{tabId, url}` | `{status:"ok"}` |
| `browser.reload` / `browser.goBack` / `browser.goForward` | `{tabId}` | `{status:"ok"}` |
| `browser.bounds` | `{x, y, w, h}`（相对 iframe 的 CSS 像素） | `{status:"ok"}` |
| `browser.hide` | 无 | `{status:"ok"}` |
| `browser.pickStart` | `{tabId}` | `{imageDataUrl, width, height, viewportCssWidth, viewportCssHeight}` |
| `browser.pickEnd` | `{tabId}` | `{status:"ok"}` |
| `browser.locate` | `{tabId, x, y}` | 元素定位结果；不可用 → `null` |
| `browser.pickElement` | `{tabId, x, y}` | 元素语义信息（`outerHTML` / `innerText` / `attributes` / `cssSelector` / `rect`）；不可用 → `null` |
| `browser.openExternal` | `{url}` | `{status:"ok"}`（系统浏览器打开） |
| `browser.openUrl` | `{url}` | 统一链接路由结果（http → 内置浏览器） |

> 上表覆盖插件常用动作，可直接照用。完整 / 权威实现见宿主应用目录下的 `ui/web-minimal/assets/host.js` 的 `dispatch()`；
> 宿主 HTTP 接口清单见 [../api/webmin.md](../api/webmin.md)。
>
> **文件与上传**：宿主 / 前端 / 后端同机运行，`dialog.files` 返回的是绝对路径，后端可直接 `fs` 读取（不必读成 base64 再走 `plugin.rpc`）；要交给 Agent（大模型）读时用 `POST /agent/upload`（落盘 `agent_vm/.buffer/upload`）。

### 5.4 事件（`type: 'event'`）

**事件按 slot 路由**：只发给声明了对应槽的插件（"范围"列为 `全体` 的才是广播给所有插件）。

| `event` | 时机 | `data` | 范围 |
| --- | --- | --- | --- |
| `host.unmount` | 宿主卸载插件 | — | 全体 |
| `host.nativeCover` | 宿主原生界面覆盖插件的显示区域 | `{ covered }` | 全体 |
| `session.switched` | 当前会话切换 | `{ session_id }` | 全体 |
| `branch.switched` | 对话分支切换 | `{ branch_id }` | 全体 |
| `requests.updated` | 待办请求状态变化 | `{ request_id }` | 全体 |
| `browser.tabEvent` | 内置浏览器标签页事件 | 标签页事件对象 | 全体 |
| `layout.empty` | 布局空置（无会话等）| `{ empty }` | `session` |
| `config.updated` | 插件配置被更新 | `{ plugin_id, config }` | `settings` |
| `browser.openUrl` | 请求在浏览器打开某链接 | `{ url }` | 命中槽 |
| `conversation.local` | 本会话消息流本地即时插入 | `{ session_id, events }` | `session` / `sidebar` |
| `conversation.updated` | 本会话消息流发生变化 | `{ session_id }` | `session` / `sidebar` |

> `panel` 槽的插件**收不到** `conversation.*`，而且它只带 `session_id`（无消息内容、无"完成"标记）：
> 插件若要判定 Agent 任务完成，需自行轮询（产物 `mtime` / `state.get`）+ 超时兜底。

---

## 6. 最小可运行示例

**`plugin.json`**

```json
{
  "id": "hello-panel",
  "name": "Hello 面板",
  "description": "A minimal panel plugin.",
  "description-en": "A minimal panel plugin.",
  "icon": "🐾",
  "slot": { "area": "panel" },
  "entry": "index.html",
  "configSchema": [
    { "key": "greeting", "type": "text", "label": "问候语", "default": "喵~" }
  ]
}
```

**`index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Hello</title>
<style>body{font-family:system-ui;margin:16px;background:transparent}</style></head>
<body>
  <h3 id="hi">喵~</h3>
  <button id="send">发到会话</button>
<script>
  let reqSeq = 0;
  const pending = new Map();
  function call(actionId, payload) {
    const id = 'r' + (++reqSeq);
    return new Promise(res => { pending.set(id, res);
      window.parent.postMessage({ type: 'callAction', id, actionId, payload }, '*'); });
  }
  window.addEventListener('message', e => {
    const m = e.data || {};
    if (m.type === 'callActionResult' && pending.has(m.id)) { pending.get(m.id)(m.ok ? m.data : m.error); pending.delete(m.id); }
    if (m.type === 'configApply') { document.getElementById('hi').textContent = m.config.greeting || '喵~'; }
  });
  document.getElementById('send').onclick = () => call('chat.send', { message: '你好，来自面板插件' });
</script>
</body>
</html>
```

---

## 7. 开发与调试

- **本地预览**：插件目录放到 `~/.purrcat/webmin-plugins/<id>/`，重启极简宿主（`/minimal` 页面 `Ctrl+R`）即可加载。
- **调试**：插件在 iframe 内运行，用浏览器开发者工具选中对应 iframe 上下文看 Console；`callAction` 出错会落宿主控制台。
- **资源引用**：`index.html` 内使用相对路径引用同目录资源。
- **自带后端**：声明 `backend: { "kind": "npm" }` 并提供 `server/server.js`（Node；依赖放插件自己的 `package.json` / `node_modules`），插件侧用 `plugin.rpc` 调用。
  宿主把它当独立子进程拉起；**进程退出后，下次 RPC 会自动重新拉起**。
  - **生命周期**：面板标签打开（iframe 挂载）时宿主自动 `start`，标签关闭时自动 `stop`。改完 `server.js` 关掉再打开标签即可加载新代码，无需重启 PurrCat；标签开着时也可调 `POST /api/webmin/plugin-backend/{plugin_id}/restart` 主动重启。
  - 宿主 → 插件（stdin，一行一条）：`{"id","handler","payload"}`。
  - 插件 → 宿主（stdout，一行一条，必须回）：`{"id","ok":true,"result":...}` 或 `{"id","ok":false,"error":"..."}`。
  - **启动后必须向 stdout 打一行 `{"event":"ready"}`**：宿主据此判定"后端已就绪"，15 秒内未收到会杀掉进程并报"后端未就绪"，前端 `plugin.rpc` 随之失败。
  - 主动上报（宿主当前仅观测，`ready` 除外）：`{"event":"<name>","data":...}`。
  - stdout 只许输出协议行，调试信息写插件目录内的日志文件，否则会污染协议。
  - **调试**：后端 `stderr` 会被宿主捕获并在报错里回显；iframe 的 `console` 在宿主 Electron 窗口的开发者工具（`Ctrl+Shift+I`）里看。

最小骨架（照此改即可，**别漏掉最后那行 ready**）：

```js
'use strict';
const readline = require('readline');
const handlers = {
  ping: (payload) => ({ pong: (payload && payload.msg) || null }),
};
function send(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }
readline.createInterface({ input: process.stdin, crlfDelay: Infinity }).on('line', (line) => {
  const text = String(line || '').trim();
  if (!text) return;
  let req;
  try { req = JSON.parse(text); }
  catch (_) { send({ id: null, ok: false, error: '请求不是合法 JSON' }); return; }
  const fn = handlers[req.handler];
  if (!fn) { send({ id: req.id, ok: false, error: '未知 handler: ' + req.handler }); return; }
  try { send({ id: req.id, ok: true, result: fn(req.payload || {}) }); }
  catch (e) { send({ id: req.id, ok: false, error: String((e && e.message) || e) }); }
});
// ★ 必须：就绪握手，缺了它宿主会等 15 秒后判定"后端未就绪"
send({ event: 'ready' });
```

---

## 8. 开发注意

- 宿主 CSS 变量**不跨 iframe 继承**，插件样式必须自带 fallback，如 `color: var(--wm-label, #16191d)`；token 全量见 `ui/web-minimal/assets/theme.css`。
- 宿主跑在 Electron 里，`window.prompt` / `alert` / `confirm` 不可用（`prompt` 直接返回 `null`）；输入与二次确认请用插件自绘浮层。
