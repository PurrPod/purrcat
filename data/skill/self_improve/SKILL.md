---
name: self_improve
description: "Use this skill whenever the user or another agent wants to extend the system's own capabilities. This includes: creating new skills, writing new Expert tasks (harness), adding new extend_tools, modifying the agent's SOUL.md personality, or understanding how the PurrCat framework can be modified to add new functionality. Do NOT use this for general coding tasks that are not about modifying PurrCat itself."
---

# PurrCat 自我提升指南

## 概述

PurrCat 提供了多层扩展机制，按复杂度从低到高排列：

```
改 SOUL.md（调性格）→ 写 Skill（加能力包）→ 加 Expert（定制工作流）→ 写 Plugin（底层工具）
```

本指南覆盖前三层，第四层 Plugin 涉及框架内部路由，非必要不动。

---

## 一、理解系统架构

### 关键目录结构

```
purrcat/
├── src/
│   ├── agent/
│   │   ├── SOUL.md              # Agent 人格定义（改性格改这里）
│   │   ├── agent.py             # Agent 主循环
│   │   ├── manager.py           # Agent 管理器单例
│   │   └── system_rules/        # 系统指令（工具指南/行为规范）
│   ├── harness/                  # Expert / Task 系统
│   │   ├── task.py              # BaseTask 基类
│   │   └── expert/
│   │       ├── coding/          # CodingTask（代码专家）
│   │       │   ├── task.py      # 任务定义 + System Prompt
│   │       │   └── extend_tool/ # 扩展工具集
│   │       └── trading/         # TradingTask（交易专家）
│   │           ├── task.py
│   │           └── extend_tool/
│   └── plugins/                 # 底层插件（非必要不动）
├── data/
│   ├── skill/                   # 技能包目录 ★ 加技能放这里
│   └── config/                  # 配置
└── tui/                         # 终端 UI
```

### 两层文件系统

```
宿主机:  project_root/    ← extend_tool / file_edit 等可以读写
宿主机:  agent_vm/  ──→  沙盒: /agent_vm/  ← execute_command 可以读写
```

- **extend_tool** 和 **file_edit/file_read/code_search/lsp** → 操作宿主机文件
- **execute_command** → 操作 Docker 沙盒（只能访问 `/agent_vm/`）
- 创建 Skill 时，`SKILL.md` 放在 `data/skill/`（宿主机），脚本放在 `scripts/` 下

---

## 二、编写 Skill（能力包）

### 2.1 Skill 的结构

```
data/skill/你的技能名/
├── SKILL.md               # ★ 核心：技能说明文档（YAML frontmatter + Markdown）
├── LICENSE.txt            # 可选：许可证
├── scripts/               # 可选：辅助脚本
│   └── your_script.py
└── ref.md                 # 可选：参考文档
```

### 2.2 SKILL.md 格式

```markdown
---
name: your_skill_name
description: "触发条件描述。何时应该使用此技能？何时不应该？"
license: MIT
---

# 技能标题

## Overview

简短说明这个技能解决什么问题。

## Quick Start

```bash
# 命令行示例
command_to_run
```

## Detailed Guide

分步骤详细说明。
```

**关键规则**：
- `name` 字段是技能的唯一标识，Agent 通过 `load_skill("name")` 加载
- `description` 要写清楚**触发条件**，帮助 Agent 判断何时使用
- 脚本要放在 `scripts/` 子目录下，通过相对路径引用
- 技能文件通过 `execute_command` 在沙盒中执行，只能访问 `/agent_vm/` 目录

### 2.3 示例：创建一个 Markdown 转 PDF 技能

```markdown
---
name: md_to_pdf
description: "Convert Markdown files to PDF using pandoc. Use when user asks to convert .md to .pdf."
---

# Markdown to PDF

## Usage

```bash
pandoc input.md -o output.pdf --pdf-engine=xelatex
```
```

### 2.4 加载和测试 Skill

```bash
# 在沙盒中测试你的脚本
python data/skill/your_skill/scripts/test.py

# Agent 加载技能
# 在对话中 Agent 会自动通过 load_skill 加载匹配的 skill
```

### 2.5 Skill 适用场景

Skill 最适合：
- 需要**命令行工具链**的操作（pandoc、ffmpeg、imagemagick 等）
- **纯知识性指导**（告诉 Agent 怎么做，不涉及代码修改）
- 封装**外部 CLI 工具**的使用方法

