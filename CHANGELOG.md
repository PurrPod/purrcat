# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1]

A follow-up to 1.1.0 with project workspaces, sidebar and chat-header improvements, a graphical installer, a local rendered-fetch path, and a deep internal refactor: the backend packages are split into focused modules, and the HTTP API reference is now generated from the FastAPI schema instead of being maintained by hand.

**English**

### Added

- **Projects**: a project store with REST API and session ownership, sidebar project groups with a quick bar, search and draft naming, and agent access to project memory files.
- **Chat header and rail**: recent-session switcher, new-session/branch toggles, scrollable dropdowns, the session title above its history, rail icons grouped by slot area with settings pinned at the bottom, and switching fixed slot plugins from the rail menu.
- **Pending-request todo list** in the sessions sidebar.
- **Composer file input**: paste or drop files as quotes.
- **Settings**: forms rendered from sensor field definitions, and `settings.open` can target a specific tab.
- **Vision history**: attachment paths are kept in session history and restored to base64 when a message is resent.
- **BrainStorm plans** are persisted per session and can be referenced with `@PLAN`.
- **Plugin backend lifecycle** can be managed from panel tabs.
- **Graphical installer** for desktop installs.
- **Local fetch**: SPA pages are rendered in a hidden Electron window and the rendered DOM is preferred, with plain HTTP as fallback.
- **Developer workflow**: typed host modules built by esbuild, development guides and CONTRIBUTING, a layered L0/L1/L3 pytest suite wired into CI, and an API reference generated from the FastAPI schema (`docs/api/openapi.json|md`) with a CI drift check.

### Changed

- TUI removed; the app runs headless only, and leftover TUI/app-config code was dropped.
- OCR replaced by RapidOCR; vision models are used without an OCR fallback; embeddings run on ONNX Runtime; fetch uses `curl_cffi` with Playwright limited to development.
- UI polish: unified palette and panel chrome, flatter session rows, proportional file preview, wrapped code blocks and tables, and a composer that stays fixed while the reference panel is open.
- Memory compression now shares one prompt and fallback between main and sub agents, and the injected header is 【历史记忆总结】.
- Internal: `utils`, `model`, `sensor`, `memory`, `tool`, `agent`, `harness`, `evolve` and `server` were split into focused modules with shared JSON/JSONL read and atomic-write helpers, an injectable ChatModel seam, and tool-registry contract tests.

### Fixed

- Branch sessions are named after their source session.
- Native browser views are cleared when the host page reloads.
- Cron writes `cron.json` atomically and tracks fire timestamps.
- Hook path mapping for references resolved into the sandbox.
- Copying raw markdown and distinguishing missing-file preview errors.
- Opening the reference panel no longer pushes the composer.
- Context-token tooltip stays inside the panel; long code blocks and tables wrap instead of overflowing.
- Built-in browser keeps chrome-devtools navigation inside the browser.
- The sandbox is no longer queried on exit when the host never created it.
- Circular import between utils, harness and model; platform-specific tests now pass on Linux CI.

---

**中文**

### 新增

- **项目**：新增项目存储与 REST API、会话归属，侧边栏支持项目分组、快捷栏、搜索与草稿命名，Agent 可读写项目记忆文件。
- **聊天头部与侧栏**：最近会话切换器、新建会话/分支开关、可内部滚动的下拉菜单、历史记录上方的会话标题；侧栏图标按 slot 区域分组并把设置固定在底部，可通过区域菜单切换固定位置的插件。
- **待审批 todo 列表**：展示在会话侧边栏。
- **输入框文件**：支持粘贴或拖拽文件为引用。
- **设置**：按 sensor 字段定义渲染配置表单，`settings.open` 可定位到指定标签页。
- **视觉附件历史**：附件路径写入会话历史，重发时还原为 base64。
- **BrainStorm 计划**按会话持久化，并支持 `@PLAN` 引用。
- **插件后端生命周期**可在面板标签页内管理。
- **图形化安装器**。
- **本地抓取**：在隐藏的 Electron 窗口中渲染 SPA 页面并优先使用渲染后的 DOM，HTTP 作为回退。
- **开发流程**：宿主拆分为 esbuild 构建的强类型模块，补充开发指南与 CONTRIBUTING，接入 L0/L1/L3 分层 pytest 与 CI 门禁，API 参考改由 FastAPI schema 生成（`docs/api/openapi.json|md`）并在 CI 校验漂移。

