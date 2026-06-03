import json
import os
from pathlib import Path
from typing import Any, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
SRC_DIR = os.path.join(BASE_DIR, "src")

PURRCAT_DIR = os.path.join(BASE_DIR, ".purrcat")
MODEL_CONFIG_PATH = os.path.join(PURRCAT_DIR, "model.json")
SENSOR_CONFIG_PATH = os.path.join(PURRCAT_DIR, "activate_sensor.json")
FILE_CONFIG_PATH = os.path.join(PURRCAT_DIR, "file.json")
MEMORY_CONFIG_PATH = os.path.join(PURRCAT_DIR, "memory.json")
MCP_CONFIG_PATH = os.path.join(PURRCAT_DIR, "mcp_config.json")

MEMORY_DIR = os.path.join(DATA_DIR, "memory")
TRACKER_DIR = os.path.join(DATA_DIR, "tracker")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
BUFFER_DIR = os.path.join(BASE_DIR, "agent_vm", ".buffer")
AGENT_VM_DIR = os.path.join(BASE_DIR, "agent_vm")
MEMORY_PENDING_DIR = os.path.join(MEMORY_DIR, "buffer", "pending")
SKILL_DIR = os.path.join(BASE_DIR, "skills")

SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")

AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(PURRCAT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_CORE_DIR, "SOUL.md")
CRON_FILE = os.path.join(AGENT_CORE_DIR, "cron.json")
SYSTEM_RULES_DIR = os.path.join(AGENT_DIR, "system_rules")

SESSIONS_DIR = os.path.join(DATA_DIR, "checkpoints", "agent")
SESSION_INDEX_PATH = os.path.join(SESSIONS_DIR, "index.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)

MCP_SCHEMA_CACHE_FILE = os.path.join(SRC_DIR, "tool", "callmcp", "mcp_schema.json")

CONTAINER_ENGINE_CONFIG_KEY = "container_engine"

GLOBAL_CONFIG_DIR = Path.home() / ".purrcat"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "settings.json"


def _load_json_file(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] 加载 JSON 文件失败 {file_path}: {e}")
        return {}


def _save_json_file(file_path: str, data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] 保存 JSON 文件失败 {file_path}: {e}")
        return False


def get_global_settings() -> dict:
    if not GLOBAL_CONFIG_FILE.exists():
        return {}
    try:
        with open(GLOBAL_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_global_setting(key: str, value: Any) -> bool:
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_global_settings()
    settings[key] = value
    try:
        with open(GLOBAL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] 保存全局配置失败: {e}")
        return False


def get_engine_preference() -> str:
    return get_global_settings().get("sandbox_engine", "auto")


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
    model_config = get_model_config()
    return model_config.get("embedding", os.path.join(BASE_DIR, "embedding"))


def get_data_dir() -> str:
    return DATA_DIR


def get_container_engine(engine_preference: str = "auto") -> str:
    import shutil

    if engine_preference in ["docker", "podman"]:
        if shutil.which(engine_preference):
            return engine_preference
        else:
            raise EnvironmentError(
                f"您选择了 {engine_preference}，但系统未检测到该环境。"
            )

    global_preference = get_engine_preference()
    if global_preference in ["docker", "podman"]:
        if shutil.which(global_preference):
            return global_preference
        else:
            print(
                f"[Config] 全局配置中指定了 '{global_preference}'，但系统未检测到该命令。"
            )

    file_config = get_file_config()
    configured_engine = file_config.get(CONTAINER_ENGINE_CONFIG_KEY)

    if configured_engine:
        if shutil.which(configured_engine):
            return configured_engine
        else:
            print(
                f"[Config] 配置的容器引擎 '{configured_engine}' 未找到，尝试自动检测..."
            )

    if shutil.which("podman"):
        return "podman"
    elif shutil.which("docker"):
        return "docker"
    else:
        raise RuntimeError(
            "未检测到可用的容器引擎 (Podman 或 Docker)。请先安装其中之一。"
        )


def set_container_engine(engine: str) -> bool:
    if engine not in ["docker", "podman"]:
        print(f"[Config] 无效的容器引擎: {engine}")
        return False

    return save_global_setting("sandbox_engine", engine)
