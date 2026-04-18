# todo:记忆、经验积累模块

import datetime
import json
import os
import threading
import uuid
import time
import glob

from json_repair import repair_json

from src.models.model import Model
from src.utils.config import TOOL_INDEX_FILE, DATA_DIR

TASK_INSTANCES = {}
dirty_tasks = set()
task_set_lock = threading.Lock()


def set_task_state(task_id, state):
    instance = TASK_INSTANCES.get(task_id)
    if instance:
        instance.state = state


def kill_task(task_id):
    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES[task_id]
        task.kill()
        set_task_state(task_id, "killed")
        return True
    return False


def inject_task_instruction(task_id: str, content: str):
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].submit_request(content)
        return True
    return False


class BaseTask:
    """
    通用智能体任务基类 (BaseTask)
    提供底层大模型通讯、工具解析、记忆管理、幻觉审查与断点恢复等基础设施。
    """
    _EXPERT_REGISTRY = {}
    def __init_subclass__(cls, expert_type=None, description="", parameters=None, **kwargs):
        """
        当任何类继承 BaseTask 时，会自动触发这个钩子。
        支持类定义时直接指定注册信息，避免循环导入。
        """
        super().__init_subclass__(**kwargs)
        if expert_type:
            cls._EXPERT_REGISTRY[expert_type] = {
                "class": cls,
                "description": description,
                "parameters": parameters or {}
            }
            print(f"✅ 自动注册子任务专家: {expert_type} -> {cls.__name__}")

    def __init__(self, task_name, prompt, core, judger):
        self.task_name = task_name
        self.prompt = prompt
        self.core = core
        self.judger = judger
        self.system_prompt = self._build_system_prompt()
        self.history = []
        self.task_id = uuid.uuid4().hex
        self.model = Model(core) if core else None
        if self.model:
            self.model.bind_task(self.task_id, self.task_name)
        self.state = "ready"
        self.step = 0
        self._lock = threading.Lock()
        self._killed = False
        self.pending_force_push = []
        self.create_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.history.append({"role": "system", "content": self.system_prompt})
        self.history.append({"role": "user", "content": f"[User Request]: \n{self.prompt}\n"})
        self.token_usage = 0
        self.window_token = 0
        if not TASK_INSTANCES.get(self.task_id, None):
            TASK_INSTANCES[self.task_id] = self
        self.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.create_time}")
        self.log_window = []
        self.log_and_notify("system", f"🎯 用户需求: \n{self.prompt}")

    def _on_save_state(self) -> dict:
        """生命周期钩子：供子类重写，返回需要额外持久化的特有属性字典"""
        return {}

    def _on_restore_state(self, state: dict):
        """生命周期钩子：供子类重写，根据 checkpoint 字典恢复特有属性和不可序列化对象"""
        pass

    def get_available_tools(self) -> list:
        """生命周期钩子：动态获取当前任务可用的所有工具，子类可覆写追加专属工具"""
        from src.plugins.route.task_tool import TASK_TOOLS
        from src.plugins.route.base_tool import BASE_TOOLS
        return list(BASE_TOOLS) + list(TASK_TOOLS)

    def _get_extra_context_messages(self) -> list:
        """生命周期钩子：每次请求大模型前，子类可追加额外的动态上下文注入（如计划表）"""
        return []

    def _handle_expert_tool(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """生命周期钩子：子类可重写此方法以拦截并执行专家的 Extend Tools"""
        return False, ""

    def _build_system_prompt(self):
        return """# 角色定义
你是一个运行任务执行专家。你的核心任务是理解老板下发的需求，并合理调度工具高效解决问题。

# 环境指南：沙盒与老板电脑
1. **沙盒环境**：你的专属安全工作区，仅使用命令行工具可以访问，物理路径包含 `/agent_vm`。在这里你有绝对的控制权，可以自由编写代码、运行脚本、克隆项目。所有危险、未知的操作必须在此进行。
2. **老板电脑**：除了沙盒以外的区域。你对此区域尽量保持只读。除非任务明确要求修改老板的项目文件，否则请在沙盒内完成工作。

# 工具认知与能力拓展
1. **内置工具池**：你拥有 `execute_command` (沙盒环境交互入口)、`filesystem` (宿主机本地文件交互)、`web` (基础网页信息获取) 等工具。
2. **Web 工具的局限**：本地 `web` 工具仅适用于基础搜索和静态页面抓取。遇到强反爬虫限制或动态网页时，不要反复重试无效操作，应当使用 get_menu 查看 MCP 工具是否提供了对应的定制化工具

# 核心行为规范
1. **工具依赖**：遇到信息不足或需要操作外部环境时，必须主动使用工具，严禁凭空捏造。
2. **交付验收**：当你认为任务完成时，必须调用 `task_done` 工具进行交付，说明任务成功与否，并给出详细的数据或总结。
3. **及时求助与止损**：如果评估发现现有条件无法完成任务，或手搓脚本成本过高，大胆承认不足并及时调用 `task_done` 返回失败原因，不要陷入死循环。
4. **利用现有技能**：每次开始任务之前，都要翻阅一下技能手册（使用 list_skill 工具），查看是否有提供的技能对应上了任务需求，要用 load_skill 加载一下获取更专业的指导并获取脚本信息，这样能让你的交付物更加专业，执行更加高效！！！
"""

    def _cleanup_resources(self):
        try:
            from src.plugins.route.base_tool import close_shell
            close_shell(session_id=self.task_id)
            self.log_and_notify("system", "🧹 已自动回收任务专属的 Shell 终端环境")
        except Exception as e:
            print(f"⚠️ 自动回收 Shell 失败: {e}")

    def run(self):
        max_steps = 150
        self.state = "running"
        while self.step < max_steps:
            self.step += 1
            try:
                response = self._run_llm_step()
                tool_calling = self._extract_tool_calling(response)
                if not tool_calling:
                    self.history.append({"role": "user", "content": "检测到你没有使用任何工具，如已完成，必须使用task_done工具结束任务，如未完成，请继续"})
                else:
                    if self._is_completed(tool_calling):
                        self.log_and_notify("system", "⚖️ 正在进行最终交付验收审查...")
                        eval_result = self._run_eval()
                        if eval_result.get("has_hallucination", False):
                            reason = eval_result.get('reason', '未知')
                            self.log_and_notify("warning", f"⚠️ 任务交付被驳回：{reason}")
                            for tc in tool_calling:
                                if tc.function.name == "task_done":
                                    self.history.append({
                                        "role": "tool",
                                        "tool_call_id": tc.id,
                                        "name": "task_done",
                                        "content": f"❌ 交付被系统审查拦截驳回：\n{reason}\n请务必修复上述问题后，再尝试交付！"
                                    })
                                else:
                                    self._tool_calling([tc])
                            self.checker()
                            continue

                        result, summary = self._extract_summary(tool_calling)
                        self.state = "completed"
                        for tc in tool_calling:
                            if tc.function.name == "task_done":
                                return_content = "任务结果交付成功！"
                                self.log_and_notify("tool", f"📦 任务结束交付: {return_content}")
                                self.history.append({
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "name": "task_done",
                                    "content": return_content
                                })
                            else:
                                self._tool_calling([tc])
                        if self.model: self.model.unbind_task()
                        self._cleanup_resources()
                        self.save_checkpoint()
                        return f"✅ 任务成功：{summary}" if result else f"❌ 任务失败：{summary}"
                    else:
                        self._tool_calling(tool_calling)
                self.checker()
            except KeyboardInterrupt:
                self.state = "error"
                if self.model: self.model.unbind_task()
                self._cleanup_resources()
                self.log_and_notify("system", "⚠️ 检测到强制中断 (Ctrl+C)，保存现场...")
                self.save_checkpoint()
                raise
            except Exception as e:
                self.state = "error"
                if self.model: self.model.unbind_task()
                self._cleanup_resources()
                self.log_and_notify("error", f"❌ 运行发生异常: {e}")
                self.save_checkpoint()
                raise InterruptedError(f"任务异常中断: {e}")

        if self.state != "completed":
            self.state = "error"
            if self.model: self.model.unbind_task()
            self._cleanup_resources()
            self.save_checkpoint()
            self.log_and_notify("error", f"❌ 任务失败: 超出最大思考步数 ({max_steps})")
            return f"❌ 任务失败: 超出最大思考步数 ({max_steps})"

    def save_checkpoint(self):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        history_path = os.path.join(self.checkpoint_dir, "history.json")
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        state = {
            "task_id": self.task_id,
            "name": self.task_name,
            "expert_type": self.__class__.__name__,
            "create_time": self.create_time,
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "core": self.core,
            "judger": self.judger,
            "state": self.state,
            "step": self.step,
            "token_usage": self.token_usage,
            "window_token": self.window_token,
            "checkpoint_dir": self.checkpoint_dir,
            "pending_force_push": self.pending_force_push,
            "extra_state": self._on_save_state(),
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        try:
            checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
            history_path = os.path.join(checkpoint_dir, "history.json")

            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)

            task = cls.__new__(cls)
            task.task_id = state.get("task_id")
            task.task_name = state.get("name", "Unknown")
            task.create_time = state.get("create_time")
            task.prompt = state.get("prompt", "")
            task.system_prompt = state.get("system_prompt", "")
            task.core = state.get("core", "")
            task.judger = state.get("judger", "")
            task.state = state.get("state", "ready")
            if task.state in ["running"]:
                task.state = "interrupted"
            task.step = state.get("step", 0)
            task.token_usage = state.get("token_usage", 0)
            task.window_token = state.get("window_token", 0)
            task.pending_force_push = state.get("pending_force_push", [])
            task.checkpoint_dir = state.get("checkpoint_dir", checkpoint_dir)
            task.history = history
            task.model = Model(task.core) if task.core else None
            if task.model:
                task.model.bind_task(task.task_id, task.task_name)
            task._lock = threading.Lock()
            task._killed = False
            task.log_window = []

            task._on_restore_state(state)
            TASK_INSTANCES[task.task_id] = task
            return task
        except Exception as e:
            print(f"❌ [Task Checkpoint] 加载失败 {checkpoint_dir}: {e}")
            return None

    def _track_token_usage(self, response) -> dict:
        usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if hasattr(response, "usage") and response.usage is not None:
            usage_data["prompt_tokens"] = response.usage.prompt_tokens
            usage_data["completion_tokens"] = response.usage.completion_tokens
            usage_data["total_tokens"] = response.usage.total_tokens
        self.token_usage += usage_data["total_tokens"]
        self.window_token = usage_data["total_tokens"]
        return usage_data

    def _run_llm_step(self):
        current_tools = self.get_available_tools()
        request_messages = self.history + self._get_extra_context_messages()
        response = self.model.chat(messages=request_messages, tools=current_tools)
        self._track_token_usage(response)

        message = response.choices[0].message
        assist_msg = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            assist_msg["tool_calls"] = [
                {"id": t.id, "type": t.type, "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in message.tool_calls
            ]
        self.history.append(assist_msg)

        if message.content:
            self.log_and_notify("thought", f"🤖 助手思考: {message.content.strip()[:200]}")
        return message

    def _is_completed(self, tool_calls: list) -> bool:
        return any(tc.function.name == "task_done" for tc in tool_calls)

    def _extract_tool_calling(self, message) -> list:
        return message.tool_calls if getattr(message, "tool_calls", None) else []

    def log_and_notify(self, card_type: str, content: str, metadata: dict = None):
        self.log_window.append(content[:300] + ("[超过300字符，已截断]" if len(content) > 200 else ""))
        log_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.create_time}")
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

    def _extract_summary(self, tool_calls: list):
        for tc in tool_calls:
            if tc.function.name == "task_done":
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    return args.get("result", True), args.get("summary", "无交付说明")
                except Exception:
                    return True, tc.function.arguments
        return True, "无交付说明"

    def kill(self):
        self._killed = True
        self.state = "killed"
        if self.model: self.model.unbind_task()
        self._cleanup_resources()
        self.log_and_notify("system", f"⚠️ 任务 {self.task_id} 被强制终止")

    def checker(self):
        if self._killed:
            self.state = "killed"
            raise InterruptedError(f"任务 {self.task_id} 被强杀。")

        local_push = []
        with self._lock:
            if self.pending_force_push:
                local_push = self.pending_force_push.copy()
                self.pending_force_push.clear()
        if local_push:
            for cnt, item in enumerate(local_push, 1):
                local_push[cnt - 1] = f"{cnt} | " + item
            content = "\n".join(local_push)
            self.history.append({
                "role": "user",
                "content": f"[System Warning] You should suspend your action and handle this message first!\n{content}"
            })
        self.memory_flush()

    def memory_flush(self, check_mode=True, max_tokens=120000):
        if check_mode and (self.window_token <= max_tokens or len(self.history) <= 150):
            return
        self.log_and_notify("system", f"⚠️ 触发记忆截断: 当前共约 {self.window_token} tokens。正在进行上下文压缩...")
        ask_result = {"result": True, "summary": ""}
        if self.log_window:
            eval_result = self._run_eval()
            if eval_result.get("has_hallucination", False):
                ask_result = self._ask_for_continue(eval_result)
        if ask_result.get("result", True):
            alert_prompt = """【系统警告：记忆容量即将溢出】
    系统即将物理抹除你最早期的一批交互记忆。
    请你现在对**此前的所有任务进度、关键决策、已发现的代码规律以及目前的阻塞点**进行全面总结，形成一份简单明了的“核心备忘录”，不要用markdown。
    这份备忘录将作为你承上启下的唯一凭证，务必包含所有关键信息！"""
            self.history.append({"role": "user", "content": alert_prompt})
            try:
                response = self.model.chat(messages=self.history)
                self._track_token_usage(response)
                archive_content = response.choices[0].message.content.strip()
                self.history.append({
                    "role": "assistant",
                    "content": f"【早期记忆备忘录】\n{archive_content}"
                })
                start_idx = 2
                keep_recent = 20
                split_idx = max(start_idx, len(self.history) - keep_recent)

                while split_idx > start_idx:
                    curr_msg = self.history[split_idx]
                    prev_msg = self.history[split_idx - 1]
                    if curr_msg.get("role") == "tool" or (
                            prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls")):
                        split_idx -= 1
                        continue
                    break
                self.history = self.history[0:start_idx] + self.history[split_idx:]
                self.log_and_notify("system", "✅ 上下文压缩完毕！")
            except Exception as e:
                self.log_and_notify("error", f"❌ 记忆存档发生异常: {e}")
        else:
            raise ValueError(f"Worker 在工作中出现幻觉，并决定终止任务，理由为：{ask_result.get('summary', '无理由')}")

    def _tool_calling(self, tool_calling):
        for tool_call in tool_calling:
            original_tool_name = tool_call.function.name
            target_tool_name = original_tool_name
            arguments_str = tool_call.function.arguments
            arguments = {}
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError as e:
                    print(f"⚠️ 标准 JSON 解析失败，尝试容错修复: {e}")
                    if repair_json:
                        try:
                            arguments = repair_json(arguments_str, return_objects=True)
                            print("✅ json-repair 修复成功！")
                        except Exception as repair_e:
                            print(f"❌ json-repair 修复失败: {repair_e}")
                    else:
                        print("💡 强烈建议终端运行 `pip install json-repair` 来自动修复此问题！")
            if original_tool_name == "call_dynamic_tool" and isinstance(arguments, dict):
                target_tool_name = arguments.get("target_tool_name", "")
                target_args = arguments.get("arguments", {})
                if isinstance(target_args, str):
                    try:
                        arguments = json.loads(target_args)
                    except Exception:
                        arguments = repair_json(target_args, return_objects=True) if repair_json else target_args
                else:
                    arguments = target_args

            if target_tool_name in ["execute_command", "close_shell"]:
                arguments["session_id"] = self.task_id
            if not isinstance(arguments, dict):
                error_msg = "❌ 系统拦截：工具参数格式严重损坏。请分批运行命令避免指令过长！！"
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": original_tool_name,
                    "content": error_msg
                })
                self.log_and_notify("system", "❌ 系统拦截：工具参数格式严重损坏")
                continue
            args_str = ", ".join([f'{k}={repr(v)}' for k, v in arguments.items()]) if isinstance(arguments, dict) else str(arguments)
            self.log_and_notify("tool_call", f"🔧 助手调起工具: {target_tool_name}({args_str})", metadata={"arguments": arguments})

            # 1. 优先尝试专家专属 Extend Tool 拦截
            is_handled, result_str = self._handle_expert_tool(target_tool_name, arguments)
            if not is_handled:
                # 2. 尝试通用 Task Tool
                from src.plugins.route.task_tool import TASK_TOOL_FUNCTIONS
                task_tool_names = list(TASK_TOOL_FUNCTIONS.keys())
                if target_tool_name in task_tool_names:
                    from src.plugins.route.task_tool import call_task_tool
                    result_str = call_task_tool(target_tool_name, arguments, self)
                # 3. 退化为基础路由工具
                else:
                    from src.plugins.plugin_manager import parse_tool
                    result_str = parse_tool(target_tool_name, arguments)
                    self.log_and_notify("tool", f"📦 工具回传结果: {result_str}")
            finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            time_aware_content = f"[finish at {finish_time}]\n{result_str}"
            self.history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": original_tool_name,
                "content": time_aware_content
            })

    def _run_eval(self):
        eval_system_prompt = """你是一个严格的 AI Agent 行为审查员。
你的任务是审查 Agent 在最近几个对话轮次中的表现，重点排查是否存在"幻觉（Hallucination）"。
请严格以 JSON 格式输出你的审查结果：
{
    "has_hallucination": true 或 false,
    "reason": "如果为 true，请直接指出具体的幻觉表现和证据；如果为 false，简述其逻辑。"
}"""
        prompt = "以下是准备被压缩的上下文日志快照：\n\n" + "\n".join(self.log_window)
        judger_key = self.judger.split("]")[-1] if "]" in self.judger else self.judger

        try:
            judger_model = Model(judger_key)
            temp_history = [
                {"role": "system", "content": eval_system_prompt},
                {"role": "user", "content": prompt}
            ]
            response = judger_model.chat(
                messages=temp_history,
                response_format={"type": "json_object"},
                temperature=0.1
            )
            eval_result = json.loads(response.choices[0].message.content)
            self.log_window = []
            log_msg = f"🤖 质检审查: {'审核不通过' if eval_result['has_hallucination'] else '审核通过'}\n{eval_result['reason']}"
            self.log_and_notify("thought", log_msg)
            return eval_result
        except Exception as e:
            self.log_and_notify("thought", f"🤖 质检审查: 默认放行 ({str(e)})")
            return {"has_hallucination": False, "reason": f"审查异常，默认放行: {str(e)}"}

    def _ask_for_continue(self, eval_result=None):
        reason = eval_result.get("reason", "操作偏离预期或编造了不存在的信息。") if eval_result else "操作偏离预期或编造了不存在的信息。"
        reflection_prompt = f"""【系统严重警告：触发幻觉/错误拦截】请务必优先处理本条消息
外部审查模块指出了你在最近几轮操作中的问题：{reason}
你需要决定是纠错并继续，还是因为无法挽回而终止任务。
请严格以 JSON 格式输出：
{{
    "result": true 或 false,
    "summary": "如果为 true，简述纠错计划；如果为 false，说明客观理由。"
}}"""
        self.history.append({"role": "user", "content": reflection_prompt})
        try:
            self.log_and_notify("system", "🧠 触发自我反思：正在要求 Core 模型进行诊断和决策...")
            response = self.model.chat(messages=self.history, response_format={"type": "json_object"}, temperature=0.3)
            self._track_token_usage(response)
            message_content = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": message_content})
            result_data = json.loads(message_content)
            return {"result": bool(result_data.get("result", True)), "summary": str(result_data.get("summary", ""))}
        except Exception as e:
            self.log_and_notify("error", f"❌ 请求反思失败: {e}，默认继续")
            return {"result": True, "summary": "❌ 反思异常，默认继续"}

    def resume(self):
        self.log_and_notify("system", "🔄 尝试从断点恢复任务...")
        if not self.history:
            self.log_and_notify("error", "❌ 历史记录为空，无法恢复。")
            return "❌ 恢复失败"
        last_msg = self.history[-1]
        if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
            self.log_and_notify("system", "🛠️ 检测到断点处缺失工具回传结果。策略：撤销最近一次未完成的思考，让模型重新规划。")
            self.history.pop()

        if self.window_token > 110000 or len(self.history) > 140:
            self.log_and_notify("system", "⚠️ 策略：恢复前强制执行记忆压缩。")
            try:
                self.memory_flush(check_mode=False)
            except Exception as e:
                self.log_and_notify("error", f"❌ 恢复前压缩记忆失败: {e}")

        self.log_and_notify("system", "🚀 环境排错完成，重新启动任务流。")
        self.state = "ready"
        return self.run()

    def submit_request(self, new_prompt: str):
        self.log_and_notify("system", f"🗣️ 收到追加指令/需求: {new_prompt}")
        if self.state in ["running", "ready"]:
            with self._lock:
                self.pending_force_push.append(
                    f"【紧急追加请求】：用户刚刚下发了新的指示，请优先响应以下内容：\n{new_prompt}")
            self.log_and_notify("system", "⚡ 任务正在执行中，已将追加指令动态注入到下一个思考循环。")
            return "✅ 指令已动态注入当前工作流"
        else:
            self.history.append({"role": "user", "content": f"[User Follow-up Request]: \n{new_prompt}\n"})
            self.step = 0
            self.state = "ready"
            self.save_checkpoint()
            self.log_and_notify("system", "🚀 任务休眠/已结束，上下文已就绪，正在重新唤醒执行...")
            threading.Thread(target=self.resume, daemon=True).start()
            return "✅ 指令已收到，任务正在后台重新唤醒"


