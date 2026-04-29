"""Task 工具主入口 - 统一调度任务创建、通知和终止操作"""

from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.task.exceptions import (
    TaskError,
    InvalidActionError,
    MissingParameterError,
    TaskNotFoundError
)
from src.tool.task.task_operations import (
    add_task_operation,
    inform_task_operation,
    kill_task_operation,
    list_tasks_operation
)


def Task(action: str, **kwargs) -> str:
    """
    统一任务操作接口，支持任务的创建、通知、终止和列表查询
    
    Args:
        action: 操作类型，支持: add（创建任务）、inform（追加指令）、kill（终止任务）、list（列出任务）
    
    针对不同 action 的参数：
        - add: name (必填), prompt (必填), expert (必填), core (可选), expert_kwargs (可选)
        - inform: task_id (必填), action (指令内容，可选，默认为 continue)
        - kill: task_id (必填)
        - list: 无额外参数
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    # 参数校验
    action = action.strip().lower() if action else ""
    
    # 检查操作类型
    if action not in ["add", "inform", "kill", "list"]:
        return error_response(
            f"无效的操作类型: {action}。支持的操作: add, inform, kill, list",
            "参数错误"
        )
    
    # 根据操作类型执行
    if action == "add":
        return _handle_add(**kwargs)
    elif action == "inform":
        return _handle_inform(**kwargs)
    elif action == "kill":
        return _handle_kill(**kwargs)
    elif action == "list":
        return _handle_list(**kwargs)
    
    return error_response("未知错误", "系统错误")


def _handle_add(**kwargs) -> str:
    """处理任务创建"""
    name = kwargs.get("name")
    prompt = kwargs.get("prompt")
    expert = kwargs.get("expert")
    core = kwargs.get("core", "openai:deepseek-v4-flash")
    expert_kwargs = kwargs.get("expert_kwargs")

    # 必填参数检查
    if not name:
        return error_response("缺少必需参数: name", "参数错误")
    if not prompt:
        return error_response("缺少必需参数: prompt", "参数错误")
    if not expert:
        return error_response("缺少必需参数: expert", "参数错误")

    try:
        result, error = add_task_operation(name, prompt, expert, core, expert_kwargs)
        
        if error:
            return warning_response(error, "任务创建失败")
        
        return text_response({
            "task_id": result["task_id"],
            "name": result["name"],
            "message": result["message"]
        }, f"任务 '{name}' 已提交")
    
    except Exception as e:
        return error_response(f"任务创建异常: {e}", "创建异常")


def _handle_inform(**kwargs) -> str:
    """处理任务通知（追加指令）"""
    task_id = kwargs.get("task_id")
    action = kwargs.get("action", "continue")

    if not task_id:
        return error_response("缺少必需参数: task_id", "参数错误")

    try:
        result, error = inform_task_operation(task_id, action)
        
        if error:
            return warning_response(error, "指令注入失败")
        
        return text_response({
            "task_id": task_id,
            "message": result["message"]
        }, f"指令已注入任务 {task_id}")
    
    except Exception as e:
        return error_response(f"指令注入异常: {e}", "注入异常")


def _handle_kill(**kwargs) -> str:
    """处理任务终止"""
    task_id = kwargs.get("task_id")

    if not task_id:
        return error_response("缺少必需参数: task_id", "参数错误")

    try:
        result, error = kill_task_operation(task_id)
        
        if error:
            return warning_response(error, "任务终止失败")
        
        return text_response({
            "task_id": task_id,
            "message": result["message"]
        }, f"任务 {task_id} 已终止")
    
    except Exception as e:
        return error_response(f"任务终止异常: {e}", "终止异常")


def _handle_list(**kwargs) -> str:
    """处理任务列表查询"""
    try:
        result, error = list_tasks_operation()
        
        if error:
            return warning_response(error, "获取任务列表失败")
        
        return text_response({
            "tasks": result["tasks"],
            "count": result["count"]
        }, f"共 {result['count']} 个任务")
    
    except Exception as e:
        return error_response(f"获取任务列表异常: {e}", "查询异常")