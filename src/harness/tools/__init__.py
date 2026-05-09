from .base_tool import BaseToolDispatcher


def get_workflow_tool_schemas():
    """获取核心工具的 schema 定义（task_done、yield_to_human）"""
    return BaseToolDispatcher.get_core_tool_schemas()


def execute_workflow_tool(tool_name: str, arguments: dict, context=None):
    """执行工具（核心工具或业务工具）"""
    return BaseToolDispatcher.dispatch(tool_name, arguments, context)