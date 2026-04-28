---
name: self_improve
description: "Extend PurrCat's capabilities. Create new Skills, write Expert tasks (harness), add extend_tools, modify agent SOUL.md, or understand framework architecture. NOT for general coding tasks."
---

# PurrCat 自我提升指南

## 概述

扩展机制按复杂度排列：
```
改 SOUL.md → 写 Skill → 加 Expert
```

---

## 一、当前系统架构

### 目录树

```
purrcat/
├── src/
│   ├── agent/
│   │   ├── SOUL.md              # Agent 人格定义
│   │   ├── agent.py             # Agent 主循环
│   │   ├── manager.py           # Agent 管理器单例
│   │   ├── core/
│   │   │   ├── HARNESS.md       # 心跳传感器注入的运维指南
│   │   │   └── memory.md        # 长期记忆（update_memo 写入）
│   │   └── system_rules/        # 系统指令
│   │       ├── 01_guide.md
│   │       ├── 02_tools.md
│   │       ├── 03_rules.md
│   │       └── 04_self_improvement.md
│   ├── harness/                  # Expert / Task 系统
│   │   ├── task.py              # BaseTask 基类
│   │   └── expert/
│   │       ├── coding/          # CodingTask（代码专家）
│   │       │   ├── task.py
│   │       │   └── extend_tool/ # 代码工具（code_search, file_edit 等）
│   │       └── trading/         # TradingTask（交易专家）
│   │           ├── task.py
│   │           └── extend_tool/ # 金融工具（data_sources, kv_cache 等）
│   ├── memory/
│   │   └── purrmemo_client.py   # PurrMemo 记忆系统客户端
│   ├── sensor/                   # 传感器系统
│   │   ├── message/             # 社交消息接收（飞书等）
│   │   │   └── feishu.py
│   │   ├── subscribe/           # 订阅轮询（RSS 等）
│   │   │   └── rss.py
│   │   ├── system/              # 系统内部传感器
│   │   │   └── const.py         # heartbeat + clock
│   │   └── environment/         # 硬件环境感知（预留）
│   ├── model/
│   │   └── model.py             # LLM 调度器（Worker 池 + 限流）
│   ├── plugins/                  # 工具路由
│   │   ├── plugin_collection/   # 工具实现
│   │   └── route/               # 工具注册与分发
│   │       ├── agent_tool.py    # Agent 工具实现
│   │       ├── base_tool.py     # 工具基类
│   │       └── mcp_tool.py      # MCP 工具加载
│   ├── loader/
│   │   └── memory.py            # 记忆加载器
│   └── utils/
│       └── config.py            # 配置管理
├── data/
│   ├── config/                   # 配置文件
│   │   ├── configs/
│   │   │   ├── system.yaml      # 系统配置（agent_model, rss, heartbeat 等）
│   │   │   └── mcp_servers.yaml # MCP 服务器配置
│   │   ├── secrets/
│   │   │   └── credentials.yaml # 凭据（API keys, tokens）
│   │   └── file_config.json     # 文件系统白名单
│   ├── skill/                    # 技能包目录 ★
│   └── memory/                   # 本地记忆存储
└── tui/                          # Textual TUI
    └── app.py                    # TUI 入口
```

### 两层文件系统

```
宿主机: project_root/        ← filesystem 工具访问（只读 + 有限修改）
宿主机: agent_vm/  ──映射──→ 沙盒: /agent_vm/  ← execute_command 访问（完全控制）
```

- **extend_tool**（code_search, file_read, file_edit 等）→ 操作宿主机文件
- **execute_command** → 操作 Docker 沙盒（只能访问 `/agent_vm/` 目录下的内容）
- 创建 Skill 时，`SKILL.md` 放在 `data/skill/`（宿主机），相关文件也放在那里

---

## 二、编写 Skill（能力包）

### 2.1 结构

```
data/skill/your_skill/
├── SKILL.md               # ★ 核心：技能说明（YAML frontmatter + Markdown）
└── (可选辅助文件)
```

### 2.2 SKILL.md 格式

```markdown
---
name: your_skill
description: "触发条件描述。何时应该使用此技能？"
---

# 技能标题

## Overview
简短说明。

## Usage
步骤或命令。
```

**关键规则**：
- `name` 是唯一标识，Agent 通过 `load_skill("name")` 加载
- `description` 写清楚**触发条件**，帮助 Agent 判断何时使用
- 所有文件放技能目录下，通过相对路径引用

### 2.3 示例：Markdown 转 PDF

```markdown
---
name: md_to_pdf
description: "Convert .md to .pdf using pandoc."
---

# MD to PDF

```bash
pandoc input.md -o output.pdf --pdf-engine=xelatex
```
```

---

## 三、编写 Expert（任务专家）

### 3.1 Expert 注册机制

Expert 通过 `BaseTask` 的元类自动注册，继承时指定 `expert_type`：

```python
from src.harness.task import BaseTask

class MyExpertTask(
    BaseTask,
    expert_type="my_expert",
    description="我的专家",
    parameters={"param1": {"type": "string", "description": "...", "required": True}}
):
    ...
```

然后在 `add_task(expert="my_expert")` 中即可调用。

### 3.2 可重写钩子

| 方法 | 作用 |
|------|------|
| `_build_system_prompt()` | 定制 System Prompt |
| `get_available_tools()` | 注入领域工具 Schema |
| `_handle_expert_tool()` | 拦截执行扩展工具 |
| `run()` | **完全重写**执行逻辑 |

### 3.3 Expert vs Skill 选择

| 场景 | Expert | Skill |
|------|--------|-------|
| 宿主机文件读写 | ✅ | ❌ |
| 复杂工作流/状态机 | ✅ 重写 run() | ❌ |
| 断点续传 | ✅ BaseTask 自带 | ❌ |
| 命令行工具封装 | ❌ 太重 | ✅ |
| 知识性指导 | ❌ | ✅ |

---

## 四、提交流程

```bash
git add data/skill/your_skill/ src/harness/expert/your_expert/
git commit -m "feat: add your_feature - description"
# push 用 token（见系统已有脚本）
```

---

## 五、调试

### 检查 Expert 注册
```python
from src.harness.task import BaseTask
print(list(BaseTask._EXPERT_REGISTRY.keys()))
```

### 检查 Skill 加载
```bash
ls data/skill/your_skill/
cat data/skill/your_skill/SKILL.md
```

### 工具查找
通过 `search_in_system("describe what you need")` 查找可用工具和技能。
