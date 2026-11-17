"""任务 checkpoint 的磁盘读取、扫描与视图合并（不依赖 harness 运行时）。"""

import json
import os
from datetime import datetime

from src.utils._fs import find_child_dir_by_token, read_jsonl
from src.utils.config import DATA_DIR

DEFAULT_CREATE_TIME = "2025-01-01 00:00:00"

# 进程重启后不可能还有任务在跑；磁盘上残留的运行态统一视为中断。
STALE_TASK_STATES = ("running", "starting")


def normalize_task_state(state) -> str:
    """把重启后不可能存在的运行态归一化为 interrupted。"""
    return "interrupted" if state in STALE_TASK_STATES else state


def normalize_node_states(node_states) -> dict:
    """节点没有中断态，落盘残留的 running 回落到 ready。"""
    if not isinstance(node_states, dict):
        return {}
    normalized = {}
    for key, value in node_states.items():
        if isinstance(value, dict):
            if value.get("state") == "running":
                value = {**value, "state": "ready"}
        elif value == "running":
            value = "ready"
        normalized[key] = value
    return normalized


def _has_running_node(node_states) -> bool:
    if not isinstance(node_states, dict):
        return False
    for value in node_states.values():
        state = value.get("state") if isinstance(value, dict) else value
        if state == "running":
            return True
    return False


def _write_json_atomic(path: str, data) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def checkpoints_root() -> str:
    return os.path.join(DATA_DIR, "checkpoints", "task")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_json_safe(path: str):
    try:
        return _read_json(path)
    except (OSError, ValueError):
        return None


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
        "state": normalize_task_state(data.get("state", "idle")),
        "step": data.get("step", 0),
        "expert_type": "Task",
        "create_time": create_time,
        "token_usage": data.get("token_usage", 0),
        "checkpoint_dir": data.get("checkpoint_dir", ""),
    }


def build_new_format_task(directory: str) -> dict | None:
    """meta.json + state.json → 任务列表项；缺少 task_id 时返回 None。"""
    meta = _read_json_safe(os.path.join(directory, "meta.json"))
    if not isinstance(meta, dict):
        return None
    tid = meta.get("task_id")
    if not tid:
        return None
    state = _read_json_safe(os.path.join(directory, "state.json")) or {}
    return {
        "id": tid,
        "name": meta.get("name", "Unknown"),
        "graph_name": meta.get("graph_name", "default"),
        "state": normalize_task_state(state.get("state", "idle")),
        "step": 0,
        "expert_type": "Task",
        "create_time": meta.get("create_time")
        or checkpoint_mtime_text(os.path.join(directory, "meta.json")),
        "token_usage": state.get("total_tokens", 0),
        "core": meta.get("core", "-"),
        "checkpoint_dir": directory,
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
    """扫描 base_dir 下的任务目录，返回 {task_id: 列表项}。

    兼容旧格式 checkpoint.json 与新格式 meta.json + state.json。
    """
    tasks = {}
    if not os.path.exists(base_dir):
        return tasks
    for entry in os.listdir(base_dir):
        directory = os.path.join(base_dir, entry)
        chk_path = os.path.join(directory, "checkpoint.json")
        try:
            if os.path.exists(chk_path):
                summary = build_disk_task(
                    _read_json(chk_path), checkpoint_mtime_text(chk_path)
                )
            else:
                summary = build_new_format_task(directory)
        except Exception as e:
            log(f"读取历史任务 {entry} 失败: {e}")
            continue
        if summary:
            tasks[summary["id"]] = summary
    return tasks


def find_task_dir(task_id: str) -> str | None:
    """按目录名匹配任务 id，返回 checkpoint 目录；找不到返回 None。

    目录命名是 `{task_name}_{task_id}`，优先精确后缀匹配，避免 task_id 恰为
    另一个任务 id 前缀时取错目录。
    """
    base_dir = checkpoints_root()
    if not os.path.isdir(base_dir):
        return None
    entries = [
        entry
        for entry in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, entry))
    ]
    for entry in entries:
        if entry == task_id or entry.endswith(f"_{task_id}"):
            return os.path.join(base_dir, entry)
    for entry in entries:
        if task_id in entry:
            return os.path.join(base_dir, entry)
    return None


