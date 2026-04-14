<div align="center">

# CatInCup

*A highly customizable local personal agent framework.*

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)]()
[![License](https://img.shields.io/badge/license-GPLv3-green)]()

> 该项目仍在持续高频更新中

</div>

---

## 📖 Introduction

CatInCup 是一个高度可定制化的本地私人 Agent 助理框架。项目使用 Python 构建，核心代码精简，易于初学者上手。有别于常规的云端应用，CatInCup 专注于本地运行，通过构建独立的沙盒环境来执行任务，并拥有管理和操作本地文件系统的能力。


## ✨ Features

*   **Easy to Use**
    *   使用 Python 构建，核心逻辑清晰，易于二次开发与定制。
*   **Efficient**
    *   独创的 Harness Engineering 经过数月实验验证，剔除了同类agent冗余的提示词工程，在保证稳定性的同时相比于同类 Agent 框架更加经济高效。
*   **Stable and Reliable**
    *   内置 API 轮询机制等异常处理模块，支持断点重连和数据备份，确保系统长效稳定运行。
*   **Local Sandbox**
    *   采用本地沙盒化运行机制，对于主机本地文件，设置了严格的读写权限；只有在沙盒内才可运行 shell 命令。


## 🆕 What's New
*   **[2026/04/14]** Docker沙盒支持动态挂载宿主机文件夹，让沙盒与主机文件系统的联系更加紧密，在保证安全的前提提高 Agent 自由度。
*   **[2026/04/13]** 新增 Agent 轻型备忘录，以极小的 token 开支让 Agent 能够记住你的喜好，在实践中增长经验。
*   **[2026/04/10]** 新增了任务绑定机制，保证一个任务对应一个 API 线程，并修改了工具清理逻辑，提高 KV cache 命中率。
*   **[2026/04/08]** 模拟操作系统多线程技术重构了模型调度过程，预防高并发任务情况下的 API 限速问题。
*   **[2026/04/06]** 新增了 Docker 对 `data/skill` 的映射目录，赋予了 Agent 的自主技能扩展能力。

## 🚀 Quick Start（待测试）

CatInCup 提供了跨平台的一键部署脚本，请确保你的电脑已安装 Miniconda、Node.js 和 Docker。

- 🪟 对于 Windows 用户：

首次安装：右键点击 scripts 文件夹下的 setup.bat 选择“以管理员身份运行”（脚本会自动为你下载缺失的 Node.js 和 Miniconda 环境，并解决网络重试问题）。

日常启动：双击运行 scripts 文件夹下的 start.bat。

- 🍎/🐧 对于 macOS / Linux 用户：

首次安装：打开终端，运行 scripts/setup.sh

日常启动：运行 scripts/start.sh


## 📚 Documentation

本项目的使用文档正在编写中，敬请期待。

> 本项目非盈利，涉及框架基础使用或环境配置等常规问题，请优先通过搜索引擎解决。本项目社区暂不提供基础教学解答。


## 🙏 Acknowledgments

*   感谢 **Gemini Pro 3.1**：协助构建了精美的 UI 界面，本项目的 UI 代码全部由 AI 编写。
*   感谢 **[zhenghuanle](https://github.com/zhenghuanle)**：为本仓库测试了从零开始的安装流程。

---

## 📄 License & Disclaimer

本项目采用 **[GNU GPL-3.0 License](https://www.gnu.org/licenses/gpl-3.0.txt)** 协议开源。使用本项目代码时，您**必须**遵守以下条款：

1.  **开源传染性（商用必开源）：** 任何基于本项目进行的二次开发、修改或衍生项目，只要对外分发（包括打包成新软件提供给他人使用），其全部源代码必须同样以 GPL-3.0 协议开源。
2.  **绝对免责声明：** 
    *   **高权限警告：** 本项目作为本地私人助理，具备直接修改、删除和操作本地文件的能力。
    *   **风险自担：** 本项目代码“按原样”提供。**作者不对任何人因使用、修改或运行本项目代码（包括但不限于 Agent 误操作导致的本地数据丢失、系统损坏等任何直接或间接后果）承担任何法律责任。** 使用本框架造成的一切后果由使用者自行承担。
3.  **合法合规使用：** 请严格遵守当地法律法规，严禁将本项目用于任何非法收集数据、恶意破坏他人系统等违规用途，由此造成的法律问题由使用者及违规教程提供者负责。