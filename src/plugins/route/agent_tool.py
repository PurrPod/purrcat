import importlib
import json
import threading
from typing import Any

from src.models.task import Task
from src.utils.config import get_models_config


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)

def add_task(
        name: str,
        prompt: str,
        core: str = "[1]openai:deepseek-chat",
        judger: str = "[1]openai:deepseek-chat"
) -> str:
    single_task = Task(
        task_name=name,
        prompt=prompt,
        core=core,
        judger=judger,
    )
    def _run_task():
        from src.agent.agent import add_message
        try:
            result = single_task.run()
            task_id = single_task.task_id
            notify_msg = f"🔔 [系统通知] 后台子任务 '{name}' (ID: {task_id}) 已执行完毕。结果交付如下：\n{result}"
            add_message({"type": "task_message", "content": notify_msg})
        except Exception as e:
            single_task.state = "error"
            error_msg = f"❌ [系统通知] 您派发的后台子任务 '{name}' (ID: {single_task.task_id})执行崩溃，原因: {e}"
            add_message({"type": "task_message", "content": error_msg})
    t = threading.Thread(target=_run_task, daemon=True)
    t.start()
    return _format_response("text", (
        f"✅ 任务 '{name}' 已提交到后台线程执行。\n"
        f"ID : {single_task.task_id}\n"
        f"请注意：任务不会立即完成。您可以继续处理其他事务，系统会在执行完毕后发消息通知您"
    ))


def list_worker() -> str:
    """获取当前所有可用的工人及其描述的清单。"""
    models = get_models_config()
    model_list = [f"\"{model_name}\" | {models[model_name]['description']}\n" for model_name in models.keys()]
    if not model_list:
        return _format_response("text", "无可用工人")
    return _format_response("text", "".join(model_list))


def send_message(channel: str, content: str, mode: str) -> str:
    """通过指定渠道发送消息"""
    try:
        module_path = f"src.sensor.{channel}"
        plugin_module = importlib.import_module(module_path)
        funct_name = f"send_{channel}_message"
        target_func = getattr(plugin_module, funct_name)
        return target_func(content, mode)
    except Exception as e:
        return _format_response("error", f"发送失败：{e}")


# AGENT_TOOLS schema 定义
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "启动一个后台子任务以提高工作效率",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "任务标题"},
                    "prompt": {"type": "string", "description": "系统提示"},
                    "core": {"type": "string", "description": "使用的核心模型，如\"[2]openai:deepseek-chat\"，可用list_worker查看"}
                },
                "required": ["name", "prompt", "core"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_worker",
            "description": "获取当前所有可用的工人及其描述的清单。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "通过指定渠道发送消息",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "发送渠道，如 feishu 等"},
                    "content": {"type": "string", "description": "消息内容"},
                    "mode": {"type": "string", "description": "发送模式，continue 或 next"}
                },
                "required": ["channel", "content", "mode"]
            }
        }
    }
]


AGENT_TOOL_FUNCTIONS = {
    "add_task": add_task,
    "list_worker": list_worker,
    "send_message": send_message,
}


def call_agent_tool(tool_name: str, arguments: dict) -> str:
    if tool_name not in AGENT_TOOL_FUNCTIONS:
        return _format_response("error", f"未知的 Agent 工具: {tool_name}")
    func = AGENT_TOOL_FUNCTIONS[tool_name]
    try:
        result = func(**arguments)
        return result
    except Exception as e:
        return _format_response("error", f"工具执行异常: {str(e)}")