### 变更

- 移除 TUI，仅以 headless 模式运行，并清理遗留的 TUI 与应用配置代码。
- OCR 改用 RapidOCR；视觉模型不再回退 OCR；向量改由 ONNX Runtime 推理；抓取改用 `curl_cffi`，Playwright 仅开发期使用。
- UI 细节：统一配色与面板外框、更扁平的会话行、按比例的预览弹窗、代码块与表格自动换行，参考面板展开时输入框保持固定。
- 记忆压缩的主/子 Agent 共用同一提示词与兜底文案，注入标题改为【历史记忆总结】。
- 内部：`utils`、`model`、`sensor`、`memory`、`tool`、`agent`、`harness`、`evolve`、`server` 拆分为职责单一的模块，合并 JSON/JSONL 读取与原子写入实现，新增可注入的 ChatModel 接缝与工具注册表契约测试。

### 修复

- 分支会话按来源会话命名。
- 宿主页面刷新时清理原生浏览器视图。
- cron 原子写入 `cron.json` 并记录触发时间。
- 引用解析到沙盒路径时的 hook 路径映射。
- 复制原始 Markdown，并区分文件缺失的预览错误。
- 打开参考面板不再挤压输入框。
- 上下文 token 提示框保持在面板内；长代码块与表格换行不再溢出。
- 内置浏览器将 chrome-devtools 跳转限制在浏览器内。
- 宿主从未创建沙盒时，退出不再查询 Docker。
- 修复 utils、harness、model 之间的循环导入；平台相关测试在 Linux CI 上通过。

## [1.1.0]

First stable release. Since 1.0.0-beta.4 this version reworks the front-end delivery model, the workflow engine and the tool set, and adds evolution factories for agent loops and graphs, sensor operations, and sandbox disk maintenance.

**English**

### Added

- **UI plugin system (`ui-plugin`)**: a new plugin type that lets developers fully customize the style and behavior of front-end panel views. Ships with a hot-swappable subprocess plugin runtime, a dedicated plugin market with automatic dependency install, plugin root/dependency/origin metadata, and the `create_ui_plugin` KernelUpgrade capability with an authoring guide.
- **Minimal UI with built-in plugins**: the app now runs on minimal UI mode and bundles the essential built-in plugins — session/history, sessions & pending approvals, task, memory graph, built-in browser, market, evolve factory, and background. User can build a efficient channel that is uniquely themselves.
- **Developer documentation**: a modular server API reference (`docs/api/*`) and plugin development guides (`docs/plugins`: graph / agentloop / sensor / ui-plugin), with CI validating that the docs stay in sync with the server routes.
- **AgentLoop and Graph evolution factories**: create, edit, and validate agent loops and workflows from the Evolve panel — sandbox category selector, editable graph canvas, in-panel save, host-side validation, and deletion of sandboxes that are no longer needed. The factories are also reachable from the KernelUpgrade and Request tools.
- **Sensor operations**: runtime status with stop/restart controls, a purge action that removes the deployed script, per-sensor icons, and a config refresh button in minimal UI.
- **Sandbox disk maintenance**: the Deploy panel now reports the Docker data disk (WSL2 vhdx) real size, estimated live data, and dead-space ratio read-only at startup; compaction runs only after the user clicks the button (one UAC prompt). A weekly `docker builder prune` plus tmpfs cache mounts keep the disk from growing back, and the sandbox container can be rebuilt from the panel.
- **Global persona editor**: edit and save `SOUL.md` from Settings.
- **Skill install from a local folder path**.
- **Search box** in the plus-panel picker for skills, MCP servers, and graphs.

### Changed

