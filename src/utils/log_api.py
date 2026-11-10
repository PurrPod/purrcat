import json
import os
from typing import Any, Dict, Optional

from src.utils._format import format_hms
from src.utils._fs import find_child_dir_by_token
from src.utils.log_format import clean_log_entry, render_log_entry

_task_log_cache = {}

__all__ = ["clean_log_entry", "format_task_log", "get_task_log_structured"]


def _checkpoints_root() -> str:
    from src.utils.config import DATA_DIR

    return os.path.join(DATA_DIR, "checkpoints", "task")


def _resolve_checkpoint_dir(task_id: str) -> Optional[str]:
    from src.harness.process import TASK_INSTANCES

    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, "checkpoint_dir"):
        return task_instance.checkpoint_dir
    return find_child_dir_by_token(_checkpoints_root(), task_id)


def get_task_log_structured(
    task_id: str, node_id: str = None, after_line: int = 0
) -> Dict[str, Any]:
    """
    获取结构化的任务日志，支持按节点过滤和增量拉取

    Args:
        task_id: 任务ID
        node_id: 可选，节点ID过滤
        after_line: 可选，返回此行数之后的日志（用于增量拉取）

    Returns:
        {
            "task_id": str,
            "total_lines": int,
            "logs": List[dict],
            "grouped_logs": Dict[str, List[dict]]  # 按节点分组
        }
    """
    checkpoint_dir = _resolve_checkpoint_dir(task_id)
    if not checkpoint_dir:
        return {"task_id": task_id, "total_lines": 0, "logs": [], "grouped_logs": {}}

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_path):
        return {"task_id": task_id, "total_lines": 0, "logs": [], "grouped_logs": {}}

    logs = []
    grouped_logs = {}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, after_line)

        for i, line in enumerate(lines[start_idx:], start=start_idx):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry["_line"] = i  # 添加行号标记，用于增量拉取
                entry["_time"] = format_hms(entry.get("timestamp", 0))
                logs.append(entry)

                # 按节点分组
                node_key = entry.get("node_id", "system")
                if node_key not in grouped_logs:
                    grouped_logs[node_key] = []
                grouped_logs[node_key].append(entry)

            except json.JSONDecodeError:
                continue

    except Exception as e:
        return {
            "task_id": task_id,
            "total_lines": 0,
            "logs": [],
            "grouped_logs": {},
            "error": str(e),
        }

    # 如果指定了节点过滤
    if node_id:
        filtered_logs = grouped_logs.get(node_id, [])
        return {
            "task_id": task_id,
            "total_lines": len(filtered_logs),
            "logs": filtered_logs,
            "grouped_logs": {node_id: filtered_logs},
        }

    return {
        "task_id": task_id,
        "total_lines": total_lines,
        "logs": logs,
        "grouped_logs": grouped_logs,
    }


def format_task_log(task_id: str, checkpoint_dir: Optional[str] = None) -> str:
    if checkpoint_dir is None:
        checkpoint_dir = _resolve_checkpoint_dir(task_id)

    if not checkpoint_dir:
        return f"Task {task_id} not found"

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_path):
        return f"No log yet (Task {task_id})"

    try:
        stat = os.stat(log_path)
        cached = _task_log_cache.get(task_id)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
    except OSError:
        pass

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return f"Read log failed (Task {task_id})"

    if not lines:
        return f"No log yet (Task {task_id})"

    output_parts = [
        f"[bold deep_sky_blue]── Task {task_id} 执行日志 ──[/bold deep_sky_blue]\n"
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        output_parts.append(render_log_entry(entry))

    result = "\n".join(output_parts)

    try:
        stat = os.stat(log_path)
        _task_log_cache[task_id] = (stat.st_mtime_ns, stat.st_size, result)
    except OSError:
        pass

    return result
