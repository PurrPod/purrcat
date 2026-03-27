"""
Agent 专属工具模块
这些工具仅在 Agent 中可用，不通过 fetch_tool 暴露给 project/task
"""

import importlib
import json
import os
import threading
import uuid
from typing import Any

from src.models.task import Task


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def add_project(name: str, prompt: str, core: str, check_mode: bool = False, refine_mode: bool = False,
                judge_mode: bool = False, is_agent: bool = True) -> str:
    """启动一个新的后台子项目。适合复杂任务和项目开发"""
    from src.models.project import Project
    new_project = Project(
        name=name,
        prompt=prompt,
        core=core,
        check_mode=check_mode,
        refine_mode=refine_mode,
        judge_mode=judge_mode,
        is_agent=is_agent
    )
    project_id = new_project.id

    def _run_project():
        from src.agent.agent import add_message
        try:
            result = new_project.run_pipeline()
            add_message({"type": "project_message", "content": f"[Project通知] 项目 {project_id} 执行结束。\n结论: {result}"})
        except Exception as e:
            add_message({"type": "project_message", "content": f"\n[Project异常] 项目 {project_id} 运行时崩溃: {e}"})

    t = threading.Thread(target=_run_project, daemon=True)
    new_project._runner_thread = t
    t.start()
    return _format_response("text", (f"成功创建并启动后台项目 '{name}'。\n"
                                      f"项目 ID 为: {project_id}\n"
                                      f"请注意：项目正在异步执行。如果遇到阻碍或需要决策，系统会通知你做出反馈。"))


def answer(project_id: str, answer_text: str) -> str:
    """回答来自特定子项目的提问，推动异步项目继续执行。"""
    from src.models.project import AGENT_QA_QUEUE
    if project_id not in AGENT_QA_QUEUE:
        return _format_response("text", f"回答失败：队列中未找到项目ID {project_id} 的等待记录。可能原因：ID错误，或该项目尚未发起提问。")
    if AGENT_QA_QUEUE[project_id].get("answer") is not None:
        return _format_response("text", f"提示：项目 {project_id} 当前的问题已经被回答，无需重复提交。")
    AGENT_QA_QUEUE[project_id]["answer"] = answer_text
    return _format_response("text", f"回答成功提交！项目 {project_id} 已拿到你的反馈，正在继续执行流水线。")


SIMPLE_TASK_STATUS = {}


def add_simple_task(
        title: str,
        desc: str,
        deliverable: str,
        prompt: str,
        judge_mode: bool = False,
        task_histories: str = "",
        core: str = "[1]openai:deepseek-chat"
) -> str:
    """启动一个简单的后台子任务。"""
    task_detail = {
        "title": title,
        "desc": desc,
        "deliverable": deliverable
    }
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    SIMPLE_TASK_STATUS[task_id] = {"status": "running", "result": None}

    def _run_task():
        from src.agent.agent import add_message
        try:
            single_task = Task(
                task_detail=task_detail,
                judge_mode=judge_mode,
                system_prompt=prompt,
                core=core,
                task_histories=task_histories,
                task_id=task_id
            )
            result_history = single_task.run_pipeline()
            SIMPLE_TASK_STATUS[task_id]["status"] = "completed"
            SIMPLE_TASK_STATUS[task_id]["result"] = result_history
            notify_msg = f"🔔 [系统通知] 后台子任务 '{title}' (ID: {task_id}) 已执行完毕。执行过程和结果如下：\n{result_history}"
            add_message({"type": "task_message", "content": notify_msg})
        except Exception as e:
            SIMPLE_TASK_STATUS[task_id]["status"] = "failed"
            SIMPLE_TASK_STATUS[task_id]["result"] = str(e)
            error_msg = f"❌ [系统通知] 您派发的后台子任务 '{title}' (ID: {task_id}) 执行崩溃，原因: {e}"
            add_message({"type": "task_message", "content": error_msg})

    t = threading.Thread(target=_run_task, daemon=True)
    t.start()
    return _format_response("text", (
        f"✅ 子任务 '{title}' 已成功提交到后台线程执行。\n"
        f"任务 ID 分配为: {task_id}\n"
        f"请注意：任务不会立即完成。您可以继续处理其他事务，系统会在执行完毕后发消息通知您"
    ))


