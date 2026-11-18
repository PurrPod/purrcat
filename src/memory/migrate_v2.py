"""记忆系统 v2 迁移：Chroma 经验回填 SQLite、重建中文 FTS、清理孤儿事件向量。

用法：
    python -m src.memory.migrate_v2 --dry-run
    python -m src.memory.migrate_v2
"""

from __future__ import annotations

import argparse
import json

from .purrmemo.core.clock import now_iso
from .purrmemo.core.filters import tokenize_for_fts
from .purrmemo.core.ids import content_hash_for
from .purrmemo.core.schema import NEW_EXPERIENCE_CONFIDENCE


def _read_chroma_experiences(vector_engine, batch: int = 500):
    """分页读取 Chroma 中的全部经验。"""
    collection = vector_engine.collection
    total = collection.count()
    records = []
    offset = 0
    while offset < total:
        result = collection.get(
            limit=batch, offset=offset, include=["documents", "metadatas"]
        )
        ids = result.get("ids") or []
        if not ids:
            break
        documents = result.get("documents") or [""] * len(ids)
        metadatas = result.get("metadatas") or [{} for _ in ids]
        for index, exp_id in enumerate(ids):
            records.append(
                (
                    exp_id,
                    documents[index] or "",
                    metadatas[index] or {},
                )
            )
        offset += len(ids)
    return records


def _backfill_experiences(experience_engine, records, dry_run: bool) -> int:
    """把 Chroma 经验写入 SQLite；已存在则跳过（幂等）。"""
    if dry_run:
        existing = set(experience_engine.list_existing_ids())
        return sum(1 for exp_id, _, _ in records if exp_id not in existing)

    anchor = now_iso()
    inserted = 0
    conn = experience_engine.conn
    with conn:
        for exp_id, content, metadata in records:
            content = (content or "").strip()
            if not exp_id or not content:
                continue
            content_hash = metadata.get("content_hash") or content_hash_for(content)
            created_at = metadata.get("timestamp") or anchor
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO experiences
                    (exp_id, content, content_hash, confidence,
                     confidence_updated_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exp_id,
                    content,
                    content_hash,
                    NEW_EXPERIENCE_CONFIDENCE,
                    anchor,
                    created_at,
                    anchor,
                ),
            )
            inserted += cursor.rowcount
    return inserted


def _rebuild_experience_fts(experience_engine, dry_run: bool) -> int:
    rows = experience_engine.conn.execute(
        "SELECT exp_id, content FROM experiences"
    ).fetchall()
    if dry_run:
        return len(rows)
    with experience_engine.conn:
        experience_engine.conn.execute("DELETE FROM experiences_fts")
        for exp_id, content in rows:
            experience_engine.conn.execute(
                "INSERT INTO experiences_fts (exp_id, tokens) VALUES (?, ?)",
                (exp_id, tokenize_for_fts(content)),
            )
    return len(rows)


def _rebuild_event_fts(event_engine, dry_run: bool) -> int:
    table = event_engine.table_name
    rows = event_engine.conn.execute(
        f"SELECT event_id, content FROM {table}"
    ).fetchall()
    if dry_run:
        return len(rows)
    conn = event_engine.conn
    with conn:
        conn.execute(f"DELETE FROM {table}_fts")
        for event_id, content in rows:
            conn.execute(
                f"INSERT INTO {table}_fts (event_id, content) VALUES (?, ?)",
                (event_id, tokenize_for_fts(content)),
            )
    return len(rows)


def _clean_orphan_events(event_engine, vector_engine, dry_run: bool) -> list[str]:
    sqlite_ids = set(event_engine.list_existing_ids())
    orphans = [
        event_id
        for event_id in vector_engine.list_event_ids()
        if event_id not in sqlite_ids
    ]
    if orphans and not dry_run:
        vector_engine.delete_event_vectors(orphans)
    return orphans


def _clean_orphan_experiences(
    experience_engine, vector_engine, dry_run: bool, expected_ids=None
) -> list[str]:
    """清理 SQLite 中不存在的经验向量（被跳过或重复的内容）。"""
    sqlite_ids = set(experience_engine.list_existing_ids())
    if expected_ids:
        sqlite_ids |= set(expected_ids)
    orphans = [
        exp_id
        for exp_id in vector_engine.list_experience_ids()
        if exp_id not in sqlite_ids
    ]
    if orphans and not dry_run:
        for exp_id in orphans:
            vector_engine.delete_experience(exp_id)
    return orphans


def migrate(vector_engine, experience_engine, event_engine, dry_run: bool = False) -> dict:
    """执行迁移；返回统计信息。"""
    records = _read_chroma_experiences(vector_engine)
    orphans = _clean_orphan_events(event_engine, vector_engine, dry_run)
    inserted = _backfill_experiences(experience_engine, records, dry_run)
    orphan_experiences = _clean_orphan_experiences(
        experience_engine,
        vector_engine,
        dry_run,
        expected_ids=[exp_id for exp_id, _, _ in records],
    )
    experience_fts = _rebuild_experience_fts(experience_engine, dry_run)
    event_fts = _rebuild_event_fts(event_engine, dry_run)

    if not dry_run:
        with experience_engine.conn:
            experience_engine.conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')"
            )

    return {
        "dry_run": dry_run,
        "chroma_experiences": len(records),
        "inserted_experiences": inserted,
        "experience_fts_rows": experience_fts,
        "event_fts_rows": event_fts,
        "orphan_event_vectors": len(orphans),
        "orphan_event_ids": orphans,
        "orphan_experience_vectors": len(orphan_experiences),
        "orphan_experience_ids": orphan_experiences,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="记忆系统 v2 迁移")
    parser.add_argument(
        "--dry-run", action="store_true", help="只统计，不写入任何数据"
    )
    args = parser.parse_args(argv)

    from .purrmemo.core.storage.event_engine import EventEngine
    from .purrmemo.core.storage.experience_engine import ExperienceEngine
    from .purrmemo.core.storage.vector_engine import VectorEngine

    stats = migrate(
        VectorEngine(), ExperienceEngine(), EventEngine(), dry_run=args.dry_run
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
