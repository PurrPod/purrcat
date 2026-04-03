import json
from typing import Any
from src.models.task import Task


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def task_done(result: bool, summary: str) -> str:
    """结束当前任务并交付结果"""
    return _format_response("task_done", {"result": result, "summary": summary})


def update_plan(**kwargs) -> str:
    """这个只是占位函数，实际状态管理会在 call_task_tool 内部拦截和处理"""
    pass


# ---------------------------------------------------------
# 1. 重构工具 Schema，支持精确的增删改查
# ---------------------------------------------------------
TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task_done",
            "description": "结束当前任务并交付结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "boolean", "description": "任务是否成功完成"},
                    "summary": {"type": "string", "description": "任务的摘要说明"}
                },
                "required": ["result", "summary"]
            }
        }
    },
    {
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
                        "description": "要执行的操作: init(全新初始化计划), add_step(新增步骤), update_step(修改步骤), complete_step(标记某步完成), delete_step(删除步骤)"
                    },
                    "overall_goal": {
                        "type": "string",
                        "description": "整体计划目标 (action为 init 时必填)"
                    },
                    "init_steps": {
                        "type": "array",
                        "description": "初始步骤列表 (仅 action为 init 时可用，可一次性批量下发多个步骤)",
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
                        "description": "操作的目标步骤ID (action为 update_step, complete_step, delete_step 时必填)"
                    },
                    "step_title": {
                        "type": "string",
                        "description": "步骤标题 (action为 add_step, update_step 时填写)"
                    },
                    "step_description": {
                        "type": "string",
                        "description": "步骤详细描述 (action为 add_step, update_step 时填写)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "手动设置步骤状态 (action为 update_step 时填写)"
                    }
                },
                "required": ["action"]
            }
        }
    }
]

TASK_TOOL_FUNCTIONS = {
    "task_done": task_done,
    "update_plan": update_plan,
}


def call_task_tool(tool_name: str, arguments: dict, task: Task) -> str:
    if tool_name not in TASK_TOOL_FUNCTIONS:
        return _format_response("error", f"未知的 Task 工具: {tool_name}")

    try:
        if tool_name == "task_done":
            func = TASK_TOOL_FUNCTIONS[tool_name]
            result = func(**arguments)
            task.state = "completed"
            is_success = arguments.get('result', True)
            summary = arguments.get('summary', '无交付说明')
            if is_success:
                task.log_and_notify("success", f"✅ 任务圆满完成: {summary}")
            else:
                task.log_and_notify("error", f"❌ 任务失败: {summary}")
            task.save_checkpoint()
            return result

        elif tool_name == "update_plan":
            # ---------------------------------------------------------
            # 2. 状态管理器拦截逻辑
            # ---------------------------------------------------------
            current_plan_dict = {"overall_goal": "未设定", "steps": [], "next_id": 1}

            # 安全解析 task.current_plan（防范它是字符串或字典的各种情况）
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

            # 处理具体的 CRUD 操作
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
                found = False
                for step in current_plan_dict["steps"]:
                    if step["id"] == sid:
                        if "step_title" in arguments: step["title"] = arguments["step_title"]
                        if "step_description" in arguments: step["description"] = arguments["step_description"]
                        if "status" in arguments: step["status"] = arguments["status"]
                        found = True
                        break
                if not found: return _format_response("error", f"未找到ID为 {sid} 的步骤")

            elif action == "complete_step":
                sid = arguments.get("step_id")
                found = False
                for step in current_plan_dict["steps"]:
                    if step["id"] == sid:
                        step["status"] = "completed"
                        found = True
                        break
                if not found: return _format_response("error", f"未找到ID为 {sid} 的步骤")

            elif action == "delete_step":
                sid = arguments.get("step_id")
                current_plan_dict["steps"] = [s for s in current_plan_dict["steps"] if s["id"] != sid]

            # 序列化为 JSON 保存到 Task 中（避免直接存对象导致旧版本的 checkpoint 崩溃）
            task.current_plan = json.dumps(current_plan_dict, ensure_ascii=False)
            task.save_checkpoint()

            # 将计划格式化为友好的 Markdown 用于系统日志和回传给大模型
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

            # 记录 UI/文件日志
            task.log_and_notify("plan", f"📋 Agent 更新了计划 [{action}]:\n{md_plan}")

            # 将当前最新状态回传给大模型，让它知道操作成功且能看到全貌
            return _format_response("plan_updated", f"✅ 操作 '{action}' 成功！当前最新计划表如下：\n{md_plan}")

    except Exception as e:
        return _format_response("error", f"工具执行异常: {str(e)}")