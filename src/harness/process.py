import asyncio
import datetime
import json
import os
import threading
import time
import uuid
from typing import Any, List

from src.model.facade import Model
from src.utils._fs import read_jsonl
from src.utils.config import DATA_DIR

from . import checkpoint as checkpoint_io
from . import (
    dag_state,
    graph_spec,
    node_io,
    node_runner,
    reset,
    task_persistence,
    task_scheduler,
    task_state,
)
from .enums import NodeState, TaskState

TASK_INSTANCES = {}


def auto_load_all_tasks():
    checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.exists(checkpoints_dir):
        return

    for task_dir in os.listdir(checkpoints_dir):
        full_path = os.path.join(checkpoints_dir, task_dir)
        # 🌟 修复：新架构下，只要有 meta.json 就认为是一个有效的任务存档
        meta_file = os.path.join(full_path, "meta.json")
        old_checkpoint = os.path.join(full_path, "checkpoint.json")

        if os.path.isdir(full_path) and (
            os.path.exists(meta_file) or os.path.exists(old_checkpoint)
        ):
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
        self.output_port_states = {}  # 端口状态 {source_node: {source_port: PortState}}
        self.node_memory = {}  # 控制指令寄存器 {node_id: {"force_push": []}}
        self.node_types = {}  # 节点类型映射 {node_id: node_type}（信封校验用）

        # 🌟 已彻底移除在内存中存储大体积的 edge_mailboxes

        self.node_list = {}
        self.graph = {}
        self.running_tasks = {}

        self.state = TaskState.READY
        self.create_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.checkpoint_dir = os.path.join(
            DATA_DIR, "checkpoints", "task", f"{self.task_name}_{self.task_id}"
        )

        # 🌟 新增：统计性能监控指标
        self.total_tokens = 0
        self.execution_time = 0.0
        self._start_time = None

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

        # 🌟 只在创建时保存一次元数据，后续不再修改
        self.save_meta()

    # 看板(dashboard)文件直接引用图目录里那份 html（purrcat://graph/{graph_name}/...），
    # 不做按任务副本，同一张图并发多个任务共享同一份看板文件。

    def load_graph(self):
        from src.utils.config import GRAPHS_DIR

        graph = graph_spec.load_graph_file(GRAPHS_DIR, self.graph_name)
        if graph is None:
            return {
                "status": "error",
                "message": f"找不到图表定义文件: {self.graph_name}",
            }
        self.graph = graph

        error_msg = graph_spec.validate_global_inputs(
            self.inputs, self.graph.get("global_schema", {})
        )
        if error_msg:
            self.state = TaskState.ERROR
            self.init_error = error_msg
            return {"status": "error", "message": error_msg}

        err = self._build_node_instances()
        if err:
            self.state = TaskState.ERROR
            self.init_error = err
            return {"status": "error", "message": err}

        return {"status": "success", "message": "图表解析与参数校验通过"}

    def _build_node_instances(self) -> str:
        """按 self.graph 重建节点实例/类型/状态（覆盖 node_list）。返回错误信息，无则空串。

        从 checkpoint 恢复的任务可能因输入参数校验失败在 build 之前提前 return，
        导致 node_list 为空；reset/注入等操作据此兜底重建，避免误报"节点不存在"。
        """
        self.node_list = {}
        self.node_types = {}
        (
            self.node_list,
            self.node_types,
            built_states,
            err,
        ) = graph_spec.build_node_instances(self.graph)
        self.node_state.update(built_states)
        return err

    def _ensure_node_list(self) -> str:
        """reset/注入前置兜底：node_list 为空时按自带 graph 重建。返回错误信息，无则空串。"""
        if self.node_list:
            return ""
        return self._build_node_instances()

    async def run(self, max_concurrency: int = 5):
        if self.state == TaskState.ERROR and self.init_error:
            return {"status": "error", "message": self.init_error}

        self._loop = asyncio.get_running_loop()
        self.state = TaskState.RUNNING
        self.running_tasks.clear()

        # 🌟 记录运行启动时间
        start_time = time.time()

        try:
            while True:
                if self._killed:
                    self._cancel_all_tasks()
                    self.state = TaskState.KILLED
                    self.execution_time += time.time() - start_time  # 🌟 累加用时
                    self.save_state()  # 🌟 状态极小，直接同步写

                    # 🌟 修复：明确返回中止的 result，替代隐式的 break 导致返回 None
                    return {
                        "status": "killed",
                        "message": "⛔ 进程已被人工/系统强行中止",
                    }

                runnable_nodes = self._get_runnable_nodes()

                if not runnable_nodes and not self.running_tasks:
                    if task_state.any_waiting(self.node_state):
                        self.state = TaskState.INTERRUPTED
                        self.execution_time += time.time() - start_time  # 🌟 累加用时
                        self.save_state()  # 🌟 状态极小，直接同步写
                        return {
                            "status": "suspended",
                            "message": task_state.suspended_message(
                                self.node_state, self.node_types
                            ),
                        }
                    self.state = TaskState.COMPLETED
                    self.execution_time += time.time() - start_time  # 🌟 累加用时
                    self.save_state()  # 🌟 状态极小，直接同步写
                    return {"status": "success", "outputs": self.outputs}

                error = await task_scheduler.run_round(
                    self,
                    runnable_nodes,
                    max_concurrency=max_concurrency,
                    save_state=self.save_state,
                )
                if error:
                    self.execution_time += time.time() - start_time  # 🌟 累加用时
                    await asyncio.to_thread(self.save_state)
                    return error

        except Exception as e:
            self.state = TaskState.ERROR
            self.execution_time += time.time() - start_time  # 🌟 累加用时
            await asyncio.to_thread(self.save_state)
            return {"status": "error", "message": f"引擎异常: {str(e)}"}

    async def _execute_node_wrapper(self, node_id: str, node_instance: Any):
        """核心包装器：隔离重型 I/O，让主循环轻装上阵"""
        return await node_runner.execute_node(
            node_id,
            node_instance,
            context=self,
            build_inputs=self._build_node_inputs,
            save_outputs=self._save_node_outputs,
        )

    def _handle_node_success(self, node_id: str, result: dict):
        """节点成功：置 COMPLETED 并点亮下游端口（顺序固定）。"""
        dag_state.mark_success(
            self.node_state,
            self.output_port_states,
            node_id,
            result,
            self.graph.get("edges", []),
        )

    def _get_port_declared_type(self, node_id: str, direction: str, port_name: str):
        """读节点 schema 中端口的类型声明（支持 union 列表）；动态端口返回 None（视为 any）"""
        node_type = self.node_types.get(node_id)
        if not node_type:
            return None
        from src.harness.node import get_node_schema

        schema = get_node_schema(node_type)
        if not schema:
            return None
        for port_def in schema.get(direction, []):
            if port_def.get("name") == port_name:
                if port_def.get("port_type") == "dynamic":
                    return None
                return port_def.get("type", "any")
        return None  # 端口不在 schema 里（动态变量名）→ any

    def _build_node_inputs(self, node_id: str) -> dict:
        """纯文件指针推导，从上游物理文件组装 input（信封化 + 类型硬校验）"""
        return node_io.build_node_inputs(
            checkpoint_dir=self.checkpoint_dir,
            graph=self.graph,
            output_port_states=self.output_port_states,
            node_id=node_id,
            declared_type=self._get_port_declared_type,
            log=self.log,
        )

    # 大内容剥离阈值：声明为 file 的端口，data 超过此长度自动落盘
    FILE_STRIP_THRESHOLD = node_io.FILE_STRIP_THRESHOLD

    def _save_node_outputs(self, node_id: str, result: dict):
        """节点输出按端口 schema 包装为信封落盘；file 端口大内容自动剥离为文件"""
        node_io.save_node_outputs(
            checkpoint_dir=self.checkpoint_dir,
            node_id=node_id,
            result=result,
            declared_type=lambda port: self._get_port_declared_type(
                node_id, "outputs", port
            ),
            log=self.log,
            strip_threshold=self.FILE_STRIP_THRESHOLD,
        )

    def _get_runnable_nodes(self) -> List[str]:
        return task_scheduler.get_runnable_nodes(self)

    def _update_port_states(self, source_node_id: str, outputs: dict):
        """只更新状态红绿灯，坚决不碰载荷数据"""
        dag_state.update_port_states(
            self.output_port_states,
            source_node_id,
            outputs,
            self.graph.get("edges", []),
        )

    def _cascade_skip(self, node_id: str):
        dag_state.cascade_skip(
            self.node_state,
            self.output_port_states,
            node_id,
            self.graph.get("edges", []),
        )

    def inject_instruction(
        self, node_id: str, instruction: str, source: str = "user"
    ) -> dict:
        """
        🌟 官方推荐的指令注入入口：自带类型校验和正确的级联重置（新架构）
        通过 node_memory 传递指令。
        source: "user"（前端/REST 人类通道）或 "agent"（主 Agent 工具通道）。
        人工干预节点只接受人类指令，Agent 无权注入。
        """
        err = self._ensure_node_list()
        if err:
            return {"status": "error", "message": err}
        if node_id not in self.node_list:
            return {"status": "error", "message": "节点不存在"}

        # 1. 严格的类型校验！拦截非 Agent 节点
        from src.harness.node.agent_node import AgentNode

        if not isinstance(self.node_list[node_id], AgentNode):
            return {
                "status": "error",
                "message": "拒绝操作：只有 Agent 类型的节点才能注入指令和记忆！",
            }

        # 2. 权限拦截：人工干预节点是人类专属通道，Agent 无权强制注入
        if source == "agent" and self.node_types.get(node_id) == "human_intervention":
            return {
                "status": "error",
                "message": (
                    "拒绝操作：[人工干预] 节点只接受人类亲自输入的指令，"
                    "Agent 没有对人工干预节点注入指令的权力。"
                    "请把问题转达给用户，由用户在任务面板输入指令后工作流才会继续。"
                ),
            }

        # 3. 🌟 新架构：将指令放入 node_memory 的 force_push 队列
        #    注入＝「续跑」而非「重跑」：本节点记忆里已含上游上下文，
        #    重跑时不能再吸收一次上游 messages，否则上游整段会重复落盘
        task_state.queue_force_push(self.node_memory, node_id, instruction)

        # 4. 触发正确的级联重置 (is_injection=True，保护当前节点的记忆)
        self._cascade_reset(node_id, is_injection=True)

        # 5. 唤醒整个任务流：运行中保持 RUNNING，避免 API 误判后重复拉起引擎
        self.state = task_state.wake_state(self.state)

        # 🌟 状态极小，直接同步写
        self.save_state()

        return {"status": "success", "message": "指令已注入，下游链路状态已重置！"}

    def reset_node(self, node_id: str) -> dict:
        """用户点击'重新运行'的入口：目标节点连带下游一起彻底清空记忆"""
        err = self._ensure_node_list()
        if err:
            return {"status": "error", "message": err}
        if node_id not in self.node_list:
            return {"status": "error", "message": "节点不存在"}

        # 🌟 修复：记录重置前的任务状态
        was_running = self.state == TaskState.RUNNING

        # 触发彻底的级联重置 (is_injection=False，连目标节点的记忆一起扬了)
        self._cascade_reset(node_id, is_injection=False)

        # 🌟 修复：如果本来就在后台大循环里跑着，就不要把大任务的状态改成 READY，防止外层重复拉起死循环
        if not was_running:
            self.state = TaskState.READY

        # 🌟 状态极小，直接同步写
        self.save_state()

        return {"status": "success", "message": "节点及其下游已彻底重置！"}

    def _cascade_reset(self, start_node_id: str, is_injection: bool):
        """
        🌟 核心数据流清理逻辑（新架构）：
        is_injection=True 代表是指令注入，目标节点的记忆必须保留！
        is_injection=False 代表彻底重跑，目标节点的记忆也要清空！

        记忆不再由 Task 管理，而是由各 AgentNode 自行管理在 nodes/ 目录下。
        """

        def _cancel(task):
            # 核心修复：使用线程安全的委托调用
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(task.cancel)
            else:
                task.cancel()

        with self._lock:
            reset.cascade_reset(
                start_node_id=start_node_id,
                is_injection=is_injection,
                checkpoint_dir=self.checkpoint_dir,
                node_state=self.node_state,
                output_port_states=self.output_port_states,
                running_tasks=self.running_tasks,
                edges=self.graph.get("edges", []),
                cancel_task=_cancel,
            )

    def save_meta(self):
        """保存任务创建时不变的静态数据。"""
        task_persistence.save_meta(self)

    def save_state(self):
        """高频写状态红绿灯；`_io_lock` 串行化，防止并发写坏 state.json。"""
        task_persistence.save_state(self)

    def _save_state_unlocked(self):
        task_persistence.save_state_unlocked(self)

    def save(self):
        """兼容旧接口，已废弃，使用 save_meta() 和 save_state() 替代"""
        self.save_state()

    def reload(self):
        """兼容新旧版本读档；细节见 task_persistence.reload。"""
        task_persistence.reload(self)

    def migrate_old_memory(self, old_memory: dict):
        """将旧格式的 node_memory 迁移到新的节点自治目录结构"""
        task_persistence.migrate_old_memory(self, old_memory)

    def kill(self):
        if not task_state.accepts_kill(self.state):
            return
        self._killed = True
        # 🌟 修复：立即打断所有正在运行的协程，而不是傻等它们跑完当前步骤
        self._cancel_all_tasks()

    def _cancel_all_tasks(self):
        for task in list(self.running_tasks.keys()):
            if not task.done():
                # 核心修复：使用线程安全的委托调用
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(task.cancel)
                else:
                    task.cancel()

    @staticmethod
    def load_checkpoint(checkpoint_dir: str) -> "Task":
        # 🌟 修复：任务复活需要的基础设定（如名字、节点结构）都在 meta.json 里
        data = checkpoint_io.read_task_descriptor(checkpoint_dir)
        if data is None:
            return None

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
        log_path = os.path.join(self.checkpoint_dir, "log.jsonl")
        if not os.path.exists(log_path):
            return []
        return read_jsonl(log_path)

    def get_injectable_nodes_info(self) -> list:
        """返回支持注入的节点信息 (结构化 List)，供前端渲染或 Agent 工具格式化"""
        nodes_info = []

        # 1. 建立 node_id 到 node_name 的映射 (从画布原始 graph 中提取)
        node_names = {}
        for node_data in self.graph.get("nodes", []):
            node_names[node_data["id"]] = node_data.get("name", node_data["id"])

        # 2. 遍历内存中的实例列表，筛选具备注入能力的节点
        # （人工干预节点只接受人类在前端面板输入指令，对 Agent 的注入视图隐藏）
        for node_id, node_instance in self.node_list.items():
            if getattr(node_instance, "can_inject", False):
                if self.node_types.get(node_id) == "human_intervention":
                    continue
                node_name = node_names.get(node_id, node_id)
                state = self.node_state.get(node_id, NodeState.READY)
                state_str = state.value if hasattr(state, "value") else str(state)

                # 返回标准的 dict 结构
                nodes_info.append(
                    {"id": node_id, "name": node_name, "state": state_str}
                )

        return nodes_info

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