- **Front-end rewritten to minimal UI mode**: the entire original hand-drawn React front-end has been removed. The former UI is published to the official plugin repository as a hand-drawn-style UI plugin, so users who prefer it can install it back. Minimal UI adds a multi-tab panel container with slot/area layout, drag-to-resize width, per-plugin opacity/width, a built-in browser that takes over clicked web links, and panel plugins replicating the former pages (task, memory, market, evolve, sessions).
- **Workflow engine (harness) rewritten**: nodes now exchange self-describing JSON envelopes (`type`/`data`/`mime`/`meta`) with `purrcat://` URIs for file payloads and engine-side type validation; graphs are stored as folders (`graph.json` + `asset/`) with automatic migration on startup. The agent loop node is now driven by the agentloop paradigm plugin and shares the main agent's memory system (memo cache sync). Nodes added: `command`, `file_reader`, `file_writer`, `string`, and a multi-format preview node. Glue nodes removed: `image_generator`, `text_file_reader`, `html_viewer`, `json_builder`, `if_else_router`, `switch_router`, `python_runner`.
- **Evolution factory evaluation overhauled**: sensor protocol self-check (L0/L1), eval assertions and verdict scoring in the MCP factory, refreshed skill/sensor evaluators, and factory reports rendered as self-contained Swiss-style HTML with an iteration archive list.
- **Tool set simplified**: removed the ComputerUse tool and its exclusive dependencies, and removed the install request types from the Request tool.
- **Marketplace**: added the ui-plugin market, agentloop market endpoints and tab, installing skills from a GitHub link, deleting installed plugins, and a reinstall action.
- **Infrastructure**: cross-layer API port coordination between the app layers; host-native settings; per-session token usage (including subagents) persisted and surfaced in the minimal UI ring.
- **AgentLoop message handoff**: injected turns are marked as resume so the loop no longer re-reads upstream input; the graph system prompt is delivered as a trailing user message; check actions warn when `failed_prompt` is missing; an agent loop without input runs with an empty paradigm instead of failing.
- **Graph validation**: every validator check is reported, and branch merges require a summary.
- **Sensor merge**: the protocol check is advisory, and credentials must be filled before merging.
- **Request tool**: test/merge request types removed; KernelUpgrade is split into per-action modules and test results include the sandbox artifact directory.
- **Defaults**: the default model is DeepSeek Flash with vision enabled; the minimal UI chat input grows automatically up to 240px.

### Fixed

- Token ring showing 0 on load — per-session usage is now read from persisted session metadata and restored on init/session switch.
- Config editor failing in minimal mode; sidebar highlight error.
- Subagent branch cancel/delete now match the internal id, wait for teardown, and key active tasks by unique id; `fix the file change accept error when the file is moved`.
- Sensor SRE mismatch caused by a leaked venv environment; MCP subprocess venv env is now stripped before merge.
- Node reset acting on a stale task due to a selection-closure race.
- Background-agent config read error.
- Plugin origin detection on cross-drive roots; stale plugin JS cache and panels overflowing past the viewport.
- Boot-session race, context-ring visibility and link color in minimal UI.
- Stale eval run directory cleaned before copy; bogus token-savings card skipped.
- Skill upgrade target guarded and empty rollback commit tolerated.
- Backend active session not synced when switching or deleting sessions.
- System messages rendered inside the assistant bubble in the task plugin.
- Agent loop re-absorbing upstream input on injection; final memory dumped out of order.
- Built-in browser: bounds not synced per frame, and `target=_blank` links covering the chat instead of opening a new tab.
- Copy of selection and visible text in the built-in browser, with rebuild deferred while selecting.
- `purrcat://` links now resolve through the task artifact endpoint.
- Paradigm switch failures now surface as a toast and restore input focus.
- `on_input_received` firing on non-user input.
- Fetch now returns an explicit refreshing notice; MCP hot-reload failures are reported.
- Session drawer height capped, with session and pending drawers mutually exclusive.
- Bare GitHub repository URLs accepted for skill and graph install.
- Reference panel not closing on outside click.

---

**中文**

### 新增

