"""Request 工具大模型输入结构 - 人类审批请求"""

REQUEST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Request",
        "description": "遇到权限拦截或缺失关键能力时，向人类（老板）发起审批请求。提交后等待老板审批，期间可挂起当前任务。技能工厂流程：skill_test 提交后 Trigger 激发测试立即免审运行，后台盲测部分需老板批准后由系统自动运行（本地无 skill_eval 图时自动跳过盲测），测试通过再申请 skill_merge 合并至主库。",
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
                        "computer_use",
                        "skill_test",  # Skill 盲测：批准后由系统自动运行
                        "skill_merge",  # 保留：合并代码仍需审批
                        "mcp_merge",  # 新增：MCP 代码合并
                    ],
                },
                "target": {
                    "type": "string",
                    "description": "目标对象。文件权限填路径；安装类填插件名；申请技能盲测(skill_test)填沙盒工作区前缀 'uuid/技能名'；申请代码合并(skill_merge/mcp_merge)填具体的插件名。",
                },
                "reason": {
                    "type": "string",
                    "description": "申请理由，明确告诉老板为什么需要这个权限或操作。若是 skill_merge 请简述你的修改点供人类 Code Review。",
                },
            },
            "required": ["request_type", "target", "reason"],
            "additionalProperties": False,
        },
    },
}
