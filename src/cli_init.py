"""purrcat init - 交互式配置向导"""
import os, getpass
from datetime import datetime

TEMPLATE = """# ============================================
# PurrCat 配置文件
# 生成时间: {timestamp}
# 可用 `purrcat init` 重新生成
# 完整参考: https://github.com/PurrPod/purrcat
# ============================================

# ── Agent 基础配置 ──
[agent]
# 默认工作模型
model = "{model}"
# Embedding 模型（用于 RAG 检索）
embedding_model = "BAAI/bge-small-zh-v1.5"

# ── 模型配置 ──
# 每个模型一个节，节名 = 模型名
[models.{model_section}]
# API Key 列表（多个 key 自动负载均衡）
api_keys = [{api_keys}]
# API 地址
base_url = "{base_url}"
# 模型描述
description = "LLM worker"
# 限流参数
rpm = {rpm}
tpm = {tpm}
concurrency = {concurrency}
max_token = {max_token}

# ── 飞书集成（可选） ──
[feishu]
app_id = "{feishu_id}"
app_secret = "{feishu_secret}"
chat_id = "{feishu_chat}"

# ── 网络工具 ──
[web]
# Tavily Search API Key（用于 web_search 工具）
# 申请: https://tavily.com
tavily_api_key = "{tavily_key}"

# ── MCP 服务器 ──
[mcp.playwright]
command = "npx"
args = ["@playwright/mcp@latest", "--user-data-dir=.buffer/playwright", "--output-dir=.buffer/screenshots"]
idle_timeout = 600

[mcp.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = {{ GITHUB_PERSONAL_ACCESS_TOKEN = "{github_token}" }}

# ── 文件系统安全 ──
[filesystem]
# 禁止读取的目录（import_file 会跳过）
dont_read_dirs = ["src/"]
# 允许导出的目录（export_file 的目标限制）
allowed_export_dirs = [".", "agent_vm/"]
# 挂载到沙盒的目录
docker_mount = ["sandbox/", "."]

# ── RSS 订阅 ──
[rss]
subscriptions = [
    {{ name = "Lilian Weng's Blog", url = "https://lilianweng.github.io/lil-log/feed.xml" }},
    {{ name = "Ahead of AI (by Sebastian Raschka)", url = "https://magazine.sebastianraschka.com/feed" }},
    {{ name = "Latepost 晚点", url = "https://rsshub.rssforever.com/latepost" }},
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


def prompt(text: str, default: str = "", secret: bool = False) -> str:
    """带默认值的交互式输入"""
    if default:
        text = f"{text} [{default}]"
    text = f"  {text}: "
    try:
        if secret:
            val = getpass.getpass(text)
        else:
            val = input(text)
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val.strip() or default


def run_init():
    print()
    print("  ╭──────────────────────────────╮")
    print("  │  🐱 PurrCat 配置向导         │")
    print("  │  按 Enter 使用默认值          │")
    print("  ╰──────────────────────────────╯")
    print()

    # 1. 模型选择
    print("  ── 基础配置 ──")
    model = prompt("默认模型", "openai:deepseek-v4-flash")
    model_section = model.replace(":", ".")
    print()

    # 2. API Key
    print("  ── 模型凭据（必填） ──")
    api_key = prompt(f"{model} 的 API Key", secret=True)
    while not api_key:
        print("  ⚠️  API Key 不能为空")
        api_key = prompt(f"{model} 的 API Key", secret=True)
    api_keys = f'"{api_key}"'
    another = prompt("是否添加第二个 API Key（负载均衡）？留空跳过", "")
    if another:
        api_keys += f', "{another}"'
    print()

    base_url = prompt("Base URL", "https://api.deepseek.com/v1")
    rpm = prompt("每分钟请求限制 (RPM)", "60")
    tpm = prompt("每分钟 Token 限制 (TPM)", "1000000")
    concurrency = prompt("最大并发数", "3")
    max_token = prompt("记忆窗口 Token 上限 (max_token)", "500000")
    print()

    # 3. 可选集成
    print("  ── 可选集成（直接 Enter 跳过） ──")
    feishu_id = prompt("飞书 App ID", "")
    feishu_secret = ""
    feishu_chat = ""
    if feishu_id:
        feishu_secret = prompt("飞书 App Secret", secret=True)
        feishu_chat = prompt("飞书 Chat ID", "")
    print()

    tavily_key = prompt("Tavily API Key（用于网络搜索）", secret=True)
    print()

    github_token = prompt("GitHub Token（用于 MCP）", secret=True)
    print()

    # 4. 确认
    print("  ── 确认配置 ──")
    config_path = os.path.expanduser("~/.purrcat.toml")
    print(f"  配置文件将写入: {config_path}")
    confirm = prompt("确认生成？(Y/n)", "Y")
    if confirm.lower() not in ("y", "yes", ""):
        print("  ❌ 已取消")
        return

    # 5. 生成文件
    content = TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=model,
        model_section=model_section,
        api_keys=api_keys,
        base_url=base_url,
        rpm=rpm,
        tpm=tpm,
        concurrency=concurrency,
        max_token=max_token,
        feishu_id=feishu_id,
        feishu_secret=feishu_secret,
        feishu_chat=feishu_chat,
        tavily_key=tavily_key,
        github_token=github_token,
    )

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ 配置已写入: {config_path}")
        print()
        print("  🚀 现在可以运行:  purrcat start")
        print()
    except Exception as e:
        print(f"  ❌ 写入失败: {e}")
        return


if __name__ == "__main__":
    run_init()