- **UI 插件体系（`ui-plugin`）**：新增插件类型，开发者可自由定制前端面板的样式与功能。配套热插拔子进程插件运行时、带依赖自动安装的独立插件市场、插件根目录/依赖/来源元数据，以及 `create_ui_plugin` 的 KernelUpgrade 能力与编写指南。
- **极简 UI 与内置插件**：应用现以极简 UI 模式运行，并内置一批必要插件——会话/历史、会话与待审批、任务、记忆图谱、内置浏览器、市场、进化工厂、背景。用户可根据需要搭建专属于自己的沟通信道。
- **开发者文档**：模块化的服务端 API 参考（`docs/api/*`）与插件开发指南（`docs/plugins`：graph / agentloop / sensor / ui-plugin），并加入 CI 校验文档与服务端路由一致。
- **AgentLoop 与 Graph 进化工厂**：在进化面板中创建、编辑并校验 agent loop 与工作流——新增沙盒分类选择、可编辑的图画布、面板内保存与宿主侧校验，不再需要的沙盒可直接删除。工厂同时接入 KernelUpgrade 与 Request 工具。
- **Sensor 运维能力**：展示运行状态并支持停止/重启，新增清除（purge）操作删除已部署脚本，补充 sensor 图标与配置刷新按钮。
- **沙盒磁盘维护**：部署面板在启动时只读展示 Docker 数据盘（WSL2 vhdx）的实际占盘、有效数据估算与空洞占比，超过阈值才提示，用户点击按钮后才执行压缩（一次 UAC 授权）；每周 `docker builder prune` 与 tmpfs 缓存挂载从源头抑制膨胀，并支持一键重建沙盒容器。
- **全局人格编辑器**：在设置中编辑并保存 `SOUL.md`。
- **技能支持从本地文件夹路径安装**。
- **加号面板的选择器新增搜索框**，支持技能、MCP 与图。

### 变更

- **前端改为极简 UI 模式**：删除了全部原有的手绘风格 React 前端。原前端以手绘风格 UI 插件的形式发布到官方插件仓库，偏好原风格的用户可重新安装。极简 UI 新增多标签页面板容器（slot/area 布局、拖拽调宽、每插件透明度/宽度）、接管网页链接的内置浏览器，以及复刻原页面的面板插件（任务、记忆、市场、进化、会话）。
- **工作流引擎（harness）重写**：节点改为交换自描述的 JSON 信封（`type`/`data`/`mime`/`meta`），文件载荷使用 `purrcat://` URI 并在引擎侧做类型校验；图改为文件夹形式存储（`graph.json` + `asset/`），启动时自动迁移。智能体循环节点改由 agentloop 范式插件驱动，并与主 agent 共享记忆系统（memo 缓存同步）。新增节点：`command`、`file_reader`、`file_writer`、`string` 及多格式预览节点。移除胶水节点：`image_generator`、`text_file_reader`、`html_viewer`、`json_builder`、`if_else_router`、`switch_router`、`python_runner`。
- **进化工厂评测体系优化**：新增 sensor 协议自检（L0/L1），MCP 工厂加入评测断言与判定评分，刷新 skill/sensor 评测器，工厂报告改为自包含的瑞士风格 HTML 并带迭代归档列表。
- **工具简化**：删除 ComputerUse 工具及其专属依赖，删除 Request 工具的 install 请求类型。
- **市场**：新增 ui-plugin 市场、agentloop 市场端点与标签页、从 GitHub 链接安装技能、卸载已装插件与"重装"操作。
- **基础设施**：应用各层之间统一 API 端口协调；宿主原生设置；按会话持久化 token 用量（含子代理）并在极简 UI 圆环展示。
- **AgentLoop 消息交接**：注入回合标记为 resume，循环不再重复读取上游输入；图的系统提示改为以末尾用户消息下发；check 动作缺少 `failed_prompt` 时给出告警；无输入的 agent loop 以空范式运行而不再报错。
- **图校验**：上报每一项校验结果，分支合流必须提供摘要。
- **Sensor 合入**：协议自检改为建议性质，合入前必须填写凭据。
- **Request 工具**：移除 test/merge 请求类型；KernelUpgrade 按动作拆分为独立模块，测试结果会带出沙盒产物目录。
- **默认值**：默认模型切换为 DeepSeek Flash 并开启视觉；极简 UI 聊天输入框自动增高至 240px 上限。

### 修复

