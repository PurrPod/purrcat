import os
import json

# 找到项目根目录（从当前文件向上找）
def find_project_root():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while True:
        # 检查是否有 .purrcat 目录
        if os.path.exists(os.path.join(current_dir, ".purrcat")):
            return current_dir
        # 或者检查是否有 main.py, environment.yml 等标志性文件
        if (os.path.exists(os.path.join(current_dir, "main.py")) or
            os.path.exists(os.path.join(current_dir, "environment.yml")) or
            os.path.exists(os.path.join(current_dir, ".gitignore"))):
            return current_dir
        # 向上一级
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # 已经到了根目录
            return os.getcwd()
        current_dir = parent_dir

PROJECT_ROOT = find_project_root()
PURRCAT_DIR = os.path.join(PROJECT_ROOT, ".purrcat")

# 配置文件路径
CONFIG_FILE = os.path.join(PURRCAT_DIR, ".memory.json")

# 默认配置
default_config = {
    "openai": {
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-v4-flash"
    },
    "chromadb": {
        "persist_directory": os.path.join(PROJECT_ROOT, "data", "memo", "chromadb"),
        "collection_name": "experiences",
        "embedding_model": "BAAI/bge-small-zh-v1.5"
    },
    "eventdb": {
        "db_path": os.path.join(PROJECT_ROOT, "data", "memo", "events.db"),
        "table_name": "events"
    },
    "graphdb": {
        "graph_path": os.path.join(PROJECT_ROOT, "data", "memo", "graph.pkl"),
        "min_confidence": 0.3
    },
    "buffer": {
        "buffer_dir": os.path.join(PROJECT_ROOT, "data", "memo", "buffer"),
        "pending_dir": os.path.join(PROJECT_ROOT, "data", "memo", "buffer", "pending"),
        "archived_dir": os.path.join(PROJECT_ROOT, "data", "memo", "buffer", "archived"),
        "error_dir": os.path.join(PROJECT_ROOT, "data", "memo", "buffer", "error")
    },
    "memory_agent": {
        "checkpoint_path": os.path.join(PROJECT_ROOT, "data", "memo", "checkpoint.json"),
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

# 加载配置
config = default_config.copy()
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        user_config = json.load(f)
        # 递归更新配置
        def update_config(target, source):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    update_config(target[key], value)
                else:
                    target[key] = value
        update_config(config, user_config)

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
SERVER_CONFIG = config['server']
