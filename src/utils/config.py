import os
import json
from typing import Any, Dict, Optional

# ── 路径常量（保持兼容，其他模块引用它们） ──
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
SRC_DIR = os.path.join(BASE_DIR, "src")

CONFIG_DIR = os.path.join(DATA_DIR, "config")
CONFIG_YAML_PATH = os.path.join(CONFIG_DIR, "config.yaml")
SECRETS_DIR = os.path.join(CONFIG_DIR, "secrets")
CONFIGS_DIR = os.path.join(CONFIG_DIR, "configs")
MCP_CONFIG_PATH = os.path.join(BASE_DIR, "mcp_config.json")

MEMORY_DIR = os.path.join(DATA_DIR, "memory")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
BUFFER_DIR = os.path.join(BASE_DIR, ".buffer")
SKILL_DIR = os.path.join(DATA_DIR, "skill")

SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")
CRON_FILE = os.path.join(SCHEDULE_DIR, "cron.json")

AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(AGENT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_CORE_DIR, "SOUL.md")
SYSTEM_RULES_DIR = os.path.join(AGENT_DIR, "system_rules")
CHECKPOINT_PATH = os.path.join(AGENT_DIR, "checkpoint.json")

PLUGINS_DIR = os.path.join(SRC_DIR, "plugins")
PLUGIN_COLLECTION_DIR = os.path.join(PLUGINS_DIR, "plugin_collection")
TOOL_INDEX_FILE = os.path.join(PLUGINS_DIR, "tool.jsonl")
LOCAL_TOOL_YAML = os.path.join(PLUGIN_COLLECTION_DIR, "local_tool.yaml")

# 保留旧的 FILE_CONFIG_PATH 引用，但内容现在走 TOML
FILE_CONFIG_PATH = os.path.join(CONFIG_DIR, "file_config.json")

_config_cache: Optional[Dict[str, Any]] = None


# ── TOML 配置加载 ──

def _find_config_files() -> list:
    """按优先级返回配置文件路径列表"""
    files = []
    home_cfg = os.path.expanduser("~/.purrcat.toml")
    if os.path.exists(home_cfg):
        files.append(home_cfg)
    local_cfg = os.path.join(BASE_DIR, "purrcat.toml")
    if os.path.exists(local_cfg):
        files.append(local_cfg)
    return files


def _load_toml_files() -> dict:
    """加载所有 TOML 配置文件并合并（后面的覆盖前面的）"""
    import tomli
    config = {}
    for path in _find_config_files():
        try:
            with open(path, "rb") as f:
                data = tomli.load(f)
            _deep_merge(config, data)
        except Exception as e:
            print(f"[Config] 加载配置文件失败 {path}: {e}")
    return config


