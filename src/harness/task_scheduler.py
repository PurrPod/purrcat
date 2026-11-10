"""单轮 DAG 调度：取可运行节点、并发启动、等待完成。

`Task.run` 只负责循环与终态判定，这里负责每一轮的任务表操作。
"""

from __future__ import annotations

import asyncio
from typing import Callable

from . import dag_state
from .enums import NodeState, TaskState


def get_runnable_nodes(task) -> list[str]:
    """按状态机取本轮可启动节点（可能就地触发级联 skip）。"""
    return dag_state.resolve_runnable_nodes(
        task.node_state, task.graph.get("edges", []), task.output_port_states
    )


def select_nodes_to_start(task, runnable_nodes: list[str]) -> list[str]:
    """排除仍在任务表中的节点，避免重置后重复启动。"""
    running = set(task.running_tasks.values())
    return [node_id for node_id in runnable_nodes if node_id not in running]


def start_nodes(task, node_ids: list[str], max_concurrency: int) -> None:
    """按并发上限启动协程：先置 RUNNING，再创建任务并登记。"""
    for node_id in node_ids:
        if len(task.running_tasks) >= max_concurrency:
            break

        task.node_state[node_id] = NodeState.RUNNING
        node_instance = task.node_list[node_id]
        coro = asyncio.create_task(task._execute_node_wrapper(node_id, node_instance))
        task.running_tasks[coro] = node_id


async def await_completion(task) -> dict | None:
    """等待首个完成；成功置位，异常置 ERROR 并返回错误结构。"""
    done, _pending = await asyncio.wait(
        task.running_tasks.keys(), return_when=asyncio.FIRST_COMPLETED
    )

    for finished in done:
        node_id = task.running_tasks.pop(finished, None)
        if node_id is None:
            continue
        try:
            result = finished.result()
            task._handle_node_success(node_id, result)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            task.node_state[node_id] = NodeState.ERROR
            task.state = TaskState.ERROR
            return {"status": "error", "message": f"节点 {node_id} 异常: {str(e)}"}
    return None


async def run_round(
    task,
    runnable_nodes: list[str],
    *,
    max_concurrency: int,
    save_state: Callable[[], None],
) -> dict | None:
    """执行一轮：启动 → 写盘 → 等首个完成 → 写盘；失败时由调用方补写终态。"""
    nodes_to_start = select_nodes_to_start(task, runnable_nodes)
    start_nodes(task, nodes_to_start, max_concurrency)

    if nodes_to_start:
        await asyncio.to_thread(save_state)

    error = await await_completion(task)
    if error:
        return error

    await asyncio.to_thread(save_state)
    return None
