"""
系统长短期记忆与知识图谱管理器
"""

from .purrmemo.client import get_memory_client
from .purrmemo.core.storage.event_engine import EventEngine
from .purrmemo.core.storage.vector_engine import VectorEngine

_memory_client = None


def _get_memory_client():
    global _memory_client
    if _memory_client is None:
        _memory_client = get_memory_client()
    return _memory_client


def init_memory():
    return _get_memory_client().init()


def search_memory(query: str = "", filters: dict = None):
    return _get_memory_client().search(query=query, filters=filters)


def add_memory(memo_data: dict) -> str:
    return _get_memory_client().add_memory(memo_data)


def get_memory_graph():
    return _get_memory_client().get_graph()


def get_recent_events(limit: int = 30):
    """获取最近的事件（从事件库）"""
    try:
        engine = EventEngine()
        return engine.get_events(limit=limit)
    except Exception:
        return []


def get_recent_experiences(limit: int = 30):
    """获取最近的经验（从向量库）"""
    try:
        engine = VectorEngine()
        if not engine.collection:
            return []
        results = engine.collection.get(include=["documents", "metadatas"])
        experiences = []
        if results and results.get("ids"):
            for i in range(len(results["ids"])):
                meta = results["metadatas"][i] or {}
                experiences.append({
                    "exp_id": results["ids"][i],
                    "content": results["documents"][i],
                    "timestamp": meta.get("timestamp", "")
                })
        experiences.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return experiences[:limit]
    except Exception:
        return []


__all__ = [
    "init_memory",
    "search_memory",
    "add_memory",
    "get_memory_graph",
    "get_recent_events",
    "get_recent_experiences",
]
