"""事件检索的默认拒识策略（e5 校准）。"""

from __future__ import annotations

from src.memory.purrmemo.core.search_tool import RAGSearchTool


class _FakeVectorEngine:
    def __init__(self, scores=None):
        self.scores = scores or {"high": 0.90, "mid": 0.82, "low": 0.55}

    def search_events_vector(self, query, top_k=200, query_embedding=None):
        return [
            {
                "id": event_id,
                "data": {"event_id": event_id, "content": event_id},
                "score": score,
            }
            for event_id, score in self.scores.items()
        ]

    def event_similarities(self, event_ids, query_embedding):
        return {}


class _FakeEventEngine:
    def __init__(self, bm25_ids=None):
        self.bm25_ids = bm25_ids or []

    def search_fts_bm25(self, query, start_time, end_time, limit=200):
        return [
            {"id": event_id, "data": {"event_id": event_id}, "score": 10.0 - rank}
            for rank, event_id in enumerate(self.bm25_ids)
        ]


def _tool(scores=None, bm25_ids=None) -> RAGSearchTool:
    tool = RAGSearchTool.__new__(RAGSearchTool)
    tool.vector_engine = _FakeVectorEngine(scores)
    tool.event_engine = _FakeEventEngine(bm25_ids)
    return tool


def test_default_keeps_secondary_matches_when_top1_passes_gate():
    """top1 达标时保留次级相关事件，保证多命中场景的召回。"""

    result = _tool()._search_events("查询", {"top_k": 10}, query_embedding=[1.0])

    assert [event["event_id"] for event in result["events"]] == ["high", "mid", "low"]


def test_default_rejects_whole_query_when_top1_below_gate():
    """top1 低于 0.80 视为无匹配对象，整次查询不返回事件。"""

    result = _tool({"weak": 0.62, "weaker": 0.41})._search_events(
        "查询", {"top_k": 10}, query_embedding=[1.0]
    )

    assert result["events"] == []


def test_explicit_min_score_still_overrides_default():
    result = _tool()._search_events(
        "查询", {"top_k": 10, "min_score": 0.5}, query_embedding=[1.0]
    )

    assert len(result["events"]) == 3


def test_ranking_follows_weighted_rrf_not_vector_score():
    """AC-1：向量首位与 BM25 首位不同时，最终顺序按加权 RRF 排列。"""

    result = _tool({"high": 0.90, "mid": 0.85}, bm25_ids=["mid"])._search_events(
        "查询", {"top_k": 10}, query_embedding=[1.0]
    )

    assert [event["event_id"] for event in result["events"]] == ["mid", "high"]


def test_output_score_stays_vector_cosine():
    """AC-2：对外分数仍是向量余弦，不是 RRF 分数。"""

    result = _tool({"high": 0.90, "mid": 0.85}, bm25_ids=["mid"])._search_events(
        "查询", {"top_k": 10}, query_embedding=[1.0]
    )

    scores = {event["event_id"]: event["score"] for event in result["events"]}
    assert scores == {"mid": 0.85, "high": 0.90}


def test_gate_uses_best_vector_score_not_fused_first():
    """AC-3：融合首位低于 0.80 时，只要候选中存在达标向量就不误拒。"""

    result = _tool({"low": 0.79, "high": 0.90}, bm25_ids=["low"])._search_events(
        "查询", {"top_k": 10}, query_embedding=[1.0]
    )

    assert [event["event_id"] for event in result["events"]] == ["low", "high"]