def auto_discover_experts():
    import importlib
    import os
    if "general" not in BaseTask._EXPERT_REGISTRY:
        BaseTask._EXPERT_REGISTRY["general"] = {
            "class": BaseTask,
            "description": "通用型任务专家，适用于常规查询、搜索、日常助理和简单的步骤执行。",
            "parameters": {}
        }
        print(f"✅ 自动注册默认任务专家: general -> BaseTask")
    try:
        expert_root = os.path.join(os.path.dirname(__file__), "expert")
        if not os.path.isdir(expert_root):
            return
        module_count = 0
        failed_modules = []
        for expert_name in os.listdir(expert_root):
            expert_path = os.path.join(expert_root, expert_name)
            task_file = os.path.join(expert_path, "task.py")
            if os.path.isfile(task_file):
                module_name = f"src.models.expert.{expert_name}.task"
                try:
                    importlib.import_module(module_name)
                    module_count += 1
                except Exception as e:
                    failed_modules.append((module_name, str(e)))
        if failed_modules and module_count == 0:
            print(f"⚠️ 所有专家模块加载失败:")
            for mod, err in failed_modules:
                print(f"   ├─ {mod}: {err}")
        elif failed_modules:
            print(f"📦 已成功加载 {module_count} 个专家模块, {len(failed_modules)} 个失败:")
            for mod, err in failed_modules:
                print(f"   ⚠️  {mod}: {err}")
    except Exception as e:
        print(f"❌ 扫描专家目录失败: {e}")
        import traceback
        traceback.print_exc()


