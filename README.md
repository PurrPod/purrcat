# PurrCat

A highly customizable local-first personal agent framework with Docker sandbox isolation, 99%+ KV Cache hit rate, and atomic Harness architecture.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-GPLv3-green)]()

---

## Quick Start

```bash
# Clone and enter
git clone https://github.com/PurrPod/purrcat.git
cd purrcat

# One-click setup (Docker sandbox + Conda env + embedding model)
purrcat setup

# Generate config files
purrcat init

# Edit your API keys
vim .purrcat/.model.yaml

# Start
purrcat start
```

- `purrcat start --headless` — run without TUI
- See [Full Documentation](https://purrpod.github.io/purrcat/) for detailed guide

---

## Core Architecture

**Sandbox Isolation** — All code execution is confined within Docker containers. Host file access is controlled via strict whitelist (`.purrcat/.file.yaml`), eliminating Agent runaway risks.

**99%+ KV Cache Hit Rate** — Proprietary `dispatch_tool()` routing decouples tool schemas from System Prompts, maintaining stable 99%+ cache hits for extreme token economy.

**Atomic Harness Architecture** — BaseTask provides 12 atomic modules (LLM communication, tool parsing, state persistence, memory compression, etc.) for composing custom Expert workflows.

**APIKeyManager Smart Scheduling** — Auto load-balances across API keys (least-busy-first). Each subtask binds an independent key with persistent state machines. Main session never blocks.

**Sensor Gateway** — Unified message gateway for multi-channel communication (Feishu, RSS, Clock). Sensors auto-register via `BaseSensor` + `SensorGateway`.

---

## Documentation

- [Introduction](https://purrpod.github.io/purrcat/intro.html) — Features and design philosophy
- [Deployment Guide](https://purrpod.github.io/purrcat/guide/deployment) — Setup instructions
- [Architecture](https://purrpod.github.io/purrcat/develop/architecture) — Project structure and design decisions
- [Extension Guide](https://purrpod.github.io/purrcat/develop/extension) — Skill, Tool, Expert, Sensor development
- [Configuration](https://purrpod.github.io/purrcat/config/) — `.purrcat/` config reference
- [FAQ](https://purrpod.github.io/purrcat/guide/faq) — Common issues

---

## Acknowledgments

- Thanks **Gemini Pro 3.1** for assisting in building the UI interface
- Thanks **[zhenghuanle](https://github.com/zhenghuanle)** for testing the installation flow
- Thanks **[Gaeulczy](https://github.com/Gaeulczy)** for testing the one-click setup and start scripts

---

## License & Disclaimer

This project is licensed under the **GNU GPL-3.0 License**.

- **Core copyleft**: Any distribution of modified core framework must be open-sourced under GPL-3.0.
- **Plugin/Extension exemption**: Plugins, Harness/Expert, and external services developed on standard interfaces are **not subject to GPL contagion** — they can be closed-source and used commercially.
- **Disclaimer**: This software is provided "as is", without warranty of any kind. The authors are not liable for any damages arising from its use.
