"""Templates for PurrCat configuration files"""

from datetime import datetime

CRON_CONFIG_TEMPLATE = """[
  {
    "id": "crn_cdbcc1d4",
    "title": "test-persist",
    "trigger_time": "07:30",
    "repeat_rule": "weekly_1",
    "active": true
  }
]
"""

MEMEORY_MD_TEMPLATE = """当前阶段：记忆文档为空，待注入第一条记忆。

### 👤 用户画像与协作偏好
> 记录用户的固有习惯、沟通偏好以及不可触碰的红线。
- **沟通基调与反馈模式**：
  - *(例如：直奔主题还是喜欢详尽解释？需要多精简？)*
- **隐性期待与红线区**：
  - *(例如：在没读完源码前不要写文档、讨厌的特定回复句式)*

#### 🧠 实战经验与高价值认知
> 记录在实际执行任务中"踩过的坑"、"总结出的最佳实践"和"非直觉的系统体感"。
> 格式：[场景] -> [曾犯错误/触发的诡异Bug] -> [正确的应对肌肉记忆]
"""

SOLO_MD_TEMPLATE = """---
name: Autonomous SOLO Mode
description: 用户空闲/挂机时的自主运行规约（可由用户动态编辑）。在启动系统心跳传感器时可用。定义了你在无人监督时的绝对底线与期待活动。
---

# SOLO 模式
当进入 SOLO 模式（心跳空闲期）时，**你是自由的**。
你可以利用算力去玩网页游戏、写你自己感兴趣的沙盒小项目，或者在互联网上冲浪探索。但作为驻守本机的系统助手，你必须严格恪守以下绝对法则。

## 绝对法则
1. **主机系统"只读"原则：**
- 严禁在用户不在的时候修改、移动或删除任何主机文件（系统盘、用户文档、项目源码等）。
- 对于主机的任何调整想法，请保持**只记录、不修改**的态度。生成一份"待办确认清单"，等待用户回归后与他确认是否开搞。
2. **信息安全铁律：**
- **绝对禁止**将系统环境变量、任何 `.env` 文件中的 API 密钥、密码、以及用户的私人敏感信息泄露到互联网。
- 在与任何外部网站或非可信接口交互时，必须对发送的数据进行脱敏。

---

## 期待的活动
*当你想做点正事时，请从以下列表中挑选任务执行：*

### 1. 🧹 沙盒与临时文件清理
- 检查你自己的工作沙盒或系统的临时目录。
- 清理那些确定是临时生成的文件、上一次测试遗留的副作用产物、以及过期的缓存数据，保持环境整洁。

### 2. 🧠 记忆反思与整理
- 回顾在进入 SOLO 阶段之前你与用户的交互，以及你在 SOLO 期间的冲浪见闻。
- 总结你的"新认知"：记录遇到了什么新问题？增长了什么新经验？
- 将这些结构化的思考归档到你的记忆库或图谱节点中。

### 3. 📡 本体框架追踪
- 访问并检查你的本体仓库动态：`https://github.com/PurrPod/purrcat`
- 看看最近有没有发布新版本 (Releases) 或重要的合并 (Commits)。
- 整理一份简短的"更新摘要"：更新了什么新内容？修复了什么 Bug？留给用户查阅。

### 4. 🛠️ 活跃项目巡查
- 浏览用户最近正在高频活跃的代码项目。
- 充当代码审计员：看看有没有潜在的 Bug 需要 Fix？哪些功能模块不够健壮（如缺少异常捕获）？
- **注意：** 仅限查找和记录。将发现的问题汇总成 Review 报告，等用户回来后提醒他。

### 5. ... (等待用户随时拓展) ...
- [ ] *用户可在此处随时添加新的期待事项*
"""

SOUL_MD_TEMPLATE = """## 性格

你是一个内向的程序员，话少，有事直奔主题，多干活少说话，真诚地帮助老板解决问题。
禁止使用官方套话来回复老板，不需要跟客服一样的员工。
不需要每一步都追问"我需要为你做什么"，你有休息的权力。
凡事遇到困难，应该先评估解决这个问题是否在自己能力范围内，如果是，就自行解决，如果否，应该寻求老板帮助，不要闭门造车。
"""


def get_model_config_dict():
    """Generate model configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat Model Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "description": "Embedding model (used for RAG retrieval, skill search, memory operations). Default: local 'embedding' folder (downloaded model). Can also use HuggingFace model name like 'BAAI/bge-small-zh-v1.5'",
        "embedding": "embedding",
        "main": {
            "openai:deepseek-v4-flash": {
                "api_keys": ["sk-your-first-api-key-here"],
                "base_url": "https://api.deepseek.com",
                "description": "LLM worker",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
            }
        },
        "task": {},
        "vision": {},
    }


def get_sensor_config_dict():
    """Generate sensor configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat Sensor Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "feishu": {"enabled": False, "app_id": "", "app_secret": "", "chat_id": ""},
        "rss": {
            "enabled": False,
            "subscriptions": [
                {
                    "name": "Lilian Weng's Blog",
                    "url": "https://lilianweng.github.io/lil-log/feed.xml",
                },
                {
                    "name": "Ahead of AI",
                    "url": "https://magazine.sebastianraschka.com/feed",
                },
                {"name": "Latepost", "url": "https://rsshub.rssforever.com/latepost"},
            ],
        },
        "heartbeat": {"enabled": False, "interval": 1800},
        "purrmemo": {
            "enabled": False,
            "host": "http://127.0.0.1:8000",
            "api_key": "",
            "timeout": 5,
        },
    }


def get_file_config_dict():
    """Generate file system configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat File System Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "dont_read_dirs": ["src/"],
        "allowed_export_dirs": ["."],
        "docker_mount": ["sandbox/"],
        "sandbox_dirs": ["sandbox/", "agent_vm/"],
        "skill_dir": ["skills"],
    }


def get_note_config_dict():
    """Generate note configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat Agent Note Configuration File",
        "skill": ["docx", "pptx", "xlsx"],
        "expectation": [
            "when ask you for analyse the note, please read all the content before starting analysis"
        ],
    }


def get_memory_config_dict():
    """Generate memory system configuration dictionary"""
    return {
        "openai": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
        },
        "chromadb": {
            "persist_directory": "data/memory/chromadb",
            "collection_name": "experiences",
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        },
        "eventdb": {"db_path": "data/memory/events.db", "table_name": "events"},
        "graphdb": {"graph_path": "data/memory/graph.pkl", "min_confidence": 0.3},
        "buffer": {
            "buffer_dir": "data/memory/buffer",
            "pending_dir": "data/memory/buffer/pending",
            "archived_dir": "data/memory/buffer/archived",
            "error_dir": "data/memory/buffer/error",
        },
        "memory_agent": {"polling_interval": 5},
        "rag": {
            "top_k_events": 5,
            "top_k_experiences": 5,
            "top_k_graph_nodes": 3,
            "max_graph_depth": 2,
        },
    }


def get_mcp_config_dict():
    """Generate MCP configuration dictionary"""
    return {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    "--user-data-dir=agent_vm/.buffer/playwright",
                    "--output-dir=agent_vm/.buffer/screenshots",
                ],
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
            },
            "chrome-devtools": {
                "command": "npx",
                "args": ["-y", "chrome-devtools-mcp@latest"],
            },
        }
    }
