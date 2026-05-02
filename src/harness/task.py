import datetime
import json
import os
import threading
import uuid
import time
import traceback
from typing import Dict

from json_repair import repair_json

from src.model import Model
from src.utils.config import DATA_DIR, get_model_config
from src.utils.enums import TaskState, LogType
from src.tool.utils.route import dispatch_tool

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
        set_task_state(task_id, TaskState.KILLED)
        return True
    return False


def inject_task_instruction(task_id: str, content: str):
    if task_id in TASK_INSTANCES:
        return TASK_INSTANCES[task_id].submit_request(content)
    return False


class BaseTask:
    """
    通用智能体任务基类 (BaseTask) - 原子化重构版
    提供底层大模型通讯、工具解析、记忆管理、幻觉审查与断点恢复等基础设施。
    """
    _EXPERT_REGISTRY = {}

    def __init_subclass__(cls, expert_type=None, description="", parameters=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if expert_type:
            cls._EXPERT_REGISTRY[expert_type] = {
                "class": cls,
                "description": description,
                "parameters": parameters or {}
            }
            print(f"✅ 自动注册子任务专家: {expert_type} -> {cls.__name__}")

    def __init__(self, task_name, prompt, core):
        self.task_name = task_name
        self.prompt = prompt
        self.core = core
        self.task_id = uuid.uuid4().hex
        self.model = Model(core)
        self.key_prefix = self.model.key_prefix
        self.state = TaskState.READY
        self.time_step = {"start": False, "mock": False} # 标记节点完成情况
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self.pending_force_push = []
        self.create_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.token_usage = 0
        self.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}")
        self.main_history = []

        if self.task_id not in TASK_INSTANCES:
            TASK_INSTANCES[self.task_id] = self
        self.save_checkpoints()

    # ==========================================
    # 生命钩子与底层工具
    # ==========================================
    def _on_save_state(self) -> dict:
        return {}

    def _on_restore_state(self, state: dict):
        pass

    def _handle_extend_tool(self, tool_name: str, arguments: dict):
        return  ""

    def _build_system_prompt(self):
        return """# 角色定义\n你是一个任务执行专家。你的核心任务是理解老板下发的需求，并合理调度工具高效解决问题。"""

    def _cleanup_resources(self):
        try:
            from src.tool.bash import close_session
            close_session(session_id=self.task_id)
            self.log_and_notify(LogType.SYSTEM, "🧹 已自动回收任务专属的 Shell 终端环境")
        except Exception as e:
            self.log_and_notify(LogType.SYSTEM, f"⚠️ 自动回收 Shell 失败: {e}")

    def log_and_notify(self, log_type: str, content: str, metadata=None):
        log_dir = self.checkpoint_dir
        os.makedirs(log_dir, exist_ok=True)
        log_data = {
            "timestamp": time.time(),
            "card_type": log_type,
            "content": content,
            "metadata": metadata or {}
        }
        with self._io_lock:
            with open(os.path.join(log_dir, "log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
                f.flush()
        with task_set_lock:
            dirty_tasks.add(self.task_id)

    # ==========================================
    # 原子化核心工作流
    # ==========================================
    def run(self):
        """主循环：编排各原子化步骤形成工作流"""
        if not self.time_step["start"]:
            self.state = TaskState.RUNNING
            self.time_step["start"] = True
        else:
            pass
        try:
            if not self.time_step["mock"]:
                self.main_history = []
                self.main_history.append({"role":"system", "content":self._build_system_prompt()})
                self.main_history.append({"role":"user", "content":self.prompt})
                self.step_mock_loop(self.main_history)
                self.time_step["mock"] = True
            else:
                pass
            if self.handle_completed():
                # 总体任务成功
                return True
            else:
                # 总体任务失败
                return False
        finally:
            if hasattr(self, 'model') and self.model:
                self.model.unbind()

    def track_token(self, response):
        """记录 Token，更新全局属性"""
        total = 0
        if hasattr(response, "usage") and response.usage is not None:
            total = getattr(response.usage, "total_tokens", 0)
        return total


    def run_llm_step(self, messages: list, tools: list = None):
        """调用大模型，传入上下文与工具"""
        self.check_kill()
        messages = self.check_tool(messages)
        self.check_memory(messages)
        self.save_checkpoints()
        response = self.model.chat(messages=messages, tools=tools)
        self.save_checkpoints()
        self.token_usage += self.track_token(response)
        return response

    def step_mock_loop(self, messages):
        step = 0
        max_steps = 500
        while step < max_steps:
            step += 1
            try:
                self.check_request()
                # 1. 执行 LLM 思考步骤
                response = self.run_llm_step(messages=messages, tools=self.get_base_tool_schema())
                assistant_msg = response.choices[0].message
                messages.append(assistant_msg.model_dump(exclude_none=True))
                tool_calling = self._extract_tool_calling(response)
                # 2. 处理无工具调用
                if not tool_calling:
                    return True
                # 3. 执行工具调用
                tool_messages = self.run_tool_calling(response)
                if tool_messages:
                    messages.extend(tool_messages)

            except InterruptedError as e:
                self.state = TaskState.ERROR
                self._cleanup_resources()
                self.log_and_notify(LogType.SYSTEM, str(e))
                self.save_checkpoints()
                break
            except KeyboardInterrupt:
                self.state = TaskState.ERROR
                self._cleanup_resources()
                self.log_and_notify(LogType.SYSTEM, "⚠️ 检测到强制中断 (Ctrl+C)，保存现场...")
                self.save_checkpoints()
                break
            except Exception as e:
                self.state = TaskState.ERROR
                self._cleanup_resources()
                self.log_and_notify(LogType.ERROR, f"❌ 运行发生异常: {traceback.format_exc()}")
                self.save_checkpoints()
                break
        if step >= max_steps and self.state != TaskState.COMPLETED:
            self.state = TaskState.ERROR
            self._cleanup_resources()
            self.save_checkpoints()
            self.log_and_notify(LogType.ERROR, f"❌ 任务失败: 超出最大思考步数 ({max_steps})")
            return f"❌ 任务失败: 超出最大思考步数 ({max_steps})"

    def run_tool_calling(self, response) -> list:
        """
        解析 response，调用普通工具。
        返回一个包含工具执行结果的 message 字典列表，供外部合并到 history 中。
        """
        tool_calls = self._extract_tool_calling(response)
        tool_messages = []

        for tc in tool_calls:
            original_tool_name = tc.function.name
            target_tool_name = original_tool_name
            arguments_str = tc.function.arguments
            arguments = {}

            # 1. 容错解析参数
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    if repair_json:
                        try:
                            arguments = repair_json(arguments_str, return_objects=True)
                        except Exception:
                            pass

            # 2. 动态工具路由处理
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

            # 3. 拦截损坏参数
            if not isinstance(arguments, dict):
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": original_tool_name,
                    "content": "❌ 系统拦截：工具参数格式严重损坏，请检查 JSON 格式！"
                })
                continue

            # 4. 会话注入
            if target_tool_name in ["Bash"]:
                arguments["session_id"] = self.task_id

            args_str = ", ".join([f"{k}={repr(v)}" for k, v in arguments.items()])
            self.log_and_notify(LogType.TOOL_CALL, f"🔧 助手调起工具: {target_tool_name}({args_str})",
                                metadata={"arguments": arguments})

            # 5. 执行工具
            if target_tool_name not in self.get_base_tool_name():
                result = self._handle_extend_tool(target_tool_name, arguments)
            else:
                result = dispatch_tool(target_tool_name, arguments)

            self.log_and_notify(LogType.TOOL, f"📦 工具回传结果: {result}")

            # 6. 收集工具结果
            finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": result
            })
        return tool_messages

    def check_tool(self, history: list) -> list:
        """闭合排查：检查提供的历史记录最后一次工具调用是否闭环，若断层则回滚"""
        last_assistant_idx = -1
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("role") == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx != -1:
            assistant_msg = history[last_assistant_idx]
            tool_calls = assistant_msg.get("tool_calls", [])

            if tool_calls:
                required_ids = {tc["id"] for tc in tool_calls} if isinstance(tool_calls[0], dict) else {tc.id for tc in
                                                                                                        tool_calls}
                found_ids = set()
                is_valid = True

                for i in range(last_assistant_idx + 1, len(history)):
                    msg = history[i]
                    if msg.get("role") != "tool":
                        is_valid = False
                        break
                    found_ids.add(msg.get("tool_call_id"))

                if not is_valid or required_ids != found_ids:
                    self.log_and_notify(LogType.SYSTEM, "🛠️ 检测到断点处工具调用未完全闭环，执行状态安全回滚...")
                    return history[:last_assistant_idx]
        return history

    def check_kill(self):
        """强杀否"""
        if self._killed:
            self.state = TaskState.KILLED
            raise InterruptedError(f"任务 {self.task_id} 被强杀。")

    def check_memory(self, message):
        """溢出否：触发记忆清理机制"""
        pass

    def check_completed(self, tool_calling: list) -> bool:
        """完成否"""
        return any(tc.function.name == "task_done" for tc in tool_calling)

    def check_request(self):
        """有无追加指令（提取 pending_force_push 注入历史）"""
        pass

    def handle_completed(self):
        """标记完成后的验收审查与资源收尾"""
        return True

    def get_base_tool_schema(self) -> list:
        """获取基础工具的 schema"""
        try:
            from src.tool import BASE_TASK_TOOL_SCHEMA
            return BASE_TASK_TOOL_SCHEMA
        except ImportError:
            return []

    def get_base_tool_name(self) -> set:
        """获取 base task 工具名集合，用于快速判断工具归属"""
        try:
            from src.tool import BASE_TASK_TOOL_SCHEMA
            return {schema["function"]["name"] for schema in BASE_TASK_TOOL_SCHEMA}
        except ImportError:
            return set()

    def memory_flush(self, history: list) -> list:
        """压缩记忆核心逻辑，返回截断/压缩后的历史"""
        pass

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        """从磁盘反序列化恢复任务对象实例"""
        try:
            checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
            history_path = os.path.join(checkpoint_dir, "history.json")

            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)

            if cls is BaseTask:
                expert_class_name = state.get("expert_type", "BaseTask")
                class_name_to_expert = {info["class"].__name__: info["class"] for info in cls._EXPERT_REGISTRY.values()}
                TargetClass = class_name_to_expert.get(expert_class_name, BaseTask)
                task = TargetClass.__new__(TargetClass)
            else:
                task = cls.__new__(cls)

            task.task_id = state.get("task_id")
            task.task_name = state.get("name", "Unknown")
            task.create_time = state.get("create_time")
            task.prompt = state.get("prompt", "")
            task.core = state.get("core", "")
            task.state = state.get("state", TaskState.READY)

            if task.state in [TaskState.RUNNING]:
                task.state = TaskState.INTERRUPTED

            task.token_usage = state.get("token_usage", 0)
            task.time_step = state.get("time_step", {"start": False, "mock": False})
            task.pending_force_push = state.get("pending_force_push", [])
            task.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{task.task_name}_{task.task_id}")
            task.main_history = history

            if task.state in [TaskState.READY, TaskState.RUNNING, TaskState.INTERRUPTED]:
                saved_key_prefix = state.get("key_prefix")
                task.model = Model(task.core, recovered_key_prefix=saved_key_prefix) if task.core else None
                if task.model:
                    task.model.bind_task(task.task_id, task.task_name)
            else:
                task.model = None

            task._lock = threading.Lock()
            task._io_lock = threading.Lock()
            task._killed = False
            task._on_restore_state(state.get("extra_state", {}))

            existing_task = TASK_INSTANCES.get(task.task_id)
            if existing_task and existing_task.state == TaskState.RUNNING:
                return existing_task

            TASK_INSTANCES[task.task_id] = task
            return task
        except Exception as e:
            print(f"❌ [Task Checkpoint] 加载失败 {checkpoint_dir}: {traceback.format_exc()}")
            return None

    def save_checkpoints(self):
        """保存任务状态与历史至磁盘"""
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        history_path = os.path.join(self.checkpoint_dir, "history.json")
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self.main_history, f, ensure_ascii=False, indent=2)

        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        state = {
            "task_id": self.task_id,
            "name": self.task_name,
            "expert_type": self.__class__.__name__,
            "create_time": self.create_time,
            "prompt": self.prompt,
            "core": self.core,
            "key_prefix": self.model.key_prefix if self.model else None,
            "state": self.state,
            "token_usage": self.token_usage,
            "time_step": self.time_step,
            "checkpoint_dir": self.checkpoint_dir,
            "pending_force_push": self.pending_force_push,
            "extra_state": self._on_save_state(),
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def submit_request(self, new_prompt: str = "继续执行", branch_tag=None):
        """处理外部干预或继续执行指令，按需唤醒沉睡任务"""
        pass

    # ==========================================
    # 其他辅助模块
    # ==========================================
    def kill(self):
        self._killed = True
        self.state = TaskState.KILLED
        if getattr(self, 'model', None):
            self.model.unbind()
        self._cleanup_resources()

    def _extract_tool_calling(self, response) -> list:
        if hasattr(response, 'choices') and len(response.choices) > 0:
            return getattr(response.choices[0].message, "tool_calls", []) or []
        return []


# === 工厂与恢复方法 ===
# [保留您提供的 auto_discover_experts, TaskFactory, auto_load_all_tasks, reload_task_by_id，已与 BaseTask 新结构兼容]


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
                module_name = f"src.harness.expert.{expert_name}.task"
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
    def create_task(expert_type: str, task_name: str, prompt: str, core: str, **kwargs):
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
            **validated_args
        )
        return task_instance

