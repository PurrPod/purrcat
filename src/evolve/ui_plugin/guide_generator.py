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
| `icon` | ❌ | string | 宿主内置图标名：`list` / `pencil` / `history` / `image` / `globe` / `panel-left` / `layout-panel-left` / `settings`；也可直接写一段自己的 `<svg ...>...</svg>`；写其它字符则按文本渲染。不填取名称首字母 |
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
| `type` | `text`（默认）／`switch`／`number`／`select`／`range`／`wallpapers` |
| `default` | 默认值；不写则 switch=false、number=0、select=第一个 option、其余为空串 |
| `options` | 仅 `select`：字符串数组 |
| `min` / `max` / `step` | 仅 `range`：默认 0~1、步长 0.01；key 叫 `opacity` 时会渲染成"透明度"滑块 |

读取方式见 §5（`config.get` 或监听 `configApply`）。

## 4. 区域（slot.area）取值

| area | 宿主行为 | 什么时候用 |
| --- | --- | --- |
| `panel` | 入驻宿主的系统级面板容器，用户从容器右上角的抽屉切换显示 | 新增独立功能页（生成时的默认值） |
| `pet` | 自由浮窗，可拖拽可缩放，多插件各自独立 | 常驻小工具、悬浮状态 |
| `popup` | 模态弹窗，遮罩铺满主区，尺寸随窗口自适应 | 一次性向导、确认流程 |
| `rail` | 最左图标栏（白条）里的一个入口 | 需要一键唤起的入口 |
| `sidebar` / `input` / `background` / `conversation` | **单例槽**：同区域只有一个插件生效 | 替换当前左侧栏／输入框／背景／会话列表 |
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
| `{ type: 'event', event, data }` | 宿主广播事件：`host.unmount`（iframe 即将卸载，做收尾）、`host.nativeCover`（`{covered}` 原生视图需让位）、`layout.empty`（`{empty}`） |

可用的 actionId（payload 以宿主实现为准，见 `ui/web-minimal/assets/host.js` 的 dispatch）：

* 会话／对话：`state.get`、`chat.send`、`chat.sendBatch`、`chat.interrupt`、`chat.traceToSkill`、`sessions.list`、`sessions.new`、`session.switch`、`session.rename`、`session.delete`、`session.branch`、`requests.list`、`requests.resolve`
* 配置：`config.get`（payload `{plugin_id}`）、`config.set`、`settings.meta`、`settings.open`、`settings.close`
* 文件／数据：`dialog.files`、`dialog.folder`、`dialog.pickWallpaper`、`ref.graphs`
* 容器（float 插件用）：`slot.move`、`slot.close`、`slot.hide`
* 插件自身：`plugin.delete`、`plugin.rpc`（payload `{plugin_id, handler, payload}`，调自己的后端子进程）
* 内置浏览器（原生视图，仅 Electron 主窗口可用）：`browser.available`、`browser.newTab`、`browser.closeTab`、`browser.navigate`、`browser.reload`、`browser.goBack`、`browser.goForward`、`browser.bounds`、`browser.hide`、`browser.locate`、`browser.pickStart`、`browser.pickEnd`、`browser.pickElement`、`browser.openExternal`、`browser.openUrl`
* 其它：`input.dropdown`（输入区下拉时告知宿主让位）

调用可能失败（返回 `ok: false`）：一律用 `error` 文案降级提示，别让界面卡住。

## 6. 可选后端（server/server.js）

在插件目录里放 `server/server.js`（Node；依赖放插件自己的 `package.json` / `node_modules`，与主程序完全隔离），
宿主会把它当作独立子进程拉起，并提供热重启：

* 宿主 → 你（stdin，一行一条）：`{"id": "<nonce>", "handler": "<name>", "payload": {...}}`
* 你 → 宿主（stdout，一行一条，必须回）：`{"id": "<nonce>", "ok": true, "result": ...}` 或 `{"id": "<nonce>", "ok": false, "error": "..."}`
* 主动上报（宿主当前仅观测）：`{"event": "<name>", "data": ...}`
* 前端调用：`callAction('plugin.rpc', {plugin_id: '__ID__', handler: 'xxx', payload: {}})`，拿到的就是 `result`

## 7. 样式：用宿主 token，但必须自带 fallback

宿主 CSS 变量**不跨 iframe 继承**，所以每个插件都要像框架文件那样写 fallback：

```css
:root { --ink: var(--wm-label, #16191d); --dim: var(--wm-label-dim, #8b96a3); }
```

常用 token（全量见 `ui/web-minimal/assets/theme.css`）：`--wm-font`、`--wm-mono`、`--wm-radius`、`--wm-radius-sm`、
`--wm-bg-base`、`--wm-bg-panel`、`--wm-bg-sidebar`、`--wm-bg-input`、`--wm-bg-hover`、`--wm-label`、
`--wm-label-2nd`、`--wm-label-dim`、`--wm-border`、`--wm-accent`、`--wm-shadow`、`--wm-bl-0`…`--wm-bl-900`。

## 8. 铁律

1. 只能引用插件目录内的文件：宿主的静态资源路由做了路径穿越校验，`../` 一律 404。
2. 区域随你挑，但要知道代价：占用单例槽（sidebar / input / background / conversation）
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
