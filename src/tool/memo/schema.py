MEMO_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Memo",
        "description": "统一记忆工具，处理短期记忆压缩与长期记忆（经验、用户画像、事件、认知）的归档。",
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
                    "description": "记忆数据（action=add时必填）。",
                    "properties": {
                        "short_term": {"type": "string", "description": "短期工作记忆，将作为新的上下文返回给对话"},
                        "work_exp": {"type": "array", "items": {"type": "string"}, "description": "工作中积累的经验教训"},
                        "user_profile": {"type": "array", "items": {"type": "string"}, "description": "对用户的新认识，包括喜好、风格等"},
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "time": {"type": "string", "description": "时间，如 20200601"},
                                    "event": {"type": "string", "description": "事件描述"}
                                }
                            },
                            "description": "最近发生的事件，大大小小越多越好"
                        },
                        "cognition": {"type": "array", "items": {"type": "string"}, "description": "对世界的新认知"}
                    }
                },
                "query": {
                    "type": "string",
                    "description": "搜索语句（action=search时必填）。"
                },
                "filter": {
                    "type": "string",
                    "description": "日期过滤（action=search时可选）。格式 YYYY-MM-DD"
                },
                "topk": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5。",
                    "default": 5
                }
            },
            "required": ["action"]
        }
    }
}