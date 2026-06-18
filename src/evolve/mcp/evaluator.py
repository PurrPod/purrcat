"""
MCP 测试执行器 (evolve/mcp/evaluator.py)
自动提取 Schema、执行 Trigger 模拟、并并发运行 Execution 测试。
"""
import os
import json
import asyncio
import threading
import subprocess
import re


def run_mcp_eval_background(workplace_id: str, mcp_name: str, main_session_id: str):
    """启动后台线程跑 MCP 测试流水线"""
    def _bg_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(_async_run_mcp_evals(workplace_id, mcp_name))
            from src.agent.manager import manager
            manager.agent_force_push(f"🔔 【MCP 测试结果】'{mcp_name}' 的自动化盲测已完成！\n\n{report}", type="system")
        except Exception as e:
            from src.agent.manager import manager
            manager.agent_force_push(f"❌ MCP '{mcp_name}' 测试运行崩溃: {e}", type="system")
        finally:
            loop.close()
    
    threading.Thread(target=_bg_task, daemon=True, name=f"MCPEval_{workplace_id}").start()


def _get_next_iteration_dir(workplace_root: str) -> tuple[str, int]:
    max_idx = 0
    if os.path.exists(workplace_root):
        for item in os.listdir(workplace_root):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
    next_idx = max_idx + 1
    return os.path.join(workplace_root, f"iteration-{next_idx}"), next_idx


