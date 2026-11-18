"""经验库 SQLite 事实源的生命周期（SPEC-020 AC-1~AC-4）。"""

from __future__ import annotations

import pytest

from src.memory.purrmemo.core.ids import experience_id_for
from src.memory.purrmemo.core.storage.experience_engine import ExperienceEngine


@pytest.fixture()
def engine(tmp_path):
    instance = ExperienceEngine(db_path=str(tmp_path / "experiences.db"))
    yield instance
    instance.close()


def _outbox_ops(engine, exp_id):
    return [
        row[0]
        for row in engine.conn.execute(
            "SELECT op FROM index_outbox WHERE memory_id = ?", (exp_id,)
        ).fetchall()
    ]


def test_add_persists_record_and_upsert(engine):
    """AC-1：新经验置信度 0.6，并登记一次向量 upsert。"""
    record = engine.add("先检查网络再重启服务")

    assert record["is_new"] is True
    assert record["exp_id"] == experience_id_for("先检查网络再重启服务")
    assert record["confidence"] == pytest.approx(0.6)
    assert engine.count() == 1
    assert _outbox_ops(engine, record["exp_id"]) == ["upsert"]


def test_duplicate_add_refreshes_anchor_only(engine):
    """AC-1：相同内容不产生第二条记录。"""
    first = engine.add("先检查网络")
    second = engine.add("先检查网络")

    assert second["is_new"] is False
    assert second["exp_id"] == first["exp_id"]
    assert engine.count() == 1


def test_reinforce_caps_at_one(engine):
    """AC-2：reinforce 每次 +0.2，上限 1.0。"""
    record = engine.add("经验 A")

    result = engine.reinforce(record["exp_id"])
    assert result["old_confidence"] == pytest.approx(0.6)
    assert result["new_confidence"] == pytest.approx(0.8)

    engine.reinforce(record["exp_id"])
    engine.reinforce(record["exp_id"])
    assert engine.get(record["exp_id"])["confidence"] == pytest.approx(1.0)
    assert engine.reinforce("exp_missing") is None


def test_replace_resets_confidence_and_updates_fts(engine):
    """AC-3：replace 保持 exp_id、重置置信度并更新检索内容。"""
    record = engine.add("旧的经验做法")
    exp_id = record["exp_id"]

    replaced = engine.replace(exp_id, "新的部署检查清单")

    assert replaced["exp_id"] == exp_id
    assert replaced["confidence"] == pytest.approx(1.0)
    assert all(
        hit["content"] != "旧的经验做法" for hit in engine.search_bm25("旧的经验做法")
    )
    assert [hit["id"] for hit in engine.search_bm25("部署检查清单")] == [exp_id]


def test_replace_rejects_duplicate_content(engine):
    """AC-3：覆盖为另一条已存在的内容时拒绝。"""
    first = engine.add("经验一")
    engine.add("经验二")

    with pytest.raises(ValueError):
        engine.replace(first["exp_id"], "经验二")


def test_delete_is_hard_and_restorable(engine):
    """AC-4：删除写快照与 outbox，restore 能从事件恢复。"""
    record = engine.add("可以恢复的经验")
    exp_id = record["exp_id"]

    snapshot = engine.delete(exp_id)
    assert snapshot["exp_id"] == exp_id
    assert engine.get(exp_id) is None
    assert engine.search_bm25("可以恢复的经验") == []
    assert _outbox_ops(engine, exp_id) == ["delete"]

    event = engine.conn.execute(
        "SELECT id FROM experience_events WHERE exp_id = ? AND action = 'delete'",
        (exp_id,),
    ).fetchone()
    restored = engine.restore(event[0])

    assert restored["exp_id"] == exp_id
    assert engine.get(exp_id) is not None
    assert [hit["id"] for hit in engine.search_bm25("可以恢复的经验")] == [exp_id]
    assert _outbox_ops(engine, exp_id) == ["upsert"]


def test_search_bm25_supports_chinese_query(engine):
    """AC-7：中文查询经 jieba 分词后能命中。"""
    record = engine.add("路径包含空格时启动会失败，应该加引号")

    hits = engine.search_bm25("路径 启动失败")

    assert [hit["id"] for hit in hits] == [record["exp_id"]]


def test_effective_confidence_decays_but_never_deletes(engine):
    """AC-10：90 天后衰减到下限，但记录仍保留。"""
    record = engine.add("很久以前的经验")
    engine.conn.execute(
        "UPDATE experiences SET confidence_updated_at = '2020-01-01T00:00:00'"
        " WHERE exp_id = ?",
        (record["exp_id"],),
    )
    engine.conn.commit()

    assert engine.get(record["exp_id"])["confidence"] == pytest.approx(0.3)
    assert engine.count() == 1
