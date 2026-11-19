"""检索打分与衰减计算（SPEC-012 / SPEC-020）。"""

from __future__ import annotations

from datetime import datetime

from .clock import parse_iso
from .schema import (
    CONFIDENCE_FLOOR,
    DECAY_HALF_LIFE_DAYS,
    GRAPH_NODE_EXACT_BOOST,
    GRAPH_NODE_PARTIAL_BOOST,
    RRF_K,
)


def reciprocal_rank_fusion(
    vector_results, bm25_results, k=RRF_K, top_k=5, vector_weight=0.5
):
    """RRF 倒数排名融合。

    :param vector_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 0.8}
    :param bm25_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 15.2}
    :param vector_weight: 向量一路的权重，BM25 取 1 - vector_weight
    """
    bm25_weight = 1.0 - vector_weight
    fused_scores = {}
    fused_data = {}

    for weight, result_list in (
        (vector_weight, vector_results),
        (bm25_weight, bm25_results),
    ):
        for rank, item in enumerate(
            sorted(result_list, key=lambda x: x["score"], reverse=True)
        ):
            item_id = item["id"]
            fused_scores[item_id] = fused_scores.get(item_id, 0) + weight / (
                k + rank + 1
            )
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


def ebbinghaus_confidence(
    confidence: float,
    days: float,
    floor: float = CONFIDENCE_FLOOR,
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
) -> float:
    """艾宾浩斯指数衰减，结果不低于 ``floor``（SPEC-020 AC-10）。"""
    decayed = confidence * (0.5 ** (max(0.0, days) / half_life_days))
    return max(floor, decayed)


def effective_confidence(
    base: float,
    updated_at: str,
    now: datetime | None = None,
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
) -> float:
    """按锚点惰性计算有效置信度；锚点非法时只做下限夹紧。"""
    current = now or datetime.now()
    try:
        anchor = parse_iso(updated_at)
    except (TypeError, ValueError):
        return max(CONFIDENCE_FLOOR, base)
    days = max(0.0, (current - anchor).total_seconds() / 86400)
    return ebbinghaus_confidence(base, days, half_life_days=half_life_days)


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
