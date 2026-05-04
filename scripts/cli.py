"""PurrCat CLI - Handles complex configuration initialization (init/env)"""
import sys
import os
import json
import argparse
from datetime import datetime

MODEL_CONFIG_TEMPLATE = """# ============================================
# PurrCat Model Configuration File
# Path: .purrcat/.model.yaml
# Generated: {timestamp}
# ============================================

# Embedding model (used for RAG retrieval)
embedding_model: BAAI/bge-small-zh-v1.5

# Main model configuration (code will automatically use the first one as agent_model)
main:
  openai:deepseek-v4-flash:
    api_keys:
      - sk-your-first-api-key-here
    base_url: https://api.deepseek.com
    description: LLM worker
    rpm: 60                # requests per minute limit
    tpm: 1000000           # tokens per minute limit
    concurrency: 3         # max concurrency
    max_token: 500000      # memory window token limit


# Task model configuration (at least one required for multi-agent collaboration,
# model can be the same as main, but cannot use the same API-Key)
task:
  # openai:deepseek-v4-flash:
  #   api_keys:
  #     - sk-your-task-api-key
  #     - sk-your-second-api-key-but-that-is-not-necessary
  #   base_url: https://api.deepseek.com
  #   description: Task Model
  #   rpm: 60
  #   tpm: 1000000
  #   concurrency: 3
  #   max_token: 500000
"""

SENSOR_CONFIG_TEMPLATE = """# ============================================
# PurrCat Sensor Configuration File
# Path: .purrcat/.sensor.yaml
# Generated: {timestamp}
# ============================================

# Feishu integration (optional)
feishu:
  enabled: false
  app_id: ""
  app_secret: ""
  chat_id: ""

# RSS subscriptions (optional)
rss:
  enabled: false
  subscriptions:
    - name: Lilian Weng's Blog
      url: https://lilianweng.github.io/lil-log/feed.xml
    - name: Ahead of AI
      url: https://magazine.sebastianraschka.com/feed
    - name: Latepost
      url: https://rsshub.rssforever.com/latepost

# Heartbeat sensor (optional)
heartbeat:
  enabled: false
  interval: 1800          # heartbeat interval (seconds)

# PurrMemo memory system (optional)
purrmemo:
  enabled: false
  host: http://127.0.0.1:8000
  api_key: ""
  timeout: 5
"""

FILE_CONFIG_TEMPLATE = """# ============================================
# PurrCat File System Configuration File
# Path: .purrcat/.file.yaml
# Generated: {timestamp}
# ============================================

# Directories prohibited from reading/importing
dont_read_dirs:
  - src/

# Directories allowed for export_file writing
allowed_export_dirs:
  - .

# Directories mounted to Docker sandbox
docker_mount:
  - sandbox/

# Sandbox directories
sandbox_dirs:
  - sandbox/
  - agent_vm/

# Skill directories
skill_dir:
  - skill
"""


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
    memory_path = os.path.join(purrcat_dir, ".memory.json")

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
        print(f"[+] .memory.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write .memory.json: {e}")
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


def _generate_model_config(purrcat_dir, force=False):
    """Generate model configuration file"""
    model_path = os.path.join(purrcat_dir, ".model.yaml")

    if os.path.exists(model_path) and not _prompt_overwrite(model_path, force):
        return False

    content = MODEL_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(model_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] .model.yaml generated")
        return True
    except Exception as e:
        print(f"X Failed to write .model.yaml: {e}")
        return False


def _generate_sensor_config(purrcat_dir, force=False):
    """Generate sensor configuration file"""
    sensor_path = os.path.join(purrcat_dir, ".sensor.yaml")

    if os.path.exists(sensor_path) and not _prompt_overwrite(sensor_path, force):
        return False

    content = SENSOR_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(sensor_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] .sensor.yaml generated")
        return True
    except Exception as e:
        print(f"X Failed to write .sensor.yaml: {e}")
        return False


def _generate_file_config(purrcat_dir, force=False):
    """Generate file system configuration file"""
    file_path = os.path.join(purrcat_dir, ".file.yaml")

    if os.path.exists(file_path) and not _prompt_overwrite(file_path, force):
        return False

    content = FILE_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] .file.yaml generated")
        return True
    except Exception as e:
        print(f"X Failed to write .file.yaml: {e}")
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
    print("[*] 开始生成配置文件，请逐个确认...")

    results = []
    results.append(("model", _generate_model_config(purrcat_dir, force=False)))
    results.append(("sensor", _generate_sensor_config(purrcat_dir, force=False)))
    results.append(("file", _generate_file_config(purrcat_dir, force=False)))
    results.append(("mcp", _generate_mcp_config(purrcat_dir, force=False)))
    results.append(("memory", _generate_memory_config(purrcat_dir, force=False)))

    print("")
    print("[*] Summary:")
    generated = sum(1 for _, ok in results if ok)
    skipped = sum(1 for _, ok in results if not ok)
    print(f"    Generated: {generated}")
    print(f"    Skipped: {skipped}")

    if generated > 0:
        print("")
        print("[*] Next steps:")
        print("    Edit .purrcat/.model.yaml to add your API Key")
        print("    Edit .purrcat/.memory.json to configure memory system")
        print("    Edit .purrcat/mcp_config.json to add MCP Token")
        print("    Then run: purrcat start")


def cmd_env():
    """Print environment variable reference"""
    print("""# PurrCat Environment Variable Reference
# Note: Current version does not support environment variable override
#       Please directly edit configuration files in .purrcat/ directory
#
# Examples:
#   # Edit model configuration
#   vim .purrcat/.model.yaml
#
#   # Edit sensor configuration
#   vim .purrcat/.sensor.yaml
#
#   # Edit MCP configuration
#   vim .purrcat/mcp_config.json
""")


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