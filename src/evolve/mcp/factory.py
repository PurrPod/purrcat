"""
MCP 进化工厂核心逻辑 (evolve/mcp/factory.py)
"""

import os
import shutil
import uuid
import subprocess
import json
from datetime import datetime
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
    os.makedirs(os.path.join(workplace_mcp_dir, "scripts"), exist_ok=True)

    # 2. 固化环境搭建脚本
    setup_script = """#!/bin/bash
uv init 2>/dev/null || true
uv venv --allow-existing
source .venv/bin/activate
uv add "mcp[cli]" httpx
"""
    with open(
        os.path.join(workplace_mcp_dir, "setup.sh"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(setup_script)

    # 3. 固化 Core 模块
    with open(os.path.join(workplace_mcp_dir, "core", "__init__.py"), "w") as f:
        f.write("")

    config_py_content = """import logging
import sys

def setup_logging():
    \"\"\"配置日志输出到 stderr，这是保护 STDIO 协议不被破坏的底线\"\"\"
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
"""
    with open(
        os.path.join(workplace_mcp_dir, "core", "config.py"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(config_py_content)

    # 4. 全局实例层 (app.py)
    app_py_content = (
        f"""from mcp.server.fastmcp import FastMCP\n\nmcp = FastMCP("{mcp_name}")\n"""
    )
    with open(
        os.path.join(workplace_mcp_dir, "app.py"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(app_py_content)

    # 5. 固化主入口 (server.py)
    server_py_content = """from app import mcp
from core.config import setup_logging
import tools.sample

def main():
    setup_logging()
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
"""
    with open(
        os.path.join(workplace_mcp_dir, "server.py"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(server_py_content)

    # 6. 固化 Tools 模块
    with open(os.path.join(workplace_mcp_dir, "tools", "__init__.py"), "w") as f:
        f.write("")

    sample_tool_content = """from app import mcp\nimport logging\n\n# ⚠️ 注意：避免工具函数名与你 import 的底层数据处理函数同名！\n# 否则会导致无限递归死循环。\n@mcp.tool()\nasync def sample_tool(param: str) -> str:\n    \"\"\"这是一个示例工具，用于展示标准的注释写法。\n    \n    Args:\n        param: 需要处理的字符串参数，例如用户输入的名字或查询条件。\n    \"\"\"\n    return f"Processed {param}"\n"""
    with open(
        os.path.join(workplace_mcp_dir, "tools", "sample.py"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(sample_tool_content)

    # 7. 生成 evals 测试模板
    evals_template = """{
  "mcp_name": "__MCP_NAME__",
  "triggers": [
    {"query": "测试唤醒", "expected_tool": "sample_tool"}
  ],
  "executions": [
    {"tool": "sample_tool", "arguments": {"param": "test"}, "description": "正常参数测试"}
  ]
}""".replace("__MCP_NAME__", mcp_name)
    with open(
        os.path.join(workplace_mcp_dir, "evals", "evals.json"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(evals_template)

    # 8. Git 忽略文件
    with open(
        os.path.join(workplace_mcp_dir, ".gitignore"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(".venv/\n__pycache__/\n*.pyc\n")

    # 9. 生成沙盒内部评测脚本
    evaluation_script = """import os, sys, json, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import server
from app import mcp

OUTPUT_DIR = "evals/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    schema_dump = [{"name": t.name, "description": t.description, "inputSchema": t.parameters} for t in mcp._tool_manager._tools.values()]
    with open(os.path.join(OUTPUT_DIR, "schema_dump.json"), "w", encoding="utf-8") as f:
        json.dump(schema_dump, f, ensure_ascii=False, indent=2)
    
    try:
        with open("evals/evals.json", "r", encoding="utf-8") as f: evals = json.load(f)
    except Exception:
        print("❌ 找不到 evals.json")
        return
    
    executions = evals.get("executions", [])
    async def run_tool(exec_case):
        t_name = exec_case.get("tool")
        if t_name not in mcp._tool_manager._tools: return {"tool": t_name, "status": "error", "error": "Not found"}
        try:
            fn = mcp._tool_manager._tools[t_name].fn
            res = await fn(**exec_case.get("arguments", {})) if asyncio.iscoroutinefunction(fn) else fn(**exec_case.get("arguments", {}))
            return {"tool": t_name, "status": "success", "result": str(res)[:500]}
        except Exception as e: return {"tool": t_name, "status": "exception", "error": str(e)}
        
    res = await asyncio.gather(*[run_tool(c) for c in executions])
    with open(os.path.join(OUTPUT_DIR, "execution_results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("✅ 执行完毕")

if __name__ == "__main__": asyncio.run(main())
"""
    with open(
        os.path.join(workplace_mcp_dir, "scripts", "evaluation.py"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(evaluation_script)

    # 10. 生成指南
    with open(
        os.path.join(workplace_root, "01_GUIDE_CREATE.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(generate_mcp_create_guide(mcp_name))
    with open(
        os.path.join(workplace_root, "02_GUIDE_TEST.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(generate_mcp_test_guide(mcp_name))
    return (
        f"【MCP 工厂分配成功】工作区路径：{workplace_root}。\n"
        f"已为你自动搭建了 '{mcp_name}' 环境。💡 请先阅读 01_GUIDE_CREATE！"
    )


def mcp_upgrade_init(mcp_name: str) -> str:
    target_dir = f"./mcps/{mcp_name}"
    if not os.path.exists(target_dir):
        return f"❌ 无法执行升级：未找到名为 '{mcp_name}' 的正式服务。"
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = f"./agent_vm/mcp_workplace/{short_uuid}"
    workplace_mcp_dir = os.path.join(workplace_root, mcp_name)
    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    def ignore_files(d, c):
        return [".venv", "venv", "__pycache__", ".git", "node_modules", ".env", "*.pyc"]

    shutil.copytree(target_dir, workplace_mcp_dir, ignore=ignore_files)
    with open(
        os.path.join(workplace_root, "01_GUIDE_CREATE.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(generate_mcp_create_guide(mcp_name))
    with open(
        os.path.join(workplace_root, "02_GUIDE_TEST.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(generate_mcp_test_guide(mcp_name))
    return f"【MCP 升级派发成功】工作区路径：{workplace_root}。\n💡 请在该路径继续迭代开发！"


def mcp_request_handle(workplace_root: str, mcp_name: str, is_approved: bool) -> str:
    """处理 MCP 合并请求的核心逻辑"""
    if not is_approved:
        return f"人类拒绝了 {mcp_name} 的合并请求，已保留当前工作区供调整。"

    source_dir = os.path.join(workplace_root, mcp_name)
    target_dir = f"./mcps/{mcp_name}"
    abs_target_dir = os.path.abspath(os.path.join(os.getcwd(), "mcps", mcp_name))
    is_upgrade = os.path.exists(target_dir)

    # 1. 代码覆盖与拷贝
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)

    def ignore_files(d, c):
        return [".venv", "venv", "__pycache__", ".git", "node_modules", ".env", "*.pyc"]

    shutil.copytree(source_dir, target_dir, ignore=ignore_files)

    # 2. Git 自动接管
    mcps_root = "./mcps"
    if not os.path.exists(os.path.join(mcps_root, ".git")):
        os.makedirs(mcps_root, exist_ok=True)
        subprocess.run(["git", "init"], cwd=mcps_root)
        with open(os.path.join(mcps_root, ".gitignore"), "w") as f:
            f.write("*.pyc\n__pycache__/\n.venv/\nvenv/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=mcps_root)
    subprocess.run(["git", "add", mcp_name], cwd=mcps_root)
    commit_msg = f"{'upgrade' if is_upgrade else 'add'} mcp {mcp_name} {datetime.now().strftime('%Y-%m-%d')}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=mcps_root)

    # 3. 自动注入 JSON 配置到 .purrcat/mcp_config.json
    config_path = os.path.abspath(
        os.path.join(os.getcwd(), ".purrcat", "mcp_config.json")
    )
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    mcp_config = {"mcpServers": {}}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                mcp_config = json.load(f)
        except Exception:
            pass

    if "mcpServers" not in mcp_config:
        mcp_config["mcpServers"] = {}

    mcp_config["mcpServers"][mcp_name] = {
        "command": "uv",
        "args": ["run", "--directory", abs_target_dir, "server.py"],
    }

    with open(config_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(mcp_config, f, indent=2, ensure_ascii=False)

    # 4. 清理沙盒
    shutil.rmtree(workplace_root, ignore_errors=True)

    # 5. 精简干净的返回
    return (
        f"🎉 审批通过！MCP '{mcp_name}' 成功合并。\n"
        f"📁 正式路径: {abs_target_dir}\n"
        f"⚙️ `.purrcat/mcp_config.json` 客户端配置已由系统自动更新，立刻生效！\n"
        f"Git: {commit_msg}"
    )
