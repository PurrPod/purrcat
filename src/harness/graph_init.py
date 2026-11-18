"""内置图初始化：把随包分发的内置图播种到用户图目录。

内置图（default / skill_eval）启动时要求与模板逐字一致：
缺失或内容不一致（被改动、损坏）都会用模板修复，不会被旧副本带走。
"""

from __future__ import annotations

import os
import shutil

DEFAULT_GRAPH_NAME = "default"
SKILL_EVAL_GRAPH_NAME = "skill_eval"
BUILTIN_GRAPH_NAMES = (DEFAULT_GRAPH_NAME, SKILL_EVAL_GRAPH_NAME)
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "graph_templates"
)


def builtin_graph_template_path(name: str) -> str:
    return os.path.join(TEMPLATES_DIR, name, "graph.json")


def is_builtin_graph(name: str) -> bool:
    return name in BUILTIN_GRAPH_NAMES


def ensure_builtin_graphs(graphs_dir: str) -> list[str]:
    """同步全部内置图，返回本次写入（新建或修复）的图名。"""
    return [name for name in BUILTIN_GRAPH_NAMES if _sync_graph(graphs_dir, name)]


def _sync_graph(graphs_dir: str, name: str) -> bool:
    template = builtin_graph_template_path(name)
    if not os.path.isfile(template):
        print(f"[!] 内置图模板缺失: {template}")
        return False

    target = os.path.join(graphs_dir, name, "graph.json")
    template_text = _read_text(template)
    if template_text is not None and _read_text(target) == template_text:
        return False

    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(template, target)
    print(f"[+] 内置图已同步: {target}")
    return True


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None
