"""Task 工具主入口 - 统一调度任务创建、终止和列表操作"""

import json
import os
import traceback

from src.tool.task.task_operations import (
    add_task_operation,
    kill_task_operation,
    list_tasks_operation,
    submit_request_operation,
)
from src.tool.utils.format import error_response, text_response, warning_response


def _get_all_graphs_info() -> dict:
    """扫描 harness/graph 目录，获取所有可用的工作流图定义及参数要求"""
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
        lines.append(f"\n▶ 【{g_name}】: {info['description']}")
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
        if action not in ["add", "kill", "list", "submit_request"]:
            return error_response(f"无效的操作: {action}", "❌ 无效action")

        if action == "add":
            return _handle_add(**kwargs)
        if action == "kill":
            return _handle_kill(**kwargs)
        if action == "list":
            return _handle_list(**kwargs)
        if action == "submit_request":
            return _handle_submit_request(**kwargs)
    except Exception as e:
        traceback.print_exc()
        return error_response(f"任务异常: {str(e)}", "❌ Task执行异常")


def _handle_add(**kwargs) -> str:
    name = kwargs.get("name")
    graph_name = kwargs.get("graph_name")
    inputs = kwargs.get("inputs") or {}
    core = kwargs.get("core", "openai:deepseek-v4-flash")

    if not name:
        return error_response("缺少必需参数: name", "❌ 缺少name")

    graphs = _get_all_graphs_info()

    if not graph_name or graph_name not in graphs:
        help_text = _get_graphs_help_text(graphs)
        err_prefix = (
            "缺少 graph_name"
            if not graph_name
            else f"未找到指定的工作流图 '{graph_name}'"
        )
        return error_response(
            f"❌ {err_prefix}。\n\n{help_text}\n\n👉 请仔细阅读上方指南，填入正确的 graph_name 和对应的 inputs 字典。",
            "❌ 图配置错误",
        )

    param_schema = graphs[graph_name]["param_schema"]

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
        all_params_info = []
        for k, v in param_schema.items():
            is_req = v.get("required", True)
            req_mark = "✅ 必填" if is_req else "⭕ 可选"
            param_type = v.get("type", "any")
            desc = v.get("description", "无描述")
            all_params_info.append(
                f"    - '{k}' (类型: {param_type}, {req_mark}): {desc}"
            )

        help_text = "\n".join(validation_errors)
        help_text += "\n\n📋 有效的参数列表:\n" + "\n".join(all_params_info)
        help_text += "\n\n💡 请检查您的输入参数后重试。"

        return error_response(help_text, "❌ 参数错误")

    try:
        result, error = add_task_operation(name, inputs, graph_name, core)
        if error:
            return warning_response(error, "⚠️ 任务创建失败")
        return text_response(
            {"task_id": result["task_id"], "message": result["message"]},
            "🚀 任务已创建",
        )
    except Exception as e:
        return error_response(f"任务创建异常: {e}", "❌ 创建任务异常")


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


def _handle_list(**kwargs) -> str:
    result, error = list_tasks_operation()
    return (
        warning_response(error, "⚠️ 获取失败")
        if error
        else text_response({"tasks": result["tasks"]}, f"📋 {result['count']}个任务")
    )


def _handle_submit_request(**kwargs) -> str:
    task_id = kwargs.get("task_id")
    content = kwargs.get("content")
    node_id = kwargs.get("node_id")

    if not task_id:
        return error_response("缺少必需参数: task_id", "❌ 缺少task_id")
    if not content:
        return error_response("缺少必需参数: content", "❌ 缺少content")

    result, error = submit_request_operation(task_id, content, node_id)

    if error:
        return warning_response(error, "⚠️ 注入失败")
    return text_response({"message": result["message"]}, "💬 指令已注入")
