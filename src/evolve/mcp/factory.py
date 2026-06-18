"""
MCP 进化工厂核心逻辑 (evolve/mcp/factory.py)
"""
import os
import shutil
import uuid
from .guide_generator import generate_mcp_create_guide, generate_mcp_test_guide

def mcp_improve_init(mcp_name: str) -> str:
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = f"./agent_vm/mcp_workplace/{short_uuid}"
    workplace_mcp_dir = os.path.join(workplace_root, mcp_name)

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    
    # 1. 创建结构化目录
    os.makedirs(workplace_mcp_dir, exist_ok=True)
    os.makedirs(os.path.join(workplace_mcp_dir, "core"), exist_ok=True)
    os.makedirs(os.path.join(workplace_mcp_dir, "tools"), exist_ok=True)
    os.makedirs(os.path.join(workplace_mcp_dir, "evals"), exist_ok=True)

    # 2. 固化环境搭建脚本
    setup_script = """#!/bin/bash
uv init
uv venv
source .venv/bin/activate
uv add "mcp[cli]" httpx
"""
    with open(os.path.join(workplace_mcp_dir, "setup.sh"), "w", encoding="utf-8") as f:
        f.write(setup_script)

    # 3. 固化 Core 模块 (配置与日志保护)
    with open(os.path.join(workplace_mcp_dir, "core", "__init__.py"), "w") as f:
        f.write("")
    
    config_py_content = """import logging
import sys

def setup_logging():
    \"\"\"配置日志输出到 stderr，这是保护 STDIO 协议不被破坏的底线\"\"\"
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# 可以在这里补充全局常量，如 BASE_URL, USER_AGENT 等
"""
    with open(os.path.join(workplace_mcp_dir, "core", "config.py"), "w", encoding="utf-8") as f:
        f.write(config_py_content)

    # 4. 固化主入口 (server.py)
    server_py_content = f"""from mcp.server.fastmcp import FastMCP
from core.config import setup_logging

# 1. 初始化安全日志
setup_logging()

# 2. 初始化 FastMCP 实例
mcp = FastMCP("{mcp_name}")

# 3. 导入 Tools (非常重要：必须在 mcp 实例化之后导入，以触发装饰器注册)
import tools.sample
# import tools.your_other_tool

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
"""
    with open(os.path.join(workplace_mcp_dir, "server.py"), "w", encoding="utf-8") as f:
        f.write(server_py_content)

    # 5. 固化 Tools 模块 (解耦的业务逻辑)
    with open(os.path.join(workplace_mcp_dir, "tools", "__init__.py"), "w") as f:
        f.write("")
    
    sample_tool_content = """from server import mcp
import logging

@mcp.tool()
async def sample_tool(param: str) -> str:
    \"\"\"
    这是一个示例工具。请在此处修改为真实的业务描述。
    Args:
        param: 请在此处描述参数的作用
    \"\"\"
    logging.info(f"Received param: {param}")
    # 在此实现具体业务逻辑
    return f"Processed {param}"
"""
    with open(os.path.join(workplace_mcp_dir, "tools", "sample.py"), "w", encoding="utf-8") as f:
        f.write(sample_tool_content)

    # 6. 生成 evals 测试模板
    evals_template = f"""{{
  "mcp_name": "{mcp_name}",
  "triggers": [
    {{
      "query": "请帮我查一下加州的天气警报",
      "expected_tool": "sample_tool"
    }},
    {{
      "query": "帮我写一首关于天气的诗",
      "expected_tool": null
    }}
  ],
  "executions": [
    {{
      "tool": "sample_tool",
      "arguments": {{"param": "test"}},
      "description": "正常参数测试"
    }},
    {{
      "tool": "sample_tool",
      "arguments": {{"param": "edge_case"}},
      "description": "边界参数测试"
    }}
  ]
}}"""
    with open(os.path.join(workplace_mcp_dir, "evals", "evals.json"), "w", encoding="utf-8") as f:
        f.write(evals_template)

    # 7. 生成 Git 忽略文件
    with open(os.path.join(workplace_mcp_dir, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(".venv/\n__pycache__/\n*.pyc\n")

    # 8. 生成指南
    with open(os.path.join(workplace_root, "01_GUIDE_CREATE.md"), "w", encoding="utf-8") as f:
        f.write(generate_mcp_create_guide(mcp_name))
    with open(os.path.join(workplace_root, "02_GUIDE_TEST.md"), "w", encoding="utf-8") as f:
        f.write(generate_mcp_test_guide(mcp_name))

    return (
        f"【MCP 工厂分配成功】工作区路径：{workplace_root}。\n"
        f"已为你自动搭建了 '{mcp_name}' 的模块化 FastMCP 环境。\n"
        f"💡 请先阅读根目录的 01_GUIDE_CREATE 和 02_GUIDE_TEST 指南！"
    )
