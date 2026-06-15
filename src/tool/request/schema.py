"""Request 工具大模型输入结构 - 人类审批请求"""

REQUEST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Request",
        "description": "遇到权限拦截或缺失关键能力时，向人类（老板）发起审批请求。提交后等待老板审批，期间可挂起当前任务。新增技能工厂支持：可通过 skill_create/skill_upgrade 申请建立进化沙盒，开发完毕后通过 skill_merge 申请合并至主库。技能测试 skill_test 可自动在后台执行 evals 并生成报告。",
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
                        "skill_create",  # 新增
                        "skill_upgrade", # 新增
                        "skill_merge",   # 新增
                        "skill_test",    # 新增：测试触发
                    ],
                },
                "target": {
                    "type": "string",
                    "description": "目标对象。文件权限填路径；安装类填插件名；技能开发(skill_create/upgrade/merge)填具体的 skill_name；申请技能测试(skill_test)时必须填写为 'uuid/skill_name' (如 a1b2c/my_skill)。",
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