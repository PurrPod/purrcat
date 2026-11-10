"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_graph_guide


def generate_graph_guide(name: str, goal: str = "") -> str:
    return build_graph_guide(name, goal)
