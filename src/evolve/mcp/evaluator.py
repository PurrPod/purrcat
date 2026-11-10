"""
MCP 测试执行器 (evolve/mcp/evaluator.py)
宿主机负责：读取沙盒产物、执行 Trigger 语义竞争分析、聚合生成专业的 MCP Server 基准报告。
"""

import os
import json
import asyncio
import threading
import shutil

from src.utils.config import AGENT_VM_DIR


from src.evolve.common.paths import next_iteration_dir as _get_next_iteration_dir
from src.evolve.common.report import (
    now_iso as _now_iso,
    write_report as _write_report,
)


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


def _execution_passed(result: dict) -> bool:
    """兼容旧产物：无 verdict 时回退为“成功返回即通过”。"""
    verdict = result.get("verdict")
    if verdict is None:
        return result.get("status") == "success"
    return verdict == "pass"


def _build_registration_block(schema_dump, H):
    """一、工具矩阵注册大盘。"""
    if not schema_dump:
        reg_stat = [
            {
                "label": "已注册工具",
                "value": "0",
                "icon_name": "server",
                "tone": "accent",
            }
        ]
        reg_body = H.note(
            "服务异常：此 MCP Server 未能在 FastMCP 中成功注册任何有效的 Tool 工具。"
        )
    else:
        reg_stat = [
            {
                "label": "已注册工具",
                "value": str(len(schema_dump)),
                "icon_name": "server",
                "tone": "ok",
            }
        ]
        reg_rows = []
        for tool in schema_dump:
            properties = (
                tool.get("inputSchema", {}).get("properties", {})
                if isinstance(tool.get("inputSchema"), dict)
                else {}
            )
            desc = (tool.get("description") or "⚠️ 未编写任何描述说明").replace(
                "\n", " "
            )
            reg_rows.append(
                [
                    f'<span class="mono">{H.esc(tool.get("name", ""))}</span>',
                    H.esc(desc),
                    f"{len(properties)} 个",
                ]
            )
        reg_body = H.table(["工具名称", "功能描述", "参数量"], reg_rows)
    return H.section(
        "01",
        "工具矩阵注册大盘（Schema Registration）",
        H.stats(reg_stat, cols=1) + reg_body,
    )


def _build_trigger_block(evals_data, schema_dump, mcp_name, H):
    """二、语义检索与路由竞争分析。"""
    triggers = evals_data.get("triggers", [])
    trig_stat = []
    if not triggers:
        trig_body = H.note(
            "未检测到 Trigger 测试用例，请在 evals.json 中配置激发路径。"
        )
    elif not schema_dump:
        trig_body = H.note("无法分析激发路由：工具矩阵注册为空。")
    else:
        from src.tool.search.mcp_search import MCPSearcher

        searcher = MCPSearcher()
        trigger_success = 0
        items = []
        for idx, t_case in enumerate(triggers):
            query = t_case.get("query", "")
            expected_tool = t_case.get("expected_tool")  # 可为 None 代表反例

            res = searcher.simulate_trigger(query, mcp_name, schema_dump, expected_tool)

            if expected_tool:
                if res["is_triggered"]:
                    status = "pass"
                    detail = f"唤醒成功（抢占第 {res['rank']} 名，得分 {res['score']}）"
                    trigger_success += 1
                else:
                    status = "fail"
                    detail = (
                        f"激发失败（得分 {res['score']}，未进 Top 5 或低于唤醒阈值）"
                    )
            else:
                if not res["is_triggered"]:
                    status = "pass"
                    detail = "反例拦截成功（工具保持静默）"
                    trigger_success += 1
                else:
                    status = "fail"
                    detail = f"反例拦截失败（不该触发却抢占了第 {res['rank']} 名）"

            competitors = res.get("competitors") or []
            items.append(
                {
                    "title": f"案例 {idx + 1}：{query}",
                    "status": status,
                    "meta": [
                        (
                            "期望工具",
                            expected_tool if expected_tool else "静默阻断（无）",
                        ),
                        ("结果", detail),
                    ],
                    "notes": [
                        "语义竞争排布（Top K）：" + ("；".join(competitors) or "无")
                    ],
                }
            )
        trig_body = H.cases(items)
        trig_stat = [
            {
                "label": "Trigger 唤醒率",
                "value": f"{trigger_success}/{len(triggers)}",
                "icon_name": "zap",
                "tone": "accent" if trigger_success == len(triggers) else "",
            }
        ]
    trig_head = H.stats(trig_stat, cols=1) if trig_stat else ""
    return H.section(
        "02", "模型意图激发分析（Trigger Semantic Routing）", trig_head + trig_body
    )


