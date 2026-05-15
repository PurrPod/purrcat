"""Templates for PurrCat configuration files"""

from datetime import datetime

CRON_CONFIG_TEMPLATE = """[
  {
    "id": "crn_cdbcc1d4",
    "title": "test-persist",
    "trigger_time": "07:30",
    "repeat_rule": "weekly_1",
    "active": true
  },
  {
    "id": "crn_7b9042b7",
    "title": "work-start",
    "trigger_time": "09:00",
    "repeat_rule": "weekly_1",
    "active": true
  },
  {
    "id": "crn_43cfdb8f",
    "title": "lunch",
    "trigger_time": "12:00",
    "repeat_rule": "everyday",
    "active": true
  },
  {
    "id": "crn_b196534b",
    "title": "meeting",
    "trigger_time": "15:00",
    "repeat_rule": "everyday",
    "active": true
  },
  {
    "id": "crn_e332b097",
    "title": "friday-drink",
    "trigger_time": "18:00",
    "repeat_rule": "weekly_5",
    "active": true
  }
]
"""

MEMEORY_MD_TEMPLATE = """# PurrCat Memory Notes

## Memory System

This file is used to record and manage the agent's memory information.

### Memory Types
- **Short-term Memory**: Session history, recent interactions
- **Long-term Memory**: Experience summaries, knowledge graphs
- **Event Memory**: Important event records
"""

SOLO_MD_TEMPLATE = """# PurrCat Solo Mode

## Solo Mode Configuration

This file is used to configure the agent's behavior in standalone mode.

### Runtime Parameters
- Working directory settings
- Task queue management
- Resource limitation configuration
"""

SOUL_MD_TEMPLATE = """# PurrCat Soul

## Core Identity

This file represents the agent's core identity and personality settings.

### Identity Characteristics
- Role positioning
- Language style
- Behavioral guidelines
"""

TODO_MD_TEMPLATE = """# PurrCat TODO

## Task Checklist

- [ ] Complete initialization configuration
- [ ] Set up API Key
- [ ] Configure sensors
- [ ] Start agent service
"""


def get_model_config_dict():
    """Generate model configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat Model Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "description": "Embedding model (used for RAG retrieval, skill search, memory operations). Default: local 'embedding' folder (downloaded model). Can also use HuggingFace model name like 'BAAI/bge-small-zh-v1.5'",
        "embedding": "embedding",
        "main": {
            "openai:deepseek-v4-flash": {
                "api_keys": ["sk-your-first-api-key-here"],
                "base_url": "https://api.deepseek.com",
                "description": "LLM worker",
                "rpm": 60,
                "tpm": 1000000,
                "concurrency": 3,
                "max_token": 500000,
            }
        },
        "task": {},
    }


def get_sensor_config_dict():
    """Generate sensor configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat Sensor Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "feishu": {"enabled": False, "app_id": "", "app_secret": "", "chat_id": ""},
        "rss": {
            "enabled": False,
            "subscriptions": [
                {
                    "name": "Lilian Weng's Blog",
                    "url": "https://lilianweng.github.io/lil-log/feed.xml",
                },
                {
                    "name": "Ahead of AI",
                    "url": "https://magazine.sebastianraschka.com/feed",
                },
                {"name": "Latepost", "url": "https://rsshub.rssforever.com/latepost"},
            ],
        },
        "heartbeat": {"enabled": False, "interval": 1800},
        "purrmemo": {
            "enabled": False,
            "host": "http://127.0.0.1:8000",
            "api_key": "",
            "timeout": 5,
        },
    }


def get_file_config_dict():
    """Generate file system configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"PurrCat File System Configuration File - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "dont_read_dirs": ["src/"],
        "allowed_export_dirs": ["."],
        "docker_mount": ["sandbox/"],
        "sandbox_dirs": ["sandbox/", "agent_vm/"],
        "skill_dir": ["skills"],
    }


def get_note_config_dict():
    """Generate note configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat Agent Note Configuration File",
        "skill": ["docx", "pptx", "xlsx"],
        "expectation": [
            "when ask you for analyse the note, please read all the content before starting analysis"
        ],
    }


def get_memory_config_dict():
    """Generate memory system configuration dictionary"""
    return {
        "openai": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
        },
        "chromadb": {
            "persist_directory": "data/memory/chromadb",
            "collection_name": "experiences",
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        },
        "eventdb": {"db_path": "data/memory/events.db", "table_name": "events"},
        "graphdb": {"graph_path": "data/memory/graph.pkl", "min_confidence": 0.3},
        "buffer": {
            "buffer_dir": "data/memory/buffer",
            "pending_dir": "data/memory/buffer/pending",
            "archived_dir": "data/memory/buffer/archived",
            "error_dir": "data/memory/buffer/error",
        },
        "memory_agent": {"polling_interval": 5},
        "rag": {
            "top_k_events": 5,
            "top_k_experiences": 5,
            "top_k_graph_nodes": 3,
            "max_graph_depth": 2,
        },
    }


def get_mcp_config_dict():
    """Generate MCP configuration dictionary"""
    return {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    "--user-data-dir=agent_vm/.buffer/playwright",
                    "--output-dir=agent_vm/.buffer/screenshots",
                ],
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
            },
            "chrome-devtools": {
                "command": "npx",
                "args": ["-y", "chrome-devtools-mcp@latest"],
            },
        }
    }
