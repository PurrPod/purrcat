<div style="display: flex; align-items: center; justify-content: space-between;">
  <div style="text-align: center; flex: 1;">
    <h1>PurrCat</h1>
    <p><blockquote>An economical, efficient, customizable, and user-centric local-first personal Agent framework.</blockquote></p>
  </div>
  <img src="purrcat-logo.svg" width="214" height="288" alt="PurrCat" />
</div>

---

## Quick Start

```bash
git clone https://github.com/PurrPod/purrcat.git
cd purrcat

purrcat setup       # One-click setup (Docker sandbox + Conda environment + embedding model)
purrcat init        # Generate .purrcat/ config files, requires API-Key configuration for first use

# Three launch options, choose one as needed
# 1. Launch with TUI
purrcat start

# 2. Launch without TUI
purrcat start --headless

# 3. Launch API service for WebUI
purrcat start --headless --api
cd ui
npm install # Required for first-time WebUI use, skip for subsequent runs
npm run dev
```

[Full docs](https://purrpod.github.io/)

---

## Key Highlights

**1. Event-driven Active Perception** Breaks the limitations of traditional LLM's single "Q&A" mode. The framework integrates an event gateway with multi-source sensors (e.g., RSS polling, Feishu integration, system timers), enabling the Agent to continuously monitor external environment changes in the background and proactively report summaries or automatically advance tasks when specific conditions are met.

**2. Multi-layer Hybrid Memory Architecture** To address the issue of information forgetting in long-term LLM interactions, the system designs a three-layer structure including short-term working memory, universal persona prompts, and long-term memory graph (PurrMemo). Combined with a time decay mechanism based on the Ebbinghaus curve, edge information that has not been recalled for a long time will be gradually cleaned up to maintain database health and retrieval efficiency.

**3. Context Cache Optimization-focused Scheduling Strategy** In extended context interactions, stable KV Cache hit rate is crucial for reducing operational costs and improving response speed. By decoupling tool schemas from System Prompt and adopting dynamic loading, along with the underlying mechanism of strong binding between API keys and session lifecycle, the system strives to maintain a high cache hit rate in multi-task concurrent scenarios.

**4. Independent Sandbox Execution Environment** The framework allocates an isolated runtime environment based on Docker for the Agent. Compared to intercepting commands via regex on the host, the physically isolated design better protects the local file system security without introducing excessive manual intervention, while also providing a stable resident space for the Agent to handle long-cycle tasks.

**5. Git-style Session Branch Management** The system introduces a session management mechanism similar to Git branches. When exploring complex problem-solving paths, users can pull new branches for trial and error. If the result is unsatisfactory, they can switch back to the main branch at any time. Additionally, the system has a built-in status check tool that automatically rolls back to the last safe state when tool calls are interrupted or return exceptions, reducing logical errors.

**6. Modular Directed Acyclic Graph (DAG) Scheduling** For complex business processes, PurrCat supports decomposing them into DAG-based workflows (Harness). This mechanism allows background nodes to flow asynchronously without blocking the front-end main session. When the process encounters permission restrictions or insufficient information, the system triggers a Human-in-the-loop mechanism to suspend the task, and precisely resumes execution from the breakpoint after receiving manual instructions.

**7. Open Tool and Process Extension System** Aims to lower the threshold for secondary development. The framework supports hot-updating external MCP (Model Context Protocol) tools through configuration files, and can quickly load community-shared Skills via terminal commands. Meanwhile, the built-in visual UI provides node orchestration and connection functions, enabling rapid export of visual flowcharts into executable deployment configurations.

---

## Documentation

- [Introduction](https://purrpod.github.io/intro)
- [Deployment Guide](https://purrpod.github.io/guide/deployment)
- [Architecture](https://purrpod.github.io/develop/architecture)
- [Extension Guide](https://purrpod.github.io/develop/extension)
- [Configuration](https://purrpod.github.io/config/)
- [FAQ](https://purrpod.github.io/guide/faq)

---

## Acknowledgments

- Thanks **Gemini Pro 3.1** for assisting in building the beautiful UI interface.
- Thanks **[zhenghuanle](https://github.com/zhenghuanle)** for testing the installation flow from scratch.
- Thanks **[Gaeulczy](https://github.com/Gaeulczy)** for testing the one-click setup and run scripts.

---

## License

This project's core framework is open-sourced under the **GNU GPL-3.0** license.

- **Core Copyleft**: Distributing modified core framework must be open-sourced.
- **Plugin/Extension Exemption**: Skills, Harness, and external services developed based on this project are **not subject to GPL contagion** and can be closed-source for commercial use.
- **Disclaimer**: Code is provided "as is" without any warranty.