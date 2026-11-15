# 前端开发

极简模式：静态宿主 + iframe 插件，无框架、无路由。Electron 开发与生产都加载 `http://127.0.0.1:<apiPort>/minimal/`，源码在 `ui/web-minimal/`。

插件如何声明区域、调用动作、开子进程，见 [UI Plugin 开发](../plugins/ui-plugin.md)。

## 结构

```text
ui/web-minimal/
├─ index.html              # 宿主页面，只引用 /minimal/assets/host.js
├─ assets/theme.css        # 设计变量与全局样式
├─ assets/host.js          # esbuild 产物（含 host.js.map），禁止手改
├─ src/host/*.ts           # 宿主源码，唯一可改处
└─ plugins/builtin/*/      # 内置插件：plugin.json + index.html（+ 可选 server/）
```

## 宿主模块

全部模块由 `main.ts` 打包成单个 IIFE，`import` 顺序即执行顺序。

| 模块 | 职责 |
| --- | --- |
| `main.ts` | 入口，串起启动流程 |
| `app.ts` | 启动装配 |
| `state.ts` | 全局状态（slot 索引、配置缓存、会话/图标栏状态） |
| `types.ts` | 宿主与插件的契约类型 |
| `globals.d.ts` | `window.purrcat` 等全局声明 |
| `manifest.ts` | 拉取并应用 manifest |
| `areas.ts` / `mount.ts` | 区域判定、iframe 挂载与卸载 |
| `panel.ts` | 面板容器（宽度、标签、透明度） |
| `rail.ts` / `float.ts` | 左侧图标栏 / 自由浮窗 |
| `bus.ts` / `actions.ts` | 动作总线 / 动作实现 |
| `config-center.ts` | 设置中心 |
| `settings-tabs.ts` / `settings-cards.ts` / `settings-appearance.ts` | 设置分栏、卡片、外观 |
| `config-apply.ts` | 配置落库与生效 |
| `sessions.ts` / `dialog.ts` / `links.ts` / `icons.ts` | 会话、对话框、外链、图标 |

## 构建链路

```text
src/host/main.ts  --esbuild-->  assets/host.js + host.js.map
```

- `npm run dev` 前置 `predev`：同步第三方前端库（`sync-vendor.mjs`）后再执行 `build:ui`。
- 长时间改宿主可用 `npm run watch:ui` 增量重建。
- `npm run dev:split` 跳过预构建，要求产物已是最新。
- 产物入库是为了让 `python main.py` 在没有 Node 的环境也能提供 UI；CI 会重建并比对产物，不一致即失败。

## 生成式 UI（GenUI）

聊天页内置一套声明式组件运行时：模型输出纯文本 DSL，前端解析后渲染成界面，样式与交互都由宿主掌握。

| 文件 | 职责 |
| --- | --- |
| `plugins/builtin/builtin-history/genui/core.js` | 词法 / 语法解析、求值器、状态绑定 |
| `genui/functions.js` | 内置函数库与动作步骤 |
| `genui/render.js` | VNode → HTML / DOM、颜色与间距映射、动作执行 |
| `genui/media.js` | 媒体识别、路径转预览地址、内嵌播放器与 `![]()` 展开 |
| `genui/components-*.js` | 组件实现（布局文本 / 输入 / 数据媒体 / 图表地图 / 绘图） |
| `genui/index.js` | `PurrCatGenUI.renderHTML(source, state)` / `mount(el, source, options)` |
| `genui/genui.css` | 组件主题，变量映射自 `--wm-*` |
| `genui/preview.html` | 调试页：左侧输入 DSL，右侧即时渲染 |

DSL 约定：

