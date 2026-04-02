import json
from typing import Any




def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def task_done(summary: str) -> str:
    """结束当前任务并交付结果"""
    return _format_response("task_done", {"summary": summary})


def update_plan(plan: str = "", current_step: str = "", steps: list = None) -> str:
    """更新当前任务的执行计划"""
    return _format_response("update_plan", {
        "plan": plan,
        "current_step": current_step,
        "steps": steps or []
    })

TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task_done",
            "description": "结束当前任务并交付结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "任务完成的摘要说明"}
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": "更新当前任务的执行计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {"type": "string", "description": "整体执行计划的描述"},
                    "current_step": {"type": "string", "description": "当前正在执行的具体步骤"},
                    "steps": {
                        "type": "array",
                        "description": "计划的具体步骤列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_name": {"type": "string", "description": "步骤名称"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"],
                                           "description": "步骤状态"},
                                "description": {"type": "string", "description": "步骤的详细说明或执行结果"}
                            },
                            "required": ["step_name", "status"]
                        }
                    }
                },
                "required": ["plan", "steps"]
            }
        }
    }
]

TASK_TOOL_FUNCTIONS = {
    "task_done": task_done,
    "update_plan": update_plan,
}

from src.models.task import Task
def call_task_tool(tool_name: str, arguments: dict, task: Task) -> str:
    if tool_name not in TASK_TOOL_FUNCTIONS:
        return _format_response("error", f"未知的 Task 工具: {tool_name}")
    func = TASK_TOOL_FUNCTIONS[tool_name]
    try:
        result = func(**arguments)

        if tool_name == "task_done":
            task.state = "completed"
            task.log_and_notify("success", f"✅ 任务圆满完成: {arguments.get('summary', '无交付说明')}")
            task.save_checkpoint()
        elif tool_name == "update_plan":
            task.current_plan = arguments
            task.log_and_notify("plan", f"📋 Agent 更新了计划:\n{json.dumps(arguments, ensure_ascii=False, indent=2)}")

        return result
    except Exception as e:
        return _format_response("error", f"工具执行异常: {str(e)}")
