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
    os.makedirs(os.path.join(workplace_mcp_dir, "scripts"), exist_ok=True)

    # 2. 固化环境搭建脚本（保证幂等与兼容）
    setup_script = """#!/bin/bash
uv init 2>/dev/null || true
uv venv --allow-existing
source .venv/bin/activate
uv add "mcp[cli]" httpx
"""
    with open(os.path.join(workplace_mcp_dir, "setup.sh"), "w", encoding="utf-8", newline='\n') as f:
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
    with open(os.path.join(workplace_mcp_dir, "core", "config.py"), "w", encoding="utf-8", newline='\n') as f:
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
    with open(os.path.join(workplace_mcp_dir, "server.py"), "w", encoding="utf-8", newline='\n') as f:
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
    with open(os.path.join(workplace_mcp_dir, "tools", "sample.py"), "w", encoding="utf-8", newline='\n') as f:
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
    with open(os.path.join(workplace_mcp_dir, "evals", "evals.json"), "w", encoding="utf-8", newline='\n') as f:
        f.write(evals_template)

    # 7. 生成 Git 忽略文件
    with open(os.path.join(workplace_mcp_dir, ".gitignore"), "w", encoding="utf-8", newline='\n') as f:
        f.write(".venv/\n__pycache__/\n*.pyc\n")

    # 8. 生成沙盒内部评测脚本 (将原先注入到沙盒的脚本固化在这里)
    evaluation_script = """import os
import sys
import json
import asyncio

# 动态将项目根目录加入模块搜索路径，防止 from server import mcp 报错
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from server import mcp

OUTPUT_DIR = "evals/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    schema_dump = []
    for tool in mcp._tool_manager._tools.values():
        schema_dump.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters
        })
    schema_path = os.path.join(OUTPUT_DIR, "schema_dump.json")
    with open(schema_path, "w", encoding="utf-8", newline='\n') as f:
        json.dump(schema_dump, f, ensure_ascii=False, indent=2)
    # 2. 读取并执行并发测试
    evals_file = "evals/evals.json"
    if not os.path.exists(evals_file):
        print(f"❌ 找不到测试用例文件: {evals_file}")
        return
    with open(evals_file, "r", encoding="utf-8") as f:
        evals = json.load(f)
    executions = evals.get("executions", [])
    if not executions:
        print("⚠️ 未配置 executions 测试用例")
        with open(os.path.join(OUTPUT_DIR, "execution_results.json"), "w", encoding="utf-8", newline='\n') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return
    async def run_tool(exec_case):
        tool_name = exec_case.get("tool")
        args = exec_case.get("arguments", {})
        desc = exec_case.get("description", "No desc")
        if tool_name not in mcp._tool_manager._tools:
            return {"tool": tool_name, "desc": desc, "status": "error", "error": "Tool not found"}
        try:
            func = mcp._tool_manager._tools[tool_name].fn
            res = await func(**args) if asyncio.iscoroutinefunction(func) else func(**args)
            return {"tool": tool_name, "desc": desc, "status": "success", "result": str(res)[:500]}
        except Exception as e:
            return {"tool": tool_name, "desc": desc, "status": "exception", "error": str(e)}
    tasks = [run_tool(case) for case in executions]
    executed_results = await asyncio.gather(*tasks)
    exec_path = os.path.join(OUTPUT_DIR, "execution_results.json")
    with open(exec_path, "w", encoding="utf-8", newline='\n') as f:
        json.dump(executed_results, f, ensure_ascii=False, indent=2)
    print(f"✅ 执行用例并发跑完 -> {exec_path}")
if __name__ == "__main__":
    asyncio.run(main())
"""
    with open(os.path.join(workplace_mcp_dir, "scripts", "evaluation.py"), "w", encoding="utf-8", newline='\n') as f:
        f.write(evaluation_script)
    # 9. 生成指南
    with open(os.path.join(workplace_root, "01_GUIDE_CREATE.md"), "w", encoding="utf-8", newline='\n') as f:
        f.write(generate_mcp_create_guide(mcp_name))
    with open(os.path.join(workplace_root, "02_GUIDE_TEST.md"), "w", encoding="utf-8", newline='\n') as f:
        f.write(generate_mcp_test_guide(mcp_name))
    return (
        f"【MCP 工厂分配成功】工作区路径：{workplace_root}。\n"
        f"已为你自动搭建了 '{mcp_name}' 的模块化 FastMCP 环境。\n"
        f"💡 请先阅读根目录的 01_GUIDE_CREATE 和 02_GUIDE_TEST 指南！"
    )
