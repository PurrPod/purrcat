"""检索打分与衰减计算（SPEC-012）。"""

from __future__ import annotations

from .schema import GRAPH_NODE_EXACT_BOOST, GRAPH_NODE_PARTIAL_BOOST


def reciprocal_rank_fusion(vector_results, bm25_results, k=60, top_k=5):
    """RRF 倒数排名融合。

    :param vector_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 0.8}
    :param bm25_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 15.2}
    """
    fused_scores = {}
    fused_data = {}

    for result_list in (vector_results, bm25_results):
        for rank, item in enumerate(
            sorted(result_list, key=lambda x: x["score"], reverse=True)
        ):
            item_id = item["id"]
            fused_scores[item_id] = fused_scores.get(item_id, 0) + 1.0 / (k + rank + 1)
            fused_data[item_id] = item["data"]

    reranked = [
        {"id": item_id, "data": fused_data[item_id], "rrf_score": score}
        for item_id, score in sorted(
            fused_scores.items(), key=lambda x: x[1], reverse=True
        )
    ]

    return reranked[:top_k]


def similarity_from_distance(distance: float) -> float:
    """ChromaDB 余弦距离转相似度。"""
    return 1.0 - distance


def graph_node_boost(query: str, node_name: str) -> float:
    """图谱节点名称命中的加权分。"""
    query_lower = query.lower()
    node_lower = node_name.lower()
    if query_lower == node_lower:
        return GRAPH_NODE_EXACT_BOOST
    if query_lower in node_lower or node_lower in query_lower:
        return GRAPH_NODE_PARTIAL_BOOST
    return 0.0


def decayed_confidence(
    confidence: float,
    days_since_update: int,
    days_threshold: int,
    decay_rate: float,
    min_confidence: float,
) -> float | None:
    """未强化边的衰减结果；无需更新时返回 ``None``。"""
    if days_since_update < days_threshold:
        return None
    decay_amount = decay_rate * (days_since_update - days_threshold)
    new_confidence = max(min_confidence, confidence - decay_amount)
    return new_confidence if new_confidence < confidence else None
