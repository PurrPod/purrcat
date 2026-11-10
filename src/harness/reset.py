"""节点重置的级联传播。

BFS 顺序逐节点：重置状态 → 清空出边端口 → 取消残留协程 → 清理节点目录
→ 把下游入队。顺序即语义，不要在调用方重排。
"""

from __future__ import annotations

import os
import shutil
from collections import deque
from typing import Callable

from .enums import NodeState


def plan_reset(start_node_id: str, edges: list[dict]) -> list[tuple[str, bool]]:
    """返回 BFS 顺序的 (node_id, is_target) 列表，目标节点排在最前。"""
    order = []
    queue = deque([(start_node_id, True)])
    visited = {start_node_id}

    while queue:
        curr_id, is_target = queue.popleft()
        order.append((curr_id, is_target))
        for edge in edges:
            if edge["source"] == curr_id:
                target_id = edge["target"]
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append((target_id, False))

    return order


def cascade_reset(
    *,
    start_node_id: str,
    is_injection: bool,
    checkpoint_dir: str,
    node_state: dict,
    output_port_states: dict,
    running_tasks: dict,
    edges: list[dict],
    cancel_task: Callable[[object], None],
) -> None:
    for curr_id, is_target in plan_reset(start_node_id, edges):
        # 1. 状态恢复待命
        node_state[curr_id] = NodeState.READY

        # 2. 清空该节点向外发射的端口状态
        if curr_id in output_port_states:
            output_port_states[curr_id].clear()

        # 3. 打断可能仍在运行的协程
        tasks_to_cancel = [t for t, n in running_tasks.items() if n == curr_id]
        for task in tasks_to_cancel:
            cancel_task(task)
            running_tasks.pop(task, None)

        # 4. 清理物理产物
        node_dir = os.path.join(checkpoint_dir, "nodes", curr_id)
        if os.path.exists(node_dir):
            if is_target and is_injection:
                # 指令注入：只删 outputs.json 触发重算，保留 live_memory
                out_file = os.path.join(node_dir, "outputs.json")
                if os.path.exists(out_file):
                    try:
                        os.remove(out_file)
                    except Exception:
                        pass
            else:
                # 彻底重置：清空整个节点目录
                shutil.rmtree(node_dir, ignore_errors=True)
