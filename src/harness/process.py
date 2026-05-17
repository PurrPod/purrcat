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
from src.utils.config import DATA_DIR
from .enums import LogType, NodeState, PortState, TaskState

TASK_INSTANCES = {}


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
    """全局指令注入函数：委托给 Task 实例的规范化 API"""
    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES[task_id]
        if node_id:
            # 使用规范化 API
            result = task.inject_instruction(node_id, content)
            return result["status"] == "success"
        else:
            # 广播模式：只向所有 Agent 节点注入
            from src.harness.node.agent_node import AgentNode
            for n_id, node_instance in task.node_list.items():
                if isinstance(node_instance, AgentNode):
                    task.inject_instruction(n_id, content)
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
        
        self.node_state = {}       # 节点状态 {node_id: NodeState}
        self.edge_mailboxes = {}   # 邮箱系统 {target_node: {target_port: payload}}
        self.output_port_states = {} # 端口状态 {source_node: {source_port: PortState}}
        self.node_memory = {}      # Agent 的私密日记本 {node_id: {"messages": [], "force_push": []}}
        
        self.node_list = {}
        self.graph = {}
        self.running_tasks = {}

        self.state = TaskState.READY
        self.checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}")
        self.model = Model(core)

        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self._loop = None
        self.init_error = None

        if self.task_id not in TASK_INSTANCES:
            TASK_INSTANCES[self.task_id] = self

        self.load_graph()
        self.reload()

    def load_graph(self):
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

    async def run(self, max_concurrency: int = 5):
        if self.state == TaskState.ERROR and self.init_error:
            return {"status": "error", "message": self.init_error}

        self._loop = asyncio.get_running_loop()
        self.state = TaskState.RUNNING
        self.running_tasks.clear()

        try:
            while True:
                if self._killed:
                    self._cancel_all_tasks()
                    self.state = TaskState.KILLED
                    break

                runnable_nodes = self._get_runnable_nodes()
                
                if not runnable_nodes and not self.running_tasks:
                    if any(s == NodeState.WAITING for s in self.node_state.values()):
                        self.state = TaskState.INTERRUPTED
                        self.save()
                        return {"status": "suspended", "message": "任务已挂起，等待人工干预"}
                    self.state = TaskState.COMPLETED
                    self.save()
                    return {"status": "success", "outputs": self.outputs}

                nodes_to_start = [n for n in runnable_nodes if n not in self.running_tasks.values()]
                for node_id in nodes_to_start:
                    if len(self.running_tasks) >= max_concurrency: break

                    self.node_state[node_id] = NodeState.RUNNING
                    node_instance = self.node_list[node_id]

                    inputs = self.edge_mailboxes.get(node_id, {})

                    task = asyncio.create_task(node_instance.execute(inputs, context=self))
                    self.running_tasks[task] = node_id

                done, pending = await asyncio.wait(self.running_tasks.keys(), return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    node_id = self.running_tasks.pop(task)
                    try:
                        result = task.result()
                        self.node_state[node_id] = NodeState.COMPLETED
                        
                        self._deliver_payloads(node_id, result)
                        
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self.node_state[node_id] = NodeState.ERROR
                        self.state = TaskState.ERROR
                        self.save()
                        return {"status": "error", "message": f"节点 {node_id} 异常: {str(e)}"}

                self.save()

        except Exception as e:
            self.state = TaskState.ERROR
            self.save()
            return {"status": "error", "message": f"引擎异常: {str(e)}"}

    def _get_runnable_nodes(self) -> List[str]:
        runnable = []
        edges = self.graph.get("edges", [])

        for node_id, state in self.node_state.items():
            if state != NodeState.READY:
                continue

            incoming_edges = [e for e in edges if e["target"] == node_id]
            
            all_ready = True
            has_void = False

            for edge in incoming_edges:
                src_node = edge["source"]
                src_port = edge.get("sourceHandle", "default")
                
                port_state = self.output_port_states.get(src_node, {}).get(src_port, PortState.PENDING)

                if port_state == PortState.VOID:
                    has_void = True
                    break
                elif port_state != PortState.HAS_DATA:
                    all_ready = False

            if has_void:
                self._cascade_skip(node_id)
            elif all_ready:
                runnable.append(node_id)

        return runnable

    def _deliver_payloads(self, source_node_id: str, outputs: dict):
        edges = self.graph.get("edges", [])
        if source_node_id not in self.output_port_states:
            self.output_port_states[source_node_id] = {}

        for edge in edges:
            if edge["source"] == source_node_id:
                out_port = edge.get("sourceHandle", "default")
                tgt_node = edge["target"]
                tgt_port = edge.get("targetHandle", "default")

                if out_port in outputs:
                    if tgt_node not in self.edge_mailboxes:
                        self.edge_mailboxes[tgt_node] = {}
                    self.edge_mailboxes[tgt_node][tgt_port] = outputs[out_port]
                    self.output_port_states[source_node_id][out_port] = PortState.HAS_DATA
                else:
                    self.output_port_states[source_node_id][out_port] = PortState.VOID

    def _cascade_skip(self, node_id: str):
        self.node_state[node_id] = NodeState.SKIPPED
        edges = self.graph.get("edges", [])
        if node_id not in self.output_port_states:
            self.output_port_states[node_id] = {}

        for edge in edges:
            if edge["source"] == node_id:
                out_port = edge.get("sourceHandle", "default")
                self.output_port_states[node_id][out_port] = PortState.VOID

    # ==========================================
    # 🌟 规范化的外部交互 API
    # ==========================================

    def inject_instruction(self, node_id: str, instruction: str) -> dict:
        """官方推荐的指令注入入口：自带类型校验和正确的级联重置"""
        if node_id not in self.node_list:
            return {"status": "error", "message": "节点不存在"}
        
        # 1. 严格的类型校验！拦截非 Agent 节点
        from src.harness.node.agent_node import AgentNode
        if not isinstance(self.node_list[node_id], AgentNode):
            return {"status": "error", "message": "拒绝操作：只有 Agent 类型的节点才能注入指令和记忆！"}

        # 2. 安全注入指令到该节点的私有记忆
        my_memory = self.node_memory.setdefault(node_id, {})
        my_memory.setdefault("force_push", []).append(instruction)

        # 3. 触发正确的级联重置 (is_injection=True，保护当前节点的记忆)
        self._cascade_reset(node_id, is_injection=True)
        
        # 4. 唤醒整个任务流
        self.state = TaskState.READY
        self.save()
        return {"status": "success", "message": "指令已注入，下游链路状态已重置！"}

    def reset_node(self, node_id: str) -> dict:
        """用户点击'重新运行'的入口：目标节点连带下游一起彻底清空记忆"""
        if node_id not in self.node_list:
            return {"status": "error", "message": "节点不存在"}
        
        # 触发彻底的级联重置 (is_injection=False，连目标节点的记忆一起扬了)
        self._cascade_reset(node_id, is_injection=False)
        
        self.state = TaskState.READY
        self.save()
        return {"status": "success", "message": "节点及其下游已彻底重置！"}

    # ==========================================
    # 🌟 史诗级带保护的级联清理算法
    # ==========================================

    def _cascade_reset(self, start_node_id: str, is_injection: bool):
        """
        核心数据流清理逻辑：
        is_injection=True 代表是指令注入，目标节点的记忆必须保留！
        is_injection=False 代表彻底重跑，目标节点的记忆也要清空！
        """
        with self._lock:
            # 队列中存储 (node_id, 是否是本次操作的起始目标节点)
            queue = deque([(start_node_id, True)])
            visited = set([start_node_id])
            edges = self.graph.get("edges", [])

            while queue:
                curr_id, is_target = queue.popleft()
                
                # 1. 所有波及的节点，状态统统恢复待命
                self.node_state[curr_id] = NodeState.READY
                
                # 2. 清空该节点向外发射的端口状态 (让引擎知道它还没产出新数据)
                if curr_id in self.output_port_states:
                    self.output_port_states[curr_id].clear()

                # 3. 🌟 记忆与邮箱清理逻辑
                # 如果是注入操作且当前是目标节点，我们只清空它的输出，【绝对不能清空它的历史记忆和输入邮箱】
                if is_injection and is_target:
                    pass
                else:
                    # 对于非目标节点（下游），或者选择了彻底重跑，必须清空邮箱并删档！
                    if curr_id in self.edge_mailboxes:
                        self.edge_mailboxes[curr_id].clear()
                    if curr_id in self.node_memory:
                        self.node_memory.pop(curr_id)

                # 4. 打断可能正在苟延残喘的协程
                task_to_cancel = [t for t, n in self.running_tasks.items() if n == curr_id]
                for t in task_to_cancel:
                    t.cancel()
                    self.running_tasks.pop(t, None)

                # 5. 顺藤摸瓜找下游
                for edge in edges:
                    if edge["source"] == curr_id:
                        target_id = edge["target"]
                        if target_id not in visited:
                            visited.add(target_id)
                            # 下游节点全部标记为 False（非目标节点），一律接受无情删档！
                            queue.append((target_id, False))

    def save(self):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        
        data = {
            "task_id": self.task_id,
            "state": self.state.value,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "node_state": {k: v.value for k, v in self.node_state.items()},
            "edge_mailboxes": self.edge_mailboxes,
            "output_port_states": {k: {p: s.value for p, s in ports.items()} for k, ports in self.output_port_states.items()},
            "node_memory": self.node_memory
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reload(self):
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        if not os.path.exists(checkpoint_path):
            return

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.state = TaskState(data.get("state", "ready"))
                if self.state == TaskState.RUNNING:
                    self.state = TaskState.INTERRUPTED
                    
                self.inputs = data.get("inputs", {})
                self.outputs = data.get("outputs", {})
                self.node_state = {k: NodeState(v) for k, v in data.get("node_state", {}).items()}
                self.edge_mailboxes = data.get("edge_mailboxes", {})
                self.output_port_states = {k: {p: PortState(s) for p, s in ports.items()} for k, ports in data.get("output_port_states", {}).items()}
                self.node_memory = data.get("node_memory", {})
        except Exception as e:
            print(f"❌ 读取 Checkpoint 失败: {e}")

    def kill(self):
        if self.state in [TaskState.COMPLETED, TaskState.ERROR, TaskState.KILLED]:
            return
        self._killed = True

    def _cancel_all_tasks(self):
        for task in self.running_tasks.keys():
            if not task.done():
                task.cancel()

    def log_and_notify(self, log_type: str, content: str, node_id: str):
        if not hasattr(self, "checkpoint_dir") or not self.checkpoint_dir:
            return

        os.makedirs(self.checkpoint_dir, exist_ok=True)
        log_path = os.path.join(self.checkpoint_dir, "log.jsonl")

        card_type = log_type.value if hasattr(log_type, "value") else str(log_type).lower()

        entry = {
            "timestamp": time.time(),
            "node_id": node_id,
            "card_type": card_type,
            "content": content
        }

        with self._io_lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @classmethod
    def load_checkpoint(cls, checkpoint_dir: str):
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        if not os.path.exists(checkpoint_path):
            return None
            
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        task = cls.__new__(cls)
        task.task_id = state.get("task_id")
        task.task_name = state.get("name", state.get("task_name", "unknown"))
        task.graph_name = state.get("graph_name")
        task.inputs = state.get("inputs", {})
        task.outputs = state.get("outputs", {})
        task.state = TaskState(state.get("state", "ready"))

        if task.state == TaskState.RUNNING:
            task.state = TaskState.INTERRUPTED

        task.graph = state.get("graph", {})
        task.checkpoint_dir = checkpoint_dir
        task.node_list = {}
        task.node_state = {}
        task.running_tasks = {}
        task.init_error = None

        task._lock = threading.Lock()
        task._io_lock = threading.Lock()
        task._killed = False
        task._loop = None
        
        task.edge_mailboxes = state.get("edge_mailboxes", {})
        task.output_port_states = state.get("output_port_states", {})
        task.node_memory = state.get("node_memory", {})

        if state.get("create_time"):
            task.create_time = state.get("create_time")
        else:
            try:
                mtime = os.path.getmtime(checkpoint_dir)
                task.create_time = datetime.datetime.fromtimestamp(mtime).strftime("%Y%m%d%H%M%S")
            except:
                task.create_time = "20250101000000"
        task.core = state.get("core", "")
        task.token_usage = state.get("token_usage", 0)
        task.result = False
        task.main_history = []
        task.dag_state = state.get("dag_state", {})

        for node_data in task.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("config", node_data.get("data", {}))
            try:
                module = importlib.import_module(f"src.harness.node.extensions.{node_type}.node")
                task.node_list[node_id] = module.Node(node_id=node_id, config=config)
            except Exception as e:
                print(f"❌ 恢复节点模块失败 {node_type}: {e}")
                task.state = TaskState.ERROR
                return None

            saved_state = task.dag_state.get(node_id, {}).get("state", "ready")
            task.node_state[node_id] = NodeState(saved_state)

        task.model = Model(task.core) if task.core else None
        if task.model:
            task.model.bind_task(task.task_id, task.task_name)
        task.key_prefix = task.model.key_prefix if task.model else None

        existing_task = TASK_INSTANCES.get(task.task_id)
        if existing_task and existing_task.state == TaskState.RUNNING:
            return existing_task

        TASK_INSTANCES[task.task_id] = task
        return task
