import json
import os
from typing import Any, Dict

# ── 路径常量 ──
# 使用文件绝对路径确定项目根目录，不受启动位置影响
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
SRC_DIR = os.path.join(BASE_DIR, "src")

PURRCAT_DIR = os.path.join(BASE_DIR, ".purrcat")
MODEL_CONFIG_PATH = os.path.join(PURRCAT_DIR, "model.json")
SENSOR_CONFIG_PATH = os.path.join(PURRCAT_DIR, "sensor.json")
FILE_CONFIG_PATH = os.path.join(PURRCAT_DIR, "file.json")
MEMORY_CONFIG_PATH = os.path.join(PURRCAT_DIR, "memory.json")
MCP_CONFIG_PATH = os.path.join(PURRCAT_DIR, "mcp_config.json")

MEMORY_DIR = os.path.join(DATA_DIR, "memory")
TRACKER_DIR = os.path.join(DATA_DIR, "tracker")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
BUFFER_DIR = os.path.join(BASE_DIR, "agent_vm", ".buffer")
MEMORY_PENDING_DIR = os.path.join(MEMORY_DIR, "buffer", "pending")
SKILL_DIR = os.path.join(BASE_DIR, "skills")

SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")

AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(PURRCAT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_CORE_DIR, "SOUL.md")
CRON_FILE = os.path.join(AGENT_CORE_DIR, "cron.json")
SYSTEM_RULES_DIR = os.path.join(AGENT_DIR, "system_rules")

# 会话管理路径配置
SESSIONS_DIR = os.path.join(DATA_DIR, "checkpoints", "agent")
SESSION_INDEX_PATH = os.path.join(SESSIONS_DIR, "index.json")

# 确保会话目录在启动时存在
os.makedirs(SESSIONS_DIR, exist_ok=True)

MCP_SCHEMA_CACHE_FILE = os.path.join(SRC_DIR, "tool", "callmcp", "mcp_schema.json")


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
        return _load_json_file(MODEL_CONFIG_PATH)
    return {}


def get_sensor_config() -> Dict[str, Any]:
    if os.path.exists(SENSOR_CONFIG_PATH):
        return _load_json_file(SENSOR_CONFIG_PATH)
    return {}


def get_file_config() -> Dict[str, Any]:
    if os.path.exists(FILE_CONFIG_PATH):
        return _load_json_file(FILE_CONFIG_PATH)
    return {}


def get_mcp_config() -> Dict[str, Any]:
    if os.path.exists(MCP_CONFIG_PATH):
        return _load_json_file(MCP_CONFIG_PATH)
    return {}


def get_memory_config() -> Dict[str, Any]:
    if os.path.exists(MEMORY_CONFIG_PATH):
        return _load_json_file(MEMORY_CONFIG_PATH)
    return {}


def get_agent_model() -> str:
    model_config = get_model_config()
    main = model_config.get("main", {})
    if isinstance(main, dict) and main:
        return next(iter(main.keys()))
    return "openai:deepseek-v4-flash"


def get_embedding_model() -> str:
    """Get the embedding model path. Uses local 'embedding' folder by default."""
    model_config = get_model_config()
    # Return configured embedding model, or default to local 'embedding' folder
    return model_config.get("embedding", os.path.join(BASE_DIR, "embedding"))


def get_data_dir() -> str:
    return DATA_DIR
