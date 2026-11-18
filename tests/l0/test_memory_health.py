"""记忆系统健康检测与自动迁移（配置版本 / SQLite 结构 / FTS）。"""

from __future__ import annotations

import json
import sqlite3

from src.memory import health


def _paths(tmp_path):
    return {
        "memory_json": str(tmp_path / "memory.json"),
        "experiences_db": str(tmp_path / "experiences.db"),
        "events_db": str(tmp_path / "events.db"),
        "events_table": "events",
        "chroma_dir": str(tmp_path / "chromadb"),
        "graph": str(tmp_path / "graph.pkl"),
        "buffer": str(tmp_path / "buffer"),
    }


def _write_healthy_memory_json(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "event_retention_days": 30,
                "decay_half_life_days": 90,
                "_version": 1,
            },
            f,
        )


def _create_experiences_db(path):
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(
            "CREATE TABLE experiences (exp_id TEXT PRIMARY KEY, content TEXT NOT NULL,"
            " content_hash TEXT NOT NULL UNIQUE, problem TEXT, solution TEXT,"
            " confidence REAL NOT NULL, confidence_updated_at TEXT NOT NULL,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE experiences_fts USING fts5(exp_id UNINDEXED, tokens)"
        )
        conn.execute(
            "CREATE TABLE experience_events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " exp_id TEXT NOT NULL, action TEXT NOT NULL, old_confidence REAL,"
            " new_confidence REAL, snapshot TEXT, created_at TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE index_outbox (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO schema_meta VALUES ('version', '2')")
    conn.close()


def _create_events_db(path, rows=0):
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, content TEXT NOT NULL,"
            " timestamp TEXT NOT NULL, source TEXT)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE events_fts USING fts5(event_id UNINDEXED, content)"
        )
        conn.execute("CREATE TABLE index_outbox (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO schema_meta VALUES ('version', '2')")
        for index in range(rows):
            event_id = f"e{index}"
            conn.execute(
                "INSERT INTO events (event_id, content, timestamp) VALUES (?, ?, ?)",
                (event_id, "内容", "2026-01-01T00:00:00"),
            )
    conn.close()


def test_missing_memory_config_is_reported(tmp_path):
    report = health.inspect_memory(_paths(tmp_path))

    codes = [item["code"] for item in report["issues"]]
    assert codes == ["memory_config_missing"]
    assert report["ok"] is False


def test_healthy_memory_system_has_no_issues(tmp_path):
    paths = _paths(tmp_path)
    _write_healthy_memory_json(paths["memory_json"])
    _create_experiences_db(paths["experiences_db"])
    _create_events_db(paths["events_db"])

    report = health.inspect_memory(paths)

    assert report["ok"] is True
    assert report["issues"] == []
    assert report["version"] == 1
    assert report["schema_version"] == 2


def test_legacy_memory_config_is_migrated(tmp_path):
    paths = _paths(tmp_path)
    with open(paths["memory_json"], "w", encoding="utf-8") as f:
        json.dump(
            {
                "event_retention_days": 30,
                "search_top_k": 8,
                "min_experience_score": 0.4,
            },
            f,
        )

    before = health.inspect_memory(paths)
    assert any(item["code"] == "memory_config_legacy" for item in before["issues"])

    result = health.migrate_memory(paths)
    assert not any("配置迁移失败" in e for e in result["errors"])

    data = json.loads(open(paths["memory_json"], encoding="utf-8").read())
    assert data["event_retention_days"] == 30
    assert data["_version"] == 1
    assert "search_top_k" not in data
    assert "min_experience_score" not in data
    assert health.inspect_memory(paths)["config"]["status"] == "ok"


def test_outdated_experiences_db_is_migrated(tmp_path):
    paths = _paths(tmp_path)
    _write_healthy_memory_json(paths["memory_json"])
    conn = sqlite3.connect(paths["experiences_db"])
    with conn:
        conn.execute(
            "CREATE TABLE experiences (exp_id TEXT PRIMARY KEY, content TEXT NOT NULL,"
            " content_hash TEXT NOT NULL UNIQUE, kind TEXT, confidence REAL NOT NULL,"
            " confidence_updated_at TEXT NOT NULL, created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE experiences_fts (exp_id TEXT UNINDEXED, tokens TEXT)"
        )
        conn.execute(
            "INSERT INTO experiences VALUES ('e1', '经验内容', 'h1', 'old', 0.6,"
            " '2026-01-01', '2026-01-01', '2026-01-01')"
        )
    conn.close()

    before = health.inspect_memory(paths)
    assert any(
        item["code"] == "experiences_schema_outdated" for item in before["issues"]
    )

    result = health.migrate_memory(paths)
    assert not any("经验库迁移失败" in e for e in result["errors"])

    after = health.inspect_memory(paths)
    assert after["experiences_db"]["schema_version"] == 2
    assert after["experiences_db"]["missing_tables"] == []
    assert after["experiences_db"]["fts_in_sync"] is True
    assert result["experiences_db"]["rebuilt_fts"] == 1


def test_out_of_sync_event_fts_is_rebuilt(tmp_path):
    paths = _paths(tmp_path)
    _write_healthy_memory_json(paths["memory_json"])
    _create_events_db(paths["events_db"], rows=2)

    before = health.inspect_memory(paths)
    assert any(item["code"] == "events_fts_out_of_sync" for item in before["issues"])

    result = health.migrate_memory(paths)

    assert result["events_db"]["rebuilt_fts"] == 2
    assert health.inspect_memory(paths)["events_db"]["fts_in_sync"] is True