def resolve_checkpoint_dir(task_id: str, task=None) -> str | None:
    if task is not None:
        return task.checkpoint_dir
    return find_child_dir_by_token(checkpoints_root(), task_id)


def load_task_checkpoint(task_id: str) -> dict | None:
    """按目录名匹配任务 id 读取任务详情，坏文件跳过。

    旧格式直接返回 checkpoint.json；新格式由 meta.json（图谱/静态信息）与
    state.json（运行状态/输出）合并成前端需要的统一结构。
    """
    directory = find_task_dir(task_id)
    if not directory:
        return None

    old_path = os.path.join(directory, "checkpoint.json")
    if os.path.exists(old_path):
        try:
            data = _read_json(old_path)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        data["state"] = normalize_task_state(data.get("state", "idle"))
        for key in ("dag_state", "node_state"):
            if isinstance(data.get(key), dict):
                data[key] = normalize_node_states(data[key])
        return data

    meta = _read_json_safe(os.path.join(directory, "meta.json"))
    state = _read_json_safe(os.path.join(directory, "state.json"))
    if not isinstance(meta, dict) and not isinstance(state, dict):
        return None
    meta = meta if isinstance(meta, dict) else {}
    state = state if isinstance(state, dict) else {}

    return {
        "task_id": meta.get("task_id") or state.get("task_id") or task_id,
        "name": meta.get("name", "Unknown"),
        "graph_name": meta.get("graph_name", "default"),
        "create_time": meta.get("create_time", ""),
        "graph": meta.get("graph", {}),
        "state": normalize_task_state(state.get("state", "idle")),
        "dag_state": normalize_node_states(
            state.get("dag_state", state.get("node_state", {}))
        ),
        "node_state": normalize_node_states(state.get("node_state", {})),
        "outputs": state.get("outputs", {}),
        "total_tokens": state.get("total_tokens", 0),
        "execution_time": state.get("execution_time", 0.0),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
    }


def reconcile_disk_task_states(base_dir: str | None = None, skip_ids=None, log=print):
    """修正重启后残留在磁盘上的运行态，返回被修正的 task_id 列表。

    只处理新格式目录（state.json 很小）；旧格式 checkpoint.json 可能很大，
    启动时不读不写，由展示层归一化。`skip_ids` 用于避开本进程内仍在运行的任务。
    """
    base_dir = base_dir or checkpoints_root()
    if not os.path.isdir(base_dir):
        return []
    skip = set(skip_ids or ())
    fixed = []
    for entry in os.listdir(base_dir):
        directory = os.path.join(base_dir, entry)
        if not os.path.isdir(directory):
            continue
        state_path = os.path.join(directory, "state.json")
        if not os.path.isfile(state_path):
            continue
        meta = _read_json_safe(os.path.join(directory, "meta.json"))
        if not isinstance(meta, dict):
            continue
        task_id = meta.get("task_id")
        if not task_id or task_id in skip:
            continue
        state = _read_json_safe(state_path)
        if not isinstance(state, dict):
            continue
        raw_dag = state.get("dag_state", {})
        raw_nodes = state.get("node_state", {})
        if (
            state.get("state") not in STALE_TASK_STATES
            and not _has_running_node(raw_dag)
            and not _has_running_node(raw_nodes)
        ):
            continue
        state["state"] = normalize_task_state(state.get("state"))
        if raw_dag:
            state["dag_state"] = normalize_node_states(raw_dag)
        if raw_nodes:
            state["node_state"] = normalize_node_states(raw_nodes)
        try:
            _write_json_atomic(state_path, state)
        except OSError as e:
            log(f"修正任务 {entry} 状态失败: {e}")
            continue
        fixed.append(task_id)
    return fixed


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
    if not os.path.exists(path):
        return []
    try:
        return read_jsonl(path)
    except OSError:
        return []


def read_history(task_id: str) -> list:
    path = find_task_file(task_id, "history.json")
    if not path:
        return []
    return _read_json(path)


def read_window_token(task_id: str) -> int:
    data = load_task_checkpoint(task_id)
    if not data:
        return 0
    return data.get("window_token", 0)
