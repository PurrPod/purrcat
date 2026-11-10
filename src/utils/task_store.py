"""任务 checkpoint 的磁盘读取、扫描与视图合并（不依赖 harness 运行时）。"""

import json
import os
from datetime import datetime

from src.utils._fs import find_child_dir_by_token
from src.utils.config import DATA_DIR

DEFAULT_CREATE_TIME = "2025-01-01 00:00:00"


def checkpoints_root() -> str:
    return os.path.join(DATA_DIR, "checkpoints", "task")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def checkpoint_mtime_text(path: str) -> str:
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return DEFAULT_CREATE_TIME


def build_disk_task(data: dict, fallback_create_time: str) -> dict | None:
    """checkpoint.json → 任务列表项；缺少 task_id 时返回 None。"""
    tid = data.get("task_id")
    if not tid:
        return None
    create_time = data.get("create_time", "")
    if not create_time:
        create_time = fallback_create_time
    return {
        "id": tid,
        "name": data.get("name", "Unknown"),
        "graph_name": data.get("graph_name", "default"),
        "state": data.get("state", "idle"),
        "step": data.get("step", 0),
        "expert_type": "Task",
        "create_time": create_time,
        "token_usage": data.get("token_usage", 0),
        "checkpoint_dir": data.get("checkpoint_dir", ""),
    }


def build_active_task(task) -> dict:
    return {
        "id": task.task_id,
        "name": task.task_name,
        "graph_name": getattr(task, "graph_name", "default"),
        "state": getattr(task.state, "value", task.state),  # 防御 Enum 类型
        "step": getattr(task, "step", 0),
        "expert_type": task.__class__.__name__,
        "create_time": task.create_time,
        "token_usage": getattr(task, "token_usage", 0),
        "checkpoint_dir": getattr(task, "checkpoint_dir", ""),
    }


def sort_task_summaries(items: list) -> list:
    return sorted(items, key=lambda x: str(x.get("create_time") or ""), reverse=True)


def scan_disk_tasks(base_dir: str, log=print) -> dict:
    """扫描 base_dir 下所有 checkpoint.json，返回 {task_id: 列表项}。"""
    tasks = {}
    if not os.path.exists(base_dir):
        return tasks
    for entry in os.listdir(base_dir):
        chk_path = os.path.join(base_dir, entry, "checkpoint.json")
        if not os.path.exists(chk_path):
            continue
        try:
            summary = build_disk_task(
                _read_json(chk_path), checkpoint_mtime_text(chk_path)
            )
            if summary:
                tasks[summary["id"]] = summary
        except Exception as e:
            log(f"读取历史任务 {entry} 失败: {e}")
            continue
    return tasks


def resolve_checkpoint_dir(task_id: str, task=None) -> str | None:
    if task is not None:
        return task.checkpoint_dir
    return find_child_dir_by_token(checkpoints_root(), task_id)


def load_task_checkpoint(task_id: str) -> dict | None:
    """按目录名匹配任务 id 读取 checkpoint.json，坏文件继续找下一个。"""
    base_dir = checkpoints_root()
    if not os.path.exists(base_dir):
        return None
    for entry in os.listdir(base_dir):
        if task_id not in entry:
            continue
        chk_path = os.path.join(base_dir, entry, "checkpoint.json")
        if not os.path.exists(chk_path):
            continue
        try:
            return _read_json(chk_path)
        except Exception:
            continue
    return None


def find_task_file(task_id: str, filename: str) -> str | None:
    base_dir = checkpoints_root()
    if not os.path.isdir(base_dir):
        return None
    for entry in os.listdir(base_dir):
        if task_id in entry:
            path = os.path.join(base_dir, entry, filename)
            if os.path.exists(path):
                return path
    return None


def read_log_entries(path: str) -> list:
    logs = []
    if not os.path.exists(path):
        return logs
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return logs


def read_history(task_id: str) -> list:
    path = find_task_file(task_id, "history.json")
    if not path:
        return []
    return _read_json(path)


def read_window_token(task_id: str) -> int:
    base_dir = checkpoints_root()
    if os.path.isdir(base_dir):
        for task_dir in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, task_dir, "checkpoint.json")
            if not os.path.exists(checkpoint_path):
                continue
            try:
                state = _read_json(checkpoint_path)
                if state.get("task_id") == task_id:
                    return state.get("window_token", 0)
            except Exception:
                continue
    return 0
