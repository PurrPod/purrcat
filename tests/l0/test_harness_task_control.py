"""任务控制指令与状态寄存器（SPEC-019 AC-1、AC-2）。

用未初始化的 ``Task`` 注入最小字段，不启动模型、不读写真实数据目录。
"""

from __future__ import annotations

import threading

import pytest

import src.tool  # noqa: F401  # 先完成工具注册，避免 agent_node 的懒导入触发循环依赖

from src.harness import process as process_module
from src.harness.enums import NodeState, TaskState
from src.harness.node.agent_node import AgentNode
from src.harness.process import Task
from src.harness.task_state import (
    accepts_kill,
    any_waiting,
    queue_force_push,
    suspended_message,
    wake_state,
)


def _agent_node() -> AgentNode:
    return object.__new__(AgentNode)


def _make_task(
    tmp_path,
    nodes: dict | None = None,
    node_types: dict | None = None,
    edges: list | None = None,
) -> Task:
    task = Task.__new__(Task)
    task.task_id = "t1"
    task.node_list = nodes or {}
    task.node_types = node_types or {nid: "agent_loop" for nid in task.node_list}
    task.node_state = {nid: NodeState.READY for nid in task.node_list}
    task.output_port_states = {}
    task.node_memory = {}
    task.graph = {"edges": edges or []}
    task.running_tasks = {}
    task.state = TaskState.READY
    task.outputs = {}
    task.total_tokens = 0
    task.execution_time = 0.0
    task.checkpoint_dir = str(tmp_path)
    task._lock = threading.Lock()
    task._io_lock = threading.Lock()
    task._killed = False
    task._loop = None
    task.init_error = None
    return task


class _FakeRuntimeTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


def test_inject_writes_force_push_and_skip_upstream(tmp_path):
    """SPEC-019 AC-1：注入指令进入 force_push，并标记续跑不重复吸收上游。"""
    task = _make_task(tmp_path, {"n": _agent_node()})

    result = task.inject_instruction("n", "继续执行")

    assert result["status"] == "success"
    assert task.node_memory["n"] == {
        "force_push": ["继续执行"],
        "skip_upstream": True,
    }
    assert task.state == TaskState.READY
    assert (tmp_path / "state.json").exists()


def test_inject_keeps_running_state_to_avoid_second_engine(tmp_path):
    """SPEC-019 AC-1：运行中的任务注入后保持 RUNNING。"""
    task = _make_task(tmp_path, {"n": _agent_node()})
    task.state = TaskState.RUNNING

    task.inject_instruction("n", "追加指令")

    assert task.state == TaskState.RUNNING


def test_inject_appends_to_existing_queue_and_repairs_bad_value(tmp_path):
    """SPEC-019 AC-1：已有队列追加；非列表队列被重置后仍可入队。"""
    task = _make_task(tmp_path, {"n": _agent_node()})
    task.node_memory["n"] = {"force_push": "坏值"}

    task.inject_instruction("n", "go")

    assert task.node_memory["n"]["force_push"] == ["go"]
    assert task.node_memory["n"]["skip_upstream"] is True


def test_inject_rejects_unknown_node(tmp_path):
    """SPEC-019 AC-1：不在 node_list 的节点直接拒绝。"""
    task = _make_task(tmp_path, {"n": _agent_node()})

    result = task.inject_instruction("missing", "go")

    assert result["status"] == "error"
    assert "不存在" in result["message"]
    assert task.node_memory == {}


def test_inject_rejects_non_agent_node(tmp_path):
    """SPEC-019 AC-1：只有 AgentNode 能接收指令。"""
    task = _make_task(tmp_path, {"n": object()})

    result = task.inject_instruction("n", "go")

    assert result["status"] == "error"
    assert "Agent" in result["message"]
    assert task.node_memory == {}


def test_agent_cannot_inject_human_intervention_node(tmp_path):
    """SPEC-019 AC-1：人工干预节点只接受人类通道注入。"""
    task = _make_task(
        tmp_path,
        {"h": _agent_node()},
        node_types={"h": "human_intervention"},
    )

    denied = task.inject_instruction("h", "go", source="agent")
    allowed = task.inject_instruction("h", "go", source="user")

    assert denied["status"] == "error"
    assert allowed["status"] == "success"
    assert task.node_memory["h"]["force_push"] == ["go"]


def test_kill_cancels_running_tasks_and_sets_flag(tmp_path):
    """SPEC-019 AC-2：非终态 kill 置停机标记并取消运行中协程。"""
    task = _make_task(tmp_path)
    runtime_task = _FakeRuntimeTask()
    task.running_tasks[runtime_task] = "n"

    task.kill()

    assert task._killed is True
    assert runtime_task.cancelled is True


@pytest.mark.parametrize(
    "state", [TaskState.COMPLETED, TaskState.ERROR, TaskState.KILLED]
)
def test_kill_is_ignored_in_terminal_states(tmp_path, state):
    """SPEC-019 AC-2：终态任务不再接受 kill。"""
    task = _make_task(tmp_path)
    task.state = state
    runtime_task = _FakeRuntimeTask()
    task.running_tasks[runtime_task] = "n"

    task.kill()

    assert task._killed is False
    assert runtime_task.cancelled is False


def test_kill_task_marks_state_killed(tmp_path, monkeypatch):
    """SPEC-019 AC-2：模块级 kill_task 在 kill 后落 KILLED。"""
    task = _make_task(tmp_path)
    task.task_id = "t1"
    monkeypatch.setattr(process_module, "TASK_INSTANCES", {"t1": task})

    assert process_module.kill_task("t1") is True
    assert task._killed is True
    assert task.state == TaskState.KILLED
    assert process_module.kill_task("missing") is False


def test_queue_force_push_preserves_existing_memory():
    """SPEC-019 AC-1：纯函数入队不覆盖节点其他寄存器。"""
    memory = {"n": {"force_push": ["a"], "other": 1}}

    queue_force_push(memory, "n", "b")

    assert memory["n"] == {"force_push": ["a", "b"], "other": 1, "skip_upstream": True}


def test_wake_state_only_keeps_running():
    """SPEC-019 AC-1：唤醒状态映射为 RUNNING 或 READY。"""
    assert wake_state(TaskState.RUNNING) == TaskState.RUNNING
    assert wake_state(TaskState.INTERRUPTED) == TaskState.READY
    assert wake_state(TaskState.READY) == TaskState.READY


def test_accepts_kill_and_waiting_register():
    """SPEC-019 AC-2：终态判定与等待人工节点文案。"""
    assert accepts_kill(TaskState.READY) is True
    assert accepts_kill(TaskState.KILLED) is False

    node_state = {"h": NodeState.WAITING, "n": NodeState.READY}
    assert any_waiting(node_state) is True
    assert "h" in suspended_message(node_state, {"h": "human_intervention"})
    assert suspended_message({"n": NodeState.READY}, {}) == "任务已挂起，等待人工干预"
