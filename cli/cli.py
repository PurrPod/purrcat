"""PurrCat CLI - 跨平台命令行入口"""
import sys, os, json, argparse
from datetime import datetime

# ── 配置模板 ──

MODEL_CONFIG_TEMPLATE = """# ============================================
# PurrCat 模型配置文件
# 路径: .purrcat/.model.yaml
# 生成: {timestamp}
# ============================================

# Embedding 模型（用于 RAG 检索）
embedding_model: BAAI/bge-small-zh-v1.5

# 主模型配置（代码会自动取第一个作为 agent_model）
main:
  openai:deepseek-v4-flash:
    api_keys:
      - sk-your-first-api-key-here
      # - sk-your-second-api-key-here
    base_url: https://api.deepseek.com/v1
    description: LLM worker
    rpm: 60                # 每分钟请求上限
    tpm: 1000000           # 每分钟 Token 上限
    concurrency: 3         # 最大并发数
    max_token: 500000      # 记忆窗口 Token 上限


# 任务模型配置（至少有一个才能开启多agent协作，模型可以和main一样，但不能同一个API-Key）
task:
  # openai:deepseek-v4-flash:
  #   api_keys:
  #     - sk-your-task-api-key
  #   base_url: https://api.deepseek.com/v1
  #   description: Task Model
  #   rpm: 60
  #   tpm: 1000000
  #   concurrency: 3
  #   max_token: 500000
"""

SENSOR_CONFIG_TEMPLATE = """# ============================================
# PurrCat 传感器配置文件
# 路径: .purrcat/.sensor.yaml
# 生成: {timestamp}
# ============================================

# 飞书集成（可选）
feishu:
  enabled: false
  app_id: ""
  app_secret: ""
  chat_id: ""

# RSS 订阅（可选）
rss:
  enabled: false
  subscriptions:
    - name: Lilian Weng's Blog
      url: https://lilianweng.github.io/lil-log/feed.xml
    - name: Ahead of AI
      url: https://magazine.sebastianraschka.com/feed
    - name: Latepost 晚点
      url: https://rsshub.rssforever.com/latepost

# 心跳传感器（可选）
heartbeat:
  enabled: false
  interval: 1800          # 心跳间隔（秒）

# PurrMemo 记忆系统（可选）
purrmemo:
  enabled: false
  host: http://127.0.0.1:8000
  api_key: ""
  timeout: 5
"""

FILE_CONFIG_TEMPLATE = """# ============================================
# PurrCat 文件系统配置文件
# 路径: .purrcat/.file.yaml
# 生成: {timestamp}
# ============================================

# 禁止读取/导入的目录
dont_read_dirs:
  - src/

# 允许 export_file 写入的目录
allowed_export_dirs:
  - .

# 挂载到 Docker 沙盒的目录
docker_mount:
  - sandbox/

# 沙盒目录
sandbox_dirs:
  - sandbox/
  - agent_vm/

# 技能目录
skill_dir:
  - skill
"""


def _generate_mcp_config(purrcat_dir):
    """生成 MCP 配置文件"""
    mcp_path = os.path.join(purrcat_dir, "mcp_config.json")

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
                "args": [
                    "@playwright/mcp@latest",
                    "--user-data-dir=agent_vm/.buffer/playwright",
                    "--output-dir=agent_vm/.buffer/screenshots"
                ],
                "idle_timeout": 600
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
            }
        }
    }

    try:
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2, ensure_ascii=False)
        print(f"✅ MCP 配置已生成: {mcp_path}")
    except Exception as e:
        print(f"❌ 写入 mcp_config.json 失败: {e}")


def _generate_model_config(purrcat_dir):
    """生成模型配置文件"""
    model_path = os.path.join(purrcat_dir, ".model.yaml")

    if os.path.exists(model_path):
        print(f"⚠️  文件已存在: {model_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已保留原配置")
            return

    content = MODEL_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(model_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 模型配置已生成: {model_path}")
    except Exception as e:
        print(f"❌ 写入 .model.yaml 失败: {e}")


def _generate_sensor_config(purrcat_dir):
    """生成传感器配置文件"""
    sensor_path = os.path.join(purrcat_dir, ".sensor.yaml")

    if os.path.exists(sensor_path):
        print(f"⚠️  文件已存在: {sensor_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已保留原配置")
            return

    content = SENSOR_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(sensor_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 传感器配置已生成: {sensor_path}")
    except Exception as e:
        print(f"❌ 写入 .sensor.yaml 失败: {e}")


def _generate_file_config(purrcat_dir):
    """生成文件系统配置文件"""
    file_path = os.path.join(purrcat_dir, ".file.yaml")

    if os.path.exists(file_path):
        print(f"⚠️  文件已存在: {file_path}")
        val = input("  覆盖？(y/N): ").strip().lower()
        if val != "y":
            print("  已保留原配置")
            return

    content = FILE_CONFIG_TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 文件系统配置已生成: {file_path}")
    except Exception as e:
        print(f"❌ 写入 .file.yaml 失败: {e}")


def cmd_init():
    """生成 .purrcat 配置目录"""
    purrcat_dir = os.path.join(os.getcwd(), ".purrcat")
    
    if os.path.exists(purrcat_dir):
        print(f"⚠️  目录已存在: {purrcat_dir}")
        val = input("  覆盖所有配置文件？(y/N): ").strip().lower()
        if val != "y":
            print("  已取消")
            return

    try:
        os.makedirs(purrcat_dir, exist_ok=True)
        print(f"📁 创建配置目录: {purrcat_dir}")
    except Exception as e:
        print(f"❌ 创建目录失败: {e}")
        sys.exit(1)

    # 生成四个配置文件
    _generate_model_config(purrcat_dir)
    _generate_sensor_config(purrcat_dir)
    _generate_file_config(purrcat_dir)
    _generate_mcp_config(purrcat_dir)

    print("")
    print("📋 配置文件结构:")
    print("   .purrcat/")
    print("   ├── .model.yaml      # 模型配置")
    print("   ├── .sensor.yaml     # 传感器配置")
    print("   ├── .file.yaml       # 文件系统配置")
    print("   └── mcp_config.json  # MCP 服务器配置")
    print("")
    print("💡 下一步:")
    print("   编辑 .purrcat/.model.yaml 填入 API Key")
    print("   编辑 .purrcat/mcp_config.json 填入 MCP Token")
    print("   然后运行: purrcat start")


def cmd_start():
    """启动主程序"""
    import sys
    import subprocess
    from pathlib import Path

    # 解析命令行参数
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--headless", action="store_true", help="不启动 TUI，仅在后台运行")
    args, _ = parser.parse_known_args()

    # 调用 main.py
    main_py = Path(__file__).parent.parent / "main.py"
    cmd = [sys.executable, str(main_py)]
    if args.headless:
        cmd.append("--headless")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


def cmd_env():
    """打印环境变量参考"""
    print("""# PurrCat 环境变量参考
# 提示: 当前版本暂不支持环境变量覆盖配置
#       请直接编辑 .purrcat/ 目录下的配置文件
#
# 示例:
#   # 编辑模型配置
#   vim .purrcat/.model.yaml
#
#   # 编辑传感器配置
#   vim .purrcat/.sensor.yaml
#
#   # 编辑 MCP 配置
#   vim .purrcat/mcp_config.json
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
