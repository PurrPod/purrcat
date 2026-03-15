import asyncio
import importlib
import inspect
import json
from typing import Dict, Optional
import uuid
from src.models.model import Model
from src.plugins.plugin_manager import get_plugin_tool_info, get_plugin_config, init_config_data
import os             # 新增
import time           # 新增
import datetime       # 新增
import threading
import shutil

# Use absolute paths so task log and checkpoint operations work regardless of current working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "data"))

TASK_POOL = []
TASK_INSTANCES = {}
dirty_tasks = set()
task_set_lock = threading.Lock()

def _resolve_task_log_path(task_id: str):
    instance = TASK_INSTANCES.get(task_id)
    if instance:
        log_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{instance.name}_{instance.creat_time}")
        return os.path.join(log_dir, "log.jsonl")
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return None
    try:
        for entry in os.listdir(base_dir):
            log_path = os.path.join(base_dir, entry, "log.jsonl")
            if os.path.isfile(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                payload = json.loads(line)
                                if payload.get("task_id") == task_id:
                                    return log_path
                except:
                    pass
    except:
        pass
    return None

def set_task_state(task_id, state):
    # Update the global TASK_POOL record
    for t in TASK_POOL:
        if t["id"] == task_id:
            t["state"] = state
            break

    # Also update the running instance (if exists), so checkpoint saving uses the correct state
    instance = TASK_INSTANCES.get(task_id)
    if instance:
        instance.state = state


def delete_task(task_id):
    global TASK_POOL
    checkpoint_dir = None

    if task_id in TASK_INSTANCES:
        instance = TASK_INSTANCES[task_id]
        checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{instance.name}_{instance.creat_time}")
        del TASK_INSTANCES[task_id]
    else:
        for t in TASK_POOL:
            if t.get("id") == task_id:
                name = t.get("name")
                creat_time = t.get("creat_time")
                if name and creat_time:
                    checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{name}_{creat_time}")
                break

    # 如果还找不到对应目录，尝试通过 log.jsonl 找文件夹（兼容仅存在 log 的情况）
    if not checkpoint_dir:
        log_path = _resolve_task_log_path(task_id)
        if log_path:
            checkpoint_dir = os.path.dirname(log_path)

    TASK_POOL = [t for t in TASK_POOL if t.get("id") != task_id]

    if checkpoint_dir and os.path.isdir(checkpoint_dir):
        try:
            shutil.rmtree(checkpoint_dir, ignore_errors=True)
        except Exception:
            pass


def kill_task(task_id):
    """全局方法：强制关闭 Task 线程"""
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].kill()
        set_task_state(task_id, "killed")
        return True
    return False

def inject_task_instruction(task_id: str, content: str):
    """全局方法：向指定的 Task 强行注入干预指令"""
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].force_push(content)
        return True
    return False

