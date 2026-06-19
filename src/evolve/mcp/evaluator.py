"""
MCP 测试执行器 (evolve/mcp/evaluator.py)
宿主机负责：读取沙盒产物、执行 Trigger 语义竞争分析、聚合生成报告。
沙盒负责：运行代码、导出 Schema、执行并发 Execution 测试。
"""
import os
import json
import asyncio
import threading
import re
import shutil


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
    outputs_dir = os.path.join(dev_mcp_dir, "evals", "outputs")

    if not os.path.exists(evals_file):
        return f"测试失败：未找到 {evals_file}。请确保你编写了测试用例。"

    schema_path = os.path.join(outputs_dir, "schema_dump.json")
    exec_results_path = os.path.join(outputs_dir, "execution_results.json")

    # 核心解耦点：不再主动执行代码，而是检查 Agent 是否完成了它的工作
    if not os.path.exists(schema_path) or not os.path.exists(exec_results_path):
        return "宿主机评测失败：未检测到沙盒内部的测试产物。请确保你已经先使用 Bash 在沙盒内成功执行了 `python scripts/evaluation.py`！"

    with open(evals_file, "r", encoding="utf-8") as f:
        evals_data = json.load(f)

    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    # 把沙盒产物归档到 iteration-N 目录
    shutil.copy2(schema_path, os.path.join(iteration_dir, 'schema_dump.json'))
    shutil.copy2(exec_results_path, os.path.join(iteration_dir, 'execution_results.json'))

    # =========================================
    # 下方生成 Markdown 报告的代码与之前基本一致
    # =========================================
    report_lines = [f"# {mcp_name} 自动化测试报告 (Iteration {iteration_idx})\n"]
    report_lines.append(f"📂 **结果已落盘于**: `{iteration_dir}`\n")
    report_lines.append("## 1. Tool Schema 注册检查\n你的工具 Schema 清单已生成在 `schema_dump.json` 中。\n")

    # 触发 Trigger 模拟测试 (这部分需要利用宿主机资源，保留)
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
    try:
        with open(os.path.join(iteration_dir, 'execution_results.json'), "r", encoding="utf-8") as f:
            exec_results = json.load(f)
        success_count = sum(1 for r in exec_results if r["status"] == "success")
        report_lines.append(f"**总计执行**: {len(exec_results)} 个用例 | **成功返回**: {success_count} 个")
        for idx, res in enumerate(exec_results):
            icon = "✅" if res["status"] == "success" else "❌"
            report_lines.append(f"- {icon} **[{res['tool']}]** ({res['desc']}) -> 状态: {res['status']}")
            if res["status"] == "exception":
                report_lines.append(f"  - 报错: `{res['error']}`")
    except Exception as e:
        report_lines.append(f"⚠️ 解析 Execution 结果失败: {e}")

    final_report = "\n".join(report_lines)
    with open(os.path.join(iteration_dir, "test_report.md"), "w", encoding="utf-8") as f:
        f.write(final_report)
        
    return final_report
