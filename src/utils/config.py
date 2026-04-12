import os
import yaml
import json
from typing import Any, Dict, Optional

# 基础目录
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
SRC_DIR = os.path.join(BASE_DIR, "src")

# 配置目录
CONFIG_DIR = os.path.join(DATA_DIR, "config")
CONFIG_YAML_PATH = os.path.join(CONFIG_DIR, "config.yaml")

# 分级配置目录
SECRETS_DIR = os.path.join(CONFIG_DIR, "secrets")
CONFIGS_DIR = os.path.join(CONFIG_DIR, "configs")

# 数据目录
MEMORY_DIR = os.path.join(DATA_DIR, "memory")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
BUFFER_DIR = os.path.join(BASE_DIR, ".buffer")
SKILL_DIR = os.path.join(DATA_DIR, "skill")

# 调度文件路径
SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")
CRON_FILE = os.path.join(SCHEDULE_DIR, "cron.json")

# Agent 相关路径
AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(AGENT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_DIR, "SOUL.md")
CHECKPOINT_PATH = os.path.join(AGENT_DIR, "checkpoint.json")

# 插件相关路径
PLUGINS_DIR = os.path.join(SRC_DIR, "plugins")
PLUGIN_COLLECTION_DIR = os.path.join(PLUGINS_DIR, "plugin_collection")
TOOL_INDEX_FILE = os.path.join(PLUGINS_DIR, "tool.jsonl")
LOCAL_TOOL_YAML = os.path.join(PLUGIN_COLLECTION_DIR, "local_tool.yaml")

# 文件系统配置路径（保留，因为需要动态修改）
FILE_CONFIG_PATH = os.path.join(CONFIG_DIR, "file_config.json")
_config_cache: Optional[Dict[str, Any]] = None


def initialize_config() -> Dict[str, Any]:
    """初始化配置，从分级配置文件中整合到 config.yaml"""
    # 确保配置目录存在
    os.makedirs(SECRETS_DIR, exist_ok=True)
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    
    # 整合配置
    config = {}
    
    # 加载 secrets 目录下的配置文件
    for filename in os.listdir(SECRETS_DIR):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(SECRETS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    secret_config = yaml.safe_load(f)
                if secret_config:
                    config.update(secret_config)
            except Exception as e:
                print(f"[Config] 加载密钥配置文件 {filename} 失败: {e}")
    
    # 加载 configs 目录下的配置文件
    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(CONFIGS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    config_config = yaml.safe_load(f)
                if config_config:
                    config.update(config_config)
            except Exception as e:
                print(f"[Config] 加载配置文件 {filename} 失败: {e}")
    
    # 保存整合后的配置到 config.yaml
    save_config(config)
    return config


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    
    # 检查 config.yaml 是否存在，如果不存在则初始化
    if not os.path.exists(CONFIG_YAML_PATH):
        _config_cache = initialize_config()
        return _config_cache
    
    with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    
    # 确保返回的是字典
    if _config_cache is None:
        _config_cache = initialize_config()
    
    return _config_cache


def reload_config() -> Dict[str, Any]:
    """重新加载配置（清除缓存）"""
    global _config_cache
    _config_cache = None
    return load_config()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置到 config.yaml"""
    with open(CONFIG_YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    reload_config()


def get_models_config() -> Dict[str, Any]:
    """获取模型配置"""
    config = load_config()
    return config.get("models", {})


def get_agent_model() -> str:
    """获取 Agent 使用的默认模型"""
    config = load_config()
    return config.get("agent_model", "")


def get_specialized_model(model_type: str) -> Dict[str, str]:
    """
    获取专用模型配置
    model_type: image_generator, image_converter, video_generator, 
                audio_generator, audio_converter, video_converter
    """
    config = load_config()
    specialized = config.get("specialized_models", {})
    return specialized.get(model_type, {})


def get_embedding_model() -> str:
    """获取 Embedding 模型名称"""
    config = load_config()
    return config.get("embedding_model", "BAAI/bge-small-zh-v1.5")


def get_feishu_config() -> Dict[str, str]:
    """获取飞书配置"""
    config = load_config()
    return config.get("feishu", {})


def get_mcp_servers() -> Dict[str, Any]:
    """获取 MCP 服务器配置"""
    config = load_config()
    return config.get("mcp_servers", {})


def get_rss_subscriptions() -> list:
    """获取 RSS 订阅列表"""
    config = load_config()
    return config.get("rss_subscriptions", [])


def get_web_api_config() -> Dict[str, str]:
    """获取 Web API 配置"""
    config = load_config()
    return config.get("web_api", {})


def get_model_config_json() -> Dict[str, Any]:
    """
    将新的 config.yaml 格式转换为旧的 model_config.json 格式
    用于兼容现有代码
    """
    config = load_config()
    result = {
        "models": config.get("models", {}),
        "agent": config.get("agent_model", ""),
    }
    # 添加专用模型配置
    specialized = config.get("specialized_models", {})
    for key, value in specialized.items():
        result[key] = value
    # 添加 embedding_model
    result["embedding_model"] = config.get("embedding_model", "BAAI/bge-small-zh-v1.5")
    return result


def get_mcp_config_json() -> Dict[str, Any]:
    """
    将新的 config.yaml 格式转换为旧的 mcp_config.json 格式
    """
    config = load_config()
    return {
        "mcpServers": config.get("mcp_servers", {})
    }

def add_model_to_config(model_name: str, api_key: str, base_url: str, desc: str = "LLM") -> bool:
    """添加新模型到配置"""
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
    """从配置中删除模型"""
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
    """更新模型配置"""
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
