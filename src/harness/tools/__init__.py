from .base_tool import BaseToolDispatcher
from src.tool import BASE_TASK_TOOL_SCHEMA


def get_workflow_tool_schemas():
    """获取保底工具的 schema 定义（核心工具 + 基础任务工具）"""
    core_schemas = BaseToolDispatcher.get_core_tool_schemas()
    
    # 去重处理：确保基础任务工具不会与核心工具重复
    core_names = {schema["function"]["name"] for schema in core_schemas}
    filtered_base_task = [
        schema for schema in BASE_TASK_TOOL_SCHEMA
        if schema["function"]["name"] not in core_names
    ]
    
    return core_schemas + filtered_base_task


def execute_workflow_tool(tool_name: str, arguments: dict, context=None):
    """执行工具（核心工具、基础任务工具或业务工具）"""
    return BaseToolDispatcher.dispatch(tool_name, arguments, context)