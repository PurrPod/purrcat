"""任务控制指令与状态寄存器（SPEC-019 AC-1、AC-2）。

用未初始化的 ``Task`` 注入最小字段，不启动模型、不读写真实数据目录。
"""

from __future__ import annotations

import json
import threading

import pytest

import src.tool  # noqa: F401  # 先完成工具注册，避免 agent_node 的懒导入触发循环依赖

from src.harness import process as process_module
from src.harness.enums import NodeState, TaskState
from src.harness.node.agent_node import AgentNode
from src.harness.process import Task
from src.harness.task_state import (
    accepts_kill,
    any_suspended,
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


def test_kill_marks_running_nodes_killed(tmp_path):
    """SPEC-019 AC-2：kill 后正在运行的节点不能残留 RUNNING。"""
    task = _make_task(tmp_path)
    task.node_state = {
        "a": NodeState.RUNNING,
        "b": NodeState.READY,
        "c": NodeState.COMPLETED,
    }

    task.kill()

    assert task.node_state == {
        "a": NodeState.KILLED,
        "b": NodeState.READY,
        "c": NodeState.COMPLETED,
    }


def test_kill_task_persists_killed_state_and_nodes(tmp_path, monkeypatch):
    """SPEC-019 AC-2：kill 后立刻落盘，节点同步为 killed，重启不会回退 running。"""
    task = _make_task(tmp_path, {"n": object()})
    task.node_state = {"n": NodeState.RUNNING}
    monkeypatch.setattr(process_module, "TASK_INSTANCES", {"t1": task})

    assert process_module.kill_task("t1") is True

    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["state"] == "killed"
    assert saved["node_state"] == {"n": "killed"}
    assert saved["dag_state"] == {"n": {"state": "killed"}}


def test_kill_task_rejects_terminal_tasks(tmp_path, monkeypatch):
    """SPEC-019 AC-2：已完成任务不再被改成 KILLED。"""
    task = _make_task(tmp_path)
    task.state = TaskState.COMPLETED
    monkeypatch.setattr(process_module, "TASK_INSTANCES", {"t1": task})

    assert process_module.kill_task("t1") is False
    assert task.state == TaskState.COMPLETED


def test_inject_after_kill_clears_flag_and_requeues(tmp_path):
    """SPEC-019 AC-1/AC-2：kill 后再次注入应重新可跑，不能带着停机标记。"""
    task = _make_task(tmp_path, {"n": _agent_node()})
    task.state = TaskState.KILLED
    task._killed = True
    task.node_state = {"n": NodeState.KILLED}

    result = task.inject_instruction("n", "再来一次")

    assert result["status"] == "success"
    assert task._killed is False
    assert task.state == TaskState.READY
    assert task.node_state["n"] == NodeState.READY


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


def test_killed_nodes_keep_task_suspended():
    """SPEC-019 AC-6：被中止未执行的节点不能当成已完成。"""
    node_state = {"k": NodeState.KILLED, "done": NodeState.COMPLETED}

    assert any_suspended(node_state) is True
    assert "k" in suspended_message(node_state, {})
    assert any_suspended({"done": NodeState.COMPLETED}) is False
    assert suspended_message({"n": NodeState.READY}, {}) == "任务已挂起，等待人工干预"


def test_accepts_kill_and_waiting_register():
    """SPEC-019 AC-2：终态判定与等待人工节点文案。"""
    assert accepts_kill(TaskState.READY) is True
    assert accepts_kill(TaskState.KILLED) is False

    node_state = {"h": NodeState.WAITING, "n": NodeState.READY}
    assert any_suspended(node_state) is True
    assert "h" in suspended_message(node_state, {"h": "human_intervention"})
    assert suspended_message({"n": NodeState.READY}, {}) == "任务已挂起，等待人工干预"
