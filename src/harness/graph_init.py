"""默认图初始化：把随包分发的 default 图播种到用户图目录。

用户图目录中的 default 就是一张普通图，可被编辑、覆盖或删除；
本模块只在文件缺失时补一份模板，绝不覆盖已有内容。
"""

from __future__ import annotations

import os
import shutil

DEFAULT_GRAPH_NAME = "default"
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "graph_templates"
)


def ensure_default_graph(graphs_dir: str) -> bool:
    """graphs_dir 下缺少 default/graph.json 时从模板复制；返回是否新建。"""
    target = os.path.join(graphs_dir, DEFAULT_GRAPH_NAME, "graph.json")
    if os.path.exists(target):
        return False

    template = os.path.join(TEMPLATES_DIR, DEFAULT_GRAPH_NAME, "graph.json")
    if not os.path.isfile(template):
        print(f"[!] 默认图模板缺失: {template}")
        return False

    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(template, target)
    print(f"[+] 默认图已初始化: {target}")
    return True
