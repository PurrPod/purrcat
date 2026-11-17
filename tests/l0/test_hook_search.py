"""search hook：limit 透传与 route=all 并行合并（SPEC-039）。"""

from __future__ import annotations

import src.tool.memo.memo as memo_mod
import src.tool.search.search as search_mod
from src.agent.hook_handler import (
    HookHandler,
    _parse_search_limit,
    _parse_search_min_score,
)
from src.utils import initial_templates


def _handler() -> HookHandler:
    return HookHandler(config_dict={"hooks": {}})


def test_limit_is_passed_to_local_search(monkeypatch):
    calls = {}

    class FakeSearch:
        def __new__(cls, route, query, topk=5, min_score=0.30):
            calls.update(route=route, query=query, topk=topk, min_score=min_score)
            return f"local:{query}:{topk}"

    monkeypatch.setattr(search_mod, "Search", FakeSearch)

    result = _handler()._search({"query": "周报", "route": "local", "limit": 3})

    assert calls == {
        "route": "local",
        "query": "周报",
        "topk": 3,
        "min_score": 0.30,
    }
    assert result == {"success": True, "inject_prompt": "local:周报:3"}


def test_min_score_is_passed_to_search(monkeypatch):
    calls = {}

    class FakeSearch:
        def __new__(cls, route, query, topk=5, min_score=0.30):
            calls.update(min_score=min_score)
            return "ok"

    monkeypatch.setattr(search_mod, "Search", FakeSearch)

    _handler()._search({"query": "q", "min_score": "0.6"})

    assert calls["min_score"] == 0.6


def test_limit_is_passed_to_memory_search(monkeypatch):
    calls = {}

    class FakeMemo:
        def __new__(cls, action=None, query=None):
            calls.update(action=action, query=query)
            return f"memory:{query['prompt']}:{query['top_k']}"

    monkeypatch.setattr(memo_mod, "Memo", FakeMemo)

    result = _handler()._search({"query": "周报", "route": "memory", "limit": 2})

    assert calls == {
        "action": "search",
        "query": {"prompt": "周报", "top_k": 2, "min_score": 0.30},
    }
    assert result["inject_prompt"] == "memory:周报:2"


def test_route_all_merges_local_and_memory(monkeypatch):
    monkeypatch.setattr(
        search_mod, "Search", lambda route, query, topk=5, min_score=0.30: "LOCAL"
    )
    monkeypatch.setattr(memo_mod, "Memo", lambda action=None, query=None: "MEMORY")

    result = _handler()._search({"query": "q", "route": "all", "limit": 4})

    assert result["success"] is True
    assert result["inject_prompt"] == "LOCAL\n\nMEMORY"


def test_route_all_keeps_partial_result_when_one_route_fails(monkeypatch):
    def boom(route, query, topk=5, min_score=0.30):
        raise RuntimeError("no index")

    monkeypatch.setattr(search_mod, "Search", boom)
    monkeypatch.setattr(memo_mod, "Memo", lambda action=None, query=None: "MEMORY")

    result = _handler()._search({"query": "q", "route": "all"})

    assert result["success"] is True
    assert "搜索失败(local)" in result["inject_prompt"]
    assert "MEMORY" in result["inject_prompt"]


def test_limit_is_clamped_to_one_through_fifteen():
    assert _parse_search_limit("0") == 1
    assert _parse_search_limit("99") == 15
    assert _parse_search_limit("bad") == 5
    assert _parse_search_limit(None) == 5


def test_min_score_falls_back_and_clamps():
    assert _parse_search_min_score("bad") == 0.30
    assert _parse_search_min_score(None) == 0.30
    assert _parse_search_min_score("-1") == 0.0
    assert _parse_search_min_score("2") == 1.0


def test_hook_default_min_score_matches_search_tool():
    from src.tool.search.search import DEFAULT_MIN_SCORE

    assert _parse_search_min_score(None) == DEFAULT_MIN_SCORE


def test_default_template_searches_memory_on_input():
    text = initial_templates.DEFAULT_PARADIGM_YAML

    assert "on_input_received:" in text
    assert 'query: "@USERQUERY"' in text
    assert 'route: "memory"' in text
    assert 'route: "all"' not in text


def test_memory_route_passes_min_score(monkeypatch):
    calls = {}

    class FakeMemo:
        def __new__(cls, action=None, query=None):
            calls.update(action=action, query=query)
            return "MEMORY"

    monkeypatch.setattr(memo_mod, "Memo", FakeMemo)

    _handler()._search({"query": "q", "route": "memory", "min_score": "0.45"})

    assert calls["query"]["min_score"] == 0.45
    assert calls["query"]["top_k"] == 5
