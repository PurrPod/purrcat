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
    """获取最近的经验（从经验库）"""
    return _get_memory_client().get_recent_experiences(limit=limit)


def _experience_engine():
    engine = getattr(_get_memory_client().search_tool, "experience_engine", None)
    if engine is None:
        raise RuntimeError("经验库不可用")
    return engine


def reinforce_experience(experience_id: str):
    """提升一条经验的置信度（+0.2）。"""
    return _experience_engine().reinforce(experience_id)


def replace_experience(experience_id: str, content: str):
    """覆盖经验内容并重置置信度。"""
    return _experience_engine().replace(experience_id, content)


def delete_experience(experience_id: str):
    """硬删除一条经验（保留可恢复快照）。"""
    return _experience_engine().delete(experience_id)


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
    "reinforce_experience",
    "replace_experience",
    "delete_experience",
    "visualize_graph",
]
