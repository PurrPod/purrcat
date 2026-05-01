SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Search",
        "description": "统一搜索工具，支持互联网搜索与本地库搜索（技能与MCP工具）",
        "parameters": {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": "搜索路由：web（互联网搜索）、local（本地技能库与MCP工具搜索）",
                    "enum": ["web", "local"]
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