- 加载时 token 圆环显示为 0——改为从持久化的会话元数据读取按会话用量，并在初始化/切换会话时恢复。
- 极简模式下配置编辑器失效；侧边栏高亮报错。
- 子代理分支取消/删除改为按内部 id 匹配、等待清理完成、按唯一 id 记录活动任务；修复文件移动后接受改动的报错。
- venv 环境泄露导致的 sensor SRE 不匹配；MCP 子进程合并前会剥离泄露的 venv 环境。
- 节点重置因选择闭包竞态而作用于过期任务。
- 后台 agent 配置读取报错。
- 跨盘符根目录下的插件来源识别；插件 JS 缓存过期与面板溢出视口。
- 极简 UI 启动会话竞态、上下文圆环可见性与链接颜色。
- 复制前清理过期的评测运行目录；跳过错误的 token 节省卡片。
- 技能升级目标加保护，并容忍空的回滚提交。
- 切换或删除会话时后端活动会话未同步。
- 任务插件中系统消息被渲染进助手气泡。
- 注入时 agent 循环重复吸收上游输入；最终记忆落盘顺序错乱。
- 内置浏览器边界未逐帧同步，`target=_blank` 链接覆盖聊天区而非新开标签页。
- 内置浏览器选中文本与可见文本的复制，选择期间延后重建。
- `purrcat://` 链接改由任务产物端点解析。
- 范式切换失败现在以 toast 提示并恢复输入焦点。
- `on_input_received` 对非用户输入也会触发。
- Fetch 返回明确的刷新提示；MCP 热重载失败会提示。
- 限制会话抽屉高度，会话与待审批抽屉互斥。
- 技能与图安装接受裸 GitHub 仓库地址。
- 参考面板点击外部不关闭。

## [1.0.0-beta.4]

Distribution model change: the one-line source installer replaces pre-built desktop installers.

**English**

### Added

- One-line installers (Windows / Linux / macOS) — this is now the only install path. The script clones the source, auto-installs missing prerequisites (git / uv / Node.js 18+ / Docker / embedding model) with multi-level fallbacks (winget → official installers → GitHub releases), and registers a global `purrcat` command.
- One-click start and update: `purrcat desktop start` lazily installs dependencies on first launch and boots the desktop app; `purrcat desktop update` pulls the latest source and syncs dependencies.
- Deploy page in Config Center: visual deployment of the embedding model, Docker, and the sandbox image (multi-source pull with automatic fallback: ghcr.io → NJU mirror → Docker Hub), greatly lowering the deployment barrier.
- Agent Loop Editor: edit the execution paradigm (`PARADIGM.yaml`) from the UI, with per-session paradigm selection and hot switching.
- Live streaming of the model's reasoning content into the thinking bubble.
- Vision inline mode.
- Market: batch "install all" button on repo detail pages.

### Changed

- Sensor module refactored onto the ACP protocol: a new ACP server, stdio bridge, and unified message dispatch replace the legacy sensor vocabulary layer; sensors get a dedicated config page with editor relay and stable-path deploy.
- Full UI localization: Chinese/English switching in Config Center, covering chat, market, Agent Loop Editor, sidebar menus and toasts; market plugin details include a zh/en description toggle. Default language is fixed to English instead of following the system language.
- Tool output limits switched from characters to tokens (10,000) with a shared token utility.
- FileSystem list returns single-level `ls`-style output (type/size/mtime); hidden entries are no longer filtered.
- Skill loading returns the full SOP as the tool result.
- Simplified tool result display: the frontend extracts pure content from the JSON wrapper.
- Prompt wording cleanup: replaced "老板" (boss) with "用户" (user) across tool descriptions.

### Fixed

- Data-root migration error on startup.
- Force-interrupt stuck in the "dozing" state; chat action buttons vanishing after interrupt.
- Vision returning empty analysis when thinking models exhausted the max_tokens budget on reasoning.
- Sandboxed Bash: the shared container no longer sleeps on subprocess exit; one automatic retry on EOF.
- Garbled lint-checker output and `biome` not found on Windows.
- Brainstorm sub-agent snapshots missing sibling tool results in the same batch; sub-agent final reply is now appended to the branch finish notification.
- Browser webview covering the chat area after closing the panel, and stale pages after closing a tab.
- Terminal view error, file-url parse error, and chat draft restore broken by React StrictMode double-run.
- Embedding model no longer auto-downloads at startup (the Deploy page is the single writer); onnx/openvino exports skipped with a corrected size hint.
- Installer hardening: BOM stripped from `install.ps1` for `irm | iex` compatibility, `npm.cmd` used to bypass execution-policy blocking, and Node/uv/git fallbacks improved.

---

**中文**

### 新增

