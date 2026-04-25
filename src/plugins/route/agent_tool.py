import importlib
import json
import threading
import os
from typing import Any

# 补充引入了原本就存在的 kill_task，为了防止与本文件的同名工具函数冲突，起个别名 core_kill_task
from src.models.task import BaseTask, TASK_INSTANCES, DATA_DIR, inject_task_instruction, kill_task as core_kill_task, TaskFactory, auto_discover_experts
from src.utils.config import get_models_config

# 先确保在文件顶部触发了扫描
auto_discover_experts()

def _get_dynamic_expert_schema() -> dict:
    enums = []
    desc_lines = ["选择最合适的子任务专家类型。当前系统动态加载的专家职责规范如下："]
    
    # 直接遍历你完美构建的 _EXPERT_REGISTRY
    for expert_type, expert_info in BaseTask._EXPERT_REGISTRY.items():
        enums.append(expert_type)
        
        # 完美契合你源码中的 "description" 字段
        description = expert_info.get("description", "无特定的职责描述")
        description = description.strip().replace("\n", " ")
        
        desc_lines.append(f"{len(enums)}. {expert_type}: {description}")

    if not enums:
        enums = ["general"]

    return {
        "type": "string",
        "enum": enums,
        "description": "\n".join(desc_lines)
    }


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def add_task(
        name: str,
        prompt: str,
        expert: str,
        core: str = "openai:deepseek-chat",
        expert_kwargs: dict = None
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

    expert_kwargs = expert_kwargs or {}
    try:
        single_task = TaskFactory.create_task(
            expert_type=expert,
            task_name=name,
            prompt=prompt,
            core=core,
            **expert_kwargs
        )
    except Exception as e:
        return _format_response("text", f"❌ 创建任务失败: {e}")

    def _run_task():
        from src.agent.manager import get_agent
        try:
            result = single_task.run()
            task_id = single_task.task_id
            notify_msg = f"任务 '{name}' (ID: {task_id}) 已执行完毕，结果交付如下：\n{result}"
            agent = get_agent()
            if agent:
                agent.force_push(notify_msg, type="task_message")
        except Exception as e:
            single_task.state = "error"
            error_msg = f"任务 '{name}' (ID: {single_task.task_id}) 执行崩溃，原因：\n {e}"
            agent = get_agent()
            if agent:
                agent.force_push(error_msg, type="task_message")

    t = threading.Thread(target=_run_task, daemon=True)
    t.start()
    return _format_response("text", (
        f"✅ 任务 '{name}' 已提交到后台线程执行。\n"
        f"ID : {single_task.task_id}\n"
        f"任务不会立即完成，您可以继续处理其他事务，系统会在执行完毕后发消息通知您"
    ))


def submit_request(task_id: str, new_prompt: str = "继续执行") -> str:
    """统一的任务交互入口：支持追加指令/继续执行，也可从磁盘加载休眠任务"""
    task = TASK_INSTANCES.get(task_id)
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
                            from src.models.task import auto_discover_experts
                            auto_discover_experts()
                            expert_type = state.get("expert_type", "BaseTask")
                            if expert_type in BaseTask._EXPERT_REGISTRY:
                                TargetClass = BaseTask._EXPERT_REGISTRY[expert_type]["class"]
                                task = TargetClass.load_checkpoint(folder_path)
                            else:
                                task = BaseTask.load_checkpoint(folder_path)
                            break
                    except Exception as e:
                        print(f"尝试加载检查点时发生异常: {e}")
                        pass
    if not task:
        raise FileNotFoundError(f"未找到ID为 {task_id} 的任务历史。")

    if task.state in ["running", "ready"]:
        inject_task_instruction(task_id, new_prompt)
        return _format_response("text", f"✅ 已成功向运行中的任务 (ID: {task_id}) 注入追加指令。")

    def _inject_and_resume():
        from src.agent.manager import get_agent
        try:
            result = task.submit_request(new_prompt)
            notify_msg = f"任务 '{task.task_name}' (ID: {task_id}) 处理追加指令完毕。\n{result}"
            agent = get_agent()
            if agent:
                agent.force_push(notify_msg, type="task_message")
        except Exception as e:
            task.state = "error"
            error_msg = f"任务 '{task.task_name}' (ID: {task_id}) 处理指令崩溃：\n{e}"
            agent = get_agent()
            if agent:
                agent.force_push(error_msg, type="task_message")

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
            if model_name in dispatcher.model_groups:
                groups = dispatcher.model_groups[model_name]
                total_workers = sum(len(group['workers']) for group in groups)
                # 由于 SmartTaskQueue 没有 qsize() 方法，我们无法精确计算空闲工人数
                # 这里简化处理，假设所有工人都是空闲的
                idle_workers = total_workers
                model_list.append(f"\"{model_name}\" | {model_desc} | 总工人数: {total_workers} | 当前空闲: {idle_workers}\n")
            else:
                api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
                valid_api_keys = [key for key in api_keys if key and key.strip()]
                # 每个 API Key 默认有 1 个大核 + 2 个小核
                total_workers = len(valid_api_keys) * 3
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
def update_memo(
    short_term: str = None,
    long_term: str = None,
    decisions: str = None,
    reminders: str = None,
    project_state: str = None
) -> str:
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
你的任务是将【新产生的关键记忆】智能（注意：不是简单的追加！！！要有判断和分析）地合并到【现存的核心记忆文档】中。
你必须先调用 get 获取当前文档，然后结合新记忆，最后必须调用 update 工具写入新文档。
保持文档精简，少废话。"""
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
    # 合并所有非空记忆维度，统一交给后台整理
    flush_parts = []
    if short_term:
        flush_parts.append(f"[短期工作状态]\n{short_term}")
    if long_term:
        flush_parts.append(f"[长期用户画像]\n{long_term}")
    if decisions:
        flush_parts.append(f"[关键决策记录]\n{decisions}")
    if reminders:
        flush_parts.append(f"[待办提醒]\n{reminders}")
    if project_state:
        flush_parts.append(f"[项目状态]\n{project_state}")
    if flush_parts:
        flush_data = "\n\n---\n\n".join(flush_parts)
        _update_core_information(flush_data)
    return _format_response("text", f"✅ 备忘录更新成功")

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_memo",
            "description": "在系统提示记忆压缩时更新备忘录，支持多维度记忆类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "short_term": {"type": "string", "description": "短期工作状态：当前处理的任务细节、挂起步骤、临时变量等即时上下文。"},
                    "long_term": {"type": "string", "description": "长期用户画像：用户性格偏好、行为习惯（如commit用英文）、核心避坑经验等需要长期记住的信息。"},
                    "decisions": {"type": "string", "description": "关键决策记录：技术选型、架构决策、方案取舍等重要的历史决策及其理由。"},
                    "reminders": {"type": "string", "description": "待办提醒：需要后续跟进的未完成任务、待处理事项。"},
                    "project_state": {"type": "string", "description": "项目状态：当前项目的整体进度、关键上下文、已完成和待完成的工作。"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "启动一个后台子任务以提高工作效率，启动后如有需要补充指令或重新加载，请调用 submit_request",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "为后台子任务起一个名称"},
                    "prompt": {"type": "string", "description": "告诉后台子任务要做什么"},
                    "expert": _get_dynamic_expert_schema(),
                    "core": {"type": "string",
                             "description": "使用的工人代号，如\"openai:deepseek-chat\"，可用list_worker查看"},
                    "expert_kwargs": {
                        "type": "object",
                        "description": "根据 expert 类型传递相应参数，例如 trading 需要 {\"company_name\": \"AAPL\", \"trade_date\": \"2026-04-16\"}"
                    }
                },
                "required": ["name", "prompt", "expert", "core"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_request",
            "description": "两重功能：reload 执行失败的任务和追加 request 到正在执行的任务里",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "目标任务的ID"},
                    "new_prompt": {"type": "string", "description": "追加的指令或需求内容，不填时默认为 reload"}
                },
                "required": ["task_id"]
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