def check_pending_questions() -> str:
    """查看当前所有正在等待回答问题的子项目列表。"""
    from src.models.project import AGENT_QA_QUEUE
    if not AGENT_QA_QUEUE:
        return _format_response("text", "当前没有项目在等待你的回答。")
    msgs = []
    for pid, data in AGENT_QA_QUEUE.items():
        if data.get("answer") is None:
            msgs.append(f"- 项目ID: {pid} | 等待的问题: {data['question']}")
    return _format_response("text", "当前等待回答的项目列表如下：\n" + "\n".join(msgs))


def list_worker() -> str:
    """获取当前所有可用的工人及其描述的清单。"""
    with open(os.path.join(os.getcwd(), "data", "config", "model_config.json"), "r") as f:
        json_config = json.load(f)
        json_config = json_config["models"]
    model_list = [f"\"{model_name}\" | {json_config[model_name]['description']}\n" for model_name in json_config.keys()]
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
            "name": "add_project",
            "description": "启动一个新的后台子项目。适合复杂任务和项目开发",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "项目名称"},
                    "prompt": {"type": "string", "description": "项目的核心任务描述"},
                    "core": {"type": "string", "description": "该项目分配的经理代号，如“[2]openai:deepseek-chat”等，可用list_worker查看"},
                    "check_mode": {"type": "boolean", "description": "是否开启分步检查模式，默认为 false。", "default": False},
                    "refine_mode": {"type": "boolean", "description": "是否开启提示词优化模式，开启的话工人将会和你沟通需求，默认为 false。", "default": False},
                    "judge_mode": {"type": "boolean", "description": "是否开启子任务质检模式，默认为 false。", "default": False}
                },
                "required": ["name", "prompt", "core"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "回答来自特定子项目的提问，推动异步项目继续执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "子项目的唯一 ID"},
                    "answer_text": {"type": "string", "description": "你针对提问给出的回答或决策内容"}
                },
                "required": ["project_id", "answer_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_pending_questions",
            "description": "查看当前所有正在等待回答问题的子项目列表。",
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
            "name": "add_simple_task",
            "description": "启动一个简单的后台子任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务标题"},
                    "desc": {"type": "string", "description": "任务描述"},
                    "deliverable": {"type": "string", "description": "任务交付物"},
                    "prompt": {"type": "string", "description": "系统提示"},
                    "judge_mode": {"type": "boolean", "description": "是否开启质检模式"},
                    "task_histories": {"type": "string", "description": "任务历史"},
                    "core": {"type": "string", "description": "使用的核心模型，如“[2]openai:deepseek-chat”，可用list_worker查看"}
                },
                "required": ["title", "desc", "deliverable", "prompt"]
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


# 工具名称到函数的映射
AGENT_TOOL_FUNCTIONS = {
    "add_project": add_project,
    "answer": answer,
    "check_pending_questions": check_pending_questions,
    "add_simple_task": add_simple_task,
    "list_worker": list_worker,
    "send_message": send_message,
}


def call_agent_tool(tool_name: str, arguments: dict) -> str:
    """
    调用 Agent 专属工具

    Args:
        tool_name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果
    """
    if tool_name not in AGENT_TOOL_FUNCTIONS:
        return _format_response("error", f"未知的 Agent 工具: {tool_name}")
    func = AGENT_TOOL_FUNCTIONS[tool_name]
    try:
        result = func(**arguments)
        return result
    except Exception as e:
        return _format_response("error", f"工具执行异常: {str(e)}")
