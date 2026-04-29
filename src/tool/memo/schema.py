MEMO_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Memo",
        "description": "更新系统备忘录。short_term 必须提供（当前工作上下文），其余字段为结构化长期记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "short_term": {
                    "type": "string",
                    "description": "短期工作状态：当前处理的任务细节、挂起步骤、临时变量等即时上下文。必填。"
                },
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "string", "description": "事件发生时间，格式 YYYYMMDDHHMM，如 202604271500"},
                            "event": {"type": "string", "description": "事件描述"}
                        },
                        "required": ["time", "event"]
                    },
                    "description": "事件记录：每条包含 time（格式YYYYMMDDHHMM）和 event 描述。记录发生过的事实、对话、操作。"
                },
                "work_exp": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "经验增长：每条一句简短经验。用户偏好、避坑教训、有效工作模式等可复用的沉淀。"
                },
                "cognition": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "认知记录：每条一句简短认知，包含事物本身及其联系。如 'Chroma是向量数据库，通过语义相似度检索，适合长期记忆存储'。"
                },
                "reminders": {
                    "type": "string",
                    "description": "待办提醒：需要后续跟进的未完成任务、待处理事项。"
                },
                "project_state": {
                    "type": "string",
                    "description": "项目状态：当前项目的整体进度、关键上下文、已完成和待完成的工作。"
                }
            },
            "required": ["short_term"]
        }
    }
}