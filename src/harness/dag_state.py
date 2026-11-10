"""DAG 节点与端口状态机的纯逻辑（不碰磁盘、不调度协程）。

`Task` 只负责持有状态并委托到这里，保证主循环可独立测试。
"""

from __future__ import annotations

from .enums import NodeState, PortState


def resolve_runnable_nodes(
    node_state: dict, edges: list[dict], output_port_states: dict
) -> list[str]:
    """扫一遍 READY 节点，返回本轮可启动的节点。

    全 VOID 的节点会被就地标记 SKIPPED 并清空下游端口；这个副作用必须在
    同一轮内立即生效，后序节点才能读到刚变成 VOID 的上游并继续传播。
    """
    runnable = []

    for node_id, state in node_state.items():
        if state != NodeState.READY:
            continue

        incoming_edges = [e for e in edges if e["target"] == node_id]

        # 源头节点（没有任何输入连线）直接可以跑
        if not incoming_edges:
            runnable.append(node_id)
            continue

        all_resolved = True  # 所有上游是否都已有结果（HAS_DATA 或 VOID）
        has_any_data = False  # 是否收到至少一份有效数据

        for edge in incoming_edges:
            src_node = edge["source"]
            src_port = edge.get("sourceHandle", "default")
            port_state = output_port_states.get(src_node, {}).get(
                src_port, PortState.PENDING
            )

            if port_state == PortState.PENDING:
                all_resolved = False
                break
            elif port_state == PortState.HAS_DATA:
                has_any_data = True

        if all_resolved:
            if has_any_data:
                # 只要有一条线有数据就唤醒（分支汇聚）
                runnable.append(node_id)
            else:
                # 所有线都是 VOID：当前分支彻底短路
                cascade_skip(node_state, output_port_states, node_id, edges)

    return runnable


def update_port_states(
    output_port_states: dict, source_node_id: str, outputs: dict, edges: list[dict]
) -> None:
    """只更新端口红绿灯，不动载荷数据。"""
    if source_node_id not in output_port_states:
        output_port_states[source_node_id] = {}
    for edge in edges:
        if edge["source"] == source_node_id:
            out_port = edge.get("sourceHandle", "default")
            if outputs and out_port in outputs:
                output_port_states[source_node_id][out_port] = PortState.HAS_DATA
            else:
                output_port_states[source_node_id][out_port] = PortState.VOID


def cascade_skip(
    node_state: dict,
    output_port_states: dict,
    node_id: str,
    edges: list[dict],
) -> None:
    """把节点标记为 SKIPPED，并把它的所有出边端口置为 VOID。"""
    node_state[node_id] = NodeState.SKIPPED
    if node_id not in output_port_states:
        output_port_states[node_id] = {}

    for edge in edges:
        if edge["source"] == node_id:
            out_port = edge.get("sourceHandle", "default")
            output_port_states[node_id][out_port] = PortState.VOID


def mark_success(
    node_state: dict,
    output_port_states: dict,
    node_id: str,
    result: dict,
    edges: list[dict],
) -> None:
    """节点成功：先置 COMPLETED，再点亮下游端口（顺序与旧实现一致）。"""
    node_state[node_id] = NodeState.COMPLETED
    update_port_states(output_port_states, node_id, result, edges)
