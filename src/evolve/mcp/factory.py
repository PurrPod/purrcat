"""
MCP 进化工厂核心逻辑 (evolve/mcp/factory.py)
"""

import os
import shutil
import uuid
import subprocess
import threading
import json
from datetime import datetime
from src.utils.config import MCP_CONFIG_PATH, DATA_ROOT, AGENT_VM_DIR
from .guide_generator import generate_mcp_guide


def _hot_reload_after_merge():
    """合并后在后台线程热刷新 Schema 缓存与搜索索引，让新 MCP 立即可被调用/搜索。

    放后台执行是因为 uv run 冷启动可能较慢（建 venv 装依赖），
    不阻塞老板的审批响应；若失败不影响已完成的代码合并与配置写入。
    """

    def _worker():
        try:
            from src.tool.callmcp.schema_manager import refresh_schemas
            from src.tool.search.mcp_search import MCPSearcher, rebuild_vectors_async

            schemas = refresh_schemas()
            MCPSearcher().reload_index()
            rebuild_vectors_async()
            print(f"✅ [MCP工厂] 合并后热加载完成，系统共载入 {len(schemas)} 个 MCP 工具")
        except Exception as e:
            print(f"⚠️ [MCP工厂] 合并后热加载失败（不影响代码合并，可手动刷新）: {e}")

    threading.Thread(target=_worker, daemon=True, name="MCP-Merge-HotReload").start()


MCP_SERVER_CONFIG_FILE = "mcp_server_config.json"


