from typing import Any, List

from src.tool.utils.route import dispatch_tool


def get_system_schema() -> List[dict]:
    """
    获取全局所有的 System Tool Schema
    包含: tool 基础任务工具 (bash, search, mcp 等)
    注意: harness 工作流原语工具已经交由 BaseNode 本身进行挂载。
    """
    # 延迟导入避免循环依赖
    from src.tool import BASE_TASK_TOOL_SCHEMA

    return list(BASE_TASK_TOOL_SCHEMA)


def execute_global_tool(tool_name: str, arguments: dict, context: Any = None) -> Any:
    """
    全局非业务拓展工具的路由执行器：直接打给底层路由
    context.model.vision=True 时开启 vision 直注（工具输出图片不落盘直接注入对话）
    """
    vision_mode = bool(getattr(getattr(context, "model", None), "vision", False))
    return dispatch_tool(tool_name, arguments, vision_mode=vision_mode)


def extract_tool_calling(response) -> list:
    """辅助方法：提取 LLM 响应中的工具调用"""
    if hasattr(response, "choices") and len(response.choices) > 0:
        return getattr(response.choices[0].message, "tool_calls", []) or []
    return []
