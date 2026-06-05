<div align="center">

# PurrCat

**[📖 Official Documentation](https://purrpod.github.io/)**

> An economical, efficient, highly customizable, local-first personal Agent framework that understands you better.

<br>

**🐾 Documentation Navigation** &nbsp;
[Introduction](https://purrpod.github.io/intro) &nbsp; | &nbsp; [Deployment](https://purrpod.github.io/guide/deployment) &nbsp; | &nbsp; [Architecture](https://purrpod.github.io/develop/architecture) &nbsp; | &nbsp; [Extension](https://purrpod.github.io/develop/extension) &nbsp; | &nbsp; [Configuration](https://purrpod.github.io/config/) &nbsp; | &nbsp; [FAQ](https://purrpod.github.io/guide/faq)

</div>

---

<img src="purrcat-logo.png" width="260" height="260" alt="PurrCat" align="right" />

## ✨ Core Highlights & Technical Architecture

### 01 Hybrid Memory & Knowledge Graph System

Solving the traditional Agent pain point of "amnesia," this system is deeply designed based on the neuroscience theory of memory classification:

- **Short-Term Working Memory:** Memory-resident `memo` variables that span across single-session gaps, retaining a condensed summary of the last 10 interactions to perfectly solve context loss during session switching.
- **Core General Memory:** System-level profiles (`MEMORY.md`) solidify user personas and work experience. They are injected into the System Prompt during initialization to establish the Agent's behavioral baseline.
- **Long-Term Structured Memory (PurrMemo):** Powered by an episodic memory engine (SQLite + FTS5) and a semantic memory engine (ChromaDB + NetworkX). It supports dynamic entity relationship building, strengthening/weakening mechanisms, and provides HTML visual graph exports.
- **Underlying Technology:** Utilizes the Reciprocal Rank Fusion (RRF) hybrid retrieval algorithm. Through a global thread pool and multi-way concurrency, it fuses BM25 (keyword matching) and Vector (semantic matching) rankings, massively improving recall accuracy.
- **Asynchronous Digestion & Ebbinghaus Forgetting:** New cognitive data is temporarily stored in `pending` and then silently transformed into triples by an independent background daemon process, ensuring zero blocking of user interactions. A dynamic decay mechanism automatically cleans up long-unreinforced memories.

### 02 Harness DAG Workflow Engine

Acting as an orchestratable chain-of-thought and production-grade state machine, Harness eliminates multi-agent communication bottlenecks and tool noise:

- **Multi-Agent Concurrency:** Abandons the huge Token bloat caused by traditional frameworks where Agents "shout" at each other in natural language. Adopts a "single-persona, multi-brain concurrent execution" strategy, vastly reducing communication overhead and inference costs.
- **Precise Task Constraints:** Binds specific tasks to specific tools and injects stage-specific prompts to prevent the Agent from getting confused in complex scenarios.
- **Polymorphic Node Matrix:** Built-in powerful nodes including image generation (direct LLM Vision connection), conditional routing for precise multi-branching (`if_else` / `switch`), and human-in-the-loop intervention nodes to hand over control.
- **State Machine Safe Rollback:** Allows injecting human commands at specific nodes at any time, instantly clearing downstream states for precise breakpoint reconnections, preventing "dirty data reads."
- **JSON Hot-Plugging:** Importing or deploying complex workflows requires only a single JSON configuration file for dynamic loading and hot updates.

### 03 All-Around Secure Toolchain

Equipping the LLM with "hands and feet" backed by absolute security, providing eight native tools to build core senses:

- **Persistent Sandbox Bash:** Replaces regex command-line interception with independent Docker virtual machines, guaranteeing absolute file security, reducing human-in-the-loop dependencies, and supporting directory mounting for external access.
- **All-in-One FileSystem Suite:** Offers codebase roaming capabilities (`read` / `edit` / `write` / `search` / `glob`). The underlying layer integrates `MarkItDown` for seamless dimensional reduction of PDF/DOCX/XLSX to Markdown.
- **Secure Cross-Boundary Conduction:** Employs physical-level black/white lists for interception. `Import` strictly verifies the 30MB limit and path traversal, while `Export` automatically triggers Git snapshots to prevent disastrous overwrites.
- **Core Extension Matrix:** Features dynamic routing `CallMCP`, hybrid retrieval `Search` (over 90% recall rate), web-to-markdown `Fetch`, asynchronous extraction `Memo`, scheduled `Cron`, and a `Task` dispatcher for background jobs.

### 04 Agent Hub & Session Management

Acting as the interactive gateway between the LLM and the external world, endowing the Agent with a dedicated soul and extreme robustness:

- **Git-Style Session Branching:** Supports `new session`, `branch session`, and `switch session`. Easily trial-and-error and safely switch back to the main trunk at any time.
- **Perfect Exception Repair:** Automatically inspects `tool calls` matching, intercepts incomplete tool messages, and rolls back to a safe state to prevent logical model collapse.
- **Intelligent Context Truncation:** Automatically finds safe truncation points (avoiding middle steps of tool calls) when Token limits are exceeded. Keeps the most recent 20 safe interactions and seamlessly replaces older history with Memo summaries.
- **Vitality & Soul Injection:** Defines persona values via `SOUL.md`. A system clock drives the `Heartbeat + SOLO + TODO` mechanism, allowing the Agent to autonomously patrol, clean garbage, and proactively report during idle times.
- **Exclusive Vision Consultant:** Equips the model with an independent Vision consultant, stripping image information from the main session to dramatically increase the signal-to-noise ratio and reduce hallucinations.

### 05 Proactive Perception & Event Gateway

Transitioning from a passive "Q&A machine" to a proactive "Smart Assistant" using a physically decoupled, MCP-like event-driven architecture:

- **Independent Processes & Zero Dependency Conflicts:** Integrates `uv` + `PEP 723` inline dependencies. All sensors run as independent subprocesses (creating virtual environments in seconds upon launch). A single sensor crash never affects the main process.
- **Standard Stream Communication:** Discards complex network ports in favor of `Stdio` pipe JSON-RPC communication. Redirects `stdout` to `stderr`, allowing only valid JSON to enter the parser for extreme lightness and zero network overhead.
- **Multi-Source Sensor Matrix:** Built-in System Sensor (heartbeat guard/scheduled polling), Feishu Sensor (WebSocket bidirectional Markdown parsing), RSS Sensor (tech blog polling and active push), and Audio Sensor (voice control capture via Whisper + pyttsx3).

### 06 Model Scheduling & High-Concurrency Gateway

An industrial-grade LLM resource scheduling management center built on operating system principles:

- **API Key Load Balancing:** The underlying layer maintains an available key list via a thread lock (`_usage_lock`), automatically allocating the most idle key to prevent single key rate limits.
- **Concurrency Lock & Exponential Backoff:** For multi-agent collaboration and high-frequency concurrency scenarios, the underlying layer implements Semaphore queuing and jittered exponential backoff retries (up to 8 times), ensuring absolute high availability of API calls.

### 07 Extreme KV Cache Hit Rate & Token Economics

Achieving extreme cost reduction and efficiency gains through deep engineering optimizations in long-context and multi-task concurrent scenarios:

- **Ultra-High Cache Hit Rate:** In complex environments with dynamic multi-session switching, long sessions still maintain an average cache hit rate of 97%+ (for example, with DeepSeek-V4-Flash, consuming 100 million hit Tokens costs only 2 RMB), providing an ultra-fast response experience.
- **Lifecycle Strong Binding:** The underlying `APIKeyManager` implements strong binding between tasks/sessions and a single key, completely eliminating hit rate collapse caused by load balancing key switching.
- **Dual-Effect Economic Design:** Relies on Harness DAG to eliminate Token redundancy from traditional Agent-to-Agent conversations; using memory summary mechanisms, task executors are required to refine Summaries and submit them to the background for digestion, avoiding full history reading waste.

### 08 Extreme Decoupling, Code-Free Extension & Engineering Aesthetics

Adhering to the principle of high cohesion and low coupling, all core extension components implement data-driven configuration loading:

- **Code-Free MCP Integration:** Simply paste standard JSON into `mcp_config.json`, and the system will automatically handshake, persist cache, and hot-update the LLM tool tree, enabling minute-level capability generalization.
- **Terminal One-Click Skill Loading:** By executing `purrcat install skill <url>`, community SOP workflows are downloaded in seconds and hot-loaded into the retrieval tree for precise foreground recall.
- **Visual DAG Deployment:** Built-in front-end UI engine supports direct drag-and-drop node orchestration, or one-click JSON graph import for second-level deployment of complex workflows.
- **Configuration-as-Sensor-Installation:** UI interface provides one-click ON/OFF toggle switches. If a missing Sensor is detected during system startup, scripts will be automatically pulled from the cloud and run instantly, giving the Agent the ability to actively change its own senses.

<br clear="right" />

---

## 🙏 Acknowledgments

- Thanks to **[zhenghuanle](https://github.com/zhenghuanle)** for testing the installation flow from scratch.
- Thanks to **[Gaeulczy](https://github.com/Gaeulczy)** for testing the one-click setup and run scripts.

---

## 📄 License

This project is open-sourced under the [MIT](LICENSE) license. You can freely use, modify, distribute, and even use this project for commercial purposes without any burden.

In this era of explosive Agent technology, there are no permanent moats, no so-called personal heroism—only a wave that pushes everyone forward. The birth of PurrCat is my tiny response to this wave. If you can gain a spark of inspiration or convenience from it, that would be the greatest meaning of PurrCat's existence. Have fun!
