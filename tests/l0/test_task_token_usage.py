"""任务总 token 消耗查询（SPEC-033）。"""

from __future__ import annotations

import threading

from src.utils import task_api, task_store


class _FakeTask:
    def __init__(self, total_tokens: int):
        self.task_id = "t1"
        self.total_tokens = total_tokens
        self._lock = threading.Lock()


def test_active_task_returns_memory_value_in_real_time(monkeypatch):
    """SPEC-033 AC-1：活跃任务读内存，累加后再次请求即刷新。"""
    task = _FakeTask(321)
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {"t1": task})
    monkeypatch.setattr(task_store, "load_task_checkpoint", lambda _tid: None)

    assert task_api.get_task_token_usage("t1") == {
        "task_id": "t1",
        "total_tokens": 321,
    }

    with task._lock:
        task.total_tokens += 179

    assert task_api.get_task_token_usage("t1")["total_tokens"] == 500


def test_dormant_task_reads_checkpoint_snapshot(monkeypatch):
    """SPEC-033 AC-2：非活跃任务读 state.json 快照。"""
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {})
    monkeypatch.setattr(
        task_store,
        "load_task_checkpoint",
        lambda _tid: {"total_tokens": 2048},
    )

    assert task_api.get_task_token_usage("t2") == {
        "task_id": "t2",
        "total_tokens": 2048,
    }


def test_missing_task_returns_none(monkeypatch):
    """SPEC-033 AC-2：任务不存在时返回 None，交由接口层转 404。"""
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {})
    monkeypatch.setattr(task_store, "load_task_checkpoint", lambda _tid: None)

    assert task_api.get_task_token_usage("missing") is None
