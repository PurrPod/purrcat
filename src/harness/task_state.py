"""任务控制指令与状态寄存器的纯逻辑（不碰磁盘、不调度协程）。

`Task` 只持有 ``node_memory`` / ``node_state`` 并委托到这里，
保证 inject/kill 的状态变化可独立测试。
"""

from __future__ import annotations

from .enums import NodeState, TaskState

TERMINAL_STATES = (TaskState.COMPLETED, TaskState.ERROR, TaskState.KILLED)


def queue_force_push(node_memory: dict, node_id: str, instruction: str) -> None:
    """把指令追加到节点的 force_push 队列，并标记续跑不重复吸收上游。"""
    memory = node_memory.setdefault(node_id, {})
    queue = memory.get("force_push")
    if not isinstance(queue, list):
        queue = []
        memory["force_push"] = queue
    queue.append(instruction)
    memory["skip_upstream"] = True


def wake_state(state: TaskState) -> TaskState:
    """注入后唤醒任务；运行中的任务保持 RUNNING，避免 API 重复拉起引擎。"""
    return state if state == TaskState.RUNNING else TaskState.READY


def accepts_kill(state: TaskState) -> bool:
    """终态任务不再接受 kill。"""
    return state not in TERMINAL_STATES


def any_waiting(node_state: dict) -> bool:
    return any(state == NodeState.WAITING for state in node_state.values())


def waiting_human_nodes(node_state: dict, node_types: dict) -> list[str]:
    return [
        node_id
        for node_id, state in node_state.items()
        if state == NodeState.WAITING
        and node_types.get(node_id) == "human_intervention"
    ]


def suspended_message(node_state: dict, node_types: dict) -> str:
    """挂起提示：点名人工干预节点，提醒 Agent 无权代答。"""
    waiting_hi = waiting_human_nodes(node_state, node_types)
    if waiting_hi:
        return (
            f"任务已在人工干预节点 {waiting_hi} 处挂起，等待人类指令。"
            "你没有对人工干预节点注入指令的权力，"
            "请转告用户：到任务面板对应节点亲自输入指令后，工作流才会继续。"
        )
    return "任务已挂起，等待人工干预"
