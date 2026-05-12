import os
import json
import importlib
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
                    "description": "'list': 查询当前节点可用的所有业务工具及详情。'execute': 执行具体的业务工具。"
                },
                "tool_name": {
                    "type": "string",
                    "description": "目标业务工具的名称 (当 action 为 'execute' 时必填)"
                },
                "tool_args": {
                    "type": "object",
                    "description": "传递给该业务工具的具体参数对象 (当 action 为 'execute' 时必填)"
                }
            },
            "required": ["action"]
        }
    }
}


def get_system_schema() -> List[dict]:
    """
    获取全局所有的 System Tool Schema，包含:
    1. call_tool (代理拓展工具)
    2. harness 核心工作流工具 (task_done, yield_to_human)
    3. tool 基础任务工具 (bash, search, mcp 等)
    """
    schemas = [CALL_TOOL_SCHEMA]

    # 追加 src/tool/__init__.py 中的基础任务工具
    schemas.extend(BASE_TASK_TOOL_SCHEMA)

    # 动态加载 harness 核心工具
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tools_dir = os.path.join(os.path.dirname(current_dir), "tools")

    if os.path.exists(tools_dir):
        for core_tool in ["task_done", "yield_to_human"]:
            meta_path = os.path.join(tools_dir, core_tool, f"{core_tool}.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        schemas.append(json.load(f))
                except Exception as e:
                    print(f"⚠️ 加载核心工具 Schema 失败 {core_tool}: {e}")

    return schemas


def execute_global_tool(tool_name: str, arguments: dict, context: Any = None) -> Any:
    """
    全局非业务拓展工具的路由执行器：
    根据 tool_name 分发给 Harness 层或底层的 Tool 层
    """
    # 1. 拦截 Harness 工作流核心工具
    if tool_name in ["task_done", "yield_to_human"]:
        try:
            module_path = f"src.harness.tools.{tool_name}.tool"
            module = importlib.import_module(module_path)
            tool_instance = module.Tool(context=context)
            return tool_instance.execute(arguments)
        except Exception as e:
            raise RuntimeError(f"工作流核心工具 '{tool_name}' 执行异常: {str(e)}")

    # 2. 其他工具统一打给 src.tool.utils.route 的底层路由调度器
    else:
        # dispatch_tool 内部已处理了格式化和安全截断，这里直接返回其结果
        return dispatch_tool(tool_name, arguments)


def extract_tool_calling(response) -> list:
    """辅助方法：提取 LLM 响应中的工具调用"""
    if hasattr(response, 'choices') and len(response.choices) > 0:
        return getattr(response.choices[0].message, "tool_calls", []) or []
    return []


def check_tool_call_completed(tool_calls: list) -> bool:
    """辅助方法：检查是否调用了完结任务的核心工具"""
    for tc in tool_calls:
        if tc.function.name in ["task_done", "yield_to_human"]:
            return True
    return False
