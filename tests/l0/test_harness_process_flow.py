"""DAG 调度、级联重置与检查点写盘的行为锁定（SPEC-016 AC-1 ~ AC-6）。

这里用 ``Task.__new__`` 构造未初始化的实例，只注入状态机所需字段，
避免触碰模型配置与真实 ``~/.purrcat`` 数据目录。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading

import pytest

from src.harness.enums import NodeState, PortState, TaskState
from src.harness.process import Task


def _make_task(tmp_path, graph: dict | None = None) -> Task:
    task = Task.__new__(Task)
    task.task_id = "t1"
    task.node_state = {}
    task.output_port_states = {}
    task.node_memory = {}
    task.node_types = {}
    task.node_list = {}
    task.graph = graph or {"edges": []}
    task.running_tasks = {}
    task.state = TaskState.READY
    task.outputs = {}
    task.total_tokens = 7
    task.execution_time = 1.234
    task.checkpoint_dir = str(tmp_path)
    task._lock = threading.Lock()
    task._io_lock = threading.Lock()
    task._killed = False
    task._loop = None
    task.init_error = None
    return task


def _edge(source: str, target: str, handle: str = "out") -> dict:
    return {"source": source, "target": target, "sourceHandle": handle}


def test_source_node_is_runnable(tmp_path):
    """SPEC-016 AC-1：无上游的源头节点直接可跑。"""
    task = _make_task(tmp_path)
    task.node_state = {"a": NodeState.READY}

    assert task._get_runnable_nodes() == ["a"]
    assert task.node_state["a"] == NodeState.READY


def test_pending_upstream_keeps_node_waiting(tmp_path):
    """SPEC-016 AC-1：上游 PENDING 时节点保持 READY，不触发 skip。"""
    task = _make_task(tmp_path, {"edges": [_edge("src", "n")]})
    task.node_state = {"n": NodeState.READY}
    task.output_port_states = {"src": {"out": PortState.PENDING}}

    assert task._get_runnable_nodes() == []
    assert task.node_state["n"] == NodeState.READY


def test_has_data_wakes_node_even_with_void_sibling(tmp_path):
    """SPEC-016 AC-1：任意一条上游有数据即可唤醒（分支汇聚）。"""
    task = _make_task(
        tmp_path,
        {"edges": [_edge("a", "n"), _edge("b", "n")]},
    )
    task.node_state = {"n": NodeState.READY}
    task.output_port_states = {
        "a": {"out": PortState.HAS_DATA},
        "b": {"out": PortState.VOID},
    }

    assert task._get_runnable_nodes() == ["n"]


def test_all_void_cascades_skip_in_same_pass(tmp_path):
    """SPEC-016 AC-1/AC-2：全 VOID 触发 skip，且同轮继续向下游传播。"""
    task = _make_task(
        tmp_path,
        {"edges": [_edge("src", "a"), _edge("a", "b")]},
    )
    task.node_state = {"a": NodeState.READY, "b": NodeState.READY}
    task.output_port_states = {"src": {"out": PortState.VOID}}

    assert task._get_runnable_nodes() == []
    assert task.node_state["a"] == NodeState.SKIPPED
    assert task.node_state["b"] == NodeState.SKIPPED
    assert task.output_port_states["a"]["out"] == PortState.VOID


def test_update_port_states_marks_has_data_and_void(tmp_path):
    """SPEC-016 AC-3：端口状态只按边声明点亮，未声明的输出端口不落状态。"""
    task = _make_task(
        tmp_path,
        {"edges": [_edge("n", "m", "ok"), _edge("n", "m", "empty")]},
    )

    task._update_port_states("n", {"ok": {"type": "text", "data": "x"}, "extra": 1})

    assert task.output_port_states["n"] == {
        "ok": PortState.HAS_DATA,
        "empty": PortState.VOID,
    }


def test_handle_node_success_sets_completed_then_ports(tmp_path):
    """SPEC-016 AC-3：成功处理先置 COMPLETED，再点亮下游端口。"""
    task = _make_task(tmp_path, {"edges": [_edge("n", "m", "out")]})
    task.node_state = {"n": NodeState.RUNNING}

    task._handle_node_success("n", {"out": {"type": "text", "data": "x"}})

    assert task.node_state["n"] == NodeState.COMPLETED
    assert task.output_port_states["n"]["out"] == PortState.HAS_DATA


def test_cascade_reset_injection_keeps_target_memory(tmp_path):
    """SPEC-016 AC-4：指令注入只删目标 outputs.json，下游目录整体清空。"""
    task = _make_task(
        tmp_path,
        {"edges": [_edge("a", "b"), _edge("b", "c")]},
    )
    task.node_state = {
        "a": NodeState.COMPLETED,
        "b": NodeState.COMPLETED,
        "c": NodeState.COMPLETED,
    }
    task.output_port_states = {
        "a": {"out": PortState.HAS_DATA},
        "b": {"out": PortState.HAS_DATA},
        "c": {"out": PortState.HAS_DATA},
    }
    for node_id in ("a", "b", "c"):
        node_dir = tmp_path / "nodes" / node_id
        node_dir.mkdir(parents=True)
        (node_dir / "outputs.json").write_text("{}", encoding="utf-8")
        (node_dir / "live_memory.json").write_text("{}", encoding="utf-8")

    task._cascade_reset("a", is_injection=True)

    assert all(state == NodeState.READY for state in task.node_state.values())
    assert (tmp_path / "nodes" / "a").is_dir()
    assert not (tmp_path / "nodes" / "a" / "outputs.json").exists()
    assert (tmp_path / "nodes" / "a" / "live_memory.json").exists()
    assert not (tmp_path / "nodes" / "b").exists()
    assert not (tmp_path / "nodes" / "c").exists()
    assert task.output_port_states == {"a": {}, "b": {}, "c": {}}


def test_cascade_reset_full_rerun_removes_target_dir(tmp_path):
    """SPEC-016 AC-4：彻底重跑连目标节点目录一起删除。"""
    task = _make_task(tmp_path, {"edges": [_edge("a", "b")]})
    task.node_state = {"a": NodeState.COMPLETED, "b": NodeState.COMPLETED}
    for node_id in ("a", "b"):
        node_dir = tmp_path / "nodes" / node_id
        node_dir.mkdir(parents=True)
        (node_dir / "live_memory.json").write_text("{}", encoding="utf-8")

    task._cascade_reset("a", is_injection=False)

    assert not (tmp_path / "nodes" / "a").exists()
    assert not (tmp_path / "nodes" / "b").exists()


def test_reset_order_is_breadth_first(tmp_path):
    """SPEC-016 AC-4：重置顺序固定为 BFS（目标节点优先）。"""
    from src.harness.reset import plan_reset

    edges = [_edge("a", "b"), _edge("a", "c"), _edge("b", "d")]

    assert plan_reset("a", edges) == [
        ("a", True),
        ("b", False),
        ("c", False),
        ("d", False),
    ]


def test_save_state_snapshot_fields(tmp_path):
    """SPEC-016 AC-5：state.json 字段、枚举序列化与耗时精度保持不变。"""
    task = _make_task(tmp_path)
    task.node_list = {"n": object()}
    task.node_state = {"n": NodeState.COMPLETED}
    task.output_port_states = {"n": {"out": PortState.HAS_DATA}}
    task.node_memory = {"n": {"force_push": ["go"], "messages": ["drop"]}}
    task.state = TaskState.COMPLETED

    task._save_state_unlocked()

    data = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert data["task_id"] == "t1"
    assert data["state"] == "completed"
    assert data["execution_time"] == 1.23
    assert data["total_tokens"] == 7
    assert data["dag_state"] == {"n": {"state": "completed"}}
    assert data["node_state"] == {"n": "completed"}
    assert data["output_port_states"] == {"n": {"out": "has_data"}}
    assert data["node_memory"] == {"n": {"force_push": ["go"]}}


def test_execute_node_wrapper_orders_build_execute_save(tmp_path):
    """SPEC-016 AC-6：输入组装 → 执行 → 输出落盘，顺序不可交换。"""
    task = _make_task(tmp_path)
    events = []

    class FakeNode:
        async def execute(self, inputs, context=None):
            events.append(("execute", inputs, context))
            return {"out": {"type": "text", "data": "x"}}

    def build(node_id):
        events.append(("build", node_id))
        return {"in": 1}

    def save(node_id, result):
        events.append(("save", node_id, result))

    task._build_node_inputs = build
    task._save_node_outputs = save

    result = asyncio.run(task._execute_node_wrapper("n1", FakeNode()))

    assert result == {"out": {"type": "text", "data": "x"}}
    assert [event[0] for event in events] == ["build", "execute", "save"]
    assert events[0][1] == "n1"
    assert events[1][1] == {"in": 1}
    assert events[2][1] == "n1"


def test_execute_node_wrapper_propagates_error_without_save(tmp_path):
    """SPEC-016 AC-6：节点异常原样上抛，且不触发输出落盘。"""
    task = _make_task(tmp_path)
    events = []

    class BoomNode:
        async def execute(self, inputs, context=None):
            raise RuntimeError("boom")

    task._build_node_inputs = lambda node_id: events.append(("build", node_id)) or {}
    task._save_node_outputs = lambda node_id, result: events.append(("save", node_id))

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(task._execute_node_wrapper("n1", BoomNode()))

    assert events == [("build", "n1")]


def test_save_state_is_atomic_under_io_lock(tmp_path):
    """SPEC-016 AC-5：写盘使用 checkpoint 的原子落盘路径，不残留临时文件。"""
    task = _make_task(tmp_path)

    task.save_state()

    files = sorted(name for name in os.listdir(tmp_path) if name.endswith(".json"))
    assert files == ["state.json"]


def test_save_meta_writes_static_descriptor(tmp_path):
    """SPEC-019 AC-4：meta.json 字段与旧实现一致，只保存创建期静态数据。"""
    task = _make_task(tmp_path)
    task.task_name = "demo"
    task.graph_name = "g1"
    task.core = "openai:test"
    task.create_time = "2024-01-02 03:04:05"
    task.inputs = {"a": 1}
    task.graph = {"nodes": [{"id": "n"}], "edges": []}

    task.save_meta()

    data = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert data == {
        "task_id": "t1",
        "name": "demo",
        "graph_name": "g1",
        "create_time": "2024-01-02 03:04:05",
        "core": "openai:test",
        "inputs": {"a": 1},
        "graph": {"nodes": [{"id": "n"}], "edges": []},
    }


def test_reload_new_format_restores_state_and_demotes_running(tmp_path):
    """SPEC-019 AC-4：state.json + meta.json 恢复字段，RUNNING 节点回落 READY。"""
    task = _make_task(tmp_path)
    task.graph = {"nodes": [], "edges": []}
    state_data = {
        "state": "running",
        "node_state": {"n": "running"},
        "output_port_states": {"n": {"out": "has_data"}},
        "outputs": {"x": 1},
        "total_tokens": 9,
        "execution_time": 2.5,
    }
    meta_data = {
        "create_time": "2024-01-01 00:00:00",
        "inputs": {"a": 1},
        "graph": {"nodes": [{"id": "n"}], "edges": []},
    }
    (tmp_path / "state.json").write_text(json.dumps(state_data), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps(meta_data), encoding="utf-8")

    task.reload()

    assert task.state == TaskState.INTERRUPTED
    assert task.node_state == {"n": NodeState.READY}
    assert task.output_port_states == {"n": {"out": PortState.HAS_DATA}}
    assert task.outputs == {"x": 1}
    assert task.total_tokens == 9
    assert task.execution_time == 2.5
    assert task.inputs == {"a": 1}
    assert task.graph == {"nodes": [{"id": "n"}], "edges": []}
    assert task.create_time == "2024-01-01 00:00:00"


def test_run_executes_nodes_in_order_and_saves_each_phase(tmp_path):
    """SPEC-019 AC-4：启动写盘 → 成功写盘 → 下游 → 终态写盘，顺序不可交换。"""
    task = _make_task(tmp_path, {"edges": [_edge("a", "b")]})
    events = []

    class FakeNode:
        def __init__(self, node_id):
            self.node_id = node_id

        async def execute(self, inputs, context=None):
            events.append(("run", self.node_id))
            return {"out": {"type": "text", "data": self.node_id}}

    task.node_list = {"a": FakeNode("a"), "b": FakeNode("b")}
    task.node_state = {"a": NodeState.READY, "b": NodeState.READY}
    task.node_types = {"a": "string", "b": "string"}
    task._build_node_inputs = lambda node_id: {}
    task._save_node_outputs = lambda node_id, result: events.append(
        ("save_outputs", node_id)
    )

    def record_save():
        snapshot = {nid: st.value for nid, st in task.node_state.items()}
        events.append(("save_state", snapshot))

    task.save_state = record_save

    result = asyncio.run(task.run())

    assert result == {"status": "success", "outputs": {}}
    assert task.state == TaskState.COMPLETED
    assert [event for event in events if event[0] == "run"] == [
        ("run", "a"),
        ("run", "b"),
    ]
    assert [event for event in events if event[0] == "save_state"] == [
        ("save_state", {"a": "running", "b": "ready"}),
        ("save_state", {"a": "completed", "b": "ready"}),
        ("save_state", {"a": "completed", "b": "running"}),
        ("save_state", {"a": "completed", "b": "completed"}),
        ("save_state", {"a": "completed", "b": "completed"}),
    ]


def test_run_suspends_on_waiting_human_node(tmp_path):
    """SPEC-019 AC-5：无任务可跑且存在 WAITING 节点时返回 suspended。"""
    task = _make_task(tmp_path)
    task.node_state = {"h": NodeState.WAITING}
    task.node_types = {"h": "human_intervention"}
    saved = []
    task.save_state = lambda: saved.append("save")

    result = asyncio.run(task.run())

    assert result["status"] == "suspended"
    assert "h" in result["message"]
    assert task.state == TaskState.INTERRUPTED
    assert saved == ["save"]


def test_run_returns_killed_and_saves_synchronously(tmp_path):
    """SPEC-019 AC-5：停机标记在进入调度前生效，状态置 KILLED 并写盘。"""
    task = _make_task(tmp_path)
    task._killed = True
    saved = []
    task.save_state = lambda: saved.append("save")

    result = asyncio.run(task.run())

    assert result["status"] == "killed"
    assert task.state == TaskState.KILLED
    assert task.execution_time >= 1.234
    assert saved == ["save"]


def test_run_returns_init_error_without_scheduling(tmp_path):
    """SPEC-019 AC-5：初始化失败的任务直接返回错误，不调度节点。"""
    task = _make_task(tmp_path)
    task.state = TaskState.ERROR
    task.init_error = "入参缺失"

    result = asyncio.run(task.run())

    assert result == {"status": "error", "message": "入参缺失"}
    assert task.execution_time == 1.234
