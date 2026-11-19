"""向量索引的模型版本标记与检测。

每个 Chroma collection 的 metadata 里记录生成向量时使用的模型 tag；
健康检查直接只读 ``chroma.sqlite3``，不额外启动 Chroma 客户端。
未带标记但已有向量的库视为旧模型产物（标记机制上线前的数据），需要重建。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from src.utils.embedding_manifest import MODEL_NAME, MODEL_TAG

INDEX_MODEL_KEY = "embedding_model"

# 状态：目录不存在 / 无向量 / 标记一致 / 标记缺失或为旧模型 / 数据库不可读
MISSING = "missing"
EMPTY = "empty"
CURRENT = "current"
STALE = "stale"
UNREADABLE = "unreadable"


def _open_ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)


def read_index_version(chroma_dir: str) -> dict:
    """只读检测向量库的模型版本；返回每个 collection 的标记与向量数。"""
    path = os.path.join(chroma_dir, "chroma.sqlite3")
    info = {
        "path": path,
        "exists": os.path.exists(path),
        "readable": True,
        "expected": MODEL_TAG,
        "model_name": MODEL_NAME,
        "collections": [],
        "models": [],
        "vectors": 0,
        "status": MISSING,
        "needs_rebuild": False,
    }
    if not info["exists"]:
        return info

    try:
        conn = _open_ro(path)
        try:
            rows = conn.execute(
                """
                SELECT c.name,
                       (SELECT m.str_value FROM collection_metadata m
                         WHERE m.collection_id = c.id AND m.key = ?
                         LIMIT 1),
                       (SELECT COUNT(*) FROM embeddings e
                         JOIN segments s ON e.segment_id = s.id
                        WHERE s.collection = c.id)
                  FROM collections c
                """,
                (INDEX_MODEL_KEY,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as error:
        info["readable"] = False
        info["error"] = str(error)
        info["status"] = UNREADABLE
        return info

    info["collections"] = [
        {"name": row[0], "model": row[1] or "", "vectors": row[2]} for row in rows
    ]
    info["models"] = sorted({row[1] for row in rows if row[1]})
    info["vectors"] = sum(row[2] for row in rows)

    if info["vectors"] == 0:
        info["status"] = EMPTY
        return info

    outdated = [
        item
        for item in info["collections"]
        if item["vectors"] and item["model"] != MODEL_TAG
    ]
    info["status"] = STALE if outdated else CURRENT
    info["needs_rebuild"] = info["status"] == STALE
    return info


def mark_index_model(vector_engine) -> list:
    """把当前模型 tag 写入三个 collection 的 metadata，返回成功的集合名。"""
    marked = []
    collections = (
        vector_engine.collection,
        vector_engine.events_collection,
        vector_engine.graph_collection,
    )
    for collection in collections:
        try:
            # hnsw:* 属于索引配置，创建后不允许改动；只写业务标记
            metadata = {
                key: value
                for key, value in (collection.metadata or {}).items()
                if not key.startswith("hnsw:")
            }
            metadata[INDEX_MODEL_KEY] = MODEL_TAG
            collection.modify(metadata=metadata)
            marked.append(collection.name)
        except Exception as error:
            print(f"写入向量模型标记失败（{collection.name}）: {error}")
    return marked
