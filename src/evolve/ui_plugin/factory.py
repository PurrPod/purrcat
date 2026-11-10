"""UI 插件工厂：在 AgentVM 沙盒里生成 web-minimal 插件的文件框架。

与 Skill / MCP / Sensor 工厂不同，UI 插件不需要 UUID 工作区与 Git 流程：
宿主（src/server/api/webmin.py）把 ``AGENT_VM_DIR/ui-plugin/*`` 直接当作一个插件根目录
扫描，所以这里写下的文件就是"已安装的插件"，改完让用户刷新页面即可看到。
"""

import html
import json
import os
import re

from src.evolve.ui_plugin.guide_generator import generate_ui_plugin_guide
from src.evolve.ui_plugin.templates import INDEX_HTML_TPL
from src.utils.config import AGENT_VM_DIR

UI_PLUGIN_DIR = os.path.join(AGENT_VM_DIR, "ui-plugin")

# 生成时的默认区域：panel 只是"不改就能跑"的保守起点，
# 要入驻其它区域（sidebar / session / pet / popup ...）直接改 plugin.json 的 slot.area 即可。
DEFAULT_AREA = "panel"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _plugin_json(plugin_id: str, name: str, area: str, goal: str) -> str:
    doc = {
        "id": plugin_id,
        "name": name,
        "description": goal or f"{name}（极简模式 UI 插件）",
        "icon": "panel-left",
        "slot": {"area": area},
        "entry": "index.html",
        "configSchema": [
            {"key": "title", "label": "标题", "type": "text", "default": name},
            {"key": "compact", "label": "紧凑模式", "type": "switch", "default": False},
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def ui_plugin_init(
    target: str, name: str = "", goal: str = ""
) -> tuple[str, str | None]:
    """生成 UI 插件文件框架。

    Args:
        target: 插件 id（目录名，也是 plugin.json 的 id）
        name:   显示名，缺省用插件 id
        goal:   本次开发目标，写进插件描述与指南

    Returns:
        (给 Agent 的说明文本, 插件目录绝对路径)；参数非法/目录已存在时目录为 None。
    """
    plugin_id = (target or "").strip()
    if not _ID_RE.match(plugin_id):
        return (
            "❌ 插件 id 非法：只能用小写字母、数字、'-'、'_'，且以字母或数字开头"
            f"（当前为 {target!r}）。换个名字再来。",
            None,
        )

    plugin_name = (name or "").strip() or plugin_id
    plugin_dir = os.path.join(UI_PLUGIN_DIR, plugin_id)
    if os.path.exists(plugin_dir):
        return (
            f"❌ 目标目录已存在：{plugin_dir}\n"
            "同一 id 只能有一份框架；要改代码请直接编辑它，要重建请先删掉整个目录。",
            None,
        )

    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
        f.write(_plugin_json(plugin_id, plugin_name, DEFAULT_AREA, goal))
    index_html = (
        INDEX_HTML_TPL.replace("__ID_JSON__", json.dumps(plugin_id))
        .replace("__NAME_JS__", plugin_name.replace("\\", "\\\\").replace("'", "\\'"))
        .replace("__NAME__", html.escape(plugin_name))
        .replace("__ID__", html.escape(plugin_id))
    )
    with open(os.path.join(plugin_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    guide = generate_ui_plugin_guide(
        plugin_id, plugin_name, DEFAULT_AREA, plugin_dir, goal
    )
    return guide, plugin_dir
