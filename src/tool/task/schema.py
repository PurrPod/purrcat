TASK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Task",
        "description": "统一任务操作工具，支持后台工作流任务的创建、终止、列表查询，以及向任务注入外部指令",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["add", "kill", "list", "submit_request"],
                },
                "name": {
                    "type": "string",
                    "description": "为该任务起一个简短的名称（action=add 时必填）",
                },
                "graph_name": {
                    "type": "string",
                    "description": "工作流图的名称，如 'default'（action=add 时必填）",
                },
                "inputs": {
                    "type": "object",
                    "description": "传递给该工作流的入口参数字典，包含该工作流要求的所有必要参数（action=add 时必填）",
                },
                "core": {
                    "type": "string",
                    "description": '使用的工人代号，如 "openai:deepseek-v4-flash"（action=add 时可选）',
                },
                "task_id": {
                    "type": "string",
                    "description": "任务ID（action=kill 或 submit_request 时必填）",
                },
                "node_id": {
                    "type": "string",
                    "description": "节点ID（action=submit_request 时可选，如果不填则默认向所有节点广播指令）",
                },
                "content": {
                    "type": "string",
                    "description": "追加或提交的具体指令或内容（action=submit_request 时必填）",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}
