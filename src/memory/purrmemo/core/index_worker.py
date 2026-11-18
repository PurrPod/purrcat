"""SQLite → Chroma 的索引同步与对账（SPEC-020）。"""

from __future__ import annotations

from .storage.outbox import backoff, enqueue, fetch_pending, remove


def _apply_event(vector_engine, event_engine, memory_id, op):
    if op == "delete":
        return bool(vector_engine.delete_event_vectors([memory_id]))
    event = event_engine.get_event_by_id(memory_id)
    if not event:
        # 主表已不存在，按删除处理
        return bool(vector_engine.delete_event_vectors([memory_id]))
    return bool(
        vector_engine.insert_event_vector(
            memory_id, event["content"], event.get("timestamp")
        )
    )


def _apply_experience(vector_engine, experience_engine, memory_id, op):
    if op == "delete":
        return bool(vector_engine.delete_experience(memory_id))
    record = experience_engine.get(memory_id)
    if not record:
        return bool(vector_engine.delete_experience(memory_id))
    return bool(
        vector_engine.insert_experience(
            memory_id, record["content"], timestamp=record.get("created_at")
        )
    )


def _drain(conn, rows, handler):
    synced = 0
    for row in rows:
        memory_id = row["memory_id"]
        try:
            ok = handler(memory_id, row["op"])
        except Exception as exc:  # 索引失败不阻塞主流程，交给退避重试
            print(f"❌ [IndexWorker] 同步 {memory_id} 失败: {exc}")
            ok = False

        if ok:
            with conn:
                remove(conn, memory_id)
            synced += 1
        else:
            with conn:
                backoff(conn, memory_id, row["attempts"] + 1)
    return synced


def process_outbox_once(
    event_engine, experience_engine, vector_engine, limit: int = 100
) -> dict:
    """处理两个库的 outbox；返回各自同步成功的条数。"""
    if vector_engine is None:
        return {"events": 0, "experiences": 0}

    event_rows = fetch_pending(event_engine.conn, limit=limit)
    experience_rows = fetch_pending(experience_engine.conn, limit=limit)

    events = _drain(
        event_engine.conn,
        event_rows,
        lambda memory_id, op: _apply_event(
            vector_engine, event_engine, memory_id, op
        ),
    )
    experiences = _drain(
        experience_engine.conn,
        experience_rows,
        lambda memory_id, op: _apply_experience(
            vector_engine, experience_engine, memory_id, op
        ),
    )
    return {"events": events, "experiences": experiences}


def _reconcile_one(conn, sqlite_ids, vector_ids, delete_vectors) -> dict:
    sqlite_set = set(sqlite_ids)
    vector_set = set(vector_ids)

    orphan_ids = [record_id for record_id in vector_set if record_id not in sqlite_set]
    if orphan_ids:
        delete_vectors(orphan_ids)

    missing_ids = [record_id for record_id in sqlite_set if record_id not in vector_set]
    if missing_ids:
        with conn:
            for record_id in missing_ids:
                enqueue(conn, record_id, "upsert")

    return {"orphans": len(orphan_ids), "missing": len(missing_ids)}


def reconcile(event_engine, experience_engine, vector_engine) -> dict:
    """启动/每日对账：清孤儿向量，为缺失向量补投 upsert。"""
    if vector_engine is None:
        return {"events": {}, "experiences": {}}

    event_stats = _reconcile_one(
        event_engine.conn,
        event_engine.list_existing_ids(),
        vector_engine.list_event_ids(),
        vector_engine.delete_event_vectors,
    )
    experience_stats = _reconcile_one(
        experience_engine.conn,
        experience_engine.list_existing_ids(),
        vector_engine.list_experience_ids(),
        lambda ids: [vector_engine.delete_experience(record_id) for record_id in ids],
    )
    return {"events": event_stats, "experiences": experience_stats}
