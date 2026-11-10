"""磁盘维护任务的内存状态（单任务互斥）。"""

import threading
import time

# 每项日志最多保留 200 行
MAX_LOG_LINES = 200

_task = {"state": "idle", "kind": None, "log": [], "finished_at": None}
_task_lock = threading.Lock()


def get_task() -> dict:
    with _task_lock:
        return {
            "state": _task["state"],
            "kind": _task["kind"],
            "log": list(_task["log"]),
            "finished_at": _task["finished_at"],
        }


def append_log(line: str) -> None:
    with _task_lock:
        _task["log"] = (_task["log"] + [line])[-MAX_LOG_LINES:]


def begin(kind: str, first_line: str) -> bool:
    """占用任务槽位；已有任务在跑时返回 False（不修改状态）。"""
    with _task_lock:
        if _task["state"] == "running":
            return False
        _task.update(
            state="running",
            kind=kind,
            log=[first_line],
            finished_at=None,
        )
        return True


def finish(state: str) -> None:
    with _task_lock:
        _task["state"] = state
        _task["finished_at"] = time.time()
