"""遗忘任务的每日判重与增量衰减。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import networkx as nx
import pytest

from src.memory import settings
from src.memory.purrmemo.core import search_tool
from src.memory.purrmemo.core.search_tool import ForgetfulnessManager


class FakeGraphEngine:
    def __init__(self, confidence=0.8, updated_at=""):
        self.graph = nx.DiGraph()
        self.graph.add_edge("a", "b", confidence=confidence, updated_at=updated_at)
        self.decayed = []

    def decay_edges(self, edges):
        self.decayed.extend(edges)
        return len(edges)


@pytest.fixture
def memory_json(tmp_path, monkeypatch):
    path = tmp_path / "memory.json"
    monkeypatch.setattr(settings, "MEMORY_CONFIG_PATH", str(path))
    monkeypatch.setattr(
        search_tool,
        "get_memory_settings",
        lambda: {"decay_half_life_days": 2, "event_retention_days": 0},
    )
    return path


def test_skips_when_last_run_within_24_hours(memory_json):
    memory_json.write_text(
        json.dumps({"_state": {"last_decay_at": datetime.now().isoformat()}}),
        encoding="utf-8",
    )
    engine = FakeGraphEngine(
        updated_at=(datetime.now() - timedelta(days=10)).isoformat()
    )

    ForgetfulnessManager(engine).run_daily_task()

    assert engine.decayed == []


def test_decays_only_the_interval_since_last_run(memory_json):
    now = datetime.now()
    memory_json.write_text(
        json.dumps(
            {"_state": {"last_decay_at": (now - timedelta(days=2)).isoformat()}}
        ),
        encoding="utf-8",
    )
    engine = FakeGraphEngine(updated_at=(now - timedelta(days=10)).isoformat())

    ForgetfulnessManager(engine).run_daily_task()

    assert len(engine.decayed) == 1
    # 半衰期 2 天、距上次衰减 2 天 → 0.8 * 0.5 = 0.4
    assert engine.decayed[0]["new_confidence"] == pytest.approx(0.4, abs=0.01)
    assert "last_decay_at" in settings.read_memory_state()


def test_first_run_decays_from_edge_updated_at(memory_json):
    now = datetime.now()
    engine = FakeGraphEngine(updated_at=(now - timedelta(days=4)).isoformat())

    ForgetfulnessManager(engine, min_confidence=0.0).run_daily_task()

    assert len(engine.decayed) == 1
    # 半衰期 2 天、4 天未强化 → 0.8 * 0.5^2 = 0.2
    assert engine.decayed[0]["new_confidence"] == pytest.approx(0.2, abs=0.01)
    payload = json.loads(memory_json.read_text(encoding="utf-8"))
    assert payload["_state"]["last_decay_at"]
    assert payload["event_retention_days"] == settings.DEFAULTS["event_retention_days"]
