"""PurrCat CLI - Handles complex configuration initialization (init/env)"""
import sys
import os
import json
import argparse
from datetime import datetime

def _generate_model_config_dict():
    """Generate model configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat Model Configuration File - Generated at {timestamp}",
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
                "max_token": 500000
            }
        },
        "task": {}
    }

def _generate_sensor_config_dict():
    """Generate sensor configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat Sensor Configuration File - Generated at {timestamp}",
        "feishu": {
            "enabled": False,
            "app_id": "",
            "app_secret": "",
            "chat_id": ""
        },
        "rss": {
            "enabled": False,
            "subscriptions": [
                {"name": "Lilian Weng's Blog", "url": "https://lilianweng.github.io/lil-log/feed.xml"},
                {"name": "Ahead of AI", "url": "https://magazine.sebastianraschka.com/feed"},
                {"name": "Latepost", "url": "https://rsshub.rssforever.com/latepost"}
            ]
        },
        "heartbeat": {
            "enabled": False,
            "interval": 1800
        },
        "purrmemo": {
            "enabled": False,
            "host": "http://127.0.0.1:8000",
            "api_key": "",
            "timeout": 5
        }
    }

def _generate_file_config_dict():
    """Generate file system configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat File System Configuration File - Generated at {timestamp}",
        "dont_read_dirs": ["src/"],
        "allowed_export_dirs": ["."],
        "docker_mount": ["sandbox/"],
        "sandbox_dirs": ["sandbox/", "agent_vm/"],
        "skill_dir": ["skill"]
    }


def _prompt_overwrite(file_path, force):
    """Prompt user for overwrite confirmation. Returns True if should overwrite."""
    if force:
        return True
    print(f"! File already exists: {file_path}")
    val = input("  Overwrite? (y/N): ").strip().lower()
    if val == "y":
        return True
    print("  [-] Skipped")
    return False


def _generate_memory_config(purrcat_dir, force=False):
    """Generate memory system configuration file"""
    memory_path = os.path.join(purrcat_dir, "memory.json")

    if os.path.exists(memory_path) and not _prompt_overwrite(memory_path, force):
        return False

    memory_config = {
        "openai": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash"
        },
        "chromadb": {
            "persist_directory": "data/memory/chromadb",
            "collection_name": "experiences",
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        },
        "eventdb": {
            "db_path": "data/memory/events.db",
            "table_name": "events"
        },
        "graphdb": {
            "graph_path": "data/memory/graph.pkl",
            "min_confidence": 0.3
        },
        "buffer": {
            "buffer_dir": "data/memory/buffer",
            "pending_dir": "data/memory/buffer/pending",
            "archived_dir": "data/memory/buffer/archived",
            "error_dir": "data/memory/buffer/error"
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
    }

    try:
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(memory_config, f, indent=2, ensure_ascii=False)
        print(f"[+] memory.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write memory.json: {e}")
        return False


def _generate_mcp_config(purrcat_dir, force=False):
    """Generate MCP configuration file"""
    mcp_path = os.path.join(purrcat_dir, "mcp_config.json")

    if os.path.exists(mcp_path) and not _prompt_overwrite(mcp_path, force):
        return False

    mcp_config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    "--user-data-dir=agent_vm/.buffer/playwright",
                    "--output-dir=agent_vm/.buffer/screenshots"
                ],
            },
            "github": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-github"
                ],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": ""
                }
            },
            "chrome-devtools": {
                "command": "npx",
                "args": ["-y", "chrome-devtools-mcp@latest"]
            }
        }
    }

    try:
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2, ensure_ascii=False)
        print(f"[+] mcp_config.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write mcp_config.json: {e}")
        return False


def _generate_note_config_dict():
    """Generate note configuration dictionary"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "PurrCat Agent Note Configuration File",
        "skill": ["docx", "pptx", "xlsx"],
        "expectation": ["when ask you for analyse the note, please read all the content before starting analysis"]
    }

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


def _generate_note_config(purrcat_dir, force=False):
    """Generate agent note configuration file"""
    agent_dir = os.path.join(purrcat_dir, "agent")
    os.makedirs(agent_dir, exist_ok=True)
    
    note_path = os.path.join(agent_dir, "note.json")

    if os.path.exists(note_path) and not _prompt_overwrite(note_path, force):
        return False

    note_config = _generate_note_config_dict()
    try:
        with open(note_path, "w", encoding="utf-8") as f:
            json.dump(note_config, f, indent=2, ensure_ascii=False)
        print(f"[+] agent/note.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write agent/note.json: {e}")
        return False


