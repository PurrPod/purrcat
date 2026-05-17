from typing import Any, List

# 导入底层基础工具 Schema 和 路由分发器
from src.tool import BASE_TASK_TOOL_SCHEMA
from src.tool.utils.route import dispatch_tool

# 🌟 全局唯一且固定的拓展业务工具代理入口
CALL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "call_tool",
        "description": "业务拓展工具的通用入口。当你需要执行特定业务逻辑时使用。请先通过 action='list' 查询当前可用工具，了解其参数要求后，再通过 action='execute' 传入 tool_name 和 tool_args 进行调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["execute", "list"],
                    "description": "'list': 查询当前节点可用的所有业务工具及详情。'execute': 执行具体的业务工具。",
                },
                "tool_name": {
                    "type": "string",
                    "description": "目标业务工具的名称 (当 action 为 'execute' 时必填)",
                },
                "tool_args": {
                    "type": "object",
                    "description": "传递给该业务工具的具体参数对象 (当 action 为 'execute' 时必填)",
                },
            },
            "required": ["action"],
        },
    },
}


def get_system_schema() -> List[dict]:
    """
    获取全局所有的 System Tool Schema，包含:
    1. call_tool (代理拓展工具)
    2. tool 基础任务工具 (bash, search, mcp 等)
    注意: harness 工作流原语工具已经交由 BaseNode 本身进行挂载。
    """
    schemas = [CALL_TOOL_SCHEMA]
    schemas.extend(BASE_TASK_TOOL_SCHEMA)
    return schemas


def execute_global_tool(tool_name: str, arguments: dict, context: Any = None) -> Any:
    """
    全局非业务拓展工具的路由执行器：直接打给底层路由
    """
    return dispatch_tool(tool_name, arguments)


def extract_tool_calling(response) -> list:
    """辅助方法：提取 LLM 响应中的工具调用"""
    if hasattr(response, "choices") and len(response.choices) > 0:
        return getattr(response.choices[0].message, "tool_calls", []) or []
    return []