class TaskFactory:
    @staticmethod
    def create_task(expert_type: str, task_name: str, prompt: str, core: str, judger: str, **kwargs):
        auto_discover_experts()
        if expert_type not in BaseTask._EXPERT_REGISTRY:
            raise ValueError(f"❌ 注册表中未找到指定的专家类型: {expert_type}")

        registry_info = BaseTask._EXPERT_REGISTRY[expert_type]
        TargetClass = registry_info["class"]

        validated_args = {}
        for param_name, param_meta in registry_info["parameters"].items():
            if param_meta.get("required", False) and param_name not in kwargs:
                raise ValueError(f"❌ 创建 {expert_type} 专家任务失败：缺失必填参数 '{param_name}'")
            validated_args[param_name] = kwargs.get(param_name, param_meta.get("default"))

        task_instance = TargetClass(
            task_name=task_name,
            prompt=prompt,
            core=core,
            judger=judger,
            **validated_args
        )
        return task_instance

def auto_load_all_tasks():
    auto_discover_experts()
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        return
    class_name_to_expert = {info["class"].__name__: info["class"] for info in BaseTask._EXPERT_REGISTRY.values()}

    for task_dir in os.listdir(checkpoints_dir):
        full_path = os.path.join(checkpoints_dir, task_dir)
        checkpoint_file = os.path.join(full_path, "checkpoint.json")
        if os.path.isdir(full_path) and os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                expert_class_name = state.get("expert_type", "BaseTask")
                TargetClass = class_name_to_expert.get(expert_class_name, BaseTask)
                task = TargetClass.load_checkpoint(full_path)
                if task:
                    print(f"✅ 成功通过 [{expert_class_name}] 恢复任务: {task.task_id}")
            except Exception as e:
                print(f"❌ 自动恢复任务目录 {task_dir} 失败: {e}")