"""PurrCat CLI - 跨平台命令行入口"""
import sys, os, argparse
from datetime import datetime

CONFIG_TEMPLATE = """# ============================================
# PurrCat 配置文件
# 路径: ~/.purrcat.toml
# 生成: {timestamp}
# 完整参考: https://github.com/PurrPod/purrcat
#
# 路径说明：所有相对路径均相对于项目根目录
# ============================================

# ── Agent 基础配置 ──
[agent]
# 默认工作模型
model = "openai:deepseek-v4-flash"
# Embedding 模型（用于 RAG 检索）
embedding_model = "BAAI/bge-small-zh-v1.5"

# ── 模型配置 ──
# 每行一个模型，节名 = 模型名（点号分隔厂商和模型）
# 例如: [models."openai:deepseek-v4-flash"]
# 每个模型一个节，节名 = 完整模型名（引号保留冒号）
# 可添加多个模型实现多模型并发
[models."openai:deepseek-v4-flash"]
# API Key 列表（多个 key 自动负载均衡、自动故障转移）
api_keys = [
    "sk-your-first-api-key-here",
    # "sk-your-second-api-key-here",   # 取消注释即可启用第二个 key
]
# API 地址
base_url = "https://api.deepseek.com/v1"
description = "LLM worker"
# 限流参数（每个 key 独立限流）
rpm = 60                # 每分钟请求上限
tpm = 1000000           # 每分钟 Token 上限
concurrency = 3         # 最大并发数
max_token = 500000      # 记忆窗口 Token 上限

# 示例：添加第二个模型
# [models."openai:qwen3-vl-plus"]
# api_keys = ["sk-your-qwen-key"]
# base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# description = "LLM worker 2"
# rpm = 30
# tpm = 500000
# concurrency = 2
# max_token = 200000

# ── 飞书集成（可选） ──
[feishu]
app_id = ""
app_secret = ""
chat_id = ""

# ── 网络工具 ──
[web]
# Tavily Search API Key（申请: https://tavily.com）
tavily_api_key = ""


# ── 文件系统安全 ──
[filesystem]
# 禁止读取/导入的目录
dont_read_dirs = ["src/"]
# 允许 export_file 写入的目录
allowed_export_dirs = [".", "agent_vm/"]
# 挂载到 Docker 沙盒的目录
docker_mount = ["sandbox/", "."]

# ── RSS 订阅 ──
[rss]
subscriptions = [
    {{ name = "Lilian Weng's Blog", url = "https://lilianweng.github.io/lil-log/feed.xml" }},
    {{ name = "Ahead of AI", url = "https://magazine.sebastianraschka.com/feed" }},
    {{ name = "Latepost 晚点", url = "https://rsshub.rssforever.com/latepost" }},
]

# ── PurrMemo 记忆系统（可选） ──
[purrmemo]
enabled = false
host = "http://127.0.0.1:8000"
api_key = ""
timeout = 5

# ── Docker 沙盒（可选） ──
[docker]
# 容器内的代理设置（用于访问外网）
# 不设置或留空则不配置代理
http_proxy = "http://host.docker.internal:7897"
https_proxy = "http://host.docker.internal:7897"
all_proxy = "socks5://host.docker.internal:7897"

# ── 心跳传感器 ──
[heartbeat]
enabled = false
interval = 1800
"""




def _generate_mcp_config():
    """生成独立的 MCP 配置文件，避免敏感 Token 混在 TOML 里"""
    mcp_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(mcp_dir, exist_ok=True)
    mcp_path = os.path.join(mcp_dir, "mcp_config.json")

    if os.path.exists(mcp_path):
        print(f"⚠️  文件已存在: {mcp_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已保留原配置")
            return

    mcp_config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest", "--user-data-dir=.buffer/playwright", "--output-dir=.buffer/screenshots"],
                "idle_timeout": 600
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": ""
                }
            }
        }
    }

    try:
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2, ensure_ascii=False)
        print(f"✅ MCP 配置已生成: {mcp_path}")
    except Exception as e:
        print(f"❌ 写入 mcp_config.json 失败: {e}")

def cmd_init():
    """生成配置模板"""
    config_path = os.path.expanduser("~/.purrcat.toml")
    if os.path.exists(config_path):
        print(f"⚠️  文件已存在: {config_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已取消")
            return

    content = CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 配置文件已生成: {config_path}")
    except Exception as e:
        print(f"❌ 写入失败: {e}")
        sys.exit(1)

    # 生成 mcp_config.json（单独存放，避免敏感信息混在 TOML 里）
    _generate_mcp_config()
    print(f"   编辑 ~/.purrcat.toml 填入 API Key 等配置")
    print(f"   编辑 mcp_config.json 填入 MCP Token")
    print(f"   然后运行: purrcat start")


def cmd_start():
    """启动主程序"""
    try:
        from src.utils.config import initialize_config
        initialize_config()
        from tui.app import PurrCatTUI
        app = PurrCatTUI()
        app.run()
    except ImportError as e:
        print(f"❌ 启动失败，缺少依赖: {e}")
        print("   运行: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


def cmd_env():
    """打印环境变量参考"""
    print("""# PurrCat 环境变量参考
# 优先级: 环境变量 > ~/.purrcat.toml > 默认值
#
# 示例:
#   export PURR_AGENT_MODEL=openai:deepseek-v4-flash
#   export PURR_WEB_TAVILY_API_KEY=sk-xxx
#   export PURR_MODELS_OPENAI_DEEPSEEK_V4_FLASH_API_KEYS_0=sk-xxx
#   purrcat start

PURR_AGENT_MODEL                          # 默认模型名
PURR_EMBEDDING_MODEL                      # Embedding 模型
PURR_WEB_TAVILY_API_KEY                   # Tavily API Key
PURR_FEISHU_APP_ID                        # 飞书 App ID
PURR_FEISHU_APP_SECRET                    # 飞书 App Secret
PURR_FEISHU_CHAT_ID                       # 飞书 Chat ID
PURR_MCP_GITHUB_ENV_GITHUB_PERSONAL_ACCESS_TOKEN  # GitHub Token
PURR_MODELS_[NAME]_API_KEYS_0             # 模型 API Key
PURR_MODELS_[NAME]_BASE_URL               # 模型 Base URL
PURR_HEARTBEAT_ENABLED                    # 心跳开关
PURR_PURRMEMO_ENABLED                     # PurrMemo 开关
""")


def main():
    parser = argparse.ArgumentParser(
        prog="purrcat",
        description="PurrCat - AI Agent Framework",
        usage="purrcat <command>"
    )
    parser.add_argument("command", nargs="?", default="start",
                        choices=["start", "init", "env", "help"],
                        help="start=启动  init=生成配置模板  env=环境变量参考")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init()
    elif args.command == "start":
        cmd_start()
    elif args.command == "env":
        cmd_env()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
