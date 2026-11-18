"""事件/经验的 SQLite 与向量一致性（SPEC-020 AC-5~AC-7）。"""

from __future__ import annotations

import pytest

from src.memory.purrmemo.core.index_worker import process_outbox_once, reconcile
from src.memory.purrmemo.core.storage.event_engine import EventEngine
from src.memory.purrmemo.core.storage.experience_engine import ExperienceEngine
from src.memory.purrmemo.core.utils import SingletonMeta


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """单例缓存按用例隔离，保证每个引擎绑定当前 tmp_path。"""
    monkeypatch.setattr(SingletonMeta, "_instances", {})
    monkeypatch.setattr(SingletonMeta, "_locks", {})


class FakeVectorEngine:
    def __init__(self, event_ids=None, experience_ids=None):
        self.event_vectors = {}
        self.experience_vectors = {}
        self.deleted_events = []
        self.deleted_experiences = []
        for event_id in event_ids or []:
            self.event_vectors[event_id] = "旧事件"
        for exp_id in experience_ids or []:
            self.experience_vectors[exp_id] = "旧经验"

    def insert_event_vector(self, event_id, content, timestamp=None):
        self.event_vectors[event_id] = content
        return True

    def insert_experience(self, exp_id, content, timestamp=None, source_event_id=None):
        self.experience_vectors[exp_id] = content
        return True

    def delete_event_vectors(self, event_ids):
        for event_id in event_ids:
            self.deleted_events.append(event_id)
            self.event_vectors.pop(event_id, None)
        return True

    def delete_experience(self, exp_id):
        self.deleted_experiences.append(exp_id)
        self.experience_vectors.pop(exp_id, None)
        return True

    def list_event_ids(self):
        return list(self.event_vectors)

    def list_experience_ids(self):
        return list(self.experience_vectors)


@pytest.fixture()
def engines(tmp_path):
    event_engine = EventEngine(db_path=str(tmp_path / "events.db"), table_name="events")
    experience_engine = ExperienceEngine(db_path=str(tmp_path / "experiences.db"))
    yield event_engine, experience_engine
    experience_engine.close()


def _outbox(engine):
    return [
        (row[0], row[1])
        for row in engine.conn.execute(
            "SELECT memory_id, op FROM index_outbox ORDER BY memory_id"
        ).fetchall()
    ]


def test_event_insert_writes_tokens_and_outbox(engines):
    """AC-5/AC-7：事件写入 FTS token，并登记 upsert。"""
    event_engine, _ = engines

    assert event_engine.insert_event(
        "e1", "路径包含空格导致启动失败", timestamp="2026-01-01T00:00:00"
    )

    assert [hit["id"] for hit in event_engine.search_fts_bm25("路径 启动失败")] == [
        "e1"
    ]
    assert _outbox(event_engine) == [("e1", "upsert")]


def test_event_delete_and_cleanup_enqueue_vector_deletes(engines):
    """AC-6：删除与 90 天清理都在同一事务登记向量删除。"""
    event_engine, _ = engines
    event_engine.insert_event("old", "陈旧", timestamp="2000-01-01T00:00:00")
    event_engine.insert_event("new", "新鲜", timestamp="2999-01-01T00:00:00")

    assert event_engine.cleanup_old_events(days_threshold=90) == 1
    assert _outbox(event_engine) == [
        ("new", "upsert"),
        ("old", "delete"),
    ]
    assert event_engine.search_fts_bm25("陈旧") == []

    assert event_engine.delete_event("new") is True
    assert ("new", "delete") in _outbox(event_engine)
    assert event_engine.search_fts_bm25("新鲜") == []


def test_process_outbox_syncs_deletes_and_upserts(engines):
    """AC-5：索引器消费 outbox 后写/删向量并清空登记。"""
    event_engine, experience_engine = engines
    vector = FakeVectorEngine(event_ids=["orphan"])

    event_engine.insert_event("e1", "开会", timestamp="2026-01-01T00:00:00")
    record = experience_engine.add("先备份再升级")

    stats = process_outbox_once(event_engine, experience_engine, vector)

    assert stats == {"events": 1, "experiences": 1}
    assert vector.event_vectors["e1"] == "开会"
    assert vector.experience_vectors[record["exp_id"]] == "先备份再升级"
    assert _outbox(event_engine) == []
    assert _outbox(experience_engine) == []

    experience_engine.delete(record["exp_id"])
    process_outbox_once(event_engine, experience_engine, vector)

    assert record["exp_id"] in vector.deleted_experiences
    assert record["exp_id"] not in vector.experience_vectors


def test_reconcile_removes_orphans_and_backfills_missing(engines):
    """AC-6：对账清孤儿向量，并为缺失向量补投 upsert。"""
    event_engine, experience_engine = engines
    event_engine.insert_event("e1", "保留事件", timestamp="2026-01-01T00:00:00")
    record = experience_engine.add("只在 SQLite 的经验")
    with event_engine.conn:
        event_engine.conn.execute("DELETE FROM index_outbox")
    with experience_engine.conn:
        experience_engine.conn.execute("DELETE FROM index_outbox")

    vector = FakeVectorEngine(event_ids=["e1", "ghost"], experience_ids=[])
    stats = reconcile(event_engine, experience_engine, vector)

    assert stats["events"] == {"orphans": 1, "missing": 0}
    assert stats["experiences"] == {"orphans": 0, "missing": 1}
    assert vector.deleted_events == ["ghost"]
    assert ("e1", "upsert") not in _outbox(event_engine)
    assert _outbox(experience_engine) == [(record["exp_id"], "upsert")]