Skill **不适合**：
- 需要**复杂工作流编排**（多角色、状态机）→ 用 Expert
- 需要**宿主机文件系统操作** → 用 Expert + extend_tool
- 需要**修改框架本身代码** → 直接修改源码

---

## 三、修改 Agent 人格（SOUL.md）

### 3.1 位置

```bash
src/agent/SOUL.md
```

### 3.2 格式

```markdown
## 1. 性格

你是一个...（描述性格、语气、价值观）
```

### 3.3 注意事项

- 只改性格描述，不要动 `system_rules/` 目录下的系统指令
- `system_rules/` 包含工具指南、行为规范等，改了可能导致工具调用异常
- 修改后重启系统生效

---

## 四、创建新 Expert（领域专家）

当需求涉及**复杂工作流编排**或**需要宿主机文件操作**时，应该创建新的 Expert。

### 4.1 完整步骤

#### 步骤 1：创建 Expert 目录

```bash
mkdir -p src/harness/expert/your_expert/extend_tool/
```

#### 步骤 2：编写 Expert Task

创建 `src/harness/expert/your_expert/task.py`：

```python
import json
from src.harness.task import BaseTask

class YourExpertTask(
    BaseTask,
    expert_type="your_expert",           # ★ add_task 时的 expert 参数值
    description="你的领域专家描述",       # ★ Agent 看到的选择描述
    parameters={                         # ★ 传给 add_task 的 expert_kwargs 参数
        "param1": {
            "type": "string",
            "description": "参数说明",
            "required": True
        }
    }
):
    def __init__(self, task_name, prompt, core, param1=None):
        # 初始化你的专属状态
        self.your_state = ""
        super().__init__(task_name, prompt, core)

    def _build_system_prompt(self):
        """定制你的 System Prompt"""
        return """# 角色定义
你是一个 XXX 专家...

# 工作流程
1. 步骤一
2. 步骤二
"""

    def get_available_tools(self) -> list:
        """注入你的专属工具"""
        tools = super().get_available_tools()
        if YOUR_TOOL_SCHEMA:
            tools.append(YOUR_TOOL_SCHEMA)
        return tools

    def _handle_expert_tool(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """处理你的专属工具调用"""
        if tool_name == "your_tool":
            return True, execute_your_tool(arguments, self)
        return False, ""

    def _on_save_state(self) -> dict:
        """持久化状态（断点恢复用）"""
        return {"your_state": self.your_state}

    def _on_restore_state(self, state: dict):
        """恢复状态"""
        self.your_state = state.get("extra_state", {}).get("your_state", "")
```

#### 步骤 3：编写 Extend Tool（可选）

创建 `src/harness/expert/your_expert/extend_tool/your_tool.py`：

```python
# extend_tool 运行在宿主机进程里，可以直接读写宿主机文件
# 不需要通过沙盒

import json
import os

YOUR_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "your_tool",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "参数说明"
                }
            },
            "required": ["param"]
        }
    }
}

def execute_your_tool(arguments: dict, task=None) -> str:
    param = arguments.get("param", "")
    # 你的业务逻辑...
    result = f"处理结果: {param}"
    return json.dumps({"type": "text", "content": result})
```

#### 步骤 4：注册到系统

**不需要手动注册！** `BaseTask.__init_subclass__` 会在类定义时**自动注册**到全局 `_EXPERT_REGISTRY`。只要文件被 import 即可。

关键代码（在 `BaseTask` 中）：

```python
def __init_subclass__(cls, expert_type=None, description="", parameters=None, **kwargs):
    super().__init_subclass__(**kwargs)
    if expert_type:
        cls._EXPERT_REGISTRY[expert_type] = {
            "class": cls,
            "description": description,
            "parameters": parameters or {}
        }
```

#### 步骤 5：确保被 import

专家的自动发现依赖 import。框架有两种方式加载：

**方式 A**：在 `src/plugins/route/agent_tool.py` 中已有：

```python
from src.harness.expert.coding.task import CodingTask
from src.harness.expert.trading.task import TradingTask
```

你需要在 `agent_tool.py` 中加上你的 import：

```python
from src.harness.expert.your_expert.task import YourExpertTask
```

**方式 B**：框架也有 `auto_discover_experts()` 函数，会扫描检查点目录恢复已有任务。但新 Expert 第一次加载仍需要 import。