def _ensure_server_config_template(mcp_dir: str):
    """确保沙盒中存在标准配置模板（全新创建时生成，升级时保留原有）"""
    config_path = os.path.join(mcp_dir, MCP_SERVER_CONFIG_FILE)
    if os.path.exists(config_path):
        return
    # 模板与合并注册逻辑配套：uv run --directory "." 由系统在合并时定位到正式目录
    default_config = {
        "command": "uv",
        "args": ["run", "--directory", ".", "server.py"],
        "env": {},
    }
    with open(
        config_path, "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)


def _write_goal_and_guide(workplace_root: str, mcp_name: str, goal: str):
    """落盘构建目标 GOAL.md + 生成单文件 GUIDE.md"""
    if goal:
        with open(
            os.path.join(workplace_root, "GOAL.md"), "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(f"# 🎯 Build Goal\n\n{goal}\n")
    with open(
        os.path.join(workplace_root, "GUIDE.md"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(generate_mcp_guide(mcp_name, goal))


def mcp_improve_init(mcp_name: str, goal: str = "") -> tuple[str, str]:
    """初始化 MCP 进化沙盒，返回 (系统提示, workplace_id)"""
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, "mcp_workplace", short_uuid)
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
    # ⚠️ mcp 2.0.0 移除了 mcp.server.fastmcp.FastMCP，模板 app.py 依赖 FastMCP，
    #    故约束 mcp<2（实测 1.29.0 全链路通过）
    setup_script = """#!/bin/bash
uv init 2>/dev/null || true
uv venv --allow-existing
source .venv/bin/activate
uv add "mcp[cli]<2" httpx
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

    # 10. 生成标准配置模板（合并注册的唯一依据，Agent 须按实际情况维护）
    _ensure_server_config_template(workplace_mcp_dir)

    # 11. 生成构建目标与单文件指南
    _write_goal_and_guide(workplace_root, mcp_name, goal)
    return (
        f"【MCP 工厂分配成功】工作区路径：/agent_vm/mcp_workplace/{short_uuid}（workplace_id: {short_uuid}）。\n"
        f"已为你自动搭建了 '{mcp_name}' 环境。💡 请先阅读 GUIDE.md！"
    ), short_uuid


def mcp_upgrade_init(mcp_name: str, goal: str = "") -> tuple[str, str]:
    """拷贝现存 MCP 至进化沙盒，返回 (系统提示, workplace_id)"""
    target_dir = os.path.join(DATA_ROOT, "mcps", mcp_name)
    if not os.path.exists(target_dir):
        return f"❌ 无法执行升级：未找到名为 '{mcp_name}' 的正式服务。", ""
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, "mcp_workplace", short_uuid)
    workplace_mcp_dir = os.path.join(workplace_root, mcp_name)
    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    def ignore_files(d, c):
        return [".venv", "venv", "__pycache__", ".git", "node_modules", ".env", "*.pyc"]

    shutil.copytree(target_dir, workplace_mcp_dir, ignore=ignore_files)
    # 老版本 MCP 没有配置文件，补齐模板（已有则保留 Agent/原版维护的内容）
    _ensure_server_config_template(workplace_mcp_dir)
    _write_goal_and_guide(workplace_root, mcp_name, goal)
    return (
        f"【MCP 升级派发成功】工作区路径：/agent_vm/mcp_workplace/{short_uuid}（workplace_id: {short_uuid}）。\n"
        f"💡 请在该路径继续迭代开发，可参考 GUIDE.md！"
    ), short_uuid


def mcp_request_handle(workplace_root: str, mcp_name: str, is_approved: bool) -> str:
    """处理 MCP 合并请求的核心逻辑"""
    if not is_approved:
        return f"人类拒绝了 {mcp_name} 的合并请求，已保留当前工作区供调整。"

    source_dir = os.path.join(workplace_root, mcp_name)
    abs_target_dir = os.path.join(DATA_ROOT, "mcps", mcp_name)
    target_dir = abs_target_dir
    is_upgrade = os.path.exists(target_dir)

    # 1. 强校验：读取 Agent 维护的 mcp_server_config.json（合并注册的唯一依据）
    sandbox_config_path = os.path.join(source_dir, MCP_SERVER_CONFIG_FILE)
    if not os.path.exists(sandbox_config_path):
        return (
            f"❌ 合并失败：沙盒中丢失了必需的配置文件 `{MCP_SERVER_CONFIG_FILE}`，"
            f"请 Agent 重新生成该文件并填写正确配置后再申请合并！"
        )
    try:
        with open(sandbox_config_path, "r", encoding="utf-8") as f:
            sandbox_config = json.load(f)
    except json.JSONDecodeError:
        return (
            f"❌ 合并失败：`{MCP_SERVER_CONFIG_FILE}` JSON 格式损坏，"
            f"请 Agent 修复后再申请合并。"
        )

    # 只提取合法键，过滤掉 Agent 可能乱加的废数据
    env_data = sandbox_config.get("env", {})
    if not isinstance(env_data, dict):
        env_data = {}
    command = sandbox_config.get("command", "uv")
    args = sandbox_config.get("args", [])
    if not isinstance(args, list):
        args = []

    # STDIO 启动不支持 cwd：相对的 --directory 必须定位到正式目录
    if "--directory" in args:
        idx = args.index("--directory")
        if idx + 1 < len(args) and not os.path.isabs(args[idx + 1]):
            args = list(args)
            args[idx + 1] = abs_target_dir

    # 2. 代码覆盖与拷贝（配置文件为沙盒元数据，不进入正式目录）
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)

    def ignore_files(d, c):
        return [
            ".venv",
            "venv",
            "__pycache__",
            ".git",
            "node_modules",
            ".env",
            "*.pyc",
            MCP_SERVER_CONFIG_FILE,
        ]

    shutil.copytree(source_dir, target_dir, ignore=ignore_files)

    # 3. Git 自动接管
    mcps_root = os.path.join(DATA_ROOT, "mcps")
    if not os.path.exists(os.path.join(mcps_root, ".git")):
        os.makedirs(mcps_root, exist_ok=True)
        subprocess.run(["git", "init"], cwd=mcps_root)
        with open(os.path.join(mcps_root, ".gitignore"), "w") as f:
            f.write("*.pyc\n__pycache__/\n.venv/\nvenv/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=mcps_root)
    subprocess.run(["git", "add", mcp_name], cwd=mcps_root)
    commit_msg = f"{'upgrade' if is_upgrade else 'add'} mcp {mcp_name} {datetime.now().strftime('%Y-%m-%d')}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=mcps_root)

    # 4. 注入 Agent 声明的配置到 .purrcat/mcp_config.json
    config_path = MCP_CONFIG_PATH
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
        "command": command,
        "args": args,
        "env": env_data,
    }

    with open(config_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(mcp_config, f, indent=2, ensure_ascii=False)

    # 5. 后台热刷新 Schema 缓存与搜索索引：合并即生效，无需重启系统
    _hot_reload_after_merge()

    # 6. 精简干净的返回
    return (
        f"🎉 审批通过！MCP '{mcp_name}' 成功合并。\n"
        f"📁 正式路径: {abs_target_dir}\n"
        f"⚙️ 配置已注入全局 `mcp_config.json`（含 {len(env_data)} 个环境变量声明），"
        f"系统正在后台热加载，稍候即可直接调用与搜索。\n"
        f"💡 若 env 中存在留空的密钥，请老板在 `.purrcat/mcp_config.json` 中补齐并保存，"
        f"下次调用会自动以新配置重启该 MCP 子进程，无需重启系统。\n"
        f"Git: {commit_msg}"
    )
