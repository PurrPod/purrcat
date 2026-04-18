import json

PLAN_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_plan",
        "description": "任务计划管理器。支持增删改查。请利用此工具细化和维护你的工作流。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["init", "add_step", "update_step", "complete_step", "delete_step"],
                    "description": "要执行的操作: init(全新初始化), add_step(新增), update_step(修改), complete_step(完成), delete_step(删除)"
                },
                "overall_goal": {
                    "type": "string",
                    "description": "整体计划目标 (action为 init 时必填)"
                },
                "init_steps": {
                    "type": "array",
                    "description": "初始步骤列表 (仅 action为 init 时可用)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "步骤标题"},
                            "description": {"type": "string", "description": "步骤详情说明"}
                        },
                        "required": ["title"]
                    }
                },
                "step_id": {
                    "type": "integer",
                    "description": "操作的目标步骤ID (action为 update/complete/delete 时必填)"
                },
                "step_title": {
                    "type": "string",
                    "description": "步骤标题"
                },
                "step_description": {
                    "type": "string",
                    "description": "步骤详细描述"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "手动设置步骤状态"
                }
            },
            "required": ["action"]
        }
    }
}


def execute_update_plan(arguments: dict, task) -> str:
    """处理计划更新逻辑，并直接修改传入的 task 实例状态"""
    current_plan_dict = {"overall_goal": "未设定", "steps": [], "next_id": 1}

    if isinstance(task.current_plan, dict):
        current_plan_dict = task.current_plan
    elif isinstance(task.current_plan, str) and task.current_plan.strip():
        try:
            parsed = json.loads(task.current_plan)
            if "steps" in parsed:
                current_plan_dict = parsed
        except json.JSONDecodeError:
            pass

    action = arguments.get("action", "init")

    if action == "init":
        current_plan_dict["overall_goal"] = arguments.get("overall_goal", current_plan_dict["overall_goal"])
        current_plan_dict["steps"] = []
        current_plan_dict["next_id"] = 1
        for step in arguments.get("init_steps", []):
            current_plan_dict["steps"].append({
                "id": current_plan_dict["next_id"],
                "title": step.get("title", "未命名步骤"),
                "description": step.get("description", ""),
                "status": "pending"
            })
            current_plan_dict["next_id"] += 1
    elif action == "add_step":
        current_plan_dict["steps"].append({
            "id": current_plan_dict["next_id"],
            "title": arguments.get("step_title", "未命名步骤"),
            "description": arguments.get("step_description", ""),
            "status": "pending"
        })
        current_plan_dict["next_id"] += 1
    elif action == "update_step":
        sid = arguments.get("step_id")
        for step in current_plan_dict["steps"]:
            if step["id"] == sid:
                if "step_title" in arguments: step["title"] = arguments["step_title"]
                if "step_description" in arguments: step["description"] = arguments["step_description"]
                if "status" in arguments: step["status"] = arguments["status"]
    elif action == "complete_step":
        sid = arguments.get("step_id")
        for step in current_plan_dict["steps"]:
            if step["id"] == sid:
                step["status"] = "completed"
    elif action == "delete_step":
        sid = arguments.get("step_id")
        current_plan_dict["steps"] = [s for s in current_plan_dict["steps"] if s["id"] != sid]

    # 保存状态
    task.current_plan = json.dumps(current_plan_dict, ensure_ascii=False)
    task.save_checkpoint()

    # 渲染 Markdown 日志
    md_plan = f"🎯 **总目标**: {current_plan_dict.get('overall_goal', '未设置')}\n\n"
    if not current_plan_dict.get("steps"):
        md_plan += "暂无具体步骤"
    else:
        md_plan += "📋 **执行计划**:\n"
        for s in current_plan_dict["steps"]:
            status_icon = "✅" if s["status"] == "completed" else ("🏃" if s["status"] == "in_progress" else "⏳")
            md_plan += f"{status_icon} **[ID: {s['id']}]** {s['title']} ({s['status']})\n"
            if s.get("description"):
                md_plan += f"    📝 {s['description']}\n"

    task.log_and_notify("plan", f"📋 Agent 更新了计划 [{action}]:\n{md_plan}")

    response_data = {"type": "plan_updated", "content": f"✅ 操作 '{action}' 成功！"}
    return json.dumps(response_data, ensure_ascii=False)