TASK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Task",
        "description": "统一任务操作工具，支持任务的创建、终止和列表查询",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["add", "kill", "list"]
                },
                "name": {
                    "type": "string",
                    "description": "任务名称（action=add 时必填）"
                },
                "prompt": {
                    "type": "string",
                    "description": "任务提示（action=add 时必填）"
                },
                "expert": {
                    "type": "string",
                    "description": "专家类型（action=add 时必填）"
                },
                "core": {
                    "type": "string",
                    "description": "使用的工人代号，如 \"openai:deepseek-v4-flash\"（action=add 时可选）"
                },
                "expert_kwargs": {
                    "type": "object",
                    "description": "专家额外参数（action=add 时可选）"
                },
                "task_id": {
                    "type": "string",
                    "description": "任务ID（action=kill 时必填）"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    }
}