- 一键安装指令（Windows / Linux / macOS），并成为唯一的安装方式：脚本自动克隆源码、补齐缺失的前置依赖（git / uv / Node.js 18+ / Docker / 向量模型，内置多级回退：winget → 官方安装器 → GitHub Releases），并注册全局 `purrcat` 命令。不再提供打包好的安装包。
- 一键启动与一键更新：`purrcat desktop start` 首次启动自动安装依赖并拉起桌面端；`purrcat desktop update` 拉取最新源码并同步依赖。
- 配置中心新增部署页面：向量模型、Docker、沙箱镜像全部可视化部署（镜像多源拉取自动回退：ghcr.io → 南大镜像站 → Docker Hub），进一步降低部署难度。
- 主循环编辑器：在界面中直接编辑执行范式（`PARADIGM.yaml`），支持按会话选择范式并热切换。
- 模型思考内容实时流式展示到思考气泡。
- 视觉内联模式。
- 市场：仓库详情页新增"全部安装"批量按钮。

### 变更

- Sensor 模块基于 ACP 协议重构：新增 ACP 服务端、stdio 桥接与统一消息分发，移除旧版 sensor 词汇层；Sensor 提供独立配置页，支持编辑器中继与稳定路径部署。
- 界面完整本地化：配置中心支持中英文切换，覆盖聊天、市场、主循环编辑器、侧边栏菜单与提示语；市场插件详情支持中英文描述切换。默认语言固定为英文，不再跟随系统语言。
- 工具输出上限从字符数改为 token 数（10000），使用统一的 token 计算工具。
- 文件列表改为单层 `ls` 风格输出（类型/大小/修改时间），不再过滤隐藏条目。
- 技能加载返回完整 SOP 作为工具结果。
- 简化工具结果展示：前端从 JSON 包装中提取纯内容。
- 提示词措辞清理：工具描述中的"老板"统一改为"用户"。

### 修复

- 启动时数据根目录迁移报错。
- 强制中断卡在"打盹"状态；中断后聊天操作按钮消失。
- 思考模型把 max_tokens 预算耗尽在推理上导致视觉分析返回空内容。
- 沙箱 Bash：子进程退出不再休眠共享容器；EOF 时自动重试一次。
- Windows 下检查器输出乱码、找不到 `biome`。
- BrainStorm 子代理快照丢失同批次兄弟工具结果；子代理最终回复现在会追加到分支完成通知中。
- 关闭面板后浏览器 webview 遮挡聊天区域、关闭标签页后显示旧页面。
- 终端视图报错、文件 URL 解析错误、React StrictMode 双执行导致草稿恢复失败。
- 向量模型不再在启动时自动下载（部署页面为唯一入口）；跳过 onnx/openvino 导出并修正体积提示。
- 安装脚本加固：`install.ps1` 去除 BOM 以兼容 `irm | iex`、改用 `npm.cmd` 绕过执行策略限制、完善 Node/uv/git 回退逻辑。

## [1.0.0-beta.3]

Bug-fix and stability release.

### Fixed

- Electron process lifecycle hardening: single-instance lock (second launch focuses the existing window), auxiliary windows destroyed on close, and a quit watchdog to prevent orphaned backend processes.
- Browser panel: tab close now activates the correct neighbor tab, and view focus handling fixed.
- Harness DAG engine: reload error fixed.
- Long-term memory stayed empty in fresh installs: the memory worker now defers (instead of dropping) pending experiences while the embedding model is unavailable.
- Terminal failed to spawn when the agent_vm working directory was missing.
- Bash tool: default timeout reduced to 30s; timeout errors now report the actual limit and include partial output captured so far.
- Skill trigger test scoring miscalculation fixed.

### Changed

- Config center: model form drafts survive tab switches and collapse; default vision template updated to `openai:deepseek-v4-flash-vision-exp`.
- Subprocess PATH is enriched from the Windows registry, so dependencies installed after the backend starts are found without a reboot.
- UI lint cleanup across ChatPage, ConfigModal, AgentBrowserPanel and IDEPanel.

## [1.0.0-beta.2]

Bug-fix and stability release.

### Fixed

- MCP sessions are no longer recycled mid-task: `callmcp` now runs in-process instead of a subprocess, so long-lived MCP servers (e.g. Chrome via chrome-devtools) stay alive across tool calls. Anti-hang protection via a configurable timeout on tool calls.
- Terminal failed to connect in some scenarios.
- Opening a page in the external browser misbehaved.
- MCP config template produced invalid `env` entries.
- UI refresh error after merging MCP market installs.

### Changed

- The agent now has full access to files inside the sandbox.

### Docs

- Requirements slimmed down (Docker core-only), GOAL.md mechanism and PARADIGM added to the architecture overview.

