<div align="center">

# PurrCat

*A highly customizable local personal agent framework.*

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)]()
[![License](https://img.shields.io/badge/license-GPLv3-green)]()

> 该项目仍在持续高频更新中

</div>

---

## 📖 Introduction

[📚 PurrCat 官方文档（持续更新中）](https://purrpod.github.io/)

PurrCat 是一个高度可定制化的本地私人 Agent 助理框架。项目使用 Python 构建，核心代码精简，易于初学者上手。有别于常规的云端应用，PurrCat 专注于本地运行，通过构建独立的沙盒环境来执行任务，并拥有管理和操作本地文件系统的能力。


## ✨ Features

* **🛡️ Local Sandbox Isolation (绝对安全的运行环境)**
    * 作为主打本地优先的私人 Agent 助手，框架提供两级环境隔离。所有代码执行与高危操作均被严格封锁在 **Docker 沙盒** 内；对于物理机本地系统，通过配置文件（隐私禁区、操作域、挂载通道）实现严格的文件级读写权限管控，确保物理机系统与个人数据的绝对安全。

* **🧩 Highly Extensible: Harness Engineering (降维打击的可定制架构)**
    * 摒弃死板的单一提示词限制，提供极具拓展性的专家（Expert）定制能力。系统原生支持标准化 Skill 与 MCP Service，并提供纯 Python 编写的底层 Plugin 基础设施。针对复杂行业工作流，开发者可继承基类深度重写流转逻辑，轻松打造专属的 Harness Engineering。

* **⚡ Efficient Context Economics (极致的上下文经济学)**
    * 经过深度实验验证的底层优化，大幅提升大模型的 KV Cache 命中率（主 Agent 稳定在 90%+），在显著压降 Token 成本的同时，带来肉眼可见的响应提速。

* **🔀 Non-blocking Concurrent Subtasks (真正的“多核”并发体验)**
    * 打破传统一问一答的单线阻塞模式。耗时任务可切入后台作为子任务静默运行，主会话窗口保持绝对自由。支持多 Agent 异步协作，并允许开发者随时通过状态机查看进度或在运行中动态注入新指令，真正实现多任务统筹调度。

* **⛰️ Stable and Reliable (7x24 小时无人值守)**
    * 引入 OS 级调度理念，内置时间片轮转 (RR) 调度与 API 线程级防堵塞设计。每个子任务独立绑定缓存，且状态机在对话结束时实时落盘。支持意外中断后的断点重连与排错，无缝恢复历史对话与任务，确保工业级长效稳定运行。

* **🧠 Soulful Private Assistant (具备“灵魂”的轻量记忆)**
    * 针对个人应用场景，抛弃臃肿低效的传统 RAG，采用极低损耗的轻型备忘录驱动记忆体系，在交互中自动积累用户偏好。开放底层人格接口 (`SOUL.md`)，允许深度定制行事风格与逻辑，打造独一无二的私人专属助手。

## 🆕 What's New
*   **[2026/04/24]** 更新了 TUI，将 WebUI 移动至别的仓库
*   **[2026/04/20]** 使用大小核架构最大化压榨单 API-Key 的 TPM 与 RPM，加速任务执行 
*   **[2026/04/19]** 上新了桌宠插件，更轻量更方便地与 Agent 对话，详见：[✨ PurrCat 的桌宠插件](https://github.com/PurrPod/widget)
*   **[2026/04/16]** 上新了 expert 特性，对特定领域子任务有专门的 Harness Engineering， 提高拓展性和可定制性（本仓库提供了 demo trading 专家，可以此为模板定制自己的工作流）
*   **[2026/04/15]** 重构了工具调用逻辑，使用路由工具防止动态加载工具破坏上下文降低 KV cache 命中率，更加经济！（目前平均 KV cache 命中率已稳定在93.1%左右）
*   **[2026/04/14]** Docker 沙盒支持动态挂载宿主机文件夹，让沙盒与主机文件系统的联系更加紧密，在保证安全的前提提高 Agent 自由度。
*   **[2026/04/13]** 新增 Agent 轻型备忘录，以极小的 token 开支让 Agent 能够记住你的喜好，在实践中增长经验。
*   **[2026/04/10]** 新增了任务绑定机制，保证一个任务对应一个 API 线程，并修改了工具清理逻辑，提高 KV cache 命中率。
*   **[2026/04/08]** 模拟操作系统多线程技术重构了模型调度过程，预防高并发任务情况下的 API 限速问题。

## 🚀 Quick Start

PurrCat 提供了跨平台的一键部署脚本，请确保你的电脑已安装 Miniconda、Node.js 和 Docker。

- 🪟 对于 Windows 用户：

首次安装：右键点击 scripts 文件夹下的 setup.bat 选择“以管理员身份运行”（脚本会自动为你下载缺失的 Miniconda 环境，并解决网络重试问题）。

日常启动：双击运行 scripts 文件夹下的 start.bat。

- 🍎/🐧 对于 macOS / Linux 用户（此方法仍未被测试，建议优先使用 Windows 版本）：

首次安装：打开终端，运行 scripts/setup.sh

日常启动：运行 scripts/start.sh

注：首次安装后，至少要进行模型配置才可正常执行指令。在`data/config/secrets/models.yaml`里，请提供至少一个模型的名称、api-key、base_url




## 🙏 Acknowledgments

*   感谢 **Gemini Pro 3.1**：协助构建了精美的 UI 界面，本项目的 UI 代码全部由 AI 编写。
*   感谢 **[zhenghuanle](https://github.com/zhenghuanle)**：为本仓库测试了从零开始的安装流程。
*   感谢 **[Gaeulczy](https://github.com/Gaeulczy)**：为本仓库测试了一键安装脚本和一键运行脚本。

---

## 📄 License & Disclaimer

本项目核心框架采用 **[GNU GPL-3.0 License](https://www.gnu.org/licenses/gpl-3.0.txt)** 协议开源。使用本项目代码时，您**必须**遵守以下条款：

1.  **核心开源与生态豁免：** 
    * **核心传染性（商用必开源）：** 任何基于本项目**核心框架**进行的二次开发、修改或衍生项目，只要对外分发（包括打包成新软件提供给他人使用或 SaaS 化交付），其全部源代码必须同样以 GPL-3.0 协议开源。
    * **插件/拓展生态豁免（允许闭源商用）：** 任何基于本框架标准接口独立开发的插件、Harness/Expert 及外部挂载服务，**均不受 GPL-3.0 协议的传染约束**。插件开发者拥有完全的版权和分发自主权，可自由选择任何开源协议，亦可完全**闭源并用于商业化变现**。
2.  **绝对免责声明：** 
    * **风险自担：** 本项目代码“按原样”提供。**作者不对任何人因使用、修改或运行本项目代码（包括但不限于 Agent 误操作/自行赋予 Agent 过高权限导致的本地数据丢失、系统损坏等任何直接或间接后果）承担任何法律责任。** 使用本框架造成的一切后果由使用者自行承担。
3.  **合法合规使用：** 请严格遵守当地法律法规，严禁将本项目用于任何非法收集数据、恶意破坏他人系统等违规用途，由此造成的法律问题由使用者及违规教程提供者负责。