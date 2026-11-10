"""会话目录、分支文件命名与 JSON 序列化（纯函数）。"""

from __future__ import annotations

import json
import os
from typing import Any

MAIN_BRANCH = "main"
META_FILENAME = "meta.json"
MEMO_FILENAME = "memo.json"
PLAN_FILENAME = "plan.md"


def is_session_id(value) -> bool:
    return bool(value) and str(value).startswith("session_")


def session_dir(sessions_dir: str, session_id: str) -> str:
    return os.path.join(sessions_dir, session_id)


def meta_path(sessions_dir: str, session_id: str) -> str:
    return os.path.join(session_dir(sessions_dir, session_id), META_FILENAME)


def branch_filename(branch_id: str) -> str:
    return "main.json" if branch_id == MAIN_BRANCH else f"sub_{branch_id}.json"


def branch_path(sessions_dir: str, session_id: str, branch_id: str) -> str:
    return os.path.join(
        session_dir(sessions_dir, session_id), branch_filename(branch_id)
    )


def plan_path(sessions_dir: str, session_id: str, filename: str = PLAN_FILENAME) -> str:
    return os.path.join(session_dir(sessions_dir, session_id), filename)


def memo_path(sessions_dir: str) -> str:
    return os.path.join(sessions_dir, MEMO_FILENAME)


def filter_session_index(data: dict) -> dict:
    """过滤掉非 session_ 前缀的异常数据（如 requests 空文件夹）。"""
    return {k: v for k, v in data.items() if str(k).startswith("session_")}


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_json_atomic(path: str, payload: Any) -> None:
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)
