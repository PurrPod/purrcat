"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_skill_guide


def generate_skill_guide(skill_name: str, goal: str = "") -> str:
    return build_skill_guide(skill_name, goal)
