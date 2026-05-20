"""
系统长短期记忆与知识图谱管理器
"""

from .purrmemo.client import get_memory_client

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
    return _get_memory_client().get_recent_events(limit=limit)


def get_recent_experiences(limit: int = 30):
    """获取最近的经验（从向量库）"""
    return _get_memory_client().get_recent_experiences(limit=limit)


def visualize_graph(output_file=None):
    """生成图谱可视化 HTML 文件"""
    return _get_memory_client().visualize_graph(output_file=output_file)


__all__ = [
    "init_memory",
    "search_memory",
    "add_memory",
    "get_memory_graph",
    "get_recent_events",
    "get_recent_experiences",
    "visualize_graph",
]
