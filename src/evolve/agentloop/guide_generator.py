"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_agentloop_guide


def generate_agentloop_guide(name: str, goal: str = "") -> str:
    return build_agentloop_guide(name, goal)
