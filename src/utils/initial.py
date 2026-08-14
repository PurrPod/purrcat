"""
PurrCat 首次启动自动初始化模块
检查 ~/.purrcat 是否存在，不存在则生成默认配置文件。
"""

import json
import os

from src.utils.config import (
    PURRCAT_DIR,
    AGENT_CORE_DIR,
    AGENT_VM_DIR,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    APP_CONFIG_PATH,
    CRON_FILE,
    LOOP_FILE,
    SOUL_MD_PATH,
)


# ==========================================
# 默认配置模板
# ==========================================

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

LOOP_CONFIG_TEMPLATE = """[
  {
    "id": "lp_default_heartbeat",
    "title": "系统心跳",
    "interval": 1800,
    "task_hook": "Agent",
    "task_inputs": {},
    "active": false
  }
]
"""

MEMORY_MD_TEMPLATE = """当前阶段：记忆文档为空，待注入第一条记忆。

### 👤 用户画像与协作偏好
> 记录用户的固有习惯、沟通偏好以及不可触碰的红线。
- **沟通基调与反馈模式**：
  - *(例如：直奔主题还是喜欢详尽解释？需要多精简？)*
- **隐性期待与红线区**：
  - *(例如：在没读完源码前不要写文档、讨厌的特定回复句式)*

#### 🧠 实战经验与高价值认知
> 记录在实际执行任务中"踩过的坑"、"总结出的最佳实践"和"非直觉的系统体感"。

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


def _get_model_config_dict():
    return {
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
        "task": {
            "openai:deepseek-v4-flash": {
                "api_keys": ["sk-your-task-api-key-here"],
                "base_url": "https://api.deepseek.com",
                "description": "Task Model",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
            }
        },
        "vision": {
            "qwen3.6-plus": {
                "api_keys": ["sk-your-vision-api-key-here"],
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            }
        },
    }


def _get_sensor_config_dict():
    from pathlib import Path

    return {
        "feishu_bot": {
            "enabled": False,
            "env": {"FEISHU_APP_ID": "", "FEISHU_APP_SECRET": "", "FEISHU_CHAT_ID": ""},
            "capabilities": {"observe": True, "express": True},
        },
        "system_clock": {
            "enabled": True,
            "env": {"CRON_FILE": str(Path.home() / ".purrcat" / "core" / "cron.json")},
            "capabilities": {"observe": True, "express": False},
        },
        "rss_watcher": {
            "enabled": False,
            "env": {
                "INTERVAL": "1800",
                "RSS_SUBSCRIPTIONS_JSON": '[{"name": "Lilian Weng\'s Blog", "rss_url": "https://lilianweng.github.io/lil-log/feed.xml"},{"name": "Ahead of AI", "rss_url": "https://magazine.sebastianraschka.com/feed"},{"name": "Latepost 晚点", "rss_url": "https://rsshub.rssforever.com/latepost"}]',
            },
            "capabilities": {"observe": True, "express": False},
        },
        "audio_assistant": {
            "enabled": False,
            "env": {
                "WHISPER_MODEL": "small",
                "LANGUAGE": "zh",
                "TTS_RATE": "150",
                "TTS_VOLUME": "1.0",
            },
            "capabilities": {"observe": True, "express": True},
        },
    }


def _get_file_config_dict():
    from datetime import datetime

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat File System Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "default_permission": "readonly",
        "permissions": {
            "blocked": [
                ".git",
                "src",
                "node_modules",
                "miniconda3",
                ".env",
            ],
            "readonly": [],
            "writable": [
                AGENT_VM_DIR,
                "./exports",
                "D:/test",
            ],
        },
    }


def _get_mcp_config_dict():
    return {
        "mcpServers": {
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


def _get_app_config_dict():
    return {
        "微信": "D:\\Path\\to\\WeChat.exe",
        "GitHub": "https://github.com",
    }


# ==========================================
# 文件生成函数
# ==========================================

def _write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_text(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _generate_all_configs():
    """在 ~/.purrcat 下生成全部默认配置文件（仅首次启动调用）"""
    os.makedirs(PURRCAT_DIR, exist_ok=True)
    os.makedirs(AGENT_CORE_DIR, exist_ok=True)

    # JSON 配置文件
    _write_json(MODEL_CONFIG_PATH, _get_model_config_dict())
    _write_json(SENSOR_CONFIG_PATH, _get_sensor_config_dict())
    _write_json(FILE_CONFIG_PATH, _get_file_config_dict())
    _write_json(MCP_CONFIG_PATH, _get_mcp_config_dict())
    _write_json(APP_CONFIG_PATH, _get_app_config_dict())

    # core/ 目录文件
    _write_json(os.path.join(AGENT_CORE_DIR, "info.json"), {"skills": [], "workshops": []})
    _write_text(CRON_FILE, CRON_CONFIG_TEMPLATE)
    _write_text(LOOP_FILE, LOOP_CONFIG_TEMPLATE)
    _write_text(os.path.join(AGENT_CORE_DIR, "MEMORY.md"), MEMORY_MD_TEMPLATE)
    _write_text(os.path.join(AGENT_CORE_DIR, "SOLO.md"), SOLO_MD_TEMPLATE)
    _write_text(SOUL_MD_PATH, SOUL_MD_TEMPLATE)

    print(f"[+] 配置目录已初始化: {PURRCAT_DIR}")


# ==========================================
# 对外入口
# ==========================================

def ensure_initialized():
    """检查 ~/.purrcat 是否存在，不存在则自动生成默认配置"""
    if not os.path.exists(PURRCAT_DIR):
        print("[*] 首次运行，正在自动初始化 ~/.purrcat 配置目录...")
        _generate_all_configs()
        print(f"[*] 请编辑 {MODEL_CONFIG_PATH} 填入你的 Agent 模型和 API Key")
        print("")
