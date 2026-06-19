"""KernelUpgrade 工具大模型输入结构 - Agent自主进化沙盒"""

KERNELUPGRADE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "KernelUpgrade",
        "description": "Agent 的核心自我进化工具。用于在隔离沙盒中自由地创建、升级和测试代码模块（目前支持 Skill 和 MCP Server）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "执行的具体操作",
                    "enum": ["create_skill", "upgrade_skill", "test_skill", "create_mcp", "upgrade_mcp", "test_mcp"]
                },
                "target": {
                    "type": "string",
                    "description": "目标对象。当 action 为 'create_skill', 'upgrade_skill' 或 'create_mcp' 时，填写具体的名称；当 action 为 'test_skill' 或 'test_mcp' 时，必须严格填写为当前沙盒的路径前缀 'uuid/name'。"
                }
            },
            "required": ["action", "target"],
            "additionalProperties": False,
        },
    },
}