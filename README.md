<div align="center">

# PurrCat

An Agent foundation designed around information theory

Let expression no longer be a lossy compression — let the Agent work your way.

**Build an Agent That Works Your Way**

[Documentation](https://purrpod.github.io/) · [中文](README.zh-CN.md)

</div>

***

<img src="purrcat-logo.png" width="220" height="220" alt="PurrCat" align="right" />

## Quickstart

> PurrCat is still iterating quickly. Installing from source is recommended so you can pick up the latest features and fixes as they land.

### One-line install

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/PurrPod/purrcat/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/PurrPod/purrcat/main/install.ps1 | iex
```

The install script checks for and installs the required prerequisites, clones the source to `~/purrcat`, installs the project dependencies, and registers a global `purrcat` command.

After installation:

```bash
purrcat desktop start # Launch the Electron desktop app
purrcat desktop update # Update the source and refresh dependencies
```

> **Installation notes:** Only source installation is currently offered — there are no pre-packaged desktop installers. The Windows flow is well tested; macOS / Linux have more limited test coverage. On Windows, Docker Desktop must be launched manually once after installation to complete setup and accept its agreement.

### API port

The desktop API uses port `8000` by default. When you run `npm run dev`, it automatically tries another available port if that one is occupied.

To pin a fixed port, set the `PURRCAT_API_PORT` environment variable or pass `--api-port` to `main.py`. If an explicitly specified port is unavailable, it returns an error instead of switching silently.

---

## Features

### 00 · Information-Driven Agent Design

> **The model decides capability; information decides direction.**

Model capability keeps improving, but the information gap between you and the Agent — and between Agents — does not close on its own. What you want still has to be fully expressed, understood, and accurately carried through execution.

PurrCat cares not only about what the model can do, but also about how task information enters the system, how it flows during execution, and which information is worth keeping for the long term. Through more flexible interaction channels, orchestrated information flow, and hybrid memory, we want the Agent to stay closer to your true intent.

- **UI plugin architecture for easier communication**: Fold your working context into UI plugins to build a channel that is uniquely yours — no need to spell everything out in text each time; a single click can communicate and fill in information efficiently.
- **Orchestrated information flow**: Organize the Agent's execution the way you work, as a configurable DAG workflow, and orchestrate the Agent Loop with a simple yaml file — you decide when the necessary information gets injected.
- **Multi-layer hybrid memory**: Inject short-term working memory, `MEMORY.md`, and PurrMemo's episodic memory, semantic memory, and knowledge graph in stages, helping the Agent retrieve the relevant information when it needs it.
- **Sub-agents that share context**: SubAgents use their own branch id, model instance, and event loop while sharing the same contextual foundation, so a sub-agent fully understands the main Agent's needs without building all collaboration on natural-language conversation between Agents — efficient and context-managed at the same time.

### 01 · Everything Is Plugins

> **Beyond the kernel — capabilities, flows, and interfaces are all extensible.**

- **Extensibility from tools to execution paradigms**: Tools, skills, sensors, Agent Loops, workflows, and UI panels can all be plugged in or customized through the extension mechanism. A single yaml file configures information injection, tool-use checks, and loop-exit conditions during execution, so the Agent's behavior can be adjusted on demand.
- **Extensible UI**: A lightweight host carries UI plugins across different regions, supporting runtime mounting and hot-swapping, so your working context quickly builds your efficient channel. For example, the built-in browser supports picking DOM elements, drawing selection boxes, and commenting in place, so interface edits can focus on specific elements instead of repeatedly describing positions in words.
- **Open plugin ecosystem**: Compatible with MCP servers and Agent Skills-format skills, installable through the built-in market. Supports extension types such as `skill`, `ui-plugin`, `mcp`, `agentloop`, `sensor`, and `graph`, along with their dependency resolution.

### 02 · RSI Self-Evolution System

> **Not only using capabilities, but building, evaluating, and iterating them.**

PurrCat combines capability generation with evaluation, so the Agent's own extensions can not only run but also be validated.

- **The Agent builds plugins on its own**: The evolution factory provides Trace2Skill, MCP tool building, and sensor building, and supports creating UI plugins through `create_ui_plugin`.
- **Evaluation after generation**: Skills can generate a companion `SKILL.md` and `evals.json` evaluation set, and pass the built-in evaluator's checks on triggering and execution quality. Sensors and MCP tools have their own validation mechanisms too. Rather than modifying itself unconditionally, this establishes a capability-improvement process that can be inspected, evaluated, and iterated.
- **Hot reload and iteration archive**: Plugins support hot reload; the evolution factory presents evaluation results as standalone HTML reports and keeps an iteration record. For upgrades that support rollback, you can restore the previous version.

### 03 · Secure Self-Hosting

> **The Agent has its own workspace; your host machine is still yours to control.**

PurrCat isolates the Agent's execution environment from the host, letting it keep working while clearly limiting the boundary of host-file access.

- **Isolated execution sandbox**: The Agent runs commands and manipulates files in a dedicated Docker container, persistently keeping its workspace and logs.
- **Controlled host-file interaction**: File imports are validated for size and path; file exports can trigger a Git snapshot for auditing and traceability; directory allow/deny lists limit the access scope.
- **Heartbeat + Goal**: `GOAL.md` provides long-term goals. When idle, the Agent can autonomously perform patrols, information gathering, and reporting on a heartbeat cycle, and the heartbeat interval supports hot reload.

### 04 · More Efficient Context and Tool Management

> **Reduce unnecessary tool information; keep a stable long-session cache.**

- **Stable KV Cache**: The API key manager binds tasks and sessions to a single key, reducing the impact of key switching on the long-session prefix cache. By project measurement, the cache hit rate holds above 99% in long sessions.
- **Retrieve tools and skills on demand**: Native tools use compact schemas; tools and skills adopt a store-then-retrieve strategy, turning an attention problem into a retrieval problem — MCP tools and skills are selected on demand via vector retrieval, so every request no longer carries all extension definitions, and hot-reloading tools does not break the cache while installing many tools does not burn extra tokens.
- **Reduce collaboration overhead**: Independent workflows pass node results as structured data, and with memory summaries and task hand-off, they cut unnecessary natural-language restatement and repeated context.

---

## Design Goals

PurrCat aims to be a customizable, extensible, and sustainably evolving Agent foundation.

From how information enters the Agent, to how tasks execute, how memory is organized, and how capabilities expand, developers can orchestrate all of it in the way they work — without being constrained by a fixed Agent Loop or a single interaction mode.

**Let the Agent be not just stronger, but more aligned with how you work.**

<br clear="right" />

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

If you run into installation or configuration problems, open an issue and describe what happened. We will look into it and provide a solution.

## Acknowledgments

- [zhenghuanle](https://github.com/zhenghuanle): tested the installation flow from scratch.
- [Gaeulczy](https://github.com/Gaeulczy): tested the one-click install and run scripts.
- [JohnWJ-co](https://github.com/JohnWJ-co): tested the macOS build and helped troubleshoot issues.
- Sponsored by the Smart Agent Development Competition hosted by the Sun Yat-sen University OpenHarmony Technology Club.

## License

PurrCat is open-sourced under the [MIT License](LICENSE), free to use, modify, and distribute, including for commercial purposes.
