"""检查点序列化、恢复与描述读取（SPEC-008）。"""

from __future__ import annotations

import json

from src.harness.checkpoint import (
    read_json,
    read_task_descriptor,
    restore_node_states,
    restore_port_states,
    restore_task_state,
    serialize_dag_state,
    serialize_memory,
    serialize_node_state,
    serialize_port_states,
    write_json,
)
from src.harness.enums import NodeState, PortState, TaskState


def test_write_read_json_roundtrip(tmp_path):
    path = tmp_path / "nested" / "state.json"

    write_json(str(path), {"a": 1})

    assert read_json(str(path)) == {"a": 1}


def test_restore_node_states_demotes_running_to_ready():
    restored = restore_node_states(
        {
            "a": {"state": "running"},
            "b": "completed",
            "c": {"state": "waiting"},
        }
    )

    assert restored == {
        "a": NodeState.READY,
        "b": NodeState.COMPLETED,
        "c": NodeState.WAITING,
    }


def test_restore_task_state_demotes_running_to_interrupted():
    assert restore_task_state("running") == TaskState.INTERRUPTED
    assert restore_task_state("completed") == TaskState.COMPLETED


def test_restore_port_states_builds_nested_enums():
    restored = restore_port_states({"n1": {"out": "has_data"}})

    assert restored == {"n1": {"out": PortState.HAS_DATA}}


def test_serializers_emit_plain_values():
    node_state = {"n1": NodeState.COMPLETED, "n2": "ready"}
    port_states = {"n1": {"out": PortState.VOID}}
    memory = {"n1": {"force_push": ["x"], "messages": ["drop"]}}

    assert serialize_node_state(node_state) == {"n1": "completed", "n2": "ready"}
    assert serialize_port_states(port_states) == {"n1": {"out": "void"}}
    assert serialize_memory(memory) == {"n1": {"force_push": ["x"]}}
    assert serialize_dag_state({"n1": None}, node_state) == {
        "n1": {"state": "completed"}
    }


def test_read_task_descriptor_prefers_meta_and_falls_back(tmp_path):
    assert read_task_descriptor(str(tmp_path)) is None

    (tmp_path / "checkpoint.json").write_text('{"name": "old"}', encoding="utf-8")
    assert read_task_descriptor(str(tmp_path)) == {"name": "old"}

    (tmp_path / "meta.json").write_text('{"name": "new"}', encoding="utf-8")
    assert read_task_descriptor(str(tmp_path)) == {"name": "new"}


def test_descriptor_is_plain_json(tmp_path):
    (tmp_path / "meta.json").write_text(
        json.dumps({"task_id": "t1", "graph": {"nodes": []}}), encoding="utf-8"
    )

    assert read_task_descriptor(str(tmp_path))["task_id"] == "t1"
