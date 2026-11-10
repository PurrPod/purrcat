"""检索结果的纯格式化与数据整形（SPEC-012）。"""

from __future__ import annotations


def format_search_results(events, experiences, graph_results, events_warning=""):
    """把三类检索结果拼成 Markdown。"""
    markdown_parts = []

    if events_warning:
        markdown_parts.append(events_warning)

    if events:
        markdown_parts.append("## 历史事件")
        markdown_parts.extend(
            [f"- [{event['timestamp']}] {event['content']}" for event in events]
        )
        markdown_parts.append("")

    if experiences:
        markdown_parts.append("## 工作经验")
        markdown_parts.extend(
            [f"- [{exp['score']:.2f}] {exp['content']}" for exp in experiences]
        )
        markdown_parts.append("")

    if graph_results:
        markdown_parts.append("## 知识图谱")
        markdown_parts.extend(
            [
                f"- {result['description']} (置信度: {result['confidence']:.2f})"
                for result in graph_results
            ]
        )
        markdown_parts.append("")

    if not markdown_parts:
        markdown_parts.append("## 检索结果")
        markdown_parts.append("没有找到相关信息")

    return "\n".join(markdown_parts)


def describe_relation(source_name, relation: str, target_name) -> str:
    """三元组的可读描述。"""
    return f"{source_name} {relation} {target_name}"


def relation_to_dict(source_node_id, target_node_id, edge_data):
    """把 NetworkX 边数据转为对外关系字典。"""
    return {
        "edge_id": edge_data.get("edge_id"),
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relation_meaning": edge_data.get("relation_meaning"),
        "confidence": edge_data.get("confidence"),
        "created_at": edge_data.get("created_at"),
        "updated_at": edge_data.get("updated_at"),
        "source_event_id": edge_data.get("source_event_id"),
    }


def graph_to_payload(graph) -> dict:
    """把 NetworkX 图转为前端使用的 nodes/edges 结构。"""
    nodes = []
    edges = []
    for node_id in graph.nodes:
        data = graph.nodes[node_id]
        nodes.append({"id": node_id, "label": data.get("name", node_id)})

    for source, target, edge_data in graph.edges(data=True):
        edges.append(
            {
                "from": source,
                "to": target,
                "label": edge_data.get("relation_meaning", "unknown"),
                "confidence": edge_data.get("confidence", 0.0),
                "updated_at": edge_data.get("updated_at", ""),
            }
        )

    return {"nodes": nodes, "edges": edges}


def collection_records_to_experiences(results, limit: int):
    """把 ChromaDB ``collection.get`` 的结果整形为最近经验列表。"""
    experiences = []
    if results and results.get("ids"):
        for i in range(len(results["ids"])):
            meta = results["metadatas"][i] or {}
            experiences.append(
                {
                    "exp_id": results["ids"][i],
                    "content": results["documents"][i],
                    "timestamp": meta.get("timestamp", ""),
                }
            )
    experiences.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return experiences[:limit]


def edge_style(confidence: float) -> tuple[float, float]:
    """图谱边的线宽与透明度。"""
    return 1 + confidence * 3, 0.3 + confidence * 0.7
