"""Request 工具大模型输入结构 - 人类审批请求"""

REQUEST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Request",
        "description": "遇到权限拦截、需要人类审批的操作时，向人类（用户）发起审批请求。提交后等待用户审批，期间可挂起当前任务。仅用于读写宿主机文件（file_read / file_write）。注意：各类进化工厂的测试与合并（skill_test / sensor_test / *_merge 等）已从本工具剥离，请改用 KernelUpgrade(action='test'/'merge', type=..., target=...) 代发。",
        "parameters": {
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "description": "申请的具体类型",
                    "enum": [
                        "file_write",
                        "file_read",
                    ],
                },
                "target": {
                    "type": "string",
                    "description": "目标对象：文件权限填文件路径。",
                },
                "reason": {
                    "type": "string",
                    "description": "申请理由，用一两句话简要说明即可。",
                },
            },
            "required": ["request_type", "target", "reason"],
            "additionalProperties": False,
        },
    },
}