def _deep_merge(base: dict, override: dict) -> None:
    """深度合并字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(config: dict) -> None:
    """环境变量覆盖配置（PURR_xxx 格式）"""
    prefix = "PURR_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        parts = env_key[len(prefix):].lower().split("_")
        # 导航到配置位置
        target = config
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                target[part] = env_val
            else:
                if part not in target:
                    target[part] = {}
                target = target[part]


def _build_config() -> dict:
    """构建完整配置（TOML + 环境变量 + 默认值）"""
    config = _load_toml_files()

    # 扁平化为旧格式兼容
    flat = {}

    # [agent] 节
    agent_cfg = config.get("agent", {})
    flat["agent_model"] = agent_cfg.get("model", "openai:deepseek-v4-flash")
    flat["embedding_model"] = agent_cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5")

    # [models.*] 节 → 转换为旧格式的 models dict
    # TOML 中用引号保留原名: [models."openai:deepseek-v4-flash"]
    models = {}
    for model_key, model_val in config.get("models", {}).items():
        models[model_key] = {
            "api_keys": model_val.get("api_keys", []),
            "base_url": model_val.get("base_url", ""),
            "description": model_val.get("description", "LLM worker"),
            "limits": {
                "rpm": model_val.get("rpm", 60),
                "tpm": model_val.get("tpm", 1000000),
                "concurrency": model_val.get("concurrency", 3),
                "max_token": model_val.get("max_token", 500000),
            }
        }
    flat["models"] = models

    # [feishu] 节
    feishu = config.get("feishu", {})
    flat["feishu"] = {
        "app_id": feishu.get("app_id", ""),
        "app_secret": feishu.get("app_secret", ""),
        "chat_id": feishu.get("chat_id", ""),
    }

    # [web] 节
    web = config.get("web", {})
    flat["web_api"] = {"tavily_api_key": web.get("tavily_api_key", "")}

    # mcp_config.json → mcp_servers（单独的 JSON 文件，不混在 TOML 里）
    mcp_servers = {}
    try:
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                mcp_data = json.load(f)
            raw = mcp_data.get("mcpServers", mcp_data)
            for server_name, server_cfg in raw.items():
                entry = {
                    "command": server_cfg.get("command", ""),
                    "args": server_cfg.get("args", []),
                }
                if "idle_timeout" in server_cfg:
                    entry["idle_timeout"] = server_cfg["idle_timeout"]
                if "env" in server_cfg:
                    entry["env"] = server_cfg["env"]
                mcp_servers[server_name] = entry
    except Exception as e:
        print(f"[Config] 加载 mcp_config.json 失败: {e}")
    flat["mcp_servers"] = mcp_servers

    # [rss] 节
    rss = config.get("rss", {})
    flat["rss_subscriptions"] = rss.get("subscriptions", [])

    # [purrmemo] 节
    purrmemo = config.get("purrmemo", {})
    flat["purrmemo"] = {
        "enabled": purrmemo.get("enabled", False),
        "host": purrmemo.get("host", "http://127.0.0.1:8000"),
        "api_key": purrmemo.get("api_key", ""),
        "timeout": purrmemo.get("timeout", 5),
    }

    # [heartbeat] 节
    hb = config.get("heartbeat", {})
    flat["heartbeat"] = {
        "enabled": hb.get("enabled", False),
        "interval": hb.get("interval", 1800),
    }

    # [filesystem] 节（替代旧的 file_config.json）
    fs = config.get("filesystem", {})

    # [docker] 节
    docker_cfg = config.get("docker", {})
    flat["docker"] = {
        "http_proxy": docker_cfg.get("http_proxy", ""),
        "https_proxy": docker_cfg.get("https_proxy", ""),
        "all_proxy": docker_cfg.get("all_proxy", ""),
    }
    flat["filesystem"] = {
        "sandbox_dirs": fs.get("sandbox_dirs", ["sandbox/", "agent_vm/"]),
        "skill_dir": fs.get("skill_dir", ["data/skill"]),
        "dont_read_dirs": fs.get("dont_read_dirs", ["src/"]),
        "docker_mount": fs.get("docker_mount", ["sandbox/"]),
        "allowed_export_dirs": fs.get("allowed_export_dirs", [".", "agent_vm/"]),
    }

    # 环境变量覆盖
    _apply_env_overrides(flat)

    _config_cache = flat
    return flat


def initialize_config() -> Dict[str, Any]:
    """初始化配置（兼容旧调用方）"""
    global _config_cache
    _config_cache = _build_config()
    return _config_cache


def load_config() -> Dict[str, Any]:
    """加载配置（带缓存）"""
    global _config_cache
    if _config_cache is None:
        _config_cache = _build_config()
    return _config_cache


def reload_config() -> Dict[str, Any]:
    """重新加载配置"""
    global _config_cache
    _config_cache = _build_config()
    return _config_cache


def save_config(config: Dict[str, Any]) -> None:
    """保存配置（兼容旧调用方，实际写入 TOML 较复杂，更新缓存即可）"""
    global _config_cache
    _config_cache = config


# ── Getter 函数（保持接口不变） ──

def get_models_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("models", {})


def get_agent_model() -> str:
    config = load_config()
    return config.get("agent_model", "")


def get_model_limits(model_name: str) -> Dict[str, int]:
    config = load_config()
    models = config.get("models", {})
    model_cfg = models.get(model_name, {})
    return model_cfg.get("limits", {})


def get_specialized_model(model_type: str) -> Dict[str, str]:
    config = load_config()
    return config.get("specialized_models", {}).get(model_type, {})


def get_embedding_model() -> str:
    config = load_config()
    return config.get("embedding_model", "BAAI/bge-small-zh-v1.5")


def get_feishu_config() -> Dict[str, str]:
    config = load_config()
    return config.get("feishu", {})


def get_purrmemo_config() -> Dict[str, any]:
    config = load_config()
    return config.get("purrmemo", {"enabled": False, "host": "http://127.0.0.1:8000", "api_key": "", "timeout": 5})


def get_heartbeat_config() -> Dict[str, any]:
    config = load_config()
    return config.get("heartbeat", {"enabled": False, "interval": 1800})


def get_mcp_servers() -> Dict[str, Any]:
    config = load_config()
    return config.get("mcp_servers", {})


def get_rss_subscriptions() -> list:
    config = load_config()
    return config.get("rss_subscriptions", [])


def get_web_api_config() -> Dict[str, str]:
    config = load_config()
    return config.get("web_api", {})


def get_docker_config() -> Dict[str, str]:
    """获取 Docker 容器代理配置"""
    config = load_config()
    return config.get("docker", {
        "http_proxy": "http://host.docker.internal:7897",
        "https_proxy": "http://host.docker.internal:7897",
        "all_proxy": "socks5://host.docker.internal:7897",
    })


def get_filesystem_config() -> Dict[str, Any]:
    """获取文件系统安全配置（替代直接读 file_config.json）"""
    config = load_config()
    return config.get("filesystem", {
        "sandbox_dirs": ["sandbox/", "agent_vm/"],
        "skill_dir": ["data/skill"],
        "dont_read_dirs": ["src/"],
        "docker_mount": ["sandbox/"],
        "allowed_export_dirs": [".", "agent_vm/"],
    })


def get_model_config_json() -> Dict[str, Any]:
    config = load_config()
    result = {
        "models": config.get("models", {}),
        "agent": config.get("agent_model", ""),
    }
    specialized = config.get("specialized_models", {})
    for key, value in specialized.items():
        result[key] = value
    result["embedding_model"] = config.get("embedding_model", "BAAI/bge-small-zh-v1.5")
    return result


def get_mcp_config_json() -> Dict[str, Any]:
    config = load_config()
    return {"mcpServers": config.get("mcp_servers", {})}


def add_model_to_config(model_name: str, api_key: str, base_url: str, desc: str = "LLM") -> bool:
    try:
        config = load_config()
        if "models" not in config:
            config["models"] = {}
        config["models"][model_name] = {
            "api_key": api_key,
            "base_url": base_url,
            "description": desc
        }
        save_config(config)
        return True
    except Exception as e:
        print(f"[Config] 添加模型失败: {e}")
        return False


def remove_model_from_config(model_name: str) -> bool:
    try:
        config = load_config()
        if "models" in config and model_name in config["models"]:
            del config["models"][model_name]
            save_config(config)
            return True
        return False
    except Exception as e:
        print(f"[Config] 删除模型失败: {e}")
        return False


def update_model_in_config(model_name: str, **kwargs) -> bool:
    try:
        config = load_config()
        if "models" not in config or model_name not in config["models"]:
            return False
        config["models"][model_name].update(kwargs)
        save_config(config)
        return True
    except Exception as e:
        print(f"[Config] 更新模型失败: {e}")
        return False
