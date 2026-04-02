import datetime
import json
import os
import threading
import uuid
import time

from json_repair import repair_json

from src.models.model import Model
from src.utils.config import TOOL_INDEX_FILE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "data"))

TASK_INSTANCES = {}
dirty_tasks = set()
task_set_lock = threading.Lock()

def set_task_state(task_id, state):
    instance = TASK_INSTANCES.get(task_id)
    if instance:
        instance.state = state

def kill_task(task_id):
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].kill()
        set_task_state(task_id, "killed")
        return True
    return False

def inject_task_instruction(task_id: str, content: str):
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].force_push(content)
        return True
    return False

class Task:
    def __init__(self, prompt, core, task_name):
        self.prompt = prompt
        self.system_prompt = self._build_system_prompt()
        self.core = core
        self.task_name = task_name
        self.history = []
        self.task_id = uuid.uuid4().hex
        self.client = Model(core).client
        self.state = "ready"
        self.step = 0
        self.dynamic_tool = [] # 用于存放本次任务core所调用的所有fetch_tool的schema，每十轮对话清空一次
        self._lock = threading.Lock()
        self._killed = False
        self.pending_force_push = None
        self.create_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.current_plan = ""
        self.history.append({"role": "system", "content": self.system_prompt})
        self.history.append({"role": "user", "content": f"[User Request]: \n{self.prompt}\n"})
        if not TASK_INSTANCES.get(self.task_id, None):
            TASK_INSTANCES[self.task_id] = self
        self.log_and_notify("system", "🧾 已加载统一 Agent 工作流上下文")
    def force_push(self, content):
        self.pending_force_push = content

    def run(self):
        max_steps = 150
        self.state = "running"
        while self.step < max_steps:
            self.step += 1
            try:
                response = self._run_llm_step()
                tool_calling = self._extract_tool_calling(response)
                if not tool_calling:
                    self.history.append({"role":"user","content":"检测到你没有使用任何工具，如已完成，必须使用task_done工具结束任务，如未完成，请继续"})
                else:
                    if self._is_completed(tool_calling):
                        summary = self._extract_summary(tool_calling)
                        self.state = "completed"
                        self.save_checkpoint()
                        return f"ok,{summary}"
                    else:
                        self._tool_calling(tool_calling)
                self.checker() # 检查是否需要memory_flush, forch_push, _check_kill, clean_dynamic_tool, 还有自动检查意外中断并提供解决方法
            except KeyboardInterrupt:
                self.state = "error"
                self.log_and_notify("system", "⚠️ 检测到强制中断 (Ctrl+C)，保存现场...")
                self.save_checkpoint()
                raise
            except Exception as e:
                self.state = "error"
                self.log_and_notify("error", f"❌ 运行发生异常: {e}")
                self.save_checkpoint()
                raise InterruptedError(f"任务异常中断: {e}")

        if self.state != "completed":
            self.state = "error"
            self.save_checkpoint()
            self.log_and_notify("error", f"❌ 任务失败: 超出最大思考步数 ({max_steps})")
            return "renwushibai"

    def save_checkpoint(self):
        checkpoint_dir = os.path.join("data", "checkpoints", "task", f"{self.task_name}_{self.create_time}")
        os.makedirs(checkpoint_dir, exist_ok=True)
        
        history_path = os.path.join(checkpoint_dir, "history.json")
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        state = {
            "task_id": self.task_id,
            "name": self.task_name,
            "create_time": self.create_time,
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "history": self.history,
            "state": self.state,
            "dynamic_tool": self.dynamic_tool,
            "current_plan": self.current_plan,
            "step": self.step
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        try:
            checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            task = cls(
                task_name=state.get("name", "Unknown"),
                prompt=state.get("prompt", ""),
                core="openai:gpt-4o",
            )
            task.state = state.get("state", None)
            task.creat_time = state.get("creat_time", task.creat_time)
            task.dynamic_tools = state.get("dynamic_tool", [])
            task.system_prompt = state.get("system_prompt", None)
            task.current_plan = state.get("current_plan", None)
            TASK_INSTANCES.pop(task.task_id, None)
            task.task_id = state.get("task_id", None)
            TASK_INSTANCES[task.task_id] = task
            return task
        except Exception as e:
            print(f"❌ [Task Checkpoint] 加载失败 {checkpoint_dir}: {e}")
            return None

    def _run_llm_step(self):
        """完全解耦的 LLM 请求封装"""
        model_name = self.core.split(":")[-1] if ':' in self.core else self.core
        from src.plugins.route.task_tool import TASK_TOOLS
        from src.plugins.plugin_manager import BASE_TOOLS
        current_tools = list(BASE_TOOLS) + list(TASK_TOOLS)
        if self.dynamic_tool:
            current_tools.extend([item["schema"] for item in self.dynamic_tool])
        kwargs = {
            "model": model_name,
            "messages": self.history,
        }
        if current_tools:
            kwargs["tools"] = current_tools
        response = self.client.chat.completions.create(**kwargs)
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
        print(content)
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

    def _extract_summary(self, tool_calls: list) -> str:
        for tc in tool_calls:
            if tc.function.name == "task_done":
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    return args.get("summary", "无交付说明")
                except Exception:
                    return tc.function.arguments
        return "无交付说明"

    def checker(self):
        """生命周期与环境维护检查器"""
        if self._killed:
            self.state = "killed"
            raise InterruptedError(f"任务 {self.task_id} 被强杀。")
        local_push = None
        with self._lock:
            if self.pending_force_push:
                local_push = self.pending_force_push
                self.pending_force_push = None

        if local_push:
            self.history.append({
                "role": "user",
                "content": f"[System Warning] You should suspend your action and handle this message first!\n{local_push}"
            })

        # 每 10 轮清理动态工具 schema 避免上下文爆炸
        if self.step % 10 == 0:
            self.dynamic_tool.clear()
            self.log_and_notify("system", "🧹 已周期清理动态工具缓存")

        self.memory_flush()

    def _build_system_prompt(self):
        return "你是一个顶级的 AI 软件工程专家..."

    def memory_flush(self, check_mode=True, max_tokens=120000):
        messages_str = json.dumps(self.history, ensure_ascii=False)
        current_tokens = len(messages_str)
        if check_mode and (current_tokens <= max_tokens or len(self.history) <= 150):
            return
        self.log_and_notify("system", f"⚠️ 触发记忆截断: 当前共约 {current_tokens} tokens。正在进行上下文压缩...")
        alert_prompt = """【系统警告：记忆容量即将溢出】
系统即将物理抹除你最早期的一批交互记忆。
请你现在对**此前的所有任务进度、关键决策、已发现的代码规律以及目前的阻塞点**进行全面总结，形成一份简单明了的“核心备忘录”，不要用markdown。
这份备忘录将作为你承上启下的唯一凭证，务必包含所有关键信息！"""
        self.history.append({"role": "user", "content": alert_prompt})
        try:
            model_name = self.core.split(":")[-1] if ':' in self.core else self.core
            response = self.client.chat.completions.create(model=model_name, messages=self.history)
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

    def _tool_calling(self, tool_calling):
        for tool_call in tool_calling:
            tool_name = tool_call.function.name
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

            args_str = ", ".join([f'{k}={repr(v)}' for k, v in arguments.items()])
            print(f"🔧 助手调起工具: {tool_name}({args_str})")
            target_route = None
            target_plugin = None

            from src.plugins.route.task_tool import TASK_TOOL_FUNCTIONS
            task_tool_names = list(TASK_TOOL_FUNCTIONS.keys())

            if tool_name in task_tool_names:
                from src.plugins.route.task_tool import call_task_tool
                result_str = call_task_tool(tool_name, arguments, self)
            else:
                for tool_item in self.dynamic_tool:
                    if tool_item.get("funct") == tool_name:
                        target_route = tool_item.get("route")
                        target_plugin = tool_item.get("plugin")
                        break

                if not target_route or not target_plugin:
                    if os.path.exists(TOOL_INDEX_FILE):
                        with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                tool_info = json.loads(line)
                                if tool_info["func"] == tool_name:
                                    target_route = tool_info["route"]
                                    target_plugin = tool_info["plugin"]
                                    break
                from src.plugins.plugin_manager import parse_tool
                result_str, new_schema_info = parse_tool(tool_name, arguments, route=target_route, plugin=target_plugin)
                if new_schema_info:
                    schemas_to_add = new_schema_info if isinstance(new_schema_info, list) else [new_schema_info]
                    for schema_item in schemas_to_add:
                        new_funct_name = schema_item["funct"]
                        self.dynamic_tool = [item for item in self.dynamic_tool if
                                              item.get("funct") != new_funct_name]
                        self.dynamic_tool.append(schema_item)
                self.log_and_notify("tool",f"📦 工具回传结果: {result_str}")
            self.history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": result_str
            })
    
    

