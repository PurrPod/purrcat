import importlib
import json
import threading
import os
from typing import Any

# 补充引入了原本就存在的 kill_task，为了防止与本文件的同名工具函数冲突，起个别名 core_kill_task
from src.models.task import Task, TASK_INSTANCES, DATA_DIR, inject_task_instruction, kill_task as core_kill_task
from src.utils.config import get_models_config


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def add_task(
        name: str,
        prompt: str,
        core: str = "openai:deepseek-chat",
        judger: str = "openai:deepseek-chat"
) -> str:
    """创建后台任务（无异常拦截，直接抛给上层）"""
    model_name = core
    models = get_models_config()
    if model_name not in models:
        raise KeyError(f"未找到模型 '{model_name}' 的配置")

    model_info = models[model_name]
    api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
    valid_api_keys = [key for key in api_keys if key and key.strip()]

    if not valid_api_keys:
        raise ValueError(f"模型 '{model_name}' 未配置有效的 api-key")

    # 不再需要检查 worker 状态！
    # 任务直接创建，底层 LLMDispatcher 的全局队列会自动处理并发与排队。

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


def reload_task(task_id: str) -> str:
    """根据 task_id 重新加载并恢复休眠/中断的任务"""
    task = TASK_INSTANCES.get(task_id)

    # 如果内存中没有，尝试从磁盘扫描加载
    if not task:
        checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.exists(checkpoints_dir):
            for folder in os.listdir(checkpoints_dir):
                folder_path = os.path.join(checkpoints_dir, folder)
                ckpt_path = os.path.join(folder_path, "checkpoint.json")
                if os.path.exists(ckpt_path):
                    try:
                        with open(ckpt_path, "r", encoding="utf-8") as f:
                            state = json.load(f)
                        if state.get("task_id") == task_id:
                            task = Task.load_checkpoint(folder_path)
                            break
                    except Exception:
                        pass

    if not task:
        raise FileNotFoundError(f"未找到ID为 {task_id} 的任务历史。")

    if task.state in ["running", "ready"] and task.step > 0:
        return _format_response("text", f"⚠️ 任务 (ID: {task_id}) 目前状态为 {task.state}，无需重载。")

    # 在后台线程中执行恢复操作，防止阻塞 Agent
    def _resume_task():
        from src.agent.agent import add_message
        try:
            result = task.resume()
            notify_msg = f"🔔 [系统通知] 恢复的任务 '{task.task_name}' (ID: {task_id}) 已执行完毕。结果如下：\n{result}"
            add_message({"type": "task_message", "content": notify_msg})
        except Exception as e:
            task.state = "error"
            error_msg = f"❌ [系统通知] 任务 '{task.task_name}' (ID: {task_id}) 恢复运行崩溃，原因: {e}"
            add_message({"type": "task_message", "content": error_msg})

    t = threading.Thread(target=_resume_task, daemon=True)
    t.start()
    return _format_response("text", f"✅ 任务 (ID: {task_id}) 正在后台恢复执行...")


def submit_request(task_id: str, new_prompt: str) -> str:
    """向指定的任务追加需求指令（无异常拦截，直接抛给上层）"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise KeyError(f"未在内存中找到任务 (ID: {task_id})，如果是旧任务请先调用 reload_task 唤醒。")

    if task.state in ["running", "ready"]:
        inject_task_instruction(task_id, new_prompt)
        return _format_response("text", f"✅ 已成功向运行中的任务 (ID: {task_id}) 注入追加指令。")

    def _inject_and_resume():
        from src.agent.agent import add_message
        try:
            result = task.submit_request(new_prompt)
            notify_msg = f"🔔 [系统通知] 任务 '{task.task_name}' (ID: {task_id}) 处理追加指令完毕。\n{result}"
            add_message({"type": "task_message", "content": notify_msg})
        except Exception as e:
            task.state = "error"
            error_msg = f"❌ [系统通知] 任务 '{task.task_name}' (ID: {task_id}) 处理指令崩溃: {e}"
            add_message({"type": "task_message", "content": error_msg})

    t = threading.Thread(target=_inject_and_resume, daemon=True)
    t.start()
    return _format_response("text", f"✅ 已向休眠的任务 (ID: {task_id}) 追加指令并重新唤醒执行。")


def kill_task(task_id: str) -> str:
    """强制终止指定的后台子任务（无异常拦截，直接抛给上层）"""
    is_killed = core_kill_task(task_id)
    if is_killed:
        return _format_response("text", f"✅ 已成功向任务 (ID: {task_id}) 发送终止信号，任务将被安全强杀。")
    else:
        raise RuntimeError(f"终止失败：未在内存中找到运行中的任务 (ID: {task_id})。")


def list_worker() -> str:
    """获取当前所有模型节点及其专属线程的清单（包含实时空闲状态）。"""
    from src.models.model import LLMDispatcher
    from src.utils.config import get_models_config
    dispatcher = LLMDispatcher()
    models = get_models_config()
    model_list = []
    for model_name, model_info in models.items():
        model_desc = model_info.get('description', 'LLM')
        with dispatcher._lock:
            if model_name in dispatcher.model_workers:
                workers = dispatcher.model_workers[model_name]
                total_workers = len(workers)
                idle_workers = sum(1 for w in workers if w.work_queue.qsize() == 0)
                model_list.append(f"\"{model_name}\" | {model_desc} | 总工人数: {total_workers} | 当前空闲: {idle_workers}\n")
            else:
                api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
                valid_api_keys = [key for key in api_keys if key and key.strip()]
                total_workers = len(valid_api_keys)
                model_list.append(f"\"{model_name}\" | {model_desc} | 总工人数: {total_workers} | 当前空闲: {total_workers}\n")
    if not model_list:
        return _format_response("text", "无可用工人(模型配置)")
    return _format_response("text", "".join(model_list))


def send_message(channel: str, content: str, mode: str) -> str:
    """通过指定渠道发送消息（无异常拦截，直接抛给上层）"""
    module_path = f"src.sensor.{channel}"
    plugin_module = importlib.import_module(module_path)
    funct_name = f"send_{channel}_message"
    target_func = getattr(plugin_module, funct_name)
    return target_func(content, mode)

import threading
MEMO_FILE_LOCK = threading.Lock()
def update_memo(short_term: str, long_term: str = None) -> str:
    """更新系统备忘录，并异步触发核心档案更新"""
    def _update_core_information(flush_data: str):
        def background_task():
            from src.models.model import Model
            from src.utils.config import get_agent_model
            from src.utils.config import SRC_DIR
            profile_path = os.path.join(SRC_DIR, "agent", "core", "memory.md")
            def get_profile():
                with MEMO_FILE_LOCK:
                    if os.path.exists(profile_path):
                        with open(profile_path, "r", encoding="utf-8") as f:
                            return f.read().strip() or "（当前档案为空）"
                    return "（当前档案为空）"
            def update_profile(content: str):
                with MEMO_FILE_LOCK:
                    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                    with open(profile_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return "更新成功"
            temp_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get",
                        "description": "读取当前核心档案内容",
                        "parameters": {"type": "object", "properties": {}}
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update",
                        "description": "<覆盖>更新核心档案内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "全新的完整档案内容，纯文本，不要有符号"}
                            },
                            "required": ["content"]
                        }
                    }
                }
            ]
            system_prompt = """你是一个专门负责知识库维护的后台记忆整理中枢。
