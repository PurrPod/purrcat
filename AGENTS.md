# PurrCat 开发入口

本地优先的 Agent 基座：Python 内核负责 Agent Loop、工具、子代理、DAG、记忆；Electron 只做桌面壳；能力以 Skill / MCP / Sensor / Graph / AgentLoop / UI Plugin 六类插件扩展，并支持自进化。

UI 是极简模式：静态宿主 + iframe 插件，全部在 `ui/web-minimal/`。

本文只放「动手时必须知道」的内容。技术栈、目录地图、运行拓扑、启动流程看 [开发指南](docs/develop/README.md)，接口看 [API 参考](docs/api/README.md)，扩展点看 [插件开发](docs/plugins/README.md)。

## 常用命令

```powershell
npm run dev          # predev 自动构建宿主 → 选端口 → 后端 → Electron
npm run dev:split    # 跳过宿主预构建（要求产物已最新）
npm run build:ui     # 改 src/host/*.ts 后执行
npm run watch:ui     # 增量重建
npm run typecheck    # tsc --noEmit，strict
uv run python main.py --api --headless --api-port 8000   # 只起后端
uv run pyinstaller main.spec   # 后端打包
npm run dist                   # 桌面安装包
npm run installer:dev          # 独立安装器
```

提交前按需执行：

```powershell
ruff check src/ scripts/ tests/
ruff format --check src/ scripts/ tests/
python scripts/check_api_docs.py
node --check electron/main.js
npm run typecheck && npm run build:ui
uv run pytest -m "l0 or l1"     # 单元 + 集成
uv run pytest -m l3             # 静态红线
```

`assets/host.js` 与 `host.js.map` 是构建产物，必须与源码同一次提交；CI 会重建并比对。

## 测试分层与 TDD

- L0 `tests/l0/`：纯逻辑单元，秒级，不碰网络、模型与 Electron。
- L1 `tests/l1/`：跨模块集成，用 `tests/support/fakes.py` 的替身与 `tmp_path`，不读写真实 `~/.purrcat`。
- L2 桌面 E2E：手动或夜间运行，不进 PR 门禁。
- L3 `tests/l3/`：静态红线与契约检查（Electron 安全、TS strict、API 文档同步）。

改动流程：

1. 新增功能或跨模块改动：先在 `tests/specs/` 写 spec（模板 `_TEMPLATE.md`），再写预期失败的测试。
2. 修复 bug：可省略 spec，但必须先写一条能复现问题的失败测试。
3. 确认测试为红后再实现；完成后跑 `uv run pytest -m "l0 or l1"`，涉及红线再跑 L3。
4. 禁止为了变绿删除用例、放宽断言或新增 skip；确需调整测试须在提交说明中写明原因。
5. 存量功能不强制补测；改到哪补哪，优先把下方“红线与已知坑”变成断言。

## 功能删除清单

功能下线时在同一次改动内完成，不拆到后续 PR：

| 对象 | 动作 |
| --- | --- |
| 功能代码 / 路由 / 配置项 / 插件入口 | 删除 |
| 对应 L0/L1/L3 用例 | 删除 |
| 仅被该用例使用的 fixture、helper、fake 方法 | 删除 |
| spec（`tests/specs/`） | 删除；有决策价值时标记 `Obsolete` |
| `docs/api`、README、CHANGELOG | 同步 |

判断：删功能后测试仍绿，说明它没测到行为边界，需审查后删除或改写。
禁止用永久 `skip`/`xfail` 掩盖失效用例；确需挂起必须带 `reason=` 且包含任务编号。

## 红线与已知坑

1. 桌面壳必须 Electron；IPC 必须 `contextBridge` + `contextIsolation`，禁止 `nodeIntegration`。
2. Windows 对话框不能混选文件+文件夹；`dialog:open` 按 `directory` 分支。
3. 改后端必须彻底重启并清理残留 `uv.exe`，否则内存代码与磁盘不一致；崩溃先看 `backend.log`。
4. `assistant.tool_calls` 必须配齐 `tool` 响应；强制打断用 `_tool_interrupt_event`，`_stop_event` 是永久停机信号。
5. 工具输出按 token 截断（FileSystem 读上限 9900）；进程隔离白名单不可扩大。
6. 宿主的可改文件只有 `src/host/*.ts`；`assets/host.js` 与 `host.js.map` 任何情况下都不手改。
7. 插件配置保存必须按 `plugin.id` 回写，避免保存到最后一个插件。
8. 内置浏览器盖在 DOM 上：设置/模态/菜单出现必须广播 `host.nativeCover`；禁止加载应用自身 URL（`/api/*` 除外）。
9. 关闭/刷新 iframe 前发 `host.unmount`，避免原生标签泄漏。
10. 面板与聊天列宽度计算必须夹紧并做 NaN 守卫；聊天列最小 360px。
11. 改 API 同步文档；提交信息英文、单行。
12. 合并 MCP 前先停服务、删目录、再拷贝（Windows `WinError 183`）；Sensor 报告必须列未覆盖项且晚于代码改动。
13. 用户数据不得提交。
14. 宿主 TS 保持 strict：禁止 `@ts-ignore` / `@ts-nocheck` / `@ts-expect-error`；纯类型整理不得夹带运行时改动。
15. 注释保持简洁：只解释非显而易见的意图或约束，不复述代码、不写改动历史。
16. 所有改动完成后检查文档是否同步（`docs/`、README、本文），避免代码与文档脱节。

## 常见改动落点

| 改动 | 位置 |
| --- | --- |
| Agent 行为/阶段注入 | `~/.purrcat/paradigms/*.yaml` + `src/agent/hook_handler.py` |
| 新增工具 | `src/tool/<name>/` → `src/tool/__init__.py` → `route.py` 的 `TOOL_FUNC_MAP` |
| 会话/聊天接口 | `src/server/api/chat.py` |
| DAG 节点 | `src/harness/node/extensions/<type>/` |
| 聊天渲染 / 输入框 | `plugins/builtin/builtin-history/index.html` |
| 会话列表 | `plugins/builtin/builtin-sessions/index.html` |
| 设置中心 | `src/host/config-center.ts`、`settings-tabs.ts` |
| 面板容器 | `src/host/panel.ts` + `plugins/builtin/builtin-panel` |
| 内置浏览器 | `plugins/builtin/builtin-browser/index.html` + `electron/main.js`（`browser:*` IPC） |
| 新增 UI 插件 | `~/.purrcat/webmin-plugins/<id>/` 或 `plugins/builtin/<id>/` |
| 记忆 / 传感器 / 自进化 | `src/memory/` / `src/sensor/` + `src/server/acp/` / `src/evolve/<type>/` |

## 文档索引

| 主题 | 文档 |
| --- | --- |
| 开发指南总览（技术栈、目录地图、拓扑、启动） | `docs/develop/README.md` |
| 后端开发 | `docs/develop/backend.md` |
| 前端开发 | `docs/develop/frontend.md` |
| 桌面壳与安装器 | `docs/develop/installer.md` |
| HTTP 接口 | `docs/api/README.md` |
| 插件总览 | `docs/plugins/README.md` |
| UI 插件（区域 / 动作 / 事件 / 后端子进程） | `docs/plugins/ui-plugin.md` |
| AgentLoop 与 Hook 阶段 | `docs/plugins/agentloop.md` |
| DAG 与节点扩展 | `docs/plugins/graph.md` |
| Sensor | `docs/plugins/sensor.md` |
| 项目说明 / 变更记录 | `README.zh-CN.md`、`CHANGELOG.md` |
