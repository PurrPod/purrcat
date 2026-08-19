<div align="center">

# PurrCat

[English](README.md) | 简体中文

经济、高效、可定制、本地优先的个人 AI Agent 框架。

[文档](https://purrpod.github.io/) | [部署](https://purrpod.github.io/guide/deployment) | [架构](https://purrpod.github.io/develop/architecture) | [扩展](https://purrpod.github.io/develop/extension) | [配置](https://purrpod.github.io/config/) | [FAQ](https://purrpod.github.io/guide/faq)

</div>

---

<img src="purrcat-logo.png" width="220" height="220" alt="PurrCat" align="right" />

## 快速开始

### 环境要求

- Python 3.10+、[uv](https://docs.astral.sh/uv/)、Node.js 18+、Git
- [Docker](https://docs.docker.com/get-docker/)（沙盒 Bash 工具需要）
- 也可运行 `purrcat setup` 一步初始化环境（uv、Docker、嵌入模型、Playwright）

### 方式一：Electron 桌面端（推荐）

```bash
git clone https://github.com/PurrPod/purrcat.git
cd purrcat
uv sync                    # 安装 Python 依赖
npm install                # 根目录依赖（Electron 等）
npm install --prefix ui    # 前端依赖
npm run dev                # 一键拉起 后端 + 前端 + Electron
```

### 方式二：Web UI（轻量）

```bash
uv sync
npm install --prefix ui
npm run build:ui                             # 构建前端静态文件
uv run python main.py --api --headless       # 浏览器打开 http://localhost:8000
```

> 注：本地文件操作、终端等功能依赖 Electron 运行时，纯浏览器模式下可能出现异常。建议使用桌面端获得完整体验。

## 架构

### 01 混合记忆与知识图谱

- 短时工作记忆：常驻内存的 `memo` 变量保留最近 10 次交互的浓缩总结，跨会话不丢失。
- 核心通用记忆：`MEMORY.md` 固化用户画像与工作经验，初始化时注入 System Prompt。
- 长期结构化记忆（PurrMemo）：情景记忆引擎（SQLite + FTS5）与语义记忆引擎（ChromaDB + NetworkX），支持实体关系的动态强化/削弱，可导出 HTML 可视化图谱。
- 混合检索：通过全局线程池并发执行 BM25 与向量检索，按 RRF 倒数排名融合。
- 异步消化：新认知先存入 `pending`，由后台守护进程转化为三元组；动态衰减机制自动清理长期未强化的记忆。

### 02 Harness DAG 工作流引擎

- 单人多脑并发执行，避免 Agent 间自然语言对话带来的 Token 冗余。
- 特定任务绑定特定工具，支持在特定阶段注入提示。
- 多态节点矩阵：直连 LLM Vision 的图片生成、条件路由（if/else、switch）、人工干预节点等。
- 状态机安全回滚：可在任意节点注入人工指令，清除下游旧状态，实现断点重连。
- 工作流通过单个 JSON 文件装载，支持运行时热更新。

### 03 安全工具链

- 沙盒 Bash：命令在独立 Docker 容器中执行，支持挂载目录访问外部。
- FileSystem 套件：`read` / `edit` / `write` / `search` / `glob`，底层经 MarkItDown 将 PDF/DOCX/XLSX 转为 Markdown。
- 边界管控：物理级黑白名单；Import 校验 30MB 上限与路径穿越，Export 自动触发 Git 快照。
- 扩展工具：CallMCP、混合检索 Search、Fetch、Memo、Cron、Task、ComputerUse、BrainStorm、KernelUpgrade，支持外部 MCP 服务。

### 04 智能体中枢与会话管理

- Git 式会话分支：new / branch / switch 自由切换，可随时安全切回主干。
- 异常修复：自动检查 tool calls 匹配情况，拦截残缺工具消息并回滚到安全状态。
- 上下文截断：Token 超限时在安全断点用 Memo 摘要替换较早历史。
- 生命力与灵魂：`SOUL.md` 定义人格价值观；Heartbeat 机制驱动空闲时自主巡查与汇报。
- 独立视觉顾问：将图片处理从主会话剥离，提高信噪比。

### 05 主动感知与事件网关

- 传感器以独立子进程运行，配合 PEP 723 内联依赖（uv 管理），单个传感器崩溃不影响主进程。
- Stdio 管道 JSON-RPC 通信，不占用网络端口。
- 内置传感器：System（心跳/轮询）、Feishu（WebSocket）、RSS、Audio（Whisper + pyttsx3）。

### 06 模型调度与并发

- API Key 负载均衡：线程锁维护可用 Key 列表，优先分配最空闲密钥。
- Semaphore 信号量排队，带 Jitter 的指数退避重试（最高 8 次），保障高并发可用性。

### 07 KV Cache 与 Token 经济

- APIKeyManager 实现任务/会话与单一密钥强绑定，多会话切换下保持稳定的缓存命中率。
- DAG 执行消除 Agent 间对话冗余；任务执行者提炼摘要交由后台消化，避免全量历史读取。

### 08 配置驱动的扩展机制

- 零代码接入 MCP：将标准 JSON 粘贴至 `mcp_config.json`，握手后工具树自动热更新。
- `purrcat install skill <url>` 下载社区 Skill 并加载至检索树。
- 前端可视化编排 DAG 节点，支持 JSON 一键导入导出。
- 传感器在 UI 中一键开关，启动时缺失的传感器脚本自动从云端拉取。

<br clear="right" />

---

## 致谢

- [zhenghuanle](https://github.com/zhenghuanle) 测试了从零开始的安装流程。
- [Gaeulczy](https://github.com/Gaeulczy) 测试了一键安装与运行脚本。
- 感谢中山大学开放鸿蒙技术俱乐部举办的智能体开发大赛提供的奖金赞助。

## 许可证

本项目基于 [MIT](LICENSE) 许可证开源，可自由使用、修改与分发，包括商业用途。
