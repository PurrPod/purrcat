"""检索层的纯计算：混合打分、TopK 排序与名次判定。

MCP 与 Skill 共用同一套公式，唯一差异是 BM25 负分是否截断。
"""

from __future__ import annotations

import numpy as np

from .semantic_utils import hybrid_tokenize

BM25_WEIGHT = 0.03


def build_bm25(corpus: list[str]):
    from rank_bm25 import BM25Okapi

    return BM25Okapi([hybrid_tokenize(doc) for doc in corpus])


def build_hybrid_index(embedding_searcher, corpus: list[str]):
    """构建稠密向量矩阵与 BM25 索引（同步/JIT 路径共用）。"""
    matrix = embedding_searcher.encode(corpus)
    return matrix, build_bm25(corpus)


def hybrid_scores(dense_scores, raw_bm25_scores, *, clamp_negative: bool) -> np.ndarray:
    """dense + log1p(bm25) * 权重。

    ``clamp_negative`` 用于保留 Skill 搜索对 BM25 负分的截断行为；
    MCP 搜索未截断，保持原语义。
    """
    scores = []
    for i in range(len(dense_scores)):
        raw = raw_bm25_scores[i]
        if clamp_negative:
            raw = max(raw, 0.0)
        scores.append(float(dense_scores[i]) + np.log1p(raw) * BM25_WEIGHT)
    return np.array(scores)


def top_k_indices(scores: np.ndarray, k: int) -> np.ndarray:
    return np.argsort(scores)[::-1][:k]


def mcp_document_text(server_name: str, tool_name: str, description: str) -> str:
    """MCP 工具在检索语料中的文本表示。"""
    return f"{server_name} {tool_name} {tool_name.replace('_', ' ')} {description}"


def skill_document_text(name: str, description: str, content: str) -> str:
    """Skill 在检索语料中的文本表示。"""
    return f"{name} {description} {content}"


def score_top_k(
    embedding_searcher, query: str, matrix, bm25, k: int, *, clamp_negative: bool
) -> tuple[np.ndarray, np.ndarray]:
    """编码查询并完成 dense + BM25 混合打分与 TopK 截断。"""
    query_vector = embedding_searcher.encode([query])
    dense_scores = embedding_searcher.calculate_similarity(query_vector, matrix)
    raw_bm25_scores = bm25.get_scores(hybrid_tokenize(query))
    scores = hybrid_scores(dense_scores, raw_bm25_scores, clamp_negative=clamp_negative)
    return scores, top_k_indices(scores, k)


def evaluate_rank(
    scores: np.ndarray, indices: np.ndarray, target_idx: int, threshold: float
) -> tuple[bool, int, float]:
    """返回 (是否触发, 名次从 1 开始, 目标得分)；未指定目标时得分为 0.0。"""
    if target_idx < 0:
        return False, -1, 0.0

    score = float(scores[target_idx])
    for rank_pos, idx in enumerate(indices):
        if idx == target_idx and score >= threshold:
            return True, rank_pos + 1, score
    return False, -1, score
