"""Task 工具主入口 - 统一调度任务创建、终止、查询和注入操作"""

import json
import os
import re
import traceback

from src.tool.task.task_operations import (
    add_task_operation,
    kill_task_operation,
    list_tasks_operation,
    submit_request_operation,
    get_task_details_operation,
)
from src.tool.utils.format import error_response, text_response, warning_response


def _get_all_graphs_info() -> dict:
    """扫描 harness/graph 目录，获取所有可用的工作流图定义、模型(core)及参数要求"""
    import src.harness.process as process_module

    graph_dir = os.path.join(os.path.dirname(process_module.__file__), "graph")
    if not os.path.exists(graph_dir):
        return {}

    graphs = {}
    for file in os.listdir(graph_dir):
        if file.endswith(".json"):
            try:
                with open(os.path.join(graph_dir, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    g_name = data.get("name", file.replace(".json", ""))

                    global_schema = data.get("global_schema", {})
                    required_inputs = data.get("required_inputs", {})

                    if global_schema:
                        param_schema = global_schema
                    else:
                        param_schema = {
                            k: {"required": True, "description": v}
                            for k, v in required_inputs.items()
                        }

                    graphs[g_name] = {
                        "description": data.get("description", "无描述"),
                        # 从 JSON 中提取 core，如果没有则提供一个默认兜底
                        "core": data.get("core", "openai:deepseek-v4-flash"),
                        "param_schema": param_schema,
                    }
            except Exception:
                pass
    return graphs


def _get_graphs_help_text(graphs: dict) -> str:
    """格式化可用工作流图列表，提供保姆级指南"""
    if not graphs:
        return "当前没有任何可用的工作流图 (Graph) 配置。"

    lines = ["💡 当前所有可用的工作流配置 (graph_name) 及其所需 inputs 如下："]
    for g_name, info in graphs.items():
        schema = info["param_schema"]
        # 展示信息时附加上它使用的模型，让大模型心中有数
        lines.append(
            f"\n▶ 【{g_name}】: {info['description']} (驱动核心: {info['core']})"
        )
        if schema:
            lines.append("   需要的 inputs 参数:")
            for k, v in schema.items():
                is_req = v.get("required", True)
                req_mark = "✅ 必填" if is_req else "⭕ 可选"
                param_type = v.get("type", "any")
                desc = v.get("description", "无描述")
                lines.append(f"     - {k} ({param_type}, {req_mark}): {desc}")
        else:
            lines.append("   需要的 inputs 参数: 无")
    return "\n".join(lines)


def Task(action: str, **kwargs) -> str:
    try:
        action = action.strip().lower() if action else ""
        if action not in ["list_graphs", "list_tasks", "add", "kill", "submit_request", "get_details"]:
            return error_response(f"无效的操作: {action}", "❌ 无效action")

        if action == "list_graphs":
            return text_response(
                {"message": _get_graphs_help_text(_get_all_graphs_info())},
                "📂 可用图列表",
            )
        if action == "list_tasks":
            return _handle_list_tasks()
        if action == "add":
            return _handle_add(**kwargs)
        if action == "kill":
            return _handle_kill(**kwargs)
        if action == "submit_request":
            return _handle_submit_request(**kwargs)
        if action == "get_details":
            return _handle_get_details(**kwargs)
    except Exception as e:
        traceback.print_exc()
        return error_response(f"任务异常: {str(e)}", "❌ Task执行异常")


def _handle_add(**kwargs) -> str:
    name = kwargs.get("name")
    graph_name = kwargs.get("graph_name")
    inputs = kwargs.get("inputs") or {}

    if not name:
        return error_response(
            "❌ 缺少必需参数: name。请为任务起一个简短的名称。", "❌ 缺少name"
        )

    # 🌟 新增：清洗并校验任务名称，防止路径非法字符和目录穿越
    name = str(name).strip()
    if re.search(r'[\\/:*?"<>|.]', name):
        return error_response(
            "❌ 任务名称(name)包含非法字符。\n"
            '💡 引导建议：为了保障底层落盘和文件系统安全，任务名称不能包含斜杠、小数点及冒号等特殊字符（如 \\ / : * ? " < > | .）。请修改名称后重试！',
            "❌ 名称非法",
        )

    if not graph_name:
        return error_response(
            "❌ 缺少必需参数: graph_name。\n"
            "💡 引导建议：你不应该自己编造图名称。请先调用 action='list_graphs' 查询当前系统有哪些可用的工作流图，然后再执行 add 创建任务！",
            "❌ 缺少graph_name",
        )

    graphs = _get_all_graphs_info()

    if graph_name not in graphs:
        return error_response(
            f"❌ 未找到指定的工作流图: '{graph_name}'。\n"
            "💡 引导建议：请先调用 action='list_graphs' 获取正确的图列表和参数要求，请勿随意编造 graph_name！",
            "❌ 图不存在",
        )

    graph_info = graphs[graph_name]
    param_schema = graph_info["param_schema"]

    validation_errors = []
    missing_required = []

    for k, v in param_schema.items():
        is_req = v.get("required", True)
        if is_req and (k not in inputs or inputs[k] is None):
            param_type = v.get("type", "any")
            desc = v.get("description", "无描述")
            missing_required.append(
                {"name": k, "type": param_type, "description": desc}
            )

    if missing_required:
        miss_str = "\n".join(
            [
                f"  - '{p['name']}' (类型: {p['type']}, 描述: {p['description']})"
                for p in missing_required
            ]
        )
        validation_errors.append(f"❌ 缺少必填参数:\n{miss_str}")

    extra_keys = [k for k in inputs.keys() if k not in param_schema]
    if extra_keys:
        extra_str = ", ".join([f"'{k}'" for k in extra_keys])
        validation_errors.append(f"⚠️ 传入了未知参数: {extra_str}")

    if validation_errors:
        help_text = "\n".join(validation_errors)
        help_text += f"\n\n💡 引导建议：你不确定参数时，请先调用 action='list_graphs' 仔细查看 '{graph_name}' 需要的 inputs 参数格式后再试！"
        return error_response(help_text, "❌ 参数错误")

    try:
        result, error = add_task_operation(name, inputs, graph_name)
        if error:
            return warning_response(error, "⚠️ 任务创建失败")
        return text_response(
            {"task_id": result["task_id"], "message": result["message"]},
            "🚀 任务已创建",
        )
    except Exception as e:
        return error_response(f"任务创建异常: {e}", "❌ 创建任务异常")


def _handle_list_tasks() -> str:
    result, error = list_tasks_operation()
    return (
        warning_response(error, "⚠️ 获取失败")
        if error
        else text_response(
            {"tasks": result["tasks"]}, f"📋 发现 {result['count']} 个任务"
        )
    )


def _handle_kill(**kwargs) -> str:
    task_id = kwargs.get("task_id")
    if not task_id:
        return error_response("缺少必需参数: task_id", "❌ 缺少task_id")
    result, error = kill_task_operation(task_id)
    return (
        warning_response(error, "⚠️ 终止失败")
        if error
        else text_response({"message": result["message"]}, "⛔ 任务已终止")
    )


def _handle_submit_request(**kwargs) -> str:
    task_id = kwargs.get("task_id")
    content = kwargs.get("content")
    node_id = kwargs.get("node_id")

    if not task_id:
        return error_response("缺少必需参数: task_id", "❌ 缺少task_id")
    if not content:
        return error_response("缺少必需参数: content", "❌ 缺少content")
    if not node_id:
        return error_response(
            "缺少必需参数: node_id。必须精确指定要向哪个节点注入指令，不支持广播！",
            "❌ 缺少node_id",
        )

    result, error = submit_request_operation(task_id, content, node_id)

    if error:
        return warning_response(error, "⚠️ 注入失败")
    return text_response({"message": result["message"]}, "💬 指令已成功注入")


def _handle_get_details(**kwargs) -> str:
    task_id = kwargs.get("task_id")
    if not task_id:
        return error_response("缺少必需参数: task_id", "❌ 缺少task_id")
        
    result, error = get_task_details_operation(task_id)
    if error:
        return warning_response(error, "⚠️ 获取详情失败")
        
    # ===== 在此层进行 LLM 友好的平文本渲染 =====
    nodes_info = result.get("nodes", [])
    if not nodes_info:
        dashboard_text = "当前任务没有支持指令注入的节点。"
    else:
        lines = []
        for node in nodes_info:
            lines.append(f"@{node['name']}(id: {node['id']}): {node['state']}")
        dashboard_text = "\n".join(lines)
        
    # 你甚至可以把 raw_data 也塞进 response 里，看具体框架是否剔除多余参数
    return text_response(
        {"message": dashboard_text},
        f"📊 任务 [{task_id}] 交互节点看板"
    )
