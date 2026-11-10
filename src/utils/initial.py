"""
PurrCat 首次启动自动初始化模块
检查 ~/.purrcat 是否存在，不存在则生成默认配置文件。

默认模板与配置字典在 initial_templates；本模块只负责落盘与幂等判断。
"""

import os

from src.utils import initial_templates
from src.utils._fs import write_json, write_text
from src.utils.config import (
    PURRCAT_DIR,
    AGENT_CORE_DIR,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    CRON_FILE,
    HEARTBEAT_FILE,
    SOUL_MD_PATH,
    BASE_DIR,
    ACP_RELAY_PATH,
    get_acp_token,
)
from src.utils.initial_templates import (
    CRON_CONFIG_TEMPLATE,
    DEFAULT_PARADIGM_YAML,
    HEARTBEAT_CONFIG_TEMPLATE,
    MEMORY_MD_TEMPLATE,
    SOUL_MD_TEMPLATE,
)

__all__ = [
    "CRON_CONFIG_TEMPLATE",
    "DEFAULT_PARADIGM_YAML",
    "deploy_acp_relay",
    "ensure_initialized",
]


# ==========================================
# 文件生成
# ==========================================


def _generate_all_configs():
    """在 ~/.purrcat 下生成缺失的默认配置文件（幂等：逐文件检查，已有文件绝不覆盖）"""
    os.makedirs(PURRCAT_DIR, exist_ok=True)
    os.makedirs(AGENT_CORE_DIR, exist_ok=True)

    # JSON 配置文件
    if not os.path.exists(MODEL_CONFIG_PATH):
        write_json(MODEL_CONFIG_PATH, initial_templates.model_config_dict())
    if not os.path.exists(SENSOR_CONFIG_PATH):
        write_json(SENSOR_CONFIG_PATH, initial_templates.sensor_config_dict())
    if not os.path.exists(FILE_CONFIG_PATH):
        write_json(FILE_CONFIG_PATH, initial_templates.file_config_dict())
    if not os.path.exists(MCP_CONFIG_PATH):
        write_json(MCP_CONFIG_PATH, initial_templates.mcp_config_dict())

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
        write_json(
            os.path.join(AGENT_CORE_DIR, "info.json"),
            {"skills": [], "workshops": []},
        )
    if not os.path.exists(CRON_FILE):
        write_text(CRON_FILE, CRON_CONFIG_TEMPLATE)
    if not os.path.exists(HEARTBEAT_FILE):
        write_text(HEARTBEAT_FILE, HEARTBEAT_CONFIG_TEMPLATE)
    if not os.path.exists(os.path.join(AGENT_CORE_DIR, "MEMORY.md")):
        write_text(os.path.join(AGENT_CORE_DIR, "MEMORY.md"), MEMORY_MD_TEMPLATE)
    if not os.path.exists(SOUL_MD_PATH):
        write_text(SOUL_MD_PATH, SOUL_MD_TEMPLATE)

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
        write_text(ACP_RELAY_PATH, source)
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
