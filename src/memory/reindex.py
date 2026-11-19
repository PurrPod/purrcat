"""按当前嵌入模型全量重建记忆向量库。

事实源不动：事件在 ``events.db``、经验在 ``experiences.db``、图谱结构在
``graph.pkl``，这里只清空并重写 Chroma 里的三个向量 collection。
用于嵌入模型更换后（旧向量的维度或语义空间已不兼容）的一次性重建。
"""

from __future__ import annotations

import time

from src.utils.embedding_manifest import MODEL_NAME, MODEL_TAG


def rebuild_vector_index(
    vector_engine=None,
    event_engine=None,
    experience_engine=None,
    graph_engine=None,
    log=None,
) -> dict:
    """重建事件 / 经验 / 图谱节点三组向量，并写入模型版本标记。"""
    from .purrmemo.core.storage.event_engine import EventEngine
    from .purrmemo.core.storage.experience_engine import ExperienceEngine
    from .purrmemo.core.storage.graph_engine import GraphEngine
    from .purrmemo.core.storage.vector_engine import VectorEngine

    log = log or print
    started = time.perf_counter()

    vector_engine = vector_engine or VectorEngine()
    event_engine = event_engine or EventEngine()
    experience_engine = experience_engine or ExperienceEngine()
    graph_engine = graph_engine or GraphEngine(vector_engine=vector_engine)

    # 先加载编码器：模型缺失时直接失败，不破坏现有向量
    vector_engine.embedding_model

    events = [
        {
            "id": item["event_id"],
            "content": item["content"],
            "timestamp": item.get("timestamp"),
        }
        for item in event_engine.list_events()
        if item.get("event_id") and item.get("content")
    ]
    experiences = experience_engine.list_all()
    nodes = graph_engine.list_nodes()
    log(
        f"待重建：事件 {len(events)} / 经验 {len(experiences)} / "
        f"图谱节点 {len(nodes)}（{MODEL_NAME}）"
    )

    vector_engine.reset_collections()
    counts = {
        "events": vector_engine.rebuild_event_vectors(events),
        "experiences": vector_engine.rebuild_experience_vectors(experiences),
        "graph_nodes": vector_engine.rebuild_graph_vectors(nodes),
    }
    marked = vector_engine.mark_index_model()

    elapsed = round(time.perf_counter() - started, 2)
    log(f"重建完成：{counts}，用时 {elapsed}s")
    return {
        "model": MODEL_TAG,
        "counts": counts,
        "marked_collections": marked,
        "elapsed_seconds": elapsed,
    }
