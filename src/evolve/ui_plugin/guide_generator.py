"""
UI 插件指南生成器模块 (evolve/ui_plugin/guide_generator.py)
单文件指南：覆盖 plugin.json 字段规范、区域取值、宿主 postMessage 协议、后端与刷新方式。
"""


def generate_ui_plugin_guide(
    plugin_id: str, plugin_name: str, area: str, plugin_dir: str, goal: str = ""
) -> str:
    goal_section = f"\n> 🎯 **本次开发目标**：{goal}\n" if goal else ""
    return (
        """# UI 插件（极简模式）开发指南

> 插件 id：`__ID__` ｜ 显示名：__NAME__ ｜ 当前区域：`__AREA__`（生成时的默认值，可改）
> 文件框架已生成在：`__DIR__`
__GOAL__
## 1. 插件是什么

极简模式（web-minimal）把界面拆成一组**热插拔插件**：每个插件就是一个自包含的静态网页，
宿主把它装进 iframe，`src = /api/webmin/plugin/<id>/<entry>`（与宿主同源，所以页面里可以直接 fetch `/api/...`）。

宿主会扫描三个根目录：

| 根目录 | 用途 | 优先级 |
| --- | --- | --- |
| `ui/web-minimal/plugins/builtin/`（项目内） | 随应用分发的内置插件，只读 | 最低 |
| `agent_vm/ui-plugin/` | **你的开发区（本次框架就在这里）** | 中 |
| `~/.purrcat/webmin-plugins/` | 用户自己装的插件 | 最高 |

* 只有**同名 id** 同时出现在多个根目录时才算冲突：优先级高的那份生效，另一份在设置里看不到。
  所以**改造内置插件时建议另起一个 id**（如 `my-history`），否则你这份会盖住内置那份。
* 改动已有文件，下次扫描即生效；**新增插件或改了 plugin.json 后，让用户按 `Ctrl+R` 刷新页面**即可看到（无需重启应用）。
* 宿主不提供任何共享 SDK / 第三方库：HTML / CSS / JS 全部自带，可引用插件目录内的相对路径文件。
  （内置 evolve 插件里的 `window.EV` 是它自己的内部库，不是宿主能力，别依赖它。）

## 2. plugin.json 字段表

| 字段 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `id` | ✅ | string | 全局唯一键，同时是静态资源 URL 的一段；只用小写字母、数字、`-`、`_` |
| `name` | 建议 | string | 设置面板与图标栏里显示的名称 |
| `icon` | ❌ | string | 宿主内置图标名：`list` / `pencil` / `history` / `image` / `globe` / `panel-left` / `panel-top` / `layout-panel-left` / `plus` / `settings`；也可直接写一段自己的 `<svg ...>...</svg>`；写其它字符则按文本渲染。不填取名称首字母 |
| `slot` | ✅ | object \\| string | 见下。**必须显式声明**，不写会把 id 当区域名，插件不会出现在界面上 |
| `entry` | ❌ | string | 入口 HTML，默认 `index.html` |
| `configSchema` | ❌ | array | 用户可配置项，见 §3 |
| `server/server.js` | ❌ | 文件 | 存在即视为"带后端的插件"，见 §6 |

`slot` 两种写法等价：`"slot": "panel"` 或 `"slot": { "area": "panel" }`。
自由浮窗（pet）与模态弹窗（popup）可额外声明尺寸：

```json
{ "slot": { "area": "pet", "size": { "w": 300, "h": 360 }, "center": true } }
{ "slot": { "area": "popup", "size": { "w": "min(1040px, 96vw)", "h": "86vh" } } }
```

`size.w/h` 写数字按 px、写字符串按 CSS 长度；`center` 只对 pet 有意义（popup 天然居中）。

## 3. configSchema（用户可配置项）

数组，每项一个字段：

| 键 | 说明 |
| --- | --- |
| `key` | 配置键名（会出现在 config 对象里） |
| `label` | 设置面板里的显示名，缺省用 key |
| `type` | `text`（默认）／`switch`／`number`／`select`／`range`／`wallpapers`／`plugin-multi`（插件多选，值为插件 id 数组，由插件自行消费） |
| `default` | 默认值；不写则 switch=false、number=0、select=第一个 option、其余为空串 |
| `options` | 仅 `select`：字符串数组 |
| `min` / `max` / `step` | 仅 `range`：`min` 默认 0、`max` 默认 1、`step` 默认 0.01；滑块初值取 `default`，未写则取 `max`；key 叫 `opacity` 时会渲染成"透明度"滑块（值越大越透明） |

读取方式见 §5（`config.get` 或监听 `configApply`）。

## 4. 区域（slot.area）取值

| area | 宿主行为 | 什么时候用 |
| --- | --- | --- |
| `panel` | 入驻宿主的系统级面板容器，用户从容器右上角的抽屉切换显示 | 新增独立功能页（生成时的默认值） |
| `pet` | 自由浮窗，可拖拽可缩放，多插件各自独立 | 常驻小工具、悬浮状态 |
| `popup` | 模态弹窗，遮罩铺满主区，尺寸随窗口自适应 | 一次性向导、确认流程 |
| `rail` | 最左图标栏（白条）里的一个入口 | 需要一键唤起的入口 |
| `sidebar` / `session` / `background` | **单例槽**：同区域只有一个插件生效 | 替换当前的会话列表栏／会话正文／背景 |
| `panel-container` | 宿主系统级容器本体，由宿主自己渲染 | 普通插件不要用 |

区域由你决定：改 `plugin.json` 的 `slot.area` 即可（改完让用户 `Ctrl+R`）。
占用单例槽就会顶掉内置插件——这是允许的，用户能在设置面板里把内置那份改回来，只是别忘了在交付说明里讲清楚。

## 5. 与宿主通信

插件跑在 iframe 里，唯一通道是 `postMessage`（框架文件的 `callAction` 封装可以直接抄）。

插件 → 宿主：

```js
var id = ++seq;
window.parent.postMessage({ type: 'callAction', id: id, actionId: 'state.get', payload: {} }, '*');
```

宿主 → 插件（`window.addEventListener('message', ...)` 收）：

| 消息 | 含义 |
| --- | --- |
| `{ type: 'callActionResult', id, ok, data \\| error }` | 上一次 callAction 的结果，按 id 对应 |
| `{ type: 'configApply', config }` | 用户在设置面板改了配置 → 实时下发全量 config |
| `{ type: 'event', event, data }` | 宿主广播事件，见下表 |

宿主广播的事件（**按 slot 路由**：只发给声明了对应槽的插件，"范围"列即接收方）：

| `event` | data | 范围 | 含义 |
| --- | --- | --- | --- |
| `host.unmount` | — | 全体 | iframe 即将卸载，做收尾 |
| `host.nativeCover` | `{covered}` | 全体 | 原生视图（内置浏览器等）需让位 |
| `session.switched` | `{session_id}` | 全体 | 用户切换了会话 |
| `branch.switched` | `{branch_id}` | 全体 | 用户切换了会话分支 |
| `requests.updated` | `{request_id}` | 全体 | 待审批请求发生变化 |
| `projects.updated` | `{project_id}` | `sidebar` | 项目增删改或会话归属变化 |
| `browser.tabEvent` | `{...}` | 全体 | 内置浏览器 Tab 事件 |
| `layout.empty` | `{empty}` | `session` | 当前区域是否为空（未挂载任何插件） |
| `config.updated` | `{plugin_id, config}` | `settings` | 配置已变更（普通插件用 `configApply` 消息即可） |
| `browser.openUrl` | `{url}` | 命中槽 | 请求在浏览器打开某链接 |
| `conversation.local` | `{session_id, events}` | `session` / `sidebar` | 本会话消息流变化（本地即时插入） |
| `conversation.updated` | `{session_id}` | `session` / `sidebar` | 会话消息流变化；**只有 `session_id`，没有消息内容或"完成"标记** |

> ⚠ **`panel` 槽的插件收不到 `conversation.local` / `conversation.updated`**（它们只发给 `session` / `sidebar` 槽）。
> 所以"Agent 处理完了没有"拿不到现成事件，必须按 §5.4 自行判定。

### 5.1 调用与返回信封

宿主对每次 `callAction` **固定**回：`{ type: "callActionResult", id, ok, data | error }`。

* `ok: true` → 结果在 `data`（各 action 见下表）。
* `ok: false` → 失败原因在 `error`（字符串）；**一律用 `error` 文案降级提示，别让界面卡住**。
* 未列出的 actionId 不会报错，但 `data` 为 `null`。

### 5.2 action 契约（payload → data）

> 下表覆盖插件常用动作，可直接照用。完整 / 权威实现见宿主应用目录下的
> `ui/web-minimal/assets/host.js` 的 `dispatch()`——该文件**不在你的 Bash 沙盒内**，
> 需要时用文件读取工具打开。

**会话 / 对话**

| actionId | payload | data（返回值） |
| --- | --- | --- |
| `state.get` | 无 | 宿主群状态副本 `{activeSessionId, sessions, draft, draftParadigm, activeBranchId, ...}`（其中 `plugins` 为 `undefined`） |
| `chat.send` | `{session_id?, message}` | 后端 `/api/chat` 的 JSON body（含 `processed_message`） |
| `chat.sendBatch` | `{session_id?, events: [...]}` | 后端 `/api/chat/batch` 的 JSON body（含 `processed_events`） |
| `chat.interrupt` | `{session_id?}` | 后端 `/api/chat/interrupt` 的 JSON body |
| `chat.traceToSkill` | `{session_id?, name, goal, is_upgrade?}` | `{status:"ok"}`（`name` / `goal` 为空会抛错） |
| `sessions.list` | 无 | 会话数组（含 `project_id`，空串表示未分类） |
| `sessions.new` | `{project_id?}` | `{status:"ok", draft:true}`；Agent 忙碌时 `{status:"busy"}`（不新建）；`project_id` 非空时在该项目内新建并注入该项目 `MEMORY.md` 的路径与维护约定 |
| `session.switch` | `{session_id}` | `{status:"ok"}`；忙碌且切到别的会话时 `{status:"busy"}` |
| `session.rename` | `{session_id, alias}` | `{status:"ok", alias}` |
| `session.delete` | `{session_id}` | `{status:"ok"}` |
| `session.branch` | `{session_id?, alias?}` | 后端返回的会话对象（含 `id`）；忙碌时 `{status:"busy"}` |
| `session.moveToProject` | `{session_id, project_id}` | `{status:"ok", project_id}`；`project_id` 为空表示移回未分类 |
| `projects.list` | 无 | 项目数组（含 `session_count`、`memory_path`） |
| `projects.create` | `{name}` | 后端创建的项目对象 |
| `projects.update` | `{project_id, name?}` | 后端返回的项目对象 |
| `projects.delete` | `{project_id, delete_sessions?}` | `{status:"ok", deleted_sessions}` |
| `session.setDraftParadigm` | `{paradigm}` | `{status:"ok", paradigm}`；非草稿态 `{status:"noop"}` |
| `branch.select` | `{branch_id?}`（默认 `main`） | `{status:"ok"}` |
| `requests.list` | 无 | 待审批请求数组 |
| `requests.resolve` | `{request_id, approved, feedback?, ignore?, duration?}` | 后端请求 JSON |

**配置 / 设置**

| actionId | payload | data（返回值） |
| --- | --- | --- |
| `config.get` | `{plugin_id}` | 该插件配置对象（无则 `{}`） |
| `config.set` | `{plugin_id, config}` | 合并后的配置对象 |
| `settings.meta` | 无 | `{plugins, config}` |
| `settings.open` / `settings.close` | 无 | `{status:"ok"}` |

**文件 / 数据**

| actionId | payload | data（返回值） |
| --- | --- | --- |
| `dialog.files` | 无 | **绝对路径字符串数组**；取消 → `[]`（Electron 外调用抛错） |
| `dialog.folder` | 无 | 同上（文件夹的绝对路径数组） |
| `dialog.resolveFiles` | `{files: [File]}`（`<input type=file>` 选好的 File） | `{paths: [...]}` |
| `dialog.pickWallpaper` | 无 | 上传后的后端 JSON；取消 → `null` |
| `ref.graphs` | 无 | 名称字符串数组 |

**容器（float 插件用；宿主只操作调用方自己的实例）**

| actionId | payload | data（返回值） |
| --- | --- | --- |
| `slot.move` | `{dx?, dy?}` | `{status:"ok"}` |
| `slot.close` | 无 | `{status:"ok"}`（隐藏调用方浮窗） |
| `slot.hide` | 无 | `{status:"ok"}`（「关闭并记住」，白条可再启用） |

**插件自身**

| actionId | payload | data（返回值） |
| --- | --- | --- |
| `plugin.delete` | `{plugin_id}` | `{status:"ok"}` |
| `plugin.rpc` | `{plugin_id, handler, payload?, timeout?}` | **handler 的 `result` 本身**（不是 `{result}` 包装） |

**内置浏览器（原生视图，仅 Electron 主窗口可用）**

| actionId | payload | data（返回值） |
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

### 5.3 文件与上传通道

宿主、插件前端、插件后端**都在同一台机器**上（后端是本机 Node 子进程，无沙箱），文件不需要"上传"，直接走路径：

* 拿路径：`dialog.files` / `dialog.folder` 返回的是**绝对路径数组**。
* 读内容：把路径放进 `plugin.rpc` 的 payload，**后端直接用 `fs` 读**（`fs.readFileSync` 或流式）；别让前端读成 base64 再塞进 RPC。
* 要**交给 Agent（大模型）读**：走宿主 HTTP 接口 `POST /agent/upload`（落盘到 `agent_vm/.buffer/upload`，Agent 在沙盒内可见），前端 `fetch` 即可。
* `plugin.rpc` 是 stdio 单行 JSON，**没有明确体积上限，但也绝不适合传文件内容**——一律传路径。

### 5.4 发消息后如何判定"完成"

`chat.send` / `chat.sendBatch` 只表示**消息已受理**，宿主不会回"Agent 处理完了"（见上面事件表：`conversation.updated` 只发给 `session` / `sidebar` 槽，且只带 `session_id`）。
"等 Agent 干完活"得自己判定，推荐：

1. 记下发出时间 `t0`；
2. 轮询**明确会变化的产物**：插件自己目录下文件的 `mtime`（Agent 写完即更新），或 `state.get` 里你关心的字段；
3. 产物 `mtime > t0` 即视为完成；再配一个兜底超时（如 5 分钟）与"仍在处理"的 UI 反馈。

> 别把"消息已发出"当成"任务已完成"。

## 6. 可选后端（server/server.js）

在插件目录里放 `server/server.js`（Node），依赖声明在 `server/package.json`（建议附 `package-lock.json`）。
宿主首次启动时会执行 `npm ci`（有锁文件）或 `npm install`，固定 `--omit=dev --ignore-scripts`，把依赖装进插件目录，
与主程序完全隔离；若插件自带 `node_modules` 则直接复用，不会联网重装。
宿主会把它当作独立子进程拉起；进程退出后，下次 RPC 会自动重新拉起：

* **启动握手（必须）**：进程就绪后先往 stdout 打一行 `{"event": "ready"}`。
  宿主据此判定"后端已就绪"；**15 秒内没收到就杀掉进程并报"插件后端未就绪"**，前端 `plugin.rpc` 随之失败。
* 宿主 → 你（stdin，一行一条）：`{"id": "<nonce>", "handler": "<name>", "payload": {...}}`
* 你 → 宿主（stdout，一行一条，必须回）：`{"id": "<nonce>", "ok": true, "result": ...}` 或 `{"id": "<nonce>", "ok": false, "error": "..."}`
* 主动上报（宿主当前仅观测；`ready` 除外，它决定就绪状态）：`{"event": "<name>", "data": ...}`
* 前端调用：`callAction('plugin.rpc', {plugin_id: '__ID__', handler: 'xxx', payload: {}})`，拿到的就是 `result`
* stdout 只许输出协议行；调试信息写插件目录内的日志文件，否则会污染协议。
* **调试入口**：后端 `stderr` 会被宿主捕获，并在启动失败/超时的报错里回显；前端 iframe 的 `console` / DOM 在**宿主 Electron 窗口的开发者工具**（`Ctrl+Shift+I`）里看。

最小骨架（照此改即可，**别漏掉最后那行 ready**）：

```js
'use strict';
const readline = require('readline');
const handlers = {
  ping: (payload) => ({ pong: (payload && payload.msg) || null }),
};
function send(obj) { process.stdout.write(JSON.stringify(obj) + '\\n'); }
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

## 7. 设计与样式约定

### 7.1 用宿主 token，但必须自带 fallback

宿主 CSS 变量**不跨 iframe 继承**，所以每个插件都要像框架文件那样写 fallback：

```css
:root { --ink: var(--wm-label, #16191d); --dim: var(--wm-label-dim, #8b96a3); }
```

常用 token（全量见 `ui/web-minimal/assets/theme.css`）：`--wm-font`、`--wm-mono`、`--wm-radius`、`--wm-radius-sm`、
`--wm-bg-base`、`--wm-bg-panel`、`--wm-bg-sidebar`、`--wm-bg-input`、`--wm-bg-hover`、`--wm-label`、
`--wm-label-2nd`、`--wm-label-dim`、`--wm-border`、`--wm-accent`、`--wm-shadow`、`--wm-bl-0`…`--wm-bl-900`。

### 7.2 默认风格：瑞士国际主义

用户**没有给出明确的前端样式需求**时，默认用**瑞士国际主义**；
用户明确给了风格（如"可爱风""毛玻璃"）时按用户的来，本条让位。

### 7.3 排版别过密，侧栏别太多

插件是塞进宿主**某个容器里的一小块**，不是整屏应用：

* 别默认铺一排侧栏 / 多级分栏；需要分栏最多一层，宽度不够时优先**上下堆叠**，而不是继续挤。
* 组件之间留呼吸空间（用宿主间距 token 或统一栅格）；卡片别塞满，文字别贴边。
* 放不下时优先**减内容 / 分组 / 折叠 / 滚动**，不要靠缩小字号、压缩间距硬塞。

### 7.4 职责边界：不要自己造会话列表

会话列表 / 会话历史 / 会话记录已由宿主的会话类插件负责（`sidebar` / `session` 槽）。除非用户**明确要求**，
**不要在插件里再实现一套会话列表或历史记录**；需要会话数据时调用宿主 action（`sessions.list`、`state.get`、
`requests.list` 等）取即可。这样既避免与现有会话插件重复，也避免误占单例槽。

### 7.5 不要用浏览器原生弹窗

宿主跑在 Electron 里，`window.prompt` **不被支持**：调用会立刻返回 `null` 且不弹任何框。
所以 `if (!prompt(...)) return;` 这类写法会让按钮表现得"点了没反应"。
`window.alert` / `window.confirm` 在嵌入容器里同样不建议用（同步阻塞、样式不受控、跨平台表现不一致）。
需要输入或二次确认时，一律用**插件自己实现的浮层**（DOM 覆盖层 + 自己的输入框 / 按钮）。

### 7.6 按工作流分层，按钮不要堆在一页

先把这个插件里**用户的操作流程拆成几个步骤 / 层级**，
再按层级决定**每个按钮出现在哪一页**：

* 顶层（首页）只放"选择与进入"类入口按钮；**不要把后面每一步的操作按钮都摊在首页**。
* 具体操作按钮跟着它所属的对象 / 步骤出现。
* 用**递进的页面 / 视图**承载（列表页 → 详情页 → 操作页），而不是把所有按钮塞进同一页。
* 自检：任意一屏上，用户"当前能做的下一步"应该只有少数几个，其余靠进入下一层才出现。

### 7.7 功能多就拆多个文件

功能较多时，把界面拆成**多个文件**（多个 `.html` / `.js` / `.css`），按视图或模块分文件组织，
**不要把所有界面都塞进一个 HTML**：

* 每个视图 / 页面一个独立文件，由入口 `index.html` 负责切换 / 挂载。
* 公共样式、工具函数抽到单独文件，多个页面共用。
* 这样单文件更短、更好读也更好改，避免一次性生成一个巨长的 HTML。

## 8. 铁律

1. 插件自身资源用相对路径引用同目录文件：宿主的静态资源路由做了路径穿越校验，`../` 一律 404。
   需要 marked / KaTeX / highlight.js 时，用宿主共享运行时 `/minimal/shared/<name>/<version>/...`
   （版本清单见 `/minimal/shared/manifest.json`），并在 `plugin.json` 的 `requires` 里声明。
2. 区域随你挑，但要知道代价：占用单例槽（sidebar / session / background）
   会把内置插件顶掉——可以，但要在交付说明里告诉用户，以及怎么在设置面板里改回去。
3. id 撞车时按 用户 > 沙盒(你) > 内置 生效；想改造内置插件请另起 id。
4. 写完自检：`plugin.json` 必须能被 JSON 解析；逻辑多的把 JS 抽成独立 `.js` 文件并用
   `node --check <file>` 过一遍语法。
5. **最后告诉用户：按 `Ctrl+R` 刷新页面即可看到你的插件**（新增插件或改了 `plugin.json` 必须刷新；
   只改已有文件的内容也同样刷新即可，不必重启应用）。
""".replace("__ID__", plugin_id)
        .replace("__NAME__", plugin_name)
        .replace("__AREA__", area)
        .replace("__DIR__", plugin_dir)
        .replace("__GOAL__", goal_section)
    )
