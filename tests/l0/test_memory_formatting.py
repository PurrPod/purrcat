"""记忆结果的格式化、提示词与 pending 解析（SPEC-012 AC-3）。"""

from __future__ import annotations

from datetime import datetime

import networkx as nx
import pytest

from src.memory.purrmemo.core import formatting
from src.memory.purrmemo.core.clock import parse_iso
from src.memory.purrmemo.core.memory_worker import payload, prompts


def test_format_search_results_empty_fallback():
    """SPEC-012 AC-3：无结果时给出固定兜底文案。"""
    assert formatting.format_search_results([], [], []) == (
        "## 检索结果\n没有找到相关信息"
    )


def test_format_search_results_warning_only():
    """SPEC-012 AC-3：仅有告警时只返回告警。"""
    assert formatting.format_search_results([], [], [], "⚠️ 无结果\n\n") == (
        "⚠️ 无结果\n\n"
    )


def test_format_search_results_full_sections_and_order():
    """SPEC-012 AC-3：三类结果分节、顺序与数值格式稳定。"""
    events = [{"timestamp": "2026-01-01T10:00:00", "content": "开会"}]
    experiences = [{"score": 0.8, "content": "先检查网络"}]
    graph_results = [
        {
            "description": "用户 喜欢 苹果",
            "confidence": 0.9,
        }
    ]

    result = formatting.format_search_results(
        events, experiences, graph_results, "⚠️ 提示\n\n"
    )

    assert result == (
        "⚠️ 提示\n\n"
        "\n"
        "## 历史事件\n"
        "- [2026-01-01T10:00:00] 开会\n"
        "\n"
        "## 工作经验\n"
        "- [0.80] 先检查网络\n"
        "\n"
        "## 知识图谱\n"
        "- 用户 喜欢 苹果 (置信度: 0.90)\n"
    )


