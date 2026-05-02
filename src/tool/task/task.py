"""Task 工具主入口 - 统一调度任务创建、终止和列表操作"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.task.exceptions import (
    TaskError,
    InvalidActionError,
    MissingParameterError,
    TaskNotFoundError
)
from src.tool.task.task_operations import (
    add_task_operation,
    kill_task_operation,
    list_tasks_operation
)


def _get_all_experts_info() -> str:
    """获取所有已注册专家的信息（动态从 BaseTask._EXPERT_REGISTRY 加载）"""
    from src.harness.task import BaseTask, auto_discover_experts
    auto_discover_experts()

    if not BaseTask._EXPERT_REGISTRY:
        return "当前没有任何已注册的专家类型"

    lines = ["当前所有可用的专家类型："]
    for expert_key, info in BaseTask._EXPERT_REGISTRY.items():
        desc = info.get("description", "无描述")
        lines.append(f"  - {expert_key}: {desc}")
    return "\n".join(lines)


def _get_expert_parameters_info(expert_type: str) -> str:
    """获取指定专家的参数信息（OpenAI SDK schema 格式）"""
    from src.harness.task import BaseTask, auto_discover_experts
    auto_discover_experts()

    if expert_type not in BaseTask._EXPERT_REGISTRY:
        return None

    registry_info = BaseTask._EXPERT_REGISTRY[expert_type]
    parameters = registry_info.get("parameters", {})

    if not parameters:
        return f"专家 '{expert_type}' 无需额外参数"

    lines = [f"专家 '{expert_type}' 的正确参数格式：", "{"]
    required_params = []

    for param_name, param_meta in parameters.items():
        param_type = param_meta.get("type", "string")
        param_desc = param_meta.get("description", "")
        is_required = param_meta.get("required", False)

        if is_required:
            required_params.append(param_name)

        lines.append(f'    "{param_name}": {{')
        lines.append(f'        "type": "{param_type}",')
        lines.append(f'        "description": "{param_desc}"')
        if not is_required:
            lines[-1] += ","
            lines.append('        "required": False')
        lines.append("    },")

    lines.append("}")
    if required_params:
        lines.append(f"\n必填参数: {', '.join(required_params)}")

    return "\n".join(lines)


def Task(action: str, **kwargs) -> str:
    """
    统一任务操作接口，支持任务的创建、终止和列表查询

    Args:
        action: 操作类型，支持: add（创建任务）、kill（终止任务）、list（列出任务）

    针对不同 action 的参数：
        - add: name (必填), prompt (必填), expert (必填), core (可选), expert_kwargs (可选)
        - kill: task_id (必填)
        - list: 无额外参数

    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 参数校验
        action = action.strip().lower() if action else ""
        
        # 检查操作类型
        if action not in ["add", "kill", "list"]:
            return error_response(
                f"无效的操作类型: {action}。支持的操作: add, kill, list",
                f"❌ 无效action | {action}"
            )

        # 根据操作类型执行
        if action == "add":
            return _handle_add(**kwargs)
        elif action == "kill":
            return _handle_kill(**kwargs)
        elif action == "list":
            return _handle_list(**kwargs)

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"任务运行时异常: {str(e)}", "❌ Task执行异常")


def _handle_add(**kwargs) -> str:
    """处理任务创建"""
    from src.harness.task import BaseTask, auto_discover_experts
    auto_discover_experts()

    name = kwargs.get("name")
    prompt = kwargs.get("prompt")
    expert = kwargs.get("expert")
    core = kwargs.get("core", "openai:deepseek-v4-flash")
    expert_kwargs = kwargs.get("expert_kwargs") or {}

    if not name:
        return error_response("缺少必需参数: name", "❌ 参数错误：缺少name")
    if not prompt:
        return error_response("缺少必需参数: prompt", "❌ 参数错误：缺少prompt")
    if not expert:
        all_experts_info = _get_all_experts_info()
        return error_response(
            f"缺少必需参数: expert\n\n{all_experts_info}",
            "❌ 参数错误：缺少expert"
        )

    if expert not in BaseTask._EXPERT_REGISTRY:
        all_experts_info = _get_all_experts_info()
        return error_response(
            f"未找到指定的专家类型: {expert}\n\n{all_experts_info}",
            f"❌ 无效的专家类型 | {expert}"
        )

    registry_info = BaseTask._EXPERT_REGISTRY[expert]
    parameters = registry_info.get("parameters", {})

    if parameters:
        missing_required = []
        for param_name, param_meta in parameters.items():
            if param_meta.get("required", False) and param_name not in expert_kwargs:
                missing_required.append(param_name)

        if missing_required:
            params_info = _get_expert_parameters_info(expert)
            return error_response(
                f"专家 '{expert}' 缺少必填参数: {', '.join(missing_required)}\n\n{params_info}",
                "❌ 参数错误：缺少必填参数"
            )

        valid_param_names = set(parameters.keys())
        unknown_params = set(expert_kwargs.keys()) - valid_param_names
        if unknown_params:
            params_info = _get_expert_parameters_info(expert)
            return error_response(
                f"专家 '{expert}' 存在未知参数: {', '.join(unknown_params)}\n\n{params_info}",
                "❌ 参数错误：存在未知参数"
            )

    try:
        result, error = add_task_operation(name, prompt, expert, core, expert_kwargs)

        if error:
            return warning_response(error, f"⚠️ 任务创建失败 | {name}")

        return text_response({
            "task_id": result["task_id"],
            "name": result["name"],
            "message": result["message"]
        }, f"🚀 任务已创建")

    except Exception as e:
        return error_response(f"任务创建异常: {e}", "❌ 创建任务异常")


def _handle_kill(**kwargs) -> str:
    """处理任务终止"""
    task_id = kwargs.get("task_id")

    if not task_id:
        return error_response("缺少必需参数: task_id", "❌ 参数错误：缺少task_id")

    try:
        result, error = kill_task_operation(task_id)

        if error:
            return warning_response(error, "⚠️ 终止失败")

        return text_response({
            "task_id": task_id,
            "message": result["message"]
        }, "⛔ 任务已终止")

    except Exception as e:
        return error_response(f"任务终止异常: {e}", "❌ 终止任务异常")


def _handle_list(**kwargs) -> str:
    """处理任务列表查询"""
    try:
        result, error = list_tasks_operation()

        if error:
            return warning_response(error, "⚠️ 获取列表失败")

        return text_response({
            "tasks": result["tasks"],
            "count": result["count"]
        }, f"📋 {result['count']}个任务")

    except Exception as e:
        return error_response(f"获取任务列表异常: {e}", "❌ 查询异常")