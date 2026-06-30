MEMO_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Memo",
        "description": "统一记忆工具，处理短期记忆压缩与长期记忆（经验、用户画像、事件、认知）的归档与检索。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "search"],
                    "description": "操作类型：add=写入记忆，search=搜索记忆",
                },
                "memo_data": {
                    "type": "object",
                    "description": "记忆数据（action=add时必填）。",
                    "properties": {
                        "short_term": {
                            "type": "string",
                            "description": "短期工作记忆，将作为新的上下文返回给接下来的对话。⚠️注意：该字段仅做临时缓存跨越对话断层，【绝对不会】被存入长期记忆库，请勿在此存放需要长久记住的重要信息！",
                        },
                        "work_exp": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "工作与任务中沉淀的高价值通用经验。绝对禁止记录流水账、数据统计或单次任务的特定细节（这些应放入 events）！"
                                "写入内容必须涵盖：【场景与问题】遇到了什么通用性问题 -> 【解决方案】是如何解决的 -> 【复用启示】未来遇到类似情况应如何处理。"
                                "取舍原则：只有当你认为这个经验在未来做其他完全不同的任务时依然有指导意义，才应该记录在这里。"
                            ),
                        },
                        "user_profile": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "对用户的新认识，包括喜好、风格等",
                        },
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "time": {
                                        "type": "string",
                                        "description": "时间，请必须使用精确到分钟的格式，如 YYYY-MM-DD HH:MM",
                                    },
                                    "event": {
                                        "type": "string",
                                        "description": "事件描述",
                                    },
                                },
                            },
                            "description": "最近发生的事件，大大小小越多越好",
                        },
                        "cognition": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "对世界的新认知",
                        },
                    },
                },
                "query": {
                    "type": "object",
                    "description": "搜索参数（action=search时使用）。如果不传，则直接返回最近五次写入的缓存记忆。如果传，必须包含 prompt 或 date 其中之一。",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "全局搜索关键词，不限日期",
                        },
                        "date": {
                            "type": "string",
                            "description": "日期过滤，格式 YYYY-MM-DD",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认 5",
                        },
                    },
                },
            },
            "required": ["action"],
        },
    },
}
