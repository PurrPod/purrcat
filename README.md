# Cat In Cup 

Cat In Cup 是一个高度可定制的开源 AI Agent 框架，致力于帮助开发者快速构建专属的智能助手。项目采用前后端分离架构，内置基于 Docker 的安全代码执行沙盒，并支持 MCP（Model Context Protocol）生态与多源传感器（如飞书、RSS），让你的 Agent 不仅能“思考”，还能“感知”和“行动”。

### 🚀 快速开始：你与 Agent 的第一句话

**1. 环境初始化（首次启动）**
为了保证 Agent 具备安全独立的代码执行能力，需要先构建沙盒环境和 Python 运行环境：

```bash
# 给 Agent 提供安全的沙盒环境，工作目录将映射为 agent_vm
docker build -t my_agent_env:latest .  

# 配置并激活宿主机 Conda 环境
conda env create -f environment.yml
conda activate CatInCup
```

**2. 启动服务**
项目包含独立的后端引擎与 Web 前端，请在两个终端分别启动：

```bash
# 终端 1：启动 Python 后端
python backend.py

# 终端 2：启动前端 UI
cd ui
npm install  # 首次运行请先安装依赖
npm run dev
```

**3. 首次连通**
服务启动后，在浏览器打开前端页面，进入**配置页**完善你的大语言模型 API 设置。配置完成后回到首页，试着向它发送一句“你好”，看看你的专属 Agent 是否已经成功苏醒。

### ⚙️ 个性化定制：打造独一无二的助手

Cat In Cup 提供了极高的自由度，你可以通过 UI 界面和本地文件深度定制你的 Agent：

* **注入灵魂**：修改 `src/agent/SOUL.md` 文件，为你的 Agent 设定独特的性格、语气和核心价值观。
* **连接世界**：在配置页添加 Tavily Web API 赋予其强大的联网搜索能力，或完善 Feishu（飞书）相关配置将其接入你的日常工作流。
* **扩展能力**：框架支持无缝接入各类 MCP 服务或 Skill，你可以根据需求为其装备不同的工具，无限扩展 Agent 的能力边界。
