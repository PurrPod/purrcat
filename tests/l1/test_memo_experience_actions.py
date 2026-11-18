"""Memo 工具的经验管理动作（SPEC-020 AC-9）。"""

from __future__ import annotations

from src.tool.memo import memo as memo_module
from src.tool.memo.schema import MEMO_TOOL_SCHEMA


def _content(result):
    return result["content"] if isinstance(result, dict) else result


def test_schema_exposes_experience_actions():
    """AC-9：action 枚举与参数覆盖 reinforce/replace/delete。"""
    parameters = MEMO_TOOL_SCHEMA["function"]["parameters"]["properties"]

    assert set(parameters["action"]["enum"]) == {
        "add",
        "search",
        "reinforce",
        "replace",
        "delete",
    }
    assert "experience_id" in parameters
    assert "content" in parameters


def test_reinforce_returns_old_and_new_confidence(monkeypatch):
    calls = []
    monkeypatch.setattr(
        memo_module,
        "reinforce_experience",
        lambda exp_id: (
            calls.append(exp_id)
            or {"exp_id": exp_id, "old_confidence": 0.6, "new_confidence": 0.8}
        ),
    )

    result = _content(memo_module.Memo(action="reinforce", experience_id="exp_1"))

    assert calls == ["exp_1"]
    assert "0.60" in result
    assert "0.80" in result


def test_reinforce_rejects_missing_id():
    result = _content(memo_module.Memo(action="reinforce"))

    assert "experience_id" in result


def test_reinforce_reports_unknown_experience(monkeypatch):
    monkeypatch.setattr(memo_module, "reinforce_experience", lambda exp_id: None)

    result = _content(memo_module.Memo(action="reinforce", experience_id="exp_missing"))

    assert "未找到经验" in result


def test_replace_requires_content():
    result = _content(memo_module.Memo(action="replace", experience_id="exp_1"))

    assert "content" in result


def test_replace_returns_new_confidence(monkeypatch):
    monkeypatch.setattr(
        memo_module,
        "replace_experience",
        lambda exp_id, content: {
            "exp_id": exp_id,
            "content": content,
            "confidence": 1.0,
        },
    )

    result = _content(
        memo_module.Memo(action="replace", experience_id="exp_1", content="新的做法")
    )

    assert "exp_1" in result
    assert "1.00" in result


def test_delete_reports_success_and_missing(monkeypatch):
    monkeypatch.setattr(
        memo_module,
        "delete_experience",
        lambda exp_id: {"exp_id": exp_id} if exp_id == "exp_1" else None,
    )

    assert "exp_1" in _content(memo_module.Memo(action="delete", experience_id="exp_1"))
    assert "未找到经验" in _content(
        memo_module.Memo(action="delete", experience_id="exp_missing")
    )


def test_search_without_query_returns_only_latest_cache(monkeypatch):
    entries = [{"short_term": f"cache-{i}"} for i in range(7)]
    monkeypatch.setattr(memo_module.SessionStore, "load_global_memo", lambda: entries)

    result = _content(memo_module.Memo(action="search"))

    for entry in entries[:-3]:
        assert entry["short_term"] not in result
    for entry in entries[-3:]:
        assert entry["short_term"] in result
