<div align="center">

# PurrCat

*A highly customizable local personal agent framework.*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-GPLv3-green)]()

[\[中文文档\]](README.md)

</div>

---

## Quick Start

```bash
git clone https://github.com/PurrPod/purrcat.git
cd purrcat

purrcat setup       # One-click setup (Docker sandbox + Conda + model)
purrcat init        # Generate .purrcat/ config files
purrcat start       # Launch with TUI
purrcat start --headless  # Launch without TUI
```

[Full docs](https://purrpod.github.io/)

---

## Highlights

**1. Dual-layer sandbox isolation.** All code execution runs inside Docker containers, isolated from the host. A strict whitelist system (`.purrcat/.file.yaml`) controls host file access: `dont_read_dirs` (privacy zone), `sandbox_dirs` (operation domain), `docker_mount` (mounting channel).

**2. Customizable Harness Engineering.** Dispatch multiple Experts (research assistant, trader, programmer) within the same system. Extend via standard Skill, modular Tool (`src/tool/`, dynamically loaded by `dispatch_tool()`), or full Harness/Expert (inherit `BaseTask`, rewrite state machine).

**3. 99%+ KV Cache hit rate.** `dispatch_tool()` decouples tool schemas from System Prompts, so model KV Cache never invalidates from dynamic schema injection. This delivers extreme token economy and millisecond-level response.

**4. 7x24 reliability.** `APIKeyManager` auto load-balances across API keys (least-busy-first). Each subtask has persistent checkpoints saved every round. Crash? Reload and resume from last checkpoint.

**5. True multi-core concurrency.** Background subtasks run with independent API keys and state machines. Main chat session never blocks. Issue new commands while Agent processes heavy tasks.

**6. Memory and soul.** Memo tool + PurrMemo local engine captures preferences automatically. Heartbeat sensor (`HARNESS.md`) enables unattended self-iteration. Modify `SOUL.md` to inject unique personality.

---

## Architecture

```
Sensor Layer (Gateway)     Feishu / RSS / Clock -> Gateway.push()
       |
Agent Layer                Dialog / force_push / Memory
       |
Model Layer (APIKeyManager)  Least-busy key allocation
       |
Tool Layer (dispatch_tool)   Bash / Fetch / FileSystem / Search / Memo / CallMCP / Cron / Task
       |
Harness Layer (BaseTask)     Atomic methods: run_llm_step / run_tool_calling / check_memory / save_checkpoints
```

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

- Thanks **Gemini Pro 3.1** for assisting in building the UI interface.
- Thanks **[zhenghuanle](https://github.com/zhenghuanle)** for testing the installation flow.
- Thanks **[Gaeulczy](https://github.com/Gaeulczy)** for testing the one-click setup and start scripts.

---

## License & Disclaimer

This project is licensed under the **GNU GPL-3.0 License**.

- **Core copyleft**: Any distribution of modified core framework must be open-sourced under GPL-3.0.
- **Plugin/Extension exemption**: Plugins, Harness/Expert, and external services developed on standard interfaces are **not subject to GPL contagion** — they can be closed-source and used commercially.
- **Disclaimer**: This software is provided "as is", without warranty of any kind. The authors are not liable for any damages arising from its use.
