import asyncio
import atexit
import datetime
import importlib
import json
import os
import shutil
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
        # 如果没有指定 node_id，注入到所有节点
        if node_id:
            return task.submit_request(node_id, content)
        else:
            # 注入到所有节点
            for n_id in task.node_list:
                task.submit_request(n_id, content)
            return True
    return False


class Task:
    """
    商业级智能体任务类 (Task)
    纯粹的调度与状态管理引擎：不耦合任何业务字段 (如 prompt)，数据通过 inputs 进，outputs 出。
    """

    def __init__(
        self, task_name: str, inputs: dict, core: str, graph_name: str = "default"
    ):
        self.task_name = task_name
        self.inputs = inputs  # 🌟 全局入口载荷
        self.outputs = {}  # 🌟 全局出口载荷
        self.core = core
        self.task_id = uuid.uuid4().hex
        self.workplace = f"agent_vm/task_workplace/{self.task_id}"
        self.checkpoint_dir = os.path.join(
            DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}"
        )

        self.model = Model(core)
        self.key_prefix = self.model.key_prefix

        self.graph_name = graph_name
        self.node_list: Dict[str, Any] = {}
        self.node_state: Dict[str, NodeState] = {}
        self.graph: Dict[str, Any] = {}
        self.pending_push_message: Dict[str, List[str]] = {}
        self.running_tasks = {}
        self.state = TaskState.READY

        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self._loop = None
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
        """纯粹地解析 JSON，动态加载节点，并执行顶层参数强校验"""
        import importlib
        import json
        import os

        from .enums import NodeState, TaskState

        graph_path = os.path.join(
            os.path.dirname(__file__), "graph", f"{self.graph_name}.json"
        )
        with open(graph_path, "r", encoding="utf-8") as f:
            self.graph = json.load(f)

        # 🌟 洗牌算法：重置所有的节点 ID 保证绝对唯一，防止图内同名节点数据污染
        id_mapping = {}
        for node_data in self.graph.get("nodes", []):
            original_id = node_data.get("id")
            # 添加短UUID后缀：原ID + 6位UUID
            new_id = f"{original_id}_{uuid.uuid4().hex[:6]}"
            id_mapping[original_id] = new_id
            node_data["id"] = new_id

        # 同步重塑 Edges 连线的源与目标
        for edge in self.graph.get("edges", []):
            edge["source"] = id_mapping.get(edge.get("source"), edge.get("source"))
            edge["target"] = id_mapping.get(edge.get("target"), edge.get("target"))

        # 🌟 核心：兼容字典和列表两种格式的 required_inputs
        required_inputs = self.graph.get("required_inputs", {})
        if isinstance(required_inputs, list):
            # 如果是列表格式，转换为字典以便统一处理
            required_inputs = {k: "" for k in required_inputs}
        missing_keys = [
            k
            for k in required_inputs.keys()
            if k not in self.inputs or self.inputs[k] is None
        ]

        if missing_keys:
            error_msg = f"❌ [拒绝启动] 缺失必填参数: {missing_keys}"
            self.log_and_notify(LogType.ERROR, error_msg)
            self.state = TaskState.ERROR
            self.error_message = error_msg
            return

        for node_data in self.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("data", {})
            try:
                module = importlib.import_module(f"src.harness.node.{node_type}.node")
                self.node_list[node_id] = module.Node(node_id=node_id, config=config)
                self.node_state[node_id] = NodeState.READY
            except Exception as e:
                self.log_and_notify(
                    LogType.ERROR, f"❌ [节点加载失败] {node_type}: {e}"
                )
                self.state = TaskState.ERROR
                self.error_message = f"节点加载失败: {e}"

    def submit_request(self, node_id: str, content: str):
        """人类/系统外部向某个节点强行注入信息，并带智能连带重置策略"""
        if node_id not in self.node_list:
            return False

        if self.state in [TaskState.COMPLETED, TaskState.KILLED]:
            self.log_and_notify(LogType.WARNING, f"⚠️ [注入拒绝] 任务已处于终态({self.state})，无法再注入指令。")
            return False

        with self._lock:
            if node_id not in self.pending_push_message:
                self.pending_push_message[node_id] = []

        # 🌟 核心判断矩阵
        if self.state != TaskState.RUNNING:
            # 【情形A】任务不在运行中：可能是被挂起(INTERRUPTED)或出错了(ERROR)
            # 1. 揪出所有处于 ERROR 或 WAITING 的异常节点，连同它们的子树全部 reset
            abnormal_nodes = [nid for nid, state in self.node_state.items() if state in [NodeState.ERROR, NodeState.WAITING]]
            for anid in abnormal_nodes:
                self._cascade_reset(anid, include_self=True)
            
            # 2. 对注入的目标节点自身及其子树进行 reset
            self._cascade_reset(node_id, include_self=True)
            self.pending_push_message[node_id].append(content)

            # 3. 重启引擎
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.run(), self._loop)
            else:
                asyncio.create_task(self.run())
        else:
            # 【情形B】任务正在热运行中 (RUNNING)
            target_state = self.node_state.get(node_id)
            if target_state == NodeState.RUNNING:
                # B1: 目标正巧也在跑（比如正等模型响应），直接塞进信箱，节点执行里的循环会取走它
                self.pending_push_message[node_id].append(content)
            else:
                # B2: 目标不在运行(可能已完成，或尚未调度到)，强行铲掉它和下游，再注入
                self._cascade_reset(node_id, include_self=True)
                self.pending_push_message[node_id].append(content)

        return True

    def _cascade_reset(self, start_node_id: str, include_self: bool = False):
        """
        纯函数式级联截断：支持是否包含自身。直接调用基类的 reset 方法彻查数据。
        """
        queue = deque([start_node_id])
        visited = set([start_node_id])
        edges = self.graph.get("edges", [])

        # 是否包含自身
        if include_self:
            self._reset_single_node(start_node_id)

        while queue:
            curr_id = queue.popleft()
            for edge in edges:
                if edge["source"] == curr_id:
                    target_id = edge["target"]
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append(target_id)
                        self._reset_single_node(target_id)
                        
    def _reset_single_node(self, node_id: str):
        """将单一节点打回原形，抹除运行时数据并取消执行"""
        self.node_state[node_id] = NodeState.READY
        
        # 调用新版 BaseNode 的 reset 释放 output 和 checkpoints
        if node_id in self.node_list:
            self.node_list[node_id].reset(self)

        # 无情强杀协程
        task_to_cancel = None
        for t, n_id in list(self.running_tasks.items()):
            if n_id == node_id:
                task_to_cancel = t
                break

        if task_to_cancel and not task_to_cancel.done():
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(task_to_cancel.cancel)
            else:
                task_to_cancel.cancel()
            self.running_tasks.pop(task_to_cancel)
            self.log_and_notify(LogType.SYSTEM, f"🛑 [级联重置] 斩断并重置节点状态数据: {node_id}")

    async def run(self, max_concurrency: int = 5) -> dict:
        """基于 DAG 的并发执行，🌟 携带标准的结果出口协议"""

        # 🌟 拦截：如果在 load_graph 阶段就因为缺少参数报错了，直接光速返回！
        if self.state == TaskState.ERROR:
            return {
                "status": "error",
                "task_id": self.task_id,
                "message": getattr(self, "error_message", "初始化失败：参数校验未通过"),
            }

        self._loop = asyncio.get_running_loop()
        self.state = TaskState.RUNNING
        self.running_tasks.clear()

        try:
            while True:
                if self._killed:
                    self.log_and_notify(
                        LogType.SYSTEM,
                        f"⏹️ [任务强杀] {self.task_id} 正在取消所有协程...",
                    )
                    self._cancel_all_tasks(self.running_tasks)
                    self.state = TaskState.KILLED
                    break

                while len(self.running_tasks) < max_concurrency:
                    runnable_nodes = self._get_runnable_nodes()
                    nodes_to_start = [
                        n
                        for n in runnable_nodes
                        if n not in self.running_tasks.values()
                    ]
                    if not nodes_to_start:
                        break
                    for node_id in nodes_to_start:
                        self.node_state[node_id] = NodeState.RUNNING
                        inputs = self._gather_inputs(node_id)
                        with self._lock:
                            force_push_msgs = self.pending_push_message.pop(node_id, [])
                        node_instance = self.node_list[node_id]
                        task = asyncio.create_task(
                            node_instance.execute(inputs, force_push_msgs, context=self)
                        )
                        self.running_tasks[task] = node_id

                        self.log_and_notify(
                            LogType.SYSTEM,
                            f"🚀 [节点启动] {node_id} (并发: {len(self.running_tasks)})",
                        )

                if not self.running_tasks:
                    if all(s == NodeState.COMPLETED for s in self.node_state.values()):
                        self.log_and_notify(
                            LogType.SYSTEM, "✅ [任务完成] 所有节点已就绪。"
                        )
                        self.state = TaskState.COMPLETED
                    else:
                        self.log_and_notify(
                            LogType.SYSTEM, "⏸️ [任务挂起] 存在异常或等待人工干预。"
                        )
                        self.state = TaskState.INTERRUPTED
                    self.save_checkpoints()
                    break

                done, pending = await asyncio.wait(
                    self.running_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=1.0,
                )

                if not done:
                    continue

                if self._killed:
                    self.log_and_notify(
                        LogType.SYSTEM,
                        f"⏹️ [任务强杀] {self.task_id} 正在取消所有协程...",
                    )
                    self._cancel_all_tasks(self.running_tasks)
                    self.state = TaskState.KILLED
                    break

                with self._lock:
                    for task in done:
                        if task not in self.running_tasks:
                            continue
                        node_id = self.running_tasks.pop(task)
                        try:
                            result = task.result()
                            if self.node_state[node_id] != NodeState.WAITING:
                                self.node_state[node_id] = NodeState.COMPLETED
                                self.node_list[node_id].outputs = result
                                self.log_and_notify(
                                    LogType.SYSTEM, f"🟢 [节点完成] {node_id}"
                                )
                        except asyncio.CancelledError:
                            self.log_and_notify(
                                LogType.SYSTEM, f"🛑 [节点中断] {node_id}"
                            )
                        except Exception as e:
                            self.node_state[node_id] = NodeState.ERROR
                            self.log_and_notify(
                                LogType.ERROR, f"❌ [节点异常] {node_id} -> {e}"
                            )

                self.save_checkpoints()
        finally:
            if self._killed:
                self._cancel_all_tasks(self.running_tasks)

        # 🌟 标准化返回结果给外部调用方
        if self.state == TaskState.COMPLETED:
            return {
                "status": "success",
                "task_id": self.task_id,
                "outputs": self.outputs,
            }
        elif self.state == TaskState.INTERRUPTED:
            return {
                "status": "interrupted",
                "task_id": self.task_id,
                "message": "任务挂起，等待人工干预",
            }
        else:
            return {
                "status": "error",
                "task_id": self.task_id,
                "message": "DAG 节点执行失败",
            }

    def _cancel_all_tasks(self, running_tasks: dict):
        for task in running_tasks.keys():
            if not task.done():
                task.cancel()
        self.log_and_notify(
            LogType.SYSTEM, f"✅ [协程清理] 已取消 {len(running_tasks)} 个运行中任务"
        )

    def _get_runnable_nodes(self) -> List[str]:
        runnable = []
        edges = self.graph.get("edges", [])

        for node_id, state in self.node_state.items():
            if state in (NodeState.READY, NodeState.WAITING):
                can_run = True
                for edge in edges:
                    if edge["target"] == node_id:
                        if self.node_state[edge["source"]] != NodeState.COMPLETED:
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

    def _cleanup_resources(self):
        try:
            close_session(session_id=self.task_id)
            self.log_and_notify(LogType.SYSTEM, "🧹 [资源回收] Task专属Shell终端已释放")
        except Exception as e:
            self.log_and_notify(LogType.SYSTEM, f"⚠️ 自动回收 Shell 失败: {e}")

    def log_and_notify(self, log_type: str, content: str, node_id: str = None):
        # 🌟 强硬拦截：不允许没有任何 node_id 归属的野日志产生
        if not node_id:
            # 如果你依然想在后台记录引擎启停，可以默默 return 掉，
            # 也可以强制给它赋一个虚拟 ID，这里我们按照你的要求直接拦截。
            return

        log_dir = self.checkpoint_dir
        os.makedirs(log_dir, exist_ok=True)
        log_data = {"content": content, "timestamp": time.time(), "type": log_type, "node_id": node_id}

        with self._io_lock:
            with open(os.path.join(log_dir, "log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
                f.flush()
        with task_set_lock:
            dirty_tasks.add(self.task_id)

    def get_log(self) -> List[Dict[str, Any]]:
        """
        调取自身的 log.jsonl 日志，并作为字典列表返回。
        """
        log_path = os.path.join(self.checkpoint_dir, "log.jsonl")
        logs = []

        if not os.path.exists(log_path):
            return logs

        try:
            with self._io_lock:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                logs.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            self.log_and_notify(
                LogType.ERROR, f"❌ [日志读取失败] 任务 {self.task_id}: {e}"
            )

        return logs

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        try:
            checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            task = cls.__new__(cls)

            task.task_id = state.get("task_id")
            task.task_name = state.get("name", "Unknown")
            task.graph_name = state.get("graph_name", "default")
            task.inputs = state.get("inputs", {})  # 🌟 恢复入参
            task.outputs = state.get("outputs", {})  # 🌟 恢复出参

            task.node_list = {}
            task.node_state = {}
            task.graph = state.get("graph", {})

            for node_data in task.graph.get("nodes", []):
                node_id = node_data["id"]
                node_type = node_data["type"]
                config = node_data.get("data", {})
                try:
                    module = importlib.import_module(
                        f"src.harness.node.{node_type}.node"
                    )
                    task.node_list[node_id] = module.Node(
                        node_id=node_id, config=config
                    )
                    task.node_state[node_id] = NodeState.READY
                except Exception as e:
                    print(f"❌ 恢复节点模块失败 {node_type}: {e}")
                    task.state = TaskState.ERROR

            task.create_time = state.get("create_time")
            task.core = state.get("core", "")
            task.state = state.get("state", TaskState.READY)
            if task.state in [TaskState.RUNNING]:
                task.state = TaskState.INTERRUPTED
            task.token_usage = state.get("token_usage", 0)
            task.dag_state = state.get("dag_state", {})
            task.pending_push_message = state.get("pending_push_message", {})
            task.checkpoint_dir = os.path.join(
                DATA_DIR, "checkpoints", "task", f"{task.task_name}_{task.task_id}"
            )
            task.main_history = []
            task.running_tasks = {}

            for n_id, n_info in task.dag_state.items():
                if n_id in task.node_list:
                    task.node_state[n_id] = NodeState(
                        n_info.get("state", "ready").lower()
                    )
                    task.node_list[n_id].outputs = n_info.get("outputs", {})
                    
                    # 🌟 让节点自行恢复更深层的 Checkpoint 状态
                    task.node_list[n_id].load_checkpoints(task)

            if task.state in [
                TaskState.READY,
                TaskState.RUNNING,
                TaskState.INTERRUPTED,
            ]:
                saved_key_prefix = state.get("key_prefix")
                task.model = (
                    Model(task.core, recovered_key_prefix=saved_key_prefix)
                    if task.core
                    else None
                )
                if task.model:
                    task.model.bind_task(task.task_id, task.task_name)
            else:
                task.model = None

            task._lock = threading.Lock()
            task._io_lock = threading.Lock()
            task._killed = False
            task._loop = None

            existing_task = TASK_INSTANCES.get(task.task_id)
            if existing_task and existing_task.state == TaskState.RUNNING:
                return existing_task

            TASK_INSTANCES[task.task_id] = task
            return task
        except Exception:
            print(
                f"❌ [Task Checkpoint] 加载失败 {checkpoint_dir}: {traceback.format_exc()}"
            )
            return None

    def save_checkpoints(self):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        state = {
            "task_id": self.task_id,
            "name": self.task_name,
            "graph_name": self.graph_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "create_time": self.create_time,
            "core": self.core,
            "key_prefix": self.model.key_prefix if self.model else None,
            "state": self.state.value if hasattr(self.state, "value") else self.state,
            "token_usage": self.token_usage,
            "dag_state": {
                n_id: {
                    "state": (
                        self.node_state[n_id].value
                        if hasattr(self.node_state[n_id], "value")
                        else self.node_state[n_id]
                    ),
                    "outputs": self.node_list[n_id].outputs,
                }
                for n_id in self.node_list
            },
            "checkpoint_dir": self.checkpoint_dir,
            "pending_push_message": self.pending_push_message,
            "graph": self.graph,
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def kill(self):
        # ⚠️ 新增防御：不要“鞭尸”已经处于终态的任务
        if self.state in [TaskState.COMPLETED, TaskState.ERROR, TaskState.KILLED]:
            return

        self._killed = True
        self.state = TaskState.KILLED
        if getattr(self, "model", None):
            self.model.unbind()
        self._cleanup_resources()
        self.save_checkpoints()  # 确保状态能及时落盘

    async def reload(self):
        self.state = TaskState.RUNNING
        self._killed = False
        return await self.run()


def auto_load_all_tasks():
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
    if task_id in TASK_INSTANCES:
        return TASK_INSTANCES[task_id]
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        return None
    for dir_name in os.listdir(checkpoints_dir):
        if dir_name.endswith(f"_{task_id}"):
            target_dir = os.path.join(checkpoints_dir, dir_name)
            try:
                task = Task.load_checkpoint(target_dir)
                if task:
                    return task
            except Exception as e:
                print(f"❌ 精准恢复任务 {task_id} 失败: {e}")
                return None
    return None


def kill_and_cleanup_task(task_id: str):
    # 1. 从内存中移除并终止
    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES.pop(task_id)
        if hasattr(task, "kill"):
            task.kill()

    # 2. 物理删除磁盘文件夹
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.exists(base_dir):
        for entry in os.listdir(base_dir):
            # 匹配文件夹名（通常包含 task_id）
            if task_id in entry:
                target_path = os.path.join(base_dir, entry)
                shutil.rmtree(target_path, ignore_errors=True)
                return True
    return False


def graceful_shutdown_tasks():
    """
    全局安全中断：捕获 Ctrl+C 或程序退出时，安全挂起正在运行的任务。
    绝对不碰已经完成 (COMPLETED)、报错 (ERROR) 或被杀死 (KILLED) 的任务！
    """
    for task_id, task in TASK_INSTANCES.items():
        # 🌟 核心修复：只对处于活跃状态的任务进行挂起操作
        if task.state in [TaskState.RUNNING, TaskState.STARTING, TaskState.READY]:
            task.state = TaskState.INTERRUPTED
            task._killed = True  # 触发引擎内部安全退出逻辑
            task.save_checkpoints()
            print(f"⏸️ [安全挂起] 任务 {task_id} 已在退出前安全中断并落盘。")


# 注册到系统退出生命周期中，无论 Ctrl+C 还是自然退出都会触发
atexit.register(graceful_shutdown_tasks)