## [1.0.0-beta.1]

First public beta release.

### Added

**Hybrid Memory and Knowledge Graph**

- Three-tier memory architecture: short-term working memory (`memo`), core general memory (`MEMORY.md`), and long-term structured memory (PurrMemo).
- Episodic memory engine (SQLite + FTS5) and semantic memory engine (ChromaDB + NetworkX).
- RRF hybrid retrieval fusing BM25 keyword matching and vector search, executed concurrently.
- Background daemon for asynchronous memory digestion, with a decay mechanism that cleans up long-unused memories.
- Knowledge graph with dynamic relation strengthening/weakening and HTML visualization export.
- Memory page in the UI: events, experiences, graph view, and a MEMORY.md editor.

**Harness DAG Workflow Engine**

- Multi-agent concurrent execution under a single persona, avoiding inter-agent natural-language chatter.
- 20 built-in node types, including conditional routing (if/else, switch), LLM-vision image generation, human intervention, and template rendering.
- Safe rollback: inject commands at any node; downstream states are cleared for breakpoint recovery.
- Workflows load from a single JSON file and hot-update at runtime.

**Secure Toolchain**

- Sandboxed Bash: commands run in isolated Docker containers, with optional directory mounts.
- FileSystem suite (read / edit / write / search / glob) with PDF/DOCX/XLSX converted to Markdown via MarkItDown.
- Physical black/white lists for cross-boundary file operations; exports trigger automatic Git snapshots.
- Native tools: CallMCP, hybrid Search, Fetch, Memo, Cron, Task, BrainStorm, KernelUpgrade. External MCP servers supported.

**Agent Core**

- Git-style session branching: new, branch, and switch sessions.
- Automatic repair: malformed tool calls are intercepted and rolled back to a safe state.
- Context truncation: older history is replaced by memo summaries at safe cut points when token limits are exceeded.
- Persona system: `SOUL.md` defines values; a heartbeat-driven mechanism (Heartbeat + GOAL.md) patrols and reports during idle time.
- Dedicated vision consultant isolates image processing from the main session.
- Customizable agent loop: the execution paradigm (triggers, lifecycle hooks, periodic injections, tool-use checks, loop exit conditions) is defined declaratively in `PARADIGM.yaml` using near-natural-language rules — rewrite the loop's behavior without touching core code.

**Self-Evolution**

- Skill factory: the agent authors and upgrades its own skills in an isolated evolution sandbox, complete with generated scaffolding, guides, and eval cases; skills that pass evaluation are promoted into the live retrieval tree.
- MCP factory: same mechanism for MCP servers — scaffold, build, and evaluate new MCP servers autonomously, then register them into the tool tree.

**Proactive Perception**

- Sensor framework: independent subprocesses with PEP 723 inline dependencies (managed by uv), communicating over Stdio JSON-RPC.
- Built-in sensors: System (heartbeat/polling), Feishu (WebSocket), RSS, and Audio (Whisper + pyttsx3).

**Model Gateway**

- API key load balancing with idle-first key allocation.
- Semaphore queuing and jittered exponential backoff (up to 8 retries).
- Strong key-to-session binding for stable KV cache hit rates across session switches.

**Desktop Client and Distribution**

- Electron desktop client with built-in browser tabs and terminal.
- Web UI mode for lightweight deployment (`python main.py --api --headless`).
- Cross-platform builds: Windows (NSIS), macOS (arm64 dmg), Linux (AppImage).
- In-app auto-update on Windows and Linux via GitHub Releases, with differential downloads.
- Release automation: one-command tagging, changelog extraction, and asset upload via GitHub Actions.

**CLI**

- `purrcat setup`: one-step environment initialization (uv, Docker, embedding model, Playwright).
- `purrcat install`: install extensions (skill, node, graph, mcp).

This list highlights the major capabilities; more features are documented at [purrpod.github.io](https://purrpod.github.io/).

### Known Issues

- The application is unsigned. Windows SmartScreen may warn on first launch (choose "Run anyway"); on macOS, right-click the app and choose Open to bypass Gatekeeper.
- macOS builds do not support silent auto-update (requires an Apple Developer certificate); download the new dmg manually.
- Sandboxed Bash requires Docker; the tool is unavailable without it.
- Local file access, terminal, and related features depend on the Electron runtime and may misbehave in a plain browser.
