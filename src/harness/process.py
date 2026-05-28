import asyncio
import datetime
import importlib
import json
import os
import threading
import time
import uuid
from collections import deque
from typing import List

from src.model.facade import Model
from src.utils.config import DATA_DIR

from .enums import NodeState, PortState, TaskState

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


def inject_task_instruction(task_id: str, content: str, node_id: str) -> bool:
    """全局指令注入函数：强制要求指定节点，彻底废弃广播模式"""
    if not node_id:
        return False

    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES[task_id]

        # 拦截不存在的节点
        if node_id not in task.node_list:
            return False

        # 精确调用规范化 API 进行单节点注入
        result = task.inject_instruction(node_id, content)
        return result.get("status") == "success"

    return False


class Task:
    def __init__(
        self,
        task_name: str,
        inputs: dict,
        graph_name: str = "default",
        task_id: str = None,
    ):
        self.task_id = task_id or uuid.uuid4().hex
        self.task_name = task_name
        self.inputs = inputs
        self.outputs = {}
        self.graph_name = graph_name

        self.node_state = {}  # 节点状态 {node_id: NodeState}
        self.edge_mailboxes = {}  # 邮箱系统 {target_node: {target_port: payload}}
        self.output_port_states = {}  # 端口状态 {source_node: {source_port: PortState}}
        self.node_memory = {}  # Agent 的私密日记本 {node_id: {"messages": [], "force_push": []}}

        self.node_list = {}
        self.graph = {}
        self.running_tasks = {}

        self.state = TaskState.READY
        self.create_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.checkpoint_dir = os.path.join(
            DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}"
        )

        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self._loop = None
        self.init_error = None

        if self.task_id not in TASK_INSTANCES:
            TASK_INSTANCES[self.task_id] = self

        self.load_graph()
        self.core = self.graph.get("core", "openai:deepseek-v4-flash")
        self.model = Model(self.core)

        self.reload()

    def load_graph(self):
        graph_path = os.path.join(
            os.path.dirname(__file__), "graph", f"{self.graph_name}.json"
        )
        if not os.path.exists(graph_path):
            return {
                "status": "error",
                "message": f"找不到图表定义文件: {self.graph_name}.json",
            }

        with open(graph_path, "r", encoding="utf-8") as f:
            self.graph = json.load(f)

        global_schema = self.graph.get("global_schema", {})

        if not global_schema and "required_inputs" in self.graph:
            old_reqs = self.graph["required_inputs"]
            global_schema = {
                k: {"required": True, "description": v} for k, v in old_reqs.items()
            }

        validation_errors = []

        missing_required = []
        for req_key, schema_info in global_schema.items():
            is_req = schema_info.get("required", True)
            if is_req and (req_key not in self.inputs or self.inputs[req_key] is None):
                desc = schema_info.get("description", "无特定说明")
                param_type = schema_info.get("type", "any")
                missing_required.append(
                    {
                        "name": req_key,
                        "type": param_type,
                        "description": desc,
                        "required": True,
                    }
                )

        if missing_required:
            param_list = "\n    - ".join(
                [
                    f"'{p['name']}' (类型: {p['type']}, 描述: {p['description']})"
                    for p in missing_required
                ]
            )
            validation_errors.append(f"❌ 缺少必填参数:\n    - {param_list}")

        extra_keys = [k for k in self.inputs.keys() if k not in global_schema]
        if extra_keys:
            extra_list = ", ".join([f"'{k}'" for k in extra_keys])
            validation_errors.append(f"⚠️ 传入了未知参数: {extra_list}")

        if validation_errors:
            all_params_info = []
            for key, schema_info in global_schema.items():
                is_req = schema_info.get("required", True)
                param_type = schema_info.get("type", "any")
                desc = schema_info.get("description", "无特定说明")
                req_mark = "✅ 必填" if is_req else "⭕ 可选"
                all_params_info.append(
                    f"    - '{key}' (类型: {param_type}, {req_mark}, 描述: {desc})"
                )

            error_msg = "\n".join(validation_errors)
            error_msg += "\n\n📋 有效的参数列表:\n" + "\n".join(all_params_info)
            error_msg += "\n\n💡 请检查您的输入参数后重试。"

            self.state = TaskState.ERROR
            self.init_error = error_msg
            return {"status": "error", "message": error_msg}

        for node_data in self.graph.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("config", node_data.get("data", {}))

            try:
                module = importlib.import_module(
                    f"src.harness.node.extensions.{node_type}.node"
                )
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
                        return {
                            "status": "suspended",
                            "message": "任务已挂起，等待人工干预",
                        }
                    self.state = TaskState.COMPLETED
                    self.save()
                    return {"status": "success", "outputs": self.outputs}

                nodes_to_start = [
                    n for n in runnable_nodes if n not in self.running_tasks.values()
                ]
                for node_id in nodes_to_start:
                    if len(self.running_tasks) >= max_concurrency:
                        break

                    self.node_state[node_id] = NodeState.RUNNING
                    node_instance = self.node_list[node_id]

                    inputs = self.edge_mailboxes.get(node_id, {})

                    task = asyncio.create_task(
                        node_instance.execute(inputs, context=self)
                    )
                    self.running_tasks[task] = node_id

                if nodes_to_start:
                    self.save()

                done, pending = await asyncio.wait(
                    self.running_tasks.keys(), return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    node_id = self.running_tasks.pop(task, None)
                    if node_id is None:
                        continue
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
                        return {
                            "status": "error",
                            "message": f"节点 {node_id} 异常: {str(e)}",
                        }

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

            # 如果这是一个源头节点（没有任何输入连线），直接可以跑
            if not incoming_edges:
                runnable.append(node_id)
                continue

            all_resolved = True  # 是否所有的上游连线都已经有结果了 (HAS_DATA 或 VOID)
            has_any_data = False  # 是否收到至少一份有效数据

            for edge in incoming_edges:
                src_node = edge["source"]
                src_port = edge.get("sourceHandle", "default")

                # 获取这条线对应的上游端口状态
                port_state = self.output_port_states.get(src_node, {}).get(
                    src_port, PortState.PENDING
                )

                if port_state == PortState.PENDING:
                    # 只要有一个上游还没跑完，当前节点就继续等
                    all_resolved = False
                    break
                elif port_state == PortState.HAS_DATA:
                    has_any_data = True

            # 🌟 核心容错逻辑：
            if all_resolved:
                if has_any_data:
                    # 只要有数据，哪怕另外一根线是 VOID 废弃的，我也能被唤醒！(完美解决分支汇聚)
                    runnable.append(node_id)
                else:
                    # 只有所有的线全传来了 VOID，我才确信自己在这个分支里彻底凉了
                    self._cascade_skip(node_id)

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
                    self.output_port_states[source_node_id][out_port] = (
                        PortState.HAS_DATA
                    )
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

    def inject_instruction(self, node_id: str, instruction: str) -> dict:
        """官方推荐的指令注入入口：自带类型校验和正确的级联重置"""
        if node_id not in self.node_list:
            return {"status": "error", "message": "节点不存在"}

        # 1. 严格的类型校验！拦截非 Agent 节点
        from src.harness.node.agent_node import AgentNode

        if not isinstance(self.node_list[node_id], AgentNode):
            return {
                "status": "error",
                "message": "拒绝操作：只有 Agent 类型的节点才能注入指令和记忆！",
            }

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
                task_to_cancel = [
                    t for t, n in self.running_tasks.items() if n == curr_id
                ]
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
        """全局唯一存档点：同时包含新架构的核心数据与前端渲染所需数据"""
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")

        # 组装兼容前端的 dag_state (前端靠这个渲染节点颜色/Loading动画)
        frontend_dag_state = {}
        for n_id in self.node_list:
            frontend_dag_state[n_id] = {
                "state": (
                    self.node_state[n_id].value
                    if hasattr(self.node_state[n_id], "value")
                    else self.node_state[n_id]
                )
            }

        data = {
            # 1. 基础元数据 (前端必须)
            "task_id": self.task_id,
            "name": getattr(self, "task_name", "unnamed_task"),
            "graph_name": getattr(self, "graph_name", "default"),
            "create_time": getattr(self, "create_time", "2025-01-01 00:00:00"),
            "core": getattr(self, "core", ""),
            "state": self.state.value if hasattr(self.state, "value") else self.state,
            # 2. 画布渲染数据 (前端必须)
            "graph": self.graph,  # 前端依赖这个来画节点和连线！
            "dag_state": frontend_dag_state,  # 前端依赖这个判断节点是 Running 还是 Completed
            # 3. 业务数据
            "inputs": self.inputs,
            "outputs": self.outputs,
            # 4. 🌟 新架构核心数据 (后端引擎的灵魂)
            "edge_mailboxes": self.edge_mailboxes,
            "node_state": {
                k: v.value if hasattr(v, "value") else v
                for k, v in self.node_state.items()
            },
            "output_port_states": {
                k: {p: s.value if hasattr(s, "value") else s for p, s in ports.items()}
                for k, ports in self.output_port_states.items()
            },
            "node_memory": self.node_memory,
        }

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reload(self):
        """兼容新旧版本的读档"""
        checkpoint_path = os.path.join(self.checkpoint_dir, "checkpoint.json")
        if not os.path.exists(checkpoint_path):
            return

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # 恢复基础状态
                self.state = TaskState(data.get("state", "ready"))
                if self.state == TaskState.RUNNING:
                    self.state = TaskState.INTERRUPTED

                self.inputs = data.get("inputs", {})
                self.outputs = data.get("outputs", {})

                # 恢复旧前端强依赖的 graph 和时间等元数据
                self.graph = data.get("graph", self.graph)
                self.create_time = data.get("create_time", "2025-01-01 00:00:00")

                # 恢复新架构的引擎状态
                saved_states = data.get("node_state", data.get("dag_state", {}))
                self.node_state = {}
                for k, v in saved_states.items():
                    # 如果从 dag_state 读取，v 是一个字典，需要取出 'state' 字符串
                    state_str = v.get("state", "ready") if isinstance(v, dict) else v
                    if state_str == NodeState.RUNNING.value:
                        state_str = NodeState.READY.value
                    self.node_state[k] = NodeState(state_str)
                self.edge_mailboxes = data.get("edge_mailboxes", {})

                # 安全恢复嵌套的端口状态
                self.output_port_states = {}
                for k, ports in data.get("output_port_states", {}).items():
                    self.output_port_states[k] = {
                        p: PortState(s) for p, s in ports.items()
                    }

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

    @staticmethod
    def load_checkpoint(checkpoint_dir: str) -> "Task":
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        if not os.path.exists(checkpoint_path):
            return None

        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        task_id = data.get("task_id")
        task_name = data.get("name", data.get("task_name", "unnamed_task"))
        graph_name = data.get("graph_name", "default")
        inputs = data.get("inputs", {})
        saved_core = data.get("core", "")

        task = Task(
            task_name=task_name,
            inputs=inputs,
            graph_name=graph_name,
            task_id=task_id,
        )
        task.checkpoint_dir = checkpoint_dir

        task.create_time = data.get(
            "create_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        if saved_core:
            task.core = saved_core
            from src.model.facade import Model

            task.model = Model(task.core)

        return task

    def get_logs(self):
        logs = []
        log_path = os.path.join(self.checkpoint_dir, "log.jsonl")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except Exception:
                            pass
        return logs

    def log(self, log_type: str, content: str, node_id: str):
        """兼容 BaseNode.log 的接口，参数顺序: (log_type, content, node_id)"""
        log_entry = {
            "timestamp": int(time.time() * 1000),
            "node_id": node_id,
            "type": log_type,
            "content": content,
        }

        os.makedirs(self.checkpoint_dir, exist_ok=True)
        log_path = os.path.join(self.checkpoint_dir, "log.jsonl")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
