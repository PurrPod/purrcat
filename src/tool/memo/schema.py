MEMO_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Memo",
        "description": "统一记忆工具，支持写入记忆或搜索记忆。action 参数决定操作类型。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "search"],
                    "description": "操作类型：add=写入记忆，search=搜索记忆"
                },
                "memo_data": {
                    "type": "object",
                    "description": "记忆数据（action=add时必填）。格式：{\"short_term\": \"...\", \"events\": [...], \"work_exp\": [...], \"cognition\": [...], \"reminders\": \"...\", \"project_state\": \"...\"}"
                },
                "query": {
                    "type": "string",
                    "description": "搜索语句（action=search时必填）。描述你想要查找的记忆内容。"
                },
                "filter": {
                    "type": "string",
                    "description": "日期过滤（action=search时可选）。格式 YYYY-MM-DD，如 '2026-05-03'。"
                },
                "topk": {
                    "type": "integer",
                    "description": "返回结果数量（action=search时可选），默认 5。",
                    "default": 5
                }
            },
            "required": ["action"]
        }
    }
}