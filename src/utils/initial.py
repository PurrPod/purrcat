"""
PurrCat 首次启动自动初始化模块
检查 ~/.purrcat 是否存在，不存在则生成默认配置文件。
"""

import json
import os

from src.utils.config import (
    PURRCAT_DIR,
    AGENT_CORE_DIR,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    APP_CONFIG_PATH,
    CRON_FILE,
    HEARTBEAT_FILE,
    SOUL_MD_PATH,
    BASE_DIR,
    ACP_RELAY_PATH,
    get_acp_token,
)

# 默认 Agent Loop（PARADIGM.yaml）模板。
# 首次需要默认范式时（agent 读取或 paradigms 目录为空），由此模板在
# ~/.purrcat/paradigms/PARADIGM.yaml 生成后读取。
DEFAULT_PARADIGM_YAML = """name: "default"
description: "default system loop"
path: "agent_vm"
loop_end_max_retry: 3
trigger:
  - cron:
      time: "08:08"
      injection: "【Demo】闹钟响了"
  - cron:
      time: "12:00"
      injection: "【Demo】该吃饭了"
hooks:
  on_build_system_prompt:
    - file_operation: 
        path: "@RULES"
        action: "read"
    - file_operation:
        path: "@INFO"
        action: "read"
    - file_operation:
        path: "@SOUL"
        action: "read"
    - file_operation:
        path: "@MEMORY"
        action: "read"
    - memo_injection:
        type: "full"
        count: 10
    - file_operation:
        action: "read"
        path: "@SYS"
  on_loop_start:
    - injection: 
        content: "如遇复杂任务，请先编排好主线路的执行计划，先规划TODO后执行"
    - file_operation:
        action: "exist_check"
        path: "@RULES"
        failed_prompt: "检测到系统指导文件不存在"
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
  on_tool_calling:
    - tool_use_check:
        name: "ComputerUse"
        successed_prompt: "组件找不到时使用 Vision 顾问进行询问。浏览器相关操作可以用浏览器相关 MCP 工具，更加高效。"
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


def _get_model_config_dict():
    return {
        "main": {
            "openai:deepseek-v4-flash": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
            }
        },
        "task": {
            "openai:deepseek-v4-flash": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
            }
        },
        "vision": {
            "openai:deepseek-v4-flash-vision-exp": {
                "api_keys": [""],
                "base_url": "https://api.deepseek.com",
            }
        },
    }


def _get_sensor_config_dict():
    return {}


def _get_file_config_dict():
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


def _get_mcp_config_dict():
    return {"mcpServers": {}}


def _get_app_config_dict():
    return {
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

    # ACP 网关 token 预生成（幂等）：启动即落盘，编辑器 relay 冷启动即可读到，
    # 修掉"首个 /acp/rpc 请求才生成"导致的 relay 永久退出问题
    try:
        get_acp_token()
    except Exception as e:
        print(f"[!] ACP token 预生成失败: {e}")

    # ACP 转接脚本部署/刷新（幂等）：~/.purrcat/bin/acp_relay.py
    deploy_acp_relay()

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
# ACP 转接脚本部署
# ==========================================


def deploy_acp_relay(force: bool = False) -> bool:
    """把 ACP 转接脚本部署到 ~/.purrcat/bin/acp_relay.py。

    - 源：BASE_DIR/scripts/acp_relay.py（开发态=仓库；打包后=_internal/scripts）
    - 幂等：已部署且内容与内置源一致时跳过；force=True 或内容有变（升级）时覆盖
    - 编辑器配置指向该稳定路径，App 升级后自动刷新，用户侧配置永不失效
    """
    src = os.path.join(BASE_DIR, "scripts", "acp_relay.py")
    if not os.path.isfile(src):
        print(f"[!] ACP relay 内置源缺失: {src}")
        return False
    try:
        with open(src, "r", encoding="utf-8") as f:
            source = f.read()
        if not force and os.path.isfile(ACP_RELAY_PATH):
            with open(ACP_RELAY_PATH, "r", encoding="utf-8") as f:
                if f.read() == source:
                    return True  # 已是最新，无需动
        _write_text(ACP_RELAY_PATH, source)
        print(f"[+] ACP relay 已部署: {ACP_RELAY_PATH}")
        return True
    except Exception as e:
        print(f"[!] ACP relay 部署失败: {e}")
        return False


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
