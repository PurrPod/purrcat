BRAINSTORM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "BrainStorm",
        "description": "脑暴与计划编排工具。支持制定主干任务线（Main-Plan）以及异步派发后台子分支线（Sub-Branches）。工具在提交后会立即返回，后台分支完成后会自动通过系统通知告知你。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：'create' (确立计划并派发子分支) 或 'cancel' (强杀运行中的子分支)",
                    "enum": ["create", "cancel"]
                },
                "main_plan": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "action=create时填写。留在主干（也就是你自己）接下来要逐步去 Work 的执行计划（如 Step1.xxx, Step2.xxx）。无前置依赖。"
                },
                "sub_branches": {
                    "type": "array",
                    "description": "action=create时填写。派发到后台并发跑的支线任务清单。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "branch_id": {"type": "string", "description": "简短的标识符，如 b1, b2"},
                            "action": {"type": "string", "description": "指派给打工仔分支的具体任务动作和上下文指导"},
                            "deliverable": {"type": "string", "description": "交付物：要求该分支完结前必须生成的沙盒物理文件路径（如 /agent_vm/api.py）"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "依赖的前置后台 branch_id。无依赖传空数组。"
                            }
                        },
                        "required": ["branch_id", "action", "deliverable", "depends_on"]
                    }
                },
                "target_branch_id": {
                    "type": "string",
                    "description": "action=cancel时必填。你要终止的那个简短子分支 ID (如 b1)。"
                }
            },
            "required": ["action"]
        }
    }
}