def test_graph_to_payload_maps_nodes_and_edges():
    """SPEC-012 AC-3：图谱转 nodes/edges 时保留默认值。"""
    graph = nx.DiGraph()
    graph.add_node("a", name="用户")
    graph.add_node("b")
    graph.add_edge(
        "a",
        "b",
        relation_meaning="喜欢",
        confidence=0.8,
        updated_at="2026-01-01T00:00:00",
    )

    assert formatting.graph_to_payload(graph) == {
        "nodes": [{"id": "a", "label": "用户"}, {"id": "b", "label": "b"}],
        "edges": [
            {
                "from": "a",
                "to": "b",
                "label": "喜欢",
                "confidence": 0.8,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
    }


def test_graph_to_payload_edge_defaults():
    """SPEC-012 AC-3：缺省边字段回退到 unknown/0.0/空串。"""
    graph = nx.DiGraph()
    graph.add_edge("a", "b")

    edge = formatting.graph_to_payload(graph)["edges"][0]

    assert edge == {
        "from": "a",
        "to": "b",
        "label": "unknown",
        "confidence": 0.0,
        "updated_at": "",
    }


def test_collection_records_to_experiences_sorts_and_limits():
    """SPEC-012 AC-3：最近经验按时间倒序并截断。"""
    results = {
        "ids": ["e1", "e2", "e3"],
        "documents": ["一", "二", "三"],
        "metadatas": [
            {"timestamp": "2026-01-01"},
            None,
            {"timestamp": "2026-03-01"},
        ],
    }

    assert formatting.collection_records_to_experiences(results, limit=2) == [
        {"exp_id": "e3", "content": "三", "timestamp": "2026-03-01"},
        {"exp_id": "e1", "content": "一", "timestamp": "2026-01-01"},
    ]


@pytest.mark.parametrize("results", [None, {}, {"ids": []}])
def test_collection_records_to_experiences_empty(results):
    """SPEC-012 AC-3：空集合结果返回空列表。"""
    assert formatting.collection_records_to_experiences(results, limit=30) == []


def test_relation_to_dict_includes_all_fields():
    """SPEC-012 AC-3：关系字典字段完整。"""
    edge_data = {
        "edge_id": "edge-1",
        "relation_meaning": "喜欢",
        "confidence": 0.5,
        "created_at": "c",
        "updated_at": "u",
        "source_event_id": "evt-1",
    }

    assert formatting.relation_to_dict("a", "b", edge_data) == {
        "edge_id": "edge-1",
        "source_node_id": "a",
        "target_node_id": "b",
        "relation_meaning": "喜欢",
        "confidence": 0.5,
        "created_at": "c",
        "updated_at": "u",
        "source_event_id": "evt-1",
    }


def test_relation_to_dict_defaults_to_none():
    """SPEC-012 AC-3：缺失字段统一为 None。"""
    assert formatting.relation_to_dict("a", "b", {}) == {
        "edge_id": None,
        "source_node_id": "a",
        "target_node_id": "b",
        "relation_meaning": None,
        "confidence": None,
        "created_at": None,
        "updated_at": None,
        "source_event_id": None,
    }


def test_describe_relation_keeps_unknown_placeholder():
    """SPEC-012 AC-3：未知节点由调用方传入占位名。"""
    assert formatting.describe_relation("用户", "喜欢", "苹果") == "用户 喜欢 苹果"
    assert formatting.describe_relation("未知", "喜欢", "未知") == "未知 喜欢 未知"


@pytest.mark.parametrize(
    "confidence, expected",
    [(0.0, (1.0, 0.3)), (0.5, (2.5, 0.65)), (1.0, (4.0, 1.0))],
)
def test_edge_style(confidence, expected):
    """SPEC-012 AC-3：图谱边宽与透明度公式。"""
    width, opacity = formatting.edge_style(confidence)
    assert width == pytest.approx(expected[0])
    assert opacity == pytest.approx(expected[1])


def test_build_user_content_numbers_entries():
    """SPEC-012 AC-3：提示词条目从 1 开始编号并带固定尾句。"""
    assert prompts.build_user_content(["第一条", "第二条"]) == (
        "【待处理的认知条目】\n"
        "1. 第一条\n"
        "2. 第二条\n"
        "\n"
        "请开始处理：先用 rag_search 检索，然后逐条写入图谱。"
    )


def test_build_messages_system_and_user_roles():
    """SPEC-012 AC-3：消息结构为 system + user。"""
    messages = prompts.build_messages(["用户喜欢苹果"])

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == prompts.MEMORY_WORKER_SYSTEM_PROMPT
    assert "1. 用户喜欢苹果" in messages[1]["content"]


def test_parse_pending_payload_defaults():
    """SPEC-012 AC-3：缺失字段回退为空列表与当前时间。"""
    parsed = payload.parse_pending_payload({})

    assert parsed.cognition == []
    assert parsed.user_profile == []
    assert parsed.work_exp == []
    assert parsed.events == []
    assert parse_iso(parsed.timestamp) <= datetime.now()


def test_parse_pending_payload_preserves_values():
    """SPEC-012 AC-3：已有字段原样保留。"""
    data = {
        "timestamp": "20260515113200",
        "cognition": ["c"],
        "user_profile": ["u"],
        "work_exp": ["w"],
        "events": [{"time": "t", "event": "e"}],
    }

    parsed = payload.parse_pending_payload(data)

    assert parsed.timestamp == "20260515113200"
    assert parsed.cognition == ["c"]
    assert parsed.user_profile == ["u"]
    assert parsed.work_exp == ["w"]
    assert parsed.events == [{"time": "t", "event": "e"}]


def test_iter_event_records_handles_dict_and_string():
    """SPEC-012 AC-3：事件对象取 event/time，字符串沿用默认时间。"""
    records = list(
        payload.iter_event_records(
            [{"event": "开会", "time": "2026-01-01"}, "散步"], "2026-02-02"
        )
    )

    assert records == [("开会", "2026-01-01"), ("散步", "2026-02-02")]


def test_iter_event_records_dict_defaults():
    """SPEC-012 AC-3：事件对象缺字段时使用默认值。"""
    records = list(payload.iter_event_records([{}], "2026-02-02"))

    assert records == [("", "2026-02-02")]
