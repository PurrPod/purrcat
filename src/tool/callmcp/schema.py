MCP_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "CallMCP",
        "description": "调用 MCP 服务器上的工具执行特定任务",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "MCP 服务器名称（可通过 Search 或 Fetch 获取）"
                },
                "tool_name": {
                    "type": "string",
                    "description": "工具名称"
                },
                "arguments": {
                    "type": "object",
                    "description": "工具的参数字典"
                }
            },
            "required": ["server_name", "tool_name"],
            "additionalProperties": False
        }
    }
}