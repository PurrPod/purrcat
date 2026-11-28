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
                    "enum": ["add", "search", "reinforce", "replace", "delete"],
                    "description": (
                        "操作类型：add=写入记忆，search=搜索记忆，"
                        "reinforce=提升某条经验的置信度，replace=覆盖某条经验内容，"
                        "delete=删除某条经验"
                    ),
                },
                "memo_data": {
                    "type": "object",
                    "description": "记忆数据（action=add时必填）。",
                    "properties": {
                        "short_term": {
                            "type": "string",
                            "description": "短期工作记忆，将作为新的上下文返回给接下来的对话。注意：该字段仅做临时缓存跨越对话断层，绝对不会被存入长期记忆库，请勿在此存放需要长久记住的重要信息！",
                        },
                        "work_exp": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "高价值通用经验。每条只写「何时何地怎么做」："
                                "何时何地在什么场景、条件下 -> 怎么做应采取的具体做法。"
                                "每条 40~80 字、最多 2 句，只保留一个可复用结论；"
                                "不写背景铺垫、过程复述、数据统计、单次任务细节和心得体会。"
                                "只有该经验在未来其他任务中依然有指导意义时才记录。"
                            ),
                        },
                        "user_profile": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "对用户长期稳定的认识：画像、偏好、习惯、要求。"
                                "每条一句话、不超过 40 字，只写一个事实；不写一次性细节或推测。"
                            ),
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
                                        "description": (
                                            "事件描述。每条只写一个客观事实，不超过 60 字、最多 2 句；"
                                            "禁止把多件事合并成一条，禁止背景铺陈、过程复述和情绪化表达。"
                                        ),
                                    },
                                },
                            },
                            "description": (
                                "最近发生的事件。当天发生的事尽量写全，但必须一条一件、短句陈述，"
                                "禁止长篇大段或流水账。"
                            ),
                        },
                        "cognition": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "对世界的新认知",
                        },
                    },
                },
                "experience_id": {
                    "type": "string",
                    "description": "经验 ID（action=reinforce/replace/delete 时必填），形如 exp_xxx；搜索结果中会返回。",
                },
                "content": {
                    "type": "string",
                    "description": "新的经验内容（action=replace 时必填）。",
                },
                "query": {
                    "type": "object",
                    "description": "搜索参数（action=search时使用）。如果不传，则直接返回最近三次写入的缓存记忆。如果传，必须包含 prompt 或 date 其中之一。搜索结果会附带经验 ID 与置信度，事件相关度为向量余弦相似度。",
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