async def _async_run_mcp_evals(workplace_id: str, mcp_name: str) -> str:
    workplace_root = f"./agent_vm/mcp_workplace/{workplace_id}"
    dev_mcp_dir = os.path.join(workplace_root, mcp_name)
    evals_file = os.path.join(dev_mcp_dir, "evals", "evals.json")

    if not os.path.exists(evals_file):
        return f"测试失败：未找到 {evals_file}。请确保你编写了测试用例。"

    with open(evals_file, "r", encoding="utf-8") as f:
        evals_data = json.load(f)

    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    # ==========================================
    # 注入沙盒测试脚本：负责导出 Schema 和并发执行
    # ==========================================
    runner_script_path = os.path.join(dev_mcp_dir, "mcp_sandbox_runner.py")
    sandbox_script = f"""
import sys
import json
import asyncio
from server import mcp

async def main():
    # 1. 导出 Tools Schema 清单
    schema_dump = []
    for tool in mcp._tools.values(): # 适配 FastMCP 内部结构或用公有 API
        schema_dump.append({{
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters
        }})
    
    with open("{os.path.abspath(os.path.join(iteration_dir, 'schema_dump.json'))}", "w", encoding="utf-8") as f:
        json.dump(schema_dump, f, ensure_ascii=False, indent=2)

    # 2. 读取 Executions 并发执行
    try:
        with open("{os.path.abspath(evals_file)}", "r", encoding="utf-8") as f:
            evals = json.load(f)
    except Exception as e:
        print(f"Error loading evals: {{e}}")
        return

    executions = evals.get("executions", [])
    results = []
    
    async def run_tool(exec_case):
        tool_name = exec_case.get("tool")
        args = exec_case.get("arguments", {{}})
        desc = exec_case.get("description", "No desc")
        
        if tool_name not in mcp._tools:
            return {{"tool": tool_name, "desc": desc, "status": "error", "error": "Tool not found"}}
            
        try:
            # 执行 FastMCP 底层绑定的 Python 函数
            func = mcp._tools[tool_name].fn
            res = await func(**args) if asyncio.iscoroutinefunction(func) else func(**args)
            return {{"tool": tool_name, "desc": desc, "status": "success", "result": str(res)[:500]}}
        except Exception as e:
            return {{"tool": tool_name, "desc": desc, "status": "exception", "error": str(e)}}

    # 启动并发测试
    tasks = [run_tool(case) for case in executions]
    executed_results = await asyncio.gather(*tasks)
    
    with open("{os.path.abspath(os.path.join(iteration_dir, 'execution_results.json'))}", "w", encoding="utf-8") as f:
        json.dump(executed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
"""
    with open(runner_script_path, "w", encoding="utf-8") as f:
        f.write(sandbox_script)

    # 执行沙盒测试脚本 (使用沙盒的虚拟环境)
    venv_python = os.path.join(dev_mcp_dir, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        return "测试失败：未找到虚拟环境，请确保你已经执行了 `bash setup.sh` 安装了依赖。"

    try:
        subprocess.run([venv_python, runner_script_path], cwd=dev_mcp_dir, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return f"测试脚本执行崩溃：\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"

    # 清理注入的脚本
    os.remove(runner_script_path)

    # 汇总报告
    report_lines = [f"# {mcp_name} 自动化测试报告 (Iteration {iteration_idx})\n"]
    report_lines.append(f"📂 **结果已落盘于**: `{iteration_dir}`\n")
    
    report_lines.append("## 1. Tool Schema 注册检查")
    report_lines.append("你的工具 Schema 清单已生成在 `schema_dump.json` 中。请稍后打开该文件，检查 FastMCP 解析出的 `inputSchema` 和类型是否完全符合你的期望。\n")

    # 🌟 新增：触发 Trigger 模拟测试 🌟
    report_lines.append("## 2. Trigger 模拟测试 (语义竞争分析)")
    
    try:
        with open(os.path.join(iteration_dir, 'schema_dump.json'), "r", encoding="utf-8") as f:
            schema_dump = json.load(f)
    except Exception:
        schema_dump = []

    triggers = evals_data.get("triggers", [])
    if not triggers:
        report_lines.append("⚠️ 未检测到 Trigger 测试用例。")
    elif not schema_dump:
        report_lines.append("⚠️ 无法执行 Trigger 测试：沙盒中未能成功导出任何 Tool Schema。")
    else:
        from src.tool.search.mcp_search import MCPSearcher
        searcher = MCPSearcher()
        
        trigger_success = 0
        for idx, t_case in enumerate(triggers):
            query = t_case.get("query", "")
            expected_tool = t_case.get("expected_tool")  # 可能为 None (反例测试)
            
            res = searcher.simulate_trigger(query, mcp_name, schema_dump, expected_tool)
            
            if expected_tool:
                # 正例测试
                if res["is_triggered"]:
                    icon = "✅"
                    trigger_success += 1
                    detail = f"成功抢占第 {res['rank']} 名 (得分: {res['score']})"
                else:
                    icon = "❌"
                    detail = f"激发失败！(工具得分: {res['score']}，未进前5或低于阈值)"
            else:
                # 反例测试
                if not res["is_triggered"]:
                    icon = "✅"
                    trigger_success += 1
                    detail = "反例测试通过，工具保持静默"
                else:
                    icon = "❌"
                    detail = f"反例测试失败！不该触发却抢占了第 {res['rank']} 名"

            report_lines.append(f"### 案例 {idx+1}: `{query}`")
            report_lines.append(f"- **期望唤醒**: `{expected_tool if expected_tool else '静默 (无)'}`")
            report_lines.append(f"- **状态**: {icon} {detail}")
            report_lines.append(f"- **竞争者排布 (Top K)**:\n  - " + "\n  - ".join(res["competitors"]))
            report_lines.append("")
            
        report_lines.append(f"**Trigger 总通过率**: {trigger_success}/{len(triggers)}\n")

    report_lines.append("## 3. 并发 Execution 测试结果")
    exec_results_path = os.path.join(iteration_dir, "execution_results.json")
    if os.path.exists(exec_results_path):
        with open(exec_results_path, "r", encoding="utf-8") as f:
            exec_results = json.load(f)
        
        success_count = sum(1 for r in exec_results if r["status"] == "success")
        report_lines.append(f"**总计执行**: {len(exec_results)} 个用例 | **成功返回**: {success_count} 个")
        
        for idx, res in enumerate(exec_results):
            icon = "✅" if res["status"] == "success" else "❌"
            report_lines.append(f"- {icon} **[{res['tool']}]** ({res['desc']}) -> 状态: {res['status']}")
            if res["status"] == "exception":
                report_lines.append(f"  - 报错: `{res['error']}`")
    else:
        report_lines.append("⚠️ 执行结果文件未生成，可能是代码存在严重语法错误导致提早退出。")

    final_report = "\n".join(report_lines)
    with open(os.path.join(iteration_dir, "test_report.md"), "w", encoding="utf-8") as f:
        f.write(final_report)
        
    return final_report
