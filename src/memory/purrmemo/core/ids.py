"""记忆子系统共享的 ID 生成（SPEC-012）。"""

from __future__ import annotations

import hashlib


def node_id_for(node_name: str) -> str:
    """由节点名称生成稳定的节点 ID。"""
    cleaned = node_name.strip().lower()
    return f"node_{hashlib.md5(cleaned.encode()).hexdigest()[:16]}"


def event_id_for(content: str) -> str:
    """由事件内容生成稳定的事件 ID。"""
    return f"evt_{hashlib.md5(content.encode()).hexdigest()}"


def experience_id_for(content: str) -> str:
    """由经验内容生成稳定的经验 ID。"""
    return f"exp_{hashlib.md5(content.encode()).hexdigest()}"


def edge_id_for(source_node_id: str, target_node_id: str, relation_meaning: str) -> str:
    """由三元组生成稳定的边 ID。"""
    key = f"{source_node_id}_{target_node_id}_{relation_meaning}"
    return hashlib.md5(key.encode()).hexdigest()
