SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Search",
        "description": "统一搜索工具，支持互联网搜索、技能搜索和 MCP 服务器搜索",
        "parameters": {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": "搜索路由：web（互联网搜索）、skill（技能搜索）、mcp（MCP服务器搜索）",
                    "enum": ["web", "skill", "mcp"]
                },
                "query": {
                    "type": "string",
                    "description": "搜索查询词"
                },
                "topk": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["route", "query"],
            "additionalProperties": False
        }
    }
}