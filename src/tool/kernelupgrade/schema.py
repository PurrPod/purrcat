"""KernelUpgrade 工具大模型输入结构 - Agent自主进化沙盒"""

KERNELUPGRADE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "KernelUpgrade",
        "description": "Agent 的核心自我进化工具。用于在隔离沙盒中自由地创建、升级和测试代码模块（目前支持 Skill，未来将扩展 MCP 等）。此工具为即时执行，无需人类审批。开发与测试完毕后，需通过 Request 工具申请合并至主库。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "执行的具体操作",
                    "enum": ["create_skill", "upgrade_skill", "test_skill"]
                },
                "target": {
                    "type": "string",
                    "description": "目标对象。当 action 为 'create_skill' 或 'upgrade_skill' 时，填写具体的 skill_name；当 action 为 'test_skill' 时，必须严格填写为当前沙盒的路径前缀 'uuid/skill_name' (例如 a5d0d/my_skill)。"
                }
            },
            "required": ["action", "target"],
            "additionalProperties": False,
        },
    },
}