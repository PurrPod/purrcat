"""PurrCat CLI - 跨平台命令行入口"""
import sys, os, argparse
from datetime import datetime

CONFIG_TEMPLATE = """# ============================================
# PurrCat 配置文件
# 路径: ~/.purrcat.toml
# 完整参考: https://github.com/PurrPod/purrcat
# ============================================

# ── Agent 基础配置 ──
[agent]
# 默认工作模型
model = "openai:deepseek-v4-flash"
# Embedding 模型（用于 RAG 检索）
embedding_model = "BAAI/bge-small-zh-v1.5"

# ── 模型配置 ──
# 每行一个模型，节名 = 完整模型名（点号分隔）
[models.openai.deepseek-v4-flash]
# API Key 列表（多个自动负载均衡）
api_keys = ["sk-your-api-key-here"]
# API 地址
base_url = "https://api.deepseek.com/v1"
description = "LLM worker"
# 限流参数
rpm = 60
tpm = 1000000
concurrency = 3
max_token = 500000

# ── 飞书集成（可选） ──
[feishu]
app_id = ""
app_secret = ""
chat_id = ""

# ── 网络工具 ──
[web]
# Tavily Search API Key（申请: https://tavily.com）
tavily_api_key = ""

# ── MCP 服务器 ──
[mcp.playwright]
command = "npx"
args = ["@playwright/mcp@latest", "--user-data-dir=.buffer/playwright", "--output-dir=.buffer/screenshots"]
idle_timeout = 600

[mcp.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_PERSONAL_ACCESS_TOKEN = "" }

# ── 文件系统安全 ──
[filesystem]
# 禁止读取的目录
dont_read_dirs = ["src/"]
# 允许导出的目录
allowed_export_dirs = [".", "agent_vm/"]
# 挂载到沙盒的目录
docker_mount = ["sandbox/", "."]

# ── RSS 订阅 ──
[rss]
subscriptions = [
    { name = "Lilian Weng's Blog", url = "https://lilianweng.github.io/lil-log/feed.xml" },
    { name = "Ahead of AI", url = "https://magazine.sebastianraschka.com/feed" },
    { name = "Latepost 晚点", url = "https://rsshub.rssforever.com/latepost" },
]

# ── PurrMemo 记忆系统（可选） ──
[purrmemo]
enabled = false
host = "http://127.0.0.1:8000"
api_key = ""

# ── 心跳传感器 ──
[heartbeat]
enabled = false
interval = 1800
"""


def cmd_init():
    """生成配置模板"""
    config_path = os.path.expanduser("~/.purrcat.toml")
    if os.path.exists(config_path):
        print(f"⚠️  文件已存在: {config_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已取消")
            return

    content = f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + CONFIG_TEMPLATE
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 配置文件已生成: {config_path}")
        print(f"   编辑此文件填入你的 API Key 等配置")
        print(f"   然后运行: purrcat start")
    except Exception as e:
        print(f"❌ 写入失败: {e}")
        sys.exit(1)


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
#   purrcat start

PURR_AGENT_MODEL                  # 默认模型名
PURR_EMBEDDING_MODEL              # Embedding 模型
PURR_WEB_TAVILY_API_KEY           # Tavily API Key
PURR_FEISHU_APP_ID                # 飞书 App ID
PURR_FEISHU_APP_SECRET            # 飞书 App Secret
PURR_FEISHU_CHAT_ID               # 飞书 Chat ID
PURR_MCP_GITHUB_ENV_GITHUB_PERSONAL_ACCESS_TOKEN  # GitHub Token
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