def _build_execution_block(iteration_dir: str, evals_data, H):
    """三、用例并发执行与可用性断言。"""
    exec_stat = []
    try:
        with open(
            os.path.join(iteration_dir, "execution_results.json"), "r", encoding="utf-8"
        ) as f:
            exec_results = json.load(f)

        executions_cases = evals_data.get("executions", [])

        pass_count = sum(1 for r in exec_results if _execution_passed(r))
        fail_count = len(exec_results) - pass_count
        exec_stat = [
            {"label": "边界用例", "value": str(len(exec_results)), "icon_name": "list"},
            {
                "label": "通过",
                "value": str(pass_count),
                "icon_name": "check",
                "tone": "ok",
            },
            {
                "label": "失败",
                "value": str(fail_count),
                "icon_name": "x",
                "tone": "accent" if fail_count else "",
            },
        ]

        items = []
        for idx, res in enumerate(exec_results):
            # 安全地通过索引与原始 executions 用例结合，取到人类可读的 description 和入参
            case_desc = "未提供用例描述"
            case_args = "{}"
            if idx < len(executions_cases):
                case_desc = executions_cases[idx].get("description", case_desc)
                case_args = json.dumps(
                    executions_cases[idx].get("arguments", {}), ensure_ascii=False
                )

            passed = _execution_passed(res)
            state = res.get("status", "exception")
            if state == "exception":
                evidence = H.code_block(res.get("error", ""))
            else:
                evidence = H.code_block(res.get("result", ""))

            meta = [
                ("工具", res.get("tool", "")),
                ("入参", case_args),
                ("状态", state),
            ]
            if not passed:
                meta.append(("原因", res.get("reason") or res.get("error") or state))

            items.append(
                {
                    "title": f"用例 {idx + 1}：{case_desc}",
                    "status": "pass" if passed else "fail",
                    "meta": meta,
                    "blocks": [evidence],
                }
            )
        exec_body = H.cases(items)
    except Exception as e:
        exec_body = H.note(f"解析执行结果失败：{e}")
    exec_head = H.stats(exec_stat, cols=3) if exec_stat else ""
    return H.section(
        "03",
        "用例并发真实执行校验（Execution & Robustness）",
        exec_head + exec_body,
    )


async def _async_run_mcp_evals(workplace_id: str, mcp_name: str) -> str:
    workplace_root = os.path.join(AGENT_VM_DIR, "mcp_workplace", workplace_id)
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

    # 渲染瑞士风 HTML 报告（报告即输出物，不列文件清单、不贴物理路径）
    from src.evolve import report_html as H

    blocks = [
        _build_registration_block(schema_dump, H),
        _build_trigger_block(evals_data, schema_dump, mcp_name, H),
        _build_execution_block(iteration_dir, evals_data, H),
    ]

    html = H.page(
        title=f"{mcp_name} · MCP 测试合规报告",
        subtitle="工具矩阵注册、语义激发路由与边界用例并发执行结果，均由宿主实跑采集，非 Agent 自报。",
        meta=[
            ("MCP Server", mcp_name),
            ("迭代", f"Iteration {iteration_idx}"),
            ("注册工具", str(len(schema_dump))),
            ("生成时间", _now_iso()),
        ],
        blocks=blocks,
        kicker="PURRCAT · MCP FACTORY",
        footer_left="MCP Compliance Report",
        footer_right=f"Iteration {iteration_idx:02d}",
    )
    _write_report(iteration_dir, html)

    return (
        f"📊 MCP 测试完成：注册 {len(schema_dump)} 个工具，"
        f"报告已生成（iteration-{iteration_idx}/report.html）。"
    )
