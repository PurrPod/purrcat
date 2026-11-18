"""经验库 SQLite 事实源（SPEC-020）。

SQLite 保存经验正文、置信度与证据日志；Chroma 仅作为向量索引，
两者通过同库 ``index_outbox`` 与索引器保持最终一致。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

from src.memory.config import EXPERIENCES_DB_PATH

from ..clock import now_iso
from ..filters import build_fts_query, build_fts_query_or, tokenize_for_fts
from ..ids import content_hash_for, experience_id_for
from ..scoring import effective_confidence
from ..schema import NEW_EXPERIENCE_CONFIDENCE, REINFORCE_INCREMENT
from .outbox import enqueue, ensure_outbox

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS experiences (
    exp_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    problem TEXT,
    solution TEXT,
    confidence REAL NOT NULL,
    confidence_updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts USING fts5(
    exp_id UNINDEXED,
    tokens,
    tokenize='unicode61'
)
"""

_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS experience_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exp_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_confidence REAL,
    new_confidence REAL,
    snapshot TEXT,
    created_at TEXT NOT NULL
)
"""

_META_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


class ExperienceEngine:
    """经验的增删改查、证据日志与 FTS 检索。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path if db_path is not None else EXPERIENCES_DB_PATH
        self._lock = threading.RLock()
        self.conn = None
        self._init_db()

    def _init_db(self) -> None:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        with self.conn:
            self.conn.execute(_TABLE_DDL)
            self.conn.execute(_FTS_DDL)
            self.conn.execute(_EVENTS_DDL)
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_experience_events_exp"
                " ON experience_events (exp_id)"
            )
            self.conn.execute(_META_DDL)
            ensure_outbox(self.conn)
            # v2 早期版本存过 kind，现已废弃；老库顺手删列
            columns = {
                row[1] for row in self.conn.execute("PRAGMA table_info(experiences)")
            }
            if "kind" in columns:
                self.conn.execute("ALTER TABLE experiences DROP COLUMN kind")
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')"
            )

    # ── 读 ──
    def _effective(self, row) -> float:
        from src.memory.settings import get_memory_settings

        return effective_confidence(
            row["confidence"],
            row["confidence_updated_at"],
            half_life_days=get_memory_settings()["decay_half_life_days"],
        )

    def _row_to_record(self, row) -> dict:
        return {
            "exp_id": row["exp_id"],
            "content": row["content"],
            "confidence": self._effective(row),
            "base_confidence": row["confidence"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "timestamp": row["created_at"],
        }

    def get(self, exp_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM experiences WHERE exp_id = ?", (exp_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_many(self, exp_ids) -> list[dict]:
        """按入参顺序返回存在的记录，不存在的 id 直接丢弃。"""
        ids = list(dict.fromkeys(exp_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM experiences WHERE exp_id IN ({placeholders})", ids
            ).fetchall()
        by_id = {row["exp_id"]: self._row_to_record(row) for row in rows}
        return [by_id[exp_id] for exp_id in ids if exp_id in by_id]

    def list_recent(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM experiences ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_existing_ids(self) -> list[str]:
        with self._lock:
            rows = self.conn.execute("SELECT exp_id FROM experiences").fetchall()
        return [row[0] for row in rows]

    def count(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]

    # ── 写 ──
    def _write_fts(self, conn, exp_id: str, content: str) -> None:
        conn.execute("DELETE FROM experiences_fts WHERE exp_id = ?", (exp_id,))
        conn.execute(
            "INSERT INTO experiences_fts (exp_id, tokens) VALUES (?, ?)",
            (exp_id, tokenize_for_fts(content)),
        )

    def _write_event(
        self,
        conn,
        exp_id: str,
        action: str,
        old_confidence,
        new_confidence,
        snapshot=None,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO experience_events
                (exp_id, action, old_confidence, new_confidence, snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                exp_id,
                action,
                old_confidence,
                new_confidence,
                json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
                now_iso(),
            ),
        )
        return cursor.lastrowid

    def add(self, content: str, timestamp: str | None = None):
        """新增经验；``content_hash`` 已存在时只刷新衰减锚点。"""
        content = (content or "").strip()
        if not content:
            raise ValueError("经验内容不能为空")

        content_hash = content_hash_for(content)
        created_at = timestamp or now_iso()
        anchor = now_iso()

        with self._lock:
            with self.conn:
                existing = self.conn.execute(
                    "SELECT * FROM experiences WHERE content_hash = ?", (content_hash,)
                ).fetchone()
                if existing:
                    old_effective = self._effective(existing)
                    self.conn.execute(
                        """
                        UPDATE experiences
                        SET confidence_updated_at = ?, updated_at = ?
                        WHERE exp_id = ?
                        """,
                        (anchor, anchor, existing["exp_id"]),
                    )
                    self._write_event(
                        self.conn,
                        existing["exp_id"],
                        "reinforce",
                        old_effective,
                        existing["confidence"],
                    )
                    record = self.get(existing["exp_id"])
                    return {**record, "is_new": False}

                exp_id = experience_id_for(content)
                self.conn.execute(
                    """
                    INSERT INTO experiences
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
                self._write_fts(self.conn, exp_id, content)
                self._write_event(
                    self.conn, exp_id, "add", None, NEW_EXPERIENCE_CONFIDENCE
                )
                enqueue(self.conn, exp_id, "upsert")
                record = self.get(exp_id)
                return {**record, "is_new": True}

    def reinforce(self, exp_id: str) -> dict | None:
        """按当前有效值 +0.2，并刷新锚点。"""
        with self._lock:
            with self.conn:
                row = self.conn.execute(
                    "SELECT * FROM experiences WHERE exp_id = ?", (exp_id,)
                ).fetchone()
                if not row:
                    return None
                old_effective = self._effective(row)
                new_base = min(1.0, old_effective + REINFORCE_INCREMENT)
                anchor = now_iso()
                self.conn.execute(
                    """
                    UPDATE experiences
                    SET confidence = ?, confidence_updated_at = ?, updated_at = ?
                    WHERE exp_id = ?
                    """,
                    (new_base, anchor, anchor, exp_id),
                )
                self._write_event(
                    self.conn, exp_id, "reinforce", old_effective, new_base
                )
        return {
            "exp_id": exp_id,
            "old_confidence": old_effective,
            "new_confidence": new_base,
        }

    def replace(self, exp_id: str, content: str) -> dict | None:
        """覆盖内容并重置置信度为 1.0，``exp_id`` 保持不变。"""
        content = (content or "").strip()
        if not content:
            raise ValueError("经验内容不能为空")
        new_hash = content_hash_for(content)

        with self._lock:
            with self.conn:
                row = self.conn.execute(
                    "SELECT * FROM experiences WHERE exp_id = ?", (exp_id,)
                ).fetchone()
                if not row:
                    return None
                conflict = self.conn.execute(
                    "SELECT exp_id FROM experiences WHERE content_hash = ?",
                    (new_hash,),
                ).fetchone()
                if conflict and conflict["exp_id"] != exp_id:
                    raise ValueError("相同内容已存在于另一条经验")

                snapshot = dict(row)
                old_effective = self._effective(row)
                anchor = now_iso()
                self.conn.execute(
                    """
                    UPDATE experiences
                    SET content = ?, content_hash = ?, confidence = 1.0,
                        confidence_updated_at = ?, updated_at = ?
                    WHERE exp_id = ?
                    """,
                    (content, new_hash, anchor, anchor, exp_id),
                )
                self._write_fts(self.conn, exp_id, content)
                self._write_event(
                    self.conn, exp_id, "replace", old_effective, 1.0, snapshot
                )
                enqueue(self.conn, exp_id, "upsert")
        return self.get(exp_id)

    def delete(self, exp_id: str) -> dict | None:
        """硬删除主表与 FTS，并写入可恢复快照。"""
        with self._lock:
            with self.conn:
                row = self.conn.execute(
                    "SELECT * FROM experiences WHERE exp_id = ?", (exp_id,)
                ).fetchone()
                if not row:
                    return None
                snapshot = dict(row)
                self.conn.execute(
                    "DELETE FROM experiences_fts WHERE exp_id = ?", (exp_id,)
                )
                self.conn.execute(
                    "DELETE FROM experiences WHERE exp_id = ?", (exp_id,)
                )
                self._write_event(
                    self.conn,
                    exp_id,
                    "delete",
                    self._effective(row),
                    None,
                    snapshot,
                )
                enqueue(self.conn, exp_id, "delete")
        return snapshot

    def restore(self, event_id: int) -> dict | None:
        """从 delete 事件快照恢复一条经验。"""
        with self._lock:
            with self.conn:
                event = self.conn.execute(
                    "SELECT * FROM experience_events WHERE id = ?", (event_id,)
                ).fetchone()
                if not event or not event["snapshot"]:
                    return None
                snapshot = json.loads(event["snapshot"])
                now = now_iso()
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO experiences
                        (exp_id, content, content_hash, problem, solution,
                         confidence, confidence_updated_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot["exp_id"],
                        snapshot["content"],
                        snapshot["content_hash"],
                        snapshot.get("problem"),
                        snapshot.get("solution"),
                        snapshot.get("confidence", NEW_EXPERIENCE_CONFIDENCE),
                        now,
                        snapshot.get("created_at", now),
                        now,
                    ),
                )
                self._write_fts(self.conn, snapshot["exp_id"], snapshot["content"])
                enqueue(self.conn, snapshot["exp_id"], "upsert")
                self._write_event(
                    self.conn,
                    snapshot["exp_id"],
                    "restore",
                    None,
                    snapshot.get("confidence"),
                )
        return self.get(snapshot["exp_id"])

    def get_event(self, event_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM experience_events WHERE id = ?", (event_id,)
            ).fetchone()
        return dict(row) if row else None

    # ── 检索 ──
    def _run_fts(self, query_str: str, limit: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT e.exp_id, e.content, f.rank
            FROM experiences_fts f
            JOIN experiences e ON f.exp_id = e.exp_id
            WHERE experiences_fts MATCH ?
            ORDER BY f.rank
            LIMIT ?
            """,
            (query_str, limit),
        ).fetchall()
        return [
            {"id": row[0], "content": row[1], "score": abs(row[2])} for row in rows
        ]

    def search_bm25(self, query: str, limit: int = 50) -> list[dict]:
        """FTS5 检索；AND 零结果时用 OR 降级重试一次。"""
        and_query = build_fts_query(query)
        if not and_query:
            return []
        with self._lock:
            hits = self._run_fts(and_query, limit)
            if hits:
                return hits
            or_query = build_fts_query_or(query)
            if or_query and or_query != and_query:
                return self._run_fts(or_query, limit)
        return []

    def close(self) -> None:
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None
