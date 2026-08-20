<div align="center">

# PurrCat

English | [简体中文](README.zh-CN.md)

An economical, efficient, customizable, local-first personal AI Agent framework.

[Documentation](https://purrpod.github.io/) | [Deployment](https://purrpod.github.io/guide/deployment)

</div>

---

<img src="purrcat-logo.png" width="220" height="220" alt="PurrCat" align="right" />

## Quickstart

### Requirements

- Python 3.10+, [uv](https://docs.astral.sh/uv/), Node.js 18+, Git
- [Docker](https://docs.docker.com/get-docker/) (required by the sandboxed Bash tool)
- Alternatively, run `purrcat setup` to initialize the environment (uv, Docker, embedding model, Playwright) in one step

### Option 1: Electron desktop (recommended)

```bash
git clone https://github.com/PurrPod/purrcat.git
cd purrcat
uv sync                    # Python dependencies
npm install                # Root dependencies (Electron, etc.)
npm install --prefix ui    # Frontend dependencies
npm run dev                # Starts backend + frontend + Electron
```

### Option 2: Web UI (lightweight)

```bash
uv sync
npm install --prefix ui
npm run build:ui                             # Build frontend assets
uv run python main.py --api --headless       # Open http://localhost:8000 in a browser
```

> Note: several features (local file access, terminal, etc.) depend on the Electron runtime and may misbehave in a plain browser. The desktop client is recommended for full functionality.

## Architecture

### 01 Hybrid Memory and Knowledge Graph

- Short-term working memory: in-memory `memo` variables retain condensed summaries of the last 10 interactions across session switches.
- Core memory: `MEMORY.md` stores user profiles and work experience, injected into the system prompt at initialization.
- Long-term structured memory (PurrMemo): episodic engine (SQLite + FTS5) and semantic engine (ChromaDB + NetworkX), with dynamic relation strengthening/weakening and HTML graph export.
- Hybrid retrieval: RRF fusion of BM25 and vector search, executed concurrently through a global thread pool.
- Asynchronous digestion: new cognitions are buffered in `pending` and converted to triples by a background daemon; a decay mechanism cleans up long-unused memories.

### 02 Harness DAG Workflow Engine

- Multi-agent concurrency under a single persona, avoiding natural-language inter-agent chatter and its token cost.
- Per-task tool binding and stage-specific prompt injection.
- Polymorphic node matrix: LLM-vision image generation, conditional routing (if/else, switch), human intervention, and more.
- Safe rollback: inject commands at any node; downstream states are cleared for precise breakpoint recovery.
- Workflows load from a single JSON file and hot-update at runtime.

### 03 Secure Toolchain

- Sandboxed Bash: commands run in isolated Docker containers, with optional directory mounts for external access.
- FileSystem suite: `read` / `edit` / `write` / `search` / `glob`, with PDF/DOCX/XLSX converted to Markdown via MarkItDown.
- Boundary control: physical black/white lists; imports are checked against a 30MB limit and path traversal, exports trigger Git snapshots.
- Extension tools: CallMCP, hybrid Search, Fetch, Memo, Cron, Task, ComputerUse, BrainStorm, KernelUpgrade; external MCP servers supported.

### 04 Agent Hub and Session Management

- Git-style session branching: new, branch, and switch sessions; trial-and-error without losing the main trunk.
- Automatic repair: malformed tool calls are intercepted and rolled back to a safe state.
- Context truncation: when token limits are exceeded, older history is replaced by memo summaries at safe cut points.
- Persona and vitality: `SOUL.md` defines values; a heartbeat-driven mechanism lets the agent patrol, clean up, and report during idle time.
- A dedicated vision consultant isolates image processing from the main session to improve signal-to-noise ratio.

### 05 Proactive Perception and Event Gateway

- Sensors run as independent subprocesses with PEP 723 inline dependencies managed by uv; a single sensor crash does not affect the main process.
- Stdio JSON-RPC communication over pipes; no network ports involved.
- Built-in sensors: System (heartbeat/polling), Feishu (WebSocket), RSS, and Audio (Whisper + pyttsx3).

### 06 Model Scheduling and Concurrency

- API key load balancing: idle-first key allocation under a thread lock, preventing single-key rate limits.
- Semaphore queuing and jittered exponential backoff (up to 8 retries) for high-concurrency availability.

### 07 KV Cache and Token Economics

- Stable KV cache hit rates across session switches, via strong key-to-session binding in the API key manager.
- DAG execution removes inter-agent token redundancy; task executors produce summaries for background digestion instead of full-history reads.

### 08 Configuration-Driven Extension

- Zero-code MCP integration: paste standard JSON into `mcp_config.json`; the tool tree hot-updates after handshake.
- `purrcat install skill <url>` downloads community skills and loads them into the retrieval tree.
- Visual DAG editing in the UI, with one-click JSON import/export.
- Sensors toggle on/off in the UI; missing sensor scripts are fetched automatically at startup.

<br clear="right" />

---

## Acknowledgments

- [zhenghuanle](https://github.com/zhenghuanle) tested the installation flow from scratch.
- [Gaeulczy](https://github.com/Gaeulczy) tested the one-click setup and run scripts.
- Sponsored by the Smart Agent Development Competition hosted by the Sun Yat-sen University OpenHarmony Technology Club.

## License

Released under the [MIT](LICENSE) license. You are free to use, modify, and distribute this project, including for commercial purposes.