def _generate_core_files(purrcat_dir, force=False):
    """Generate core directory files"""
    core_dir = os.path.join(purrcat_dir, "core")
    os.makedirs(core_dir, exist_ok=True)

    results = []

    # cron.json
    cron_path = os.path.join(core_dir, "cron.json")
    if os.path.exists(cron_path) and not _prompt_overwrite(cron_path, force):
        results.append(("cron.json", False))
    else:
        try:
            with open(cron_path, "w", encoding="utf-8") as f:
                f.write(CRON_CONFIG_TEMPLATE)
            print(f"[+] core/cron.json generated")
            results.append(("cron.json", True))
        except Exception as e:
            print(f"X Failed to write core/cron.json: {e}")
            results.append(("cron.json", False))

    # MEMORY.md
    memory_md_path = os.path.join(core_dir, "MEMORY.md")
    if os.path.exists(memory_md_path) and not _prompt_overwrite(memory_md_path, force):
        results.append(("MEMORY.md", False))
    else:
        try:
            with open(memory_md_path, "w", encoding="utf-8") as f:
                f.write(MEMEORY_MD_TEMPLATE)
            print(f"[+] core/MEMORY.md generated")
            results.append(("MEMORY.md", True))
        except Exception as e:
            print(f"X Failed to write core/MEMORY.md: {e}")
            results.append(("MEMORY.md", False))

    # SOLO.md
    solo_md_path = os.path.join(core_dir, "SOLO.md")
    if os.path.exists(solo_md_path) and not _prompt_overwrite(solo_md_path, force):
        results.append(("SOLO.md", False))
    else:
        try:
            with open(solo_md_path, "w", encoding="utf-8") as f:
                f.write(SOLO_MD_TEMPLATE)
            print(f"[+] core/SOLO.md generated")
            results.append(("SOLO.md", True))
        except Exception as e:
            print(f"X Failed to write core/SOLO.md: {e}")
            results.append(("SOLO.md", False))

    # SOUL.md
    soul_md_path = os.path.join(core_dir, "SOUL.md")
    if os.path.exists(soul_md_path) and not _prompt_overwrite(soul_md_path, force):
        results.append(("SOUL.md", False))
    else:
        try:
            with open(soul_md_path, "w", encoding="utf-8") as f:
                f.write(SOUL_MD_TEMPLATE)
            print(f"[+] core/SOUL.md generated")
            results.append(("SOUL.md", True))
        except Exception as e:
            print(f"X Failed to write core/SOUL.md: {e}")
            results.append(("SOUL.md", False))

    # TODO.md
    todo_md_path = os.path.join(core_dir, "TODO.md")
    if os.path.exists(todo_md_path) and not _prompt_overwrite(todo_md_path, force):
        results.append(("TODO.md", False))
    else:
        try:
            with open(todo_md_path, "w", encoding="utf-8") as f:
                f.write(TODO_MD_TEMPLATE)
            print(f"[+] core/TODO.md generated")
            results.append(("TODO.md", True))
        except Exception as e:
            print(f"X Failed to write core/TODO.md: {e}")
            results.append(("TODO.md", False))

    return all(ok for _, ok in results)


def _generate_model_config(purrcat_dir, force=False):
    """Generate model configuration file"""
    model_path = os.path.join(purrcat_dir, "model.json")

    if os.path.exists(model_path) and not _prompt_overwrite(model_path, force):
        return False

    model_config = _generate_model_config_dict()
    model_config["$comment"] = model_config["$comment"].format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(model_config, f, indent=2, ensure_ascii=False)
        print(f"[+] model.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write model.json: {e}")
        return False


def _generate_sensor_config(purrcat_dir, force=False):
    """Generate sensor configuration file"""
    sensor_path = os.path.join(purrcat_dir, "sensor.json")

    if os.path.exists(sensor_path) and not _prompt_overwrite(sensor_path, force):
        return False

    sensor_config = _generate_sensor_config_dict()
    sensor_config["$comment"] = sensor_config["$comment"].format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(sensor_path, "w", encoding="utf-8") as f:
            json.dump(sensor_config, f, indent=2, ensure_ascii=False)
        print(f"[+] sensor.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write sensor.json: {e}")
        return False


