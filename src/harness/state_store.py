"""检查点 `state.json` 快照的组装与落盘。

字段与写盘时机由 `Task.save_state` 控制，这里只负责纯数据拼装，
避免主循环里夹带序列化细节。
"""

from __future__ import annotations

import os

from . import checkpoint as checkpoint_io


def build_state_snapshot(
    *,
    task_id: str,
    state,
    outputs: dict,
    total_tokens: int,
    execution_time: float,
    node_list: dict,
    node_state: dict,
    output_port_states: dict,
    node_memory: dict,
) -> dict:
    """拼装落盘快照；只保留极轻量状态与 force_push 指令。"""
    return {
        "task_id": task_id,
        "state": state.value if hasattr(state, "value") else state,
        "outputs": outputs,
        "total_tokens": total_tokens,
        "execution_time": round(execution_time, 2),
        "dag_state": checkpoint_io.serialize_dag_state(node_list, node_state),
        "node_state": checkpoint_io.serialize_node_state(node_state),
        "output_port_states": checkpoint_io.serialize_port_states(output_port_states),
        "node_memory": checkpoint_io.serialize_memory(node_memory),
    }


def persist_state(checkpoint_dir: str, snapshot: dict) -> None:
    checkpoint_io.write_json(os.path.join(checkpoint_dir, "state.json"), snapshot)