class Task:
    VALID_STATES = ["waiting", "handling", "completed"]

    def __init__(self, task_detail: Dict, judge_mode: bool, system_prompt: str, task_histories: str = None,
                 task_id: str = None, register: bool = True):
        self.run_result = None
        for key in ["title", "desc", "deliverable", "worker", "judger", "available_tools"]:
            if key not in task_detail.keys():
                raise ValueError(f"Missing key '{key}' in task details")
        self.judge_mode = judge_mode
        self.task_detail = task_detail
        self.client = Model(task_detail['worker']).client
        if judge_mode:
            self.eval_client = Model(task_detail['judger']).client
        self.max_len = 50
        self.current_history = []
        self.eval_history = []
        self.system_prompt = system_prompt
        self.task_histories = task_histories
        self.task_id = task_id or str(uuid.uuid4())
        self._killed = False
        self.pending_force_push = None
        self.name = task_detail.get('title', 'Unknown')
        self.creat_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        # Track the current state so it is reflected in checkpoints and UI.
        self.state = "running"

        # 注册到全局任务池（用于前端展示、管理）
        if register:
            existing = [t for t in TASK_POOL if t.get("id") == self.task_id]
            if existing:
                # already exists, just update its reference/state
                for t in existing:
                    t["name"] = task_detail.get('title', 'Unknown')
                    t["state"] = "running"
                    t["progress"] = 50
                    t["creat_time"] = self.creat_time
                    t["worker"] = task_detail.get('worker')
                    t["judger"] = task_detail.get('judger')
            else:
                TASK_POOL.append(
                    {
                        "name": task_detail.get('title', 'Unknown'),
                        "id": self.task_id,
                        "state": "running",
                        "progress": 50,
                        "creat_time": self.creat_time,
                        "worker": task_detail.get('worker'),
                        "judger": task_detail.get('judger'),
                    }
                )
            TASK_INSTANCES[self.task_id] = self
            self.log_and_notify("text", self.system_prompt)
    def _clean_json_string(self, text: str) -> str:
        """辅助方法：清理模型输出的 Markdown 标记，提取纯 JSON 字符串"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def log_and_notify(self, card_type: str, content: str, metadata: dict = None):
        """为前端专门准备的结构化执行日志数据，同时输出到控制台"""
        print(content)
        log_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.name}_{self.creat_time}")
        os.makedirs(log_dir, exist_ok=True)
        log_data = {
            "task_id": self.task_id,
            "timestamp": time.time(),
            "card_type": card_type,
            "content": content,
            "metadata": metadata or {}
        }
        with open(os.path.join(log_dir, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
            f.flush()
        with task_set_lock:
            dirty_tasks.add(self.task_id)

    def save_checkpoint(self):
        """保存Task的当前状态到checkpoint.json"""
        checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.name}_{self.creat_time}")
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        # Ensure checkpoint stores the most up-to-date state.
        current_state = getattr(self, 'state', None)
        if not current_state:
            # Fallback to TASK_POOL record if available
            for t in TASK_POOL:
                if t.get("id") == self.task_id:
                    current_state = t.get("state")
                    break
        state = {
            "task_id": self.task_id,
            "name": self.name,
            "creat_time": self.creat_time,
            "task_detail": self.task_detail,
            "judge_mode": self.judge_mode,
            "system_prompt": self.system_prompt,
            "task_histories": self.task_histories,
            "current_history": self.current_history,
            "eval_history": self.eval_history,
            "run_result": self.run_result,
            "state": current_state or "running",
            "pending_force_push": self.pending_force_push
        }
        try:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ [Task Checkpoint] 保存失败: {e}")

    @classmethod
    def load_checkpoint(cls, checkpoint_path: str):
        """从checkpoint加载Task"""
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            # 从checkpoint恢复时不要重复注册到TASK_POOL（避免重复条目）
            task = cls(
                task_detail=state["task_detail"],
                judge_mode=state["judge_mode"],
                system_prompt=state["system_prompt"],
                task_histories=state.get("task_histories"),
                task_id=state["task_id"],
                register=False,
            )
            task.current_history = state.get("current_history", [])
            task.eval_history = state.get("eval_history", [])
            task.run_result = state.get("run_result")
            task.pending_force_push = state.get("pending_force_push")
            task.state = state.get("state", "running")
            # Ensure we restore the original folder timestamp so logs/checkpoints stay consistent
            task.creat_time = state.get("creat_time", task.creat_time)

            # 确保 TASK_POOL 中只保留一份任务（按 task_id 唯一）
            existing = [t for t in TASK_POOL if t.get("id") == task.task_id]
            if not existing:
                TASK_POOL.append({
                    "name": task.name,
                    "id": task.task_id,
                    "state": state.get("state", "running"),
                    "progress": 100 if task.run_result else 50,
                    "creat_time": task.creat_time,
                    "worker": (task.task_detail or {}).get("worker") or (state.get("task_detail") or {}).get("worker"),
                    "judger": (task.task_detail or {}).get("judger") or (state.get("task_detail") or {}).get("judger"),
                })
            else:
                # 更新状态/进度
                for t in existing:
                    t["state"] = state.get("state", t.get("state", "running"))
                    t["progress"] = 100 if task.run_result else t.get("progress", 50)

            # 保证实例可用
            TASK_INSTANCES[task.task_id] = task
            return task
        except Exception as e:
            print(f"❌ [Task Checkpoint] 加载失败 {checkpoint_path}: {e}")
            return None

    def force_push(self, content: str):
        if self.current_history and self.current_history[-1].get('role') == 'assistant' and self.current_history[-1].get('tool_calls'):
            self.pending_force_push = content
        else:
            warning_prompt = (
                f"【系统紧急干预】请立刻停止你当前做的事，优先执行此指令！\n"
                f"{content}"
            )
            self.current_history.append({
                "role": "user",
                "content": warning_prompt
            })
            self.log_and_notify("system", f"⚠️ [Task {self.task_id}] 已强行注入干预指令：\n{content}")
    def kill(self):
        self._killed = True
        self.log_and_notify("system", f"⚠️ [Task] 收到Kill指令，准备直接关闭任务 {self.task_id} 线程...")

    def _check_kill(self):
        """无需保留节点状态，直接抛异常中止"""
        if self._killed:
            raise InterruptedError(f"任务 {self.task_id} 被手动强制关闭。")

    def run(self, suggestion: str = None, max_steps: int = 500):
        init_config_data()
        if not suggestion:
            sys_prompt = (
                "你是一个高级智能助手（Worker），负责执行子任务并善用工具。\n"
                "【重要交付规范】\n"
                "1. 在执行任务期间，你可以正常输出文本思考并调用工具。\n"
                "2. 当你认为任务最终完成或确认无法完成，【且不再需要调用任何工具时】，你的最后一次回复必须是一个合法的纯JSON对象，不要包含任何多余的说明文字或Markdown标记！\n"
                "3. 最终的JSON格式必须为：{\"status\": \"completed\", \"task_result\": true或false, \"summary\": \"最终交付物或失败原因\"}\n"
                "4. 质检员（QA）只能看到你 completed 状态下的 summary，看不到你之前的 thought。\n"
                "5. 如果没有直接产生文件，必须把交付的完整文本写在 summary 里；如果有生成文件，写明文件绝对路径和内容简要说明。"
            )
            self.current_history.append({"role": "system", "content": sys_prompt})

            prompt = f"{self.system_prompt}\n\n请你开始执行当前阶段的子任务。"
            if self.task_histories:
                prompt += f"\n\n[前置任务情况]\n{self.task_histories}"
            self.current_history.append({"role": "user", "content": prompt})
        else:
            self.current_history.append(
                {"role": "user",
                 "content": f"QA反馈不通过：{suggestion}\n请修正后重新提交。记得最终交付时不再调用工具，并直接输出规范的JSON格式。"})

        available_tools = self.task_detail.get('available_tools', [])
        if isinstance(available_tools, str):
            available_tools = [available_tools] if available_tools else []
        tools_info = get_plugin_tool_info(available_tools)

        model_name = self.task_detail["worker"].split(":")[-1] if ':' in self.task_detail["worker"] else \
            self.task_detail["worker"]
        step = 0

        while step < max_steps:
            self.memory_flush()
            self._check_kill()
            step += 1
            try:
                kwargs = {
                    "model": model_name,
                    "messages": self.current_history,
                }
                if tools_info:
                    kwargs["tools"] = tools_info

                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message

                # 记录模型的原始回复
                assist_msg = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id, "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in message.tool_calls
                    ]
                self.current_history.append(assist_msg)

                if message.content and message.content.strip():
                    self.log_and_notify("text", f"🤖 Worker: {message.content.strip()}")

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                        self.log_and_notify("tool_call", f"🔎 Worker Tool: {tool_name}({arguments_str})", {"tool_name": tool_name})
                        try:
                            mcp_type, func_name = tool_name.split('__', 1)
                            arguments = json.loads(arguments_str) if arguments_str else {}
                            result = self._execute_tool(mcp_type, func_name, arguments)
                        except json.JSONDecodeError as e:
                            result = f"Tool Execution Error: Invalid JSON format generated for arguments. Error details: {str(e)}. Please try calling the tool again with valid JSON."
                        except Exception as e:
                            result = f"Tool Execution Error: {str(e)}"
                        self.log_and_notify("tool_result", f"😇 Tool Result: {str(result)[:200]}...")
                        self.current_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": str(result)
                        })

                    if self.pending_force_push:
                        warning_prompt = (
                            f"【系统紧急干预】请立刻停止你当前做的事，优先执行此指令！\n"
                            f"{self.pending_force_push}"
                        )
                        self.current_history.append({
                            "role": "user",
                            "content": warning_prompt
                        })
                        self.log_and_notify("system", f"⚠️ [Task {self.task_id}] 已强行注入干预指令：\n{self.pending_force_push}")
                        self.pending_force_push = None
                else:
                    raw_content = message.content.strip() if message.content else ""
                    cleaned_content = self._clean_json_string(raw_content)

                    try:
                        content_dict = json.loads(cleaned_content)
                        if content_dict.get("status") == "completed":
                            self.run_result = content_dict
                            set_task_state(self.task_id, "completed")
                            self.save_checkpoint()
                            return content_dict
                        else:
                            self.current_history.append({
                                "role": "user",
                                "content": "你没有调用任何工具，系统判断你需要交付结果。但你输出的JSON缺少 '\"status\": \"completed\"'。请输出规范的纯JSON对象。"
                            })
                    except json.JSONDecodeError as e:
                        self.current_history.append({
                            "role": "user",
                            "content": f"任务执行已结束(无工具调用)，此时你需要提交最终交付物。请把你最终的结果按规范格式转化为纯JSON对象输出，不要包含任何前言后语。JSON解析错误: {e}"
                        })
            except Exception as e:
                self.log_and_notify("error", f"❌ API 调用发生意外异常: {e}")
                set_task_state(self.task_id, "error")
                self.save_checkpoint()
                raise InterruptedError(f"API意外中断: {e}")
        set_task_state(self.task_id, "error")
        self.save_checkpoint()
        return {"task_result": False, "summary": f"Worker超出最大思考步数({max_steps})，被强制终止。"}

    def run_eval(self, max_steps: int = 30):
        self.eval_history = []
        sys_prompt = (
            "你是一个严格且专业的项目质检员（QA）。\n"
            "【质检核心标准】\n"
            "严格对照当前子任务要求进行逐项检查。发现遗漏、幻觉、格式错误判定为不通过。绝不能代替Worker执行任务！\n"
            "【重要交付规范】\n"
            "1. 质检过程中你可以正常输出文本思考或调用工具查验。\n"
            "2. 当质检完成，【且不再调用工具时】，你必须直接返回纯JSON对象，不要包含其他说明文字。\n"
            "3. 最终的JSON格式必须为：{\"status\": \"completed\", \"eval_result\": true或false, \"suggestion\": \"失败原因/修改建议 或 成功的评价\"}"
        )
        self.eval_history.append({"role": "system", "content": sys_prompt})

        prompt = f"{self.system_prompt}\n\n请完成当前阶段的质检：\nWorker的交付内容：{json.dumps(self.run_result, ensure_ascii=False)}\n【参考】前置任务日志：{self.task_histories}"
        self.eval_history.append({"role": "user", "content": prompt})

        available_tools = self.task_detail.get('available_tools', [])
        if isinstance(available_tools, str):
            available_tools = [available_tools] if available_tools else []
        tools_info = get_plugin_tool_info(available_tools)

        model_name = self.task_detail["judger"].split(":")[-1] if ':' in self.task_detail["judger"] else \
            self.task_detail["judger"]

        step = 0
        while step < max_steps:
            self._check_kill()
            step += 1
            try:
                kwargs = {
                    "model": model_name,
                    "messages": self.eval_history,
                }
                if tools_info:
                    kwargs["tools"] = tools_info
                response = self.eval_client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                assist_msg = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id, "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in message.tool_calls
                    ]
                self.eval_history.append(assist_msg)

                if message.content and message.content.strip():
                    self.log_and_notify("text", f"🤖 Judger: {message.content.strip()}")

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                        self.log_and_notify("tool_call", f"🔎 Judger Tool: {tool_name}({arguments_str})", {"tool_name": tool_name})

                        try:
                            mcp_type, func_name = tool_name.split('__', 1)
                            arguments = json.loads(arguments_str) if arguments_str else {}
                            result = self._execute_tool(mcp_type, func_name, arguments)
                        except Exception as e:
                            result = f"Tool Execution Error: {str(e)}"

                        self.log_and_notify("tool_result", f"😇 Tool Result: {str(result)[:200]}...")
                        self.eval_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": str(result)
                        })

                    if self.pending_force_push:
                        warning_prompt = (
                            f"【系统紧急干预】请立刻停止你当前做的事，优先执行此指令！\n"
                            f"{self.pending_force_push}"
                        )
                        self.eval_history.append({
                            "role": "user",
                            "content": warning_prompt
                        })
                        self.log_and_notify("system", f"⚠️ [Task {self.task_id}] 已强行注入干预指令：\n{self.pending_force_push}")
                        self.pending_force_push = None
                else:
                    raw_content = message.content.strip() if message.content else ""
                    cleaned_content = self._clean_json_string(raw_content)
                    try:
                        content_dict = json.loads(cleaned_content)
                        if content_dict.get("status") == "completed":
                            set_task_state(self.task_id, "completed")
                            self.save_checkpoint()
                            return content_dict
                        else:
                            self.eval_history.append({
                                "role": "user",
                                "content": "请输出包含 '\"status\": \"completed\"' 的JSON对象完成质检。"
                            })
                    except json.JSONDecodeError as e:
                        self.eval_history.append({
                            "role": "user",
                            "content": f"质检结束请直接输出纯JSON判定结果，不要包含多余文字。JSON解析错误: {e}"
                        })

            except Exception as e:
                print(f"API 调用发生意外异常: {e}")
                set_task_state(self.task_id, "error")
                self.save_checkpoint()
                raise InterruptedError(f"API意外中断: {e}")

        set_task_state(self.task_id, "error")
        self.save_checkpoint()
        return {"eval_result": False, "suggestion": "QA质检过程超出最大思考步数。"}

    def _execute_tool(self, mcp_type: str, func_name: str, arguments: dict):
        plugin_config = get_plugin_config(mcp_type)
        if not plugin_config:
            raise ValueError(f"未找到插件配置：{mcp_type}")
        try:
            module_path = f"src.plugins.plugin_collection.{mcp_type}"
            plugin_module = importlib.import_module(module_path)
        except ImportError as e:
            try:
                plugin_module = importlib.import_module(mcp_type)
            except ImportError:
                raise ValueError(f"导入插件包失败 {mcp_type}: {e}")
        if not hasattr(plugin_module, func_name):
            raise ValueError(f"插件包 {mcp_type} 中无函数：{func_name}")

        target_func = getattr(plugin_module, func_name)

        if inspect.iscoroutinefunction(target_func):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = asyncio.get_event_loop().run_until_complete(target_func(**arguments))
            else:
                result = asyncio.run(target_func(**arguments))
        else:
            result = target_func(**arguments)

        return result if result else "Success (No Output)"

    def run_pipeline(self):
        try:
            result_history = []
            run_result = self.run()
            result_history.append(str(run_result))
            if run_result.get("task_result") and self.judge_mode:
                eval_result = self.run_eval()
                result_history.append(str(eval_result))
                if not eval_result.get("eval_result"):
                    suggestion = f"该阶段的质检不通过；质检建议：{eval_result.get('suggestion')}"
                    self.log_and_notify("qa_reject", f"🔁 QA 打回修改: {suggestion}")
                    run_result = self.run(suggestion=suggestion)
                    result_history.append(str(run_result))
                    eval_result = self.run_eval()
                    result_history.append(str(eval_result))
                    if not eval_result.get("eval_result"):
                        final_failure = {"task_result": False, "desc": "模型尝试两次修改后均未通过QA，子任务宣告失败。"}
                        result_history.append(str(final_failure))
            set_task_state(self.task_id, "completed")
            return result_history
        except InterruptedError as e:
            set_task_state(self.task_id, "killed")
            raise e

        except Exception as e:
            set_task_state(self.task_id, "error")
            raise e

    def memory_flush(self, check_mode=True, max_tokens=100000):
        """
        阶段性记忆压缩：结合轮数与 Token 数量进行双重判断。
        - check_mode=True: 检查 token 是否超过 100000，或轮数是否达到 max_len(50)。均未超出则不压缩。
        - check_mode=False: 强制无论如何都要执行压缩逻辑。
        """
        messages_str = json.dumps(self.current_history, ensure_ascii=False)
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            current_tokens = len(encoding.encode(messages_str))
        except ImportError:
            current_tokens = len(messages_str) // 2  # 更保守的估算

        # 【逻辑修正】：当开启 check_mode 时，才进行条件拦截
        if check_mode:
            # 只有轮数和 Token 都处于安全范围内时，才跳过压缩
            if len(self.current_history) < self.max_len and current_tokens < max_tokens:
                return

        # 如果 check_mode 为 False，或者上述任一条件超出阈值，直接开始执行以下归档流程
        self.log_and_notify("system", f"⚠️ Memory Flush: 当前 {len(self.current_history)} 轮，共计约 {current_tokens} tokens。")

        # 换用与 agent.py 风格一致的强烈归档 Prompt
        alert_prompt = """【系统严重警告：大脑记忆容量即将溢出！！！】
