import json
import os
from typing import Any
from src.utils.config import TOOL_INDEX_FILE


def _format_response(msg_type: str, content: Any) -> str:
    """确保内部所有报错调度也符合统一格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def parse_tool(tool_name: str, arguments: dict, route: str = None, plugin: str = None) -> tuple[str, list]:
    """
    核心枢纽：统一处理工具调用的路由和执行。
    """
    new_schema_info = None
    result_content = ""
    try:
        # 1. 尝试将请求路由给 base_tool
        from src.plugins.route.base_tool import BASE_TOOL_NAMES, call_base_tool
        if tool_name in BASE_TOOL_NAMES or tool_name == "close_shell":
            result_content, new_schema_info = call_base_tool(tool_name, arguments)

        # 2. 如果不是 base_tool，走具体的路由和 Agent 逻辑
        else:
            from src.plugins.route.agent_tool import AGENT_TOOL_FUNCTIONS
            if tool_name in AGENT_TOOL_FUNCTIONS:
                from src.plugins.route.agent_tool import call_agent_tool
                result_content = call_agent_tool(tool_name, arguments)
            else:
                # 动态探活寻找正确的 Route 与 Plugin
                if not route or not plugin:
                    if os.path.exists(TOOL_INDEX_FILE):
                        with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                tool_info = json.loads(line)
                                if tool_info["func"] == tool_name:
                                    route = tool_info["route"]
                                    plugin = tool_info["plugin"]
                                    break

                # 路由分发
                if route == "local":
                    from src.plugins.route.local_tool import call_local_tool
                    result_content = call_local_tool(plugin, tool_name, arguments)
                elif route == "mcp":
                    from src.plugins.route.mcp_tool import call_mcp_tool
                    result_content = call_mcp_tool(plugin, tool_name, arguments)
                else:
                    result_content = _format_response("error", f"❌ 调度失败：未找到 {tool_name} 的底层路由映射。请确认它是否通过 fetch_tool 正常加载。")

    except Exception as e:
        result_content = _format_response("error", f"❌ 工具调度/执行异常: {str(e)}")

    return str(result_content), new_schema_info