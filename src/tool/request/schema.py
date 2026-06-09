"""Request 工具大模型输入结构 - 人类审批请求"""

REQUEST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Request",
        "description": "当遇到权限拦截（读写宿主机文件）或缺失关键能力（需下载 mcp/skill/sensor/graph）时，向人类（老板）发起审批请求。提交后等待老板的系统通知，期间可挂起当前任务或执行与该请求无强依赖的其他工作。",
        "parameters": {
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "description": "申请的具体类型",
                    "enum": [
                        "mcp_install",
                        "skill_install",
                        "file_write",
                        "file_read",
                        "sensor_install",
                        "graph_install",
                    ],
                },
                "target": {
                    "type": "string",
                    "description": "目标对象。文件权限类为宿主机绝对/相对路径，install 安装类为目标插件/模块名称",
                },
                "reason": {
                    "type": "string",
                    "description": "申请理由，明确告诉老板为什么需要这个权限或插件，用来干什么",
                },
            },
            "required": ["request_type", "target", "reason"],
            "additionalProperties": False,
        },
    },
}
