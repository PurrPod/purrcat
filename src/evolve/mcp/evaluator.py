"""
MCP 测试执行器 (evolve/mcp/evaluator.py)
宿主机负责：读取沙盒产物、执行 Trigger 语义竞争分析、聚合生成专业的 MCP Server 基准报告。
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
            report = loop.run_until_complete(
                _async_run_mcp_evals(workplace_id, mcp_name)
            )
            from src.agent.manager import manager

            manager.agent_force_push(
                f"🔔 【MCP 自动化测试完成】'{mcp_name}' 核心基准测试已结束，报告已更新！\n\n{report}",
                type="system",
            )
        except Exception as e:
            from src.agent.manager import manager

            manager.agent_force_push(
                f"❌ MCP '{mcp_name}' 测试运行崩溃: {e}", type="system"
            )
        finally:
            loop.close()

    threading.Thread(
        target=_bg_task, daemon=True, name=f"MCPEval_{workplace_id}"
    ).start()


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

    # 检查沙盒内部的测试产物
    if not os.path.exists(schema_path) or not os.path.exists(exec_results_path):
        return "宿主机评测失败：未检测到沙盒内部的测试产物。请确保你已经先在沙盒内使用终端成功执行了 `python scripts/evaluation.py`！"

    with open(evals_file, "r", encoding="utf-8") as f:
        evals_data = json.load(f)

    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    # 把沙盒产物归档到 iteration-N 目录
    shutil.copy2(schema_path, os.path.join(iteration_dir, "schema_dump.json"))
    shutil.copy2(
        exec_results_path, os.path.join(iteration_dir, "execution_results.json")
    )

    try:
        with open(
            os.path.join(iteration_dir, "schema_dump.json"), "r", encoding="utf-8"
        ) as f:
            schema_dump = json.load(f)
    except Exception:
        schema_dump = []

    # =========================================================================
    # 生成纯粹、高可读性的专业 MCP Server 测试报告
    # =========================================================================
    report_lines = [
        f"# 🔌 {mcp_name} 自动化测试与合规报告 (Iteration {iteration_idx})",
        f"📂 **归档物理路径**: `{iteration_dir}`\n",
    ]

    # 一、工具矩阵注册大盘
    report_lines.append("## 📊 一、工具矩阵注册大盘 (Schema Registration)")
    if not schema_dump:
        report_lines.append(
            "❌ **服务异常**：此 MCP Server 未能在 FastMCP 中成功注册任何有效的 Tool 工具！\n"
        )
    else:
        report_lines.append(
            f"✅ **服务检查通过**：系统检测到当前服务已成功向 STDIO 协议注册 **{len(schema_dump)}** 个工具。\n"
        )
        report_lines.append(
            "| 工具名称 (Tool Name) | 功能描述 (Description) | 参数量 (Params) |"
        )
        report_lines.append("| :--- | :--- | :--- |")
        for tool in schema_dump:
            properties = (
                tool.get("inputSchema", {}).get("properties", {})
                if isinstance(tool.get("inputSchema"), dict)
                else {}
            )
            param_count = len(properties)
            desc = tool.get("description", "⚠️ 未编写任何描述说明").replace("\n", " ")
            report_lines.append(f"| `{tool['name']}` | {desc} | {param_count} 个 |")
        report_lines.append("")

    # 二、语义检索与路由竞争分析
    report_lines.append("## 🎯 二、模型意图激发分析 (Trigger Semantic Routing)")
    triggers = evals_data.get("triggers", [])
    if not triggers:
        report_lines.append(
            "⚠️ **未检测到 Trigger 测试用例**。请在 `evals.json` 中配置激发路径。\n"
        )
    elif not schema_dump:
        report_lines.append("⚠️ **无法分析激发路由**：因为工具矩阵注册为空。\n")
    else:
        from src.tool.search.mcp_search import MCPSearcher

        searcher = MCPSearcher()
        trigger_success = 0

        for idx, t_case in enumerate(triggers):
            query = t_case.get("query", "")
            expected_tool = t_case.get("expected_tool")  # 可为 None 代表反例

            res = searcher.simulate_trigger(query, mcp_name, schema_dump, expected_tool)

            if expected_tool:
                if res["is_triggered"]:
                    icon, status_text = (
                        "✅",
                        f"唤醒成功 (抢占第 {res['rank']} 名，得分: {res['score']})",
                    )
                    trigger_success += 1
                else:
                    icon, status_text = (
                        "❌",
                        f"激发失败 (工具权重得分: {res['score']}，未进 Top 5 或低于唤醒阈值)",
                    )
            else:
                if not res["is_triggered"]:
                    icon, status_text = "✅", "反例拦截成功 (工具保持绝对静默)"
                    trigger_success += 1
                else:
                    icon, status_text = (
                        "❌",
                        f"反例拦截失败 (不该触发却抢占了第 {res['rank']} 名)",
                    )

            report_lines.append(f"### 案例 {idx + 1}: 用户请求 `{query}`")
            report_lines.append(
                f"- **期望工具**: `{expected_tool if expected_tool else '静默阻断 (无)'}`"
            )
            report_lines.append(f"- **评测状态**: {icon} **{status_text}**")
            report_lines.append("- **语义竞争排布 (Top K 路由树)**:")
            for comp in res["competitors"]:
                report_lines.append(f"  - {comp}")
            report_lines.append("")

        report_lines.append(
            f"📈 **意图路由总唤醒率 (Trigger Pass Rate)**: **{trigger_success}/{len(triggers)}**\n"
        )

    # 三、用例并发执行与可用性断言
    report_lines.append("## ⚡ 三、用例并发真实执行校验 (Execution & Robustness)")
    try:
        with open(
            os.path.join(iteration_dir, "execution_results.json"), "r", encoding="utf-8"
        ) as f:
            exec_results = json.load(f)

        executions_cases = evals_data.get("executions", [])
        success_count = sum(1 for r in exec_results if r["status"] == "success")

        report_lines.append(
            f"📊 **执行统计**: 总计并发运行 **{len(exec_results)}** 个边界用例 | **成功返回**: {success_count} 个 | **失败/阻断**: {len(exec_results) - success_count} 个\n"
        )

        for idx, res in enumerate(exec_results):
            # 安全地通过索引与原始 executions 用例结合，取到人类可读的 description 和入参
            case_desc = "未提供用例描述"
            case_args = "{}"
            if idx < len(executions_cases):
                case_desc = executions_cases[idx].get("description", case_desc)
                case_args = json.dumps(
                    executions_cases[idx].get("arguments", {}),
                    ensure_ascii=False,
                )

            if res["status"] == "success":
                report_lines.append(
                    f"### 🟢 用例 {idx + 1}: [{res['tool']}] - {case_desc}"
                )
                report_lines.append(f"- **测试入参**: `{case_args}`")
                report_lines.append("- **执行状态**: `SUCCESS` ✅")
                report_lines.append("- **返回值输出截断 (Stdout Snip)**:")
                report_lines.append(f"  ```text\n  {res.get('result', '')}\n  ```\n")
            else:
                report_lines.append(
                    f"### 🔴 用例 {idx + 1}: [{res['tool']}] - {case_desc}"
                )
                report_lines.append(f"- **测试入参**: `{case_args}`")
                report_lines.append(f"- **执行状态**: `{res['status'].upper()}` ❌")
                report_lines.append("- **致命报错与堆栈信息 (Exception Stack)**:")
                report_lines.append(
                    f"  ```python\n  {res.get('error', '未知错误导致沙盒进程中断')}\n  ```\n"
                )

    except Exception as e:
        report_lines.append(f"⚠️ **解析 Execution 执行结果失败**: {e}")

    final_report = "\n".join(report_lines)
    with open(
        os.path.join(iteration_dir, "test_report.md"), "w", encoding="utf-8"
    ) as f:
        f.write(final_report)

    return final_report
