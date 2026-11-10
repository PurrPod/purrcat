"""Evolve 沙盒的迭代目录布局约定。"""

import os
import re

_ITERATION_RE = re.compile(r"iteration-(\d+)$")


def latest_iteration_dir(workplace_root: str) -> tuple:
    """返回 (最新迭代目录, 编号)；尚无迭代时返回 (None, 0)。"""
    latest_dir, latest_idx = None, 0
    if os.path.exists(workplace_root):
        for item in os.listdir(workplace_root):
            match = _ITERATION_RE.match(item)
            if match and int(match.group(1)) > latest_idx:
                latest_idx = int(match.group(1))
                latest_dir = os.path.join(workplace_root, item)
    return latest_dir, latest_idx


def latest_iteration_idx(workplace_root: str) -> int:
    """返回当前最大迭代编号；尚无迭代时返回 0。"""
    return latest_iteration_dir(workplace_root)[1]


def next_iteration_dir(workplace_root: str) -> tuple:
    """分配新的迭代目录 iteration-N。"""
    next_idx = latest_iteration_idx(workplace_root) + 1
    return os.path.join(workplace_root, f"iteration-{next_idx}"), next_idx


def reuse_or_next_iteration_dir(workplace_root: str, marker_filename: str) -> tuple:
    """优先复用最新迭代目录；若其中已存在 marker 文件则新开一代。"""
    latest_dir, latest_idx = latest_iteration_dir(workplace_root)
    if latest_idx > 0 and latest_dir:
        if not os.path.exists(os.path.join(latest_dir, marker_filename)):
            return latest_dir, latest_idx
    return next_iteration_dir(workplace_root)
