"""Task 工具大模型输入结构"""

TASK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Task",
        "description": "统一任务操作工具，支持：1.列出可用图(list_graphs) 2.查询当前任务列表(list_tasks) 3.创建任务(add) 4.终止任务(kill) 5.向任务节点注入人工指令(submit_request) 6.查询任务的交互节点列表及状态(get_details) 7.视觉顾问(vision，接收图片/视频/音频附件，可作为 ComputerUse 识别失败时的兜底，也可对前端/矢量图/PPT 等成果做错位乱码质检)。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": [
                        "list_graphs",
                        "list_tasks",
                        "add",
                        "kill",
                        "submit_request",
                        "get_details",
                        "vision",
                    ],
                },
                "name": {
                    "type": "string",
                    "description": "为该任务起一个简短的名称（action=add 时必填）",
                },
                "graph_name": {
                    "type": "string",
                    "description": "工作流图的名称，可用 list_graphs 列出可用图（action=add 时必填）",
                },
                "inputs": {
                    "type": "object",
                    "description": "传递给该工作流的入口参数字典，包含图要求的所有必要参数（action=add 时必填）",
                },
                "task_id": {
                    "type": "string",
                    "description": "任务ID（action=kill, submit_request 或 get_details 时必填）",
                },
                "node_id": {
                    "type": "string",
                    "description": "节点ID（action=submit_request 时【绝对必填】。必须明确指定要向哪个具体的 Agent 节点注入指令，不支持全局广播）",
                },
                "content": {
                    "type": "string",
                    "description": "追加或提交的具体人工指令内容（action=submit_request 时必填）",
                },
                "attachment_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "仅 action=vision 使用。附件路径数组，支持图片/视频/音频，用于多模态联合分析。支持沙盒路径（以 /agent_vm/ 开头）与宿主机本地路径。",
                },
                "prompt": {
                    "type": "string",
                    "description": "仅 action=vision 使用。视觉顾问的提示词指令。明确告诉顾问要看/听什么、关心哪种问题（如按钮识别/错位/乱码/音视频内容理解）、要建议还是只要描述，prompt 越具体诊断越准。",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}