### 4.2 Expert 生命周期

```
用户通过 add_task 创建
       │
       ▼
TaskFactory.create_task(expert_type="your_expert", ...)
       │
       ▼
__init__ → _build_system_prompt → 保存检查点
       │
       ▼
run() 循环:
  ├─ 调 LLM（带你的工具）
  ├─ 解析响应 → 执行工具 → 回填结果
  └─ 循环直到 task_done
       │
       ▼
完成 / 可断点恢复
```

### 4.3 可重写的钩子方法

| 方法 | 作用 |
|------|------|
| `_build_system_prompt()` | 定制 System Prompt |
| `get_available_tools()` | 注入领域工具 Schema |
| `_handle_expert_tool()` | 拦截执行扩展工具 |
| `_on_save_state()` | 持久化额外状态 |
| `_on_restore_state()` | 恢复额外状态 |
| `run()` | **完全重写**执行逻辑（如 TradingTask 的多角色辩论） |

### 4.4 完整示例：创建一个代码审查 Expert

```python
# src/harness/expert/code_review/task.py
from src.harness.task import BaseTask

class CodeReviewTask(
    BaseTask,
    expert_type="code_review",
    description="代码审查专家，负责对代码变更进行质量审查",
    parameters={
        "repo_path": {
            "type": "string",
            "description": "仓库路径",
            "required": True
        }
    }
):
    def __init__(self, task_name, prompt, core, repo_path=None):
        self.repo_path = repo_path or os.getcwd()
        self.review_results = []
        super().__init__(task_name, prompt, core)

    def _build_system_prompt(self):
        return """# 角色定义
你是一名资深代码审查专家。

# 审查原则
1. 安全性：检查 SQL 注入、XSS、权限漏洞
2. 性能：识别 N+1 查询、内存泄漏
3. 可维护性：命名、注释、设计模式
4. 正确性：边界条件、并发问题

# 输出格式
对每个审查点给出：✅ 通过 / ⚠️ 警告 / ❌ 拒绝 + 理由
"""

    def get_available_tools(self):
        tools = super().get_available_tools()
        # 复用 coding 的 code_search 和 file_read 工具
        from src.harness.expert.coding.extend_tool import EXTEND_TOOLS_SCHEMA
        tools.extend(EXTEND_TOOLS_SCHEMA)
        return tools
```

然后在 `agent_tool.py` 中加上 import：

```python
from src.harness.expert.code_review.task import CodeReviewTask
```

### 4.5 Expert vs Skill 选择指南

| 场景 | 选 Expert | 选 Skill |
|------|-----------|----------|
| 需要**宿主机文件读写** | ✅ | ❌ 脚本在沙盒 |
| 需要**复杂工作流**（多角色/状态机） | ✅ 可重写 run() | ❌ |
| 需要**持久化状态**（断点续传） | ✅ BaseTask 自带 | ❌ |
| 只是**命令行工具封装** | ❌ 太重 | ✅ |
| 只是**知识性指导**（告诉 Agent 怎么做） | ❌ | ✅ |
| **快速开发** | ❌ 需要写 Python 类 | ✅ 写 Markdown 即可 |

---

## 五、提交流程

```bash
# 1. 创建分支
git checkout -b your-feature

# 2. 添加文件
git add data/skill/your_skill/ src/harness/expert/your_expert/

# 3. 提交（用英文）
git commit -m "feat: add your_feature - brief description"

# 4. 推送
git push origin your-feature

# 5. 在 GitHub 创建 Pull Request
```

---

## 六、调试技巧

### 检查 Expert 是否成功注册

Expert 启动时会在控制台打印：

```
✅ 自动注册子任务专家: coding -> CodingTask
✅ 自动注册子任务专家: trading -> TradingTask
```

如果在日志中看不到你的 Expert 名称，说明 import 没生效。

### 手动测试 Expert

```python
# 在沙盒中测试
python3 -c "
from src.harness.expert.your_expert.task import YourExpertTask
print('✅ Expert loaded successfully')
print('Registered experts:', list(BaseTask._EXPERT_REGISTRY.keys()))
"
```

### 检查 Skill 是否可加载

```bash
ls data/skill/   # 确认目录存在
cat data/skill/your_skill/SKILL.md   # 确认格式正确
```