你的任务是将【新产生的关键记忆】智能地合并到【现存的核心记忆文档】中。
你必须先调用 get 获取当前文档，然后结合新记忆，最后必须调用 update 工具写入新文档。保持文档精简，少废话。"""
            user_prompt = f"【新产生的近期记忆备忘录】:\n{flush_data}"
            bg_model = Model(get_agent_model())
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            max_rounds = 5
            for _ in range(max_rounds):
                response = bg_model.chat(messages=messages, tools=temp_tools, temperature=0.1)
                msg_resp = response.choices[0].message
                assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
                tool_calls = msg_resp.tool_calls
                if tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id,
                            "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in tool_calls
                    ]
                messages.append(assist_msg)
                if not tool_calls:
                    has_updated = any(m.get("name") == "update" for m in messages if m.get("role") == "tool")
                    if has_updated:
                        print("📝 [Background] 核心记忆档案合并与落盘成功！")
                        break
                    else:
                        messages.append(
                            {"role": "user", "content": "打回：你必须调用 update 工具来保存最终的结果！请立即调用。"})
                        continue
                for t in tool_calls:
                    t_name = t.function.name
                    res = ""
                    if t_name == "get":
                        res = get_profile()
                    elif t_name == "update":
                        try:
                            args = json.loads(t.function.arguments)
                            res = update_profile(args.get("content", ""))
                        except Exception as e:
                            res = f"参数解析失败: {e}"
                    else:
                        res = "未知工具"
                    messages.append({"role": "tool", "tool_call_id": t.id, "name": t_name, "content": str(res)})
        thread = threading.Thread(target=background_task)
        thread.daemon = True
        thread.start()
    if long_term:
        _update_core_information(long_term)
    return _format_response("text", f"✅ 备忘录更新成功")

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_memo",
            "description": "在系统提示记忆压缩时更新备忘录。分离短期状态缓存与长期用户画像。",
            "parameters": {
                "type": "object",
                "properties": {
                    "short_term": {"type": "string", "description": "当前工作细节、挂起任务、临时全局变量等短期上下文。"},
                    "long_term": {"type": "string", "description": "提炼出的用户长期偏好、性格画像或核心避坑经验。"}
                },
                "required": ["short_term"]
            }
        }
    },
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
                    "core": {"type": "string",
                             "description": "使用的核心模型，如\"openai:deepseek-chat\"，可用list_worker查看"}
                },
                "required": ["name", "prompt", "core"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reload_task",
            "description": "通过任务ID恢复并重新启动一个异常中断或此前完成的休眠任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "要恢复的任务的ID"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_request",
            "description": "向指定的子任务下发追加指令或新需求",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "目标任务的ID"},
                    "new_prompt": {"type": "string", "description": "追加的指令或需求内容"}
                },
                "required": ["task_id", "new_prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_task",
            "description": "强制终止指定的后台子任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "要终止的目标任务的ID"}
                },
                "required": ["task_id"]
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
    "reload_task": reload_task,
    "submit_request": submit_request,
    "kill_task": kill_task,
    "list_worker": list_worker,
    "send_message": send_message,
    "update_memo": update_memo,
}


def call_agent_tool(tool_name: str, arguments: dict) -> str:
    """
    调用 Agent 工具（无异常拦截，直接抛给上层 parse_tool）
    """
    if tool_name not in AGENT_TOOL_FUNCTIONS:
        raise KeyError(f"未知的 Agent 工具: {tool_name}")
    func = AGENT_TOOL_FUNCTIONS[tool_name]
    result = func(**arguments)
    return result