def auto_load_all_tasks():
    auto_discover_experts()
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        return
        
    # 【修改这里】：同时兼容 "CodingTask" 和 "coding" 两种 Key 的映射
    class_name_to_expert = {}
    for expert_key, info in BaseTask._EXPERT_REGISTRY.items():
        class_name_to_expert[info["class"].__name__] = info["class"] # 类名映射
        class_name_to_expert[expert_key] = info["class"]             # 别名映射 (兼容老数据)

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


def reload_task_by_id(task_id: str):
    """
    根据 task_id 精准查找并恢复指定的任务实例。
    """
    # 1. 如果任务已经在内存中处于激活状态，直接返回
    if task_id in TASK_INSTANCES:
        return TASK_INSTANCES[task_id]
    auto_discover_experts()
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        print(f"❌ 找不到存档总目录: {checkpoints_dir}")
        return None
    # 2. 由于新的命名规则为 {task_name}_{task_id}，可以直接通过后缀匹配文件夹
    target_dir = None
    for dir_name in os.listdir(checkpoints_dir):
        if dir_name.endswith(f"_{task_id}"):
            target_dir = os.path.join(checkpoints_dir, dir_name)
            break
    if not target_dir:
        print(f"❌ 未找到 task_id 为 {task_id} 的存档文件夹")
        return None
    checkpoint_file = os.path.join(target_dir, "checkpoint.json")
    if not os.path.exists(checkpoint_file):
        print(f"❌ 存档文件夹存在，但缺失 checkpoint.json: {target_dir}")
        return None
    # 3. 读取存档并动态实例化
    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        expert_class_name = state.get("expert_type", "BaseTask")
        # 兼容类名和别名映射
        class_name_to_expert = {}
        for expert_key, info in BaseTask._EXPERT_REGISTRY.items():
            class_name_to_expert[info["class"].__name__] = info["class"]
            class_name_to_expert[expert_key] = info["class"]
        TargetClass = class_name_to_expert.get(expert_class_name, BaseTask)
        # 调用子类/基类的 load_checkpoint 进行恢复
        task = TargetClass.load_checkpoint(target_dir)
        if task:
            print(f"✅ 成功通过 [{expert_class_name}] 精准恢复任务: {task.task_id}")
            return task
    except Exception as e:
        print(f"❌ 精准恢复任务 {task_id} 失败: {e}")
        return None