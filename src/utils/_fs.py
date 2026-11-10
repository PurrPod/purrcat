"""utils 内部共用的 JSON / 文本写入与目录查找。"""

import json
import os


def write_json(path: str, data: dict, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def write_json_atomic(path: str, data, indent: int | None = 2) -> None:
    """先写临时文件再替换：读者只会看到完整的旧版本或新版本。

    临时文件名带 pid，多个进程写同一文件时互不覆盖。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    os.replace(tmp_path, path)


def read_jsonl(path: str, on_error=None) -> list:
    """逐行读取 JSONL；空行跳过，坏行交给 on_error 记录后继续。

    文件不存在时抛 OSError，由调用方决定容错语义。
    """
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                if on_error is not None:
                    on_error(line)
    return records


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
