"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_sensor_guide


def generate_sensor_guide(sensor_name: str, goal: str = "") -> str:
    return build_sensor_guide(sensor_name, goal)
