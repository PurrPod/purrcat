"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_ui_plugin_guide


def generate_ui_plugin_guide(
    plugin_id: str, plugin_name: str, area: str, plugin_dir: str, goal: str = ""
) -> str:
    return build_ui_plugin_guide(plugin_id, plugin_name, area, plugin_dir, goal)
