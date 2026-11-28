"""模型并发上限解析：model.json 顶层 concurrency 优先，兼容 limits.concurrency。"""

from __future__ import annotations

from src.model.facade.model import AgentModel, Model
from src.model.manager.concurrency import resolve_concurrency


def test_resolve_concurrency_prefers_top_level():
    assert resolve_concurrency({"concurrency": 3}) == 3
    assert resolve_concurrency({"concurrency": 3, "limits": {"concurrency": 2}}) == 3


def test_resolve_concurrency_falls_back_to_nested_limits():
    assert resolve_concurrency({"limits": {"concurrency": 2}}) == 2


def test_resolve_concurrency_defaults_and_guards():
    assert resolve_concurrency({}) == 1
    assert resolve_concurrency(None) == 1
    assert resolve_concurrency({"concurrency": 0}) == 1
    assert resolve_concurrency({"concurrency": "bad"}) == 1


def test_agent_model_uses_configured_concurrency(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "src.model.facade.model.get_key_semaphore",
        lambda api_key, limit: captured.setdefault("limit", limit),
    )
    monkeypatch.setattr("src.model.facade.model.LLMClient", lambda **kwargs: object())

    model = AgentModel.__new__(AgentModel)
    model.task_id = "t"
    model.model_name = "m"
    model.base_url = "http://x"
    model.api_key = "k"
    model.vision = False
    model._init_client({"concurrency": 3, "api_keys": ["k"]})

    assert captured["limit"] == 3


def test_task_model_uses_configured_concurrency(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "src.model.facade.model.get_model_config",
        lambda: {
            "task": {
                "m": {
                    "api_keys": ["k"],
                    "base_url": "http://x",
                    "concurrency": 4,
                }
            }
        },
    )
    monkeypatch.setattr(
        "src.model.facade.model.get_key_semaphore",
        lambda api_key, limit: captured.setdefault("limit", limit),
    )
    monkeypatch.setattr("src.model.facade.model.LLMClient", lambda **kwargs: object())

    Model("m")

    assert captured["limit"] == 4
