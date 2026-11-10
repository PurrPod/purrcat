"""utils 内部共用的 JSON / 文本写入与目录查找。"""

import json
import os


def write_json(path: str, data: dict, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def read_json(path: str, default=None):
    """读取 JSON；文件缺失或损坏时返回 default（需要区分异常的场景请自行捕获）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def find_child_dir_by_token(root: str, token: str) -> str | None:
    """在 root 下按名称子串找第一个目录（checkpoint 目录命名携带任务 id）。"""
    if not os.path.isdir(root):
        return None
    for entry in os.listdir(root):
        if token in entry:
            return os.path.join(root, entry)
    return None