- 每行一条语句，`name = Expr` 定义，`$name = value` 声明可交互状态；首个 `root = ...` 为渲染入口。
- 组件写成 `Name(args)`，函数写成 `@Name(args)`，支持引用、成员访问、索引、数组 / 对象、三元与二元运算，`//` 起注释。
- 非法语句按行丢弃，不阻塞其余内容；未知组件降级为灰色占位。
- 动作：`ToAssistant` / `OpenUrl` / `Set` / `Reset` / `CopyToClipboard`，可用 `Action([...])` 组合。
- 交互模型：组件只修改状态，160ms 后整体重渲染，并按 `data-bind` 恢复焦点与选区。

聊天页识别两种来源：助手消息里语言标记为 `genui` / `openui` 的围栏代码块；MCP 工具返回的 `mcp_data.structuredContent` 中带 `kind` + `dsl`（或 `source` / `ui`）时直接渲染。
`ToAssistant` 会把文本写回输入框，可附带表单当前值。

### 文件引用与内嵌媒体

除内联代码块，助手也可以用 Markdown 图片语法引用产物文件，宿主自动展开：

| 写法 | 渲染 |
| --- | --- |
| `![](/agent_vm/genui/card.genui)` | 读取文件内容并挂载为 GenUI 卡片（`.openui` 等同） |
| `![](/agent_vm/out/trend.png)` | 内嵌图片（带文件名说明） |
| `![](/agent_vm/out/voice.mp3)` | 音频播放器 |
| `![](/agent_vm/out/demo.mp4)` | 视频播放器 |

- 本地路径经 `genui/media.js` 转成 `/api/filesystem/preview?path=...`，沙盒路径自动转换，Range 请求由后端支持，音视频可拖动进度。
- 远程图片保持原生 `<img>`；远程音视频同样走播放器。
- `.genui` 引用在消息插入后异步读取、展开，历史重建前由 `destroyGenUI()` 统一销毁定时器与实例。
- 展开失败显示「无法加载 GenUI 文件」，不影响同一条消息里的其它内容。

## 模块约定

- `types.ts` 是契约的唯一来源；改字段先改它，再改使用方。
- 相对导入统一写 `./x.js`（esbuild 自动解析到 `x.ts`），不要省略后缀或用 `.ts`。
- 跨模块共享的 `let` 绑定对导入方只读：修改时用 `export function setXxx()`，或对对象/数组原地修改（`obj.k = v`、`arr.length = 0`），禁止整体重新赋值。
- 新增模块必须被 `main.ts` 的依赖链引用才会进入产物；纯类型文件用 `import type`。
- 宿主不得写死任何插件专属逻辑，插件行为一律通过 slot / action / event 契约表达。
- TypeScript 按 strict 维护：禁止 `@ts-ignore` / `@ts-expect-error`，空值优先写显式守卫。

## 常见改动位置

| 改动 | 位置 |
| --- | --- |
| 聊天渲染 / 输入框 | `plugins/builtin/builtin-history/index.html` |
| 生成式 UI 组件 / DSL | `plugins/builtin/builtin-history/genui/`（预览 `preview.html`） |
| 会话列表 | `plugins/builtin/builtin-sessions/index.html` |
| 设置中心 | `src/host/config-center.ts`、`settings-tabs.ts` |
| 面板容器 | `src/host/panel.ts` + `plugins/builtin/builtin-panel` |
| 内置浏览器 | `plugins/builtin/builtin-browser/index.html` + `electron/main.js` 的 `browser:*` IPC |
| 新增 UI 插件 | `~/.purrcat/webmin-plugins/<id>/` 或 `plugins/builtin/<id>/` |

## 调试

- 宿主与插件 iframe 的 `console` 都在 Electron 窗口的开发者工具里看（`Ctrl+Shift+I`）。
- 动作总线可直接在控制台验证：

```js
await window.purrcatWebmin.callAction('settings.meta', {})
```

- 内置浏览器是原生 `WebContentsView`，会盖住 DOM；设置 / 模态 / 菜单出现时宿主会广播 `host.nativeCover`，插件需据此隐藏原生视图。
- 关闭或刷新 iframe 前宿主会发 `host.unmount`，插件应在此释放原生资源。
