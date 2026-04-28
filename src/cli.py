"""PurrCat CLI - 命令行入口"""
import sys, os, argparse

def main():
    parser = argparse.ArgumentParser(
        prog="purrcat",
        description="PurrCat - AI Agent Framework",
        usage="purrcat <command> [options]"
    )
    parser.add_argument("command", nargs="?", default="start",
                        choices=["start", "init", "env"],
                        help="start=启动主程序  init=初始化配置  env=打印环境变量参考")

    args = parser.parse_args()

    if args.command == "init":
        from src.cli_init import run_init
        run_init()
    elif args.command == "start":
        try:
            from src.utils.config import initialize_config
            initialize_config()
            from tui.app import PurrCatTUI
            app = PurrCatTUI()
            app.run()
        except ImportError as e:
            print(f"❌ 启动失败，缺少依赖: {e}")
            print("请运行: pip install -r requirements.txt")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            sys.exit(1)
    elif args.command == "env":
        print("""# PurrCat 环境变量参考
# 设置这些环境变量会覆盖 ~/.purrcat.toml 中的对应配置
#
# 示例:
#   export PURR_AGENT_MODEL=openai:deepseek-v4-flash
#   export PURR_WEB_TAVILY_API_KEY=sk-xxx
#   purrcat start

# 基础配置
PURR_AGENT_MODEL              # 默认模型名
PURR_EMBEDDING_MODEL          # Embedding 模型名

# 模型配置（以 deepseek-v4-flash 为例）
PURR_MODELS_OPENAI_DEEPSEEK_V4_FLASH_API_KEYS_0  # API Key（索引0）
PURR_MODELS_OPENAI_DEEPSEEK_V4_FLASH_BASE_URL    # Base URL

# 飞书
PURR_FEISHU_APP_ID
PURR_FEISHU_APP_SECRET
PURR_FEISHU_CHAT_ID

# Web
PURR_WEB_TAVILY_API_KEY

# GitHub
PURR_MCP_GITHUB_ENV_GITHUB_PERSONAL_ACCESS_TOKEN

# 文件系统
PURR_FILESYSTEM_DONT_READ_DIRS_0    # 黑名单目录（索引0）
""")

if __name__ == "__main__":
    main()
