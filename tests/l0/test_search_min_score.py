"""Search 工具：skill / mcp / local 的置信度过滤（min_score）。"""

from __future__ import annotations

import src.tool.search.search as search_mod
from src.tool.search.search import (
    DEFAULT_MIN_SCORE,
    Search,
    parse_min_score,
    raw_search,
)

SKILLS = [
    {"skill": {"name": "keep", "description": "keep me"}, "score": 0.52},
    {"skill": {"name": "drop", "description": "drop me"}, "score": 0.25},
]
MCPS = [
    {"server_name": "svr", "tool_name": "keep", "description": "", "score": 0.35},
    {"server_name": "svr", "tool_name": "drop", "description": "", "score": 0.25},
]


def _patch(monkeypatch, skills=None, mcps=None):
    monkeypatch.setattr(
        search_mod, "search_skills", lambda q, k: (list(skills or []), None)
    )
    monkeypatch.setattr(search_mod, "mcp_search", lambda q, k: (list(mcps or []), None))


def test_default_threshold_is_035():
    assert DEFAULT_MIN_SCORE == 0.30


def test_parse_min_score_clamps_and_falls_back():
    assert parse_min_score("bad") == DEFAULT_MIN_SCORE
    assert parse_min_score(None) == DEFAULT_MIN_SCORE
    assert parse_min_score("-1") == 0.0
    assert parse_min_score("3") == 1.0


def test_local_search_filters_by_default_threshold(monkeypatch):
    _patch(monkeypatch, SKILLS, MCPS)

    data = raw_search("local", "q")["data"]

    assert [item["skill"]["name"] for item in data["skills"]] == ["keep"]
    assert [item["tool_name"] for item in data["mcp_tools"]] == ["keep"]


def test_min_score_can_be_lowered(monkeypatch):
    _patch(monkeypatch, SKILLS, MCPS)

    data = raw_search("local", "q", min_score=0.2)["data"]

    assert len(data["skills"]) == 2
    assert len(data["mcp_tools"]) == 2


def test_min_score_can_be_raised(monkeypatch):
    _patch(monkeypatch, SKILLS, MCPS)

    data = raw_search("local", "q", min_score=0.9)["data"]

    assert data["skills"] == []
    assert data["mcp_tools"] == []


def test_search_tool_applies_default_filter(monkeypatch):
    _patch(monkeypatch, SKILLS, MCPS)

    text = Search("skill", "q")["content"]

    assert "keep" in text
    assert "drop" not in text


def test_web_route_is_not_filtered(monkeypatch):
    monkeypatch.setattr(
        search_mod,
        "web_search",
        lambda q, k: ([{"title": "t", "url": "u", "snippet": "s"}], None),
    )

    data = raw_search("web", "q", min_score=0.99)["data"]

    assert len(data["results"]) == 1
