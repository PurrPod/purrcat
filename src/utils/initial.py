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
    HEARTBEAT_FILE,
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

HEARTBEAT_CONFIG_TEMPLATE = """{
  "interval": 1800,
  "active": false
}
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
    """在 ~/.purrcat 下生成缺失的默认配置文件（幂等：逐文件检查，已有文件绝不覆盖）"""
    os.makedirs(PURRCAT_DIR, exist_ok=True)
    os.makedirs(AGENT_CORE_DIR, exist_ok=True)

    # JSON 配置文件
    if not os.path.exists(MODEL_CONFIG_PATH):
        _write_json(MODEL_CONFIG_PATH, _get_model_config_dict())
    if not os.path.exists(SENSOR_CONFIG_PATH):
        _write_json(SENSOR_CONFIG_PATH, _get_sensor_config_dict())
    if not os.path.exists(FILE_CONFIG_PATH):
        _write_json(FILE_CONFIG_PATH, _get_file_config_dict())
    if not os.path.exists(MCP_CONFIG_PATH):
        _write_json(MCP_CONFIG_PATH, _get_mcp_config_dict())
    if not os.path.exists(APP_CONFIG_PATH):
        _write_json(APP_CONFIG_PATH, _get_app_config_dict())

    # core/ 目录文件
    if not os.path.exists(os.path.join(AGENT_CORE_DIR, "info.json")):
        _write_json(
            os.path.join(AGENT_CORE_DIR, "info.json"), {"skills": [], "workshops": []}
        )
    if not os.path.exists(CRON_FILE):
        _write_text(CRON_FILE, CRON_CONFIG_TEMPLATE)
    if not os.path.exists(HEARTBEAT_FILE):
        _write_text(HEARTBEAT_FILE, HEARTBEAT_CONFIG_TEMPLATE)
    if not os.path.exists(os.path.join(AGENT_CORE_DIR, "MEMORY.md")):
        _write_text(os.path.join(AGENT_CORE_DIR, "MEMORY.md"), MEMORY_MD_TEMPLATE)
    if not os.path.exists(SOUL_MD_PATH):
        _write_text(SOUL_MD_PATH, SOUL_MD_TEMPLATE)

    print(f"[+] 配置目录已就绪: {PURRCAT_DIR}")


# ==========================================
# 对外入口
# ==========================================


def ensure_initialized():
    """确保 ~/.purrcat 及全部默认配置就绪（幂等：逐文件补缺，绝不覆盖用户已有配置）

    注意：必须在所有业务模块 import 之前调用。import 链上存在模块级副作用
    （如 usage_tracer 实例化时会创建 ~/.purrcat 子目录），若目录先被创建，
    这里不能再以"目录是否存在"作为跳过依据，否则模板永远不会生成。
    """
    first_run = not os.path.exists(PURRCAT_DIR)
    if first_run:
        print("[*] 首次运行，正在自动初始化 ~/.purrcat 配置目录...")
    _generate_all_configs()
    if first_run:
        print(f"[*] 请编辑 {MODEL_CONFIG_PATH} 填入你的 Agent 模型和 API Key")
        print("")