def _generate_file_config(purrcat_dir, force=False):
    """Generate file system configuration file"""
    file_path = os.path.join(purrcat_dir, "file.json")

    if os.path.exists(file_path) and not _prompt_overwrite(file_path, force):
        return False

    file_config = _generate_file_config_dict()
    file_config["$comment"] = file_config["$comment"].format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(file_config, f, indent=2, ensure_ascii=False)
        print(f"[+] file.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write file.json: {e}")
        return False


def cmd_help():
    """Print help menu"""
    print("PurrCat CLI - Cross-platform AI Agent Framework")
    print("==========================================")
    print("Usage: purrcat <command> [options]")
    print("")
    print("Commands:")
    print("  setup   - Initialize environment (Conda, Docker, Models)")
    print("  init    - Generate .purrcat config templates")
    print("  start   - Start PurrCat (append --headless for background run)")
    print("  env     - View environment variable reference")
    print("")
    print("Examples:")
    print("  purrcat setup")
    print("  purrcat init")
    print("  purrcat init --force    # Skip all prompts (CI/CD)")
    print("  purrcat start --headless")


def cmd_env():
    """Print environment variable reference"""
    print("""# PurrCat Environment Variable Reference
# Note: Current version does not support environment variable override
#       Please directly edit configuration files in .purrcat/ directory
#
# Examples:
#   # Edit model configuration
#   vim .purrcat/model.json
#
#   # Edit sensor configuration
#   vim .purrcat/sensor.json
#
#   # Edit MCP configuration
#   vim .purrcat/mcp_config.json
#
#   # Edit file system configuration
#   vim .purrcat/file.json
#
#   # Edit agent note configuration
#   vim .purrcat/agent/note.json
#""")


def cmd_init(force=False):
    """Generate .purrcat configuration directory"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    purrcat_dir = os.path.join(project_root, ".purrcat")

    if os.path.exists(purrcat_dir):
        if force:
            print(f"[*] Directory exists: {purrcat_dir} (force mode, overwriting)")
        else:
            print(f"[!] .purrcat directory already exists, continue initialization?")
            val = input("  All config files will be confirmed one by one (Y/N): ").strip().lower()
            if val != "y":
                print("  Cancelled")
                return
    else:
        try:
            os.makedirs(purrcat_dir, exist_ok=True)
            print(f"[+] Created config directory: {purrcat_dir}")
        except Exception as e:
            print(f"X Failed to create directory: {e}")
            sys.exit(1)

    print("")
    print("[*] Starting config file generation, please confirm each...")

    results = []
    results.append(("model", _generate_model_config(purrcat_dir, force=False)))
    results.append(("sensor", _generate_sensor_config(purrcat_dir, force=False)))
    results.append(("file", _generate_file_config(purrcat_dir, force=False)))
    results.append(("mcp", _generate_mcp_config(purrcat_dir, force=False)))
    results.append(("memory", _generate_memory_config(purrcat_dir, force=False)))
    results.append(("note", _generate_note_config(purrcat_dir, force=False)))
    results.append(("core", _generate_core_files(purrcat_dir, force=False)))

    print("")
    print("[*] Summary:")
    generated = sum(1 for _, ok in results if ok)
    skipped = sum(1 for _, ok in results if not ok)
    print(f"    Generated: {generated}")
    print(f"    Skipped: {skipped}")

    if generated > 0:
        print("")
        print("[*] Next steps:")
        print("    Edit .purrcat/model.json to add your API Key")
        print("    Edit .purrcat/memory.json to configure memory system")
        print("    Edit .purrcat/mcp_config.json to add MCP Token")
        print("    Then run: purrcat start")


def main():
    parser = argparse.ArgumentParser(
        prog="purrcat",
        description="PurrCat - AI Agent Framework Configuration Tool",
        add_help=False
    )
    parser.add_argument("command", nargs="?", default="help", choices=["init", "env", "help"])
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing files")
    parser.add_argument("--help", "-h", action="store_true", help="Show this help message")

    args, _ = parser.parse_known_args()

    if args.help or args.command == "help":
        cmd_help()
    elif args.command == "init":
        cmd_init(force=args.force)
    elif args.command == "env":
        cmd_env()


if __name__ == "__main__":
    main()
