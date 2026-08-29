# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
