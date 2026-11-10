"""单轮 DAG 调度：可运行集合、并发上限、完成顺序与失败置 ERROR（SPEC-019 AC-3）。"""

from __future__ import annotations

import asyncio
import threading

from src.harness import dag_state
from src.harness.enums import NodeState, PortState, TaskState
from src.harness.task_scheduler import (
    get_runnable_nodes,
    run_round,
    select_nodes_to_start,
)


class _FakeNode:
    def __init__(self, node_id: str, events: list, gate=None, fail: bool = False):
        self.node_id = node_id
        self.events = events
        self.gate = gate
        self.fail = fail

    async def execute(self, inputs, context=None):
        self.events.append(("start", self.node_id))
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("boom")
        self.events.append(("finish", self.node_id))
        return {"out": {"type": "text", "data": self.node_id}}


class _FakeTask:
    def __init__(self, nodes: dict, edges: list | None = None):
        self.node_list = nodes
        self.node_state = {node_id: NodeState.READY for node_id in nodes}
        self.output_port_states = {}
        self.node_memory = {}
        self.node_types = {node_id: "agent_loop" for node_id in nodes}
        self.graph = {"edges": edges or []}
        self.running_tasks = {}
        self.state = TaskState.RUNNING
        self.outputs = {}
        self.total_tokens = 0
        self.execution_time = 0.0
        self.checkpoint_dir = ""
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._killed = False
        self._loop = None
        self.init_error = None

    async def _execute_node_wrapper(self, node_id, node_instance):
        return await node_instance.execute({}, context=self)

    def _handle_node_success(self, node_id, result):
        dag_state.mark_success(
            self.node_state,
            self.output_port_states,
            node_id,
            result,
            self.graph.get("edges", []),
        )


def _edge(source: str, target: str, handle: str = "out") -> dict:
    return {"source": source, "target": target, "sourceHandle": handle}


def test_get_runnable_nodes_honors_ports_and_states():
    """SPEC-019 AC-3：源头可跑；上游点亮后下游才可跑。"""
    task = _FakeTask({"a": None, "b": None}, edges=[_edge("a", "b")])

    assert get_runnable_nodes(task) == ["a"]

    task.node_state["a"] = NodeState.COMPLETED
    task.output_port_states["a"] = {"out": PortState.HAS_DATA}

    assert get_runnable_nodes(task) == ["b"]


def test_select_nodes_to_start_skips_already_running():
    """SPEC-019 AC-3：已在任务表中的节点不会重复启动。"""
    task = _FakeTask({"a": None, "b": None})
    task.running_tasks[object()] = "a"

    assert select_nodes_to_start(task, ["a", "b"]) == ["b"]


def test_run_round_starts_under_cap_and_handles_first_completion():
    """SPEC-019 AC-3：并发上限内启动；首轮只消费先完成的节点，未完成者留待下轮。"""
    gate = asyncio.Event()
    events: list = []
    nodes = {"a": _FakeNode("a", events, gate=gate), "b": _FakeNode("b", events)}
    task = _FakeTask(nodes)
    saves: list = []

    async def scenario():
        error = await run_round(
            task,
            ["a", "b"],
            max_concurrency=2,
            save_state=lambda: saves.append("save"),
        )
        assert error is None
        assert events == [("start", "a"), ("start", "b"), ("finish", "b")]
        assert list(task.running_tasks.values()) == ["a"]
        assert task.node_state["a"] == NodeState.RUNNING
        assert task.node_state["b"] == NodeState.COMPLETED
        assert saves == ["save", "save"]

        gate.set()
        await run_round(
            task, [], max_concurrency=2, save_state=lambda: saves.append("save")
        )

        assert events[-1] == ("finish", "a")
        assert task.node_state["a"] == NodeState.COMPLETED
        assert task.running_tasks == {}
        assert saves == ["save", "save", "save"]

    asyncio.run(scenario())


def test_run_round_respects_max_concurrency():
    """SPEC-019 AC-3：达到并发上限后不再启动新节点。"""
    events: list = []
    nodes = {"a": _FakeNode("a", events), "b": _FakeNode("b", events)}
    task = _FakeTask(nodes)

    async def scenario():
        await run_round(task, ["a", "b"], max_concurrency=1, save_state=lambda: None)

        assert events == [("start", "a"), ("finish", "a")]
        assert task.node_state["b"] == NodeState.READY
        assert "b" not in task.running_tasks.values()

        await run_round(task, ["b"], max_concurrency=1, save_state=lambda: None)
        assert task.node_state["b"] == NodeState.COMPLETED

    asyncio.run(scenario())


def test_run_round_marks_error_and_returns_payload():
    """SPEC-019 AC-3：节点异常置节点与任务 ERROR，返回错误结构且不写收尾快照。"""
    events: list = []
    task = _FakeTask({"a": _FakeNode("a", events, fail=True)})
    saves: list = []

    async def scenario():
        payload = await run_round(
            task,
            ["a"],
            max_concurrency=2,
            save_state=lambda: saves.append("save"),
        )
        assert payload == {"status": "error", "message": "节点 a 异常: boom"}
        assert task.node_state["a"] == NodeState.ERROR
        assert task.state == TaskState.ERROR
        assert saves == ["save"]

    asyncio.run(scenario())
