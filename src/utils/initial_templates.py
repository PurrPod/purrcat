"""首启默认配置模板（纯常量与构造器，不触碰文件系统）。"""

# 默认 Agent Loop（PARADIGM.yaml）模板。
# 首次需要默认范式时（agent 读取或 paradigms 目录为空），由此模板在
# ~/.purrcat/paradigms/PARADIGM.yaml 生成后读取。
DEFAULT_PARADIGM_YAML = """name: "default"
description: "default system loop"
path: "agent_vm"
loop_end_max_retry: 3
hooks:
  on_build_system_prompt:
    - injection:
        content: "@RULES"
    - injection:
        content: "@INFO"
    - injection:
        content: "@SOUL"
    - injection:
        content: "@MEMORY"
    - memo_injection:
        type: "full"
        count: 10
    - injection:
        content: "@SYS"
  on_loop_start:
    - injection: 
        content: "如遇复杂任务，请先编排好主线路的执行计划，先规划TODO后执行"
  on_loop_epoch:
    - injection:
        delay: 5
        content: "[system regular hint]在执行任务前可使用 Search 工具和 Memo 工具搜索有无对应的能力与历史经验"
    - injection:
        interval: 10
        content: "[system regular hint]请随时按进度更新主路规划或与用户对齐需求，防止跑偏"
  on_loop_end:
    # only ALL check passed can exit the loop
    - tool_use_check:
        name: "Memo"
        parameter_check:
          - action: "add"
        failed_prompt: "检查到本轮对话你未调用 Memo 工具进行记忆总结，最好总结一下，让你的能力随记忆系统的丰富而增强，如无经验更新，可添加短期记忆以免会话切换时失忆"
"""

# ==========================================
# 默认配置模板
# ==========================================

CRON_CONFIG_TEMPLATE = """[
  {
    "id": "crn_cdbcc1d4",
    "title": "test-persist",
    "description": "",
    "trigger_time": "07:30",
    "repeat_rule": "weekly_1",
    "active": true,
    "task_hook": "Agent",
    "task_inputs": {}
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
