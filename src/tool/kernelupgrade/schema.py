"""KernelUpgrade 工具大模型输入结构 - Agent自主进化沙盒"""

KERNELUPGRADE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "KernelUpgrade",
        "description": (
            "Agent 的核心自我进化工具，用于在隔离沙盒中创建/升级、合并与测试各类模块。"
            "支持 type：skill（技能）、mcp（MCP Server）、sensor（外部感知器）、graph（任务图）、"
            "agentloop（主循环范式）、ui-plugin（极简模式 UI 插件）。\n"
            "action 语义：\n"
            "- create：在某 type 的隔离沙盒中搭建全新骨架（再读沙盒内 GUIDE.md 开发）；\n"
            "- upgrade：把正式区中已存在的该 type 对象（必要时连带配置）搬进沙盒再改；"
            "注意：MCP 只有源码落在受管 mcps 目录里的才能升级，外部自行下载、仅注册在 mcp_config.json 的 MCP 会报错；\n"
            "- merge：代发合并审批请求（等同原 Request 的 *_merge，仍需用户 Yes/No）；\n"
            "- test：代发/直跑架构级测试（skillTrigger+盲测审批、sensor协议体检、mcp后台并发评测、"
            "agentloop/graph宿主侧静态三重校验，均免审）；ui-plugin 无架构级测试，需你自行在沙盒自测。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "执行的具体操作",
                    "enum": ["create", "upgrade", "merge", "test"],
                },
                "type": {
                    "type": "string",
                    "description": "要操作的对象类型",
                    "enum": [
                        "skill",
                        "mcp",
                        "sensor",
                        "graph",
                        "agentloop",
                        "ui-plugin",
                    ],
                },
                "target": {
                    "type": "string",
                    "description": (
                        "目标对象。一般为名字。特殊情形：\n"
                        "- action='merge'/'test' 填沙盒前缀 'uuid/名字'（skill / sensor / mcp / graph / agentloop 均如此），"
                        "用于唯一定位要合并/测试的沙盒对象。\n"
                        "- action='create'/'upgrade'：type='ui-plugin' 填插件 id（小写字母/数字/-/_）。"
                    ),
                },
            },
            "required": ["action", "type", "target"],
            "additionalProperties": False,
        },
    },
}
