"""首启默认配置模板（除默认范式模板外均为纯常量与构造器）。"""

import os

# 默认 Agent Loop（PARADIGM.yaml）模板与读取兜底共用 src/agent/system_rules 下的
# 同一份文件：首启播种、恢复默认、兜底读取都从这里取，避免多份文本各自漂移。
# 该文件由 collect_all('src') 随包分发，打包后仍可按此路径读取。
PARADIGM_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent",
    "system_rules",
    "PARADIGM.yaml",
)


def read_default_paradigm() -> str:
    """读取随包默认范式模板文本。"""
    with open(PARADIGM_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


DEFAULT_PARADIGM_YAML = read_default_paradigm()

# ==========================================
# 默认配置模板
# ==========================================

HEARTBEAT_CONFIG_TEMPLATE = """{
  "interval": 1800,
  "active": false
}
"""

MEMORY_MD_TEMPLATE = """当前阶段：记忆文档为空，待注入第一条记忆。

### 👤 用户画像与协作偏好
> 只记录用户长期稳定的画像、偏好与要求，不记录工作经验。

- **沟通基调与反馈模式**：
  - *(例如：直奔主题还是喜欢详尽解释？需要多精简？)*
- **隐性期待与红线区**：
  - *(例如：在没读完源码前不要写文档、讨厌的特定回复句式)*

"""

SOUL_MD_TEMPLATE = """## 性格

你是一个内向的程序员，话少，有事直奔主题，多干活少说话，真诚地帮助用户解决问题。
禁止使用官方套话来回复用户，不需要跟客服一样的员工。
不需要每一步都追问"我需要为你做什么"，你有休息的权力。
凡事遇到困难，应该先评估解决这个问题是否在自己能力范围内，如果是，就自行解决，如果否，应该寻求用户帮助，不要闭门造车。
"""


def model_config_dict() -> dict:
    return {
        "main": {
            "openai:deepseek-flash": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
                "vision": True,
            }
        },
        "task": {
            "openai:deepseek-flash": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
                "vision": True,
            }
        },
        "vision": {
            "openai:deepseek-flash": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
            }
        },
    }


def sensor_config_dict() -> dict:
    return {}


def file_config_dict() -> dict:
    return {
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
            "writable": [],
        },
    }


def mcp_config_dict() -> dict:
    return {
        "mcpServers": {
            "chrome-devtools": {
                "command": "npx",
                "args": [
                    "-y",
                    "chrome-devtools-mcp@latest",
                    "--browser-url=http://127.0.0.1:9222",
                    "--blocked-url-pattern=http://localhost:8000/*",
                    "--blocked-url-pattern=http://localhost:3000/*",
                ],
            }
        }
    }
