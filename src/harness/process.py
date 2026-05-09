import asyncio
import datetime
import importlib
import json
import os
import threading
import time
import traceback
import uuid
from collections import deque
from typing import Dict, Any, List

from json_repair import repair_json

from src.model import Model
from src.utils.config import DATA_DIR
from .enums import TaskState, NodeState
from src.tool.utils.route import dispatch_tool
from src.tool.bash import close_session

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


class Task:
    """
    通用智能体任务类 (Task) - 原子化重构版
    提供底层大模型通讯、工具解析、记忆管理、幻觉审查与断点恢复等基础设施。
    所有任务类型统一使用 JSON 拓扑图驱动，无需子类区分。
    """

    def __init__(self, task_name: str, prompt: str, core: str, graph_name: str = "default"):
        self.task_name = task_name
        self.prompt = prompt
        self.core = core
        self.task_id = uuid.uuid4().hex
        self.workplace = f"agent_vm/task_workplace/{self.task_id}"
        self.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}")

        # 实例化大模型
        self.model = Model(core)
        self.key_prefix = self.model.key_prefix

        # DAG 引擎状态
        self.graph_name = graph_name
        self.node_list: Dict[str, Any] = {}  # {node_id: NodeInstance}
        self.node_state: Dict[str, NodeState] = {}  # {node_id: NodeState}
        self.graph: Dict[str, Any] = {}  # 存放 nodes 和 edges 拓扑图
        self.pending_force_push: Dict[str, List[str]] = {}  # {node_id: [content1, ...]}
        self.state = TaskState.READY
        
        # 其他状态属性
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self.create_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.token_usage = 0
        self.result = False
        self.main_history = []
        self.dag_state = {}

        if self.task_id not in TASK_INSTANCES:
            TASK_INSTANCES[self.task_id] = self
        self.save_checkpoints()

        self.load_graph()

    def load_graph(self):
        """解析 JSON 并通过 importlib 动态加载节点，抛弃臃肿的 NODE_REGISTRY"""
        graph_path = os.path.join(os.path.dirname(__file__), "graph", f"{self.graph_name}.json")
        with open(graph_path, "r", encoding="utf-8") as f:
            self.graph = json.load(f)

        for node_data in self.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]  # 对应 node/ 下的文件夹名，如 "llm_chat"
            config = node_data.get("data", {})

            # 动态导入 node/{node_type}/node.py 模块
            try:
                module = importlib.import_module(f"harness.node.{node_type}.node")
                # 约定每个节点模块暴露一个 Node 类
                self.node_list[node_id] = module.Node(node_id=node_id, config=config)
                self.node_state[node_id] = NodeState.READY
            except Exception as e:
                print(f"❌ 加载节点模块失败 {node_type}: {e}")
                self.state = TaskState.ERROR

    def submit_request(self, node_id: str, content: str):
        """Human-in-the-loop：人类注入或干预"""
        if node_id not in self.node_list:
            print(f"❌ 未找到节点 {node_id}")
            return

        # 1. 注入 pending_force_push 队列
        if node_id not in self.pending_force_push:
            self.pending_force_push[node_id] = []
        self.pending_force_push[node_id].append(content)

        # 2. 状态机响应
        current_state = self.node_state[node_id]
        if current_state == NodeState.COMPLETED:
            # 修改已完成的节点，触发下游雪崩重置 (BFS)
            self._cascade_reset(node_id, content)
        elif current_state == NodeState.ERROR:
            # 修复了报错节点，将其置回 WAITING 准备重试
            self.node_state[node_id] = NodeState.WAITING

        # 3. 唤醒任务引擎
        if self.state != TaskState.RUNNING:
            asyncio.create_task(self.run())

    def _cascade_reset(self, start_node_id: str, human_instruction: str):
        """通过 BFS 将被人类打回的节点及其所有受波及的下游节点重置为 WAITING"""
        queue = deque([start_node_id])
        visited = set([start_node_id])
        self.node_state[start_node_id] = NodeState.WAITING
        edges = self.graph.get("edges", [])
        while queue:
            curr_id = queue.popleft()
            for edge in edges:
                if edge["source"] == curr_id:
                    target_id = edge["target"]
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append(target_id)
                        # 强制改变下游节点状态
                        self.node_state[target_id] = NodeState.WAITING
                        # 给下游注入级联上下文警告
                        cascade_msg = (
                            f"⚠️ 系统提示：前置节点【{start_node_id}】针对用户需求：“{human_instruction}” "
                            f"做了相应变更，请检查相应变更是否影响你的结果，并根据最新上下文重新生成。"
                        )
                        if target_id not in self.pending_force_push:
                            self.pending_force_push[target_id] = []
                        self.pending_force_push[target_id].append(cascade_msg)

    async def run(self, max_concurrency: int = 5):
        """基于 DAG 的并发执行 (优化版：单节点即时结算，流水线调度)"""
        self.state = TaskState.RUNNING

        # 维护当前正在运行的协程任务字典 { asyncio.Task : node_id }
        running_tasks = {}

        while True:
            # 1. 填补并发槽位：只要没达到最大并发数，就尽力塞入可运行的节点
            while len(running_tasks) < max_concurrency:
                runnable_nodes = self._get_runnable_nodes()
                # 过滤掉那些已经在运行池里的节点
                nodes_to_start = [n for n in runnable_nodes if n not in running_tasks.values()]
                if not nodes_to_start:
                    break  # 当前没有新节点可以触发了，跳出填充循环
                for node_id in nodes_to_start:
                    # 标记为运行中，防止重复调度
                    self.node_state[node_id] = NodeState.RUNNING
                    inputs = self._gather_inputs(node_id)
                    force_push_msgs = self.pending_force_push.pop(node_id, [])
                    node_instance = self.node_list[node_id]
                    # 创建单个独立协程并塞入运行池
                    # 核心变化：将 self 作为 context 传给节点！
                    task = asyncio.create_task(node_instance.execute(inputs, force_push_msgs, context=self))
                    running_tasks[task] = node_id

                    print(f"🚀 触发节点执行: {node_id} (当前并发数: {len(running_tasks)})")
            # 2. 终止条件检查
            if not running_tasks:
                if all(s == NodeState.COMPLETED for s in self.node_state.values()):
                    print("✅ 所有节点执行完毕，任务完成。")
                    self.state = TaskState.COMPLETED
                else:
                    print("⏸️ 任务挂起：存在 ERROR 节点或需要人类干预，引擎进入休眠。")
                    self.state = TaskState.INTERRUPTED
                break
            # 3. 核心机制：监听池子中谁先完成 (即时结算！)
            # 这里会阻塞等待，但只要有任何一个或多个节点执行完毕，就会立刻放行
            done, pending = await asyncio.wait(
                running_tasks.keys(),
                return_when=asyncio.FIRST_COMPLETED
            )
            # 4. 结算已经完成的这批任务（通常只有1个，也可能由于速度极快有多个同时完成）
            for task in done:
                node_id = running_tasks.pop(task)  # 从运行池中移除，腾出并发槽位
                try:
                    # 获取该节点的返回结果
                    result = task.result()
                    self.node_state[node_id] = NodeState.COMPLETED
                    self.node_list[node_id].outputs = result
                    print(f"🟢 节点 {node_id} 结算完成，释放下游。")
                except Exception as e:
                    # 错误隔离：只把当前崩溃的节点标记为 ERROR，不影响 pending 里的其他任务
                    self.node_state[node_id] = NodeState.ERROR
                    print(f"❌ 节点 {node_id} 执行崩溃: {e}")
            # 每次有节点结算完毕，保存一次全量状态
            self.save_checkpoints()

    def _get_runnable_nodes(self) -> List[str]:
        """寻找依赖已经满足的可执行节点"""
        runnable = []
        edges = self.graph.get("edges", [])

        for node_id, state in self.node_state.items():
            if state in (NodeState.READY, NodeState.WAITING):
                can_run = True
                for edge in edges:
                    if edge["target"] == node_id:
                        # 如果上游节点没有完成，则当前节点不能跑
                        if self.node_state[edge["source"]] != NodeState.COMPLETED:
                            can_run = False
                            break
                if can_run:
                    runnable.append(node_id)
        return runnable

    def _gather_inputs(self, node_id: str) -> Dict[str, Any]:
        """根据连线从上游节点的 outputs 中提取当前节点的 inputs"""
        inputs = {}
        for edge in self.graph.get("edges", []):
            if edge["target"] == node_id:
                source_node = self.node_list[edge["source"]]
                src_port = edge.get("sourceHandle", "default")
                tgt_port = edge.get("targetHandle", "default")

                if hasattr(source_node, 'outputs') and source_node.outputs:
                    inputs[tgt_port] = source_node.outputs.get(src_port)
        return inputs

    def _on_save_state(self) -> dict:
        return {}

    def _on_restore_state(self, state: dict):
        pass

    def _handle_extend_tool(self, tool_name: str, arguments: dict):
        return "模拟工具调用成功"

    def _build_system_prompt(self):
        return """# 角色定义\n你是一个任务执行专家。你的核心任务是理解老板下发的需求，并合理调度工具高效解决问题。"""

    def _cleanup_resources(self):
        try:
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

    def _build_default_graph(self) -> dict:
        """
        生成一个默认的图定义（等同于以前 hardcode 的流程）。
        未来这里将直接读取前端拖拽生成的 JSON 结构。
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self.prompt
        workplace = self.workplace
        return {
            "nodes": [
                {"id": "node_sys_msg", "type": "message_card_builder", "data": {"role": "system", "content": system_prompt}},
                {"id": "node_user_msg", "type": "message_card_builder", "data": {"role": "user", "content": user_prompt}},
                {"id": "node_appender", "type": "appender"},
                {"id": "node_tools", "type": "tool_kit"},
                {"id": "node_loop", "type": "file_output_loop", "data": {"file_path": f"{workplace}/FINISHED.md"}}
            ],
            "edges": [
                {"source": "node_sys_msg", "target": "node_appender", "targetHandle": "base_list"},
                {"source": "node_user_msg", "target": "node_appender", "targetHandle": "append_list"},
                {"source": "node_appender", "target": "node_loop", "targetHandle": "messages"},
                {"source": "node_tools", "target": "node_loop", "targetHandle": "tools"}
            ]
        }

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
        if self.check_memory(messages):
            self.flusher(messages)
        self.save_checkpoints()
        response = self.model.chat(messages=messages, tools=tools)
        self.save_checkpoints()
        self.token_usage += self.track_token(response)
        return response

    def check_file_exist(self, file_path: str):
        if os.path.exists(file_path):
            return True
        return False

    def global_tool_kit(self):
        from src.tool import BASE_TASK_TOOL_SCHEMA
        task_done_schema = {
            "type": "function",
            "function": {
                "name": "task_done",
                "description": "标记当前阶段任务完成，表示当前阶段的工作已完成",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "对当前阶段的简单总结"
                        }
                    },
                    "required": ["summary"]
                }
            }
        }
        return BASE_TASK_TOOL_SCHEMA + [task_done_schema]

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
                required_ids = {tc["id"] for tc in tool_calls} if isinstance(tool_calls[0], dict) else {tc.id for tc in tool_calls}
                found_ids = set()
                is_valid = True
                for i in range(last_assistant_idx + 1, len(history)):
                    msg = history[i]
                    if msg.get("role") == "tool":
                        found_ids.add(msg.get("tool_call_id"))
                    else:
                        if required_ids != found_ids:
                            is_valid = False
                        break
                if required_ids != found_ids:
                    is_valid = False

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
        return False

    def handle_completed(self):
        """标记完成后的验收审查与资源收尾"""
        self.state = TaskState.COMPLETED
        if self.result:
            result_str = f"✅ 任务完成，工作产物痕迹存放在：{self.workplace}"
        else:
            result_str = f"❌ 任务失败，工作产物痕迹存放在：{self.workplace}"
        return result_str

    def get_base_tool_name(self) -> set:
        """获取 base task 工具名集合，用于快速判断工具归属"""
        from src.tool import BASE_TASK_TOOL_SCHEMA
        return {schema["function"]["name"] for schema in BASE_TASK_TOOL_SCHEMA}

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
            
            # 直接生成 Task 实例，不再需要复杂的类查找逻辑
            task = cls.__new__(cls)
            
            task.task_id = state.get("task_id")
            task.task_name = state.get("name", "Unknown")
            task.graph_name = state.get("graph_name", "default")  # 从存档读取使用的图
            task.create_time = state.get("create_time")
            task.prompt = state.get("prompt", "")
            task.core = state.get("core", "")
            task.state = state.get("state", TaskState.READY)
            if task.state in [TaskState.RUNNING]:
                task.state = TaskState.INTERRUPTED
            task.token_usage = state.get("token_usage", 0)
            task.dag_state = state.get("dag_state", {})
            task.pending_force_push = state.get("pending_force_push", {})
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
            "graph_name": self.graph_name,  # 用 graph_name 替代以前的 expert_type
            "create_time": self.create_time,
            "prompt": self.prompt,
            "core": self.core,
            "key_prefix": self.model.key_prefix if self.model else None,
            "state": self.state,
            "token_usage": self.token_usage,
            "dag_state": self.dag_state,
            "checkpoint_dir": self.checkpoint_dir,
            "pending_force_push": self.pending_force_push,
            "extra_state": self._on_save_state(),
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def submit_request(self, new_prompt: str = "继续执行", branch_tag=None):
        """处理外部干预或继续执行指令，按需唤醒沉睡任务"""
        pass

    def kill(self):
        self._killed = True
        self.state = TaskState.KILLED
        if getattr(self, 'model', None):
            self.model.unbind()
        self._cleanup_resources()

    def reload(self):
        """重新标记任务状态并运行"""
        self.state = TaskState.RUNNING
        self._killed = False
        return self.run()

    def flusher(self, messages, tools=None):
        pass


# --- 替代以前复杂的 TaskFactory，现在创建任务只需一行代码 ---
# task = Task(task_name="写代码", prompt="写个贪吃蛇", core="gpt-4o", graph_name="coder_workflow")


def auto_load_all_tasks():
    """扫描存档目录，极简恢复所有任务"""
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        return

    for task_dir in os.listdir(checkpoints_dir):
        full_path = os.path.join(checkpoints_dir, task_dir)
        checkpoint_file = os.path.join(full_path, "checkpoint.json")
        if os.path.isdir(full_path) and os.path.exists(checkpoint_file):
            try:
                task = Task.load_checkpoint(full_path)
                if task:
                    print(f"✅ 成功恢复任务: {task.task_id} (图表: {task.graph_name})")
            except Exception as e:
                print(f"❌ 自动恢复任务目录 {task_dir} 失败: {e}")


def reload_task_by_id(task_id: str):
    """根据 task_id 极简恢复单个任务"""
    if task_id in TASK_INSTANCES:
        return TASK_INSTANCES[task_id]
        
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        print(f"❌ 找不到存档总目录: {checkpoints_dir}")
        return None
        
    for dir_name in os.listdir(checkpoints_dir):
        if dir_name.endswith(f"_{task_id}"):
            target_dir = os.path.join(checkpoints_dir, dir_name)
            try:
                task = Task.load_checkpoint(target_dir)
                if task:
                    print(f"✅ 成功精准恢复任务: {task.task_id}")
                    return task
            except Exception as e:
                print(f"❌ 精准恢复任务 {task_id} 失败: {e}")
                return None
    return None