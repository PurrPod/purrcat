import json
import os
import threading
import uuid
from typing import List, Any
from src.agent.agent import add_message

from src.models.task import Task
def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)
def add_project(name: str, prompt: str, core: str, check_mode: bool = False, refine_mode: bool = False,
                judge_mode: bool = False, is_agent: bool = True) -> str:
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
        try:
            result = new_project.run_pipeline()
            add_message({"type": "project_message", "content": f"[Project通知] 项目 {project_id} 执行结束。\n结论: {result}"})
        except Exception as e:
            add_message({"type": "project_message", "content": f"\n[Project异常] 项目 {project_id} 运行时崩溃: {e}"})
    t = threading.Thread(target=_run_project, daemon=True)
    t.start()
    return _format_response("text",(f"成功创建并启动后台项目 '{name}'。\n"
            f"项目 ID 为: {project_id}\n"
            f"请注意：项目正在异步执行。如果遇到阻碍或需要决策，系统会通知你做出反馈。"))

def answer(project_id: str, answer_text: str) -> str:
    from src.models.project import AGENT_QA_QUEUE
    if project_id not in AGENT_QA_QUEUE:
        return _format_response("text",f"回答失败：队列中未找到项目ID {project_id} 的等待记录。可能原因：ID错误，或该项目尚未发起提问。")
    if AGENT_QA_QUEUE[project_id].get("answer") is not None:
        return _format_response("text",f"提示：项目 {project_id} 当前的问题已经被回答，无需重复提交。")
    AGENT_QA_QUEUE[project_id]["answer"] = answer_text
    return _format_response("text",f"回答成功提交！项目 {project_id} 已拿到你的反馈，正在继续执行流水线。")




SIMPLE_TASK_STATUS = {}
def add_simple_task(
        title: str,
        desc: str,
        deliverable: str,
        worker: str,
        judger: str,
        available_tools: List[str],
        prompt: str,
        judge_mode: bool = False,
        task_histories: str = ""
) -> str:
    task_detail = {
        "title": title,
        "desc": desc,
        "deliverable": deliverable,
        "worker": worker,
        "judger": judger,
        "available_tools": available_tools
    }
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    SIMPLE_TASK_STATUS[task_id] = {"status": "running", "result": None}

    def _run_task():
        try:
            single_task = Task(
                task_detail=task_detail,
                judge_mode=judge_mode,
                system_prompt=prompt,
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
    return _format_response("text",(
        f"✅ 子任务 '{title}' 已成功提交到后台线程执行。\n"
        f"任务 ID 分配为: {task_id}\n"
        f"请注意：任务不会立即完成。您可以继续处理其他事务，系统会在执行完毕后发消息通知您"
    ))

def check_pending_questions() -> str:
    from src.models.project import AGENT_QA_QUEUE
    if not AGENT_QA_QUEUE:
        return _format_response("text","当前没有项目在等待你的回答。")
    msgs = []
    for pid, data in AGENT_QA_QUEUE.items():
        if data.get("answer") is None:
            msgs.append(f"- 项目ID: {pid} | 等待的问题: {data['question']}")
    return _format_response("text","当前等待回答的项目列表如下：\n" + "\n".join(msgs))

def list_tool() -> str:
    from src.plugins.plugin_manager import load_global_tool_yaml
    config = load_global_tool_yaml()
    if not config:
        return _format_response("text","当前未加载任何工具。")
    lines = []
    for idx, (tool_key, tool_info) in enumerate(config.items(), 1):
        desc = tool_info.get("desc", "无描述")
        lines.append(f"[{idx}]\"{tool_key}\" | {desc}")
    
    return _format_response("text", "\n".join(lines))

def list_worker() -> str:
    with open(os.path.join(os.getcwd(), "data", "config", "model_config.json"), "r") as f:
        json_config = json.load(f)
        json_config = json_config["models"]
    model_list = [f"\"{model_name}\" | {json_config[model_name]["description"]}\n" for model_name in json_config.keys()]
    if not model_list:
        return _format_response("text", "无可用工人")
    return _format_response("text", "\n".join(model_list))

def fetch_tool(tool_name_list: List[str]) -> str:
    """挑选下一步行动需要用到的工具（清空旧工具，仅保留新请求的工具）"""
    from src.agent.agent import GLOBAL_AGENT_TOOLS
    if not tool_name_list:
        GLOBAL_AGENT_TOOLS.clear()
        return json.dumps({
            "type": "text",
            "content": "Successfully cleared all tools. No tools are currently available."
        }, ensure_ascii=False)
    result = []
    for tool_name in tool_name_list:
        plugin_dir = os.path.join(os.getcwd(), "src", "plugins", "plugin_collection", tool_name)
        if not os.path.exists(plugin_dir):
            return json.dumps({
                "type": "error",
                "content": f"Failed: Tool '{tool_name}' does not exist in the registry. The previous tool list remains unchanged. Please check the tool list by manager__list_tool."
            }, ensure_ascii=False)
        result.append(tool_name)
    GLOBAL_AGENT_TOOLS.clear()
    GLOBAL_AGENT_TOOLS.extend(result)
    GLOBAL_AGENT_TOOLS.extend(["manager","feishu"])
    fetched_tools_str = ", ".join(result)
    return json.dumps({
        "type": "text",
        "content": f"Successfully cleared old tools and loaded: [{fetched_tools_str}]. These are now your ONLY available tools for the next action."
    }, ensure_ascii=False)