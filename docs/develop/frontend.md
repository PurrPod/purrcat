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
