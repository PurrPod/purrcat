FETCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Fetch",
        "description": "统一获取工具，支持获取网页内容、加载技能文件、获取 MCP 工具 Schema、读取 HARNESS.md 和 TODO.md",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "获取来源：web（网页内容）、skill（技能文件）、mcp（MCP工具）、harness（HARNESS.md）、todo（TODO.md）",
                    "enum": ["web", "skill", "mcp", "harness", "todo"]
                },
                "url": {
                    "type": "string",
                    "description": "网页地址（source=web 时必填）"
                },
                "name": {
                    "type": "string",
                    "description": "技能名称（source=skill 时必填）"
                },
                "server_name": {
                    "type": "string",
                    "description": "MCP 服务器名称（source=mcp 时必填）"
                },
                "tool_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要获取的工具名称列表（source=mcp 时可选，不填则获取所有工具）"
                }
            },
            "required": ["source"],
            "additionalProperties": False
        }
    }
}