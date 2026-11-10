"""图谱 pickle 文件的读写（SPEC-012）。"""

from __future__ import annotations

import pickle

import networkx as nx


def load_graph(path: str) -> nx.DiGraph:
    """从 ``path`` 加载图谱；文件损坏或缺失时由调用方兜底。"""
    with open(path, "rb") as f:
        return pickle.load(f)


def save_graph(path: str, graph: nx.DiGraph) -> None:
    """把图谱写入 ``path``。"""
    with open(path, "wb") as f:
        pickle.dump(graph, f)
