"""任务检查点的读写与状态恢复。

只处理纯数据，不依赖 Task 实例。
"""

from __future__ import annotations

import json
import os

from .enums import NodeState, PortState, TaskState


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data, *, indent: int | None = 2) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def restore_node_states(saved_states: dict) -> dict:
    """把落盘的节点状态还原为枚举；中断时的 RUNNING 一律回落到 READY。"""
    restored = {}
    for key, value in saved_states.items():
        state_str = value.get("state", "ready") if isinstance(value, dict) else value
        if state_str == NodeState.RUNNING.value:
            state_str = NodeState.READY.value
        restored[key] = NodeState(state_str)
    return restored


def restore_port_states(raw: dict) -> dict:
    return {
        key: {port: PortState(s) for port, s in ports.items()}
        for key, ports in raw.items()
    }


def restore_task_state(raw_state) -> TaskState:
    state = TaskState(raw_state)
    return TaskState.INTERRUPTED if state == TaskState.RUNNING else state


def serialize_node_state(node_state: dict) -> dict:
    return {
        key: value.value if hasattr(value, "value") else value
        for key, value in node_state.items()
    }


def serialize_port_states(port_states: dict) -> dict:
    return {
        key: {
            port: state.value if hasattr(state, "value") else state
            for port, state in ports.items()
        }
        for key, ports in port_states.items()
    }


def serialize_dag_state(node_list: dict, node_state: dict) -> dict:
    """仅保留当前图内节点的状态（原 dag_state 字段）。"""
    return {
        node_id: {
            "state": node_state[node_id].value
            if hasattr(node_state[node_id], "value")
            else node_state[node_id]
        }
        for node_id in node_list
    }


def serialize_memory(node_memory: dict) -> dict:
    """落盘时只保留极轻量的 force_push 指令。"""
    return {
        node_id: {"force_push": memory.get("force_push", [])}
        for node_id, memory in node_memory.items()
    }


def read_task_descriptor(checkpoint_dir: str) -> dict | None:
    """读取任务复活所需的静态描述（meta.json 优先，兼容旧 checkpoint.json）。"""
    meta_path = os.path.join(checkpoint_dir, "meta.json")
    old_checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
    if os.path.exists(meta_path):
        return read_json(meta_path)
    if os.path.exists(old_checkpoint_path):
        return read_json(old_checkpoint_path)
    return None
