# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Native tools: CallMCP, hybrid Search, Fetch, Memo, Cron, Task, ComputerUse, BrainStorm, KernelUpgrade. External MCP servers supported.

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
