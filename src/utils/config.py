import os
import json
from typing import Any, Dict

# ── 路径常量 ──
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
SRC_DIR = os.path.join(BASE_DIR, "src")

PURRCAT_DIR = os.path.join(BASE_DIR, ".purrcat")
MODEL_CONFIG_PATH = os.path.join(PURRCAT_DIR, ".model.yaml")
SENSOR_CONFIG_PATH = os.path.join(PURRCAT_DIR, ".sensor.yaml")
FILE_CONFIG_PATH = os.path.join(PURRCAT_DIR, ".file.yaml")
MCP_CONFIG_PATH = os.path.join(PURRCAT_DIR, "mcp_config.json")

MEMORY_DIR = os.path.join(DATA_DIR, "memory")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
BUFFER_DIR = os.path.join(BASE_DIR, "agent_vm", ".buffer")
SKILL_DIR = os.path.join(BASE_DIR, "skill")

SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")

AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(AGENT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_CORE_DIR, "SOUL.md")
CRON_FILE = os.path.join(AGENT_CORE_DIR, "cron.json")
SYSTEM_RULES_DIR = os.path.join(AGENT_DIR, "system_rules")
CHECKPOINT_PATH = os.path.join(AGENT_DIR, "checkpoint.json")

MCP_SCHEMA_CACHE_FILE = os.path.join(SRC_DIR, "tool", "callmcp", "mcp_schema.json")


def _load_yaml_file(file_path: str) -> dict:
    """加载 YAML 文件"""
    try:
        import yaml
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print(f"[Config] 需要安装 PyYAML 来加载 YAML 配置")
        return {}
    except Exception as e:
        print(f"[Config] 加载 YAML 文件失败 {file_path}: {e}")
        return {}


def _load_json_file(file_path: str) -> dict:
    """加载 JSON 文件"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] 加载 JSON 文件失败 {file_path}: {e}")
        return {}


# ── Getter 函数 ──

def get_model_config() -> Dict[str, Any]:
    if os.path.exists(MODEL_CONFIG_PATH):
        return _load_yaml_file(MODEL_CONFIG_PATH)
    return {}


def get_sensor_config() -> Dict[str, Any]:
    if os.path.exists(SENSOR_CONFIG_PATH):
        return _load_yaml_file(SENSOR_CONFIG_PATH)
    return {}


def get_file_config() -> Dict[str, Any]:
    if os.path.exists(FILE_CONFIG_PATH):
        return _load_yaml_file(FILE_CONFIG_PATH)
    return {}


def get_mcp_config() -> Dict[str, Any]:
    if os.path.exists(MCP_CONFIG_PATH):
        return _load_json_file(MCP_CONFIG_PATH)
    return {}


def get_agent_model() -> str:
    model_config = get_model_config()
    main = model_config.get("main", {})
    if isinstance(main, dict) and main:
        return next(iter(main.keys()))
    return "openai:deepseek-v4-flash"


def get_embedding_model() -> str:
    model_config = get_model_config()
    return model_config.get("embedding", "BAAI/bge-small-zh-v1.5")


def get_data_dir() -> str:
    return DATA_DIR
