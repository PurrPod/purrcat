"""记忆检索的纯打分、过滤、时间与 ID 逻辑（SPEC-012 AC-1/AC-2）。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.memory.purrmemo.core import clock, filters, ids, scoring


def test_rrf_merges_and_orders_by_fused_rank():
    """SPEC-012 AC-1：同时出现在两路结果中的条目排名优先。"""
    vector = [
        {"id": "a", "data": {"source": "vector"}, "score": 0.9},
        {"id": "b", "data": {"source": "vector"}, "score": 0.5},
    ]
    bm25 = [
        {"id": "b", "data": {"source": "bm25"}, "score": 9.0},
        {"id": "c", "data": {"source": "bm25"}, "score": 1.0},
    ]

    fused = scoring.reciprocal_rank_fusion(vector, bm25, k=60, top_k=2)

    assert [item["id"] for item in fused] == ["b", "a"]
    assert set(fused[0]) == {"id", "data", "rrf_score"}
    assert fused[0]["data"] == {"source": "bm25"}


def test_rrf_truncates_to_top_k():
    vector = [{"id": str(i), "data": i, "score": 1.0 - i / 10} for i in range(5)]

    assert len(scoring.reciprocal_rank_fusion(vector, [], top_k=3)) == 3


@pytest.mark.parametrize(
    "distance, expected",
    [(0.0, 1.0), (0.2, 0.8), (0.5, 0.5), (1.0, 0.0)],
)
def test_similarity_from_distance(distance, expected):
    """SPEC-012 AC-1：ChromaDB 距离转相似度。"""
    assert scoring.similarity_from_distance(distance) == pytest.approx(expected)


@pytest.mark.parametrize(
    "query, node_name, expected",
    [
        ("苹果", "苹果", 2.0),
        ("苹果", "红富士苹果", 0.5),
        ("红富士苹果", "苹果", 0.5),
        ("苹果", "香蕉", 0.0),
        ("Apple", "apple", 2.0),
    ],
)
def test_graph_node_boost(query, node_name, expected):
    """SPEC-012 AC-1：图谱节点名称命中加权。"""
    assert scoring.graph_node_boost(query, node_name) == pytest.approx(expected)


@pytest.mark.parametrize(
    "confidence, days, expected",
    [
        (1.0, 6, None),
        (1.0, 7, None),
        (1.0, 17, 0.5),
        (0.4, 100, 0.3),
        (0.3, 100, None),
    ],
)
def test_decayed_confidence(confidence, days, expected):
    """SPEC-012 AC-1：未强化边的衰减结果与下限夹紧。"""
    result = scoring.decayed_confidence(
        confidence,
        days,
        days_threshold=7,
        decay_rate=0.05,
        min_confidence=0.3,
    )
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "top_k, available, expected",
    [(5, 10, 5), (10, 5, 5), (0, 0, 0), (3, 3, 3)],
)
def test_clamp_top_k(top_k, available, expected):
    """SPEC-012 AC-2：请求条数不超过集合实际数量。"""
    assert filters.clamp_top_k(top_k, available) == expected


def test_filter_by_time_range_is_inclusive():
    """SPEC-012 AC-2：时间区间为闭区间，只读取 data.timestamp。"""
    items = [
        {"data": {"timestamp": "2026-01-01T00:00:00"}},
        {"data": {"timestamp": "2026-01-02T00:00:00"}},
        {"data": {"timestamp": "2026-01-03T00:00:00"}},
    ]

    result = filters.filter_by_time_range(
        items, "2026-01-01T00:00:00", "2026-01-02T00:00:00"
    )

    assert [item["data"]["timestamp"] for item in result] == [
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
    ]


def test_filter_experiences_by_score_uses_threshold():
    """SPEC-012 AC-2：默认阈值 0.35（含边界），可覆盖。"""
    items = [{"score": 0.2}, {"score": 0.35}, {"score": 0.5}]

    assert [item["score"] for item in filters.filter_experiences_by_score(items)] == [
        0.35,
        0.5,
    ]
    assert filters.filter_experiences_by_score(items, min_score=0.5) == [{"score": 0.5}]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("苹果", '"苹果"*'),
        (" 苹果   香蕉 ", '"苹果"* AND "香蕉"*'),
        ('he said "hi"', '"he"* AND "said"* AND "hi"*'),
        ("it's ok", '"its"* AND "ok"*'),
    ],
)
def test_build_fts_query(query, expected):
    """SPEC-012 AC-2：FTS5 前缀 AND 查询。"""
    assert filters.build_fts_query(query) == expected


@pytest.mark.parametrize("query", ["", "   ", '"""', "''"])
def test_build_fts_query_returns_none_without_tokens(query):
    """SPEC-012 AC-2：无有效词时不构造查询。"""
    assert filters.build_fts_query(query) is None


def test_date_range_for_day_bounds():
    """SPEC-012 AC-2：日期转当天起止时间。"""
    assert filters.date_range_for(" 2026-05-15 ") == (
        "2026-05-15T00:00:00",
        "2026-05-15T23:59:59.999999",
    )


@pytest.mark.parametrize("raw_date", ["2026/05/15", "2026-13-01", "not-a-date"])
def test_date_range_for_rejects_invalid(raw_date):
    """SPEC-012 AC-2：非法日期抛 ValueError，由调用方决定提示。"""
    with pytest.raises(ValueError):
        filters.date_range_for(raw_date)


@pytest.mark.parametrize(
    "func, value, prefix",
    [
        (ids.event_id_for, "杯子掉在地上", "evt_"),
        (ids.experience_id_for, "先检查网络", "exp_"),
    ],
)
def test_content_ids_are_stable_and_prefixed(func, value, prefix):
    """SPEC-012 AC-1：内容 ID 可复现且前缀固定。"""
    first = func(value)
    assert first == func(value)
    assert first.startswith(prefix)
    assert len(first) == len(prefix) + 32


def test_node_id_normalizes_name():
    """SPEC-012 AC-1：节点 ID 去空格、统一小写并截断。"""
    node_id = ids.node_id_for("  Apple ")
    assert node_id == ids.node_id_for("apple")
    assert node_id.startswith("node_")
    assert len(node_id) == len("node_") + 16


def test_edge_id_depends_on_relation():
    """SPEC-012 AC-1：边 ID 由三元组决定。"""
    first = ids.edge_id_for("a", "b", "喜欢")
    assert first == ids.edge_id_for("a", "b", "喜欢")
    assert first != ids.edge_id_for("a", "b", "讨厌")
    assert len(first) == 32


def test_clock_helpers():
    """SPEC-012 AC-1：共享时间原语的格式与相对天数。"""
    now = datetime(2026, 5, 15, 12, 0, 0)

    assert clock.parse_iso(clock.now_iso()) <= datetime.now()
    assert clock.iso_days_ago(7, now=now) == "2026-05-08T12:00:00"
    assert clock.days_since("2026-05-01T00:00:00", now=now) == 14
