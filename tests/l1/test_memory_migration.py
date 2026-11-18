"""记忆系统 v2 迁移（SPEC-020 AC-11）。"""

from __future__ import annotations

import pytest

from src.memory.migrate_v2 import migrate
from src.memory.purrmemo.core.storage.event_engine import EventEngine
from src.memory.purrmemo.core.storage.experience_engine import ExperienceEngine
from src.memory.purrmemo.core.utils import SingletonMeta


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """单例缓存按用例隔离，保证每个引擎绑定当前 tmp_path。"""
    monkeypatch.setattr(SingletonMeta, "_instances", {})
    monkeypatch.setattr(SingletonMeta, "_locks", {})


class FakeCollection:
    def __init__(self, ids, documents, metadatas):
        self.ids = list(ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)

    def count(self):
        return len(self.ids)

    def get(self, limit=None, offset=None, include=None):
        start = offset or 0
        end = start + (limit or len(self.ids))
        return {
            "ids": self.ids[start:end],
            "documents": self.documents[start:end],
            "metadatas": self.metadatas[start:end],
        }


class FakeVectorEngine:
    def __init__(self, collection, event_ids):
        self.collection = collection
        self.event_ids = list(event_ids)
        self.deleted_events = []
        self.deleted_experiences = []

    def list_event_ids(self):
        return list(self.event_ids)

    def delete_event_vectors(self, event_ids):
        self.deleted_events.extend(event_ids)
        for event_id in event_ids:
            if event_id in self.event_ids:
                self.event_ids.remove(event_id)
        return True

    def list_experience_ids(self):
        return list(self.collection.ids)

    def delete_experience(self, exp_id):
        self.deleted_experiences.append(exp_id)
        index = self.collection.ids.index(exp_id)
        for values in (
            self.collection.ids,
            self.collection.documents,
            self.collection.metadatas,
        ):
            values.pop(index)
        return True


@pytest.fixture()
def setup(tmp_path):
    event_engine = EventEngine(db_path=str(tmp_path / "events.db"), table_name="events")
    experience_engine = ExperienceEngine(db_path=str(tmp_path / "experiences.db"))
    event_engine.insert_event("e1", "真实事件", timestamp="2026-01-01T00:00:00")
    collection = FakeCollection(
        ids=["exp_a", "exp_b"],
        documents=["路径空格启动失败", "发布前先跑测试"],
        metadatas=[
            {"timestamp": "2026-01-02T00:00:00"},
            {"timestamp": "2026-01-03T00:00:00"},
        ],
    )
    vector_engine = FakeVectorEngine(collection, ["e1", "ghost"])
    yield vector_engine, experience_engine, event_engine
    experience_engine.close()


def test_migration_dry_run_writes_nothing(setup):
    """AC-11：dry-run 只统计，不改动任何库。"""
    vector_engine, experience_engine, event_engine = setup

    stats = migrate(vector_engine, experience_engine, event_engine, dry_run=True)

    assert stats["chroma_experiences"] == 2
    assert stats["inserted_experiences"] == 2
    assert stats["orphan_event_vectors"] == 1
    assert stats["orphan_experience_vectors"] == 0
    assert experience_engine.count() == 0
    assert vector_engine.deleted_events == []
    assert vector_engine.deleted_experiences == []
    assert [hit["id"] for hit in event_engine.search_fts_bm25("真实事件")] == ["e1"]


def test_migration_backfills_and_is_idempotent(setup):
    """AC-11：回填置信度 0.6，重建中文 FTS，清孤儿并重复执行安全。"""
    vector_engine, experience_engine, event_engine = setup

    stats = migrate(vector_engine, experience_engine, event_engine)

    assert stats["inserted_experiences"] == 2
    assert stats["orphan_event_ids"] == ["ghost"]
    assert experience_engine.count() == 2

    record = experience_engine.get("exp_a")
    assert "kind" not in record
    assert record["confidence"] == pytest.approx(0.6)
    assert record["created_at"] == "2026-01-02T00:00:00"

    assert [hit["id"] for hit in experience_engine.search_bm25("路径 启动失败")] == [
        "exp_a"
    ]
    assert [hit["id"] for hit in event_engine.search_fts_bm25("真实事件")] == ["e1"]

    second = migrate(vector_engine, experience_engine, event_engine)
    assert second["inserted_experiences"] == 0
    assert experience_engine.count() == 2
