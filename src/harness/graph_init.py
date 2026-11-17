"""默认图初始化：把随包分发的 default 图播种到用户图目录。

default 是内置图，启动时要求与模板逐字一致：
缺失或内容不一致（被改动、损坏）都会用模板修复，不会被旧副本带走。
"""

from __future__ import annotations

import os
import shutil

DEFAULT_GRAPH_NAME = "default"
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "graph_templates"
)


def default_graph_template_path() -> str:
    return os.path.join(TEMPLATES_DIR, DEFAULT_GRAPH_NAME, "graph.json")


def ensure_default_graph(graphs_dir: str) -> bool:
    """确保 default/graph.json 与模板一致；返回是否写入（新建或修复）。"""
    template = default_graph_template_path()
    if not os.path.isfile(template):
        print(f"[!] 默认图模板缺失: {template}")
        return False

    target = os.path.join(graphs_dir, DEFAULT_GRAPH_NAME, "graph.json")
    template_text = _read_text(template)
    if template_text is not None and _read_text(target) == template_text:
        return False

    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(template, target)
    print(f"[+] 默认图已同步: {target}")
    return True


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None
