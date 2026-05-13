import os
import json

# 导入统一的配置模块
from src.utils.config import get_memory_config, get_embedding_model, BASE_DIR

# 获取内存配置
config = get_memory_config()

# 默认配置（当配置文件不存在时使用）
default_config = {
    "openai": {
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-v4-flash"
    },
    "chromadb": {
        "persist_directory": os.path.join(BASE_DIR, "data", "memory", "chromadb"),
        "collection_name": "experiences",
        "embedding_model": get_embedding_model()
    },
    "eventdb": {
        "db_path": os.path.join(BASE_DIR, "data", "memory", "events.db"),
        "table_name": "events"
    },
    "graphdb": {
        "graph_path": os.path.join(BASE_DIR, "data", "memory", "graph.pkl"),
        "min_confidence": 0.3
    },
    "buffer": {
        "buffer_dir": os.path.join(BASE_DIR, "data", "memory", "buffer"),
        "pending_dir": os.path.join(BASE_DIR, "data", "memory", "buffer", "pending"),
        "archived_dir": os.path.join(BASE_DIR, "data", "memory", "buffer", "archived"),
        "error_dir": os.path.join(BASE_DIR, "data", "memory", "buffer", "error")
    },
    "memory_agent": {
        "polling_interval": 5
    },
    "rag": {
        "top_k_events": 5,
        "top_k_experiences": 5,
        "top_k_graph_nodes": 3,
        "max_graph_depth": 2
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000
    }
}

# 合并用户配置和默认配置
def merge_config(default, user):
    result = default.copy()
    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value
    return result

config = merge_config(default_config, config)

# 工作目录配置
BUFFER_DIR = config['buffer']['buffer_dir']
PENDING_DIR = config['buffer']['pending_dir']
ARCHIVED_DIR = config['buffer']['archived_dir']
ERROR_DIR = config['buffer']['error_dir']

# 确保目录存在
os.makedirs(os.path.dirname(config['chromadb']['persist_directory']), exist_ok=True)
os.makedirs(os.path.dirname(config['eventdb']['db_path']), exist_ok=True)
os.makedirs(os.path.dirname(config['graphdb']['graph_path']), exist_ok=True)
os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs(ARCHIVED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)

# OpenAI API 配置
OPENAI_API_CONFIG = config['openai']

# 记忆代理配置
MEMORY_AGENT_CONFIG = config['memory_agent']

# 事件库配置（SQLite）
EVENT_DATABASE_CONFIG = config['eventdb']

# 向量库配置（Chroma）
VECTOR_DATABASE_CONFIG = config['chromadb']

# 图谱库配置（NetworkX）
GRAPH_DATABASE_CONFIG = config['graphdb']

# RAG 配置
RAG_CONFIG = config['rag']

# 服务器配置
SERVER_CONFIG = config.get('server', {'host': '127.0.0.1', 'port': 8000})
