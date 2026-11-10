"""部署任务的内存进度与日志。"""

import threading
import time

DEPLOY_ITEMS = ("uv", "node", "sandbox", "embedding")

# 每项日志滚动保留的最大行数
MAX_LOG_LINES = 200

# item -> {"state": idle|running|success|failed, "log": [str], "finished_at": float|None}
_tasks: dict = {
    item: {"state": "idle", "log": [], "finished_at": None} for item in DEPLOY_ITEMS
}
_lock = threading.Lock()


def append_log(item: str, line: str) -> None:
    with _lock:
        task = _tasks[item]
        task["log"] = (task["log"] + [line])[-MAX_LOG_LINES:]


def begin(item: str, first_line: str) -> bool:
    """占用单项任务槽位；已在部署中返回 False（不重置日志）。"""
    with _lock:
        if _tasks[item]["state"] == "running":
            return False
        _tasks[item] = {
            "state": "running",
            "log": [first_line],
            "finished_at": None,
        }
        return True


def finish(item: str, ok: bool) -> None:
    with _lock:
        _tasks[item]["state"] = "success" if ok else "failed"
        _tasks[item]["finished_at"] = time.time()


def snapshot() -> dict:
    with _lock:
        return {
            k: {
                "state": v["state"],
                "log": list(v["log"]),
                "finished_at": v["finished_at"],
            }
            for k, v in _tasks.items()
        }