为了防止记忆断层，系统即将物理抹除你最早期的一批记忆。
请你现在亲自对**此前的所有对话、事件和执行记录**进行全面总结，提取出核心事件、任务进度、你的关键决策以及目前遇到的阻碍，形成一份“早期记忆备忘录”。
直接用自然语言输出。这份备忘录将作为你未来回忆那段时光的唯一凭证，也是你承上启下的节点，请务必保证包含影响任务推进的关键信息！"""

        self.current_history.append({
            "role": "user",
            "content": alert_prompt
        })

        try:
            model_name = self.task_detail["worker"].split(":")[-1] if ':' in self.task_detail["worker"] else \
            self.task_detail["worker"]
            kwargs = {
                "model": model_name,
                "messages": self.current_history,
            }
            response = self.client.chat.completions.create(**kwargs)
            archive_content = response.choices[0].message.content.strip()

            self.log_and_notify("system", f"🧠 Task归档完成，生成备忘录长度: {len(archive_content)} 字符")

            # 使用显式的备忘录抬头保存
            self.current_history.append({
                "role": "assistant",
                "content": f"【早期记忆备忘录】\n{archive_content}"
            })

            # Task 专属逻辑：保留 System Prompt (idx=0) 和 初始 User Task Prompt (idx=1)
            start_idx = 2
            keep_recent = 20  # 对齐 Agent 保持 20 条较长上下文

            split_idx = len(self.current_history) - keep_recent

            if split_idx > start_idx:
                # 往前寻找安全边界，避开切断 tool_call 链条
                while split_idx > start_idx:
                    curr_msg = self.current_history[split_idx]
                    prev_msg = self.current_history[split_idx - 1]
                    if curr_msg.get("role") == "tool":
                        split_idx -= 1
                        continue
                    if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                        split_idx -= 1
                        continue
                    break

            if split_idx < start_idx:
                split_idx = start_idx

            self.current_history = self.current_history[0:start_idx] + self.current_history[split_idx:]
            self.log_and_notify("system", "✅ Memory Flush: 记忆清理完毕！")

        except Exception as e:
            self.log_and_notify("error", f"❌ 记忆存档发生异常: {e}")