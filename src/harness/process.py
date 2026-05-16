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
from typing import Any, Dict, List

from src.model.facade import Model
from src.tool.bash import close_session
from src.utils.config import DATA_DIR

from .enums import LogType, NodeState, TaskState

TASK_INSTANCES = {}
dirty_tasks = set()
task_set_lock = threading.Lock()


def auto_load_all_tasks():
    """
    全局初始化：仅将磁盘中的任务读取到内存，不自动触发运行。
    让任务安安静静地躺在 TASK_INSTANCES 里，等待前端唤醒或追加指令。
    """
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
                    print(f"✅ 成功从磁盘加载任务到内存: {task.task_id}")
            except Exception as e:
                print(f"❌ 加载任务目录 {task_dir} 失败: {e}")


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


def inject_task_instruction(task_id: str, content: str, node_id: str = None):
    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES[task_id]
        if node_id:
            return task.submit_request(node_id, content)
        else:
            for n_id in task.node_list:
                task.submit_request(n_id, content)
            return True
    return False


class Task:
    def __init__(self, task_name: str, inputs: dict, core: str, graph_name: str = "default", task_id: str = None):
        self.task_id = task_id or uuid.uuid4().hex
        self.task_name = task_name
        self.inputs = inputs
        self.outputs = {}
        self.core = core
        self.graph_name = graph_name

        self.node_list = {}
        self.node_state = {}
        self.graph = {}
        self.pending_force_push = {}
        self.running_tasks = {}

        self.state = TaskState.READY
        self.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}")

        self.model = Model(core)
        self.key_prefix = self.model.key_prefix

        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self._loop = None
        self.create_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.token_usage = 0
        self.result = False
        self.main_history = []
        self.dag_state = {}
        self.init_error = None

        if self.task_id not in TASK_INSTANCES:
            TASK_INSTANCES[self.task_id] = self
        self.save_checkpoints()

        self.load_graph()

    def load_graph(self) -> dict:
        graph_path = os.path.join(os.path.dirname(__file__), "graph", f"{self.graph_name}.json")
        if not os.path.exists(graph_path):
            return {"status": "error", "message": f"找不到图表定义文件: {self.graph_name}.json"}

        with open(graph_path, "r", encoding="utf-8") as f:
            self.graph = json.load(f)

        global_schema = self.graph.get("global_schema", {})
        
        if not global_schema and "required_inputs" in self.graph:
            old_reqs = self.graph["required_inputs"]
            global_schema = {k: {"required": True, "description": v} for k, v in old_reqs.items()}

        missing_keys = []
        for req_key, schema_info in global_schema.items():
            is_req = schema_info.get("required", True)
            if is_req and (req_key not in self.inputs or self.inputs[req_key] is None):
                desc = schema_info.get("description", "无特定说明")
                missing_keys.append(f"'{req_key}' (描述: {desc})")

        if missing_keys:
            error_msg = f"初始化失败：缺失全局必填参数 {', '.join(missing_keys)}。请检查您的输入并重试。"
            self.state = TaskState.ERROR
            self.init_error = error_msg
            return {"status": "error", "message": error_msg}

        for node_data in self.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("config", node_data.get("data", {}))
            
            try:
                module = importlib.import_module(f"src.harness.node.extensions.{node_type}.node")
                self.node_list[node_id] = module.Node(node_id=node_id, config=config)
                self.node_state[node_id] = NodeState.READY
            except Exception as e:
                error_msg = f"节点加载失败 [{node_type}]: {e}"
                self.state = TaskState.ERROR
                self.init_error = error_msg
                return {"status": "error", "message": error_msg}

        return {"status": "success", "message": "图表解析与参数校验通过"}

    def submit_request(self, node_id: str, instruction: str) -> dict:
        if node_id not in self.node_list:
            return {"status": "error", "message": f"节点 {node_id} 不存在于当前任务中。"}

        from src.harness.node.agent_node import AgentNode
        if not isinstance(self.node_list[node_id], AgentNode):
            return {"status": "error", "message": f"拒绝操作：节点 {node_id} 不是 Agent 类型的节点，不支持指令注入或打回重做。"}

        self._cascade_reset(node_id)

        if node_id not in self.pending_force_push:
            self.pending_force_push[node_id] = []
        self.pending_force_push[node_id].append(instruction)

        if self.state in [TaskState.ERROR, TaskState.INTERRUPTED, TaskState.COMPLETED]:
            self.state = TaskState.READY
        self.save_checkpoints()

        return {"status": "success", "message": "指令已注入，链路已重置，等待引擎下一次 run()"}

    def _cascade_reset(self, start_node_id: str):
        queue = deque([(start_node_id, True)]) # 队列存 (node_id, 是否是源目标节点)
        visited = set([start_node_id])
        edges = self.graph.get("edges", [])

        while queue:
            curr_id, is_target = queue.popleft()

            self.node_state[curr_id] = NodeState.READY

            if curr_id in self.node_list:
                # 🌟 关键修复：目标节点不删档 (False)，下游节点全删档 (True)
                self.node_list[curr_id].reset(self, clear_backup=not is_target)

            # 🌟 必须加锁保护跨线程操作
            with self._lock:
                task_to_cancel = None
                for t, n_id in list(self.running_tasks.items()):
                    if n_id == curr_id:
                        task_to_cancel = t
                        break

                if task_to_cancel and not task_to_cancel.done():
                    if self._loop and self._loop.is_running():
                        self._loop.call_soon_threadsafe(task_to_cancel.cancel)
                    else:
                        task_to_cancel.cancel()
                    # 🌟 安全移除
                    self.running_tasks.pop(task_to_cancel, None)

            for edge in edges:
                if edge["source"] == curr_id:
                    target_id = edge["target"]
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append((target_id, False)) # 下游节点全部标记为 False

    async def run(self, max_concurrency: int = 5):
        if self.state == TaskState.ERROR and self.init_error:
            return {"status": "error", "message": self.init_error}

        self._loop = asyncio.get_running_loop()
        self.state = TaskState.RUNNING
        self.running_tasks.clear()

        try:
            while True:
                if self._killed:
                    self._cancel_all_tasks(self.running_tasks)
                    self.state = TaskState.KILLED
                    break

                runnable_nodes = self._get_runnable_nodes()
                nodes_to_start = [n for n in runnable_nodes if n not in self.running_tasks.values()]

                for node_id in nodes_to_start:
                    if len(self.running_tasks) >= max_concurrency:
                        break

                    self.node_state[node_id] = NodeState.RUNNING
                    node_instance = self.node_list[node_id]

                    inputs = self._gather_inputs(node_id)
                    force_push_msgs = self.pending_force_push.pop(node_id, [])

                    task = asyncio.create_task(
                        node_instance.execute(inputs, force_push_msgs, context=self)
                    )
                    self.running_tasks[task] = node_id

                if not self.running_tasks:
                    if all(s == NodeState.COMPLETED for s in self.node_state.values()):
                        self.state = TaskState.COMPLETED
                        self.save_checkpoints()
                        return {"status": "success", "outputs": self.outputs}
                    else:
                        self.state = TaskState.INTERRUPTED
                        self.save_checkpoints()
                        return {"status": "interrupted", "message": "任务挂起或依赖图断裂"}

                done, pending = await asyncio.wait(
                    self.running_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED
                )

                if self._killed:
                    self._cancel_all_tasks(self.running_tasks)
                    self.state = TaskState.KILLED
                    break

                for task in done:
                    if task not in self.running_tasks:
                        continue
                    node_id = self.running_tasks.pop(task)
                    try:
                        result = task.result()
                        self.node_state[node_id] = NodeState.COMPLETED
                        self.node_list[node_id].outputs = result
                    except asyncio.CancelledError:
                        # 🌟 啥也不做！保持它自尽前设定的 WAITING 状态，或者原本的状态。
                        # 只有这样，Task.run 才会因为没有可运行节点而优雅地结束并变成 INTERRUPTED。
                        pass
                    except Exception as e:
                        self.node_state[node_id] = NodeState.ERROR
                        self.state = TaskState.ERROR
                        self.save_checkpoints()
                        print(f"❌ 节点 {node_id} 执行崩溃: {traceback.format_exc()}")
                        return {"status": "error", "message": f"节点 {node_id} 发生异常: {str(e)}"}

                self.save_checkpoints()

        except Exception as e:
            self.state = TaskState.ERROR
            self.save_checkpoints()
            return {"status": "error", "message": f"引擎致命错误: {str(e)}"}

    def _get_runnable_nodes(self) -> List[str]:
        runnable = []
        edges = self.graph.get("edges", [])

        for node_id, state in self.node_state.items():
            if state == NodeState.READY:  # 🌟 必须只认 READY！
                can_run = True
                for edge in edges:
                    if edge["target"] == node_id:
                        if self.node_state.get(edge["source"]) != NodeState.COMPLETED:
                            can_run = False
                            break
                if can_run:
                    runnable.append(node_id)
        return runnable

    def _gather_inputs(self, node_id: str) -> Dict[str, Any]:
        inputs = {}
        for edge in self.graph.get("edges", []):
            if edge["target"] == node_id:
                source_node = self.node_list[edge["source"]]
                src_port = edge.get("sourceHandle", "default")
                tgt_port = edge.get("targetHandle", "default")

                if hasattr(source_node, "outputs") and source_node.outputs:
                    inputs[tgt_port] = source_node.outputs.get(src_port)
        return inputs

    def _cancel_all_tasks(self, running_tasks: dict):
        for task in running_tasks.keys():
            if not task.done():
                task.cancel()

    def kill(self):
        if self.state in [TaskState.COMPLETED, TaskState.ERROR, TaskState.KILLED]:
            return
        self._killed = True

    def save_checkpoints(self):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        state = {
            "task_id": self.task_id,
            "name": self.task_name,
            "graph_name": self.graph_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "state": self.state.value if hasattr(self.state, "value") else self.state,
            "dag_state": {
                n_id: {"state": self.node_state[n_id].value}
                for n_id in self.node_list
            },
            "pending_force_push": self.pending_force_push,
            "graph": self.graph,
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        task = cls.__new__(cls)
        task.task_id = state.get("task_id")
        task.task_name = state.get("name")
        task.graph_name = state.get("graph_name")
        task.inputs = state.get("inputs", {})
        task.outputs = state.get("outputs", {})
        task.state = TaskState(state.get("state", "ready"))

        if task.state == TaskState.RUNNING:
            task.state = TaskState.INTERRUPTED

        task.graph = state.get("graph", {})
        task.pending_force_push = state.get("pending_force_push", {})
        task.checkpoint_dir = checkpoint_dir
        task.node_list = {}
        task.node_state = {}
        task.running_tasks = {}
        task.init_error = None

        task._lock = threading.Lock()
        task._io_lock = threading.Lock()
        task._killed = False
        task._loop = None
        task.create_time = state.get("create_time")
        task.core = state.get("core", "")
        task.token_usage = state.get("token_usage", 0)
        task.result = False
        task.main_history = []
        task.dag_state = state.get("dag_state", {})

        for node_data in task.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("data", {})
            try:
                module = importlib.import_module(f"src.harness.node.extensions.{node_type}.node")
                task.node_list[node_id] = module.Node(node_id=node_id, config=config)
            except Exception as e:
                print(f"❌ 恢复节点模块失败 {node_type}: {e}")
                task.state = TaskState.ERROR
                return None

            saved_state = task.dag_state.get(node_id, {}).get("state", "ready")
            task.node_state[node_id] = NodeState(saved_state)

            node_backup = task.node_list[node_id].load_checkpoints(task)
            if node_backup and "outputs" in node_backup:
                task.node_list[node_id].outputs = node_backup["outputs"]

        if task.state in [TaskState.READY, TaskState.INTERRUPTED]:
            saved_key_prefix = state.get("key_prefix")
            task.model = Model(task.core, recovered_key_prefix=saved_key_prefix) if task.core else None
            if task.model:
                task.model.bind_task(task.task_id, task.task_name)
        else:
            task.model = None
        task.key_prefix = task.model.key_prefix if task.model else None

        existing_task = TASK_INSTANCES.get(task.task_id)
        if existing_task and existing_task.state == TaskState.RUNNING:
            return existing_task

        TASK_INSTANCES[task.task_id] = task
        return task