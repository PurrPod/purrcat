"""任务检查点的保存、恢复与旧格式迁移。

`Task` 只持有字段，写盘细节与读档兼容分支集中在这里；
节点目录删除由 reset 与任务 API 负责。
"""

from __future__ import annotations

import json
import os

from . import checkpoint as checkpoint_io
from . import state_store


def save_meta(task) -> None:
    """保存任务创建时不变的静态数据（graph、inputs、task_id 等）。"""
    os.makedirs(task.checkpoint_dir, exist_ok=True)
    meta_data = {
        "task_id": task.task_id,
        "name": getattr(task, "task_name", "unnamed_task"),
        "graph_name": getattr(task, "graph_name", "default"),
        "create_time": getattr(task, "create_time", "2025-01-01 00:00:00"),
        "core": getattr(task, "core", ""),
        "inputs": task.inputs,
        "graph": task.graph,
    }
    meta_path = os.path.join(task.checkpoint_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)


def save_state(task) -> None:
    """高频写状态红绿灯；用 `_io_lock` 串行化注入线程与引擎线程。"""
    os.makedirs(task.checkpoint_dir, exist_ok=True)
    with task._io_lock:
        save_state_unlocked(task)


def save_state_unlocked(task) -> None:
    snapshot = state_store.build_state_snapshot(
        task_id=task.task_id,
        state=task.state,
        outputs=task.outputs,
        total_tokens=task.total_tokens,
        execution_time=task.execution_time,
        node_list=task.node_list,
        node_state=task.node_state,
        output_port_states=task.output_port_states,
        node_memory=task.node_memory,
    )
    state_store.persist_state(task.checkpoint_dir, snapshot)


def reload(task) -> None:
    """兼容新旧版本读档：state.json + meta.json 优先，其次过渡格式与旧 checkpoint。"""
    state_path = os.path.join(task.checkpoint_dir, "state.json")
    meta_path = os.path.join(task.checkpoint_dir, "meta.json")
    graph_path = os.path.join(task.checkpoint_dir, "graph.json")
    mailboxes_path = os.path.join(task.checkpoint_dir, "mailboxes.json")
    old_checkpoint_path = os.path.join(task.checkpoint_dir, "checkpoint.json")

    try:
        # 最新格式：state.json + meta.json
        if os.path.exists(state_path) and os.path.exists(meta_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)

            task.state = checkpoint_io.restore_task_state(
                state_data.get("state", "ready")
            )

            task.create_time = meta_data.get("create_time", "2025-01-01 00:00:00")
            task.inputs = meta_data.get("inputs", {})
            task.graph = meta_data.get("graph", task.graph)

            saved_states = state_data.get("node_state", state_data.get("dag_state", {}))
            task.node_state = checkpoint_io.restore_node_states(saved_states)

            task.output_port_states = checkpoint_io.restore_port_states(
                state_data.get("output_port_states", {})
            )

            task.outputs = state_data.get("outputs", {})
            task.total_tokens = state_data.get("total_tokens", 0)
            task.execution_time = state_data.get("execution_time", 0.0)

        # 过渡格式：state.json + graph.json + mailboxes.json
        elif os.path.exists(state_path) and os.path.exists(graph_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            with open(graph_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            task.state = checkpoint_io.restore_task_state(
                state_data.get("state", "ready")
            )

            task.create_time = state_data.get("create_time", "2025-01-01 00:00:00")

            saved_states = state_data.get("node_state", state_data.get("dag_state", {}))
            task.node_state = checkpoint_io.restore_node_states(saved_states)

            task.output_port_states = checkpoint_io.restore_port_states(
                state_data.get("output_port_states", {})
            )

            task.graph = graph_data

            if os.path.exists(mailboxes_path):
                with open(mailboxes_path, "r", encoding="utf-8") as f:
                    mailboxes_data = json.load(f)
                task.inputs = mailboxes_data.get("inputs", {})
                task.outputs = mailboxes_data.get("outputs", {})

        # 旧格式：从 checkpoint.json 读取（向后兼容）
        elif os.path.exists(old_checkpoint_path):
            with open(old_checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            task.state = checkpoint_io.restore_task_state(data.get("state", "ready"))

            task.inputs = data.get("inputs", {})
            task.outputs = data.get("outputs", {})
            task.graph = data.get("graph", task.graph)
            task.create_time = data.get("create_time", "2025-01-01 00:00:00")

            saved_states = data.get("node_state", data.get("dag_state", {}))
            task.node_state = checkpoint_io.restore_node_states(saved_states)

            task.output_port_states = checkpoint_io.restore_port_states(
                data.get("output_port_states", {})
            )

            migrate_old_memory(task, data.get("node_memory", {}))

        # 无论从哪里加载，强行剔除内存里的 messages，防止污染新架构
        for _node_id, mem in task.node_memory.items():
            mem.pop("messages", None)

    except Exception as e:
        print(f"❌ 读取 Checkpoint 失败: {e}")


def migrate_old_memory(task, old_memory: dict) -> None:
    """把旧格式 node_memory 迁移到节点自治目录结构。"""
    if not old_memory:
        return

    from src.harness.node.agent_node import AgentNode

    for node_id, memory_data in old_memory.items():
        if node_id in task.node_list:
            node_instance = task.node_list[node_id]
            if isinstance(node_instance, AgentNode):
                node_instance.migrate_old_memory(memory_data, task)
