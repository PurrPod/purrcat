import json
from typing import Any
from src.harness.task import BaseTask

def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)

def task_done(result: bool, summary: str) -> str:
    """结束当前任务并交付结果"""
    return _format_response("task_done", {"result": result, "summary": summary})

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
    }
]

TASK_TOOL_FUNCTIONS = {
    "task_done": task_done,
}

def call_task_tool(tool_name: str, arguments: dict, task) -> str:
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
    except Exception as e:
        return _format_response("error", f"工具执行异常: {str(e)}")