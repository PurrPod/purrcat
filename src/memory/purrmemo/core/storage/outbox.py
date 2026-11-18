"""SQLite 索引 outbox：在同一事务内登记 Chroma 待同步操作（SPEC-020）。"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..clock import now_iso

# 失败重试的最大退避秒数
MAX_BACKOFF_SECONDS = 300

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS index_outbox (
    memory_id TEXT PRIMARY KEY,
    op TEXT NOT NULL CHECK(op IN ('upsert', 'delete')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def ensure_outbox(conn) -> None:
    """建 outbox 表；调用方负责事务与提交。"""
    conn.execute(OUTBOX_DDL)


def enqueue(conn, memory_id: str, op: str, now: str | None = None) -> None:
    """登记或覆盖一条待同步操作（同一 memory_id 只保留最后一次意图）。"""
    ts = now or now_iso()
    conn.execute(
        """
        INSERT INTO index_outbox
            (memory_id, op, attempts, next_retry_at, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?, ?)
        ON CONFLICT(memory_id) DO UPDATE SET
            op = excluded.op,
            next_retry_at = excluded.next_retry_at,
            updated_at = excluded.updated_at
        """,
        (memory_id, op, ts, ts, ts),
    )


def fetch_pending(conn, limit: int = 100, now: str | None = None) -> list[dict]:
    """取出到了重试时间的待同步操作。"""
    ts = now or now_iso()
    rows = conn.execute(
        """
        SELECT memory_id, op, attempts
        FROM index_outbox
        WHERE next_retry_at <= ?
        ORDER BY created_at
        LIMIT ?
        """,
        (ts, limit),
    ).fetchall()
    return [
        {"memory_id": row[0], "op": row[1], "attempts": row[2]} for row in rows
    ]


def remove(conn, memory_id: str) -> None:
    """同步成功后删除登记行。"""
    conn.execute("DELETE FROM index_outbox WHERE memory_id = ?", (memory_id,))


def backoff(conn, memory_id: str, attempts: int) -> None:
    """失败后累计次数并指数退避，上限 ``MAX_BACKOFF_SECONDS``。"""
    delay = min(MAX_BACKOFF_SECONDS, 2 ** min(attempts, 8))
    next_retry = (datetime.now() + timedelta(seconds=delay)).isoformat()
    conn.execute(
        """
        UPDATE index_outbox
        SET attempts = ?, next_retry_at = ?, updated_at = ?
        WHERE memory_id = ?
        """,
        (attempts, next_retry, now_iso(), memory_id),
    )
